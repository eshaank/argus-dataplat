---
description: Validate harness installation — symlinks, hooks, tools, dependencies
allowed-tools: Bash, Read, Glob
---

# Harness Health Check

Run a comprehensive health check on the harness installation.

## Checks to Perform

### 1. Symlinks
Verify all expected symlinks exist and resolve correctly:

```bash
for link in .claude .rules CLAUDE.md AGENTS.md; do
    if [ -L "$link" ]; then
        target=$(readlink "$link")
        if [ -e "$link" ]; then
            echo "OK: $link → $target"
        else
            echo "BROKEN: $link → $target (target missing)"
        fi
    elif [ -e "$link" ]; then
        echo "WARNING: $link exists but is not a symlink"
    else
        echo "MISSING: $link"
    fi
done
```

### 2. Hook Executability
Verify all hooks are executable:

```bash
for hook in .claude/hooks/*; do
    if [ -f "$hook" ]; then
        if [ -x "$hook" ]; then
            echo "OK: $hook (executable)"
        else
            echo "WARNING: $hook (not executable — run chmod +x)"
        fi
    fi
done
```

### 3. Required Tools
Check that hook dependencies are installed:

```bash
# Python 3 (required by block-secrets.py and all hooks that parse JSON)
python3 --version 2>/dev/null && echo "OK: python3" || echo "MISSING: python3"

# lsof (required by check-ports.sh)
command -v lsof &>/dev/null && echo "OK: lsof" || echo "MISSING: lsof"

# git (required by check-branch.sh, verify-no-secrets.sh)
git --version 2>/dev/null && echo "OK: git" || echo "MISSING: git"
```

### 4. Optional Linter Tools
Check which linters are available for lint-on-save.sh:

```bash
command -v npx &>/dev/null && echo "OK: npx (TypeScript/JS linting)" || echo "OPTIONAL: npx not found"
command -v ruff &>/dev/null && echo "OK: ruff (Python linting)" || echo "OPTIONAL: ruff not found"
command -v go &>/dev/null && echo "OK: go (Go linting)" || echo "OPTIONAL: go not found"
```

### 5. Configuration
Verify harness.config.json exists and is valid:

```bash
if [ -f "harness/harness.config.json" ]; then
    python3 -c "import json; json.load(open('harness/harness.config.json'))" 2>/dev/null \
        && echo "OK: harness.config.json (valid JSON)" \
        || echo "ERROR: harness.config.json (invalid JSON)"
else
    echo "WARNING: harness/harness.config.json not found"
fi
```

### 6. Env Sync
Check .env and .env.example status:

```bash
[ -f ".env" ] && echo "OK: .env exists" || echo "INFO: no .env file"
[ -f ".env.example" ] && echo "OK: .env.example exists" || echo "WARNING: no .env.example"

# Check .gitignore
if [ -f ".gitignore" ]; then
    grep -q "\.env" .gitignore && echo "OK: .env in .gitignore" || echo "WARNING: .env not in .gitignore"
fi
```

### 7. MCP Servers
If mcp.json exists, check server URLs are reachable:

```bash
if [ -f ".mcp.json" ]; then
    echo "MCP servers configured:"
    python3 -c "
import json
with open('.mcp.json') as f:
    config = json.load(f)
for name, server in config.get('mcpServers', {}).items():
    print(f'  {name}: {server.get(\"url\", \"no url\")}')
"
fi
```

## Output Format

| Check | Status | Details |
|-------|--------|---------|
| Symlinks | OK/BROKEN/MISSING | list |
| Hooks | OK/WARNING | list |
| Required tools | OK/MISSING | list |
| Optional tools | OK/MISSING | list |
| Config | OK/ERROR | details |
| Env files | OK/WARNING | details |
| MCP servers | OK/UNREACHABLE | list |

**Overall: HEALTHY / NEEDS ATTENTION / BROKEN**
