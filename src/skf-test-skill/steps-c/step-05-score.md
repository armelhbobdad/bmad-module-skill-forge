---
nextStepFile: './step-06-report.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
scoringScript: 'scripts/compute-score.py'
---

# Step 5: Score

## STEP GOAL:

Calculate the overall completeness score by aggregating coverage, coherence, and external validation category scores with the appropriate weight distribution (naive or contextual), apply the pass/fail threshold, and determine the test result.

## Rules

- Focus only on score calculation — do not generate remediation suggestions (Step 06)
- Score must be deterministic — same inputs always produce same output
- Show the math: category scores, weights, weighted contributions, total

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Scoring Rules

Load `{scoringRulesFile}` to get:
- Category weights (naive vs contextual distribution)
- Default threshold (80%)
- Tier-dependent scoring adjustments
- Any custom threshold override from workflow input

**Docs-only mode check:** If the Coverage Analysis section in `{outputFile}` notes docs-only mode (set by step-03 for skills with all `[EXT:...]` citations and no local source), apply Quick-tier weight redistribution: Signature Accuracy and Type Coverage are not scored, their weights (22% + 14%) are redistributed proportionally to remaining active categories. Coverage score is based on documentation completeness rather than source coverage (as calculated by step-03).

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

#### 3a. Construct Scoring Input JSON

Build a JSON object from the data gathered in steps 1-2:

```json
{
  "mode": "{testMode: contextual or naive}",
  "tier": "{forge_tier: Quick, Forge, Forge+, or Deep}",
  "docsOnly": "{true if docs_only_mode detected in step 03, else false}",
  "state2": "{true if analysis_confidence is provenance-map, else false}",
  "scores": {
    "exportCoverage": "{export_coverage_percentage}",
    "signatureAccuracy": "{signature_accuracy_percentage or null if N/A}",
    "typeCoverage": "{type_coverage_percentage or null if N/A}",
    "coherence": "{combined_coherence_percentage or null if naive mode}",
    "externalValidation": "{external_validation_score or null if N/A}"
  },
  "threshold": "{custom_threshold or omit for default 80}"
}
```

**Important:** Score values must be numbers (not strings). Use `null` (not `"N/A"`) for categories that were not scored.

#### 3b. Run the Scoring Script

```bash
python3 {scoringScript} '<JSON>'
```

Where `{scoringScript}` is the path resolved from the frontmatter variable (relative to the skill root, i.e., the skf-test-skill/ directory).

Parse the JSON output. The script returns:
- `weights` — final redistributed weights per category
- `weightedScores` — weighted contribution per category
- `totalScore` — the overall completeness score
- `threshold` — the threshold used
- `result` — `"PASS"` or `"FAIL"`
- `activeCategories` — list of categories that were scored
- `skippedCategories` — list of categories that were skipped
- `skipReasons` — why each category was skipped
- `weightSum` — sum of final weights (should be ~100)

Use these values for Section 4 (pass/fail) and Section 6 (output formatting).

#### 3c. Fallback (if script execution fails)

If the script is unavailable or returns an error, fall back to manual calculation:

1. Select the weight table from `{scoringRulesFile}` for the detected mode (naive or contextual)
2. Determine skip conditions: Quick tier/docsOnly/state2 skip Signature Accuracy + Type Coverage; naive mode coherence is already 0; null external validation means skip it
3. For each skipped category, set its weight to 0
4. Compute sum of active category weights
5. For each active category: `new_weight = old_weight / sum_active * 100`
6. `weighted_score = new_weight / 100 * category_score`
7. `total = sum of all weighted_scores`

Report: "**Note:** Scoring script unavailable — calculated manually per scoring-rules.md."

### 4. Determine Pass/Fail

```
threshold = custom_threshold OR default_threshold (80%)
score = sum of weighted category scores

IF score >= threshold → PASS
IF score < threshold → FAIL
```

### 5. Determine Next Workflow Recommendation

Based on test result:

**IF PASS:**
- `nextWorkflow: 'export-skill'` — skill is ready for export

**IF FAIL:**
- `nextWorkflow: 'update-skill'` — skill needs remediation before export

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
**Result:** **{PASS|FAIL}**

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
- `testResult: '{pass|fail}'`
- `score: '{total}%'`
- `threshold: '{threshold}%'`
- `analysisConfidence: '{analysis_confidence}'`
- `nextWorkflow: '{export-skill|update-skill}'`
- Append `'step-05-score'` to `stepsCompleted`

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

### 9. Auto-Proceed

Display: "**Proceeding to gap report...**"

#### Menu Handling Logic:

- After score is calculated and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed scoring step with no user choices
- Proceed directly to next step after score is determined

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the score is calculated, pass/fail is determined, the Completeness Score section is appended to {outputFile}, and frontmatter is updated with testResult and score, will you then load and read fully `{nextStepFile}` to execute gap report generation.

