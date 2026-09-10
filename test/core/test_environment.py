import pytest
from pydantic import ValidationError

from lib.core.environment import Env

# Both keys are pinned explicitly, including to None: Env still reads os.environ,
# so without this a developer with ANTHROPIC_API_KEY exported gets different
# results than CI. An explicit None in init kwargs does override the environment.
BASE = {
    'JWT_SECRET_KEY': 'test-secret-key-padded-to-thirty-two-plus-bytes',
    'OPENAI_API_KEY': 'sk-openai',
    'ANTHROPIC_API_KEY': None,
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


def test_unroutable_provider_is_rejected_even_with_its_key():
    """Settings load is the only place this can fail loudly -- resolve_model is
    called from inside function_tool bodies, which swallow exceptions."""
    with pytest.raises(ValidationError, match='no route yet'):
        _env(
            EXTRACTION_MODEL='anthropic/claude-sonnet-5',
            ANTHROPIC_API_KEY='sk-ant',
        )


def test_misspelled_provider_cannot_skip_the_key_check():
    """A typo'd prefix still parses, so an unknown provider must not fall
    through the key checks."""
    with pytest.raises(ValidationError, match='no route yet'):
        _env(EXTRACTION_MODEL='opanai/gpt-5.6-luna', OPENAI_API_KEY=None)


def test_vlm_model_is_validated_too():
    """Both configured models are checked, not just the extraction one."""
    with pytest.raises(ValidationError, match='no route yet'):
        _env(VLM_MODEL='anthropic/claude-sonnet-5', ANTHROPIC_API_KEY='sk-ant')


def test_the_failing_setting_is_named():
    """The message says which setting to go fix."""
    with pytest.raises(ValidationError, match='VLM_MODEL='):
        _env(VLM_MODEL='gemini/some-model')
