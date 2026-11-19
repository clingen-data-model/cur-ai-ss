"""The ClinVar lookup hands the harmonization agent every name a record is
known by, so a paper's legacy residue numbering can be matched to it."""

import json
from pathlib import Path

import pytest

from lib.agents.variant_harmonization_agent import (
    VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS,
    _builds_of_chromosome_accessions,
    _clinvar_records,
    _registry_gnomad_id,
    _registry_protein_hgvs,
    _registry_query,
    _variant_validator_projection,
)
from lib.models.variant import GenomeBuild

FIXTURE = Path(__file__).parent / 'fixtures' / 'clinvar_esummary_14879.json'


def test_records_carry_aliases_protein_change_and_condition():
    """VCV14879 is Vastardis 1996's MSX1 variant (paper 80). The paper calls
    it Arg31Pro, counted within the homeodomain; ClinVar titles it
    p.Arg202Pro and keeps R31P as an alias. On 2026-09-30 the agent rejected
    this record because the codons differed, having never been shown the
    alias."""
    (record,) = _clinvar_records(json.loads(FIXTURE.read_text()))

    assert record == {
        'hgvs': 'NM_002448.3(MSX1):c.605G>C (p.Arg202Pro)',
        'caid': 'CA124423',
        'rsid': 'rs121913129',
        'protein_change': 'R202P',
        'aliases': ['R31P'],
        'condition': ['Tooth agenesis, selective, 1'],
        'classification': 'Pathogenic',
    }


def test_missing_fields_read_as_empty_not_errors():
    summary = {
        'result': {
            'uids': ['1'],
            '1': {'variation_set': [{'variation_name': 'X', 'variation_xrefs': []}]},
        }
    }

    (record,) = _clinvar_records(summary)

    assert record['aliases'] == []
    assert record['condition'] == []
    assert record['protein_change'] is None
    assert record['classification'] is None
    assert record['caid'] is None and record['rsid'] is None


def test_empty_reply_yields_no_records():
    assert _clinvar_records({}) == []
    assert _clinvar_records({'result': {'uids': []}}) == []


def test_state_4_tells_the_agent_to_read_the_aliases_before_rejecting():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'aliases or protein_change, it IS the variant' in rules
    assert 'A mismatched codon alone is not grounds for rejection' in rules
    assert (
        rules.index('Step 5C')
        < rules.index('aliases or protein_change')
        < rules.index('Case A')
    )


def test_state_0_checks_the_paper_position_against_the_residue_window():
    """Paper 109 (PKD1, 2000) numbers from the L33243 mRNA start, 211 ahead of
    HGVS c.; 'C7696T' projected cleanly onto Leu2566 and was stored as a real
    allele. The window check is what catches that before projection."""
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'residue N is encoded by c.(3N-2) to c.3N' in rules
    assert '"C810T" with "R200X" does not' in rules
    assert rules.index('Numbering check') < rules.index('STATE 1')


def test_state_3_projects_the_window_candidates_and_vetoes_a_wrong_consequence():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    state_3 = rules[rules.index('STATE 3') : rules.index('STATE 4')]
    assert 'gives c.598C>T, c.599C>T and' in state_3
    assert 'Consequence check' in state_3
    assert 'a Synonymous input that resolved' in state_3
    assert 'Do not return it with a note' in state_3
    assert state_3.index('Numbering.') < state_3.index('1. Resolve')
    assert state_3.index('Call allele_registry_resolver') < state_3.index(
        'Consequence check'
    )


def test_a_genbank_transcript_sends_the_agent_to_the_canonical_one():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'is a GenBank accession rather' in rules
    assert 'counted from an mRNA start' in rules  # and it is not a conflict flag


def test_an_uncheckable_position_on_a_genbank_sequence_is_not_projected():
    """The first run of the rule projected paper 109's 'Del 1 bp (G3336)' as
    c.3336del: no residue to check, so the mRNA-start number went through and
    resolved a frameshift the paper never describes."""
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'is not projected at all' in rules
    assert 'other than the one the paper names' in rules


def test_state_0_infers_terms_from_a_description_for_the_states_to_consume():
    """A variant arriving as words alone ("deletion of exon 2") met no state's
    condition and came back all null. State 0 now infers the terms the words
    could mean, and the states take them as the fields they stand in for."""
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    state_0 = rules[rules.index('STATE 0') : rules.index('STATE 1')]
    assert 'Description inference' in state_0
    assert 'as if\nthey were the input fields they stand in for' in state_0
    assert 'hgvs_c candidates' in state_0 and 'search terms for State 4' in state_0
    assert "an exon's bounds are not written from memory" in state_0
    assert 'heterozygous, homozygous, de novo, maternal' in state_0
    assert state_0.index('The lookups are\nthe check') < state_0.index(
        'Description inference'
    )
    state_4 = rules[rules.index('STATE 4') : rules.index('STATE 5')]
    assert 'or State 0 inferred search terms from a description' in state_4
    assert 'take the place of the protein\nforms' in state_4
    assert 'Resolution resting on a term inferred from a description' in rules


@pytest.mark.parametrize('caid', ['SCV000998966.1', 'SUB7928387', '_:CA'])
def test_a_malformed_caid_does_not_shadow_the_hgvs(caid):
    """A ClinVar submission accession in the CAID field was sent to the
    registry as allele/SCV... (HTTP 500) ahead of a perfectly good HGVS, so
    two paper 5 variants never harmonized."""
    assert (
        _registry_query(None, caid, 'NM_020982.4:c.475G>A', None)
        == 'allele?hgvs=NM_020982.4%3Ac.475G%3EA'
    )


def test_registry_query_order():
    assert _registry_query('rs1', 'CA117961', 'c', 'g') == 'allele/CA117961'
    assert _registry_query('rs1', None, None, 'g') == 'allele?hgvs=g'
    assert _registry_query('rs1', None, None, None) == 'alleles?dbSNP.rs=rs1'
    assert _registry_query(None, None, None, None) is None


def test_an_identifier_that_does_not_resolve_falls_through_to_state_3():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    state_2 = rules[rules.index('STATE 2') : rules.index('STATE 3')]
    assert 'it is not the end of the run' in state_2
    assert 'Proceed\nto State 3 when the input has a coding change' in state_2


def test_the_registry_position_is_the_first_changed_base():
    """The registry's B2M CC>TT (CA2499222953) as it returns it: positions
    count the gaps between bases, so the change starts at 44715509. Taking
    `end` wrote 15-44715510-CC-TT, a REF the genome does not have there."""
    genomic_allele = {
        'chromosome': '15',
        'referenceGenome': 'GRCh38',
        'coordinates': [
            {
                'start': 44715508,
                'end': 44715510,
                'referenceAllele': 'CC',
                'allele': 'TT',
            }
        ],
    }
    assert _registry_gnomad_id(genomic_allele) == '15-44715509-CC-TT'


def test_a_single_base_registry_change_keeps_its_position():
    genomic_allele = {
        'chromosome': '3',
        'coordinates': [
            {
                'start': 187236419,
                'end': 187236420,
                'referenceAllele': 'C',
                'allele': 'T',
            }
        ],
    }
    assert _registry_gnomad_id(genomic_allele) == '3-187236420-C-T'


@pytest.mark.parametrize('ref, alt', [('CT', ''), ('', 'A')])
def test_an_unanchored_registry_indel_gives_no_gnomad_id(ref, alt):
    genomic_allele = {
        'chromosome': '7',
        'coordinates': [
            {'start': 100, 'end': 102, 'referenceAllele': ref, 'allele': alt}
        ],
    }
    assert _registry_gnomad_id(genomic_allele) is None


def test_a_nucleotide_change_on_a_protein_accession_is_not_a_protein_change():
    """The registry's MANE protein for CAMK4 c.387-1G>A."""
    assert _registry_protein_hgvs('NP_001735.1:n.387-1G>A') is None
    assert _registry_protein_hgvs(None) is None
    assert _registry_protein_hgvs('NP_004039.1:p.Pro52Leu') == 'NP_004039.1:p.Pro52Leu'


def test_grch38_is_the_higher_chromosome_accession_version():
    """VariantValidator's genomic spans for CDH2 NM_001792.5. Compared as text,
    .10 sorts before .9 and the builds came back swapped."""
    spans = ['NC_000018.10', 'NC_000018.9', 'NG_011605.1']
    assert _builds_of_chromosome_accessions(spans) == {
        GenomeBuild.GRCh37: 'NC_000018.9',
        GenomeBuild.GRCh38: 'NC_000018.10',
    }
    assert _builds_of_chromosome_accessions(['NC_000002.12', 'NC_000002.11']) == {
        GenomeBuild.GRCh37: 'NC_000002.11',
        GenomeBuild.GRCh38: 'NC_000002.12',
    }
    assert _builds_of_chromosome_accessions(['NC_012920.1']) == {
        GenomeBuild.GRCh38: 'NC_012920.1'
    }
    assert _builds_of_chromosome_accessions(['NG_011605.1']) == {}


def test_variant_validator_says_why_it_gave_no_id():
    """VariantValidator's reply to TSEN2 NM_025265.4:c.914-5T>A, trimmed."""
    reply = {
        'flag': 'warning',
        'validation_warning_1': {
            'primary_assembly_loci': {},
            'validation_warnings': [
                'IntronBaseMismatchWarning: NM_025265.4:c.914-5T>A mapped to '
                'NC_000003.12:g.12516610T>A: Variant reference (T) does not agree '
                'with reference sequence (G)',
                'ExonBoundaryError: Position c.914-5 does not correspond with an '
                'exon boundary for transcript NM_025265.4',
                'LovdSyntaxcheckLibraryVersion: 1.1.2',
            ],
        },
        'metadata': {'variantvalidator_version': '3'},
    }
    projection = _variant_validator_projection(reply)
    assert projection['gnomad_ids'] == []
    assert [w.split(':')[0] for w in projection['validation_warnings']] == [
        'IntronBaseMismatchWarning',
        'ExonBoundaryError',
    ]


def test_variant_validator_ids_keep_their_warnings():
    """CANT1 NM_138793.4:c.-286+1G>A: VariantValidator corrects the description
    and maps it, and says so."""
    reply = {
        'NM_138793.4:c.-285T>A': {
            'primary_assembly_loci': {
                'grch38': {
                    'vcf': {'chr': 'chr17', 'pos': '78997907', 'ref': 'A', 'alt': 'T'}
                }
            },
            'validation_warnings': [
                'NM_138793.4:c.-286+1G>A automapped to NM_138793.4:c.-285T>A'
            ],
        },
    }
    assert _variant_validator_projection(reply) == {
        'gnomad_ids': ['17-78997907-A-T'],
        'validation_warnings': [
            'NM_138793.4:c.-286+1G>A automapped to NM_138793.4:c.-285T>A'
        ],
    }


def test_a_rejected_description_is_a_failed_projection():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    state_3 = rules[rules.index('STATE 3') : rules.index('STATE 4')]
    assert 'validation_warnings say why' in state_3
    assert 'not\n        returned as hgvs_c' in state_3
