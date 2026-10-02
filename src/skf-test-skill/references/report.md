---
nextStepFile: 'health-check.md'

outputFile: '{report_file}'
# §4c gives the report this public name once its checks pass (a run the hard
# gate blocked included), the name export-skill and update-skill read.
publishedReportFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
# The run's gap ledger: the stages recorded their gaps in it, §4b adds the
# discovery outcome, and §4c renders the Gap Report from it.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
# §4c builds the shared emitter's payload from the run's records with it.
resultContextScript: 'scripts/build-result-context.py'
scoringRulesFile: 'references/scoring-rules.md'
outputFormatsFile: 'assets/output-section-formats.md'
# outputContractSchema and healthCheck resolve relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file. §4c probes both health-check
# paths in order and HALTs, before anything is published, if neither exists.
outputContractSchema: 'shared/references/output-contract-schema.md'
healthCheckProbeOrder:
  - '{project-root}/_bmad/skf/shared/health-check.md'
  - '{project-root}/src/shared/health-check.md'
# Resolve `{skillInventoryHelper}` to the first existing path. §4b.0 reads the
# inventory to count the folders that hold a skill.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. Test report prose in {document_output_language}. -->

# Step 6: Gap Report

## STEP GOAL:

Publish the run. Record the discovery outcome in the gap ledger, render the Gap Report from the ledger, check that every stage ran and wrote its section, then publish the report under its public name, write the result contract, run the on_complete hook and present the result. Do not recalculate scores (step 5 ran them) or classify the stages' gaps again (each stage recorded its own). A run the hard gate blocked comes here straight from step 4c and takes the same sequence, with the blocked-run branch each section names. This step chains to the local health-check step via `{nextStepFile}` after completion; the user-facing report is not the terminal step.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

§7 releases the lock when the run ends.

### 1. Collect All Issues

The stages before this one recorded every gap they found in the gap ledger `{ledgerFile}`, each with the severity and the category the Gap Severity table gives it. The ledger is the record of the run's gaps: the hard gate counted it, and the Gap Report, the result contract and update-skill `--from-test-report` read it. Do not collect gaps again from the report's sections. The one source of gaps left is discovery testing (§4b), which runs after the gate.

**A run the hard gate blocked** (frontmatter `hardGate: 'blocked'`, set by step 4c §3) was not scored and skips discovery testing (§4b) and the loads in §2 and §3: after §4, continue at §4c.

### 2. Load Severity Rules

For the discovery record §4b writes, load the **Gap Severity** table from `{scoringRulesFile}`, the single source of truth for a gap's severity and category; do not restate its rows here.

### 3. Load the Record Format

Load `{outputFormatsFile}` for the Ledger Record Format and the remediation quality rules the discovery record follows. The ledger numbers the gaps and the Gap Report orders them, so nothing is ordered by hand.

### 4. The Terminal Sequence

Every run that reaches this step, a blocked one included, ends through one sequence, and a check that fails stops it before anything is published:

1. §4b records the discovery outcome in the ledger (a blocked run skips it).
2. §4c renders the Gap Report from the ledger, checks that every stage ran and wrote its section and that the health check is installed, then publishes the report, writes the result contract and runs the on_complete hook.
3. §6 presents the result, §6b keeps the headless envelope for the run's last line, and §7 releases the run lock and hands over to the health check.

### 4b. Discovery Testing

**`--no-discovery` flag bypass (precedes the precondition check).** If `no_discovery: true` is set in workflow context (from §1 of `init.md`: the `--no-discovery` flag on invocation), record the skip (below) with the reason `--no-discovery flag set`, log the bypass, and SKIP §4b.1 to §4b.3. Proceed to §4b.4 (description optimization) only if Tessl Review's description score is below 90% or skill-check flagged description issues; otherwise skip directly to §4b.5.

Perform minimum-viable discovery testing. Its outcome is at most one gap (§4b.5), and the Discovery Quality subsection §4c writes shows it.

**Recording a skip.** A discovery test that does not run is still counted. Each skip branch (the bypass above, §4b.0 and the §4b.2 guard) is one Info `discovery` gap, the Gap Severity table's "Discovery testing not performed" row, titled `Discovery testing not performed: {reason}`, with the SKILL.md frontmatter `description` as its Source and a Remediation that names what lets the test run: a run without `--no-discovery`, a second skill in the catalog (or `--discovery-catalog=all`), or an environment that can spawn subagents. The Discovery Quality subsection also gets the note `discovery: skipped, {reason}`. §4b.5 records the gap.

**4b.0 Precondition — catalog size check:**

Count the folders that hold a skill, not every folder: SKF's own `_batch/` holds none, and a versioned skill keeps its `SKILL.md` under `active/`. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skillsOutputFolder}
```

Bind `{not_skf_output}` ← `not_skf_output` and `{discovery_catalog}` ← every `skills[]` entry whose `has_skill_md` is true and whose `skf_skill` is true or whose `name` is in `{not_skf_output}`, each as its `name` plus `{active_path}/SKILL.md`. Skills SKF did not generate stay in the catalog: they compete for the same prompts. `catalog_size` ← the number of `{discovery_catalog}` entries. Without the helper (no candidate resolves, or the status is not `ok`), build the same set with your file tools, never a shell pipeline: each folder directly in `{skillsOutputFolder}` whose name does not start with `.`, is not `_batch` and holds no `.skf-`, and that holds `SKILL.md` directly or at `active/<folder>/SKILL.md`.

- If `catalog_size < 2`: **skip §4b.1 to §4b.3**. Record the skip with the reason `catalog size N={catalog_size}, requires ≥2 candidates for meaningful routing`. The routing test is vacuous with one candidate (any prompt returns the sole skill); reporting `3/3 PASS` under those conditions inflates the Discovery score and masks genuinely bad description triggers. Proceed to §4b.4 (description optimization) if Tessl Review's description score is below 90% or skill-check flagged description issues; otherwise skip to §4b.5.
- If `catalog_size >= 2`: continue with §4b.1 as written.

Optional escape hatch: the workflow accepts `--discovery-catalog=all` (init.md §1 stores `discovery_catalog_all: true`) to broaden the candidate pool to `{project-root}/.claude/skills/` or `{project-root}/_bmad/agents/` for single-skill repos where the repo-local catalog is trivially too small. When `discovery_catalog_all` is true, add each folder directly in `{project-root}/.claude/skills/` or `{project-root}/_bmad/agents/` that holds a `SKILL.md` directly to `{discovery_catalog}` (a name already in it counts once), then recount `catalog_size` before the precondition check.

**4b.1 Extract realistic prompts from the skill under test:**

Parse SKILL.md for the three most "organic" prompts found in its `description`, `Triggers`, or example sections. Prefer prompts that:
- Use conversational phrasing (contractions, casual language, implicit context)
- Omit the skill name or explicit command invocation
- Reflect how a user would actually ask for this capability

If SKILL.md does not contain enough organic examples, synthesize 3 from the skill's exports/capability summary using the patterns from §4b.4 below.

**4b.2 Spawn a discovery subagent:**

**Subagents-unavailable guard (precedes the spawn).** If subagents cannot be spawned in this environment (e.g. a headless/CI pipeline with no subagent capability), do not fall back to answering the routing in the main thread: the main thread knows which skill is under test, so it would self-route to `3/3 PASS` and inflate the Discovery score, the exact false confidence §4b.0 warns against. Instead record the skip with the reason `subagents unavailable, routing test requires isolated context`, exclude the discovery check from Discovery Quality scoring (do not count it PASS or FAIL), and skip to §4b.5.

For each of the 3 prompts, spawn an isolated subagent with NO prior context about which skill is under test. Provide only:
1. A compact list of every skill in `{discovery_catalog}` (the same set §4b.0 counted): name + description line from that entry's SKILL.md frontmatter
2. The prompt text

Instruction to the subagent:

> "You are an agent selecting the best skill to handle a user request. Here is the catalog: {catalog}. The user says: '{prompt}'. Return JSON: `{\"selected_skill\": \"<name>\", \"confidence\": \"<high|medium|low>\", \"reasoning\": \"<one sentence>\"}`. If no skill fits, return `{\"selected_skill\": null, ...}`. Return only JSON."

**4b.3 Evaluate discovery results:**

Parse the 3 responses. Schema-validate (required: `selected_skill`, `confidence`, `reasoning`). On any parse/schema failure, record the prompt as `discovery_result: error` and continue.

For each prompt, PASS = `selected_skill == skill_name` (the skill under test), FAIL otherwise.

- **3 of 3 PASS** → discovery check PASS: no gap.
- **2 of 3 PASS** → discovery check WARN: a Medium `discovery` gap titled `discovery: 1/3 realistic prompts misrouted`.
- **≤1 of 3 PASS** → discovery check FAIL: a High `discovery` gap titled `discovery: {N}/3 realistic prompts misrouted; description triggers are not pulling the skill`.

Either gap has the SKILL.md frontmatter `description` as its Source, the misrouted prompts and the skills they reached as its Issue, and a Remediation that names the trigger phrases to add (§4b.4). Keep the prompts, the selected skills and the outcomes for the Discovery Quality table, which §4c writes after the Gap Report.

**4b.4 Description optimization (secondary):** If the Tessl Review description score (the test report's `### Tessl Review` block; absent when Tessl Review did not run) is below 90%, or skill-check flagged description issues, keep these remediation hints for the Discovery Quality subsection §4c writes:
- Third-person voice check
- Explicit trigger keywords matching real user phrasing
- Negative triggers ("NOT for: ...") to prevent false positives
- Alternative skill references for excluded use cases

Realistic prompt patterns for synthesis (§4b.1 fallback):
- Vague: "can you help me with this {artifact} my boss sent"
- Implicit: "why did {metric} drop last {period}"
- Abbreviated: "run the {keyword} thing on this data"

**4b.5 Record the discovery gap.** A skip, a WARN or a FAIL is one gap; a PASS records none. Record it in the ledger, with the record between the two markers exactly as it is (`{gapLedgerScript}` resolves relative to the skill root):

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage report <<'SKF_GAPS'
<the discovery record, a JSON array of one>
SKF_GAPS
```

Exit 0: continue. Exit 2: nothing was written; correct the record `errors[]` names and run the command again. Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `report:discovery`). Discovery runs after the hard gate, so a discovery gap blocks nothing, a High one included: it is counted in the Gap Report's totals and in the counts §6 presents, never as a blocking gap.

### 4c. Result Contract

Nothing is published until the report is whole: render the Gap Report and check the report first, and only then give the report its public name, write the result files and run the on_complete hook.

**Render the Gap Report.** The ledger now holds every gap of the run (`{gapLedgerScript}` resolves relative to the skill root):

```bash
uv run {gapLedgerScript} render --ledger "{ledgerFile}" --heading
```

Exit 0: its output is the whole Gap Report section, heading included: the totals, the Remediation Summary and one entry per gap, by severity (with no gaps, it says none were found). Write it unchanged in place of the template's `## Gap Report` heading and the placeholder comment under it, in `{outputFile}`, then add the **Discovery Quality** subsection under it (format in `{outputFormatsFile}`): the §4b outcome, its prompt table or skip note, and the §4b.4 hints, or, for a run the hard gate blocked, the line that discovery testing did not run. Any other exit printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `report:gap-report`).

Then take the gap counts from the ledger:

```bash
uv run {gapLedgerScript} summary --ledger "{ledgerFile}"
```

Bind `{gap_counts}` ← `counts`, `{total_gaps}` ← `total` and `{blocking_gaps}` ← `blocking`: §6 presents them. Exit 1: HALT with its `error` (`halt_reason: "helper-failed"`, phase `report:gap-report`).

**Enforce step completeness.** Read `stepsCompleted` from the `{outputFile}` frontmatter. Each stage appended its own token when it finished, and `'report'` is appended only once the result files are written, so it is not in the expected set:

```
['init',
 'detect-mode',
 'coverage-check',
 'coherence-check',
 'external-validators',
 'hard-gate',
 'score']
```

A run the hard gate blocked was never scored: its expected set ends at `'hard-gate'`. If any expected entry is missing, HALT (`halt_reason: "step-completeness-violation"`, phase `report:steps`) with "step completeness violation: missing {list}; workflow state is inconsistent, do not finalize the report".

**Check the report sections.** Each stage wrote its section in place of its heading and the placeholder comment under it in the template, so a stage that skipped its section left the placeholder behind, and one that appended its section instead left its heading twice. Count them with grep, not by eye, and read the counts it prints (a count of 0 also makes grep exit 1):

```bash
for heading in '## Test Summary' '## Coverage Analysis' '## Coherence Analysis' '## External Validation' '## Completeness Score' '## Gap Report'; do
  printf '%s: ' "$heading"; grep -cxF "$heading" "{outputFile}"
done
printf 'placeholders: '; grep -c '^<!-- Populated by' "{outputFile}"
```

Each heading must print 1, standing alone on exactly one line, and `placeholders` must print 0. A run the hard gate blocked has all six: step 4c §3 wrote the Completeness Score section in scoring's place. On a heading whose count is not 1, or a placeholder left, HALT (`halt_reason: "report-anchor-missing"`, phase `report:anchors`) with "report anchor missing: {each heading whose count is not 1, with its count}, or {N} placeholder comments left; the section was not written once by its owning step".

**Find the health check** unless `no_health_check` is true (the `--no-health-check` flag): resolve `{healthCheckFile}` ← first existing path in `{healthCheckProbeOrder}`. It ends the run (§7), so check it now, while a HALT still leaves the previous run's report and result files in place. If neither candidate exists, HALT (`halt_reason: "health-check-missing"`, phase `report:health-check`):

```
Error: cannot locate shared/health-check.md at either of:
  - {project-root}/_bmad/skf/shared/health-check.md
  - {project-root}/src/shared/health-check.md

test-skill delegates its terminal step to the shared health-check. Install
the SKF module or run from a development checkout with src/ present.
```

**Renew the run lock** before anything below writes. The lock init.md §6a took goes stale 60 minutes after it was taken, and a long run can outlast that; an acquire by the owner that holds the lock renews it. From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"
```

- Exit 0: the lock is this run's again; continue.
- Exit 3 (`acquired` is false): another run took the lock over after this run's lock went stale. HALT before writing anything (`halt_reason: "another-run-active"`, phase `report:run-lock`), with "**Another test-skill run took over the run lock for {skill_name}.** This run wrote no result files. {message}", where `{message}` is the helper's.
- Exit 1 or 2, or no JSON: HALT with the helper's stderr message (`halt_reason: "helper-failed"`, phase `report:run-lock`), as init.md §6b does.

The run lock renewed here stays held until §7 releases it, so no other run publishes over this run's report or result files meanwhile.

**Publish the report.** Set `health_check_dispatched` in the `{outputFile}` frontmatter: `false` when `no_health_check` is true (the `--no-health-check` flag), else `true`, since the health check now runs with no menu before it. The checks passed, so the report takes its public name, the one export-skill and update-skill read, a blocked run's included. From `{project-root}`, run:

```bash
mv "{report_file}" "{publishedReportFile}"
```

and bind `{report_file}` ← `{publishedReportFile}`. If the move fails, HALT (`halt_reason: "write-failed"`, phase `report:publish`, `"path": "{publishedReportFile}"`): no result file has been written, so the previous run's verdict still stands.

**Write the result contract.** The shared emitter writes it, per `{outputContractSchema}`, and every value in it comes from the run's own records: `{resultContextScript}` (it resolves relative to the skill root) reads the report frontmatter, the gap ledger and the scoring output, derives `verdict`, `exit_code` and `next_workflow` from `testResult`, and writes the emitter's payload. Pass `--score` for a scored run (a run the hard gate blocked has no scoring output), `--no-health-check` when that flag was given, and `--warning` when SKILL.md On Activation step 3 kept a `{customization_resolver_unavailable}` reason: first write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes, backticks or `$( )`), and pass that file's text (the emitter adds the warnings a stage recorded in the run's sink):

```bash
uv run {resultContextScript} --report "{report_file}" --ledger "{ledgerFile}" [--score "{run_dir}/score.json"] [--no-health-check] [--warning "$(cat "{run_dir}/resolver-warning.txt")"] --output "{run_dir}/result-context.json"
```

Bind `{emit_target}` ← `target` from its JSON (`stderr` for a run the hard gate blocked, else `stdout`). Exit 1: HALT with its `error` (`halt_reason: "helper-failed"`, phase `report:result-contract`). Then, in every mode, run:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-test-skill --run-dir "{run_dir}" --result-dir "{forge_version}" --target {emit_target} < "{run_dir}/result-context.json"
```

It writes `{forge_version}/skf-test-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name) and then its `skf-test-skill-result-latest.json` copy (stable path for pipeline consumers: a copy, not a symlink), each atomically, so a partial write is never observable; stamps the timestamp, `run_id`, `headless_decisions` and `warnings` into both; and prints the `SKF_TEST_RESULT_JSON:` line. Bind `{result_line}` ← that line and `{result_path}` ← its `result_path`. A run the hard gate blocked writes the record too, as a FAIL (`status: "error"`, `verdict: "FAIL"`, `halt_reason: "hard-gate-blocked"`, `exit_code` 2), so `skf-test-skill-result-latest.json` never holds an earlier run's verdict. A result file that could not be written leaves `result_path` null and a `result_file_write_failed` warning in the line, and the run still finishes. If the emitter exits non-zero, run both commands once more; if it fails again, HALT (`halt_reason: "write-failed"`, phase `report:result-contract`) with its stderr: the run's result contract could not be written. `references/invocation-contract.md` lists the record's fields.

Once the result files are written, append `'report'` to `stepsCompleted` in the `{outputFile}` frontmatter (it stays out of the expected set above).

**Post-finalization hook.** If `{onCompleteCommand}` (resolved in SKILL.md On Activation §3 from `workflow.on_complete` scalar) is non-empty and `{result_path}` is not null, invoke it as:

```bash
{onCompleteCommand} --result-path={result_path}
```

Run it with a bounded timeout (default 60s). On success: log Info note "on_complete: invoked {command}" and continue. On non-zero exit, timeout, or any failure: keep the reason (for example `on_complete failed (exit {N}): {stderr_first_line}`) for a line of its own in §6, and continue. **The hook must never fail the workflow**: its purpose is integration glue (notify a CI router, post to a queue, archive the result) and any failure there is orthogonal to the test verdict, which the result files already hold. If `{onCompleteCommand}` is empty, this hook is a no-op (no log entry needed).

### 5. Finalize Output Document

The report is final once §4c published it and wrote the result files: no later section changes it.

**INCONCLUSIVE as gate:** if `testResult == 'inconclusive'` (from step 5), §4c wrote the result contract with that verdict and §6 presents it. Do not auto-map INCONCLUSIVE to PASS or FAIL. Recommend `manual-review`. The step must still complete (§7 dispatches the health check): INCONCLUSIVE is a report-time signal, not a workflow abort.

### 6. Present Final Report

"**Test complete for {skill_name}.**

---

**Result:** **{PASS|PASS_WITH_DRIFT|FAIL|INCONCLUSIVE}** — **{score}%** (threshold: {threshold}%)

{If the hard gate blocked the run, in place of the line above:}
**Result:** **FAIL**, not scored: the hard gate blocked the run on {blocking_gaps} Critical or High gap(s).

{If `thresholdFallback` is present in output frontmatter:}
**Threshold fallback:** scored {score}% against {originalThreshold} target — accepted at 80% floor. Evidence report: {evidenceReportPath}

**Gaps Found:** {total_gaps}
- Critical: {gap_counts.Critical}
- High: {gap_counts.High}
- Medium: {gap_counts.Medium}
- Low: {gap_counts.Low}
- Info: {gap_counts.Info}

**Report saved to:** `{outputFile}`
{If the on_complete hook failed:}
**on_complete hook failed:** {its reason}. The verdict and the result files stand.

---

**Recommended next step:**

{IF PASS:}
**export-skill** — This skill is ready for export. Run the export-skill workflow to package it for distribution.

{IF PASS_WITH_DRIFT:}
**update-skill** — The skill scored above threshold, but `--allow-workspace-drift` was in effect: the test ran against workspace HEAD, not `metadata.source_commit`. A conditional PASS is not trustworthy enough to export. Re-sync the source tree to the pinned commit (or re-extract against current HEAD) and re-run test-skill without the drift override before exporting.

{IF FAIL after scoring:}
**update-skill `--from-test-report`**: This skill needs remediation. Review the Gap Report above, then run `@Ferris US {skill_name} --from-test-report`: Update Skill reads this report's gaps and repairs the skill at its pinned commit. Test it again afterwards.

{IF the hard gate blocked the run:}
**update-skill `--from-test-report`**: The hard gate stopped this run before scoring on {blocking_gaps} Critical or High gap(s), listed first in the Gap Report. Run `@Ferris US {skill_name} --from-test-report` to repair them, then test again.

{IF INCONCLUSIVE:}
**manual-review** — The evidence base was too thin to grade automatically. See `inconclusiveReasons` in the Completeness Score section. Typical fixes: upgrade forge tier, enable external validators, or re-extract with a wider scope. Do not export.

---

**See Discovery Quality section in the report for description optimization and realistic prompt testing recommendations.**

**Test report finalized.**"

### 6b. Keep the Headless Result Envelope for the Last Line

If `{headless_mode}`, bind `{result_envelope_line}` ← `{result_line}`, the `SKF_TEST_RESULT_JSON` line §4c's emitter printed, a blocked run's included. Do not display it here and never retype it: the shared health check displays it verbatim as the run's last line, after everything else it shows (§7 displays it itself under `--no-health-check`), so it is the final message of a headless run. Non-headless runs bind nothing: the §6 presentation is their result.

### 7. Health-Check Dispatch

**`--no-health-check` flag bypass.** If `no_health_check: true` is set in workflow context (from the `--no-health-check` flag, `init.md` §1), §4c already recorded `health_check_dispatched: false` in the report and `healthCheckDispatched: false` in the result files. Release the run lock now, from `{project-root}`, with `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`, and remove the run folder with `rm -rf "{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}"`. Log Info note "health-check: skipped, --no-health-check flag set", then, in `{headless_mode}`, display `{result_envelope_line}` verbatim as the run's last line, with nothing after it. The workflow ends there (non-headless, after the §6 presentation): do not chain to `{nextStepFile}`. This flag is the one path where §7 does not dispatch the health-check.

**Release the run lock:** §4c's write of the result files was the run's last, and the health check writes none, so no run waits on this one while the health check runs. From `{project-root}`, run:

```bash
uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"
```

Then remove the run folder init.md §6b created: no later step reads it.

```bash
rm -rf "{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}"
```

Then load and execute `{nextStepFile}` (the local health-check step, which hands over to the `{healthCheckFile}` §4c found), with no menu before it: the run is finished, and the health check is informational. The test report at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report. In `{headless_mode}`, `{result_envelope_line}` (§6b) is bound, and the health check displays it as the run's last line.
