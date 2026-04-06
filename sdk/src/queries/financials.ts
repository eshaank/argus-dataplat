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

/**
 * Map the timeframe param ('annual'|'quarterly') to a SQL filter
 * using the new schema's fiscal_period column.
 *   annual     → fiscal_period = 'FY'
 *   quarterly  → fiscal_period IN ('Q1','Q2','Q3','Q4')
 */
function timeframeFilter(tf?: 'annual' | 'quarterly'): string {
  if (tf === 'annual') return "fiscal_period = 'FY'";
  if (tf === 'quarterly') return "fiscal_period IN ('Q1','Q2','Q3','Q4')";
  return '';
}

/** Derive a virtual timeframe value from fiscal_period for backward compat. */
function deriveTimeframe(fiscalPeriod: string): 'annual' | 'quarterly' {
  return fiscalPeriod === 'FY' ? 'annual' : 'quarterly';
}

interface RawFinancialRow {
  ticker: string;
  cik: string | null;
  period_start: string | null;
  period_end: string;
  fiscal_year: string;
  fiscal_period: string;
  form_type: string;
  filed_date: string | null;
  accession_number: string | null;

  // Income statement
  revenue: number | null;
  cost_of_revenue: number | null;
  gross_profit: number | null;
  operating_expenses: number | null;
  operating_income: number | null;
  net_income: number | null;
  basic_eps: number | null;
  diluted_eps: number | null;
  research_and_dev: number | null;
  sga_expenses: number | null;
  income_tax: number | null;
  interest_expense: number | null;
  ebitda: number | null;

  // Balance sheet
  total_assets: number | null;
  current_assets: number | null;
  noncurrent_assets: number | null;
  total_liabilities: number | null;
  current_liabilities: number | null;
  noncurrent_liabilities: number | null;
  total_equity: number | null;
  retained_earnings: number | null;
  long_term_debt: number | null;
  short_term_debt: number | null;
  cash_and_equivalents: number | null;
  inventory: number | null;
  accounts_receivable: number | null;
  accounts_payable: number | null;
  goodwill: number | null;

  // Cash flow
  operating_cash_flow: number | null;
  investing_cash_flow: number | null;
  financing_cash_flow: number | null;
  capex: number | null;
  dividends_paid: number | null;
  depreciation_amortization: number | null;

  // Dilution & shares
  shares_outstanding: number | null;
  weighted_avg_shares_basic: number | null;
  weighted_avg_shares_diluted: number | null;
  stock_based_compensation: number | null;
  buyback_value: number | null;
  dividends_per_share: number | null;
}

function mapRow(r: RawFinancialRow): Financial {
  return {
    ticker: r.ticker,
    cik: r.cik,
    periodStart: r.period_start,
    periodEnd: r.period_end,
    fiscalYear: r.fiscal_year,
    fiscalPeriod: r.fiscal_period,
    formType: r.form_type,
    filedDate: r.filed_date,
    accessionNumber: r.accession_number,

    revenue: r.revenue,
    costOfRevenue: r.cost_of_revenue,
    grossProfit: r.gross_profit,
    operatingExpenses: r.operating_expenses,
    operatingIncome: r.operating_income,
    netIncome: r.net_income,
    basicEps: r.basic_eps,
    dilutedEps: r.diluted_eps,
    researchAndDev: r.research_and_dev,
    sgaExpenses: r.sga_expenses,
    incomeTax: r.income_tax,
    interestExpense: r.interest_expense,
    ebitda: r.ebitda,

    totalAssets: r.total_assets,
    currentAssets: r.current_assets,
    noncurrentAssets: r.noncurrent_assets,
    totalLiabilities: r.total_liabilities,
    currentLiabilities: r.current_liabilities,
    noncurrentLiabilities: r.noncurrent_liabilities,
    totalEquity: r.total_equity,
    retainedEarnings: r.retained_earnings,
    longTermDebt: r.long_term_debt,
    shortTermDebt: r.short_term_debt,
    cashAndEquivalents: r.cash_and_equivalents,
    inventory: r.inventory,
    accountsReceivable: r.accounts_receivable,
    accountsPayable: r.accounts_payable,
    goodwill: r.goodwill,

    operatingCashFlow: r.operating_cash_flow,
    investingCashFlow: r.investing_cash_flow,
    financingCashFlow: r.financing_cash_flow,
    capex: r.capex,
    dividendsPaid: r.dividends_paid,
    depreciationAmortization: r.depreciation_amortization,

    sharesOutstanding: r.shares_outstanding,
    weightedAvgSharesBasic: r.weighted_avg_shares_basic,
    weightedAvgSharesDiluted: r.weighted_avg_shares_diluted,
    stockBasedCompensation: r.stock_based_compensation,
    buybackValue: r.buyback_value,
    dividendsPerShare: r.dividends_per_share,

    // Derived for backward compat
    timeframe: deriveTimeframe(r.fiscal_period),
  };
}

export async function getFinancials(
  client: DataPlatClient,
  params: FinancialsParams,
): Promise<Financial[]> {
  const filters: string[] = [`ticker = '${escTicker(params.ticker)}'`];

  const tfFilter = timeframeFilter(params.timeframe);
  if (tfFilter) filters.push(tfFilter);

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
    researchAndDev: 'research_and_dev',
    sgaExpenses: 'sga_expenses',
    ebitda: 'ebitda',
    interestExpense: 'interest_expense',
    capex: 'capex',
    sharesOutstanding: 'shares_outstanding',
    weightedAvgSharesBasic: 'weighted_avg_shares_basic',
    weightedAvgSharesDiluted: 'weighted_avg_shares_diluted',
    stockBasedCompensation: 'stock_based_compensation',
    cashAndEquivalents: 'cash_and_equivalents',
    retainedEarnings: 'retained_earnings',
    shortTermDebt: 'short_term_debt',
  };

  const col = colMap[params.metric as string] ?? (params.metric as string);
  const limit = params.limit ?? 20;

  const tfFilter = timeframeFilter(params.timeframe);
  const tfClause = tfFilter ? `AND ${tfFilter}` : '';

  const sql = `
    SELECT
      ticker,
      toString(period_end) AS periodEnd,
      fiscal_year AS fiscalYear,
      fiscal_period AS fiscalPeriod,
      ${col} AS value
    FROM financials
    WHERE ticker IN (${tickerList(params.tickers)})
      ${tfClause}
    ORDER BY ticker, period_end DESC
    LIMIT ${limit * params.tickers.length}
  `;

  const result = await client.query<MetricDataPoint>(sql);
  return result.rows;
}
