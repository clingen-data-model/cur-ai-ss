from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from lib.misc.curation.models import CurationSummaryRow, SectionContent
from lib.misc.pdf.paths import pdf_image_path
from lib.models.family import FamilyDB
from lib.models.paper import PaperDB, PedigreeDB
from lib.models.patient import AffectedStatus, PatientDB, ProbandStatus
from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
from lib.models.phenotype import HpoDB, PhenotypeDB
from lib.models.segregation_analysis import (
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
)
from lib.models.variant import AnnotatedVariantDB, HarmonizedVariantDB, VariantDB


def build_curation_row(paper_id: int, session: Session) -> list[CurationSummaryRow]:
    """Assemble curation summary rows for a single paper (one row per proband).

    Returns one CurationSummaryRow per proband, each with that proband's variants,
    phenotypes, and shared family-level data.
    """
    # 1. Publication & Testing (shared across all rows from this paper)
    paper = session.get(PaperDB, paper_id)
    if not paper:
        raise ValueError(f'Paper {paper_id} not found')

    # Check for patients - if none, return empty list
    first_patient = (
        session.query(PatientDB).filter(PatientDB.paper_id == paper_id).first()
    )
    if not first_patient:
        return []

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

    # 2. Get all probands and build a row for each
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

    if not probands:
        return []

    # 3. Get all families and cache family-level data
    families = (
        session.query(FamilyDB)
        .join(PatientDB, FamilyDB.id == PatientDB.family_id)
        .filter(PatientDB.paper_id == paper_id)
        .distinct()
        .all()
    )

    family_segregation_map: dict[int, list[SectionContent]] = {}
    family_score_map: dict[int, list[SectionContent]] = {}

    for family in families:
        seg_sections = []
        seg_evidence = (
            session.query(SegregationEvidenceDB)
            .filter(SegregationEvidenceDB.family_id == family.id)
            .first()
        )
        if seg_evidence:
            if seg_evidence.extracted_lod_score is not None:
                seg_sections.append(
                    SectionContent(
                        title=f'Family "{family.identifier}"',
                        content=f'Extracted LOD: {seg_evidence.extracted_lod_score}',
                    )
                )
            if seg_evidence.has_unexplainable_non_segregations:
                seg_sections.append(
                    SectionContent(
                        title=f'Family "{family.identifier}"',
                        content='Has unexplainable non-segregations',
                    )
                )

        seg_computed = (
            session.query(SegregationAnalysisComputedDB)
            .filter(SegregationAnalysisComputedDB.family_id == family.id)
            .first()
        )
        if seg_computed:
            seg_info = (
                f'Segregation count: {seg_computed.segregation_count}\n'
                f'Computed LOD: {seg_computed.computed_lod_score}'
            )
            seg_sections.append(
                SectionContent(title=f'Family "{family.identifier}"', content=seg_info)
            )

        family_segregation_map[family.id] = seg_sections

        score_sections = []
        if seg_computed:
            score_sections.append(
                SectionContent(
                    title=f'Family "{family.identifier}"',
                    content=str(seg_computed.points_assigned),
                )
            )
        family_score_map[family.id] = score_sections

    # 4. Build one row per proband
    rows: list[CurationSummaryRow] = []
    pedigree = session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).first()
    pedigree_image_path_str = None
    if pedigree:
        path = pdf_image_path(paper_id, pedigree.image_id)
        if path.exists():
            pedigree_image_path_str = str(path)

    first_row = True
    for proband in probands:
        family = proband.family

        # Build proband section once (reused for each variant)
        proband_section = []
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
        country_str = (
            f'Country: {proband.country_of_origin}'
            if proband.country_of_origin != 'Unknown'
            else ''
        )
        demographic = ', '.join(filter(None, [sex_str, age_str, country_str]))

        family_header = f'Family "{family.identifier}"'
        if family.consanguinity:
            family_header += ' (Consanguineous)'
        proband_lines = [family_header, f'  - {proband.identifier}']
        if demographic:
            proband_lines[-1] += f' ({demographic})'

        proband_section.append(
            SectionContent(title='', content='\n'.join(proband_lines))
        )

        # Build clinical presentation once (reused for each variant)
        clinical_sections = []
        phenotypes = (
            session.query(PhenotypeDB)
            .filter(PhenotypeDB.patient_id == proband.id)
            .all()
        )
        if phenotypes:
            phenotype_concepts = [pheno.concept for pheno in phenotypes]
            if phenotype_concepts:
                clinical_sections.append(
                    SectionContent(
                        title='Phenotypes',
                        content=', '.join(phenotype_concepts),
                    )
                )

        # Affected family members (only for single-proband papers)
        if len(probands) == 1:
            affected_relatives = (
                session.query(PatientDB)
                .filter(
                    and_(
                        PatientDB.family_id == proband.family_id,
                        PatientDB.id != proband.id,
                        PatientDB.affected_status == AffectedStatus.Affected.value,
                    )
                )
                .all()
            )
            if affected_relatives:
                from lib.models.patient import RelationshipToProband

                relative_lines = []
                for relative in affected_relatives:
                    rel_type = relative.relationship_to_proband or 'Unknown relation'
                    relative_lines.append(f'{rel_type} ({relative.identifier})')

                if relative_lines:
                    clinical_sections.append(
                        SectionContent(
                            title='Family notes',
                            content='\n'.join(relative_lines),
                        )
                    )

        # Get variants linked to this proband
        variant_links = (
            session.query(PatientVariantOccurrenceDB)
            .filter(PatientVariantOccurrenceDB.patient_id == proband.id)
            .all()
        )

        # Create one row per proband/variant pair
        if variant_links:
            for link in variant_links:
                variant = link.variant
                variant_parts = []

                # 1. Zygosity / de novo status (first)
                zygosity_info = link.zygosity if link.zygosity != 'Unknown' else ''
                if link.de_novo:
                    zygosity_info = f'{zygosity_info} (de novo)'.strip()
                if zygosity_info:
                    variant_parts.append(f'Zygosity: {zygosity_info}')

                # 1b. Variant type
                if variant.variant_type and variant.variant_type != 'Unknown':
                    variant_parts.append(f'Type: {variant.variant_type}')

                # 1c. Inheritance
                if link.inheritance and link.inheritance != 'Unknown':
                    variant_parts.append(f'Inheritance: {link.inheritance}')

                # 2. HGVS nomenclature
                hgvs_parts = []
                if variant.hgvs_c:
                    hgvs_parts.append(variant.hgvs_c)
                if variant.hgvs_p:
                    hgvs_parts.append(variant.hgvs_p)
                if hgvs_parts:
                    variant_parts.append(' '.join(hgvs_parts))

                # 3. Exon
                if variant.annotated_variant and variant.annotated_variant.exon:
                    variant_parts.append(f'Exon: {variant.annotated_variant.exon}')

                # 4. gnomAD MAF
                if variant.annotated_variant:
                    if variant.annotated_variant.gnomad_top_level_af is not None:
                        variant_parts.append(
                            f'gnomAD MAF: {variant.annotated_variant.gnomad_top_level_af:.5f}'
                        )
                    else:
                        variant_parts.append('gnomAD: MISSING')
                else:
                    variant_parts.append('gnomAD: MISSING')

                # 5. ClinVar ID and classification
                if variant.annotated_variant:
                    if variant.annotated_variant.pathogenicity:
                        variant_parts.append(
                            f'ClinVar: {variant.annotated_variant.pathogenicity}'
                        )
                    else:
                        variant_parts.append('ClinVar: MISSING')
                        # 6. CAID only if not in ClinVar
                        if (
                            variant.harmonized_variant
                            and variant.harmonized_variant.caid
                        ):
                            variant_parts.append(
                                f'CAID: {variant.harmonized_variant.caid}'
                            )
                else:
                    variant_parts.append('ClinVar: MISSING')
                    if variant.harmonized_variant and variant.harmonized_variant.caid:
                        variant_parts.append(f'CAID: {variant.harmonized_variant.caid}')

                # Keep REVEL and SpliceAI
                if variant.annotated_variant:
                    if variant.annotated_variant.revel is not None:
                        variant_parts.append(
                            f'REVEL: {variant.annotated_variant.revel:.3f}'
                        )
                    if variant.annotated_variant.spliceai and isinstance(
                        variant.annotated_variant.spliceai, dict
                    ):
                        max_score = variant.annotated_variant.spliceai.get(
                            'max_score', 0
                        )
                        if max_score > 0:
                            variant_parts.append(f'SpliceAI: {max_score:.3f}')

                # Title is just the variant (no HGVS in title)
                variant_title = f'Variant {variant.id}'
                variant_section = [
                    SectionContent(
                        title=variant_title,
                        content='\n'.join(variant_parts) if variant_parts else '',
                    )
                ]

                # Functional/Segregation - specific to this variant
                functional_sections = []

                # Functional evidence for this variant
                if variant.functional_evidence and variant.functional_evidence_evidence:
                    ev_dict = variant.functional_evidence_evidence
                    if isinstance(ev_dict, dict) and 'reasoning' in ev_dict:
                        functional_sections.append(
                            SectionContent(
                                title='Functional Evidence',
                                content=ev_dict['reasoning'],
                            )
                        )

                # Segregation data (only if > 0 segregations)
                seg_computed = (
                    session.query(SegregationAnalysisComputedDB)
                    .filter(SegregationAnalysisComputedDB.family_id == family.id)
                    .first()
                )
                if seg_computed and seg_computed.segregation_count > 0:
                    seg_parts = [
                        f'Segregation count: {seg_computed.segregation_count}',
                        f'Computed LOD: {seg_computed.computed_lod_score}',
                    ]
                    functional_sections.append(
                        SectionContent(
                            title=f'Segregation (Family "{family.identifier}")',
                            content='\n'.join(seg_parts),
                        )
                    )

                # Score - family-level data (cached)
                score_sections = family_score_map.get(family.id, [])

                # Create one row for this proband/variant pair
                # Publication/Testing only on first row
                pub_test = publication_and_testing_sections if first_row else []
                rows.append(
                    CurationSummaryRow(
                        paper_id=paper_id,
                        publication_and_testing=pub_test,
                        proband=proband_section,
                        variant_info=variant_section,
                        clinical_presentation=clinical_sections,
                        functional_segregation=functional_sections,
                        score=score_sections,
                        pedigree_image_path=pedigree_image_path_str,
                    )
                )
                first_row = False
        else:
            # No variants for this proband - create one row anyway
            variant_section = [
                SectionContent(title='Variants', content='No variants for this proband')
            ]
            score_sections = family_score_map.get(family.id, [])
            pub_test = publication_and_testing_sections if first_row else []
            rows.append(
                CurationSummaryRow(
                    paper_id=paper_id,
                    publication_and_testing=pub_test,
                    proband=proband_section,
                    variant_info=variant_section,
                    clinical_presentation=clinical_sections,
                    functional_segregation=[],
                    score=score_sections,
                    pedigree_image_path=pedigree_image_path_str,
                )
            )
            first_row = False

    return rows
