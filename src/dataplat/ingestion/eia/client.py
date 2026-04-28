"""EIA API v2 client — rate-limited, with retry logic.

EIA rate limit: ~5,000 requests/hour. We use 0.3s delay between calls.
API docs: https://www.eia.gov/opendata/documentation.php

All series return JSON with {period, value} observations.
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings

logger = logging.getLogger(__name__)

# Suppress noisy httpx request logging
logging.getLogger("httpx").setLevel(logging.WARNING)

EIA_BASE = "https://api.eia.gov/v2"

# Delay between requests — generous given 5k/hour limit
_RATE_LIMIT_DELAY = 0.3


def fetch_series(
    client: httpx.Client,
    route: str,
    series_id: str,
    frequency: str = "daily",
    start: str = "1900-01-01",
    end: str | None = None,
    facets: dict[str, str] | None = None,
) -> list[tuple[str, float]]:
    """Fetch all observations for a single EIA series.

    Args:
        client: httpx client instance.
        route: EIA API route, e.g. "petroleum/pri/spt/data".
        series_id: The series identifier, e.g. "RWTC" for WTI spot.
            For endpoints that use the `series` facet.
        frequency: "daily", "weekly", or "monthly".
        start: Observation start date (YYYY-MM-DD or YYYY-MM).
        end: Observation end date (YYYY-MM-DD or YYYY-MM). None = latest.
        facets: Additional facet filters, e.g. {"productId": "57", "countryRegionId": "SAU"}.
            Used for endpoints like international/ that don't use the `series` facet.

    Returns:
        List of (date_str, value) tuples, sorted ascending.
        Monthly periods (YYYY-MM) are normalized to YYYY-MM-01.
    """
    # Truncate start to match frequency format
    effective_start = start[:7] if frequency == "monthly" else start

    params: dict[str, str] = {
        "api_key": settings.eia_api_key,
        "frequency": frequency,
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "start": effective_start,
        "length": "5000",
    }
    if series_id:
        params["facets[series][]"] = series_id
    if facets:
        for facet_key, facet_val in facets.items():
            params[f"facets[{facet_key}][]"] = facet_val
    if end:
        params["end"] = end[:7] if frequency == "monthly" else end

    url = f"{EIA_BASE}/{route}"
    label = series_id or ",".join(f"{k}={v}" for k, v in (facets or {}).items())
    all_rows: list[tuple[str, float]] = []
    offset = 0
    page = 0

    while True:
        params["offset"] = str(offset)
        page += 1

        for attempt in range(3):
            try:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                break
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(
                        "  ⚠ %s retry %d/3 (%s)",
                        label, attempt + 1, type(exc).__name__,
                    )
                    time.sleep(wait)
                else:
                    raise

        body = resp.json()
        response_data = body.get("response", {})
        rows_data = response_data.get("data", [])

        if not rows_data:
            break

        for row in rows_data:
            period = row.get("period", "")
            val = row.get("value")
            if val is None or period == "":
                continue
            try:
                # Normalize YYYY-MM to YYYY-MM-01 for monthly data
                if len(period) == 7 and "-" in period:
                    period = f"{period}-01"
                all_rows.append((period, float(val)))
            except (ValueError, TypeError):
                continue

        total = int(response_data.get("total", 0))
        offset += len(rows_data)

        if page > 1:
            logger.debug("  %s: page %d — %d/%d rows", label, page, offset, total)

        if offset >= total:
            break

        time.sleep(_RATE_LIMIT_DELAY)

    return all_rows


def fetch_and_pivot(
    client: httpx.Client,
    series_map: dict[str, tuple[str, str, str] | tuple[str, str, str, dict[str, str]]],
    start: str = "1900-01-01",
    end: str | None = None,
) -> pl.DataFrame:
    """Fetch multiple EIA series and full-outer-join into one wide DataFrame.

    Args:
        client: httpx client instance.
        series_map: {column_name: (route, series_id, frequency)} or
                    {column_name: (route, series_id, frequency, facets_dict)}.
        start: Observation start date (YYYY-MM-DD).
        end: Observation end date (YYYY-MM-DD). None = latest.

    Returns:
        Wide DataFrame with 'date' + one column per series, sorted by date.
    """
    frames: list[pl.DataFrame] = []

    total_series = len(series_map)
    for idx, (col_name, spec) in enumerate(series_map.items(), 1):
        if len(spec) == 4:
            route, series_id, frequency, facets = spec  # type: ignore[misc]
        else:
            route, series_id, frequency = spec  # type: ignore[misc]
            facets = None

        label = series_id or ",".join(f"{k}={v}" for k, v in (facets or {}).items())
        logger.info("  [%d/%d] %s ← %s/%s (%s)", idx, total_series, col_name, route, label, frequency)

        obs = fetch_series(client, route, series_id, frequency, start, end, facets=facets)

        if not obs:
            logger.warning("  [%d/%d] %s: no observations", idx, total_series, col_name)
        else:
            df = pl.DataFrame(
                {"date": [r[0] for r in obs], col_name: [r[1] for r in obs]},
            ).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
            frames.append(df)
            logger.info("  [%d/%d] %s: %s obs (%s – %s)",
                        idx, total_series, col_name, f"{len(obs):,}", obs[0][0], obs[-1][0])

        time.sleep(_RATE_LIMIT_DELAY)

    if not frames:
        return pl.DataFrame()

    # Full outer join all series on date
    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="full", coalesce=True)

    # Ensure all expected columns exist
    for col in series_map:
        if col not in result.columns:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias(col))

    cols = ["date"] + list(series_map.keys())
    return result.select(cols).sort("date")
