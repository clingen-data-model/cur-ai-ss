import inspect
import os
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from lib.core.model_names import (
    PROVIDER_KEY_SETTINGS,
    ROUTABLE_PROVIDERS,
    split_provider,
)


class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.environ.get('ENV_FILE', '.env'))

    NCBI_API_KEY: Optional[str] = None
    NCBI_EMAIL: Optional[str] = None

    # Model selection: LiteLLM-style '<provider>/<model>' names, prefix
    # required ('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5').
    # 'openai/' goes to the agents SDK's default provider, 'anthropic/'
    # through LiteLLM -- see lib/agents/model_factory.py.
    EXTRACTION_MODEL: str = 'openai/gpt-5.6-luna'
    VLM_MODEL: str = 'openai/gpt-5.6-sol'
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LOG_LEVEL: LogLevel = LogLevel.INFO

    # SMTP (optional — if unset, registration emails are logged but not sent)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = 'noreply@localhost'

    # Auth / JWT
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Directories
    CAA_ROOT: str = '/var/caa'
    SQLLITE_DIR: str = 'sqllite'
    EXTRACTED_PDF_DIR: str = 'extracted_pdfs'
    REFERENCE_DATA_DIR: str = 'reference_data'

    # Reference data
    MONDO_ONTOLOGY_URL: str = 'https://purl.obolibrary.org/obo/mondo.json'
    HPO_ONTOLOGY_URL: str = 'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.json'

    # UI->API
    API_ENDPOINT: str = 'localhost:8000'
    PROTOCOL: str = 'http://'

    # API allowed origins
    CORS_ALLOWED_ORIGINS: str = 'http://localhost:8501'  # Comma-separated list

    # Feature Flags
    SKIP_DATA_MIGRATIONS: bool = False

    @model_validator(mode='after')
    def validate_ncbi_settings(self) -> 'Env':
        if self.NCBI_API_KEY and not self.NCBI_EMAIL:
            raise ValueError('If NCBI_API_KEY is specified, NCBI_EMAIL is required.')
        return self

    @model_validator(mode='after')
    def validate_models(self) -> 'Env':
        """Each configured model must name a routable provider and have its key.

        Checking routability here is what makes a bad provider fail loudly: it
        raises at settings load, before any agent exists. Left to resolve_model,
        the same error reaches the vision tools inside a function_tool body,
        where the SDK's default handler turns it into text for the model and the
        run persists a plausible-looking empty result instead of failing.
        """
        for setting, model in (
            ('EXTRACTION_MODEL', self.EXTRACTION_MODEL),
            ('VLM_MODEL', self.VLM_MODEL),
        ):
            provider, _ = split_provider(model)
            if provider not in ROUTABLE_PROVIDERS:
                supported = ', '.join(sorted(ROUTABLE_PROVIDERS))
                raise ValueError(
                    f'{setting}={model!r} names provider {provider!r}, which has '
                    f'no route yet. Supported: {supported}.'
                )
            key_setting = PROVIDER_KEY_SETTINGS[provider]
            if not getattr(self, key_setting):
                raise ValueError(f'{setting}={model!r} requires {key_setting}.')
        return self

    @field_validator('NCBI_EMAIL', mode='after')
    def encode_email(cls, v: Optional[str]) -> Optional[str]:
        # Avoid quoting None
        return quote(v) if v else v

    @property
    def sqlite_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.SQLLITE_DIR

    @property
    def extracted_pdf_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.EXTRACTED_PDF_DIR

    @property
    def reference_data_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.REFERENCE_DATA_DIR

    def init_dirs(self) -> None:
        root = Path(self.CAA_ROOT)
        if not root.is_absolute():
            raise RuntimeError(f'CAA_ROOT must be an absolute path: {root}')
        root.mkdir(parents=True, exist_ok=True)
        for name, prop in inspect.getmembers(
            type(self), lambda x: isinstance(x, property)
        ):
            if name.endswith('_dir'):
                path = getattr(self, name)
                if isinstance(path, Path):
                    path.mkdir(parents=True, exist_ok=True)


env = Env()  # type: ignore[call-arg]
env.init_dirs()
