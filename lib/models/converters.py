"""Converters between Pydantic extraction models and SQLAlchemy DB models."""

from typing import Any

from lib.agents.patient_extraction_agent import (
    CountryCode,
    PatientInfo,
    RaceEthnicity,
    SexAtBirth,
)
from lib.agents.variant_extraction_agent import (
    HgvsInferenceConfidence,
    Inheritance,
    Variant,
    VariantType,
    Zygosity,
)
from lib.evagg.types.base import Paper
from lib.models import PaperDB, PatientDB, VariantDB


def _enum_to_str(val: Any) -> str | None:
    """Convert an enum value to its string .value, or return None."""
    if val is None:
        return None
    if hasattr(val, 'value'):
        return val.value
    return str(val)


def _str_to_enum(val: str | None, enum_cls: type) -> Any:
    """Convert a string back to an enum, or return None."""
    if val is None:
        return None
    return enum_cls(val)


def patient_info_to_db(patient: PatientInfo, paper_id: str) -> PatientDB:
    return PatientDB(
        paper_id=paper_id,
        identifier=patient.identifier,
        sex=_enum_to_str(patient.sex),
        age_diagnosis=patient.age_diagnosis,
        age_report=patient.age_report,
        age_death=patient.age_death,
        country_of_origin=_enum_to_str(patient.country_of_origin),
        race_ethnicity=_enum_to_str(patient.race_ethnicity),
        identifier_evidence=patient.identifier_evidence,
        sex_evidence=patient.sex_evidence,
        age_diagnosis_evidence=patient.age_diagnosis_evidence,
        age_report_evidence=patient.age_report_evidence,
        age_death_evidence=patient.age_death_evidence,
        country_of_origin_evidence=patient.country_of_origin_evidence,
        race_ethnicity_evidence=patient.race_ethnicity_evidence,
    )


def patient_db_to_pydantic(patient_db: PatientDB) -> PatientInfo:
    return PatientInfo(
        identifier=patient_db.identifier or '',
        sex=_str_to_enum(patient_db.sex, SexAtBirth) or SexAtBirth.Unknown,
        age_diagnosis=patient_db.age_diagnosis,
        age_report=patient_db.age_report,
        age_death=patient_db.age_death,
        country_of_origin=_str_to_enum(patient_db.country_of_origin, CountryCode)
        or CountryCode.Unknown,
        race_ethnicity=_str_to_enum(patient_db.race_ethnicity, RaceEthnicity)
        or RaceEthnicity.Unknown,
        identifier_evidence=patient_db.identifier_evidence,
        sex_evidence=patient_db.sex_evidence,
        age_diagnosis_evidence=patient_db.age_diagnosis_evidence,
        age_report_evidence=patient_db.age_report_evidence,
        age_death_evidence=patient_db.age_death_evidence,
        country_of_origin_evidence=patient_db.country_of_origin_evidence,
        race_ethnicity_evidence=patient_db.race_ethnicity_evidence,
    )


def variant_to_db(variant: Variant, paper_id: str) -> VariantDB:
    return VariantDB(
        paper_id=paper_id,
        gene=variant.gene,
        transcript=variant.transcript,
        variant_verbatim=variant.variant_verbatim,
        genomic_coordinates=variant.genomic_coordinates,
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        hgvs_c_inferred=variant.hgvs_c_inferred,
        hgvs_p_inferred=variant.hgvs_p_inferred,
        hgvs_inference_confidence=_enum_to_str(variant.hgvs_inference_confidence),
        hgvs_inference_evidence_context=variant.hgvs_inference_evidence_context,
        variant_type=_enum_to_str(variant.variant_type),
        zygosity=_enum_to_str(variant.zygosity),
        inheritance=_enum_to_str(variant.inheritance),
        variant_type_evidence_context=variant.variant_type_evidence_context,
        variant_evidence_context=variant.variant_evidence_context,
        zygosity_evidence_context=variant.zygosity_evidence_context,
        inheritance_evidence_context=variant.inheritance_evidence_context,
    )


def variant_db_to_pydantic(variant_db: VariantDB) -> Variant:
    return Variant(
        gene=variant_db.gene or '',
        transcript=variant_db.transcript,
        variant_verbatim=variant_db.variant_verbatim,
        genomic_coordinates=variant_db.genomic_coordinates,
        hgvs_c=variant_db.hgvs_c,
        hgvs_p=variant_db.hgvs_p,
        hgvs_c_inferred=variant_db.hgvs_c_inferred,
        hgvs_p_inferred=variant_db.hgvs_p_inferred,
        hgvs_inference_confidence=_str_to_enum(
            variant_db.hgvs_inference_confidence, HgvsInferenceConfidence
        ),
        hgvs_inference_evidence_context=variant_db.hgvs_inference_evidence_context,
        variant_type=_str_to_enum(variant_db.variant_type, VariantType)
        or VariantType.unknown,
        zygosity=_str_to_enum(variant_db.zygosity, Zygosity) or Zygosity.unknown,
        inheritance=_str_to_enum(variant_db.inheritance, Inheritance)
        or Inheritance.unknown,
        variant_type_evidence_context=variant_db.variant_type_evidence_context,
        variant_evidence_context=variant_db.variant_evidence_context,
        zygosity_evidence_context=variant_db.zygosity_evidence_context,
        inheritance_evidence_context=variant_db.inheritance_evidence_context,
    )


def paper_metadata_to_db(paper: Paper, paper_db: PaperDB) -> None:
    """Copy metadata fields from a Paper dataclass onto a PaperDB row."""
    paper_db.pmid = paper.pmid
    paper_db.pmcid = paper.pmcid
    paper_db.doi = paper.doi
    paper_db.title = paper.title
    paper_db.abstract = paper.abstract
    paper_db.journal = paper.journal
    paper_db.first_author = paper.first_author
    paper_db.pub_year = paper.pub_year
    paper_db.citation = paper.citation
    paper_db.is_open_access = paper.OA
    paper_db.can_access = paper.can_access
    paper_db.license = paper.license
    paper_db.link = paper.link


def paper_db_to_metadata_dict(paper_db: PaperDB) -> dict:
    """Build a metadata dict from a PaperDB row (for UI compatibility)."""
    return {
        'id': paper_db.id,
        'pmid': paper_db.pmid,
        'pmcid': paper_db.pmcid,
        'doi': paper_db.doi,
        'title': paper_db.title,
        'abstract': paper_db.abstract,
        'journal': paper_db.journal,
        'first_author': paper_db.first_author,
        'pub_year': paper_db.pub_year,
        'citation': paper_db.citation,
        'OA': paper_db.is_open_access,
        'can_access': paper_db.can_access,
        'license': paper_db.license,
        'link': paper_db.link,
    }
