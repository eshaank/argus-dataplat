# Argus DataPlat — Task Runner
# Install just: https://github.com/casey/just

set dotenv-load

# Start ClickHouse
up:
    docker compose up -d

# Stop ClickHouse
down:
    docker compose down

# Nuke ClickHouse data and start fresh
reset:
    docker compose down -v
    docker compose up -d
    @echo "Waiting for ClickHouse to start..."
    @sleep 3
    just migrate

# Run schema migrations
migrate:
    uv run python -m dataplat.cli.migrate

# Backfill OHLCV data
# Examples:
#   just backfill --source polygon --tickers AAPL,MSFT --months 48
#   just backfill --source polygon --universe spy --months 48
#   just backfill --source polygon --universe qqq
#   just backfill --source polygon --universe all --concurrency 20
#   just backfill --source schwab --universe spy --years 20
backfill *ARGS:
    uv run python -m dataplat.cli.backfill {{ARGS}}

# Backfill daily OHLCV via Polygon grouped daily endpoint → ohlcv_daily table
# Examples:
#   just backfill-daily --universe nyse --months 3
#   just backfill-daily --tickers AAPL,MSFT --months 1
#   just backfill-daily --all-tickers --months 1
backfill-daily *ARGS:
    uv run python -m dataplat.cli.backfill --source polygon-daily {{ARGS}}

# Fetch all active US equity tickers from Polygon → universes/all.txt
fetch-universe:
    uv run python src/dataplat/ingestion/polygon/universes/fetch_all.py

# Backfill dividends, splits, universe details from Polygon
# Examples:
#   just backfill-fundamentals --universe spy
#   just backfill-fundamentals --universe all
#   just backfill-fundamentals --tickers AAPL,MSFT
backfill-fundamentals *ARGS:
    uv run python -m dataplat.cli.backfill_fundamentals {{ARGS}}

# Backfill economic indicators from FRED (treasury yields, inflation, rates, macro)
# Examples:
#   just backfill-economy                     # All 9 tables (~47 FRED series)
#   just backfill-economy --table rates        # Single table
#   just backfill-economy --table macro_daily --table macro_weekly
#   just backfill-economy --list               # Show available tables + series
backfill-economy *ARGS:
    uv run python -m dataplat.cli.backfill_economy {{ARGS}}

# Backfill commodity prices + EIA petroleum data
# Examples:
#   just backfill-commodities --all                         # All sources, full history
#   just backfill-commodities --source eia                  # EIA only
#   just backfill-commodities --source yfinance             # Yahoo Finance futures only
#   just backfill-commodities --source fred                 # FRED gold/silver only
#   just backfill-commodities --all --start 2025-04-01      # Pull recent from all sources
#   just backfill-commodities --table eia_petroleum_weekly   # Single EIA table
#   just backfill-commodities --list                        # Show available series
backfill-commodities *ARGS:
    uv run python -m dataplat.cli.backfill_commodities {{ARGS}}

# Commodity futures intraday data (yfinance)
# 15m: last 60 days, 1h/4h: last 730 days
commodities-15m:
    uv run python -c "from dataplat.ingestion.yfinance.commodities import run_yfinance_commodities; run_yfinance_commodities(interval='15m')"

commodities-1h:
    uv run python -c "from dataplat.ingestion.yfinance.commodities import run_yfinance_commodities; run_yfinance_commodities(interval='1h')"

commodities-4h:
    uv run python -c "from dataplat.ingestion.yfinance.commodities import run_yfinance_commodities; run_yfinance_commodities(interval='4h')"

commodities-daily:
    uv run python -c "from dataplat.ingestion.yfinance.commodities import run_yfinance_commodities; run_yfinance_commodities()"

# Migrate local ClickHouse → cloud ClickHouse
# Examples:
#   just migrate-to-cloud
#   just migrate-to-cloud --parallel 10
#   just migrate-to-cloud --skip-ohlcv
migrate-to-cloud *ARGS:
    uv run python -m dataplat.cli.migrate_to_cloud {{ARGS}}

# Backfill options data from ThetaData v3
# Requires: just thetadata up
# Examples:
#   just backfill-options --tickers AAPL,MSFT
#   just backfill-options --universe sp100
#   just backfill-options --universe sp100 --resume
#   just backfill-options --universe sp100 --dry-run
backfill-options *ARGS:
    uv run python -m dataplat.cli.backfill_options {{ARGS}}

# Backfill tick-level option trades from ThetaData v3
# Requires: just thetadata up
# Examples:
#   just backfill-option-trades --tickers ARM
#   just backfill-option-trades --tickers ARM,SPY,QQQ --years 2
#   just backfill-option-trades --tickers SPY --years 2 --resume
#   just backfill-option-trades --dry-run --tickers SPY,QQQ
backfill-option-trades *ARGS:
    uv run python -m dataplat.cli.backfill_option_trades {{ARGS}}

# Backfill from SEC EDGAR (financials, filings, insider trades, institutional holders)
# Examples:
#   just backfill-edgar --all --universe all
#   just backfill-edgar --financials --tickers NBIS,ARM
#   just backfill-edgar --filings --universe spy
#   just backfill-edgar --insider --universe spy --insider-years 3
#   just backfill-edgar --institutional --universe spy
#   just backfill-edgar --all --gaps-only
#   just backfill-edgar --all --universe all --dry-run
backfill-edgar *ARGS:
    uv run python -m dataplat.cli.backfill_edgar {{ARGS}}

# Zweig Breadth Thrust detector
# Examples:
#   just zbt
#   just zbt --months 6
zbt *ARGS:
    uv run python -m dataplat.cli.zbt {{ARGS}}

# ── Algo: Feature Engineering ──────────────────────────────────────

# Compute daily algo features → ClickHouse
# Examples:
#   just compute-features --start 2023-01-01 --end 2024-12-31
#   just compute-features --today
#   just compute-features --today --dry-run
#   just compute-features --list
compute-features *ARGS:
    uv run python -m dataplat.cli.compute_features {{ARGS}}

# Run tests
test:
    uv run pytest tests/ -v

# Lint and format check
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Auto-fix lint issues
fix:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

# ClickHouse interactive shell
# Uses .env credentials — works for both local and cloud
ch-shell:
    #!/usr/bin/env bash
    if [[ "$CLICKHOUSE_HOST" == *".clickhouse.cloud"* || "${CLICKHOUSE_PORT:-8123}" == "8443" ]]; then
        PORT=9440
        SECURE="--secure"
    else
        PORT=9000
        SECURE=""
    fi
    clickhouse client \
        --host "${CLICKHOUSE_HOST:-localhost}" \
        --port "$PORT" \
        --user "${CLICKHOUSE_USER:-default}" \
        --password "${CLICKHOUSE_PASSWORD}" \
        --database "${CLICKHOUSE_DATABASE:-dataplat}" \
        $SECURE

# Run a SQL file against ClickHouse
# Native protocol: local=9000, cloud=9440. HTTP ports (8123/8443) don't work with clickhouse client.
ch-query FILE:
    #!/usr/bin/env bash
    if [[ "$CLICKHOUSE_HOST" == *".clickhouse.cloud"* || "${CLICKHOUSE_PORT:-8123}" == "8443" ]]; then
        PORT=9440
        SECURE="--secure"
    else
        PORT=9000
        SECURE=""
    fi
    clickhouse client \
        --host "${CLICKHOUSE_HOST:-localhost}" \
        --port "$PORT" \
        --user "${CLICKHOUSE_USER:-default}" \
        --password "${CLICKHOUSE_PASSWORD}" \
        --database "${CLICKHOUSE_DATABASE:-dataplat}" \
        $SECURE \
        --queries-file "{{FILE}}"

# Check ClickHouse is healthy
ch-ping:
    #!/usr/bin/env bash
    PROTO="http"
    [[ "${CLICKHOUSE_SECURE:-false}" == "true" || "$CLICKHOUSE_HOST" == *".clickhouse.cloud"* || "${CLICKHOUSE_PORT:-8123}" == "8443" ]] && PROTO="https"
    curl -sS "${PROTO}://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8123}/ping" \
        && echo " ClickHouse is up" || echo " ClickHouse is down"

# Start ThetaData Terminal v3 (requires THETADATA_USERNAME and THETADATA_PASSWORD in .env)
# Serves REST API + MCP on port 25503
thetadata *CMD='up':
    #!/usr/bin/env bash
    case "{{CMD}}" in
        up)
            echo "Starting ThetaTerminal v3 on port 25503..."
            echo -e "${THETADATA_USERNAME}\n${THETADATA_PASSWORD}" > creds.txt
            java -jar ThetaTerminalv3.jar
            ;;
        down)
            pkill -f ThetaTerminalv3.jar && echo "ThetaTerminal v3 stopped" || echo "ThetaTerminal v3 not running"
            ;;
        *)
            echo "Usage: just thetadata [up|down]"
            ;;
    esac

# Options table audit — storage, quality, and coverage summary
options-status:
    #!/usr/bin/env bash
    PROTO="http"
    [[ "${CLICKHOUSE_SECURE:-false}" == "true" || "$CLICKHOUSE_HOST" == *".clickhouse.cloud"* || "${CLICKHOUSE_PORT:-8123}" == "8443" ]] && PROTO="https"
    CH="${PROTO}://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8123}/"
    AUTH="${CLICKHOUSE_USER:-default}:${CLICKHOUSE_PASSWORD}"
    DB="${CLICKHOUSE_DATABASE:-dataplat}"

    echo "═══════════════════════════════════════════"
    echo "  option_chains — Table Audit"
    echo "═══════════════════════════════════════════"

    echo ""
    echo "── Storage ──────────────────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        formatReadableQuantity(total_rows)    AS rows, \
        formatReadableSize(total_bytes)       AS compressed, \
        formatReadableSize(data_uncompressed_bytes) AS uncompressed, \
        round(data_uncompressed_bytes / greatest(total_bytes, 1), 1) AS compression_ratio, \
        partition_count AS partitions \
      FROM ( \
        SELECT \
          sum(rows)                    AS total_rows, \
          sum(bytes_on_disk)           AS total_bytes, \
          sum(data_uncompressed_bytes) AS data_uncompressed_bytes, \
          count()                      AS partition_count \
        FROM system.parts \
        WHERE database = '${DB}' AND table = 'option_chains' AND active \
      ) FORMAT PrettyCompact"

    echo ""
    echo "── Overview ─────────────────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        formatReadableQuantity(count())           AS total_rows, \
        countDistinct(underlying)                 AS underlyings, \
        countDistinct(snapshot_date)              AS trading_days, \
        min(snapshot_date)                        AS earliest, \
        max(snapshot_date)                        AS latest, \
        countDistinct(expiration)                 AS expirations, \
        round(avg(toFloat64(expiration - snapshot_date)), 1) AS avg_dte, \
        countIf(put_call = 'call')                AS calls, \
        countIf(put_call = 'put')                 AS puts \
      FROM ${DB}.option_chains \
      FORMAT PrettyCompact"

    echo ""
    echo "── Data Quality ─────────────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        countIf(bid = 0 AND ask = 0)                                           AS zero_bid_ask, \
        countIf(implied_vol = 0)                                               AS zero_iv, \
        countIf(implied_vol > 5)                                               AS iv_above_500pct, \
        countIf(delta = 0 AND gamma = 0 AND theta = 0)                         AS zero_greeks, \
        countIf(open IS NULL AND high IS NULL AND low IS NULL AND close IS NULL) AS null_ohlc, \
        countIf(underlying_price IS NULL)                                      AS null_underlying_px, \
        countIf(volume = 0)                                                    AS zero_volume, \
        countIf(open_interest = 0)                                             AS zero_oi, \
        round(100.0 * countIf(bid = 0 AND ask = 0) / count(), 2)              AS pct_zero_bid_ask, \
        round(100.0 * countIf(implied_vol = 0) / count(), 2)                  AS pct_zero_iv \
      FROM ${DB}.option_chains \
      FORMAT PrettyCompact"

    echo ""
    echo "── Source Breakdown ─────────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        source, \
        formatReadableQuantity(count()) AS rows, \
        countDistinct(underlying)       AS underlyings, \
        min(snapshot_date)              AS earliest, \
        max(snapshot_date)              AS latest \
      FROM ${DB}.option_chains \
      GROUP BY source ORDER BY count() DESC \
      FORMAT PrettyCompact"

    echo ""
    echo "── Partitions (by year) ─────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        toYear(snapshot_date)                     AS year, \
        formatReadableQuantity(count())           AS rows, \
        countDistinct(underlying)                 AS underlyings, \
        countDistinct(snapshot_date)              AS trading_days \
      FROM ${DB}.option_chains \
      GROUP BY year ORDER BY year \
      FORMAT PrettyCompact"

    echo ""
    echo "── Top 20 Underlyings ───────────────────"
    curl -s "$CH" --user "$AUTH" -d "SELECT \
        underlying, \
        formatReadableQuantity(count())   AS rows, \
        countDistinct(snapshot_date)      AS days, \
        min(snapshot_date)                AS earliest, \
        max(snapshot_date)                AS latest, \
        countDistinct(expiration)         AS expirations, \
        round(avg(implied_vol), 4)        AS avg_iv, \
        round(avg(toFloat64(expiration - snapshot_date)), 0) AS avg_dte \
      FROM ${DB}.option_chains \
      GROUP BY underlying ORDER BY count() DESC LIMIT 20 \
      FORMAT PrettyCompact"

# Show table row counts
ch-stats:
    #!/usr/bin/env bash
    PROTO="http"
    [[ "${CLICKHOUSE_SECURE:-false}" == "true" || "$CLICKHOUSE_HOST" == *".clickhouse.cloud"* || "${CLICKHOUSE_PORT:-8123}" == "8443" ]] && PROTO="https"
    curl -s "${PROTO}://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8123}/" \
        --user "${CLICKHOUSE_USER:-default}:${CLICKHOUSE_PASSWORD}" \
        -d "SELECT name, formatReadableQuantity(total_rows) AS rows, formatReadableSize(total_bytes) AS size FROM system.tables WHERE database = '${CLICKHOUSE_DATABASE:-dataplat}' AND total_rows > 0 ORDER BY total_rows DESC FORMAT PrettyCompact"
