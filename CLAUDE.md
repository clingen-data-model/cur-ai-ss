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

**Run the application (three terminals):**
```bash
./bin/api       # FastAPI backend (port 8000)
./bin/worker    # Background job processor
./bin/ui        # React dev server on port 8501; `./bin/ui <script>` runs any pnpm script (Ansible uses install/build)
```

**Frontend setup (first time only):**
```bash
cd frontend
pnpm install
pnpm dlx skills add shadcn/ui   # Install shadcn/ui AI skill (gitignored, run once per machine)
```

**Frontend commands** (from `frontend/`; not covered by CI, so run them before deploying):
```bash
pnpm dev          # Vite dev server on port 8501
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

**Three components:**

1. **Backend API** (`lib/api/app.py`)
   - FastAPI server handling PDF uploads, data storage, and retrieval
   - SQLite database (configured via `lib/api/db.py`)
   - CORS middleware configured for the SPA's dev server
   - Serves both API endpoints and static assets

2. **React SPA** (`frontend/`)
   - React 19 + TypeScript + Vite, Tailwind v4, shadcn/ui primitives vendored into `src/components/ui/`
   - TanStack Router and TanStack Query. Route components live in
     `src/routes/`, but the route table `src/routeTree.ts` is **hand-written** —
     the TanStack codegen plugin is not installed, so adding a component there
     does nothing until it is imported, declared and listed in `addChildren`
   - The API client in `src/api/generated/` is generated from the FastAPI OpenAPI schema
     by `pnpm build` — never edit it by hand, and regenerate after changing API models
   - The only UI (Streamlit has been retired): dashboard, paper pages, PDF evidence
     viewer. Served at the site root
   - **See `frontend/README.md`** for architecture, the base-path rules, and a
     description of every JavaScript dependency

3. **Background Worker** (`lib/bin/worker.py`)
   - Polls database for papers with extraction tasks
   - Runs extraction agents sequentially in a pipeline
   - Updates paper `pipeline_status` as tasks progress
   - Admission from the tasks table: starts what the concurrency limits leave room for, with a lease per attempt

### Extraction Pipeline

Papers flow through this sequence of agents (all triggered by worker):

1. **Paper Extraction** → Parses PDF, extracts metadata, markdown content, tables
2. **Patient Extraction** → Identifies patients, demographics, proband status
3. **Figure Description** → Shows every figure to the vision model, which classifies it against the readable kinds (`FigureKind` in `lib/models/figure.py`: pedigree, chromatogram, gel, copy-number plot, read pileup, karyotype or FISH) and describes the ones that match; one `figure_descriptions` row per described figure, carrying the caption the model was shown (`caption`, the alt text of the figure's `[figure-N] ![caption](...)` line in anchored.md, which is where Docling's caption-to-picture link is transcribed at parse time; where Docling linked none, the parser's walk looks at the one part right under the picture and, if `_legend_item` accepts it (one visible heading or paragraph, not a list item, whose text opens like a figure label: `is_figure_legend`), folds it into the figure line as a Docling caption would be, alt text and caption boxes, marks the anchor `caption_adopted`, and skips the part so it is not printed twice; the comment above `_legend_item` in `lib/misc/pdf/anchors.py` spells out the four ways Docling's link fails on dev and the five steps of the rule, which recovered 9 of dev's 24 uncaptioned described figures on 2026-10-27, all below their picture; parsing runs first with no model, and the Figure Description step reads what it wrote: a readable figure whose line still carries no caption is asked of the vision model, `find_legend`, shown the headings and paragraphs within ten blocks either side (`figure_neighbourhoods`) and answering with a block id, a transcription of a legend drawn inside the image, or none; a legend further away than that is not found and the figure has no caption; the answer goes on the row, never into anchored.md; this settled the other 15 on dev, panels of one figure getting their own panel labels; `caption_source` (`CaptionSource`: Docling, Adjacent text, Model chose, Model transcribed) records which way each row's caption came, `Anchor.caption_adopted` in anchors.json telling the first two apart for a parse-time adoption; rows from before migration `b7e2f9c4d6a1` are filled by `lib.bin.backfill_figure_captions` from what `paper_figures` would hand a re-run (the figure line's caption, else the same question), `--no-model` to skip the question; a stored caption the figure line lacks is spliced under the line for the agents, `splice_figure_descriptions`). Not an agent (`lib/agents/figure_describer.py`), so it has no conversation to ask and curator notes go into its vision prompts. Every paper-reading agent then gets each description spliced into the paper text as a quoted block under its `[figure-N]` line (`paper_text` in `lib/tasks/handlers.py`, `lib/misc/pdf/figure_text.py`); the `/document` endpoint serves the same text, a quote from a description checks out against its figure, highlights the picture in the PDF view and both the figure and the span in the Markdown view
4. **Variant Extraction** → Extracts genetic variant information
5. **Variant Harmonization** → Normalizes variants to standard formats
6. **Variant Annotation** → Adds annotations (SpliceAI, etc.)
7. **Phenotype Extraction + HPO Linking** → Links phenotypes to HPO ontology terms. Phenotype extraction is queued per patient when their demographics completes, for every patient but those it marked Unaffected (a curator can still queue it for anyone); HPO linking follows for every phenotype the run produced that the HPO link cache did not already link, whatever the patient's variants (it used to wait for a variant occurrence, which saved ~15 calls a paper and left a manual phenotype run linking nothing)
8. **Patient-Variant Linking** → Links patients to their variants with inheritance info. Waits on Patient Extraction and Variant Extraction, not on demographics, which it never reads; segregation (evidence extraction, then the computed analysis) is the step that waits on the last per-patient demographics run, since it reads affected status (`TASK_SUCCESSORS` in `lib/tasks/models.py`)
9. **Extraction Verification** → Runs once every other task of the paper has settled (queued by the worker, not by a graph edge); merges curator flags that raise the same decision more than once (`lib/tasks/extraction_verification.py`)

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
  dev-caa deployment overrides this to `anthropic/claude-haiku-5-5` in
  `infrastructure/ansible/templates/env.j2`
- `LINKING_MODEL` - The model the two ontology-linking agents (HPO, MONDO) run on, same form (default: `openai/gpt-5.6-luna`; dev-caa sets `anthropic/claude-haiku-5-5`). Every other agent is on `EXTRACTION_MODEL`, which dev-caa moved to `anthropic/claude-sonnet-5-5` on 2026-10-22: the Haiku 5.5 trial showed its HPO links match Sonnet's, while no prompt fixed its paper-reading failures (skipped pedigree members on paper 108, a cohort-wide testing method applied to 3 of 11 subjects in three runs where Sonnet gave 11 of 11 in three). Linking is many small calls per paper, extraction a few large ones, so this is where the cost split pays
- `VLM_MODEL` - Vision model, same form (default: `openai/gpt-5.6-sol`; the
  dev-caa deployment overrides this to `anthropic/claude-opus-5-5` in
  `infrastructure/ansible/templates/env.j2`; it was Fable 5.1 until 2026-10-19,
  when Fable's safety classifier deterministically refused a table-correction
  call on paper 106 and failed its PDF parse). A classifier refusal through
  LiteLLM now raises `ModelDeclined` (`lib/agents/model_factory.py`) on the
  first turn instead of looping to `MaxTurnsExceeded`; table correction
  catches it and marks the table unrecovered
- `OPENAI_API_KEY` - required whenever a configured model names `openai/`
- `JWT_SECRET_KEY` - Secret used to sign auth access tokens (set a strong value in prod)

**Optional:**
- `ANTHROPIC_API_KEY` - required whenever a configured model names `anthropic/`. `anthropic/` routes through LiteLLM; `openai/` goes to the agents SDK's default provider. The two settings may name different providers, so vision and extraction can be pointed at different providers independently. Extraction used to be pinned to OpenAI because `responses_api_model()`'s server-side `conversation_id` had no Anthropic equivalent; that dependency is gone now that `lib.tasks.agent_session` gives every task its own provider-agnostic `SQLiteSession` (see `docs/anthropic-migration.md`), so extraction can run on Claude too -- verified live against the MASP1 test paper (PMID 26419238) before flipping dev-caa to it
- `NCBI_API_KEY` / `NCBI_EMAIL` - For variant enrichment
- `API_ENDPOINT` / `PROTOCOL` - Address the worker puts in the paper-completion email (default: `http://localhost:8000`)
- `CORS_ALLOWED_ORIGINS` - CORS origins (default: `http://localhost:8501`)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `JWT_ALGORITHM` - JWT signing algorithm (default: `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token lifetime (default: `1440`)

**Directories (relative to `CAA_ROOT`, default `/var/caa`):**
- `sqllite/` - Database file
- `documents/` - Per paper: the uploaded files, parsed and anchored text, table and figure images, thumbnail and extraction snapshots (layout in `lib/misc/pdf/paths.py`)
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
- Agent output goes to the database through the converters below, not to files beside the paper
- Update database with converter functions (`lib/models/converters.py`)
- Log with Python's `logging` module
- The word "reasoning" never reaches a model. Every evidence block's `reasoning` field is presented to the model as `basis` (`lib/agents/model_facing.py`: wrap `output_type` in `model_facing_output(...)`, write prompt prose with "basis"; `test_no_agent_prose_asks_for_reasoning` guards it). Anthropic's `reasoning_extraction` classifier otherwise cuts Sonnet 5.5 and Opus 5.5 off partway through the JSON (found 2026-10-22 on papers 108 and 106; Haiku has no such guard). The database, API and UI keep `reasoning`
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
8. Add UI components in `frontend/src/` for display/editing

**Adding a new API endpoint:**
1. Import or create Pydantic models in `lib/models/`
2. Add endpoint in `lib/api/app.py` following existing patterns
3. Use `session: Session = Depends(get_session)` for database access
4. Return appropriate HTTP status codes
5. Document response model

**Modifying UI:**
1. Edit the relevant component in `frontend/src/components/` or the route in `frontend/src/routes/`
2. Reuse the editable rows in `EditableField.tsx` for user input (they force a human-edit note)
3. Call the generated API client; regenerate it after changing API models
4. PDF highlighting comes from the `/highlight` endpoint (`lib/misc/pdf/highlight.py`)

**Generating API specification:**
```bash
./bin/generate-api-spec
```
Extracts OpenAPI schema from FastAPI app and generates `frontend/api-spec.json`. Does not require running the API server.

## Important Notes

**Paper file organization:** Everything on disk for a paper lives under `documents/<paper_id>/`: `thumbnail.png` and `snapshots/` at the top, then `main/` and `supplement/`, each holding the uploaded `raw.*`, `words.json`, `anchored.md`, `anchors.json`, `tables/` and `images/`. Tables and images are keyed by Docling index, the same N as the `table-N` and `figure-N` anchors. Use the `document_*` helpers in `lib/misc/pdf/paths.py`; the Docling document itself is not kept, so a re-parse (`parse_content(force=True)`) rebuilds everything from `raw.*`. The old `extracted_pdfs/` layout was retired in 2026-10 (PR #417 moved the last live files and the folder was deleted from dev-caa).

**Pipeline status:** `PipelineStatus` enum tracks paper extraction progress. Worker updates this. UI shows status with icons (⏳🟡❌✔️🎉).

**Task Management:**
- Tasks represent individual extraction steps in the pipeline
- Tasks have a type, status (Pending/Running/Completed/Failed), and optional scope (patient_id, variant_id, phenotype_id)
- Tasks form a dependency graph: when a task completes, successor tasks are automatically queued
- The "Rerun Agents" button in the UI (top-right of paper page) lets you re-run any task and its successors
- **Skip Successors:** Check "Skip successor tasks" when queueing a task to run ONLY that task without triggering dependent tasks. Useful for debugging or manual reruns. The flag is stored in `tasks.skip_successors` and checked by the worker when a task completes.
- **Re-run all tasks:** the dialog's "All tasks" tab queues PDF Parsing (with "Also re-parse the PDF") or Paper Classifier through `POST /papers/{id}/tasks` like any other task; there is no separate endpoint or paper field. Every task descends from those two, and a task's `additional_context` comes down the successor graph: `enqueue_successors` copies it to every descendant of that run with `tasks.context_origin` naming the task it was given to, so a note on the root is the run-all note, and the note reaches every agent worded "given for this re-run of the whole paper" (`curator_note_section` in `lib/tasks/handlers.py`; for any other origin, "supplied to X and might also be relevant here"). A descendant starts fresh with the note as the last item of its first message (`with_curator_note`), after the cache-breakpointed paper block, instructions and data; figure description, which has no conversation, puts the labelled note in its vision prompts; phenotype extraction skips the HPO link cache while its run has a note, so the HPO agent actually sees it. A note only ever becomes a follow-up to the task's own conversation when it was given to that task and the task has a conversation to follow up on (`continues_conversation`); otherwise, including after a retry cleared the session, it goes into a fresh first message. The next enqueue of a descendant without a note clears it, so a note lives on one chain of runs: `papers.paper_global_additional_context`, the sticky paper-wide note it replaced, was dropped on 2026-10-22. PDF Parsing is not an agent and reads no note itself, but its successors get it.
- Task models: `TaskDB` (ORM), `TaskResp` (API response), `TaskCreateRequest` (for queueing)
- Task status and dependency logic in `lib/tasks/models.py` and `lib/tasks/misc.py`

**Claimed tasks and the single worker:** everything the scheduler knows is in the `tasks` table. Each poll (every 10 s, one transaction, `_poll_and_schedule_tasks` in `lib/bin/worker.py`) counts RUNNING rows against `GLOBAL_CONCURRENCY` and `TASK_CONCURRENCY`, and starts as many PENDING rows as fit: claiming a task is starting it (`start_attempt` stamps RUNNING, `started_at` and `tries`), so nothing waits in an in-process queue and a freed slot is refilled on the next poll. The per-(paper, type) fan-out gate is decided from the same table: a batch whose first attempt is RUNNING admits nothing more until an attempt of that batch has finished within `CACHE_WARM_S`. An attempt's lease runs from `started_at` (`lease_timeout_s`: 20 min by default, 30 min for PDF Parsing; never refreshed, so each must exceed the longest legitimate run of its type, and PDF Parsing has reached 15 min on a 44-page supplement); an attempt past it is retired: its coroutine is cancelled (the worker keeps a handle per live attempt in `_attempts`) and its row goes PENDING with its session cleared while retries remain, else FAILED. A cancel lands at the handler's next await, so thread-bound work such as a Docling parse runs to its end first; whenever the coroutine does get to its outcome, it finds the row's status or tries moved on and drops it (`execute_task` only writes for the attempt it was started as). `TaskStatus` is PENDING, RUNNING, COMPLETED or FAILED; QUEUED, the old claimed-but-parked status, was dropped on 2026-10-26 (migration `7c1e5a9d3b2f` turns leftover rows PENDING). There is one worker process, and the worker relies on it: on a shutdown signal it stops polling and sweeps *every* claimed row back to PENDING (session cleared) or FAILED on its last try, and it runs the same sweep before its first poll, so a crash or a kill leaves nothing claimed past the next start (`_sweep_claimed_tasks`). A second worker would steal the first one's live tasks.

**PDF highlighting:** Words/images can be highlighted in PDFs with colors (red, orange, yellow, blue, green, violet, gray, primary). Uses Grobid annotations for word positioning.

**OpenAI agents:** Uses `openai_agents.Runner` for structured outputs. Models must have Pydantic schema for OpenAI to use as response schema.

**Deployment:** One GCP VM (`dev-caa`, domain `gene-curation-ai.app`) behind nginx:
FastAPI at `/api/` (prefix stripped), the React SPA's static build at `/`. Deploy with `ansible-playbook -i dev-caa.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml`,
which pulls `main` from GitHub — so changes must be merged and pushed before deploying.
See the Deployment section of `README.md`.

**The SPA is built against a configurable base path** (`VITE_BASE_PATH`, `/` today), so
anything root-relative in `frontend/` must be built from `import.meta.env.BASE_URL`, or it
breaks the day the app is served under a prefix again:

- Navigate with `<Link>` from TanStack Router, never `<a href="/...">`
- Reference `public/` assets as `` `${import.meta.env.BASE_URL}<file>` `` in TSX, or
  `%BASE_URL%<file>` in `index.html`
- Build API-served URLs (PDFs, thumbnails) from `API_BASE_URL` exported by `lib/api.ts`,
  not from `import.meta.env.VITE_API_URL` directly
