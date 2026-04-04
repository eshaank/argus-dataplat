# Eval Generation

How to generate evals when a target skill has none, and how to manage eval snapshots for `--continue`.

## When to Generate vs. Use Existing

- **Evals exist** (`evals/*.json` in the skill directory with valid `name`, `task`, `assertions` fields): use them as-is. Display the eval list and assertion count. Confirm with the user before starting.
- **No evals exist**: generate them following the protocol below. Show the user for confirmation. Write to `evals/` only after confirmation.

Never edit existing eval files. If evals are inadequate, note it in the final report.

## The 5x5 Structure

Generate 5 evals with 5 binary assertions each (25 total):

| Eval | Purpose | What to test |
|------|---------|-------------|
| 1. Happy path (primary) | Most common use case | Core workflow output matches SKILL.md instructions |
| 2. Happy path (variant) | Different prompt, same core use case | Tests generalization, not overfitting to one prompt |
| 3. Happy path (variant) | Third distinct prompt | Covers a different aspect of the skill's domain |
| 4. Edge case | Valid but unusual input | Uncommon scenario mentioned or implied by SKILL.md |
| 5. Boundary test | Reference file compliance | Verifies a specific `references/` file's guidance is followed |

## Deriving Evals from SKILL.md

Read the target SKILL.md and all reference files. For each eval:

1. **Write a realistic task prompt.** Something a real user would type — not abstract or sanitized. Include details like file names, context, casual phrasing. Vary length and formality across the 5 evals.

2. **Write 5 binary assertions.** Each must be objectively verifiable as true/false. Prioritize:
   - **Format/structure rules** explicitly stated in the skill ("use this template", "start with X")
   - **Constraints** ("under N words", "no em-dashes", "no questions at the end")
   - **Reference file compliance** ("uses the framework from references/X.md")
   - **Negative rules** ("does NOT include disclaimers", "does NOT use passive voice")
   - **Content requirements** ("contains at least one statistic", "mentions the product name")

## What Makes a Good Assertion

Binary means two people would independently agree on the answer:

| Good (binary) | Bad (subjective) |
|---|---|
| Under 300 words | Concise and well-written |
| First line is a standalone sentence | Has a compelling opening |
| Does not contain em-dashes | Uses good punctuation |
| Final line is not a question | Ends with a strong close |
| Contains at least one specific number | Includes relevant data |

## Self-Check Before Proposing

Before showing evals to the user, verify:

1. **No assertion can be graded by reading the SKILL.md itself** — it must require running the skill and examining output
2. **No assertion uses subjective language** ("high quality", "compelling", "appropriate", "good")
3. **Each assertion tests something the SKILL.md specifically adds** — not Claude's baseline ability (e.g., "writes grammatically correct English" is a Claude baseline, not a skill contribution)
4. **All 5 evals have distinct tasks** — no near-duplicates or trivially different prompts
5. **Assertions span multiple dimensions** — don't put 5 word-count assertions; mix format, content, structure, and negative checks

## Confirmation Protocol

Present the evals in a readable format:

```
Eval 1: happy-path-linkedin-post
  Task: "Write a LinkedIn post about why simple automations beat complex ones"
  Assertions:
    1. First line appears as a standalone sentence, not part of a paragraph
    2. Contains at least one specific number or statistic
    3. Final line is not a question
    4. Total word count is under 300
    5. Does not contain em-dashes (—)

Eval 2: ...
```

State total: "5 evals, 25 assertions total."

Wait for explicit confirmation. Do NOT start the loop until confirmed. The user may:
- Approve as-is
- Modify assertions (apply changes, re-confirm)
- Add/remove evals (apply changes, re-confirm)
- Ask for completely different evals (regenerate)

## Writing Evals to Disk

After confirmation, write each eval as a separate JSON file in the skill's `evals/` directory:

```json
{
  "name": "happy-path-linkedin-post",
  "task": "Write a LinkedIn post about why simple automations beat complex ones",
  "context_files": [],
  "assertions": [
    "First line appears as a standalone sentence, not part of a paragraph",
    "Contains at least one specific number or statistic",
    "Final line is not a question",
    "Total word count is under 300",
    "Does not contain em-dashes"
  ]
}
```

Filename matches the `name` field: `happy-path-linkedin-post.json`.

## Eval Snapshot for --continue

When starting a loop, record the eval state in the JSON log's `eval_snapshot` field. On `--continue`:

1. Re-read current eval files from disk
2. Compare against the snapshot in the log
3. Report changes to the user:

| Change type | Action |
|---|---|
| Assertions added to existing eval | Re-evaluate only new assertions, append to history |
| Assertions modified in existing eval | Re-evaluate those assertions, keep others |
| Assertions removed from existing eval | Drop from scoring, adjust denominator |
| New eval file added | Run full baseline on new eval only |
| Eval file removed | Drop from history |
| No changes | Resume with stall counter reset |

Show the user what changed before resuming: "I see you modified 2 assertions and added 1 new eval. Re-baselining the changed items before continuing."
