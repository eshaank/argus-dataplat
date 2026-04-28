// ── ClickHouse connection ──────────────────────────────────────────

export interface ClickHouseConfig {
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
  /** Use HTTPS (default: true for cloud, false for localhost) */
  secure?: boolean;
}

// ── OHLCV ──────────────────────────────────────────────────────────

export type OHLCVInterval = '1m' | '5m' | '15m' | '1h' | '1d';

export interface OHLCVBar {
  ticker: string;
  /** ISO timestamp string (1m/5m/15m/1h) or date string (1d) */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap: number | null;
  transactions: number | null;
}

export interface OHLCVParams {
  ticker: string;
  interval: OHLCVInterval;
  start?: string;
  end?: string;
}

export interface OHLCVMultiParams {
  tickers: string[];
  interval: OHLCVInterval;
  start?: string;
  end?: string;
}

export interface ReturnData {
  ticker: string;
  startPrice: number;
  endPrice: number;
  returnPct: number;
}

export interface LatestPrice {
  ticker: string;
  date: string;
  close: number;
  prevClose: number;
  changePct: number;
  volume: number;
}

// ── Financials ─────────────────────────────────────────────────────

export type FiscalPeriod = 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'FY';
export type FinancialTimeframe = 'annual' | 'quarterly';

export interface Financial {
  ticker: string;
  cik: string | null;
  periodStart: string | null;
  periodEnd: string;
  fiscalYear: string;
  fiscalPeriod: string;
  formType: string;
  filedDate: string | null;
  accessionNumber: string | null;

  // Income statement
  revenue: number | null;
  costOfRevenue: number | null;
  grossProfit: number | null;
  operatingExpenses: number | null;
  operatingIncome: number | null;
  netIncome: number | null;
  basicEps: number | null;
  dilutedEps: number | null;
  researchAndDev: number | null;
  sgaExpenses: number | null;
  incomeTax: number | null;
  interestExpense: number | null;
  ebitda: number | null;

  // Balance sheet
  totalAssets: number | null;
  currentAssets: number | null;
  noncurrentAssets: number | null;
  totalLiabilities: number | null;
  currentLiabilities: number | null;
  noncurrentLiabilities: number | null;
  totalEquity: number | null;
  retainedEarnings: number | null;
  longTermDebt: number | null;
  shortTermDebt: number | null;
  cashAndEquivalents: number | null;
  inventory: number | null;
  accountsReceivable: number | null;
  accountsPayable: number | null;
  goodwill: number | null;

  // Cash flow
  operatingCashFlow: number | null;
  investingCashFlow: number | null;
  financingCashFlow: number | null;
  capex: number | null;
  dividendsPaid: number | null;
  depreciationAmortization: number | null;

  // Dilution & shares
  sharesOutstanding: number | null;
  weightedAvgSharesBasic: number | null;
  weightedAvgSharesDiluted: number | null;
  stockBasedCompensation: number | null;
  buybackValue: number | null;
  dividendsPerShare: number | null;

  // Derived (computed by SDK for backward compat)
  timeframe: 'annual' | 'quarterly';
}

export interface FinancialsParams {
  ticker: string;
  timeframe?: FinancialTimeframe;
  fiscalYear?: string;
  fiscalPeriod?: FiscalPeriod;
  limit?: number;
}

export interface MetricParams {
  tickers: string[];
  metric: keyof Financial;
  timeframe?: FinancialTimeframe;
  limit?: number;
}

export interface MetricDataPoint {
  ticker: string;
  periodEnd: string;
  fiscalYear: string;
  fiscalPeriod: string;
  value: number | null;
}

// ── Universe ───────────────────────────────────────────────────────

export interface UniverseEntry {
  ticker: string;
  name: string;
  type: string;
  exchange: string;
  micCode: string | null;
  sector: string | null;
  sicCode: string | null;
  marketCap: number | null;
  active: boolean;
  description: string | null;
  homepageUrl: string | null;
  totalEmployees: number | null;
  listDate: string | null;
  cik: string | null;
  sicDescription: string | null;
  addressCity: string | null;
  addressState: string | null;
}

export interface UniverseFilters {
  sector?: string;
  exchange?: string;
  type?: string;
  active?: boolean;
  minMarketCap?: number;
  maxMarketCap?: number;
}

export interface SectorSummary {
  sector: string;
  tickerCount: number;
  totalMarketCap: number;
}

// ── Dividends ──────────────────────────────────────────────────────

export interface Dividend {
  ticker: string;
  exDividendDate: string;
  declarationDate: string | null;
  recordDate: string | null;
  payDate: string | null;
  cashAmount: number;
  currency: string;
  frequency: number;
  dividendType: string;
}

// ── Stock Splits ───────────────────────────────────────────────────

export interface StockSplit {
  ticker: string;
  executionDate: string;
  splitFrom: number;
  splitTo: number;
}

// ── Macro / Economic ───────────────────────────────────────────────

export interface TreasuryYield {
  date: string;
  yield1Month: number | null;
  yield3Month: number | null;
  yield1Year: number | null;
  yield2Year: number | null;
  yield5Year: number | null;
  yield10Year: number | null;
  yield30Year: number | null;
}

export interface YieldCurvePoint {
  maturity: string;
  yield: number | null;
}

export interface InflationData {
  date: string;
  cpi: number | null;
  cpiCore: number | null;
  pce: number | null;
  pceCore: number | null;
  pceSpending: number | null;
}

export interface LaborMarketData {
  date: string;
  unemploymentRate: number | null;
  laborForceParticipationRate: number | null;
  avgHourlyEarnings: number | null;
  jobOpenings: number | null;
}

export interface InflationExpectation {
  date: string;
  market5Year: number | null;
  market10Year: number | null;
  forwardYears5To10: number | null;
  model1Year: number | null;
  model5Year: number | null;
  model10Year: number | null;
  model30Year: number | null;
}

export interface DateRangeParams {
  start?: string;
  end?: string;
}

// ── Options ────────────────────────────────────────────────────────

export type PutCall = 'call' | 'put';

export interface OptionContract {
  underlying: string;
  expiration: string;
  strike: number;
  putCall: PutCall;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
  tradeCount: number;
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
  // First-order greeks
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
  // Second-order greeks
  vanna: number | null;
  charm: number | null;
  vomma: number | null;
  veta: number | null;
  // Third-order greeks
  speed: number | null;
  zomma: number | null;
  color: number | null;
  ultima: number | null;
  // Other
  epsilon: number | null;
  lambda: number | null;
  vera: number | null;
  impliedVol: number;
  ivError: number | null;
  openInterest: number;
  underlyingPrice: number | null;
  snapshotDate: string;
}

export interface OptionChain {
  underlying: string;
  expiration: string;
  snapshotDate: string;
  calls: OptionContract[];
  puts: OptionContract[];
}

export interface IVSurfacePoint {
  expiration: string;
  strike: number;
  impliedVol: number;
  delta: number;
  putCall: PutCall;
  volume: number;
  openInterest: number;
}

export interface GreeksSnapshot {
  strike: number;
  putCall: PutCall;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
  vanna: number | null;
  charm: number | null;
  vomma: number | null;
  veta: number | null;
  speed: number | null;
  zomma: number | null;
  color: number | null;
  ultima: number | null;
}

export interface OIProfilePoint {
  strike: number;
  callOI: number;
  putOI: number;
}

export interface VolumeProfilePoint {
  strike: number;
  callVolume: number;
  putVolume: number;
}

export interface OptionChainParams {
  underlying: string;
  expiration: string;
  snapshotDate?: string;
}

export interface OptionSurfaceParams {
  underlying: string;
  snapshotDate?: string;
}

// ── Raw SQL ────────────────────────────────────────────────────────

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  rowCount: number;
  elapsedMs: number;
}

export interface SchemaColumn {
  table: string;
  name: string;
  type: string;
}

// ── Flow Surface ───────────────────────────────────────────────────

export interface FlowSurfacePoint {
  expiration: string;      // ISO date (e.g., "2026-04-11")
  strike: number;
  dte: number;             // Days to expiration
  bullishNotional: number; // Total $ bullish flow
  bearishNotional: number; // Total $ bearish flow
  netFlow: number;         // bullish - bearish (positive = bullish, negative = bearish)
  biasRatio: number;       // -1 (all bearish) to +1 (all bullish), normalized
}

export interface FlowSurfaceResult {
  tradeDate: string;       // Date of the flow data (for UI display)
  points: FlowSurfacePoint[];
}

export interface FlowSurfaceParams {
  underlying: string;
  tradeDate?: string;      // ISO date; defaults to latest available
}
