---
nextStepFile: 'synthesize.md'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
reportUpdateScript: 'scripts/skf-report-update.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
# The skill summaries integrations.md §3 merged: `summaries`, one per skill
# matched to a Covered technology that it could read, with its exports and
# capabilities, and `unread`, the skills it could not read.
skillSummariesFile: '{run_dir}/skill-summaries.json'
---

<!-- Config: communicate in {communication_language}. Append the Requirements Coverage section to the report in {document_output_language}. -->

# Step 4: Requirements Coverage

## STEP GOAL:

If a PRD or vision document was provided in Step 01, verify that the combined capabilities of the generated skills address each stated requirement. If no PRD was provided, skip this pass and auto-proceed. Produce a requirements coverage table with Fulfilled, Partially Fulfilled, or Not Addressed verdicts.

## Rules

- Focus only on requirements-to-skills coverage assessment
- Do not re-analyze integrations (Step 03) or synthesize verdicts (Step 05)
- If no PRD was provided, skip immediately with a clear message

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Check PRD Availability

**Read `prdAvailable` from `{outputFile}` frontmatter (set in Step 01). If `prdAvailable` is false (no PRD/vision document was provided, or the one given was not found):**

"**Pass 3: Requirements Coverage — Skipped**

{IF `prdDoc` in the `{outputFile}` frontmatter names a path, not `none`:}The PRD at `{prdDoc}` was not found.{ELSE:}No PRD or vision document was provided.{END IF} Requirements coverage analysis requires a document describing project capabilities and constraints.

To include this pass, re-run **[VS]** with a PRD or vision document path.

**Proceeding to synthesis...**"

Record the skipped pass in `{outputFile}`:

```bash
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind requirements-skipped
```

On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `requirements:report`. On exit 2 with `INVALID_INPUT`, or with no JSON (a usage error), fix the file or the call its `error` or usage line names, then run that call and the ones after it again. On exit 2 with `INVALID_REPORT`, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `requirements:report`, naming its `error`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `requirements:report`, with `"path": "{outputFile}"`, naming its JSON `error`.

Load, read the full file and then execute `{nextStepFile}`. The no-PRD path ends here — sections 2-6 are the PRD-present branch and do not run.

**If PRD/vision document was provided:** Continue to section 2.

### 2. Extract Requirements

Take the PRD's path from `prdDoc` in the `{outputFile}` frontmatter, then parse that document for capability requirements.

**Build a requirements list** with each entry containing:
- `requirement_id` — sequential identifier (R1, R2, R3...)
- `requirement_text` — the stated requirement
- `category` — feature, technical, non-functional, integration, or infrastructure
- `source_section` — the PRD section where it was found

### 3. Assess Stack Coverage

For each requirement, evaluate whether the combined capabilities of the generated skills address it. Work from the `summaries` step 3 wrote to `{skillSummariesFile}`, one per skill matched to a Covered technology that it could read (its `exports`, `capabilities`, `protocols_inferred` and `data_formats_inferred`), never from a SKILL.md read in this context: step 3 already read each one. A skill its `unread` list names counts toward no verdict.

When a verdict turns on a detail no summary holds, delegate it: one subagent reads that skill's SKILL.md and returns only `{"requirement_id": "…", "verdict": "Fulfilled|Partially Fulfilled|Not Addressed", "evidence": "…"}`.

**Assign verdict per requirement:**
- **Fulfilled** — one or more skills clearly provide the needed capability, with specific exports or patterns identified
- **Partially Fulfilled** — skills provide related capability but gaps remain (specify what is covered and what is not)
- **Not Addressed** — no skill in the stack provides capability relevant to this requirement

**Count the verdicts deterministically.** Write `{run_dir}/requirement-rows.json` as `{"rows": [{"requirement_id": "R1", "verdict": "Fulfilled|Partially Fulfilled|Not Addressed"}, …]}`, one row per requirement, and run:

```bash
uv run {coverageTallyScript} --kind requirements --stdin < "{run_dir}/requirement-rows.json" > "{run_dir}/requirement-tally.json"
```

`{run_dir}/requirement-tally.json` holds `requirements_fulfilled`, `requirements_partial`, `requirements_not_addressed` and `requirement_count` (run `uv run {coverageTallyScript} --help` for the contract). When it exits non-zero, it rejected its input and the file says why (its JSON `error`): fix the rows and run it again.

### 4. Display Requirements Results

"**Pass 3: Requirements Coverage**

| ID | Requirement | Category | Verdict | Contributing Skills |
|----|-------------|----------|---------|-------------------|
| {id} | {requirement_text} | {category} | {Fulfilled/Partially Fulfilled/Not Addressed} | {skill_names or '—'} |

**Coverage: {requirements_fulfilled} Fulfilled, {requirements_partial} Partially Fulfilled, {requirements_not_addressed} Not Addressed** (from `{run_dir}/requirement-tally.json`)

{IF the `unread` list of `{skillSummariesFile}` names a skill, one line for each:}
**Not read:** `{skill}`: its API surface could not be read, so no requirement was checked against it: re-run **[VS]**.

{IF any Not Addressed:}
**Unaddressed Requirements — Recommendations:**
{For each not addressed requirement:}
- **{id}:** {requirement_text} → Evaluate `{category}` libraries that provide this capability, generate a skill with **[CS]** or **[QS]**, then re-run **[VS]**

{IF any Partially Fulfilled:}
**Partial Coverage — Details:**
{For each partially fulfilled requirement:}
- **{id}:** Covered by `{skill_names}` — **Gap:** {what remains unaddressed}"

### 5. Append to Report

Write `{run_dir}/requirements-section.md`, the Requirements Coverage content that goes under `## Recommendations` (the shared schema's fixed top-level headings are Executive Summary, Coverage Analysis, Integration Verdicts, Recommendations, Evidence Sources; requirements detail lives under Recommendations):
- Include the full requirements coverage table, with its **Not read:** lines
- Include the gap §4 shows for each Partially Fulfilled requirement, and no recommendation: synthesize writes one for each Not Addressed and Partially Fulfilled requirement, in its prioritized list

The helper writes the `### Requirements Coverage` line, so the file holds no `#`, `##` or `###` heading. Then run the calls in order, stopping at the first that exits non-zero:

```bash
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Recommendations' --subsection 'Requirements Coverage' < "{run_dir}/requirements-section.md"
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind requirements < "{run_dir}/requirement-tally.json"
```

On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `requirements:report`. On exit 2 with `INVALID_INPUT`, or with no JSON (a usage error), fix the file or the call its `error` or usage line names, then run that call and the ones after it again. On exit 2 with `INVALID_REPORT`, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `requirements:report`, naming its `error`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `requirements:report`, with `"path": "{outputFile}"`, naming its JSON `error`.

### 6. Auto-Proceed to Next Step

"**Proceeding to synthesis...**"

Load, read the full file and then execute `{nextStepFile}`.

