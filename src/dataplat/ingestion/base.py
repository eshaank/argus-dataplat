"""Abstract ingestion pipeline interface.

Every pipeline follows Extract → Transform → Load.  The interface is
designed so Kafka can be inserted between Extract and Transform later
without rewriting the Transform or Load layers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import polars as pl

logger = logging.getLogger(__name__)


class IngestPipeline(ABC):
    """Base class for all ingestion pipelines."""

    @abstractmethod
    def extract(self, **params: object) -> list[dict]:
        """Fetch raw data from a source API.

        Returns a list of raw record dicts (one per bar / row).
        """
        ...

    @abstractmethod
    def transform(self, raw: list[dict]) -> pl.DataFrame:
        """Clean, validate, and reshape raw records into the target schema.

        Returns a Polars DataFrame ready for ClickHouse insertion.
        """
        ...

    @abstractmethod
    def load(self, df: pl.DataFrame) -> int:
        """Bulk-insert a DataFrame into ClickHouse.

        Returns the number of rows inserted.
        """
        ...

    def run(self, **params: object) -> int:
        """Execute the full ETL pipeline.

        Subclasses can override this to insert Kafka between stages.
        """
        raw = self.extract(**params)
        if not raw:
            logger.warning("extract() returned no data — skipping transform/load")
            return 0
        df = self.transform(raw)
        if df.is_empty():
            logger.warning("transform() produced empty DataFrame — skipping load")
            return 0
        return self.load(df)
