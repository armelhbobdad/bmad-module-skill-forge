---
nextStepFile: './step-07-generate-artifacts.md'
tesslDismissalData: 'assets/tessl-dismissal-rules.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — losing atomic-write guarantees is not
# an option for the staging-directory artifacts this step produces.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

# Step 6: Validate

## STEP GOAL:

To validate the compiled SKILL.md content against the agentskills.io specification using skill-check, auto-fix any validation failures, and confirm spec compliance before artifact generation.

## Rules

- Focus only on validating compiled content against spec — only fix spec compliance issues
- Validation and auto-fix modify files in the staging directory
- `<staging-skill-dir>` resolves to `_bmad-output/{skill-name}/` as created by step-05. The directory name must match the skill's frontmatter `name` field exactly — `skill-check`'s `frontmatter.name_matches_directory` rule rejects any suffix.
- If skill-check unavailable: skip validation, add warning to evidence report
- Ignore non-zero exit codes from skill-check if JSON output shows 0 errors

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 0. Description Guard Protocol

**Used by:** §2 (`skill-check check --fix`), §4 (`split-body`), and any future tool invocation that may modify SKILL.md.

External validators occasionally rewrite the frontmatter `description` field — `skill-check --fix` may replace it with a generic or truncated version, and `split-body` may touch it during mechanical restructuring. The step-05 §2a compiled description is **authoritative**: it has already been sanitized of angle-bracket tokens and trigger-optimized for agent discovery. Losing it to a tool's well-meaning rewrite breaks discovery quality and re-introduces the angle-bracket failure mode.

To prevent this, any tool invocation that may touch SKILL.md must run inside the following four-phase guard:

1. **Capture.** Before invoking the tool, read the current SKILL.md frontmatter and snapshot the exact `description` value into a local variable (e.g., `guarded_description`). Capture the in-context copy as well.
2. **Execute.** Run the tool as specified in its section.
3. **Verify.** After the tool completes, re-read the on-disk SKILL.md and compare its frontmatter `description` against `guarded_description` as **token streams**: split each string on whitespace (`str.split()` — any run of spaces/tabs/newlines collapses) and compare the resulting lists element-by-element. This catches content divergence (missing words, replaced phrases, truncation, angle-bracket re-introduction) while ignoring cosmetic whitespace changes that a tool may apply (trailing newline, re-wrapped quoted strings). Do NOT use a normalized-string equality — a tool that rewrites `"foo  bar"` to `"foo bar"` (collapsed inner run) would trip a naive normalization even though no semantic content changed, and a tool that swapped one word would slip past a looser fuzzy match. Token-stream comparison is the sweet spot.
4. **Restore on divergence.** If the post-tool description differs from `guarded_description` in any way other than whitespace normalization, write `guarded_description` back to the on-disk SKILL.md frontmatter and update the in-context copy to match. Record `description_guard_restored: true` with the tool name in context for the evidence report.
5. **Re-validate restored description.** After a restore, run `uv run {project-root}/src/shared/scripts/skf-validate-frontmatter.py <staging-skill-dir>/SKILL.md` against the on-disk file to confirm the restored description still satisfies the frontmatter contract (length limits, forbidden tokens, required fields). The script declares pyyaml in its PEP 723 inline metadata; `uv run` resolves it automatically (per `docs/getting-started.md`'s uv prereq), while bare `python3` would `ModuleNotFoundError` on a fresh interpreter. Capture `schema_revalidation_result` in context. If the validator exits non-zero OR reports failure for the `description` field: flip the Schema result back to `FAIL` in the evidence report (overriding any prior PASS/WARN from §2), record `description_guard_revalidation: FAIL` with the validator's diagnostic message, and continue — do not halt (step-09 health-check and result contract still need to run so the failure is surfaced through the normal artifact path).

**What counts as divergence:**

- The description was replaced (different content).
- The description was truncated (suffix missing).
- Angle-bracket tokens were re-introduced (should never happen after step-05 §2a, but protect anyway).
- The field was deleted entirely (extreme tool behavior).

**What does NOT count as divergence:** whitespace-only differences (trailing newline, trimmed spaces) — treat as equivalent.

**Why this is centralized:** previously, §2 and §4 each contained their own capture/verify/restore prose. Duplicated defensive code drifts: a fix in one section doesn't propagate to the other, and adding a new tool invocation in the future requires remembering to copy the pattern. Centralizing the protocol gives step-06 one place to update when external validator behavior changes.

### 1. Check Tool Availability

Run: `timeout 30s npx skill-check -h` — the short timeout protects against a cold `npx` download blocking the workflow indefinitely on a slow network.

- If succeeds: Continue to automated validation (section 2)
- If fails or times out: Perform manual fallback (section 3); add note to evidence-report: "Spec validation performed manually — skill-check tool unavailable". Also set `metadata.validation_status: 'manual-only'` in `metadata.json` (write via `python3 {atomicWriteHelper} write --target <staging-skill-dir>/metadata.json`), and in the evidence-report's `Validation Results` section mark Security, Body, and Content Quality (tessl) rows explicitly as `skipped — skill-check unavailable`. Downstream consumers (pipeline, forger, test-skill) check `validation_status` to decide how much weight to put on the artifact; leaving it unset would make a manual-only run look equivalent to a fully automated PASS.

**Important:** Do not assume availability — empirical check required.

### 2. Validate & Auto-Fix (skill-check check --fix)

Run the external skill-check tool against the compiled skill staging directory.

**Flag probe (run once, cache the result for §4 and §5 re-invocations):**

```bash
npx skill-check --help 2>/dev/null | grep -- --no-security-scan
```

- If the probe matches `--no-security-scan`: set `{security_scan_flag} = "--no-security-scan"`.
- Else run a second probe — `npx skill-check --help 2>/dev/null | grep -- --skip-security` — and if it matches, set `{security_scan_flag} = "--skip-security"`.
- If neither flag exists: set `{security_scan_flag} = ""` (empty) AND set `{skill_check_flag_fallback} = true`. Skip §2 and §4 automated flows entirely — fall through to §3 manual frontmatter validation. Record in evidence-report: `skill_check_flag_probe: neither --no-security-scan nor --skip-security supported by installed skill-check; validation performed manually`.

**If a security-scan-disable flag was resolved (probe succeeded):**

```bash
npx skill-check check <staging-skill-dir> --fix --format json {security_scan_flag}
```

This performs frontmatter validation, description quality checks, body limit enforcement, local link resolution, file formatting, auto-fix of deterministic issues, and quality scoring (0-100) across five weighted categories.

**Parse the JSON output** for: `qualityScore` (0-100), `diagnostics[]` (remaining issues), `fixed[]` (auto-corrected issues).

**Description Guard Protocol:** This invocation may modify SKILL.md (especially when `fixed[]` is non-empty). Wrap the `skill-check check --fix` call in the four-phase protocol defined in §0: capture `guarded_description` before the call, execute, verify against the post-tool description, and restore on divergence. If `fixed[]` is non-empty, also re-read the modified SKILL.md to sync the in-context copy before proceeding — this prevents silent divergence between the in-context and on-disk versions that step-07 will use for artifact generation.

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

**Description Guard Protocol:** Split operations may rewrite the frontmatter. Wrap the split invocation in the four-phase protocol defined in §0 to capture `guarded_description` before the call, execute, verify, and restore on divergence.

**Mandatory approach — selective split:** Identify Tier 2 sections by their `## Full` heading prefix (e.g., `## Full API Reference`, `## Full Type Definitions`, `## Full Integration Patterns`). Extract ONLY those sections to `references/`, starting with the largest. Keep ALL Tier 1 content and any smaller sections inline. Inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval (per Vercel research).

**FORBIDDEN:** Running `npx skill-check split-body --write` without prior selective extraction. The `split-body --write` command extracts ALL `##` sections top-to-bottom, destroying Tier 1 inline content that the two-tier design depends on. This command is a LAST RESORT only after selective split has been attempted and proven insufficient.

**If selective split alone does not bring body under the limit** (rare — typically only occurs when Tier 1 itself exceeds 300 lines): reduce Tier 1 Key API Summary and Architecture at a Glance sections to fit within limits. Do NOT fall back to automated `split-body --write` to solve a Tier 1 sizing problem.

**Tier 1 preservation check:** After ANY split operation, verify that ALL of the following sections remain inline in SKILL.md (not moved to references/): Overview, Quick Start, Common Workflows, Key API Summary, Migration & Deprecation Warnings (if present), Key Types, Architecture at a Glance, CLI (if present), Scripts & Assets (if present), Manual Sections. If any Tier 1 section was moved to references/, restore it immediately and re-split targeting only Tier 2 sections.

**Post-split Tier-1 count check (mandatory):** before invoking the splitter, count the Tier-1 `##`-level section headings present in SKILL.md (any heading whose title matches one of the Tier-1 names listed above) and store as `tier1_count_pre`. After the split completes, recount as `tier1_count_post`. **HALT** if `tier1_count_post < tier1_count_pre` with: "Split reduced Tier-1 section count from {pre} to {post}. Tier-1 sections must remain inline. Restoring from staging backup and aborting body split — manual review required." Do not proceed past §4 — Tier-1 preservation is a hard invariant and a count drop indicates the splitter pulled an inline section into references/ regardless of the section-list check above (e.g., heading-text variation, capitalization, or the splitter's own heuristics).

**Anchor validation and remediation:** After any split, verify that context-snippet section anchors (`#quick-start`, `#key-types`) still resolve to headings in SKILL.md. If an anchor no longer resolves (section was split out), restore that section to SKILL.md inline content — the context-snippet must always reference sections that exist in the main file.

Then re-validate: `npx skill-check check <staging-skill-dir> --format json {security_scan_flag}` — use the flag cached from §2's probe. If `{skill_check_flag_fallback}` is true, skip re-validation and rely on the §3 manual check.

**If skill-check unavailable or no body size issue:** Skip.

### 5. Security Scan

**If skill-check available:**

```bash
npx skill-check check <staging-skill-dir> --format json
```

(Security scan enabled by default when `--no-security-scan` omitted. The scan uses [Snyk](https://docs.snyk.io/) to check for prompt injection risks, sensitive data exposure, and unsafe tool permissions.)

Record any security warnings in evidence-report. Security findings are advisory — they do not block artifact generation. If the full validation re-run produces a different quality score than section 2, update the evidence-report with the newer score.

**If security scan fails due to missing SNYK_TOKEN:**

Display: "Security scan requires a Snyk Enterprise API token ([docs](https://docs.snyk.io/snyk-api/authentication-for-api)). Set `SNYK_TOKEN=your-token` in environment or `.env`, then re-run [SF] Setup Forge. Without Enterprise, use `--no-security-scan` to skip. Security scanning is optional and does not block skill compilation."

Record: "Security scan skipped — SNYK_TOKEN not configured"

**If skill-check unavailable:** Skip with note: "Security scan skipped — skill-check tool unavailable"

### 6. Content Quality Review (tessl)

**If tessl available**, run: `timeout 120s npx -y tessl skill review <staging-skill-dir>` — the 120s cap matches skf-test-skill's tessl invocation guard and prevents a stalled LLM call in tessl from blocking compilation. On timeout, treat the step as unavailable and record `tessl: timeout — content quality review skipped` in the evidence report.

Parse output for: `description_score`, `content_score`, `review_score`, `validation_result`, `judge_suggestions[]`.

**Load dismissal rules:** Before interpreting any findings, load `{tesslDismissalData}` completely. This file is the single source of truth for tessl findings that SKF expects and must dismiss. It defines score thresholds, suggestion dismissal patterns, and the action to take when each rule matches.

**Apply dismissal rules** in this order:

1. **Check score thresholds** against the "Score Thresholds" table in `{tesslDismissalData}`. Most importantly:
   - If `description_score < 100`: follow the **recover-then-halt** path defined by the `description-xml-tags-guarded-upstream` rule in `{tesslDismissalData}`. Re-apply step-05 §2a's `<`/`>` → `{`/`}` substitution in place on the staging SKILL.md frontmatter `description`, re-sync the in-context copy, and re-run `npx -y tessl skill review <staging-skill-dir>` once. **Re-run gate:** treat `description_score == 100` on the re-run as the only successful recovery outcome. ANY value strictly less than 100 on the re-run — including 99, intermediate-but-improved scores like 95 (formerly tolerated as "close enough"), or 0 — counts as recovery failure: halt with the original `description-xml-tags-guarded-upstream` failure message from `{tesslDismissalData}`, do NOT proceed to §6b, and do NOT downgrade the recovery to a warning. If the re-run produces `description_score == 100`, log `description-recovery: applied ({count} substitutions)` in the evidence report under "Dismissed tessl suggestions" and continue suggestion iteration against the rerun's `judge_suggestions[]`.
   - If `review_score < 60` or `content_score < 60`: record warnings in the evidence report, continue.
2. **Iterate `judge_suggestions[]`.** For each suggestion:
   - Cross-reference against the rules in `{tesslDismissalData}` in order.
   - If a rule matches: record `{rule_id, rationale, suggestion_text}` under "Dismissed tessl suggestions" in the evidence report. Do not apply.
   - If no rule matches: add to the "Novel tessl suggestions" list for §6b to surface to the user.
3. **Short-circuit when empty.** If every suggestion was dismissed (no novel suggestions), §6b has nothing to show — auto-proceed to §7.

- **Unavailable:** Skip with note: "Content quality review skipped — tessl tool unavailable"

tessl installs automatically via `npx`. A missing tool is not an error — graceful skip.

#### 6b. User Decision Gate (conditional)

**If §6 produced no novel suggestions (all dismissed via `{tesslDismissalData}`) OR tessl was unavailable:** Skip this gate — auto-proceed.

**If §6 produced novel suggestions** (ones not matched by any dismissal rule), present them to the user:

"**Content quality review: {score}%**

tessl suggestions (novel — not matched by `{tesslDismissalData}`):
{numbered list of novel suggestions}

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

## Description Guard
- Restored: {true/false}
- Triggering tool: {tool_name or —}
- Original description preserved: {true/false}
- Notes: {one-sentence detail or —}

## Auto-Fixed Issues
- {list of issues automatically corrected by --fix}

## Remaining Warnings / Security Findings / Content Quality (tessl)
- {warnings, security results, tessl scores and suggestions — or "skipped"}
```

**Description Guard population:** if the §0 protocol fired during §2 (`skill-check --fix`) or §4 (`split-body`), fill the four Description Guard fields from context:

- `Restored: true` when `description_guard_restored == true`, otherwise `false`.
- `Triggering tool`: the tool name recorded by §0 (`skill-check --fix`, `skill-check split-body`, etc.), or `—` if the guard did not fire.
- `Original description preserved`: `true` if the restore succeeded (on-disk now matches the pre-tool snapshot), `false` if restoration itself failed (rare — treat as a halt condition in a future version).
- `Notes`: a one-sentence description of what the tool had changed. Typical values: `"replaced with generic summary"`, `"truncated at N chars"`, `"angle-bracket tokens re-introduced"`, `"field deleted entirely"`. If `Restored: false`, use `—`.

When `Restored: false`, the three follow-up fields are all `—` — this is the clean-run expected state.

### 9. Menu Handling Logic

**Conditional interaction step.** If tessl produced suggestions, section 6b halts for user input. Otherwise, auto-proceed.

After validation completes (including any user decisions from section 6b), immediately load, read entire file, then execute `{nextStepFile}`.

- Tool unavailability is a skip, not a halt
- Validation failures are warnings — proceed to artifact generation
- tessl gate only triggers when suggestions exist — no gate for clean reviews or unavailable tools

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN validation is complete (or skipped) and evidence-report content is updated will you proceed to load `{nextStepFile}` for artifact generation.

