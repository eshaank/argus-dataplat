import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { isToolCallEventType } from "@mariozechner/pi-coding-agent";

/**
 * Git Guards Extension
 *
 * Migrated from:
 *   - hooks/check-branch.sh (PreToolUse Bash) — blocks commits to main/master
 *   - hooks/check-e2e.sh (PreToolUse Bash) — warns before pushing to main without E2E tests
 */

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (!isToolCallEventType("bash", event)) return;

    const command = event.input.command;
    if (!command) return;

    // --- Branch Protection: block commits to main/master ---
    if (/git\s+commit/.test(command)) {
      try {
        // Detect git -C <path> in the command
        const gitCMatch = command.match(/git\s+-C\s+([^\s]+)\s+/);
        const gitArgs = gitCMatch ? ["-C", gitCMatch[1]] : [];

        const inGit = await pi.exec("git", [...gitArgs, "rev-parse", "--is-inside-work-tree"], { timeout: 5000 });
        if (inGit.code !== 0) return;

        // Allow initial commits
        const hasHead = await pi.exec("git", [...gitArgs, "rev-parse", "HEAD"], { timeout: 5000 });
        if (hasHead.code !== 0) return;

        const branchResult = await pi.exec("git", [...gitArgs, "branch", "--show-current"], { timeout: 5000 });
        const branch = branchResult.stdout.trim();

        if (branch === "main" || branch === "master") {
          return {
            block: true,
            reason: `BLOCKED: You're committing directly to '${branch}'. Create a feature branch first:\n  git checkout -b feat/<feature-name>`,
          };
        }
      } catch {
        // Don't block on errors
      }
    }

    // --- E2E Test Check: warn before pushing to main ---
    if (/git\s+push/.test(command)) {
      try {
        const inGit = await pi.exec("git", ["rev-parse", "--is-inside-work-tree"], { timeout: 5000 });
        if (inGit.code !== 0) return;

        const branchResult = await pi.exec("git", ["branch", "--show-current"], { timeout: 5000 });
        const branch = branchResult.stdout.trim();

        let pushingToMain = false;

        // Explicit push to main/master
        if (/git\s+push\s+\S+\s+(main|master)/.test(command)) {
          pushingToMain = true;
        }
        // On main/master without explicit branch target
        if ((branch === "main" || branch === "master") && !/git\s+push\s+\S+\s+\S+/.test(command)) {
          pushingToMain = true;
        }

        if (!pushingToMain) return;

        // Check for E2E tests
        const e2eDir = await pi.exec("test", ["-d", "tests/e2e"], { timeout: 5000 });
        if (e2eDir.code !== 0) {
          ctx.ui.notify("⚠️ No tests/e2e/ directory found. Consider creating E2E tests.", "warning");
          return;
        }

        const findTests = await pi.exec("find", ["tests/e2e", "-name", "*.spec.ts", "-o", "-name", "*.test.ts", "-o", "-name", "*_test.go"], { timeout: 5000 });
        const realTests = findTests.stdout
          .trim()
          .split("\n")
          .filter((f) => f && !f.includes("example-homepage.spec.ts"));

        if (realTests.length === 0) {
          ctx.ui.notify("⚠️ No E2E tests found. Consider creating E2E tests before pushing to main.", "warning");
        }
      } catch {
        // Don't block on errors
      }
    }
  });
}
