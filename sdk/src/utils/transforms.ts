import type { OHLCVBar, Financial } from '../types.js';

/**
 * Normalize price series to base 100 at the first data point.
 * Used for comparing performance across tickers with different price levels.
 */
export function normalizeToBase100(bars: OHLCVBar[]): OHLCVBar[] {
  if (bars.length === 0) return [];
  const base = bars[0]?.close;
  if (!base || base === 0) return bars;

  const factor = 100 / base;
  return bars.map((bar) => ({
    ...bar,
    open: bar.open * factor,
    high: bar.high * factor,
    low: bar.low * factor,
    close: bar.close * factor,
  }));
}

/**
 * Compute simple percentage returns from OHLCV bars.
 * Returns array of { time, returnPct } where returnPct is cumulative from start.
 */
export function computeCumulativeReturns(
  bars: OHLCVBar[],
): { time: string; returnPct: number }[] {
  if (bars.length === 0) return [];
  const base = bars[0]?.close;
  if (!base || base === 0) return [];

  return bars.map((bar) => ({
    time: bar.time,
    returnPct: ((bar.close - base) / base) * 100,
  }));
}

/**
 * Compute simple moving average from OHLCV close prices.
 */
export function computeSMA(
  bars: OHLCVBar[],
  period: number,
): { time: string; value: number }[] {
  if (bars.length < period) return [];

  const result: { time: string; value: number }[] = [];
  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sum += bars[j]!.close;
    }
    result.push({ time: bars[i]!.time, value: sum / period });
  }
  return result;
}

/**
 * Compute exponential moving average from OHLCV close prices.
 */
export function computeEMA(
  bars: OHLCVBar[],
  period: number,
): { time: string; value: number }[] {
  if (bars.length < period) return [];

  const multiplier = 2 / (period + 1);
  const smaSlice = bars.slice(0, period);
  let ema = smaSlice.reduce((sum, b) => sum + b.close, 0) / period;

  const result: { time: string; value: number }[] = [
    { time: bars[period - 1]!.time, value: ema },
  ];

  for (let i = period; i < bars.length; i++) {
    ema = (bars[i]!.close - ema) * multiplier + ema;
    result.push({ time: bars[i]!.time, value: ema });
  }
  return result;
}

/**
 * Compute YoY growth rates from financial data.
 * Groups by fiscal period and computes growth for each metric.
 */
export function computeYoYGrowth(
  financials: Financial[],
  metric: keyof Financial,
): { fiscalYear: string; fiscalPeriod: string; value: number | null; growthPct: number | null }[] {
  // Sort chronologically
  const sorted = [...financials].sort(
    (a, b) => a.periodEnd.localeCompare(b.periodEnd),
  );

  return sorted.map((f, i) => {
    const currentVal = f[metric] as number | null;
    // Find same fiscal period in previous year
    const prevYear = sorted.find(
      (p) =>
        p.fiscalPeriod === f.fiscalPeriod &&
        p.fiscalYear === String(Number(f.fiscalYear) - 1),
    );
    const prevVal = prevYear ? (prevYear[metric] as number | null) : null;

    let growthPct: number | null = null;
    if (currentVal != null && prevVal != null && prevVal !== 0) {
      growthPct = ((currentVal - prevVal) / Math.abs(prevVal)) * 100;
    }

    return {
      fiscalYear: f.fiscalYear,
      fiscalPeriod: f.fiscalPeriod,
      value: currentVal,
      growthPct,
    };
  });
}

/**
 * Compute Bollinger Bands from OHLCV close prices.
 * Returns middle (SMA), upper (SMA + stdDev*mult), lower (SMA - stdDev*mult).
 */
export function computeBollingerBands(
  bars: OHLCVBar[],
  period = 20,
  multiplier = 2,
): { time: string; middle: number; upper: number; lower: number }[] {
  if (bars.length < period) return [];

  const result: { time: string; middle: number; upper: number; lower: number }[] = [];
  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += bars[j]!.close;
    const mean = sum / period;

    let sqSum = 0;
    for (let j = i - period + 1; j <= i; j++) sqSum += (bars[j]!.close - mean) ** 2;
    const std = Math.sqrt(sqSum / period);

    result.push({
      time: bars[i]!.time,
      middle: mean,
      upper: mean + multiplier * std,
      lower: mean - multiplier * std,
    });
  }
  return result;
}

/**
 * Compute RSI (Relative Strength Index) from OHLCV close prices.
 */
export function computeRSI(
  bars: OHLCVBar[],
  period = 14,
): { time: string; value: number }[] {
  if (bars.length < period + 1) return [];

  // Calculate price changes
  const changes: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    changes.push(bars[i]!.close - bars[i - 1]!.close);
  }

  // Initial average gain/loss
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 0; i < period; i++) {
    const c = changes[i]!;
    if (c > 0) avgGain += c;
    else avgLoss += Math.abs(c);
  }
  avgGain /= period;
  avgLoss /= period;

  const result: { time: string; value: number }[] = [];

  // RSI for first point
  const rs0 = avgLoss === 0 ? 100 : avgGain / avgLoss;
  result.push({ time: bars[period]!.time, value: 100 - 100 / (1 + rs0) });

  // Smoothed RSI for remaining points
  for (let i = period; i < changes.length; i++) {
    const c = changes[i]!;
    const gain = c > 0 ? c : 0;
    const loss = c < 0 ? Math.abs(c) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push({ time: bars[i + 1]!.time, value: 100 - 100 / (1 + rs) });
  }
  return result;
}

/**
 * Compute MACD (Moving Average Convergence Divergence).
 * Returns MACD line, signal line, and histogram.
 */
export function computeMACD(
  bars: OHLCVBar[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9,
): { time: string; macd: number; signal: number; histogram: number }[] {
  const fastEMA = computeEMA(bars, fastPeriod);
  const slowEMA = computeEMA(bars, slowPeriod);

  if (fastEMA.length === 0 || slowEMA.length === 0) return [];

  // Align by time
  const slowMap = new Map(slowEMA.map((d) => [d.time, d.value]));
  const macdLine: { time: string; value: number }[] = [];
  for (const f of fastEMA) {
    const s = slowMap.get(f.time);
    if (s != null) macdLine.push({ time: f.time, value: f.value - s });
  }

  if (macdLine.length < signalPeriod) return [];

  // Signal line = EMA of MACD line
  const signalMultiplier = 2 / (signalPeriod + 1);
  let signalEma = macdLine.slice(0, signalPeriod).reduce((s, d) => s + d.value, 0) / signalPeriod;

  const result: { time: string; macd: number; signal: number; histogram: number }[] = [
    {
      time: macdLine[signalPeriod - 1]!.time,
      macd: macdLine[signalPeriod - 1]!.value,
      signal: signalEma,
      histogram: macdLine[signalPeriod - 1]!.value - signalEma,
    },
  ];

  for (let i = signalPeriod; i < macdLine.length; i++) {
    signalEma = (macdLine[i]!.value - signalEma) * signalMultiplier + signalEma;
    result.push({
      time: macdLine[i]!.time,
      macd: macdLine[i]!.value,
      signal: signalEma,
      histogram: macdLine[i]!.value - signalEma,
    });
  }
  return result;
}

/**
 * Compute gross, operating, and net margins from financial data.
 */
export function computeMargins(
  financials: Financial[],
): {
  periodEnd: string;
  fiscalYear: string;
  fiscalPeriod: string;
  grossMargin: number | null;
  operatingMargin: number | null;
  netMargin: number | null;
}[] {
  return financials.map((f) => {
    const rev = f.revenue;
    return {
      periodEnd: f.periodEnd,
      fiscalYear: f.fiscalYear,
      fiscalPeriod: f.fiscalPeriod,
      grossMargin: rev && f.grossProfit != null ? (f.grossProfit / rev) * 100 : null,
      operatingMargin: rev && f.operatingIncome != null ? (f.operatingIncome / rev) * 100 : null,
      netMargin: rev && f.netIncome != null ? (f.netIncome / rev) * 100 : null,
    };
  });
}
