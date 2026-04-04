---
name: electron-development
description: >
  Electron desktop application development patterns, security, IPC architecture,
  and packaging for the Argus project. Use this skill whenever working on: Electron
  main process code, preload scripts, IPC handlers, BrowserWindow configuration,
  tRPC-over-IPC integration, process sandboxing with @anthropic-ai/sandbox-runtime,
  electron-forge build/packaging, DMG distribution, context isolation, the agent
  execution system, or any code in the electron/ directory. Also trigger when
  modifying how the frontend communicates with the main process, adding new IPC
  channels, working on the bundled Python runtime, or debugging Electron-specific
  issues (white screen, IPC timeouts, packaging failures). If the task touches
  the desktop app shell in any way, load this skill.
---

# Electron Development

This skill covers general Electron security and architecture best practices, followed
by Argus-specific patterns for tRPC-over-IPC, agent sandboxing, and DMG packaging.

## General Electron Patterns

### Process Model — Understand the Boundary

Electron has two process types, and they have fundamentally different capabilities and
trust levels:

**Main process** — This is a Node.js process with full system access. It can read/write
files, spawn child processes, access the network, manage windows, and interact with native
OS APIs. It runs your tRPC server, domain logic, and agent orchestration. Treat it as your
backend.

**Renderer process** — This is a Chromium browser tab. It runs your React frontend. It
has NO direct access to Node.js, the filesystem, or the network (beyond standard browser
APIs). It can only talk to the main process through the IPC bridge exposed via the preload
script.

The security boundary between these two processes is the most important architectural
concept in Electron. Everything flows through IPC — never give the renderer direct access
to Node.js APIs.

### Security — The Non-Negotiables

These settings must be enabled for every BrowserWindow. They are not optional, not even
in development:

```typescript
const win = new BrowserWindow({
  webPreferences: {
    contextIsolation: true,     // Separate JS contexts for preload and renderer
    sandbox: true,              // Restrict renderer to browser-only APIs
    nodeIntegration: false,     // No require() in renderer
    nodeIntegrationInWorker: false,
    webviewTag: false,          // Disable <webview> (attack surface)
    preload: path.join(__dirname, 'preload.js'),
  },
});
```

**Why each one matters:**

- `contextIsolation: true` — Without this, your preload script shares a JavaScript context
  with the renderer. A malicious script injected via XSS could access everything the preload
  exposes, including raw Electron APIs. Context isolation creates a wall between them.

- `sandbox: true` — Restricts the renderer process at the OS level. Even if an attacker
  achieves code execution in the renderer, they can't access the filesystem or spawn processes.

- `nodeIntegration: false` — Never, ever enable this. It gives the renderer process full
  Node.js access, which means any XSS vulnerability becomes a full system compromise.

**Additional security hardening:**

```typescript
// Prevent navigation to untrusted origins
win.webContents.on('will-navigate', (event, url) => {
  const allowed = ['http://localhost:', 'file://'];
  if (!allowed.some(prefix => url.startsWith(prefix))) {
    event.preventDefault();
  }
});

// Block new window creation
win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

// Set a strict Content Security Policy
session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
  callback({
    responseHeaders: {
      ...details.responseHeaders,
      'Content-Security-Policy': [
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
      ],
    },
  });
});
```

### IPC — The Right Way

**Always use `invoke/handle` (request-response), not `send/on` (fire-and-forget).**

`invoke` returns a Promise, which means the renderer gets a response and can handle errors.
`send` is one-way — the renderer has no idea if the main process handled it successfully.

```typescript
// Main process
ipcMain.handle('argus:trpc', async (_event, payload) => {
  // Validate payload, call tRPC router, return result
  return result;
});

// Renderer (via preload)
const result = await window.argus.invoke('argus:trpc', { path, input });
```

The only exception to this is event streaming (like chat SSE), where the main process
needs to push events to the renderer. For that, use `webContents.send()` from main and
`ipcRenderer.on()` in the preload.

**Never use `sendSync()`.** It blocks the entire renderer process until the main process
responds. If the main process is busy, the UI freezes. There is no legitimate use case
for `sendSync()` in a modern Electron app.

**Never use `@electron/remote`.** It appears convenient but it exposes main-process objects
directly to the renderer, bypassing context isolation. It's a massive security hole and
a performance bottleneck.

### Preload Script — Keep It Minimal

The preload script is the bridge between main and renderer. Its job is to expose a narrow,
typed API via `contextBridge`. It should contain zero business logic.

```typescript
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('argus', {
  // Request-response (for tRPC and most operations)
  invoke: (channel: string, data?: unknown) => {
    const allowedChannels = ['argus:trpc', 'argus:chat:stream', 'argus:agent:submit'];
    if (!allowedChannels.includes(channel)) {
      throw new Error(`IPC channel not allowed: ${channel}`);
    }
    return ipcRenderer.invoke(channel, data);
  },

  // Event subscription (for streaming and status updates)
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    const allowedChannels = ['argus:chat:event', 'argus:agent:status'];
    if (!allowedChannels.includes(channel)) {
      throw new Error(`IPC channel not allowed: ${channel}`);
    }
    const subscription = (_event: Electron.IpcRendererEvent, ...args: unknown[]) => {
      callback(...args);
    };
    ipcRenderer.on(channel, subscription);
    // Return cleanup function
    return () => ipcRenderer.removeListener(channel, subscription);
  },
});
```

Key principles:

- **Allowlist channels.** Never pass arbitrary channel names from the renderer to `ipcRenderer`.
  An XSS attack could invoke internal Electron channels if you don't restrict this.
- **Strip the event object.** Never forward the `IpcRendererEvent` to the renderer — it
  contains internal Electron references that shouldn't leak.
- **Return cleanup functions** for event subscriptions so React components can unsubscribe
  in useEffect cleanup.

### Validate IPC Inputs in Main

Even though the renderer is your own React app, treat all IPC messages like untrusted
HTTP requests. The preload is a trust boundary — validate on both sides.

```typescript
ipcMain.handle('argus:trpc', async (event, payload) => {
  // Verify the sender is a known window
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || !trustedWindows.has(win.id)) {
    throw new Error('Unauthorized IPC sender');
  }

  // Validate payload shape
  const parsed = TRPCPayloadSchema.parse(payload);

  // Process the request
  return callTRPCRouter(parsed);
});
```

### Performance

**Keep the main process lean.** The main process runs on a single thread. If you block it
with heavy computation, window management and IPC both freeze. Offload CPU-intensive work
to worker threads or child processes.

```typescript
import { Worker } from 'worker_threads';

function runHeavyComputation(data: unknown): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const worker = new Worker('./workers/compute.js', { workerData: data });
    worker.on('message', resolve);
    worker.on('error', reject);
  });
}
```

**Lazy-load heavy modules.** Don't import everything at startup — use dynamic `import()`
for modules that aren't needed immediately:

```typescript
// Bad — delays app startup
import { SandboxManager } from '@anthropic-ai/sandbox-runtime';

// Good — loaded only when agents feature is first used
let sandboxManager: typeof import('@anthropic-ai/sandbox-runtime') | null = null;
async function getSandboxManager() {
  if (!sandboxManager) {
    sandboxManager = await import('@anthropic-ai/sandbox-runtime');
    await sandboxManager.SandboxManager.initialize(config);
  }
  return sandboxManager;
}
```

**Use `app.whenReady()` not `app.on('ready')`.** The former returns a Promise, so you
can `await` it and structure your startup sequence cleanly.

---

## Argus-Specific Patterns

### tRPC Over IPC

Argus uses tRPC for type-safe communication between the React renderer and the Electron
main process. Instead of HTTP, tRPC calls go through Electron IPC via a custom adapter.

There is an existing library `trpc-electron` (a fork of electron-trpc updated for tRPC v11)
that handles this. Use it rather than building a custom adapter from scratch.

**Main process setup:**

```typescript
import { app, BrowserWindow } from 'electron';
import { createIPCHandler } from 'trpc-electron/main';
import { appRouter } from './trpc/root';

app.whenReady().then(() => {
  const win = new BrowserWindow({
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  createIPCHandler({ router: appRouter, windows: [win] });

  // Load the React frontend
  if (process.env.NODE_ENV === 'development') {
    win.loadURL('http://localhost:5173');
  } else {
    win.loadFile(path.join(__dirname, '../frontend/dist/index.html'));
  }
});
```

**Preload setup:**

```typescript
import { exposeElectronTRPC } from 'trpc-electron/main';

process.once('loaded', async () => {
  exposeElectronTRPC();
});
```

**Renderer client:**

```typescript
import { createTRPCClient } from '@trpc/client';
import { ipcLink } from 'trpc-electron/renderer';
import type { AppRouter } from '../../electron/trpc/root';

export const trpc = createTRPCClient<AppRouter>({
  links: [ipcLink()],
});
```

This gives you full type safety end-to-end — the renderer knows exactly what procedures
exist, what inputs they accept, and what they return, all enforced at compile time.

### Chat Streaming — Dedicated IPC Channel

tRPC's request-response model doesn't fit SSE-style streaming well. For the chat/LLM
domain, use a dedicated IPC channel alongside the tRPC integration:

```typescript
// Main process — sends streaming events to renderer
function streamChatResponse(win: BrowserWindow, messages: ChatMessage[]) {
  const eventChannel = 'argus:chat:event';

  // Together AI streaming callback
  for await (const chunk of togetherStream) {
    win.webContents.send(eventChannel, {
      type: chunk.type, // 'thinking' | 'text' | 'tool_start' | 'tool_result' | 'done'
      content: chunk.content,
    });
  }
}

// Renderer — subscribes to events
const cleanup = window.argus.on('argus:chat:event', (event) => {
  // Update chat UI with streaming event
});

// In React useEffect cleanup
return () => cleanup();
```

The chat domain still has a tRPC router for non-streaming operations (fetching chat
history, managing conversations) — only the live streaming goes through the dedicated channel.

### Agent Sandbox — @anthropic-ai/sandbox-runtime

Argus uses Anthropic's open-source sandbox runtime to execute AI-generated scripts in
isolation. This is OS-level sandboxing using macOS `sandbox-exec` — no Docker, no VMs,
no external dependencies.

**Architecture:**

```
User requests backtest
  → Main process (tRPC) receives request
    → Orchestrator calls Together AI to plan research steps
      → Workspace manager creates temp directory for job
        → SandboxManager wraps the execution command
          → Sandboxed process runs with restricted filesystem + network
            → Results collected from workspace directory
              → Status update sent to renderer via IPC
```

**Sandbox configuration pattern:**

```typescript
import { SandboxManager } from '@anthropic-ai/sandbox-runtime';

const sandboxConfig = {
  network: {
    // Only allow the APIs the agent actually needs
    allowedDomains: ['api.polygon.io', 'api.stlouisfed.org'],
    deniedDomains: [],
    allowLocalBinding: false,
  },
  filesystem: {
    // Writes denied by default — only allow the job workspace
    allowWrite: [`./agent-workspaces/${jobId}/`],
    denyWrite: ['.env', '~', '..'],
    // Reads allowed by default — deny sensitive paths
    denyRead: ['.env', '.env.local', '~/.ssh', '~/.aws'],
    allowRead: ['./resources/'],
  },
};

await SandboxManager.initialize(sandboxConfig);
const wrapped = await SandboxManager.wrapWithSandbox(command);
// Execute `wrapped` as a child process
```

**Security rules for agent sandboxes:**

- Never allow write access outside the job's workspace directory
- Never allow network access to domains not explicitly needed by the script
- Always deny access to `.env`, SSH keys, and credential files
- Always clean up workspace directories after job completion (or failure)
- Set a timeout on agent execution — kill processes that run too long
- Capture both stdout and stderr — log stderr for debugging, return stdout as results

### Agent Execution Runtime

Agent scripts execute using `@anthropic-ai/sandbox-runtime` with OS-level sandboxing.
The Pi multi-agent system (`electron/agents/`) orchestrates specialist agents (orchestrator,
data-analyst, visualizer) that run in isolated sandboxes with filesystem and network restrictions.

Key files:
- `electron/agents/agent-factory.ts` — Creates configured Pi Agent instances by role
- `electron/agents/agent-roles.ts` — System prompts, models, budgets per specialist
- `electron/agents/workspace.ts` — Workspace lifecycle + directory conventions
- `electron/agents/shared-extensions/` — Reusable Pi extensions (data tools, sandbox bash, safety limits)

### Electron Forge — DMG Packaging

Argus is packaged as a macOS DMG using electron-forge.

**Key configuration points:**

```typescript
// forge.config.ts
export default {
  packagerConfig: {
    name: 'Argus',
    executableName: 'argus',
    icon: './assets/icon',
    osxSign: {},  // Code signing (configure when ready for distribution)
    extraResource: [
      './resources',  // Extra resources (outside asar)
    ],
    asar: true,  // Pack app source into asar archive
  },
  makers: [
    { name: '@electron-forge/maker-dmg', config: {} },
    { name: '@electron-forge/maker-zip', platforms: ['darwin'] },
  ],
  plugins: [
    {
      name: '@electron-forge/plugin-vite',
      config: {
        // Vite builds both main process and renderer
        build: [
          { entry: 'electron/main.ts', config: 'vite.main.config.ts' },
          { entry: 'electron/preload.ts', config: 'vite.preload.config.ts' },
        ],
        renderer: [
          { name: 'main_window', config: 'vite.renderer.config.ts' },
        ],
      },
    },
  ],
};
```

**Build commands:**

```bash
npm run build        # Build frontend + electron
npm run make         # Package into DMG
npm run start        # Run in development mode
```

**Common packaging pitfalls:**

- **Native modules** — If any dependency uses native addons (e.g., better-sqlite3), they
  need to be rebuilt for Electron's Node.js version. Use `electron-rebuild` or configure
  forge to handle this.
- **Path resolution** — `__dirname` behaves differently in development vs production (asar).
  Always use `app.isPackaged` to branch path resolution. Use `app.getPath('userData')` for
  persistent user data, not relative paths.
- **asar and child processes** — Code inside the asar archive can't be executed as a child
  process. Any bundled runtimes must be in `extraResource`, not inside the asar.
- **Code signing** — macOS Gatekeeper will quarantine unsigned apps. For distribution beyond
  your own machine, you need an Apple Developer certificate and notarization. Skip this for
  development, but plan for it before shipping.

### Dev vs Production Mode

Use a consistent pattern for switching between development and production behavior:

```typescript
const isDev = !app.isPackaged;

// Window loading
if (isDev) {
  win.loadURL('http://localhost:5173');
  win.webContents.openDevTools();
} else {
  win.loadFile(path.join(__dirname, '../frontend/dist/index.html'));
}

// Logging
if (isDev) {
  app.commandLine.appendSwitch('enable-logging');
}
```

Never use `process.env.NODE_ENV` for this check in the main process — it's unreliable
after packaging. `app.isPackaged` is the canonical way to detect production in Electron.

### App Lifecycle

```typescript
// macOS convention — keep app running when all windows are closed
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// macOS convention — recreate window when dock icon clicked
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// Cleanup on quit — stop agent processes, close connections
app.on('before-quit', async () => {
  await agentOrchestrator.cancelAll();
  await SandboxManager.cleanup();
});
```

### Reference Files

For deeper guidance on specific topics, read these files in the `references/` directory:

- `references/electron-security-checklist.md` — Complete security audit checklist for production
- `references/trpc-electron-setup.md` — Step-by-step tRPC + Electron integration with trpc-electron library

---

## Pi Multi-Agent Research System

Argus uses Pi (`@mariozechner/pi-agent-core` + `@mariozechner/pi-ai`) for complex financial research tasks. The chat LLM delegates via the `run_research_agent` tool to a Pi-powered orchestrator.

### Architecture

```
Chat LLM → run_research_agent → Pi Orchestrator (GLM-5)
  ├── Domain data tools (get_income_statement, get_quote, etc.) — direct calls
  ├── create_artifact — renders JSX visualizations in chat
  └── run_data_analysis → Data Analyst sub-agent (for computation tasks)
```

**Key files:**
- `electron/agents/agent-factory.ts` — Creates Pi Agent instances by role
- `electron/agents/agent-roles.ts` — System prompts, model IDs, budgets, tool lists
- `electron/agents/agent-bridge.ts` — Translates Pi events → Argus IPC events
- `electron/agents/pi-imports.ts` — ESM import helper (bypasses pi-ai exports map)
- `electron/agents/shared-extensions/` — Reusable Pi tools (domain data, sandbox bash, safety limits)
- `electron/agents/sub-agents/orchestrator.ts` — Main research agent with `create_artifact`

### ESM/CommonJS Bridge (Critical)

Pi packages are **ESM-only** (`"type": "module"`, no CJS fallback). The Electron main process runs **CommonJS**. This means:

```typescript
// WRONG — fails at runtime with "No exports main defined"
import { Agent } from '@mariozechner/pi-agent-core';
const { Type } = await import('@mariozechner/pi-ai');

// CORRECT — use pi-imports.ts helper for pi-ai
import type { Agent } from '@mariozechner/pi-agent-core'; // type-only OK
const { Agent } = await import('@mariozechner/pi-agent-core'); // works (no exports map)
const { importPiAi } = await import('./pi-imports');
const { Type } = await importPiAi(); // resolves file path, bypasses exports map
```

`pi-agent-core` works with plain `await import()` (no restrictive exports map).
`pi-ai` requires `pi-imports.ts` which resolves the dist entry point by filesystem traversal.

### Per-Agent Budgets

Each specialist has independent limits enforced by `safety-limits.ts`:

| Role | Turns | Cost | Wall Clock | Model |
|------|-------|------|------------|-------|
| Orchestrator | 25 | $1.00 | 8 min | zai-org/GLM-5 |
| Data Analyst | 20 | $0.30 | 4 min | Llama 3.3 70B |
| Visualizer | 12 | $0.15 | 3 min | Llama 3.1 8B |

### Workspace Conventions

All agents write to a persistent conversation workspace at `.argus/workspaces/{conversationId}/`:

```
data/        — JSON/CSV from data analyst
charts/      — PNG/HTML from visualizer
scripts/     — Analysis scripts
dashboards/  — HTML dashboards
_meta/       — Internal metadata
```

### Artifact Pipeline

The orchestrator creates visualizations via `create_artifact` tool:
1. Orchestrator writes JSX code + passes data (inline or from workspace file)
2. `create_artifact` validates code via `validateCodeStructure` + `validateCodeSyntax` (Sucrase dry-run)
3. If validation fails → error returned to orchestrator → it fixes and retries
4. If valid → emitted as `agent:artifact` event through bridge → chat IPC → iframe renderer

### Adding a New Agent Role

1. Add role to `AgentRole` union type in `shared/types/agents.ts`
2. Add system prompt, model ID, tool list, budget to `agent-roles.ts`
3. Create `electron/agents/sub-agents/<role>.ts` with factory + runner functions
4. Wire into orchestrator as a tool (or standalone via job queue)

### Common Pitfalls

- **Model selection matters for tool-calling.** GLM-5 reliably calls TypeBox-schema tools. Llama 3.3 often responds with text instead. Always test tool-calling behavior when changing models.
- **Don't delegate simple data fetches to sub-agents.** The orchestrator has domain tools. Only use `run_data_analysis` for computation that can't be done with raw API data.
- **Always validate JSX before emitting.** Reuse `validateCodeStructure` and `validateCodeSyntax` from `visualization-handler.ts`. Never emit unvalidated code.
- **Tool execution is sequential by default.** Set in `agent-factory.ts` via `toolExecution: 'sequential'`. Parallel execution would be faster but may hit rate limits.
