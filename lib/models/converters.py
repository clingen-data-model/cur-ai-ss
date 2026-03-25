from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.models import PatientDB, PedigreeDB, VariantDB
from lib.models.evidence_block import ReasoningBlock
from lib.models.patient import Patient
from lib.models.patient_variant_link import PatientVariantLink, PatientVariantLinkDB
from lib.models.phenotype import (
    ExtractedPhenotype,
    ExtractedPhenotypeDB,
    HpoDB,
    HPOTerm,
)
from lib.models.variant import HarmonizedVariant, HarmonizedVariantDB, Variant


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


def phenotype_to_db(
    paper_id: int, phenotype: ExtractedPhenotype
) -> ExtractedPhenotypeDB:
    """Convert ExtractedPhenotype to ExtractedPhenotypeDB, extracting values and evidence from EvidenceBlock."""
    return ExtractedPhenotypeDB(
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
    """Convert an HPO EvidenceBlock to HpoDB, storing the HPOTerm atomically and the full evidence block."""
    return HpoDB(
        phenotype_id=phenotype_id,
        hpo_term=hpo.value.model_dump() if hpo.value else None,
        hpo_evidence=hpo.model_dump(),
    )


def variant_to_db(paper_id: int, gene_symbol: str, variant: Variant) -> VariantDB:
    """Convert Variant to VariantDB, extracting values and evidence from EvidenceBlocks."""
    kwargs = {
        'paper_id': paper_id,
        'gene_symbol': gene_symbol,
    }

    # All fields except gene have evidence blocks
    evidence_fields = [
        'transcript',
        'protein_accession',
        'genomic_accession',
        'lrg_accession',
        'gene_accession',
        'genomic_coordinates',
        'genome_build',
        'rsid',
        'caid',
        'variant',
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


def harmonized_variant_to_db(variant: HarmonizedVariant) -> HarmonizedVariantDB:
    """Convert HarmonizedVariant to HarmonizedVariantDB."""
    return HarmonizedVariantDB(
        variant_id=variant.variant_id,
        gnomad_style_coordinates=variant.gnomad_style_coordinates,
        rsid=variant.rsid,
        caid=variant.caid,
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        hgvs_g=variant.hgvs_g,
        reasoning=variant.reasoning,
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
