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

From `frontend/`: `pnpm type-check`, `pnpm lint`, `pnpm build` (regenerates the API client first). CI runs all three (`.github/workflows/frontend-check.yml`) whenever `frontend/` or `lib/` changes, since an API change can break the frontend's types.

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

Both failures below are silent, and both have destroyed production data. `test/migrations/test_migration_safety.py` walks every new migration over a database with a row in every table and fails on either one, on an Enum column holding anything but member names, and on a second alembic head. It uses generic rows, so a data migration still wants its own test with realistic rows in `test_alembic.py`.

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
0. Curators see "Individual" wherever the code says patient (since 2026-11-06): visible strings, table headers, API error details, API routes (`/papers/{id}/individuals`) and the functions behind them say Individual, while models, API fields (`patient_id`), tables and component names keep patient. The three task types named for the step were renamed on 2026-11-12 (Individual Extraction, Individual Demographics, Individual Variant Occurrences; their agents, handlers and output models with them; migration `d5f1b3a7c9e2`, which rewrites the stored names in `tasks` and `flags`). Curators never see a task type's value: each step has a plain-language name, `TaskType.label` ("Finding variants" for Variant Extraction), served by `GET /task-types` and shown through `taskLabel` (`frontend/src/lib/taskLabel.ts`, registered by the root layout before signed-in pages render); the paper chat is given both names and answers with the label, and snapshot and busy messages use it. Requests, logs and code keep the value. The progress timeline groups steps into the stages of `lib/tasks/tracks.py`, whose labels are curator-facing too
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
- **Re-run all tasks:** the dialog's "All tasks" tab queues PDF Parsing (with "Also re-parse the PDF") or Paper Classifier through `POST /papers/{id}/tasks` like any other task; there is no separate endpoint or paper field. Every task descends from those two, and a task's `additional_context` comes down the successor graph: `enqueue_successors` copies it to every descendant of that run with `tasks.context_origin` naming the task it was given to, so a note on the root is the run-all note, and the note reaches every agent worded "given for this re-run of the whole paper" (`curator_note_section` in `lib/tasks/handlers.py`; for any other origin, "supplied to X and might also be relevant here"). A descendant starts fresh with the note as the last item of its first message (`with_curator_note`), after the cache-breakpointed paper block, instructions and data; figure description, which has no conversation, puts the labelled note in its vision prompts; phenotype extraction skips the HPO link cache while its run has a note, so the HPO agent actually sees it. A note only ever becomes a follow-up to the task's own conversation when it was given to that task and the task has a conversation to follow up on (`continues_conversation`); otherwise, including after a retry cleared the session, it goes into a fresh first message. A follow-up restates the task's data as it stands now (the patient JSON and proband, the family structure, the variant JSON, the phenotype, the MONDO target) ahead of the note, since a curator may have edited those rows since the first run and the conversation holds only the first run's copy (`build_followup_prompt`); the paper and the instructions are not resent, and the four handlers whose first message is the paper alone pass no data. The next enqueue of a descendant without a note clears it, so a note lives on one chain of runs: `papers.paper_global_additional_context`, the sticky paper-wide note it replaced, was dropped on 2026-10-22. PDF Parsing is not an agent and reads no note itself, but its successors get it.
- **Quick run:** `tasks.budget_model` (migration `c3d9e1f7a2b4`) runs the task and its successors on `EXTRACTION_BUDGET_MODEL`; see that setting above. The chat agent's queue tool does not set it
- Task models: `TaskDB` (ORM), `TaskResp` (API response), `TaskCreateRequest` (for queueing)
- Task status and dependency logic in `lib/tasks/models.py` and `lib/tasks/misc.py`

**Claimed tasks and the sharded workers:** everything the scheduler knows is in the `tasks` table, and since 2026-11-09 it is shared by `WORKER_COUNT` worker processes, each owning the papers whose id % `WORKER_COUNT` is its `WORKER_ID` (`shard_filter` in `lib/bin/worker.py`, on every query the module runs over the table; the deployment runs four as the systemd template instances `worker@0` .. `worker@3`, `worker_count` in the playbook, and a developer's defaults are one worker owning everything). A paper's whole pipeline runs in one process, and the concurrency limits are per process, so the PDF Parsing cap of 1 is four parses in flight against the pdf-parsing service's two instances. Each poll (every 5 s since 2026-11-03, one transaction, `_poll_and_schedule_tasks`) counts the shard's RUNNING rows against `GLOBAL_CONCURRENCY` and `TASK_CONCURRENCY`, and starts as many of its PENDING rows as fit: claiming a task is starting it (`start_attempt` stamps RUNNING, `started_at` and `tries`), so nothing waits in an in-process queue and a freed slot is refilled on the next poll. The per-(paper, type) fan-out gate is decided from the same table: a batch whose first attempt is RUNNING admits nothing more until an attempt of that batch has finished within `CACHE_WARM_S`. An attempt's lease runs from `started_at` (`lease_timeout_s`: 20 min by default, 30 min for PDF Parsing; never refreshed, so each must exceed the longest legitimate run of its type, and PDF Parsing has reached 15 min on a 44-page supplement); an attempt past it is retired: its coroutine is cancelled (the worker keeps a handle per live attempt in `_attempts`) and its row goes PENDING with its session cleared while retries remain, else FAILED. A cancel lands at the handler's next await, so thread-bound work such as a Docling parse runs to its end first; whenever the coroutine does get to its outcome, it finds the row's status or tries moved on and drops it (`execute_task` only writes for the attempt it was started as). `TaskStatus` is PENDING, RUNNING, COMPLETED or FAILED; QUEUED, the old claimed-but-parked status, was dropped on 2026-10-26 (migration `7c1e5a9d3b2f` turns leftover rows PENDING). There is one worker process per shard, and the worker relies on it: on a shutdown signal it stops polling and sweeps *every* claimed row of its shard back to PENDING (session cleared) or FAILED on its last try, and it runs the same sweep before its first poll, so a crash or a kill leaves nothing claimed past the next start (`_sweep_claimed_tasks`). Two workers with the same shard, or started with different `WORKER_COUNT`s, would steal each other's live tasks, which is why the count is written into every unit instance and the old single `worker` unit is disabled by the playbook.

**Curator sign-off and the reviews:** a stamp on each patient-variant occurrence (`reviewed_at`, `reviewed_by_user_id`; `lib/models/signoff.py`, migration `e5f1a7c3d9b8`, since 2026-11-03) says a curator checked it. The occurrence is the only stamped row: it is what curation checks, and stamping its patient and variant too asked for three confirmations of one fact. `POST /papers/{id}/signoff` stamps or unstamps a list of occurrences and then `sync_review_status` moves the paper's review status to match: first stamp on an unstarted paper, In progress under the curator who stamped; last occurrence stamped, Completed; a take-back on a completed paper, In progress again, assignee kept. Open flags never hold completion back. An agent rewriting an occurrence in place (compound-het pairing, MONDO on an occurrence) clears its stamp (`clear_signoff`) and reopens a completed paper; occurrence extraction recreates its rows, so the stamp goes with them; demographics, harmonization and annotation re-runs leave it. The occurrence review writes it: the **Review occurrences** button above the occurrences table opens a modal (`OccurrenceReviewDialog.tsx`) beside the PDF, one occurrence per step (a compound-het pair is one step, as the table draws it), grouped by family and in paper order (each step at the first passage its fields cite, each family at its first step). The pane holds the list, then an Occurrence panel (its fields, each with the table's editable control, its basis and View in PDF, and the open flags about the individual, occurrences and variants), then the table's own Individual and Variant panels; parent of origin appears only as the De novo switch, as everywhere else. Keys: `j`/`k` previous/next, `a` accept or take back (`POST /papers/{id}/signoff`), `x` reject, which deletes the occurrence (both, for a pair); opening the review snapshots the paper ("Before occurrence review", `POST /papers/{id}/occurrences/review`) and that snapshot is the undo. The paper page keeps the open occurrence in its URL (`?occurrence=<id>`, `&panel=variant` for the Variant panel, `&review=occurrences` with the review open on that step; `ExtractionSearch` in `frontend/src/routeTree.ts`), so a flag chip, a pasted link or a refresh lands on it. It replaced Review Mode, the `/papers/$id/review` page that walked a family at a time with the paper page's tables, on 2026-11-19, together with its `review-cases` endpoint and the papers list's button into it. Progress (`PaperResp.signoff`, stamped/total occurrences) shows on the button and, as plain text, in the papers table. A paper's review can be assigned to several curators (`paper_review_assignees`, migration `f6a2b8d4c1e9`, since 2026-11-10; `PaperResp.review_assignees`, `PATCH /papers/{id}/review` takes the whole set as `assignee_user_ids`): the status stays one per paper, shared by everyone on it, and the dashboard's assignee filter matches any of them. `papers.review_assignee_user_id`, the single assignee it replaced, is still a mapped column that nothing reads or writes, because dropping it means rebuilding `papers`. Phenotypes carry the same stamp (migration `f7c2a9e4b1d6`, since 2026-11-19), written by the HPO review, the same kind of modal (both share `ReviewParts.tsx`, whose `useReviewKeys` reads the latest state so fast key presses land on the right step): the **Review HPO terms** button above an individual's phenotype table opens `HpoReviewDialog.tsx`, which walks the terms in paper order (each at its first cited passage, `anchorPosition` on the PDF context) beside the PDF, with keys `j`/`k` previous/next, `a` accept (`POST /papers/{id}/phenotypes/signoff`), `r` relink, `x` reject. Reject deletes the phenotype, like every other delete (it reaches `deletion_log`); opening the review snapshots the paper ("Before HPO review: <individual>") and that snapshot is the undo. A phenotype stamp does not move the paper's review status, and relinking, by a curator or the HPO agent, clears it.

**PDF highlighting:** Words/images can be highlighted in PDFs with colors (red, orange, yellow, blue, green, violet, gray, primary). Uses Grobid annotations for word positioning.

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
