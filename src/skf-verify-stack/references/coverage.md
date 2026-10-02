---
nextStepFile: 'integrations.md'
coveragePatternsData: 'references/coverage-patterns.md'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
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
inventoryFile: '{run_dir}/skill-inventory.json'
docMentionsFile: '{run_dir}/doc-mentions.json'
---

<!-- Config: communicate in {communication_language}. Append the Coverage Analysis section to the report in {document_output_language}. -->

# Step 2: Technology Coverage Analysis

## STEP GOAL:

Verify that a generated skill exists for every technology, library, or framework referenced in the architecture document. Produce a coverage matrix showing which technologies are covered and which are missing. Detect extra skills not referenced in the architecture.

## Rules

- Focus only on technology-to-skill coverage mapping — do not analyze API surfaces (Step 03) or requirements (Step 04)
- Coverage verdicts must be binary: Covered or Missing

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Coverage Patterns

Load `{coveragePatternsData}`: which technologies the mentions helper finds and which the model finds, the aliases a skill goes by, and what fenced code hides from both.

### 2. Extract Technology References

**Run the mentions helper once.** Resolve `{comentionHelper}` from `{comentionProbeOrder}`; first existing path wins. Take the architecture document's path from `architectureDoc` in the `{outputFile}` frontmatter, then run:

```bash
uv run {comentionHelper} mentions --doc "<architectureDoc>" --skills - > "{docMentionsFile}"
```

piping on stdin a JSON array with one object per `skills[]` entry of `{inventoryFile}`: `{"name": "<name>", "aliases": [...]}`, where `aliases` holds the entry's `source_repo_basename` and `source_root_basename` that are not null, and each other name a persistent fact gives the skill. If no candidate exists, or the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `coverage:mentions`, naming its first stderr line. The integrations stage reads its `candidates[]` from `{docMentionsFile}` too.

**Skills the document names:** each skill in the helper's `mentioned` list is a referenced technology, labelled with the skill's `name`, whose source section is the `header` of its first `skills[].paragraphs[]` entry (none when that `header` is null or the document names the skill only in a heading).

**Other technologies:** find the document's other technology, library and framework names, skipping each term that names a `mentioned` skill:

**Section-based detection:**
- Identify section headings that indicate technology listings (e.g., "Tech Stack", "Dependencies", "Technologies", "Libraries", layer-specific headings)
- Extract technology names listed under these headings

**Contextual detection:**
- Identify technology names mentioned in prose alongside architectural descriptions
- Look for version-pinned references (e.g., "Express v4", "Tailwind CSS 3.x")

**Build a deduplicated list** of all referenced technologies with the document section where each was found.

### 3. Cross-Reference Against Skills

For each referenced technology in the list:

**Check if a matching skill exists** in the skill inventory step 1 wrote to `{inventoryFile}`.
- A `mentioned` skill matches its own row: the helper already matched its name and aliases.
- A technology §2's own detection found matches a skill by the skill's name (case-insensitive), or by a common alias from {coveragePatternsData} (e.g., "PostgreSQL" for `postgres`), so a document that writes only "PostgreSQL" still covers a `postgres` skill.

**Run the mentions helper again when the model matched a skill.** When a technology §2's own detection found matches a skill that is not in `mentioned`, add the technology's term, as the document writes it, to that skill's `aliases`. Once every technology is checked, run the §2 `mentions` command once more with the extended array, overwriting `{docMentionsFile}` (the same HALT applies), and take §2's skill rows from the new file: each such skill is in `mentioned` now, and its row, labelled with its `name`, replaces the technology's. The integrations stage then finds that skill's pairs in `candidates[]`. With no such match, skip the second run.

**Detect a deliberate-removal signal (from the architecture document):** Before assigning Covered/Missing, check whether the referenced technology is explicitly marked for removal or replacement in the architecture document itself. Be conservative — recognize a removal signal only when one of these is present, and when in doubt leave it as a normal reference (a false removal signal silently drops a real coverage gap):
- The technology is listed under a section whose heading matches (case-insensitive) one of: "deprecated", "removed", "legacy", "migrating away", "being replaced", "to be removed", "sunset", "retiring".
- The technology's own mention carries an inline removal annotation, e.g. "(deprecated)", "(being replaced by …)", "(removing)", "(to be removed)", "(legacy)".

Record the cited section heading or annotation text as evidence for every technology flagged this way.

**Assign verdict:**
- **Covered** — a matching skill exists in the inventory
- **Replaced** — no matching skill exists AND a deliberate-removal signal (above) was found; the technology is intentionally being removed/replaced, so no skill should exist for it
- **Missing** — no matching skill found and no removal signal

Build the coverage matrix as a structured table.

**Tally the matrix deterministically.** Assigning each verdict is judgment; counting the classes and computing the percentage has one correct answer, so delegate it. Serialize the matrix as `{"rows": [{"technology": "…", "verdict": "Covered|Missing|Replaced"}, …]}` and run:

```bash
echo '<rows JSON>' | uv run {coverageTallyScript} --stdin
```

The script (run `uv run {coverageTallyScript} --help` for the contract) returns `covered_count`, `missing_count`, `replaced_count`, `live_count` (the denominator: Covered + Missing, with Replaced excluded because a technology being removed is not a gap to close), `total_referenced`, and `coverage_percentage` (Replaced excluded from the denominator, half-up rounding pinned so the same matrix always yields the same integer). Consume these values in §5, §6 and §7 rather than recomputing them.

### 4. Detect Extra Skills

Check if any skills in the inventory are not referenced in the architecture document: a skill in the `unmentioned` or `fenced_only` list of `{docMentionsFile}`, as §3 left it.

**Subdivide into two categories (both informational, not errors), by the skill's `source_repo_basename` in `{inventoryFile}`:**
- **Extra (unreferenced):** `source_repo_basename` is set, but no architecture document tech token matches the skill.
- **Orphan (source_repo unresolvable):** `source_repo_basename` is null: metadata.json records no `source_repo`, or none a repository name can be read from. Cross-reference against architecture tokens is not possible for this skill.

**For each extra skill:**
- If `source_repo_basename` is set → mark as **Extra (unreferenced)**, note: "Skill `{skill_name}` exists and has a resolvable `source_repo`, but no architecture reference was found."
- If `source_repo_basename` is null → mark as **Orphan (source_repo unresolvable)**, note: "Skill `{skill_name}` has no resolvable `source_repo`, so it cannot be cross-referenced against the architecture. Re-run [CS] or update the skill's metadata."

Extra and Orphan skills are informational only. They do not affect the coverage verdict.

### 5. Display Coverage Results

"**Pass 1: Technology Coverage**

| Technology | Source Section | Skill Match | Verdict |
|------------|---------------|-------------|---------|
| {tech_name} | {section_heading} | {skill_name or '—'} | {Covered / Missing / Replaced} |

**Coverage: {covered_count}/{live_count} ({coverage_percentage}%)** (from the §3 tally; `live_count` excludes **Replaced** technologies)

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
- `{skill_name}`: not referenced in architecture document

{IF a skill of the helper's `fenced_only` list is Extra:}
**Detection limitation:** {those skills} appear only inside fenced code, which coverage does not read, so they count as Extra. {IF a `fenced_blocks[]` entry of `{docMentionsFile}` has the `info` string `mermaid`:}Part of the stack is drawn in a Mermaid diagram: list its technologies in prose (a Tech Stack section, say), then re-run **[VS]**.{ELSE:}Name them in prose, then re-run **[VS]**."

### 6. Append to Report

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `coverage:report`.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Coverage Analysis** section to `{outputFile}` (see `{feasibilitySchemaRef}` — section headings are fixed and ordered: `## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`):
- Include the full coverage table, with the §5 header `| Technology | Source Section | Skill Match | Verdict |` and one token alone in each Verdict cell (`Covered`, `Missing` or `Replaced`): the next run's delta reads the Technology and Verdict columns
- Include coverage percentage
- Include missing skill recommendations
- Include the Replaced (being removed/replaced) subdivision from section 3, with the cited removal evidence — these are not gaps and carry no [CS]/[QS] recommendation
- Include the Extra (unreferenced) and Orphan (source_repo unresolvable) subdivisions from section 4, and the §5 detection limitation when it shows
- Update frontmatter: append `'coverage'` to `stepsCompleted`; from the §3 tally, set `coveragePercentage` ← `coverage_percentage` (integer 0..100), `coverageCovered` ← `covered_count`, `coverageMissing` ← `missing_count` and `coverageReplaced` ← `replaced_count` (synthesize's verdict rollup reads the three counts)
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}`. On a non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `coverage:report`, with `"path": "{outputFile}"`.

### 7. Auto-Proceed to Next Step

{IF coverage_percentage is 0:} display one warning line (headless: log it), record it in the run sink, and continue; the run resolves to `NOT_FEASIBLE` in synthesize, and the report still carries a recommendation for each Missing or Replaced technology:
- when `total_referenced` is 0: "**Warning:** the architecture document names no technology, so there is nothing to verify. Name the stack's technologies in it (a Tech Stack section, say), then re-run [VS]." Record `no_technology_referenced: the architecture document names no technology`.
- when `live_count` is 0 (every referenced technology is Replaced): "**Warning:** every referenced technology is marked for removal or replacement, so nothing live is left to verify. Update the architecture document to describe the technologies that remain, then re-run [VS]." Record `no_live_technology: every referenced technology is marked for removal or replacement`.
- otherwise: "**Warning:** 0% coverage: no generated skill matches a referenced technology, so the integration and requirements passes have nothing to check. Generate skills with [CS] or [QS] for the Missing technologies, then re-run [VS]." Record `zero_coverage: no generated skill matches a referenced technology`.

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning to record>'
```

"**Proceeding to integration analysis...**"

Load, read the full file and then execute `{nextStepFile}`.
