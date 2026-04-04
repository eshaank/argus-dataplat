---
description: Show project progress — what's done, what's pending, what's next
allowed-tools: Read, Bash(find:*), Bash(ls:*), Bash(wc:*), Bash(git log:*)
---

# Project Progress

Check the actual state of all source code and report status.

## Instructions

1. Read project docs or README for context (if they exist)
2. Auto-detect source directories by scanning for common patterns
3. Check test directories
4. Check recent git activity

## Shell Commands to Run

```bash
echo "=== Source Files ==="
# Auto-detect: find source files by extension
for ext in ts tsx js jsx py go rs rb java; do
    count=$(find . -name "*.$ext" -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/dist/*" -not -path "*/.git/*" 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" -gt 0 ] && echo "  .$ext files: $count"
done

echo ""
echo "=== Test Files ==="
find . -name "*.test.*" -o -name "*.spec.*" -o -name "test_*.py" -o -name "*_test.go" 2>/dev/null | grep -v node_modules | head -20

echo ""
echo "=== Recent Activity (Last 7 Days) ==="
git log --oneline --since="7 days ago" 2>/dev/null | head -15 || echo "No recent commits"

echo ""
echo "=== File Counts by Directory ==="
for dir in $(find . -maxdepth 2 -type d -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/.venv/*" -not -path "*/dist/*" 2>/dev/null | head -20); do
    count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" -gt 2 ] && echo "  $dir: $count files"
done
```

## Output Format

| Area | Files | Status | Notes |
|------|-------|--------|-------|
| Source code | N files | ... | ... |
| Tests | N files | ... | ... |
| Documentation | ... | ... | ... |

### Next Actions (Priority Order)
1. ...
2. ...
3. ...
