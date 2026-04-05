"""Polygon reference backfill — dividends, splits, ticker details.

Financials are owned by SEC EDGAR (backfill-edgar --financials).
This pipeline handles only corporate actions and universe enrichment.
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

POLYGON_BASE = "https://api.polygon.io"

# ISO 10383 MIC code → human-readable exchange name
MIC_TO_EXCHANGE: dict[str, str] = {
    "XNYS": "NYSE",
    "XNAS": "NASDAQ",
    "XASE": "NYSE American",
    "ARCX": "NYSE Arca",
    "BATS": "Cboe BZX",
    "EDGX": "Cboe EDGX",
    "IEXG": "IEX",
    "XPHL": "NASDAQ PSX",
    "XBOS": "NASDAQ BX",
    "XCHI": "Chicago SE",
    "OTCM": "OTC Markets",
    "OOTC": "OTC Markets",
}


def _paginate(client: httpx.Client, url: str, params: dict) -> list[dict]:
    """Paginate through a Polygon v3/vX endpoint, collecting all results."""
    all_results: list[dict] = []
    while url:
        resp = client.get(url, params=params)
        if resp.status_code == 403:
            return all_results
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        next_url = data.get("next_url")
        if next_url:
            url = next_url
            params = {"apiKey": settings.polygon_api_key}
        else:
            url = None
    return all_results


def _transform_dividends(results: list[dict]) -> pl.DataFrame:
    """Transform Polygon /v3/reference/dividends results."""
    if not results:
        return pl.DataFrame()

    rows = []
    for r in results:
        rows.append({
            "ticker": r.get("ticker", ""),
            "ex_dividend_date": r.get("ex_dividend_date"),
            "declaration_date": r.get("declaration_date"),
            "record_date": r.get("record_date"),
            "pay_date": r.get("pay_date"),
            "cash_amount": r.get("cash_amount", 0.0),
            "currency": r.get("currency", "USD"),
            "frequency": r.get("frequency", 0),
            "dividend_type": r.get("dividend_type", ""),
        })

    df = pl.DataFrame(rows)
    for col in ["ex_dividend_date", "declaration_date", "record_date", "pay_date"]:
        df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))
    df = df.with_columns(pl.col("frequency").cast(pl.UInt8))
    return df


def _transform_splits(results: list[dict]) -> pl.DataFrame:
    """Transform Polygon /v3/reference/splits results."""
    if not results:
        return pl.DataFrame()

    rows = [
        {
            "ticker": r.get("ticker", ""),
            "execution_date": r.get("execution_date"),
            "split_from": float(r.get("split_from", 0)),
            "split_to": float(r.get("split_to", 0)),
        }
        for r in results
    ]

    df = pl.DataFrame(rows)
    df = df.with_columns(pl.col("execution_date").cast(pl.Date, strict=False))
    return df


def run_fundamentals_backfill(tickers: list[str]) -> None:
    """Backfill dividends, splits, and ticker details for a list of tickers.

    Financials are handled by SEC EDGAR (backfill-edgar --financials).
    """
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY must be set in .env")

    ensure_schema()
    ch = get_client()
    start_time = time.monotonic()
    total_dividends = 0
    total_details = 0
    total_splits = 0
    failures: list[str] = []

    logger.info("Reference backfill: %d tickers", len(tickers))

    with httpx.Client(timeout=60.0) as client:
        # --- Per-ticker ---
        for idx, ticker in enumerate(tickers, 1):
            try:
                # Dividends
                div_results = _paginate(
                    client,
                    f"{POLYGON_BASE}/v3/reference/dividends",
                    {"ticker": ticker, "limit": "1000", "apiKey": settings.polygon_api_key},
                )
                div_rows = 0
                if div_results:
                    df_div = _transform_dividends(div_results)
                    if not df_div.is_empty():
                        ch.insert_arrow("dividends", df_div.to_arrow())
                        div_rows = len(df_div)
                total_dividends += div_rows

                # Stock Splits (per-ticker)
                split_results = _paginate(
                    client,
                    f"{POLYGON_BASE}/v3/reference/splits",
                    {"ticker": ticker, "limit": "100", "apiKey": settings.polygon_api_key},
                )
                split_rows = 0
                if split_results:
                    df_splits = _transform_splits(split_results)
                    if not df_splits.is_empty():
                        ch.insert_arrow("stock_splits", df_splits.to_arrow())
                        split_rows = len(df_splits)
                total_splits += split_rows

                # Ticker Details → enrich universe
                detail_resp = client.get(
                    f"{POLYGON_BASE}/v3/reference/tickers/{ticker}",
                    params={"apiKey": settings.polygon_api_key},
                )
                if detail_resp.status_code == 200:
                    detail = detail_resp.json().get("results", {})
                    if detail:
                        addr = detail.get("address", {})
                        mic = detail.get("primary_exchange", "")
                        exchange_name = MIC_TO_EXCHANGE.get(mic, mic)
                        ch.command(
                            "INSERT INTO universe (ticker, name, type, exchange, mic_code, sector, sic_code, "
                            "market_cap, active, description, homepage_url, total_employees, "
                            "list_date, cik, sic_description, address_city, address_state, composite_figi) "
                            "VALUES (%(ticker)s, %(name)s, %(type)s, %(exchange)s, %(mic_code)s, '', %(sic_code)s, "
                            "%(market_cap)s, true, %(description)s, %(homepage_url)s, %(total_employees)s, "
                            "%(list_date)s, %(cik)s, %(sic_description)s, %(city)s, %(state)s, %(figi)s)",
                            parameters={
                                "ticker": ticker,
                                "name": detail.get("name", ""),
                                "type": detail.get("type", ""),
                                "exchange": exchange_name,
                                "mic_code": mic,
                                "sic_code": detail.get("sic_code", ""),
                                "market_cap": detail.get("market_cap", 0.0),
                                "description": detail.get("description", ""),
                                "homepage_url": detail.get("homepage_url", ""),
                                "total_employees": detail.get("total_employees", 0),
                                "list_date": detail.get("list_date", "1970-01-01"),
                                "cik": detail.get("cik", ""),
                                "sic_description": detail.get("sic_description", ""),
                                "city": addr.get("city", ""),
                                "state": addr.get("state", ""),
                                "figi": detail.get("composite_figi", ""),
                            },
                        )
                        total_details += 1

                logger.info(
                    "[%d/%d] %s: %d dividends, %d splits",
                    idx, len(tickers), ticker, div_rows, split_rows,
                )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    elapsed = time.monotonic() - start_time
    logger.info(
        "Reference backfill complete: %d dividends, %d splits, %d details in %.1f min",
        total_dividends, total_splits, total_details, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures))
