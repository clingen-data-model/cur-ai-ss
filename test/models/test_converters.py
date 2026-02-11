import pytest

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
from lib.models.converters import (
    paper_db_to_metadata_dict,
    paper_metadata_to_db,
    patient_db_to_pydantic,
    patient_info_to_db,
    variant_db_to_pydantic,
    variant_to_db,
)


def _sample_patient() -> PatientInfo:
    return PatientInfo(
        identifier='Patient 1',
        sex=SexAtBirth.Male,
        age_diagnosis='5 years',
        age_report='10 years',
        age_death=None,
        country_of_origin=CountryCode.United_States,
        race_ethnicity=RaceEthnicity.Non_Finnish_European,
        identifier_evidence='The proband, Patient 1',
        sex_evidence='male patient',
        age_diagnosis_evidence='diagnosed at age 5',
        age_report_evidence='reported at age 10',
        age_death_evidence=None,
        country_of_origin_evidence='from the United States',
        race_ethnicity_evidence='European ancestry',
    )


def _sample_variant() -> Variant:
    return Variant(
        gene='BRCA1',
        transcript='NM_007294.3',
        variant_verbatim='Val600Glu mutation',
        genomic_coordinates='chr17:41276044',
        hgvs_c='c.1799T>A',
        hgvs_p='p.Val600Glu',
        hgvs_c_inferred=None,
        hgvs_p_inferred='p.Val600Glu',
        hgvs_inference_confidence=HgvsInferenceConfidence.high,
        hgvs_inference_evidence_context='Val600Glu mutation in exon 15',
        variant_type=VariantType.missense,
        zygosity=Zygosity.heterozygous,
        inheritance=Inheritance.dominant,
        variant_type_evidence_context='missense variant',
        variant_evidence_context='Val600Glu mutation',
        zygosity_evidence_context='heterozygous',
        inheritance_evidence_context='autosomal dominant',
    )


class TestPatientConverter:
    def test_round_trip(self):
        patient = _sample_patient()
        db_obj = patient_info_to_db(patient, 'paper123')
        assert db_obj.paper_id == 'paper123'
        assert db_obj.sex == 'Male'
        assert db_obj.country_of_origin == 'United States'
        assert db_obj.race_ethnicity == 'Non-Finnish European'

        restored = patient_db_to_pydantic(db_obj)
        assert restored.identifier == patient.identifier
        assert restored.sex == patient.sex
        assert restored.age_diagnosis == patient.age_diagnosis
        assert restored.age_report == patient.age_report
        assert restored.age_death == patient.age_death
        assert restored.country_of_origin == patient.country_of_origin
        assert restored.race_ethnicity == patient.race_ethnicity
        assert restored.identifier_evidence == patient.identifier_evidence
        assert restored.sex_evidence == patient.sex_evidence

    def test_none_enum_defaults(self):
        db_obj = PatientDB(
            paper_id='p1', sex=None, country_of_origin=None, race_ethnicity=None
        )
        restored = patient_db_to_pydantic(db_obj)
        assert restored.sex == SexAtBirth.Unknown
        assert restored.country_of_origin == CountryCode.Unknown
        assert restored.race_ethnicity == RaceEthnicity.Unknown


class TestVariantConverter:
    def test_round_trip(self):
        variant = _sample_variant()
        db_obj = variant_to_db(variant, 'paper456')
        assert db_obj.paper_id == 'paper456'
        assert db_obj.gene == 'BRCA1'
        assert db_obj.variant_type == 'missense'
        assert db_obj.zygosity == 'heterozygous'
        assert db_obj.inheritance == 'dominant'
        assert db_obj.hgvs_inference_confidence == 'high'

        restored = variant_db_to_pydantic(db_obj)
        assert restored.gene == variant.gene
        assert restored.transcript == variant.transcript
        assert restored.variant_verbatim == variant.variant_verbatim
        assert restored.genomic_coordinates == variant.genomic_coordinates
        assert restored.hgvs_c == variant.hgvs_c
        assert restored.hgvs_p == variant.hgvs_p
        assert restored.hgvs_p_inferred == variant.hgvs_p_inferred
        assert restored.hgvs_inference_confidence == variant.hgvs_inference_confidence
        assert restored.variant_type == variant.variant_type
        assert restored.zygosity == variant.zygosity
        assert restored.inheritance == variant.inheritance
        assert restored.variant_evidence_context == variant.variant_evidence_context

    def test_none_enum_defaults(self):
        db_obj = VariantDB(
            paper_id='p1',
            gene='BRCA1',
            variant_type=None,
            zygosity=None,
            inheritance=None,
            hgvs_inference_confidence=None,
        )
        restored = variant_db_to_pydantic(db_obj)
        assert restored.variant_type == VariantType.unknown
        assert restored.zygosity == Zygosity.unknown
        assert restored.inheritance == Inheritance.unknown
        assert restored.hgvs_inference_confidence is None


class TestPaperMetadataConverter:
    def test_to_db(self):
        paper = Paper(
            id='abc123',
            pmid='12345678',
            pmcid='PMC1234',
            doi='10.1234/test',
            title='Test Paper',
            abstract='Abstract text',
            journal='Nature',
            first_author='Smith J',
            pub_year=2024,
            citation='Smith J et al. Nature 2024',
            OA=True,
            can_access=True,
            license='CC BY 4.0',
            link='https://example.com',
        )
        paper_db = PaperDB(id='abc123', gene_id='1', filename='test.pdf')
        paper_metadata_to_db(paper, paper_db)

        assert paper_db.pmid == '12345678'
        assert paper_db.title == 'Test Paper'
        assert paper_db.is_open_access is True
        assert paper_db.pub_year == 2024

    def test_to_metadata_dict(self):
        paper_db = PaperDB(
            id='abc',
            gene_id='1',
            filename='test.pdf',
            pmid='12345',
            title='Test',
            is_open_access=True,
        )
        d = paper_db_to_metadata_dict(paper_db)
        assert d['pmid'] == '12345'
        assert d['title'] == 'Test'
        assert d['OA'] is True
        assert d['id'] == 'abc'
