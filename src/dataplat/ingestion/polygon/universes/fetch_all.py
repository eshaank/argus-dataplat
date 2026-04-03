#!/usr/bin/env python3
"""Fetch all active US equity tickers from Polygon and write to all.txt.

Usage:
    uv run python src/dataplat/ingestion/polygon/universes/fetch_all.py

Requires POLYGON_API_KEY in .env.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import httpx

# Add project root to path so we can import config
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from dataplat.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io/v3/reference/tickers"
OUTPUT = Path(__file__).parent / "all.txt"


def fetch_all_tickers() -> list[str]:
    """Paginate through Polygon reference API and return all active US stock tickers."""
    if not settings.polygon_api_key:
        logger.error("POLYGON_API_KEY not set in .env")
        sys.exit(1)

    tickers: list[str] = []
    params = {
        "market": "stocks",
        "active": "true",
        "locale": "us",
        "type": "CS",  # Common Stock only (excludes ETFs, warrants, etc.)
        "limit": "1000",
        "order": "asc",
        "sort": "ticker",
        "apiKey": settings.polygon_api_key,
    }

    url = POLYGON_BASE
    page = 0

    with httpx.Client(timeout=60.0) as client:
        while url:
            page += 1
            resp = client.get(url, params=params if page == 1 else None)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            batch = [r["ticker"] for r in results if r.get("ticker")]
            tickers.extend(batch)
            logger.info("Page %d: %d tickers (total: %d)", page, len(batch), len(tickers))

            next_url = data.get("next_url")
            if next_url:
                url = f"{next_url}&apiKey={settings.polygon_api_key}"
                params = None  # next_url already has params
            else:
                url = None

    return sorted(set(tickers))


def main() -> None:
    tickers = fetch_all_tickers()
    OUTPUT.write_text("\n".join(tickers) + "\n")
    logger.info("Wrote %d tickers to %s", len(tickers), OUTPUT.name)


if __name__ == "__main__":
    main()
