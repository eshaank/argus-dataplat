# Argus DataPlat — Task Runner
# Install just: https://github.com/casey/just

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
backfill *ARGS:
    uv run python -m dataplat.cli.backfill {{ARGS}}

# Seed the universe table
seed-universe:
    uv run python scripts/seed_universe.py

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
ch-shell:
    @docker compose exec clickhouse clickhouse-client -d dataplat

# Check ClickHouse is healthy
ch-ping:
    @curl -sS 'http://localhost:8123/ping' && echo " ClickHouse is up" || echo " ClickHouse is down"

# Show table row counts
ch-stats:
    @curl -s 'http://localhost:8123/' --user "default:local_dev_clickhouse" -d "SELECT name, formatReadableQuantity(total_rows) AS rows, formatReadableSize(total_bytes) AS size FROM system.tables WHERE database = 'dataplat' AND total_rows > 0 ORDER BY total_rows DESC FORMAT PrettyCompact"
