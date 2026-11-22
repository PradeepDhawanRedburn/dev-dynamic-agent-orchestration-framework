"""Plain SQL migrations. Each file in `migrations/` runs once, in name order, in one transaction.

Applied versions are recorded in `schema_migrations`. An advisory lock makes concurrent runners
safe: the second waits, then finds nothing to do. Run it as the database owner, not as the
application role."""

from importlib.resources import files

import psycopg

LOCK_KEY = 7_305_001


def migration_files() -> list[tuple[str, str]]:
    folder = files("orchestrator.persistence") / "migrations"
    found = [(item.name, item.read_text(encoding="utf-8")) for item in folder.iterdir()]
    return sorted(
        (name.removesuffix(".sql"), text) for name, text in found if name.endswith(".sql")
    )


def apply_migrations(dsn: str) -> list[str]:
    """Apply every pending migration and return the versions applied by this call."""
    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        # One runner at a time, from creating the bookkeeping table to the last migration.
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            for version, text in migration_files():
                with conn.transaction():
                    done = conn.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
                    ).fetchone()
                    if done:
                        continue
                    conn.execute(text.encode())  # no parameters: the file is sent as it is
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                    applied.append(version)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return applied
