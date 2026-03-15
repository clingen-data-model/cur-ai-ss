#!/usr/bin/env python3
import asyncio
import datetime
import json
import logging
import time
import traceback

from agents import Runner
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from lib.agents.hpo_linking_agent import agent as hpo_linking_agent
from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.patient_variant_linking_agent import (
    agent as patient_variant_linking_agent,
)
from lib.agents.pedigree_describer_agent import agent as pedigree_describer_agent
from lib.agents.phenotype_patient_linking_agent import (
    agent as phenotype_patient_linking_agent,
)
from lib.agents.variant_enrichment_agent import (
    HarmonizedVariant,
    VariantEnrichmentOutput,
    enrich_variants_batch,
)
from lib.agents.variant_extraction_agent import agent as variant_extraction_agent
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.api.db import session_scope
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import fulltext_md, pdf_image_caption_path, pdf_image_path
from lib.models import (
    PaperDB,
    PhenotypeLinkingEntry,
    PhenotypeLinkingOutput,
    PipelineStatus,
)
from lib.reference_data.hpo import build_term_lookup, find_matching_hpo_terms

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
RETRIES = 2

setup_logging()
logger = logging.getLogger(__name__)


async def parse_paper_task_async(paper_id: str) -> None:
    result = await Runner.run(
        paper_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_id)}',
    )
    with session_scope() as session:
        fetched_paper = session.get(PaperDB, paper_id)
        if not fetched_paper:
            return None
        result.final_output.apply_to(fetched_paper)


async def parse_patients_task_async(paper_id: str) -> None:
    result = await Runner.run(
        patient_extraction_agent,
        f'Paper (fulltext md): {fulltext_md(paper_id)}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    PaperDB(id=paper_id).patient_info_json_path.parent.mkdir(
        parents=True, exist_ok=True
    )
    with open(PaperDB(id=paper_id).patient_info_json_path, 'w') as f:
        f.write(json_response)


async def harmonize_variants_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.variants_json_path, 'r') as f:
        variants_output = json.load(f)

    result = await Runner.run(
        variant_harmonization_agent,
        f'Variants JSON:\n{json.dumps(variants_output, indent=2)}',
        max_turns=10 * len(variants_output['variants']),
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.harmonized_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.harmonized_variants_json_path, 'w') as f:
        f.write(json_response)


async def extract_variants_task_async(paper_id: str, gene_symbol: str) -> None:
    result = await Runner.run(
        variant_extraction_agent,
        f'Gene Symbol: {gene_symbol}\nPaper (fulltext md): {fulltext_md(paper_id)}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    PaperDB(id=paper_id).variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(PaperDB(id=paper_id).variants_json_path, 'w') as f:
        f.write(json_response)


async def pedigree_describer_task_async(paper_id: str) -> None:
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
    json_response = result.final_output.model_dump_json(indent=2)
    PaperDB(id=paper_id).pedigree_descriptions_json_path.parent.mkdir(
        parents=True, exist_ok=True
    )
    with open(PaperDB(id=paper_id).pedigree_descriptions_json_path, 'w') as f:
        f.write(json_response)


async def patient_variant_linking_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.variants_json_path, 'r') as f:
        variants_output = json.load(f)
    with open(paper_db.patient_info_json_path, 'r') as f:
        patients_output = json.load(f)
    with open(paper_db.pedigree_descriptions_json_path, 'r') as f:
        pedigree_descriptions_output = json.load(f)

    structured_variants = [
        {
            'variant_id': idx,
            'variant_description_verbatim': variant['variant_description_verbatim'],
            'variant_evidence_context': variant['variant_evidence_context'],
        }
        for idx, variant in enumerate(variants_output['variants'], start=1)
    ]
    structured_patients = [
        {
            'patient_id': idx,
            'identifier': patient['identifier'],
            'identifier_evidence_context': patient['identifier_evidence_context'],
        }
        for idx, patient in enumerate(patients_output['patients'], start=1)
    ]
    structured_pedigree_descriptions = [
        {
            'image_id': idx,
            'is_pedigree': pedigree_description['is_pedigree'],
            'description': pedigree_description['description'],
        }
        for idx, pedigree_description in enumerate(
            pedigree_descriptions_output['pedigrees'], start=1
        )
    ]
    result = await Runner.run(
        patient_variant_linking_agent,
        f'Variants JSON:\n{structured_variants}\n Patients JSON:\n {structured_patients} Image Descriptions JSON: \n {structured_pedigree_descriptions}',
    )
    json_response = result.final_output.model_dump_json(indent=2)
    paper_db.patient_variant_links_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.patient_variant_links_json_path, 'w') as f:
        f.write(json_response)


async def phenotype_patient_linking_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.patient_info_json_path, 'r') as f:
        patients_output = json.load(f)

    structured_patients = [
        {
            'patient_id': idx,
            'identifier': patient['identifier'],
            'identifier_evidence_context': patient['identifier_evidence_context'],
        }
        for idx, patient in enumerate(patients_output['patients'], start=1)
    ]
    result = await Runner.run(
        phenotype_patient_linking_agent,
        f'Paper (fulltext md): {fulltext_md(paper_db.id)}\n\nStructured Patients JSON:\n{structured_patients}',
    )

    # Convert phenotype extraction output to combined phenotype-linking format
    phenotypes_output = result.final_output
    phenotype_links = [
        PhenotypeLinkingEntry.from_extraction(ph) for ph in phenotypes_output.phenotypes
    ]
    combined_output = PhenotypeLinkingOutput(phenotypes=phenotype_links)
    json_response = combined_output.model_dump_json(indent=2)
    paper_db.phenotype_linking_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.phenotype_linking_json_path, 'w') as f:
        f.write(json_response)


async def enrich_variants_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.harmonized_variants_json_path, 'r') as f:
        harmonized_data = json.load(f)
    harmonized_variants = [HarmonizedVariant(**v) for v in harmonized_data['variants']]
    # Offload blocking enrichment to thread
    enriched_variants = await asyncio.to_thread(
        enrich_variants_batch,
        harmonized_variants,
    )
    output = VariantEnrichmentOutput(variants=enriched_variants)
    paper_db.enriched_variants_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_db.enriched_variants_json_path, 'w') as f:
        f.write(output.model_dump_json(indent=2))


async def hpo_linking_task_async(paper_db: PaperDB) -> None:
    with open(paper_db.phenotype_linking_json_path, 'r') as f:
        phenotype_data = json.load(f)

    phenotype_linking = PhenotypeLinkingOutput(**phenotype_data)
    term_lookup = build_term_lookup()

    # Add HPO candidates to each phenotype
    for entry in phenotype_linking.phenotypes:
        candidates = find_matching_hpo_terms(entry.text, term_lookup=term_lookup)
        entry.candidates = candidates

    # Exclude optional fields to keep agent input clean
    phenotype_data_filtered = phenotype_linking.model_dump(
        exclude={'notes', 'onset', 'location', 'severity', 'modifier', 'section'}
    )
    result = await Runner.run(
        hpo_linking_agent,
        f'Phenotypes JSON:\n{json.dumps(phenotype_data_filtered, indent=2)}',
        max_turns=5 * len(phenotype_linking.phenotypes),
    )

    json_response = result.final_output.model_dump_json(indent=2)
    with open(paper_db.phenotype_linking_json_path, 'w') as f:
        f.write(json_response)


def initial_extraction(paper_id: str, gene_symbol: str) -> None:
    async def _run_extraction_pipeline(paper_id: str, gene_symbol: str) -> None:
        await asyncio.gather(
            parse_paper_task_async(paper_id),
            parse_patients_task_async(paper_id),
            extract_variants_task_async(paper_id, gene_symbol),
            pedigree_describer_task_async(paper_id),
        )

    max_attempts = RETRIES + 1
    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=PipelineStatus.EXTRACTION_RUNNING)
        )
    for attempt in range(1, max_attempts + 1):
        try:
            parse_content(paper_id, force=True)
            asyncio.run(_run_extraction_pipeline(paper_id, gene_symbol))
            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=PipelineStatus.EXTRACTION_COMPLETED)
                )
            logger.info(f'Extraction attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise
        except Exception:
            logger.exception(f'Extraction failed on attempt {attempt}')
            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=PipelineStatus.EXTRACTION_FAILED)
                    )
                return


def linking_tasks(paper_id: str) -> None:
    async def _run_linking_pipeline(paper_db: PaperDB) -> None:
        await asyncio.gather(
            harmonize_variants_task_async(paper_db),
            patient_variant_linking_task_async(paper_db),
            phenotype_patient_linking_task_async(paper_db),
        )
        await asyncio.gather(
            enrich_variants_task_async(paper_db),
            hpo_linking_task_async(paper_db),
        )

    max_attempts = RETRIES + 1
    with session_scope() as session:
        session.execute(
            update(PaperDB)
            .where(PaperDB.id == paper_id)
            .values(pipeline_status=PipelineStatus.LINKING_RUNNING)
        )
    for attempt in range(1, max_attempts + 1):
        try:
            paper_db = PaperDB(id=paper_id).with_content()
            asyncio.run(_run_linking_pipeline(paper_db))
            with session_scope() as session:
                session.execute(
                    update(PaperDB)
                    .where(PaperDB.id == paper_id)
                    .values(pipeline_status=PipelineStatus.COMPLETED)
                )
            logger.info(f'Attempt {attempt}/{max_attempts} succeeded')
            return
        except KeyboardInterrupt:
            logger.info(f'Interrupted on attempt {attempt}')
            raise
        except Exception as e:
            logger.exception(f'Linking failed on attempt {attempt}')
            if attempt == max_attempts:
                with session_scope() as session:
                    session.execute(
                        update(PaperDB)
                        .where(PaperDB.id == paper_id)
                        .values(pipeline_status=PipelineStatus.LINKING_FAILED)
                    )
                return


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
                                PaperDB.last_modified < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.last_modified.asc())  # oldest first
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
                                PaperDB.last_modified < expired_cutoff,
                            ),
                        )
                    )
                    .order_by(PaperDB.last_modified.asc())
                    .limit(1)
                ).first()

                if linking_job:
                    paper_id = linking_job.id
                    logger.info(f'Dequeued paper {paper_id} for linking')

            if linking_job:
                linking_tasks(paper_id)
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
