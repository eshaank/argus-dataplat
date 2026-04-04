"""SEC EDGAR HTTP client with rate limiting and retry."""

from __future__ import annotations

import logging
import time

import httpx

from dataplat.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://data.sec.gov"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# SEC allows 10 req/sec. We use 100ms sleep = 10 req/sec.
REQUEST_DELAY_S = 0.1

_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _get_with_retry(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    """GET with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params)
            if resp.status_code in _RETRYABLE_STATUS:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "HTTP %d on %s, retry %d/%d in %.1fs",
                    resp.status_code, url[:80], attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            return resp
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "%s on %s, retry %d/%d in %.1fs",
                    type(exc).__name__, url[:80], attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


def _get_user_agent() -> str:
    """Return the SEC EDGAR User-Agent from config, or raise."""
    ua = settings.sec_edgar_user_agent
    if not ua:
        raise RuntimeError(
            "SEC_EDGAR_USER_AGENT must be set in .env "
            '(e.g. SEC_EDGAR_USER_AGENT="YourName your@email.com")'
        )
    return ua


def make_client() -> httpx.Client:
    """Create an httpx client with the required User-Agent header."""
    return httpx.Client(
        timeout=60.0,
        headers={"User-Agent": _get_user_agent()},
        follow_redirects=True,
    )


def get_companyfacts(client: httpx.Client, cik: str) -> dict | None:
    """Fetch all XBRL financial facts for a company.

    Returns the full JSON response or None on 404.
    """
    url = f"{BASE_URL}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
    resp = _get_with_retry(client, url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)
    return resp.json()


def get_submissions(client: httpx.Client, cik: str) -> dict | None:
    """Fetch filing submissions metadata for a company.

    Returns the full JSON response or None on 404.
    """
    url = f"{BASE_URL}/submissions/CIK{cik.zfill(10)}.json"
    resp = _get_with_retry(client, url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)
    return resp.json()


def get_filing_doc(client: httpx.Client, cik: str, accession: str, doc: str) -> str | None:
    """Fetch a specific filing document (XML, HTML, etc.).

    Args:
        cik: Company CIK (leading zeros stripped internally).
        accession: Accession number with dashes (e.g. "0001140361-26-013192").
        doc: Primary document filename.

    Returns the document text or None on 404.
    """
    cik_num = cik.lstrip("0")
    accession_nodash = accession.replace("-", "")
    url = f"{ARCHIVES_URL}/{cik_num}/{accession_nodash}/{doc}"
    resp = _get_with_retry(client, url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)
    return resp.text


def get_filing_index(client: httpx.Client, cik: str, accession: str) -> list[dict]:
    """Fetch the filing index to discover all documents in a filing.

    Returns a list of {name, size} dicts.
    """
    cik_num = cik.lstrip("0")
    accession_nodash = accession.replace("-", "")
    url = f"{ARCHIVES_URL}/{cik_num}/{accession_nodash}/index.json"
    resp = _get_with_retry(client, url)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_S)
    return resp.json().get("directory", {}).get("item", [])


def build_filing_url(cik: str, accession: str) -> str:
    """Construct the SEC filing index page URL."""
    cik_num = cik.lstrip("0")
    accession_nodash = accession.replace("-", "")
    return f"{ARCHIVES_URL}/{cik_num}/{accession_nodash}/"


def build_document_url(cik: str, accession: str, primary_doc: str) -> str:
    """Construct a direct URL to a filing document."""
    cik_num = cik.lstrip("0")
    accession_nodash = accession.replace("-", "")
    return f"{ARCHIVES_URL}/{cik_num}/{accession_nodash}/{primary_doc}"
