---
nextStepFile: 'improvements.md'
refinementRulesData: '{refinementRulesPath}'
findingStorageData: 'references/finding-storage.md'
# §4 joins the [VS] verdicts to the inventory and the scope with it.
preservationScript: 'scripts/skf-check-preservation.py'
# The shared emitter: §4's halts print their envelope with it.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Append issue-detection findings to the RA state file in {document_output_language}. -->

# Step 3: Issue Detection

## STEP GOAL:

Find contradictions between what the architecture document claims and what the generated skills reveal about actual API surfaces. Each issue takes a type and a severity tier the refinement rules define. If a VS feasibility report is available, raise its in-scope verdicts as issues, as the refinement rules map their tokens.

## Rules

- Focus only on contradictions between architecture claims and skill API reality
- Do not detect gaps (Step 02) or suggest expansions (Step 04)
- Every issue must cite both the architecture claim and the contradicting skill evidence

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 2. Extract Integration Claims from Architecture

Parse the architecture document for specific claims about how technologies interact. Read it as `{analysis_doc}`, the copy Step 01 §1b wrote with any earlier Refine Architecture pass set aside, so a claim is always the user's, never an old RA annotation.

**Claim types to extract:**
- **API claims:** "Library X provides/exposes/exports {function/endpoint}"
- **Protocol claims:** "Library X communicates via {protocol}"
- **Data flow claims:** "Data flows from X to Y as {format}"
- **Integration claims:** "X and Y integrate through {mechanism}"
- **Capability claims:** "Library X handles {capability}"

For each claim, record:
- The claim's exact text as one line of `{analysis_doc}` holds it, copied character for character (Step 05 anchors the issue's callout on it), then a paraphrase if one helps
- The section where it appears
- The libraries referenced

### 3. Verify Claims Against Skill API Surfaces

Check each claim against the compact API surfaces Step 02 §4 collected, the per-skill `{skill_api_surfaces}` summaries (`{exports, protocols, data_formats, capabilities}`), and against each skill's `language` in `skill_inventory`. If the summaries are no longer in context, read them from the `<!-- [RA-SURFACES] ... -->` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`), never from the SKILL.md files. Look at what the claim says about an API and its signature, a protocol or data format, a call across languages, and the types passed between libraries. Whether a named export exists is a membership lookup in the skill's `exports[]` in `{run_dir}/skill-inventory.json` (Step 01 §2), never in the surface: a claim fails on existence only when that list lacks the name, and for a name it holds, judge only the signature, protocol or types the claim states. When that list is empty (a stack skill, or `exports_source` `unknown`), the surface's `exports` were extracted from the files read and may be partial: judge existence from them, never taking a missing name as proof. A claim the skill evidence contradicts is an issue: type it by the Issue Classification of `{refinementRulesData}`.

### 4. Incorporate VS Report (If Available)

If `vs_report_available` is false, skip this section: issue detection proceeds with skill data only.

**Join the verdicts to the scope.** The report's verdicts span the whole skill set, which may exceed this architecture's surface. One call reads its verdict rows (`pairVerdicts`) again through the shared feasibility-report reader and joins them to the skill names and aliases in `{run_dir}/skill-terms.json` (Step 02 §2), the scope Step 02 §3 settled and the VS Report Integration table of `{refinementRulesData}`:

```bash
uv run {preservationScript} verdicts --report "{vs_report_path}" --generated-at "{vs_generated_at}" --skills "{run_dir}/skill-terms.json" --in-scope "{in_scope_names}" --rules "{refinementRulesData}"
```

`{vs_report_path}` and `{vs_generated_at}` are the `path` and `generatedAt` of `{vs_report}` (an empty string when `generatedAt` is null), and `{in_scope_names}` every name in `{in_scope_skills}`, comma-separated. If they are no longer in context, read them from the `[RA-VS]` and `[RA-SCOPE]` blocks of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`). Branch on its exit code:

- **0:** each `in_scope` row (both libraries in-scope skills, in report order) whose `raises` names a tier is an issue of that tier; one whose `raises` is null raises none. The token alone decides, never phrases in the rationale text. Record every `out_of_scope` row, with its `reason`, under the informational Out-of-Scope bucket instead of promoting it to an issue for this architecture.
- **1** (`status: "stale"`): the report this run started from is gone ([VS] rewrote it during this run, or it cannot be read again), or the refinement rules no longer pass step 1's check: HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `issue-detection:vs-report`, naming the `detail` of each of its `problems`, with `"path"` set to `{vs_report_path}`.
- **2** with a JSON (`error` names the file it could not read): stage `{run_dir}/skill-terms.json` again as Step 02 §2 does and run the command again. **2 with no JSON:** a malformed call: fix it and run it again.
- **3**, or `uv` cannot start the script: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `issue-detection:vs-report`, naming its `error` (the shared feasibility-report reader is not installed).

**For each VS-sourced issue, include dual citations:**
- Evidence from the skill content
- Verdict and rationale from the VS report

### 5. Document Each Issue

For each detected issue, cite it in this format:

```
**[ISSUE]**: {description}

Architecture states: "{the claim's exact text from §2}" (Section: {section_name})
Skill reality: {skill_name} exports: `{actual_api}` — {explanation of contradiction}
{IF VS report}: VS verdict: {verdict} for {pair}: {VS rationale}

Suggestion: {specific correction with API evidence}
```

**Severity:** give each issue one tier of the Issue Severity table of `{refinementRulesData}`; a VS-sourced issue takes the tier its verdict's row raises.

### 6. Report Issues & Store Findings

Report the in-scope issue count with its count per severity tier, then list each issue as a row of **# / Libraries / Issue Type / Severity / Summary** followed by its full §5 citation. One signal is not inferable from the counts and must survive regardless of format:

- **Out-of-scope VS verdicts were set aside (from §4):** list them separately for awareness only — they were not counted as issues — and note that re-running with `--scope-skills` pulls any that belong into scope.

Store the **in-scope** issue findings under a `<!-- [RA-ISSUES] ... -->` block (their citations carry the architecture claim, skill evidence, VS verdict, severity and suggestion) and any out-of-scope VS verdicts under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker, as `{findingStorageData}` says (an issue that matches one a review dropped goes under `[RA-DISMISSED]` instead).

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

