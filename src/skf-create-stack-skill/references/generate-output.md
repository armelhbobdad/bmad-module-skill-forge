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
pairsFile: '{run_dir}/pair-intersect.json'
stackInventoryFile: '{run_dir}/stack-inventory.json'
composeEntriesFile: '{run_dir}/compose-entries.json'
draftFolder: '{run_dir}/draft'
runFile: '{run_dir}/run.json'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## Rules

- Stage the draft step 6 approved verbatim, except for the fixes the §8 pre-commit gate makes in staging, and take every other value from `{bundleFile}` and `{exportRecordsFile}`, never from memory

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT here prints its envelope, as SKILL.md's Workflow Rules require: stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints and stop with the halt's exit code (`references/invocation-contract.md` lists every halt); when `{emitEnvelopeHelper}` resolves to no path or prints no line, display the halt message alone.

**Warnings.** Every `workflow_warnings[]` entry here has `step: "step-07"` and `severity: "warn"` unless its section names another severity. Record each at once: write its `[step-07/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

**Advisory checks.** §5's snippet count, §7's source-line check and §8's validator and export-name check never halt the run: when a check's helper resolves to no path, cannot run or prints no JSON (exit `2`), append a `workflow_warnings[]` entry (`code`: the one the section names, `message`: the reason) and go on.

### 1. Resolve Paths and Stage Target Directory

`{skill_group}` is `{skills_output_folder}/{stack_name}/`, `{skill_package}` is `{skills_output_folder}/{stack_name}/{version}/{stack_name}/` and `{forge_version}` is `{forge_data_folder}/{stack_name}/{version}/`, with the `{version}` the stack version below resolves.

**The atomic writer.** Resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}`; first existing path wins. If neither exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `generate-output:atomic-writer`) with "**Cannot proceed.** `skf-atomic-write.py` is missing, so the stack cannot be written safely. Re-install SKF, then re-run." Nothing is written before this check: §2 to §6 stage the package, which §9 commits whole before §10 flips the `active` link, and §7 and §8b write each workspace file atomically.

**Prior stack.** Step 1 §0 checked `{skill_group}` and bound `{prior_active_version}`, `{prior_stack_version}` and `{prior_libraries}` (read them from `{runFile}` if lost): a set `{prior_stack_version}` makes this run a **re-composition**, a `null` one a new stack. Resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}`; first existing path wins.

**Stack version.** `{skillInventoryHelper}` computes `{version}`; never reduce, compare or bump a version by hand:

- **Code mode:** bind `{version}` ← `version`; the helper takes each library of `{bundleFile}` with its `file_count` as its import count and its manifest `version`:

  ```bash
  uv run {skillInventoryHelper} version primary --bundle "{bundleFile}"
  ```

- **Compose mode, new stack** (`{prior_stack_version}` unset): `1.0.0`; the constituent versions stay in `dependencies[]`.
- **Compose mode, re-composition:** bind `{version}` ← `version`, with this run's libraries as `{stack_libraries}` and both lists comma-separated:

  ```bash
  uv run {skillInventoryHelper} version bump --prior "{prior_stack_version}" --prior-libraries "{prior_libraries}" --libraries "{stack_libraries}"
  ```

Narrate the version and the helper's `reason` or `bump`. On `BAD_INPUT` or `USAGE` the call, or in code mode the bundle field its `error` names, is malformed: fix it and run it again. Start a new release line at `1.0.0` only when no candidate resolves, the call prints no JSON, or the prior `version` names none (`NOT_A_VERSION`), and append a `workflow_warnings[]` entry (`code: "stack-version-default"`, `message`: the helper's `error`, or why it did not run).

**Pre-flight: ownership, phase 2.** Before the first write below, check the version folder this run writes: run the call below, bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder` and `{write_detail}` ← `write_check.detail`, and apply the ownership refusals below:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

**Ownership refusals.** Continue only when the status is `ok` and `{write_verdict}` is `"ok"`, or, when no helper candidate resolves, only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise create nothing and refuse with "**`{stack_name}`: nothing was written.** {clause}", taking the clause of the first case that applies:

- `{write_verdict}` is `"flat-layout"`: "It still uses the flat layout: a version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {stack_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"`: "It is not SKF output: `{write_folder}` {write_detail}, so SKF writes no version there. {remedy}"
- The status is not `ok`, or the output has no `write_check` (an older helper with no `--write-check` reports a new skill as `SKILL_NOT_FOUND`): "SKF could not check who generated it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date). {remedy}"
- No helper candidate resolved: "SKF cannot check who generated it: `skf-skill-inventory.py` is missing; re-install SKF. {remedy}"

`{remedy}` is "A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{stack_name}` yourself and pass another `stack_name` for this stack. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder without `metadata.json` may be an interrupted run's: delete it yourself."

Each refusal is a HARD HALT (exit 5, `halt_reason: "not-skf-output"`, or `halt_reason: "flat-layout"` for the flat-layout refusal, phase `generate-output:ownership`, `path` `{write_folder}`, or `{skill_group}` when no helper candidate resolved): do NOT proceed to staging.

**Stage**, in write order: the staging folder `{skill_package}.skf-tmp/` (`{skill_staging}` below), its subfolders, then the workspace folder:

```bash
python3 {atomicWriteHelper} stage-dir --target {skill_package}
mkdir -p {skill_staging}/references/integrations
mkdir -p {forge_version}
```

**Rollback contract.** If a write of §2 to §9 fails, run `python3 {atomicWriteHelper} commit-dir --rollback --target {skill_package}`, purge any `{forge_version}/*-tmp` staging artifacts and HALT (exit 4, `halt_reason: "write-failure"`, phase `generate-output:write`, unless the section names another halt), keeping the run folder.

### 2. Stage SKILL.md

Copy the approved draft as it stands on disk:

```bash
cp "{draftFolder}/SKILL.md" "{skill_staging}/SKILL.md"
```

### 3. Stage Per-Library Reference Files

Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. If no candidate resolves, invoke the rollback contract from §1, with exit 3, `halt_reason: "helper-missing"` and phase `generate-output:references` for its HALT. Otherwise run the call of the run's mode:

```bash
uv run {renderStackMetadataHelper} references --mode code --bundle "{bundleFile}" --records "{exportRecordsFile}" --pairs "{pairsFile}" --out "{skill_staging}/references"
uv run {renderStackMetadataHelper} references --mode compose --bundle "{bundleFile}" --out "{skill_staging}/references"
```

It writes `references/{library_name}.md` for each library of `{bundleFile}`'s `per_library_extractions[]` in the references structure of the bundled `assets/stack-skill-template.md`: its title, `**Version:**`, Import count (its `file_count`; compose mode: its export count), `**Confidence:**` and Key Exports (its records in `{exportRecordsFile}`; compose mode: its `exports`). When the entry's `temporal` holds an item, its `## Migration & Deprecation` section lists each `deprecated_exports`, `migration_notes` and `version_warnings` item as written, label and citation included; with none, the file has no such section. It writes §4's pair files too. On exit `2` its stderr names the input it refused (fix that bundle, record or pair field and run it again) or the write that failed (invoke the rollback contract from §1).

In each library file its `written[]` lists, replace the `<!-- skf:fill usage-patterns -->` line with the entry's `usage_patterns`, each cited as compile-stack §4 cites, and the `<!-- skf:fill common-imports -->` line with the most frequent import statements. When `{stackSkillTemplatePath}` is a house-style copy that adds a section to the references structure, write that section into each library file where the copy places it.

If step 6 extracted the catalog, copy `{draftFolder}/stack-catalog.md` to `{skill_staging}/references/stack-catalog.md` too; its per-library links stay file-relative, `[ref]({name}.md)`.

### 4. Stage Integration Pair Reference Files

§3's call wrote `references/integrations/{a}-{b}.md` for each entry of `{bundleFile}`'s `integrations[]` in the integrations structure of the bundled `assets/stack-skill-template.md`: its title, `**Type:**`, `**Co-import files:**` (its pair's `intersection_count` in `{pairsFile}`, 0 in compose mode), its `**Confidence:**` label and Key Files (its `key_files`; in compose mode the entry's `evidence` and `reference` lines and, when its `vs` is set, its VS lines). In each pair file its `written[]` lists, replace the `<!-- skf:fill integration-pattern -->` line with the entry's `description` and its `key_files` citations (in compose mode its `description`, citing the Key Files lines without repeating them), and the `<!-- skf:fill usage-convention -->` line with how the project structures the integration. A section a house-style `{stackSkillTemplatePath}` adds to the integrations structure goes into each pair file where the copy places it.

### 5. Stage context-snippet.md

Write `{skill_staging}/context-snippet.md` in the context-snippet format of `{stackSkillTemplatePath}`, with the `{version}` §1 resolved. Measure it as step 8's validator does: resolve `{countTokensHelper}` from `{countTokensProbeOrder}`, run the call below and bind `{token_estimate}` ← its `context-snippet.md` row's `tokens` (advisory, `snippet-unmeasured`: an unmeasured snippet stays as written).

```bash
uv run {countTokensHelper} {skill_staging}
```

While `{token_estimate}` exceeds **120**, apply the next trim and measure again: drop the `gotchas` line; strip the `stack` line's versions; keep its top 8 dependencies by import count (export count in compose mode); keep the top 5 `integrations` by co-import file count (§4), each cut list ending `, ...+{N} more`. Never trim the `IMPORTANT:` line. Over budget after the last trim, keep the snippet and append a `workflow_warnings[]` entry (`code: "snippet-over-budget"`, `message`: its `{token_estimate}`).

### 6. Stage metadata.json

Write `{skill_staging}/metadata.json` to `assets/metadata-contract.md`, with `version` ← `{version}` and `forge_tier` ← the `forge_tier` of `{runFile}`, the run tier step 1 saved. Run the helper §3 resolved:

```bash
uv run {renderStackMetadataHelper} metadata --bundle "{bundleFile}"
```

It reads every library of `{bundleFile}`, with its `per_library_extractions[].confidence` and, in compose mode, the constituent's authority step 4 wrote, and every pair of its `integrations[]`, each named as its `references/integrations/{a}-{b}.md` file is: write the fields the contract takes from it verbatim. On exit `2`, fix the bundle field its stderr names and run it again; any other failure invokes the rollback contract from §1.

### 7. Write Forge Data Artifacts (Workspace)

Write `{forge_version}/provenance-map.json`, the variant of the run's mode in `assets/provenance-map-schema.md`; if the write fails, invoke the rollback contract from §1.

- **In code-mode:** `entries[]` is the `entries` of `{exportRecordsFile}`, the records step 4 checked, and `integrations[]` holds the pairs of `{bundleFile}`, each with its co-import files from `{pairsFile}`: the call below writes both from those files as they stand. Pipe it only the map's `provenance_version`, `skill_name`, `skill_type`, `source_repo`, `source_commit` and `generated_at`. On exit `2` its stderr names the input it refused (fix it and run it again) or the write that failed.

  ```bash
  <the other map fields as JSON> | uv run {renderStackMetadataHelper} provenance --records "{exportRecordsFile}" --bundle "{bundleFile}" --pairs "{pairsFile}" --input - --target "{forge_version}/provenance-map.json"
  ```

- **In compose-mode:** write only the entries, as `{"entries": [...]}`, to `{composeEntriesFile}`, each with its `source_library` and cited fields, its `export_name` the literal identifier of the cited contract as the staged `SKILL.md` or a file directly in `references/` writes it, never a descriptive label (§8 checks it). The call below sets each entry's `confidence`, `signature_source` and `extraction_method` from its constituent's `per_library_extractions[].confidence` and adds `integrations[]` and `constituents[]`, each `metadata_hash` copied from `{stackInventoryFile}`, never a fresh hash. Pipe it the code-mode fields and `source_ref`, the `source_*` fields null; exit `2` as in code mode.

  ```bash
  <the other map fields as JSON> | uv run {renderStackMetadataHelper} provenance --records "{composeEntriesFile}" --bundle "{bundleFile}" --inventory "{stackInventoryFile}" --skills-root "{skills_output_folder}" --project-root "{project-root}" --input - --target "{forge_version}/provenance-map.json"
  ```

**Source lines (code mode only).** Check that each entry's `source_line` defines its export: resolve `{verifyProvenanceCompletenessHelper}` from `{verifyProvenanceCompletenessProbeOrder}` and run `verify`, `fix`, then `verify` again, with `{project_root}` the project root, `project_root` from step 1, that each `source_file` is relative to (never `{scan_root}`):

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

Read the JSON, not the exit code, ignoring `missing` and `orphaned` (a stack's `exports` is `[]`). Record a `workflow_warnings[]` entry (`severity: "info"`, `code: "provenance-lines-fixed"`) naming the lines `fix` moved, and one (`code: "provenance-line-unverified"`, `message`: the item's `export_name`, `source_file`, `source_line`, `reason` and `definition_lines`, and, when it carries `folded_to`, that its line was checked against that base name) per `stale[]` item of the last `verify`. The check is advisory (`provenance-lines-unchecked`) and ends at a `summary.stale_check` of `skipped-no-source-root`. Delete `{forge_version}/provenance-verify.skf-tmp` at the end.

### 8. Pre-Commit Gate

Catch in staging what step 8's `skill-check --fix` cannot correct, a `description` over 1024 characters or a body over 500 lines: resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}` and run it on the staged `SKILL.md` under the real skill name:

```bash
uv run {frontmatterValidator} {skill_staging}/SKILL.md --skill-dir-name {stack_name} --max-body-lines 500 --max-body-tokens 5000
```

Act on its `issues[]` severities, not its exit code (an over-long `description` is `medium` and exits `0`):

- **`status` is `fail`, or an issue is `high` or `medium`:** fix it in staging and run the validator again until it clears: shorten the `description`, or split the largest Tier-2 sections of the `body` into `{skill_staging}/references/` (Tier-1 content stays inline, as in `validate.md` §3) or trim it. A split that moves the catalog into `{skill_staging}/references/stack-catalog.md` rewrites each `[ref](references/{name}.md)` in it to `[ref]({name}.md)`.
- **Only `low` issues:** append each to `workflow_warnings[]` (`code: "pre-commit-gate-issue"`, `message`: its `field` and `message`) and proceed.

If the validator does not resolve or cannot run, the gate is advisory (`pre-commit-gate-skipped`).

**Compose-mode export names (compose mode only).** `skf-test-skill` counts an entry toward Export Coverage only when the package writes its `export_name`: resolve `{namesPresentHelper}` from `{namesPresentProbeOrder}` and run:

```bash
uv run {namesPresentHelper} --provenance {forge_version}/provenance-map.json --skill-dir {skill_staging}
```

When its `absent[]` is empty, go on to §8b. Otherwise rename each absent entry whose contract a staged file names by a literal identifier to that identifier in `{composeEntriesFile}` and run the §7 compose-mode `provenance` call again; then run the call above with `--drop-absent` to drop every entry still absent. Record a `workflow_warnings[]` entry (`message`: its `source_library` and `export_name`, old and new for a rename) per renamed entry (`code: "compose-export-name-renamed"`) and per `dropped[]` entry (`code: "compose-export-name-dropped"`). The check is advisory (`compose-export-names-unchecked`).

### 8b. Write the Evidence Report (Workspace)

With the §8 gate's warnings recorded, write `evidence-report.md` with the helper §3 resolved, running the call of the run's mode:

```bash
uv run {renderStackMetadataHelper} evidence-report --bundle "{bundleFile}" --run-dir "{run_dir}" --provenance "{forge_version}/provenance-map.json" --pairs "{pairsFile}" --target "{forge_version}/evidence-report.md"
uv run {renderStackMetadataHelper} evidence-report --bundle "{bundleFile}" --run-dir "{run_dir}" --provenance "{forge_version}/provenance-map.json" --target "{forge_version}/evidence-report.md"
```

**evidence-report.md** lists each library's extraction summary and tier from `{bundleFile}` (its `failed[]` included); each pair's integration result; every `workflow_warnings[]` entry, each line of `{run_dir}/warnings.jsonl` decoded as the JSON string it holds; each auto-decision of `{run_dir}/headless-decisions.jsonl` as its `gate`, `taken_action` and `reason` (the scope gate's dropped libraries and `prior_kept` included), or "none"; and the final map's entries binned by `signature_source` with `skf-render-metadata-stats.py`, one count per entry (`metadata.json` counts libraries), or "not computed" with its reason when that helper is missing or the map cannot be read. On exit `2` its stderr names the input it refused (fix it and run the call again) or the write that failed; when the write fails or the call cannot run, invoke the rollback contract from §1.

### 9. Commit Staging Directory

With §2 to §6 staged, swap the staging dir into place:

```bash
python3 {atomicWriteHelper} commit-dir --target {skill_package}
```

On failure, invoke the rollback contract from §1. Then delete the working files no later step reads: `rm -rf "{draftFolder}" "{bundleFile}" "{exportRecordsFile}" "{importCountsFile}" "{pairsFile}" "{stackInventoryFile}" "{composeEntriesFile}"`; the run folder keeps its warnings and decisions for step 9's envelope.

### 10. Flip Active Symlink

Only after `commit-dir` succeeds, point `{skill_group}/active` at the committed `{version}`:

```bash
python3 {atomicWriteHelper} flip-link --link {skill_group}/active --target {version}
```

If it fails, append a `workflow_warnings[]` entry (`code: "flip-link-failed"`, `message`: the helper's error) and continue: the committed package is valid.

### 11. Display Write Summary

Report each file written, with its path and size (SKILL.md's line count, the snippet's `{token_estimate}`), the `{skill_group}/active -> {version}` link and the file count.

### 12. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.
