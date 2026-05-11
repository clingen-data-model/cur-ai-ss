from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from lib.models.curation_summary import CurationSummaryRow
from lib.models.family import FamilyDB
from lib.models.patient import PatientDB, ProbandStatus
from lib.models.patient_variant_link import PatientVariantLinkDB
from lib.models.phenotype import HpoDB, PhenotypeDB
from lib.models.segregation_analysis import (
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
)
from lib.models.variant import EnrichedVariantDB, HarmonizedVariantDB, VariantDB


def build_curation_row(paper_id: int, session: Session) -> CurationSummaryRow:
    """Assemble a curation summary row for a single paper.

    Queries the database for all relevant data (publication, patients, variants,
    phenotypes, segregation) and assembles them into a single CurationSummaryRow.
    """
    # 1. Publication & Testing
    # For simplicity, fetch via direct query of first patient to get paper
    first_patient = (
        session.query(PatientDB).filter(PatientDB.paper_id == paper_id).first()
    )
    if not first_patient:
        raise ValueError(f'No patients found for paper {paper_id}')

    paper = first_patient.paper
    author_year = (
        f'{paper.first_author or "Unknown"} et al., {paper.publication_year or "?"}'
    )
    pmid_str = f'PMID: {paper.pmid}' if paper.pmid else ''
    publication_part = f'{author_year}\n{pmid_str}'.strip()

    # Get unique testing methods
    testing_links = (
        session.query(PatientVariantLinkDB)
        .filter(PatientVariantLinkDB.paper_id == paper_id)
        .all()
    )
    testing_methods_set = set()
    for link in testing_links:
        if link.testing_methods:
            testing_methods_set.update(link.testing_methods)
    testing_str = ', '.join(sorted(testing_methods_set)) if testing_methods_set else ''
    publication_and_testing = f'{publication_part}\n{testing_str}'.strip()

    # 2. Proband - group by family
    families = session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).all()
    proband_lines = []
    for family in families:
        patients = (
            session.query(PatientDB)
            .filter(PatientDB.family_id == family.id)
            .order_by(PatientDB.proband_status.desc())
            .all()
        )
        patient_ids = ', '.join(p.identifier for p in patients)
        proband_lines.append(f'Family {family.identifier}: {patient_ids}')
    proband = '\n'.join(proband_lines)

    # 3. Variant Info - main_focus variants with harmonized + enriched data
    variants = (
        session.query(VariantDB)
        .filter(
            and_(
                VariantDB.paper_id == paper_id,
                VariantDB.main_focus.is_(True),
            )
        )
        .all()
    )
    variant_lines = []
    for variant in variants:
        parts = []

        # HGVS notation
        if variant.hgvs_c:
            parts.append(f'{variant.hgvs_c}')
        if variant.hgvs_p:
            parts.append(f'({variant.hgvs_p})')
        if parts:
            variant_lines.append(' '.join(parts))

        # Harmonized data
        if variant.harmonized_variant:
            hv = variant.harmonized_variant
            if hv.gnomad_style_coordinates:
                variant_lines.append(f'Coord: {hv.gnomad_style_coordinates}')
            if hv.rsid:
                variant_lines.append(f'rsID: {hv.rsid}')
            if hv.caid:
                variant_lines.append(f'CAID: {hv.caid}')

            # Enriched data
            if hv.enriched_variant:
                ev = hv.enriched_variant
                enriched_parts = []
                if ev.pathogenicity:
                    enriched_parts.append(f'ClinVar: {ev.pathogenicity}')
                if ev.submissions is not None:
                    enriched_parts.append(f'Submissions: {ev.submissions}')
                if ev.stars is not None:
                    enriched_parts.append(f'Stars: {ev.stars}')
                if ev.exon:
                    enriched_parts.append(f'Exon: {ev.exon}')
                if ev.revel is not None:
                    enriched_parts.append(f'REVEL: {ev.revel:.3f}')
                if ev.alphamissense_class:
                    enriched_parts.append(f'AlphaMissense: {ev.alphamissense_class}')
                if ev.alphamissense_score is not None:
                    enriched_parts.append(f'({ev.alphamissense_score:.3f})')
                if ev.spliceai and isinstance(ev.spliceai, dict):
                    max_score = ev.spliceai.get('max_score', 0)
                    if max_score > 0:
                        enriched_parts.append(f'SpliceAI: {max_score:.3f}')
                if ev.gnomad_top_level_af is not None:
                    enriched_parts.append(f'gnomAD AF: {ev.gnomad_top_level_af:.5f}')
                if ev.gnomad_popmax_af is not None:
                    pop = ev.gnomad_popmax_population or 'unknown'
                    enriched_parts.append(
                        f'PopMax AF: {ev.gnomad_popmax_af:.5f} ({pop})'
                    )
                if enriched_parts:
                    variant_lines.append('; '.join(enriched_parts))

    variant_info = (
        '\n'.join(variant_lines) if variant_lines else 'No main-focus variants'
    )

    # 4. Clinical Presentation - phenotypes for probands
    proband_patients = (
        session.query(PatientDB)
        .filter(
            and_(
                PatientDB.paper_id == paper_id,
                PatientDB.proband_status == ProbandStatus.Proband.value,
            )
        )
        .all()
    )
    phenotype_concepts = []
    for patient in proband_patients:
        phenotypes = (
            session.query(PhenotypeDB)
            .join(HpoDB, PhenotypeDB.id == HpoDB.phenotype_id)
            .filter(PhenotypeDB.patient_id == patient.id)
            .all()
        )
        for pheno in phenotypes:
            hpo_term = pheno.hpo.hpo_name if pheno.hpo else None
            if hpo_term:
                phenotype_concepts.append(f'{pheno.concept} ({hpo_term})')
            else:
                phenotype_concepts.append(pheno.concept)

    # Add inheritance patterns from patient-variant links
    inheritance_patterns = set()
    for patient in proband_patients:
        links = (
            session.query(PatientVariantLinkDB)
            .filter(PatientVariantLinkDB.patient_id == patient.id)
            .all()
        )
        for link in links:
            if link.inheritance:
                inheritance_patterns.add(link.inheritance)

    clinical_parts = []
    if phenotype_concepts:
        clinical_parts.append(', '.join(phenotype_concepts))
    if inheritance_patterns:
        clinical_parts.append(f'Inheritance: {", ".join(sorted(inheritance_patterns))}')
    clinical_presentation = '; '.join(clinical_parts) if clinical_parts else ''

    # 5. Functional/Segregation
    functional_seg_parts = []

    # Functional evidence from variants
    for variant in variants:
        if variant.functional_evidence:
            # Parse the evidence block from JSON
            if variant.functional_evidence_evidence:
                ev_dict = variant.functional_evidence_evidence
                if isinstance(ev_dict, dict) and 'reasoning' in ev_dict:
                    functional_seg_parts.append(
                        f'Functional evidence: {ev_dict["reasoning"]}'
                    )

    # Segregation data per family
    for family in families:
        seg_evidence = (
            session.query(SegregationEvidenceDB)
            .filter(SegregationEvidenceDB.family_id == family.id)
            .first()
        )
        if seg_evidence:
            if seg_evidence.extracted_lod_score is not None:
                functional_seg_parts.append(
                    f'Family {family.identifier} Extracted LOD: {seg_evidence.extracted_lod_score}'
                )
            if seg_evidence.has_unexplainable_non_segregations:
                functional_seg_parts.append(
                    f'Family {family.identifier} has unexplainable non-segregations'
                )

        seg_computed = (
            session.query(SegregationAnalysisComputedDB)
            .filter(SegregationAnalysisComputedDB.family_id == family.id)
            .first()
        )
        if seg_computed:
            functional_seg_parts.append(
                f'Family {family.identifier} Segregation count: {seg_computed.segregation_count}'
            )
            functional_seg_parts.append(
                f'Family {family.identifier} Computed LOD: {seg_computed.computed_lod_score}'
            )

    functional_segregation = (
        '\n'.join(functional_seg_parts) if functional_seg_parts else ''
    )

    # 6. Score - points_assigned from segregation analysis
    score_parts = []
    for family in families:
        seg_computed = (
            session.query(SegregationAnalysisComputedDB)
            .filter(SegregationAnalysisComputedDB.family_id == family.id)
            .first()
        )
        if seg_computed:
            score_parts.append(f'{family.identifier}: {seg_computed.points_assigned}')
    score = ', '.join(score_parts) if score_parts else ''

    return CurationSummaryRow(
        paper_id=paper_id,
        publication_and_testing=publication_and_testing,
        proband=proband,
        variant_info=variant_info,
        clinical_presentation=clinical_presentation,
        functional_segregation=functional_segregation,
        score=score,
    )
