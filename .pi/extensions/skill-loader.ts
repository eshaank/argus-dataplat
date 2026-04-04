import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { isToolCallEventType } from "@mariozechner/pi-coding-agent";

/**
 * Skill Loader Extension
 *
 * Migrated from:
 *   - hooks/skill-loader-reminder.sh (UserPromptSubmit) — reminds to load skills
 *   - hooks/skill-loader-gate.sh (PreToolUse Edit|Write) — warns before edits without skills
 *
 * Injects skill-loading reminders into the system prompt and warns
 * before file edits to ensure skills are consulted first.
 */

const SKILL_REMINDER = `Before writing ANY code, you MUST:
1. Identify matching skills for this task from the available skills list
2. Read each matching SKILL.md file using the Read tool
3. Verify codebase state (package.json, actual file structure)
4. ONLY THEN begin exploring or coding

Quick reference:
  Frontend/UI        → ui-design-system + vercel-react-best-practices
  Chat/LLM/streaming → chat-orchestration
  Widget type        → widget-builder + ui-design-system
  Backend domain     → domain-builder + massive-api
  Electron/IPC       → electron-development
  TypeScript         → typescript-best-practices
  Supabase/auth/DB   → supabase-postgres-best-practices
  Code review        → code-review

If the user's message is a question, greeting, or non-code task, you may skip this.
Otherwise: READ THE SKILLS FIRST. No exceptions.`;

// Paths that are safe to edit without loading skills
const SAFE_PATH_PATTERNS = [
  /\.pi\/(hooks|settings|extensions)/,
  /\.claude\/(hooks|settings|projects)/,
  /project-docs\/plans/,
  /memory\//,
  /tasks\//,
  /SKILL\.md$/,
  /CLAUDE\.md$/,
  /AGENTS\.md$/,
  /\.rules\//,
];

function isSafePath(filePath: string): boolean {
  return SAFE_PATH_PATTERNS.some((pattern) => pattern.test(filePath));
}

export default function (pi: ExtensionAPI) {
  // Inject skill-loading reminder into system prompt on each turn
  pi.on("before_agent_start", async (event, _ctx) => {
    return {
      systemPrompt: event.systemPrompt + "\n\n## Skill Loader Reminder\n\n" + SKILL_REMINDER,
    };
  });

  // Warn before file edits if skills may not have been loaded
  pi.on("tool_call", async (event, _ctx) => {
    if (!isToolCallEventType("edit", event) && !isToolCallEventType("write", event)) return;

    const filePath = event.input.path;
    if (!filePath) return;

    // Skip safe paths
    if (isSafePath(filePath)) return;

    // This is a non-blocking warning — just inject context
    // The message goes to stderr equivalent (shown to LLM but doesn't block)
    // In pi extensions, we can't inject a warning without blocking,
    // so we use sendMessage with steer delivery
    pi.sendMessage({
      customType: "skill-loader",
      content: `SKILL-LOADER CHECK: You are about to edit/create '${filePath}'. Have you loaded the matching SKILL.md files for this task? If not — STOP, read the skills first, then come back to this edit.`,
      display: false, // Don't clutter the UI
    }, { deliverAs: "steer" });
  });
}
