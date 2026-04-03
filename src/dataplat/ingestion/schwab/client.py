"""Thin typed wrapper around schwabdev.Client.

Provides a singleton Schwab client configured from dataplat settings.
On first use, schwabdev may open a browser for OAuth — after that,
tokens auto-refresh from the SQLite token store.
"""

from __future__ import annotations

import logging

import schwabdev

from dataplat.config import settings

logger = logging.getLogger(__name__)

_client: schwabdev.Client | None = None


def get_schwab_client() -> schwabdev.Client:
    """Return a schwabdev Client, creating one on first call."""
    global _client
    if _client is None:
        if not settings.schwab_app_key or not settings.schwab_app_secret:
            raise RuntimeError(
                "SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in .env. "
                "Register at https://developer.schwab.com"
            )
        logger.info("Initializing Schwab client (tokens_db=%s)", settings.schwab_tokens_db)
        _client = schwabdev.Client(
            app_key=settings.schwab_app_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_redirect_uri,
            tokens_db=settings.schwab_tokens_db,
        )
    return _client
