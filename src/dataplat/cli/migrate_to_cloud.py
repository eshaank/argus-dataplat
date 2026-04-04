"""CLI entry point: python -m dataplat.cli.migrate_to_cloud

Migrates data from local ClickHouse → cloud ClickHouse using
remoteSecure() — ClickHouse handles the transfer directly,
no data passes through Python.

Chunks ohlcv by year-month to keep memory bounded.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import clickhouse_connect
from clickhouse_connect.driver import Client

from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

# ── Local defaults ──────────────────────────────────────────
LOCAL_HOST = "localhost"
LOCAL_PORT = 8123
LOCAL_USER = "default"
LOCAL_PASS = "local_dev_clickhouse"
LOCAL_DB = "dataplat"

# Small tables — transferred in one shot
SMALL_TABLES = [
    "universe",
    "financials",
    "dividends",
    "stock_splits",
    "treasury_yields",
    "inflation",
    "inflation_expectations",
    "labor_market",
]

_MAX_RETRIES = 3


def _get_local_client() -> Client:
    return clickhouse_connect.get_client(
        host=LOCAL_HOST,
        port=LOCAL_PORT,
        username=LOCAL_USER,
        password=LOCAL_PASS,
        database=LOCAL_DB,
    )


def _get_cloud_settings() -> dict:
    """Return cloud connection details from .env."""
    from dataplat.config import settings

    return {
        "host": settings.clickhouse_host,
        "port": settings.clickhouse_port,
        "user": settings.clickhouse_user,
        "password": settings.clickhouse_password,
        "database": settings.clickhouse_database,
    }


# remoteSecure() uses ClickHouse native TLS protocol, not HTTP.
# ClickHouse Cloud exposes native TLS on port 9440.
_CLOUD_NATIVE_PORT = 9440


def _remote_secure_expr(cloud: dict, table: str) -> str:
    """Build a remoteSecure() function call for INSERT INTO FUNCTION."""
    return (
        f"remoteSecure("
        f"'{cloud['host']}:{_CLOUD_NATIVE_PORT}', "
        f"'{cloud['database']}.{table}', "
        f"'{cloud['user']}', "
        f"'{cloud['password']}')"
    )


def _transfer_table(
    local: Client, cloud: dict, table: str, where: str = "",
) -> int:
    """Transfer a table via remoteSecure(). Returns row count."""
    query = f"SELECT * FROM {table}"
    if where:
        query += f" WHERE {where}"

    remote = _remote_secure_expr(cloud, table)
    sql = f"INSERT INTO FUNCTION {remote} {query}"

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            local.command(sql)
            # Get the count of what we transferred
            count_q = f"SELECT count() FROM {table}"
            if where:
                count_q += f" WHERE {where}"
            rows = int(local.query(count_q).result_rows[0][0])
            return rows
        except Exception as exc:
            last_exc = exc
            delay = 2 ** (attempt + 1)
            logger.warning(
                "%s: attempt %d/%d failed — %s — retrying in %ds",
                table, attempt + 1, _MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate local ClickHouse → cloud ClickHouse via remoteSecure()"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=3,
        help="Parallel remoteSecure() transfers (default: 3)",
    )
    parser.add_argument(
        "--tables",
        type=str,
        default=None,
        help="Comma-separated list of tables to migrate (default: all). "
        "e.g. --tables ohlcv  or  --tables financials,universe",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("clickhouse_connect").setLevel(logging.WARNING)

    all_tables = SMALL_TABLES + ["ohlcv"]
    if args.tables:
        requested = [t.strip().lower() for t in args.tables.split(",") if t.strip()]
        unknown = [t for t in requested if t not in all_tables]
        if unknown:
            logger.error(
                "Unknown tables: %s. Available: %s",
                ", ".join(unknown), ", ".join(all_tables),
            )
            sys.exit(1)
        tables_to_migrate = requested
    else:
        tables_to_migrate = all_tables

    start = time.monotonic()

    # ── Step 1: Ensure cloud schema ──
    print("=== Step 1: Ensure cloud schema ===")
    try:
        ensure_schema()
    except Exception as exc:
        logger.error("Failed to run migrations on cloud: %s", exc)
        sys.exit(1)
    print("")

    local = _get_local_client()
    cloud = _get_cloud_settings()

    # ── Step 2: Small tables ──
    small = [t for t in tables_to_migrate if t in SMALL_TABLES]
    if small:
        print("=== Step 2: Migrate small tables ===")
        for table in small:
            count = int(local.query(f"SELECT count() FROM {table}").result_rows[0][0])
            if count == 0:
                print(f"  {table}: empty, skipped")
                continue
            try:
                t0 = time.monotonic()
                rows = _transfer_table(local, cloud, table)
                elapsed = time.monotonic() - t0
                print(f"  {table}: {rows:,} rows ✓ ({elapsed:.1f}s)")
            except Exception as exc:
                print(f"  {table}: FAILED — {exc}")
        print("")

    # ── Step 3: ohlcv by month ──
    if "ohlcv" in tables_to_migrate:
        print("=== Step 3: Migrate ohlcv (by month via remoteSecure) ===")
        result = local.query(
            "SELECT DISTINCT toYYYYMM(timestamp) AS ym, "
            "count() AS cnt "
            "FROM ohlcv GROUP BY ym ORDER BY ym"
        )
        months = [(int(row[0]), int(row[1])) for row in result.result_rows]

        if not months:
            print("  ohlcv: empty, skipping")
        else:
            total_months = len(months)
            completed = 0
            total_rows = 0
            lock = __import__("threading").Lock()

            def _do_month(ym: int, count: int) -> None:
                nonlocal completed, total_rows
                # Each thread gets its own local client
                thread_local = _get_local_client()
                logger.info("ohlcv/%d: %s rows — transferring...", ym, f"{count:,}")
                t0 = time.monotonic()
                try:
                    rows = _transfer_table(
                        thread_local, cloud, "ohlcv",
                        f"toYYYYMM(timestamp) = {ym}",
                    )
                    elapsed = time.monotonic() - t0
                    rate = rows / max(elapsed, 0.1)
                    with lock:
                        completed += 1
                        total_rows += rows
                    logger.info(
                        "[%d/%d] ohlcv/%d: %s rows ✓ (%.0fs, %.0f rows/s)",
                        completed, total_months, ym, f"{rows:,}", elapsed, rate,
                    )
                except Exception as exc:
                    with lock:
                        completed += 1
                    logger.error("[%d/%d] ohlcv/%d: FAILED — %s", completed, total_months, ym, exc)

            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                futures = [pool.submit(_do_month, ym, count) for ym, count in months]
                for f in as_completed(futures):
                    f.result()  # propagate exceptions

            print(f"  ohlcv total: {total_rows:,} rows")
        print("")

    # ── Step 4: Verify ──
    print("=== Step 4: Verify cloud ===")
    try:
        verify_remote = _remote_secure_expr(cloud, "system.tables")
        # Can't query system tables via remoteSecure easily, use a direct cloud client
        cloud_client = clickhouse_connect.get_client(
            host=cloud["host"],
            port=cloud["port"],
            username=cloud["user"],
            password=cloud["password"],
            database=cloud["database"],
            secure=True,
        )
        result = cloud_client.query(
            "SELECT name, formatReadableQuantity(total_rows) AS rows, "
            "formatReadableSize(total_bytes) AS size "
            "FROM system.tables "
            f"WHERE database = '{cloud['database']}' "
            "AND total_rows > 0 AND name NOT LIKE '.inner%' "
            "ORDER BY total_bytes DESC"
        )
        for row in result.result_rows:
            print(f"  {row[0]}: {row[1]} ({row[2]})")
    except Exception as exc:
        logger.error("Verify failed: %s", exc)

    elapsed = time.monotonic() - start
    print(f"\n=== Done in {elapsed / 60:.1f} minutes ===")


if __name__ == "__main__":
    main()
