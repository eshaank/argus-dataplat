import type { DataPlatClient } from '../client.js';
import type { QueryResult, SchemaColumn } from '../types.js';

/**
 * Execute an arbitrary read-only SQL query.
 * The client enforces read-only validation — only SELECT/WITH/EXPLAIN allowed.
 */
export async function rawQuery<T = Record<string, unknown>>(
  client: DataPlatClient,
  sql: string,
): Promise<QueryResult<T>> {
  return client.query<T>(sql);
}

/** Get schema for all tables in the database. */
export async function getSchema(
  client: DataPlatClient,
): Promise<SchemaColumn[]> {
  return client.getSchema();
}
