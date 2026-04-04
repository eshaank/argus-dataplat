/**
 * Market-level queries: top movers, most active, sector performance, indices.
 * These are aggregation queries over ohlcv_daily_mv + universe.
 */
import type { DataPlatClient } from '../client.js';

// ── Types ──────────────────────────────────────────────────────────

export interface Mover {
  ticker: string;
  name: string;
  close: number;
  changePct: number;
  volume: number;
}

export interface SectorPerformance {
  sector: string;
  tickerCount: number;
  avgReturnPct: number;
}

export interface MiniBar {
  time: string;
  close: number;
}

// ── SIC → Sector mapping (done in SQL for speed) ──────────────────

const SECTOR_CASE = `
  CASE 
    WHEN substring(sic_code,1,2) IN ('10','12','13','14') THEN 'Energy'
    WHEN substring(sic_code,1,2) = '28' THEN 'Pharma'
    WHEN substring(sic_code,1,2) IN ('35','36','37','38') THEN 'Tech & Electronics'
    WHEN substring(sic_code,1,2) = '73' THEN 'Software & Services'
    WHEN substring(sic_code,1,2) IN ('60','61','62','63','64','65','67') THEN 'Financials'
    WHEN substring(sic_code,1,2) IN ('48','49') THEN 'Telecom & Utilities'
    WHEN substring(sic_code,1,2) BETWEEN '52' AND '59' THEN 'Retail'
    WHEN substring(sic_code,1,2) IN ('20','21') THEN 'Food & Beverage'
    ELSE 'Other'
  END
`;

// ── Top Movers ─────────────────────────────────────────────────────

export async function getTopMovers(
  client: DataPlatClient,
  direction: 'gainers' | 'losers',
  limit = 10,
): Promise<Mover[]> {
  const order = direction === 'gainers' ? 'DESC' : 'ASC';

  const sql = `
    WITH latest AS (
      SELECT ticker, day, close, total_volume,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) AS prev_close
      FROM ohlcv_daily_mv
      WHERE day >= today() - 7
    ),
    movers AS (
      SELECT 
        ticker,
        close,
        round((close - prev_close) / prev_close * 100, 2) AS changePct,
        total_volume AS volume
      FROM latest
      WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
        AND prev_close > 0
      ORDER BY changePct ${order}
      LIMIT ${limit}
    )
    SELECT m.ticker, u.name, m.close, m.changePct, m.volume
    FROM movers m
    LEFT JOIN universe u ON m.ticker = u.ticker
    ORDER BY m.changePct ${order}
  `;

  const result = await client.query<Mover>(sql);
  return result.rows;
}

// ── Most Active ────────────────────────────────────────────────────

export async function getMostActive(
  client: DataPlatClient,
  limit = 10,
): Promise<Mover[]> {
  const sql = `
    WITH latest AS (
      SELECT ticker, day, close, total_volume,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) AS prev_close
      FROM ohlcv_daily_mv
      WHERE day >= today() - 7
    ),
    active AS (
      SELECT 
        ticker,
        close,
        round((close - prev_close) / prev_close * 100, 2) AS changePct,
        total_volume AS volume
      FROM latest
      WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
        AND prev_close > 0
      ORDER BY total_volume DESC
      LIMIT ${limit}
    )
    SELECT a.ticker, u.name, a.close, a.changePct, a.volume
    FROM active a
    LEFT JOIN universe u ON a.ticker = u.ticker
    ORDER BY a.volume DESC
  `;

  const result = await client.query<Mover>(sql);
  return result.rows;
}

// ── Sector Performance ─────────────────────────────────────────────

export async function getSectorPerformance(
  client: DataPlatClient,
  days = 7,
): Promise<SectorPerformance[]> {
  const sql = `
    WITH sector_map AS (
      SELECT ticker, ${SECTOR_CASE} AS sector
      FROM universe
      WHERE sic_code IS NOT NULL AND sic_code != ''
    ),
    returns AS (
      SELECT ticker,
        argMax(close, day) AS last_close,
        argMin(close, day) AS first_close
      FROM ohlcv_daily_mv
      WHERE day >= today() - ${days}
      GROUP BY ticker
    )
    SELECT 
      s.sector,
      count() AS tickerCount,
      round(avg((r.last_close - r.first_close) / r.first_close * 100), 2) AS avgReturnPct
    FROM sector_map s
    JOIN returns r ON s.ticker = r.ticker
    WHERE r.first_close > 0
    GROUP BY s.sector
    ORDER BY avgReturnPct DESC
  `;

  const result = await client.query<SectorPerformance>(sql);
  return result.rows;
}

// ── Mini Sparkline Data ────────────────────────────────────────────

/** Get last N days of close prices for sparkline rendering. */
export async function getSparkline(
  client: DataPlatClient,
  ticker: string,
  days = 30,
): Promise<MiniBar[]> {
  const sql = `
    SELECT toString(day) AS time, close
    FROM ohlcv_daily_mv
    WHERE ticker = '${ticker.replace(/'/g, "\\'")}'
      AND day >= today() - ${days}
    ORDER BY day
  `;

  const result = await client.query<MiniBar>(sql);
  return result.rows;
}

// ── Treemap Data ───────────────────────────────────────────────────

export interface TreemapTicker {
  ticker: string;
  name: string;
  sector: string;
  marketCap: number;
  close: number;
  changePct: number;
}

/** All tickers with sector, market cap, and daily return — for treemap heatmap.
 *  minMarketCap filters out tiny tiles that would be unreadable (default ~$55B). */
export async function getTreemapData(
  client: DataPlatClient,
  minMarketCap = 55_000_000_000,
): Promise<TreemapTicker[]> {
  const sql = `
    WITH daily AS (
      SELECT ticker, day, close,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) AS prev_close
      FROM ohlcv_daily_mv
      WHERE day >= today() - 7
    ),
    latest AS (
      SELECT ticker, close,
        round((close - prev_close) / prev_close * 100, 2) AS changePct
      FROM daily
      WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
        AND prev_close > 0
    )
    SELECT
      u.ticker,
      u.name,
      ${SECTOR_CASE} AS sector,
      coalesce(u.market_cap, 0) AS marketCap,
      l.close,
      l.changePct
    FROM universe u
    JOIN latest l ON u.ticker = l.ticker
    WHERE u.sic_code IS NOT NULL AND u.sic_code != ''
      AND u.market_cap >= ${minMarketCap}
    ORDER BY marketCap DESC
  `;

  const result = await client.query<TreemapTicker>(sql);
  return result.rows;
}

// ── Momentum Velocity ──────────────────────────────────────────────

export interface MomentumBar {
  date: string;
  returnPct: number;
}

/** Weekly returns for a ticker over N weeks — for momentum bar chart. */
export async function getMomentumVelocity(
  client: DataPlatClient,
  ticker: string,
  weeks = 26,
): Promise<MomentumBar[]> {
  const esc = ticker.replace(/'/g, "\\'");

  const sql = `
    WITH weekly AS (
      SELECT
        toMonday(day) AS week_start,
        argMin(close, day) AS week_open,
        argMax(close, day) AS week_close
      FROM ohlcv_daily_mv
      WHERE ticker = '${esc}'
        AND day >= today() - (${weeks} * 7)
      GROUP BY week_start
      ORDER BY week_start
    )
    SELECT
      toString(week_start) AS date,
      round((week_close - week_open) / week_open * 100, 2) AS returnPct
    FROM weekly
    WHERE week_open > 0
    ORDER BY week_start
  `;

  const result = await client.query<MomentumBar>(sql);
  return result.rows;
}

// ── Screener ──────────────────────────────────────────────────────

export interface ScreenerRow {
  ticker: string;
  name: string;
  sector: string;
  exchange: string;
  marketCap: number;
  close: number;
  changePct: number;
  volume: number;
  revenue: number | null;
  netIncome: number | null;
  grossMargin: number | null;
  netMargin: number | null;
  pe: number | null;
}

/** Full screener data: universe + latest price + latest financials. */
export async function getScreenerData(
  client: DataPlatClient,
): Promise<ScreenerRow[]> {
  const sql = `
    WITH prices AS (
      SELECT ticker, day, close, total_volume,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) AS prev_close
      FROM ohlcv_daily_mv
      WHERE day >= today() - 7
    ),
    latest_prices AS (
      SELECT ticker, close,
        round((close - prev_close) / prev_close * 100, 2) AS changePct,
        total_volume AS volume
      FROM prices
      WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
        AND prev_close > 0
    ),
    latest_fins AS (
      SELECT
        ticker,
        argMax(revenue, period_end) AS revenue,
        argMax(net_income, period_end) AS netIncome,
        argMax(gross_profit, period_end) AS grossProfit,
        argMax(diluted_eps, period_end) AS eps
      FROM financials
      WHERE timeframe = 'annual'
      GROUP BY ticker
    )
    SELECT
      u.ticker AS ticker,
      u.name AS name,
      ${SECTOR_CASE} AS sector,
      u.exchange AS exchange,
      coalesce(u.market_cap, 0) AS marketCap,
      p.close,
      p.changePct,
      p.volume,
      f.revenue,
      f.netIncome,
      CASE WHEN f.revenue > 0 AND f.grossProfit IS NOT NULL THEN round(f.grossProfit / f.revenue * 100, 1) ELSE NULL END AS grossMargin,
      CASE WHEN f.revenue > 0 AND f.netIncome IS NOT NULL THEN round(f.netIncome / f.revenue * 100, 1) ELSE NULL END AS netMargin,
      CASE WHEN f.eps > 0 THEN round(p.close / f.eps, 1) ELSE NULL END AS pe
    FROM universe u
    JOIN latest_prices p ON u.ticker = p.ticker
    LEFT JOIN latest_fins f ON u.ticker = f.ticker
    WHERE u.sic_code IS NOT NULL AND u.sic_code != ''
    ORDER BY u.market_cap DESC
  `;

  const result = await client.query<ScreenerRow>(sql);
  return result.rows;
}

// ── Correlation Matrix ─────────────────────────────────────────────

export interface CorrelationPair {
  tickerA: string;
  tickerB: string;
  correlation: number;
}

export async function getCorrelationMatrix(
  client: DataPlatClient,
  tickers: string[],
  days = 180,
): Promise<CorrelationPair[]> {
  if (tickers.length < 2) return [];
  const list = tickers.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(', ');

  const sql = `
    WITH daily AS (
      SELECT ticker, day, close
      FROM ohlcv_daily_mv
      WHERE ticker IN (${list})
        AND day >= today() - ${days}
    )
    SELECT
      a.ticker AS tickerA,
      b.ticker AS tickerB,
      round(corr(a.close, b.close), 4) AS correlation
    FROM daily a
    JOIN daily b ON a.day = b.day
    WHERE a.ticker < b.ticker
    GROUP BY a.ticker, b.ticker
    ORDER BY a.ticker, b.ticker
  `;

  const result = await client.query<CorrelationPair>(sql);
  return result.rows;
}

/** Get sparklines for multiple tickers in one query. */
export async function getSparklines(
  client: DataPlatClient,
  tickers: string[],
  days = 30,
): Promise<Record<string, MiniBar[]>> {
  if (tickers.length === 0) return {};

  const list = tickers.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(', ');

  const sql = `
    SELECT ticker, toString(day) AS time, close
    FROM ohlcv_daily_mv
    WHERE ticker IN (${list})
      AND day >= today() - ${days}
    ORDER BY ticker, day
  `;

  const result = await client.query<{ ticker: string; time: string; close: number }>(sql);

  const grouped: Record<string, MiniBar[]> = {};
  for (const row of result.rows) {
    if (!grouped[row.ticker]) grouped[row.ticker] = [];
    grouped[row.ticker]!.push({ time: row.time, close: row.close });
  }
  return grouped;
}
