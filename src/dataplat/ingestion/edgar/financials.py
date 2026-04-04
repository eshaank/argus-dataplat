"""SEC EDGAR financials pipeline — companyfacts → financials table."""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.edgar.cik_map import CIKMap
from dataplat.ingestion.edgar.client import build_filing_url, get_companyfacts, make_client
from dataplat.ingestion.edgar.concepts import extract_financials

logger = logging.getLogger(__name__)

# All columns in the financials table (must match migration 019)
FINANCIALS_COLUMNS = [
    "ticker", "cik", "period_start", "period_end", "fiscal_year", "fiscal_period",
    "form_type", "filed_date", "accession_number",
    # Income
    "revenue", "cost_of_revenue", "gross_profit", "operating_expenses",
    "operating_income", "net_income", "basic_eps", "diluted_eps",
    "research_and_dev", "sga_expenses", "income_tax", "interest_expense", "ebitda",
    # Balance
    "total_assets", "current_assets", "noncurrent_assets",
    "total_liabilities", "current_liabilities", "noncurrent_liabilities",
    "total_equity", "retained_earnings", "long_term_debt", "short_term_debt",
    "cash_and_equivalents", "inventory", "accounts_receivable", "accounts_payable", "goodwill",
    # Cash Flow
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "dividends_paid", "depreciation_amortization",
    # Dilution
    "shares_outstanding", "shares_issued",
    "weighted_avg_shares_basic", "weighted_avg_shares_diluted",
    "stock_based_compensation", "buyback_shares", "buyback_value",
    "shares_issued_options", "shares_issued_rsu_vested", "unvested_rsu_shares",
    "antidilutive_shares", "dividends_per_share", "issuance_proceeds",
    # Authorized Headroom
    "shares_authorized", "preferred_shares_authorized",
    "stock_plan_shares_authorized", "buyback_program_authorized",
    # Warrants
    "warrants_outstanding", "warrant_exercise_price", "warrant_shares_callable",
    "warrants_fair_value", "warrant_proceeds",
    # Convertible Debt
    "convertible_debt", "convertible_debt_current",
    "convertible_conversion_price", "convertible_conversion_ratio",
    "convertible_debt_proceeds", "convertible_debt_repayments", "shares_from_conversion",
    # Options Pool
    "options_outstanding", "options_exercisable",
    "options_weighted_avg_price", "options_intrinsic_value",
    # Meta
    "filing_url", "source",
]


def _transform_periods(ticker: str, cik: str, periods: list[dict]) -> pl.DataFrame:
    """Transform extracted periods into a DataFrame matching the financials schema."""
    if not periods:
        return pl.DataFrame()

    rows: list[dict] = []
    for p in periods:
        row: dict = {
            "ticker": ticker,
            "cik": cik,
            "period_start": p.get("period_start"),
            "period_end": p.get("period_end"),
            "fiscal_year": p.get("period_end", "")[:4],
            "fiscal_period": p.get("fiscal_period", ""),
            "form_type": p.get("form_type", ""),
            "filed_date": p.get("filed_date"),
            "accession_number": p.get("accession_number"),
        }

        # Copy all financial fields
        for col in FINANCIALS_COLUMNS:
            if col not in row and col not in ("ticker", "cik", "filing_url", "source"):
                row[col] = p.get(col)

        # Build filing URL
        accn = p.get("accession_number")
        row["filing_url"] = build_filing_url(cik, accn) if accn else ""
        row["source"] = "sec_edgar"

        rows.append(row)

    df = pl.DataFrame(rows, infer_schema_length=None)

    # Cast date columns
    for col in ["period_start", "period_end", "filed_date"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))

    # Ensure all numeric columns are Float64 (avoid int/float mix across rows)
    for col in df.columns:
        if col in ("ticker", "cik", "fiscal_year", "fiscal_period", "form_type",
                   "accession_number", "filing_url", "source",
                   "period_start", "period_end", "filed_date"):
            continue
        if df[col].dtype in (pl.Int64, pl.Int32, pl.UInt64, pl.UInt32):
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))

    return df


def run_financials_backfill(
    tickers: list[str],
    *,
    cik_map: CIKMap | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Backfill financials from SEC EDGAR companyfacts API.

    Args:
        tickers: List of ticker symbols.
        cik_map: Pre-loaded CIK map (created if None).
        client: Pre-created httpx client (created if None).

    Returns:
        Total rows inserted.
    """
    ensure_schema()
    ch = get_client()

    if cik_map is None:
        cik_map = CIKMap()
        cik_map.load()

    own_client = client is None
    if own_client:
        client = make_client()

    start_time = time.monotonic()
    total_rows = 0
    total_periods = 0
    skipped = 0
    failures: list[str] = []

    logger.info("EDGAR financials backfill: %d tickers", len(tickers))

    try:
        for idx, ticker in enumerate(tickers, 1):
            cik = cik_map.cik(ticker)
            if not cik:
                logger.debug("[%d/%d] %s: no CIK mapping, skipping", idx, len(tickers), ticker)
                skipped += 1
                continue

            try:
                data = get_companyfacts(client, cik)
                if not data:
                    logger.debug("[%d/%d] %s: no companyfacts data", idx, len(tickers), ticker)
                    skipped += 1
                    continue

                periods = extract_financials(data)
                if not periods:
                    logger.debug("[%d/%d] %s: no financial periods extracted", idx, len(tickers), ticker)
                    skipped += 1
                    continue

                df = _transform_periods(ticker, cik, periods)
                if df.is_empty():
                    continue

                ch.insert_arrow("financials", df.to_arrow())
                total_rows += len(df)
                total_periods += len(periods)

                if idx % 100 == 0 or idx == len(tickers):
                    logger.info(
                        "[%d/%d] %s: %d periods — total: %s rows",
                        idx, len(tickers), ticker, len(periods), f"{total_rows:,}",
                    )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    finally:
        if own_client:
            client.close()

    elapsed = time.monotonic() - start_time
    logger.info(
        "EDGAR financials complete: %s rows, %d periods, %d skipped in %.1f min",
        f"{total_rows:,}", total_periods, skipped, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures[:50]))

    return total_rows
