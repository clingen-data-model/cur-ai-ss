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
uv run ruff check lib              # Run ruff linter
uv run ruff format --check lib test  # Check code formatting with ruff
uv run mypy lib                    # Run mypy type checking
uv run pytest test --cov=lib --cov-report=term-missing  # Run all tests with coverage
uv run pytest test/path/to/test_file.py  # Run a specific test
```

**Run the application (three separate terminals):**
```bash
./bin/api       # FastAPI backend (port 8000)
./bin/ui        # Streamlit frontend (port 8501)
./bin/worker    # Background job processor
```

**Frontend setup (first time only):**
```bash
cd frontend
pnpm install
pnpm dlx skills add shadcn/ui   # Install shadcn/ui AI skill (gitignored, run once per machine)
```

**Frontend commands** (from `frontend/`; not covered by CI, so run them before deploying):
```bash
pnpm dev          # Vite dev server on port 8501 (conflicts with ./bin/ui)
pnpm type-check   # tsc --noEmit
pnpm lint         # eslint
pnpm build        # regenerates the API client, then tsc -b && vite build
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

**Four components:**

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

3. **React SPA** (`frontend/`)
   - React 19 + TypeScript + Vite, Tailwind v4, shadcn/ui primitives vendored into `src/components/ui/`
   - TanStack Router and TanStack Query. Route components live in
     `src/routes/`, but the route table `src/routeTree.ts` is **hand-written** —
     the TanStack codegen plugin is not installed, so adding a component there
     does nothing until it is imported, declared and listed in `addChildren`
   - The API client in `src/api/generated/` is generated from the FastAPI OpenAPI schema
     by `pnpm build` — never edit it by hand, and regenerate after changing API models
   - In-progress replacement for the Streamlit UI, deployed in parallel under `/v2`
   - **See `frontend/README.md`** for architecture, the base-path rules, and a
     description of every JavaScript dependency

4. **Background Worker** (`lib/bin/worker.py`)
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
6. **Variant Annotation** → Adds annotations (SpliceAI, etc.)
7. **Phenotype Extraction + HPO Linking** → Links phenotypes to HPO ontology terms
8. **Patient-Variant Linking** → Links patients to their variants with inheritance info

Each agent is implemented with OpenAI API calls. Output files are stored in JSON format alongside the PDF.

### Data Models

All models are defined with Pydantic (for serialization) and SQLAlchemy ORM (for database):

- **Paper** (`lib/models/paper.py`) - Represents a research paper with pipeline status and path references
- **Patient** (`lib/models/patient.py`) - Patient demographics and clinical data
- **Phenotype** (`lib/models/phenotype.py`) - Extracted phenotypes with HPO matching candidates and confidence scores
- **Variant** (`lib/models/variant.py`) - Extracted, harmonized, and annotated variants
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
- `EXTRACTION_MODEL` - Text-extraction model as `<provider>/<model>` (default: `openai/gpt-5.6-luna`); prefix required; the
  dev-caa deployment overrides this to `anthropic/claude-haiku-4-5-20251001` in
  `infrastructure/ansible/templates/env.j2`
- `VLM_MODEL` - Vision model, same form (default: `openai/gpt-5.6-sol`; the
  dev-caa deployment overrides this to `anthropic/claude-fable-5-1` in
  `infrastructure/ansible/templates/env.j2`)
- `OPENAI_API_KEY` - required whenever a configured model names `openai/`
- `JWT_SECRET_KEY` - Secret used to sign auth access tokens (set a strong value in prod)

**Optional:**
- `ANTHROPIC_API_KEY` - required whenever a configured model names `anthropic/`. `anthropic/` routes through LiteLLM; `openai/` goes to the agents SDK's default provider. The two settings may name different providers, so vision and extraction can be pointed at different providers independently. Extraction used to be pinned to OpenAI because `responses_api_model()`'s server-side `conversation_id` had no Anthropic equivalent; that dependency is gone now that `lib.tasks.agent_session` gives every task its own provider-agnostic `SQLiteSession` (see `docs/anthropic-migration.md`), so extraction can run on Claude too -- verified live against the MASP1 test paper (PMID 26419238) before flipping dev-caa to it
- `NCBI_API_KEY` / `NCBI_EMAIL` - For variant enrichment
- `API_ENDPOINT` - Where UI reaches API (default: `localhost:8000`)
- `CORS_ALLOWED_ORIGINS` - CORS origins (default: `http://localhost:8501`)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `JWT_ALGORITHM` - JWT signing algorithm (default: `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token lifetime (default: `1440`)

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

**SQLAlchemy enum columns round-trip through the member's *name*, not its value** — `SQLEnum(SomeEnum)` with no `values_callable` stores e.g. `'COMPLETED'`, not `'completed'` (see `TaskStatus`). A `server_default` (or any raw-SQL backfill) that writes the lowercase *value* instead of the uppercase *name* leaves rows the ORM cannot map back to an enum member — a `LookupError` on every read, not on write, so it passes the migration and only surfaces the first time something queries the table. This broke `GET /papers` (and the whole dashboard) in production on 2026-09-17: migration `f3a8c2d914b7` added `papers.review_status` with `server_default=ReviewStatus.NOT_ASSIGNED.value`; fixed by `4a424fffb965`, which repairs the already-written data and corrects the default to `.name`. When adding a new enum column, default it to the member's name, and confirm by reading a freshly-migrated row back through the ORM (not just checking the raw SQL value) before merging.

**Database migrations (SQLite safety):**

When using `batch_alter_table()` on any table that has CASCADE foreign keys pointing to it, you **MUST disable foreign key constraints** before the batch operation, then re-enable them. Otherwise, when SQLite drops and recreates the table, CASCADE constraints will delete child rows unexpectedly.

**`PRAGMA foreign_keys` is a no-op inside an open transaction** (documented SQLite behavior), and alembic's `env.py` (`context.begin_transaction()`) already has one open by the time `upgrade()` runs. `connection.execute(text('PRAGMA foreign_keys = OFF'))` alone therefore silently does nothing — this is exactly what caused both the June 2026 incident below and a September 2026 repeat (migration `f3a8c2d914b7`, wiped every row in patients/families/variants/tasks/chat_messages; recovered from a same-day backup with ~9 hours of data loss).

**Do not "fix" this with `connection.commit()`.** A same-day follow-up incident: calling `.commit()` directly on the connection deactivates alembic's own managed transaction object. The DDL/data changes still commit, but alembic's post-migration `alembic_version` bookkeeping write then lands in a transaction whose final commit (at the end of `context.begin_transaction()`) silently becomes a no-op — so whichever migration runs *last* in a given `alembic upgrade head` invocation leaves `alembic_version` one revision behind the schema it actually produced. No exception, no warning; it only surfaces when a later migration tries to re-run against a table that already has the change, or (worse) when that stale-versioned re-run hits this exact CASCADE bug a second time. Use `op.get_context().autocommit_block()` — alembic's own supported mechanism for stepping outside its managed transaction — instead.

**Safe pattern for batch alterations:**
```python
from alembic import op

def upgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('table_name', schema=None) as batch_op:
            batch_op.add_column(...)
            # ... other operations
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
```

**Additional rules:**
- **NEVER use `ondelete='CASCADE'` when adding new foreign keys inside batch_alter_table** — add the column first, then the constraint separately in a non-batch operation.
- Always backup before running complex migrations (especially those involving multiple batches or adding CASCADE constraints).
- After migrations, verify data integrity: check row counts on tables with cascade relationships.
- This pattern is critical for tables like `families` (has CASCADE dependents like `patients`) — June 2026 migration `3b2d941d02a2` deleted all patients because FK constraints weren't actually disabled (see above: the `execute(text(...))` form never worked in the first place).
- Before trusting a new batch-alter migration against real data, reproduce the exact scenario locally first: create the parent + a CASCADE child row, run the migration, assert the child row survives, run `alembic upgrade head` a second time and confirm it's a clean no-op (proves `alembic_version` actually landed). Do not rely on the migration completing without error — both failure modes here are completely silent and only show up later, as missing rows or as a stale version re-running destructive DDL.

**Agent implementation:**
- Agents use `openai_agents` library (structured outputs)
- Store outputs in JSON files alongside PDFs (paths via `lib/misc/pdf/paths.py`)
- Update database with converter functions (`lib/models/converters.py`)
- Log with Python's `logging` module
- **See `lib/agents/AGENT_GUIDE.md` for writing new agents** — tools, instructions, output models, calling patterns

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

**Generating API specification:**
```bash
./bin/generate-api-spec
```
Extracts OpenAPI schema from FastAPI app and generates `frontend/api-spec.json`. Does not require running the API server.

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

**Deployment:** One GCP VM (`dev-caa`, domain `gene-curation-ai.app`) behind nginx:
Streamlit at `/`, FastAPI at `/api/` (prefix stripped), the React SPA's static build at
`/v2/`. Deploy with `ansible-playbook -i dev-caa.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml`,
which pulls `main` from GitHub — so changes must be merged and pushed before deploying.
See the Deployment section of `README.md`.

**The SPA is served under a path prefix**, so anything root-relative in `frontend/` must
be built from `import.meta.env.BASE_URL` or it escapes `/v2` and hits the Streamlit app:

- Navigate with `<Link>` from TanStack Router, never `<a href="/...">`
- Reference `public/` assets as `` `${import.meta.env.BASE_URL}<file>` `` in TSX, or
  `%BASE_URL%<file>` in `index.html`
- Build API-served URLs (PDFs, thumbnails) from `API_BASE_URL` exported by `lib/api.ts`,
  not from `import.meta.env.VITE_API_URL` directly
