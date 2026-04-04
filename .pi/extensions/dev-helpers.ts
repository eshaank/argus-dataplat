import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { isToolCallEventType } from "@mariozechner/pi-coding-agent";

/**
 * Dev Helpers Extension
 *
 * Migrated from:
 *   - hooks/check-ports.sh (PreToolUse Bash) — blocks starting server on occupied port
 *   - hooks/check-rybbit.sh (PreToolUse Bash) — blocks deploy without Rybbit config
 *   - hooks/lint-on-save.sh (PostToolUse Write) — runs linter after file write
 *   - hooks/check-env-sync.sh (Stop) — warns about .env/.env.example drift
 */

function detectPort(command: string): string | null {
  // Explicit port flags: -p 3000, --port 3000, --port=3000
  let match = command.match(/(?:-p|--port[= ])\s*(\d+)/);
  if (match) return match[1];

  // PORT= environment variable prefix
  match = command.match(/PORT=(\d+)/);
  if (match) return match[1];

  // Common defaults: npm/pnpm/yarn/bun run dev
  if (/(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?dev\s*$/.test(command)) {
    return "3000";
  }

  return null;
}

function isDeployCommand(command: string): boolean {
  // Skip git operations
  if (/git\s+(commit|add|push|merge|rebase|checkout|branch|tag|log|diff|status)/.test(command)) {
    return false;
  }
  return /docker\s+push|vercel\s+deploy|vercel\s+--prod|curl.*application\.deploy/i.test(command);
}

export default function (pi: ExtensionAPI) {
  // --- Port Conflict Check ---
  pi.on("tool_call", async (event, _ctx) => {
    if (!isToolCallEventType("bash", event)) return;
    const command = event.input.command;
    if (!command) return;

    const port = detectPort(command);
    if (!port) return;

    try {
      const lsof = await pi.exec("lsof", ["-ti", `:${port}`], { timeout: 5000 });
      if (lsof.code !== 0 || !lsof.stdout.trim()) return;

      const pid = lsof.stdout.trim().split("\n")[0];
      const proc = await pi.exec("ps", ["-p", pid, "-o", "comm="], { timeout: 5000 });
      const procName = proc.stdout.trim() || "unknown";

      return {
        block: true,
        reason: `BLOCKED: Port ${port} is already in use by ${procName} (PID: ${pid}).\nKill it first: lsof -ti:${port} | xargs kill -9`,
      };
    } catch {
      // Don't block on errors
    }
  });

  // --- Rybbit Deploy Check ---
  pi.on("tool_call", async (event, _ctx) => {
    if (!isToolCallEventType("bash", event)) return;
    const command = event.input.command;
    if (!command || !isDeployCommand(command)) return;

    try {
      // Check if project uses Rybbit via config file
      const confCheck = await pi.exec("grep", ["-q", "analytics.*=.*rybbit", "claude-mastery-project.conf"], { timeout: 5000 });
      if (confCheck.code !== 0) return;

      // Check .env exists
      const envCheck = await pi.exec("test", ["-f", ".env"], { timeout: 5000 });
      if (envCheck.code !== 0) {
        return {
          block: true,
          reason: "BLOCKED: Rybbit analytics is configured but .env file is missing.\nCreate .env with NEXT_PUBLIC_RYBBIT_SITE_ID=<your-site-id> before deploying.",
        };
      }

      // Check site ID
      const grepResult = await pi.exec("grep", ["-E", "^NEXT_PUBLIC_RYBBIT_SITE_ID=", ".env"], { timeout: 5000 });
      const siteId = grepResult.stdout.trim().split("=").slice(1).join("=").replace(/["']/g, "").trim();

      if (!siteId) {
        return {
          block: true,
          reason: "BLOCKED: NEXT_PUBLIC_RYBBIT_SITE_ID is missing from .env.\nAdd it before deploying. Get your site ID from https://app.rybbit.io",
        };
      }

      if (/your_site|placeholder|changeme|your-site|example/i.test(siteId)) {
        return {
          block: true,
          reason: `BLOCKED: NEXT_PUBLIC_RYBBIT_SITE_ID appears to be a placeholder ('${siteId}').\nSet a real site ID from https://app.rybbit.io before deploying.`,
        };
      }
    } catch {
      // Don't block on errors
    }
  });

  // --- Lint on Save ---
  pi.on("tool_result", async (event, _ctx) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return;
    if (event.isError) return;

    const filePath = (event.input as { path?: string }).path;
    if (!filePath) return;

    const ext = filePath.split(".").pop()?.toLowerCase();
    if (!ext) return;

    try {
      let lintResult: { stdout: string; stderr: string; code: number } | undefined;

      switch (ext) {
        case "ts":
        case "tsx": {
          const hasTsConfig = await pi.exec("test", ["-f", "tsconfig.json"], { timeout: 2000 });
          if (hasTsConfig.code === 0) {
            lintResult = await pi.exec("npx", ["tsc", "--noEmit", "--pretty", filePath], { timeout: 15000 });
          }
          break;
        }
        case "js":
        case "jsx": {
          lintResult = await pi.exec("npx", ["eslint", "--no-error-on-unmatched-pattern", filePath], { timeout: 15000 });
          break;
        }
        case "py": {
          const hasRuff = await pi.exec("which", ["ruff"], { timeout: 2000 });
          if (hasRuff.code === 0) {
            lintResult = await pi.exec("ruff", ["check", filePath], { timeout: 15000 });
          }
          break;
        }
        case "go": {
          const hasGo = await pi.exec("which", ["go"], { timeout: 2000 });
          if (hasGo.code === 0) {
            lintResult = await pi.exec("go", ["vet", filePath], { timeout: 15000 });
          }
          break;
        }
      }

      // If lint found issues, inject them as a steer message so the LLM sees the errors
      if (lintResult && lintResult.code !== 0) {
        const output = (lintResult.stdout + "\n" + lintResult.stderr).trim();
        if (output) {
          const truncated = output.split("\n").slice(0, 20).join("\n");
          return {
            content: [
              ...event.content,
              { type: "text" as const, text: `\n\nLint issues in ${filePath}:\n${truncated}` },
            ],
          };
        }
      }
    } catch {
      // Lint failures are non-critical
    }
  });

  // --- Env Example Sync Check ---
  pi.on("turn_end", async (_event, ctx) => {
    try {
      const hasEnv = await pi.exec("test", ["-f", ".env"], { timeout: 2000 });
      const hasExample = await pi.exec("test", ["-f", ".env.example"], { timeout: 2000 });
      if (hasEnv.code !== 0 || hasExample.code !== 0) return;

      const envKeys = await pi.exec("bash", ["-c", `grep -E '^(export\\s+)?[A-Za-z_][A-Za-z0-9_]*=' .env | sed 's/^export *//' | cut -d'=' -f1 | sort -u`], { timeout: 5000 });
      const exampleKeys = await pi.exec("bash", ["-c", `grep -E '^(export\\s+)?[A-Za-z_][A-Za-z0-9_]*=' .env.example | sed 's/^export *//' | cut -d'=' -f1 | sort -u`], { timeout: 5000 });

      if (envKeys.code !== 0 || exampleKeys.code !== 0) return;

      const envSet = new Set(envKeys.stdout.trim().split("\n").filter(Boolean));
      const exampleSet = new Set(exampleKeys.stdout.trim().split("\n").filter(Boolean));

      const missing = [...envSet].filter((k) => !exampleSet.has(k));

      if (missing.length > 0) {
        ctx.ui.notify(
          `ENV SYNC: Keys in .env missing from .env.example:\n${missing.map((k) => `  - ${k}`).join("\n")}\nAdd them to .env.example with placeholder values.`,
          "warning"
        );
      }
    } catch {
      // Non-critical
    }
  });
}
