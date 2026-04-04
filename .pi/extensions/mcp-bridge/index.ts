/**
 * MCP Bridge Extension for Pi
 *
 * Bridges MCP servers (ThetaData, Together AI Docs, Codemogger) into pi
 * as native tools. Pi doesn't support MCP natively, so this extension
 * acts as an MCP client and registers each server's tools.
 *
 * Supports three transport types:
 *  - SSE (ThetaData)
 *  - Streamable HTTP (Together AI Docs)
 *  - Stdio (Codemogger)
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { spawn, type ChildProcess } from "node:child_process";

// ─── Types ───────────────────────────────────────────────────────────

interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: string;
  id: number | string;
  result?: unknown;
  error?: { code: number; message: string };
}

// ─── Transport: Streamable HTTP ──────────────────────────────────────

async function mcpHttpCall(
  url: string,
  method: string,
  params: Record<string, unknown> = {},
  id: number = 1
): Promise<unknown> {
  const body = JSON.stringify({ jsonrpc: "2.0", id, method, params });
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    },
    body,
  });

  const text = await resp.text();

  // Streamable HTTP may return SSE format
  if (text.startsWith("event:")) {
    const dataLine = text.split("\n").find((l) => l.startsWith("data:"));
    if (dataLine) {
      const parsed = JSON.parse(dataLine.slice(5)) as JsonRpcResponse;
      if (parsed.error) throw new Error(parsed.error.message);
      return parsed.result;
    }
  }

  const parsed = JSON.parse(text) as JsonRpcResponse;
  if (parsed.error) throw new Error(parsed.error.message);
  return parsed.result;
}

// ─── Transport: SSE ──────────────────────────────────────────────────

async function mcpSseInit(
  baseUrl: string
): Promise<{ sessionUrl: string }> {
  // Connect to SSE endpoint to get session
  const resp = await fetch(baseUrl, {
    headers: { Accept: "text/event-stream" },
  });

  // Read the endpoint event which contains the session URL
  const reader = resp.body?.getReader();
  if (!reader) throw new Error("No response body from SSE endpoint");

  const decoder = new TextDecoder();
  let buffer = "";
  let sessionUrl = "";

  // Read until we get the endpoint event
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Look for endpoint event
    const endpointMatch = buffer.match(
      /event:\s*endpoint\ndata:\s*(\S+)/
    );
    if (endpointMatch) {
      sessionUrl = endpointMatch[1];
      break;
    }
  }

  // Don't close the reader - SSE connection stays open
  // But we need to stop blocking
  reader.cancel().catch(() => {});

  if (!sessionUrl) throw new Error("No endpoint event received from SSE");

  // Resolve relative URLs
  if (sessionUrl.startsWith("/")) {
    const url = new URL(baseUrl);
    sessionUrl = `${url.protocol}//${url.host}${sessionUrl}`;
  }

  // Initialize
  await mcpSsePost(sessionUrl, "initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "pi-mcp-bridge", version: "1.0.0" },
  });

  return { sessionUrl };
}

async function mcpSsePost(
  sessionUrl: string,
  method: string,
  params: Record<string, unknown> = {},
  id: number = 1
): Promise<unknown> {
  const body = JSON.stringify({ jsonrpc: "2.0", id, method, params });
  const resp = await fetch(sessionUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  const parsed = (await resp.json()) as JsonRpcResponse;
  if (parsed.error) throw new Error(parsed.error.message);
  return parsed.result;
}

// ─── Transport: Stdio ────────────────────────────────────────────────

class StdioTransport {
  private process: ChildProcess;
  private buffer = "";
  private pending = new Map<
    number,
    {
      resolve: (v: unknown) => void;
      reject: (e: Error) => void;
    }
  >();
  private nextId = 1;
  private ready: Promise<void>;

  constructor(command: string, args: string[]) {
    this.process = spawn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.process.stdout!.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString();
      this.processBuffer();
    });

    this.process.stderr!.on("data", (chunk: Buffer) => {
      // Silently ignore stderr (startup messages etc)
    });

    // Initialize
    this.ready = this.call("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "pi-mcp-bridge", version: "1.0.0" },
    }).then(() => {});
  }

  private processBuffer() {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line) as JsonRpcResponse;
        const pending = this.pending.get(Number(msg.id));
        if (pending) {
          this.pending.delete(Number(msg.id));
          if (msg.error) {
            pending.reject(new Error(msg.error.message));
          } else {
            pending.resolve(msg.result);
          }
        }
      } catch {
        // skip non-JSON lines
      }
    }
  }

  async call(
    method: string,
    params: Record<string, unknown> = {}
  ): Promise<unknown> {
    if (method !== "initialize") await this.ready;
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });
      this.process.stdin!.write(msg + "\n");
    });
  }

  kill() {
    this.process.kill();
  }
}

// ─── Extension ───────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  let codemoggerTransport: StdioTransport | null = null;
  let thetaSessionUrl: string | null = null;

  // ── Together AI Docs (Streamable HTTP) ─────────────────────────

  const TOGETHER_URL = "https://docs.together.ai/mcp";

  pi.registerTool({
    name: "search_together_ai_docs",
    label: "Search Together AI Docs",
    description:
      "Search across the Together AI documentation for relevant information, code examples, API references, and guides.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query" }),
    }),
    async execute(_id, params, signal) {
      try {
        // Initialize + call in one shot (stateless HTTP)
        await mcpHttpCall(TOGETHER_URL, "initialize", {
          protocolVersion: "2024-11-05",
          capabilities: {},
          clientInfo: { name: "pi-mcp-bridge", version: "1.0.0" },
        });
        const result = await mcpHttpCall(
          TOGETHER_URL,
          "tools/call",
          { name: "search_together_ai_docs", arguments: params },
          2
        );
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            { type: "text", text: `Error searching Together docs: ${msg}` },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  pi.registerTool({
    name: "get_page_together_ai_docs",
    label: "Get Together AI Docs Page",
    description:
      "Retrieve the full content of a specific Together AI documentation page by its path.",
    parameters: Type.Object({
      page: Type.String({
        description: "Page path (e.g. 'api-reference/chat-completions')",
      }),
    }),
    async execute(_id, params, signal) {
      try {
        await mcpHttpCall(TOGETHER_URL, "initialize", {
          protocolVersion: "2024-11-05",
          capabilities: {},
          clientInfo: { name: "pi-mcp-bridge", version: "1.0.0" },
        });
        const result = await mcpHttpCall(
          TOGETHER_URL,
          "tools/call",
          { name: "get_page_together_ai_docs", arguments: params },
          2
        );
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            { type: "text", text: `Error fetching Together docs page: ${msg}` },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  // ── Codemogger (Stdio) ─────────────────────────────────────────

  function getCodemogger(): StdioTransport {
    if (!codemoggerTransport) {
      codemoggerTransport = new StdioTransport("npx", [
        "-y",
        "codemogger",
        "mcp",
      ]);
    }
    return codemoggerTransport;
  }

  pi.registerTool({
    name: "codemogger_search",
    label: "Search Code Index",
    description:
      "Search an indexed codebase for relevant code. Two modes: 'semantic' (natural language) and 'keyword' (identifier lookup). Returns matching code chunks with file path, name, kind, signature, and line numbers.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query" }),
      mode: Type.Optional(
        Type.String({
          description:
            "Search mode: 'semantic' for conceptual, 'keyword' for exact identifier. Default: semantic",
        })
      ),
      limit: Type.Optional(
        Type.Number({
          description: "Max results (1-50, default 10)",
        })
      ),
      includeSnippet: Type.Optional(
        Type.Boolean({
          description:
            "Include full code snippet in results. Default: true",
        })
      ),
    }),
    async execute(_id, params, signal) {
      try {
        const transport = getCodemogger();
        const result = await transport.call("tools/call", {
          name: "codemogger_search",
          arguments: {
            query: params.query,
            mode: params.mode ?? "semantic",
            limit: params.limit ?? 10,
            includeSnippet: params.includeSnippet ?? true,
          },
        });
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            { type: "text", text: `Error searching code index: ${msg}` },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  pi.registerTool({
    name: "codemogger_index",
    label: "Index Codebase",
    description:
      "Index a directory of source code for later searching. Supports Rust, C, C++, Go, Python, Zig, Java, Scala, JavaScript, TypeScript, TSX, PHP, and Ruby. Incremental: only re-indexes changed files.",
    parameters: Type.Object({
      directory: Type.String({
        description: "Absolute path to the directory to index",
      }),
    }),
    async execute(_id, params, signal) {
      try {
        const transport = getCodemogger();
        const result = await transport.call("tools/call", {
          name: "codemogger_index",
          arguments: params,
        });
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            { type: "text", text: `Error indexing codebase: ${msg}` },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  pi.registerTool({
    name: "codemogger_reindex",
    label: "Reindex Codebase",
    description:
      "Update the code index after modifying files. Only re-processes changed files.",
    parameters: Type.Object({
      directory: Type.String({
        description: "Absolute path to the directory to reindex",
      }),
    }),
    async execute(_id, params, signal) {
      try {
        const transport = getCodemogger();
        const result = await transport.call("tools/call", {
          name: "codemogger_reindex",
          arguments: params,
        });
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            { type: "text", text: `Error reindexing: ${msg}` },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  // ── ThetaData (SSE) ────────────────────────────────────────────

  const THETA_SSE_URL = "http://127.0.0.1:25503/mcp/sse";

  async function callTheta(
    toolName: string,
    args: Record<string, unknown>
  ): Promise<unknown> {
    // Lazy init SSE session
    if (!thetaSessionUrl) {
      const session = await mcpSseInit(THETA_SSE_URL);
      thetaSessionUrl = session.sessionUrl;
    }
    return mcpSsePost(
      thetaSessionUrl,
      "tools/call",
      { name: toolName, arguments: args },
      Math.floor(Math.random() * 100000)
    );
  }

  // We don't know ThetaData's exact tool list until the server runs.
  // Register a generic passthrough tool that discovers and calls any tool.

  pi.registerTool({
    name: "thetadata_list_tools",
    label: "ThetaData: List Tools",
    description:
      "List all available tools from the ThetaData MCP server. Call this first to discover what data endpoints are available (options chains, greeks, historical snapshots, etc). Requires ThetaTerminal to be running on localhost:25503.",
    parameters: Type.Object({}),
    async execute(_id, _params, signal) {
      try {
        if (!thetaSessionUrl) {
          const session = await mcpSseInit(THETA_SSE_URL);
          thetaSessionUrl = session.sessionUrl;
        }
        const result = await mcpSsePost(
          thetaSessionUrl,
          "tools/list",
          {},
          Math.floor(Math.random() * 100000)
        );
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            {
              type: "text",
              text: `Error connecting to ThetaData MCP (is ThetaTerminal running?): ${msg}`,
            },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  pi.registerTool({
    name: "thetadata_call",
    label: "ThetaData: Call Tool",
    description:
      "Call a specific ThetaData MCP tool by name. Use thetadata_list_tools first to discover available tools and their parameters. Requires ThetaTerminal to be running on localhost:25503.",
    parameters: Type.Object({
      tool_name: Type.String({
        description: "The MCP tool name to call (from thetadata_list_tools)",
      }),
      arguments: Type.Optional(
        Type.Unknown({
          description:
            "Arguments object to pass to the tool (matches the tool's inputSchema)",
        })
      ),
    }),
    async execute(_id, params, signal) {
      try {
        const args = (params.arguments ?? {}) as Record<string, unknown>;
        const result = await callTheta(params.tool_name, args);
        return {
          content: [
            { type: "text", text: JSON.stringify(result, null, 2) },
          ],
          details: {},
        };
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [
            {
              type: "text",
              text: `Error calling ThetaData tool '${params.tool_name}': ${msg}`,
            },
          ],
          details: {},
          isError: true,
        };
      }
    },
  });

  // ── Cleanup ────────────────────────────────────────────────────

  pi.on("session_shutdown", async () => {
    if (codemoggerTransport) {
      codemoggerTransport.kill();
      codemoggerTransport = null;
    }
    thetaSessionUrl = null;
  });
}
