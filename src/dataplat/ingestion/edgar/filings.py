"""SEC EDGAR filings + material events pipeline — submissions → sec_filings + material_events."""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.edgar.cik_map import CIKMap
from dataplat.ingestion.edgar.client import build_filing_url, get_submissions, make_client

logger = logging.getLogger(__name__)

# 8-K item code → human-readable description
ITEM_CODE_MAP: dict[str, str] = {
    "1.01": "Material Agreement",
    "1.02": "Termination of Material Agreement",
    "1.03": "Bankruptcy/Receivership",
    "1.04": "Mine Safety",
    "2.01": "Acquisition/Disposition Completed",
    "2.02": "Results of Operations",
    "2.03": "Direct Financial Obligation Created",
    "2.04": "Triggering Event (Acceleration)",
    "2.05": "Restructuring/Exit Costs",
    "2.06": "Material Impairments",
    "3.01": "Delisting Notice",
    "3.02": "Unregistered Sales of Equity",
    "3.03": "Material Modification of Rights",
    "4.01": "Change of Accountant",
    "4.02": "Non-Reliance on Prior Financials",
    "5.01": "Change in Control",
    "5.02": "Officer Departure/Appointment",
    "5.03": "Bylaw Amendments",
    "5.04": "Temporary Suspension of Trading",
    "5.05": "Code of Ethics Amendment",
    "5.06": "Change in Shell Status",
    "5.07": "Submission to Security Holders Vote",
    "5.08": "Shareholder Nominations",
    "6.01": "ABS Servicer Info",
    "6.02": "ABS Change of Servicer",
    "6.03": "ABS Change in Credit Enhancement",
    "6.04": "ABS Failure to Distribute",
    "6.05": "ABS Demand on Securities",
    "7.01": "Reg FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


def _extract_filings(ticker: str, cik: str, submissions: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Extract sec_filings and material_events DataFrames from submissions JSON.

    Returns (filings_df, events_df).
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if not forms:
        return pl.DataFrame(), pl.DataFrame()

    accessions = recent.get("accessionNumber", [])
    filed_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_docs = recent.get("primaryDocument", [])
    primary_descs = recent.get("primaryDocDescription", [])
    items_list = recent.get("items", [])
    is_xbrl_list = recent.get("isXBRL", [])

    n = len(forms)

    # Build sec_filings rows
    filing_rows: list[dict] = []
    event_rows: list[dict] = []

    for i in range(n):
        accession = accessions[i] if i < len(accessions) else ""
        filed = filed_dates[i] if i < len(filed_dates) else ""
        report = report_dates[i] if i < len(report_dates) else None
        doc = primary_docs[i] if i < len(primary_docs) else ""
        desc = primary_descs[i] if i < len(primary_descs) else None
        items_str = items_list[i] if i < len(items_list) else ""
        is_xbrl = bool(is_xbrl_list[i]) if i < len(is_xbrl_list) else False

        url = build_filing_url(cik, accession) if accession else ""

        filing_rows.append({
            "ticker": ticker,
            "cik": cik,
            "accession_number": accession,
            "form_type": forms[i],
            "filed_date": filed or None,
            "report_date": report or None,
            "primary_doc": doc,
            "primary_doc_desc": desc,
            "items": items_str or None,
            "is_xbrl": is_xbrl,
            "filing_url": url,
            "source": "sec_edgar",
        })

        # Expand 8-K items into material_events
        if forms[i] in ("8-K", "8-K/A") and items_str:
            for item_code in items_str.split(","):
                item_code = item_code.strip()
                if not item_code:
                    continue
                event_rows.append({
                    "ticker": ticker,
                    "cik": cik,
                    "accession_number": accession,
                    "filed_date": filed or None,
                    "report_date": report or None,
                    "item_code": item_code,
                    "item_description": ITEM_CODE_MAP.get(item_code, "Unknown"),
                    "primary_doc": doc,
                    "filing_url": url,
                    "source": "sec_edgar",
                })

    filings_df = pl.DataFrame(filing_rows, infer_schema_length=None)
    events_df = pl.DataFrame(event_rows, infer_schema_length=None) if event_rows else pl.DataFrame()

    # Cast dates
    if not filings_df.is_empty():
        for col in ["filed_date", "report_date"]:
            if col in filings_df.columns:
                filings_df = filings_df.with_columns(pl.col(col).cast(pl.Date, strict=False))
    if not events_df.is_empty():
        for col in ["filed_date", "report_date"]:
            if col in events_df.columns:
                events_df = events_df.with_columns(pl.col(col).cast(pl.Date, strict=False))

    return filings_df, events_df


def run_filings_backfill(
    tickers: list[str],
    *,
    cik_map: CIKMap | None = None,
    client: httpx.Client | None = None,
) -> tuple[int, int]:
    """Backfill sec_filings and material_events from EDGAR submissions.

    Returns (filings_rows, events_rows).
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
    total_filings = 0
    total_events = 0
    skipped = 0
    failures: list[str] = []

    logger.info("EDGAR filings backfill: %d tickers", len(tickers))

    try:
        for idx, ticker in enumerate(tickers, 1):
            cik = cik_map.cik(ticker)
            if not cik:
                skipped += 1
                continue

            try:
                submissions = get_submissions(client, cik)
                if not submissions:
                    skipped += 1
                    continue

                filings_df, events_df = _extract_filings(ticker, cik, submissions)

                if not filings_df.is_empty():
                    ch.insert_arrow("sec_filings", filings_df.to_arrow())
                    total_filings += len(filings_df)

                if not events_df.is_empty():
                    ch.insert_arrow("material_events", events_df.to_arrow())
                    total_events += len(events_df)

                if idx % 100 == 0 or idx == len(tickers):
                    logger.info(
                        "[%d/%d] %s — total: %s filings, %s events",
                        idx, len(tickers), ticker,
                        f"{total_filings:,}", f"{total_events:,}",
                    )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    finally:
        if own_client:
            client.close()

    elapsed = time.monotonic() - start_time
    logger.info(
        "EDGAR filings complete: %s filings, %s events, %d skipped in %.1f min",
        f"{total_filings:,}", f"{total_events:,}", skipped, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures[:50]))

    return total_filings, total_events
