import type { ClickHouseConfig, QueryResult, SchemaColumn } from './types.js';

const BLOCKED_KEYWORDS = new Set([
  'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
  'TRUNCATE', 'GRANT', 'REVOKE', 'ATTACH', 'DETACH',
]);

function validateReadOnly(sql: string): void {
  const trimmed = sql.trim();
  const firstToken = trimmed.split(/\s+/)[0]?.toUpperCase();
  if (firstToken !== 'SELECT' && firstToken !== 'WITH' && firstToken !== 'EXPLAIN') {
    throw new Error(`Only SELECT queries are allowed. Got: ${firstToken}`);
  }
  const upper = trimmed.toUpperCase();
  for (const keyword of BLOCKED_KEYWORDS) {
    // Match keyword as a whole word (not inside identifiers)
    const re = new RegExp(`\\b${keyword}\\b`);
    if (re.test(upper)) {
      throw new Error(`Mutation keyword detected: ${keyword}`);
    }
  }
}

export class DataPlatClient {
  private readonly baseUrl: string;
  private readonly authHeader: string;
  private readonly database: string;

  constructor(config: ClickHouseConfig) {
    const protocol = config.secure !== false && config.port === 8443 ? 'https' : 'http';
    this.baseUrl = `${protocol}://${config.host}:${config.port}`;
    this.authHeader = `Basic ${btoa(`${config.user}:${config.password}`)}`;
    this.database = config.database;
  }

  /**
   * Execute a read-only SQL query against ClickHouse.
   * Returns typed rows parsed from JSONEachRow format.
   */
  async query<T = Record<string, unknown>>(sql: string): Promise<QueryResult<T>> {
    validateReadOnly(sql);

    const start = performance.now();
    const url = new URL('/', this.baseUrl);
    url.searchParams.set('database', this.database);
    url.searchParams.set('default_format', 'JSONEachRow');

    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'text/plain',
      },
      body: sql,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`ClickHouse query failed (${response.status}): ${body}`);
    }

    const text = await response.text();
    const elapsedMs = Math.round(performance.now() - start);

    if (!text.trim()) {
      return { rows: [], rowCount: 0, elapsedMs };
    }

    // JSONEachRow: one JSON object per line
    const rows = text
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line) as T);

    return { rows, rowCount: rows.length, elapsedMs };
  }

  /**
   * Get schema for all user tables in the database.
   */
  async getSchema(): Promise<SchemaColumn[]> {
    const result = await this.query<SchemaColumn>(`
      SELECT table, name, type
      FROM system.columns
      WHERE database = '${this.database}'
        AND table NOT LIKE '.inner%'
        AND table != '_migrations'
      ORDER BY table, position
    `);
    return result.rows;
  }

  /**
   * Health check — returns true if ClickHouse responds.
   */
  async ping(): Promise<boolean> {
    try {
      const url = new URL('/ping', this.baseUrl);
      const response = await fetch(url.toString(), {
        headers: { 'Authorization': this.authHeader },
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}
