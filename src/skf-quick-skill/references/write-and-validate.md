---
nextStepFile: 'finalize.md'
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
outputValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
# Resolve `{descriptionGuardHelper}` by probing `{descriptionGuardProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §4 runs `skill-check --fix` between its capture and
# verify-restore calls; if neither path resolves, §4 runs skill-check without
# `--fix` and logs a validation issue rather than fixing unguarded.
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
# Resolve `{skillInventoryHelper}` by probing `{skillInventoryProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §1 runs its write check before any directory is
# created; without it, §1 writes only into a skill folder that does not exist yet.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. Generated SKILL.md text in {document_output_language}. -->

# Step 5: Write & Validate

## STEP GOAL:

To write the compiled SKILL.md, context-snippet.md, and metadata.json to the versioned skill package, then validate them on disk against the agentskills.io specification at community tier. Writing happens here (before step 6 finalization) because `skill-check` is a file-based CLI — it reads artifacts from disk — so the files must exist before validation runs. Report any gaps or issues. Validation is advisory — issues are reported but do not block the workflow.

## Rules

- Write exactly what was compiled — do not modify content during writing or after validation
- Community-tier validation (lighter than official requirements)
- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

### 1. Check Ownership, Then Create Output Directory

Resolve `{version}` from the extraction inventory's detected version, defaulting to `1.0.0` if not detected.

**Ownership check.** Run it before creating any directory and before the overwrite prompt below. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {repo_name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

`--forge-data-folder` only tells the helper whether both settings name one folder.

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder` and `{write_detail}` ← `write_check.detail`. Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{repo_name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {repo_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{repo_name}` is not SKF output — nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{repo_name}` yourself, and Quick Skill names a skill after its target, so to create it under another name, brief it with `@Ferris BS` and compile it with `@Ferris CS`. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted quick-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}".

Each refusal is a HARD HALT with **exit code 9 (state-conflict)**: stage `{"phase": "write-and-validate", "halt_reason": "<the halt reason>", "reason": "<the message's first sentence>", "skill_package": null, "error": {"code": "<the halt reason>", "message": "<the same sentence>", "details": {"folder": "<the folder the message names>"}}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, with no `--result-dir` (`references/halt-contract.md`). This halt writes no result file on disk: `{skill_package}` would sit in a folder SKF did not generate. It is a HALT, not a gate, so it has no headless default.

Then create the skill output directories:

```
{skill_group}                          # {skills_output_folder}/{repo_name}/
{skill_package}                        # {skills_output_folder}/{repo_name}/{version}/{repo_name}/
```

If `{skill_package}/metadata.json` exists, confirm with user before overwriting:

"**Directory `{skill_package}` already exists.** Overwrite will replace the prior compiled output; validation results, result contracts, and any manual tweaks from the previous run will not be preserved. Overwrite existing files? [Y/N]"

- **If user selects Y:** Proceed to section 2.
- **If user selects N:** HARD HALT with **exit code 5 (overwrite-cancelled)**: "Overwrite cancelled. Existing skill preserved. Run [QS] with a different skill name or remove the existing directory manually." Stage `{"phase": "write-and-validate", "halt_reason": "overwrite-cancelled", "reason": "Overwrite cancelled. Existing skill preserved.", "skill_package": "{skill_package}"}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`: `{skill_package}` holds `metadata.json`, so the emitter also writes the `-latest.json` envelope there, and consumers that hardcode that path see a deterministic file even on this cancelled run.

**GATE [default: Y]**: if `{headless_mode}` is true, auto-proceed with Y, log "headless: overwriting existing `{skill_package}`", and record the decision: stage `{"gate": "write-and-validate.overwrite", "default_action": "Y", "taken_action": "Y", "reason": "headless: overwrote the existing package", "evidence": {"skill_package": "{skill_package}"}}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

A `{skill_package}` without `metadata.json` holds only what an interrupted run leaves (the ownership check refuses anything else), so it is written without asking.

### 2. Write Deliverables

Write File 3 (`metadata.json`) first, so a run interrupted mid-write leaves a package that carries the SKF marker, which the next run's ownership check accepts.

Write the three compiled artifacts to the skill package so that validation in sections 3–7 has files on disk to read:

**File 1:** `{skill_package}/SKILL.md` — the compiled skill document
**File 2:** `{skill_package}/context-snippet.md` — the compressed context snippet. **Skip this write** if `{overrides.skip_snippet}` was set; the artifact is omitted from `outputs`.
**File 3:** `{skill_package}/metadata.json` — the machine-readable metadata

Confirm after each write: "Written: SKILL.md" / "Written: context-snippet.md" / "Written: metadata.json". When `--skip-snippet` is active, log "Skipped: context-snippet.md (--skip-snippet)" instead of the snippet write confirmation.

**If any write fails, HARD HALT (exit code 4, write-failure):** stage `{"phase": "write-and-validate", "halt_reason": "write-failure", "reason": "Write failed: could not write <path>.", "skill_package": "{skill_package}", "outputs": {<each file that did write before the failure, as "metadata", "skill_md" or "context_snippet" with its path>}, "error": {"code": "write-failure", "message": "Write failed: could not write <path>.", "details": {"failed_path": "<path>", "error": "<details>"}}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"`. When `metadata.json` itself failed to write, run it without `--result-dir "{skill_package}"`: the contract writes no result file on disk, because a package holding only result files would read as not SKF output to the next run's ownership check.

"**Write failed:** Could not write to `{file_path}`.

Error: {error details}

Check:
- Does the output directory exist and is it writable?
- Is there sufficient disk space?
- Are there permission issues?"

### 3. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds (returns usage information): Continue to automated validation (section 4)
- If fails (command not found or error): Skip to manual fallback in section 4

### 4. Validate SKILL.md via skill-check (if available)

**If `npx skill-check` is available**, run automated validation + security scan in one invocation against the skill package written in section 2 (security scan is enabled by default when `--no-security-scan` is omitted, so the same call covers §6 and avoids paying the npx startup cost twice). `--fix` can also rewrite the frontmatter `description` the user approved in step 4, which would leave SKILL.md out of step with `metadata.json`, so the call runs inside the description guard. Resolve `{descriptionGuardHelper}` ← first existing path in `{descriptionGuardProbeOrder}`, then run the three commands in order:

```bash
uv run {descriptionGuardHelper} capture {skill_package}/SKILL.md
npx skill-check check {skill_package} --fix --format json
uv run {descriptionGuardHelper} verify-restore {skill_package}/SKILL.md \
    --captured-description '{guarded_description}'
```

The skill-check call validates frontmatter, description, body limits, links, and formatting; runs the security scan; and auto-fixes deterministic issues (field ordering, slug format, required fields, trailing newlines).

**Guard outputs.** Bind `{guarded_description}` ← `description` from `capture`, and `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from `verify-restore`. When `{guard_restored}` is true, the approved description is back in SKILL.md, matching `metadata.json`: record the validation note "description restored after `skill-check --fix` ({guard_diff_kind})", which §7 lists with the auto-fixed issues. Put `{guarded_description}` between the single quotes as captured, writing each `'` in it as `'\''`: a description often holds double quotes, backticks or `$`, which would split or rewrite a double-quoted argument. `verify-restore` refuses an empty or whitespace-only `--captured-description` (exit 1, file untouched): re-run it with the description compiled in step 4, never with the empty value. When it exits 2 with JSON on stdout (the JSON carries `restore_error`), the restore could not be written, so record a high-severity issue: SKILL.md's description no longer matches `metadata.json`. An exit 2 with no JSON on stdout is a usage error from a mangled call, not a failed write: fix the quoting and run it again.

**If no `{descriptionGuardProbeOrder}` path exists**, never run `--fix` unguarded. Run `npx skill-check check {skill_package} --format json` instead, which validates and scans without fixing, and log the validation issue "description guard unavailable (`skf-description-guard.py` missing): skill-check ran without `--fix`".

**Parse JSON output** to extract:
- `scores[].score` — overall score (0-100); match the entry by `relativePath`/`skillId`
- `diagnostics[]` — remaining issues after auto-fix
- `fixed[]` — issues automatically corrected
- `security[]` (when present) — security findings, recorded as advisory warnings (security issues do not block output)

Bind `{quality_score}` ← that score, and record the remaining diagnostics and security findings as validation issues. `{quality_score}` is null when skill-check did not run.

**If skill-check is not available**, run the shared frontmatter validator. Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}`; first existing path wins. If no candidate exists, log a high-severity issue ("frontmatter validator unavailable — both `npx skill-check` and `skf-validate-frontmatter.py` missing") and skip frontmatter validation.

```bash
uv run {frontmatterValidator} {skill_package}/SKILL.md --skill-dir-name {repo_name}
```

The validator emits JSON with `status` (`pass`/`fail`), `issues[]` (each with `severity`, `code`, `message`), and `frontmatter` (the parsed name/description). It checks frontmatter delimiters, name format (Unicode letters + digits + hyphens, no consecutive/trailing hyphens), name-directory match, description presence and length, and unknown fields against the agentskills.io spec. Record each `issues[]` entry as a validation issue with its reported severity. Missing frontmatter or missing required fields are high-severity — skills without valid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 5. Validate Body, Snippet, and Metadata via skf-validate-output.py

Run the shared output validator against the on-disk skill package — it performs the body-structure, snippet-format, and metadata-shape checks. Pass `--skip-frontmatter` since §4 has already covered frontmatter.

**Resolve `{outputValidator}`:** probe `{outputValidatorProbeOrder}` (installed first, dev fallback); first existing path wins. If neither candidate exists, log a high-severity issue ("output validator unavailable — `skf-validate-output.py` missing") and skip body/snippet/metadata validation.

```bash
python3 {outputValidator} {skill_package} --generated-by quick-skill --skip-frontmatter
```

The validator emits JSON with `result` (PASS/FAIL), `validation.skill_md.body[]`, `validation.context_snippet.issues[]`, `validation.metadata.issues[]`, and a severity-bucketed `summary`. Record each issue as a validation issue at its reported severity.

The validator covers:

- **Body structure** — Overview, Description, Key Exports, Usage sections present (medium when missing)
- **Context snippet** — `[{name} v{version}]|root: ...` first line, `|IMPORTANT:` second line, ~80–120-token length
- **Metadata** — required string fields (`name`, `version`, `source_authority`, `language`, `generation_date`), `source_repo`, `generated_by`, `confidence_tier`, and `stats` numerics (`exports_documented`, `exports_public_api`, `exports_total`, `public_api_coverage`, `total_coverage`)

### 6. Security Scan (covered by §4)

Security findings are already collected from the §4 invocation (no separate `npx` round trip needed — `skill-check check ... --fix --format json` runs the security scan by default). If skill-check was unavailable in §3, log "security scan skipped — skill-check unavailable" in validation results.

### 7. Report Validation Results

"**Validation complete:**

**SKILL.md:** {pass/issues found} (quality score: {score}/100 if skill-check was available)
{list any issues}
{list any auto-fixed issues, and the §4 description-guard note when the guard restored the description}

**context-snippet.md:** {pass/issues found}
{list any issues}

**metadata.json:** {pass/issues found}
{list any issues}

**Security:** {pass/warn/skipped}
{list any security findings}

**Overall:** {pass / N issues found}

{If issues found:}
These issues are advisory for community-tier skills. You can proceed to finalize or go back to adjust.

**Proceeding to finalize...**"

Set `validation_result` with pass/fail status, quality score, and issues list, and `{validation_issues}` ← `{"skill_md": <n>, "context_snippet": <n>, "metadata": <n>, "security": <n>}`, each `<n>` the number of entries the validators returned for that heading: `skill_md` counts skill-check's `diagnostics[]` (without skill-check, the frontmatter validator's `issues[]`) plus `validation.skill_md.body[]`; `context_snippet` counts `validation.context_snippet.issues[]`; `metadata` counts `validation.metadata.issues[]`; `security` counts skill-check's `security[]`. A check that did not run counts 0, and `fixed[]` and the guard note count nothing. Step 6 §3's summary carries `{quality_score}` and `{validation_issues}`.

### 8. Auto-Proceed to Finalize

Once deliverables are written to `{skill_package}` and validation is reported (advisory), load and execute {nextStepFile} to finalize; when `{headless_mode}` is true, print this step's `done` event and step 6's `start` event first (`references/halt-contract.md`).

