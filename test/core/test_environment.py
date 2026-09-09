import pytest
from pydantic import ValidationError

from lib.core.environment import Env

BASE = {
    'JWT_SECRET_KEY': 'test-secret-key-padded-to-thirty-two-plus-bytes',
    'OPENAI_API_KEY': 'sk-openai',
}


def _env(**overrides) -> Env:
    # _env_file=None so a developer's own .env cannot leak into the assertion.
    return Env(_env_file=None, **{**BASE, **overrides})


def test_prefixed_openai_models_validate():
    env = _env(EXTRACTION_MODEL='openai/gpt-5.6-luna', VLM_MODEL='openai/gpt-5.6-sol')

    assert env.EXTRACTION_MODEL == 'openai/gpt-5.6-luna'
    assert env.VLM_MODEL == 'openai/gpt-5.6-sol'


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_model_names_are_rejected(name):
    with pytest.raises(ValidationError, match='provider prefix'):
        _env(EXTRACTION_MODEL=name)


def test_openai_model_requires_openai_key():
    with pytest.raises(ValidationError, match='requires OPENAI_API_KEY'):
        _env(EXTRACTION_MODEL='openai/gpt-5.6-luna', OPENAI_API_KEY=None)


def test_anthropic_model_requires_anthropic_key():
    with pytest.raises(ValidationError, match='requires ANTHROPIC_API_KEY'):
        _env(EXTRACTION_MODEL='anthropic/claude-sonnet-5')


def test_vlm_model_is_validated_too():
    """Both configured models are checked, not just the extraction one."""
    with pytest.raises(ValidationError, match='requires ANTHROPIC_API_KEY'):
        _env(VLM_MODEL='anthropic/claude-sonnet-5')
