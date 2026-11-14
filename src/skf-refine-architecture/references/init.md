---
nextStepFile: 'gap-analysis.md'
refinementRulesData: '{refinementRulesPath}'
# The findings a step 5 review dropped from an earlier refinement (compile.md §8).
dismissedFile: '{outputFolderPath}/.ra-dismissed-{arch_project_name}.json'
# The draft compile.md builds, which a stopped step 5 review leaves behind (§1a).
draftFile: '{forge_data_folder}/.skf-ra-draft-{project_name}.md'
# Each probe order resolves to its first existing path.
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
# §1b hashes the architecture document with it, and §1a compares that hash with a stopped run's.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
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

### 0. Pre-flight: Config, Write Probe and Run Folder

These run before the first prompt, in this order, so an empty path halts as missing config (exit 3), not as a write failure. Until the run folder exists, a headless halt here passes its payload on stdin with the `emit-halt` block SKILL.md On Activation §5 shows, not through `{run_dir}/halt.json`.

**Config-completeness (exit 3).** If `{outputFolderPath}` is empty: HALT (exit code 3, `halt_reason: "output-folder-unconfigured"`) at phase `on-activation:config`: "Set `output_folder` in config.yaml, then re-run [RA]." If `{forge_data_folder}` is empty: HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `on-activation:config`: "Set `forge_data_folder` in config.yaml, then re-run [RA]."

**Write probe (exit 4).** Check that both paths are writable before any prompt:

```bash
for dir in "{outputFolderPath}" "{forge_data_folder}"; do
  mkdir -p "$dir" && \
    printf 'probe' > "$dir/.skf-write-probe" && \
    rm "$dir/.skf-write-probe"
done
```

On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:write-probe`, with `"path"` set to the folder that failed.

**Run folder (exit 4).**

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
```

If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." Once it exists and `{customization_resolver_unavailable}` is set, record the reason in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`.

Every halting pre-flight check has now passed: run each entry in `workflow.activation_steps_append` in order, then go on to §1.

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
1. **Architecture document path** (REQUIRED): {IF `{vs_architecture_doc}` is set:}The [VS] report verified `{vs_architecture_doc}`: press Enter to use it, or give another path.{ELSE:}your project's architecture doc to refine{END IF}
2. **VS feasibility report path** (OPTIONAL): {IF the probe found a report:}Found the [VS] report from {vs_report_date}: press Enter to use it, or give another path.{ELSE:}From a previous [VS] Verify Stack run, for additional context.{END IF} Type `none` to refine without a report.

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

`{vs_report_date}` is the date in the report's `generatedAt` (the probe's, or the path mode's), or the file name of its `path` when `generatedAt` is null. `{vs_architecture_doc}` is the `architectureDoc` of the report JSON in hand when the prompt shows (the path mode's when it read the `--vs-report-path` report, which runs before the prompt, else the probe's), when it is not null and names a file that exists (a relative path resolves from `{project-root}`), else empty.

Wait for user input. Store the validated architecture document path as `architecture_doc`: Enter at the architecture question takes `{vs_architecture_doc}` when it is set. **GATE [default: use args]:** a question a flag answered is not asked, and headless answers the rest with their defaults. If `{headless_mode}` and `--architecture-doc` was provided: use that path and auto-proceed, log: "headless: using provided architecture path". If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) at phase `init:inputs`, since headless never takes `{vs_architecture_doc}` as its default. The report question's default is the probe's report when its `status` is `ok`: with no `--vs-report-path`, headless takes it and logs "headless: using the [VS] report found at {path}", or logs "headless: no [VS] report for {project_name}; issue detection will use skill data only" when the probe found none.

A headless run that answered the report question this way (no `--vs-report-path`, or one it could not read) records the decision: `{"gate": "init.vs-report", "default_action": "use-found-report", "taken_action": "use-found-report", "reason": "<the line logged>", "evidence": {"vs_report_path": "<path>"}}` when the probe found a report, or `{"gate": "init.vs-report", "default_action": "no-report", "taken_action": "no-report", "reason": "<the line logged>"}` when it found none.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt: Display "Cancelled: no refinement was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `init:inputs`.

**Validate the architecture document:** when the file is missing or unreadable, say "Architecture document not found at `{path}`. Provide a valid path." and HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `init:architecture-doc`, with `"path"` set to the path given, if the user cannot provide one (a headless run, at once).

**Resolve `{arch_project_name}`**, which names the refined output file: the `project_name` the architecture document's YAML frontmatter declares, else the config `{project_name}`. The RA state file and the VS report probe stay keyed on the config `{project_name}`.

**Record the VS report.** Cache the JSON of the report this run uses as `{vs_report}`: no step reads the report file by hand. Set `vs_report_available` to true when there is one (its `status` is `ok`), and to false when the probe found none or `none` was typed or passed with `--vs-report-path`; set `vs_report_path` to its `path`.

**The document the report verified.** When the `architectureDoc` of `{vs_report}` is not null and names another file than `{architecture_doc}` (each relative path resolved from `{project-root}`), say once: "The [VS] report from {vs_report_date} verified `{architectureDoc}`, not `{architecture_doc}`: its verdicts are about that document." (in headless, log it).

**Scope hint (optional, `--scope-skills`):** If `--scope-skills <names>` was provided, store the comma-separated names as `{scope_skills}`, as given: Step 02 §2b takes them as the in-scope skill set, and Step 02 §3 checks each against the inventory. If absent, leave `{scope_skills}` empty.

### 1a. Resume a Stopped Review

Only an interactive run looks for a stopped review: a headless run skips this section and always starts a new run.

A step 5 review that stopped before its [C] or [X] (the session ended or lost its context, say) leaves its run folder, its draft and the RA state file behind, so the review can go on without the analysis running again. Read the `<!-- [RA-RUN] ... -->` block of `{forge_data_folder}/ra-state-{project_name}.md`, one `key=value` per line as §3c writes it, and offer to resume only when all of these hold:

- the state file holds that block with every key §3c writes, and its `headless_mode` is `false`: a block an older version wrote on one line lacks keys, and a headless run's sink holds decisions an interactive result would then report;
- its `architecture_doc` names the same file as `{architecture_doc}`;
- the folder its `run_dir` names holds `insertion-plan.json` and `apply.json`, which `apply` writes only once it has built a draft;
- `{draftFile}` exists: step 5's [X] deletes the draft and its [C] moves it into place, so a review that ended either way leaves none, while a [C] whose `promote` halted keeps it for the resumed review to approve again;
- the document is as that run read it: resolve `{hashContentHelper}` from `{hashContentProbeOrder}` (first existing path wins) and run §1b's call, `uv run {hashContentHelper} hash "{architecture_doc}"`, which must print a `content_hash` that is not empty and equals the block's `architecture_doc_hash`. The kept plan's anchors and findings come from that run's copy of the document, so applied to an edited one it would insert findings about text the document no longer holds.

Otherwise say nothing and go on to §1b. The one exception: when the first four hold and only the last does not (the hashes differ, or either is empty), say "A review of this document stopped before it finished, but the document changed after that run read it, or cannot be compared with it, so this run starts over." and go on to §1b.

When they all hold, `{stopped_timestamp}` is the block's `timestamp` and `{stopped_run_dir}` its `run_dir` (`{timestamp}` and `{run_dir}` are still this run's). Show:

"**A review of this document stopped before it finished.** Its draft, from the run of {stopped_timestamp}, is at `{draftFile}`, and its plan in `{stopped_run_dir}`. Resuming rebuilds that draft from the plan and shows the review again with that run's settings: its scope, its [VS] report, its output folder and its refinement rules, so the report you chose above and `--scope-skills` do not apply to it. A new run reads the skills again and builds a new draft, and leaves that run's folder as it is."

Display: **Select:** [R] Resume the review of the draft from {stopped_timestamp} | [N] Start a new run

Wait for the user's choice.

- IF R: delete the run folder this activation made, which holds at most the resolver warning: `rm -rf "{run_dir}"`. Then bind each key of the block as §3c maps it, so `{run_dir}`, `{timestamp}` and every other binding there are the stopped run's, and bind `{analysis_doc}` ← `{run_dir}/analysis-doc.md`. When `{customization_resolver_unavailable}` is set, add it to that folder's run sink with the file write and the `record` call §0 uses. Then run §4's `rules` check, which halts as §4 says, except that its message ends "Fix that copy, or run [RA] again and choose [N] to start a new run." in place of its last sentence: the path is the stopped run's, which removing the override does not change. Set `{resumed_review}` to true, and load, read the full file and then execute `references/compile.md`: its review starts again from the kept plan. §1's report answer and `--scope-skills` do not apply to it, since compile reads the stopped run's `[RA-VS]` and `[RA-SCOPE]` blocks.
- IF N: leave the stopped run folder as it is and go on to §1b. Once §3c replaces the state file, that review can no longer be resumed.
- IF cancel / exit / [X] / q / :q: display "Cancelled: no refinement was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `init:resume`.
- IF anything else: answer it (a question about the stopped review, say), then redisplay the menu.

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

**Hash the document.** Resolve `{hashContentHelper}` from `{hashContentProbeOrder}` (first existing path wins) unless §1a did, and run:

```bash
uv run {hashContentHelper} hash "{architecture_doc}"
```

Bind `{architecture_doc_hash}` ← the `content_hash` it prints: §3c records it, so a later run's §1a resumes this run's review only while the document is as this run read it. When no candidate exists, or the call exits non-zero or prints no `content_hash`, bind it empty and go on: this run's review then cannot be resumed.

### 2. Scan Skills Folder

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists, `uv` cannot start it, or the command below exits non-zero (a `{skills_output_folder}` that does not exist, say), HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`: "Refine Architecture cannot list the skills: {its first stderr line, or with no candidate: `skf-enumerate-stack-skills.py` is not installed. Re-install SKF (`npx bmad-module-skill-forge install`).}" No step walks `{skills_output_folder}` by hand.

```bash
uv run {enumerateStackSkillsHelper} enumerate "{skills_output_folder}" --reliability > "{run_dir}/skill-inventory.json"
```

The helper reads only the skills SKF generated. Each `skills[]` entry has `name`, `path`, `exports`, `exports_source`, `confidence` (from the exports source, not metadata's `confidence_tier`), the `language` Step 02 reads, and the `source_repo_basename` and `source_root_basename` the `terms` call below reads, so no step opens `metadata.json`; `warnings[]` names per-skill problems, each starting `<name>: `. `--reliability` adds `inventory_reliable` with the counts behind it. Read the JSON it writes to `{run_dir}/skill-inventory.json` as `skill_inventory` (Step 02 §4 and Step 03 §3 read each skill's `exports[]` from that file), and bind `{not_skf_output}` ← `not_skf_output`, `{inventory_reliable}` ← `inventory_reliable`, `{warning_count}` ← `warning_count`, `{skill_count}` ← `skill_count` and `{inventory_warnings}` ← `warnings`. When `{not_skf_output}` is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}". Those folders count toward neither `{skill_count}` nor `{warning_count}`.

**Write the skill terms.** The same helper writes, from the saved inventory, the names the later steps find each skill by: the mentions helper (Step 02 §2) in the document, the `verdicts` join (Step 03 §4) in the [VS] report, and Step 03 §2 when it maps a claim to its skill.

```bash
uv run {enumerateStackSkillsHelper} terms --inventory "{run_dir}/skill-inventory.json" -o "{run_dir}/skill-terms.json"
```

`{run_dir}/skill-terms.json` holds one `{"name", "aliases"}` per skill, its aliases the entry's `source_repo_basename` and `source_root_basename` that are not null (the repository and folder the skill was built from, so a skill named `oms-cognee` is matched where the document says "Cognee"); the helper's module docstring gives the contract. If `uv` cannot start it or it exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`: "Refine Architecture cannot write the skill terms: {its first stderr line}." No step builds the terms by hand.

**Failure-budget guard:** If `{inventory_reliable}` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `init:inventory` with: "Inventory scan unreliable: {warning_count} warning(s) across {skill_count} skill(s) SKF generated: {inventory_warnings}. Fix the skills named there (re-save an unreadable `metadata.json` as plain UTF-8 JSON or restore it from version control, and regenerate a skill whose exports are missing), then re-run [RA]."

### 3. Validate Minimum Requirements

When `{skill_count}` is 0, say "**Cannot proceed.** No skill SKF generated was found in `{skills_output_folder}`. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [RA]." (appending "Skipped (not SKF output): {not_skf_output}." when `{not_skf_output}` is non-empty) and HALT (exit code 5, `halt_reason: "insufficient-skills"`) at phase `init:skills`. When it is 1, say "⚠️ Proceeding with 1 skill: gap analysis needs at least 2 and will find no gaps; issue and improvement detection run normally."

### 3c. Reset RA State File

Create (or overwrite) `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header:

```markdown
<!-- RA state for {project_name} — generated {current_date} -->
```

Then append a `<!-- [RA-VS] ... -->` block: the `path`, `generatedAt`, `coveragePercentage` and `coverageMeasured` of `{vs_report}` when `vs_report_available` is true, or `none`. Step 03 reads the report again from that `path` and checks its `generatedAt`, and Step 05 reads the block back if context degrades on a long run.

Then append the run's bindings as a `<!-- [RA-RUN] ... -->` block, one `key=value` per line, since a path can hold spaces:

```markdown
<!-- [RA-RUN]
run_dir={run_dir}
timestamp={timestamp}
architecture_doc={architecture_doc}
architecture_doc_hash={architecture_doc_hash}
arch_project_name={arch_project_name}
headless_mode={headless_mode}
output_folder_path={outputFolderPath}
refinement_rules_path={refinementRulesPath}
previous_pass={previous_pass}
-->
```

A key's value is everything after the first `=` of its line, empty when the line ends there (an `architecture_doc_hash` §1b could not compute, say). Each key reads back as the binding its line names: `output_folder_path` as `{outputFolderPath}`, `refinement_rules_path` as `{refinementRulesPath}`, and every other key as the binding of its own name. The block holds no `on_complete` hook: the forge data folder may be committed, and a personal hook in `_bmad/custom/skf-refine-architecture.user.toml` can hold a token, so Step 06 binds a lost `{onCompleteCommand}` from the customization resolver instead. Steps 02 to 06 read these bindings back from the block when context degrades, since the run's records live in `{run_dir}`, and §1a reads a stopped run's.

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

