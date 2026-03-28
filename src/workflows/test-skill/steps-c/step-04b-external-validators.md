---
name: 'step-04b-external-validators'
description: 'Run external validation tools (skill-check, tessl) and capture scores for scoring step'

nextStepFile: './step-05-score.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
---

# Step 4b: External Validators

## STEP GOAL:

Run external validation tools (`skill-check` and `tessl`) against the skill directory, capture their scores and findings, and append results to the test report. These tools catch complementary issues that internal coverage and coherence checks miss: `skill-check` validates spec compliance while `tessl` evaluates content quality and actionability.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor running external quality gates
- ✅ Both tools are optional — unavailability is a skip, never a halt
- ✅ Report scores factually — do not editorialize on the results

### Step-Specific Rules:

- 🎯 Run each tool independently — one tool's failure does not affect the other
- 🚫 FORBIDDEN to halt the workflow if either tool is unavailable or fails
- 🚫 FORBIDDEN to modify skill content — this step only measures and reports
- ⚠️ Ignore non-zero exit codes if the tool produces parseable output

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Append External Validation section to {outputFile}
- 📖 Update stepsCompleted in {outputFile}
- 📖 Store scores in context for step-05 scoring

## CONTEXT BOUNDARIES:

- Available: skill directory path, testMode, forge tier from previous steps
- Focus: External tool execution and score capture only
- Limits: Do NOT modify skill content or recalculate internal scores
- Dependencies: steps 03 and 04 must have completed

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Resolve Skill Directory

Read {outputFile} frontmatter to get the skill directory path (`skillDir`).

### 1b. Check for Recent Validation Results (Auto-Reuse)

Before running external validators, check if `{forge_data_folder}/{skill_name}/evidence-report.md` contains validation results (a `## Validation Results` section with quality scores).

**Staleness check:** Determine whether SKILL.md has changed since the evidence report was generated.

**Primary (git-tracked):** Run `git log -1 --format=%cI -- {skillDir}/SKILL.md` to get the last commit date of SKILL.md. Compare against the evidence report's generation date (from its frontmatter or the `## Validation Results` timestamp). If SKILL.md's last commit is newer, results are stale.

**Secondary (uncommitted changes):** Run `git diff --name-only -- {skillDir}/SKILL.md`. If output is non-empty, SKILL.md has uncommitted changes — treat results as stale regardless of commit dates.

**Fallback (non-git environments):** If git commands fail (not a git repository), fall back to `metadata.json` `generation_date` comparison with a warning: "Staleness check using metadata.json — may be identical to evidence report timestamp. Consider a git-tracked directory for reliable staleness detection."

If SKILL.md was modified after the evidence report was generated (e.g., after update-skill), the cached results are stale — skip auto-reuse and proceed to section 2 for a fresh run.

If recent, non-stale results exist (from a create-skill run that just completed), auto-reuse them — skip re-running validators and use the existing scores. Record: "External validation: reused from create-skill evidence report." Skip to section 5 (append results).

If no evidence report exists, it contains no validation section, or results are stale, proceed to section 2 (fresh run).

### 2. Run skill-check

**Check availability:**

```bash
npx skill-check -h
```

If unavailable, record `skill_check_score: N/A` and skip to section 3.

**Run validation:**

```bash
npx skill-check check {skillDir} --format json --no-security-scan
```

**Parse JSON output** to extract:
- `qualityScore` — overall score (0-100)
- `diagnostics[]` — any remaining issues
- `errorCount` and `warningCount`

**Note:** `skill-check` may return a non-zero exit code even when `errorCount` is 0. Always rely on the parsed JSON output, not the shell exit code.

Store in context: `skill_check_score`, `skill_check_diagnostics`

**If skill-check fails entirely:** Record `skill_check_score: N/A`, log warning, continue.

### 3. Run tessl

**Check availability:**

```bash
npx -y tessl --version
```

If unavailable, record `tessl_score: N/A` and skip to section 4.

**Run review:**

```bash
npx -y tessl skill review {skillDir}
```

**Parse the output** to extract:
- `description_score` — percentage (e.g., 100%)
- `content_score` — percentage (e.g., 45%)
- `average_score` — percentage (e.g., 73%)
- `validation_result` — PASSED/FAILED
- `judge_suggestions[]` — list of improvement suggestions

The tessl output is human-readable text, not JSON. Parse the percentage values from lines like "Description: 100%", "Content: 45%", "Average Score: 73%".

Store in context: `tessl_description_score`, `tessl_content_score`, `tessl_average_score`, `tessl_suggestions`

**If tessl content score < 70%:** Flag a warning:

"**Content quality warning:** tessl scored content at {score}%. This often indicates SKILL.md lacks inline actionable content (e.g., after split-body). If this is a split-body skill, the score drop is expected — tessl evaluates only SKILL.md body, not `references/*.md` (see scoring-rules.md). Consider using selective split to keep actionable content inline."

**If tessl fails entirely:** Record `tessl_score: N/A`, log warning, continue.

### 4. Calculate Combined External Score

**If both tools ran:**

```
external_score = (skill_check_score + tessl_average_score) / 2
```

Note: `skill_check_score` is 0-100, `tessl_average_score` is 0-100%. Both are on the same scale.

**If only one tool ran:** Use that tool's score as the external score.

**If neither tool ran:** Record `external_score: N/A`. The scoring step will redistribute the external validation weight.

### 5. Append External Validation to Output

Append to `{outputFile}`:

```markdown
## External Validation

### skill-check
- **Available:** {yes/no}
- **Quality Score:** {score}/100
- **Errors:** {count}
- **Warnings:** {count}
- **Diagnostics:** {list or "none"}

### tessl
- **Available:** {yes/no}
- **Validation:** {PASSED/FAILED}
- **Description Score:** {score}%
- **Content Score:** {score}%
- **Average Score:** {score}%
- **Suggestions:**
{bulleted list of judge suggestions}

### Combined External Score
- **External Validation Score:** {external_score}%
- **Tools used:** {list of tools that ran}
```

### 6. Report Results

"**External validation complete.**

| Tool | Score | Status |
|------|-------|--------|
| skill-check | {score}/100 | {available/skipped} |
| tessl | {average}% | {available/skipped} |
| **Combined** | **{external_score}%** | |

{content quality warning if tessl content < 70%}

**Proceeding to scoring...**"

### 7. Auto-Proceed

#### Menu Handling Logic:

- After external validation is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed validation step with no user choices
- Tool unavailability is a skip, not a halt
- Proceed directly to next step after external validation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN external validation results are appended to {outputFile} and scores are stored in context will you proceed to load `{nextStepFile}` for scoring.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- skill-check executed and quality score captured (or skipped with N/A if unavailable)
- tessl executed and description/content/average scores captured (or skipped with N/A)
- Content quality warning raised if tessl content < 70%
- Combined external score calculated
- External Validation section appended to output
- Scores stored in context for step-05
- Auto-proceeded to step-05

### ❌ SYSTEM FAILURE:

- Halting the workflow because a tool is unavailable or fails
- Not recording N/A when a tool is skipped (step-05 needs to know)
- Modifying skill content based on validation results
- Not parsing tessl content score (the key insight this tool provides)
- Fabricating scores not from actual tool output

**Master Rule:** External validators inform — they do not block. Run what's available, capture the scores, report factually, and proceed.
