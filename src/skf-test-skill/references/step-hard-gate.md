---
nextStepFile: 'score.md'
# A run the gate blocks is never scored: it ends through the report step's
# terminal sequence instead (§3).
blockedStepFile: 'report.md'
outputFile: '{report_file}'
# The public name report.md §4c gives the report once its checks pass, a
# blocked run's included: §1 names it in the blocked payload.
publishedReportFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
hardGateScript: 'scripts/hard-gate.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4c: Hard Gate

## STEP GOAL:

Decide from the gap ledger whether this run may be scored. Coverage, coherence and external validation recorded every gap they found in `{ledgerFile}`, each with the severity and the category the Gap Severity table gives it. Any Critical or High gap blocks the run: no score is computed, and the report step publishes the run as a FAIL. When only Medium, Low or Info gaps exist, the run passes through to scoring.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### §1. Run the Gate

The gate reads the ledger, not the report: a gap the report shows only in a table still counts, and a stage that never recorded its gaps cannot pass for one that found none. Run it (`{hardGateScript}` resolves relative to the skill root):

```bash
uv run {hardGateScript} check --ledger "{ledgerFile}" --skill-name "{skill_name}" --report-path "{publishedReportFile}" --require-stage coverage-check --require-stage coherence-check --require-stage external-validators
```

Rely on its JSON and do not count the gaps again by hand.

### §2. Evaluate Gate

- `gate` is `blocked` (exit 0): `blocking` lists every Critical and High gap, Critical first. Go to §3.
- `gate` is `passed` (exit 0): no gap is Critical or High. Go to §4.
- Exit 1 with `code` `LEDGER_MISSING` or `STAGE_NOT_RECORDED`: a stage before the gate recorded nothing in the ledger (`missing_stages` names it; with no ledger, none of them did), so the gate cannot decide. HALT (`halt_reason: "step-completeness-violation"`, phase `hard-gate:check`) with "step completeness violation: {the stages} never recorded their gaps in `{ledgerFile}`; workflow state is inconsistent, do not score or finalize the report".
- Any other `code` (`LEDGER_INVALID`, `HELPER_MISSING`) or exit, or no JSON: HALT (`halt_reason: "helper-failed"`, phase `hard-gate:check`) with the script's `error`, or with its stderr when it printed no JSON.

### §3. Block: Critical or High Gaps

The gate blocks the run, and scoring never runs. The run still ends through the report step's terminal sequence: the Gap Report, the FAIL result contract and the on_complete hook, then the health check (unless `--no-health-check` was passed). Its result envelope and result files carry `exit_code` 2 and verdict `FAIL`, and the report keeps its in-progress name until report.md §4c's checks pass, so a halt there leaves no partial report under the public name.

Update `{outputFile}` frontmatter:
- Set `hardGate: 'blocked'`
- Set `testResult: 'fail'`
- Set `nextWorkflow: 'update-skill'`
- Append `'hard-gate'` to `stepsCompleted`

Write the **Completeness Score** section, which scoring would otherwise write, in place of the template's `## Completeness Score` heading and the placeholder comment under it:

```markdown
## Completeness Score

**Result:** **FAIL**, not scored: the hard gate blocked this run on {blocking_count} Critical or High gap(s), listed first in the Gap Report.
```

Report to the user:

"**Hard gate BLOCKED: {blocking_count} Critical or High gap(s) must be resolved before scoring.**

| # | Gap | Severity | Source |
|---|-----|----------|--------|
{for each `blocking` entry:}
| {i} | {id}: {title} | {severity} | {source} |

**{non_blocking_count} Medium, Low or Info gap(s) also recorded (non-blocking).**

**Recommended next step:** `@Ferris US {skill_name} --from-test-report` (update-skill repairs the gaps this report lists), once the report step has written the Gap Report and the result files."

Then load and execute `{blockedStepFile}`. Do not chain to `{nextStepFile}`: a blocked run is never scored.

### §4. Pass: No Critical or High Gaps

The hard gate passes. The Medium, Low and Info gaps stay in the ledger for the Gap Report and do not block.

Update `{outputFile}` frontmatter:
- Set `hardGate: 'passed'`

Report that the hard gate passed, noting the count of non-blocking Medium, Low and Info gap(s) (`non_blocking_count`), then proceed to scoring.

Append `'hard-gate'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute `{nextStepFile}`.
