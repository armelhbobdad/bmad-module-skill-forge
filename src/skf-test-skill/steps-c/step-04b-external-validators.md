---
nextStepFile: './step-05-score.md'
outputFile: '{forge_version}/test-report-{skill_name}.md'
---

# Step 4b: External Validators

## STEP GOAL:

Run external validation tools (`skill-check` and `tessl`) against the skill directory, capture their scores and findings, and append results to the test report. These tools catch complementary issues that internal coverage and coherence checks miss: `skill-check` validates spec compliance while `tessl` evaluates content quality and actionability.

## Rules

- Run each tool independently — one tool's failure does not affect the other
- Do not halt the workflow if either tool is unavailable or fails
- Read-only — do not modify skill content

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Resolve Skill Directory

Read {outputFile} frontmatter to get the skill directory path (`skillDir`).

### 1b. Check for Recent Validation Results (Auto-Reuse)

Before running external validators, check if `{forge_data_folder}/{skill_name}/evidence-report.md` contains validation results (a `## Validation Results` section with quality scores).

**Staleness check:** Determine whether SKILL.md has changed since the evidence report was generated. Walk through these checks in order:

**Pre-check (untracked or staged-only file):** Run `git ls-files --error-unmatch {skillDir}/SKILL.md 2>/dev/null`.
- If the command fails (exit code non-zero) or git is not available, the file is either **untracked** (new, never committed) or we're in a **non-git environment**:
  - Check if `{skillDir}/metadata.json` exists and has a `generation_date` field
  - Compare `metadata.json` `generation_date` against the evidence report's generation date (from its frontmatter or `## Validation Results` timestamp)
  - If timestamps match within the same minute (same workflow session): auto-reuse is safe — the evidence report was generated from the same SKILL.md content
  - If timestamps differ or metadata.json is missing: treat as stale, proceed to section 2 for a fresh run
  - Note: "Staleness check: SKILL.md is untracked/non-git — using metadata.json timestamp comparison."
- If the command succeeds (file is tracked by git), continue to Primary check below.

**Primary (git-tracked):** Run `git log -1 --format=%cI -- {skillDir}/SKILL.md` to get the last commit date of SKILL.md. Compare against the evidence report's generation date (from its frontmatter or the `## Validation Results` timestamp). If SKILL.md's last commit is newer, results are stale.

**Secondary (uncommitted changes):** Run `git diff --name-only -- {skillDir}/SKILL.md`. If output is non-empty, SKILL.md has uncommitted changes — treat results as stale regardless of commit dates. Also check `git diff --cached --name-only -- {skillDir}/SKILL.md` for staged-but-uncommitted changes — if non-empty, SKILL.md has been staged since last commit, treat results as stale.

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
- `review_score` — percentage (e.g., 73%)
- `validation_result` — PASSED/FAILED
- `judge_suggestions[]` — list of improvement suggestions

The tessl output is human-readable text, not JSON. Parse the percentage values from lines like "Description: 100%", "Content: 45%", "Review Score: 73%".

Store in context: `tessl_description_score`, `tessl_content_score`, `tessl_review_score`, `tessl_suggestions`

**If tessl content score < 70%:** Flag a warning:

"**Content quality warning:** tessl scored content at {score}%. This often indicates SKILL.md lacks inline actionable content (e.g., after split-body). If this is a split-body skill, the score drop is expected — tessl evaluates only SKILL.md body, not `references/*.md` (see scoring-rules.md). Consider using selective split to keep actionable content inline."

**If tessl fails entirely:** Record `tessl_score: N/A`, log warning, continue.

### 4. Calculate Combined External Score

**If both tools ran:**

```
external_score = (skill_check_score + tessl_review_score) / 2
```

Note: `skill_check_score` is 0-100, `tessl_review_score` is 0-100%. Both are on the same scale.

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
- **Review Score:** {score}%
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

