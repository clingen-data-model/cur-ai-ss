import pytest

from lib.agents.paper_extraction_agent import (
    PaperExtractionOutput,
    PaperType,
    TestingMethod,
)
from lib.agents.patient_extraction_agent import (
    CountryCode,
    PatientInfo,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.agents.variant_extraction_agent import (
    GenomeBuild,
    HgvsInferenceConfidence,
    Variant,
    VariantType,
)
from lib.models import PaperDB, PatientDB, VariantDB
from lib.models.converters import (
    paper_metadata_to_db,
    patient_db_to_pydantic,
    patient_info_to_db,
    variant_db_to_pydantic,
    variant_to_db,
)


def _sample_patient() -> PatientInfo:
    return PatientInfo(
        identifier='Patient 1',
        proband_status=ProbandStatus.Proband,
        sex=SexAtBirth.Male,
        age_diagnosis='5 years',
        age_report='10 years',
        age_death=None,
        country_of_origin=CountryCode.United_States,
        race_ethnicity=RaceEthnicity.Non_Finnish_European,
        identifier_evidence='Described as Patient 1',
        sex_evidence='male child',
        age_diagnosis_evidence='diagnosed at 5 years',
        age_report_evidence='reported at age 10',
        age_death_evidence=None,
        country_of_origin_evidence='from the United States',
        race_ethnicity_evidence='European descent',
    )


def _sample_variant() -> Variant:
    return Variant(
        gene='BRCA1',
        transcript='NM_007294.4',
        protein_accession='NP_009225.1',
        genomic_accession=None,
        lrg_accession=None,
        gene_accession=None,
        variant_description_verbatim='c.5266dupC frameshift',
        genomic_coordinates=None,
        genome_build=GenomeBuild.GRCh38,
        rsid='rs80357906',
        caid=None,
        hgvs_c='c.5266dupC',
        hgvs_p='p.Gln1756Profs*74',
        hgvs_g=None,
        hgvs_c_inferred=None,
        hgvs_p_inferred='p.Gln1756Profs*74',
        hgvs_p_inference_confidence=HgvsInferenceConfidence.high,
        hgvs_p_inference_evidence_context='c.5266dupC causes frameshift',
        hgvs_c_inference_confidence=None,
        hgvs_c_inference_evidence_context=None,
        variant_type=VariantType.frameshift,
        variant_evidence_context='c.5266dupC found in exon 20',
        variant_type_evidence_context='frameshift insertion',
    )


class TestPatientConverter:
    def test_round_trip(self):
        patient = _sample_patient()
        db_row = patient_info_to_db(patient, paper_id='paper123')
        assert db_row.paper_id == 'paper123'
        assert db_row.proband_status == 'Proband'
        assert db_row.sex == 'Male'
        assert db_row.country_of_origin == 'United States'

        restored = patient_db_to_pydantic(db_row)
        assert restored.identifier == patient.identifier
        assert restored.proband_status == patient.proband_status
        assert restored.sex == patient.sex
        assert restored.age_diagnosis == patient.age_diagnosis
        assert restored.country_of_origin == patient.country_of_origin
        assert restored.race_ethnicity == patient.race_ethnicity
        assert restored.identifier_evidence == patient.identifier_evidence

    def test_null_fields(self):
        patient = PatientInfo(
            identifier='Unknown',
            proband_status=ProbandStatus.Unknown,
            sex=SexAtBirth.Unknown,
            age_diagnosis=None,
            age_report=None,
            age_death=None,
            country_of_origin=CountryCode.Unknown,
            race_ethnicity=RaceEthnicity.Unknown,
            identifier_evidence=None,
            sex_evidence=None,
            age_diagnosis_evidence=None,
            age_report_evidence=None,
            age_death_evidence=None,
            country_of_origin_evidence=None,
            race_ethnicity_evidence=None,
        )
        db_row = patient_info_to_db(patient, paper_id='p1')
        restored = patient_db_to_pydantic(db_row)
        assert restored.age_diagnosis is None
        assert restored.age_death_evidence is None


class TestVariantConverter:
    def test_round_trip(self):
        variant = _sample_variant()
        db_row = variant_to_db(variant, paper_id='paper456')
        assert db_row.paper_id == 'paper456'
        assert db_row.gene == 'BRCA1'
        assert db_row.genome_build == 'GRCh38'
        assert db_row.variant_type == 'frameshift'
        assert db_row.hgvs_p_inference_confidence == 'high'

        restored = variant_db_to_pydantic(db_row)
        assert restored.gene == variant.gene
        assert restored.transcript == variant.transcript
        assert restored.genome_build == variant.genome_build
        assert restored.rsid == variant.rsid
        assert restored.hgvs_c == variant.hgvs_c
        assert restored.hgvs_p == variant.hgvs_p
        assert restored.variant_type == variant.variant_type
        assert (
            restored.hgvs_p_inference_confidence == variant.hgvs_p_inference_confidence
        )

    def test_null_fields(self):
        variant = Variant(
            gene='TP53',
            transcript=None,
            protein_accession=None,
            genomic_accession=None,
            lrg_accession=None,
            gene_accession=None,
            variant_description_verbatim=None,
            genomic_coordinates=None,
            genome_build=None,
            rsid=None,
            caid=None,
            hgvs_c=None,
            hgvs_p=None,
            hgvs_g=None,
            hgvs_c_inferred=None,
            hgvs_p_inferred=None,
            hgvs_p_inference_confidence=None,
            hgvs_p_inference_evidence_context=None,
            hgvs_c_inference_confidence=None,
            hgvs_c_inference_evidence_context=None,
            variant_type=VariantType.unknown,
            variant_evidence_context=None,
            variant_type_evidence_context=None,
        )
        db_row = variant_to_db(variant, paper_id='p1')
        restored = variant_db_to_pydantic(db_row)
        assert restored.transcript is None
        assert restored.genome_build is None
        assert restored.hgvs_c_inference_confidence is None


class TestPaperMetadataConverter:
    def test_paper_metadata_to_db(self):
        output = PaperExtractionOutput(
            title='Test Title',
            first_author='Smith',
            journal_name='Nature',
            abstract='Some abstract',
            publication_year=2024,
            doi='10.1234/test',
            pmid='12345678',
            pmcid='PMC123456',
            testing_methods=[TestingMethod.Exome_sequencing],
            testing_methods_evidence=['WES was performed'],
            paper_types=[PaperType.Research],
        )
        paper_db = PaperDB(
            id='test_paper',
            gene_id=1,
            filename='test.pdf',
        )
        paper_metadata_to_db(output, paper_db)
        assert paper_db.title == 'Test Title'
        assert paper_db.first_author == 'Smith'
        assert paper_db.journal == 'Nature'
        assert paper_db.abstract == 'Some abstract'
        assert paper_db.pub_year == 2024
        assert paper_db.doi == '10.1234/test'
        assert paper_db.pmid == '12345678'
        assert paper_db.pmcid == 'PMC123456'
        assert paper_db.paper_types == ['Research']
        assert paper_db.testing_methods == ['Exome sequencing']
        assert paper_db.testing_methods_evidence == ['WES was performed']
