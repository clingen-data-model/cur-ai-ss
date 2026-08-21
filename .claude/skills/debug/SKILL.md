---
name: debug
description: Inspect the dev-caa instance read-only over SSH — query the app SQLite database, read extracted PDF artifacts, and tail service logs. Use when investigating why a paper, task, patient, variant, or phenotype looks wrong on dev.
allowed-tools: Bash(gcloud compute ssh dev-caa *)
---

# Debug Skill

Investigate problems on the `dev-caa` instance by reading its live database and files.

## Read-only rule (hard constraint)

This skill **reads only**. Never run `INSERT`, `UPDATE`, `DELETE`, `CREATE`,
`ALTER`, `DROP`, `VACUUM`, `ATTACH`, or any other statement that mutates data
or schema — not to "test a fix", and not when asked to correct bad data. Also
don't restart services, edit files, or run `alembic` on the box. If a fix
requires a write, stop and report the finding plus the exact statement or
command you would run, and let the user run it.

Every query goes through `sqlite3 -readonly`, which enforces this at the SQLite
level so a stray write errors instead of corrupting dev data. Do not drop that
flag.

## Running a query

```bash
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa \
  --command 'sudo -u caa sqlite3 -readonly -header -column /var/caa/sqllite/app.db "SELECT id, title, updated_at FROM papers ORDER BY updated_at DESC LIMIT 10;"'
```

- `sudo -u caa` is the non-interactive form of `sudo su caa`; the `caa` user owns
  `/var/caa`.
- Outer quoting single, SQL double-quoted; use SQL single quotes for literals
  (`WHERE status = 'FAILED'`). For longer SQL, pipe a heredoc:

```bash
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa \
  --command 'sudo -u caa sqlite3 -readonly -header -column /var/caa/sqllite/app.db' <<'SQL'
SELECT type, status, count(*) FROM tasks GROUP BY 1, 2 ORDER BY 1;
SQL
```

- `-json` instead of `-column` when you want to post-process.
- Keep result sets small (`LIMIT`, named columns). Rows contain paper text and
  user data — don't dump whole tables.

## Orienting yourself

```sql
SELECT name FROM sqlite_master WHERE type = 'table';   -- .tables also works
SELECT sql FROM sqlite_master WHERE name = 'tasks';    -- schema for one table
```

Real table names (note: they differ from some older docs):
`papers`, `genes`, `tasks`, `agent_runs`, `patients`, `families`, `pedigrees`,
`phenotypes`, `hpos`, `variants`, `harmonized_variants`, `annotated_variants`,
`patient_variant_occurrences`, `segregation_evidence`,
`segregation_analysis_computed`, `conversations`, `users`.

There is no `pipeline_status` column on `papers` — a paper's overall state is
inferred from the status of its rows in `tasks`.

Enums are stored as their Python **member names**, not the human-readable
values you see in the UI. So `tasks.status` is `PENDING`, `QUEUED`, `RUNNING`,
`COMPLETED`, `FAILED`, and `tasks.type` is `PDF_PARSING`, `PATIENT_EXTRACTION`,
`VARIANT_HARMONIZATION`, `HPO_LINKING`, ... (see `TaskType` in
`lib/tasks/models.py` for the full list and the successor graph). Useful task columns: `tries`,
`error_message`, `skip_successors`, `additional_context`, `agent_run_id`, and
the scope columns `family_id` / `patient_id` / `variant_id` / `phenotype_id` /
`patient_variant_occurrence_id`.

## Useful starting points

```sql
-- Recently failed tasks and why
SELECT id, paper_id, type, tries, substr(error_message, 1, 300) AS err, updated_at
FROM tasks WHERE status = 'FAILED' ORDER BY updated_at DESC LIMIT 20;

-- Papers with unfinished work
SELECT p.id, p.title, t.type, t.status, t.updated_at
FROM tasks t JOIN papers p ON p.id = t.paper_id
WHERE t.status IN ('PENDING', 'QUEUED', 'RUNNING')
ORDER BY t.updated_at DESC LIMIT 30;

-- Everything that happened for one paper
SELECT id, type, status, tries, patient_id, variant_id, phenotype_id, updated_at
FROM tasks WHERE paper_id = <paper_id> ORDER BY updated_at;

-- What a paper extracted
SELECT (SELECT count(*) FROM patients WHERE paper_id = <id>) AS patients,
       (SELECT count(*) FROM variants  WHERE paper_id = <id>) AS variants;

-- Which agent run / code version produced the data
SELECT id, git_hash, model, description, updated_at
FROM agent_runs ORDER BY updated_at DESC LIMIT 10;
```

## Files and logs on the box

Extraction artifacts live under `/var/caa/extracted_pdfs/<paper_id>/` (parsed
markdown, tables, images, agent output JSON) — see `lib/misc/pdf/paths.py` for
the exact filenames.

```bash
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa \
  --command 'sudo -u caa ls -la /var/caa/extracted_pdfs/<paper_id>/'
```

`api`, `ui`, and `worker` run as **systemd user services** under `caa` and log
to the journal (not to files):

```bash
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa \
  --command 'sudo journalctl _SYSTEMD_USER_UNIT=worker.service --no-pager -n 200'
```

Swap in `api.service` / `ui.service`; add `--since "1 hour ago"` or
`-g <pattern>` to narrow. Read logs, don't restart units.
