"""Database utilities — client factory, migrations, schema bootstrap."""

from dataplat.db.client import get_client, ping
from dataplat.db.migrate import ensure_schema, run_migrations

__all__ = ["get_client", "ping", "ensure_schema", "run_migrations"]
