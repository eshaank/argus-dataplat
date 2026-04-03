"""Tests for OHLCV transform functions."""

from __future__ import annotations

from dataplat.transforms.ohlcv import transform_polygon_aggs, transform_schwab_candles
from dataplat.transforms.validation import validate_ohlcv


def test_polygon_transform_shape(sample_polygon_results: list[dict]) -> None:
    df = transform_polygon_aggs(sample_polygon_results, "AAPL")
    assert len(df) == 3
    assert set(df.columns) == {
        "ticker", "timestamp", "open", "high", "low", "close",
        "volume", "vwap", "transactions", "source",
    }
    assert df["ticker"][0] == "AAPL"
    assert df["source"][0] == "polygon_backfill"


def test_polygon_transform_types(sample_polygon_results: list[dict]) -> None:
    import polars as pl

    df = transform_polygon_aggs(sample_polygon_results, "AAPL")
    assert df["open"].dtype == pl.Float64
    assert df["volume"].dtype == pl.UInt64
    assert df["vwap"].dtype == pl.Float64
    assert df["transactions"].dtype == pl.UInt32


def test_schwab_transform_shape(sample_schwab_candles: list[dict]) -> None:
    df = transform_schwab_candles(sample_schwab_candles, "AAPL")
    assert len(df) == 3
    assert df["ticker"][0] == "AAPL"
    assert df["source"][0] == "schwab"
    assert df["vwap"][0] is None
    assert df["transactions"][0] is None


def test_polygon_empty_input() -> None:
    df = transform_polygon_aggs([], "AAPL")
    assert df.is_empty()


def test_validation_drops_bad_rows(sample_polygon_results: list[dict]) -> None:
    # Inject a bad row: high < low
    bad = sample_polygon_results + [
        {"v": 100, "vw": 200.0, "o": 200.0, "c": 200.0, "h": 195.0, "l": 205.0, "t": 1743494580000, "n": 5}
    ]
    df = transform_polygon_aggs(bad, "AAPL")
    assert len(df) == 4  # pre-validation
    df = validate_ohlcv(df)
    assert len(df) == 3  # bad row dropped


def test_validation_dedup(sample_polygon_results: list[dict]) -> None:
    duped = sample_polygon_results + [sample_polygon_results[0]]
    df = transform_polygon_aggs(duped, "AAPL")
    df = validate_ohlcv(df)
    assert len(df) == 3  # duplicate removed
