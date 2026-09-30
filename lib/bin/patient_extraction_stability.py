#!/usr/bin/env python3
"""Run patient extraction several times per paper and report whether it agrees with itself.

The patient extraction prompt decides who counts as a patient. When it leaves
room for interpretation, the same paper yields a different patient list on every
call (paper 80 gave 9, 20 and 25 on 2026-09-30). This script is the check to run
after touching that prompt: it sends the agent exactly the message production
sends (``lib.tasks.handlers.patient_extraction_message``) N times, each in a
fresh conversation, and compares the identifier sets. Nothing is written to the
database or to disk; the runs cost only model calls.

Exit status is 1 when any paper's runs disagree, so it can gate a re-run.

Usage:
    uv run python -m lib.bin.patient_extraction_stability --paper-id 80 [--paper-id N ...] [--runs 3]
"""

import argparse
import asyncio
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from agents import Runner, SQLiteSession

from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models.patient import PatientExtractionOutput, ProbandStatus
from lib.tasks.handlers import patient_extraction_message

logger = logging.getLogger(__name__)


@dataclass
class Report:
    """How a paper's runs compare."""

    stable: bool
    union: set[str]
    intersection: set[str]
    # Indexes (0-based) of the runs whose set differs from the most common one.
    # When no set occurs twice there is no majority and every run dissents.
    dissenting_runs: list[int]


def compare_runs(sets: list[set[str]]) -> Report:
    """Compare the identifier sets of several runs of one paper."""
    if not sets:
        return Report(stable=True, union=set(), intersection=set(), dissenting_runs=[])
    union = set().union(*sets)
    intersection = set.intersection(*sets)
    counts = Counter(frozenset(s) for s in sets)
    majority, occurrences = counts.most_common(1)[0]
    if occurrences == 1 and len(sets) > 1:
        dissenting = list(range(len(sets)))
    else:
        dissenting = [i for i, s in enumerate(sets) if frozenset(s) != majority]
    return Report(
        stable=not dissenting,
        union=union,
        intersection=intersection,
        dissenting_runs=dissenting,
    )


async def run_paper(paper_id: int, runs: int) -> Report:
    """Run the agent ``runs`` times on one paper and log each result."""
    with session_scope() as session:
        message = patient_extraction_message(session, paper_id)

    sets: list[set[str]] = []
    for run in range(runs):
        # A fresh in-memory conversation per run: no history shared between runs.
        conversation = SQLiteSession(
            session_id=f'stability-{paper_id}-{uuid4()}', db_path=':memory:'
        )
        result = await Runner.run(
            patient_extraction_agent, message, session=conversation
        )
        parsed = cast(PatientExtractionOutput, result.final_output)
        identifiers = {p.identifier.value for p in parsed.patients}
        probands = sorted(
            p.identifier.value
            for p in parsed.patients
            if p.proband_status.value == ProbandStatus.Proband
        )
        logger.info(
            f'paper {paper_id} run {run}: {len(identifiers)} patients '
            f'{sorted(identifiers)} probands {probands}'
        )
        sets.append(identifiers)

    report = compare_runs(sets)
    if report.stable:
        logger.info(f'paper {paper_id}: stable ({len(report.union)} patients)')
    else:
        logger.warning(
            f'paper {paper_id}: UNSTABLE, runs {report.dissenting_runs} disagree; '
            f'in every run {sorted(report.intersection)}; '
            f'in some runs only {sorted(report.union - report.intersection)}'
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--paper-id',
        type=int,
        action='append',
        required=True,
        help='Paper to run; repeat for several',
    )
    parser.add_argument('--runs', type=int, default=3, help='Runs per paper')
    args = parser.parse_args()

    setup_logging()
    reports = [
        asyncio.run(run_paper(paper_id, args.runs)) for paper_id in args.paper_id
    ]
    unstable = [
        paper_id
        for paper_id, report in zip(args.paper_id, reports, strict=True)
        if not report.stable
    ]
    if unstable:
        logger.warning(f'unstable papers: {unstable}')
        sys.exit(1)
    logger.info('all papers stable')


if __name__ == '__main__':
    main()
