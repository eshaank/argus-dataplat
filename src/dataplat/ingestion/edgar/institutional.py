"""SEC EDGAR institutional holders pipeline — SC 13G/13D XML → institutional_holders table."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.edgar.cik_map import CIKMap
from dataplat.ingestion.edgar.client import (
    build_filing_url,
    get_filing_doc,
    get_filing_index,
    get_submissions,
    make_client,
)

logger = logging.getLogger(__name__)

_13G_FORMS = {"SC 13G", "SC 13G/A", "SCHEDULE 13G", "SCHEDULE 13G/A"}
_13D_FORMS = {"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A"}
ALL_13_FORMS = _13G_FORMS | _13D_FORMS


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from a tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _find(el: ET.Element, tag: str) -> ET.Element | None:
    """Find a child element, ignoring namespaces."""
    direct = el.find(tag)
    if direct is not None:
        return direct
    for child in el:
        if _strip_ns(child.tag) == tag:
            return child
    return None


def _text_ns(el: ET.Element, tag: str) -> str | None:
    """Get text from a child, namespace-agnostic."""
    child = _find(el, tag)
    return child.text.strip() if child is not None and child.text else None


def _float_ns(el: ET.Element, tag: str) -> float | None:
    """Get float from a child, namespace-agnostic."""
    text = _text_ns(el, tag)
    if text is None:
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def parse_13g_xml(xml_text: str) -> dict | None:
    """Parse a structured SC 13G/13D XML (post-2025 format).

    Returns a dict with holder info or None if parsing fails.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Check it's actually a 13G/13D
    form_data = _find(root, "formData")
    if form_data is None:
        return None

    header = _find(form_data, "coverPageHeader")
    person = _find(form_data, "coverPageHeaderReportingPersonDetails")
    items = _find(form_data, "items")

    if person is None:
        return None

    # Extract holder info
    holder_name = _text_ns(person, "reportingPersonName") or ""
    holder_type = _text_ns(person, "typeOfReportingPerson") or ""

    # Shares and ownership
    shares_el = _find(person, "reportingPersonBeneficiallyOwnedNumberOfShares")
    sole_voting = _float_ns(shares_el, "soleVotingPower") if shares_el is not None else None
    shared_voting = _float_ns(shares_el, "sharedVotingPower") if shares_el is not None else None
    sole_disp = _float_ns(shares_el, "soleDispositivePower") if shares_el is not None else None
    shared_disp = _float_ns(shares_el, "sharedDispositivePower") if shares_el is not None else None

    agg_shares = _float_ns(person, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")
    class_pct = _float_ns(person, "classPercent")

    # Try items section for shares too
    if agg_shares is None and items is not None:
        item4 = _find(items, "item4")
        if item4 is not None:
            agg_shares = _float_ns(item4, "amountBeneficiallyOwned")
            if class_pct is None:
                class_pct = _float_ns(item4, "classPercent")

    # Event date
    event_date = _text_ns(header, "eventDateRequiresFilingThisStatement") if header is not None else None
    # Normalize date format (MM/DD/YYYY → YYYY-MM-DD)
    if event_date and "/" in event_date:
        parts = event_date.split("/")
        if len(parts) == 3:
            event_date = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"

    # Amendment info
    amendment_no = None
    is_amendment = False
    if header is not None:
        amend_text = _text_ns(header, "amendmentNo")
        if amend_text:
            is_amendment = True
            try:
                amendment_no = int(amend_text)
            except ValueError:
                amendment_no = None

    # Holder CIK from filer info
    holder_cik = None
    header_data = _find(root, "headerData")
    if header_data is not None:
        filer_info = _find(header_data, "filerInfo")
        if filer_info is not None:
            filer = _find(filer_info, "filer")
            if filer is not None:
                creds = _find(filer, "filerCredentials")
                if creds is not None:
                    holder_cik = _text_ns(creds, "cik")

    # Holder address
    holder_address = None
    if items is not None:
        item2 = _find(items, "item2")
        if item2 is not None:
            holder_address = _text_ns(item2, "principalBusinessOfficeOrResidenceAddress")

    return {
        "holder_cik": holder_cik,
        "holder_name": holder_name,
        "holder_type": holder_type,
        "holder_address": holder_address,
        "shares_held": agg_shares or 0,
        "class_percent": class_pct,
        "sole_voting_power": sole_voting,
        "shared_voting_power": shared_voting,
        "sole_dispositive": sole_disp,
        "shared_dispositive": shared_disp,
        "event_date": event_date,
        "amendment_number": amendment_no,
        "is_amendment": is_amendment,
    }


def _try_parse_html_13g(html_text: str) -> dict | None:
    """Best-effort extraction from pre-2025 HTML 13G filings.

    Returns a dict with whatever we can extract, or None.
    """
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text)

    holder_name = None
    shares = None
    pct = None

    # Try to find "NAME OF REPORTING PERSON" followed by a name
    name_match = re.search(r"NAME OF REPORTING PERSON[S]?\s*[:\-]?\s*([A-Z][\w\s,\.&]+?)(?:\d|\n|CHECK)", text, re.IGNORECASE)
    if name_match:
        holder_name = name_match.group(1).strip()

    # Try to find aggregate shares
    shares_match = re.search(r"AGGREGATE AMOUNT[^:]*?(\d[\d,]+)", text, re.IGNORECASE)
    if shares_match:
        try:
            shares = float(shares_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Try to find percent
    pct_match = re.search(r"PERCENT OF CLASS[^:]*?([\d.]+)\s*%?", text, re.IGNORECASE)
    if pct_match:
        try:
            pct = float(pct_match.group(1))
        except ValueError:
            pass

    if not holder_name and not shares:
        return None

    return {
        "holder_cik": None,
        "holder_name": holder_name or "",
        "holder_type": "",
        "holder_address": None,
        "shares_held": shares or 0,
        "class_percent": pct,
        "sole_voting_power": None,
        "shared_voting_power": None,
        "sole_dispositive": None,
        "shared_dispositive": None,
        "event_date": None,
        "amendment_number": None,
        "is_amendment": False,
    }


def run_institutional_backfill(
    tickers: list[str],
    *,
    cik_map: CIKMap | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Backfill institutional holders from SC 13G/13D filings.

    Returns total rows inserted.
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
    total_filings_parsed = 0
    skipped = 0
    failures: list[str] = []

    logger.info("EDGAR institutional backfill: %d tickers", len(tickers))

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

                # Collect 13G/13D filings
                filings_13: list[tuple[str, str, str, str]] = []  # (form, accession, filed, doc)
                for i, form in enumerate(forms):
                    if form not in ALL_13_FORMS:
                        continue
                    acc = accessions[i] if i < len(accessions) else ""
                    filed = filed_dates[i] if i < len(filed_dates) else ""
                    doc = primary_docs[i] if i < len(primary_docs) else ""
                    if acc:
                        filings_13.append((form, acc, filed, doc))

                if not filings_13:
                    skipped += 1
                    continue

                ticker_rows: list[dict] = []
                for form_type, acc, filed, doc in filings_13:
                    try:
                        # Try primary_doc.xml first (structured XML, post-2025)
                        parsed: dict | None = None
                        doc_text: str | None = None

                        if doc.endswith(".xml"):
                            doc_text = get_filing_doc(client, cik, acc, doc)
                            if doc_text and "schedule13" in doc_text[:500].lower():
                                parsed = parse_13g_xml(doc_text)
                        else:
                            # Check filing index for primary_doc.xml
                            index_files = get_filing_index(client, cik, acc)
                            for f in index_files:
                                name = f.get("name", "")
                                if name == "primary_doc.xml":
                                    doc_text = get_filing_doc(client, cik, acc, name)
                                    if doc_text and "schedule13" in doc_text[:500].lower():
                                        parsed = parse_13g_xml(doc_text)
                                    break

                        # Fallback: try HTML parsing for older filings
                        if parsed is None and doc and not doc.endswith(".xml"):
                            doc_text = get_filing_doc(client, cik, acc, doc)
                            if doc_text:
                                parsed = _try_parse_html_13g(doc_text)

                        if parsed is None:
                            continue

                        filing_url = build_filing_url(cik, acc)
                        ticker_rows.append({
                            "ticker": ticker,
                            "cik": cik,
                            "accession_number": acc,
                            "filed_date": filed,
                            "event_date": parsed.get("event_date"),
                            "holder_cik": parsed.get("holder_cik"),
                            "holder_name": parsed.get("holder_name", ""),
                            "holder_type": parsed.get("holder_type", ""),
                            "holder_address": parsed.get("holder_address"),
                            "shares_held": parsed.get("shares_held", 0),
                            "class_percent": parsed.get("class_percent"),
                            "sole_voting_power": parsed.get("sole_voting_power"),
                            "shared_voting_power": parsed.get("shared_voting_power"),
                            "sole_dispositive": parsed.get("sole_dispositive"),
                            "shared_dispositive": parsed.get("shared_dispositive"),
                            "form_type": form_type,
                            "amendment_number": parsed.get("amendment_number"),
                            "is_amendment": parsed.get("is_amendment", False),
                            "primary_doc": doc,
                            "filing_url": filing_url,
                            "source": "sec_edgar",
                        })
                        total_filings_parsed += 1

                    except Exception as exc:
                        logger.debug("%s 13G/D %s: parse error — %s", ticker, acc, exc)

                if ticker_rows:
                    df = pl.DataFrame(ticker_rows)
                    for col in ["filed_date", "event_date"]:
                        if col in df.columns:
                            df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))
                    ch.insert_arrow("institutional_holders", df.to_arrow())
                    total_rows += len(df)

                if idx % 50 == 0 or idx == len(tickers):
                    logger.info(
                        "[%d/%d] %s — total: %s rows from %d filings",
                        idx, len(tickers), ticker,
                        f"{total_rows:,}", total_filings_parsed,
                    )

            except Exception as exc:
                logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
                failures.append(ticker)

    finally:
        if own_client:
            client.close()

    elapsed = time.monotonic() - start_time
    logger.info(
        "EDGAR institutional complete: %s rows from %d filings, %d skipped in %.1f min",
        f"{total_rows:,}", total_filings_parsed, skipped, elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures[:50]))

    return total_rows
