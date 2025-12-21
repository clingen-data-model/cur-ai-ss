import os
from enum import Enum
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
    OPENAI_API_DEPLOYMENT: str = Field(...)
    OPENAI_API_KEY: str = Field(...)
    LOG_LEVEL: LogLevel = LogLevel.INFO

    # Directories
    SQLLITE_DB_DIR: str = '/var/cur-ai-ss/sqllite'
    EXTRACTED_PDF_DIR: str = '/var/cur-ai-ss/extracted_pdfs'
    LOG_OUT_DIR: str = '/var/cur-ai-ss/logs'

    # API
    API_ENDPOINT: str = 'localhost'
    API_PORT: int = 8000

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


env = Env()  # type: ignore[call-arg]
