"""lib.bin.backfill_clinvar_variation_ids stores the ClinVar record's ID only
when that record still gives the classification already stored on the row."""

import pytest

from lib.bin import backfill_clinvar_variation_ids as script
from lib.models import (
    AnnotatedVariantDB,
    GeneDB,
    HarmonizedVariantDB,
    PaperDB,
    VariantDB,
)
from lib.models.variant import AnnotatedVariant


def _ev(value=None):
    return {'value': value, 'reasoning': '', 'quote': '', 'citations': []}


def _variant(session, paper, rsid, pathogenicity, variation_id=None):
    variant = VariantDB(
        paper_id=paper.id,
        variant_type='Missense',
        functional_evidence=False,
        main_focus=False,
        **{
            f'{field}_evidence': _ev()
            for field in (
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
                'main_focus',
            )
        },
    )
    session.add(variant)
    session.flush()
    session.add(
        HarmonizedVariantDB(
            variant_id=variant.id,
            rsid=rsid,
            hgvs_c=f'NM_1.1:c.{variant.id}A>G',
            reasoning='r',
        )
    )
    annotated = AnnotatedVariantDB(
        variant_id=variant.id,
        rsid=rsid,
        pathogenicity=pathogenicity,
        clinvar_variation_id=variation_id,
    )
    session.add(annotated)
    session.flush()
    return annotated


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='MSX1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='abc123', gene_id=gene.id, filename='msx1.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


@pytest.fixture
def lookups(monkeypatch):
    """ClinVar as the backfill sees it today, keyed by rsID; records the HGVS
    each lookup was given."""
    records = {
        'rs1': AnnotatedVariant(clinvar_variation_id='101', pathogenicity='Pathogenic'),
        'rs2': AnnotatedVariant(clinvar_variation_id='202', pathogenicity='Benign'),
    }
    calls: list[tuple] = []

    def lookup(rsid, caid, hgvs_g, hgvs_c):
        calls.append((rsid, caid, hgvs_g, hgvs_c))
        return records.get(rsid, AnnotatedVariant())

    monkeypatch.setattr(script, 'clinvar_lookup', lookup)
    monkeypatch.setattr(script, 'request_interval_seconds', lambda: 0)
    return calls


def test_fills_only_records_that_agree(db_session, paper, lookups):
    agrees = _variant(db_session, paper, 'rs1', 'Pathogenic')
    moved = _variant(db_session, paper, 'rs2', 'Likely pathogenic')
    missing = _variant(db_session, paper, 'rs3', 'Uncertain significance')
    already = _variant(db_session, paper, 'rs1', 'Pathogenic', variation_id='7')
    unclassified = _variant(db_session, paper, 'rs1', None)
    db_session.commit()

    script.backfill()
    db_session.expire_all()

    assert agrees.clinvar_variation_id == '101'
    assert moved.clinvar_variation_id is None
    assert missing.clinvar_variation_id is None
    assert already.clinvar_variation_id == '7'
    assert unclassified.clinvar_variation_id is None
    # The lookup is given the harmonized HGVS, as annotation was.
    assert ('rs1', None, None, f'NM_1.1:c.{agrees.variant_id}A>G') in lookups
    assert len(lookups) == 3


def test_dry_run_writes_nothing(db_session, paper, lookups):
    row = _variant(db_session, paper, 'rs1', 'Pathogenic')
    db_session.commit()

    script.backfill(dry_run=True)
    db_session.expire_all()

    assert row.clinvar_variation_id is None
