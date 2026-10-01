---
nextStepFile: 'improvements.md'
refinementRulesData: '{refinementRulesPath}'
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

Find contradictions between what the architecture document claims and what the generated skills reveal about actual API surfaces. Detect language boundary issues not addressed, protocol mismatches assumed away, and missing bridge layers. If a VS feasibility report is available, incorporate its `Risky` and `Blocked` verdicts as confirmed issues and its `Plausible` verdicts as potential ones.

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

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: issue classification (API Mismatch, Protocol Contradiction, Language Boundary Ignored, Type Incompatibility) and VS report integration rules.

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

For each extracted claim, verify against the compact API surfaces already collected in Step 02 §4 — the per-skill `{skill_api_surfaces}` summaries (`{exports, protocols, data_formats}`), carried forward as workflow state exactly like `{in_scope_skills}`. Reload a skill's SKILL.md directly only if its summary is unavailable or context has compacted (see Step 02 §4 for the canonical delegate-the-read pattern). Then check:

**API Mismatch check:**
- Does the claimed API actually exist in the skill's export list?
- Does the function signature match what the architecture describes?
- If the architecture describes an API that does not appear in the skill: flag as issue

**Protocol Contradiction check:**
- Does the skill document the protocol the architecture assumes?
- If the architecture claims gRPC but the skill shows HTTP-only: flag as issue

**Language Boundary check:**
- If two libraries are in different languages, does the architecture describe a bridge mechanism?
- If the architecture assumes direct calls across language boundaries without FFI/IPC: flag as issue

**Type Incompatibility check:**
- Does the architecture assume type compatibility that the skills contradict?
- If Library A exports Type X but the architecture claims Library B consumes it, and Library B expects Type Y: flag as issue

### 4. Incorporate VS Report (If Available)

If `vs_report_available` is true:

**Read the verdicts from `{vs_report}`**, the report JSON Step 01 §1 cached from the feasibility-report helper; never read the report file by hand. Its `pairVerdicts` lists each pair of the report's canonical verdict table as `{lib_a, lib_b, verdict, rationale}`, and `overallVerdict` gives the report's overall verdict for context. Step 01 halted on a report whose `unknownTokens` was not empty, so every `verdict` is a token the schema defines: compare it exactly as written (tokens are case-sensitive) and never map another spelling.

**Recover the report JSON.** If `{vs_report}` is no longer in context, read the `[RA-VS]` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`), resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}`, and run Step 01's path mode with `{vs_report_path}` set to the `path` the block records:

```bash
uv run {validateFeasibilityReportHelper} "{vs_report_path}"
```

Use its JSON when it exits 0 with the `generatedAt` the block records. When it exits non-zero with a JSON, or its `generatedAt` differs ([VS] rewrote the report during this run), the verdicts this run started from are gone: HALT (exit code 8, `halt_reason: "recovery-failed"`) at phase `issue-detection:vs-report`, naming the VS report, with `"path"` set to its `path`. An exit 2 with no JSON is a malformed call, as in Step 01: fix it and run it again.

**Scope filter (reuse `{in_scope_pairs}` and `{out_of_scope_pairs}` from Step 02 §3, or the `[RA-SCOPE]` block of the same state file if they are no longer in context):** The VS report carries verdicts across the entire skill set, which may exceed this architecture's surface. Map each pair's `lib_a` and `lib_b` to the inventory skill whose name, or one of the aliases Step 02 §2 passed to the mentions helper, equals it (compared case-insensitively). A verdict whose pair is in `{in_scope_pairs}`, in either order, is promoted by the rules below. Record every other verdict (a pair in `{out_of_scope_pairs}`, or one naming a library no inventory skill matches) under the informational Out-of-Scope bucket instead of promoting it to an issue for this architecture.

**Promote the in-scope verdicts by their token:**
- **`Risky`:** Promote to confirmed issues with the VS evidence as additional citation
- **`Blocked`:** Promote to critical issues requiring architecture redesign
- **`Plausible`:** Flag as a potential issue. The token means every compatibility check passed but neither skill cites the other literally, so the integration rests on weaker evidence; the token decides this, never phrases in the rationale text
- **`Verified`:** Not an issue

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
{IF VS report}: VS verdict: {Risky|Blocked|Plausible} for {pair}: {VS rationale}

Suggestion: {specific correction with API evidence}
```

**Severity classification:**
- **Critical:** Blocked VS verdicts, fundamental language barriers with no bridge
- **Major:** Risky VS verdicts, protocol mismatches, missing bridge layers
- **Minor:** `Plausible` VS verdicts, minor type differences with easy conversion

### 6. Report Issues & Store Findings

Report the in-scope issue count with its critical/major/minor breakdown, then list each issue as a row of **# / Libraries / Issue Type / Severity / Summary** followed by its full §5 citation. One signal is not inferable from the counts and must survive regardless of format:

- **Out-of-scope VS verdicts were set aside (from §4):** list them separately for awareness only — they were not counted as issues — and note that re-running with `--scope-skills` pulls any that belong into scope.

Store the **in-scope** issue findings per the Finding Storage rule (refinement rules), under a `<!-- [RA-ISSUES] ... -->` block (its citations carry the architecture claim, skill evidence, VS verdict, severity, and suggestion). Record any out-of-scope VS verdicts under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker so Step 05 leaves them out — informational only.

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

