"""SEC EDGAR insider trades pipeline — Form 4 XML → insider_trades table."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.edgar.cik_map import CIKMap
from dataplat.ingestion.edgar.client import (
    build_filing_url,
    get_filing_index,
    get_submissions,
    make_client,
)

logger = logging.getLogger(__name__)

# Transaction code → human-readable type
TX_CODE_MAP: dict[str, str] = {
    "P": "buy",
    "S": "sell",
    "M": "exercise",
    "F": "tax_withhold",
    "G": "gift",
    "A": "award",
    "C": "conversion",
    "D": "disposition_to_issuer",
    "E": "expiration",
    "H": "expiration",
    "I": "discretionary",
    "J": "other",
    "K": "equity_swap",
    "L": "small_acquisition",
    "O": "exercise_oom",
    "U": "disposition_tender",
    "W": "acquisition_will",
    "X": "exercise_itm",
    "Z": "deposit_withdrawal",
}


def _text(el: ET.Element | None, tag: str) -> str | None:
    """Safely extract text from a child element."""
    if el is None:
        return None
    child = el.find(tag)
    if child is None:
        # Try with namespace-less search
        for c in el:
            if c.tag.split("}")[-1] == tag:
                return c.text
        return None
    return child.text


def _float(el: ET.Element | None, tag: str) -> float | None:
    """Safely extract a float from a child element's <value> or direct text."""
    if el is None:
        return None
    child = el.find(tag)
    if child is None:
        return None
    # Some fields have <value> sub-element, some have direct text
    value_el = child.find("value")
    text = value_el.text if value_el is not None else child.text
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except (ValueError, TypeError):
        return None


def _bool_flag(el: ET.Element | None, tag: str) -> bool:
    """Check if a boolean flag element has value 'true' or '1'."""
    if el is None:
        return False
    child = el.find(tag)
    if child is None:
        return False
    text = (child.text or "").strip().lower()
    return text in ("true", "1", "yes")


def parse_form4_xml(xml_text: str) -> list[dict]:
    """Parse a Form 4 XML document into transaction dicts.

    Returns a list of transactions (a single Form 4 can contain multiple).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    transactions: list[dict] = []

    # Period of report
    report_date = _text(root, "periodOfReport")

    # Issuer info
    issuer = root.find("issuer")
    issuer_ticker = _text(issuer, "issuerTradingSymbol") or ""

    # Reporter info
    reporter = root.find("reportingOwner")
    reporter_id = reporter.find("reportingOwnerId") if reporter is not None else None
    reporter_rel = reporter.find("reportingOwnerRelationship") if reporter is not None else None

    reporter_cik = _text(reporter_id, "rptOwnerCik")
    reporter_name = _text(reporter_id, "rptOwnerName") or ""
    is_officer = _bool_flag(reporter_rel, "isOfficer")
    is_director = _bool_flag(reporter_rel, "isDirector")
    is_ten_pct = _bool_flag(reporter_rel, "isTenPercentOwner")
    officer_title = _text(reporter_rel, "officerTitle")

    base = {
        "report_date": report_date,
        "reporter_cik": reporter_cik,
        "reporter_name": reporter_name,
        "reporter_title": officer_title,
        "is_officer": is_officer,
        "is_director": is_director,
        "is_ten_pct_owner": is_ten_pct,
    }

    # Non-derivative transactions (common stock)
    nd_table = root.find("nonDerivativeTable")
    if nd_table is not None:
        for tx in nd_table.findall("nonDerivativeTransaction"):
            security = _text(tx.find("securityTitle"), "value") or ""
            coding = tx.find("transactionCoding")
            code = _text(coding, "transactionCode") or ""
            amounts = tx.find("transactionAmounts")
            shares = _float(amounts, "transactionShares")
            price = _float(amounts, "transactionPricePerShare")
            acq_disp_el = amounts.find("transactionAcquiredDisposedCode") if amounts is not None else None
            acq_disp = _text(acq_disp_el, "value") if acq_disp_el is not None else None

            post = tx.find("postTransactionAmounts")
            shares_after = _float(post, "sharesOwnedFollowingTransaction")

            ownership = tx.find("ownershipNature")
            own_type_el = ownership.find("directOrIndirectOwnership") if ownership is not None else None
            own_type = _text(own_type_el, "value") if own_type_el is not None else "D"

            value = (shares or 0) * (price or 0) if shares and price else None

            transactions.append({
                **base,
                "security_title": security,
                "transaction_code": code,
                "transaction_type": TX_CODE_MAP.get(code, "other"),
                "is_derivative": False,
                "shares": shares or 0,
                "price": price,
                "value": value,
                "acquired_or_disposed": acq_disp or "",
                "shares_owned_after": shares_after,
                "ownership_type": own_type or "D",
            })

    # Derivative transactions (options, warrants)
    d_table = root.find("derivativeTable")
    if d_table is not None:
        for tx in d_table.findall("derivativeTransaction"):
            security = _text(tx.find("securityTitle"), "value") or ""
            coding = tx.find("transactionCoding")
            code = _text(coding, "transactionCode") or ""
            amounts = tx.find("transactionAmounts")
            shares = _float(amounts, "transactionShares")
            price = _float(amounts, "transactionPricePerShare")
            acq_disp_el = amounts.find("transactionAcquiredDisposedCode") if amounts is not None else None
            acq_disp = _text(acq_disp_el, "value") if acq_disp_el is not None else None

            post = tx.find("postTransactionAmounts")
            shares_after = _float(post, "sharesOwnedFollowingTransaction")

            ownership = tx.find("ownershipNature")
            own_type_el = ownership.find("directOrIndirectOwnership") if ownership is not None else None
            own_type = _text(own_type_el, "value") if own_type_el is not None else "D"

            value = (shares or 0) * (price or 0) if shares and price else None

            transactions.append({
                **base,
                "security_title": security,
                "transaction_code": code,
                "transaction_type": TX_CODE_MAP.get(code, "other"),
                "is_derivative": True,
                "shares": shares or 0,
                "price": price,
                "value": value,
                "acquired_or_disposed": acq_disp or "",
                "shares_owned_after": shares_after,
                "ownership_type": own_type or "D",
            })

    return transactions


def run_insider_backfill(
    tickers: list[str],
    *,
    years: int = 3,
    cik_map: CIKMap | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Backfill insider trades from Form 4 XML filings.

    Args:
        tickers: List of ticker symbols.
        years: How many years back to fetch Form 4s (default 3).
        cik_map: Pre-loaded CIK map.
        client: Pre-created httpx client.

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

    cutoff = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    start_time = time.monotonic()
    total_rows = 0
    total_form4s = 0
    skipped = 0
    failures: list[str] = []

    logger.info("EDGAR insider backfill: %d tickers, %d years back", len(tickers), years)

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

                recent = submissions.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                accessions = recent.get("accessionNumber", [])
                filed_dates = recent.get("filingDate", [])
                primary_docs = recent.get("primaryDocument", [])

                # Collect Form 4 accessions within the date range
                form4s: list[tuple[str, str, str]] = []  # (accession, filed_date, primary_doc)
                for i, form in enumerate(forms):
                    if form != "4":
                        continue
                    filed = filed_dates[i] if i < len(filed_dates) else ""
                    if filed < cutoff:
                        continue
                    acc = accessions[i] if i < len(accessions) else ""
                    doc = primary_docs[i] if i < len(primary_docs) else ""
                    if acc:
                        form4s.append((acc, filed, doc))

                if not form4s:
                    skipped += 1
                    continue

                # Fetch and parse each Form 4 XML
                ticker_rows: list[dict] = []
                for acc, filed, doc in form4s:
                    try:
                        # Find the raw XML file (not the XSLT-rendered version)
                        xml_text: str | None = None

                        # If primary_doc points to xsl*, we need to find the raw XML
                        if "xsl" in doc.lower():
                            index_files = get_filing_index(client, cik, acc)
                            for f in index_files:
                                name = f.get("name", "")
                                if name.endswith(".xml") and "index" not in name.lower() and "xsl" not in name.lower():
                                    from dataplat.ingestion.edgar.client import get_filing_doc
                                    xml_text = get_filing_doc(client, cik, acc, name)
                                    break
                        else:
                            from dataplat.ingestion.edgar.client import get_filing_doc
                            xml_text = get_filing_doc(client, cik, acc, doc)

                        if not xml_text or "<ownershipDocument" not in xml_text:
                            continue

                        txns = parse_form4_xml(xml_text)
                        filing_url = build_filing_url(cik, acc)

                        for tx in txns:
                            tx["ticker"] = ticker
                            tx["cik"] = cik
                            tx["accession_number"] = acc
                            tx["filed_date"] = filed
                            tx["primary_doc"] = doc
                            tx["filing_url"] = filing_url
                            tx["source"] = "sec_edgar"
                            ticker_rows.append(tx)

                        total_form4s += 1

                    except Exception as exc:
                        logger.debug("%s Form 4 %s: parse error — %s", ticker, acc, exc)

                if ticker_rows:
                    df = pl.DataFrame(ticker_rows)
                    # Cast dates
                    for col in ["filed_date", "report_date"]:
                        if col in df.columns:
                            df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))
                    ch.insert_arrow("insider_trades", df.to_arrow())
                    total_rows += len(df)

                if idx % 50 == 0 or idx == len(tickers):
                    logger.info(
                        "[%d/%d] %s — total: %s rows from %d Form 4s",
                        idx, len(tickers), ticker,
                        f"{total_rows:,}", total_form4s,
                    )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    finally:
        if own_client:
            client.close()

    elapsed = time.monotonic() - start_time
    logger.info(
        "EDGAR insider complete: %s rows from %d Form 4s, %d skipped in %.1f min",
        f"{total_rows:,}", total_form4s, skipped, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures[:50]))

    return total_rows
