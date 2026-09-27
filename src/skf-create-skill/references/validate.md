---
nextStepFile: 'generate-artifacts.md'
# Resolve `{descriptionGuardProtocol}` (the guard's prose protocol, not its
# helper script) by probing `{descriptionGuardProtocolProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. Advisory: if neither path exists, skip the load and
# continue, because §0 states every guard rule this step acts on and the
# protocol only explains them.
descriptionGuardProtocolProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/description-guard-protocol.md'
  - '{project-root}/src/shared/references/description-guard-protocol.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — losing atomic-write guarantees is not
# an option for the staging-directory artifacts this step produces.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{descriptionGuardHelper}` by probing `{descriptionGuardProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. HALT if neither resolves — letting an external
# tool's rewrite of the description field stand would silently regress
# discovery quality.
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
# Resolve `{frontmatterValidator}` by probing `{frontmatterValidatorProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves — §6's description check has no
# fallback, and §0's post-restore re-validation hook uses it too; an installed
# module has no src/ tree, so a bare src/ path would silently skip both.
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
# Resolve `{shardBodyHelper}` by probing `{shardBodyProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. §4 uses it as the deterministic selective splitter and reads its
# `tier1_preserved` field instead of counting Tier-1 headings pre/post by hand.
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
# Resolve `{renderMetadataStatsHelper}` by probing `{renderMetadataStatsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §7 uses it in --check mode to re-derive the metadata
# `stats` / `confidence_distribution` instead of re-doing the arithmetic by hand.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
# Resolve `{tesslReviewHelper}` by probing `{tesslReviewProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. If neither path exists, §6b records that Tessl Review did not run
# and continues: the review is optional and never gates the workflow.
tesslReviewProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-tessl-review.py'
  - '{project-root}/src/shared/scripts/skf-tessl-review.py'
# Resolve `{tesslReviewRules}` the same way. §6b loads it after a completed
# review to mark the suggestions SKF does not follow; without it the
# suggestions are listed unmarked.
tesslReviewRulesProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/tessl-review.md'
  - '{project-root}/src/shared/references/tessl-review.md'
preferencesFile: '{sidecar_path}/preferences.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Step 6: Validate

## STEP GOAL:

To validate the compiled SKILL.md content against the agentskills.io specification using skill-check, auto-fix any validation failures, confirm that the frontmatter description holds no angle brackets, and confirm spec compliance before artifact generation. When the user has opted in to Tessl Review, also record Tessl's review of the skill as advice; it never gates the step.

## Rules

- Focus only on validating compiled content against spec — only fix spec compliance issues
- Validation and auto-fix modify files in the staging directory
- `<staging-skill-dir>` resolves to `_bmad-output/.skf-stage/{skill-name}/` as created by step 5. Its last folder name must match the skill's frontmatter `name` field exactly — `skill-check`'s `frontmatter.name_matches_directory` rule rejects any suffix.
- If skill-check unavailable: skip validation, add warning to evidence report
- Ignore non-zero exit codes from skill-check if JSON output shows 0 errors
- Tessl Review (§6b) is optional and advisory: it never halts, never asks the user anything and never changes the staged files, and SKF applies none of its suggestions

## MANDATORY SEQUENCE

### 0. Description Guard Protocol

**Used by:** §2 (`skill-check check --fix`), §4 (`split-body`), and any future tool invocation that may modify SKILL.md.

Resolve `{descriptionGuardProtocol}` ← first existing path in `{descriptionGuardProtocolProbeOrder}` and load it for the full prose explanation of the four-phase guard (why it exists, what counts as divergence, why token-stream comparison is the right shape). The load is advisory: if neither path exists, continue, because the rules below are all this step needs from it. The deterministic phases are executed via `{descriptionGuardHelper}` — the calling sections (§2 and §4) invoke the helper at the capture and verify-restore points.

**Guard outputs.** Bind `{guarded_description}` ← `description` from each `capture`, run while the in-context SKILL.md copy matches the file on disk. Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from each `verify-restore`. When `{guard_restored}` is true, set the in-context `description` to `{guarded_description}` so later sections do not work from the tool-mutated value, and record `description_guard_restored: true` with the tool name and `description_guard_diff_kind: {guard_diff_kind}` in workflow context for the evidence report (§8). A later `verify-restore` that exits 0 with `{guard_restored}` false leaves those records in place.

**Empty-snapshot rule.** `verify-restore` refuses an empty or whitespace-only `--captured-description` (exit 1, file untouched). Never re-run it with the empty value: writing it back would blank the field the guard protects. If the compiled description is still in context (the in-context SKILL.md copy), re-run `verify-restore` with that value. Otherwise record `description_guard_restored: false` and `description_guard_refused: empty-capture` with the tool name; the evidence report (§8) renders that as a fired guard, not as a clean run.

**This skill's post-restore re-validation hook:** after `{descriptionGuardHelper}` reports `restored: true`, resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}` (first existing path wins), run `uv run {frontmatterValidator} <staging-skill-dir>/SKILL.md` and capture `schema_revalidation_result` in context. If the validator exits non-zero OR reports failure for the `description` field, flip the Schema result back to `FAIL` in the evidence report (overriding any prior PASS/WARN from §2), record `description_guard_revalidation: FAIL` with the validator's diagnostic message, and continue — do not halt (step 9 health-check and result contract still need to run so the failure is surfaced through the normal artifact path).

### 1. Check Tool Availability

Run: `timeout 30s npx skill-check -h` — the short timeout protects against a cold `npx` download blocking the workflow indefinitely on a slow network.

- If succeeds: Continue to automated validation (section 2)
- If fails or times out: Perform manual fallback (section 3); add note to evidence-report: "Spec validation performed manually — skill-check tool unavailable". Also set `metadata.validation_status: 'manual-only'` in `metadata.json` (write via `python3 {atomicWriteHelper} write --target <staging-skill-dir>/metadata.json`), and in the evidence-report's `Validation Results` section mark the Security and Body rows explicitly as `skipped — skill-check unavailable` (§6 and §6b do not depend on skill-check). Downstream consumers (pipeline, forger, test-skill) check `validation_status` to decide how much weight to put on the artifact; leaving it unset would make a manual-only run look equivalent to a fully automated PASS.

**Important:** Do not assume availability — empirical check required.

### 2. Validate & Auto-Fix (skill-check check --fix)

Run the external skill-check tool against the compiled skill staging directory.

**Flag probe (run once, cache the result for §4 and §5 re-invocations):**

```bash
npx skill-check check --help 2>/dev/null | grep -- --no-security-scan
```

- If the probe matches `--no-security-scan`: set `{security_scan_flag} = "--no-security-scan"`.
- Else run a second probe — `npx skill-check check --help 2>/dev/null | grep -- --skip-security` — and if it matches, set `{security_scan_flag} = "--skip-security"`.
- If neither flag exists: set `{security_scan_flag} = ""` (empty) AND set `{skill_check_flag_fallback} = true`. Skip §2 and §4 automated flows entirely — fall through to §3 manual frontmatter validation. Record in evidence-report: `skill_check_flag_probe: neither --no-security-scan nor --skip-security supported by installed skill-check; validation performed manually`.

**If a security-scan-disable flag was resolved (probe succeeded):**

```bash
npx skill-check check <staging-skill-dir> --fix --format json {security_scan_flag}
```

This performs frontmatter validation, description quality checks, body limit enforcement, local link resolution, file formatting, auto-fix of deterministic issues, and quality scoring (0-100) across five weighted categories.

**Parse the JSON output** for: `scores[].score` (0-100 — match the entry by `relativePath`/`skillId`; falls back to a top-level `qualityScore` on older skill-check builds), `diagnostics[]` (remaining issues), `fixed[]` (auto-corrected issues).

**Description Guard Protocol:** This invocation may modify SKILL.md (especially when `fixed[]` is non-empty). Wrap the `skill-check check --fix` call in the four-phase guard defined in §0 by invoking `{descriptionGuardHelper}` at the capture and verify-restore points:

```bash
# Phase 1 — capture before the tool call
uv run {descriptionGuardHelper} capture <staging-skill-dir>/SKILL.md
# stash the returned `description` as `guarded_description` in workflow context

# Phase 2 — run skill-check (see command block above)

# Phases 3+4 — verify and restore after the tool call
uv run {descriptionGuardHelper} verify-restore <staging-skill-dir>/SKILL.md \
    --captured-description "{guarded_description}"
```

If `restored: true` in the verify-restore output, apply §0's post-restore re-validation hook. If `fixed[]` was non-empty in the skill-check output, also re-read the modified SKILL.md to sync the in-context copy before proceeding — this prevents silent divergence between the in-context and on-disk versions that step 7 will use for artifact generation.

**Note:** `skill-check` may return non-zero exit code even when `summary.errorCount` is 0. Always rely on parsed JSON, not the shell exit code.

- **Score ≥ 70:** Record "Schema: PASS (score: {score}/100)" in evidence-report
- **Score < 70:** Log remaining diagnostics as warnings, record "Schema: WARN — score {score}/100, {count} remaining issues", proceed
- **Unfixable errors:** Record specific rule IDs and suggestions, proceed with warnings

### 3. Validate Frontmatter (Fallback)

**If skill-check was available:** Skip — already validated in step 2.

**If skill-check not available (fallback):** Perform manual frontmatter compliance check:

- [ ] Frontmatter present — file starts with `---` and has closing `---`
- [ ] `name` field — present, non-empty, lowercase alphanumeric + hyphens only, 1-64 chars
- [ ] `name` matches skill output directory name
- [ ] `description` field — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` permitted
- [ ] `version` and `author` are not in frontmatter (they belong in metadata.json)

If fails: auto-fix (deterministic), re-validate once, record result. If passes: record "Frontmatter: PASS".

### 4. Split Oversized Body (if needed)

**If step 2 reported `body.max_lines` failure:**

**Description Guard Protocol:** Split operations may rewrite the frontmatter. Wrap the split invocation in the four-phase guard defined in §0:

```bash
# Phase 1 — capture before the split
uv run {descriptionGuardHelper} capture <staging-skill-dir>/SKILL.md
# stash returned `description` as `guarded_description`

# Phase 2 — run the split (selective extraction or, last-resort, split-body --write)

# Phases 3+4 — verify and restore after the split
uv run {descriptionGuardHelper} verify-restore <staging-skill-dir>/SKILL.md \
    --captured-description "{guarded_description}"
```

If `restored: true` in the verify-restore output, apply §0's post-restore re-validation hook.

**Mandatory approach — selective split:** Identify Tier 2 sections by their `## Full` heading prefix (e.g., `## Full API Reference`, `## Full Type Definitions`, `## Full Integration Patterns`). Extract ONLY those sections to `references/`, starting with the largest. Keep ALL Tier 1 content and any smaller sections inline. Inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval (per Vercel research).

This selective split is deterministic — run `{shardBodyHelper}` (the same splitter step 5b auto-shard uses) rather than counting and extracting by hand. **Resolve `{shardBodyHelper}`** from `{shardBodyProbeOrder}`; first existing path wins.

```bash
uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --budget 400
```

It extracts the largest `## Full` sections to `references/` until the body fits, rewrites each as a cross-reference blockquote through the atomic-write helper, and reports `sections_extracted`, `body_lines_after`, `tier1_preserved`, `xref_ok`, and `under_budget`.

**Do not run `npx skill-check split-body --write` before selective extraction.** It extracts every `##` section top-to-bottom, destroying the Tier 1 inline content the two-tier design depends on — a last resort used only after selective split has been attempted and proven insufficient.

**If selective split alone does not bring body under the limit** (the splitter reports `under_budget: false` — rare, typically only when Tier 1 itself exceeds 300 lines): reduce Tier 1 Key API Summary and Architecture at a Glance sections to fit within limits. Do not fall back to automated `split-body --write` to solve a Tier 1 sizing problem.

**Tier 1 preservation check:** After any split operation, verify that all of the following Tier 1 sections remain inline in SKILL.md (not moved to references/): Overview, Quick Start, Common Workflows, Key API Summary, Migration & Deprecation Warnings (if present), Key Types, Architecture at a Glance, CLI (if present), Scripts & Assets (if present), Manual Sections. If any was moved to references/, restore it immediately and re-split targeting only Tier 2 sections.

**Post-split Tier-1 count check (mandatory):** do not recount Tier-1 headings by hand — consume the splitter's `tier1_preserved` field. `{shardBodyHelper}` compares the Tier-1 headings inline before extraction against those inline afterward and reports `tier1_preserved` (with any pulled headings in `tier1_missing`). Read it from the invocation above, or re-check any split's result with `uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --dry-run`. **HALT** if `tier1_preserved` is false with: "Split reduced Tier-1 section count (missing {tier1_missing}). Tier-1 sections must remain inline. Restoring from staging backup and aborting body split — manual review required." Do not proceed past §4 — Tier-1 preservation is a hard invariant and a `tier1_preserved: false` result means the splitter pulled an inline section into references/ regardless of the section-list check above (e.g., heading-text variation, capitalization, or the splitter's own heuristics).

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

### 6. Description Angle-Bracket Check

The Claude platform does not accept a skill whose frontmatter `description` contains XML tags, and none of the validators this step runs checks for them: skill-check has no such rule and Tessl Review accepts them. Step 5 §2a replaces every `<` with `{` and every `>` with `}` before SKILL.md is written, and the §0 guard puts that description back whenever a tool rewrites it; this section checks the staged result after every tool in this step has run, whether or not skill-check was available.

Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}`; first existing path wins. If neither path resolves, or the command below prints no JSON object, HALT with: "Cannot check the staged description — skf-validate-frontmatter.py is missing or did not run. Re-install SKF, then re-run create-skill." Run:

```bash
uv run {frontmatterValidator} "<staging-skill-dir>/SKILL.md" --forbid-angle-brackets
```

Rely on the parsed JSON, not the exit code: the validator also exits 1 for the frontmatter issues §2 and §3 already recorded. Bind `{description_angle_brackets}` ← `description_angle_brackets`.

- **`{description_angle_brackets}` is `0`:** record `Description angle brackets: none` and continue to §6b.
- **`{description_angle_brackets}` is null** (the description is missing, blank or not a string, which §2 or §3 already recorded): record `Description angle brackets: not checked — no description` and continue to §6b.
- **`{description_angle_brackets}` is above `0`:** apply step 5 §2a's substitution again, in place. The guard helper rewrites only the `description` field and takes no description on the command line, so backticks and `$` in it are safe:

  ```bash
  uv run {descriptionGuardHelper} sanitize "<staging-skill-dir>/SKILL.md"
  ```

  Bind `{angle_bracket_substitutions}` ← `substitutions`, `{angle_brackets_sanitized}` ← `sanitized` and `{sanitized_description}` ← `description`. Then run the validator command above once more and bind `{description_angle_brackets}` ← `description_angle_brackets` again.
  - **Recovered** (the guard helper exited 0, `{angle_brackets_sanitized}` is true and `{description_angle_brackets}` is now `0`): set the in-context SKILL.md copy's `description` to `{sanitized_description}` (step 7 writes from the in-context copies), record `Description angle brackets: re-sanitized ({angle_bracket_substitutions} substitutions)` and continue to §6b.
  - **Otherwise HALT** with: "Description sanitization failed — the staged SKILL.md description still holds angle brackets after step 5 §2a's substitution was applied again. The Claude platform does not accept XML tags in a skill description. Check that `<staging-skill-dir>/SKILL.md` can be written, then re-run create-skill." Nothing has been promoted yet, so under `{headless_mode}` emit the stderr envelope per `references/report.md` "Result Contract on HARD HALT" with `status: "failed"`, `phase: "validate"`, `summary.halt_reason: "description-angle-brackets"`, `summary.evidence_report: null` and `skill_package: null`.

### 6b. Tessl Review (optional)

Tessl Review (`tessl review run`, which the helper below runs on a copy of `<staging-skill-dir>`) scores the skill on Tessl's servers with validation checks and two AI judges, one for the description and one for the content. It runs only when the user opted in by setting `tessl_review_workspace` in `{preferencesFile}` to a Tessl workspace name, because it needs a Tessl account, uploads the skill's files to that workspace's review history and spends Tessl credits. The helper applies that setting and every other condition, so run it on every pass and let it decide; `{tesslReviewRules}` explains what is uploaded and what each result means. Nothing in this section halts, asks the user anything, changes the staged files or adds an auto-decision, in interactive and headless runs alike.

Resolve `{tesslReviewHelper}` ← first existing path in `{tesslReviewProbeOrder}`. If neither path exists, set `{tessl_summary}` to `not run — skf-tessl-review.py is missing` and `{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, add that line to the evidence report's Remaining Warnings and continue to §7. Otherwise submit the review:

```bash
uv run {tesslReviewHelper} submit "<staging-skill-dir>" --preferences "{preferencesFile}"
```

A review takes Tessl about two minutes, so no call waits for all of it. When the review is on, `submit` sends a copy of the skill to Tessl and returns `pending` with Tessl's run id as soon as Tessl accepts it; when it is off or cannot run, `submit` returns that result instead. While `{tessl_status}` is `pending`, collect the review, at most six times, and add `--final` to the sixth call, which turns a review still running into `timeout`:

```bash
uv run {tesslReviewHelper} collect "{tessl_run_id}" --workspace "{tessl_workspace}" --tessl-version "{tessl_version}"
```

Each call ends within two minutes (a `collect` checks the review for up to 90 seconds, then returns `pending` again or the result), so run each one with your shell tool's default time limit. If the shell tool stops a call before it prints its JSON, or it prints none, make that the last call: set `{tessl_status}` to `failed`, `{tessl_summary}` to `failed — stopped before skf-tessl-review.py reported a result` and `{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, keep `{tessl_run_id}` and the other values the calls before it bound, add that line to the Remaining Warnings and continue to §7. Otherwise rely on the JSON, not the exit code, and bind these from the `submit` JSON and again from each `collect` JSON, whose values replace the earlier ones:

- `{tessl_status}` ← `status`
- `{tessl_summary}` ← `summary`
- `{tessl_warnings}` ← `warnings`
- `{tessl_workspace}` ← `workspace`
- `{tessl_version}` ← `tessl_version`
- `{tessl_run_id}` ← `run_id`
- `{tessl_review_score}` ← `review_score`
- `{tessl_description_score}` ← `description_score`
- `{tessl_content_score}` ← `content_score`
- `{tessl_validation}` ← `validation`
- `{tessl_description_suggestions}` ← `description_suggestions`
- `{tessl_content_suggestions}` ← `content_suggestions`

Every key is always present: the scores and `{tessl_validation}` are null and the suggestion lists are empty unless `{tessl_status}` is `reviewed`, and `{tessl_run_id}` is null until Tessl has accepted the review. After the last call, add each entry of `{tessl_warnings}` to the evidence report's Remaining Warnings: a score below 60%, validation errors or, for any status other than `reviewed` and `off`, why the review produced no score. When `{tessl_status}` is `reviewed`, resolve `{tesslReviewRules}` ← first existing path in `{tesslReviewRulesProbeOrder}`, load it, and mark each entry of `{tessl_content_suggestions}` that one of its rules matches with `(not applicable: <rule-id>)`; if neither path exists, list the suggestions unmarked. Apply no suggestion: content suggestions would add text SKF cannot cite to source, and the description comes from the brief. The staged skill holds no `scripts/` or `assets/` until step 7 copies them, so for a brief with scripts or assets, validation findings about missing `scripts/` or `assets/` paths are expected here; test-skill reviews the finished package. §8 records the result.

### 7. Validate metadata.json

**Re-derive the computed fields with `{renderMetadataStatsHelper}` in check mode** rather than re-doing the arithmetic by hand. Resolve `{renderMetadataStatsHelper}` from `{renderMetadataStatsProbeOrder}` (first existing path wins; HALT if neither resolves), then run it against the staged provenance-map and metadata.json:

```bash
uv run {renderMetadataStatsHelper} <staging-skill-dir>/provenance-map.json \
    --check <staging-skill-dir>/metadata.json
```

The helper re-bins `entries[]` by `signature_source`, recomputes `exports_documented`, `exports_total`, and `public_api_coverage` / `total_coverage` (null when the denominator is 0), and cross-checks `stats.scripts_count` / `stats.assets_count` against the `scripts[]` / `assets[]` array lengths and the provenance-map `file_entries` counts. It takes the judgment values (`exports_public_api`, `exports_internal`, `effective_denominator`) from `metadata.json` itself and infers the shape from `scope_type` / `skill_type` (pass `--shape` to override). Parse the emitted JSON (rely on the JSON, not the exit code):

- **`coherence.ok: true`** — the computed fields are internally consistent; record "Metadata: PASS".
- **`coherence.ok: false`** — each `violations[]` entry is `{field, expected, actual}` where `expected` is the correct value. **Auto-fix each computed-value violation** (`field` starting `stats.` or `confidence_distribution.`) by setting that field in `metadata.json` to `expected` (write via `python3 {atomicWriteHelper} write --target <staging-skill-dir>/metadata.json`), leaving every other stats field — e.g. `stats.notes` on a reference app — untouched. Record "Metadata: auto-fixed {N} computed-value discrepanc(y|ies)" listing the fields. These are computed values, so the helper is authoritative — a `confidence_distribution` violation is the per-entry mis-binning compile.md §4 describes (T2 annotations + T3 doc items counted on top of the per-export tiers); the helper's per-entry counts replace them. Carve-outs are handled by `--shape`: a **stack** distribution sums to the constituent count and a **reference-app** distribution to the per-citation count, so those are consistent states, not violations. A `provenance.file_entries.*` violation is not a computed metadata field — it means the provenance-map `file_entries` and metadata counts disagree; record it as a warning for manual reconciliation rather than auto-editing the count.

Then verify the two fields the helper does not own (genuine constants/contract):
- `spec_version` is `"1.3"`.
- `scope_type` is present and equals the brief's `scope.type` verbatim.

### 8. Update Evidence Report

Add validation results to evidence-report content in context:

```markdown
## Validation Results
- Schema: {pass/fail} (quality score: {score}/100)
- Frontmatter: {pass/fail}
- Body: {pass/fail} {split-body applied if applicable}
- Security: {pass/warn/skipped}
- Description angle brackets: {none | re-sanitized ({count} substitutions) | not checked — no description}
- Tessl Review: {tessl_summary}
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

## Remaining Warnings
- {warnings and security results, then each entry of {tessl_warnings} — or "none"}

## Tessl Review
- Result: {tessl_summary}
- Workspace: {tessl_workspace or —} · tessl {tessl_version or —} · Run: {tessl_run_id or —}
- Validation findings: {each {tessl_validation} finding as `name (status): message`, or "none"}
- Description suggestions (to act on one, edit the description in the brief and re-run create-skill): {each of {tessl_description_suggestions}, or "none"}
- Content suggestions (advisory, not applied): {each of {tessl_content_suggestions} with its `(not applicable: <rule-id>)` mark, or "none"}
```

When `{tessl_status}` is not `reviewed`, the `## Tessl Review` section holds only its Result line and, when `{tessl_run_id}` is set, its Workspace line, so the report names the run of a review that may still finish.

**Auto-Decisions table (reconcile from the durable sink — idempotent):** all gates have now fired — each fired before step 5 and appended its row to the on-disk sink `{sidecar_path}/auto-decisions.jsonl` as it landed, step 5 §7 rendered those step 1–3d rows into the staged `<staging-skill-dir>/evidence-report.md`, and steps 6–9 add none. Reconcile: read the sink's JSON lines (the authoritative durable record — it survives any compaction of the in-context buffer), union them with both the `## Auto-Decisions` rows already in `<staging-skill-dir>/evidence-report.md` and the in-context `headless_decisions[]` buffer, keyed on `step`+`gate` so no decision is duplicated or dropped, and re-render the section from that union. Because the rows are recovered from the sink rather than from the possibly-compacted buffer, the audit table stays complete on a long headless run. Emit one row per entry:

```
## Auto-Decisions

| Step | Gate | Decision | Rationale | Timestamp |
|------|------|----------|-----------|-----------|
| {step} | {gate} | {decision}{value?} | {rationale} | {timestamp} |
```

If the sink, the on-disk rows, and `headless_decisions[]` are all empty, keep the single line step 5 §7 emitted: `No auto-decisions — workflow ran interactively (or all gates had no match to auto-resolve).` This keeps the section always present so reviewers can tell "zero auto-decisions" apart from "section missing", and keeps the row count equal to `summary.auto_decision_count`.

**Description Guard population:** if the §0 protocol fired during §2 (`skill-check --fix`) or §4 (`split-body`), fill the four Description Guard fields from context:

- `Restored: true` when `description_guard_restored == true`, otherwise `false`.
- `Triggering tool`: the tool name recorded by §0 (`skill-check --fix`, `skill-check split-body`, etc.), or `—` if the guard did not fire.
- `Original description preserved`: `true` if the restore succeeded (on-disk now matches the pre-tool snapshot), `false` if restoration itself failed (rare — treat as a halt condition in a future version).
- `Notes`: a one-sentence description of what the tool had changed, based on the recorded `description_guard_diff_kind` (`replaced`, `truncated` or `deleted`). Typical values: `"replaced with generic summary"`, `"truncated at N chars"`, `"angle-bracket tokens re-introduced"`, `"field deleted entirely"`. If `Restored: false`, use `—`.

When `Restored: false`, the three follow-up fields are all `—` — this is the clean-run expected state — with one exception: when `description_guard_refused == "empty-capture"` (§0's empty-snapshot rule — `verify-restore` exited 1 and no in-context copy allowed a re-run), the guard did fire and must not render as a clean run. Set `Restored: false`, `Triggering tool` to the recorded tool name, `Original description preserved: false`, and `Notes: guard refused — empty captured snapshot (empty-capture)`.

### 9. Auto-Proceed

No user interaction: this step has no gate. After validation completes, load `{nextStepFile}`, read it fully, then execute it. Tool unavailability, validation failures and every Tessl Review result are recorded as skips and warnings; the step halts only where a section above says HALT — a helper whose probe order says HALT and that no path resolves, the §4 Tier-1 preservation check, and the §6 description check.

