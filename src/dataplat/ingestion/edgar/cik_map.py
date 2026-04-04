"""Ticker → CIK resolution using SEC bulk mapping file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from dataplat.ingestion.edgar.client import _get_user_agent

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
CACHE_PATH = Path(__file__).resolve().parents[4] / ".edgar_cik_map.json"


class CIKMap:
    """Ticker → (CIK, exchange) lookup backed by SEC bulk file."""

    def __init__(self) -> None:
        self._map: dict[str, tuple[str, str]] = {}

    def load(self, *, force_refresh: bool = False) -> None:
        """Load the CIK map from cache or download from SEC."""
        if not force_refresh and CACHE_PATH.exists():
            try:
                raw = json.loads(CACHE_PATH.read_text())
                self._map = {k: (v[0], v[1]) for k, v in raw.items()}
                logger.info("Loaded CIK map from cache: %d tickers", len(self._map))
                return
            except Exception:
                logger.warning("Cache corrupt, re-downloading CIK map")

        logger.info("Downloading CIK map from SEC...")
        resp = httpx.get(TICKERS_URL, headers={"User-Agent": _get_user_agent()}, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        # Structure: {"fields": ["cik","name","ticker","exchange"], "data": [[cik, name, ticker, exchange], ...]}
        fields = data.get("fields", [])
        rows = data.get("data", [])

        ticker_idx = fields.index("ticker") if "ticker" in fields else 2
        cik_idx = fields.index("cik") if "cik" in fields else 0
        exchange_idx = fields.index("exchange") if "exchange" in fields else 3

        for row in rows:
            ticker = str(row[ticker_idx]).upper()
            cik = str(row[cik_idx]).zfill(10)
            exchange = str(row[exchange_idx]) if row[exchange_idx] else ""
            self._map[ticker] = (cik, exchange)

        # Cache to disk
        cache_data = {k: list(v) for k, v in self._map.items()}
        CACHE_PATH.write_text(json.dumps(cache_data))
        logger.info("Downloaded CIK map: %d tickers → %s", len(self._map), CACHE_PATH.name)

    def lookup(self, ticker: str) -> tuple[str, str] | None:
        """Return (cik, exchange) for a ticker, or None if not found."""
        return self._map.get(ticker.upper())

    def cik(self, ticker: str) -> str | None:
        """Return just the CIK for a ticker, or None."""
        result = self._map.get(ticker.upper())
        return result[0] if result else None

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, ticker: str) -> bool:
        return ticker.upper() in self._map
