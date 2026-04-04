# Loop Algorithm

The core autoresearch loop: grade → analyze → edit → re-grade → commit or revert → repeat.

## Subagent Spawning Protocol

For each eval, spawn a subagent with:
- **User message**: the `task` field from the eval JSON, verbatim
- **Skill context**: the target skill's SKILL.md loaded (use `--skill-path` or equivalent)
- **Context files**: any paths listed in the eval's `context_files` array
- **Isolation**: each subagent gets a clean context — no loop state, no autoresearch SKILL.md, no other eval outputs

Spawn all eval subagents in parallel within a single iteration for speed. Wait for all to complete before grading.

## Inline Grading

Grade each eval's output directly — do not spawn a separate grading subagent. For each assertion in the eval:

1. Read the assertion text (a binary statement like "Output is under 300 words")
2. Examine the subagent's output
3. If the output clearly demonstrates the assertion is true: **PASS**
4. If the output does not clearly demonstrate it, or is ambiguous: **FAIL**

Ambiguity is always FAIL. The skill's instructions should be clear enough that outputs unambiguously satisfy assertions. If they don't, that's the gap the loop will fix.

Record results as:
```json
{
  "eval_name": "happy-path-linkedin-post",
  "assertions": [
    {"text": "First line is a standalone sentence", "passed": true},
    {"text": "Under 300 words", "passed": false}
  ]
}
```

## Score Formula

```
score_pct = (total passed assertions across all evals) / (total assertions across all evals) * 100
```

One rep per eval during the loop. The score is deterministic given the eval outputs. Variance is an eval-quality concern addressed by the optional 3-rep final validation, not by the loop itself.

## The Loop (pseudocode)

```
create branch autoresearch/<skill-name>
baseline = grade_all_evals()
prev_score = baseline.score_pct
stall_count = 0
iteration = 0

while true:
    iteration += 1

    # Check exit conditions (before grading next iteration)
    if prev_score >= target_score:
        exit("target_score_reached")
    if stall_count >= max_stalls:
        exit("max_stalls_reached")
    if iteration > max_iterations:
        exit("max_iterations_reached")

    # Analyze failures and make one edit
    failing = get_failing_assertions(prev_results)
    root_cause = analyze_root_cause(failing, log)
    apply_one_edit(root_cause)

    # Re-grade with the edit applied
    new_results = grade_all_evals()
    new_score = new_results.score_pct

    # Commit or revert
    if new_score > prev_score:
        git_commit(iteration, prev_score, new_score, root_cause)
        stall_count = 0
        prev_score = new_score
        prev_results = new_results
    elif new_score == prev_score:
        git_commit(iteration, prev_score, new_score, root_cause)
        stall_count += 1
        prev_results = new_results
    else:  # regression
        git_reset_hard_HEAD()
        stall_count += 1
        log_failed_attempt(root_cause)

    append_to_log(iteration, root_cause, outcome)
    print_progress(iteration, prev_score, stall_count)
```

## Why Neutral Edits Get Committed

A neutral edit (score unchanged) still gets committed because:
- It may have fixed one assertion while breaking another — a net-zero that shifts the failure pattern
- The next iteration sees a different set of failures, enabling different root-cause analysis
- Reverting a neutral edit leaves the loop stuck in the exact same state

But neutral edits DO increment the stall counter because the score didn't improve.

## Exit Condition Precedence

Check in this order:
1. `score_pct >= target_score` — success exit
2. `stall_count >= max_stalls` — stall exit
3. `iteration > max_iterations` — budget exit

Check BEFORE making the next edit, so the final committed state is always recorded before exit.

## Stall Detection

`stall_count` tracks consecutive iterations without score improvement:
- **Increments** when `new_score <= prev_score` (both regression-reverted and neutral-committed)
- **Resets to 0** when `new_score > prev_score`
- **Exit** when `stall_count >= max_stalls`

The rationale: if the model's edits aren't improving score for N iterations, it's stuck. Neutral edits that shift the failure pattern without improving score are still stalls — they consume budget without progress.

## JSON Log Schema

Saved to `evals/results/autoresearch-<skill-name>-log.json`:

```json
{
  "skill": "marketing-copywriting",
  "skill_path": "~/.claude/skills/marketing-copywriting",
  "started_at": "2026-03-28T02:00:00Z",
  "baseline_score": {"total": 25, "passed": 17, "pct": 68.0},
  "target_score": 100,
  "max_iterations": 50,
  "max_stalls": 5,
  "eval_snapshot": [
    {"name": "happy-path-linkedin", "assertion_count": 5},
    {"name": "happy-path-landing-page", "assertion_count": 5},
    {"name": "happy-path-email", "assertion_count": 5},
    {"name": "edge-case-short-form", "assertion_count": 5},
    {"name": "boundary-persuasion-toolkit", "assertion_count": 5}
  ],
  "iterations": [
    {
      "iteration": 1,
      "scores_before": {"total": 25, "passed": 17, "pct": 68.0},
      "failing_assertions": [
        {"eval": "happy-path-linkedin", "assertion": "Under 300 words"},
        {"eval": "happy-path-email", "assertion": "Under 300 words"}
      ],
      "root_cause": "Multiple evals fail on word count. SKILL.md has no explicit length constraint.",
      "edit": {
        "file": "SKILL.md",
        "description": "Added rule: all outputs must be under 300 words unless the prompt specifies otherwise"
      },
      "scores_after": {"total": 25, "passed": 19, "pct": 76.0},
      "delta": 8.0,
      "outcome": "commit",
      "commit_sha": "abc1234",
      "stall_count": 0
    }
  ],
  "final_score": {"total": 25, "passed": 25, "pct": 100.0},
  "exit_reason": "target_score_reached",
  "completed_at": "2026-03-28T02:22:00Z"
}
```

## Progress Line Format

Print after each iteration:
```
[iter 3/50] score: 18/25 (72%) -> 20/25 (80%) +8%  stalls: 0/5  edited: SKILL.md
[iter 4/50] score: 20/25 (80%) -> 20/25 (80%)  0%  stalls: 1/5  edited: SKILL.md (neutral)
[iter 5/50] score: 20/25 (80%) -> 18/25 (72%) -8%  stalls: 2/5  REVERTED
```
