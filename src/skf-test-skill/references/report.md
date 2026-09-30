---
nextStepFile: 'health-check.md'

outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
# The run's gap ledger: the stages recorded their gaps in it, §4b adds the
# discovery outcome, and §4c renders the Gap Report from it.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
scoringRulesFile: '{scoringRulesPath}'
outputFormatsFile: '{outputFormatsPath}'
# outputContractSchema and healthCheck resolve relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file. Both paths are probed in
# order; HALT if neither exists.
outputContractSchema: 'shared/references/output-contract-schema.md'
healthCheckProbeOrder:
  - '{project-root}/_bmad/skf/shared/health-check.md'
  - '{project-root}/src/shared/health-check.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §4b.0 reads the
# inventory to count the folders that hold a skill.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. Test report prose in {document_output_language}. -->

# Step 6: Gap Report

## STEP GOAL:

Publish the run. Record the discovery outcome in the gap ledger, render the Gap Report from the ledger, check that every stage ran and wrote its section, then write the result contract, run the on_complete hook and present the result. Do not recalculate scores (step 5 ran them) or classify the stages' gaps again (each stage recorded its own). A run the hard gate blocked comes here straight from step 4c and takes the same sequence, with the blocked-run branch each section names. This step chains to the local health-check step via `{nextStepFile}` after completion; the user-facing report is not the terminal step.

Every HALT in this step releases the run lock first (SKILL.md Workflow Rules), and §7 releases it when the run ends.

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
2. §4c renders the Gap Report from the ledger and checks that every stage ran and wrote its section, then writes the result contract and runs the on_complete hook.
3. §6 presents the result, §6b and §6c settle the exit code and the headless envelope, and §7 hands over to the health check and releases the run lock.

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

Optional escape hatch: the workflow accepts `--discovery-catalog=all` to broaden the candidate pool to `{project-root}/.claude/skills/` or `{project-root}/_bmad/agents/` for single-skill repos where the repo-local catalog is trivially too small. When the flag is set, add each folder directly in `{project-root}/.claude/skills/` or `{project-root}/_bmad/agents/` that holds a `SKILL.md` directly to `{discovery_catalog}` (a name already in it counts once), then recount `catalog_size` before the precondition check.

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

Exit 0: continue. Exit 2: nothing was written; correct the record `errors[]` names and run the command again. Exit 1: HALT with the script's `error`. Discovery runs after the hard gate, so a discovery gap blocks nothing, a High one included: it is counted in the Gap Report's totals and in the counts §6 presents, never as a blocking gap.

### 4c. Result Contract (atomic write)

Nothing is published until the report is whole: render the Gap Report and check the report first, and only then write the result files and run the on_complete hook.

**Render the Gap Report.** The ledger now holds every gap of the run (`{gapLedgerScript}` resolves relative to the skill root):

```bash
uv run {gapLedgerScript} render --ledger "{ledgerFile}" --heading
```

Exit 0: its output is the whole Gap Report section, heading included: the totals, the Remediation Summary and one entry per gap, by severity (with no gaps, it says none were found). Write it unchanged in place of the template's `## Gap Report` heading and the placeholder comment under it, in `{outputFile}`, then add the **Discovery Quality** subsection under it (format in `{outputFormatsFile}`): the §4b outcome, its prompt table or skip note, and the §4b.4 hints, or, for a run the hard gate blocked, the line that discovery testing did not run. Any other exit printed its error on stderr: HALT with it.

Then take the gap counts from the ledger:

```bash
uv run {gapLedgerScript} summary --ledger "{ledgerFile}"
```

Bind `{gap_counts}` ← `counts`, `{total_gaps}` ← `total` and `{blocking_gaps}` ← `blocking`: the result contract and §6 use them. Exit 1: HALT with its `error`.

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

A run the hard gate blocked was never scored: its expected set ends at `'hard-gate'`. If any expected entry is missing, HALT with "step completeness violation: missing {list}; workflow state is inconsistent, do not finalize the report". **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"step-completeness-violation"}
```

**Check the report sections.** Each stage wrote its section in place of its heading and the placeholder comment under it in the template, so a stage that skipped its section left the placeholder behind, and one that appended its section instead left its heading twice. Count them with grep, not by eye, and read the counts it prints (a count of 0 also makes grep exit 1):

```bash
for heading in '## Test Summary' '## Coverage Analysis' '## Coherence Analysis' '## External Validation' '## Completeness Score' '## Gap Report'; do
  printf '%s: ' "$heading"; grep -cxF "$heading" "{outputFile}"
done
printf 'placeholders: '; grep -c '^<!-- Populated by' "{outputFile}"
```

Each heading must print 1, standing alone on exactly one line, and `placeholders` must print 0. A run the hard gate blocked has all six: step 4c §3 wrote the Completeness Score section in scoring's place. On a heading whose count is not 1, or a placeholder left, HALT with "report anchor missing: {each heading whose count is not 1, with its count}, or {N} placeholder comments left; the section was not written once by its owning step". **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"report-anchor-missing"}
```

**Renew the run lock** before anything below writes. The lock init.md §6a took goes stale 60 minutes after it was taken, and a long run can outlast that; an acquire by the owner that holds the lock renews it. From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"
```

- Exit 0: the lock is this run's again; continue.
- Exit 3 (`acquired` is false): another run took the lock over after this run's lock went stale. HALT before writing anything, with "**Another test-skill run took over the run lock for {skill_name}.** This run wrote no result files. {message}", where `{message}` is the helper's. **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

  ```
  SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"another-run-active"}
  ```

- Exit 1 or 2, or no JSON: HALT with the helper's stderr message, as init.md §6b does.

**Resolve `{atomicWriteHelper}`:** probe `{atomicWriteProbeOrder}`. HALT if neither candidate exists — the contract is a downstream-consumer protocol and must never be written non-atomically. **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"atomic-writer-missing"}
```

Write the result contract per `{outputContractSchema}`:
- Per-run record: `{forge_version}/skf-test-skill-result-{run_id}.json` (the `{run_id}` init.md §6a took with the run lock: the UTC time and a random suffix, so two runs in the same second never collide).
- Latest copy: `{forge_version}/skf-test-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink).

Both writes must go through the atomic writer so partial writes are never observable:

```bash
# Build the JSON payload in memory, then:
cat payload.json | python3 {atomicWriteHelper} write --target {forge_version}/skf-test-skill-result-{run_id}.json
cat payload.json | python3 {atomicWriteHelper} write --target {forge_version}/skf-test-skill-result-latest.json
```

Payload contents:
- `outputs[]` — include the test report path at `{outputFile}` with its `{run_id}` suffix
- `summary` — `score`, `threshold`, `result` (`"PASS"`, `"PASS_WITH_DRIFT"`, `"FAIL"`, or **`"INCONCLUSIVE"`**), `testMode` (naive/contextual), `activeCategories[]`, `inconclusiveReasons[]` (when present). `PASS_WITH_DRIFT` is set when the workflow observed workspace drift and the user passed `--allow-workspace-drift` — see step 5 §5 drift override. Downstream consumers must treat `PASS_WITH_DRIFT` as a non-exportable result: re-run against the pinned commit before export. When threshold fallback occurred, add `threshold_fallback: true`, `original_threshold: {N}`, and `evidence_report_path: '{path}'` to the summary — these fields are absent (not `false`/`null`) when no fallback occurred.
- `runId` — the workflow's `{run_id}` for downstream correlation
- `healthCheckDispatched` — boolean, set by §7 after the dispatch decision
- `summary.gapCounts`: `{gap_counts}`, the ledger's gaps by severity (discovery included), and `summary.hardGate`: `passed` or `blocked`, from the frontmatter.
- **A run the hard gate blocked** writes this record too, as a FAIL: `status: "error"`, `verdict: "FAIL"`, `score` and `threshold` null, `next_workflow: "update-skill"`, `exit_code: 2` and `halt_reason: "hard-gate-blocked"` (the values of its §6c envelope), with `summary.result` `"FAIL"`, `summary.score` and `summary.threshold` null and `summary.activeCategories` empty. `skf-test-skill-result-latest.json` then holds this run's FAIL, never an earlier run's verdict.

The run lock renewed above stays held until §7 releases it after the result contract's last rewrite, so no other run overwrites `skf-test-skill-result-latest.json` meanwhile.

Once both result files are written, append `'report'` to `stepsCompleted` in the `{outputFile}` frontmatter (it stays out of the expected set above).

**Post-finalization hook.** If `{onCompleteCommand}` (resolved in SKILL.md On Activation §3 from `workflow.on_complete` scalar) is non-empty, invoke it as:

```bash
{onCompleteCommand} --result-path={forge_version}/skf-test-skill-result-{run_id}.json
```

Run it with a bounded timeout (default 60s). On success: log Info note "on_complete — invoked: {command}" and continue. On non-zero exit, timeout, or any failure: append the failure reason to `workflow_warnings[]` (e.g. `on_complete — failed (exit {N}): {stderr_first_line}`) and continue. **The hook must never fail the workflow** — its purpose is integration glue (notify a CI router, post to a queue, archive the result) and any failure there is orthogonal to the test verdict. If `{onCompleteCommand}` is empty, this hook is a no-op (no log entry needed).

### 5. Finalize Output Document

The report is final once §4c wrote the result files: no later section changes its body, and §7 only records `health_check_dispatched` in its frontmatter.

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

### 6b. Determine Headless Exit Code

This step only determines the terminal exit code — it does not exit. Both modes then reach §7 (headless auto-proceeds past the menu; non-headless goes through the [C] menu), and the terminal process-exit with this code happens in §7 after the health-check dispatch.

If `{headless_mode}`, map `testResult` to the code the workflow will exit with in §7 and store it as `{headless_exit_code}` in workflow context:
- `testResult: 'pass'` → exit code 0
- `testResult: 'pass-with-drift'` → exit code 4 (distinct from clean pass — see the pass-with-drift row in SKILL.md Exit Codes; exiting 0 under a drift override would wrongly signal a clean pass)
- `testResult: 'fail'` → exit code 2, a run the hard gate blocked included (the result contract was written in §4c: never exit before it)
- `testResult: 'inconclusive'` → exit code 3 (distinct from fail so orchestrators can route to manual-review queues)

### 6c. Emit Headless Result Envelope

If `{headless_mode}`, emit the terminal result envelope to **stdout** as a single line before chaining to §7 — this is the branchable record a headless orchestrator reads for the happy path (PASS / FAIL / INCONCLUSIVE / pass-with-drift). The SKILL.md Result Contract owns the shape and the field rules; the on-disk copy written in §4c is the richer form. Build it from the settled verdict and the values already in the output frontmatter:

```
SKF_TEST_RESULT_JSON: {"status":"success","skill_name":"{skill_name}","verdict":"{PASS|FAIL|INCONCLUSIVE|pass-with-drift}","score":{score},"threshold":{threshold},"report_path":"{outputFile}","next_workflow":{export-skill when PASS | update-skill when FAIL or pass-with-drift | null when INCONCLUSIVE},"exit_code":{headless_exit_code},"halt_reason":null}
```

`verdict` is uppercase for `pass`/`fail`/`inconclusive` (→ `PASS`/`FAIL`/`INCONCLUSIVE`) and the literal `pass-with-drift`. When threshold fallback occurred (frontmatter `thresholdFallback: true`), add `"threshold_fallback":true` and `"original_threshold":{originalThreshold}`; omit both otherwise. Non-headless runs skip this emission — the §6 presentation is their terminal output.

**A run the hard gate blocked** emits its envelope on **stderr** instead, with `status: "error"` and the values §4c recorded:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":"FAIL","score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":"update-skill","exit_code":2,"halt_reason":"hard-gate-blocked"}
```

### 7. Health-Check Dispatch + MENU OPTIONS

**`--no-health-check` flag bypass (precedes the health-check resolution).** If `no_health_check: true` is set in workflow context (from the `--no-health-check` flag, `init.md` §1), set `health_check_dispatched: false` in the output report frontmatter and mirror `healthCheckDispatched: false` into the result contract written in §4c (re-write atomically via `{atomicWriteHelper}`). That rewrite is the run's last write to the result files: release the run lock now, from `{project-root}`, with `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`. Log Info note "health-check: skipped, --no-health-check flag set" and exit the workflow: in `{headless_mode}`, exit with `{headless_exit_code}` (determined in §6b); non-headless, simply terminate after the §6 presentation. Do not resolve `{healthCheckFile}`, do not display the menu, do not chain to `{nextStepFile}`. This flag is the one path where §7 does not dispatch the health-check.

Resolve `{healthCheckFile}`: probe `{healthCheckProbeOrder}` in order. **HALT** if neither candidate exists — the health-check is the true terminal step; without it the workflow cannot complete honestly:

```
Error: cannot locate shared/health-check.md at either of:
  - {project-root}/_bmad/skf/shared/health-check.md
  - {project-root}/src/shared/health-check.md

test-skill delegates its terminal step to the shared health-check. Install
the SKF module or run from a development checkout with src/ present.
```

**Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"health-check-missing"}
```

Before displaying the menu, write the dispatch decision into the output report frontmatter (so the artifact records whether the health-check ran):

- `health_check_dispatched: true` — when the C menu choice will be taken (headless, or user will select C)
- `health_check_dispatched: false` — should be rare (only if operator explicitly skips, e.g. future flag)

Also mirror the boolean into the `healthCheckDispatched` field of the result contract written in §4c (re-write atomically via `{atomicWriteHelper}` if the dispatch decision is made after the initial contract write).

**Release the run lock:** that rewrite is the run's last write to the result files, and releasing before the menu keeps a run that waits at [C], and the health check after it, from holding the lock. From `{project-root}`, run:

```bash
uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"
```

Display: "**Test complete.** [C] Finish"

On [C] (or auto-proceed in `{headless_mode}` — log: "headless: auto-continue past report menu"): set `health_check_dispatched: true` in frontmatter, then load and execute `{nextStepFile}` (the local health-check dispatcher). The test report document at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report. In `{headless_mode}`, once the dispatched health-check completes, the workflow makes its terminal process-exit with `{headless_exit_code}` (determined in §6b) — this is the single terminal exit for the headless happy path.

