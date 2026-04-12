// ── Client ──────────────────────────────────────────────────────────
export { DataPlatClient } from './client.js';

// ── Types ───────────────────────────────────────────────────────────
export type {
  ClickHouseConfig,
  OHLCVInterval,
  OHLCVBar,
  OHLCVParams,
  OHLCVMultiParams,
  ReturnData,
  LatestPrice,
  FiscalPeriod,
  FinancialTimeframe,
  Financial,
  FinancialsParams,
  MetricParams,
  MetricDataPoint,
  UniverseEntry,
  UniverseFilters,
  SectorSummary,
  Dividend,
  StockSplit,
  TreasuryYield,
  YieldCurvePoint,
  InflationData,
  LaborMarketData,
  InflationExpectation,
  DateRangeParams,
  PutCall,
  OptionContract,
  OptionChain,
  IVSurfacePoint,
  GreeksSnapshot,
  OIProfilePoint,
  VolumeProfilePoint,
  OptionChainParams,
  OptionSurfaceParams,
  FlowSurfacePoint,
  FlowSurfaceResult,
  FlowSurfaceParams,
  QueryResult,
  SchemaColumn,
} from './types.js';

// ── Queries: OHLCV ──────────────────────────────────────────────────
export { getOHLCV, getOHLCVMulti, getReturns, getLatestPrices } from './queries/ohlcv.js';

// ── Queries: Financials ─────────────────────────────────────────────
export {
  getFinancials,
  getIncomeStatement,
  getBalanceSheet,
  getCashFlow,
  getMetric,
} from './queries/financials.js';

// ── Queries: Universe ───────────────────────────────────────────────
export {
  getUniverse,
  searchTickers,
  getTicker,
  getSectors,
  getTickersBySector,
} from './queries/universe.js';

// ── Queries: Dividends ──────────────────────────────────────────────
export { getDividends, getDividendCalendar } from './queries/dividends.js';

// ── Queries: Splits ─────────────────────────────────────────────────
export { getSplits } from './queries/splits.js';

// ── Queries: Macro ──────────────────────────────────────────────────
export {
  getTreasuryYields,
  getYieldCurve,
  getYieldCurveTimeSeries,
  getInflation,
  getLaborMarket,
  getInflationExpectations,
} from './queries/macro.js';

// ── Queries: Options ────────────────────────────────────────────────
export {
  getOptionChain,
  getExpirations,
  getIVSurface,
  getIVSkew,
  getGreeksSnapshot,
  getIVHistory,
  getOpenInterestProfile,
  getVolumeProfile,
  getLatestTradeDate,
  getFlowSurface,
} from './queries/options.js';

// ── Queries: Market ─────────────────────────────────────────────────
export {
  getTopMovers,
  getMostActive,
  getSectorPerformance,
  getTreemapData,
  getMomentumVelocity,
  getScreenerData,
  getCorrelationMatrix,
  getSparkline,
  getSparklines,
} from './queries/market.js';

export type {
  Mover,
  SectorPerformance,
  TreemapTicker,
  MomentumBar,
  ScreenerRow,
  CorrelationPair,
  MiniBar,
} from './queries/market.js';

// ── Queries: Derivatives ───────────────────────────────────────────
export {
  getATMIVHistory,
  getIVGauge,
  getPutCallRatio,
  getGEX,
  getIVTermStructure,
  getSkewHistory,
  getUnusualActivity,
  getVolumeGtOI,
  getChainTable,
  getHVvsIV,
  getOIWalls,
} from './queries/derivatives.js';

export type {
  ATMIVPoint,
  IVGauge,
  PutCallRatioPoint,
  GEXPoint,
  TermStructurePoint,
  SkewPoint,
  UnusualContract,
  ChainRow,
  HVvsIVPoint,
  OIWallPoint,
} from './queries/derivatives.js';

// ── Queries: Signals ────────────────────────────────────────────────
export {
  getMarketBreadth,
  get52WeekHighLowCounts,
  get52WeekHighs,
  get52WeekLows,
  getDividendChanges,
  getNotableInsiderBuys,
  getUpcomingDividends,
} from './queries/signals.js';

export type {
  MarketBreadth,
  HighLowCounts,
  HighLowTicker,
  DividendChange,
  NotableInsiderBuy,
  UpcomingDividend,
} from './queries/signals.js';

// ── Queries: SEC ────────────────────────────────────────────────────
export {
  getInsiderTrades,
  getInsiderMonthly,
  getInstitutionalHolders,
  getMaterialEvents,
  getSecFilings,
  getDilutionSnapshot,
  getDilutionTimeSeries,
} from './queries/sec.js';

export type {
  InsiderTrade,
  InsiderMonthly,
  InstitutionalHolder,
  MaterialEvent,
  SecFiling,
  DilutionSnapshot,
  DilutionTimeSeriesPoint,
} from './queries/sec.js';

// ── Queries: Commodities & Energy ───────────────────────────────────
export {
  getEnergySpotPrices,
  getEnergySpotLatest,
  getCommodityOHLCV,
  getCommodityOHLCVMulti,
  getCommodityLatest,
  getCommodityReturns,
  getCommodityTickers,
  getBrentWTISpread,
  getPetroleumWeekly,
  getPetroleumStocksVs5Yr,
  getOPECShare,
  getPersianGulfDependency,
} from './queries/commodities.js';

export type {
  EnergySpotPrice,
  EnergySpotLatest,
  CommodityOHLCV,
  CommodityLatest,
  CommodityReturn,
  BrentWTISpread,
  PetroleumWeekly,
  PetroleumStocksVs5Yr,
  OPECShare,
  PersianGulfDependency,
} from './queries/commodities.js';

// ── Queries: Raw SQL (ad-hoc exploration only) ──────────────────────
export { rawQuery, getSchema } from './queries/sql.js';

// ── Utils ───────────────────────────────────────────────────────────
export {
  formatCurrency,
  formatLargeNumber,
  formatPercent,
  formatDate,
  formatDateCompact,
  formatVolume,
} from './utils/formatting.js';

export {
  normalizeToBase100,
  computeCumulativeReturns,
  computeSMA,
  computeEMA,
  computeBollingerBands,
  computeRSI,
  computeMACD,
  computeYoYGrowth,
  computeMargins,
} from './utils/transforms.js';
