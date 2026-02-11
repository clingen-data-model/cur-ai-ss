# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for package management and `make` for common development tasks. **Prefer make targets over raw commands when available**:

- **Run all CI checks**: `make ci` or `make` (default target) — runs linting, type checking, format checking, and tests
- **Run tests**: `make test` — runs pytest with coverage (sets `ENV_FILE=.env.test` automatically)
- **Run linting**: `make lint` — runs `ruff check`
- **Run type checking**: `make type` — runs mypy
- **Run format check**: `make format` — runs `ruff format --check`
- **Run all linters**: `make all-lint` — runs lint + type + format
- **Auto-fix lint and formatting**: `make fix` — runs `ruff check --fix` and `ruff format`
- **Run single test file**: `ENV_FILE=.env.test uv run pytest test/path/to/test_file.py`
- **Install dependencies**: `uv sync` (after making changes to pyproject.toml)

## Formatting

After all code edits, run `make fix` to auto-fix import sorting and formatting.

## Architecture Overview

Evidence Aggregator is a system for extracting and aggregating genetic variant evidence from scientific papers using AI. It runs as a three-component full-stack application, plus a standalone CLI tool.

### Full-Stack Application

The full-stack app consists of three processes:

1. **FastAPI API** (`lib/api/app.py`) — REST API for paper and gene management. Run with `./bin/api`. On startup, runs Alembic migrations. Endpoints: `/papers`, `/papers/{id}`, `/papers/{id}/patients`, `/papers/{id}/variants`, `/genes`, `/status`.

2. **Streamlit UI** (`lib/ui/streamlit_app.py`) — Web frontend. Run with `./bin/ui`. Pages: dashboard (paper list) and details (single paper view). Communicates with the API via HTTP (`lib/ui/api.py`).

3. **Worker** (`lib/bin/worker.py`) — Background job processor. Run with `./bin/worker`. Polls the database for papers with `QUEUED` status, then for each paper: parses the PDF, extracts metadata via LLM + NCBI lookup, runs patient and variant extraction agents concurrently (OpenAI Agents SDK), and persists results to the database.

### CLI Tool

`lib/bin/extract_single_pdf.py` — Standalone single-paper extraction using the `App` class from `lib/evagg/app.py`. Takes `--pdf`, `--gene-symbol`, and `--retries` arguments.

### Key Modules

- `lib/api/` — FastAPI app (`app.py`) and database layer (`db.py`: `get_engine()`, `get_sessionmaker()`, `get_session()`, `session_scope()`)
- `lib/ui/` — Streamlit UI (`streamlit_app.py`, `dashboard.py`, `details.py`, `api.py`, `helpers.py`)
- `lib/bin/` — Entry points (`worker.py`, `extract_single_pdf.py`)
- `lib/agents/` — OpenAI Agents SDK agent definitions (`patient_extraction_agent.py`, `variant_extraction_agent.py`)
- `lib/models/` — SQLAlchemy models (`GeneDB`, `PaperDB`, `PatientDB`, `VariantDB`), Pydantic response models, and `converters.py` (agent output to DB conversion)
- `lib/evagg/app.py` — `App` class: single-paper extraction pipeline (content extraction, VEP/ClinVar/gnomAD enrichment)
- `lib/evagg/content/` — Content extraction (prompt-based, observation finding, HGVS variant handling)
- `lib/evagg/ref/` — Reference data providers (NCBI, VEP, ClinVar, gnomAD, HPO, Mutalyzer, RefSeq)
- `lib/evagg/llm/` — OpenAI client
- `lib/evagg/pdf/` — PDF parsing and thumbnail generation
- `lib/evagg/types/` — Type definitions (`Paper`, `PromptTag`)
- `lib/evagg/utils/` — Environment config (pydantic-settings), web client
- `lib/evagg/library/` — Paper retrieval
- `migrations/` — Alembic database migrations

### Configuration

Environment variables are managed via pydantic-settings (`lib/evagg/utils/environment.py`), loaded from an `.env` file (overridden by the `ENV_FILE` env var). Key variables: `OPENAI_API_KEY`, `CAA_ROOT` (data directory, default `/var/caa`), `API_ENDPOINT`, `CORS_ALLOWED_ORIGINS`.

### Database

SQLite via SQLAlchemy. Alembic migrations in `migrations/` (not `alembic/`, to avoid Python import conflicts). The migrations directory is configured in `alembic.ini`.

### Testing

Tests are under `test/` mirroring the `lib/` structure. Tests require `ENV_FILE=.env.test` (the `.env.test` file should set `CAA_ROOT` to a temp directory like `/tmp/caa_test`). The `make test` target sets this automatically.