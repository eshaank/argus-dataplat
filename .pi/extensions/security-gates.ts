import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { isToolCallEventType } from "@mariozechner/pi-coding-agent";

/**
 * Security Gates Extension
 *
 * Migrated from:
 *   - hooks/block-secrets.py (PreToolUse Read|Edit|Write)
 *   - hooks/verify-no-secrets.sh (Stop / turn_end)
 *
 * Blocks access to sensitive files and checks for secrets in staged git files.
 */

const SENSITIVE_FILENAMES = new Set([
  ".env",
  ".env.local",
  ".env.production",
  ".env.staging",
  ".env.development",
  "secrets.json",
  "secrets.yaml",
  "id_rsa",
  "id_ed25519",
  ".npmrc",
  ".pypirc",
  "credentials.json",
  "service-account.json",
  ".docker/config.json",
]);

const SENSITIVE_PATTERNS = [
  "aws/credentials",
  ".ssh/",
  "private_key",
  "secret_key",
];

function isSensitivePath(filePath: string): string | null {
  const fileName = filePath.split("/").pop() ?? "";

  if (SENSITIVE_FILENAMES.has(fileName)) {
    return `Access to '${filePath}' denied. This is a sensitive file.`;
  }

  for (const pattern of SENSITIVE_PATTERNS) {
    if (filePath.includes(pattern)) {
      return `Access to '${filePath}' denied. Path matches sensitive pattern '${pattern}'.`;
    }
  }

  return null;
}

export default function (pi: ExtensionAPI) {
  // Block access to sensitive files (read, edit, write)
  pi.on("tool_call", async (event, _ctx) => {
    let filePath: string | undefined;

    if (isToolCallEventType("read", event)) {
      filePath = event.input.path;
    } else if (isToolCallEventType("edit", event)) {
      filePath = event.input.path;
    } else if (isToolCallEventType("write", event)) {
      filePath = event.input.path;
      // Allow writing .env files (needed for scaffolding), only block read/edit
      const fileName = filePath?.split("/").pop() ?? "";
      if (fileName.startsWith(".env")) return;
    }

    if (!filePath) return;

    // Strip leading @ (some models include it)
    if (filePath.startsWith("@")) filePath = filePath.slice(1);

    const reason = isSensitivePath(filePath);
    if (reason) {
      return { block: true, reason: `BLOCKED: ${reason}` };
    }
  });

  // Check for secrets in staged files after each turn
  pi.on("turn_end", async (_event, _ctx) => {
    try {
      const inGit = await pi.exec("git", ["rev-parse", "--is-inside-work-tree"], { timeout: 5000 });
      if (inGit.code !== 0) return;

      const staged = await pi.exec("git", ["diff", "--cached", "--name-only"], { timeout: 5000 });
      if (staged.code !== 0 || !staged.stdout.trim()) return;

      const stagedFiles = staged.stdout.trim().split("\n");
      const violations: string[] = [];

      // Check for sensitive files being staged
      const sensitiveFiles = [
        ".env", ".env.local", ".env.production", ".env.staging",
        "secrets.json", "id_rsa", "id_ed25519", "credentials.json",
        "service-account.json", ".npmrc",
      ];

      for (const file of stagedFiles) {
        const fileName = file.split("/").pop() ?? "";
        if (sensitiveFiles.includes(fileName)) {
          violations.push(`SENSITIVE FILE STAGED: ${file}`);
        }
      }

      // Check staged file contents for secret patterns
      for (const file of stagedFiles) {
        const content = await pi.exec("git", ["show", `:${file}`], { timeout: 5000 });
        if (content.code !== 0 || !content.stdout) continue;

        if (/(?:api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*["'][A-Za-z0-9+/=_-]{16,}/i.test(content.stdout)) {
          violations.push(`POSSIBLE SECRET in ${file}`);
        }
        if (/AKIA[0-9A-Z]{16}/.test(content.stdout)) {
          violations.push(`AWS ACCESS KEY in ${file}`);
        }
      }

      if (violations.length > 0) {
        pi.sendMessage({
          customType: "security-gates",
          content: `⚠️ POTENTIAL SECRETS DETECTED:\n${violations.map((v) => `  - ${v}`).join("\n")}\n\nReview staged files before committing.`,
          display: true,
        }, { deliverAs: "steer", triggerTurn: true });
      }
    } catch {
      // Silently ignore errors — don't block the workflow
    }
  });
}
