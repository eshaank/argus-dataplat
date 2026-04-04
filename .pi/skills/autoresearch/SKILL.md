---
name: autoresearch
description: >
  Runs a Karpathy-style autonomous self-improvement loop on a target skill's evals,
  making one targeted edit per iteration and committing on improvement. Use when the
  user asks to auto-improve a skill, run a self-improvement loop, optimize a skill
  overnight, or make a skill pass its evals autonomously. Also use when the user says
  "autoresearch", "auto-research", or "self-improve" in the context of skills. Does
  not trigger for manual skill editing (edit the skill directly).
argument-hint: "<skill-name> [--max-iterations N] [--max-stalls N] [--target-score N] [--continue] [--hint '...']"
---

# Autoresearch

Autonomous self-improvement loop for Claude Code skills. Runs binary assertions against skill output, makes one targeted edit per iteration, keeps or reverts based on score, and loops until the target is reached or the budget is exhausted.

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `<skill-name>` | required | Skill directory name under `~/.claude/skills/` |
| `--max-iterations N` | 50 | Hard stop after N iterations |
| `--max-stalls N` | 5 | Stop when score hasn't improved for N consecutive iterations |
| `--target-score N` | 100 | Stop when pass rate reaches N% |
| `--continue` | — | Resume a previous loop using existing log and branch |
| `--hint "..."` | — | Seed the first iteration's root-cause analysis with a direction |

## Prerequisites

- Target skill must exist in `~/.claude/skills/<skill-name>/`
- `~/.claude/` must be a git repo (for branch isolation and commit/revert)
- For overnight runs: start in tmux first (`tmux new -s autoresearch`), then invoke this skill, then detach (`ctrl-b d`). Reattach in the morning with `tmux attach -t autoresearch`.

## Workflow

### Step 1: Validate Target

Read `~/.claude/skills/<skill-name>/SKILL.md`. Confirm it exists. Catalog all editable files: SKILL.md plus everything in `references/`. Files in `evals/`, `scripts/`, and outside the skill directory are off-limits.

### Step 2: Load or Generate Evals

Check `~/.claude/skills/<skill-name>/evals/` for `.json` files with valid `name`, `task`, and `assertions` fields.

- **Evals exist**: display the eval list and total assertion count. Confirm with the user before proceeding.
- **No evals**: generate 5 evals with 5 binary assertions each (25 total) following the protocol in [references/eval-generation.md](references/eval-generation.md). Present to the user and wait for explicit confirmation before writing to disk.

Never edit eval files during the loop. If evals are inadequate, note it in the final report.

### Step 3: Create Git Branch

Create branch `autoresearch/<skill-name>` from current HEAD. Use `git checkout -b autoresearch/<skill-name>` from current HEAD. If `--continue`, check out the existing branch instead.

If `--continue`: check out the existing branch, load the JSON log, and diff evals against the log's snapshot. Report any eval changes to the user per the diffing protocol in [references/eval-generation.md](references/eval-generation.md).

### Step 4: Establish Baseline

Run 1 rep per eval using clean subagents (see [references/loop-algorithm.md](references/loop-algorithm.md) for spawning protocol). Grade all assertions inline. Record the baseline score.

Display:
```
Baseline: X/Y assertions passed (Z%)
Target:   100% | Budget: 50 iterations, 5 max stalls
```

If baseline already meets `--target-score`, skip to Step 8.

### Step 5: The Improvement Loop

Repeat until an exit condition is met:

**5a. Check exit conditions.** In order: target score reached, max stalls reached, max iterations reached. See [references/loop-algorithm.md](references/loop-algorithm.md) for precedence.

**5b. Root-cause analysis.** Examine all failing assertions across all evals. Identify the single highest-leverage edit. Read [references/edit-strategy.md](references/edit-strategy.md) for the decision tree. If `--hint` was passed and this is iteration 1, incorporate the hint.

**5c. Make one edit.** Edit SKILL.md or one reference file. Log which file, what changed, and why.

**5d. Re-score.** Run 1 rep per eval again with the edit applied.

**5e. Commit or revert.**
- Score improved (`new > prev`): git commit, reset stall count to 0
- Score unchanged (`new == prev`): git commit, increment stall count
- Score regressed (`new < prev`): `git checkout -- skills/<skill-name>/`, increment stall count, log the failed attempt

**5f. Print progress line:**
```
[iter 3/50] score: 18/25 (72%) -> 20/25 (80%) +8%  stalls: 0/5  edited: SKILL.md
```

**5g. Append iteration to JSON log.** See log schema in [references/loop-algorithm.md](references/loop-algorithm.md).


### Step 6: Merge

If final score > baseline: merge the branch into main with `--no-ff`. If final score <= baseline: do not merge, report that no net improvement was achieved.

### Step 7: Generate Report

Write the markdown report to `evals/results/YYYY-MM-DD-autoresearch.md` and the JSON log to `evals/results/autoresearch-<skill-name>-log.json`. See [references/report-format.md](references/report-format.md) for the full template.

Print console summary:
```
=== Autoresearch Complete ===
Skill:      <skill-name>
Exit:       target_score_reached
Baseline:   68% (17/25) -> Final: 100% (25/25)
Iterations: 12 of 50 | Commits: 8 | Reverted: 3 | Stalls: 1
Branch:     autoresearch/<skill-name>
Report:     evals/results/YYYY-MM-DD-autoresearch.md
```

### Step 8: External Recommendations

For any assertions still failing, analyze whether the root cause is inside or outside the skill. Recommend specific external fixes in the report (file path, line, suggested change). These require human action — the loop cannot edit files outside the skill directory.

## Important

- **Never edit evals.** Evals are ground truth. Editing them to improve score is gaming, not improving.
- **One edit per iteration.** Batching obscures causality. The tight feedback loop is the whole point.
- **Never stop to ask.** Once the loop begins, do not pause for confirmation. The user may be asleep. Run autonomously until an exit condition is met or interrupted.
- **Never force-push.** All changes are on the autoresearch branch. Main is only touched at merge time.
- **Log everything.** Every iteration, every edit, every revert. The log is the user's morning briefing.
