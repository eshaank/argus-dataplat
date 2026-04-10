import type { DataPlatClient } from '../client.js';
import type { DateRangeParams } from '../types.js';

// ── Types ──────────────────────────────────────────────────────────

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
    FROM commodity_prices
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
    SELECT ticker, name, toString(date) AS date, open, high, low, close, volume
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
    SELECT ticker, name, toString(date) AS date, open, high, low, close, volume
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
    SELECT ticker, name, toString(date) AS date, open, high, low, close, volume
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
    SELECT DISTINCT ticker FROM commodities_ohlcv ORDER BY ticker
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
