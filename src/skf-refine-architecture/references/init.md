---
nextStepFile: 'gap-analysis.md'
refinementRulesData: '{refinementRulesPath}'
# Resolve `{enumerateStackSkillsHelper}` by probing
# `{enumerateStackSkillsProbeOrder}` in order (installed SKF module path
# first, src/ dev-checkout fallback); first existing path wins. §2 calls
# it for the deterministic inventory of the skills SKF generated
# (cascade-resolved exports, metadata-hash, the exports-source confidence,
# the unique pairs, and `not_skf_output` for the rest). If neither
# candidate exists, §2 falls through to the LLM-driven inventory as
# graceful degradation (see §2).
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
# Resolve `{validateFeasibilityReportHelper}` the same way. §1 calls it to
# find the [VS] report (`--locate`) and to check and read a report path the
# user gives; its JSON is the run's only source for the report. If neither
# candidate exists, no report is read (see §1).
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Refinement

## STEP GOAL:

Load the architecture document (required), scan the skills folder to build a skill inventory with metadata, load the optional VS feasibility report for context, validate that all inputs exist and meet minimum requirements, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and validating prerequisites — do not perform analysis
- Present a clear initialization summary so downstream steps have validated inputs

## MANDATORY SEQUENCE

### 1. Accept Input Documents

`--architecture-doc <path>` and `--vs-report-path <path>` apply in every mode, as the SKILL.md Invocation Contract says: each one answers its question below, which is then not asked, in an interactive run as in headless.

**Refine without a report.** `--vs-report-path none` answers the report question as typing `none` at the prompt does, in every mode: skip the probe and the path mode below, use no report, and say "VS report skipped (--vs-report-path none)." (in headless, log it). Pass it when the report on disk must not be used, such as a stale or broken `-latest` copy, or in a pipeline whose [VS] step wrote no report.

**Find the [VS] report first.** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins. Unless `--vs-report-path` was passed, run the probe before asking anything:

```bash
uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"
```

It turns the config `{project_name}` into the slug [VS] names its report by and reads only `feasibility-report-<slug>-latest.md` in `{forge_data_folder}`, the copy [VS] rewrites each time a run finishes and its report passes the schema check: the helper builds the file name, so this step never does. It checks the report as the shared feasibility-report schema requires and prints one JSON (the helper's module docstring lists every key). Branch on its exit code:

- **0 with `status: "ok"`:** the report [VS] last wrote for this project. It becomes the report question's default below.
- **0 with `status: "not-found"`:** there is no [VS] report for this project, so the question has no default.
- **1** (the report breaks the contract) **or 2** with a JSON (the report exists but could not be read): HALT as **Unusable VS report** says below.
- **2 with no JSON** on stdout: argparse refused the call itself (its usage error is on stderr), such as a folder path left unquoted that holds a space. It says nothing about the report: fix the call and run it again.

**Read a report path.** A path from `--vs-report-path`, or one typed at the prompt, goes through the helper's path mode, which checks and reads that file exactly as `--locate` does and prints the same JSON:

```bash
uv run {validateFeasibilityReportHelper} "{vs_report_path}"
```

- **0:** use this report.
- **1:** HALT as **Unusable VS report** says below.
- **2** with a JSON (the file is missing or could not be read; its `error` says which): in an interactive run, show `error`, run the probe above if it has not run, and ask the report question again. In headless, log "headless: VS report not read at {vs_report_path} ({error}); probing for the [VS] report instead", then run the probe above and take its outcome as if `--vs-report-path` had not been passed.
- **2 with no JSON:** a malformed call, as for the probe: fix it and run it again.

**Unusable VS report.** A report that breaks the contract is never interpreted: HALT (exit code 2, `halt_reason: "input-invalid"`) and, in headless, emit the error envelope. Name the report's `path` and each problem its JSON shows: a `schemaVersion` other than `1.0` (`schemaVersionOk` is false), sections missing or out of order (`missingHeadings`, `orderViolations`), no verdict table (`verdictTableFound` is false), a second verdict table (at line `duplicateVerdictTableLine`), each entry of `unknownTokens`, or the `error` of a report that could not be read. End with: "Re-run [VS] to write a current report, pass another one with `--vs-report-path <path>`, or refine without one with `--vs-report-path none`."

**Ask for the inputs.** Ask only for what no flag answered:

"**Refine Architecture: Evidence-Backed Refinement** (additive: never deletes original content).

If you wanted to *verify* the stack first, type `cancel` and run `[VS] Verify Stack`; if no skills exist yet, run `[CS] Create Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED): your project's architecture doc to refine
2. **VS feasibility report path** (OPTIONAL): {IF the probe found a report:}Found the [VS] report from {vs_report_date}: press Enter to use it, or give another path.{ELSE:}From a previous [VS] Verify Stack run, for additional context.{END IF} Type `none` to refine without a report.

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

`{vs_report_date}` is the date in the probe's `generatedAt`, or the file name of its `path` when `generatedAt` is null.

Wait for user input. Store the validated architecture document path as `architecture_doc`. **GATE [default: use args]:** a question a flag answered is not asked, and headless answers the rest with their defaults. If `{headless_mode}` and `--architecture-doc` was provided: use that path and auto-proceed, log: "headless: using provided architecture path". If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) and emit the error envelope. The report question's default is the probe's report when its `status` is `ok`: with no `--vs-report-path`, headless takes it and logs "headless: using the [VS] report found at {path}", or logs "headless: no [VS] report for {project_name}; issue detection will use skill data only" when the probe found none.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt: Display "Cancelled — no refinement was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable: "Architecture document not found at `{path}`. Provide a valid path."
- HALT (exit code 2, `halt_reason: "input-invalid"`) if the user cannot provide a valid path. In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" immediately.

**Resolve `{arch_project_name}` (names the refined output file):** Read the architecture document's YAML frontmatter. If it declares a `project_name`, store that value as `{arch_project_name}`; otherwise fall back to the config `{project_name}` resolved at activation. Stash `{arch_project_name}` as a workflow-context variable: `compile.md` and `report.md` resolve `{outputFile}` from it. This makes a producer-side refine of a consumer's architecture doc (the producer/consumer forge split) name the proposal after the doc's own project rather than the forge workspace config. Producer-side working state (`ra-state-{project_name}.md`) and the VS report probe stay keyed on the config `{project_name}`.

**Record the VS report.** Cache the JSON of the report this run uses as `{vs_report}`. It is the run's only source for the report, so no later step reads the file by hand: Step 03 reads its `pairVerdicts`, and Step 05 its `coveragePercentage`, `coverageMeasured` and `path`. Set `vs_report_available` to true when there is one (its `status` is `ok`), and to false when the probe found none, `none` was typed or passed with `--vs-report-path`, or the helper is unavailable; set `vs_report_path` to its `path`.

If `{validateFeasibilityReportHelper}` has no existing candidate, or `uv` cannot run it, no report is read: set `vs_report_available: false` and say "VS report not read: the feasibility-report helper is unavailable." (in headless, log it). Neither the report's file name nor its verdict table is ever worked out by hand.

**Scope hint (optional, `--scope-skills`):** If `--scope-skills <names>` was provided, store the comma-separated names as `{scope_skills}`, as given: gap analysis (Step 02 §2b) takes them as the in-scope skill set, and Step 02 §3 checks each against the inventory and names any that is not an inventory skill instead of dropping it silently. If absent, leave `{scope_skills}` empty; Step 02 derives scope from the architecture document instead.

### 2. Scan Skills Folder

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins.

**Primary path — deterministic enumeration via shared helper:**

```bash
uv run {enumerateStackSkillsHelper} enumerate "{skills_output_folder}" --pairs --reliability
```

The helper reads only the skills SKF generated. For each top-level folder (links, dot-names, `_batch` and `.skf-` names aside) it takes the version the `active` link names when that version's `{name}/metadata.json` carries an SKF marker, else the highest version whose `metadata.json` does, else a flat root `SKILL.md` beside a marked `metadata.json`; it never reads the export manifest. It resolves that package's exports from `metadata.json` `exports`, else a `references/*.md` `## API` or `## Exports` section, else a SKILL.md `## Exports` or `## API Surface` section, and follows `composes:` to find cycles. Each `skills[]` entry has `name` (the folder name), `path` (the package, relative to `{skills_output_folder}`: `x/active/x`, `x/<version>/x` or `x`), `exports`, `exports_source` (`metadata`, `references`, `skill-md` or `unknown`), `confidence` (`T1`, `T2` or `T1-low`, from the exports source — not metadata's `confidence_tier`) and `metadata_hash`. `warnings[]` names per-skill problems, each starting `<name>: `: a `metadata.json` or version folder that cannot be read (including one that keeps SKF from telling whether it generated the folder), an SKF package with no `SKILL.md`, no exports found, and `composes` cycles; a folder with no skill in it is skipped silently. Cache the result as `skill_inventory`, and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count`, `{inventory_warnings}` ← `warnings`, `{pairs}` ← `pairs` and `{pair_count}` ← `pair_count`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders, such as a module's own skills in a shared skills folder, are not in `skills[]` and count toward neither `{skill_count}` nor `{warning_count}`.

Each entry also carries the fields the helper reads from `metadata.json`, so no step opens that file for them: Step 02 reads `language`, and the `source_repo_basename` and `source_root_basename` that name the repository and folder a skill was built from, which it matches against the architecture document.

`--pairs` additionally attaches `skill_inventory.pairs` — the complete, deterministic set of unique `{library_a, library_b}` combinations over the skills SKF generated only (`itertools.combinations`, sorted-name order, `pair_count == N*(N-1)/2`) — plus `skill_inventory.pair_count`. Cache both alongside the inventory. This is the exact pair set Step 02 (gap analysis) iterates; the helper owns the combinatorics, so a pair can never be silently dropped or duplicated at larger N and downstream steps read the set rather than re-deriving it.

`--reliability` adds `inventory_reliable` (bool), `unreliable_ratio` (float), `skill_count` and `warning_count`, over the skills SKF generated and their warnings, so the reliability threshold lives in one unit-tested place and this step reads a boolean rather than re-deriving a ratio.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with: "Inventory scan unreliable — {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [RA]." In headless, emit the error envelope.

**Fallback path — graceful degradation when the helper is unavailable:** If `{enumerateStackSkillsHelper}` has no existing candidate, fall through to the LLM-driven inventory: walk `{skills_output_folder}`, resolving each top-level folder in the helper's order and recording the helper's entry fields. Only a package whose `metadata.json` carries an SKF marker is a skill: `generated_by` is `quick-skill`, `create-skill` or `create-stack-skill`, `tool_versions` has an `skf` key, or `skill_type` is `single`, `individual` or `stack` together with `forge_tier` or `confidence_tier`. A folder whose packages have no such `metadata.json` goes into `{not_skf_output}` without counting a warning; a `metadata.json` that cannot be read counts as one warning, and so does a marked package with no `SKILL.md` or no exports found. Cache the entries as `skill_inventory`, and bind `{skill_count}` to the number of skills found, `{warning_count}` to the number of warnings counted and `{inventory_warnings}` to those warnings, each starting `<name>: `. Display the skipped line as above. On this degraded path only — with no helper to consult — treat the run as unreliable and HALT the same way if warnings exceed one in five (`{warning_count} / ({skill_count} + {warning_count}) > 0.20`).

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 1 skill SKF generated must exist (`{skill_count}`)
- If none: "**Cannot proceed.** No skill SKF generated was found in `{skills_output_folder}`. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [RA]." When `{not_skf_output}` is non-empty, append: "Skipped (not SKF output): {not_skf_output}."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`). In headless, emit the error envelope.
- If exactly 1 skill SKF generated was found: "⚠️ Proceeding with 1 skill. Note: gap analysis will find no gaps — pairwise analysis requires at least 2 skills. Step 02 will still execute and issue an appropriate notice. Issue detection and improvement detection will proceed normally."

**Output paths (`{outputFolderPath}`, `forge_data_folder`):** both were asserted non-empty (config-completeness → exit 3, `output-folder-unconfigured` / `forge-folder-unconfigured`) and then probed for writability (→ exit 4, `write-failed`) at On-Activation §5. If either was unconfigured or unwritable the run already halted there, so both are guaranteed present and writable here — no re-check needed.

**Check architecture document:**
- Confirm it was loaded successfully in section 1
- If not: HALT with error (should not reach here if section 1 validation passed)

### 3c. Reset RA State File

Create (or overwrite) `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header:

```markdown
<!-- RA state for {project_name} — generated {current_date} -->
```

Then append a `<!-- [RA-VS] ... -->` block: the `path`, `generatedAt`, `coveragePercentage` and `coverageMeasured` of `{vs_report}` when `vs_report_available` is true, or `none`. If context degrades on a long run, Step 03 reads the report again from that `path` and checks its `generatedAt`, and Step 05 reads the block back.

This ensures steps 02-04 append to a clean slate and context recovery in step 5 never loads stale findings from a prior run.

On any write failure (read-only mount, disk full, permissions denied): HALT (exit code 4, `halt_reason: "write-failed"`) with the captured error and emit the error envelope. The On-Activation §5 probe should have caught this earlier — if it surfaces here, the filesystem state changed mid-workflow.

### 4. Load Refinement Rules

Load `{refinementRulesData}` for reference by downstream steps.

Extract: gap detection rules, issue detection rules, improvement detection rules, citation format, and preservation rules.

### 5. Display Initialization Summary

"**Architecture Refinement Initialized**

| Field | Value |
|-------|-------|
| **Architecture Doc** | {architecture_doc} |
| **VS Report** | {vs_report_path, or 'None: issue detection will use skill data only'} |
| **Skills Loaded** | {skill_count} |

**Skill Inventory:**

| Skill | Exports | Exports source | Confidence |
|-------|---------|----------------|------------|
| {name} | {number of exports} | {exports_source} | {confidence} |

**Proceeding to gap analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

