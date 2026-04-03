#!/usr/bin/env bash
# Migrate local ClickHouse data to ClickHouse Cloud.
#
# Usage:
#   1. Set your cloud credentials below
#   2. Run: bash scripts/migrate_to_cloud.sh
#
# This exports base tables from local (skips materialized views — they auto-rebuild).
# Total data: ~4.5 GB compressed, takes ~5-10 minutes depending on upload speed.

set -euo pipefail

# ── Cloud credentials (fill these in) ──
CLOUD_HOST="${CLOUD_HOST:?Set CLOUD_HOST}"
CLOUD_PORT="${CLOUD_PORT:-8443}"
CLOUD_USER="${CLOUD_USER:-default}"
CLOUD_PASS="${CLOUD_PASS:?Set CLOUD_PASS}"

# ── Local credentials ──
LOCAL_HOST="localhost"
LOCAL_PORT="8123"
LOCAL_USER="default"
LOCAL_PASS="local_dev_clickhouse"
LOCAL_DB="dataplat"

EXPORT_DIR="/tmp/dataplat_export"
mkdir -p "$EXPORT_DIR"

local_query() {
    curl -s "http://${LOCAL_HOST}:${LOCAL_PORT}/?database=${LOCAL_DB}" \
        --user "${LOCAL_USER}:${LOCAL_PASS}" -d "$1"
}

cloud_query() {
    curl -s "https://${CLOUD_HOST}:${CLOUD_PORT}/?database=${LOCAL_DB}" \
        --user "${CLOUD_USER}:${CLOUD_PASS}" -d "$1"
}

cloud_insert() {
    local table="$1"
    local file="$2"
    curl -s "https://${CLOUD_HOST}:${CLOUD_PORT}/?database=${LOCAL_DB}&query=INSERT+INTO+${table}+FORMAT+Native" \
        --user "${CLOUD_USER}:${CLOUD_PASS}" \
        --data-binary "@${file}"
}

echo "=== Step 1: Create database + schema on cloud ==="
cloud_query "CREATE DATABASE IF NOT EXISTS ${LOCAL_DB}"
echo "Database created"

echo ""
echo "=== Step 2: Run migrations on cloud ==="
# Use the Python migration runner pointed at cloud
echo "Run: CLICKHOUSE_HOST=$CLOUD_HOST CLICKHOUSE_PORT=$CLOUD_PORT CLICKHOUSE_PASSWORD=\$CLOUD_PASS CLICKHOUSE_SECURE=true just migrate"
echo "(do this manually, then press Enter to continue)"
read -r

# Base tables to export (skip MVs — they auto-rebuild from ohlcv inserts)
TABLES=(
    "ohlcv"
    "universe"
    "financials"
    "dividends"
    "stock_splits"
    "treasury_yields"
    "inflation"
    "inflation_expectations"
    "labor_market"
)

echo ""
echo "=== Step 3: Export from local → import to cloud ==="
for table in "${TABLES[@]}"; do
    echo -n "  ${table}: exporting..."
    local_query "SELECT * FROM ${table} FORMAT Native" > "${EXPORT_DIR}/${table}.native"
    size=$(ls -lh "${EXPORT_DIR}/${table}.native" | awk '{print $5}')
    echo -n " ${size}... uploading..."
    cloud_insert "${table}" "${EXPORT_DIR}/${table}.native"
    echo " ✓"
done

echo ""
echo "=== Step 4: Verify ==="
cloud_query "
SELECT name, formatReadableQuantity(total_rows) AS rows, formatReadableSize(total_bytes) AS size
FROM system.tables WHERE database = '${LOCAL_DB}' AND total_rows > 0 AND name NOT LIKE '.inner%'
ORDER BY total_bytes DESC FORMAT PrettyCompact"

echo ""
echo "=== Done! ==="
echo "Update your .env:"
echo "  CLICKHOUSE_HOST=${CLOUD_HOST}"
echo "  CLICKHOUSE_PORT=${CLOUD_PORT}"
echo "  CLICKHOUSE_PASSWORD=<your-cloud-password>"
echo "  CLICKHOUSE_SECURE=true"
echo ""
echo "Then: just ch-ping"

# Cleanup
rm -rf "$EXPORT_DIR"
