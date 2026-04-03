   # Backfill
   - `just backfill --source polygon --tickers AAPL,MSFT,GOOGL --months 48`

   # Query in ClickHouse shell
   - `just ch-shell`

   # Then SQL:
   - `SELECT * FROM ohlcv_daily_mv WHERE ticker = 'AAPL' ORDER BY day DESC LIMIT 10;`
   - `SELECT * FROM ohlcv_5min_mv WHERE ticker = 'AAPL' AND toDate(bucket) = today() ORDER BY bucket;`
   - `SELECT * FROM ohlcv WHERE ticker = 'AAPL' AND timestamp >= now() - INTERVAL 1 HOUR ORDER BY timestamp;`

   # Storage stats
   - `just ch-stats`