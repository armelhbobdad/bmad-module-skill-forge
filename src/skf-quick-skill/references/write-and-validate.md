---
nextStepFile: 'finalize.md'
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
outputValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
securityScanProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-security-scan.py'
  - '{project-root}/src/shared/scripts/skf-security-scan.py'
validationSummaryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-summarize-validation.py'
  - '{project-root}/src/shared/scripts/skf-summarize-validation.py'
---

<!-- Config: communicate in {communication_language}. Generated SKILL.md text in {document_output_language}. -->

# Step 5: Write & Validate

## STEP GOAL:

To write the compiled SKILL.md, context-snippet.md, and metadata.json to the versioned skill package, then validate them on disk against the agentskills.io specification at community tier. Validation is advisory: issues are reported but do not block the workflow.

## Rules

- Write exactly what was compiled — do not modify content during writing or after validation
- Community-tier validation (lighter than official requirements)
- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).
- Bind each `{<stem>}` or `{<stem>Helper}` this step runs ← `helpers.<stem>` in the `helpers.json` SKILL.md On Activation step 1 wrote: in `{run_dir}`, or under `--batch` in the batch folder that holds it, the parent folder of `{run_dir}`. Take the first existing path in the `<stem>ProbeOrder` array above only when that file holds no `<stem>`. Each step below that resolves a helper from its probe order binds it by this rule; its halt or fallback for a helper with no path still applies, and fires only when neither the file nor the probe order names a path that exists, as when the helper was removed after activation.

## Steps

### 1. Check Ownership, Then Create Output Directory

Resolve `{version}` ← the `version` of `{run_dir}/metadata.json`, which step 4 §4 rendered: the version the target pinned, else the manifest's, else `1.0.0`. The version folder and the file's `version` are then one value.

**Ownership check.** Run it before creating any directory and before the overwrite prompt below. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {repo_name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

`--forge-data-folder` only tells the helper whether both settings name one folder.

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder`, `{write_detail}` ← `write_check.detail`, and `{existing_generator}` ← `write_check.version_generated_by` and `{existing_tier}` ← `write_check.version_confidence_tier` (the build already at `{version}`, each null when none names it). Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{repo_name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {repo_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{repo_name}` is not SKF output — nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{repo_name}` yourself, and Quick Skill names a skill after its target, so to create it under another name, brief it with `@Ferris BS` and compile it with `@Ferris CS`. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted quick-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}".

Each refusal is a HARD HALT with **exit code 9 (state-conflict)**: stage `{"phase": "write-and-validate", "halt_reason": "<the halt reason>", "reason": "<the message's first sentence>", "skill_package": null, "details": {"folder": "<the folder the message names>"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, with no `--result-dir` (`references/halt-contract.md`). This halt writes no result file on disk: `{skill_package}` would sit in a folder SKF did not generate. It is a HALT, not a gate, so it has no headless default.

Then create the skill output directories:

```
{skill_group}                          # {skills_output_folder}/{repo_name}/
{skill_package}                        # {skills_output_folder}/{repo_name}/{version}/{repo_name}/
```

If `{skill_package}/metadata.json` exists, confirm with user before overwriting:

"**Directory `{skill_package}` already exists.** It holds a `{existing_generator}` build ({existing_tier}); overwriting replaces it whole with a community quick skill, and validation results, result contracts, and any manual tweaks from the previous run will not be preserved. Overwrite existing files? [Y/N]" (say "an SKF build" in place of "a `{existing_generator}` build ({existing_tier})" when `{existing_generator}` is null, and leave out " ({existing_tier})" when only `{existing_tier}` is null).

- **If user selects Y:** when `{existing_generator}` is neither `quick-skill` nor null, remove the old package first, so none of its files (create-skill's `references/` and `extraction-rules.yaml`, for example) stays beside the quick skill, and set `{replaced_build}` ← `{existing_generator}` for step 6's summary. The `case` guard removes nothing unless the path is this skill's version package:

  ```bash
  case "{skill_package}" in */{repo_name}/{version}/{repo_name}) rm -rf "{skill_package}" && mkdir -p "{skill_package}" ;; esac
  ```

  Proceed to section 2.
- **If user selects N:** HARD HALT with **exit code 5 (overwrite-cancelled)**: "Overwrite cancelled. Existing skill preserved. Quick Skill names a skill after its target, so to create it under another name, brief it with `@Ferris BS` and compile it with `@Ferris CS`; or remove the existing directory yourself and re-run." Stage `{"phase": "write-and-validate", "halt_reason": "overwrite-cancelled", "reason": "Overwrite cancelled. Existing skill preserved.", "skill_package": "{skill_package}", "details": {"existing_generator": "{existing_generator}"}}` as `{run_dir}/halt.json` (`existing_generator` null when none names it) and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`: `{skill_package}` holds `metadata.json`, so the emitter also writes the `-latest.json` envelope there; a caller still reads the run's own `SKF_QUICK_SKILL_RESULT_JSON` line, never that copy in its place.

**GATE [default: Y]** when `{existing_generator}` is `quick-skill` or null: if `{headless_mode}` is true, auto-proceed with Y, log "headless: overwriting existing `{skill_package}`", and record the decision: stage `{"gate": "write-and-validate.overwrite", "default_action": "Y", "taken_action": "Y", "reason": "headless: overwrote the existing package", "evidence": {"skill_package": "{skill_package}"}}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

**GATE [default: N]** for any other `{existing_generator}`, so no headless run or batch replaces another workflow's build with a quick skill: if `{headless_mode}` is true, record the decision: stage `{"gate": "write-and-validate.overwrite", "default_action": "N", "taken_action": "N", "reason": "headless: kept the {existing_generator} build", "evidence": {"skill_package": "{skill_package}", "existing_generator": "{existing_generator}"}}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`, then halt as **If user selects N** does, with the message "**Kept the `{existing_generator}` build at `{skill_package}`.** A headless run never replaces another workflow's build with a quick skill. To replace it, run Quick Skill interactively and answer Y; to keep it, give the quick skill another version (`@Ferris QS <package>@<version>`)." and the `reason` "Kept the {existing_generator} build: a headless run never replaces another workflow's build".

A `{skill_package}` without `metadata.json` holds only what an interrupted run leaves (the ownership check refuses anything else), so it is written without asking.

### 2. Write Deliverables

Write the three compiled artifacts to the skill package in this order, `metadata.json` first, so a run interrupted mid-write leaves a package that carries the SKF marker, which the next run's ownership check accepts:

1. `{skill_package}/metadata.json`: installed from the file step 4 §4 rendered, never typed again. Resolve `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` and run:

   ```bash
   uv run {atomicWriteHelper} write --target "{skill_package}/metadata.json" < "{run_dir}/metadata.json"
   ```

   It writes the file in place atomically, so an interrupted run never leaves half a `metadata.json`. If no candidate exists, write nothing and HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too: "**Nothing was written to `{skill_package}`.** SKF's atomic writer (`skf-atomic-write.py`) is missing from `{project-root}/_bmad/skf/shared/scripts/`, so re-install SKF." Stage `{"phase": "write-and-validate", "halt_reason": "resolution-failure", "reason": "Nothing was written: the atomic writer is missing.", "skill_package": "{skill_package}", "details": {"cause": "atomic-writer-missing"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`, without `--result-dir "{skill_package}"` when no earlier run's `metadata.json` is there (`references/halt-contract.md`).
2. `{skill_package}/SKILL.md`: the compiled skill document.
3. `{skill_package}/context-snippet.md`: the compressed context snippet. **Skip this write** if `{overrides.skip_snippet}` was set; the artifact is omitted from `outputs`.

Confirm after each write: "Written: metadata.json" / "Written: SKILL.md" / "Written: context-snippet.md". When `--skip-snippet` is active, log "Skipped: context-snippet.md (--skip-snippet)" instead of the snippet write confirmation.

**If any write fails, HARD HALT (exit code 4, write-failure):** stage `{"phase": "write-and-validate", "halt_reason": "write-failure", "reason": "Write failed: could not write <path>.", "skill_package": "{skill_package}", "outputs": {<each file that did write before the failure, as "metadata", "skill_md" or "context_snippet" with its path>}, "details": {"failed_path": "<path>", "error": "<details>"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`. When `metadata.json` itself failed to write, run it without `--result-dir "{skill_package}"`: the contract writes no result file on disk, because a package holding only result files would read as not SKF output to the next run's ownership check.

"**Write failed:** Could not write to `{file_path}`.

Error: {error details}

Check:
- Does the output directory exist and is it writable?
- Is there sufficient disk space?
- Are there permission issues?"

### 3. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds (returns usage information): Continue to automated validation (section 4)
- If fails (command not found or error): skip to the frontmatter validator in section 4; the security scan at the end of section 4 still runs

### 4. Validate SKILL.md via skill-check (if available)

**If `npx skill-check` is available**, run validation against the skill package written in section 2. `--fix` can also rewrite the frontmatter `description` the user approved in step 4, which would leave SKILL.md out of step with `metadata.json`, so the call runs inside the description guard. Resolve `{descriptionGuardHelper}` ← first existing path in `{descriptionGuardProbeOrder}` and `{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}`, then run the five commands in order. `verify-restore` runs whatever skill-check exits; note that exit code:

```bash
uv run {hashContentHelper} hash "{skill_package}/SKILL.md" > "{run_dir}/skill-md-hash-before.json"
uv run {descriptionGuardHelper} capture "{skill_package}/SKILL.md" > "{run_dir}/description-guard.json"
npx skill-check check "{skill_package}" --fix --format json --no-security-scan > "{run_dir}/skill-check.json" 2> "{run_dir}/skill-check.stderr"; echo "skill-check exited $?"
uv run {descriptionGuardHelper} verify-restore "{skill_package}/SKILL.md" --captured-file "{run_dir}/description-guard.json"
uv run {hashContentHelper} hash "{skill_package}/SKILL.md" > "{run_dir}/skill-md-hash-after.json"
```

**If no "skill-check exited" line came back**, the shell tool stopped the block before skill-check finished: run the `verify-restore` command on its own before reading `{run_dir}/skill-check.json`, so a description `--fix` rewrote is restored, then run the second `hash` command.

**Guard outputs.** `capture` stages the approved description in `{run_dir}/description-guard.json` and `verify-restore` reads it there, so it never passes through a shell string. Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from `verify-restore`. When `{guard_restored}` is true, the approved description is back in SKILL.md, matching `metadata.json`: record the validation note "description restored after `skill-check --fix` ({guard_diff_kind})", which §6 lists with the auto-fixed issues. `verify-restore` refuses an empty or whitespace-only captured description, and a file it cannot read (exit 1, SKILL.md untouched): re-run it with `--captured-file "{skill_package}/metadata.json"`, whose `description` step 4 rendered, never with an empty value, and if that exits 1 too, record a high-severity issue: the guard could not check the description. When it exits 2 with JSON on stdout (the JSON carries `restore_error`), the restore could not be written, so record a high-severity issue: SKILL.md's description no longer matches `metadata.json`.

**Rewrite note.** skill-check's JSON lists no fix, so the two `hash` commands tell whether `--fix` changed SKILL.md. Bind `{skill_md_changed}` ← true when the `content_hash` in `{run_dir}/skill-md-hash-before.json` differs from the one in `{run_dir}/skill-md-hash-after.json`, taken after the last `verify-restore` (run the second `hash` command again after a `verify-restore` re-run). When no `{hashContentProbeOrder}` path exists (leave both `hash` commands out) or either file holds no `content_hash`, SKILL.md was not hashed: bind `{skill_md_changed}` ← true as well. When `{skill_md_changed}` is true, record the validation note "skill-check --fix rewrote SKILL.md", or "SKILL.md may have been rewritten (not hashed) by skill-check --fix" when it was not hashed, which §6 lists with the auto-fixed issues. When the block above did not run at all (§3 found no skill-check, or the guard below is missing), `--fix` did not run: hash nothing and bind `{skill_md_changed}` ← false.

**If no `{descriptionGuardProbeOrder}` path exists**, never run `--fix` unguarded. Run `npx skill-check check "{skill_package}" --format json --no-security-scan` instead, which validates without fixing, with the same capture (`> "{run_dir}/skill-check.json" 2> "{run_dir}/skill-check.stderr"`, its exit code noted), and log the validation issue "description guard unavailable (`skf-description-guard.py` missing): skill-check ran without `--fix`".

**If `{run_dir}/skill-check.json` does not start with a JSON object**, skill-check stopped before it validated (exit 2 on a config, option or plugin error): log "skill-check failed: {the stderr line that names the cause, or its last line}" and run the frontmatter validator below, as when skill-check is not available. Otherwise skill-check validated, even when its stdout goes on after the JSON (a `Wrote <path>` line when the project config sets a report path): §6 reads the score and the remaining diagnostics from that JSON.

**Read the JSON, not the exit code.** skill-check prints its JSON, then exits 1 when `summary.errorCount` is above 0, or when `--strict` or `--fail-on-warning` is passed and `summary.warningCount` is above 0 (this call passes neither), so `summary.errorCount` alone is the validation verdict. `--no-security-scan` keeps the security scan out of this call: skill-check 1.2.0 writes its JSON before the scan runs and passes none of the scanner's findings on, so the scan runs on its own at the end of this section.

**If skill-check is not available**, run the shared frontmatter validator. Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}`; first existing path wins. If no candidate exists, nothing can check the frontmatter: HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too: "**`{skill_package}` was written but not validated.** skill-check is unavailable and SKF's frontmatter validator (`skf-validate-frontmatter.py`) is missing from `{project-root}/_bmad/skf/shared/scripts/`, so re-install SKF, then re-run." Stage `{"phase": "write-and-validate", "halt_reason": "resolution-failure", "reason": "The skill was written but not validated: the frontmatter validator is missing.", "skill_package": "{skill_package}", "outputs": {<each deliverable §2 wrote, as "metadata", "skill_md" or "context_snippet" with its path>}, "details": {"cause": "frontmatter-validator-missing"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`.

```bash
uv run {frontmatterValidator} "{skill_package}/SKILL.md" --skill-dir-name {repo_name} > "{run_dir}/frontmatter.json"
```

The validator writes its JSON, with `status` (`pass`/`fail`), `issues[]` (each with `severity`, `field` and `message`) and `frontmatter` (the parsed name and description), to `{run_dir}/frontmatter.json`, where §6 reads the issues.

**Security scan.** Run it whether or not skill-check ran. Resolve `{securityScanHelper}` ← first existing path in `{securityScanProbeOrder}` and run it on the written package, with the longest timeout your shell tool takes (it ends within two minutes):

```bash
uv run {securityScanHelper} run --package "{skill_package}" > "{run_dir}/security.json"
```

It runs Snyk Agent Scan, at the version it pins, only when `SNYK_TOKEN` is set, and reads the scanner's own JSON report, so rely on the JSON it prints, never on an exit code. Bind `{security_result}` ← its `security_result` (`pass`, `warn` or `skipped`) and `{security_note}` ← its `note` in `{run_dir}/security.json`, whose `findings[]` §6 lists as advisory validation issues: security findings do not block output. For `skipped`, log "security scan skipped: {security_note}" in the validation results. When no `{securityScanProbeOrder}` path exists, bind `{security_result}` ← `skipped` and `{security_note}` ← `skf-security-scan.py missing`; when the file holds no JSON object, bind `skipped` and `skf-security-scan.py printed no result`. Log either one as a skipped scan.

### 5. Validate Body, Snippet, and Metadata via skf-validate-output.py

Run the shared output validator against the on-disk skill package — it performs the body-structure, snippet-format, and metadata-shape checks. Pass `--skip-frontmatter` since §4 has already covered frontmatter.

**Resolve `{outputValidator}`** from `{outputValidatorProbeOrder}`; first existing path wins. If no candidate exists, HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too: "**`{skill_package}` was written but not validated.** SKF's output validator (`skf-validate-output.py`) is missing from `{project-root}/_bmad/skf/shared/scripts/`, so re-install SKF, then re-run." Stage `{"phase": "write-and-validate", "halt_reason": "resolution-failure", "reason": "The skill was written but not validated: the output validator is missing.", "skill_package": "{skill_package}", "outputs": {<each deliverable §2 wrote, as "metadata", "skill_md" or "context_snippet" with its path>}, "details": {"cause": "output-validator-missing"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`. Otherwise run:

```bash
uv run {outputValidator} "{skill_package}" --generated-by quick-skill --skip-frontmatter > "{run_dir}/output.json"
```

The validator writes its JSON, with `result` (PASS/FAIL), `validation.skill_md.body[]`, `validation.context_snippet.issues[]`, `validation.metadata.issues[]` and a severity-bucketed `summary`, to `{run_dir}/output.json`, where §6 reads the issues.

### 6. Report Validation Results

Resolve `{validationSummaryHelper}` ← first existing path in `{validationSummaryProbeOrder}`. If no candidate exists, HARD HALT with **exit code 3 (resolution-failure)**, in interactive mode too: "**`{skill_package}` was written and validated, but its validation was not summarized.** SKF's validation summarizer (`skf-summarize-validation.py`) is missing from `{project-root}/_bmad/skf/shared/scripts/`, so re-install SKF, then re-run." Stage `{"phase": "write-and-validate", "halt_reason": "resolution-failure", "reason": "The skill was written and validated, but its validation was not summarized: the validation summarizer is missing.", "skill_package": "{skill_package}", "outputs": {<each deliverable §2 wrote, as "metadata", "skill_md" or "context_snippet" with its path>}, "details": {"cause": "validation-summarizer-missing"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`. Otherwise summarize the files §4 and §5 saved, from the folder §4 ran skill-check in. Pass every flag on every path: a file no check wrote counts nothing.

```bash
uv run {validationSummaryHelper} --skill-check "{run_dir}/skill-check.json" --frontmatter "{run_dir}/frontmatter.json" --output "{run_dir}/output.json" --security "{run_dir}/security.json" --skill-dir "{skill_package}" > "{run_dir}/validation-summary.json"
```

Bind `{quality_score}` ← `quality_score` (skill-check's score for this skill, null when skill-check did not validate it or reported no score) and `{validation_issues}` ← `validation_issues` from `{run_dir}/validation-summary.json`. Under the SKILL.md, context-snippet.md, metadata.json and Security headings below, list the entries of that file's `issues.skill_md`, `issues.context_snippet`, `issues.metadata` and `issues.security`, each with its `check`, `severity`, `message` and `line`: the issues the counts count. List beside them the notes §4 recorded, which count nothing: the rewrite note, the guard note, "skill-check failed", "description guard unavailable" and the guard's high-severity issues.

"**Validation complete:**

**SKILL.md:** {pass/issues found}{ (quality score: {quality_score}/100), only when `{quality_score}` is not null}
{list any issues}
{list the auto-fixed issues: the §4 rewrite note when `{skill_md_changed}` is true, and the §4 description-guard note when the guard restored the description}

**context-snippet.md:** {pass/issues found}
{list any issues}

**metadata.json:** {pass/issues found}
{list any issues}

**Security:** {security_result}
{`{security_note}`, then each §4 security finding}

**Overall:** {pass / N issues found}

{If issues found:}
These issues are advisory for community-tier skills: fix them in the written files, or re-run Quick Skill once the source or the hints change.

**Proceeding to finalize...**"

Step 6 §3's summary carries `{quality_score}`, `{validation_issues}` and `{security_result}`.

### 7. Auto-Proceed to Finalize

Once deliverables are written to `{skill_package}` and validation is reported (advisory), load and execute {nextStepFile} to finalize; when `{headless_mode}` is true, print this step's `done` event and step 6's `start` event first (`references/halt-contract.md`).

