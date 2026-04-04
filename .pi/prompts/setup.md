---
description: Interactive project setup — configure .env for frontend, backend, and API keys
argument-hint: [--reset]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# Project Setup

Walk the user through configuring environment variables for this TypeScript + Python stack. Creates or updates the `.env` file with real values while keeping `.env.example` as the template.

**Arguments:** $ARGUMENTS

If `--reset` is passed, start fresh (re-ask all questions even if .env already has values).

## Step 0 — Check Current State

```bash
# Does .env exist?
ls .env 2>/dev/null

# Does .env.example exist?
ls .env.example 2>/dev/null

# Is .env in .gitignore?
grep -q "^\.env$" .gitignore 2>/dev/null && echo ".env is gitignored" || echo "WARNING: .env NOT in .gitignore"
```

If `.env` doesn't exist, create it from `.env.example`.
If `.env.example` doesn't exist, create a blank `.env`.
If `.env` is NOT in `.gitignore`, add it immediately before proceeding.

## Step 0.5 — Development Environment Check (WSL)

Detect the current environment:

```bash
# Check if running on WSL
uname -r 2>/dev/null | grep -qi "microsoft\|wsl" && echo "WSL_DETECTED=true" || echo "WSL_DETECTED=false"

# Check if running on Windows (not WSL)
uname -s 2>/dev/null | grep -qi "mingw\|msys\|cygwin" && echo "WINDOWS_NATIVE=true" || echo "WINDOWS_NATIVE=false"

# Check current working directory — is the project on the Windows filesystem from WSL?
pwd | grep -q "^/mnt/c\|^/mnt/d" && echo "PROJECT_ON_WINDOWS_FS=true" || echo "PROJECT_ON_WINDOWS_FS=false"
```

### If on Windows (native, not WSL):

Tell the user:

```
⚠️  You're running on Windows natively.

STRONGLY RECOMMENDED: Use WSL 2 (Windows Subsystem for Linux) instead.

Why this matters:
  • HMR (hot module replacement) is 5-10x faster in WSL
  • File watching (Vite, uvicorn --reload) is dramatically more reliable
  • Node.js and Python tooling avoid the NTFS translation layer
  • Claude Code runs faster with native Linux tools (grep, find, git)

Setup (one time):
  1. Open PowerShell as admin: wsl --install
  2. Restart your computer
  3. Install VS Code extension: "WSL" (ms-vscode-remote.remote-wsl)
  4. Open VS Code → click green "><" bottom-left → "Connect to WSL"
  5. Clone your projects INSIDE WSL: ~/projects/ (NOT /mnt/c/)

After setup, VS Code runs its backend inside WSL while the UI stays on Windows.
```

### If on WSL but project is on the Windows filesystem (/mnt/c/ or /mnt/d/):

Tell the user:

```
⚠️  You're on WSL but your project is on the Windows filesystem (/mnt/c/...).

This kills most WSL performance benefits. File operations between WSL and the
Windows filesystem go through a slow translation layer.

MOVE YOUR PROJECT to the native WSL filesystem:
  mkdir -p ~/projects
  cp -r /mnt/c/Users/you/projects/finance-dashboard ~/projects/finance-dashboard
  cd ~/projects/finance-dashboard

Then open VS Code from WSL:
  code .

This alone can make HMR 5-10x faster and fix unreliable file watching.
```

### If on WSL with project on Linux filesystem:

```
✓ WSL detected with project on native Linux filesystem — optimal setup.
```

### If on macOS or native Linux:

Skip this check entirely — no action needed.

## Step 1 — Read .env.example

Read `.env.example` to see which variables this project needs. This project uses:

- **Frontend:** `VITE_API_BASE_URL` (backend URL for the React app)
- **Backend:** `MASSIVE_API_KEY`, `DEBUG`

## Step 2 — Interactive Configuration

Ask the user about each variable. Show the current value (if set in .env) and ask if they want to change it. Skip variables that already have real values unless `--reset` was passed.

### Category: Frontend

- **`VITE_API_BASE_URL`** — Backend API base URL (e.g. `http://localhost:8000`). The Vite app uses this to call the FastAPI backend. For local dev, use `http://localhost:8000`.

Ask: "What's the backend URL for the frontend? (e.g. http://localhost:8000 for local dev)"

### Category: Backend (API keys)

- **`MASSIVE_API_KEY`** — API key for Polygon.io and Massive (market data and fundamentals). Get from https://massive.com. **NEVER display this value back to the user after they enter it.**

Ask: "Do you have a MASSIVE_API_KEY for market data? (Get it from https://massive.com)"

### Category: Backend (debug)

- **`DEBUG`** — Enable FastAPI debug mode (true/false). Default: `false` for production, `true` for local dev if desired.

Ask: "Enable DEBUG for the backend?" (yes/no) — write `true` or `false`.

### Category: GitHub (optional)

Ask: "Do you want to configure GitHub (username, SSH vs HTTPS) for this project?" (yes/no)

If yes:
- GitHub username — for git remote URLs and PR creation
- SSH or HTTPS — which auth method for git?

## Step 3 — Write .env

Write all configured values to `.env`. Format with category comments matching `.env.example`.

**CRITICAL RULES:**
- NEVER display secrets (e.g. MASSIVE_API_KEY) back to the user after they enter them
- NEVER commit the .env file
- Confirm .env is in .gitignore after writing
- Show a summary of what was configured (category names only, NOT values)

## Step 4 — Update .env.example

If the user added any NEW variables that aren't in `.env.example`, add them with placeholder values so the template stays in sync.

## Step 5 — Report

```
Project Setup Complete
======================
✓ Frontend (VITE_API_BASE_URL)
✓ Backend (MASSIVE_API_KEY, DEBUG)
✓ GitHub (username: <username> or skipped)

.env is gitignored: ✓
.env.example updated: ✓
```

Show ✓ for configured categories.

Remind the user how to run the stack:
- Start backend: `cd backend && uv run uvicorn app.main:app --reload` (port 8000)
- Start frontend: `cd frontend && npm run dev` (port 5173)
