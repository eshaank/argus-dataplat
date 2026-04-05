"""Declarative registry: FRED series → ClickHouse tables.

To add a new series, add one entry to the appropriate table's `series` dict.
No other code changes needed — the backfill runner reads this registry.

Each table config:
    table  — ClickHouse table name
    start  — earliest observation date to fetch
    series — {FRED_series_id: clickhouse_column_name}
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableConfig:
    """Configuration for one ClickHouse table backed by FRED series."""
    table: str
    start: str
    series: dict[str, str] = field(default_factory=dict)


# ── Existing tables ─────────────────────────────────────────────────

TREASURY_YIELDS = TableConfig(
    table="treasury_yields",
    start="1962-01-01",
    series={
        "DGS1MO":  "yield_1_month",
        "DGS3MO":  "yield_3_month",
        "DGS1":    "yield_1_year",
        "DGS2":    "yield_2_year",
        "DGS5":    "yield_5_year",
        "DGS10":   "yield_10_year",
        "DGS30":   "yield_30_year",
    },
)

INFLATION = TableConfig(
    table="inflation",
    start="1947-01-01",
    series={
        "CPIAUCSL": "cpi",
        "CPILFESL": "cpi_core",
        "PCEPI":    "pce",
        "PCEPILFE": "pce_core",
        "PCE":      "pce_spending",
    },
)

INFLATION_EXPECTATIONS = TableConfig(
    table="inflation_expectations",
    start="1982-01-01",
    series={
        "T5YIE":      "market_5_year",
        "T10YIE":     "market_10_year",
        "T5YIFR":     "forward_years_5_to_10",
        "EXPINF1YR":  "model_1_year",
        "EXPINF5YR":  "model_5_year",
        "EXPINF10YR": "model_10_year",
        "EXPINF30YR": "model_30_year",
    },
)

LABOR_MARKET = TableConfig(
    table="labor_market",
    start="1948-01-01",
    series={
        "UNRATE":        "unemployment_rate",
        "CIVPART":       "labor_force_participation_rate",
        "CES0500000003": "avg_hourly_earnings",
        "JTSJOL":        "job_openings",
    },
)

# ── New tables ──────────────────────────────────────────────────────

RATES = TableConfig(
    table="rates",
    start="1954-01-01",
    series={
        "DFF":           "fed_funds_rate",
        "SOFR":          "sofr",
        "DBAA":          "baa_yield",
        "DAAA":          "aaa_yield",
        "BAMLH0A0HYM2":  "hy_oas",
        "BAMLC0A0CM":    "ig_oas",
        "DFII10":        "tips_10y",
        "DFII5":         "tips_5y",
        "DCPF3M":        "commercial_paper_3m",
        "TB3MS":         "tbill_3m",
    },
)

MACRO_DAILY = TableConfig(
    table="macro_daily",
    start="1976-01-01",
    series={
        "VIXCLS":            "vix",
        "DTWEXBGS":          "usd_index",
        "T10Y2Y":            "yield_curve_10y2y",
        "T10Y3M":            "yield_curve_10y3m",
        "DCOILWTICO":        "wti_crude",
    },
)

MACRO_WEEKLY = TableConfig(
    table="macro_weekly",
    start="1971-01-01",
    series={
        "STLFSI2":       "financial_stress",
        "NFCI":          "financial_conditions",
        "MORTGAGE30US":  "mortgage_rate_30y",
        "ICSA":          "initial_claims",
        "CCSA":          "continued_claims",
    },
)

MACRO_MONTHLY = TableConfig(
    table="macro_monthly",
    start="1919-01-01",
    series={
        "M2SL":         "m2_money_supply",
        "UMCSENT":      "consumer_sentiment",
        "RSAFS":        "retail_sales",
        "PSAVERT":      "personal_savings_rate",
        "RPI":          "real_personal_income",
        "HOUST":        "housing_starts",
        "CSUSHPINSA":   "case_shiller",
        "INDPRO":       "industrial_production",
        "TCU":          "capacity_utilization",
        "USSLIND":      "leading_index",
        "PAYEMS":       "nonfarm_payrolls",
        "TOTALSA":      "auto_sales",
        "BUSLOANS":     "bank_lending",
        "GDPC1":        "real_gdp",
        "USREC":        "recession",
        "SAHMREALTIME": "sahm_rule",
    },
)

# ── All tables in backfill order ────────────────────────────────────

ALL_TABLES: list[TableConfig] = [
    TREASURY_YIELDS,
    INFLATION,
    INFLATION_EXPECTATIONS,
    LABOR_MARKET,
    RATES,
    MACRO_DAILY,
    MACRO_WEEKLY,
    MACRO_MONTHLY,
]

# Lookup by table name for --table filtering
TABLE_BY_NAME: dict[str, TableConfig] = {t.table: t for t in ALL_TABLES}
