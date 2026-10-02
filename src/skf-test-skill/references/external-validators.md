---
nextStepFile: 'step-hard-gate.md'
outputFile: '{report_file}'
externalScoreScript: 'scripts/combine-external-scores.py'
outputFormatsFile: 'assets/output-section-formats.md'
scoringRulesFile: 'references/scoring-rules.md'
# §5b records the validators' findings in the run's gap ledger, which the
# hard gate (step 4c) reads and the Gap Report is rendered from.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
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

Run the external validators (`skill-check` whenever it is installed, and Tessl Review when the user opted in) against the skill directory, capture their scores and findings, and write their results into the test report. These tools catch complementary issues that internal coverage and coherence checks miss: `skill-check` validates spec compliance, while Tessl Review's AI judges score the description and the content of the whole skill folder.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Resolve Skill Directory

Read {outputFile} frontmatter to get the skill directory path (`skillDir`).

### 2. Run skill-check

Run skill-check fresh on every test: a score cached in an evidence report can predate the SKILL.md under test, so no earlier result is reused.

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
echo '{"skillCheckScore": <score or null>, "tesslReviewScore": <score or null>}' | uv run {externalScoreScript} --stdin --output "{run_dir}/external.json"
```

`--output` also writes the result to the run folder, where step 5 hands it to the scoring script; run the command even when neither tool produced a score. Read the result: do not re-average by hand. Bind `{external_score}` ← `externalScore` (the mean when both tools produced a score, the single score when one did, or `null` when neither did: the scoring step then redistributes the external-validation weight) and `{external_tools_used}` ← `toolsUsed` (`skill-check`, and `tessl` for Tessl Review). Record `external_score: N/A` when `{external_score}` is null.

### 5. Write the External Validation Section

Write this section in place of the template's `## External Validation` heading and the placeholder comment under it, in `{outputFile}`:

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

### 5b. Record the External Validation Gaps

Record the validators' findings in the gap ledger `{ledgerFile}`, so the Gap Report lists them beside the coverage and coherence gaps. Each is one record in the Ledger Record Format of `{outputFormatsFile}`, with the severity and category the Gap Severity table (`{scoringRulesFile}`) gives it:

- each entry of `skill_check_diagnostics`: a Low `external-validator` gap, with the file and line it names as its Source (else `SKILL.md`) and its message as the Issue;
- each `{tessl_validation}` finding: a Low `external-validator` gap, titled `Tessl Review: {name}`, with `SKILL.md` as its Source and its message as the Issue;
- each of `{tessl_description_suggestions}`: a Low `description` gap titled with the suggestion, with the SKILL.md frontmatter `description` as its Source;
- each of `{tessl_content_suggestions}` not marked `(not applicable: <rule-id>)`: an Info `external-validator` gap titled with the suggestion, with `SKILL.md` as its Source.

Write the records as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`), as it is when neither validator ran: the hard gate refuses to decide until every stage before it has recorded, with gaps or without (`{gapLedgerScript}` resolves relative to the skill root).

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage external-validators <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on its JSON:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0) and run the command again.
- Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `external-validators:ledger`).

### 6. Report Results

Report the external validation result to the user: skill-check's score out of 100 (or `skipped`), the line `Tessl Review: {tessl_summary}`, the combined external score, and each entry of `{tessl_warnings}` as a warning. Then proceed to the hard gate.

Append `'external-validators'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.

