# Database Migrations

This project uses Alembic for database migrations. The database engine is
configured in `lib/api/db.py` via `get_engine()`, and models are defined in
`lib/models/__init__.py`.

All commands below should be run with `uv run` from the project root.

## Common Commands

Generate a new migration after changing models:

    uv run alembic revision --autogenerate -m "short description of change"

Apply all pending migrations:

    uv run alembic upgrade head

Check the current revision:

    uv run alembic current

Roll back one migration:

    uv run alembic downgrade -1

View migration history:

    uv run alembic history

## Notes

### Batch mode (`render_as_batch`)

SQLite's ALTER TABLE is limited — you cannot change a column's type, add or drop
constraints (NOT NULL, UNIQUE, FOREIGN KEY, CHECK), or change/drop default values
on existing columns. Alembic's batch mode works around this by recreating the
table:

1. Create a new table with the desired schema.
2. Copy all data from the old table.
3. Drop the old table.
4. Rename the new table to the original name.

This is enabled via `render_as_batch=True` in `migrations/env.py` (in both the
online and offline run functions). Without it, any migration that alters an
existing column will fail on SQLite.

### Autogenerate limitations

`alembic revision --autogenerate` compares your SQLAlchemy models against the
current database schema and generates upgrade/downgrade functions. It reliably
detects most additions and removals of tables/cols and some changes to them.

It **cannot** detect:

- Column renames (appears as a drop + add — data will be lost)
- Table renames
- Changes to column types in some cases

For these changes, if avoiding data loss is needed, the migration file
needs to be edited manually to create the appropriate sqlalchemy/sql calls.
