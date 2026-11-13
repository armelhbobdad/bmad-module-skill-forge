---
nextStepFile: 'coverage.md'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
inventoryFile: '{run_dir}/skill-inventory.json'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
previousReportScript: 'scripts/skf-previous-report.py'
reportUpdateScript: 'scripts/skf-report-update.py'
---

<!-- Config: communicate in {communication_language}. Initialize the feasibility report skeleton in {document_output_language}. -->

# Step 1: Initialize Verification

## STEP GOAL:

Load all generated skills from the skills output folder, accept the architecture document path (required) and optional PRD/vision document path from the user, validate that all inputs exist and are readable, create the feasibility report document, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and creating the report skeleton — do not perform analysis
- Auto-proceed — halts only on validation errors

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"report_path": "{outputFile}"` once §4 wrote the report and `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Pre-flight: run folder and write probe.** Both run before the first prompt. Create the run folder:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
```

If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." With no folder to stage in, a headless run passes the payload to the emitter directly, with `"customization_resolver_unavailable": "<reason>"` added when SKILL.md On Activation step 4 kept one:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --target stderr <<'SKF_VS_HALT'
{"phase": "init:run-folder", "reason": "<the halt message>", "halt_reason": "write-failed"}
SKF_VS_HALT
```

Once the folder exists and `{customization_resolver_unavailable}` is set (SKILL.md On Activation step 4), record the reason in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes or `$( )`), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`.

Then check that `forge_data_folder`, which `{outputFolderPath}` names, was resolved from config.yaml and is non-empty. If it is undefined or empty: "**Cannot proceed.** `forge_data_folder` is not configured in config.yaml. Re-run [SF] Setup Forge to initialize." HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `init:forge-data-folder`.

Then verify `{outputFolderPath}` is writable: a read-only mount, full disk, or permissions-denied path otherwise only surfaces at §4's atomic write, after the user has gone through the input prompts.

```bash
mkdir -p "{outputFolderPath}" && \
  printf 'probe' > "{outputFolderPath}/.skf-write-probe" && \
  rm "{outputFolderPath}/.skf-write-probe"
```

On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:write-probe`, with `"path": "{outputFolderPath}"`.

**Bind `{project_slug}`.** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins. Run:

```bash
uv run {validateFeasibilityReportHelper} --locate "{outputFolderPath}" --project-name "{project_name}"
```

Bind `{project_slug}` ← `projectSlug`, whatever `status` says: this run needs only the slug, and the helper holds the one slug rule that the consumers of this report apply when they look for it. If no candidate exists, or the command prints no JSON: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:project-slug`.

**Pre-flight: skills folder existence.**
- If `{skills_output_folder}` does not exist on disk: HALT (exit code 3, `halt_reason: "skills-folder-missing"`) at phase `init:skills-folder` with "**Cannot proceed.** `{skills_output_folder}` does not exist: run **[SF] Setup Forge** to initialize the forge, then generate skills with [CS] or [QS]."
- If `{skills_output_folder}` exists but is empty (no subdirectories at all): HALT (exit code 3, `halt_reason: "skills-folder-missing"`) at phase `init:skills-folder` with "**Cannot proceed.** `{skills_output_folder}` contains 0 skills. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]."

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`.

**Enumerate the skills with the shared helper:**

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability > "{inventoryFile}"
```

If the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`, naming its first stderr line. Read `{inventoryFile}` now: every later stage reads the inventory from it, not from context.

The helper reads only the skills SKF generated (its `--help` says how it picks each package and resolves its exports). The later stages read these fields of each `skills[]` entry: `name` (the folder name), `path` (the package, relative to `{skills_output_folder}`), `exports`, `exports_source`, `confidence` (from the exports source, not metadata's `confidence_tier`), `evidence_tier` (`T1`, `T1-low`, `T2` or `T3`, one scale for every skill type), `confidence_tier`, `metadata_schema_version`, `language` (a string, or a list for a stack), `exports_documented`, `source_repo_basename` and `source_root_basename`, so no stage opens `metadata.json`. `warnings[]` names per-skill problems, each starting `<name>: `. The file is `skill_inventory` (used by the skill-count check below, §4, §5, the coverage and integrations stages, and synthesize's delta and Evidence Sources table), and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count` and `{inventory_warnings}` ← `warnings`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders, such as a module's own skills in a shared skills folder, are not in `skills[]` and count toward neither `{skill_count}` nor `{warning_count}`.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `init:inventory` with: "Inventory scan unreliable: {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [VS]."

**Check skill count:**
- At least 2 skills SKF generated must exist (`{skill_count}`; a stack requires multiple libraries)
- If fewer than 2 → "**Cannot proceed.** Only {skill_count} skill(s) SKF generated were found in `{skills_output_folder}`. A stack requires at least 2 skills. Generate more skills with [CS] Create Skill or [QS] Quick Skill, then re-run [VS]." When `{not_skf_output}` is non-empty, append: "Skipped (not SKF output): {not_skf_output}."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`) at phase `init:skill-count`.

### 1. Accept Input Documents

**Find the previous report first.** When `{previous_report_path}` is null, run the previous-report helper without `--provided` before the prompt; the resolve block below runs the same command with `--provided`:

```bash
uv run {previousReportScript} --folder "{outputFolderPath}" --slug "{project_slug}" --timestamp "{timestamp}" [--provided "<path>"]
```

It never returns a file this run writes (`{outputFile}` or `{outputFileLatest}`); without `--provided` it picks the newest earlier report that finished. When it prints no JSON (exit 2, a usage error), the line it prints names the flag it rejected: fix that flag's value and run it again. Otherwise branch on `status`:

- `discovered`: line 3 of the prompt below offers the returned `previousReport` as its Enter default, and an empty answer there sets `previousReport` to it.
  **GATE [default: Y]**: if `{headless_mode}`, set `previousReport` to the returned `previousReport`, log: "headless: delta comparison against `{previousReport}`", and record the decision in the run sink the moment it is taken. Stage `{run_dir}/decision.json` as `{"gate": "init.previous-report", "default_action": "Y", "taken_action": "Y", "reason": "headless: delta comparison against <previousReport>", "evidence": {"previous_report": "<previousReport>"}}` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-verify-stack --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- `none`: leave `previousReport` empty (no finished earlier report, no delta).
- `reader-missing` (exit 3): the shared report reader the helper loads is not installed: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:previous-report`, naming the file its `error` gives.

**Ask only for what no flag answered.** A path the invocation gave (`{architecture_doc_path}`, `{prd_path}`, `{previous_report_path}`, bound at activation) is used in every mode and never asked for again, unless an interactive run finds no file there (the validation below then asks once). An interactive run with any of the three still null shows this prompt, with only the numbered lines whose input is null:

"**Verify Stack: Feasibility Analysis** (read-only: never modifies your skills, architecture doc, or PRD).

If you meant to *generate* skills first, type `cancel` and run `[CS] Create Skill` or `[QS] Quick Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED): your project's architecture doc
2. **PRD or vision document path** (OPTIONAL): for requirements coverage analysis
3. **Previous feasibility report** (OPTIONAL), for delta comparison: {IF the helper found one:}Found the report from {previousTimestamp}: press Enter to compare against it, paste another path, or type `none` to skip.{ELSE:}a timestamped report from an earlier run, or leave it empty to skip.{END IF}

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

When the prompt shows, wait for user input, and bind each answer to its variable (an empty answer leaves an optional one null). An empty line 3 takes the found report; `none` there, like `--previous-report none`, skips the comparison in every mode. **GATE [default: use args]**: headless asks nothing. With `{architecture_doc_path}` set it auto-proceeds and logs "headless: using provided architecture path"; with it null: HALT (exit code 2, `halt_reason: "input-missing"`) at phase `init:input-documents`. A null `{prd_path}` skips the requirements pass, and a null `{previous_report_path}` compares against the newest earlier report.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt below: Display "Cancelled: no analysis was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate the architecture document** (`{architecture_doc_path}`):
- Confirm the file exists and is readable
- If missing or unreadable → "Architecture document not found at `{path}`. Provide a valid path."
- HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:architecture-doc`, with `"path"` set to the path given, if the user cannot provide a valid path; a headless run has no one to ask, so it halts at once.

**Validate the PRD (when `{prd_path}` is set):**
- Confirm the file exists and is readable
- If missing or unreadable, an interactive run asks once: "PRD not found at `{prd_path}`: give another path, or press Enter to continue without it." It checks a path given there the same way, with no further ask.
- Still missing or unreadable → "PRD document not found at `{prd_path}`. Proceeding without PRD: the requirements pass will be skipped." Keep `{prd_path}`, the last path given, so the report's `prdDoc` names it, with `prdAvailable: false`; in headless, record `prd_not_found: <path>` now, with the record block at the end of this section.
- Store PRD availability as `prdAvailable: true|false`

**Resolve a given previous report** (when `{previous_report_path}` is set). `none`, in any case, leaves `previousReport` empty and runs no helper. A path runs the command above with `--provided` set to it; branch on `status`:

- `collision` (exit 1): "`{provided}` is `{collidesWith}`, which this run overwrites. Give a timestamped report from an earlier run, leave the path empty to compare against the most recent one, or type `none` to skip." Interactive: wait for the answer, run the helper again with `--provided` set to it and branch on its `status` as here; an empty answer runs it without `--provided` and sets `previousReport` to the `previousReport` it returns (empty on `none`; `reader-missing` halts as in the find block), and `none` skips as above. In headless, where the path came from `--previous-report`: HALT (exit code 5, `halt_reason: "previous-report-collision"`) at phase `init:previous-report`, with `"path"` set to the path given.
- `not-found`: an interactive run asks once: "Previous report not found at `{provided}`: give another path, press Enter to compare against the most recent one, or type `none` to skip the comparison." It takes the answer as at a collision, and a second `not-found` asks nothing. Still missing → "Previous report not found at `{provided}`. Proceeding without delta comparison." Set `previousReport` to empty; in headless, record `previous_report_not_found: <path>` now, with the record block below.
- `provided`: set `previousReport` to the returned `previousReport`.

**Record a path that was not found.** In headless, record each warning, `prd_not_found: <path>` or `previous_report_not_found: <path>`, as its branch above finds it, one at a time: write it alone to `{run_dir}/input-warning.txt` with a file write, never `echo` (a path can hold quotes or `$( )`), then run:

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/input-warning.txt")"
```

### 4. Create Feasibility Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report`.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report`.

**Filename variables:** `timestamp` was fixed at activation (SKILL.md On Activation §2) and `project_slug` by the Bind block at the top of this step; reuse them, do not re-derive. `{outputFile}` and `{outputFileLatest}` resolve from them per the stage frontmatter template, the latter as a copy, not a symlink (per schema), which only report.md §1 writes.

**Check the template.** If `test -f "{reportTemplatePath}" && test -r "{reportTemplatePath}"` fails, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report-template`, with `"path": "{reportTemplatePath}"`: "`report_template_path` names `{reportTemplatePath}`, which is not a readable file. Point it at your copy in `{project-root}/_bmad/custom/skf-verify-stack.toml` or `.user.toml`, or re-install SKF when it is the bundled `assets/feasibility-report-template.md`." Nothing is written.

**Load** `{reportTemplatePath}` (the customize-aware template path resolved in SKILL.md On Activation §4) and stage the initial content. Substitute the template's `Schema contract:` line `{feasibilitySchemaRef}` placeholder with the resolved schema path so every emitted report cites a path that exists on the running machine.

**Fill the per-run frontmatter keys** and keep every other template value: `projectName` ← `{project_name}`, `projectSlug` ← `{project_slug}`, `generatedAt` ← the ISO-8601 UTC time, `prdAvailable` (§1), `architectureDoc` ← `{architecture_doc_path}`, `prdDoc` ← `{prd_path}` (or `none`), `previousReport` (or empty), `skillsAnalyzed` ← `{skill_count}` and `stepsCompleted: ['init']`. The header lines under the title take the same values, with ` (not found)` after `{prdDoc}` when `prdAvailable` is false and `prdDoc` is not `none`.

**Atomic write:** Pipe the staged content through `python3 {atomicWriteHelper} write --target {outputFile}`: a plain `rm`+rewrite risks a partial write corrupting the report.

On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:report`, with `"path": "{outputFile}"` and no `report_path`: the report was not written.

**Check the new report.** Run `uv run {validateFeasibilityReportHelper} "{outputFile}" -o "{run_dir}/template-check.json"`. On a non-zero exit, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `init:report-template`, with `"report_path": "{outputFile}"`: name from the JSON what the template `{reportTemplatePath}` breaks (`missingHeadings`, `orderViolations`, `verdictTableFound` false or `duplicateVerdictTableLine`, `unknownTokens`, `schemaVersionFound`), and leave `{outputFileLatest}` as it is. The message opens "`report_template_path` names `{reportTemplatePath}`, whose report fails the feasibility-report check:" and ends with the fix sentence of the template check above. No stage has analysed anything yet.

**Check the Evidence Sources table**, which that check does not read and synthesize fills in place:

```bash
uv run {reportUpdateScript} fill-table --report "{outputFile}" --heading 'Evidence Sources' < /dev/null
```

With no rows on stdin it leaves the template's empty table as it is. On exit 2, the copy keeps no such table: HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `init:report-template`, with `"report_path": "{outputFile}"`. The message opens "`report_template_path` names `{reportTemplatePath}`, whose report has no table under `## Evidence Sources`:", names its JSON `error` and ends with the fix sentence of the template check above. On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:report`, with `"path": "{outputFile}"`.

### 5. Display Initialization Summary

"**Stack Verification Initialized**

| Field | Value |
|-------|-------|
| **Skills Loaded** | {skill_count} |
| **Architecture Doc** | {architecture_doc_path} |
| **PRD Document** | {prd_path, with ' (not found: requirements pass will be skipped)' after it when prdAvailable is false, or 'Not provided: requirements pass will be skipped'} |
| **Previous Report** | {previousReport, or 'Not found: no delta comparison' when the path given was not found, or 'Not provided: no delta comparison'} |

**Skill Inventory:**

| Skill | Exports | Exports source | Confidence |
|-------|---------|----------------|------------|
| {name} | {number of exports} | {exports_source} | {confidence} |

**Proceeding to coverage analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

