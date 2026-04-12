import type { DataPlatClient } from '../client.js';
import type {
  OptionContract,
  OptionChain,
  IVSurfacePoint,
  GreeksSnapshot,
  OIProfilePoint,
  VolumeProfilePoint,
  OptionChainParams,
  OptionSurfaceParams,
  PutCall,
  FlowSurfacePoint,
  FlowSurfaceResult,
  FlowSurfaceParams,
} from '../types.js';

function esc(s: string): string {
  return s.replace(/'/g, "\\'");
}

/** Resolves snapshot date — defaults to latest available. */
function snapshotFilter(snapshotDate?: string): string {
  if (snapshotDate) return `AND snapshot_date = '${snapshotDate}'`;
  return '';
}

/** Subquery to get the latest snapshot date for an underlying. */
function latestSnapshotSubquery(underlying: string): string {
  return `(SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')`;
}

// ── Raw row type (snake_case from ClickHouse) ──────────────────────

interface RawOptionRow {
  underlying: string;
  expiration: string;
  strike: number;
  put_call: 'call' | 'put';
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
  trade_count: number;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
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
  epsilon: number | null;
  lambda: number | null;
  vera: number | null;
  implied_vol: number;
  iv_error: number | null;
  open_interest: number;
  underlying_price: number | null;
  snapshot_date: string;
}

function mapContract(r: RawOptionRow): OptionContract {
  return {
    underlying: r.underlying,
    expiration: r.expiration,
    strike: r.strike,
    putCall: r.put_call,
    open: r.open,
    high: r.high,
    low: r.low,
    close: r.close,
    volume: r.volume,
    tradeCount: r.trade_count,
    bid: r.bid,
    ask: r.ask,
    bidSize: r.bid_size,
    askSize: r.ask_size,
    delta: r.delta,
    gamma: r.gamma,
    theta: r.theta,
    vega: r.vega,
    rho: r.rho,
    vanna: r.vanna,
    charm: r.charm,
    vomma: r.vomma,
    veta: r.veta,
    speed: r.speed,
    zomma: r.zomma,
    color: r.color,
    ultima: r.ultima,
    epsilon: r.epsilon,
    lambda: r.lambda,
    vera: r.vera,
    impliedVol: r.implied_vol,
    ivError: r.iv_error,
    openInterest: r.open_interest,
    underlyingPrice: r.underlying_price,
    snapshotDate: r.snapshot_date,
  };
}

const ALL_COLS = `
  underlying, toString(expiration) AS expiration, strike, put_call,
  open, high, low, close, volume, trade_count,
  bid, ask, bid_size, ask_size,
  delta, gamma, theta, vega, rho,
  vanna, charm, vomma, veta,
  speed, zomma, color, ultima,
  epsilon, lambda, vera,
  implied_vol, iv_error, open_interest, underlying_price,
  toString(snapshot_date) AS snapshot_date
`;

// ── Public API ─────────────────────────────────────────────────────

/** Full option chain for one underlying + expiration. */
export async function getOptionChain(
  client: DataPlatClient,
  params: OptionChainParams,
): Promise<OptionChain> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT ${ALL_COLS}
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      AND expiration = '${params.expiration}'
      ${snapshotClause}
    ORDER BY strike, put_call
  `;

  const result = await client.query<RawOptionRow>(sql);
  const contracts = result.rows.map(mapContract);

  return {
    underlying: params.underlying,
    expiration: params.expiration,
    snapshotDate: contracts[0]?.snapshotDate ?? params.snapshotDate ?? '',
    calls: contracts.filter((c) => c.putCall === 'call'),
    puts: contracts.filter((c) => c.putCall === 'put'),
  };
}

/** Available expiration dates for an underlying. */
export async function getExpirations(
  client: DataPlatClient,
  underlying: string,
  snapshotDate?: string,
): Promise<string[]> {
  const snapshotClause = snapshotDate
    ? `AND snapshot_date = '${snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(underlying)}`;

  const sql = `
    SELECT DISTINCT toString(expiration) AS expiration
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      ${snapshotClause}
    ORDER BY expiration
  `;

  const result = await client.query<{ expiration: string }>(sql);
  return result.rows.map((r) => r.expiration);
}

/** IV surface data: IV by strike × expiration. */
export async function getIVSurface(
  client: DataPlatClient,
  params: OptionSurfaceParams,
): Promise<IVSurfacePoint[]> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT
      toString(expiration) AS expiration,
      strike,
      implied_vol AS impliedVol,
      delta,
      put_call AS putCall,
      volume,
      open_interest AS openInterest
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      ${snapshotClause}
      AND implied_vol > 0
    ORDER BY expiration, strike
  `;

  const result = await client.query<IVSurfacePoint>(sql);
  return result.rows;
}

/** IV skew: IV vs strike for a single expiration. */
export async function getIVSkew(
  client: DataPlatClient,
  params: OptionChainParams,
): Promise<IVSurfacePoint[]> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT
      toString(expiration) AS expiration,
      strike,
      implied_vol AS impliedVol,
      delta,
      put_call AS putCall,
      volume,
      open_interest AS openInterest
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      AND expiration = '${params.expiration}'
      ${snapshotClause}
      AND implied_vol > 0
    ORDER BY strike
  `;

  const result = await client.query<IVSurfacePoint>(sql);
  return result.rows;
}

/** Full greeks snapshot for one expiration. */
export async function getGreeksSnapshot(
  client: DataPlatClient,
  params: OptionChainParams,
): Promise<GreeksSnapshot[]> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT
      strike, put_call AS putCall,
      delta, gamma, theta, vega, rho,
      vanna, charm, vomma, veta,
      speed, zomma, color, ultima
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      AND expiration = '${params.expiration}'
      ${snapshotClause}
    ORDER BY strike, put_call
  `;

  const result = await client.query<GreeksSnapshot>(sql);
  return result.rows;
}

/** IV history for a single contract over time. */
export async function getIVHistory(
  client: DataPlatClient,
  underlying: string,
  strike: number,
  expiration: string,
  putCall: PutCall,
): Promise<{ date: string; impliedVol: number }[]> {
  const pcVal = putCall === 'call' ? 'call' : 'put';

  const sql = `
    SELECT
      toString(snapshot_date) AS date,
      implied_vol AS impliedVol
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      AND strike = ${strike}
      AND expiration = '${expiration}'
      AND put_call = '${pcVal}'
    ORDER BY snapshot_date
  `;

  const result = await client.query<{ date: string; impliedVol: number }>(sql);
  return result.rows;
}

/** Open interest by strike — calls vs puts. */
export async function getOpenInterestProfile(
  client: DataPlatClient,
  params: OptionChainParams,
): Promise<OIProfilePoint[]> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT
      strike,
      sumIf(open_interest, put_call = 'call') AS callOI,
      sumIf(open_interest, put_call = 'put') AS putOI
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      AND expiration = '${params.expiration}'
      ${snapshotClause}
    GROUP BY strike
    ORDER BY strike
  `;

  const result = await client.query<OIProfilePoint>(sql);
  return result.rows;
}

/** Volume by strike — calls vs puts. */
export async function getVolumeProfile(
  client: DataPlatClient,
  params: OptionChainParams,
): Promise<VolumeProfilePoint[]> {
  const snapshotClause = params.snapshotDate
    ? `AND snapshot_date = '${params.snapshotDate}'`
    : `AND snapshot_date = ${latestSnapshotSubquery(params.underlying)}`;

  const sql = `
    SELECT
      strike,
      sumIf(volume, put_call = 'call') AS callVolume,
      sumIf(volume, put_call = 'put') AS putVolume
    FROM option_chains
    WHERE underlying = '${esc(params.underlying)}'
      AND expiration = '${params.expiration}'
      ${snapshotClause}
    GROUP BY strike
    ORDER BY strike
  `;

  const result = await client.query<VolumeProfilePoint>(sql);
  return result.rows;
}

// ── Flow Surface (tick-level directional flow) ─────────────────────

const FLOW_SURFACE_QUERY = `
SELECT 
    toInt32(dateDiff('day', toDate({trade_date:Date}), expiration)) AS dte,
    toString(expiration) AS exp_str,
    strike,
    sum(CASE 
        WHEN (put_call = 'call' AND aggressor_side = 'buy') 
          OR (put_call = 'put' AND aggressor_side = 'sell')
        THEN notional
        WHEN aggressor_side = 'mid' THEN notional * 0.25
        ELSE 0 
    END) AS bullish_notional,
    sum(CASE 
        WHEN (put_call = 'call' AND aggressor_side = 'sell') 
          OR (put_call = 'put' AND aggressor_side = 'buy')
        THEN notional
        WHEN aggressor_side = 'mid' THEN notional * 0.25
        ELSE 0 
    END) AS bearish_notional,
    bullish_notional - bearish_notional AS net_flow,
    (bullish_notional - bearish_notional) / NULLIF(bullish_notional + bearish_notional, 0) AS bias_ratio
FROM option_trades
WHERE underlying = {underlying:String}
  AND trade_date = {trade_date:Date}
  AND expiration >= {trade_date:Date}
GROUP BY expiration, strike
HAVING bullish_notional + bearish_notional >= 10000
ORDER BY expiration, strike
`;

interface RawFlowRow {
  exp_str: string;
  strike: number;
  dte: number;
  bullish_notional: number;
  bearish_notional: number;
  net_flow: number;
  bias_ratio: number | null;
}

/** Get the latest trade date for flow data. */
export async function getLatestTradeDate(
  client: DataPlatClient,
  underlying: string,
): Promise<string | null> {
  const sql = `
    SELECT toString(max(trade_date)) AS latest_date
    FROM option_trades
    WHERE underlying = '${esc(underlying)}'
  `;
  const result = await client.query<{ latest_date: string }>(sql);
  const date = result.rows[0]?.latest_date;
  return date && date !== '1970-01-01' ? date : null;
}

/** Flow surface: net directional positioning by strike × expiration. */
export async function getFlowSurface(
  client: DataPlatClient,
  params: FlowSurfaceParams,
): Promise<FlowSurfaceResult> {
  // If no date provided, get latest
  const tradeDate = params.tradeDate ?? (await getLatestTradeDate(client, params.underlying));
  if (!tradeDate) return { tradeDate: '', points: [] };

  const sql = FLOW_SURFACE_QUERY
    .replace(/{underlying:String}/g, `'${esc(params.underlying)}'`)
    .replace(/{trade_date:Date}/g, `'${tradeDate}'`);

  const result = await client.query<RawFlowRow>(sql);

  const points: FlowSurfacePoint[] = result.rows.map((row) => ({
    expiration: row.exp_str,
    strike: row.strike,
    dte: row.dte,
    bullishNotional: row.bullish_notional,
    bearishNotional: row.bearish_notional,
    netFlow: row.net_flow,
    biasRatio: row.bias_ratio ?? 0,
  }));

  return { tradeDate, points };
}
