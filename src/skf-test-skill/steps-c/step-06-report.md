---
# nextStepFile `shared/health-check.md` resolves relative to the SKF module
# root (`_bmad/skf/` when installed, `src/` during development), NOT relative
# to this step file.
nextStepFile: 'shared/health-check.md'

outputFile: '{forge_version}/test-report-{skill_name}.md'
scoringRulesFile: 'references/scoring-rules.md'
outputFormatsFile: 'assets/output-section-formats.md'
# outputContractSchema `shared/references/output-contract-schema.md` resolves
# relative to the SKF module root (`_bmad/skf/` when installed, `src/` during
# development), NOT relative to this step file.
outputContractSchema: 'shared/references/output-contract-schema.md'
---

# Step 6: Gap Report

## STEP GOAL:

Generate a detailed gap report listing every issue found during coverage and coherence analysis, assign severity to each gap, provide specific actionable remediation suggestions, and finalize the test report document. This is the final step — no next step file.

## Rules

- Focus on gap enumeration, severity classification, and remediation — do not recalculate scores
- Remediation suggestions reference specific files, exports, and line numbers
- Gaps are ordered by severity (Critical > High > Medium > Low > Info)
- Chains to shared health check via `{nextStepFile}` after completion

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

### 4b. Discovery and Description Quality Recommendations

After gap enumeration, append a **Discovery Quality** subsection to the gap report. Use the `Gap Entry Format` from `{outputFormatsFile}` for any Low/Info entries. The prose recommendations below are appended after the gap entries:

**Description optimization:** If tessl `description_score` (from step 04b) is below 90%, or if skill-check flagged description issues, recommend description improvements:
- Check that the description uses third-person voice consistently
- Check for specific trigger keywords that match how users would phrase requests
- Check for negative triggers ("NOT for: ...") to prevent false matches
- Check for alternative skill references for excluded use cases

**Discovery testing recommendation:** Regardless of pass/fail, always append:

"**Discovery testing recommended.** Before export, test the skill with 3-5 realistic prompts phrased the way real users actually talk — with casual language, typos, incomplete context, and implicit references. A skill tested only with clean prompts may fail to trigger in production. Example realistic prompt patterns:
- Vague: 'can you help me with this csv file my boss sent'
- Implicit: 'why did revenue drop last quarter'
- Abbreviated: 'run the {skill-name} thing on this data'"

Record discovery testing status as Info-level in the gap table. This is advisory — it does not affect the score.

### 4c. Result Contract

Write `{forge_version}/skf-test-skill-result.json` per `{outputContractSchema}`. Include the test report path in `outputs`; include `score`, `threshold`, `result` (PASS/FAIL), and `testMode` (naive/contextual) in `summary`.

### 5. Finalize Output Document

Update `{outputFile}` frontmatter:
- Set `stepsCompleted` to `['step-01-init', 'step-02-detect-mode', 'step-03-coverage-check', 'step-04-coherence-check', 'step-04b-external-validators', 'step-05-score', 'step-06-report']`

### 6. Present Final Report

"**Test complete for {skill_name}.**

---

**Result:** **{PASS|FAIL}** — **{score}%** (threshold: {threshold}%)

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

{IF FAIL:}
**update-skill** — This skill needs remediation. Review the gap report above and run the update-skill workflow to address the {N} blocking issues (Critical + High).

---

**See Discovery Quality section in the report for description optimization and realistic prompt testing recommendations.**

**Test report finalized.**"

### 7. Present MENU OPTIONS

Display: "**Test complete.** [C] Finish"

#### Menu Handling Logic:

- IF C: Load and execute `{nextStepFile}` for workflow self-improvement check.
- IF Any other: help user respond, then redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past report menu"
- C triggers the health check, which is the true workflow exit
- User may ask questions about the report before finishing

## CRITICAL STEP COMPLETION NOTE

When the user selects C, this step chains to the shared health check. After the health check completes, the test-skill workflow is fully done. The test report document at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report.

