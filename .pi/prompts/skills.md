---
description: List available skills and their activation triggers
allowed-tools: Read, Glob
---

# Available Skills

List all skills installed in this project.

## Steps

1. Find all `SKILL.md` files:
   ```bash
   find .claude/skills -name "SKILL.md" -type f
   ```

2. For each SKILL.md, read its frontmatter to extract:
   - `name`
   - `description`
   - `triggers`

3. Display as a formatted table:

| Skill | Description | Triggers |
|-------|-------------|----------|
| name  | description | trigger1, trigger2 |

4. Note which skills are from core vs which preset they came from (check the manifest files if available).
