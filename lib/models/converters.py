"""Converters between agent Pydantic models and DB models."""

from enum import Enum
from typing import Optional, Type, TypeVar, overload

from lib.agents.paper_extraction_agent import PaperExtractionOutput
from lib.agents.patient_extraction_agent import (
    CountryCode,
    PatientInfo,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.agents.variant_extraction_agent import Variant
from lib.models import PaperDB, PatientDB, PatientResp, VariantDB

E = TypeVar('E', bound=Enum)


def _enum_to_str(val: Optional[Enum]) -> Optional[str]:
    if val is None:
        return None
    return val.value


@overload
def _str_to_enum(val: str, enum_cls: Type[E]) -> E: ...


@overload
def _str_to_enum(val: Optional[str], enum_cls: Type[E]) -> Optional[E]: ...


def _str_to_enum(val: Optional[str], enum_cls: Type[E]) -> Optional[E]:
    if val is None:
        return None
    return enum_cls(val)


# ---------------------------------------------------------------------------
# Patient converters
# ---------------------------------------------------------------------------


def patient_info_to_db(patient: PatientInfo, paper_id: str) -> PatientDB:
    return PatientDB(
        paper_id=paper_id,
        identifier=patient.identifier,
        proband_status=_enum_to_str(patient.proband_status),
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


def patient_resp_to_pydantic(pr: PatientResp) -> PatientInfo:
    return PatientInfo(
        identifier=pr.identifier,
        proband_status=_str_to_enum(
            pr.proband_status or ProbandStatus.Unknown.value, ProbandStatus
        ),
        sex=_str_to_enum(pr.sex or SexAtBirth.Unknown.value, SexAtBirth),
        age_diagnosis=pr.age_diagnosis,
        age_report=pr.age_report,
        age_death=pr.age_death,
        country_of_origin=_str_to_enum(
            pr.country_of_origin or CountryCode.Unknown.value, CountryCode
        ),
        race_ethnicity=_str_to_enum(
            pr.race_ethnicity or RaceEthnicity.Unknown.value, RaceEthnicity
        ),
        identifier_evidence=pr.identifier_evidence,
        sex_evidence=pr.sex_evidence,
        age_diagnosis_evidence=pr.age_diagnosis_evidence,
        age_report_evidence=pr.age_report_evidence,
        age_death_evidence=pr.age_death_evidence,
        country_of_origin_evidence=pr.country_of_origin_evidence,
        race_ethnicity_evidence=pr.race_ethnicity_evidence,
    )


# ---------------------------------------------------------------------------
# Variant converters
# ---------------------------------------------------------------------------


def variant_to_db(variant: Variant, paper_id: str) -> VariantDB:
    return VariantDB(
        paper_id=paper_id,
        gene=variant.gene,
        transcript=variant.transcript,
        protein_accession=variant.protein_accession,
        genomic_accession=variant.genomic_accession,
        lrg_accession=variant.lrg_accession,
        gene_accession=variant.gene_accession,
        variant_description_verbatim=variant.variant_description_verbatim,
        genomic_coordinates=variant.genomic_coordinates,
        genome_build=_enum_to_str(variant.genome_build),
        rsid=variant.rsid,
        caid=variant.caid,
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        hgvs_g=variant.hgvs_g,
        hgvs_c_inferred=variant.hgvs_c_inferred,
        hgvs_p_inferred=variant.hgvs_p_inferred,
        hgvs_p_inference_confidence=_enum_to_str(variant.hgvs_p_inference_confidence),
        hgvs_p_inference_evidence_context=variant.hgvs_p_inference_evidence_context,
        hgvs_c_inference_confidence=_enum_to_str(variant.hgvs_c_inference_confidence),
        hgvs_c_inference_evidence_context=variant.hgvs_c_inference_evidence_context,
        variant_type=_enum_to_str(variant.variant_type),
        variant_evidence_context=variant.variant_evidence_context,
        variant_type_evidence_context=variant.variant_type_evidence_context,
    )


# ---------------------------------------------------------------------------
# Paper metadata converter
# ---------------------------------------------------------------------------


def paper_metadata_to_db(output: PaperExtractionOutput, paper_db: PaperDB) -> None:
    """Copy metadata from agent output onto an existing PaperDB row."""
    paper_db.title = output.title
    paper_db.first_author = output.first_author
    paper_db.journal = output.journal_name
    paper_db.abstract = output.abstract
    paper_db.pub_year = output.publication_year
    paper_db.doi = output.doi
    paper_db.pmid = output.pmid
    paper_db.pmcid = output.pmcid
    paper_db.paper_types = (
        [pt.value for pt in output.paper_types] if output.paper_types else None
    )
    paper_db.testing_methods = (
        [tm.value for tm in output.testing_methods] if output.testing_methods else None
    )
    paper_db.testing_methods_evidence = (
        list(output.testing_methods_evidence)
        if output.testing_methods_evidence
        else None
    )
