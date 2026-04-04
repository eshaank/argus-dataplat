---
description: List all available commands, skills, and agents
allowed-tools: ""
---

# Help — All Available Commands

Display the complete list of commands, skills, and agents available for this project.

**Project: finance-dashboard**

List all commands found in `.claude/commands/`, all skills in `.claude/skills/`, and all agents in `.claude/agents/`.

For each command, read its frontmatter `description` field and display it.
For each skill, read its frontmatter `name` and `triggers` fields.
For each agent, read its frontmatter `name` and `description` fields.

Format as a clean table grouped by category.
