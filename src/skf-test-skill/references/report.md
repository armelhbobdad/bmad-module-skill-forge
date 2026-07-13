---
nextStepFile: 'health-check.md'

outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
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
---

<!-- Config: communicate in {communication_language}. Test report prose in {document_output_language}. -->

# Step 6: Gap Report

## STEP GOAL:

Generate a detailed gap report listing every issue found during coverage and coherence analysis, assign severity to each gap, provide specific actionable remediation suggestions, and finalize the test report document. Do not recalculate scores — that ran in step 5. This step chains to the local health-check step via `{nextStepFile}` after completion; the user-facing report is not the terminal step.

### 1. Collect All Issues

Read `{outputFile}` and extract every issue found across all analysis sections:

**From Coverage Analysis (step 03):**
- Missing documentation (exports in source but not in SKILL.md)
- Signature mismatches (documented signature differs from source)
- Stale documentation (documented but no longer in source)
- Type coverage gaps (undocumented types/interfaces)

**From Coherence Analysis (step 04):**
- Broken references (file paths, skill references, type imports that don't resolve)
- Incomplete integration patterns (contextual mode)
- Structural issues (naive mode — missing sections, broken examples)

**From External Validation (step 04b):**
- skill-check diagnostics (unresolved errors and warnings)
- tessl judge suggestions (content quality and actionability improvements)

### 2. Load Severity Rules

Load the **Gap Severity** table from `{scoringRulesFile}` — it is the single source of truth for classifying every gap (Critical / High / Medium / Low / Info). Classify each issue directly against that table in §3; do not restate its rows here, so the table cannot drift between this step and the scoring step that already consumes it.

### 3. Classify and Order Gaps

Load `{outputFormatsFile}` for gap entry format and remediation quality rules.

For each issue, assign severity from `{scoringRulesFile}` and generate a specific remediation following the quality rules in `{outputFormatsFile}`. Remediation suggestions must reference specific files, exports, and line numbers. Order gaps by severity: Critical → High → Medium → Low → Info.

### 4. Generate Remediation Summary and Append Gap Report

Load the Gap Report section format from `{outputFormatsFile}`. Count gaps by severity, estimate effort per the guidelines in `{outputFormatsFile}`, and append the complete **Gap Report** section to `{outputFile}`.

If no gaps found, append a clean pass message recommending **export-skill** workflow.

### 4b. Discovery Testing

**`--no-discovery` flag bypass (precedes the precondition check).** If `no_discovery: true` is set in workflow context (from §1 of `init.md` — `--no-discovery` flag on invocation), record an Info-severity note in the Discovery Quality subsection: `discovery — skipped: --no-discovery flag set`, log the bypass, and SKIP §4b.1–§4b.3. Proceed to §4b.4 (description optimization) only if tessl/skill-check flagged description issues; otherwise skip directly to §4c.

After gap enumeration, perform minimum-viable discovery testing. This is a **Medium-weight** check contributing to the Discovery Quality subsection.

**4b.0 Precondition — catalog size check:**

Count the skills in `{skillsOutputFolder}`: `ls -1d {skillsOutputFolder}/*/ 2>/dev/null | wc -l` (directories only — each skill package lives at `{skillsOutputFolder}/<skill-name>/`).

- If `catalog_size < 2`: **skip §4b.1–§4b.3**. Record an Info-severity note in the Discovery Quality subsection: `discovery — skipped: catalog size N={catalog_size}, requires ≥2 candidates for meaningful routing`. The routing test is vacuous with one candidate (any prompt returns the sole skill); reporting `3/3 PASS` under those conditions inflates the Discovery score and masks genuinely bad description triggers. Proceed to §4b.4 (description optimization) if tessl/skill-check flagged description issues; otherwise skip to §4c.
- If `catalog_size >= 2`: continue with §4b.1 as written.

Optional escape hatch: the workflow accepts `--discovery-catalog=all` to broaden the candidate pool to `{project-root}/.claude/skills/` or `{project-root}/_bmad/agents/` for single-skill repos where the repo-local catalog is trivially too small. When the flag is set, rebuild `catalog_size` from the broader pool before the precondition check.

**4b.1 Extract realistic prompts from the skill under test:**

Parse SKILL.md for the three most "organic" prompts found in its `description`, `Triggers`, or example sections. Prefer prompts that:
- Use conversational phrasing (contractions, casual language, implicit context)
- Omit the skill name or explicit command invocation
- Reflect how a user would actually ask for this capability

If SKILL.md does not contain enough organic examples, synthesize 3 from the skill's exports/capability summary using the patterns from §4b.4 below.

**4b.2 Spawn a discovery subagent:**

**Subagents-unavailable guard (precedes the spawn).** If subagents cannot be spawned in this environment (e.g. a headless/CI pipeline with no subagent capability), do not fall back to answering the routing in the main thread — the main thread knows which skill is under test, so it would self-route to `3/3 PASS` and inflate the Discovery score, the exact false confidence §4b.0 warns against. Instead record an Info-severity note in the Discovery Quality subsection: `discovery — skipped: subagents unavailable, routing test requires isolated context`, exclude the discovery check from Discovery Quality scoring (do not count it PASS or FAIL), and skip to §4c.

For each of the 3 prompts, spawn an isolated subagent with NO prior context about which skill is under test. Provide only:
1. A compact list of ALL skills available in `{skillsOutputFolder}` (name + description line from each skill's SKILL.md frontmatter)
2. The prompt text

Instruction to the subagent:

> "You are an agent selecting the best skill to handle a user request. Here is the catalog: {catalog}. The user says: '{prompt}'. Return JSON: `{\"selected_skill\": \"<name>\", \"confidence\": \"<high|medium|low>\", \"reasoning\": \"<one sentence>\"}`. If no skill fits, return `{\"selected_skill\": null, ...}`. Return only JSON."

**4b.3 Evaluate discovery results:**

Parse the 3 responses. Schema-validate (required: `selected_skill`, `confidence`, `reasoning`). On any parse/schema failure, record the prompt as `discovery_result: error` and continue.

For each prompt, PASS = `selected_skill == skill_name` (the skill under test), FAIL otherwise.

- **3 of 3 PASS** → discovery check PASS (Info severity note, no gap)
- **2 of 3 PASS** → discovery check WARN → **Medium**-severity gap: `discovery — 1/3 realistic prompts misrouted`
- **≤1 of 3 PASS** → discovery check FAIL → **High**-severity gap: `discovery — {N}/3 realistic prompts misrouted; description triggers are not pulling the skill`

Append the prompts, selected skills, and outcomes as a table in the Discovery Quality subsection.

**4b.4 Description optimization (secondary):** If tessl `description_score` (from step 04b) is below 90%, or skill-check flagged description issues, add remediation hints to the Discovery Quality subsection:
- Third-person voice check
- Explicit trigger keywords matching real user phrasing
- Negative triggers ("NOT for: ...") to prevent false positives
- Alternative skill references for excluded use cases

Realistic prompt patterns for synthesis (§4b.1 fallback):
- Vague: "can you help me with this {artifact} my boss sent"
- Implicit: "why did {metric} drop last {period}"
- Abbreviated: "run the {keyword} thing on this data"

### 4c. Result Contract (atomic write)

**Resolve `{atomicWriteHelper}`:** probe `{atomicWriteProbeOrder}`. HALT if neither candidate exists — the contract is a downstream-consumer protocol and must never be written non-atomically. **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"atomic-writer-missing"}
```

Write the result contract per `{outputContractSchema}`:
- Per-run record: `{forge_version}/skf-test-skill-result-{run_id}.json` (the `{run_id}` set in step 1 §6a — already carries UTC timestamp + PID + random suffix, so no same-second collision).
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

The `{forge_version}/.test-skill.lock` acquired in step 1 §6b remains held until the end of this step — it guards against concurrent latest-file overwrites.

**Post-finalization hook.** If `{onCompleteCommand}` (resolved in SKILL.md On Activation §3 from `workflow.on_complete` scalar) is non-empty, invoke it as:

```bash
{onCompleteCommand} --result-path={forge_version}/skf-test-skill-result-{run_id}.json
```

Run it with a bounded timeout (default 60s). On success: log Info note "on_complete — invoked: {command}" and continue. On non-zero exit, timeout, or any failure: append the failure reason to `workflow_warnings[]` (e.g. `on_complete — failed (exit {N}): {stderr_first_line}`) and continue. **The hook must never fail the workflow** — its purpose is integration glue (notify a CI router, post to a queue, archive the result) and any failure there is orthogonal to the test verdict. If `{onCompleteCommand}` is empty, this hook is a no-op (no log entry needed).

### 5. Finalize Output Document — Enforce Step Completeness

**Incremental step tracking:** read `stepsCompleted` from the output frontmatter. The expected set is the canonical chain:

```
['init',
 'detect-mode',
 'coverage-check',
 'coherence-check',
 'external-validators',
 'hard-gate',
 'score',
 'report']
```

If any expected entry is missing, HALT with "step completeness violation — missing {list}; workflow state is inconsistent, do not finalize the report". **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"step-completeness-violation"}
```

Only append `'report'` and write back after the check passes.

**Section anchor presence check (companion to stepsCompleted).** The
report template ships six canonical H2 anchors — one per populating step. An
off-sequence run (e.g. a step wrote its section into the wrong anchor, or a
subagent truncated the file) can leave `stepsCompleted` intact while a section
is missing. `grep -n` each anchor below against `{outputFile}`; each must
return ≥1 match:

```
^## Test Summary$
^## Coverage Analysis$
^## Coherence Analysis$
^## External Validation$
^## Completeness Score$
^## Gap Report$
```

On any miss, HALT with "report anchor missing: {anchor} — section was not
appended by its owning step". **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"report-anchor-missing"}
```

Do not append `'report'` and do not
write the result contract. The template at `{testReportTemplatePath}`
declares these anchors as TBD placeholders; a miss means a step silently
skipped its append.

**INCONCLUSIVE as gate:** if `testResult == 'inconclusive'` (from step 5), the report final presentation (§6) and result contract (§4c) have already been written with that verdict. Do not auto-map INCONCLUSIVE to PASS or FAIL. Recommend `manual-review`. The step must still complete (health-check runs unconditionally) — INCONCLUSIVE is a report-time signal, not a workflow abort.

### 6. Present Final Report

"**Test complete for {skill_name}.**

---

**Result:** **{PASS|PASS_WITH_DRIFT|FAIL|INCONCLUSIVE}** — **{score}%** (threshold: {threshold}%)

{If `thresholdFallback` is present in output frontmatter:}
**Threshold fallback:** scored {score}% against {originalThreshold} target — accepted at 80% floor. Evidence report: {evidenceReportPath}

**Gaps Found:** {total_gaps}
- Critical: {N}
- High: {N}
- Medium: {N}
- Low: {N}
- Info: {N}

**Report saved to:** `{outputFile}`

---

**Recommended next step:**

{IF PASS:}
**export-skill** — This skill is ready for export. Run the export-skill workflow to package it for distribution.

{IF PASS_WITH_DRIFT:}
**update-skill** — The skill scored above threshold, but `--allow-workspace-drift` was in effect: the test ran against workspace HEAD, not `metadata.source_commit`. A conditional PASS is not trustworthy enough to export. Re-sync the source tree to the pinned commit (or re-extract against current HEAD) and re-run test-skill without the drift override before exporting.

{IF FAIL:}
**update-skill** — This skill needs remediation. Review the gap report above and run the update-skill workflow to address the {N} blocking issues (Critical + High).

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
- `testResult: 'fail'` → exit code 2 (the result contract was written in §4c — never exit before it)
- `testResult: 'inconclusive'` → exit code 3 (distinct from fail so orchestrators can route to manual-review queues)

### 6c. Emit Headless Result Envelope (stdout)

If `{headless_mode}`, emit the terminal result envelope to **stdout** as a single line before chaining to §7 — this is the branchable record a headless orchestrator reads for the happy path (PASS / FAIL / INCONCLUSIVE / pass-with-drift). The SKILL.md Result Contract owns the shape and the field rules; the on-disk copy written in §4c is the richer form. Build it from the settled verdict and the values already in the output frontmatter:

```
SKF_TEST_RESULT_JSON: {"status":"success","skill_name":"{skill_name}","verdict":"{PASS|FAIL|INCONCLUSIVE|pass-with-drift}","score":{score},"threshold":{threshold},"report_path":"{outputFile}","next_workflow":{export-skill when PASS | update-skill when FAIL or pass-with-drift | null when INCONCLUSIVE},"exit_code":{headless_exit_code},"halt_reason":null}
```

`verdict` is uppercase for `pass`/`fail`/`inconclusive` (→ `PASS`/`FAIL`/`INCONCLUSIVE`) and the literal `pass-with-drift`. When threshold fallback occurred (frontmatter `thresholdFallback: true`), add `"threshold_fallback":true` and `"original_threshold":{originalThreshold}`; omit both otherwise. Non-headless runs skip this emission — the §6 presentation is their terminal output.

### 7. Health-Check Dispatch + MENU OPTIONS

**`--no-health-check` flag bypass (precedes the health-check resolution).** If `no_health_check: true` is set in workflow context (from §1 of `init.md` — `--no-health-check` flag on invocation), set `health_check_dispatched: false` in the output report frontmatter and mirror `healthCheckDispatched: false` into the result contract written in §4c (re-write atomically via `{atomicWriteHelper}`). Log Info note "health-check — skipped: --no-health-check flag set" and exit the workflow: in `{headless_mode}`, exit with `{headless_exit_code}` (determined in §6b); non-headless, simply terminate after the §6 presentation. Do not resolve `{healthCheckFile}`, do not display the menu, do not chain to `{nextStepFile}`. This flag is the one path where §7 does not dispatch the health-check.

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

Display: "**Test complete.** [C] Finish"

On [C] (or auto-proceed in `{headless_mode}` — log: "headless: auto-continue past report menu"): set `health_check_dispatched: true` in frontmatter, then load and execute `{nextStepFile}` (the local health-check dispatcher). The test report document at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report. In `{headless_mode}`, once the dispatched health-check completes, the workflow makes its terminal process-exit with `{headless_exit_code}` (determined in §6b) — this is the single terminal exit for the headless happy path.

