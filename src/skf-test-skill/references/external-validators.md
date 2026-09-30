---
nextStepFile: 'step-hard-gate.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
externalScoreScript: 'scripts/combine-external-scores.py'
# Resolve `{tesslReviewHelper}` by probing `{tesslReviewProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. If neither path exists, §3 records that Tessl Review did not run
# and continues: the review is optional and never gates the workflow.
tesslReviewProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-tessl-review.py'
  - '{project-root}/src/shared/scripts/skf-tessl-review.py'
# Resolve `{tesslReviewRules}` the same way. §3 loads it after a completed
# review to mark the suggestions SKF does not follow; without it the
# suggestions are listed unmarked.
tesslReviewRulesProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/tessl-review.md'
  - '{project-root}/src/shared/references/tessl-review.md'
preferencesFile: '{sidecar_path}/preferences.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4b: External Validators

## STEP GOAL:

Run the external validators — `skill-check` whenever it is installed, and Tessl Review when the user opted in — against the skill directory, capture their scores and findings, and append results to the test report. These tools catch complementary issues that internal coverage and coherence checks miss: `skill-check` validates spec compliance, while Tessl Review's AI judges score the description and the content of the whole skill folder.

### 1. Resolve Skill Directory

Read {outputFile} frontmatter to get the skill directory path (`skillDir`).

### 1b. Check for Recent Validation Results (Auto-Reuse)

Before running external validators, check whether `{forge_evidence_report}`, the evidence report init.md §2 bound (the skill version folder's, or the flat copy an older skill may still keep), contains validation results (a `## Validation Results` section with quality scores). When it is null, go to section 2.

**Staleness check:** Determine whether SKILL.md has changed since the evidence report was generated. Walk through these checks in order:

**Pre-check (untracked or staged-only file):** Run `git ls-files --error-unmatch {skillDir}/SKILL.md 2>/dev/null`.
- If the command fails (exit code non-zero) or git is not available, the file is either **untracked** (new, never committed) or we're in a **non-git environment**:
  - Check if `{skillDir}/metadata.json` exists and has a `generation_date` field
  - Compare `metadata.json` `generation_date` against the evidence report's generation date (from its frontmatter `generated` field or the `## Validation Results` timestamp)
  - **Precision guard (mirror of the git-path Primary-cross check):** date-granularity equality is not proof of same-session generation. A same-day `update-skill` that regenerates SKILL.md *after* the cached evidence report was produced yields the same calendar date (e.g. `metadata.generation_date: 2026-05-23T00:00:00Z` vs evidence `generated: 2026-05-23`), so reusing on date-equality alone would publish pre-update scores for post-update content. Auto-reuse is safe **only** when both timestamps carry a real time-of-day component — neither a date-only string (`2026-05-23`) nor a midnight-coerced `…T00:00:00Z` — AND they match to the minute. In that case auto-reuse: the evidence report was generated from the same SKILL.md content.
  - Otherwise — if either timestamp is date-only or midnight-coerced, if they differ, or if `metadata.json` is missing or has no `generation_date` — treat as stale and proceed to section 2 for a fresh run. Forcing a fresh run on ambiguous precision matches the git path's bias toward freshness over reusing possibly-stale scores.
  - Note: "Staleness check: SKILL.md is untracked/non-git — using metadata.json timestamp comparison (date-only/midnight timestamps force a fresh run)."
- If the command succeeds (file is tracked by git), continue to Primary check below.

**Primary (git-tracked):** Run `git log -1 --format=%cI -- {skillDir}/SKILL.md` to get the last commit date of SKILL.md. Compare against the evidence report's generation date (from its frontmatter or the `## Validation Results` timestamp). If SKILL.md's last commit is newer, results are stale.

**Primary-cross (single-commit bundle detection):** The git-commit-timestamp comparison can return a false "fresh" when `update-skill` commits a regenerated SKILL.md alongside an unchanged `evidence-report.md` in the same commit — both files share the same `%cI` even though the cached validation results inside the evidence report were produced during an earlier run. To catch this, after the Primary check also compare `{skillDir}/metadata.json`'s `generation_date` field against the evidence report's internal `## Validation Results` timestamp (or its frontmatter `generated` field). If `metadata.json.generation_date` is strictly newer than the evidence report's internal validation timestamp, treat results as stale regardless of git commit parity — SKILL.md was regenerated after the cached validation ran, so the scores no longer reflect current content. If `metadata.json` is missing or has no `generation_date`, skip this cross-check and rely on the git comparison alone.

**Secondary (uncommitted changes):** Run `git diff --name-only -- {skillDir}/SKILL.md`. If output is non-empty, SKILL.md has uncommitted changes — treat results as stale regardless of commit dates. Also check `git diff --cached --name-only -- {skillDir}/SKILL.md` for staged-but-uncommitted changes — if non-empty, SKILL.md has been staged since last commit, treat results as stale.

If SKILL.md was modified after the evidence report was generated (e.g., after update-skill), the cached results are stale — skip auto-reuse and proceed to section 2 for a fresh run.

If recent, non-stale results exist (from a create-skill run that just completed), reuse the skill-check result instead of re-running it: take `skill_check_score` from the evidence report's `Schema:` row quality score (N/A when that row says skill-check was unavailable) and the remaining issues from its `## Remaining Warnings`, record "skill-check: reused from create-skill evidence report.", skip section 2 and continue at section 3. Never reuse a Tessl Review result from the evidence report: create-skill reviews the staged skill before step 7 copies its `scripts/` and `assets/`, and older evidence reports carry a `Content Quality (tessl)` row instead. Section 3 decides whether Tessl Review runs on this skill folder, and section 4 combines the scores.

If no evidence report exists, it contains no validation section, or results are stale, proceed to section 2 (fresh run).

### 2. Run skill-check

**Check availability (short probe — 15s timeout):**

```bash
timeout 15s npx --no-install skill-check -h 2>/dev/null
```

Use `--no-install` so the probe never triggers a slow cold-cache download (npx
would otherwise fetch the package before printing help). Wrap in `timeout 15s`
so a hung probe cannot stall the workflow — consistent with the 120s cap used
on the actual validator run below. If the probe exits non-zero OR the 15s
timeout trips (exit code `124`), record `skill_check_score: N/A` and skip to
section 3.

**Run validation (120s timeout):**

```bash
timeout 120s npx skill-check check {skillDir} --format json --no-security-scan
```

If the command exits non-zero AND the exit code is `124` (GNU timeout's signal for the 120s wall-clock expiring), record `skill_check_score: N/A` with reason `timeout-120s`, log a warning, and skip to section 3. Other non-zero exits fall through to the regular JSON-parse path per the note below.

**Parse JSON output** to extract:
- `scores[].score` — overall score (0-100); match the entry by `relativePath` (or `skillId`) to the validated skill dir. Older skill-check builds exposed this as a top-level `qualityScore` — fall back to that if `scores[]` is absent.
- `diagnostics[]` — any remaining issues
- `summary.errorCount` and `summary.warningCount` — issue counts (the counts live under `summary`, not at the top level)

**Note:** `skill-check` may return a non-zero exit code even when `summary.errorCount` is 0. Always rely on the parsed JSON output, not the shell exit code.

Store in context: `skill_check_score`, `skill_check_diagnostics`

**If skill-check fails entirely:** Record `skill_check_score: N/A`, log warning, continue.

### 3. Run Tessl Review (optional)

Tessl Review (`tessl review run`, which the helper below runs on a copy of `{skillDir}`) scores the skill on Tessl's servers with validation checks and two AI judges, one for the description and one for the content. It runs only when the user opted in by setting `tessl_review_workspace` in `{preferencesFile}` to a Tessl workspace name, because it needs a Tessl account, uploads the skill's files to that workspace's review history and spends Tessl credits. The helper applies that setting and every other condition, so run it whenever this section is reached and let it decide; `{tesslReviewRules}` explains what is uploaded and what each result means. It never halts the workflow.

Resolve `{tesslReviewHelper}` ← first existing path in `{tesslReviewProbeOrder}`. If neither path exists, set `{tessl_summary}` to `not run — skf-tessl-review.py is missing` and `{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, log that line as a warning, set `{tessl_review_score}` to null and go to section 4. Otherwise submit the review:

```bash
uv run {tesslReviewHelper} submit "{skillDir}" --preferences "{preferencesFile}"
```

A review takes Tessl about two minutes, so no call waits for all of it. When the review is on, `submit` sends a copy of the skill to Tessl and returns `pending` with Tessl's run id as soon as Tessl accepts it; when it is off or cannot run, `submit` returns that result instead. While `{tessl_status}` is `pending`, collect the review, at most six times, and add `--final` to the sixth call, which turns a review still running into `timeout`:

```bash
uv run {tesslReviewHelper} collect "{tessl_run_id}" --workspace "{tessl_workspace}" --tessl-version "{tessl_version}"
```

Each call ends within two minutes (a `collect` checks the review for up to 90 seconds, then returns `pending` again or the result), so run each one with your shell tool's default time limit. If the shell tool stops a call before it prints its JSON, or it prints none, make that the last call: set `{tessl_status}` to `failed`, `{tessl_summary}` to `failed — stopped before skf-tessl-review.py reported a result` and `{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, keep `{tessl_run_id}` and the other values the calls before it bound, log that line as a warning, set `{tessl_review_score}` to null and go to section 4. Otherwise rely on the JSON, not the exit code, and bind these from the `submit` JSON and again from each `collect` JSON, whose values replace the earlier ones:

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

Every key is always present: the scores and `{tessl_validation}` are null and the suggestion lists are empty unless `{tessl_status}` is `reviewed`, and `{tessl_run_id}` is null until Tessl has accepted the review, so section 4 receives a null `{tessl_review_score}` whenever Tessl Review produced no score. After the last call, log each entry of `{tessl_warnings}` as a warning: a score below 60%, validation errors or, for any status other than `reviewed` and `off`, why the review produced no score. When `{tessl_status}` is `reviewed`, resolve `{tesslReviewRules}` ← first existing path in `{tesslReviewRulesProbeOrder}`, load it, and mark each entry of `{tessl_content_suggestions}` that one of its rules matches with `(not applicable: <rule-id>)`; if neither path exists, list the suggestions unmarked.

### 4. Calculate Combined External Score

The combined external score feeds `externalValidation` into the scoring script (step 5), so its mean is computed by a script, not in-prompt. Both scores are on the same 0-100 scale (skill-check's quality score; the Tessl Review score). Pass `skill_check_score` as `skillCheckScore` and `{tessl_review_score}` as `tesslReviewScore`, each `null` when its tool produced no score (`{externalScoreScript}` resolves relative to the skill root):

```bash
echo '{"skillCheckScore": <score or null>, "tesslReviewScore": <score or null>}' | uv run {externalScoreScript} --stdin
```

Read the result — do not re-average by hand. Bind `{external_score}` ← `externalScore` (the mean when both tools produced a score, the single score when one did, or `null` when neither did: the scoring step then redistributes the external-validation weight) and `{external_tools_used}` ← `toolsUsed` (`skill-check`, and `tessl` for Tessl Review). Record `external_score: N/A` when `{external_score}` is null.

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

### Tessl Review
- **Result:** {tessl_summary}
- **Review Score:** {tessl_review_score}%
- **Description Score:** {tessl_description_score}%
- **Content Score:** {tessl_content_score}%
- **Validation Findings:** {each {tessl_validation} finding as `name (status): message`, or "none"}
- **Run:** {tessl_run_id} in workspace `{tessl_workspace}` (tessl {tessl_version})
- **Description Suggestions** (edit the description in the brief to act on one): {each of {tessl_description_suggestions}, or "none"}
- **Content Suggestions** (advisory): {each of {tessl_content_suggestions} with its `(not applicable: <rule-id>)` mark, or "none"}

### Combined External Score
- **External Validation Score:** {external_score}%
- **Tools used:** {external_tools_used}
```

When `{tessl_status}` is not `reviewed`, the Tessl Review block holds only its Result line and, when `{tessl_run_id}` is set, its Run line, so the report names the run of a review that may still finish.

### 6. Report Results

Report the external validation result to the user: skill-check's score out of 100 (or `skipped`), the line `Tessl Review: {tessl_summary}`, the combined external score, and each entry of `{tessl_warnings}` as a warning. Then proceed to scoring.

Update stepsCompleted, then load and execute {nextStepFile}.

