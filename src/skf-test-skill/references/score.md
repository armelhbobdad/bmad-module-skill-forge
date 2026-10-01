---
nextStepFile: 'report.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
scoringScript: 'scripts/compute-score.py'
# §4b.1 reads the run's gaps from the gap ledger the stages recorded them in.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Score

## STEP GOAL:

Calculate the overall completeness score by aggregating coverage, coherence, and external validation category scores with the appropriate weight distribution (naive or contextual), apply the pass/fail threshold, and determine the test result.

Every HALT in this step releases the run lock first (SKILL.md Workflow Rules).

### 1. Resolve the Pass Threshold

`{scoringScript}` owns the category weights, their redistribution and every verdict rule; this step sets its flags, hands it the score files and reads its output.

**Resolve the pass threshold (precedence: CLI > pipeline default > scalar > bundled fallback):**

1. If the workflow received `--threshold=<N>` on invocation, use that integer as `effective_threshold` (CLI wins). Set `threshold_source` = `"CLI override ({N}%)"`.
2. Else if `{pipeline_default_threshold}` is set in workflow context (resolved by init.md §1b from the per-pipeline threshold lookup table when `{pipeline_alias}` is present), use it as `effective_threshold`. Set `threshold_source` = `"pipeline default ({pipeline_alias} → {N}%)"`.
3. Else if the resolved `{defaultThreshold}` workflow-context variable (from SKILL.md On Activation §3 — `workflow.default_threshold` scalar, default `80`) is set, use it as `effective_threshold`. Set `threshold_source` = `"workflow default ({N}%)"`.
4. Else fall back to `80` (the bundled default — this branch should be unreachable when SKILL.md resolution ran correctly, but keeps the step robust if customize.toml resolution failed silently). Set `threshold_source` = `"bundled fallback (80%)"`.

Store `threshold_source` in workflow context for use in the score report section.

Pass `effective_threshold` into the scoring-input JSON's `threshold` field in §3a. The CLI flag, pipeline default, and the scalar all feed the same downstream field; the script does not need to know which layer supplied the value.

### 2. The Category Score Files

The category scores are never read back out of the report: each is the output file of the script that computed it, in the run folder `{run_dir}` (init.md §6b), and §3b hands the files to the scoring script by path:

- `coverage.json`: Export Coverage (coverage-check §2c)
- `signatures.json`: Signature Accuracy and Type Coverage (coverage-check §2b; there is none at Quick tier, for a docs-only skill, at States 2 to 5, or for a stack or a reference app)
- `coherence.json`: the combined coherence (coherence-check §5c; contextual mode only)
- `external.json`: the external validation score (external-validators §4; its `externalScore` is null when neither validator scored)
- `surface.json`: at State 2, the provenance-map and metadata counts behind the State 2 undercount deduction (coverage-check §2)

### 3. Apply Weight Distribution

**Read testMode from {outputFile} frontmatter.**

#### 3a. Construct Scoring Input JSON

Build the flags the script reads from workflow context:

```json
{
  "mode": "{testMode: contextual or naive}",
  "tier": "{forge_tier: Quick, Forge, Forge+, or Deep}",
  "docsOnly": "{true if docs_only_mode is set (coverage-check §0), else false}",
  "state2": "{true if analysis_confidence is provenance-map, else false}",
  "stackSkill": "{true if metadata.json.skill_type == 'stack', else false}",
  "referenceApp": "{true if metadata.json.scope_type == 'reference-app', else false}",
  "threshold": "{effective_threshold from §1: CLI --threshold wins, then pipeline default, then workflow.default_threshold scalar, then 80}",
  "analysisConfidence": "{analysis_confidence: full, provenance-map, metadata-only, remote-only or docs-only}",
  "toolingStatus": "{tooling_status from init.md §3b: ok, or frontmatter-validator-timeout}"
}
```

**Important:** the flags are bare booleans (`true`, not `"true"`) and the threshold a number. Always pass `toolingStatus`: any value other than `ok` fires Cap 1 (§3d). `analysisConfidence` names the source access only, never tooling health. Read `metadata.json.skill_type` and `metadata.json.scope_type` from `{resolved_skill_package}/metadata.json`: a stack (`stackSkill`) and a reference app (`referenceApp`, which documents wiring patterns, not library export signatures) have no Signature Accuracy or Type Coverage, and the script redistributes their weights. With no local source (`analysisConfidence` `metadata-only` or `remote-only`, States 3 and 4) it skips both categories at any tier, as it does at Quick tier, for `docsOnly` and for `state2`.

#### 3b. Run the Scoring Script

Pass the §3a JSON and the score files that exist: `--signatures` when coverage-check scored the signatures, `--coherence` in contextual mode, and `--surface` at State 2:

```bash
uv run {scoringScript} --json-input '<the §3a JSON>' --coverage "{run_dir}/coverage.json" [--signatures "{run_dir}/signatures.json"] [--coherence "{run_dir}/coherence.json"] --external "{run_dir}/external.json" [--surface "{run_dir}/surface.json"]
```

Where `{scoringScript}` is the path resolved from the frontmatter variable (relative to the skill root, i.e., the skf-test-skill/ directory).

Parse the JSON output. The script returns:
- `weights`: final redistributed weights per category
- `weightedScores`: weighted contribution per category
- `totalScore`: the overall completeness score
- `threshold`: the threshold used
- `result`: `"PASS"`, `"FAIL"`, or **`"INCONCLUSIVE"`** (the minimum-evidence floor)
- `activeCategories`: list of categories that were scored
- `skippedCategories`: list of categories that were skipped
- `skipReasons`: why each category was skipped
- `weightSum`: sum of final weights (should be ~100)
- `inconclusiveReasons`: only present when `result == "INCONCLUSIVE"`; explains which floor clause tripped
- `state2Deduction` and `scoringNotes`: present when the State 2 undercount deduction was weighed (`applied` says whether it lowered Export Coverage) and when a note applies
- **Verdict-override group**: present as an atomic set of four keys only when a post-score cap or the threshold fallback engaged (§3d/§4b are applied by the script, not re-derived here):
  - `effectiveResult`: the **final verdict** after caps + fallback (`"PASS"` / `"FAIL"`); read this as the outcome for §4 to §8
  - `capReason`: string describing the cap(s) that fired, or `null`
  - `thresholdFallback`: `true` when the FAIL→PASS-at-80-floor fallback fired
  - `originalThreshold`: the pre-fallback threshold when `thresholdFallback` is `true`, else `null`
  - When the group is **absent**, no cap or fallback engaged and `result` is the final verdict.

Use these values for Section 4 (pass/fail/inconclusive) and Section 6 (output formatting). **The script owns the minimum-evidence floor, the State 2 deduction, both post-score caps, and the threshold fallback: everywhere below, read its emitted fields (`result`, `effectiveResult`, `capReason`, `thresholdFallback`, `scoringNotes`) and never recompute a verdict, cap, deduction or threshold decision.** The final verdict is `effectiveResult` when the override group is present, otherwise `result` (INCONCLUSIVE is never overridden).

#### 3c. If the Script Refuses the Input or Does Not Run

A `{"error": ..., "code": "INVALID_INPUT"}` envelope on stdout (exit 2, or exit 1 for a payload that is not JSON) means the script ran and refused what it was given: a flag is missing, mistyped or out of range, or a score file is missing its score or holds a refused result. **Correct the §3a input, or re-run the step that writes the refused file, and run it again.** Never compute a total by hand from the numbers the script refused.

No envelope at all (the script file is missing, or it cannot start): HALT with its stderr. A quality gate does not score by hand, so the run stops without a score rather than with an unchecked one.

### 3d. Read Post-Score Caps (applied by the script)

The script settles the verdict in the one order its docstring states, with two post-score caps: **Cap 1** (any `toolingStatus` other than `ok`) and **Cap 2** (docs-only with no external validation score). It returns the settled outcome as `capReason` + `effectiveResult` (§3b). Read those fields; never recompute a cap. If `capReason` is non-null, record `scoring_notes: {capReason}` in the report. A fired cap forces the script's `PASS` into `FAIL`, never touches an INCONCLUSIVE verdict, and is never re-flipped by the threshold fallback (§4b): a capped run stays FAIL whatever the threshold. (Both caps exist because a degraded-tooling or docs-only-without-validators run has too thin an evidence base to trust a PASS; §3a passes the field Cap 1 reads.)

### 4. Determine Result (PASS / FAIL / INCONCLUSIVE)

The scoring script enforces the minimum-evidence floor BEFORE comparing score vs threshold, then applies the post-score caps (§3d) and threshold fallback (§4b). The **settled verdict** is `effectiveResult` when the override group is present, otherwise `result`:

```
IF result == "INCONCLUSIVE" — minimum-evidence floor tripped; not PASS, not FAIL (never overridden)
ELSE settled verdict = effectiveResult if the override group is present, else result   (PASS or FAIL)
```

**INCONCLUSIVE floor clauses** (the script's minimum-evidence floor):
- `active_categories < 2` (after all redistribution), OR
- `tier == "Quick"` AND Export Coverage is the sole scoring contributor

### 4b. Threshold Fallback and Evidence Report

After §4 determines the result but before §5 recommends the next workflow, the script's threshold fallback may already have converted a FAIL into a PASS at the 80% floor. This step documents that quality compromise in an evidence report.

Read the script's fields:

- `thresholdFallback == true` → the fallback fired; `effectiveResult` is `"PASS"` and `originalThreshold` holds the pre-fallback threshold.
- `thresholdFallback` absent or `false` → no fallback; the settled verdict from §4 stands.

**When `thresholdFallback` is true:**

1. Record `threshold_fallback: true`, `original_threshold: {originalThreshold}`, `fallback_threshold: 80` in workflow context.
2. Use `effectiveResult` (`"PASS"`) as the settled verdict — do not recompute it.
3. Set `effective_threshold = 80` for use by §5/§6/§7/§8.
4. Generate the evidence report (§4b.1 below).

The `{totalScore}` used in the report below is the script's raw `totalScore`.

#### 4b.1 Generate Evidence Report

Write the evidence report to `{forge_version}/evidence-report-fallback.md`. The report documents the quality compromise for audit purposes.

**Read the gaps from the gap ledger**, not from the report's sections: the stages recorded every gap they found in `{ledgerFile}`, and the hard gate passed, so none is Critical or High. The script orders and counts them (`{gapLedgerScript}` resolves relative to the skill root):

```bash
uv run {gapLedgerScript} render --ledger "{ledgerFile}"
```

Exit 0: write its output unchanged under **Findings Preventing Higher Threshold**: the totals, the Remediation Summary and one entry per gap, by severity. A render that exits 1 prints its error on stderr: write that line there instead and continue, since the evidence report does not decide the verdict.

**Check for prior remediation:** glob `{forge_version}/test-report-{skill_name}-*.md` for a prior test report. If found, note the path — this implies remediation was attempted between runs. If not found, note "first test run — no prior remediation cycle".

**Evidence report template:**

```markdown
# Evidence Report: Threshold Fallback

**Skill:** {skill_name}
**Date:** {ISO-8601 timestamp}
**Run ID:** {run_id}

## Threshold Summary

| Field | Value |
|-------|-------|
| Attempted Threshold | {original_threshold}% |
| Achieved Score | {totalScore}% |
| Threshold Source | {threshold_source} |
| Final Accepted Threshold | 80% |

## Findings Preventing Higher Threshold

{the output of the render command above, unchanged}

## Remediation Context

{If prior test report exists:}
A prior test run was found at `{prior_report_path}`, indicating remediation was attempted between runs.

{If no prior test report:}
No prior test report found for this skill version — this is the first test run.

## Conclusion

Skill accepted at 80% floor (original target: {original_threshold}%). The findings above prevented meeting the higher threshold. Review and address findings before the next pipeline run to achieve the {original_threshold}% target.
```

Record `evidence_report_path: '{forge_version}/evidence-report-fallback.md'` in workflow context for use by §6/§7/§8 and by report.md.

### 5. Determine Next Workflow Recommendation

Based on the **settled verdict** (§4 — `effectiveResult` when the override group is present, else `result`; INCONCLUSIVE is never overridden):

**IF PASS:**
- `nextWorkflow: 'export-skill'` — skill is ready for export
- **Drift override:** if workflow context carries
  `allow_workspace_drift: true` (set in step 1 §5b when the user passed
  `--allow-workspace-drift` AND the workspace HEAD did not match
  `metadata.source_commit`), the PASS is a **conditional PASS**:
  - Write `testResult: 'pass-with-drift'` to the output frontmatter instead of
    bare `'pass'`. The result contract (§4c of step 6) mirrors the same
    value.
  - Override `nextWorkflow` to `'update-skill'` — **refuse to recommend
    `export-skill`**. The drift override weakens the workflow's strongest
    false-positive guard (we tested against HEAD, not the pinned source); a
    PASS under drift is not trustworthy enough to promote to export without a
    clean re-test against the pinned commit.
  - Record `scoring_notes: workspace drift overridden — PASS is conditional; re-run against pinned commit before export`.

**IF FAIL:**
- `nextWorkflow: 'update-skill'` — skill needs remediation before export

**IF INCONCLUSIVE:**
- `nextWorkflow: 'manual-review'` — evidence base is insufficient to grade the skill automatically. The test report records `inconclusiveReasons` from the scoring script. Surface to the user — do not auto-recommend export or update.

### 6. Write the Completeness Score Section

Write the **Completeness Score** section in place of the template's `## Completeness Score` heading and the placeholder comment under it, in `{outputFile}`:

```markdown
## Completeness Score

### Score Breakdown

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Export Coverage | {N}% | {W}% | {WS}% |
| Signature Accuracy | {N}% | {W}% | {WS}% |
| Type Coverage | {N}% | {W}% | {WS}% |
| Coherence | {N}% | {W}% | {WS}% |
| External Validation | {N}% | {W}% | {WS}% |
| **Total** | | **100%** | **{total}%** |

### Result

**Score:** {total}%
**Threshold:** {threshold}%
**Result:** **{PASS|FAIL|INCONCLUSIVE}**
{If INCONCLUSIVE:}
**Inconclusive Reasons:**
{bulleted list from script `inconclusiveReasons`}

**Threshold Source:** {threshold_source}
{If threshold_fallback is true:}
**Threshold Fallback:** scored {totalScore}% against {original_threshold}% target — accepted at 80% floor. Evidence report: {evidence_report_path}
**Weight Distribution:** {naive (redistributed) | contextual (full)}
**Tier Adjustment:** {none | Quick tier — signature and type coverage not scored}
**External Validators:** {skill-check and Tessl Review | skill-check only | Tessl Review only | none — weight redistributed} (from `{external_tools_used}`; `tessl` is Tessl Review)
**Analysis Confidence:** {full | provenance-map | metadata-only | remote-only | docs-only}
**Tooling Status:** {ok | frontmatter-validator-timeout}
{If the script returned `scoringNotes` or a `capReason`:}
**Scoring Notes:** {each entry of `scoringNotes`, and `capReason`}
```

If `analysis_confidence` is not `full`, add a degradation notice at the end of the Completeness Score section. **The notice must be confidence-aware** (see the degradation notice rules in `{sourceAccessProtocol}`):

```markdown
### Access Degradation Notice

**Resolved via:** {analysis_confidence} {confidence breakdown if provenance-map, e.g., "(T1 AST-verified at compilation time)" or "(12 T1, 3 T1-low)"}
**Impact:** {describe limitation — e.g., "Signature checks limited to name-matching. Source file:line citations from provenance-map, not live AST." — or "Provenance data is at highest confidence; no limitation." for all-T1 provenance-map}
**Recommendation:** {confidence-dependent — see {sourceAccessProtocol} degradation notice rules. Do not recommend local clone when provenance-map entries are already T1.}
```

### 7. Update Output Frontmatter

Update `{outputFile}` frontmatter:
- `testResult: '{pass|pass-with-drift|fail|inconclusive}'` (lowercase; mirrors the **settled verdict** — `effectiveResult` when the override group is present, else `result` — with `pass-with-drift` substituted for `pass` when `allow_workspace_drift` was set and drift was observed — see §5 drift override)
- `score: '{total}%'`
- `threshold: '{threshold}%'`
- `thresholdSource: '{threshold_source}'`
- When `threshold_fallback` is true, add: `thresholdFallback: true`, `originalThreshold: '{original_threshold}%'`, `evidenceReportPath: '{evidence_report_path}'`
- `analysisConfidence: '{full|provenance-map|metadata-only|remote-only|docs-only}'`
- `toolingStatus: '{ok|frontmatter-validator-timeout}'`
- `nextWorkflow: '{export-skill|update-skill|manual-review}'`
- Append `'score'` to `stepsCompleted`

### 8. Report Score

Report the completeness score to the user: the total percentage and PASS/FAIL verdict, the per-category weighted breakdown (already appended to the report in §6), the threshold, and the recommended next workflow (export-skill on pass, update-skill on fail). When `threshold_fallback` is true, include the fallback notice:

**Threshold fallback:** scored {totalScore}% against {original_threshold}% target — accepted at 80% floor. Evidence report: {evidence_report_path}

Then proceed to the gap report.

`stepsCompleted` now ends with `'score'` (§7 appended it), so load and execute {nextStepFile}.

