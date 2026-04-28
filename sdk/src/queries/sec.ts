/**
 * SEC data queries: insider trades, institutional holders, material events,
 * filings, dilution snapshots.
 * Backed by ClickHouse views and base tables.
 */
import type { DataPlatClient } from '../client.js';

// ── Types ──────────────────────────────────────────────────────────

export interface InsiderTrade {
  ticker: string;
  filedDate: string;
  reportDate: string;
  name: string;
  title: string | null;
  type: string;
  shares: number;
  price: number | null;
  value: number | null;
  sharesAfter: number | null;
  filingUrl: string;
}

export interface InsiderMonthly {
  month: string;
  buyCount: number;
  sellCount: number;
  buyValue: number | null;
  sellValue: number | null;
  netValue: number;
}

export interface InstitutionalHolder {
  name: string;
  sharesHeld: number;
  classPct: number | null;
  filedDate: string;
  formType: string;
  filingUrl: string;
}

export interface MaterialEvent {
  filedDate: string;
  reportDate: string | null;
  itemCode: string;
  itemDescription: string;
  filingUrl: string;
}

export interface SecFiling {
  formType: string;
  filedDate: string;
  primaryDocDesc: string | null;
  filingUrl: string;
}

export interface DilutionSnapshot {
  periodEnd: string;
  sharesOutstanding: number | null;
  sharesAuthorized: number | null;
  headroomPct: number | null;
  sbc: number | null;
  sbcPctRevenue: number | null;
  warrantsOutstanding: number | null;
  warrantExercisePrice: number | null;
  convertibleDebt: number | null;
  convertibleConversionPrice: number | null;
  optionsOutstanding: number | null;
  optionsExercisable: number | null;
  optionsAvgPrice: number | null;
  unvestedRSU: number | null;
  totalPotentialDilution: number;
  totalDilutionPct: number | null;
  netBuybackShares: number;
}

export interface DilutionTimeSeriesPoint {
  periodEnd: string;
  fiscalYear: string;
  fiscalPeriod: string;
  sharesOutstanding: number | null;
  weightedAvgBasic: number | null;
  weightedAvgDiluted: number | null;
  dilutiveEffect: number | null;
  sbc: number | null;
  sbcPctRevenue: number | null;
  buybackShares: number | null;
  buybackValue: number | null;
  sharesIssuedOptions: number | null;
  sharesIssuedRsuVested: number | null;
  unvestedRsu: number | null;
  optionsOutstanding: number | null;
  warrantsOutstanding: number | null;
  convertibleDebt: number | null;
  sharesAuthorized: number | null;
  headroomPct: number | null;
}

// ── Queries ────────────────────────────────────────────────────────

export async function getInsiderTrades(
  client: DataPlatClient, ticker: string, days = 365, limit = 50,
): Promise<InsiderTrade[]> {
  const result = await client.query<{
    ticker: string; f_date: string; r_date: string; reporter_name: string;
    reporter_title: string | null; transaction_type: string;
    shares: number; price: number | null; value: number | null;
    shares_owned_after: number | null; filing_url: string;
  }>(`
    SELECT ticker, CAST(filed_date AS String) as f_date, CAST(report_date AS String) as r_date,
      reporter_name, reporter_title, transaction_type, shares, price, value,
      shares_owned_after, filing_url
    FROM insider_trades
    WHERE ticker = '${ticker}' AND filed_date >= today() - ${days}
      AND transaction_code IN ('P','S') AND NOT is_derivative
    ORDER BY report_date DESC
    LIMIT ${limit}
  `);

  return result.rows.map((r) => ({
    ticker: r.ticker, filedDate: r.f_date, reportDate: r.r_date,
    name: r.reporter_name, title: r.reporter_title, type: r.transaction_type,
    shares: r.shares, price: r.price, value: r.value,
    sharesAfter: r.shares_owned_after, filingUrl: r.filing_url,
  }));
}

export async function getInsiderMonthly(
  client: DataPlatClient, ticker: string, days = 730,
): Promise<InsiderMonthly[]> {
  const result = await client.query<{
    m: string; buy_count: number; sell_count: number;
    buy_value: number | null; sell_value: number | null; net_value: number;
  }>(`
    SELECT CAST(month AS String) as m, buy_count, sell_count,
      buy_value, sell_value, net_value
    FROM v_insider_monthly
    WHERE ticker = '${ticker}' AND month >= today() - ${days}
    ORDER BY month DESC
  `);

  return result.rows.map((r) => ({
    month: r.m, buyCount: r.buy_count, sellCount: r.sell_count,
    buyValue: r.buy_value, sellValue: r.sell_value, netValue: r.net_value,
  }));
}

export async function getInstitutionalHolders(
  client: DataPlatClient, ticker: string, limit = 20,
): Promise<InstitutionalHolder[]> {
  const result = await client.query<{
    holder_name: string; shares_held: number; class_percent: number | null;
    f_date: string; form_type: string; filing_url: string;
  }>(`
    SELECT holder_name, shares_held, class_percent,
      CAST(filed_date AS String) as f_date, form_type, filing_url
    FROM v_institutional_latest
    WHERE ticker = '${ticker}'
    ORDER BY shares_held DESC
    LIMIT ${limit}
  `);

  return result.rows.map((r) => ({
    name: r.holder_name, sharesHeld: r.shares_held, classPct: r.class_percent,
    filedDate: r.f_date, formType: r.form_type, filingUrl: r.filing_url,
  }));
}

export async function getMaterialEvents(
  client: DataPlatClient, ticker: string, days = 730, limit = 30,
): Promise<MaterialEvent[]> {
  const result = await client.query<{
    f_date: string; r_date: string | null; item_code: string;
    item_description: string; filing_url: string;
  }>(`
    SELECT CAST(filed_date AS String) as f_date,
      CAST(report_date AS Nullable(String)) as r_date,
      item_code, item_description, filing_url
    FROM v_events_timeline
    WHERE ticker = '${ticker}' AND filed_date >= today() - ${days}
    ORDER BY filed_date DESC
    LIMIT ${limit}
  `);

  return result.rows.map((r) => ({
    filedDate: r.f_date, reportDate: r.r_date,
    itemCode: r.item_code, itemDescription: r.item_description,
    filingUrl: r.filing_url,
  }));
}

export async function getSecFilings(
  client: DataPlatClient, ticker: string, days = 730, limit = 40,
): Promise<SecFiling[]> {
  const result = await client.query<{
    form_type: string; f_date: string;
    primary_doc_desc: string | null; filing_url: string;
  }>(`
    SELECT form_type, CAST(filed_date AS String) as f_date,
      primary_doc_desc, filing_url
    FROM sec_filings
    WHERE ticker = '${ticker}' AND filed_date >= today() - ${days}
    ORDER BY filed_date DESC
    LIMIT ${limit}
  `);

  return result.rows.map((r) => ({
    formType: r.form_type, filedDate: r.f_date,
    primaryDocDesc: r.primary_doc_desc, filingUrl: r.filing_url,
  }));
}

export async function getDilutionSnapshot(
  client: DataPlatClient, ticker: string,
): Promise<DilutionSnapshot | null> {
  const result = await client.query<{
    p_end: string; shares_outstanding: number | null;
    shares_authorized: number | null; headroom_pct: number | null;
    stock_based_compensation: number | null; sbc_pct_of_revenue: number | null;
    warrants_outstanding: number | null; warrant_exercise_price: number | null;
    convertible_debt: number | null; convertible_conversion_price: number | null;
    options_outstanding: number | null; options_exercisable: number | null;
    options_weighted_avg_price: number | null; unvested_rsu_shares: number | null;
    total_potential_dilution_shares: number; total_dilution_pct: number | null;
    net_buyback_shares: number;
  }>(`
    SELECT CAST(period_end AS String) as p_end, shares_outstanding, shares_authorized,
      headroom_pct, stock_based_compensation, sbc_pct_of_revenue,
      warrants_outstanding, warrant_exercise_price,
      convertible_debt, convertible_conversion_price,
      options_outstanding, options_exercisable, options_weighted_avg_price,
      unvested_rsu_shares, total_potential_dilution_shares, total_dilution_pct,
      net_buyback_shares
    FROM v_dilution_snapshot
    WHERE ticker = '${ticker}'
    ORDER BY period_end DESC
    LIMIT 1
  `);

  const r = result.rows[0];
  if (!r) return null;

  return {
    periodEnd: r.p_end,
    sharesOutstanding: r.shares_outstanding,
    sharesAuthorized: r.shares_authorized,
    headroomPct: r.headroom_pct,
    sbc: r.stock_based_compensation,
    sbcPctRevenue: r.sbc_pct_of_revenue,
    warrantsOutstanding: r.warrants_outstanding,
    warrantExercisePrice: r.warrant_exercise_price,
    convertibleDebt: r.convertible_debt,
    convertibleConversionPrice: r.convertible_conversion_price,
    optionsOutstanding: r.options_outstanding,
    optionsExercisable: r.options_exercisable,
    optionsAvgPrice: r.options_weighted_avg_price,
    unvestedRSU: r.unvested_rsu_shares,
    totalPotentialDilution: r.total_potential_dilution_shares,
    totalDilutionPct: r.total_dilution_pct,
    netBuybackShares: r.net_buyback_shares,
  };
}

async function _queryDilutionTimeSeries(
  client: DataPlatClient,
  ticker: string,
  periodFilter: string,
): Promise<DilutionTimeSeriesPoint[]> {

  const result = await client.query<{
    p_end: string; fiscal_year: string; fiscal_period: string;
    shares_outstanding: number | null;
    weighted_avg_shares_basic: number | null;
    weighted_avg_shares_diluted: number | null;
    dilutive_effect: number | null;
    stock_based_compensation: number | null;
    sbc_pct_revenue: number | null;
    buyback_shares: number | null;
    buyback_value: number | null;
    shares_issued_options: number | null;
    shares_issued_rsu_vested: number | null;
    unvested_rsu_shares: number | null;
    options_outstanding: number | null;
    warrants_outstanding: number | null;
    convertible_debt: number | null;
    shares_authorized: number | null;
    headroom_pct: number | null;
  }>(`
    SELECT
      CAST(period_end AS String) as p_end,
      fiscal_year, fiscal_period,
      shares_outstanding,
      weighted_avg_shares_basic,
      weighted_avg_shares_diluted,
      dilutive_effect,
      stock_based_compensation,
      sbc_pct_revenue,
      buyback_shares,
      buyback_value,
      shares_issued_options,
      shares_issued_rsu_vested,
      unvested_rsu_shares,
      options_outstanding,
      warrants_outstanding,
      convertible_debt,
      shares_authorized,
      headroom_pct
    FROM v_dilution_timeseries
    WHERE ticker = '${ticker}'
      AND fiscal_period IN (${periodFilter})
    ORDER BY period_end ASC
  `);

  return result.rows.map((r) => ({
    periodEnd: r.p_end,
    fiscalYear: r.fiscal_year,
    fiscalPeriod: r.fiscal_period,
    sharesOutstanding: r.shares_outstanding,
    weightedAvgBasic: r.weighted_avg_shares_basic,
    weightedAvgDiluted: r.weighted_avg_shares_diluted,
    dilutiveEffect: r.dilutive_effect,
    sbc: r.stock_based_compensation,
    sbcPctRevenue: r.sbc_pct_revenue,
    buybackShares: r.buyback_shares,
    buybackValue: r.buyback_value,
    sharesIssuedOptions: r.shares_issued_options,
    sharesIssuedRsuVested: r.shares_issued_rsu_vested,
    unvestedRsu: r.unvested_rsu_shares,
    optionsOutstanding: r.options_outstanding,
    warrantsOutstanding: r.warrants_outstanding,
    convertibleDebt: r.convertible_debt,
    sharesAuthorized: r.shares_authorized,
    headroomPct: r.headroom_pct,
  }));
}

/**
 * Fetch dilution time series, falling back to annual ('FY') if the
 * requested quarterly periods return no data. Foreign private issuers
 * (e.g. 20-F filers like NBIS) only ever have FY periods.
 */
export async function getDilutionTimeSeries(
  client: DataPlatClient,
  ticker: string,
  periods: 'annual' | 'quarterly' = 'quarterly',
): Promise<DilutionTimeSeriesPoint[]> {
  const filter = periods === 'annual' ? "'FY'" : "'Q1','Q2','Q3','Q4'";
  const rows = await _queryDilutionTimeSeries(client, ticker, filter);

  // Foreign private issuers only have FY data — fall back transparently.
  if (rows.length === 0 && periods === 'quarterly') {
    return _queryDilutionTimeSeries(client, ticker, "'FY'");
  }

  return rows;
}
