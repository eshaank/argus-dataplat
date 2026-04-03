"""Shared test fixtures for dataplat tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_polygon_results() -> list[dict]:
    """Realistic Polygon /v2/aggs response results for AAPL."""
    return [
        {"v": 1694, "vw": 221.4161, "o": 221.42, "c": 221.41, "h": 221.42, "l": 221.41, "t": 1743494400000, "n": 29},
        {"v": 463134, "vw": 248.1701, "o": 248.245, "c": 247.64, "h": 249.1, "l": 247.28, "t": 1743494460000, "n": 6345},
        {"v": 12000, "vw": 248.50, "o": 247.64, "c": 248.30, "h": 248.60, "l": 247.50, "t": 1743494520000, "n": 150},
    ]


@pytest.fixture
def sample_schwab_candles() -> list[dict]:
    """Realistic Schwab /pricehistory candles for AAPL."""
    return [
        {"open": 150.0, "high": 152.0, "low": 149.5, "close": 151.0, "volume": 50000000, "datetime": 1704067200000},
        {"open": 151.0, "high": 153.0, "low": 150.0, "close": 152.5, "volume": 45000000, "datetime": 1704153600000},
        {"open": 152.5, "high": 154.0, "low": 151.0, "close": 153.0, "volume": 42000000, "datetime": 1704240000000},
    ]
