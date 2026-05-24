---
nextStepFile: 'report.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
scoringScript: 'scripts/compute-score.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Score

## STEP GOAL:

Calculate the overall completeness score by aggregating coverage, coherence, and external validation category scores with the appropriate weight distribution (naive or contextual), apply the pass/fail threshold, and determine the test result.

### 1. Load Scoring Rules

Load `{scoringRulesFile}` to get:
- Category weights (naive vs contextual distribution)
- Tier-dependent scoring adjustments

**Resolve the pass threshold (precedence: CLI > scalar > bundled fallback):**

1. If the workflow received `--threshold=<N>` on invocation, use that integer as `effective_threshold` (CLI wins).
2. Else if the resolved `{defaultThreshold}` workflow-context variable (from SKILL.md On Activation §3 — `workflow.default_threshold` scalar, default `80`) is set, use it as `effective_threshold`.
3. Else fall back to `80` (the bundled default — this branch should be unreachable when SKILL.md resolution ran correctly, but keeps the step robust if customize.toml resolution failed silently).

Pass `effective_threshold` into the scoring-input JSON's `threshold` field in §3a (the compute-score.py script already honors this field). The CLI flag and the scalar feed the same downstream field; the script does not need to know which layer supplied the value.

**Docs-only mode check:** If the Coverage Analysis section in `{outputFile}` notes docs-only mode (set by step 3 for skills with all `[EXT:...]` citations and no local source), apply Quick-tier weight redistribution: Signature Accuracy and Type Coverage are not scored, their weights (22% + 14%) are redistributed proportionally to remaining active categories. Coverage score is based on documentation completeness rather than source coverage (as calculated by step 3).

### 2. Read Category Scores from Output

Read `{outputFile}` and extract the category scores calculated in previous steps:

**From Coverage Analysis (step 03):**
- Export Coverage: {percentage}%
- Signature Accuracy: {percentage}% or N/A (Quick tier)
- Type Coverage: {percentage}% or N/A (Quick tier)

**From Coherence Analysis (step 04):**
- Combined Coherence: {percentage}% (contextual mode only)
- Or: not scored (naive mode — weight redistributed)

**From External Validation (step 04b):**
- External Validation Score: {percentage}% (combined skill-check + tessl average)
- Or: N/A (if neither tool was available — weight redistributed to other categories)

### 3. Apply Weight Distribution

**Read testMode from {outputFile} frontmatter.**

#### 2b. Apply State 2 Undercount Deduction (pre-script)

If `analysis_confidence == 'provenance-map'` (State 2) AND `metadata.json.skill_type != "stack"` AND step 3 recorded a provenance vs metadata divergence > 5% (see §4b in step 3), apply a 10-point deduction to `exportCoverage` BEFORE building the scoring input:

```
exportCoverage_adjusted = max(0, exportCoverage - 10)
```

Record in the report: `scoring_notes: State 2 undercount risk acknowledged — 10% deduction applied to Export Coverage (raw: {N}%, adjusted: {M}%)`. Use the adjusted value as the `exportCoverage` field in §3a below. The deduction is deterministic and does not change category weights or active-category counting.

Stack skills are exempt (the `metadata.json.skill_type != "stack"` guard above; `skill_type` is loaded in step 01 and also surfaces as `stackSkill` in §3a): a stack's own barrel is empty by design, so a provenance-vs-metadata divergence on a stack reflects the barrel-vs-constituent surface difference (suppressed by §4b's stack-skill branch in step 3), not extraction undercount — deducting for it would penalize a correctly built stack.

#### 3a. Construct Scoring Input JSON

Build a JSON object from the data gathered in steps 1-2:

```json
{
  "mode": "{testMode: contextual or naive}",
  "tier": "{forge_tier: Quick, Forge, Forge+, or Deep}",
  "docsOnly": "{true if docs_only_mode detected in step 03, else false}",
  "state2": "{true if analysis_confidence is provenance-map, else false}",
  "stackSkill": "{true if metadata.json.skill_type == 'stack', else false}",
  "referenceApp": "{true if metadata.json.scope_type == 'reference-app', else false}",
  "scores": {
    "exportCoverage": "{export_coverage_percentage}",
    "signatureAccuracy": "{signature_accuracy_percentage or null if N/A}",
    "typeCoverage": "{type_coverage_percentage or null if N/A}",
    "coherence": "{combined_coherence_percentage or null if naive mode}",
    "externalValidation": "{external_validation_score or null if N/A}"
  },
  "threshold": "{effective_threshold from §1 — CLI --threshold wins, then workflow.default_threshold scalar, then 80}"
}
```

**Important:** Score values must be numbers (not strings). Use `null` (not `"N/A"`) for categories that were not scored. Read `metadata.json.skill_type` from `{resolved_skill_package}/metadata.json`; if the value is `"stack"`, set `stackSkill: true` and pass `null` for `signatureAccuracy` and `typeCoverage` (the categories will be redistributed per `{scoringRulesFile}` Stack Skills rule). Likewise read `metadata.json.scope_type`; if the value is `"reference-app"`, set `referenceApp: true` and pass `null` for `signatureAccuracy` and `typeCoverage` (redistributed per `{scoringRulesFile}` Reference-App rule — a reference app documents wiring patterns, not library export signatures).

#### 3b. Run the Scoring Script

```bash
echo '<JSON>' | uv run {scoringScript} --stdin
```

Where `{scoringScript}` is the path resolved from the frontmatter variable (relative to the skill root, i.e., the skf-test-skill/ directory). The script also accepts the JSON as a positional argument (`uv run {scoringScript} '<JSON>'`) or via `--json-input '<JSON>'`; `--stdin` is preferred since it avoids shell-quote escaping of nested JSON.

Parse the JSON output. The script returns:
- `weights` — final redistributed weights per category
- `weightedScores` — weighted contribution per category
- `totalScore` — the overall completeness score
- `threshold` — the threshold used
- `result` — `"PASS"`, `"FAIL"`, or **`"INCONCLUSIVE"`** (minimum-evidence floor — see `{scoringRulesFile}`)
- `activeCategories` — list of categories that were scored
- `skippedCategories` — list of categories that were skipped
- `skipReasons` — why each category was skipped
- `weightSum` — sum of final weights (should be ~100)
- `inconclusiveReasons` — only present when `result == "INCONCLUSIVE"`; explains which floor clause tripped

Use these values for Section 4 (pass/fail/inconclusive) and Section 6 (output formatting). **Never override the script's `result` value** — floor enforcement is centralized in the script for determinism.

#### 3c. Fallback (if script execution fails)

If the script is unavailable or returns an error, fall back to manual calculation:

1. Select the weight table from `{scoringRulesFile}` for the detected mode (naive or contextual)
2. Determine skip conditions: Quick tier/docsOnly/state2/stackSkill/referenceApp skip Signature Accuracy + Type Coverage; naive mode coherence is already 0; null external validation means skip it
3. For each skipped category, set its weight to 0
4. Compute sum of active category weights
5. For each active category: `new_weight = old_weight / sum_active * 100`
6. `weighted_score = new_weight / 100 * category_score`
7. `total = sum of all weighted_scores`

Report: "**Note:** Scoring script unavailable — calculated manually per scoring-rules.md."

### 3d. Apply Post-Score Caps (BEFORE PASS/FAIL determination)

The scoring script returns `totalScore` and a preliminary `result`. Two caps may override the script's PASS into FAIL — applied in this order, and ONLY if the script did NOT return INCONCLUSIVE (floor always takes precedence):

**Cap 1 — Tooling degraded:** if `analysisConfidence == "degraded"` or `toolingStatus` indicates a missing helper (`python3-missing`, `frontmatter-validator-missing`), set `effective_score = min(totalScore, threshold - 1)` and record `scoring_notes: tooling degraded — capped below threshold until helper restored`.

**Cap 2 — Docs-only without external validators:** if `docsOnly == true` AND `externalValidation` score was null (neither skill-check nor tessl ran), set `effective_score = min(effective_score, threshold - 1)` and record `scoring_notes: docs-only without external validators — capped below threshold`.

If either cap fired and `result` was `PASS`, change it to `FAIL`. If `result` was already `INCONCLUSIVE`, leave it — the evidence-floor verdict is never overridden by a cap.

### 4. Determine Result (PASS / FAIL / INCONCLUSIVE)

The scoring script enforces the minimum-evidence floor BEFORE comparing score vs threshold. Three possible outcomes:

```
IF result == "INCONCLUSIVE" — minimum-evidence floor tripped; not PASS, not FAIL
IF score >= threshold       → PASS
IF score < threshold        → FAIL
```

**INCONCLUSIVE floor clauses** (see `{scoringRulesFile}`):
- `active_categories < 2` (after all redistribution), OR
- `tier == "Quick"` AND Export Coverage is the sole scoring contributor

**Tooling-degraded cap:** If the `analysisConfidence` in output frontmatter is `degraded` (python3 missing, frontmatter validator missing, or other degraded state flagged in step 1), the step MUST cap the score at `threshold - 1` BEFORE the PASS/FAIL comparison. This forces a deterministic FAIL until tooling is restored. Do NOT override an INCONCLUSIVE result with the cap — INCONCLUSIVE remains the verdict.

### 5. Determine Next Workflow Recommendation

Based on test result:

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

### 6. Append Completeness Score to Output

Append the **Completeness Score** section to `{outputFile}`:

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

**Weight Distribution:** {naive (redistributed) | contextual (full)}
**Tier Adjustment:** {none | Quick tier — signature and type coverage not scored}
**External Validators:** {both available | skill-check only | tessl only | none — weight redistributed}
**Analysis Confidence:** {full | provenance-map | metadata-only | remote-only | docs-only}
```

If `analysis_confidence` is not `full`, append a degradation notice. **The notice must be confidence-aware** — see the degradation notice rules in `{sourceAccessProtocol}`:

```markdown
### Access Degradation Notice

**Resolved via:** {analysis_confidence} {confidence breakdown if provenance-map, e.g., "(T1 AST-verified at compilation time)" or "(12 T1, 3 T1-low)"}
**Impact:** {describe limitation — e.g., "Signature checks limited to name-matching. Source file:line citations from provenance-map, not live AST." — or "Provenance data is at highest confidence; no limitation." for all-T1 provenance-map}
**Recommendation:** {confidence-dependent — see {sourceAccessProtocol} degradation notice rules. Do NOT recommend local clone when provenance-map entries are already T1.}
```

### 7. Update Output Frontmatter

Update `{outputFile}` frontmatter:
- `testResult: '{pass|pass-with-drift|fail|inconclusive}'` (lowercase; mirrors script `result`, with `pass-with-drift` substituted for `pass` when `allow_workspace_drift` was set and drift was observed — see §5 drift override)
- `score: '{total}%'`
- `threshold: '{threshold}%'`
- `analysisConfidence: '{full|degraded|provenance-map|metadata-only|remote-only|docs-only}'`
- `nextWorkflow: '{export-skill|update-skill|manual-review}'`
- Append `'score'` to `stepsCompleted`

### 8. Report Score

"**Completeness score calculated.**

**{skill_name}:** **{total}%** — **{PASS|FAIL}**

| Category | Score | Weighted |
|----------|-------|----------|
| Export Coverage | {N}% | {WS}% |
| Signature Accuracy | {N}% | {WS}% |
| Type Coverage | {N}% | {WS}% |
| Coherence | {N}% | {WS}% |
| External Validation | {N}% | {WS}% |

**Threshold:** {threshold}%
**Recommendation:** {export-skill if pass | update-skill if fail}

**Proceeding to gap report...**"

Update stepsCompleted, then load and execute {nextStepFile}.

