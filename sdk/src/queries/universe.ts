import type { DataPlatClient } from '../client.js';
import type { UniverseEntry, UniverseFilters, SectorSummary } from '../types.js';

function esc(s: string): string {
  return s.replace(/'/g, "\\'");
}

interface RawUniverseRow {
  ticker: string;
  name: string;
  type: string;
  exchange: string;
  sector: string | null;
  sic_code: string | null;
  market_cap: number | null;
  active: boolean;
  description: string | null;
  homepage_url: string | null;
  total_employees: number | null;
  list_date: string | null;
  cik: string | null;
  sic_description: string | null;
  address_city: string | null;
  address_state: string | null;
}

function mapRow(r: RawUniverseRow): UniverseEntry {
  return {
    ticker: r.ticker,
    name: r.name,
    type: r.type,
    exchange: r.exchange,
    sector: r.sector,
    sicCode: r.sic_code,
    marketCap: r.market_cap,
    active: r.active,
    description: r.description,
    homepageUrl: r.homepage_url,
    totalEmployees: r.total_employees,
    listDate: r.list_date,
    cik: r.cik,
    sicDescription: r.sic_description,
    addressCity: r.address_city,
    addressState: r.address_state,
  };
}

export async function getUniverse(
  client: DataPlatClient,
  filters?: UniverseFilters,
): Promise<UniverseEntry[]> {
  const where: string[] = [];

  if (filters?.sector) where.push(`sector = '${esc(filters.sector)}'`);
  if (filters?.exchange) where.push(`exchange = '${esc(filters.exchange)}'`);
  if (filters?.type) where.push(`type = '${esc(filters.type)}'`);
  if (filters?.active !== undefined) where.push(`active = ${filters.active ? 1 : 0}`);
  if (filters?.minMarketCap != null) where.push(`market_cap >= ${filters.minMarketCap}`);
  if (filters?.maxMarketCap != null) where.push(`market_cap <= ${filters.maxMarketCap}`);

  const whereClause = where.length > 0 ? `WHERE ${where.join(' AND ')}` : '';

  const sql = `
    SELECT
      ticker, name, type, exchange, sector, sic_code, market_cap,
      active, description, homepage_url, total_employees,
      toString(list_date) AS list_date, cik, sic_description,
      address_city, address_state
    FROM universe
    ${whereClause}
    ORDER BY ticker
  `;

  const result = await client.query<RawUniverseRow>(sql);
  return result.rows.map(mapRow);
}

export async function searchTickers(
  client: DataPlatClient,
  query: string,
  limit = 20,
): Promise<UniverseEntry[]> {
  const q = esc(query.toUpperCase());

  const sql = `
    SELECT
      ticker, name, type, exchange, sector, sic_code, market_cap,
      active, description, homepage_url, total_employees,
      toString(list_date) AS list_date, cik, sic_description,
      address_city, address_state
    FROM universe
    WHERE ticker LIKE '${q}%' OR upper(name) LIKE '%${q}%'
    ORDER BY
      CASE WHEN ticker = '${q}' THEN 0
           WHEN ticker LIKE '${q}%' THEN 1
           ELSE 2 END,
      market_cap DESC
    LIMIT ${limit}
  `;

  const result = await client.query<RawUniverseRow>(sql);
  return result.rows.map(mapRow);
}

export async function getTicker(
  client: DataPlatClient,
  ticker: string,
): Promise<UniverseEntry | null> {
  const sql = `
    SELECT
      ticker, name, type, exchange, sector, sic_code, market_cap,
      active, description, homepage_url, total_employees,
      toString(list_date) AS list_date, cik, sic_description,
      address_city, address_state
    FROM universe
    WHERE ticker = '${esc(ticker)}'
    LIMIT 1
  `;

  const result = await client.query<RawUniverseRow>(sql);
  const row = result.rows[0];
  return row ? mapRow(row) : null;
}

export async function getSectors(
  client: DataPlatClient,
): Promise<SectorSummary[]> {
  const sql = `
    SELECT
      sector,
      count() AS tickerCount,
      sum(coalesce(market_cap, 0)) AS totalMarketCap
    FROM universe
    WHERE sector IS NOT NULL AND sector != ''
    GROUP BY sector
    ORDER BY tickerCount DESC
  `;

  const result = await client.query<SectorSummary>(sql);
  return result.rows;
}

export async function getTickersBySector(
  client: DataPlatClient,
  sector: string,
): Promise<UniverseEntry[]> {
  return getUniverse(client, { sector });
}
