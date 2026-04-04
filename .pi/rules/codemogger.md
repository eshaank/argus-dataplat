---
description: Codemogger code search tool usage — use semantic/keyword search before falling back to Grep or Glob
alwaysApply: true
---

# Codemogger

## Repository Setup
When indexing a new repo or working in a repo for the first time:

- Ensure `.codemogger/` is in the repo's `.gitignore`. If missing, add it before running `codemogger_index`.

## Usage
- Use `codemogger_search` as the PRIMARY code search tool — before Grep, Glob, or Explore agents
- **Keyword mode** for exact identifiers: `codemogger_search("UserClaims", mode="keyword")`
- **Semantic mode** for concepts: `codemogger_search("how does auth work", mode="semantic")`
- Fall back to Grep/Glob only when: codemogger returns no results, you need every reference (not just definitions), or searching non-code files
- After creating/modifying/deleting source files, call `codemogger_reindex`
- To index a new project: `codemogger_index("/path/to/project")`