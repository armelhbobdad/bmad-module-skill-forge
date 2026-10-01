---
nextStepFile: 'validate.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
namesPresentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-names-present.py'
  - '{project-root}/src/shared/scripts/skf-names-present.py'
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
renderStackMetadataProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-stack-metadata.py'
  - '{project-root}/src/shared/scripts/skf-render-stack-metadata.py'
countTokensProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-tokens.py'
  - '{project-root}/src/shared/scripts/skf-count-tokens.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
exportRecordsFile: '{run_dir}/export-records.json'
importCountsFile: '{run_dir}/import-counts.json'
draftFolder: '{run_dir}/draft'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## Rules

- Write all output files in correct directory structure. Stage the draft step 6 approved verbatim, except for the fixes the §8 pre-commit gate makes in staging, and take every other value from `{bundleFile}` and `{exportRecordsFile}`, never from memory
- Create directory structure before writing files
- Report each file written with path and size

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, adding `"path"` when the halt names a file or folder, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). Nothing was committed, so the envelope's `skill_package` is `null`. If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

**Advisory checks.** The snippet count (§5), the source-line check (§7), the pre-commit gate's validator and the export-name check (§8) never halt the run: when a check's helper resolves to no path, cannot run, or prints no JSON (exit `2`), append one `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code`: the one the section names, `message`: the reason) and go on without it.

### 1. Resolve Paths and Stage Target Directory

The final artifact paths, where the skill name is `{stack_name}` (step 1 §0) and `{version}` is the version S11 below resolves:

```
{skill_group}                          # {skills_output_folder}/{stack_name}/
{skill_package}                        # {skills_output_folder}/{stack_name}/{version}/{stack_name}/
├── references/
│   └── integrations/
{forge_version}                        # {forge_data_folder}/{stack_name}/{version}/
```

**The atomic writer.** Resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}`; first existing path wins. Every write of this step goes through it, as the rollback contract below requires. If neither path exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `generate-output:atomic-writer`) with "**Cannot proceed.** `skf-atomic-write.py` is missing, so the stack cannot be written safely. Re-install SKF, then re-run." Nothing is written before this check.

**Pre-flight: ownership, phase 1 (S3).** Resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}` and run, before any prior metadata is read:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --forge-data-folder {forge_data_folder}
```

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder`, `{write_detail}` ← `write_check.detail` and `{prior_active_version}` ← `write_check.marked_active_version`, and apply the ownership refusals below.

When `{prior_active_version}` is not null, read `{skills_output_folder}/{stack_name}/{prior_active_version}/{stack_name}/metadata.json`. If its `skill_type` is not `"stack"`, do NOT proceed to staging or commit: HALT (exit 4, `halt_reason: "write-failure"`, phase `generate-output:not-a-stack`, `path` `{skill_group}`) with "**Cannot proceed.** `{skills_output_folder}/{stack_name}/` exists but is not a stack skill (`skill_type={found_type}`). Rename the existing directory or pass another `stack_name` to avoid collision."

Otherwise this run is a **re-composition**: capture its `version` as `{prior_stack_version}` and its `libraries` array as `{prior_libraries}`. When `{prior_active_version}` is null (the group is absent, holds only what an interrupted run leaves, or its `active` link names no version SKF generated), treat this as a new stack and leave `{prior_stack_version}` unset: prior metadata is read only from a version SKF generated.

**Stack version (S11).** `{skillInventoryHelper}` computes `{version}`; never reduce, compare or bump a version by hand:

- **Code mode:** pipe `[{"name": "<library>", "import_count": <its file_count>, "version": "<its manifest version, or null>"}, ...]`, one entry per library of `{bundleFile}`, to the call below and bind `{version}` ← `version`, the most imported library's version as one folder name (`^18.2.0` gives `18.2.0`; the helper names its pick in `reason`).

  ```bash
  uv run {skillInventoryHelper} version primary -
  ```

- **Compose mode, new stack** (`{prior_stack_version}` unset): `1.0.0`, the stack's own release line; the constituent versions stay in `dependencies[]`.
- **Compose mode, re-composition:** continue the prior line (a reset to `1.0.0` would shadow a prior `3.0.5`). Bind `{version}` ← `version` from the call below, with this run's library names as `{stack_libraries}` and both lists comma-separated: the helper bumps the major number when a library of `{prior_libraries}` is gone, else the minor one.

  ```bash
  uv run {skillInventoryHelper} version bump --prior "{prior_stack_version}" --prior-libraries "{prior_libraries}" --libraries "{stack_libraries}"
  ```

Narrate the version and the helper's `reason` or `bump`. On `BAD_INPUT` or `USAGE` the call is malformed (the candidates piped, or an unquoted list the shell split): fix it and run it again. Start a new release line at `1.0.0` only when no candidate resolves, the call prints no JSON (`uv` cannot run it), or the prior stack records no `version` or one that names none (`NOT_A_VERSION`), and append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code: "stack-version-default"`, `message`: the helper's `error`, or why it did not run).

**Pre-flight: ownership, phase 2.** Before `stage-dir` and `mkdir -p {forge_version}` below, run the same command with `--write-version {version}`, and apply the same bindings and refusals:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

**Ownership refusals (both phases).** Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{stack_name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {stack_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{stack_name}` is not SKF output: nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{stack_name}` yourself, and pass another `stack_name` to create this stack beside it. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted create-stack-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}". Here `{skill_group}` is `{skills_output_folder}/{stack_name}`.

Each refusal is a HARD HALT (exit 5, `halt_reason: "not-skf-output"`, or `halt_reason: "flat-layout"` for the flat-layout refusal, phase `generate-output:ownership`, `path` `{write_folder}`): do NOT proceed to staging.

**Atomic write strategy (C2 / B5):** All artifact writes for `{skill_package}` MUST stage into a temp directory first, then commit atomically via `commit-dir` (§9). The active symlink flip only happens AFTER the commit succeeds.

Create the staging directory:

```bash
python3 {atomicWriteHelper} stage-dir --target {skill_package}
```

After this call, writes land in `{skill_package}.skf-tmp/` (referred to below as `{skill_staging}`). Create the required subdirectories inside the staging dir:

```bash
mkdir -p {skill_staging}/references/integrations
```

Also create the forge workspace directory directly (workspace artifacts, not deliverables, need no stage-dir / commit-dir):

```bash
mkdir -p {forge_version}
```

**Rollback contract:** If ANY write in sections 2 to 8b fails, immediately run:

```bash
python3 {atomicWriteHelper} commit-dir --rollback --target {skill_package}
```

Then purge any `{forge_version}/*-tmp` staging artifacts and HALT (exit 4, `halt_reason: "write-failure"`, phase `generate-output:write`, unless the section that invokes the contract names another halt), keeping the run folder. This is the single rollback exit shared by §6 (a missing metadata helper), §7 and §8b (workspace-write failures) and §9 (commit-dir failure).

### 2. Stage SKILL.md

Copy the draft step 6 approved, as it stands on disk, into the staging dir (the whole staging dir is committed atomically later):

```bash
cp "{draftFolder}/SKILL.md" "{skill_staging}/SKILL.md"
```

### 3. Stage Per-Library Reference Files

For each library of `{bundleFile}`'s `per_library_extractions[]`, write `{skill_staging}/references/{library_name}.md` in the references structure of `{stackSkillTemplatePath}`, from its bundle entry:
- Library name and `version` (**in compose-mode**: the constituent's `metadata.json` version)
- Import count and file count: its `file_count` and `files_analyzed` (**in compose-mode**: the export count)
- Key exports with signatures: its records in `{exportRecordsFile}` (**in compose-mode**: its `exports`)
- Usage patterns with file:line citations: its `usage_patterns`
- Confidence tier label: its `confidence`

**If the catalog was extracted** (large stack: step 06 §4 placed the `Library Reference Index` + `Per-Library Summaries` out of SKILL.md), copy the approved `{draftFolder}/stack-catalog.md` to `{skill_staging}/references/stack-catalog.md` the same way, and confirm SKILL.md carries the inline pointer instead of the two sections. The catalog sits in `references/`, so its links to the per-library files are file-relative, `[ref]({name}.md)`: a `references/{name}.md` link there would resolve to `references/references/{name}.md`. Small stacks keep the catalog inline and write no `stack-catalog.md`.

### 4. Stage Integration Pair Reference Files

For each entry of `{bundleFile}`'s `integrations[]`, write `{skill_staging}/references/integrations/{a}-{b}.md` in the integrations structure of `{stackSkillTemplatePath}`: the pair and its `type`, the co-import file count (`co_import_files`), its `description` with the file:line citations of its `key_files`, the usage convention, and its `tier` label. **If no integrations detected:** Skip this section (no files to write).

### 5. Stage context-snippet.md

Write `{skill_staging}/context-snippet.md` in the context-snippet format of `{stackSkillTemplatePath}`, with the `{version}` §1 resolved, targeting **~80-120 tokens** (M2). A snippet under 80 tokens is fine: small stacks write short ones.

**Measure it** with `{countTokensHelper}` (resolve it from `{countTokensProbeOrder}`), the count step 8's validator also takes (`len(text) // 4`): bind `{token_estimate}` ← the `tokens` of the `context-snippet.md` row of its `files[]`.

```bash
uv run {countTokensHelper} {skill_staging}
```

When it cannot measure, keep the snippet as written: advisory (`snippet-unmeasured`), and step 8 still checks its bounds.

**Overflow strategy (M2):** If `{token_estimate}` exceeds **120**, trim in this fixed order, writing the snippet again and measuring it again after each trim, until it is 120 or below:

1. **Drop the `gotchas` line** (pitfalls live in SKILL.md and references).
2. **Strip versions from the `stack` line** (`{dep-1}, {dep-2}` instead of `{dep-1}@{v1}`; `metadata.json` keeps them).
3. **Truncate the `stack` list to the top 8 dependencies by import count** (or by export count in compose-mode), appending `, ...+{N} more`.
4. **Truncate the `integrations` list to the top 5 by file count**, appending `, ...+{N} more`.

If the snippet is still over budget after step 4, append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code: "snippet-over-budget"`, `message`: its `{token_estimate}`) and keep it: the budget never blocks the write. The `IMPORTANT:` line is mandatory and never trimmed.

### 6. Stage metadata.json

Write `{skill_staging}/metadata.json` with every field of `assets/metadata-contract.md`, the single schema source: it carries the SKF ownership markers every later run checks, so no customization override replaces it; do not re-transcribe it here. The fields that count, bin or rank come from `{renderStackMetadataHelper}` (resolve it from `{renderStackMetadataProbeOrder}`), never from hand counting:

```bash
uv run {renderStackMetadataHelper} metadata --input -
```

Pipe it `{"mode": "code|compose", "libraries": [{"name": "<library>", "confidence": "<its per_library_extractions[].confidence>", "source_authority": "<compose mode: the constituent's>"}, ...], "integrations": [{"a": "<library>", "b": "<library>"}, ...]}`: every library of `{bundleFile}`, and every pair of its `integrations[]` in the order of its `references/integrations/{a}-{b}.md` name. Write its `library_count`, `integration_count`, `libraries`, `integration_pairs`, `confidence_distribution` (libraries, not provenance entries: the evidence report bins those, §8b), `confidence_tier` and `source_authority` verbatim. On exit `2`, fix the input its stderr names and run it again. If no candidate resolves, invoke the rollback contract from §1, with exit 3, `halt_reason: "helper-missing"` and phase `generate-output:metadata` for its HALT.

Also set `version` to the `{version}` §1 resolved (the contract's `1.0.0` is only the new-stack default) and `forge_tier` to step 1's run tier (Quick/Forge/Forge+/Deep).

### 7. Write Forge Data Artifacts (Workspace)

Write workspace artifacts directly to `{forge_version}` (workspace-only, so no staging), each through the atomic writer's `write`. This section writes `provenance-map.json` and, in code mode, checks its source lines; §8b writes `evidence-report.md` after the §8 gate, so the report lists the warnings both record:

```bash
<json-content> | python3 {atomicWriteHelper} write --target {forge_version}/provenance-map.json
```

If any workspace write fails, invoke the rollback contract from §1.

**provenance-map.json:**

Use the schema of `assets/provenance-map-schema.md`, which gives the canonical templates and field definitions of both variants. Its `integrations[]` holds one entry per pair of `{bundleFile}`'s `integrations[]`, with its `tier` as `confidence` and its `co_import_files` as they stand:

- **In code-mode:** use the code-mode variant (`source_repo` / `source_commit` populated; `detection_method = "co-import grep"`). `entries[]` is the `entries` of `{exportRecordsFile}`, the records step 4 checked, as they stand.
- **In compose-mode:** use the compose-mode variant (source-anchor fields `null`; `extraction_method = "compose-from-skill"`; `detection_method ∈ "architecture_co_mention|constituent_documented_contract|inferred_from_shared_domain"`; includes the additional `constituents[]` array for drift detection). Each entry's `confidence` and `signature_source` are its constituent's tier (`per_library_extractions[].confidence`), and its `export_name` is the literal identifier of the cited contract as the staged `SKILL.md` or a `.md` file directly in `references/` writes it, never a descriptive label or a name written only in `references/integrations/` (§8 checks it). Each `constituents[]` entry is filled from its bundle entry (`library`, `skill_dir`, `version`), with the `metadata_hash` step 4 §0 recorded there as the provenance anchor, never a fresh hash.

**Source lines (code mode only).** The provenance verifier checks that each entry's `source_line` is the line that defines its export (a `def` recorded on its decorator line is not). Resolve `{verifyProvenanceCompletenessHelper}` from `{verifyProvenanceCompletenessProbeOrder}` and run `verify`, then `fix`, which moves each `source_line` to its export's definition line when the file has exactly one, then `verify` once more. `{project_root}` is the project root, `project_root` from step 1, which each `source_file` is relative to (never `{scan_root}`):

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {skill_staging}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {project_root} \
    -o {forge_version}/provenance-verify.skf-tmp
uv run {verifyProvenanceCompletenessHelper} fix \
    --verify {forge_version}/provenance-verify.skf-tmp \
    --provenance {forge_version}/provenance-map.json \
    --skill-dir {skill_staging}
```

Rely on each call's JSON, not its exit code (`1` means findings, or items `fix` left), and ignore `missing` and `orphaned`: a stack's `exports` is `[]` by design. Append one `workflow_warnings[]` entry (`step: "step-07"`, `severity: "info"`, `code: "provenance-lines-fixed"`) naming each line `fix` moved (its `applied[]`), and one (`severity: "warn"`, `code: "provenance-line-unverified"`, `message`: its `export_name`, `source_file`, `source_line`, `reason` and `definition_lines`) for each `stale[]` item the last `verify` reports, for a person to decide. The check is advisory (`provenance-lines-unchecked`), and a `summary.stale_check` of `skipped-no-source-root` ends it the same way. Delete `{forge_version}/provenance-verify.skf-tmp` when the check ends.

### 8. Pre-Commit Gate

Step 8 validates only after commit-dir and flip-link have published the package, so catch here, while it is staged, the `skill-check` rejects `--fix` cannot correct: a `description` over 1024 characters and a body over `body.max_lines` (500). Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}` and run it on the **staged** `SKILL.md`, with the real skill name so the `.skf-tmp` suffix does not fail the directory-match check:

```bash
uv run {frontmatterValidator} {skill_staging}/SKILL.md --skill-dir-name {stack_name} --max-body-lines 500 --max-body-tokens 5000
```

Act on the `issues[]` severities in its JSON, not on the exit code (an over-long `description` is `medium` and exits `0`):

- **`status` is `fail`, or an issue is `high` or `medium`:** HALT-to-fix **in staging** and re-run the validator until it clears; do NOT proceed to §8b or the §9 commit-dir before then. Remediate by `field`:
  - `description` / `name` / `compatibility`: correct `{skill_staging}/SKILL.md` (shorten `description` to ≤ 1024 chars).
  - `body` (`body lines N exceeds max 500`): prefer a **selective split** of the largest Tier-2 section(s) into `{skill_staging}/references/`, keeping Tier-1 content inline (as `validate.md` §3 does), or trim redundant content.
    When the split moves the catalog into `{skill_staging}/references/stack-catalog.md`, rewrite each `[ref](references/{name}.md)` in it to `[ref]({name}.md)`, as §3 above does for a catalog step 06 extracted.
- **Only `low` issues** (an unexpected field, or `body token estimate N exceeds max 5000`, a char/4 estimate that `skill-check` only warns on): append each to `workflow_warnings[]` (`step: "step-07"`, `severity: "warn"`, `code: "pre-commit-gate-issue"`, `message`: the issue's `field` and `message`) and proceed.

**If `{frontmatterValidator}` does not resolve or cannot run**, the gate is advisory (`pre-commit-gate-skipped`): step 8 remains the post-commit backstop.

**Compose-mode export names (compose mode only).** `skf-test-skill` credits a compose-mode entry toward Export Coverage only when the package writes its `export_name`. Resolve `{namesPresentHelper}` from `{namesPresentProbeOrder}` and run:

```bash
uv run {namesPresentHelper} --provenance {forge_version}/provenance-map.json --skill-dir {skill_staging}
```

Its `absent[]` lists each entry (`entry_index`, `export_name`, `source_library`) whose name `skf-test-skill` would not find in the staged package; when it is empty, go on to §8b. Otherwise, when `{headless_mode}` is false, set the `export_name` of each absent entry whose contract a staged file names by a literal identifier (a descriptive label was recorded in its place) to that identifier, and rewrite the map with the atomic writer as §7 does. Then, in both modes, run the call again with `--drop-absent`, which drops every entry still absent and rewrites the map. Append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `message`: its `source_library` and `export_name`, the old and the new one for a rename) per renamed entry (`code: "compose-export-name-renamed"`) and per `dropped[]` entry (`code: "compose-export-name-dropped"`). The check is advisory (`compose-export-names-unchecked`).

### 8b. Write the Evidence Report (Workspace)

Now that the §8 gate has recorded its warnings, bin the final map's entries by `signature_source` for the report, in both modes. Resolve `{renderMetadataStatsHelper}` from `{renderMetadataStatsProbeOrder}` and run:

```bash
echo '{}' | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json --shape stack
```

Then write `evidence-report.md` to `{forge_version}` the same way as §7, through the atomic writer and with no staging:

```bash
<md-content> | python3 {atomicWriteHelper} write --target {forge_version}/evidence-report.md
```

If the write fails, invoke the rollback contract from §1.

**evidence-report.md:**
- Extraction summary per library, with its tier, from `{bundleFile}` (its `failed[]` included)
- Integration detection results per pair
- Warnings and failures encountered: every `workflow_warnings[]` entry recorded so far, each line of `{run_dir}/warnings.jsonl` decoded as the JSON string it holds (the §7 line check's and the §8 gate's among them)
- Auto-decisions: each line of `{run_dir}/headless-decisions.jsonl` as its `gate`, `taken_action` and `reason`, the scope gate's dropped libraries included, or "none"
- Confidence tier distribution: the helper's `confidence_distribution`, one count per provenance entry (`metadata.json` counts libraries, §6), or "not computed" when the helper is missing or exits `2`

### 9. Commit Staging Directory

After all staged writes in sections 2–6 completed successfully, atomically swap the staging dir into place:

```bash
python3 {atomicWriteHelper} commit-dir --target {skill_package}
```

On failure, invoke the rollback contract from §1. Once it succeeds, delete the run's working files, which no later step reads: `rm -rf "{draftFolder}" "{bundleFile}" "{exportRecordsFile}" "{importCountsFile}"`. The run folder keeps its warnings and decisions until step 9 has emitted the envelope.

### 10. Flip Active Symlink

ONLY AFTER `commit-dir` succeeds, flip the `{skill_group}/active` symlink to point at `{version}`:

```bash
python3 {atomicWriteHelper} flip-link --link {skill_group}/active --target {version}
```

After the flip, `{skill_group}/active/{stack_name}/` resolves to the just-committed skill package. If `flip-link` fails, append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code: "flip-link-failed"`, `message`: the helper's error) and continue: the committed package is still valid, and step 9 lists the warning.

### 11. Display Write Summary

Report the files written: the `{skill_package}` deliverables (SKILL.md with `{line_count}` lines, context-snippet.md with `{token_estimate}` tokens, metadata.json, `references/` `{lib_count}` library files, `references/integrations/` `{pair_count}` integration files), the `{forge_version}` workspace (provenance-map.json, evidence-report.md), the `{skill_group}/active -> {version}` symlink, and the `{total_count}` total.

### 12. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

