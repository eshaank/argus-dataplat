# Project Rules — Base

---

## Critical Rules

### 0. NEVER Publish Sensitive Data

- NEVER commit passwords, API keys, tokens, or secrets to git/npm/docker
- NEVER commit `.env` files — ALWAYS verify `.env` is in `.gitignore`
- Before ANY commit: verify no secrets are included
- NEVER output secrets in suggestions, logs, or responses

### 1. NEVER Hardcode Credentials

- ALWAYS use environment variables for secrets
- NEVER put API keys, passwords, or tokens directly in code
- NEVER hardcode connection strings — use environment variables from .env

### 2. ALWAYS Ask Before Deploying

- NEVER auto-deploy, even if the fix seems simple
- NEVER assume approval — wait for explicit "yes, deploy"
- ALWAYS ask before deploying to production

---

## When Something Seems Wrong

Before jumping to conclusions:

- Test failing? → Read the error message fully BEFORE changing code
- Auth failing? → Check which auth system is configured BEFORE debugging
- Empty data? → Check if external API services are running BEFORE assuming broken

---

## Workflow Preferences

- Quality over speed — if unsure, ask before executing
- One task, one chat — `/clear` between unrelated tasks
- When testing: queue observations, fix in batch (not one at a time)

---

## Naming — NEVER Rename Mid-Project

If you must rename packages, modules, or key variables:

1. Create a checklist of ALL files and references first
2. Use IDE semantic rename (not search-and-replace)
3. Full project search for old name after renaming
4. Check: .md files, .txt files, .env files, comments, strings, paths
5. Start a FRESH session after renaming
