---
name: 'step-06-report'
description: 'Generate gap report with remediation suggestions and finalize test report'

outputFile: '{output_folder}/test-report-{skill_name}.md'
scoringRulesFile: '../data/scoring-rules.md'
outputFormatsFile: '../data/output-section-formats.md'
---

# Step 6: Gap Report

## STEP GOAL:

Generate a detailed gap report listing every issue found during coverage and coherence analysis, assign severity to each gap, provide specific actionable remediation suggestions, and finalize the test report document. This is the final step — no next step file.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER fabricate gaps — every item must trace to findings from steps 03 and 04
- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor in Ferris's Audit mode — zero hallucination
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Remediation suggestions must be specific and actionable — not vague advice
- ✅ Each gap tells the user exactly what to fix, where, and how

### Step-Specific Rules:

- 🎯 Focus on gap enumeration, severity classification, and remediation
- 🚫 FORBIDDEN to recalculate scores — use the score from step 05
- 💬 Remediation suggestions reference specific files, exports, and line numbers
- 📋 Gaps are ordered by severity (Critical → High → Medium → Low → Info)

## EXECUTION PROTOCOLS:

- 🎯 Read all findings from {outputFile} coverage and coherence sections
- 💾 Append Gap Report section to {outputFile}
- 📖 Update {outputFile} frontmatter: mark stepsCompleted with all steps, finalize document
- 🚫 This is the final step — no next step to load

## CONTEXT BOUNDARIES:

- Available: Complete {outputFile} with Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score
- Focus: Gap enumeration and remediation only
- Limits: Do NOT re-analyze source code — work from existing findings
- Dependencies: steps 03, 04, and 05 must have completed their sections

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

### 2. Load Severity Rules

Load `{scoringRulesFile}` for gap severity classification:

| Severity | Criteria |
|----------|----------|
| **Critical** | Missing exported function/class documentation |
| **High** | Signature mismatch between source and SKILL.md |
| **Medium** | Missing type or interface documentation |
| **Medium** | Migration section present/absent mismatch with T2-future annotation data (Deep tier) |
| **Low** | Missing optional metadata or examples |
| **Info** | Style suggestions, non-blocking observations |

### 3. Classify and Order Gaps

Load `{outputFormatsFile}` for gap entry format and remediation quality rules.

For each issue, assign severity from `{scoringRulesFile}` and generate a specific remediation following the quality rules in `{outputFormatsFile}`. Order gaps by severity: Critical → High → Medium → Low → Info.

### 4. Generate Remediation Summary and Append Gap Report

Load the Gap Report section format from `{outputFormatsFile}`. Count gaps by severity, estimate effort per the guidelines in `{outputFormatsFile}`, and append the complete **Gap Report** section to `{outputFile}`.

If no gaps found, append a clean pass message recommending **export-skill** workflow.

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

**Test report finalized.**"

### 7. Present MENU OPTIONS

Display: "**Test complete.** [C] Finish"

#### Menu Handling Logic:

- IF C: Workflow is complete. No further steps to load.
- IF Any other: help user respond, then redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- This is the final step — C ends the workflow
- User may ask questions about the report before finishing

## CRITICAL STEP COMPLETION NOTE

This is the final step of the test-skill workflow. When the user selects C, the workflow is complete. The test report document at `{outputFile}` contains the full analysis: Test Summary, Coverage Analysis, Coherence Analysis, Completeness Score, and Gap Report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every gap traces to a finding from steps 03 or 04 (zero fabrication)
- Gaps classified by severity using scoring rules
- Gaps ordered by severity (Critical first)
- Every gap has a specific, actionable remediation suggestion
- Remediation summary with counts and effort estimates
- Output document finalized with all stepsCompleted
- Correct next workflow recommended (export-skill or update-skill)
- Report presented clearly to user

### ❌ SYSTEM FAILURE:

- Fabricating gaps not found in analysis steps
- Vague remediation suggestions ("fix the issue", "add documentation")
- Not classifying severity
- Recalculating or modifying the score from step 05
- Not finalizing the output document frontmatter
- Missing the next workflow recommendation

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. Every gap is specific, every remediation is actionable.
