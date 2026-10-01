---
nextStepFile: 'improvements.md'
refinementRulesData: '{refinementRulesPath}'
findingStorageData: 'references/finding-storage.md'
# Resolve `{validateFeasibilityReportHelper}` by probing
# `{validateFeasibilityReportProbeOrder}` in order (installed SKF module
# path first, src/ dev-checkout fallback); first existing path wins. §4
# calls it only to read the [VS] report again when the JSON Step 01 cached
# is no longer in context.
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
# The shared emitter: §4's recovery halt prints its envelope with it.
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

Check each claim against the compact API surfaces Step 02 §4 collected, the per-skill `{skill_api_surfaces}` summaries (`{exports, protocols, data_formats, capabilities}`), and against each skill's `language` in `skill_inventory`. If the summaries are no longer in context, read them from the `<!-- [RA-SURFACES] ... -->` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`), never from the SKILL.md files. Look at what the claim says about an API and its signature, a protocol or data format, a call across languages, and the types passed between libraries. A claim the skill evidence contradicts is an issue: type it by the Issue Classification of `{refinementRulesData}`.

### 4. Incorporate VS Report (If Available)

If `vs_report_available` is true:

**Read the verdicts from `{vs_report}`**, the report JSON Step 01 §1 cached from the feasibility-report helper; never read the report file by hand. Its `pairVerdicts` lists each pair of the report's canonical verdict table as `{lib_a, lib_b, verdict, rationale}`, and `overallVerdict` gives the report's overall verdict for context. Step 01 halted on a report whose `unknownTokens` was not empty, so every `verdict` is a token the schema defines: compare it exactly as written (tokens are case-sensitive) and never map another spelling.

**Recover the report JSON.** If `{vs_report}` is no longer in context, read the `[RA-VS]` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`), resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`, and run Step 01's path mode with `{vs_report_path}` set to the `path` the block records:

```bash
uv run {validateFeasibilityReportHelper} "{vs_report_path}"
```

Use its JSON when it exits 0 with the `generatedAt` the block records. When it exits non-zero with a JSON, or its `generatedAt` differs ([VS] rewrote the report during this run), the verdicts this run started from are gone: HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `issue-detection:vs-report`, naming the VS report, with `"path"` set to its `path`. An exit 2 with no JSON is a malformed call, as in Step 01: fix it and run it again.

**Scope filter (reuse `{in_scope_pairs}` and `{out_of_scope_pairs}` from Step 02 §3, or the `[RA-SCOPE]` block of the same state file if they are no longer in context):** The VS report carries verdicts across the entire skill set, which may exceed this architecture's surface. Map each pair's `lib_a` and `lib_b` to the inventory skill whose name, or one of the aliases Step 02 §2 passed to the mentions helper, equals it (compared case-insensitively). A verdict whose pair is in `{in_scope_pairs}`, in either order, is promoted by the rules below. Record every other verdict (a pair in `{out_of_scope_pairs}`, or one naming a library no inventory skill matches) under the informational Out-of-Scope bucket instead of promoting it to an issue for this architecture.

**Promote the in-scope verdicts by their token:** each raises the issue the VS Report Integration table of `{refinementRulesData}` maps its token to, or none. The token alone decides, never phrases in the rationale text.

**For each VS-sourced issue, include dual citations:**
- Evidence from the skill content
- Verdict and rationale from the VS report

If `vs_report_available` is false: Skip this section. Issue detection proceeds with skill data only.

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

