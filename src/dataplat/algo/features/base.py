"""Base interface for feature modules.

Every feature module:
1. Queries ClickHouse for raw data around a target date
2. Computes one or more named features
3. Returns a FeatureRow dict with feature names → float values
4. Reports which features are stale (forward-filled from old data)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from clickhouse_connect.driver import Client

logger = logging.getLogger(__name__)


@dataclass
class FeatureRow:
    """Output of a single feature module for one date.

    features: {feature_name: value} — NaN for missing
    stale:    feature names that used forward-filled data beyond the freshness threshold
    """

    features: dict[str, float] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)


class FeatureModule(ABC):
    """Abstract base for a group of related features."""

    # Subclasses must set this — used for logging and registry
    name: str = ""

    # Maximum days a value can be forward-filled before being flagged stale.
    # Override per-module: macro (weekly) can be staler than options (daily).
    staleness_threshold_days: int = 1

    def __init__(self, client: Client) -> None:
        self.client = client

    @abstractmethod
    def compute(self, target_date: date) -> FeatureRow:
        """Compute all features for the given date.

        Must handle missing data gracefully — return NaN for missing features,
        add feature name to FeatureRow.stale if forward-filled beyond threshold.
        """
        ...

    @property
    def feature_names(self) -> list[str]:
        """Return the list of feature names this module produces.

        Used by the pipeline to validate output completeness.
        Default implementation calls compute() — override for efficiency.
        """
        raise NotImplementedError(f"{self.name} must implement feature_names")

    def _query(self, sql: str, params: dict | None = None) -> list[dict]:
        """Run a ClickHouse query and return rows as list of dicts."""
        result = self.client.query(sql, parameters=params or {})
        columns = result.column_names
        return [dict(zip(columns, row, strict=True)) for row in result.result_rows]

    def _query_single(self, sql: str, params: dict | None = None) -> dict | None:
        """Run a query expecting 0 or 1 rows. Returns dict or None."""
        rows = self._query(sql, params)
        return rows[0] if rows else None
