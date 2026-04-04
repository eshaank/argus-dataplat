#!/bin/bash
# Fire-and-forget autoresearch on all skills.
# Usage: tmux new -s autoresearch '.claude/scripts/run-autoresearch.sh'

# Do NOT use set -e — claude -p may exit non-zero and we want to continue

skills=(
  ui-design-system
  typescript-best-practices
  electron-development
  chat-orchestration
  agent-system
  domain-builder
  widget-builder
  duckdb-data-layer
  code-review
  massive-api
  polymarket-api
  testing-patterns
  vercel-react-best-practices
  supabase-postgres-best-practices
  together-chat-completions
)

cd /Users/eshaan/projects/finance-dashboard

# Return to main before starting (autoresearch creates its own branches)
git checkout main 2>/dev/null || true

for skill in "${skills[@]}"; do
  echo ""
  echo "============================================"
  echo "  AUTORESEARCH: $skill"
  echo "  $(date)"
  echo "============================================"

  # Return to main between runs so each autoresearch starts clean
  git checkout main 2>/dev/null || true

  yes | claude -p "/autoresearch $skill -- Evals are pre-generated and reviewed. Do NOT ask for confirmation. Start the loop immediately. Proceed without asking." --dangerously-skip-permissions --verbose || true

  exit_code=$?
  echo "=== Completed: $skill (exit: $exit_code) at $(date) ==="
done

echo ""
echo "============================================"
echo "  ALL DONE — $(date)"
echo "============================================"

# Keep tmux alive so you can read the output
echo "Press Enter to close..."
read
