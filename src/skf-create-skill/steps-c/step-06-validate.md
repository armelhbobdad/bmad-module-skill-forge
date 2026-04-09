---
nextStepFile: './step-07-generate-artifacts.md'
---

# Step 6: Validate

## STEP GOAL:

To validate the compiled SKILL.md content against the agentskills.io specification using skill-check, auto-fix any validation failures, and confirm spec compliance before artifact generation.

## Rules

- Focus only on validating compiled content against spec — only fix spec compliance issues
- Validation and auto-fix modify files in the staging directory
- If skill-check unavailable: skip validation, add warning to evidence report
- Ignore non-zero exit codes from skill-check if JSON output shows 0 errors

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

**Description preservation after --fix:** After re-reading the modified SKILL.md, compare the frontmatter `description` field against the original step-05 compiled description. If `--fix` replaced the description with a generic or truncated version, restore the original description to the on-disk file and update the in-context copy. The step-05 compiled description is authoritative — auto-fix tools must not replace trigger-optimized descriptions.

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

**Description preservation:** Before any split operation, capture the current SKILL.md frontmatter `description` field. After the split completes, verify the `description` was not modified. If it was replaced with a generic placeholder, restore the original immediately.

**Mandatory approach — selective split:** Identify Tier 2 sections by their `## Full` heading prefix (e.g., `## Full API Reference`, `## Full Type Definitions`, `## Full Integration Patterns`). Extract ONLY those sections to `references/`, starting with the largest. Keep ALL Tier 1 content and any smaller sections inline. Inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval (per Vercel research).

**FORBIDDEN:** Running `npx skill-check split-body --write` without prior selective extraction. The `split-body --write` command extracts ALL `##` sections top-to-bottom, destroying Tier 1 inline content that the two-tier design depends on. This command is a LAST RESORT only after selective split has been attempted and proven insufficient.

**If selective split alone does not bring body under the limit** (rare — typically only occurs when Tier 1 itself exceeds 300 lines): reduce Tier 1 Key API Summary and Architecture at a Glance sections to fit within limits. Do NOT fall back to automated `split-body --write` to solve a Tier 1 sizing problem.

**Tier 1 preservation check:** After ANY split operation, verify that ALL of the following sections remain inline in SKILL.md (not moved to references/): Overview, Quick Start, Common Workflows, Key API Summary, Migration & Deprecation Warnings (if present), Key Types, Architecture at a Glance, CLI (if present), Scripts & Assets (if present), Manual Sections. If any Tier 1 section was moved to references/, restore it immediately and re-split targeting only Tier 2 sections.

**Anchor validation and remediation:** After any split, verify that context-snippet section anchors (`#quick-start`, `#key-types`) still resolve to headings in SKILL.md. If an anchor no longer resolves (section was split out), restore that section to SKILL.md inline content — the context-snippet must always reference sections that exist in the main file.

Then re-validate: `npx skill-check check <staging-skill-dir> --format json --no-security-scan`

**If skill-check unavailable or no body size issue:** Skip.

### 5. Security Scan

**If skill-check available:**

```bash
npx skill-check check <staging-skill-dir> --format json
```

(Security scan enabled by default when `--no-security-scan` omitted. The scan uses [Snyk Agent Scan](https://github.com/snyk/agent-scan) to check for prompt injection risks, sensitive data exposure, and unsafe tool permissions.)

Record any security warnings in evidence-report. Security findings are advisory — they do not block artifact generation. If the full validation re-run produces a different quality score than section 2, update the evidence-report with the newer score.

**If security scan fails due to missing SNYK_TOKEN:**

Display: "Security scan requires a Snyk Enterprise API token ([docs](https://docs.snyk.io/snyk-api/authentication-for-api)). Set `SNYK_TOKEN=your-token` in environment or `.env`, then re-run [SF] Setup Forge. Without Enterprise, use `--no-security-scan` to skip. Security scanning is optional and does not block skill compilation."

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
- `confidence_distribution.t1`, `confidence_distribution.t1_low`, `confidence_distribution.t2`, `confidence_distribution.t3` match actual counts
- `spec_version` is "1.3"
- If `scripts[]` or `assets[]` arrays present: verify `stats.scripts_count`/`stats.assets_count` match array lengths; verify `file_entries` count in provenance-map.json matches

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

