---
nextStepFile: 'gap-analysis.md'
refinementRulesData: '{refinementRulesPath}'
# The findings a step 5 review dropped from an earlier refinement (compile.md §8).
dismissedFile: '{outputFolderPath}/.ra-dismissed-{arch_project_name}.json'
# Each probe order resolves to its first existing path.
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
preservationScript: 'scripts/skf-check-preservation.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Refinement

## STEP GOAL:

Load the architecture document (required), scan the skills folder to build a skill inventory with metadata, load the optional VS feasibility report for context, validate that all inputs exist and meet minimum requirements, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and validating prerequisites — do not perform analysis

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Recording a decision or a warning.** A gate below that picks its default for a headless run records that decision in the run sink the moment it decides: stage the decision it shows as `{run_dir}/decision.json`, then run the first command. A warning goes in with the second:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-refine-architecture --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'
```

### 1. Accept Input Documents

`--architecture-doc <path>` and `--vs-report-path <path>` apply in every mode, as the SKILL.md Invocation Contract says: each one answers its question below, which is then not asked, in an interactive run as in headless.

**Refine without a report.** `--vs-report-path none` answers the report question as typing `none` at the prompt does, in every mode: skip the probe and the path mode below, use no report, and say "VS report skipped (--vs-report-path none)." (in headless, log it).

**Find the [VS] report first.** Unless `--vs-report-path none` was passed, resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`; first existing path wins. If no candidate exists, or `uv` cannot start it, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:feasibility-validator`: "Refine Architecture cannot read a [VS] report: `skf-validate-feasibility-report.py` is not installed. Re-install SKF (`npx bmad-module-skill-forge install`), or refine without a report with `--vs-report-path none`."

Unless `--vs-report-path` was passed, run the probe (the first command) before asking anything: it reads the `-latest` report [VS] wrote for `{project_name}`, whose file name the helper builds. A path from `--vs-report-path`, or one typed at the prompt, goes through the path mode (the second), which checks and reads that file exactly as `--locate` does and prints the same JSON:

```bash
uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"
uv run {validateFeasibilityReportHelper} "{vs_report_path}"
```

Each checks the report against the shared feasibility-report schema and prints one JSON (its module docstring lists every key). Branch on its exit code:

- **0 with `status: "ok"`:** the report to use. The probe's becomes the report question's default below.
- **0 with `status: "not-found"`** (the probe only): there is no [VS] report for this project, so the question has no default.
- **1** (the report breaks the contract), or **2** with a JSON from the probe (the report exists but could not be read): HALT as **Unusable VS report** says below.
- **2** with a JSON from the path mode (the file is missing or could not be read; its `error` says which): in an interactive run, show `error`, run the probe above if it has not run, and ask the report question again. In headless, log "headless: VS report not read at {vs_report_path} ({error}); probing for the [VS] report instead", record the decision `{"gate": "init.vs-report-unreadable", "default_action": "probe", "taken_action": "probe", "reason": "<the line logged>", "evidence": {"given": "<vs_report_path>", "error": "<error>"}}`, then run the probe above and take its outcome as if `--vs-report-path` had not been passed.
- **2 with no JSON** on stdout: argparse refused the call itself (its usage error is on stderr). It says nothing about the report: fix the call and run it again.

**Unusable VS report.** A report that breaks the contract is never interpreted: HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:vs-report`, with `"path"` set to the report's `path`. Name the report's `path` and each problem its JSON shows: a `schemaVersion` other than `1.0` (`schemaVersionOk` is false), sections missing or out of order (`missingHeadings`, `orderViolations`), no verdict table (`verdictTableFound` is false), a second verdict table (at line `duplicateVerdictTableLine`), each entry of `unknownTokens`, or the `error` of a report that could not be read. End with: "Re-run [VS] to write a current report, pass another one with `--vs-report-path <path>`, or refine without one with `--vs-report-path none`."

**Ask for the inputs.** Ask only for what no flag answered:

"**Refine Architecture: Evidence-Backed Refinement** (additive: never deletes original content).

If you wanted to *verify* the stack first, type `cancel` and run `[VS] Verify Stack`; if no skills exist yet, run `[CS] Create Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED): your project's architecture doc to refine
2. **VS feasibility report path** (OPTIONAL): {IF the probe found a report:}Found the [VS] report from {vs_report_date}: press Enter to use it, or give another path.{ELSE:}From a previous [VS] Verify Stack run, for additional context.{END IF} Type `none` to refine without a report.

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

`{vs_report_date}` is the date in the probe's `generatedAt`, or the file name of its `path` when `generatedAt` is null.

Wait for user input. Store the validated architecture document path as `architecture_doc`. **GATE [default: use args]:** a question a flag answered is not asked, and headless answers the rest with their defaults. If `{headless_mode}` and `--architecture-doc` was provided: use that path and auto-proceed, log: "headless: using provided architecture path". If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) at phase `init:inputs`. The report question's default is the probe's report when its `status` is `ok`: with no `--vs-report-path`, headless takes it and logs "headless: using the [VS] report found at {path}", or logs "headless: no [VS] report for {project_name}; issue detection will use skill data only" when the probe found none.

A headless run that answered the report question this way (no `--vs-report-path`, or one it could not read) records the decision: `{"gate": "init.vs-report", "default_action": "use-found-report", "taken_action": "use-found-report", "reason": "<the line logged>", "evidence": {"vs_report_path": "<path>"}}` when the probe found a report, or `{"gate": "init.vs-report", "default_action": "no-report", "taken_action": "no-report", "reason": "<the line logged>"}` when it found none.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt: Display "Cancelled: no refinement was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `init:inputs`.

**Validate the architecture document:** when the file is missing or unreadable, say "Architecture document not found at `{path}`. Provide a valid path." and HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:architecture-doc`, with `"path"` set to the path given, if the user cannot provide one (a headless run, at once).

**Resolve `{arch_project_name}`**, which names the refined output file: the `project_name` the architecture document's YAML frontmatter declares, else the config `{project_name}`. The RA state file and the VS report probe stay keyed on the config `{project_name}`.

**Record the VS report.** Cache the JSON of the report this run uses as `{vs_report}`: no step reads the report file by hand. Set `vs_report_available` to true when there is one (its `status` is `ok`), and to false when the probe found none or `none` was typed or passed with `--vs-report-path`; set `vs_report_path` to its `path`.

**Scope hint (optional, `--scope-skills`):** If `--scope-skills <names>` was provided, store the comma-separated names as `{scope_skills}`, as given: Step 02 §2b takes them as the in-scope skill set, and Step 02 §3 checks each against the inventory. If absent, leave `{scope_skills}` empty.

### 1b. Set Aside an Earlier Refinement Pass

Before §3c resets the state file, set aside any earlier Refine Architecture pass, whose annotations are not the user's text:

```bash
uv run {preservationScript} inspect --doc "{architecture_doc}" --stripped "{run_dir}/analysis-doc.md" -o "{run_dir}/inspect.json"
```

Bind `{analysis_doc}` ← `{run_dir}/analysis-doc.md`, the document with any earlier pass set aside: Steps 02 to 04 read the architecture document only through it, while Step 05 builds from `{architecture_doc}` itself. Bind `{previous_pass}` ← `previous_pass`. Then act on the script's exit code:

- **0** with `previous_pass` true: say "This document holds an earlier Refine Architecture pass ({signals}): its RA blocks ({marked_blocks} marked, {legacy_blocks} unmarked) are set aside, and this run writes one current set in their place. Refinements you moved into your own prose stay as they are." (in headless, log it). An unmarked block runs to the next heading, so it can hold text of yours: when `set_aside` holds a `legacy` entry, list each one's `start`-`end` lines and `first_line`, say "Text of your own in these lines is neither analyzed nor kept in the refined document: move it above the RA heading and re-run [RA] to keep it.", and record the warning `legacy_blocks_set_aside: lines <each start-end, comma-separated>`. When `malformed_markers` is not empty (an RA marker without its pair, kept with the text around it as the user's), name those lines and record the warning `malformed_ra_markers: lines <the lines, comma-separated>`.
- **0** with `previous_pass` false: nothing to set aside; the analysis copy equals the document.
- **2** with a JSON: the document cannot be read as UTF-8 text: HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:previous-pass`, naming its `error`, with `"path"` set to `{architecture_doc}`. **2 with no JSON:** a malformed call: fix it and run it again.
- **3:** the analysis copy could not be written: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:previous-pass`, naming its `error`.
- If `uv` cannot start the script: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:previous-pass`.

**Findings an earlier review dropped.** When `{previous_pass}` is true and `{dismissedFile}` exists, read it as `{dismissed_findings}`: the list of `{kind, skills, anchor, title, capability}` records Step 05 writes when its review drops a finding, which Steps 02 to 04 match as `references/finding-storage.md` says. Otherwise `{dismissed_findings}` is empty. A file that is not such a JSON list leaves it empty too: say "The record of findings dropped at an earlier review cannot be read ({reason}): they may come back in this run." (in headless, log it).

### 2. Scan Skills Folder

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists, `uv` cannot start it, or the command below exits non-zero (a `{skills_output_folder}` that does not exist, say), HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`: "Refine Architecture cannot list the skills: {its first stderr line, or with no candidate: `skf-enumerate-stack-skills.py` is not installed. Re-install SKF (`npx bmad-module-skill-forge install`).}" No step walks `{skills_output_folder}` by hand.

```bash
uv run {enumerateStackSkillsHelper} enumerate "{skills_output_folder}" --pairs --reliability
```

The helper reads only the skills SKF generated. Each `skills[]` entry has `name`, `path`, `exports`, `exports_source`, `confidence` (from the exports source, not metadata's `confidence_tier`), and the `language`, `source_repo_basename` and `source_root_basename` Step 02 reads, so no step opens `metadata.json`; `warnings[]` names per-skill problems, each starting `<name>: `. `--pairs` adds `pairs`, every unique `{library_a, library_b}` pair of the skills SKF generated, which Step 02 never re-derives, and `--reliability` adds `inventory_reliable` with the counts behind it. Cache the result as `skill_inventory`, and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count`, `{inventory_warnings}` ← `warnings`, `{pairs}` ← `pairs` and `{pair_count}` ← `pair_count`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders count toward neither `{skill_count}` nor `{warning_count}`.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `init:inventory` with: "Inventory scan unreliable: {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [RA]."

### 3. Validate Minimum Requirements

When `{skill_count}` is 0, say "**Cannot proceed.** No skill SKF generated was found in `{skills_output_folder}`. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [RA]." (appending "Skipped (not SKF output): {not_skf_output}." when `{not_skf_output}` is non-empty) and HALT (exit code 5, `halt_reason: "insufficient-skills"`) at phase `init:skills`. When it is 1, say "⚠️ Proceeding with 1 skill: gap analysis needs at least 2 and will find no gaps; issue and improvement detection run normally."

### 3c. Reset RA State File

Create (or overwrite) `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header:

```markdown
<!-- RA state for {project_name} — generated {current_date} -->
```

Then append a `<!-- [RA-VS] ... -->` block: the `path`, `generatedAt`, `coveragePercentage` and `coverageMeasured` of `{vs_report}` when `vs_report_available` is true, or `none`. Step 03 reads the report again from that `path` and checks its `generatedAt`, and Step 05 reads the block back if context degrades on a long run.

Then append `<!-- [RA-RUN] run_dir={run_dir} timestamp={timestamp} architecture_doc={architecture_doc} arch_project_name={arch_project_name} -->`: Steps 05 and 06 read these bindings back when context degrades, since the run's records live in `{run_dir}`.

On a write failure: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `init:state-file`, with `"path"` set to the state file, naming the captured error.

### 4. Check the Refinement Rules

`{refinementRulesData}` holds the house-style rules Steps 02 to 05 classify with: the bundled `references/refinement-rules.md`, or the copy `workflow.refinement_rules_path` names. The preservation script checks that it holds the six tables the steps read and that its tiers follow the rules the file's first section states, so the Refinement Summary can count each tier:

```bash
uv run {preservationScript} rules --rules "{refinementRulesData}"
```

- **0:** bind `{rule_tiers}` ← `tiers`, the tiers of the Issue Severity and Improvement Value tables in their order, which Step 05 writes into its plan.
- **1** (`status: "violations"`: it lacks a table or breaks a tier rule), or **2** with a JSON (`error` says why the file cannot be read): HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:rules`, with `"path"` set to it: "The refinement rules at `{refinementRulesData}` {cannot be read: {error} | break these rules: {the `detail` of each of its `violations`}}. Fix the copy `refinement_rules_path` names, starting again from the bundled `references/refinement-rules.md`, or remove that override." **2 with no JSON:** a malformed call: fix it and run it again.

### 5. Display Initialization Summary

"**Architecture Refinement Initialized**

| Field | Value |
|-------|-------|
| **Architecture Doc** | {architecture_doc} |
| **VS Report** | {vs_report_path, or 'None: issue detection will use skill data only'} |
| **Earlier RA pass** | {IF previous_pass: set aside ({signals}), replaced by this run ELSE: none} |
| **Skills Loaded** | {skill_count} |

**Skill Inventory:**

| Skill | Exports | Exports source | Confidence |
|-------|---------|----------------|------------|
| {name} | {number of exports} | {exports_source} | {confidence} |

**Proceeding to gap analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

