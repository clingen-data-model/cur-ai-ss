from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.models import PatientDB, PedigreeDB, VariantDB
from lib.models.evidence_block import ReasoningBlock
from lib.models.patient import Patient
from lib.models.patient_variant_link import PatientVariantLink, PatientVariantLinkDB
from lib.models.phenotype import (
    ExtractedPhenotype,
    HpoDB,
    HPOTerm,
    PhenotypeDB,
)
from lib.models.variant import (
    HarmonizedVariant,
    HarmonizedVariantDB,
    Variant,
)


def patient_to_db(paper_id: int, patient: Patient) -> PatientDB:
    """Convert a Patient to PatientDB, splitting values from evidence."""
    kwargs = {
        'paper_id': paper_id,
    }

    # Extract values and evidence blocks for each field
    for field_name in Patient.model_fields:
        field_value = getattr(patient, field_name)
        kwargs[field_name] = field_value.value
        kwargs[f'{field_name}_evidence'] = field_value.model_dump()

    return PatientDB(**kwargs)


def pedigree_to_db(paper_id: int, pedigree: PedigreeExtractionOutput) -> PedigreeDB:
    """Convert PedigreeExtractionOutput to PedigreeDB."""
    return PedigreeDB(
        paper_id=paper_id,
        image_id=pedigree.image_id,
        description=pedigree.description,
    )


def phenotype_to_db(paper_id: int, phenotype: ExtractedPhenotype) -> PhenotypeDB:
    """Convert ExtractedPhenotype to PhenotypeDB, extracting values and evidence from EvidenceBlock."""
    return PhenotypeDB(
        paper_id=paper_id,
        patient_id=phenotype.patient_id,
        concept=phenotype.concept.value,
        concept_evidence=phenotype.concept.model_dump(),
        negated=phenotype.negated,
        uncertain=phenotype.uncertain,
        family_history=phenotype.family_history,
        onset=phenotype.onset,
        location=phenotype.location,
        severity=phenotype.severity,
        modifier=phenotype.modifier,
    )


def hpo_to_db(
    phenotype_id: int,
    hpo: ReasoningBlock[HPOTerm | None],
) -> HpoDB:
    """Convert an HPO ReasoningBlock to HpoDB, storing ID, name, and reasoning separately."""
    return HpoDB(
        phenotype_id=phenotype_id,
        hpo_id=hpo.value.id if hpo.value else None,
        hpo_name=hpo.value.name if hpo.value else None,
        reasoning=hpo.reasoning,
    )


def variant_to_db(paper_id: int, variant: Variant) -> VariantDB:
    """Convert Variant to VariantDB, extracting values and evidence from EvidenceBlocks."""
    kwargs = {
        'paper_id': paper_id,
    }

    # All fields except gene have evidence blocks
    evidence_fields = [
        'variant',
        'transcript',
        'protein_accession',
        'genomic_accession',
        'lrg_accession',
        'gene_accession',
        'genomic_coordinates',
        'genome_build',
        'rsid',
        'caid',
        'hgvs_c',
        'hgvs_p',
        'hgvs_g',
        'variant_type',
        'functional_evidence',
    ]

    for field_name in evidence_fields:
        field_value = getattr(variant, field_name)
        kwargs[field_name] = field_value.value
        kwargs[f'{field_name}_evidence'] = field_value.model_dump()

    return VariantDB(**kwargs)


def harmonized_variant_to_db(
    variant_id: int, harmonized_variant: ReasoningBlock[HarmonizedVariant]
) -> HarmonizedVariantDB:
    """Convert ReasoningBlock[HarmonizedVariant] to HarmonizedVariantDB."""
    data = harmonized_variant.value
    return HarmonizedVariantDB(
        variant_id=variant_id,
        gnomad_style_coordinates=data.gnomad_style_coordinates if data else None,
        rsid=data.rsid if data else None,
        caid=data.caid if data else None,
        hgvs_c=data.hgvs_c if data else None,
        hgvs_p=data.hgvs_p if data else None,
        hgvs_g=data.hgvs_g if data else None,
        reasoning=harmonized_variant.reasoning,
    )


def patient_variant_link_to_db(
    paper_id: int, link: PatientVariantLink
) -> PatientVariantLinkDB:
    """Convert PatientVariantLink to PatientVariantLinkDB, extracting values and evidence."""
    return PatientVariantLinkDB(
        paper_id=paper_id,
        patient_id=link.patient_id,
        variant_id=link.variant_id,
        zygosity=link.zygosity.value.value,
        zygosity_evidence=link.zygosity.model_dump(),
        inheritance=link.inheritance.value.value,
        inheritance_evidence=link.inheritance.model_dump(),
        testing_methods=[m.value.value for m in link.testing_methods],
        testing_methods_evidence=[m.model_dump() for m in link.testing_methods],
    )
