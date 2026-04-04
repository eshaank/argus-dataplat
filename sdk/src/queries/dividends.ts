import type { DataPlatClient } from '../client.js';
import type { Dividend } from '../types.js';

function esc(s: string): string {
  return s.replace(/'/g, "\\'");
}

interface RawDividendRow {
  ticker: string;
  ex_dividend_date: string;
  declaration_date: string | null;
  record_date: string | null;
  pay_date: string | null;
  cash_amount: number;
  currency: string;
  frequency: number;
  dividend_type: string;
}

function mapRow(r: RawDividendRow): Dividend {
  return {
    ticker: r.ticker,
    exDividendDate: r.ex_dividend_date,
    declarationDate: r.declaration_date,
    recordDate: r.record_date,
    payDate: r.pay_date,
    cashAmount: r.cash_amount,
    currency: r.currency,
    frequency: r.frequency,
    dividendType: r.dividend_type,
  };
}

export async function getDividends(
  client: DataPlatClient,
  ticker: string,
): Promise<Dividend[]> {
  const sql = `
    SELECT
      ticker,
      toString(ex_dividend_date) AS ex_dividend_date,
      toString(declaration_date) AS declaration_date,
      toString(record_date) AS record_date,
      toString(pay_date) AS pay_date,
      cash_amount, currency, frequency, dividend_type
    FROM dividends
    WHERE ticker = '${esc(ticker)}'
    ORDER BY ex_dividend_date DESC
  `;

  const result = await client.query<RawDividendRow>(sql);
  return result.rows.map(mapRow);
}

export async function getDividendCalendar(
  client: DataPlatClient,
  start: string,
  end: string,
): Promise<Dividend[]> {
  const sql = `
    SELECT
      ticker,
      toString(ex_dividend_date) AS ex_dividend_date,
      toString(declaration_date) AS declaration_date,
      toString(record_date) AS record_date,
      toString(pay_date) AS pay_date,
      cash_amount, currency, frequency, dividend_type
    FROM dividends
    WHERE ex_dividend_date >= '${start}' AND ex_dividend_date <= '${end}'
    ORDER BY ex_dividend_date
  `;

  const result = await client.query<RawDividendRow>(sql);
  return result.rows.map(mapRow);
}
