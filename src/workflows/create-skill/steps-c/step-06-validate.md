---
name: 'step-06-validate'
description: 'Validate compiled skill content against agentskills.io spec via skill-check'
nextStepFile: './step-07-generate-artifacts.md'
---

# Step 6: Validate

## STEP GOAL:

To validate the compiled SKILL.md content against the agentskills.io specification using skill-check, auto-fix any validation failures, and confirm spec compliance before artifact generation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing quality assurance
- ✅ Validation ensures spec compliance — it does not modify content semantics
- ✅ Tool unavailability means skip validation, not halt workflow

### Step-Specific Rules:

- 🎯 Focus ONLY on validating compiled content against spec
- 🚫 FORBIDDEN to add new content — only fix spec compliance issues
- 💾 Validation and auto-fix modify files in the staging directory (`_bmad-output/{name}/`)
- 💬 If auto-fix fails, report issues clearly but proceed (warn, don't halt)
- ⚙️ If skill-check unavailable: skip validation, add warning to evidence report
- ⚠️ Ignore non-zero exit codes from `skill-check` if the JSON output shows 0 errors — parse JSON output, not exit codes

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Validation results are added to evidence-report content in context
- 📖 Auto-fix pattern: validate → fix → re-validate (once)
- 🚫 Maximum one auto-fix attempt per validation failure
- ⏸️ **Conditional interaction:** If tessl returns suggestions (section 6b), halt for user input. Otherwise auto-proceed. This is a conditional gate step, not a pure auto-proceed step.

## CONTEXT BOUNDARIES:

- Available: All compiled content from step-05 (SKILL.md, metadata.json, etc.)
- Focus: Spec compliance validation and auto-fix
- Limits: Do NOT add new content or modify extraction data
- Dependencies: Compiled content must exist from step-05

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds: Continue to automated validation (section 2)
- If fails: Perform manual fallback (section 3); add note to evidence-report: "Spec validation performed manually — skill-check tool unavailable"

**Important:** Do not assume availability — empirical check required.

### 2. Validate & Auto-Fix (skill-check check --fix)

Run the external skill-check tool against the compiled skill staging directory:

```bash
npx skill-check check <staging-skill-dir> --fix --format json --no-security-scan
```

This performs frontmatter validation, description quality checks, body limit enforcement, local link resolution, file formatting, auto-fix of deterministic issues, and quality scoring (0-100) across five weighted categories.

**Parse the JSON output** for: `qualityScore` (0-100), `diagnostics[]` (remaining issues), `fixed[]` (auto-corrected issues).

**Context sync after --fix:** If `fixed[]` is non-empty (i.e., `--fix` modified files on disk), re-read the modified SKILL.md to update the in-context copy. Verify the re-read content matches expectations before proceeding. This prevents silent divergence between the in-context SKILL.md and the on-disk version that step-07 will use for artifact generation.

**Note:** `skill-check` may return non-zero exit code even when `errorCount` is 0. Always rely on parsed JSON, not the shell exit code.

- **Score ≥ 70:** Record "Schema: PASS (score: {score}/100)" in evidence-report
- **Score < 70:** Log remaining diagnostics as warnings, record "Schema: WARN — score {score}/100, {count} remaining issues", proceed
- **Unfixable errors:** Record specific rule IDs and suggestions, proceed with warnings

### 3. Validate Frontmatter (Fallback)

**If skill-check was available:** Skip — already validated in step 2.

**If skill-check NOT available (fallback):** Perform manual frontmatter compliance check:

- [ ] Frontmatter present — file starts with `---` and has closing `---`
- [ ] `name` field — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] `name` matches skill output directory name
- [ ] `description` field — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` permitted
- [ ] `version` and `author` are NOT in frontmatter (they belong in metadata.json)

If fails: auto-fix (deterministic), re-validate once, record result. If passes: record "Frontmatter: PASS".

### 4. Split Oversized Body (if needed)

**If step 2 reported `body.max_lines` failure:**

```bash
npx skill-check split-body <staging-skill-dir> --write
```

Then re-validate: `npx skill-check check <staging-skill-dir> --format json --no-security-scan`

**If skill-check unavailable or no body size issue:** Skip.

### 5. Security Scan

**If skill-check available:**

```bash
npx skill-check check <staging-skill-dir> --format json
```

(Security scan enabled by default when `--no-security-scan` omitted. The scan uses [Snyk Agent Scan](https://github.com/snyk/agent-scan) to check for prompt injection risks, sensitive data exposure, and unsafe tool permissions.)

Record any security warnings in evidence-report. Security findings are advisory — they do not block artifact generation.

**If security scan fails due to missing SNYK_TOKEN:**

Display actionable guidance:

"Security scan requires a Snyk API token. **Important:** The Snyk API requires an Enterprise plan ([authentication docs](https://docs.snyk.io/snyk-api/authentication-for-api)). To enable:
1. Obtain a Snyk Enterprise account with API access
2. Get your API token from Account Settings → API Token
3. Set `SNYK_TOKEN=your-token` in your environment or `.env`
4. Re-run [SF] Setup Forge to update tool detection, then re-run [CS] Create Skill

If you don't have an Enterprise account, use `--no-security-scan` flag in skill-check to skip, or `--security-scan-runner pipx|uvx|local` to control the execution method. Security scanning is optional and does not affect tier level or block skill compilation."

Record: "Security scan skipped — SNYK_TOKEN not configured"

**If skill-check unavailable:** Skip with note: "Security scan skipped — skill-check tool unavailable"

### 6. Content Quality Review (tessl)

**If tessl available**, run: `npx -y tessl skill review <staging-skill-dir>`

Parse output for: `description_score`, `content_score`, `average_score`, `validation_result`, `judge_suggestions[]`.

- **Content score < 70%:** Record warning: "Content quality warning: tessl scored content at {score}%."
- **Unavailable:** Skip with note: "Content quality review skipped — tessl tool unavailable"

> **EXPECTED BEHAVIOR — Two-Tier Scoring:** The Skill Forge two-tier design (Tier 1 Key API Summary + Tier 2 Full API Reference) intentionally includes progressive disclosure. tessl's `conciseness` scorer will flag this as redundancy (typically scoring 2/3), which is **expected behavior — not a defect**. tessl may also suggest removing `[MANUAL]` markers, moving Full API Reference to a separate file, or consolidating duplicate parameter documentation — **all three suggestions conflict with SKF design principles and must be dismissed.** Acceptable threshold: content scores >= 60% are normal for two-tier skills. Do NOT consolidate Tier 1 and Tier 2 content to improve the score — the two-tier structure is a deliberate design choice for standalone usability.

tessl installs automatically via `npx`. A missing tool is not an error — graceful skip.

#### 6b. User Decision Gate (conditional)

**If tessl returned no suggestions OR tessl was unavailable:** Skip this gate — auto-proceed.

**If tessl returned suggestions**, present them to the user:

"**Content quality review: {score}%**

tessl suggestions:
{numbered list of judge_suggestions}

**Select an option:**
- **[S] Skip** — proceed with current content as-is (default)
- **[A] Apply structural fixes** — apply only structural suggestions (split sections, consolidate duplicates). No new content generated.
- **[R] Review all** — show each suggestion with proposed changes before applying"

#### Gate Rules:

- **Structural suggestions** (split reference section, consolidate duplicates, reorder sections) can be applied without zero-hallucination risk — they restructure existing content
- **Semantic suggestions** (add examples, add error handling, add validation checkpoints) introduce content not verified from source code. If the user chooses to apply these:
  - Warn: "This adds content not verified from source code."
  - Mark applied content with `<!-- [TESSL:auto-fix] -->` markers
  - Cite as `[TESSL:suggestion]` in the provenance map with `confidence: "TESSL"` (below T3)
  - Record in evidence report: "TESSL-suggested content applied: {count} items (unverified)"
- **If user selects [S]:** Record "tessl suggestions: skipped by user" in evidence report. Proceed to section 7.
- **If user selects [A]:** Apply structural fixes only, re-run tessl to capture updated score, record results. Proceed to section 7.
- **If user selects [R]:** Show each suggestion with the proposed change. For each, user confirms or skips. Apply confirmed changes, record results. Proceed to section 7.

### 7. Validate metadata.json

Cross-check metadata.json against extraction inventory:
- `stats.exports_documented` / `stats.exports_public_api` / `stats.exports_internal` / `stats.exports_total` are accurate
- `stats.public_api_coverage` and `stats.total_coverage` are correctly computed (null when denominator is 0)
- `confidence_t1`, `confidence_t2`, `confidence_t3` match actual counts
- `spec_version` is "1.3"

Auto-fix any discrepancies (these are computed values).

### 8. Update Evidence Report

Add validation results to evidence-report content in context:

```markdown
## Validation Results
- Schema: {pass/fail} (quality score: {score}/100)
- Frontmatter: {pass/fail}
- Body: {pass/fail} {split-body applied if applicable}
- Security: {pass/warn/skipped}
- Content Quality (tessl): {pass/warn/skipped} (score: {score}%)
- Metadata: {pass/fail}

## Quality Score Breakdown
- Frontmatter (30%): {score} | Description (30%): {score} | Body (20%): {score} | Links (10%): {score} | File (10%): {score}

## Auto-Fixed Issues
- {list of issues automatically corrected by --fix}

## Remaining Warnings / Security Findings / Content Quality (tessl)
- {warnings, security results, tessl scores and suggestions — or "skipped"}
```

### 9. Menu Handling Logic

**Conditional interaction step.** If tessl produced suggestions, section 6b halts for user input. Otherwise, auto-proceed.

After validation completes (including any user decisions from section 6b), immediately load, read entire file, then execute `{nextStepFile}`.

- Tool unavailability is a skip, not a halt
- Validation failures are warnings — proceed to artifact generation
- tessl gate only triggers when suggestions exist — no gate for clean reviews or unavailable tools

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN validation is complete (or skipped) and evidence-report content is updated will you proceed to load `{nextStepFile}` for artifact generation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- `npx skill-check check --fix --format json` executed (or skipped with warning if unavailable)
- Quality score captured and recorded; auto-fix applied for deterministic issues
- Split-body applied if `body.max_lines` failed; security scan executed (or skipped with warning)
- `npx -y tessl skill review` executed (or skipped); content quality warning raised if score < 70%
- tessl suggestions presented to user when available; user decision recorded
- TESSL-applied content marked with `<!-- [TESSL:auto-fix] -->` and cited as `[TESSL:suggestion]`
- Metadata cross-check performed; evidence report updated with structured results
- Proceeded to step-07 (auto or after user gate)

### ❌ SYSTEM FAILURE:

- Halting on validation failure or skill-check unavailability (should warn and proceed)
- Adding new content during validation without user approval via the tessl gate
- Applying semantic tessl suggestions without warning the user about unverified content
- Not recording quality score; skipping security scan without recording the skip
- Attempting more than one auto-fix cycle per failure

**Master Rule:** Validation informs, it does not block. Record results, fix what's deterministic, scan for security issues, warn about the rest, and proceed.
