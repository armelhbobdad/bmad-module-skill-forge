---
outputFile: '{outputFolderPath}/refined-architecture-{arch_project_name}.md'
nextStepFile: 'health-check.md'
# The records scripts/skf-check-preservation.py wrote at step 1 and step 5.
inspectResult: '{run_dir}/inspect.json'
applyResult: '{run_dir}/apply.json'
promoteResult: '{run_dir}/promote.json'
preservationScript: 'scripts/skf-check-preservation.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Render the user-facing summary in {document_output_language}. -->

# Step 6: Present Report

## STEP GOAL:

Present the complete refinement summary, write the result contract, run the post-completion hook, and offer the user a walkthrough of the refinements before the run finishes. Every count comes from the files the preservation script wrote. Chains to the shared health check when the user finishes.

## Rules

- Focus only on presenting the completed refinement: no new analysis
- Do not discover new gaps, issues, or improvements, and do not modify the refined document
- Take every count from `{applyResult}`, never from a `## Refinement Summary` in a document: an architecture document refined before can hold an older one
- The result contract is written before the final menu, so that menu's [X] finishes the run: it never cancels it
- Chains to the local health-check step via `{nextStepFile}` after completion: the user-facing summary is not the terminal step

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "refined_path": "{outputFile}"}` (step 5 promoted it), resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load the Run's Numbers

**Run recovery:** if `{run_dir}` or `{arch_project_name}` is no longer bound, read it from the `<!-- [RA-RUN] -->` block of `{forge_data_folder}/ra-state-{project_name}.md`.

Stage the result contract's payload from the records of step 1's check for an earlier pass, step 5's build of the draft and its promotion to `{outputFile}`:

```bash
uv run {preservationScript} context --inspect "{inspectResult}" --apply "{applyResult}" --promote "{promoteResult}" --out "{run_dir}/result-context.json"
```

- **0:** `{run_dir}/result-context.json` holds the payload §4 hands the emitter.
- **2** with a JSON: a record is missing or is not its step's (`error` names it): HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `report:numbers`: "⚠️ The record of the refined document's build or promotion is missing ({error}). Re-run [RA] from the beginning." **2 with no JSON:** fix the malformed call and run it again.
- **3:** HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:numbers`, naming its `error`.
- If `uv` cannot start the script: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `report:numbers`.

**Bind the metrics from the files:** `gap_count`, `issue_count` and `improvement_count` from `counts.gap`, `counts.issue` and `counts.improvement` of `{applyResult}`; `critical_count`, `major_count` and `minor_count` from `counts.issue_tiers`; `high_count`, `medium_count` and `low_count` from `counts.improvement_tiers`; `unverified_count` from `counts.unverified` and `unverified_technologies` from its `unverified_technologies` (comma-separated, or `none`), the list the count was taken from; `skill_count` from `counts.skills`; the Evidence Sources from `evidence`; `{ranges}` from the `legacy` entries of `set_aside`, each as `start`-`end`; `previous_refined_path` from the `previous` of `{promoteResult}` (null when no earlier refined document was there); `previous_pass` from `{inspectResult}`; and `vs_coverage` from `{vs_report}` as Step 05 §5 wrote it (the `[RA-VS]` block) when a VS report was used. With no VS report, leave the VS Coverage row out of the summary below.

### 2. Display Summary

"**Refine Architecture: Refinement Complete**

---

| Metric | Count |
|--------|-------|
| **Gaps Filled** | {gap_count} |
| **Issues Flagged** | {issue_count} (Critical: {critical_count}, Major: {major_count}, Minor: {minor_count}) |
| **Improvements Suggested** | {improvement_count} (High: {high_count}, Medium: {medium_count}, Low: {low_count}) |
| **Skills Used as Evidence** | {skill_count} |
| **Not verified (no skill)** | {unverified_count} ({unverified_technologies}) |
| **VS Coverage** | {vs_coverage} |

**Evidence Sources:** (which skills contributed evidence)

{One row per entry of `evidence`: the skill and how many refinements cite it}

---

**Your refined architecture is at:** `{outputFile}`
{IF previous_refined_path:}Your earlier refined document was kept as `{previous_refined_path}`.
{IF previous_pass:}The earlier Refine Architecture pass in your document was set aside: these refinements replace it.

{IF `{ranges}` is empty:}The original architecture content is preserved in full: the preservation script found every line unchanged before step 5 promoted the draft.{ELSE:}Every original line is preserved except lines {ranges} of the document this run refined (kept as `{previous_refined_path}` when it was the refined document itself), which an earlier pass left without RA markers: they were set aside unchecked, so text of your own there is not in the refined document.{END IF} Every refinement sits between `<!-- RA:BEGIN ... -->` and `<!-- RA:END -->` marker lines, in `[!NOTE]`, `[!WARNING]` and `[!TIP]` callout blocks."

### 3. Present Next Steps

"**Recommended next steps:**

{IF unverified_count > 0:}
**Generate the missing skills first:** no skill covers {unverified_technologies}, so nothing checked what the architecture says about them. Create their skills with **[CS] Create Skill** or **[QS] Quick Skill**, then re-run **[RA]** before moving on to **[SS] Stack Skill**.

1. **Review the refined document:** to accept a refinement, move what you keep into your own prose, outside its `<!-- RA:BEGIN ... -->` and `<!-- RA:END -->` markers. Anything still between RA markers is replaced the next time you run [RA] on this document; delete a block, markers included, to drop it from this copy (a later [RA] run that finds the same thing again adds it back)
2. **[SS] Stack Skill**: compose-mode activates automatically when SS detects existing individual skills without a codebase; provide this refined architecture doc as the architecture document when prompted
3. **Re-run [VS] Verify Stack** if you made changes based on issue corrections, to confirm resolution

{IF issues with Critical severity were found:}
**⚠️ Attention:** {critical_count} critical issue(s) were flagged. These indicate fundamental contradictions between your architecture and the verified API surfaces. Address these before proceeding to stack skill composition."

### 4. Result Contract

The shared emitter writes the result contract (per `shared/references/output-contract-schema.md`, which resolves relative to the SKF module root: `{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development) and prints the envelope from the payload §1 staged, every count from `{applyResult}`. Run, in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-refine-architecture --run-dir "{run_dir}" --result-dir "{outputFolderPath}" < "{run_dir}/result-context.json"
```

It writes `{outputFolderPath}/refine-architecture-result-{YYYYMMDD-HHmmss}.json` and its `refine-architecture-result-latest.json` copy (a copy, not a symlink: the stable path pipelines read), stamping the time, the run id, the run's warnings and the auto-decisions the gates recorded, and prints the `SKF_REFINE_ARCHITECTURE_RESULT_JSON:` line on stdout. When `{headless_mode}` is true, display the line verbatim. Bind `{result_path}` ← the line's `result_path`: a result file that could not be written leaves it null and a `result_file_write_failed` warning in the line, and the run still finishes. If the emitter exits non-zero, run §1's `context` command and the emitter once more; if it fails again, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:result-contract`: the run's result contract could not be written.

### 5. Post-Completion Hook (optional)

Skip this section when `{onCompleteCommand}` (resolved at SKILL.md On Activation §4 from `workflow.on_complete`) is empty, the bundled default. When `{result_path}` is null, skip it too, with one line saying no result file was written for the hook to read. Otherwise invoke it now, after the emitter wrote both result files, so a notifier, indexer or chained pipeline sees a complete record:

```bash
{onCompleteCommand} --result-path="{result_path}"
```

Run it with a bounded timeout. On success, continue. On a non-zero exit, a timeout or any other failure, display "**Warning:** on_complete failed: {reason}" (for example `exit {N}: {stderr_first_line}`) on its own line of this report, in headless too, and continue: the hook never fails the workflow, since the refined document and its result contract are already written. The warning is in neither the envelope nor the result file: the hook reads the result file, so both are written before it runs.

### 6. Present Menu

Display: "**[R] Review changes in detail** | **[X] Finish**"

The result contract is written, so [X] finishes the run with exit code 0, and so do `exit`, `cancel`, `q` and `:q` here: this menu is the one place where they do not cancel.

#### Menu Handling Logic:

- **IF R:** Walk through each refinement with its full evidence citation:
  1. First, all gaps with their evidence and proposed integration paths
  2. Then, all issues ordered by severity with architecture claim vs. skill reality
  3. Finally, all improvements ordered by value with untapped capability details
  After completing the walkthrough, redisplay the menu.

- **IF X:** "**Refined architecture saved to:** `{outputFile}`

Re-run **[RA] Refine Architecture** anytime after updating your skills or architecture document: run on this refined document, it replaces the blocks between RA markers with a current set and keeps everything else.

**Architecture refinement complete.**"

  Then delete the run folder, whose analysis copy, plan and payloads the run no longer needs: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`: the health-check step is the true terminal step of this workflow.

#### EXECUTION RULES:

- This is the exit gate: halt for the user's choice. [R] walks every refinement with its evidence (repeatable: re-shows this menu after each pass); [X] finishes the run and chains to the health check. Headless auto-selects [X].
