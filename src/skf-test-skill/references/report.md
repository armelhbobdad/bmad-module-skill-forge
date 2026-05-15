---
nextStepFile: 'health-check.md'

outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
scoringRulesFile: 'references/scoring-rules.md'
outputFormatsFile: 'assets/output-section-formats.md'
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

Generate a detailed gap report listing every issue found during coverage and coherence analysis, assign severity to each gap, provide specific actionable remediation suggestions, and finalize the test report document. This is the final step — no next step file.

## Rules

- Focus on gap enumeration, severity classification, and remediation — do not recalculate scores
- Remediation suggestions reference specific files, exports, and line numbers
- Gaps are ordered by severity (Critical > High > Medium > Low > Info)
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

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

Load `{scoringRulesFile}` for gap severity classification:

| Severity | Criteria |
|----------|----------|
| **Critical** | Missing exported function/class documentation |
| **High** | Signature mismatch between source and SKILL.md |
| **Medium** | Missing type or interface documentation |
| **Medium** | Migration section present/absent mismatch with T2-future annotation data (Deep tier) |
| **Medium** | Script/asset directory exists but no Scripts & Assets section in SKILL.md |
| **Medium** | Scripts & Assets section references file not found in scripts/ or assets/ directory |
| **Low** | Script/asset file present without provenance entry in provenance-map.json file_entries |
| **Low** | Missing optional metadata or examples |
| **Low** | Description trigger optimization recommended (third-person voice, negative triggers, or keyword coverage gaps) |
| **Info** | Style suggestions, non-blocking observations |
| **Info** | Discovery testing not performed — realistic prompt testing recommended before export |

### 3. Classify and Order Gaps

Load `{outputFormatsFile}` for gap entry format and remediation quality rules.

For each issue, assign severity from `{scoringRulesFile}` and generate a specific remediation following the quality rules in `{outputFormatsFile}`. Order gaps by severity: Critical → High → Medium → Low → Info.

### 4. Generate Remediation Summary and Append Gap Report

Load the Gap Report section format from `{outputFormatsFile}`. Count gaps by severity, estimate effort per the guidelines in `{outputFormatsFile}`, and append the complete **Gap Report** section to `{outputFile}`.

If no gaps found, append a clean pass message recommending **export-skill** workflow.

### 4b. Discovery Testing (MANDATORY — H4)

After gap enumeration, perform minimum-viable discovery testing. This is a **Medium-weight** check contributing to the Discovery Quality subsection — no longer advisory boilerplate.

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

For each of the 3 prompts, spawn an isolated subagent with NO prior context about which skill is under test. Provide only:
1. A compact list of ALL skills available in `{skillsOutputFolder}` (name + description line from each skill's SKILL.md frontmatter)
2. The prompt text

Instruction to the subagent:

> "You are an agent selecting the best skill to handle a user request. Here is the catalog: {catalog}. The user says: '{prompt}'. Return JSON: `{\"selected_skill\": \"<name>\", \"confidence\": \"<high|medium|low>\", \"reasoning\": \"<one sentence>\"}`. If no skill fits, return `{\"selected_skill\": null, ...}`. Return ONLY JSON."

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

### 4c. Result Contract (atomic write — B4)

**Resolve `{atomicWriteHelper}`:** probe `{atomicWriteProbeOrder}`. HALT if neither candidate exists — the contract is a downstream-consumer protocol and must never be written non-atomically.

Write the result contract per `{outputContractSchema}`:
- Per-run record: `{forge_version}/skf-test-skill-result-{run_id}.json` (the `{run_id}` set in step 1 §6a — already carries UTC timestamp + PID + random suffix, so no same-second collision).
- Latest copy: `{forge_version}/skf-test-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink).

Both writes MUST go through the atomic writer so partial writes are never observable:

```bash
# Build the JSON payload in memory, then:
cat payload.json | python3 {atomicWriteHelper} write --target {forge_version}/skf-test-skill-result-{run_id}.json
cat payload.json | python3 {atomicWriteHelper} write --target {forge_version}/skf-test-skill-result-latest.json
```

Payload contents:
- `outputs[]` — include the test report path at `{outputFile}` with its `{run_id}` suffix
- `summary` — `score`, `threshold`, `result` (`"PASS"`, `"PASS_WITH_DRIFT"`, `"FAIL"`, or **`"INCONCLUSIVE"`**), `testMode` (naive/contextual), `activeCategories[]`, `inconclusiveReasons[]` (when present). `PASS_WITH_DRIFT` is set when the workflow observed workspace drift and the user passed `--allow-workspace-drift` — see step 5 §5 (M5). Downstream consumers MUST treat `PASS_WITH_DRIFT` as a non-exportable result: re-run against the pinned commit before export.
- `runId` — the workflow's `{run_id}` for downstream correlation
- `healthCheckDispatched` — boolean, set by §7 after the dispatch decision

The `{forge_version}/.test-skill.lock` acquired in step 1 §6b remains held until the end of this step — it guards against concurrent latest-file overwrites.

### 5. Finalize Output Document — Enforce Step Completeness

**Per S6 (incremental step tracking):** read `stepsCompleted` from the output frontmatter. The expected set is the canonical chain:

```
['init',
 'detect-mode',
 'coverage-check',
 'coherence-check',
 'external-validators',
 'score',
 'report']
```

If any expected entry is missing, HALT with "step completeness violation — missing {list}; workflow state is inconsistent, do not finalize the report". Only append `'report'` and write back after the check passes.

**M4 — Section anchor presence check (companion to stepsCompleted).** The
report template ships six canonical H2 anchors — one per populating step. An
off-sequence run (e.g. a step wrote its section into the wrong anchor, or a
subagent truncated the file) can leave `stepsCompleted` intact while a section
is missing. `grep -n` each anchor below against `{outputFile}`; each MUST
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
appended by its owning step". Do NOT append `'report'` and do NOT
write the result contract. The template in `templates/test-report-template.md`
declares these anchors as TBD placeholders; a miss means a step silently
skipped its append.

**INCONCLUSIVE as gate:** if `testResult == 'inconclusive'` (from step 5), the report final presentation (§6) and result contract (§4c) have already been written with that verdict. Do NOT auto-map INCONCLUSIVE to PASS or FAIL. Recommend `manual-review`. The step must still complete (health-check runs unconditionally) — INCONCLUSIVE is a report-time signal, not a workflow abort.

### 6. Present Final Report

"**Test complete for {skill_name}.**

---

**Result:** **{PASS|PASS_WITH_DRIFT|FAIL|INCONCLUSIVE}** — **{score}%** (threshold: {threshold}%)

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
**manual-review** — The evidence base was too thin to grade automatically. See `inconclusiveReasons` in the Completeness Score section. Typical fixes: upgrade forge tier, enable external validators, or re-extract with a wider scope. Do NOT export.

---

**See Discovery Quality section in the report for description optimization and realistic prompt testing recommendations.**

**Test report finalized.**"

### 6b. Headless Exit Status (S7)

If `{headless_mode}`:
- `testResult: 'pass'` → `exit 0`
- `testResult: 'pass-with-drift'` → `exit 4` (distinct from clean pass — orchestrators MUST route to re-test-against-pinned-commit queues and refuse export; never exit 0 under drift override)
- `testResult: 'fail'` → `exit 2` (after the result contract has been written in §4c — never before)
- `testResult: 'inconclusive'` → `exit 3` (distinct from fail so orchestrators can route to manual-review queues)

Non-headless mode always drops to the menu in §7.

### 7. Health-Check Dispatch + MENU OPTIONS

Resolve `{healthCheckFile}` per H2: probe `{healthCheckProbeOrder}` in order. **HALT** if neither candidate exists — the health-check is the true terminal step; without it the workflow cannot complete honestly:

```
Error: cannot locate shared/health-check.md at either of:
  - {project-root}/_bmad/skf/shared/health-check.md
  - {project-root}/src/shared/health-check.md

test-skill delegates its terminal step to the shared health-check. Install
the SKF module or run from a development checkout with src/ present.
```

Before displaying the menu, write the dispatch decision into the output report frontmatter (so the artifact records whether the health-check ran):

- `health_check_dispatched: true` — when the C menu choice will be taken (headless, or user will select C)
- `health_check_dispatched: false` — should be rare (only if operator explicitly skips, e.g. future flag)

Also mirror the boolean into the `healthCheckDispatched` field of the result contract written in §4c (re-write atomically via `{atomicWriteHelper}` if the dispatch decision is made after the initial contract write).

Display: "**Test complete.** [C] Finish"

#### Menu Handling Logic:

- IF C: Load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.
- IF Any other: help user respond, then redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past report menu"; set `health_check_dispatched: true` in frontmatter before chaining
- C triggers the health check, which is the true workflow exit
- User may ask questions about the report before finishing

## CRITICAL STEP COMPLETION NOTE

When the user selects C, this step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md`. After the health check completes, the test-skill workflow is fully done. The test report document at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report.

