"""The output of ``convert_content`` and how it is written to / read back from disk.

This is the contract between whatever runs Docling and the worker, so it only
needs ``docling_core`` (no torch, no models). The document is saved with
``ImageRefMode.REFERENCED``: each picture's crop is a file in ``raw_artifacts/``
next to the JSON, and the JSON records that file's *absolute* path. Loading
therefore only works if the artifacts sit at the same absolute path on the
machine that reads the JSON as on the one that wrote it. The worker chooses the
JSON path and the converter writes there, so both sides agree by construction.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from docling_core.types.doc import DoclingDocument, ImageRefMode

from lib.misc.pdf.words import WordLoc


@dataclass
class ConvertResult:
    document: DoclingDocument
    words: list[WordLoc]


def save_convert_result(
    result: ConvertResult, json_path: Path, words_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    result.document.save_as_json(json_path, image_mode=ImageRefMode.REFERENCED)
    words_path.parent.mkdir(parents=True, exist_ok=True)
    with open(words_path, 'w') as fp:
        json.dump([w.model_dump() for w in result.words], fp, indent=2)


def load_convert_result(json_path: Path, words_path: Path) -> ConvertResult:
    return ConvertResult(
        document=DoclingDocument.load_from_json(json_path),
        words=[WordLoc(**w) for w in json.loads(words_path.read_text())],
    )
