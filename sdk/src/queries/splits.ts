import type { DataPlatClient } from '../client.js';
import type { StockSplit } from '../types.js';

function esc(s: string): string {
  return s.replace(/'/g, "\\'");
}

interface RawSplitRow {
  ticker: string;
  execution_date: string;
  split_from: number;
  split_to: number;
}

function mapRow(r: RawSplitRow): StockSplit {
  return {
    ticker: r.ticker,
    executionDate: r.execution_date,
    splitFrom: r.split_from,
    splitTo: r.split_to,
  };
}

export async function getSplits(
  client: DataPlatClient,
  ticker: string,
): Promise<StockSplit[]> {
  const sql = `
    SELECT
      ticker,
      toString(execution_date) AS execution_date,
      split_from,
      split_to
    FROM stock_splits
    WHERE ticker = '${esc(ticker)}'
    ORDER BY execution_date DESC
  `;

  const result = await client.query<RawSplitRow>(sql);
  return result.rows.map(mapRow);
}
