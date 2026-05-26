---
nextStepFile: 'score.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4c: Hard Gate

## STEP GOAL:

Scan accumulated findings from coverage and coherence analysis for critical or high severity gaps. If any exist, block the pipeline with a clear listing of every blocking finding — no coverage score is computed or reported. If only medium, low, or info findings exist, pass through to scoring.

### §1. Read Findings from Output

Read `{outputFile}` and scan the **Coverage Analysis** and **Coherence Analysis** sections for GAP entries. Each GAP entry contains a severity marker in this format:

```
**Severity:** {Critical|High|Medium|Low|Info}
```

Extract every line matching `**Severity:** Critical` or `**Severity:** High`. For each match, also capture the parent GAP heading (`### GAP-{NNN}: {title}`) and the `**Source:**` line to build a blocking-findings list.

### §2. Evaluate Gate

**Count blocking findings** (Critical + High severity).

**IF blocking findings exist → BLOCK (§3)**

**IF no blocking findings → PASS (§4)**

### §3. Block — Critical/High Findings Detected

The hard gate blocks the pipeline. No scoring step runs.

Update `{outputFile}` frontmatter:
- Set `testResult: 'fail'`
- Append `'hard-gate'` to `stepsCompleted`

Report to the user:

"**Hard gate BLOCKED — {N} critical/high finding(s) must be resolved before scoring.**

| # | GAP | Severity | Source |
|---|-----|----------|--------|
{for each blocking finding:}
| {i} | {GAP-NNN}: {title} | {severity} | {source} |

**{M} medium/low/info findings also noted (non-blocking).**

**Action required:** resolve all Critical and High findings, then re-run test-skill.
**Recommended next step:** update-skill"

**Headless envelope (if `{headless_mode}`):** emit to **stderr**:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":"FAIL","score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":"update-skill","exit_code":2,"halt_reason":"hard-gate-blocked"}
```

HALT — do not chain to `{nextStepFile}`.

### §4. Pass — No Critical/High Findings

The hard gate passes. Medium, low, and info findings are documented in the gap report but do not block.

Update `{outputFile}` frontmatter:
- Append `'hard-gate'` to `stepsCompleted`

Report:

"**Hard gate passed** — {N} medium/low/info finding(s) noted, proceeding to scoring."

Update stepsCompleted, then load and execute `{nextStepFile}`.
