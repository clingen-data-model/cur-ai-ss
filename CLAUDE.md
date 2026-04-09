# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

**Install dependencies:**
```bash
uv sync
uv pip install -e .
```

**Common commands:**
```bash
make ci              # Run linting, formatting, type checks, and tests (required for PRs)
make test            # Run tests with coverage report
make lint            # Run ruff linter
make format          # Check code formatting with ruff
make type            # Run mypy type checking

uv run pytest test/path/to/test_file.py  # Run a specific test
```

**Run the application (three separate terminals):**
```bash
./bin/api       # FastAPI backend (port 8000)
./bin/ui        # Streamlit frontend (port 8501)
./bin/worker    # Background job processor
```

**Database migrations:**
```bash
alembic current             # Check current migration version
alembic upgrade head        # Apply pending migrations
alembic revision --autogenerate -m "description"  # Create new migration
```

## Project Architecture

This is a research paper analysis system that extracts genetic information (patients, phenotypes, variants) from scientific papers and links them to standard databases (HPO for phenotypes).

### Core Components

**Three-tier application:**

1. **Backend API** (`lib/api/app.py`)
   - FastAPI server handling PDF uploads, data storage, and retrieval
   - SQLite database (configured via `lib/api/db.py`)
   - CORS middleware configured for Streamlit UI access
   - Serves both API endpoints and static assets

2. **Frontend UI** (`lib/ui/streamlit_app.py`)
   - Multi-page Streamlit app (dashboard, paper views)
   - Dashboard lists papers and their extraction status
   - Paper pages show extracted patients, variants, phenotypes with editing capabilities
   - Renders PDF highlighting and thumbnails via API

3. **Background Worker** (`lib/bin/worker.py`)
   - Polls database for papers with extraction tasks
   - Runs extraction agents sequentially in a pipeline
   - Updates paper `pipeline_status` as tasks progress
   - Implements lease-based locking to prevent concurrent processing

### Extraction Pipeline

Papers flow through this sequence of agents (all triggered by worker):

1. **Paper Extraction** → Parses PDF, extracts metadata, markdown content, tables
2. **Patient Extraction** → Identifies patients, demographics, proband status
3. **Pedigree Description** → Describes family relationships
4. **Variant Extraction** → Extracts genetic variant information
5. **Variant Harmonization** → Normalizes variants to standard formats
6. **Variant Enrichment** → Adds annotations (SpliceAI, etc.)
7. **Phenotype Extraction + HPO Linking** → Links phenotypes to HPO ontology terms
8. **Patient-Variant Linking** → Links patients to their variants with inheritance info

Each agent is implemented with OpenAI API calls. Output files are stored in JSON format alongside the PDF.

### Data Models

All models are defined with Pydantic (for serialization) and SQLAlchemy ORM (for database):

- **Paper** (`lib/models/paper.py`) - Represents a research paper with pipeline status and path references
- **Patient** (`lib/models/patient.py`) - Patient demographics and clinical data
- **Phenotype** (`lib/models/phenotype.py`) - Extracted phenotypes with HPO matching candidates and confidence scores
- **Variant** (`lib/models/variant.py`) - Extracted, harmonized, and enriched variants
- **PatientVariantLink** (`lib/models/patient_variant_link.py`) - Links patients to variants with inheritance/testing info
- **Evidence** (`lib/models/evidence_block.py`) - Text blocks from paper supporting extracted data

Models use a consistent pattern:
- `SomeModel` - Pydantic base (serializable)
- `SomeDB` - SQLAlchemy ORM model (database)
- `SomeResp` - API response model (may include computed fields)
- `SomeUpdateRequest` - Pydantic model for PATCH requests

### Database

- **Engine:** SQLite with foreign key constraints enabled
- **Location:** `{CAA_ROOT}/sqllite/app.db` (see `lib/core/environment.py`)
- **Migrations:** Alembic under `migrations/versions/`
- **Session management:** `lib/api/db.py` provides `session_scope()` context manager and FastAPI dependency

Key tables:
- `papers` - Paper metadata and extraction status
- `patients` - Extracted patient information
- `extracted_phenotypes` - Raw extracted phenotype text with extraction confidence
- `hpos` - HPO term candidates matched to phenotypes
- `extracted_variants` - Raw variant extractions
- `harmonized_variants` - Normalized to standard genomic coordinates
- `enriched_variants` - With annotation data
- `patient_variant_links` - Patient-to-variant associations with inheritance/testing data

## Environment & Configuration

Configuration is in `lib/core/environment.py` using Pydantic BaseSettings:

**Required:**
- `OPENAI_API_KEY` - OpenAI API key (Bearer token)
- `OPENAI_API_DEPLOYMENT` - Model to use (default: `gpt-5-mini`)

**Optional:**
- `NCBI_API_KEY` / `NCBI_EMAIL` - For variant enrichment
- `API_ENDPOINT` - Where UI reaches API (default: `localhost:8000`)
- `CORS_ALLOWED_ORIGINS` - CORS origins (default: `http://localhost:8501`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

**Directories (relative to `CAA_ROOT`, default `/var/caa`):**
- `sqllite/` - Database file
- `extracted_pdfs/` - Parsed PDF content and output JSONs
- `evagg/` - (Legacy, may be deprecated)
- `logs/` - Application logs
- `reference_data/` - HPO data cache

Load from `.env` file or environment variables. Override with `ENV_FILE=.env.test` for testing.

## Testing

- **Framework:** pytest with asyncio support
- **Coverage:** Must maintain coverage for `lib/` (checked in CI)
- **Fixtures:** `test/conftest.py` provides shared fixtures

Run tests:
```bash
make test                    # All tests with coverage
uv run pytest test/          # All tests (no coverage)
uv run pytest test/api/test_app.py::test_function  # Specific test
```

**Test database:** Uses `ENV_FILE=.env.test` which should point to a test SQLite database or use in-memory database.

### Key Test Files

- `test/api/test_app.py` - API endpoint tests
- `test/models/test_converters.py` - Model conversion logic
- `test/migrations/test_alembic.py` - Database migration validation
- `test/evagg/pdf/` - PDF parsing tests
- `test/reference_data/test_hpo.py` - HPO data loading

## Code Patterns & Conventions

**Type hints:** Strict mypy configuration (`disallow_untyped_defs`). All functions must have type hints including return types.

**Imports:** Sorted by ruff with import-sorting rule (`I`).

**Formatting:** Single quotes for strings, ruff format rules applied.

**Pydantic models:**
- Use `BaseModel` for serializable objects
- Use `computed_field` for derived values (e.g., file paths)
- Use `field_validator` for input validation
- Use `model_validator` for cross-field validation

**Database access:**
- Use `session_scope()` context manager in background code
- Use FastAPI dependency injection in endpoints: `session: Session = Depends(get_session)`
- Explicitly handle `IntegrityError` for constraint violations

**Agent implementation:**
- Agents use `openai_agents` library (structured outputs)
- Store outputs in JSON files alongside PDFs (paths via `lib/misc/pdf/paths.py`)
- Update database with converter functions (`lib/models/converters.py`)
- Log with Python's `logging` module

## Common Tasks

**Adding a new extraction agent:**
1. Create agent in `lib/agents/new_agent.py` using `openai_agents.Runner`
2. Define output model with Pydantic
3. Create converter in `lib/models/converters.py` to convert to `*DB` model
4. Add agent call to worker pipeline in `lib/bin/worker.py`
5. Add database model in `lib/models/` if needed
6. Create migration: `alembic revision --autogenerate -m "add_new_agent_tables"`
7. Add API endpoints in `lib/api/app.py` for retrieving data
8. Add UI components in `lib/ui/paper/` for display/editing

**Adding a new API endpoint:**
1. Import or create Pydantic models in `lib/models/`
2. Add endpoint in `lib/api/app.py` following existing patterns
3. Use `session: Session = Depends(get_session)` for database access
4. Return appropriate HTTP status codes
5. Document response model

**Modifying UI:**
1. Edit relevant file in `lib/ui/paper/` (each entity type has its own file)
2. Use Streamlit data editors for user input
3. Call API endpoints to save changes
4. Use PDF highlighting via `lib/misc/pdf/highlight.py` utilities

## Important Notes

**PDF file organization:** All extracted content for a paper is stored in a directory named after the paper ID. Use path functions from `lib/misc/pdf/paths.py` to build consistent paths:
- `pdf_raw_path()`, `pdf_markdown_path()`, `pdf_highlighted_path()`, etc.

**Pipeline status:** `PipelineStatus` enum tracks paper extraction progress. Worker updates this. UI shows status with icons (⏳🟡❌✔️🎉).

**Task Management:**
- Tasks represent individual extraction steps in the pipeline
- Tasks have a type, status (Pending/Running/Completed/Failed), and optional scope (patient_id, variant_id, phenotype_id)
- Tasks form a dependency graph: when a task completes, successor tasks are automatically queued
- The "Rerun Agents" button in the UI (top-right of paper page) lets you re-run any task and its successors
- **Skip Successors:** Check "Skip successor tasks" when queueing a task to run ONLY that task without triggering dependent tasks. Useful for debugging or manual reruns. The flag is stored in `tasks.skip_successors` and checked by the worker when a task completes.
- Task models: `TaskDB` (ORM), `TaskResp` (API response), `TaskCreateRequest` (for queueing)
- Task status and dependency logic in `lib/tasks/models.py` and `lib/tasks/misc.py`

**Lease-based concurrency:** Worker uses database leases to prevent multiple workers processing the same paper. Lease timeout is 900s.

**PDF highlighting:** Words/images can be highlighted in PDFs with colors (red, orange, yellow, blue, green, violet, gray, primary). Uses Grobid annotations for word positioning.

**OpenAI agents:** Uses `openai_agents.Runner` for structured outputs. Models must have Pydantic schema for OpenAI to use as response schema.
