"""HTTP front for ``convert_content``, meant to run on Cloud Run.

One request converts one document. The input and the result live in object
storage, not in the HTTP body (PDFs and results are tens of MB; Cloud Run caps
HTTP/1 requests at 32 MB). The caller names the absolute ``json_path`` /
``words_path`` it will load the result from, the service writes them there, and
the whole directory travels back as one archive -- see ``convert_archive``.

Authentication is Cloud Run IAM (deploy without public access); this app does no
auth of its own. It handles one conversion at a time because the paths are the
caller's and conversion needs the instance's memory.
"""

import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from lib.docling_service import storage
from lib.misc.pdf.convert import convert_content
from lib.misc.pdf.convert_archive import pack_tree
from lib.misc.pdf.convert_result import save_convert_result
from lib.misc.pdf.file_format import FileFormat

logger = logging.getLogger(__name__)

# Requests may only write below this directory.
ALLOWED_ROOT = Path(os.environ.get('DOCLING_ALLOWED_ROOT', '/var/caa'))

app = FastAPI(title='docling-service')
_convert_lock = threading.Lock()


class ConvertRequest(BaseModel):
    input_uri: str
    output_uri: str
    json_path: str
    words_path: str
    file_format: FileFormat = FileFormat.PDF


class ConvertResp(BaseModel):
    seconds: float


def _checked(path_str: str) -> Path:
    path = Path(os.path.normpath(path_str))
    if not path.is_absolute() or not path.is_relative_to(ALLOWED_ROOT):
        raise HTTPException(400, f'{path_str!r} is not under {ALLOWED_ROOT}')
    return path


@app.get('/healthz')
def healthz() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/convert')
def convert(req: ConvertRequest) -> ConvertResp:
    json_path, words_path = _checked(req.json_path), _checked(req.words_path)
    if req.file_format == FileFormat.XLSX:
        raise HTTPException(400, 'xlsx is not converted by Docling')
    if json_path.parent != words_path.parent:
        raise HTTPException(400, 'json_path and words_path must share a directory')
    out_dir = json_path.parent
    if out_dir == ALLOWED_ROOT:
        # The directory is deleted after the request; never the root itself.
        raise HTTPException(400, f'paths must be in a subdirectory of {ALLOWED_ROOT}')

    with _convert_lock:
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / 'content'
                storage.download(req.input_uri, raw)
                result = convert_content(raw.read_bytes(), req.file_format)
                save_convert_result(result, json_path, words_path)
                archive = Path(tmp) / 'result.tar.gz'
                pack_tree(out_dir, archive)
                storage.upload(archive, req.output_uri)
        finally:
            # Cloud Run's filesystem is memory: leave nothing behind.
            shutil.rmtree(out_dir, ignore_errors=True)
        seconds = time.monotonic() - started
    logger.info('converted %s in %.1fs', req.input_uri, seconds)
    return ConvertResp(seconds=seconds)
