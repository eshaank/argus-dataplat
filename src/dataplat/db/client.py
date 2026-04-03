"""ClickHouse client factory.

Returns a ``clickhouse_connect`` client configured from
:pydata:`dataplat.config.settings`.  The module exposes a lazy
singleton via :func:`get_client` so every caller shares one
connection (HTTP keep-alive under the hood).
"""

from __future__ import annotations

import clickhouse_connect
from clickhouse_connect.driver import Client

from dataplat.config import settings

_client: Client | None = None


def get_client(*, database: str | None = None) -> Client:
    """Return a ClickHouse client, creating one on first call.

    Parameters
    ----------
    database:
        Override the database from settings.  Useful for the migration
        runner which needs to connect before the target DB exists.
    """
    global _client
    if _client is None or database is not None:
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=database or settings.clickhouse_database,
            secure=settings.clickhouse_secure,
        )
        if database is not None:
            return client  # one-off, don't cache
        _client = client
    return _client


def ping() -> bool:
    """Return True if ClickHouse is reachable."""
    try:
        client = get_client(database="system")
        client.command("SELECT 1")
        return True
    except Exception:
        return False
