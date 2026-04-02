#!/usr/bin/env python3
import asyncio
import datetime
import json
import logging
import time
import traceback
from typing import Callable

from agents import Runner
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from lib.agents.hpo_linking_agent import agent as hpo_linking_agent
from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.patient_phenotype_linking_agent import (
    agent as patient_phenotype_linking_agent,
)
from lib.agents.patient_variant_linking_agent import (
    agent as patient_variant_linking_agent,
)
from lib.agents.pedigree_describer_agent import agent as pedigree_describer_agent
from lib.agents.variant_enrichment_agent import enrich_variants_batch
from lib.agents.variant_extraction_agent import (
    agent as variant_extraction_agent,
)
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import fulltext_md, pdf_image_caption_path, pdf_image_path
from lib.models import (
    EnrichedVariantDB,
    HarmonizedVariantDB,
    PaperDB,
    PatientDB,
    PatientVariantLinkDB,
    PedigreeDB,
    PipelineStatus,
    VariantDB,
)
from lib.models.converters import (
    harmonized_variant_to_db,
    hpo_to_db,
    patient_to_db,
    patient_variant_link_to_db,
    pedigree_to_db,
    phenotype_to_db,
    variant_to_db,
)
from lib.models.evidence_block import ReasoningBlock
from lib.models.phenotype import HpoCandidate, HpoDB, PhenotypeDB
from lib.models.variant import HarmonizedVariant, Variant
from lib.reference_data.hpo import build_term_lookup, find_matching_hpo_terms

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
RETRIES = 2

setup_logging()
logger = logging.getLogger(__name__)


def run_with_retries(
    paper_id: int,
    run_fn: Callable,
    running_status: PipelineStatus,
    success_status: PipelineStatus,
    failure_status: PipelineStatus,
) -> None:
    max_attempts = RETRIES + 1

    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=running_status)
        )

    for attempt in range(1, max_attempts + 1):
        try:
            run_fn()

            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=success_status)
                )

            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return

        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise

        except Exception:
            logger.exception(f'Attempt {attempt} failed')

            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=failure_status)
                    )
                return


async def parse_paper_task_async(paper_id: int) -> None:
    result = await Runner.run(
        paper_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_id)}',
    )
    with session_scope() as session:
        fetched_paper = session.get(PaperDB, paper_id)
        if not fetched_paper:
            return None
        result.final_output.apply_to(fetched_paper)


async def parse_patients_task_async(paper_db: PaperDB) -> None:
    # Load pedigree from DB
    with session_scope() as session:
        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_db.id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    result = await Runner.run(
        patient_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_db.id)} Pedigree Description: \n {pedigree_descriptions_output}',
    )

    # Persist patients to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        session.query(PatientDB).filter(PatientDB.paper_id == paper_db.id).delete()
        for patient_info in result.final_output.patients:
            session.add(patient_to_db(paper_db.id, patient_info))


async def harmonize_variants_task_async(
    paper_db: PaperDB, gene_symbol: str, variant_id: int | None = None
) -> None:
    with session_scope() as session:
        query = session.query(VariantDB).filter(VariantDB.paper_id == paper_db.id)

        if variant_id is not None:
            query = query.filter(VariantDB.id == variant_id)

        rows = query.order_by(VariantDB.id).all()

        # Extract everything we will ever need while session is alive
        variant_payloads = [
            (
                row.id,
                {
                    'gene_symbol': gene_symbol,
                    **{f: getattr(row, f) for f in Variant.model_fields},
                },
            )
            for row in rows
        ]

    sem = asyncio.Semaphore(3)  # <- your max parallelism

    async def harmonize_single_variant(
        variant_id: int, variant_input: dict
    ) -> tuple[int, ReasoningBlock[HarmonizedVariant]]:
        async with sem:
            result = await Runner.run(
                variant_harmonization_agent,
                f'Variant JSON:\n{json.dumps(variant_input, indent=2)}',
                max_turns=15,
            )
            return variant_id, result.final_output

    results = await asyncio.gather(
        *[
            harmonize_single_variant(variant_id, variant_input)
            for variant_id, variant_input in variant_payloads
        ]
    )

    with session_scope() as session:
        # Delete existing harmonized variants for this paper (idempotent: delete-then-insert)
        delete_query = session.query(HarmonizedVariantDB).filter(
            HarmonizedVariantDB.variant_id.in_(
                select(VariantDB.id).where(VariantDB.paper_id == paper_db.id)
            )
        )
        if variant_id is not None:
            delete_query = delete_query.filter(
                HarmonizedVariantDB.variant_id == variant_id
            )
        delete_query.delete()
        for variant_id, harmonized_output in results:
            session.add(harmonized_variant_to_db(variant_id, harmonized_output))


async def extract_variants_task_async(paper_id: int, gene_symbol: str) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f'Gene Symbol: {gene_symbol}\nPaper (fulltext md): {fulltext_md(paper_id)}',
    )
    with session_scope() as session:
        session.query(VariantDB).filter(VariantDB.paper_id == paper_id).delete()
        for variant in result.final_output.variants:
            session.add(variant_to_db(paper_id, variant))


async def pedigree_describer_task_async(paper_id: int) -> None:
    image_id, combined_text = 0, ''
    while True:
        pdf_image = pdf_image_path(paper_id, image_id)
        if not pdf_image.exists():
            break
        caption_path = pdf_image_caption_path(paper_id, image_id)
        caption_text = (
            caption_path.read_text() if caption_path.exists() else 'No caption'
        )
        image_url = f'{env.PROTOCOL}{env.API_ENDPOINT}{pdf_image}'
        combined_text += f'[Processing Pipeline Figure {image_id}]\n'
        combined_text += f'URL: {image_url}\n'
        combined_text += f'Caption: {caption_text}\n\n'
        image_id += 1
    result = await Runner.run(
        pedigree_describer_agent,
        combined_text,
    )
    # Persist pedigree to DB (idempotent: delete-then-insert)
    # Only insert if pedigree was found
    with session_scope() as session:
        session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_id).delete()
        if result.final_output and result.final_output.found:
            session.add(pedigree_to_db(paper_id, result.final_output))


async def patient_variant_linking_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        variant_rows = (
            session.query(VariantDB)
            .filter(VariantDB.paper_id == paper_db.id)
            .order_by(VariantDB.id)
            .all()
        )
        structured_variants = [
            {
                'variant_id': v.id,
                'variant_quote': v.variant_evidence['value'],
            }
            for v in variant_rows
        ]
        patient_rows = (
            session.query(PatientDB)
            .filter(PatientDB.paper_id == paper_db.id)
            .order_by(PatientDB.id)
            .all()
        )
        structured_patients = [
            {
                'patient_id': p.id,
                'identifier': p.identifier,
                'identifier_quote': p.identifier_evidence['quote'],
            }
            for p in patient_rows
        ]
        # Load pedigree from DB
        pedigree_row = (
            session.query(PedigreeDB).filter(PedigreeDB.paper_id == paper_db.id).first()
        )
        pedigree_descriptions_output = (
            {
                'image_id': pedigree_row.image_id,
                'description': pedigree_row.description,
            }
            if pedigree_row
            else None
        )

    result = await Runner.run(
        patient_variant_linking_agent,
        f'Variants JSON:\n{structured_variants}\n Patients JSON:\n {structured_patients} Pedigree Description: \n {pedigree_descriptions_output} Paper (fulltext md): {fulltext_md(paper_db.id)}',
    )
    # Persist patient-variant links to DB (idempotent: delete then insert)
    links = result.final_output.links
    with session_scope() as session:
        session.query(PatientVariantLinkDB).filter(
            PatientVariantLinkDB.paper_id == paper_db.id
        ).delete()
        for link in links:
            session.add(patient_variant_link_to_db(paper_db.id, link))


async def patient_phenotype_linking_task_async(
    paper_db: PaperDB, patient_id: int | None = None
) -> None:
    with session_scope() as session:
        query = session.query(PatientDB).filter(PatientDB.paper_id == paper_db.id)

        if patient_id is not None:
            query = query.filter(PatientDB.id == patient_id)

        patient_rows = query.order_by(PatientDB.id).all()

        # Extract all data while session is active
        patient_payloads = [
            (
                p.id,
                {
                    'patient_id': p.id,
                    'identifier': p.identifier,
                    'identifier_quote': p.identifier_evidence['quote'],
                },
            )
            for p in patient_rows
        ]

    async def extract_phenotypes_for_patient(
        pid: int, patient_data: dict
    ) -> tuple[int, list]:
        result = await Runner.run(
            patient_phenotype_linking_agent,
            f'Paper (fulltext md): {fulltext_md(paper_db.id)}\n\nStructured Patient JSON:\n{[patient_data]}',
        )
        return pid, result.final_output

    results = await asyncio.gather(
        *[
            extract_phenotypes_for_patient(pid, patient_data)
            for pid, patient_data in patient_payloads
        ]
    )

    # Persist extracted phenotypes to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        delete_query = session.query(PhenotypeDB).filter(
            PhenotypeDB.paper_id == paper_db.id
        )
        if patient_id is not None:
            delete_query = delete_query.filter(PhenotypeDB.patient_id == patient_id)
        delete_query.delete()

        for pid, phenotypes in results:
            for phenotype in phenotypes:
                session.add(phenotype_to_db(paper_db.id, phenotype))


async def enrich_variants_task_async(paper_db: PaperDB) -> None:
    with session_scope() as session:
        rows = (
            session.query(HarmonizedVariantDB)
            .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
            .filter(VariantDB.paper_id == paper_db.id)
            .order_by(VariantDB.id)
            .all()
        )
        harmonized_variants = [
            HarmonizedVariant(
                gnomad_style_coordinates=r.gnomad_style_coordinates,
                rsid=r.rsid,
                caid=r.caid,
                hgvs_c=r.hgvs_c,
                hgvs_p=r.hgvs_p,
                hgvs_g=r.hgvs_g,
            )
            for r in rows
        ]
        # Extract harmonized_variant IDs while session is active
        harmonized_variant_ids = [r.id for r in rows]
    # Offload blocking enrichment to thread
    enriched_variants = await asyncio.to_thread(
        enrich_variants_batch,
        harmonized_variants,
    )
    # Persist enriched variants to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        session.query(EnrichedVariantDB).filter(
            EnrichedVariantDB.harmonized_variant_id.in_(
                select(HarmonizedVariantDB.id)
                .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
                .where(VariantDB.paper_id == paper_db.id)
            )
        ).delete()
        for hv_id, ev in zip(harmonized_variant_ids, enriched_variants):
            session.add(
                EnrichedVariantDB(
                    harmonized_variant_id=hv_id,
                    gnomad_style_coordinates=ev.gnomad_style_coordinates,
                    rsid=ev.rsid,
                    caid=ev.caid,
                    pathogenicity=ev.pathogenicity,
                    submissions=ev.submissions,
                    stars=ev.stars,
                    exon=ev.exon,
                    revel=ev.revel,
                    alphamissense_class=ev.alphamissense_class,
                    alphamissense_score=ev.alphamissense_score,
                    spliceai=ev.spliceai.model_dump() if ev.spliceai else None,
                    gnomad_top_level_af=ev.gnomad_top_level_af,
                    gnomad_popmax_af=ev.gnomad_popmax_af,
                    gnomad_popmax_population=ev.gnomad_popmax_population,
                )
            )


async def hpo_linking_task_async(
    paper_db: PaperDB, phenotype_id: int | None = None
) -> None:
    with session_scope() as session:
        query = session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_db.id)

        if phenotype_id is not None:
            query = query.filter(PhenotypeDB.id == phenotype_id)

        phenotype_rows = query.order_by(PhenotypeDB.patient_id, PhenotypeDB.id).all()

        # Extract all data while session is active
        phenotype_id_set = {row.id for row in phenotype_rows}

        term_lookup = build_term_lookup()

        phenotype_inputs = []
        for row in phenotype_rows:
            candidates: list[HpoCandidate] = find_matching_hpo_terms(
                str(row.concept), term_lookup=term_lookup
            )
            phenotype_inputs.append(
                {
                    'phenotype_id': row.id,
                    'concept': row.concept,
                    'negated': row.negated,
                    'uncertain': row.uncertain,
                    'family_history': row.family_history,
                    'candidates': [c.model_dump() for c in candidates],
                }
            )

    async def link_phenotype_to_hpo(phenotype_data: dict) -> list:
        result = await Runner.run(
            hpo_linking_agent,
            f'Phenotype JSON:\n{json.dumps(phenotype_data, indent=2)}',
            max_turns=20,
            metadata={
                'paper_id': paper_db.id,
                'phenotype_id': phenotype_data['phenotype_id'],
                'concept': phenotype_data['concept'],
            },
        )
        return result.final_output

    results = await asyncio.gather(
        *[link_phenotype_to_hpo(phenotype_data) for phenotype_data in phenotype_inputs]
    )

    # Persist HPO links to DB (idempotent: delete-then-insert)
    with session_scope() as session:
        # Delete HPO links for phenotypes in this paper
        delete_query = session.query(HpoDB).filter(
            HpoDB.phenotype_id.in_(phenotype_id_set)
        )
        delete_query.delete()

        for links in results:
            for link in links:
                if link.phenotype_id in phenotype_id_set:
                    session.add(hpo_to_db(link.phenotype_id, link.hpo))


def initial_extraction(paper_id: int, gene_symbol: str) -> None:
    def run() -> None:
        async def _run1() -> None:
            await asyncio.gather(
                parse_paper_task_async(paper_id),
                extract_variants_task_async(paper_id, gene_symbol),
                pedigree_describer_task_async(paper_id),
            )

        paper_db = PaperDB(id=paper_id).with_content()

        async def _run2() -> None:
            await asyncio.gather(
                parse_patients_task_async(paper_db),
            )

        parse_content(paper_id, force=True)
        asyncio.run(_run1())
        asyncio.run(_run2())

    run_with_retries(
        paper_id=paper_id,
        run_fn=run,
        running_status=PipelineStatus.EXTRACTION_RUNNING,
        success_status=PipelineStatus.EXTRACTION_COMPLETED,
        failure_status=PipelineStatus.EXTRACTION_FAILED,
    )


def linking_tasks(paper_id: int, gene_symbol: str) -> None:
    def run() -> None:
        async def _run() -> None:
            paper_db = PaperDB(id=paper_id).with_content()

            await asyncio.gather(
                harmonize_variants_task_async(paper_db, gene_symbol),
                patient_variant_linking_task_async(paper_db),
                patient_phenotype_linking_task_async(paper_db),
            )

            await asyncio.gather(
                enrich_variants_task_async(paper_db),
                hpo_linking_task_async(paper_db),
            )

        asyncio.run(_run())

    run_with_retries(
        paper_id=paper_id,
        run_fn=run,
        running_status=PipelineStatus.LINKING_RUNNING,
        success_status=PipelineStatus.COMPLETED,
        failure_status=PipelineStatus.LINKING_FAILED,
    )


def main() -> None:
    while True:
        try:
            now = datetime.datetime.utcnow()
            expired_cutoff = now - datetime.timedelta(seconds=LEASE_TIMEOUT_S)
            with session_scope() as session:
                # Extraction queue
                extraction_job = session.scalars(
                    select(PaperDB)
                    .where(
                        or_(
                            PaperDB.pipeline_status == PipelineStatus.QUEUED,
                            and_(
                                PaperDB.pipeline_status
                                == PipelineStatus.EXTRACTION_RUNNING,
                                PaperDB.updated_at < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.updated_at.asc())  # oldest first
                    .limit(1)
                ).first()

                if extraction_job:
                    paper_id = extraction_job.id
                    gene_symbol = extraction_job.gene.symbol
                    logger.info(f'Dequeued paper {paper_id} for extraction')

            if extraction_job:
                initial_extraction(paper_id, gene_symbol)
                continue  # restart loop immediately

            with session_scope() as session:
                # Linking queue
                linking_job = session.scalars(
                    select(PaperDB)
                    .where(
                        or_(
                            PaperDB.pipeline_status
                            == PipelineStatus.EXTRACTION_COMPLETED,
                            and_(
                                PaperDB.pipeline_status
                                == PipelineStatus.LINKING_RUNNING,
                                PaperDB.updated_at < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.updated_at.asc())
                    .limit(1)
                ).first()

                if linking_job:
                    paper_id = linking_job.id
                    gene_symbol = linking_job.gene.symbol
                    logger.info(f'Dequeued paper {paper_id} for linking')

            if linking_job:
                linking_tasks(paper_id, gene_symbol)
                continue

        except KeyboardInterrupt:
            logger.info('Shutting down poller')
            break

        except Exception:
            logger.exception('Unexpected error in poller loop')

        logger.info('Looking for work')
        time.sleep(POLL_INTERVAL_S)


if __name__ == '__main__':
    main()
