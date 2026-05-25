from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from lib.misc.curation.models import CurationSummaryRow, SectionContent
from lib.misc.pdf.paths import pdf_image_path
from lib.models.family import FamilyDB
from lib.models.paper import PaperDB, PedigreeDB
from lib.models.patient import PatientDB, ProbandStatus
from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
from lib.models.phenotype import HpoDB, PhenotypeDB
from lib.models.segregation_analysis import (
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
)
from lib.models.variant import AnnotatedVariantDB, HarmonizedVariantDB, VariantDB


def build_curation_row(paper_id: int, session: Session) -> CurationSummaryRow:
    """Assemble a curation summary row for a single paper.

    Queries the database for all relevant data (publication, patients, variants,
    phenotypes, segregation) and assembles them into a single CurationSummaryRow.
    """
    # 1. Publication & Testing
    # Fetch paper directly if available
    paper = session.get(PaperDB, paper_id)
    if not paper:
        raise ValueError(f'Paper {paper_id} not found')

    # Check for patients - if none, return empty row
    first_patient = (
        session.query(PatientDB).filter(PatientDB.paper_id == paper_id).first()
    )
    author_year = (
        f'{paper.first_author or "Unknown"} et al., {paper.publication_year or "?"}'
    )
    pmid_str = f'PMID: {paper.pmid}' if paper.pmid else ''
    publication_part = f'{author_year} {pmid_str}'.strip()

    # Get unique testing methods
    testing_links = (
        session.query(PatientVariantOccurrenceDB)
        .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
        .all()
    )
    testing_methods_set = set()
    for link in testing_links:
        if link.testing_methods:
            testing_methods_set.update(link.testing_methods)
    testing_str = ', '.join(sorted(testing_methods_set)) if testing_methods_set else ''

    publication_and_testing_sections = []
    if publication_part:
        publication_and_testing_sections.append(
            SectionContent(title='Publication', content=publication_part)
        )
    if testing_str:
        publication_and_testing_sections.append(
            SectionContent(title='Testing Methods', content=testing_str)
        )

    # If no patients found, return early with basic publication info
    if not first_patient:
        return CurationSummaryRow(
            paper_id=paper_id,
            publication_and_testing=publication_and_testing_sections,
            proband=[],
            variant_info=[],
            clinical_presentation=[],
            functional_segregation=[],
            score=[],
            pedigree_image_path=None,
        )

    # 2. Proband - flat list with family info
    probands = (
        session.query(PatientDB)
        .filter(
            and_(
                PatientDB.paper_id == paper_id,
                PatientDB.proband_status == ProbandStatus.Proband.value,
            )
        )
        .all()
    )
    proband_sections = []
    if probands:
        proband_lines = []
        for proband in probands:
            family = proband.family
            sex_str = proband.sex or ''
            age_parts = []
            if proband.age_report is not None and proband.age_report_unit:
                age_parts.append(
                    f'{proband.age_report} {proband.age_report_unit.value.lower()}'
                )
            if proband.age_death is not None and proband.age_death_unit:
                age_parts.append(
                    f'(†{proband.age_death} {proband.age_death_unit.value.lower()})'
                )
            age_str = ' '.join(age_parts)
            demographic = ', '.join(filter(None, [sex_str, age_str]))
            line = f'{proband.identifier} - Family {family.identifier}'
            if demographic:
                line += f' ({demographic})'
            proband_lines.append(line)
        proband_sections.append(
            SectionContent(title='Probands', content='\n'.join(proband_lines))
        )

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
    variant_info_sections = []
    if variants:
        for idx, variant in enumerate(variants, 1):
            parts = []

            # HGVS notation
            hgvs_parts = []
            if variant.hgvs_c:
                hgvs_parts.append(variant.hgvs_c)
            if variant.hgvs_p:
                hgvs_parts.append(f'({variant.hgvs_p})')
            hgvs_str = ' '.join(hgvs_parts) if hgvs_parts else f'Variant {idx}'

            # Harmonized data
            if variant.harmonized_variant:
                hv = variant.harmonized_variant
                if hv.gnomad_style_coordinates:
                    parts.append(f'Coord: {hv.gnomad_style_coordinates}')
                if hv.rsid:
                    parts.append(f'rsID: {hv.rsid}')
                if hv.caid:
                    parts.append(f'CAID: {hv.caid}')

                # Enriched data
                if variant.annotated_variant:
                    ev = variant.annotated_variant
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
                        enriched_parts.append(
                            f'AlphaMissense: {ev.alphamissense_class}'
                        )
                    if ev.alphamissense_score is not None:
                        enriched_parts.append(f'({ev.alphamissense_score:.3f})')
                    if ev.spliceai and isinstance(ev.spliceai, dict):
                        max_score = ev.spliceai.get('max_score', 0)
                        if max_score > 0:
                            enriched_parts.append(f'SpliceAI: {max_score:.3f}')
                    if ev.gnomad_top_level_af is not None:
                        enriched_parts.append(
                            f'gnomAD AF: {ev.gnomad_top_level_af:.5f}'
                        )
                    if ev.gnomad_popmax_af is not None:
                        pop = ev.gnomad_popmax_population or 'unknown'
                        enriched_parts.append(
                            f'PopMax AF: {ev.gnomad_popmax_af:.5f} ({pop})'
                        )
                    if enriched_parts:
                        parts.append('; '.join(enriched_parts))

            variant_info_sections.append(
                SectionContent(
                    title=hgvs_str, content='\n'.join(parts) if parts else ''
                )
            )
    else:
        variant_info_sections.append(
            SectionContent(title='Variants', content='No main-focus variants')
        )

    # 4. Clinical Presentation - inheritance + phenotypes for each proband
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

    clinical_sections = []

    # Inheritance patterns first
    inheritance_patterns = set()
    for patient in proband_patients:
        links = (
            session.query(PatientVariantOccurrenceDB)
            .filter(PatientVariantOccurrenceDB.patient_id == patient.id)
            .all()
        )
        for link in links:
            if link.inheritance:
                inheritance_patterns.add(link.inheritance)

    if inheritance_patterns:
        clinical_sections.append(
            SectionContent(
                title='Inheritance',
                content=', '.join(sorted(inheritance_patterns)),
            )
        )

    # Then phenotypes for each proband
    for patient in proband_patients:
        phenotypes = (
            session.query(PhenotypeDB)
            .join(HpoDB, PhenotypeDB.id == HpoDB.phenotype_id)
            .filter(PhenotypeDB.patient_id == patient.id)
            .all()
        )
        phenotype_concepts = []
        for pheno in phenotypes:
            if pheno.hpo and pheno.hpo.hpo_id and pheno.hpo.hpo_name:
                phenotype_concepts.append(
                    f'{pheno.concept} ({pheno.hpo.hpo_id}: {pheno.hpo.hpo_name})'
                )
            elif pheno.hpo and pheno.hpo.hpo_name:
                phenotype_concepts.append(f'{pheno.concept} ({pheno.hpo.hpo_name})')
            else:
                phenotype_concepts.append(pheno.concept)

        if phenotype_concepts:
            clinical_sections.append(
                SectionContent(
                    title=f'Proband {patient.identifier}',
                    content=', '.join(phenotype_concepts),
                )
            )

    # 5. Functional/Segregation
    functional_segregation_sections = []

    # Functional evidence from variants
    functional_parts = []
    for variant in variants:
        if variant.functional_evidence:
            # Parse the evidence block from JSON
            if variant.functional_evidence_evidence:
                ev_dict = variant.functional_evidence_evidence
                if isinstance(ev_dict, dict) and 'reasoning' in ev_dict:
                    functional_parts.append(ev_dict['reasoning'])
    if functional_parts:
        functional_segregation_sections.append(
            SectionContent(
                title='Functional Evidence',
                content='\n'.join(functional_parts),
            )
        )

    # Get all families for this paper
    families = (
        session.query(FamilyDB)
        .join(PatientDB, FamilyDB.id == PatientDB.family_id)
        .filter(PatientDB.paper_id == paper_id)
        .distinct()
        .all()
    )

    # Segregation data per family
    for family in families:
        seg_parts = []
        seg_evidence = (
            session.query(SegregationEvidenceDB)
            .filter(SegregationEvidenceDB.family_id == family.id)
            .first()
        )
        if seg_evidence:
            if seg_evidence.extracted_lod_score is not None:
                seg_parts.append(f'Extracted LOD: {seg_evidence.extracted_lod_score}')
            if seg_evidence.has_unexplainable_non_segregations:
                seg_parts.append('Has unexplainable non-segregations')

        seg_computed = (
            session.query(SegregationAnalysisComputedDB)
            .filter(SegregationAnalysisComputedDB.family_id == family.id)
            .first()
        )
        if seg_computed:
            seg_parts.append(f'Segregation count: {seg_computed.segregation_count}')
            seg_parts.append(f'Computed LOD: {seg_computed.computed_lod_score}')

        if seg_parts:
            functional_segregation_sections.append(
                SectionContent(
                    title=f'Family:  {family.identifier}',
                    content='\n'.join(seg_parts),
                )
            )

    # 6. Score - points_assigned from segregation analysis
    score_sections = []
    for family in families:
        seg_computed = (
            session.query(SegregationAnalysisComputedDB)
            .filter(SegregationAnalysisComputedDB.family_id == family.id)
            .first()
        )
        if seg_computed:
            score_sections.append(
                SectionContent(
                    title=f'Family {family.identifier}',
                    content=str(seg_computed.points_assigned),
                )
            )

    pedigree = session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).first()
    pedigree_image_path_str = None
    if pedigree:
        path = pdf_image_path(paper_id, pedigree.image_id)
        if path.exists():
            pedigree_image_path_str = str(path)

    return CurationSummaryRow(
        paper_id=paper_id,
        publication_and_testing=publication_and_testing_sections,
        proband=proband_sections,
        variant_info=variant_info_sections,
        clinical_presentation=clinical_sections,
        functional_segregation=functional_segregation_sections,
        score=score_sections,
        pedigree_image_path=pedigree_image_path_str,
    )
