# Edit Strategy

How the loop decides what to change each iteration.

## The One-Edit Constraint

Make exactly one discrete edit per iteration. This is the Karpathy constraint: small changes with immediate measurement. Batching multiple edits obscures which one helped or hurt, making the loop's commit/revert mechanism unreliable.

One edit means one of:
- Add a rule or instruction to SKILL.md
- Modify an existing instruction in SKILL.md
- Remove a contradictory or confusing instruction from SKILL.md
- Add, modify, or remove content in a reference file
- Add a pointer in SKILL.md to a new or existing reference file

## Root-Cause Analysis Protocol

Before choosing an edit, examine ALL failing assertions across ALL evals:

1. **List every failing assertion** with its eval name
2. **Group by failure pattern** — do multiple assertions fail for the same underlying reason?
   - Example: 3 assertions about word count fail → root cause is no length constraint
   - Example: 2 assertions about structure fail differently → separate root causes
3. **Rank groups by size** — the group with the most failing assertions gets priority
4. **If groups are equal**, prefer the one that appears across more distinct evals (broader impact)
5. **Choose the single edit** that addresses the highest-ranked group

## Edit Decision Tree

Given the root cause, decide what to edit:

1. **Missing instruction** — The skill simply doesn't tell Claude to do something the assertions expect
   → Add the instruction to SKILL.md (or reference file if it's detailed)

2. **Vague instruction** — The instruction exists but is too ambiguous to follow reliably
   → Strengthen it with specifics, examples, or constraints

3. **Contradictory instructions** — SKILL.md says one thing, a reference file says another
   → Resolve the contradiction (usually by updating the reference file to match the intended behavior)

4. **Missing reference file pointer** — Detailed guidance exists in references/ but SKILL.md doesn't point to it
   → Add a pointer in SKILL.md directing Claude to read the reference file

5. **Instruction present but buried** — The rule exists but is easy to miss in a long section
   → Move it to a more prominent position or make it a standalone step

## Which File to Edit

- **SKILL.md** for: workflow steps, high-level rules, format constraints, pointers to references
- **Reference files** for: detailed examples, domain knowledge, extended explanations, style guides
- **Prefer SKILL.md** when the edit is short (1-3 lines) — it's always loaded
- **Prefer reference files** when the edit would push SKILL.md over 200 lines

## Forbidden Edits

Never edit:
- Files in `evals/` — evals are ground truth, not targets to game
- The JSON log (`autoresearch-*-log.json`) — it's an append-only record
- Files in `scripts/` — scripts are deterministic tools with side effects
- Files outside `~/.claude/skills/<skill-name>/` — unbounded blast radius

If the root cause is in an external file (e.g., `~/.claude/rules/preferences.md`), log it as an external recommendation in the report. Do not edit external files.

## Avoiding Repeat Failures

Before choosing an edit, scan the JSON log's `iterations[].edit` entries:

1. Has this exact edit been tried before? → Skip it
2. Has a similar edit to the same file and section been tried? → Try a fundamentally different approach
3. Have all obvious edits for this failure group been tried and reverted? → Move to the next failure group

"Fundamentally different" means changing the approach, not rewording the same instruction. Examples:
- Tried adding a rule to SKILL.md, it didn't help → Try adding an example instead
- Tried strengthening an instruction, it regressed → Try removing a contradictory instruction elsewhere
- Tried editing SKILL.md → Try editing the relevant reference file instead

## Anti-Patterns

- **Duplicating instructions** — Adding "must be under 300 words" when it already says "keep it brief and under 300 words" elsewhere
- **Bloating SKILL.md** — If your edit pushes SKILL.md over 200 lines, move detail to references/ instead
- **Adding examples for workflow gaps** — Examples show what, not how. If Claude skips a step, add the step, don't add an example of the step's output
- **Gaming the evals** — Weakening skill constraints to make assertions pass defeats the purpose. The skill should be genuinely better, not just eval-compliant
- **Over-specifying** — Adding 5 new rules to fix 1 assertion. One targeted edit per iteration.
