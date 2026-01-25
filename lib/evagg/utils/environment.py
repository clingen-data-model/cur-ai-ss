import os
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.environ.get('ENV_FILE', '.env'))

    NCBI_EUTILS_API_KEY: Optional[str] = None
    NCBI_EUTILS_EMAIL: Optional[str] = None

    # Required fields
    OPENAI_API_DEPLOYMENT: str = "gpt-5-mini"
    OPENAI_API_KEY: str = Field(...)
    LOG_LEVEL: LogLevel = LogLevel.INFO

    # Directories
    CAA_ROOT: str = '/var/caa'
    SQLLITE_DIR: str = 'sqllite'
    EVAGG_DIR: str = 'evagg'
    EXTRACTED_PDF_DIR: str = 'extracted_pdfs'
    LOG_DIR: str = 'logs'

    # API
    API_HOSTNAME: str = 'localhost'
    API_PORT: int = 8000
    CORS_ALLOWED_ORIGINS: str = 'http://localhost:8501'  # Comma-separated list

    @model_validator(mode='after')
    def validate_ncbi_settings(self) -> 'Env':
        if self.NCBI_EUTILS_API_KEY and not self.NCBI_EUTILS_EMAIL:
            raise ValueError(
                'If NCBI_EUTILS_API_KEY is specified, NCBI_EUTILS_EMAIL is required.'
            )
        return self

    @field_validator('NCBI_EUTILS_EMAIL', mode='after')
    def encode_email(cls, v: Optional[str]) -> Optional[str]:
        # Avoid quoting None
        return quote(v) if v else v

    @property
    def sqlite_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.SQLLITE_DIR

    @property
    def evagg_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.EVAGG_DIR

    @property
    def extracted_pdf_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.EXTRACTED_PDF_DIR

    @property
    def log_dir(self) -> Path:
        return Path(self.CAA_ROOT) / self.LOG_DIR

    def init_dirs(self) -> None:
        root = Path(self.CAA_ROOT)
        if not root.is_absolute():
            raise RuntimeError(f'CAA_ROOT must be an absolute path: {root}')
        for p in (
            root,
            self.sqlite_dir,
            self.evagg_dir,
            self.extracted_pdf_dir,
            self.log_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


env = Env()  # type: ignore[call-arg]
env.init_dirs()
