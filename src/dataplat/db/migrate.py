"""Simple forward-only migration runner for ClickHouse.

Tracks applied migrations in a ``_migrations`` table inside the target
database.  Each migration is a numbered ``.sql`` file executed in order.

Usage::

    from dataplat.db.migrate import run_migrations
    run_migrations()          # applies all pending
    run_migrations(dry_run=True)  # prints what would run
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from dataplat.config import settings
from dataplat.db.client import get_client

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_MIGRATIONS_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS _migrations (
    version    String,
    name       String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY version
"""


def _ensure_database() -> None:
    """Create the target database if it doesn't exist."""
    client = get_client(database="default")
    client.command(f"CREATE DATABASE IF NOT EXISTS {settings.clickhouse_database}")


def _ensure_migrations_table() -> None:
    """Create the ``_migrations`` tracking table if needed.

    If a legacy UInt32-keyed table exists, recreate it as String-keyed
    so we can track version keys like '002b'.
    """
    client = get_client()

    # Check if a legacy UInt32 version column exists.
    rows = client.query(
        "SELECT type FROM system.columns "
        "WHERE database = currentDatabase() "
        "  AND table = '_migrations' "
        "  AND name = 'version'"
    ).result_rows

    if rows and "UInt32" in str(rows[0][0]):
        logger.info("Recreating _migrations table (UInt32 → String version key)...")
        # Save existing rows
        existing = client.query(
            "SELECT toString(version) AS version, name FROM _migrations"
        ).result_rows
        client.command("DROP TABLE _migrations")
        client.command(_MIGRATIONS_TABLE_DDL)
        for ver, name in existing:
            client.command(
                "INSERT INTO _migrations (version, name) VALUES (%(v)s, %(n)s)",
                parameters={"v": str(ver), "n": name},
            )
        logger.info("  ✓ Migrated %d existing migration records.", len(existing))
    else:
        client.command(_MIGRATIONS_TABLE_DDL)


def _applied_versions() -> set[str]:
    """Return the set of already-applied migration version keys."""
    client = get_client()
    rows = client.query("SELECT version FROM _migrations").result_rows
    return {str(row[0]).lstrip('0') or '0' for row in rows}


def _discover_migrations() -> list[tuple[str, str, Path]]:
    """Return ``(version_key, name, path)`` tuples sorted by filename.

    version_key is the full prefix (e.g. "002b") used for tracking.
    Supports suffixed versions like 002b, 002c that sort naturally
    via the filename sort.
    """
    pattern = re.compile(r"^(\d{3}[a-z]?)_(.+)\.sql$")
    found: list[tuple[str, str, Path]] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = pattern.match(f.name)
        if m:
            found.append((m.group(1), f.stem, f))
    return found


def ensure_schema() -> None:
    """Ensure all tables exist by running pending migrations.

    Call this before any pipeline that writes to ClickHouse.
    It is idempotent — if everything is up to date it returns instantly.
    """
    applied = run_migrations()
    if applied:
        logger.info("Auto-applied %d migration(s) to ensure schema exists.", applied)


def run_migrations(*, dry_run: bool = False) -> int:
    """Apply all pending migrations.  Returns count of applied."""
    _ensure_database()
    _ensure_migrations_table()

    applied = _applied_versions()
    migrations = _discover_migrations()
    # Normalise discovered version keys the same way as applied ones
    def _norm(v: str) -> str:
        return v.lstrip('0') or '0'

    pending = [(v, name, path) for v, name, path in migrations if _norm(v) not in applied]

    if not pending:
        logger.info("All migrations already applied.")
        return 0

    client = get_client()
    count = 0

    for version, name, path in pending:
        if dry_run:
            logger.info("[DRY RUN] Would apply: %s_%s", version, name)
            count += 1
            continue

        logger.info("Applying migration %s ...", name)
        sql = path.read_text()

        # Split on semicolons to handle multi-statement migrations.
        # ClickHouse doesn't support multi-statement in one command().
        for statement in sql.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            client.command(statement)

        client.command(
            "INSERT INTO _migrations (version, name) VALUES (%(v)s, %(n)s)",
            parameters={"v": version, "n": name},
        )
        logger.info("  ✓ %s applied.", name)
        count += 1

    return count
