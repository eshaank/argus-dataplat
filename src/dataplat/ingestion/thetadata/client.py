"""ThetaData v3 REST API client.

Thin wrapper around ThetaTerminal v3 on localhost:25503.
Returns raw response text (NDJSON/CSV/JSON) — parsing happens
in the transform layer.

Requires ThetaTerminal v3 running: `just thetadata up`
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0


class ThetaDataClient:
    """HTTP client for ThetaTerminal v3 REST API."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 25503,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = f"http://{host}:{port}/v3"
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str]) -> str:
        """Execute GET request and return response text.

        Raises on HTTP errors after logging.
        """
        url = f"{self.base_url}{path}"
        resp = httpx.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    # ── Chain-level endpoints (expiration=*) ──────────────

    def get_eod_greeks(
        self,
        symbol: str,
        date: str,
        *,
        fmt: str = "ndjson",
        max_dte: int | None = None,
        strike_range: int | None = None,
    ) -> str:
        """Full chain EOD greeks for one underlying on one day.

        Uses ``expiration=*`` to get ALL contracts in a single request.
        Returns raw response text in the requested format.

        Parameters
        ----------
        symbol:
            Underlying ticker (e.g., ``AAPL``).
        date:
            Trading date as ``YYYYMMDD`` or ``YYYY-MM-DD``.
        fmt:
            Response format: ``ndjson``, ``csv``, ``json``.
        max_dte:
            If set, only contracts with DTE <= this value.
        strike_range:
            If set, only N strikes above/below spot + ATM.
        """
        params: dict[str, str] = {
            "symbol": symbol,
            "expiration": "*",
            "start_date": date,
            "end_date": date,
            "format": fmt,
        }
        if max_dte is not None:
            params["max_dte"] = str(max_dte)
        if strike_range is not None:
            params["strike_range"] = str(strike_range)
        return self._get("/option/history/greeks/eod", params)

    def get_open_interest(
        self,
        symbol: str,
        date: str,
        *,
        fmt: str = "ndjson",
    ) -> str:
        """Full chain open interest for one underlying on one day.

        Uses ``expiration=*`` to get ALL contracts.
        """
        params: dict[str, str] = {
            "symbol": symbol,
            "expiration": "*",
            "date": date,
            "format": fmt,
        }
        return self._get("/option/history/open_interest", params)

    # ── Discovery endpoints ───────────────────────────────

    def get_expirations(self, symbol: str) -> list[str]:
        """All expiration dates for an underlying.

        Returns list of date strings (``YYYY-MM-DD``).
        """
        import json

        text = self._get("/option/list/expirations", {"symbol": symbol, "format": "json"})
        data = json.loads(text)
        return [row["expiration"] for row in data.get("response", [])]

    def get_trading_dates(self, symbol: str) -> list[str]:
        """All trading dates with data for an underlying.

        Uses the stock trade dates endpoint (same trading calendar
        as options). Returns list of date strings (``YYYY-MM-DD``).
        """
        import json

        text = self._get("/stock/list/dates/trade", {"symbol": symbol, "format": "json"})
        data = json.loads(text)
        return [row["date"] for row in data.get("response", [])]

    def get_symbols(self) -> list[str]:
        """All available option root symbols."""
        import json

        text = self._get("/option/list/symbols", {"format": "json"})
        data = json.loads(text)
        return [row["symbol"] for row in data.get("response", [])]


# ── Module-level singleton ────────────────────────────────

_client: ThetaDataClient | None = None


def get_thetadata_client() -> ThetaDataClient:
    """Return a ThetaDataClient singleton."""
    global _client
    if _client is None:
        _client = ThetaDataClient()
    return _client
