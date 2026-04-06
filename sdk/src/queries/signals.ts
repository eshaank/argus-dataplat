/**
 * Signal queries: market breadth, 52-week highs/lows, dividend changes,
 * notable insider buys, upcoming dividends.
 * All backed by ClickHouse views (migration 027).
 */
import type { DataPlatClient } from '../client.js';

// ── Types ──────────────────────────────────────────────────────────

export interface MarketBreadth {
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
  avgChange: number;
  medianChange: number;
}

export interface HighLowCounts {
  newHighs: number;
  newLows: number;
  total: number;
}

export interface HighLowTicker {
  ticker: string;
  name: string;
  close: number;
  changePct: number;
  volume: number;
}

export interface DividendChange {
  ticker: string;
  name: string;
  prevAmount: number;
  latestAmount: number;
  changePct: number;
  exDate: string;
}

export interface NotableInsiderBuy {
  ticker: string;
  name: string;
  title: string | null;
  shares: number;
  price: number | null;
  value: number | null;
  filedDate: string;
}

export interface UpcomingDividend {
  ticker: string;
  name: string;
  amount: number;
  exDate: string;
}

// ── Queries ────────────────────────────────────────────────────────

export async function getMarketBreadth(client: DataPlatClient): Promise<MarketBreadth> {
  const result = await client.query<{
    advancers: number; decliners: number; unchanged: number;
    total: number; avg_change: number; median_change: number;
  }>('SELECT * FROM v_market_breadth');

  const row = result.rows[0];
  if (!row) return { advancers: 0, decliners: 0, unchanged: 0, total: 0, avgChange: 0, medianChange: 0 };

  return {
    advancers: row.advancers,
    decliners: row.decliners,
    unchanged: row.unchanged,
    total: row.total,
    avgChange: row.avg_change,
    medianChange: row.median_change,
  };
}

export async function get52WeekHighLowCounts(client: DataPlatClient): Promise<HighLowCounts> {
  const result = await client.query<{ new_highs: number; new_lows: number; total: number }>(
    'SELECT * FROM v_52w_hilo_counts',
  );
  const row = result.rows[0];
  if (!row) return { newHighs: 0, newLows: 0, total: 0 };
  return { newHighs: row.new_highs, newLows: row.new_lows, total: row.total };
}

export async function get52WeekHighs(client: DataPlatClient, limit = 25): Promise<HighLowTicker[]> {
  const result = await client.query<{
    ticker: string; name: string; close: number; change_pct: number; volume: number;
  }>(`SELECT * FROM v_52w_highs ORDER BY change_pct DESC LIMIT ${limit}`);

  return result.rows.map((r) => ({
    ticker: r.ticker, name: r.name, close: r.close,
    changePct: r.change_pct, volume: r.volume,
  }));
}

export async function get52WeekLows(client: DataPlatClient, limit = 25): Promise<HighLowTicker[]> {
  const result = await client.query<{
    ticker: string; name: string; close: number; change_pct: number; volume: number;
  }>(`SELECT * FROM v_52w_lows ORDER BY change_pct ASC LIMIT ${limit}`);

  return result.rows.map((r) => ({
    ticker: r.ticker, name: r.name, close: r.close,
    changePct: r.change_pct, volume: r.volume,
  }));
}

export async function getDividendChanges(client: DataPlatClient, limit = 30): Promise<DividendChange[]> {
  const result = await client.query<{
    ticker: string; name: string; prev_amount: number; latest_amount: number;
    change_pct: number; ex_date: string;
  }>(`SELECT ticker, name, prev_amount, latest_amount, change_pct, CAST(ex_date AS String) as ex_date FROM v_dividend_changes ORDER BY abs(change_pct) DESC LIMIT ${limit}`);

  return result.rows.map((r) => ({
    ticker: r.ticker, name: r.name,
    prevAmount: r.prev_amount, latestAmount: r.latest_amount,
    changePct: r.change_pct, exDate: r.ex_date,
  }));
}

export async function getNotableInsiderBuys(client: DataPlatClient, limit = 5): Promise<NotableInsiderBuy[]> {
  const result = await client.query<{
    ticker: string; name: string; title: string | null;
    shares: number; price: number | null; value: number | null; filed_date: string;
  }>(`SELECT ticker, name, title, shares, price, value, CAST(filed_date AS String) as filed_date FROM v_notable_insider_buys ORDER BY value DESC LIMIT ${limit}`);

  return result.rows.map((r) => ({
    ticker: r.ticker, name: r.name, title: r.title,
    shares: r.shares, price: r.price, value: r.value,
    filedDate: r.filed_date,
  }));
}

export async function getUpcomingDividends(client: DataPlatClient, limit = 8): Promise<UpcomingDividend[]> {
  const result = await client.query<{
    ticker: string; name: string; cash_amount: number; ex_date: string;
  }>(`SELECT ticker, name, cash_amount, CAST(ex_date AS String) as ex_date FROM v_upcoming_dividends ORDER BY cash_amount DESC LIMIT ${limit}`);

  return result.rows.map((r) => ({
    ticker: r.ticker, name: r.name,
    amount: r.cash_amount, exDate: r.ex_date,
  }));
}
