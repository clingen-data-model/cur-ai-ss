"""Direct edits from the paper chat: turning what the chat model asks for
into a proposal a curator can read, and applying it when they press Apply.

The two paths a curator has in chat stay apart (see lib.agents.chat_agent):
queueing a task asks an agent to read the paper again, and its re-run
replaces what it wrote before; a direct edit is the curator changing the data
themselves, exactly as the paper page's forms do. So each proposed edit is
stored as the request that form would send (``PatientUpdateRequest``,
``VariantCreateRequest``, ...), with the curator's chat message as its human
edit note, and Apply hands it to the function the form's endpoint calls
(lib.api.entity_edits, lib.api.phenotype_edits, or the request's own
``apply_to``). Apply writes every edit in one transaction: all or none.

Evidence is the curator's, never the model's: an edit carries a citation only
when the curator's own message holds the quote, word for word, and the code
-- not the model -- finds the block of the paper it comes from. The forms
have no citation to give, so Apply puts the quote on the evidence of each
field the edit sets, after the shared function has written it.

The chat model answers once: either the edits, or why it cannot and what to
do next. ``propose`` checks the edits it output (``prepare_edits``: against
the database, the field types and the paper's text) and either builds the
proposal the confirmation dialog shows or tells the curator what stopped it;
nothing goes back to the model to retry. Families,
individuals, variants and occurrences share one prepare and one apply,
driven by ``EntitySpec``; phenotypes have their own: they are added
unlinked (choosing an HPO term is HPO linking's job) and their link is not
edited in chat.

A proposal can only refer to rows that exist when it is made: an individual
for a family the same proposal creates is a second request, after Apply.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from lib.api.entity_edits import (
    EditError,
    add_family,
    add_individual,
    add_occurrence,
    add_variant,
    find_family,
    find_individual,
    find_occurrence,
    find_variant,
    remove_family,
    remove_individual,
    remove_occurrence,
    remove_variant,
    update_variant,
    variant_text,
)
from lib.api.phenotype_edits import (
    add_phenotype,
    find_patient,
    find_phenotype,
    remove_phenotype,
)
from lib.models import (
    FamilyDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    PhenotypeDB,
    VariantDB,
)
from lib.models.base import Base, PatchModel
from lib.models.chat_message import (
    ChatProposal,
    EditAction,
    EditEntity,
    ProposedChange,
    ProposedCitation,
    ProposedEdit,
)
from lib.models.evidence_block import (
    ATTRIBUTION_FIELDS,
    Citation,
    EvidenceBlock,
    HumanEvidenceBlock,
    verify_citations,
)
from lib.models.family import FamilyCreateRequest, FamilyUpdateRequest
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Ethnicity,
    OnsetCategory,
    PatientCreateRequest,
    PatientUpdateRequest,
    ProbandStatus,
    Race,
    RelationshipToProband,
    SexAtBirth,
    TwinType,
)
from lib.models.patient_variant_occurrences import (
    Inheritance,
    PatientVariantOccurrenceCreateRequest,
    PatientVariantOccurrenceUpdateRequest,
    TestingMethod,
    VariantInheritance,
    Zygosity,
)
from lib.models.phenotype import PhenotypeCreateRequest
from lib.models.user import UserDB
from lib.models.variant import (
    HarmonizedVariantUpdate,
    VariantCreateRequest,
    VariantType,
    VariantUpdateRequest,
)
from lib.tasks.flags import patient_label

Value = str | int | bool | list[str] | None


class FieldValue(BaseModel):
    field: str
    value: Value = None


class EditRequest(BaseModel):
    """One edit as the chat model asks for it (the propose_edits tool's
    argument). ``parent_id`` is the row a new one belongs to: the family, for
    an individual; the individual, for an occurrence or a phenotype.
    ``quote`` is the sentence the curator gave as the edit's evidence, copied
    from their message; never one the model found."""

    entity: EditEntity
    action: EditAction
    entity_id: int | None = None
    parent_id: int | None = None
    values: list[FieldValue] = Field(default_factory=list)
    quote: str | None = None


@dataclass(frozen=True)
class CuratorWords:
    """What the curator said in the exchange that led to the edits.
    ``said`` is their messages, where a quote has to come from; ``note`` is
    what every edit records as its human edit note."""

    said: str
    note: str


def curator_note(summary: str, messages: list[str]) -> str:
    """An edit's note: the chat's one line saying what was asked, then the
    curator's own messages in order, so the history reads on its own ("try
    again" alone says nothing) and their words are kept beside the model's."""
    quoted = ' / '.join(f'"{m.strip()}"' for m in messages if m.strip())
    summary = summary.strip()
    if not quoted:
        return summary or 'Requested in the paper chat'
    lead = f'{summary} -- ' if summary else ''
    return f'{lead}Curator in chat: {quoted}'


class EditProblem(ValueError):
    """Requested edits that cannot be proposed; the message lists every
    problem, for the chat model to fix and ask again."""


def _values(request: EditRequest) -> dict[str, Value]:
    return {v.field: v.value for v in request.values}


def _label(patient: PatientDB) -> str:
    return patient_label(patient.family.identifier, patient.identifier)


def _norm(text: str) -> str:
    return ' '.join(text.split()).lower()


def _dump(request: BaseModel) -> dict[str, Any]:
    """A form request as the proposal stores it: only what it sets, so a
    patch stays a patch when it is read back."""
    return request.model_dump(mode='json', exclude_unset=True)


def _citation(
    request: EditRequest,
    value: Any,
    texts: Mapping[str, str],
    curator: CuratorWords,
) -> ProposedCitation | None:
    """The citation for the curator's quote: refused unless the quote is in
    their message, and placed in the first block of the paper that holds it
    (checked as every agent citation is)."""
    if not request.quote or not request.quote.strip():
        return None
    quote = request.quote.strip()
    if _norm(quote) not in _norm(curator.said):
        raise EditProblem(
            f'the quote "{quote}" is not in your message, and evidence has to '
            'be a sentence you give; paste it from the paper'
        )
    for anchor in texts:
        block = EvidenceBlock[Any](
            value=value,
            reasoning='the sentence a direct edit rests on',
            citations=[Citation(anchor=anchor, quote=quote)],
        )
        try:
            verify_citations(block, texts)
        except ValueError:
            continue
        return ProposedCitation(anchor=anchor, quote=quote)
    raise EditProblem(
        f'the quote "{quote}" is not in the paper word for word; copy it from '
        'the PDF exactly'
    )


def _chat_evidence(value: Any, note: str, citation: ProposedCitation | None) -> dict:
    """The evidence block a chat edit writes for a field it creates: the
    curator's message as note and reasoning, and their quote, if any, as
    citation."""
    block = HumanEvidenceBlock[Any](
        value=value,
        # Where it came from; the why is the note, shown beside it, as a
        # form entry's reasoning is just "Manually entered by curator."
        reasoning='Entered by the curator through the paper chat.',
        human_edit_note=note,
        citations=(
            [Citation(anchor=citation.anchor, quote=citation.quote)] if citation else []
        ),
    )
    return block.model_dump(
        mode='json', exclude=set(ATTRIBUTION_FIELDS) | {'previous_value'}
    )


# --- the generic entities: families, individuals, variants, occurrences ------


@dataclass(frozen=True)
class EntitySpec:
    """What the chat may set on one kind of row, and the form requests that
    carry it.

    ``fields`` maps every field the chat may set to its type, which a value
    is checked against before anything is shown; a create's missing fields
    take ``defaults``. ``update_fields`` is the subset an update may change
    (what the paper page's forms change). ``harmonized`` names update fields
    that live on a variant's harmonized record: a new variant has no
    harmonized record, so its ``hgvs_c`` is the raw field of that name, while
    an update's is the harmonized one (the raw fields are the paper's text
    and the forms do not edit them). ``update_only`` fields exist only on
    the harmonized record."""

    noun: str
    row_type: type[Base]
    create_request: type[BaseModel]
    update_request: type[PatchModel]
    fields: dict[str, Any]
    update_fields: frozenset[str]
    required: frozenset[str] = frozenset()
    defaults: dict[str, Any] = field(default_factory=dict)
    harmonized: frozenset[str] = frozenset()
    update_only: frozenset[str] = frozenset()


FIELD_LABELS = {
    'identifier': 'Identifier',
    'is_obligate_carrier': 'Obligate carrier',
    'country_of_origin': 'Country of origin',
    'variant_inheritance': 'Inherited from',
    'inheritance': 'Inheritance mechanism',
    'hgvs_c': 'HGVS c.',
    'hgvs_p': 'HGVS p.',
    'hgvs_g': 'HGVS g.',
    'rsid': 'rsID',
    'caid': 'CAid',
    'gnomad_style_coordinates': 'gnomAD coordinates',
    'variant': 'Variant',
    'variant_id': 'Variant',
}


def _field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name.replace('_', ' ').capitalize())


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, list):
        return ', '.join(_display(v) or '' for v in value) or None
    return str(value)


def _wire(value: Any) -> Any:
    """A checked value as the form requests and the columns hold it."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_wire(v) for v in value]
    return value


_AGE = int | None

SPECS: dict[EditEntity, EntitySpec] = {
    EditEntity.FAMILY: EntitySpec(
        noun='family',
        row_type=FamilyDB,
        create_request=FamilyCreateRequest,
        update_request=FamilyUpdateRequest,
        fields={'identifier': str, 'consanguinity': bool},
        update_fields=frozenset({'identifier', 'consanguinity'}),
        required=frozenset({'identifier'}),
    ),
    EditEntity.PATIENT: EntitySpec(
        noun='individual',
        row_type=PatientDB,
        create_request=PatientCreateRequest,
        update_request=PatientUpdateRequest,
        fields={
            'identifier': str,
            'proband_status': ProbandStatus,
            'affected_status': AffectedStatus,
            'sex': SexAtBirth,
            'country_of_origin': CountryCode,
            'race': Race,
            'ethnicity': Ethnicity,
            'ancestry': str | None,
            'age_diagnosis': _AGE,
            'age_diagnosis_unit': AgeUnit | None,
            'age_report': _AGE,
            'age_report_unit': AgeUnit | None,
            'age_death': _AGE,
            'age_death_unit': AgeUnit | None,
            'age_onset': _AGE,
            'age_onset_unit': AgeUnit | None,
            'onset_category': OnsetCategory | None,
            'is_obligate_carrier': bool | None,
            'relationship_to_proband': RelationshipToProband | None,
            'twin_type': TwinType | None,
        },
        update_fields=frozenset(
            f for f in PatientUpdateRequest.model_fields if not f.endswith('_note')
        ),
        required=frozenset({'identifier'}),
        defaults={
            'proband_status': ProbandStatus.Unknown,
            'affected_status': AffectedStatus.Unknown,
            'sex': SexAtBirth.Unknown,
            'country_of_origin': CountryCode.Unknown,
            'race': Race.Unknown,
            'ethnicity': Ethnicity.Unknown,
        },
    ),
    EditEntity.VARIANT: EntitySpec(
        noun='variant',
        row_type=VariantDB,
        create_request=VariantCreateRequest,
        update_request=VariantUpdateRequest,
        fields={
            'variant': str | None,
            'transcript': str | None,
            'protein_accession': str | None,
            'genomic_accession': str | None,
            'lrg_accession': str | None,
            'gene_accession': str | None,
            'genomic_coordinates': str | None,
            'genome_build': str | None,
            'rsid': str | None,
            'caid': str | None,
            'hgvs_c': str | None,
            'hgvs_p': str | None,
            'hgvs_g': str | None,
            'variant_type': VariantType,
            'functional_evidence': bool,
            'main_focus': bool,
            'gnomad_style_coordinates': str | None,
        },
        update_fields=frozenset(
            {'variant_type', 'functional_evidence', 'main_focus'}
            | set(HarmonizedVariantUpdate.model_fields)
        ),
        harmonized=frozenset(HarmonizedVariantUpdate.model_fields),
        update_only=frozenset({'gnomad_style_coordinates'}),
    ),
    EditEntity.OCCURRENCE: EntitySpec(
        noun='occurrence',
        row_type=PatientVariantOccurrenceDB,
        create_request=PatientVariantOccurrenceCreateRequest,
        update_request=PatientVariantOccurrenceUpdateRequest,
        fields={
            'variant_id': int,
            'zygosity': Zygosity,
            'inheritance': Inheritance,
            'variant_inheritance': VariantInheritance,
            'testing_methods': list[TestingMethod],
            'disease_name': str | None,
        },
        update_fields=frozenset(
            {
                'zygosity',
                'inheritance',
                'variant_inheritance',
                'testing_methods',
                'disease_name',
            }
        ),
        required=frozenset({'variant_id'}),
    ),
}


def _choices(kind: Any) -> list[str] | None:
    """The values a choice field takes, for a problem message."""
    for candidate in getattr(kind, '__args__', ()) or (kind,):
        if isinstance(candidate, type) and issubclass(candidate, Enum):
            return [m.value for m in candidate]
        if getattr(candidate, '__args__', None):
            found = _choices(candidate)
            if found:
                return found
    return None


def _as_choice(raw: Value, choices: list[str]) -> Value:
    """A choice in the case its field spells it: the model writes
    'frameshift' as readily as 'Frameshift', and either means the one value.
    Anything that matches no choice is left for validation to refuse."""
    by_case = {choice.casefold(): choice for choice in choices}
    if isinstance(raw, str):
        return by_case.get(raw.casefold(), raw)
    if isinstance(raw, list):
        return [by_case.get(item.casefold(), item) for item in raw]
    return raw


def _check_values(
    spec: EntitySpec, values: dict[str, Value], allowed: set[str] | frozenset[str]
) -> dict[str, Any]:
    """Each value converted to its field's type, or EditProblem naming the
    field and, for a choice, the values it takes."""
    unknown = set(values) - set(allowed)
    if unknown:
        raise EditProblem(
            f'a {spec.noun} has no settable field(s) {sorted(unknown)}; '
            f'the fields are {sorted(allowed)}'
        )
    checked: dict[str, Any] = {}
    for name, raw in values.items():
        kind = spec.fields[name]
        choices = _choices(kind)
        try:
            checked[name] = TypeAdapter(kind).validate_python(
                _as_choice(raw, choices) if choices else raw
            )
        except ValidationError:
            hint = f'; one of {choices}' if choices else ''
            raise EditProblem(f'{name}: {raw!r} is not a valid value{hint}') from None
    methods = checked.get('testing_methods')
    if methods is not None and len(methods) > 2:
        raise EditProblem('testing_methods takes at most two methods')
    return checked


def _evidence_fields(spec: EntitySpec, names: list[str]) -> list[str]:
    """The fields among ``names`` with one evidence block of their own, where
    a chat note and quote go: not a harmonized field on an update (it keeps
    none), not testing methods (one block per method)."""
    return [
        n
        for n in names
        if n not in spec.harmonized
        and n != 'testing_methods'
        and hasattr(spec.row_type, f'{n}_evidence')
    ]


def _note_fields(update_request: type[PatchModel], names: list[str], note: str) -> dict:
    """The human edit note of each field an update changes, as the form sends
    it alongside the value (testing methods have a note of their own)."""
    notes = {
        (
            'testing_methods_note' if n == 'testing_methods' else f'{n}_human_edit_note'
        ): note
        for n in names
    }
    return {k: v for k, v in notes.items() if k in update_request.model_fields}


@dataclass
class _Target:
    """An existing row a generic edit is about, as the card names it."""

    row: Base
    label: str
    owner_label: str | None


def _find(session: Session, paper_id: int, entity: EditEntity, row_id: int) -> _Target:
    if entity is EditEntity.FAMILY:
        family = find_family(session, paper_id, row_id)
        return _Target(family, family.identifier, None)
    if entity is EditEntity.PATIENT:
        patient = find_individual(session, paper_id, row_id)
        return _Target(patient, patient.identifier, patient.family.identifier)
    if entity is EditEntity.VARIANT:
        variant = find_variant(session, paper_id, row_id)
        return _Target(variant, variant_text(variant), None)
    occurrence = find_occurrence(session, paper_id, row_id)
    return _Target(
        occurrence, variant_text(occurrence.variant), _label(occurrence.patient)
    )


def _current(row: Base, spec: EntitySpec, name: str) -> Any:
    if name in spec.harmonized:
        hv = getattr(row, 'harmonized_variant', None)
        return getattr(hv, name, None) if hv is not None else None
    return getattr(row, name, None)


def _prepare_create(
    session: Session,
    paper_id: int,
    request: EditRequest,
    spec: EntitySpec,
    checked: dict[str, Any],
) -> tuple[BaseModel, str, str | None]:
    """The form's create request for a new row, with how the card names the
    row and its owner; EditProblem for a row that cannot be added."""
    values = {k: _wire(v) for k, v in checked.items()}
    entity = request.entity
    if entity is EditEntity.FAMILY:
        identifier = values['identifier']
        taken = session.query(FamilyDB).filter(
            FamilyDB.paper_id == paper_id, FamilyDB.identifier == identifier
        )
        if taken.first() is not None:
            raise EditProblem(f'the paper already has a family "{identifier}"')
        return FamilyCreateRequest(**values), identifier, None
    if entity is EditEntity.PATIENT:
        if request.parent_id is None:
            raise EditProblem('a new individual needs parent_id, the family')
        family = find_family(session, paper_id, request.parent_id)
        identifier = values['identifier']
        if any(p.identifier == identifier for p in family.patients):
            raise EditProblem(f'{family.identifier} already has "{identifier}"')
        defaults = {k: _wire(v) for k, v in spec.defaults.items()}
        create = PatientCreateRequest(**{**defaults, **values, 'family_id': family.id})
        return create, identifier, family.identifier
    if entity is EditEntity.VARIANT:
        names = ('variant', 'hgvs_c', 'hgvs_p', 'hgvs_g', 'rsid')
        label = next((values[n] for n in names if values.get(n)), None)
        if label is None:
            raise EditProblem(
                'a new variant needs at least one of variant, hgvs_c, hgvs_p, '
                'hgvs_g or rsid'
            )
        return VariantCreateRequest(**values), label, None
    if request.parent_id is None:
        raise EditProblem('a new occurrence needs parent_id, the individual')
    patient = find_individual(session, paper_id, request.parent_id)
    variant = find_variant(session, paper_id, values['variant_id'])
    duplicate = session.query(PatientVariantOccurrenceDB).filter(
        PatientVariantOccurrenceDB.patient_id == patient.id,
        PatientVariantOccurrenceDB.variant_id == variant.id,
    )
    if duplicate.first() is not None:
        raise EditProblem(f'{_label(patient)} already carries {variant_text(variant)}')
    occurrence = PatientVariantOccurrenceCreateRequest(
        **{**values, 'patient_id': patient.id}
    )
    return occurrence, variant_text(variant), _label(patient)


def _prepare_generic(
    session: Session,
    paper_id: int,
    request: EditRequest,
    texts: Mapping[str, str],
    curator: CuratorWords,
) -> ProposedEdit:
    spec = SPECS[request.entity]
    values = _values(request)

    if request.action is EditAction.CREATE:
        checked = _check_values(spec, values, set(spec.fields) - spec.update_only)
        missing = spec.required - set(checked)
        if missing:
            raise EditProblem(f'a new {spec.noun} needs {sorted(missing)}')
        create, label, owner_label = _prepare_create(
            session, paper_id, request, spec, checked
        )
        return ProposedEdit(
            entity=request.entity,
            action=request.action,
            label=label,
            owner_label=owner_label,
            changes=[
                ProposedChange(field=k, label=_field_label(k), new=_display(v))
                for k, v in checked.items()
                if k != 'variant_id'  # the label names the variant
            ],
            citation=_citation(request, label, texts, curator),
            payload={'request': _dump(create)},
        )

    if request.entity_id is None:
        raise EditProblem(f'{request.action.value} needs entity_id, the {spec.noun}')
    target = _find(session, paper_id, request.entity, request.entity_id)

    if request.action is EditAction.DELETE:
        if values:
            raise EditProblem('a delete takes no values')
        if isinstance(target.row, FamilyDB) and target.row.patients:
            raise EditProblem(
                f'{target.label} still has {len(target.row.patients)} '
                'individual(s); delete all individuals in the family first, '
                'then the family'
            )
        return ProposedEdit(
            entity=request.entity,
            action=request.action,
            entity_id=request.entity_id,
            label=target.label,
            owner_label=target.owner_label,
            changes=_also_removed(session, target.row),
            citation=_citation(request, target.label, texts, curator),
        )

    if not values:
        raise EditProblem('an update needs at least one value to change')
    checked = _check_values(spec, values, spec.update_fields)
    harmonized = sorted(set(checked) & spec.harmonized)
    if harmonized and getattr(target.row, 'harmonized_variant', None) is None:
        raise EditProblem(
            f'{harmonized} are harmonized fields, and this variant has not been '
            'harmonized yet'
        )
    # A value the row already holds is left out rather than refused: the model
    # restates a companion field (the unit beside a new age) as a matter of
    # course. Only an update that would change nothing is a problem.
    unchanged = {
        name: new
        for name, new in checked.items()
        if _wire(_current(target.row, spec, name)) == _wire(new)
    }
    if unchanged == checked:
        name, new = next(iter(checked.items()))
        raise EditProblem(f'{name} is already {_display(new)!r}')
    checked = {name: new for name, new in checked.items() if name not in unchanged}
    harmonized = sorted(set(checked) & spec.harmonized)
    changes = []
    for name, new in checked.items():
        old = _current(target.row, spec, name)
        changes.append(
            ProposedChange(
                field=name,
                label=_field_label(name),
                old=_display(old),
                new=_display(new),
            )
        )
    citation = _citation(request, None, texts, curator)
    if citation and not _evidence_fields(spec, list(checked)):
        raise EditProblem(
            f'{sorted(checked)} keep no evidence, so a quote cannot be attached; '
            'leave it out'
        )

    values = {k: _wire(v) for k, v in checked.items()}
    own = {k: v for k, v in values.items() if k not in spec.harmonized}
    fields: dict[str, Any] = {
        **own,
        **_note_fields(spec.update_request, list(own), curator.note),
    }
    if harmonized:
        fields['harmonized_variant'] = {k: values[k] for k in harmonized}
    update = spec.update_request.model_validate(fields)
    return ProposedEdit(
        entity=request.entity,
        action=request.action,
        entity_id=request.entity_id,
        label=target.label,
        owner_label=target.owner_label,
        changes=changes,
        citation=citation,
        payload={'request': _dump(update)},
    )


def _apply_generic(
    session: Session, paper_id: int, edit: ProposedEdit, editor: UserDB, note: str
) -> None:
    spec = SPECS[edit.entity]
    entity = edit.entity
    request = edit.payload.get('request', {})
    set_fields = [c.field for c in edit.changes]

    if edit.action is EditAction.CREATE:
        row: Base
        if entity is EditEntity.FAMILY:
            row = add_family(
                session,
                paper_id=paper_id,
                request=FamilyCreateRequest.model_validate(request),
                editor=editor,
            )
        elif entity is EditEntity.PATIENT:
            row = add_individual(
                session,
                paper_id=paper_id,
                request=PatientCreateRequest.model_validate(request),
                editor=editor,
            )
        elif entity is EditEntity.VARIANT:
            row = add_variant(
                session,
                paper_id=paper_id,
                request=VariantCreateRequest.model_validate(request),
                editor=editor,
            )
        else:
            occurrence = add_occurrence(
                session,
                paper_id=paper_id,
                request=PatientVariantOccurrenceCreateRequest.model_validate(request),
                editor=editor,
            )
            occurrence.testing_methods_evidence = [
                _chat_evidence(m, note, edit.citation)
                for m in occurrence.testing_methods
            ]
            row = occurrence
        # The forms' rows say "Manually entered by curator"; a chat row says
        # which message entered each field the curator set, and their quote.
        for name in _evidence_fields(spec, set_fields):
            setattr(
                row,
                f'{name}_evidence',
                _chat_evidence(getattr(row, name), note, edit.citation),
            )
        session.flush()
        return

    entity_id = edit.entity_id
    assert entity_id is not None
    if edit.action is EditAction.DELETE:
        if entity is EditEntity.FAMILY:
            remove_family(
                session, paper_id=paper_id, family_id=entity_id, editor=editor
            )
        elif entity is EditEntity.PATIENT:
            remove_individual(
                session, paper_id=paper_id, patient_id=entity_id, editor=editor
            )
        elif entity is EditEntity.VARIANT:
            remove_variant(
                session, paper_id=paper_id, variant_id=entity_id, editor=editor
            )
        else:
            remove_occurrence(
                session, paper_id=paper_id, occurrence_id=entity_id, editor=editor
            )
        return

    target = _find(session, paper_id, entity, entity_id)
    if entity is EditEntity.VARIANT:
        update_variant(
            session,
            paper_id=paper_id,
            variant_id=entity_id,
            request=VariantUpdateRequest.model_validate(request),
            editor=editor,
        )
    else:
        spec.update_request.model_validate(request).apply_to(
            target.row, editor, session
        )
    # The form has no citation to send: the curator's quote replaces the
    # citations that supported the old value. The extraction's reasoning
    # stays, as it does for a form edit, beside the note.
    if edit.citation is not None:
        for name in _evidence_fields(spec, set_fields):
            evidence = dict(getattr(target.row, f'{name}_evidence') or {})
            if evidence:
                evidence['citations'] = [edit.citation.model_dump()]
                setattr(target.row, f'{name}_evidence', evidence)
    session.flush()


# --- phenotypes ---------------------------------------------------------------


def _prepare_phenotype(
    session: Session,
    paper_id: int,
    request: EditRequest,
    texts: Mapping[str, str],
    curator: CuratorWords,
) -> ProposedEdit:
    values = _values(request)
    if request.action is EditAction.UPDATE:
        # Choosing an ontology term is HPO linking's job, not the chat's.
        raise EditProblem(
            "a phenotype's HPO term isn't changed in chat; use the HPO picker "
            'on the paper page, or ask me to re-run HPO linking for it'
        )

    if request.action is EditAction.CREATE:
        if request.parent_id is None:
            raise EditProblem('a new phenotype needs parent_id, the individual')
        patient = find_patient(session, paper_id, request.parent_id)
        unknown = set(values) - {'concept'}
        if unknown:
            raise EditProblem(
                'a new phenotype is added without an HPO term; link it with '
                'the HPO picker on the paper page'
            )
        raw = values.get('concept')
        concept = raw.strip() if isinstance(raw, str) else ''
        if not concept:
            raise EditProblem('a new phenotype needs a "concept" value')
        existing = (
            session.query(PhenotypeDB)
            .filter(PhenotypeDB.patient_id == patient.id)
            .all()
        )
        if any(p.concept.strip().lower() == concept.lower() for p in existing):
            raise EditProblem(f'{_label(patient)} already has "{concept}"')
        return ProposedEdit(
            entity=EditEntity.PHENOTYPE,
            action=EditAction.CREATE,
            label=concept,
            owner_label=_label(patient),
            changes=[
                ProposedChange(field='concept', label='Phenotype', new=concept),
                ProposedChange(field='hpo', label='HPO term', new=None),
            ],
            citation=_citation(request, concept, texts, curator),
            payload={
                'patient_id': patient.id,
                'request': _dump(PhenotypeCreateRequest(concept=concept)),
            },
        )

    if request.entity_id is None:
        raise EditProblem(f'{request.action.value} needs entity_id, the phenotype')
    phenotype = find_phenotype(session, paper_id, request.entity_id)
    owner = _label(phenotype.patient)
    if request.action is EditAction.DELETE:
        return ProposedEdit(
            entity=EditEntity.PHENOTYPE,
            action=EditAction.DELETE,
            entity_id=phenotype.id,
            label=phenotype.concept,
            owner_label=owner,
            citation=_citation(request, phenotype.concept, texts, curator),
        )

    raise EditProblem(f'unknown action {request.action}')


def _apply_phenotype(
    session: Session, paper_id: int, edit: ProposedEdit, editor: UserDB, note: str
) -> None:
    if edit.action is EditAction.CREATE:
        create = PhenotypeCreateRequest.model_validate(edit.payload['request'])
        add_phenotype(
            session,
            paper_id=paper_id,
            patient_id=edit.payload['patient_id'],
            concept=create.concept,
            hpo_id=None,
            editor=editor,
            evidence=_chat_evidence(create.concept, note, edit.citation),
        )
        return
    assert edit.entity_id is not None
    remove_phenotype(
        session, paper_id=paper_id, phenotype_id=edit.entity_id, editor=editor
    )


# --- the registry ---------------------------------------------------------------

Prepare = Callable[
    [Session, int, EditRequest, Mapping[str, str], CuratorWords], ProposedEdit
]
Apply = Callable[[Session, int, ProposedEdit, UserDB, str], None]

EDITORS: dict[EditEntity, tuple[Prepare, Apply]] = {
    EditEntity.FAMILY: (_prepare_generic, _apply_generic),
    EditEntity.PATIENT: (_prepare_generic, _apply_generic),
    EditEntity.VARIANT: (_prepare_generic, _apply_generic),
    EditEntity.OCCURRENCE: (_prepare_generic, _apply_generic),
    EditEntity.PHENOTYPE: (_prepare_phenotype, _apply_phenotype),
}


def _also_removed(session: Session, row: Base) -> list[ProposedChange]:
    """What deleting ``row`` takes with it, for the dialog to say: an
    individual's occurrences and phenotypes, a variant's occurrences."""
    parts: list[str] = []
    if isinstance(row, PatientDB):
        occurrences = (
            session.query(PatientVariantOccurrenceDB)
            .filter(PatientVariantOccurrenceDB.patient_id == row.id)
            .count()
        )
        phenotypes = (
            session.query(PhenotypeDB).filter(PhenotypeDB.patient_id == row.id).count()
        )
        parts = [
            f'{occurrences} occurrence(s)' if occurrences else '',
            f'{phenotypes} phenotype(s)' if phenotypes else '',
        ]
    elif isinstance(row, VariantDB):
        occurrences = (
            session.query(PatientVariantOccurrenceDB)
            .filter(PatientVariantOccurrenceDB.variant_id == row.id)
            .count()
        )
        parts = [f'{occurrences} occurrence(s)' if occurrences else '']
    text = ' and '.join(p for p in parts if p)
    return (
        [ProposedChange(field='also_removes', label='Also removes', new=text)]
        if text
        else []
    )


def _owners(session: Session, edit: ProposedEdit) -> tuple[int | None, int | None]:
    """The individual and the variant an occurrence or phenotype edit hangs
    off (a new row's from its request, an existing row's from the row)."""
    request = edit.payload.get('request', {})
    if edit.entity is EditEntity.OCCURRENCE:
        if edit.entity_id is None:
            return request.get('patient_id'), request.get('variant_id')
        occurrence = session.get(PatientVariantOccurrenceDB, edit.entity_id)
        return (
            (occurrence.patient_id, occurrence.variant_id)
            if occurrence
            else (None, None)
        )
    if edit.entity is EditEntity.PHENOTYPE:
        if edit.entity_id is None:
            return edit.payload.get('patient_id'), None
        phenotype = session.get(PhenotypeDB, edit.entity_id)
        return (phenotype.patient_id if phenotype else None), None
    return None, None


def _settle_cascades(session: Session, edits: list[ProposedEdit]) -> list[ProposedEdit]:
    """Deleting an individual takes their occurrences and phenotypes, and
    deleting a variant its occurrences, so a delete of one of those in the
    same request is already done: it is dropped (Apply would otherwise find
    the row gone and undo everything). Any other change to a row the request
    deletes cannot mean anything, and is refused."""
    gone = {
        (edit.entity, edit.entity_id)
        for edit in edits
        if edit.action is EditAction.DELETE
        and edit.entity in (EditEntity.PATIENT, EditEntity.VARIANT)
    }
    if not gone:
        return edits
    kept: list[ProposedEdit] = []
    problems: list[str] = []
    for edit in edits:
        if (
            edit.action is not EditAction.DELETE
            and (edit.entity, edit.entity_id) in gone
        ):
            problems.append(
                f'{edit.label} is deleted by this request, so it cannot also be changed'
            )
            continue
        patient_id, variant_id = _owners(session, edit)
        removed_with = (EditEntity.PATIENT, patient_id) in gone or (
            EditEntity.VARIANT,
            variant_id,
        ) in gone
        if not removed_with:
            kept.append(edit)
        elif edit.action is not EditAction.DELETE:
            problems.append(
                f'{edit.label} belongs to a row this request deletes, so it cannot '
                'be added or changed'
            )
    if problems:
        raise EditProblem('\n'.join(f'- {p}' for p in problems))
    return kept


def prepare_edits(
    session: Session,
    paper_id: int,
    requests: list[EditRequest],
    texts: Mapping[str, str],
    curator: CuratorWords,
) -> list[ProposedEdit]:
    """The confirmation card's edits, or EditProblem naming every request
    that cannot be proposed (numbered from 1, as the model sent them)."""
    if not requests:
        raise EditProblem('no edits given')
    edits: list[ProposedEdit] = []
    problems: list[str] = []
    for request in requests:
        prepare, _ = EDITORS[request.entity]
        try:
            edits.append(prepare(session, paper_id, request, texts, curator))
        except EditError as exc:
            problems.append(exc.detail)
        except ValueError as exc:  # EditProblem, and pydantic's ValidationError
            problems.append(str(exc))
    if problems:
        raise EditProblem('\n'.join(f'- {p}' for p in problems))
    return _settle_cascades(session, edits)


def propose(
    session: Session,
    paper_id: int,
    requests: list[EditRequest],
    texts: Mapping[str, str],
    curator: CuratorWords,
) -> tuple[str, ChatProposal | None]:
    """The chat's reply to edits its model output, and the proposal to
    confirm when every edit checks out. One pass: a problem is not sent back
    to the model to fix, but told to the curator, with nothing proposed --
    the model already had its chance to say it could not."""
    try:
        edits = prepare_edits(session, paper_id, requests, texts, curator)
    except EditProblem as exc:
        return (
            f"I couldn't propose {'that change' if len(requests) == 1 else 'those changes'}"
            f', and nothing was changed:\n{exc}',
            None,
        )
    count = len(edits)
    reply = (
        "Here's the change I'd make. Review it and confirm to make it."
        if count == 1
        else f"Here are the {count} changes I'd make. Review them and confirm "
        'to make them all.'
    )
    return reply, ChatProposal(request=curator.note, edits=edits)


def _refuse_stale(session: Session, paper_id: int, proposal: ChatProposal) -> None:
    """An update shows each field's value as it was when proposed. If one has
    changed since (a form edit, another proposal), confirming would overwrite
    that change unseen, so the proposal is refused instead."""
    stale = []
    for edit in proposal.edits:
        if edit.action is not EditAction.UPDATE or edit.entity not in SPECS:
            continue
        assert edit.entity_id is not None
        target = _find(session, paper_id, edit.entity, edit.entity_id)
        spec = SPECS[edit.entity]
        for change in edit.changes:
            now = _display(_current(target.row, spec, change.field))
            if now != change.old:
                stale.append(
                    f'{target.label} {change.label} is now {now or "empty"}, '
                    f'not {change.old or "empty"}'
                )
    if stale:
        raise EditError(409, '; '.join(stale))


def apply_edits(
    session: Session, paper_id: int, proposal: ChatProposal, editor: UserDB
) -> None:
    """Write every edit of the proposal as ``editor``, in order. Raises
    EditError when one no longer applies (a row since deleted, a family
    since given members); the caller rolls back, so it is all or none."""
    note = proposal.request or 'Requested in the paper chat'
    _refuse_stale(session, paper_id, proposal)
    for edit in proposal.edits:
        _, apply = EDITORS[edit.entity]
        try:
            apply(session, paper_id, edit, editor, note)
        except ValidationError as exc:
            raise EditError(409, str(exc)) from exc
