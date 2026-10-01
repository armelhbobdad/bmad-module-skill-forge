---
nextStepFile: 'report.md'
refinementRulesData: '{refinementRulesPath}'
outputFile: '{outputFolderPath}/refined-architecture-{arch_project_name}.md'
draftFile: '{forge_data_folder}/.skf-ra-draft-{project_name}.md'
planFile: '{run_dir}/insertion-plan.json'
applyResult: '{run_dir}/apply.json'
promoteResult: '{run_dir}/promote.json'
preservationScript: 'scripts/skf-check-preservation.py'
# The findings a review dropped, which Steps 02-04 leave out of a later run on the refined document.
dismissedFile: '{outputFolderPath}/.ra-dismissed-{arch_project_name}.json'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Compile the refined architecture document in {document_output_language}. -->

# Step 5: Compile Refined Architecture

## STEP GOAL:

Stage every finding of Steps 02-04 as an entry of an insertion plan, then let the preservation script build the refined document from the original as a draft: every original line copied unchanged, each finding's block where its anchor puts it, the Refinement Summary appended, and every line checked. Present the draft for review; only the review's [C] replaces `{outputFile}`.

## Rules

- Do not discover new gaps, issues, or improvements: use only what Steps 02-04 produced
- Never write the refined document yourself and never retype the original: `{preservationScript}` copies it, places the plan's blocks, checks that every original line survived and writes the draft

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Prepare the Original as Base

The base is the architecture document `{architecture_doc}` with any earlier Refine Architecture pass set aside, as Step 01 §1b set it aside in `{analysis_doc}`. You never copy it: §6's script reads `{architecture_doc}` itself and keeps every line unmodified. Read `{analysis_doc}` only to pick each finding's anchor.

**Run recovery:** if `{run_dir}`, `{timestamp}`, `{architecture_doc}` or `{arch_project_name}` is no longer bound, read it from the `<!-- [RA-RUN] -->` block of `{forge_data_folder}/ra-state-{project_name}.md`; `{analysis_doc}` is `{run_dir}/analysis-doc.md`.

**Context recovery check:** If gap, issue, or improvement findings from Steps 02-04 are not available in context, read the durability state from `{forge_data_folder}/ra-state-{project_name}.md`: its `<!-- [RA-GAPS] -->`, `<!-- [RA-ISSUES] -->`, and `<!-- [RA-IMPROVEMENTS] -->` comment blocks hold the complete formatted findings, and a `<!-- [RA-DISMISSED] -->` block, when there is one, holds the findings that match one a review dropped. If a section is still missing or contains only summary counts after recovery, HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `compile:recovery`: "⚠️ Context for the [Gaps|Issues|Improvements] analysis was lost and the durability state is insufficient to reconstruct findings. Re-run [RA] from the beginning: step 01 will reset the state file, then steps 02-04 will rebuild all findings."

**Scope recovery:** the plan (§6) also needs `{unverified_technologies}` from Step 02 §2b. If it is not in context, read it from the `<!-- [RA-SCOPE] -->` block of the same state file; if that block is missing too, HALT the same way (exit code 8, `halt_reason: "recovery-failed"`) at phase `compile:recovery`, naming the Scope analysis.

**VS report recovery:** the VS Coverage row (§5) needs the report JSON Step 01 §1 cached (`{vs_report}`). If it is not in context, read the `<!-- [RA-VS] -->` block of the same state file: it holds that report's `path`, `generatedAt`, `coveragePercentage` and `coverageMeasured`, or `none` when the run used no report. If that block is missing too, HALT the same way (exit code 8, `halt_reason: "recovery-failed"`) at phase `compile:recovery`, naming the VS report.

### 2. Plan the Gap-Fill Subsections

The insertion plan is one JSON object, written to `{planFile}` at §6 (the script's module docstring gives every field). Each finding becomes one entry of its `entries` list: an `id` (`gap-1`, `issue-1`, `improvement-1` and so on), its `kind` (`gap`, `issue` or `improvement`), the `anchor` that places it, the `skills` its evidence cites, and the `block` to insert. A finding stored under `[RA-DISMISSED]` gets no entry: §7 lists it, and §8 gives it one only when the user takes it back.

**Anchors.** An anchor is text copied exactly from one line of `{analysis_doc}`: a heading line such as `## Data Layer`, or the sentence a finding is about. It must occur on exactly one line (a heading anchor matches only a heading of its level and title); when several lines hold it, add `occurrence` (1-based) to pick one. An anchor of `null` sends the entry to its kind's fallback section at the end of the document. You choose the anchor, and the script decides the line: it refuses a plan with an anchor that is missing or ambiguous before it writes anything.

For each gap finding from Step 02:

- **anchor:** the heading of the section where this integration logically belongs. The script puts the block at the end of that section, one heading level deeper. `null` when no section fits: the script then collects the gap under `## RA: Additional Integration Paths`.
- **block** (the script sets the heading's level, so any number of `#` will do):

```markdown
#### RA: {Library A} <-> {Library B} Integration Path

> [!NOTE] **Gap Identified by Refine Architecture**
> This integration path was not documented in the original architecture but is supported by skill API evidence.

{Gap description with full evidence citation from Step 02}

**Proposed Integration:**
{Suggested architecture content describing how the libraries connect}
```

### 3. Plan the Issue Annotations

For each issue finding from Step 03, with `tier` its severity, a tier of the Issue Severity table of `{refinementRulesData}`:

- **anchor:** the contradicted claim, exactly as Step 03 recorded it from its line of `{analysis_doc}`. The script puts the callout right after the block that holds the claim: the paragraph, the whole list, the table, the blockquote or the code fence, so no list item, table row or code block is ever split. `null` when the claim cannot be located precisely: the script collects such issues under `## RA: Additional Issues Detected`, the most severe tier first.
- **block:**

```markdown
> [!WARNING] **Issue Detected by Refine Architecture** ({severity})
> Architecture states: "{quoted claim}"
> Skill reality: {contradicting evidence from skill}
> {IF VS report}: VS verdict: {verdict} for {pair}
>
> **Suggested Correction:** {specific correction with API evidence}
```

### 4. Plan the Improvement Suggestions

For each in-scope improvement finding from Step 04 (the `[RA-IMPROVEMENTS]` findings; out-of-scope improvements and synergies stay under `[RA-OUT-OF-SCOPE]` and never enter the refined document), with `tier` its value, a tier of the Improvement Value table of `{refinementRulesData}`:

- **anchor:** the heading of the section where the library is discussed, also when it appears there only in a table, code block or Mermaid diagram: the script puts the block at the end of that section, one heading level deeper, so it never splits them. `null` when no section discusses the library: the script then collects the improvement under `## RA: Additional Improvements Suggested`, the most valuable tier first.
- **block:**

```markdown
#### RA: Enhancement: {Improvement Title}

> [!TIP] **Improvement Suggested by Refine Architecture** ({value} value)
> {skill_name} provides `{api}` which is not currently leveraged.

{Full improvement description with evidence citation from Step 04}

**How to Incorporate:**
{Specific suggestion for updating the architecture}
```

### 5. Add Refinement Summary Section

The plan's `summary` is the `## Refinement Summary` section, which the script appends last. Leave the count placeholders below as they are: the script fills `{gap_count}`, `{issue_count}`, `{improvement_count}`, a `{<tier>_count}` for each severity and value tier, and `{evidence_rows}` from the plan's entries, `{unverified_count}` and `{unverified_technologies}` from its `unverified_technologies`, and `{skill_count}` from its `skill_count`, so no count is ever typed, and it refuses a summary that types the three totals. Fill every other placeholder yourself: it also refuses a placeholder it does not know. The section contains:

- **Header:** "Produced by: Refine Architecture workflow using {skill_count} skills" and date
- **Changes Made table** with the following rows. The Issues Flagged and Improvements Suggested breakdowns name the tiers of the Issue Severity and Improvement Value tables of `{refinementRulesData}`, in its order, each as `<Tier>: {<tier>_count}` (the tier in lower case, spaces as `_`); the rows below show the bundled tiers:

| Category | Count | Breakdown |
|----------|-------|-----------|
| Gaps Filled | {gap_count} | - |
| Issues Flagged | {issue_count} | Critical: {critical_count}, Major: {major_count}, Minor: {minor_count} |
| Improvements Suggested | {improvement_count} | High: {high_count}, Medium: {medium_count}, Low: {low_count} |
| Skills Used as Evidence | {skill_count} | - |
| Not verified (no skill) | {unverified_count} | {unverified_technologies} |
| VS Coverage | {vs_coverage} | technologies with a skill when [VS] ran, from `{vs_report_name}` |

The Not verified (no skill) row is always written: its Breakdown names the technologies comma-separated, or reads `none`. Write the VS Coverage row only when a VS report was used (`vs_report_available` is true), from the report JSON Step 01 §1 cached (`{vs_report}`), never from the report file: `{vs_coverage}` is its `coveragePercentage` followed by `%` when its `coverageMeasured` is true, and `not recorded` when `coverageMeasured` is false (the helper's JSON decides whether coverage was measured). `{vs_report_name}` is the file name of the JSON's `path` (`{vs_report_path}`) without its folder: the refined document is shared, so it names no local path.

- **Evidence Sources table:** a `| Skill | Refinements |` header row and its separator, then `{evidence_rows}` (the script writes one row per cited skill)
- **Next Steps:** Review `[!WARNING]` issues, `[!NOTE]` gaps, `[!TIP]` improvements; then run **[SS] Stack Skill** to compose your individual skills into a unified stack skill, providing this refined architecture doc when prompted. When `{unverified_technologies}` is not empty, add one line before [SS] that names them: nothing checked what the architecture says about them, so generate their skills with **[CS] Create Skill** or **[QS] Quick Skill** and re-run **[RA]** first.

### 6. Build the Draft

Write the plan to `{planFile}`: the `entries` of §2 to §4, the `summary` of §5, `unverified_technologies` (Step 02 §2b's list as written in the document, `[]` when it is empty), `skill_count` (the inventory's `{skill_count}`, Step 01 §2) and `tiers` (`{"issue": [...], "improvement": [...]}`, the tiers of the Issue Severity and Improvement Value tables, in their order). Then run:

```bash
uv run {preservationScript} apply --original "{architecture_doc}" --plan "{planFile}" --draft "{draftFile}" -o "{applyResult}"
```

It checks the plan, builds the draft and writes it only when every original line survived. Branch on its exit code:

- **0:** the draft is written and the check passed. `{applyResult}` holds its `counts`, `evidence`, filled `summary`, `unverified_technologies` and `set_aside` (the earlier pass's blocks): §7 and Step 06 take every number and name from there.
- **1 with `status: "problems"`:** nothing was written. Each entry of `problems[]` names the plan entry (`id`), the `reason` and what to change: an `anchor-not-found` names the `closest` line, an `anchor-ambiguous` every line in `matches` (quote text only one of them holds, or add `occurrence`). Fix the plan and run the command again. An anchor that is still not found after one fix becomes `null`, so its entry goes to the fallback section.
- **1 with `status: "not-preserved"`:** the draft would lose or change a line of the original, so nothing was written and an earlier draft stays as it was; running the same plan again gives the same result. Show the first entry of `missing[]` (its `line` and `text`) and of `altered[]` (the original line and what replaced it). In headless, HALT (exit code 4, `halt_reason: "preservation-failed"`) at phase `compile:draft` without a retry, naming that first line; in an interactive run, show the failure at §7 and offer no [C] until a feedback round's `apply` passes.
- **2** with a JSON: a file could not be read (`error` names it). When it is `{planFile}`, write the plan again; when it is `{architecture_doc}`, HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `compile:draft`, with `"path"` set to it. **2 with no JSON:** a malformed call: fix it and run it again.
- **3:** the draft could not be written: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `compile:draft`, naming its `error`, with `"path": "{draftFile}"`.
- If `uv` cannot start the script, here or for §8's `promote`: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `compile:draft` (`compile:promote` for `promote`).

`{outputFile}` is not touched here: an earlier refined document stays as it is until §8's [C].

### 7. Present the Draft for Review

"**Refined architecture compiled. Please review:**

---

{Display the `summary` of `{applyResult}`: the Refinement Summary as the draft holds it}

---

{IF the `[RA-DISMISSED]` block holds findings:}**Left out, as a review dropped them from an earlier refinement of this document.** Ask for one back to insert it:
{One line per finding: its kind, its skills, its own title and the title of the record it matched}

**The draft is at:** `{draftFile}`. {IF `{outputFile}` exists: `{outputFile}` still holds your earlier refined document; approving renames it with this run's timestamp before the draft takes its place.}{ELSE: Approving writes it to `{outputFile}`.} Ask for changes here rather than editing the draft: each feedback round rebuilds it.

- Original architecture content preserved in full: the preservation script found every line unchanged
{IF previous_pass:}- The earlier Refine Architecture pass in this document was set aside, and these refinements replace it

**Does the refinement look correct?** Choose [R] to walk through each refinement with its evidence, or tell me what to change, such as a finding to drop."

Say "Original architecture content preserved in full" only when the last `apply` exited 0 and its `set_aside` holds no `legacy` entry. When it holds one, say instead "Every original line is preserved except lines {ranges} of `{architecture_doc}`, which an earlier pass left without RA markers: they were set aside unchecked, so text of your own there is not in the draft", where `{ranges}` lists each `legacy` entry's `start`-`end`. After a build that failed the check, say instead which line the draft would lose and that [C] waits for a draft that passes.

### 8. Present MENU OPTIONS

Display: **Select:** [R] Review each refinement | [C] Approve and replace the refined document | [X] Cancel

#### GATE [default: C]

This is a review gate: halt for the user's decision and do not chain onward until they approve. Headless auto-selects [C] (log: "headless: auto-approve compiled architecture") and records that decision in the run sink the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "compile.review", "default_action": "C", "taken_action": "C", "reason": "headless: auto-approve compiled architecture", "evidence": {"draft": "{draftFile}", "output": "{outputFile}"}}`, then run:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-refine-architecture --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

#### Menu Handling Logic:

- IF R: walk through each refinement with its full evidence citation and its plan `id`, so feedback can name it: the gaps, then the issues by severity tier and the improvements by value tier (in the rules' order), then the findings left out as previously dismissed. It changes nothing; then redisplay this menu.
- IF C (only while the last `apply` exited 0): promote the draft. The script checks it once more (the draft may have changed during the review), renames a file already at `{outputFile}` to `refined-architecture-{arch_project_name}-{timestamp}.md` (`-2`, `-3` ... when that name is taken), and moves the draft there:

  ```bash
  uv run {preservationScript} promote --original "{architecture_doc}" --draft "{draftFile}" --output "{outputFile}" --timestamp "{timestamp}" -o "{promoteResult}"
  ```

  - **0:** the draft is now `{outputFile}`, and `{promoteResult}` records `previous`, the name the earlier refined document took (null when there was none). Only now does what the review dropped reach `{dismissedFile}`: when a feedback round staged `{run_dir}/dismissed.json`, resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}` (first existing path wins) and run:

    ```bash
    uv run {atomicWriteHelper} write --target "{dismissedFile}" < "{run_dir}/dismissed.json"
    ```

    If no candidate exists or the command fails, say "The dropped findings were not recorded ({reason}): a later run may raise them again." and go on. Then load, read the entire file, and execute `{nextStepFile}`.
  - **1** (`not-preserved`): nothing was moved. Show the first entry of `missing[]` or `altered[]`, rebuild once with §6's `apply`, and promote again. If it fails the same way, HALT (exit code 4, `halt_reason: "preservation-failed"`) at phase `compile:promote`, naming that line: the draft stays at `{draftFile}` and `{outputFile}` is as it was.
  - **2** with a JSON (`error` names the file it could not read): for the draft, rebuild it once and promote again, and if it still cannot be read, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `compile:promote`, with `"path": "{draftFile}"`; for `{architecture_doc}`, HALT (exit code 2, `halt_reason: "input-invalid"`) at phase `compile:promote`, with `"path"` set to it. **2 with no JSON:** fix the malformed call and run it again.
  - **3:** HALT (exit code 4, `halt_reason: "write-failed"`) at phase `compile:promote`, naming its `error`, with `"path": "{outputFile}"`. `{outputFile}` is as it was unless the `error` names a file the script could not put back.
- IF cancel / exit / [X] / q / :q: delete the draft (`rm -f "{draftFile}"`), display "Cancelled: refinement not finalized. `{outputFile}` is unchanged." and HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `compile:review`. These global cancel tokens pre-empt the feedback branch below.
- IF Any other: process it as feedback on the plan. Change the anchor, tier or block of the entries it is about, drop an entry the user rejects, or add one, as §2 to §4 would, for a previously dismissed finding the user takes back, in `{planFile}`, and record each drop or take-back as below. Then run §6's `apply` command again: it rebuilds the draft from the original, so feedback never edits the draft. On exit 0, redisplay §7 with the new counts. On a failure the previous draft stays as it was: handle it as §6 says for its exit code, and [C] waits for a round whose `apply` passes. Then [Redisplay Menu Options](#8-present-menu-options)

  **Record what the review dropped.** A dropped entry adds its record, `{"kind", "skills", "anchor", "title", "capability"}` (`title` a line naming the finding, such as its heading; `capability` the `{api}` an improvement's block names, `null` for a gap or an issue), to the list of dropped findings, and a finding taken back removes the record it matched (`references/finding-storage.md` says how a later run leaves a dropped finding out). Keep that list in `{run_dir}/dismissed.json`, which the first round that changes it starts from `{dismissedFile}` (`[]` when that file does not exist). It reaches `{dismissedFile}` only at [C], once `promote` exits 0, so [X] leaves the record as it was.
