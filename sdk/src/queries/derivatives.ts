/**
 * Derivatives analytics: IV percentile, put/call ratio, GEX, skew, term structure.
 * All computed from the option_chains table via ClickHouse aggregations.
 */
import type { DataPlatClient } from '../client.js';

function esc(s: string): string {
  return s.replace(/'/g, "\\'");
}

// ── Types ──────────────────────────────────────────────────────────

export interface ATMIVPoint {
  date: string;
  iv: number;
}

export interface IVGauge {
  currentIV: number;
  percentileRank: number;
  min1Y: number;
  max1Y: number;
  avg1Y: number;
}

export interface PutCallRatioPoint {
  date: string;
  putVolume: number;
  callVolume: number;
  ratio: number;
}

export interface GEXPoint {
  strike: number;
  netGamma: number;
  callGamma: number;
  putGamma: number;
}

export interface TermStructurePoint {
  expiration: string;
  dte: number;
  iv: number;
}

export interface SkewPoint {
  date: string;
  putIV25d: number;
  callIV25d: number;
  skew: number;
}

export interface OIWallPoint {
  strike: number;
  callOI: number;
  putOI: number;
  totalOI: number;
}

// ── ATM IV History ─────────────────────────────────────────────────

/** ATM 30-DTE implied vol per day — for IV time series and percentile gauge. */
export async function getATMIVHistory(
  client: DataPlatClient,
  underlying: string,
  days = 365,
): Promise<ATMIVPoint[]> {
  const sql = `
    SELECT
      toString(snapshot_date) AS date,
      round(avg(implied_vol), 4) AS iv
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      AND put_call = 'call'
      AND abs(delta) BETWEEN 0.40 AND 0.60
      AND (expiration - snapshot_date) BETWEEN 20 AND 40
      AND implied_vol > 0
      AND snapshot_date >= today() - ${days}
    GROUP BY snapshot_date
    ORDER BY snapshot_date
  `;

  const result = await client.query<ATMIVPoint>(sql);
  return result.rows;
}

// ── IV Gauge ───────────────────────────────────────────────────────

/** Current ATM IV with 1Y percentile rank, min, max, avg. */
export async function getIVGauge(
  client: DataPlatClient,
  underlying: string,
): Promise<IVGauge | null> {
  const sql = `
    WITH daily_iv AS (
      SELECT
        snapshot_date,
        round(avg(implied_vol), 4) AS iv
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND put_call = 'call'
        AND abs(delta) BETWEEN 0.40 AND 0.60
        AND (expiration - snapshot_date) BETWEEN 20 AND 40
        AND implied_vol > 0
        AND snapshot_date >= today() - 365
      GROUP BY snapshot_date
    ),
    current AS (
      SELECT iv FROM daily_iv ORDER BY snapshot_date DESC LIMIT 1
    ),
    stats AS (
      SELECT
        min(iv) AS min1Y,
        max(iv) AS max1Y,
        round(avg(iv), 4) AS avg1Y,
        count() AS total_days
      FROM daily_iv
    ),
    rank AS (
      SELECT countIf(iv <= (SELECT iv FROM current)) AS below
      FROM daily_iv
    )
    SELECT
      (SELECT iv FROM current) AS currentIV,
      round(below / greatest(total_days, 1) * 100, 1) AS percentileRank,
      min1Y,
      max1Y,
      avg1Y
    FROM stats, rank
  `;

  const result = await client.query<IVGauge>(sql);
  return result.rows[0] ?? null;
}

// ── Put/Call Ratio ─────────────────────────────────────────────────

/** Daily put/call volume ratio. */
export async function getPutCallRatio(
  client: DataPlatClient,
  underlying: string,
  days = 90,
): Promise<PutCallRatioPoint[]> {
  const sql = `
    SELECT
      toString(snapshot_date) AS date,
      sumIf(volume, put_call = 'put') AS putVolume,
      sumIf(volume, put_call = 'call') AS callVolume,
      round(
        sumIf(volume, put_call = 'put') / greatest(sumIf(volume, put_call = 'call'), 1),
        3
      ) AS ratio
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      AND snapshot_date >= today() - ${days}
    GROUP BY snapshot_date
    ORDER BY snapshot_date
  `;

  const result = await client.query<PutCallRatioPoint>(sql);
  return result.rows;
}

// ── GEX (Gamma Exposure) ───────────────────────────────────────────

/** Net gamma exposure by strike — market maker positioning. */
export async function getGEX(
  client: DataPlatClient,
  underlying: string,
  snapshotDate?: string,
): Promise<GEXPoint[]> {
  const dateClause = snapshotDate
    ? `AND snapshot_date = '${snapshotDate}'`
    : `AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')`;

  const sql = `
    SELECT
      strike,
      round(sumIf(gamma * open_interest * 100, put_call = 'call'), 2) AS callGamma,
      round(sumIf(gamma * open_interest * 100, put_call = 'put'), 2) AS putGamma,
      round(
        sumIf(gamma * open_interest * 100, put_call = 'call')
        - sumIf(gamma * open_interest * 100, put_call = 'put'),
        2
      ) AS netGamma
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      ${dateClause}
      AND (expiration - snapshot_date) <= 45
      AND open_interest > 0
    GROUP BY strike
    HAVING abs(netGamma) > 0
    ORDER BY strike
  `;

  const result = await client.query<GEXPoint>(sql);
  return result.rows;
}

// ── IV Term Structure ──────────────────────────────────────────────

/** ATM IV per expiration — the volatility curve. */
export async function getIVTermStructure(
  client: DataPlatClient,
  underlying: string,
  snapshotDate?: string,
): Promise<TermStructurePoint[]> {
  const dateClause = snapshotDate
    ? `AND snapshot_date = '${snapshotDate}'`
    : `AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')`;

  const sql = `
    SELECT
      toString(expiration) AS expiration,
      toUInt32(toDate(expiration) - toDate(snapshot_date)) AS dte,
      round(avg(implied_vol), 4) AS iv
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      ${dateClause}
      AND put_call = 'call'
      AND abs(delta) BETWEEN 0.35 AND 0.65
      AND implied_vol > 0
    GROUP BY expiration, snapshot_date
    HAVING dte > 0 AND dte <= 365
    ORDER BY dte
  `;

  const result = await client.query<TermStructurePoint>(sql);
  return result.rows;
}

// ── Skew History ───────────────────────────────────────────────────

/** 25-delta skew: OTM put IV minus OTM call IV over time. */
export async function getSkewHistory(
  client: DataPlatClient,
  underlying: string,
  days = 180,
): Promise<SkewPoint[]> {
  const sql = `
    WITH daily AS (
      SELECT
        snapshot_date,
        avgIf(implied_vol, put_call = 'put' AND delta BETWEEN -0.30 AND -0.20
          AND (expiration - snapshot_date) BETWEEN 20 AND 40) AS putIV25d,
        avgIf(implied_vol, put_call = 'call' AND delta BETWEEN 0.20 AND 0.30
          AND (expiration - snapshot_date) BETWEEN 20 AND 40) AS callIV25d
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND implied_vol > 0
        AND snapshot_date >= today() - ${days}
      GROUP BY snapshot_date
    )
    SELECT
      toString(snapshot_date) AS date,
      round(putIV25d, 4) AS putIV25d,
      round(callIV25d, 4) AS callIV25d,
      round(putIV25d - callIV25d, 4) AS skew
    FROM daily
    WHERE putIV25d > 0 AND callIV25d > 0
    ORDER BY snapshot_date
  `;

  const result = await client.query<SkewPoint>(sql);
  return result.rows;
}

// ── OI Walls ───────────────────────────────────────────────────────

// ── Unusual Activity ───────────────────────────────────────────────

export interface UnusualContract {
  underlying: string;
  expiration: string;
  strike: number;
  putCall: 'call' | 'put';
  volume: number;
  openInterest: number;
  avgVolume20d: number;
  volRatio: number;
  impliedVol: number;
  delta: number;
  bid: number;
  ask: number;
  underlyingPrice: number | null;
  dte: number;
}

/** Contracts with volume significantly above 20-day average. */
export async function getUnusualActivity(
  client: DataPlatClient,
  underlying: string,
  minVolRatio = 3,
  minVolume = 500,
  limit = 30,
): Promise<UnusualContract[]> {
  const sql = `
    WITH hist AS (
      SELECT underlying, expiration, strike, put_call,
        avg(volume) AS avg_vol
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND snapshot_date BETWEEN (
          SELECT max(snapshot_date) - 25 FROM option_chains WHERE underlying = '${esc(underlying)}'
        ) AND (
          SELECT max(snapshot_date) - 1 FROM option_chains WHERE underlying = '${esc(underlying)}'
        )
      GROUP BY underlying, expiration, strike, put_call
      HAVING avg_vol > 0
    ),
    latest AS (
      SELECT *
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')
    )
    SELECT
      l.underlying,
      toString(l.expiration) AS expiration,
      l.strike,
      l.put_call AS putCall,
      l.volume,
      l.open_interest AS openInterest,
      round(h.avg_vol, 0) AS avgVolume20d,
      round(l.volume / greatest(h.avg_vol, 1), 1) AS volRatio,
      round(l.implied_vol, 4) AS impliedVol,
      round(l.delta, 3) AS delta,
      l.bid,
      l.ask,
      l.underlying_price AS underlyingPrice,
      toUInt32(toDate(l.expiration) - toDate(l.snapshot_date)) AS dte
    FROM latest l
    JOIN hist h ON l.underlying = h.underlying
      AND l.expiration = h.expiration
      AND l.strike = h.strike
      AND l.put_call = h.put_call
    WHERE l.volume >= ${minVolume}
      AND l.volume / greatest(h.avg_vol, 1) >= ${minVolRatio}
    ORDER BY volRatio DESC
    LIMIT ${limit}
  `;

  const result = await client.query<UnusualContract>(sql);
  return result.rows;
}

/** Contracts where volume exceeds open interest (new positions). */
export async function getVolumeGtOI(
  client: DataPlatClient,
  underlying: string,
  minVolume = 500,
  limit = 20,
): Promise<UnusualContract[]> {
  const sql = `
    WITH hist AS (
      SELECT underlying, expiration, strike, put_call,
        avg(volume) AS avg_vol
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND snapshot_date BETWEEN (
          SELECT max(snapshot_date) - 25 FROM option_chains WHERE underlying = '${esc(underlying)}'
        ) AND (
          SELECT max(snapshot_date) - 1 FROM option_chains WHERE underlying = '${esc(underlying)}'
        )
      GROUP BY underlying, expiration, strike, put_call
      HAVING avg_vol > 0
    ),
    latest AS (
      SELECT *
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')
        AND volume > open_interest
        AND volume >= ${minVolume}
    )
    SELECT
      l.underlying,
      toString(l.expiration) AS expiration,
      l.strike,
      l.put_call AS putCall,
      l.volume,
      l.open_interest AS openInterest,
      round(coalesce(h.avg_vol, 0), 0) AS avgVolume20d,
      round(l.volume / greatest(coalesce(h.avg_vol, 1), 1), 1) AS volRatio,
      round(l.implied_vol, 4) AS impliedVol,
      round(l.delta, 3) AS delta,
      l.bid,
      l.ask,
      l.underlying_price AS underlyingPrice,
      toUInt32(toDate(l.expiration) - toDate(l.snapshot_date)) AS dte
    FROM latest l
    LEFT JOIN hist h ON l.underlying = h.underlying
      AND l.expiration = h.expiration
      AND l.strike = h.strike
      AND l.put_call = h.put_call
    ORDER BY l.volume DESC
    LIMIT ${limit}
  `;

  const result = await client.query<UnusualContract>(sql);
  return result.rows;
}

// ── Chain Table ────────────────────────────────────────────────────

export interface ChainRow {
  strike: number;
  callBid: number;
  callAsk: number;
  callLast: number | null;
  callVolume: number;
  callOI: number;
  callIV: number;
  callDelta: number;
  callAvgVol: number;
  putBid: number;
  putAsk: number;
  putLast: number | null;
  putVolume: number;
  putOI: number;
  putIV: number;
  putDelta: number;
  putAvgVol: number;
}

/** Full chain for one expiration with historical volume averages for flagging. */
export async function getChainTable(
  client: DataPlatClient,
  underlying: string,
  expiration: string,
): Promise<ChainRow[]> {
  const sql = `
    WITH hist AS (
      SELECT expiration, strike, put_call,
        avg(volume) AS avg_vol
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND expiration = '${expiration}'
        AND snapshot_date BETWEEN (
          SELECT max(snapshot_date) - 25 FROM option_chains WHERE underlying = '${esc(underlying)}'
        ) AND (
          SELECT max(snapshot_date) - 1 FROM option_chains WHERE underlying = '${esc(underlying)}'
        )
      GROUP BY expiration, strike, put_call
    ),
    latest AS (
      SELECT *
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND expiration = '${expiration}'
        AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')
    )
    SELECT
      strike,
      maxIf(l.bid, l.put_call = 'call') AS callBid,
      maxIf(l.ask, l.put_call = 'call') AS callAsk,
      maxIf(l.close, l.put_call = 'call') AS callLast,
      maxIf(l.volume, l.put_call = 'call') AS callVolume,
      maxIf(l.open_interest, l.put_call = 'call') AS callOI,
      round(maxIf(l.implied_vol, l.put_call = 'call'), 4) AS callIV,
      round(maxIf(l.delta, l.put_call = 'call'), 3) AS callDelta,
      round(maxIf(h.avg_vol, l.put_call = 'call'), 0) AS callAvgVol,
      maxIf(l.bid, l.put_call = 'put') AS putBid,
      maxIf(l.ask, l.put_call = 'put') AS putAsk,
      maxIf(l.close, l.put_call = 'put') AS putLast,
      maxIf(l.volume, l.put_call = 'put') AS putVolume,
      maxIf(l.open_interest, l.put_call = 'put') AS putOI,
      round(maxIf(l.implied_vol, l.put_call = 'put'), 4) AS putIV,
      round(maxIf(l.delta, l.put_call = 'put'), 3) AS putDelta,
      round(maxIf(h.avg_vol, l.put_call = 'put'), 0) AS putAvgVol
    FROM latest l
    LEFT JOIN hist h ON l.expiration = h.expiration
      AND l.strike = h.strike AND l.put_call = h.put_call
    GROUP BY strike
    ORDER BY strike
  `;

  const result = await client.query<ChainRow>(sql);
  return result.rows;
}

// ── Historical Volatility vs IV ──────────────────────────────────────

export interface HVvsIVPoint {
  date: string;
  hv30: number;
  iv30: number;
}

/** 30-day realized vol (from OHLCV) vs 30-day ATM IV (from options). */
export async function getHVvsIV(
  client: DataPlatClient,
  underlying: string,
  days = 365,
): Promise<HVvsIVPoint[]> {
  const sql = `
    WITH daily_returns AS (
      SELECT day,
        log(close / lagInFrame(close) OVER (ORDER BY day)) AS log_ret
      FROM ohlcv_daily_mv
      WHERE ticker = '${esc(underlying)}'
        AND day >= today() - ${days + 40}
    ),
    realized AS (
      SELECT day,
        round(stddevPopStable(log_ret) OVER (ORDER BY day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) * sqrt(252) * 100, 2) AS hv30
      FROM daily_returns
      WHERE log_ret IS NOT NULL
    ),
    implied AS (
      SELECT snapshot_date AS day,
        round(avg(implied_vol) * 100, 2) AS iv30
      FROM option_chains
      WHERE underlying = '${esc(underlying)}'
        AND put_call = 'call'
        AND abs(delta) BETWEEN 0.40 AND 0.60
        AND (toDate(expiration) - toDate(snapshot_date)) BETWEEN 20 AND 40
        AND implied_vol > 0
        AND snapshot_date >= today() - ${days}
      GROUP BY snapshot_date
    )
    SELECT
      toString(r.day) AS date,
      r.hv30,
      i.iv30
    FROM realized r
    JOIN implied i ON r.day = i.day
    WHERE r.day >= today() - ${days}
      AND r.hv30 > 0
    ORDER BY r.day
  `;

  const result = await client.query<HVvsIVPoint>(sql);
  return result.rows;
}

/** Largest open interest clusters by strike — support/resistance levels. */
export async function getOIWalls(
  client: DataPlatClient,
  underlying: string,
  snapshotDate?: string,
): Promise<OIWallPoint[]> {
  const dateClause = snapshotDate
    ? `AND snapshot_date = '${snapshotDate}'`
    : `AND snapshot_date = (SELECT max(snapshot_date) FROM option_chains WHERE underlying = '${esc(underlying)}')`;

  const sql = `
    SELECT
      strike,
      sumIf(open_interest, put_call = 'call') AS callOI,
      sumIf(open_interest, put_call = 'put') AS putOI,
      sum(open_interest) AS totalOI
    FROM option_chains
    WHERE underlying = '${esc(underlying)}'
      ${dateClause}
      AND (expiration - snapshot_date) <= 45
      AND open_interest > 0
    GROUP BY strike
    HAVING totalOI > 100
    ORDER BY strike
  `;

  const result = await client.query<OIWallPoint>(sql);
  return result.rows;
}
