import time
from collections import defaultdict
from pathlib import Path

import hpotk
import requests

from lib.core.environment import env

ONTOLOGY_ENDPOINT = 'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.json'
MAX_AGE_S = 7 * 24 * 60 * 60  # 7 days


def ontology_path() -> Path:
    return env.reference_data_dir / 'hpo.json'


def download_ontology() -> Path:
    path = ontology_path()
    tmp_path = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(ONTOLOGY_ENDPOINT, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    tmp_path.replace(path)
    return path


def ensure_ontology() -> Path:
    path = ontology_path()
    if not path.exists():
        return download_ontology()
    age = time.time() - path.stat().st_mtime
    if age > MAX_AGE_S:
        return download_ontology()
    return path


def build_term_lookup() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
    hpo = hpotk.load_ontology(str(ensure_ontology()))
    term_lookup = defaultdict(list)
    for term in hpo.terms:
        term_lookup[term.name.lower()].append(term.identifier)
        if not term.synonyms:
            continue
        for syn in term.synonyms:
            term_lookup[syn.name.lower()].append(term.identifier)
    return term_lookup
