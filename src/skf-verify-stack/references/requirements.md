---
nextStepFile: 'synthesize.md'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
# The skill summaries integrations.md §3 wrote: one per skill matched to a
# Covered technology, with its exports and capabilities.
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

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `requirements:report`.

**Read `prdAvailable` from `{outputFile}` frontmatter (set in Step 01). If `prdAvailable` is false (no PRD/vision document was provided):**

"**Pass 3: Requirements Coverage — Skipped**

No PRD or vision document was provided. Requirements coverage analysis requires a document describing project capabilities and constraints.

To include this pass, re-run **[VS]** with a PRD or vision document path.

**Proceeding to synthesis...**"

Update `{outputFile}` frontmatter: append `'requirements'` to `stepsCompleted`; set `requirementsPass: "skipped"`. Pipe the updated content through `python3 {atomicWriteHelper} write --target {outputFile}`. On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `requirements:report`, with `"path": "{outputFile}"`.

Load, read the full file and then execute `{nextStepFile}`. The no-PRD path ends here — sections 2-6 are the PRD-present branch and do not run.

**If PRD/vision document was provided:** Continue to section 2.

### 2. Extract Requirements

Parse the PRD/vision document for capability requirements.

**Look for:**
- **Feature descriptions** — explicit capabilities the product must have
- **Technical requirements** — performance targets, scalability needs, platform support
- **Non-functional requirements** — offline-first, real-time sync, multi-language support, accessibility, security constraints
- **Integration requirements** — third-party service dependencies, API contracts
- **Infrastructure requirements** — deployment targets, CI/CD needs, monitoring

**Build a requirements list** with each entry containing:
- `requirement_id` — sequential identifier (R1, R2, R3...)
- `requirement_text` — the stated requirement
- `category` — feature, technical, non-functional, integration, or infrastructure
- `source_section` — the PRD section where it was found

### 3. Assess Stack Coverage

For each requirement, evaluate whether the combined capabilities of the generated skills address it. Work from the summaries step 3 wrote to `{skillSummariesFile}`, one per skill matched to a Covered technology (its `exports`, `capabilities`, `protocols_inferred` and `data_formats_inferred`), never from a SKILL.md read in this context: step 3 already read each one in a subagent.

**Assessment method:**
- Match each requirement against the skills' `capabilities` and `exports`
- Check if skill exports provide functions, types, or patterns relevant to the requirement
- Consider combinations of multiple skills that together address a requirement
- For non-functional requirements, check if the summaries name relevant configuration or patterns
- When a verdict turns on a detail no summary holds, delegate it: one subagent reads that skill's SKILL.md and returns only `{"requirement_id": "…", "verdict": "Fulfilled|Partially Fulfilled|Not Addressed", "evidence": "…"}`

**Assign verdict per requirement:**
- **Fulfilled** — one or more skills clearly provide the needed capability, with specific exports or patterns identified
- **Partially Fulfilled** — skills provide related capability but gaps remain (specify what is covered and what is not)
- **Not Addressed** — no skill in the stack provides capability relevant to this requirement

**Each verdict includes:**
- Which skills contribute (if any)
- Specific exports or capabilities from those skills that are relevant
- For Partially Fulfilled: what gap remains

**Count the verdicts deterministically.** Assigning each verdict is judgment; counting them has one correct answer, so delegate it. Write `{run_dir}/requirement-rows.json` as `{"rows": [{"requirement_id": "R1", "verdict": "Fulfilled|Partially Fulfilled|Not Addressed"}, …]}`, one row per requirement, and run:

```bash
uv run {coverageTallyScript} --kind requirements --stdin < "{run_dir}/requirement-rows.json"
```

It returns `requirements_fulfilled`, `requirements_partial`, `requirements_not_addressed` and `requirement_count` (run `uv run {coverageTallyScript} --help` for the contract). When it exits non-zero, it rejected its input and says why (its JSON `error`): fix the rows and run it again. Section 4 displays these counts and section 5 persists them.

### 4. Display Requirements Results

"**Pass 3: Requirements Coverage**

| ID | Requirement | Category | Verdict | Contributing Skills |
|----|-------------|----------|---------|-------------------|
| {id} | {requirement_text} | {category} | {Fulfilled/Partially Fulfilled/Not Addressed} | {skill_names or '—'} |

**Coverage: {requirements_fulfilled} Fulfilled, {requirements_partial} Partially Fulfilled, {requirements_not_addressed} Not Addressed**

{IF any Not Addressed:}
**Unaddressed Requirements — Recommendations:**
{For each not addressed requirement:}
- **{id}:** {requirement_text} → Evaluate `{category}` libraries that provide this capability, generate a skill with **[CS]** or **[QS]**, then re-run **[VS]**

{IF any Partially Fulfilled:}
**Partial Coverage — Details:**
{For each partially fulfilled requirement:}
- **{id}:** Covered by `{skill_names}` — **Gap:** {what remains unaddressed}"

### 5. Append to Report

Write the Requirements Coverage content under the `## Recommendations` section (or as a clearly-titled subsection preceding Recommendations — the shared schema's fixed top-level headings are Executive Summary, Coverage Analysis, Integration Verdicts, Recommendations, Evidence Sources; requirements detail lives under Recommendations):
- Include the full requirements coverage table
- Include recommendations for Not Addressed and Partially Fulfilled items
- Update frontmatter: append `'requirements'` to `stepsCompleted`
- Set `requirementsPass: "completed"`
- From the §3 tally, set `requirementsFulfilled` ← `requirements_fulfilled`, `requirementsPartial` ← `requirements_partial` and `requirementsNotAddressed` ← `requirements_not_addressed`
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}`. On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `requirements:report`, with `"path": "{outputFile}"`.

### 6. Auto-Proceed to Next Step

"**Proceeding to synthesis...**"

Load, read the full file and then execute `{nextStepFile}`.

