"""Polygon company fundamentals backfill — financials, dividends, splits, ticker details.

Fetches per-ticker from Polygon reference endpoints and bulk-inserts into ClickHouse.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

POLYGON_BASE = "https://api.polygon.io"


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


def _extract_financial_value(section: dict, key: str) -> float | None:
    """Extract a numeric value from a Polygon financials section."""
    item = section.get(key)
    if item and isinstance(item, dict):
        return item.get("value")
    return None


def _transform_financials(results: list[dict], ticker: str) -> pl.DataFrame:
    """Transform Polygon /vX/reference/financials results into a DataFrame."""
    rows: list[dict] = []
    for r in results:
        fin = r.get("financials", {})
        inc = fin.get("income_statement", {})
        bs = fin.get("balance_sheet", {})
        cf = fin.get("cash_flow_statement", {})

        rows.append({
            "ticker": ticker,
            "period_start": r.get("start_date"),
            "period_end": r.get("end_date"),
            "fiscal_year": r.get("fiscal_year", ""),
            "fiscal_period": r.get("fiscal_period", ""),
            "timeframe": r.get("timeframe", ""),
            "filing_date": r.get("filing_date"),
            "cik": r.get("cik"),
            # Income Statement
            "revenue": _extract_financial_value(inc, "revenues"),
            "cost_of_revenue": _extract_financial_value(inc, "cost_of_revenue"),
            "gross_profit": _extract_financial_value(inc, "gross_profit"),
            "operating_expenses": _extract_financial_value(inc, "operating_expenses"),
            "operating_income": _extract_financial_value(inc, "operating_income_loss"),
            "net_income": _extract_financial_value(inc, "net_income_loss"),
            "basic_eps": _extract_financial_value(inc, "basic_earnings_per_share"),
            "diluted_eps": _extract_financial_value(inc, "diluted_earnings_per_share"),
            "basic_shares": _extract_financial_value(inc, "basic_average_shares"),
            "diluted_shares": _extract_financial_value(inc, "diluted_average_shares"),
            "research_and_dev": _extract_financial_value(inc, "research_and_development"),
            "sga_expenses": _extract_financial_value(inc, "selling_general_and_administrative_expenses"),
            "income_tax": _extract_financial_value(inc, "income_tax_expense_benefit"),
            # Balance Sheet
            "total_assets": _extract_financial_value(bs, "assets"),
            "current_assets": _extract_financial_value(bs, "current_assets"),
            "noncurrent_assets": _extract_financial_value(bs, "noncurrent_assets"),
            "total_liabilities": _extract_financial_value(bs, "liabilities"),
            "current_liabilities": _extract_financial_value(bs, "current_liabilities"),
            "noncurrent_liabilities": _extract_financial_value(bs, "noncurrent_liabilities"),
            "total_equity": _extract_financial_value(bs, "equity"),
            "long_term_debt": _extract_financial_value(bs, "long_term_debt"),
            "inventory": _extract_financial_value(bs, "inventory"),
            "accounts_payable": _extract_financial_value(bs, "accounts_payable"),
            # Cash Flow
            "operating_cash_flow": _extract_financial_value(cf, "net_cash_flow_from_operating_activities"),
            "investing_cash_flow": _extract_financial_value(cf, "net_cash_flow_from_investing_activities"),
            "financing_cash_flow": _extract_financial_value(cf, "net_cash_flow_from_financing_activities"),
            "net_cash_flow": _extract_financial_value(cf, "net_cash_flow"),
            # Overflow
            "raw_json": json.dumps(r),
        })

    if not rows:
        return pl.DataFrame()

    df = pl.DataFrame(rows)

    # Cast date columns
    for col in ["period_start", "period_end", "filing_date"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))

    # Cast share counts to UInt64
    for col in ["basic_shares", "diluted_shares"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.UInt64, strict=False))

    return df


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
    """Backfill financials, dividends, splits, and ticker details for a list of tickers."""
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY must be set in .env")

    ch = get_client()
    start_time = time.monotonic()
    total_financials = 0
    total_dividends = 0
    total_details = 0
    failures: list[str] = []

    logger.info("Fundamentals backfill: %d tickers", len(tickers))

    total_splits = 0

    with httpx.Client(timeout=60.0) as client:
        # --- Per-ticker ---
        for idx, ticker in enumerate(tickers, 1):
            try:
                # Financials (quarterly + annual)
                fin_rows = 0
                for tf in ["quarterly", "annual"]:
                    results = _paginate(
                        client,
                        f"{POLYGON_BASE}/vX/reference/financials",
                        {"ticker": ticker, "timeframe": tf, "limit": "100", "apiKey": settings.polygon_api_key},
                    )
                    if results:
                        df = _transform_financials(results, ticker)
                        if not df.is_empty():
                            ch.insert_arrow("financials", df.to_arrow())
                            fin_rows += len(df)

                total_financials += fin_rows

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
                        ch.command(
                            "INSERT INTO universe (ticker, name, type, exchange, sector, sic_code, "
                            "market_cap, active, description, homepage_url, total_employees, "
                            "list_date, cik, sic_description, address_city, address_state, composite_figi) "
                            "VALUES (%(ticker)s, %(name)s, %(type)s, %(exchange)s, '', %(sic_code)s, "
                            "%(market_cap)s, true, %(description)s, %(homepage_url)s, %(total_employees)s, "
                            "%(list_date)s, %(cik)s, %(sic_description)s, %(city)s, %(state)s, %(figi)s)",
                            parameters={
                                "ticker": ticker,
                                "name": detail.get("name", ""),
                                "type": detail.get("type", ""),
                                "exchange": detail.get("primary_exchange", ""),
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
                    "[%d/%d] %s: %d financials, %d dividends, %d splits",
                    idx, len(tickers), ticker, fin_rows, div_rows, split_rows,
                )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    elapsed = time.monotonic() - start_time
    logger.info(
        "Fundamentals backfill complete: %d financials, %d dividends, %d splits, %d details in %.1f min",
        total_financials, total_dividends, total_splits, total_details, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures))
