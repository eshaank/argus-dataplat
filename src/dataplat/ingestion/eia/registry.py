"""Declarative registry: EIA series → ClickHouse tables.

Same pattern as the FRED registry. Each table config maps
ClickHouse column names to EIA API specs.

Series values are either:
    (route, series_id, frequency)                — for endpoints using the `series` facet
    (route, "",        frequency, facets_dict)    — for endpoints using other facets (e.g. international)

To add a new series, add one entry to the appropriate table's `series` dict.
No other code changes needed — the backfill runner reads this registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Type alias for series spec
SeriesSpec = tuple[str, str, str] | tuple[str, str, str, dict[str, str]]


@dataclass(frozen=True)
class EIATableConfig:
    """Configuration for one ClickHouse table backed by EIA series."""

    table: str
    start: str
    update_frequency: str = "daily"  # dominant frequency for the table
    series: dict[str, SeriesSpec] = field(default_factory=dict)


# ── Helpers ─────────────────────────────────────────────────────────

def _intl_production(country: str) -> tuple[str, str, str, dict[str, str]]:
    """Build an international crude oil production spec.

    Uses the EIA v2 international endpoint with facets:
    productId=57 (crude oil), activityId=1 (production),
    unit=TBPD (thousand bbl/day), countryRegionId=<ISO or group>.
    """
    return (
        "international/data", "", "monthly",
        {"productId": "57", "activityId": "1", "unit": "TBPD", "countryRegionId": country},
    )


# ── Daily energy prices → commodity_prices table ────────────────────

COMMODITY_PRICES_EIA = EIATableConfig(
    table="commodity_prices",
    start="1986-01-01",
    series={
        "wti_crude":    ("petroleum/pri/spt/data", "RWTC",  "daily"),
        "brent_crude":  ("petroleum/pri/spt/data", "RBRTE", "daily"),
        "natural_gas":  ("natural-gas/pri/fut/data", "RNGWHHD", "daily"),
        "gasoline":     ("petroleum/pri/gnd/data", "EMM_EPMR_PTE_NUS_DPG", "weekly"),
        "heating_oil":  ("petroleum/pri/spt/data", "EER_EPJK_PF4_RGC_DPG", "daily"),
    },
)

# ── Weekly Petroleum Status Report ──────────────────────────────────

EIA_PETROLEUM_WEEKLY = EIATableConfig(
    table="eia_petroleum_weekly",
    start="1982-01-01",
    update_frequency="weekly",
    series={
        # Supply (thousand bbl/day)
        "crude_production":    ("petroleum/sum/sndw/data", "WCRFPUS2", "weekly"),
        "crude_imports":       ("petroleum/sum/sndw/data", "WCRIMUS2", "weekly"),
        "crude_exports":       ("petroleum/sum/sndw/data", "WCREXUS2", "weekly"),
        # Stocks (thousand barrels)
        "crude_stocks":        ("petroleum/sum/sndw/data", "WCESTUS1", "weekly"),
        "spr_stocks":          ("petroleum/sum/sndw/data", "WCSSTUS1", "weekly"),
        "gasoline_stocks":     ("petroleum/sum/sndw/data", "WGTSTUS1", "weekly"),
        "distillate_stocks":   ("petroleum/sum/sndw/data", "WDISTUS1", "weekly"),
        # Demand / product supplied (thousand bbl/day)
        "product_supplied":    ("petroleum/sum/sndw/data", "WRPUPUS2", "weekly"),
        "gasoline_supplied":   ("petroleum/sum/sndw/data", "WGFUPUS2", "weekly"),
        "distillate_supplied": ("petroleum/sum/sndw/data", "WDIUPUS2", "weekly"),
        "jet_fuel_supplied":   ("petroleum/sum/sndw/data", "WKJUPUS2", "weekly"),
        # Refining
        "refinery_utilization": ("petroleum/sum/sndw/data", "WPULEUS3", "weekly"),
        "refinery_inputs":     ("petroleum/sum/sndw/data", "WGIRIUS2", "weekly"),
    },
)

# ── Monthly international petroleum ─────────────────────────────────
# International endpoint uses facets (productId, activityId, unit, countryRegionId).
# US production + imports use petroleum/* routes with the `series` facet.

EIA_PETROLEUM_MONTHLY = EIATableConfig(
    table="eia_petroleum_monthly",
    start="1973-01-01",
    update_frequency="monthly",
    series={
        # Global production (thousand bbl/day) — international endpoint
        "opec_production":    _intl_production("OPEC"),
        "us_production":      ("petroleum/crd/crpdn/data", "MCRFPUS2", "monthly"),
        "russia_production":  _intl_production("RUS"),
        "saudi_production":   _intl_production("SAU"),
        "iran_production":    _intl_production("IRN"),
        "iraq_production":    _intl_production("IRQ"),
        "uae_production":     _intl_production("ARE"),
        "world_production":   _intl_production("WORL"),
        # US crude imports by origin (thousand bbl/day — series suffix 2)
        "imports_persian_gulf": ("petroleum/move/impcus/data", "MCRIMUSPG2", "monthly"),
        "imports_canada":       ("petroleum/move/impcus/data", "MCRIMUSCA2", "monthly"),
        "imports_mexico":       ("petroleum/move/impcus/data", "MCRIMUSMX2", "monthly"),
        "imports_total":        ("petroleum/move/impcus/data", "MCRIMUS2",   "monthly"),
    },
)

# ── All EIA tables in backfill order ────────────────────────────────

ALL_TABLES: list[EIATableConfig] = [
    COMMODITY_PRICES_EIA,
    EIA_PETROLEUM_WEEKLY,
    EIA_PETROLEUM_MONTHLY,
]

# Lookup by table name for --table filtering
TABLE_BY_NAME: dict[str, EIATableConfig] = {t.table: t for t in ALL_TABLES}
