from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.models import ExtractedVariantDB, PatientDB, PedigreeDB
from lib.models.evidence_block import ReasoningBlock
from lib.models.patient import Patient
from lib.models.phenotype import (
    ExtractedPhenotype,
    ExtractedPhenotypeDB,
    HpoDB,
    HPOTerm,
)
from lib.models.variant import ExtractedVariant, HarmonizedVariant, HarmonizedVariantDB


def patient_to_db(paper_id: str, patient_idx: int, patient: Patient) -> PatientDB:
    """Convert a Patient to PatientDB, splitting values from evidence."""
    kwargs = {
        'paper_id': paper_id,
        'patient_idx': patient_idx,
    }

    # Extract values and evidence blocks for each field
    for field_name in Patient.model_fields:
        field_value = getattr(patient, field_name)
        kwargs[field_name] = field_value.value
        kwargs[f'{field_name}_evidence'] = field_value.model_dump()

    return PatientDB(**kwargs)


def pedigree_to_db(paper_id: str, pedigree: PedigreeExtractionOutput) -> PedigreeDB:
    """Convert PedigreeExtractionOutput to PedigreeDB."""
    return PedigreeDB(
        paper_id=paper_id,
        image_id=pedigree.image_id,
        description=pedigree.description,
    )


def phenotype_to_db(
    paper_id: str, phenotype_idx: int, phenotype: ExtractedPhenotype
) -> ExtractedPhenotypeDB:
    """Convert ExtractedPhenotype to ExtractedPhenotypeDB, extracting values and evidence from EvidenceBlock."""
    return ExtractedPhenotypeDB(
        paper_id=paper_id,
        patient_idx=phenotype.patient_idx,
        phenotype_idx=phenotype_idx,
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
    paper_id: str,
    patient_idx: int,
    phenotype_idx: int,
    hpo: ReasoningBlock[HPOTerm | None],
) -> HpoDB:
    """Convert an HPO EvidenceBlock to HpoDB, storing the HPOTerm atomically and the full evidence block."""
    return HpoDB(
        paper_id=paper_id,
        patient_idx=patient_idx,
        phenotype_idx=phenotype_idx,
        hpo_term=hpo.value.model_dump() if hpo.value else None,
        hpo_evidence=hpo.model_dump(),
    )


def variant_to_db(
    paper_id: str, variant_idx: int, variant: ExtractedVariant
) -> ExtractedVariantDB:
    """Convert Variant to ExtractedVariantDB, extracting values and evidence from EvidenceBlocks."""
    kwargs = {
        'paper_id': paper_id,
        'variant_idx': variant_idx,
        'gene': variant.gene,
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

    return ExtractedVariantDB(**kwargs)


def harmonized_variant_to_db(
    paper_id: str, variant_idx: int, variant: HarmonizedVariant
) -> HarmonizedVariantDB:
    """Convert HarmonizedVariant to HarmonizedVariantDB."""
    return HarmonizedVariantDB(
        paper_id=paper_id,
        variant_idx=variant_idx,
        gnomad_style_coordinates=variant.gnomad_style_coordinates,
        rsid=variant.rsid,
        caid=variant.caid,
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        hgvs_g=variant.hgvs_g,
        reasoning=variant.reasoning,
    )
