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
    version    UInt32,
    name       String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY version
"""


def _ensure_database() -> None:
    """Create the target database if it doesn't exist."""
    client = get_client(database="default")
    client.command(f"CREATE DATABASE IF NOT EXISTS {settings.clickhouse_database}")


def _ensure_migrations_table() -> None:
    """Create the ``_migrations`` tracking table if needed."""
    client = get_client()
    client.command(_MIGRATIONS_TABLE_DDL)


def _applied_versions() -> set[int]:
    """Return the set of already-applied migration version numbers."""
    client = get_client()
    rows = client.query("SELECT version FROM _migrations").result_rows
    return {int(row[0]) for row in rows}


def _discover_migrations() -> list[tuple[int, str, Path]]:
    """Return ``(version, name, path)`` tuples sorted by version."""
    pattern = re.compile(r"^(\d{3})_(.+)\.sql$")
    found: list[tuple[int, str, Path]] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = pattern.match(f.name)
        if m:
            found.append((int(m.group(1)), f.stem, f))
    return found


def run_migrations(*, dry_run: bool = False) -> int:
    """Apply all pending migrations.  Returns count of applied."""
    _ensure_database()
    _ensure_migrations_table()

    applied = _applied_versions()
    migrations = _discover_migrations()
    pending = [(v, name, path) for v, name, path in migrations if v not in applied]

    if not pending:
        logger.info("All migrations already applied.")
        return 0

    client = get_client()
    count = 0

    for version, name, path in pending:
        if dry_run:
            logger.info("[DRY RUN] Would apply: %03d_%s", version, name)
            count += 1
            continue

        logger.info("Applying migration %03d_%s ...", version, name)
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
        logger.info("  ✓ %03d_%s applied.", version, name)
        count += 1

    return count
