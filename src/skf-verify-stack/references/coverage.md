---
nextStepFile: 'integrations.md'
coveragePatternsData: '{coveragePatternsPath}'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
---

<!-- Config: communicate in {communication_language}. Append the Coverage Analysis section to the report in {document_output_language}. -->

# Step 2: Technology Coverage Analysis

## STEP GOAL:

Verify that a generated skill exists for every technology, library, or framework referenced in the architecture document. Produce a coverage matrix showing which technologies are covered and which are missing. Detect extra skills not referenced in the architecture.

## Rules

- Focus only on technology-to-skill coverage mapping — do not analyze API surfaces (Step 03) or requirements (Step 04)
- Coverage verdicts must be binary: Covered or Missing

## MANDATORY SEQUENCE

### 1. Load Coverage Patterns

Load `{coveragePatternsData}` for detection rules.

Extract: technology name patterns, section heading indicators, common aliases, and framework-to-library mappings.

### 2. Extract Technology References

Parse the architecture document for technology, library, and framework names.

**Detection methods (apply in order):**

**Section-based detection:**
- Identify section headings that indicate technology listings (e.g., "Tech Stack", "Dependencies", "Technologies", "Libraries", layer-specific headings)
- Extract technology names listed under these headings

**Direct name matching:**
- Scan the full document for names that match loaded skill names (case-insensitive)
- Apply alias resolution from {coveragePatternsData} (e.g., "React" matches "react", "PostgreSQL" matches "postgres")

**Contextual detection:**
- Identify technology names mentioned in prose alongside architectural descriptions
- Look for version-pinned references (e.g., "Express v4", "Tailwind CSS 3.x")

**Build a deduplicated list** of all referenced technologies with the document section where each was found.

### 3. Cross-Reference Against Skills

For each referenced technology in the list:

**Check if a matching skill exists** in the skill inventory from Step 01.
- Match by skill name (case-insensitive)
- Match by alias from {coveragePatternsData}
- Match by `source_repo` or `source_root` field in metadata.json if skill name differs from technology name, using this algorithm:
  1. For `source_repo`: extract the basename (last URL segment after the final `/`), strip any trailing `.git` suffix, lowercase
  2. For `source_root`: take the last path segment (after the final `/` or `\`), lowercase
  3. Lowercase each architecture tech token
  4. Compare the resulting basenames/segments against the tech tokens via case-insensitive equality (no substring/fuzzy matching)
  5. A match on either `source_repo` basename or `source_root` last segment counts as a hit

**Detect a deliberate-removal signal (from the architecture document):** Before assigning Covered/Missing, check whether the referenced technology is explicitly marked for removal or replacement in the architecture document itself. Be conservative — recognize a removal signal ONLY when one of these is present, and when in doubt do NOT treat it as removal:
- The technology is listed under a section whose heading matches (case-insensitive) one of: "deprecated", "removed", "legacy", "migrating away", "being replaced", "to be removed", "sunset", "retiring".
- The technology's own mention carries an inline removal annotation, e.g. "(deprecated)", "(being replaced by …)", "(removing)", "(to be removed)", "(legacy)".

Record the cited section heading or annotation text as evidence for every technology flagged this way.

**Assign verdict:**
- **Covered** — a matching skill exists in the inventory
- **Replaced** — no matching skill exists AND a deliberate-removal signal (above) was found; the technology is intentionally being removed/replaced, so no skill should exist for it
- **Missing** — no matching skill found and no removal signal

**Replaced** technologies are EXCLUDED from the coverage denominator — they are not a gap to close. The denominator (`live_count`) is the count of referenced technologies that are **Covered** or **Missing**; **Replaced** technologies do not count toward it.

Build the coverage matrix as a structured table.

### 4. Detect Extra Skills

Check if any skills in the inventory are NOT referenced in the architecture document.

**Subdivide into two categories (both informational — not errors):**
- **Extra (unreferenced)** — The skill's `source_repo` / `source_root` resolves cleanly (both non-empty and well-formed), but no architecture document tech token matches it.
- **Orphan (source_repo unresolvable)** — The skill's `source_repo` is empty, malformed (not a valid URL-like string), OR its basename cannot be deterministically extracted. Cross-reference against architecture tokens is not possible for this skill.

**For each extra skill:**
- If `source_repo` resolves → mark as **Extra (unreferenced)**, note: "Skill `{skill_name}` exists and has a resolvable `source_repo`, but no architecture reference was found."
- If `source_repo` does not resolve → mark as **Orphan (source_repo unresolvable)**, note: "Skill `{skill_name}` has no resolvable `source_repo` — cannot cross-reference against architecture. Re-run [CS] or update the skill's metadata."

Extra and Orphan skills are informational only. They do not affect the coverage verdict.

### 5. Display Coverage Results

"**Pass 1: Technology Coverage**

| Technology | Source Section | Skill Match | Verdict |
|------------|---------------|-------------|---------|
| {tech_name} | {section_heading} | {skill_name or '—'} | {Covered / Missing / Replaced} |

**Coverage: {covered_count}/{live_count} ({percentage}%)** — `live_count` excludes technologies marked **Replaced** (being removed/replaced); they are not a coverage gap.

{IF 100% coverage AND no Extra skills:}
**All referenced technologies have a matching skill. No extra skills detected.**

{IF any Missing:}
**Missing Skills — Action Required:**
{For each missing technology:}
- `{tech_name}` → Run **[CS] Create Skill** or **[QS] Quick Skill** for `{tech_name}`, then re-run **[VS]**

{IF any Replaced:}
**Replaced / Being Removed (informational — no skill needed):**
{For each replaced technology:}
- `{tech_name}` — marked for removal/replacement in the architecture document ({cited_removal_evidence}); excluded from coverage. No skill should be created; if the technology is not actually being removed, correct the architecture document and re-run **[VS]**.

{IF any Extra:}
**Extra Skills (informational):**
{For each extra skill:}
- `{skill_name}` — not referenced in architecture document"

### 6. Append to Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. HALT if no candidate exists.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Coverage Analysis** section to `{outputFile}` (see `{feasibilitySchemaRef}` — section headings are fixed and ordered: `## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`):
- Include the full coverage table
- Include coverage percentage
- Include missing skill recommendations
- Include the Replaced (being removed/replaced) subdivision from section 3, with the cited removal evidence — these are NOT gaps and carry no [CS]/[QS] recommendation
- Include the Extra (unreferenced) and Orphan (source_repo unresolvable) subdivisions from section 4
- Update frontmatter: append `'coverage'` to `stepsCompleted`; set `coveragePercentage` (integer 0..100) computed as `covered_count / live_count` (Replaced technologies excluded from the denominator; if `live_count` is 0, set `coveragePercentage: 0`)
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 7. Auto-Proceed to Next Step

{IF live_count is 0 — every referenced technology is marked Replaced:}
"**⚠️ Every referenced technology is marked for removal/replacement — there is no live technology to verify.** Coverage is reported as 0%; the architecture document describes only technologies being removed, so the stack cannot be assessed as described.

**Recommended:** Update the architecture document to describe the technologies that remain after the pivot, then re-run [VS].

**Select:** [X] Halt workflow (recommended) | [C] Continue anyway"

- IF X: "**Workflow halted.** Update the architecture document and re-run [VS] when ready." — END workflow
- IF C: "**Continuing — the analysis covers only technologies marked for removal and will be limited.**" Load, read the full file and then execute `{nextStepFile}`.

{IF coveragePercentage is 0% AND live_count > 0:}
"**⚠️ 0% coverage — no matching skills found for any referenced technology.** All subsequent analysis (integration, requirements) will be vacuous and produce empty tables.

**Recommended:** Generate skills with [CS] or [QS] for your architecture technologies, then re-run [VS].

**Select:** [X] Halt workflow (recommended) | [C] Continue anyway"

- IF X: "**Workflow halted.** Generate skills and re-run [VS] when ready." — END workflow
- IF C: "**Continuing with 0% coverage — results will be limited.**"

  Load, read the full file and then execute `{nextStepFile}`.

{IF coveragePercentage is not 0:}
"**Proceeding to integration analysis...**"

Load, read the full file and then execute `{nextStepFile}`.

