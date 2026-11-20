# CLAUDE.md

A curation assistant: it reads genetics papers (PDF) and extracts individuals, phenotypes and variants, links them to HPO, MONDO and variant registries, and lets curators review and sign off what it found. Three processes share one SQLite database:

- **API**: FastAPI, `lib/api/app.py`. Database sessions come from `lib/api/db.py`: `session_scope()` in background code, `Depends(get_session)` in endpoints.
- **Worker**: `lib/bin/worker.py`. It runs the pipeline as tasks from the `tasks` table.
- **SPA**: React in `frontend/`, the only UI (Streamlit is retired). See `frontend/README.md` for its architecture and dependencies.

## Commands

```bash
uv sync && uv pip install -e .
uv run ruff check lib && uv run ruff format --check lib test && uv run mypy lib
uv run pytest test/path/to/test_file.py          # CI runs the whole suite with coverage of lib/
./bin/api    ./bin/worker    ./bin/ui            # ports 8000 and 8501; `./bin/ui <script>` runs a pnpm script
./bin/generate-api-spec                          # frontend/api-spec.json from the FastAPI app, no server needed
alembic upgrade head
```

From `frontend/`: `pnpm type-check`, `pnpm lint`, `pnpm build` (regenerates the API client first). CI does not run these, so run them yourself before merging frontend work.

Tests read `ENV_FILE=.env.test`. Settings live in `lib/core/environment.py`, loaded from `.env` or the environment. Data is under `CAA_ROOT` (`/var/caa`): `sqllite/app.db`, `documents/`, `logs/`, `reference_data/`.

**Commits and PR titles are Conventional Commits** (`feat: ...`, `fix(worker): ...`), because a squash merge puts the PR title on `main`. commitizen checks them in the `commit-msg` hook (`git config core.hooksPath .githooks`, once per clone), in `bin/check-commits` (add `--message 'feat: a title'` to check a title) and in CI.

## Pipeline

Tasks form a graph. `TaskType` and `TASK_SUCCESSORS` are in `lib/tasks/models.py`, and the handlers are `TASK_HANDLERS` in `lib/tasks/handlers.py`. Finishing a task queues its successors. A task is scoped to a paper, and optionally to a patient, family, variant, phenotype or occurrence.

PDF Parsing (docling-serve on Cloud Run, `docs/cloud-run-parsing.md`) → Paper Classifier, which then branches:

- Paper Metadata → Paper MONDO Linking
- Figure Description → Individual Extraction → per individual: Demographics → Phenotype Extraction → HPO Linking, plus segregation per family
- Variant Extraction → Harmonization → Annotation
- Individual Variant Occurrences, once both extractions are done → Compound Het, MONDO linking, segregation
- Extraction Verification, last, once every other task has settled

**Read `docs/pipeline.md` before changing a step's behaviour, re-runs, curator notes, the quick run, worker scheduling or model choice.** It records why each step works the way it does, the cases that broke earlier versions, and how notes and `budget_model` travel down the graph. Workers are sharded by paper id, one process per shard. Two workers on the same shard take each other's tasks.

## Agents

- Agents use `openai_agents` structured outputs. Their output reaches the database through `lib/models/converters.py`. See `lib/agents/AGENT_GUIDE.md` for writing one.
- **Models see "basis", never the word "reasoning".** Wrap `output_type` in `model_facing_output(...)` (`lib/agents/model_facing.py`) and write prompts with "basis". Anthropic's `reasoning_extraction` classifier cuts Sonnet and Opus off mid-JSON otherwise. `test_no_agent_prose_asks_for_reasoning` guards this. The database, API and UI keep `reasoning`.
- Models are named `<provider>/<model>`. `anthropic/` goes through LiteLLM; `openai/` goes to the agents SDK. dev-caa's choices, and why, are in `infrastructure/ansible/templates/env.j2` and `docs/pipeline.md`.
- Keep prompts generic: a motivating paper's gene, PMID or wording belongs in comments, never in prompt text.

## Data

- Models come in four forms: `SomeModel` (Pydantic), `SomeDB` (SQLAlchemy), `SomeResp` (API), `SomeUpdateRequest` (PATCH).
- A paper's files are under `documents/<paper_id>/`. Use the `document_*` helpers in `lib/misc/pdf/paths.py`. Tables and images are numbered by Docling index, the same N as the `table-N` and `figure-N` anchors. The Docling document itself is not saved; `parse_content(force=True)` rebuilds everything from `raw.*`.
- **Curators see "Individual" wherever the code says patient.** That covers UI strings, API routes and error details. Models, fields and tables keep `patient`. Curators see a task's `TaskType.label`, never its value. Read `docs/curation.md` before changing curator-facing wording, the patient or occurrence fields, or sign-off and review.

## Migrations (SQLite)

Both failures below are silent, and both have destroyed production data.

- **Enum columns store the member's name** (`'COMPLETED'`), not its value. A `server_default` or raw-SQL backfill must write `.name`. Confirm by reading a freshly migrated row back through the ORM: a wrong value only fails on read, with a `LookupError` (this took down `GET /papers` on 2026-09-17).
- **`batch_alter_table` on a table with CASCADE dependents recreates it and deletes the child rows** unless foreign keys are really off. `PRAGMA foreign_keys` does nothing inside alembic's open transaction. Calling `connection.commit()` to escape it leaves `alembic_version` one revision behind. Use `autocommit_block()`:

```python
connection = op.get_bind()
with op.get_context().autocommit_block():
    connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
try:
    with op.batch_alter_table('table_name') as batch_op:
        ...
finally:
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = ON')
```

- Add a CASCADE foreign key in its own non-batch operation, after the column exists.
- Before trusting a batch migration, run it against a parent with a CASCADE child row and check the child survives. Run `alembic upgrade head` a second time and check it does nothing. Back up before running it on real data, and compare row counts afterwards.

## Frontend

- `src/routeTree.ts` is **hand-written**: a new route component does nothing until it is imported, declared and added to `addChildren`.
- `src/api/generated/` is generated. Regenerate it after changing API models, never edit it by hand.
- Use the rows in `EditableField.tsx` for curator input; they require an edit note.
- The SPA is built against `VITE_BASE_PATH`, so build root-relative URLs from it:
  - navigate with TanStack `<Link>`;
  - write public assets as `${import.meta.env.BASE_URL}<file>`, or `%BASE_URL%<file>` in `index.html`;
  - build API-served URLs from `API_BASE_URL` in `lib/api.ts`.

## Deployment

dev-caa is one GCP VM (instance `dev-caa-2`, domain `gene-curation-ai.app`). nginx serves FastAPI at `/api/` (prefix stripped) and the SPA at `/`. `ansible-playbook -i dev-caa-2.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml` deploys `main` from GitHub, so merge and push first. See the Deployment section of `README.md`.
