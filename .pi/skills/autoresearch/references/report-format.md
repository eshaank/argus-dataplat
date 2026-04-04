# Report Format

The autoresearch loop produces three outputs: a markdown report, a JSON log, and a console summary.

## Markdown Report

Saved to `evals/results/YYYY-MM-DD-autoresearch.md` in the target skill's directory.

```markdown
# Autoresearch Report: <skill-name>

**Date**: YYYY-MM-DD
**Branch**: autoresearch/<skill-name>
**Run duration**: X minutes
**Exit reason**: target_score_reached | max_stalls_reached | max_iterations_reached

## Summary

| Metric | Value |
|--------|-------|
| Baseline score | X% (N/M assertions) |
| Final score | Y% (P/M assertions) |
| Delta | +Z% |
| Iterations run | N of 50 |
| Commits made | N |
| Regressions reverted | N |
| Stalls encountered | N of 5 |

## Score Trajectory

| Iter | Score | Delta | Edit | Outcome |
|------|-------|-------|------|---------|
| baseline | 68% (17/25) | — | — | — |
| 1 | 76% (19/25) | +8% | Added 300-word limit to SKILL.md | commit |
| 2 | 76% (19/25) | 0% | Strengthened format rules | commit (neutral) |
| 3 | 72% (18/25) | -4% | Moved format rules to references/ | REVERTED |
| ... | | | | |

## Commits That Improved Score

### Iteration 1: +8% (68% -> 76%)
**File**: SKILL.md
**Edit**: Added rule — "All outputs must be under 300 words unless the prompt specifies otherwise"
**Assertions fixed**:
- happy-path-linkedin: "Under 300 words"
- happy-path-email: "Under 300 words"

### Iteration 5: +4% (76% -> 80%)
...

## Edits That Were Reverted

### Iteration 3: -4% (76% -> 72%)
**File**: SKILL.md
**Attempted**: Moved format rules from SKILL.md to references/format-guide.md
**Why it regressed**: Claude stopped loading the format reference consistently
**Lesson**: Keep high-frequency rules in SKILL.md where they're always in context

## Remaining Failures

### Assertion: "Contains at least one specific statistic"
**Evals affected**: happy-path-linkedin, edge-case-short-form
**Root cause**: Skill doesn't provide source data or instruct Claude to include statistics
**Attempts made**:
- Iter 8: Added "include a relevant statistic" to SKILL.md → no improvement
- Iter 10: Added example statistics to references/examples.md → reverted (regression)
**Recommended action**: Add a references/statistics.md with domain-specific data points for Claude to draw from

### Assertion: "Uses framework from references/persuasion-toolkit.md"
**Evals affected**: boundary-persuasion-toolkit
**Root cause**: External dependency — persuasion-toolkit.md references concepts not defined in the skill
**Recommended action**: Review and update references/persuasion-toolkit.md (external to autoresearch scope)

## External Fix Recommendations

For assertions that the loop couldn't resolve because the root cause is outside the skill directory:

| Assertion | External File | Suggested Fix |
|-----------|--------------|---------------|
| "Uses persuasion framework" | references/persuasion-toolkit.md | Define the 3 core techniques explicitly |
| "Follows brand voice" | ~/.claude/rules/preferences.md line 12 | Resolve contradiction with SKILL.md line 34 |
```

## JSON Log

Saved to `evals/results/autoresearch-<skill-name>-log.json`. See [loop-algorithm.md](loop-algorithm.md) for the full schema. The log is the machine-readable record of every iteration — the markdown report is derived from it.

## Console Summary

Printed to stdout when the loop exits:

```
=== Autoresearch Complete ===
Skill:      marketing-copywriting
Exit:       target_score_reached
Baseline:   68% (17/25)
Final:      100% (25/25)
Iterations: 12 of 50
Commits:    8 | Reverted: 3 | Stalls: 1
Branch:     autoresearch/marketing-copywriting
Report:     ~/.claude/skills/marketing-copywriting/evals/results/2026-03-28-autoresearch.md
```

If the user is in tmux (`$TMUX` is set), also suggest:
```
Review changes: git log autoresearch/marketing-copywriting --oneline
```
