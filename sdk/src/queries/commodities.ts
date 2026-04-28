import type { DataPlatClient } from '../client.js';
import type { DateRangeParams } from '../types.js';

// ── Types ──────────────────────────────────────────────────────────

/** Supported intervals for commodity OHLCV data */
export type CommodityOHLCVInterval =
  | '15m' | '30m' | '1h' | '2h' | '4h'  // intraday
  | '1d' | '1wk' | '1mo' | '1q' | '1yr'; // daily+

/** OHLCV bar for multi-interval commodity data */
export interface CommodityOHLCVBar {
  ticker: string;
  name: string;
  /** ISO timestamp string (intraday) or date string (daily+) */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Latest return per commodity ticker */
export interface CommodityLatestReturn {
  ticker: string;
  name: string;
  date: string;
  close: number;
  prevClose: number | null;
  returnPct: number | null;
}

/** EIA energy spot prices (daily) */
export interface EnergySpotPrice {
  date: string;
  wtiCrude: number | null;
  brentCrude: number | null;
  naturalGas: number | null;
  gasoline: number | null;
  heatingOil: number | null;
}

/** Latest EIA energy spot prices */
export interface EnergySpotLatest {
  date: string;
  wtiCrude: number | null;
  brentCrude: number | null;
  naturalGas: number | null;
  gasoline: number | null;
  heatingOil: number | null;
}

/** Commodity futures OHLCV bar */
export interface CommodityOHLCV {
  ticker: string;
  name: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Latest close for each commodity */
export interface CommodityLatest {
  ticker: string;
  name: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Daily return for a commodity */
export interface CommodityReturn {
  ticker: string;
  name: string;
  date: string;
  close: number;
  prevClose: number | null;
  returnPct: number | null;
}

export interface BrentWTISpread {
  date: string;
  wtiCrude: number;
  brentCrude: number;
  spread: number;
  spreadPct: number;
}

export interface PetroleumWeekly {
  date: string;
  crudeProduction: number | null;
  crudeImports: number | null;
  crudeExports: number | null;
  crudeNetImports: number | null;
  crudeStocks: number | null;
  sprStocks: number | null;
  totalStocks: number | null;
  productSupplied: number | null;
  gasolineSupplied: number | null;
  distillateSupplied: number | null;
  jetFuelSupplied: number | null;
  refineryUtilization: number | null;
  refineryInputs: number | null;
  daysOfSupply: number | null;
  crudeStocksWow: number | null;
  sprStocksWow: number | null;
}

export interface PetroleumStocksVs5Yr {
  date: string;
  currentStocks: number;
  fiveYrAvg: number;
  fiveYrMin: number;
  fiveYrMax: number;
  vsAvg: number;
  vsAvgPct: number;
}

export interface OPECShare {
  date: string;
  opecProduction: number | null;
  saudiProduction: number | null;
  iranProduction: number | null;
  iraqProduction: number | null;
  uaeProduction: number | null;
  russiaProduction: number | null;
  usProduction: number | null;
  worldProduction: number | null;
  saudiPct: number | null;
  iranPct: number | null;
  iraqPct: number | null;
  uaePct: number | null;
  opecMom: number | null;
  iranMom: number | null;
  usMom: number | null;
}

export interface PersianGulfDependency {
  date: string;
  importsPersianGulf: number | null;
  importsTotal: number | null;
  gulfPct: number | null;
  gulfMom: number | null;
  totalMom: number | null;
}

// ── Raw row types ──────────────────────────────────────────────────

interface RawEnergySpotRow {
  date: string;
  wti_crude: number | null;
  brent_crude: number | null;
  natural_gas: number | null;
  gasoline: number | null;
  heating_oil: number | null;
}

interface RawCommodityOHLCVRow {
  ticker: string;
  name: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface RawCommodityReturnRow {
  ticker: string;
  name: string;
  date: string;
  close: number;
  prev_close: number | null;
  return_pct: number | null;
}

interface RawSpreadRow {
  date: string;
  wti_crude: number;
  brent_crude: number;
  spread: number;
  spread_pct: number;
}

interface RawPetroleumWeeklyRow {
  date: string;
  crude_production: number | null;
  crude_imports: number | null;
  crude_exports: number | null;
  crude_net_imports: number | null;
  crude_stocks: number | null;
  spr_stocks: number | null;
  total_stocks: number | null;
  product_supplied: number | null;
  gasoline_supplied: number | null;
  distillate_supplied: number | null;
  jet_fuel_supplied: number | null;
  refinery_utilization: number | null;
  refinery_inputs: number | null;
  days_of_supply: number | null;
  crude_stocks_wow: number | null;
  spr_stocks_wow: number | null;
}

interface RawStocksVs5YrRow {
  date: string;
  current_stocks: number;
  five_yr_avg: number;
  five_yr_min: number;
  five_yr_max: number;
  vs_avg: number;
  vs_avg_pct: number;
}

interface RawOPECRow {
  date: string;
  opec_production: number | null;
  saudi_production: number | null;
  iran_production: number | null;
  iraq_production: number | null;
  uae_production: number | null;
  russia_production: number | null;
  us_production: number | null;
  world_production: number | null;
  saudi_pct: number | null;
  iran_pct: number | null;
  iraq_pct: number | null;
  uae_pct: number | null;
  opec_mom: number | null;
  iran_mom: number | null;
  us_mom: number | null;
}

interface RawGulfRow {
  date: string;
  imports_persian_gulf: number | null;
  imports_total: number | null;
  gulf_pct: number | null;
  gulf_mom: number | null;
  total_mom: number | null;
}

// ── Interval table/view mapping ────────────────────────────────────

/** Maps interval to the correct ClickHouse table/view name */
function tableForInterval(interval: CommodityOHLCVInterval): string {
  switch (interval) {
    // Base tables (ReplacingMergeTree — FINAL applied at query level)
    case '15m': return 'commodities_ohlcv_15m';
    case '1h':  return 'commodities_ohlcv_1h';
    case '4h':  return 'commodities_ohlcv_4h';
    case '1d':  return 'commodities_ohlcv';
    // Aggregated views (already apply FINAL internally — do NOT add FINAL at query level)
    case '30m': return 'v_commodity_ohlcv_30m';
    case '2h':  return 'v_commodity_ohlcv_2h';
    case '1wk': return 'v_commodity_ohlcv_1wk';
    case '1mo': return 'v_commodity_ohlcv_1mo';
    case '1q':  return 'v_commodity_ohlcv_3mo';  // migration 050 created 3mo, not 1q
    case '1yr': return 'v_commodity_ohlcv_1yr';
  }
}

/** Base table intervals need FINAL for ReplacingMergeTree dedup; views handle it internally */
function needsFinal(interval: CommodityOHLCVInterval): boolean {
  return interval === '15m' || interval === '1h' || interval === '4h' || interval === '1d';
}

/** Returns the time column name for the given interval */
function timeCol(interval: CommodityOHLCVInterval): string {
  // Intraday intervals use 'timestamp', daily+ use 'date'
  switch (interval) {
    case '15m':
    case '30m':
    case '1h':
    case '2h':
    case '4h':
      return 'timestamp';
    case '1d':
    case '1wk':
    case '1mo':
    case '1q':
    case '1yr':
      return 'date';
  }
}

// ── Helpers ────────────────────────────────────────────────────────

function dateFilter(col: string, start?: string, end?: string): string {
  const parts: string[] = [];
  if (start) parts.push(`${col} >= '${start}'`);
  if (end) parts.push(`${col} <= '${end}'`);
  return parts.length > 0 ? parts.join(' AND ') : '';
}

function whereClause(...conditions: string[]): string {
  const valid = conditions.filter(Boolean);
  return valid.length > 0 ? `WHERE ${valid.join(' AND ')}` : '';
}

function mapEnergySpot(r: RawEnergySpotRow): EnergySpotPrice {
  return {
    date: r.date,
    wtiCrude: r.wti_crude,
    brentCrude: r.brent_crude,
    naturalGas: r.natural_gas,
    gasoline: r.gasoline,
    heatingOil: r.heating_oil,
  };
}

// ── Queries: Energy Spot Prices (EIA) ──────────────────────────────

export async function getEnergySpotPrices(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<EnergySpotPrice[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      wti_crude, brent_crude, natural_gas, gasoline, heating_oil
    FROM commodity_prices FINAL
    ${whereClause(dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawEnergySpotRow>(sql);
  return result.rows.map(mapEnergySpot);
}

export async function getEnergySpotLatest(
  client: DataPlatClient,
): Promise<EnergySpotLatest | null> {
  const result = await client.query<RawEnergySpotRow>(`
    SELECT toString(date) AS date, wti_crude, brent_crude, natural_gas, gasoline, heating_oil
    FROM v_commodity_latest
  `);
  const row = result.rows[0];
  if (!row) return null;
  return mapEnergySpot(row);
}

// ── Queries: Commodity Futures OHLCV ───────────────────────────────

export async function getCommodityOHLCV(
  client: DataPlatClient,
  ticker: string,
  params?: DateRangeParams,
): Promise<CommodityOHLCV[]> {
  const esc = ticker.replace(/'/g, "\\'");
  const sql = `
    SELECT ticker, name, toString(date) AS date, open, high, low, close, toFloat64(volume) AS volume
    FROM commodities_ohlcv FINAL
    ${whereClause(`ticker = '${esc}'`, dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawCommodityOHLCVRow>(sql);
  return result.rows;
}

export async function getCommodityOHLCVMulti(
  client: DataPlatClient,
  tickers: string[],
  params?: DateRangeParams,
): Promise<CommodityOHLCV[]> {
  const inList = tickers.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(',');
  const sql = `
    SELECT ticker, name, toString(date) AS date, open, high, low, close, toFloat64(volume) AS volume
    FROM commodities_ohlcv FINAL
    ${whereClause(`ticker IN (${inList})`, dateFilter('date', params?.start, params?.end))}
    ORDER BY ticker, date
  `;

  const result = await client.query<RawCommodityOHLCVRow>(sql);
  return result.rows;
}

export async function getCommodityLatest(
  client: DataPlatClient,
): Promise<CommodityLatest[]> {
  const result = await client.query<RawCommodityOHLCVRow>(`
    SELECT ticker, name, toString(date) AS date, open, high, low, close, toFloat64(volume) AS volume
    FROM v_commodities_ohlcv_latest
  `);
  return result.rows;
}

export async function getCommodityReturns(
  client: DataPlatClient,
  ticker: string,
  params?: DateRangeParams,
): Promise<CommodityReturn[]> {
  const esc = ticker.replace(/'/g, "\\'");
  const sql = `
    SELECT ticker, name, toString(date) AS date, close, prev_close, return_pct
    FROM v_commodity_returns
    ${whereClause(`ticker = '${esc}'`, dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawCommodityReturnRow>(sql);
  return result.rows.map((r) => ({
    ticker: r.ticker,
    name: r.name,
    date: r.date,
    close: r.close,
    prevClose: r.prev_close,
    returnPct: r.return_pct,
  }));
}

/** List all available commodity tickers */
export async function getCommodityTickers(
  client: DataPlatClient,
): Promise<string[]> {
  const result = await client.query<{ ticker: string }>(`
    SELECT DISTINCT ticker FROM commodities_ohlcv FINAL ORDER BY ticker
  `);
  return result.rows.map((r) => r.ticker);
}

// ── Queries: Brent-WTI Spread ──────────────────────────────────────

export async function getBrentWTISpread(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<BrentWTISpread[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      wti_crude, brent_crude, spread, spread_pct
    FROM v_brent_wti_spread
    ${whereClause(dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawSpreadRow>(sql);
  return result.rows.map((r) => ({
    date: r.date,
    wtiCrude: r.wti_crude,
    brentCrude: r.brent_crude,
    spread: r.spread,
    spreadPct: r.spread_pct,
  }));
}

// ── Queries: Petroleum Weekly ──────────────────────────────────────

export async function getPetroleumWeekly(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<PetroleumWeekly[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      crude_production, crude_imports, crude_exports, crude_net_imports,
      crude_stocks, spr_stocks, total_stocks,
      product_supplied, gasoline_supplied, distillate_supplied, jet_fuel_supplied,
      refinery_utilization, refinery_inputs,
      days_of_supply, crude_stocks_wow, spr_stocks_wow
    FROM v_petroleum_supply_demand
    ${whereClause(dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawPetroleumWeeklyRow>(sql);
  return result.rows.map((r) => ({
    date: r.date,
    crudeProduction: r.crude_production,
    crudeImports: r.crude_imports,
    crudeExports: r.crude_exports,
    crudeNetImports: r.crude_net_imports,
    crudeStocks: r.crude_stocks,
    sprStocks: r.spr_stocks,
    totalStocks: r.total_stocks,
    productSupplied: r.product_supplied,
    gasolineSupplied: r.gasoline_supplied,
    distillateSupplied: r.distillate_supplied,
    jetFuelSupplied: r.jet_fuel_supplied,
    refineryUtilization: r.refinery_utilization,
    refineryInputs: r.refinery_inputs,
    daysOfSupply: r.days_of_supply,
    crudeStocksWow: r.crude_stocks_wow,
    sprStocksWow: r.spr_stocks_wow,
  }));
}

export async function getPetroleumStocksVs5Yr(
  client: DataPlatClient,
): Promise<PetroleumStocksVs5Yr[]> {
  const result = await client.query<RawStocksVs5YrRow>(`
    SELECT toString(date) AS date,
      current_stocks, five_yr_avg, five_yr_min, five_yr_max, vs_avg, vs_avg_pct
    FROM v_petroleum_stocks_vs_5yr
    ORDER BY date
  `);
  return result.rows.map((r) => ({
    date: r.date,
    currentStocks: r.current_stocks,
    fiveYrAvg: r.five_yr_avg,
    fiveYrMin: r.five_yr_min,
    fiveYrMax: r.five_yr_max,
    vsAvg: r.vs_avg,
    vsAvgPct: r.vs_avg_pct,
  }));
}

// ── Queries: OPEC & Geopolitical ───────────────────────────────────

export async function getOPECShare(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<OPECShare[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      opec_production, saudi_production, iran_production,
      iraq_production, uae_production, russia_production,
      us_production, world_production,
      saudi_pct, iran_pct, iraq_pct, uae_pct,
      opec_mom, iran_mom, us_mom
    FROM v_opec_share
    ${whereClause(dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawOPECRow>(sql);
  return result.rows.map((r) => ({
    date: r.date,
    opecProduction: r.opec_production,
    saudiProduction: r.saudi_production,
    iranProduction: r.iran_production,
    iraqProduction: r.iraq_production,
    uaeProduction: r.uae_production,
    russiaProduction: r.russia_production,
    usProduction: r.us_production,
    worldProduction: r.world_production,
    saudiPct: r.saudi_pct,
    iranPct: r.iran_pct,
    iraqPct: r.iraq_pct,
    uaePct: r.uae_pct,
    opecMom: r.opec_mom,
    iranMom: r.iran_mom,
    usMom: r.us_mom,
  }));
}

export async function getPersianGulfDependency(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<PersianGulfDependency[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      imports_persian_gulf, imports_total,
      gulf_pct, gulf_mom, total_mom
    FROM v_persian_gulf_dependency
    ${whereClause(dateFilter('date', params?.start, params?.end))}
    ORDER BY date
  `;

  const result = await client.query<RawGulfRow>(sql);
  return result.rows.map((r) => ({
    date: r.date,
    importsPersianGulf: r.imports_persian_gulf,
    importsTotal: r.imports_total,
    gulfPct: r.gulf_pct,
    gulfMom: r.gulf_mom,
    totalMom: r.total_mom,
  }));
}

// ── Queries: Multi-Interval OHLCV ──────────────────────────────────

interface RawCommodityOHLCVBarRow {
  ticker: string;
  name: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Get commodity OHLCV data for a specific interval */
export async function getCommodityOHLCVInterval(
  client: DataPlatClient,
  ticker: string,
  interval: CommodityOHLCVInterval,
  params?: DateRangeParams,
): Promise<CommodityOHLCVBar[]> {
  const table = tableForInterval(interval);
  const col = timeCol(interval);
  const final = needsFinal(interval) ? ' FINAL' : '';
  const esc = ticker.replace(/'/g, "\\'");

  const sql = `
    SELECT
      ticker,
      name,
      toString(${col}) AS time,
      open, high, low, close, volume
    FROM ${table}${final}
    ${whereClause(`ticker = '${esc}'`, dateFilter(col, params?.start, params?.end))}
    ORDER BY ${col}
  `;

  const result = await client.query<RawCommodityOHLCVBarRow>(sql);
  return result.rows;
}

interface RawCommodityLatestReturnRow {
  ticker: string;
  name: string;
  date: string;
  close: number;
  prev_close: number | null;
  return_pct: number | null;
}

/** Get latest return for each commodity ticker */
export async function getCommodityLatestReturns(
  client: DataPlatClient,
): Promise<CommodityLatestReturn[]> {
  const sql = `
    SELECT
      ticker,
      name,
      toString(date) AS date,
      close,
      prev_close,
      return_pct
    FROM v_commodity_returns FINAL
    WHERE date = (SELECT max(date) FROM v_commodity_returns)
    ORDER BY ticker
  `;

  const result = await client.query<RawCommodityLatestReturnRow>(sql);
  return result.rows.map((r) => ({
    ticker: r.ticker,
    name: r.name,
    date: r.date,
    close: r.close,
    prevClose: r.prev_close,
    returnPct: r.return_pct,
  }));
}

// ── Correlation Matrix ─────────────────────────────────────────────

export interface CommodityCorrelationPair {
  tickerA: string;
  tickerB: string;
  correlation: number;
}

export interface RollingCorrelationPoint {
  date: string;
  correlation: number;
}

/**
 * Compute pairwise correlation matrix for commodity futures.
 * Uses daily close prices over the specified lookback window.
 */
export async function getCommodityCorrelationMatrix(
  client: DataPlatClient,
  tickers?: string[],
  days = 180,
): Promise<CommodityCorrelationPair[]> {
  // If no tickers provided, get all available
  let tickerList: string[];
  if (!tickers || tickers.length === 0) {
    const allTickers = await getCommodityTickers(client);
    tickerList = allTickers;
  } else {
    tickerList = tickers;
  }

  if (tickerList.length < 2) return [];

  const list = tickerList.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(', ');

  const sql = `
    WITH daily AS (
      SELECT ticker, date AS day, close
      FROM commodities_ohlcv FINAL
      WHERE ticker IN (${list})
        AND date >= today() - ${days}
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

  const result = await client.query<CommodityCorrelationPair>(sql);
  return result.rows;
}

/**
 * Compute cross-asset correlation matrix combining commodities and equities.
 * Joins commodity daily closes with equity daily closes for correlation analysis.
 */
export async function getCrossAssetCorrelation(
  client: DataPlatClient,
  commodityTickers: string[],
  equityTickers: string[],
  days = 180,
): Promise<CommodityCorrelationPair[]> {
  if (commodityTickers.length + equityTickers.length < 2) return [];

  const commList = commodityTickers.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(', ');
  const eqList = equityTickers.map((t) => `'${t.replace(/'/g, "\\'")}'`).join(', ');

  const sql = `
    WITH combined AS (
      SELECT ticker, date AS day, close
      FROM commodities_ohlcv FINAL
      WHERE ticker IN (${commList})
        AND date >= today() - ${days}
      UNION ALL
      SELECT ticker, day, close
      FROM ohlcv_daily_mv
      WHERE ticker IN (${eqList})
        AND day >= today() - ${days}
    )
    SELECT
      a.ticker AS tickerA,
      b.ticker AS tickerB,
      round(corr(a.close, b.close), 4) AS correlation
    FROM combined a
    JOIN combined b ON a.day = b.day
    WHERE a.ticker < b.ticker
    GROUP BY a.ticker, b.ticker
    ORDER BY a.ticker, b.ticker
  `;

  const result = await client.query<CommodityCorrelationPair>(sql);
  return result.rows;
}

// ── Rolling Correlation ────────────────────────────────────────────

interface RawRollingCorrelationRow {
  date: string;
  correlation: number;
}

/**
 * Compute rolling correlation time series between two commodity tickers.
 * Uses daily close prices with a sliding window.
 */
export async function getRollingCorrelation(
  client: DataPlatClient,
  tickerA: string,
  tickerB: string,
  windowDays = 30,
  lookbackDays = 730,
): Promise<RollingCorrelationPoint[]> {
  const escA = tickerA.replace(/'/g, "\\'");
  const escB = tickerB.replace(/'/g, "\\'");

  const sql = `
    WITH paired AS (
      SELECT
        a.date,
        a.close AS closeA,
        b.close AS closeB
      FROM commodities_ohlcv a FINAL
      JOIN commodities_ohlcv b FINAL ON a.date = b.date
      WHERE a.ticker = '${escA}' AND b.ticker = '${escB}'
        AND a.date >= today() - ${lookbackDays}
    )
    SELECT
      toString(date) AS date,
      round(corr(closeA, closeB) OVER (
        ORDER BY date
        ROWS BETWEEN ${windowDays - 1} PRECEDING AND CURRENT ROW
      ), 4) AS correlation
    FROM paired
    ORDER BY date
  `;

  const result = await client.query<RawRollingCorrelationRow>(sql);
  return result.rows;
}

// ── Commodity Movers ───────────────────────────────────────────────

export interface CommodityMover {
  ticker: string;
  name: string;
  close: number;
  changePct: number;
}

interface RawMoverRow {
  ticker: string;
  name: string;
  close: number;
  change_pct: number;
}

/**
 * Get top commodity gainers and losers for the most recent trading day.
 * Returns both top N gainers and bottom N losers.
 */
export async function getCommodityMovers(
  client: DataPlatClient,
  limit = 5,
): Promise<{ gainers: CommodityMover[]; losers: CommodityMover[] }> {
  const sql = `
    WITH latest AS (
      SELECT
        ticker,
        name,
        close,
        open,
        round((close - open) / open * 100, 2) AS change_pct
      FROM commodities_ohlcv FINAL
      WHERE date = (SELECT max(date) FROM commodities_ohlcv)
        AND open > 0
    )
    SELECT ticker, name, close, change_pct
    FROM latest
    ORDER BY change_pct DESC
  `;

  const result = await client.query<RawMoverRow>(sql);
  const all = result.rows.map((r) => ({
    ticker: r.ticker,
    name: r.name,
    close: r.close,
    changePct: r.change_pct,
  }));

  const gainers = all.filter((m) => m.changePct > 0).slice(0, limit);
  const losers = all.filter((m) => m.changePct < 0).slice(-limit).reverse();

  return { gainers, losers };
}

// ── Commodity Volatility ───────────────────────────────────────────

export interface CommodityVolatility {
  ticker: string;
  name: string;
  volatility: number;
}

interface RawVolatilityRow {
  ticker: string;
  name: string;
  volatility: number;
}

/**
 * Compute annualized realized volatility for each commodity over a lookback window.
 * Uses log returns and stddev, annualized by sqrt(252).
 */
export async function getCommodityVolatility(
  client: DataPlatClient,
  days = 30,
): Promise<CommodityVolatility[]> {
  const sql = `
    SELECT
      ticker,
      name,
      round(stddevPop(log(close / prev_close)) * sqrt(252) * 100, 2) AS volatility
    FROM (
      SELECT
        ticker,
        name,
        close,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
      FROM commodities_ohlcv FINAL
      WHERE date >= today() - ${days}
    )
    WHERE prev_close > 0
    GROUP BY ticker, name
    ORDER BY volatility DESC
  `;

  const result = await client.query<RawVolatilityRow>(sql);
  return result.rows;
}

// ── Commodity Spreads ──────────────────────────────────────────────

export interface CommoditySpread {
  name: string;
  currentValue: number;
  avgValue: number;
  pctVsAvg: number;
}

interface RawSpreadCalcRow {
  name: string;
  current_value: number;
  avg_value: number;
  pct_vs_avg: number;
}

/**
 * Calculate crack spread, crush spread, and other key commodity spreads.
 * - Crack spread: 2*RB + 1*HO - 3*CL ($/barrel, simplified 3:2:1 crack)
 * - Crush spread: ZM*0.022 + ZL*0.11 - ZS (soybean processing margin)
 * Returns current value, N-day average, and % vs average.
 */
export async function getCommoditySpreads(
  client: DataPlatClient,
  days = 90,
): Promise<CommoditySpread[]> {
  const sql = `
    WITH daily_data AS (
      SELECT
        date,
        sumIf(close, ticker = 'CL=F') AS cl,
        sumIf(close, ticker = 'RB=F') AS rb,
        sumIf(close, ticker = 'HO=F') AS ho,
        sumIf(close, ticker = 'ZS=F') AS zs,
        sumIf(close, ticker = 'ZM=F') AS zm,
        sumIf(close, ticker = 'ZL=F') AS zl,
        sumIf(close, ticker = 'GC=F') AS gold,
        sumIf(close, ticker = 'SI=F') AS silver,
        sumIf(close, ticker = 'NG=F') AS natgas
      FROM commodities_ohlcv FINAL
      WHERE date >= today() - ${days}
        AND ticker IN ('CL=F', 'RB=F', 'HO=F', 'ZS=F', 'ZM=F', 'ZL=F', 'GC=F', 'SI=F', 'NG=F')
      GROUP BY date
      HAVING cl > 0 AND rb > 0 AND ho > 0
    ),
    spreads AS (
      SELECT
        date,
        -- Crack spread: 2*RB + 1*HO - 3*CL (in $/barrel, RB/HO are $/gallon, 42 gal/barrel)
        round((2 * rb * 42 + ho * 42 - 3 * cl), 2) AS crack_spread,
        -- Crush spread: ZM*0.022 + ZL*0.11 - ZS (cents/bushel)
        CASE WHEN zs > 0 AND zm > 0 AND zl > 0
          THEN round(zm * 0.022 + zl * 0.11 - zs / 100, 2)
          ELSE NULL END AS crush_spread,
        -- Gold/Silver ratio
        CASE WHEN silver > 0 THEN round(gold / silver, 2) ELSE NULL END AS gold_silver_ratio,
        -- Crude/NatGas ratio (energy equivalent)
        CASE WHEN natgas > 0 THEN round(cl / natgas, 2) ELSE NULL END AS crude_natgas_ratio
      FROM daily_data
    ),
    latest AS (
      SELECT * FROM spreads ORDER BY date DESC LIMIT 1
    ),
    avgs AS (
      SELECT
        round(avg(crack_spread), 2) AS avg_crack,
        round(avg(crush_spread), 2) AS avg_crush,
        round(avg(gold_silver_ratio), 2) AS avg_gold_silver,
        round(avg(crude_natgas_ratio), 2) AS avg_crude_natgas
      FROM spreads
    )
    SELECT
      'Crack Spread (3:2:1)' AS name,
      latest.crack_spread AS current_value,
      avgs.avg_crack AS avg_value,
      round((latest.crack_spread - avgs.avg_crack) / avgs.avg_crack * 100, 2) AS pct_vs_avg
    FROM latest, avgs
    WHERE latest.crack_spread IS NOT NULL
    UNION ALL
    SELECT
      'Crush Spread' AS name,
      latest.crush_spread AS current_value,
      avgs.avg_crush AS avg_value,
      round((latest.crush_spread - avgs.avg_crush) / avgs.avg_crush * 100, 2) AS pct_vs_avg
    FROM latest, avgs
    WHERE latest.crush_spread IS NOT NULL AND avgs.avg_crush != 0
    UNION ALL
    SELECT
      'Gold/Silver Ratio' AS name,
      latest.gold_silver_ratio AS current_value,
      avgs.avg_gold_silver AS avg_value,
      round((latest.gold_silver_ratio - avgs.avg_gold_silver) / avgs.avg_gold_silver * 100, 2) AS pct_vs_avg
    FROM latest, avgs
    WHERE latest.gold_silver_ratio IS NOT NULL AND avgs.avg_gold_silver != 0
    UNION ALL
    SELECT
      'Crude/NatGas Ratio' AS name,
      latest.crude_natgas_ratio AS current_value,
      avgs.avg_crude_natgas AS avg_value,
      round((latest.crude_natgas_ratio - avgs.avg_crude_natgas) / avgs.avg_crude_natgas * 100, 2) AS pct_vs_avg
    FROM latest, avgs
    WHERE latest.crude_natgas_ratio IS NOT NULL AND avgs.avg_crude_natgas != 0
  `;

  const result = await client.query<RawSpreadCalcRow>(sql);
  return result.rows.map((r) => ({
    name: r.name,
    currentValue: r.current_value,
    avgValue: r.avg_value,
    pctVsAvg: r.pct_vs_avg,
  }));
}

// ── Commodity Seasonality ──────────────────────────────────────────

export interface SeasonalityPoint {
  month: number;
  avgClose: number;
  minClose: number;
  maxClose: number;
  currentYearClose: number | null;
}

interface RawSeasonalityRow {
  month: number;
  avg_close: number;
  min_close: number;
  max_close: number;
  current_year_close: number | null;
}

/**
 * Get average price by month over N years, plus current year overlay.
 * Useful for identifying seasonal patterns in commodity prices.
 */
export async function getCommoditySeasonality(
  client: DataPlatClient,
  ticker: string,
  years = 10,
): Promise<SeasonalityPoint[]> {
  const esc = ticker.replace(/'/g, "\\'");

  const sql = `
    WITH monthly AS (
      SELECT
        toMonth(date) AS month,
        toYear(date) AS year,
        avg(close) AS avg_close_month
      FROM commodities_ohlcv FINAL
      WHERE ticker = '${esc}'
        AND date >= today() - INTERVAL ${years} YEAR
      GROUP BY month, year
    ),
    historical_avg AS (
      SELECT
        month,
        round(avg(avg_close_month), 4) AS avg_close,
        round(min(avg_close_month), 4) AS min_close,
        round(max(avg_close_month), 4) AS max_close
      FROM monthly
      WHERE year < toYear(today())
      GROUP BY month
    ),
    current_year AS (
      SELECT
        month,
        round(avg_close_month, 4) AS current_year_close
      FROM monthly
      WHERE year = toYear(today())
    )
    SELECT
      h.month,
      h.avg_close,
      h.min_close,
      h.max_close,
      if(c.current_year_close = 0, NULL, c.current_year_close) AS current_year_close
    FROM historical_avg h
    LEFT JOIN current_year c ON h.month = c.month
    ORDER BY h.month
  `;

  const result = await client.query<RawSeasonalityRow>(sql);
  return result.rows.map((r) => ({
    month: r.month,
    avgClose: r.avg_close,
    minClose: r.min_close,
    maxClose: r.max_close,
    currentYearClose: r.current_year_close,
  }));
}

// ── Commodity Ratios ───────────────────────────────────────────────

export interface CommodityRatio {
  name: string;
  tickerA: string;
  tickerB: string;
  currentRatio: number;
  avgRatio: number;
  stddev: number;
  zscore: number;
}

interface RawRatioRow {
  name: string;
  ticker_a: string;
  ticker_b: string;
  current_ratio: number;
  avg_ratio: number;
  stddev: number;
  zscore: number;
}

/**
 * Calculate key commodity ratios with z-scores for mean reversion signals.
 * Ratios: Gold/Silver, Crude/NatGas, Platinum/Gold, Corn/Wheat, Copper/Gold
 * Returns current ratio, 2-year average, stddev, and z-score.
 */
export async function getCommodityRatios(
  client: DataPlatClient,
  lookbackDays = 730, // 2 years
): Promise<CommodityRatio[]> {
  const sql = `
    WITH daily_ratios AS (
      SELECT
        date,
        sumIf(close, ticker = 'GC=F') AS gold,
        sumIf(close, ticker = 'SI=F') AS silver,
        sumIf(close, ticker = 'CL=F') AS crude,
        sumIf(close, ticker = 'NG=F') AS natgas,
        sumIf(close, ticker = 'PL=F') AS platinum,
        sumIf(close, ticker = 'ZC=F') AS corn,
        sumIf(close, ticker = 'ZW=F') AS wheat,
        sumIf(close, ticker = 'HG=F') AS copper
      FROM commodities_ohlcv FINAL
      WHERE date >= today() - ${lookbackDays}
        AND ticker IN ('GC=F', 'SI=F', 'CL=F', 'NG=F', 'PL=F', 'ZC=F', 'ZW=F', 'HG=F')
      GROUP BY date
    ),
    ratios AS (
      SELECT
        date,
        CASE WHEN silver > 0 THEN gold / silver ELSE NULL END AS gold_silver,
        CASE WHEN natgas > 0 THEN crude / natgas ELSE NULL END AS crude_natgas,
        CASE WHEN gold > 0 THEN platinum / gold ELSE NULL END AS platinum_gold,
        CASE WHEN wheat > 0 THEN corn / wheat ELSE NULL END AS corn_wheat,
        CASE WHEN gold > 0 THEN copper * 100 / gold ELSE NULL END AS copper_gold -- copper in cents
      FROM daily_ratios
    ),
    stats AS (
      SELECT
        round(avg(gold_silver), 4) AS avg_gs,
        round(stddevPop(gold_silver), 4) AS std_gs,
        round(avg(crude_natgas), 4) AS avg_cn,
        round(stddevPop(crude_natgas), 4) AS std_cn,
        round(avg(platinum_gold), 4) AS avg_pg,
        round(stddevPop(platinum_gold), 4) AS std_pg,
        round(avg(corn_wheat), 4) AS avg_cw,
        round(stddevPop(corn_wheat), 4) AS std_cw,
        round(avg(copper_gold), 4) AS avg_cpg,
        round(stddevPop(copper_gold), 4) AS std_cpg
      FROM ratios
    ),
    latest AS (
      SELECT * FROM ratios ORDER BY date DESC LIMIT 1
    )
    SELECT
      'Gold/Silver' AS name,
      'GC=F' AS ticker_a,
      'SI=F' AS ticker_b,
      round(latest.gold_silver, 2) AS current_ratio,
      stats.avg_gs AS avg_ratio,
      stats.std_gs AS stddev,
      CASE WHEN stats.std_gs > 0
        THEN round((latest.gold_silver - stats.avg_gs) / stats.std_gs, 2)
        ELSE 0 END AS zscore
    FROM latest, stats
    WHERE latest.gold_silver IS NOT NULL

    UNION ALL

    SELECT
      'Crude/NatGas' AS name,
      'CL=F' AS ticker_a,
      'NG=F' AS ticker_b,
      round(latest.crude_natgas, 2) AS current_ratio,
      stats.avg_cn AS avg_ratio,
      stats.std_cn AS stddev,
      CASE WHEN stats.std_cn > 0
        THEN round((latest.crude_natgas - stats.avg_cn) / stats.std_cn, 2)
        ELSE 0 END AS zscore
    FROM latest, stats
    WHERE latest.crude_natgas IS NOT NULL

    UNION ALL

    SELECT
      'Platinum/Gold' AS name,
      'PL=F' AS ticker_a,
      'GC=F' AS ticker_b,
      round(latest.platinum_gold, 4) AS current_ratio,
      stats.avg_pg AS avg_ratio,
      stats.std_pg AS stddev,
      CASE WHEN stats.std_pg > 0
        THEN round((latest.platinum_gold - stats.avg_pg) / stats.std_pg, 2)
        ELSE 0 END AS zscore
    FROM latest, stats
    WHERE latest.platinum_gold IS NOT NULL

    UNION ALL

    SELECT
      'Corn/Wheat' AS name,
      'ZC=F' AS ticker_a,
      'ZW=F' AS ticker_b,
      round(latest.corn_wheat, 4) AS current_ratio,
      stats.avg_cw AS avg_ratio,
      stats.std_cw AS stddev,
      CASE WHEN stats.std_cw > 0
        THEN round((latest.corn_wheat - stats.avg_cw) / stats.std_cw, 2)
        ELSE 0 END AS zscore
    FROM latest, stats
    WHERE latest.corn_wheat IS NOT NULL

    UNION ALL

    SELECT
      'Copper/Gold' AS name,
      'HG=F' AS ticker_a,
      'GC=F' AS ticker_b,
      round(latest.copper_gold, 4) AS current_ratio,
      stats.avg_cpg AS avg_ratio,
      stats.std_cpg AS stddev,
      CASE WHEN stats.std_cpg > 0
        THEN round((latest.copper_gold - stats.avg_cpg) / stats.std_cpg, 2)
        ELSE 0 END AS zscore
    FROM latest, stats
    WHERE latest.copper_gold IS NOT NULL
  `;

  const result = await client.query<RawRatioRow>(sql);
  return result.rows.map((r) => ({
    name: r.name,
    tickerA: r.ticker_a,
    tickerB: r.ticker_b,
    currentRatio: r.current_ratio,
    avgRatio: r.avg_ratio,
    stddev: r.stddev,
    zscore: r.zscore,
  }));
}
