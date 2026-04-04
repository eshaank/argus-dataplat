import type { DataPlatClient } from '../client.js';
import type {
  Financial,
  FinancialsParams,
  MetricParams,
  MetricDataPoint,
} from '../types.js';

function escTicker(t: string): string {
  return t.replace(/'/g, "\\'");
}

function tickerList(tickers: string[]): string {
  return tickers.map((t) => `'${escTicker(t)}'`).join(', ');
}

interface RawFinancialRow {
  ticker: string;
  period_start: string;
  period_end: string;
  fiscal_year: string;
  fiscal_period: string;
  timeframe: string;
  filing_date: string | null;
  revenue: number | null;
  cost_of_revenue: number | null;
  gross_profit: number | null;
  operating_expenses: number | null;
  operating_income: number | null;
  net_income: number | null;
  basic_eps: number | null;
  diluted_eps: number | null;
  basic_shares: number | null;
  diluted_shares: number | null;
  research_and_dev: number | null;
  sga_expenses: number | null;
  income_tax: number | null;
  total_assets: number | null;
  current_assets: number | null;
  noncurrent_assets: number | null;
  total_liabilities: number | null;
  current_liabilities: number | null;
  noncurrent_liabilities: number | null;
  total_equity: number | null;
  long_term_debt: number | null;
  inventory: number | null;
  accounts_payable: number | null;
  operating_cash_flow: number | null;
  investing_cash_flow: number | null;
  financing_cash_flow: number | null;
  net_cash_flow: number | null;
}

function mapRow(r: RawFinancialRow): Financial {
  return {
    ticker: r.ticker,
    periodStart: r.period_start,
    periodEnd: r.period_end,
    fiscalYear: r.fiscal_year,
    fiscalPeriod: r.fiscal_period,
    timeframe: r.timeframe,
    filingDate: r.filing_date,
    revenue: r.revenue,
    costOfRevenue: r.cost_of_revenue,
    grossProfit: r.gross_profit,
    operatingExpenses: r.operating_expenses,
    operatingIncome: r.operating_income,
    netIncome: r.net_income,
    basicEps: r.basic_eps,
    dilutedEps: r.diluted_eps,
    basicShares: r.basic_shares,
    dilutedShares: r.diluted_shares,
    researchAndDev: r.research_and_dev,
    sgaExpenses: r.sga_expenses,
    incomeTax: r.income_tax,
    totalAssets: r.total_assets,
    currentAssets: r.current_assets,
    noncurrentAssets: r.noncurrent_assets,
    totalLiabilities: r.total_liabilities,
    currentLiabilities: r.current_liabilities,
    noncurrentLiabilities: r.noncurrent_liabilities,
    totalEquity: r.total_equity,
    longTermDebt: r.long_term_debt,
    inventory: r.inventory,
    accountsPayable: r.accounts_payable,
    operatingCashFlow: r.operating_cash_flow,
    investingCashFlow: r.investing_cash_flow,
    financingCashFlow: r.financing_cash_flow,
    netCashFlow: r.net_cash_flow,
  };
}

export async function getFinancials(
  client: DataPlatClient,
  params: FinancialsParams,
): Promise<Financial[]> {
  const filters: string[] = [`ticker = '${escTicker(params.ticker)}'`];

  if (params.timeframe === 'annual') {
    filters.push("timeframe = 'annual'");
  } else if (params.timeframe === 'quarterly') {
    filters.push("timeframe = 'quarterly'");
  }
  if (params.fiscalYear) {
    filters.push(`fiscal_year = '${params.fiscalYear}'`);
  }
  if (params.fiscalPeriod) {
    filters.push(`fiscal_period = '${params.fiscalPeriod}'`);
  }

  const limit = params.limit ?? 40;

  const sql = `
    SELECT *
    FROM financials
    WHERE ${filters.join(' AND ')}
    ORDER BY period_end DESC
    LIMIT ${limit}
  `;

  const result = await client.query<RawFinancialRow>(sql);
  return result.rows.map(mapRow);
}

export async function getIncomeStatement(
  client: DataPlatClient,
  ticker: string,
  timeframe: 'annual' | 'quarterly' = 'quarterly',
  limit = 12,
): Promise<Financial[]> {
  return getFinancials(client, { ticker, timeframe, limit });
}

export async function getBalanceSheet(
  client: DataPlatClient,
  ticker: string,
  timeframe: 'annual' | 'quarterly' = 'quarterly',
  limit = 12,
): Promise<Financial[]> {
  return getFinancials(client, { ticker, timeframe, limit });
}

export async function getCashFlow(
  client: DataPlatClient,
  ticker: string,
  timeframe: 'annual' | 'quarterly' = 'quarterly',
  limit = 12,
): Promise<Financial[]> {
  return getFinancials(client, { ticker, timeframe, limit });
}

/** Get a single metric across multiple tickers for comparison. */
export async function getMetric(
  client: DataPlatClient,
  params: MetricParams,
): Promise<MetricDataPoint[]> {
  if (params.tickers.length === 0) return [];

  // Map camelCase metric name to snake_case column
  const colMap: Record<string, string> = {
    revenue: 'revenue',
    costOfRevenue: 'cost_of_revenue',
    grossProfit: 'gross_profit',
    operatingExpenses: 'operating_expenses',
    operatingIncome: 'operating_income',
    netIncome: 'net_income',
    basicEps: 'basic_eps',
    dilutedEps: 'diluted_eps',
    totalAssets: 'total_assets',
    totalLiabilities: 'total_liabilities',
    totalEquity: 'total_equity',
    longTermDebt: 'long_term_debt',
    operatingCashFlow: 'operating_cash_flow',
    investingCashFlow: 'investing_cash_flow',
    financingCashFlow: 'financing_cash_flow',
    netCashFlow: 'net_cash_flow',
    researchAndDev: 'research_and_dev',
    sgaExpenses: 'sga_expenses',
  };

  const col = colMap[params.metric as string] ?? (params.metric as string);
  const limit = params.limit ?? 20;

  const timeframeFilter = params.timeframe === 'annual'
    ? "AND timeframe = 'annual'"
    : params.timeframe === 'quarterly'
      ? "AND timeframe = 'quarterly'"
      : '';

  const sql = `
    SELECT
      ticker,
      toString(period_end) AS periodEnd,
      fiscal_year AS fiscalYear,
      fiscal_period AS fiscalPeriod,
      ${col} AS value
    FROM financials
    WHERE ticker IN (${tickerList(params.tickers)})
      ${timeframeFilter}
    ORDER BY ticker, period_end DESC
    LIMIT ${limit * params.tickers.length}
  `;

  const result = await client.query<MetricDataPoint>(sql);
  return result.rows;
}
