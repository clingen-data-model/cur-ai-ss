---
name: dev-database
description: How to SSH to the dev-caa VM and inspect or modify its SQLite database, run one-off scripts, and manage the app services
---

# Dev Database Skill

The development instance runs on the GCE VM `dev-caa` (zone `us-east4-a`, project `clingen-caa`), serving https://gene-curation-ai.app.

## Layout on the VM

- App repo (deployed from GitHub main via the `deploy` skill): `/opt/caa`
- Runtime user: `caa` (services run as systemd **user** units under lingering)
- Environment file: `/opt/caa/.env`
- Data root (`CAA_ROOT`): `/var/caa`
  - Database: `/var/caa/sqllite/app.db`
  - Extracted PDFs + snapshots: `/var/caa/extracted_pdfs/<paper_id>/`

## SSH

```bash
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa
# or one-off commands:
gcloud compute ssh dev-caa --zone us-east4-a --project clingen-caa --command '<cmd>'
```

## Querying the database

Always interact as the `caa` user:

```bash
sudo -u caa sqlite3 /var/caa/sqllite/app.db
# e.g. read-only checks:
sudo -u caa sqlite3 /var/caa/sqllite/app.db 'SELECT count(*) FROM papers;'
sudo -u caa sqlite3 /var/caa/sqllite/app.db 'SELECT version_num FROM alembic_version;'
```

For any write, prefer application code paths (API, worker, or a `lib/bin` script)
over raw SQL — the app relies on `PRAGMA foreign_keys=ON` and evidence-JSON
conventions that raw SQL can silently violate.

## Running one-off scripts (lib/bin)

Run from `/opt/caa` so the deployed `.env` is picked up:

```bash
sudo -u caa bash -lc "cd /opt/caa && uv run python -m lib.bin.<script>"
# example:
sudo -u caa bash -lc "cd /opt/caa && uv run python -m lib.bin.backfill_snapshots"
```

Note: the VM runs whatever is deployed at `/opt/caa` (git main via the deploy
skill) — local uncommitted code is not there. Deploy first if the script is new.

## Services

`api`, `ui`, and `worker` are systemd *user* units for the `caa` user:

```bash
sudo -u caa XDG_RUNTIME_DIR=/run/user/$(id -u caa) systemctl --user status worker
sudo -u caa XDG_RUNTIME_DIR=/run/user/$(id -u caa) systemctl --user restart worker
sudo -u caa XDG_RUNTIME_DIR=/run/user/$(id -u caa) journalctl --user -u worker -n 100
```

## Cautions

- **Back up before schema changes or bulk writes:**
  `sudo -u caa cp /var/caa/sqllite/app.db /var/caa/sqllite/app.db.bak-$(date +%Y%m%d)`
- Stop or pause the `worker` before manual DB surgery — it polls every 10s and
  holds lease-based task state.
- The dev DB's alembic stamp tracks whichever branch last migrated it; if
  `alembic` can't find a revision, the DB may need re-stamping.
- Migrations on tables with CASCADE FKs must follow the PRAGMA
  foreign_keys OFF/ON batch pattern (see CLAUDE.md) — this DB has lost data to
  that mistake before.
