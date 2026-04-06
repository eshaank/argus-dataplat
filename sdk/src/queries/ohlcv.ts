import type { DataPlatClient } from '../client.js';
import type {
  OHLCVBar,
  OHLCVInterval,
  OHLCVParams,
  OHLCVMultiParams,
  ReturnData,
  LatestPrice,
} from '../types.js';

/** Maps interval to the correct ClickHouse table/MV and time column. */
function tableForInterval(interval: OHLCVInterval): { table: string; timeCol: string } {
  switch (interval) {
    case '1m':  return { table: 'ohlcv', timeCol: 'timestamp' };
    case '5m':  return { table: 'ohlcv_5min_mv', timeCol: 'bucket' };
    case '15m': return { table: 'ohlcv_15min_mv', timeCol: 'bucket' };
    case '1h':  return { table: 'ohlcv_1h_mv', timeCol: 'bucket' };
    case '1d':  return { table: 'ohlcv_daily_mv', timeCol: 'day' };
  }
}

/** Volume column name differs between base table and MVs. */
function volumeCol(interval: OHLCVInterval): string {
  return interval === '1m' ? 'toFloat64(volume)' : 'toFloat64(total_volume)';
}

function escTicker(t: string): string {
  return t.replace(/'/g, "\\'");
}

function tickerList(tickers: string[]): string {
  return tickers.map((t) => `'${escTicker(t)}'`).join(', ');
}

function dateFilter(timeCol: string, start?: string, end?: string): string {
  const parts: string[] = [];
  if (start) parts.push(`${timeCol} >= '${start}'`);
  if (end) parts.push(`${timeCol} <= '${end}'`);
  return parts.length > 0 ? `AND ${parts.join(' AND ')}` : '';
}

interface RawOHLCVRow {
  ticker: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap: number | null;
  transactions: number | null;
}

export async function getOHLCV(
  client: DataPlatClient,
  params: OHLCVParams,
): Promise<OHLCVBar[]> {
  const { table, timeCol } = tableForInterval(params.interval);
  const volCol = volumeCol(params.interval);

  const sql = `
    SELECT
      ticker,
      toString(${timeCol}) AS time,
      open, high, low, close,
      ${volCol} AS volume,
      vwap,
      transactions
    FROM ${table}
    WHERE ticker = '${escTicker(params.ticker)}'
      ${dateFilter(timeCol, params.start, params.end)}
    ORDER BY ${timeCol}
  `;

  const result = await client.query<RawOHLCVRow>(sql);
  return result.rows;
}

export async function getOHLCVMulti(
  client: DataPlatClient,
  params: OHLCVMultiParams,
): Promise<OHLCVBar[]> {
  if (params.tickers.length === 0) return [];

  const { table, timeCol } = tableForInterval(params.interval);
  const volCol = volumeCol(params.interval);

  const sql = `
    SELECT
      ticker,
      toString(${timeCol}) AS time,
      open, high, low, close,
      ${volCol} AS volume,
      vwap,
      transactions
    FROM ${table}
    WHERE ticker IN (${tickerList(params.tickers)})
      ${dateFilter(timeCol, params.start, params.end)}
    ORDER BY ticker, ${timeCol}
  `;

  const result = await client.query<RawOHLCVRow>(sql);
  return result.rows;
}

export async function getReturns(
  client: DataPlatClient,
  tickers: string[],
  start: string,
  end: string,
): Promise<ReturnData[]> {
  if (tickers.length === 0) return [];

  const sql = `
    SELECT
      ticker,
      argMin(close, day) AS startPrice,
      argMax(close, day) AS endPrice,
      (argMax(close, day) - argMin(close, day)) / argMin(close, day) * 100 AS returnPct
    FROM ohlcv_daily_mv
    WHERE ticker IN (${tickerList(tickers)})
      AND day >= '${start}'
      AND day <= '${end}'
    GROUP BY ticker
    ORDER BY returnPct DESC
  `;

  const result = await client.query<ReturnData>(sql);
  return result.rows;
}

export async function getLatestPrices(
  client: DataPlatClient,
  tickers: string[],
): Promise<LatestPrice[]> {
  if (tickers.length === 0) return [];

  const sql = `
    WITH latest AS (
      SELECT
        ticker,
        day AS date,
        close,
        toFloat64(total_volume) AS volume,
        row_number() OVER (PARTITION BY ticker ORDER BY day DESC) AS rn
      FROM ohlcv_daily_mv
      WHERE ticker IN (${tickerList(tickers)})
      ORDER BY day DESC
    )
    SELECT
      l1.ticker,
      toString(l1.date) AS date,
      l1.close,
      l2.close AS prevClose,
      CASE WHEN l2.close > 0
        THEN (l1.close - l2.close) / l2.close * 100
        ELSE 0
      END AS changePct,
      l1.volume
    FROM latest l1
    LEFT JOIN latest l2 ON l1.ticker = l2.ticker AND l2.rn = 2
    WHERE l1.rn = 1
    ORDER BY l1.ticker
  `;

  const result = await client.query<LatestPrice>(sql);
  return result.rows;
}
