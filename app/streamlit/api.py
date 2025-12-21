import requests

from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env


def get_papers():
    resp = requests.get(f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers')
    resp.raise_for_status()
    return resp.json()


def get_paper(paper_id: str):
    resp = requests.get(f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers/{paper_id}')
    resp.raise_for_status()
    return resp.json()


def put_paper(uploaded_file):
    paper = {
        'id': Paper.from_content(uploaded_file.read()).id,
        'file_name': uploaded_file.name,
    }
    resp = requests.put(
        f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers',
        json=paper,
        headers={'Content-Type': 'application/json'},  # optional but explicit
    )
    resp.raise_for_status()
    return resp.json()
