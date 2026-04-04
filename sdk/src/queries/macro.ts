import type { DataPlatClient } from '../client.js';
import type {
  TreasuryYield,
  YieldCurvePoint,
  InflationData,
  LaborMarketData,
  InflationExpectation,
  DateRangeParams,
} from '../types.js';

function dateFilter(col: string, start?: string, end?: string): string {
  const parts: string[] = [];
  if (start) parts.push(`${col} >= '${start}'`);
  if (end) parts.push(`${col} <= '${end}'`);
  return parts.length > 0 ? `WHERE ${parts.join(' AND ')}` : '';
}

// ── Treasury Yields ────────────────────────────────────────────────

interface RawYieldRow {
  date: string;
  yield_1_month: number | null;
  yield_3_month: number | null;
  yield_1_year: number | null;
  yield_2_year: number | null;
  yield_5_year: number | null;
  yield_10_year: number | null;
  yield_30_year: number | null;
}

function mapYield(r: RawYieldRow): TreasuryYield {
  return {
    date: r.date,
    yield1Month: r.yield_1_month,
    yield3Month: r.yield_3_month,
    yield1Year: r.yield_1_year,
    yield2Year: r.yield_2_year,
    yield5Year: r.yield_5_year,
    yield10Year: r.yield_10_year,
    yield30Year: r.yield_30_year,
  };
}

export async function getTreasuryYields(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<TreasuryYield[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      yield_1_month, yield_3_month, yield_1_year,
      yield_2_year, yield_5_year, yield_10_year, yield_30_year
    FROM treasury_yields
    ${dateFilter('date', params?.start, params?.end)}
    ORDER BY date
  `;

  const result = await client.query<RawYieldRow>(sql);
  return result.rows.map(mapYield);
}

export async function getYieldCurve(
  client: DataPlatClient,
  date: string,
): Promise<YieldCurvePoint[]> {
  const sql = `
    SELECT
      yield_1_month, yield_3_month, yield_1_year,
      yield_2_year, yield_5_year, yield_10_year, yield_30_year
    FROM treasury_yields
    WHERE date <= '${date}'
    ORDER BY date DESC
    LIMIT 1
  `;

  const result = await client.query<RawYieldRow>(sql);
  const row = result.rows[0];
  if (!row) return [];

  return [
    { maturity: '1M', yield: row.yield_1_month },
    { maturity: '3M', yield: row.yield_3_month },
    { maturity: '1Y', yield: row.yield_1_year },
    { maturity: '2Y', yield: row.yield_2_year },
    { maturity: '5Y', yield: row.yield_5_year },
    { maturity: '10Y', yield: row.yield_10_year },
    { maturity: '30Y', yield: row.yield_30_year },
  ];
}

export async function getYieldCurveTimeSeries(
  client: DataPlatClient,
  dates: string[],
): Promise<{ date: string; curve: YieldCurvePoint[] }[]> {
  const results: { date: string; curve: YieldCurvePoint[] }[] = [];
  for (const date of dates) {
    const curve = await getYieldCurve(client, date);
    results.push({ date, curve });
  }
  return results;
}

// ── Inflation ──────────────────────────────────────────────────────

interface RawInflationRow {
  date: string;
  cpi: number | null;
  cpi_core: number | null;
  pce: number | null;
  pce_core: number | null;
  pce_spending: number | null;
}

function mapInflation(r: RawInflationRow): InflationData {
  return {
    date: r.date,
    cpi: r.cpi,
    cpiCore: r.cpi_core,
    pce: r.pce,
    pceCore: r.pce_core,
    pceSpending: r.pce_spending,
  };
}

export async function getInflation(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<InflationData[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      cpi, cpi_core, pce, pce_core, pce_spending
    FROM inflation
    ${dateFilter('date', params?.start, params?.end)}
    ORDER BY date
  `;

  const result = await client.query<RawInflationRow>(sql);
  return result.rows.map(mapInflation);
}

// ── Labor Market ───────────────────────────────────────────────────

interface RawLaborRow {
  date: string;
  unemployment_rate: number | null;
  labor_force_participation_rate: number | null;
  avg_hourly_earnings: number | null;
  job_openings: number | null;
}

function mapLabor(r: RawLaborRow): LaborMarketData {
  return {
    date: r.date,
    unemploymentRate: r.unemployment_rate,
    laborForceParticipationRate: r.labor_force_participation_rate,
    avgHourlyEarnings: r.avg_hourly_earnings,
    jobOpenings: r.job_openings,
  };
}

export async function getLaborMarket(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<LaborMarketData[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      unemployment_rate, labor_force_participation_rate,
      avg_hourly_earnings, job_openings
    FROM labor_market
    ${dateFilter('date', params?.start, params?.end)}
    ORDER BY date
  `;

  const result = await client.query<RawLaborRow>(sql);
  return result.rows.map(mapLabor);
}

// ── Inflation Expectations ─────────────────────────────────────────

interface RawInflExpRow {
  date: string;
  market_5_year: number | null;
  market_10_year: number | null;
  forward_years_5_to_10: number | null;
  model_1_year: number | null;
  model_5_year: number | null;
  model_10_year: number | null;
  model_30_year: number | null;
}

function mapInflExp(r: RawInflExpRow): InflationExpectation {
  return {
    date: r.date,
    market5Year: r.market_5_year,
    market10Year: r.market_10_year,
    forwardYears5To10: r.forward_years_5_to_10,
    model1Year: r.model_1_year,
    model5Year: r.model_5_year,
    model10Year: r.model_10_year,
    model30Year: r.model_30_year,
  };
}

export async function getInflationExpectations(
  client: DataPlatClient,
  params?: DateRangeParams,
): Promise<InflationExpectation[]> {
  const sql = `
    SELECT
      toString(date) AS date,
      market_5_year, market_10_year, forward_years_5_to_10,
      model_1_year, model_5_year, model_10_year, model_30_year
    FROM inflation_expectations
    ${dateFilter('date', params?.start, params?.end)}
    ORDER BY date
  `;

  const result = await client.query<RawInflExpRow>(sql);
  return result.rows.map(mapInflExp);
}
