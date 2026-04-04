---
description: Scan project for security issues — exposed secrets, missing .gitignore entries, unsafe patterns
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(grep:*), Bash(find:*)
---

# Security Check

Scan this project for security vulnerabilities. Auto-detect the project stack and run checks for all detected languages/frameworks.

## Checks to Perform

### 1. Secrets in Code
```bash
# Search for common secret patterns in tracked files (exclude lockfiles and node_modules)
git grep -n -E '(api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*["'\''"][A-Za-z0-9+/=_-]{8,}' -- ':!*.lock' ':!node_modules' 2>/dev/null || echo "No secrets found in code"

# Search for AWS keys
git grep -n 'AKIA[0-9A-Z]\{16\}' 2>/dev/null || echo "No AWS keys found"

# Search for hardcoded URLs with credentials
git grep -n -E '(https?://[^:]+:[^@]+@)' 2>/dev/null || echo "No credential URLs found"
```

### 2. .gitignore Coverage
Verify these entries exist in .gitignore:
- [ ] `.env`
- [ ] `.env.*`
- [ ] `.env.local`
- [ ] `node_modules/`
- [ ] `.venv/` (Python virtual environment)
- [ ] `dist/`
- [ ] `CLAUDE.local.md`
- [ ] `*.log`

### 3. Sensitive Files Check
```bash
# Check if any sensitive files are tracked by git
for f in .env .env.local .env.production secrets.json credentials.json id_rsa .npmrc; do
  git ls-files --error-unmatch "$f" 2>/dev/null && echo "WARNING: $f is tracked by git!"
done
echo "Sensitive file check complete."
```

### 4. .env File Verification
- [ ] `.env` exists but is NOT in git
- [ ] `.env.example` exists and IS in git
- [ ] `.env.example` has NO real values (only placeholders)

### 5. Dependency Audit

Auto-detect and run the appropriate audit:

```bash
# Node.js / npm
[ -f "package.json" ] && npm audit --production 2>/dev/null | head -20 || true

# Python / pip
if command -v pip-audit &>/dev/null; then
    pip-audit 2>/dev/null | head -25
elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
    echo "Python project detected but pip-audit not installed. Install with: pip install pip-audit"
fi

# Go
[ -f "go.mod" ] && go list -m -json all 2>/dev/null | head -20 || true

# Rust
[ -f "Cargo.toml" ] && command -v cargo-audit &>/dev/null && cargo audit 2>/dev/null | head -20 || true
```

### 6. Virtual Environment Not Committed
- [ ] `.venv/` is in .gitignore and not tracked

## Output Format

| Check | Status | Details |
|-------|--------|---------|
| Secrets in code | Pass/Fail | ... |
| .gitignore coverage | Pass/Fail | ... |
| Sensitive files tracked | Pass/Fail | ... |
| .env handling | Pass/Fail | ... |
| Dependencies | Pass/Fail | ... |
| .venv not committed | Pass/Fail | ... |

**Overall: PASS / FAIL**

List any specific remediation steps needed.
