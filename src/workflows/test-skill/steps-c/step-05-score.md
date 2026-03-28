---
name: 'step-05-score'
description: 'Calculate completeness score from coverage and coherence findings'

nextStepFile: './step-06-report.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
scoringRulesFile: '../data/scoring-rules.md'
sourceAccessProtocol: '../data/source-access-protocol.md'
---

# Step 5: Score

## STEP GOAL:

Calculate the overall completeness score by aggregating coverage, coherence, and external validation category scores with the appropriate weight distribution (naive or contextual), apply the pass/fail threshold, and determine the test result.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER invent scores — all values must derive from step 03 and step 04 findings
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor in Ferris's Audit mode — zero hallucination
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Scoring is mechanical — apply the formula, report the math
- ✅ Do not editorialize on the score — facts and numbers only

### Step-Specific Rules:

- 🎯 Focus only on score calculation — do NOT generate remediation suggestions (that's step 06)
- 🚫 FORBIDDEN to adjust scores subjectively — the formula determines the result
- 💬 Show the math: category scores, weights, weighted contributions, total
- 📋 Score must be reproducible — same inputs always produce same output

## EXECUTION PROTOCOLS:

- 🎯 Load scoring rules and read findings from {outputFile}
- 💾 Append Completeness Score section to {outputFile}
- 📖 Update {outputFile} frontmatter with testResult, score, and stepsCompleted
- 🚫 FORBIDDEN to proceed without setting testResult to pass or fail

## CONTEXT BOUNDARIES:

- Available: Coverage Analysis (step 03), Coherence Analysis (step 04), and External Validation (step 04b) in {outputFile}
- Focus: Score calculation and pass/fail determination only
- Limits: Do NOT generate gap remediation — that's step 06
- Dependencies: steps 03, 04, and 04b must have appended their analysis sections

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

Apply the weight distribution from `{scoringRulesFile}` for the detected mode (naive or contextual). The scoring rules define category weights, external validation redistribution when unavailable, and Quick tier adjustments. Calculate the weighted score for each category and sum for the total.

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All category scores read from previous steps (not invented)
- Correct weight distribution applied (naive vs contextual)
- Tier adjustment applied if Quick tier
- Score calculated with visible math (show the formula)
- Pass/fail determined against threshold
- Completeness Score section appended to output
- Frontmatter updated with testResult, score, threshold, nextWorkflow
- Auto-proceeded to step 06

### ❌ SYSTEM FAILURE:

- Inventing category scores not calculated in steps 03/04
- Using wrong weight distribution for the detected mode
- Not showing the math (score must be reproducible)
- Subjectively adjusting the score
- Not setting testResult in frontmatter
- Generating remediation suggestions (that's step 06)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. Scoring is mechanical — apply the formula, report the math.
