---
nextStepFile: 'integrations.md'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
reportUpdateScript: 'scripts/skf-report-update.py'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
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
- Each technology gets exactly one verdict: Covered, Missing or Replaced (§3)

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 2. Extract Technology References

**Run the mentions helper once.** Resolve `{comentionHelper}` from `{comentionProbeOrder}` and `{enumerateStackSkillsHelper}` from `{enumerateStackSkillsProbeOrder}`; first existing path wins. Take the architecture document's path from `architectureDoc` in the `{outputFile}` frontmatter, then write the skill terms, add to the `aliases` of each skill in `{run_dir}/skill-terms.json` each other name a persistent fact gives the skill, and run the mentions helper:

```bash
uv run {enumerateStackSkillsHelper} terms --inventory "{inventoryFile}" -o "{run_dir}/skill-terms.json"
uv run {comentionHelper} mentions --doc "<architectureDoc>" --skills - > "{docMentionsFile}"
```

piping `{run_dir}/skill-terms.json` on stdin: a JSON array with one object per `skills[]` entry of `{inventoryFile}`, `{"name": "<name>", "aliases": [...]}`, where `aliases` holds the entry's `source_repo_basename` and `source_root_basename` that are not null, with the persistent-fact names added. If no candidate exists, or the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `coverage:mentions`, naming its first stderr line; a `terms` call that exits non-zero halts the same way. The integrations stage reads its `candidates[]` from `{docMentionsFile}` too.

**Skills the document names:** each skill in the helper's `mentioned` list is a referenced technology, labelled with the skill's `name`, whose source section is the `header` of its first `skills[].paragraphs[]` entry (none when that `header` is null or the document names the skill only in a heading).

**Other technologies:** write `{run_dir}/technologies.json`, a JSON array of the other technology, library and framework names the document's prose writes (`[]` when there is none): each once, as the document writes it but without a version (`Tailwind CSS` for "Tailwind CSS 3.x"), skipping each term that names a `mentioned` skill. Note the section each was first found under. Coverage reads only prose (headings, paragraphs, lists, tables): the helper skips every fenced block, a Mermaid diagram or an install command alike, so a skill the document names only inside one is in its `fenced_only` list, and no name from fenced code goes in the file.

### 3. Cross-Reference Against Skills

**Match the other technologies by script.** Run the §2 mentions command again (never the `terms` call, which would drop the added aliases) with the same array on stdin and `--technologies` added, overwriting `{docMentionsFile}` (the same HALT applies):

```bash
uv run {comentionHelper} mentions --doc "<architectureDoc>" --skills - --technologies "{run_dir}/technologies.json" > "{docMentionsFile}"
```

Each referenced technology matches a skill of `{inventoryFile}` this way:
- A `mentioned` skill matches its own row: the helper already matched its name and aliases.
- A `technologies[]` entry matches the `skill` of each `covered_by` entry of kind `name` or `alias`: the helper found the name equal to that skill's name or an alias once case, spaces, hyphens, dots and underscores are dropped (`Tailwind CSS` for `tailwindcss`).
- Judge only the names in `unverified_technologies`: one matches a skill under a common alias of the skill's name ("ReactJS" or "react.js" for a `react` skill, "PostgreSQL" for a `postgres` skill), or a framework name for the skill of a library it encompasses (e.g., "Tauri" encompasses the Tauri ecosystem). A `name-contained` or `alias-contained` entry is no match by itself: React Native is not `react`.
- A technology matched to a `mentioned` skill adds no row: that skill's own row stands.

**Run the mentions helper again when a technology matches a skill that is not `mentioned`.** Add the technology's term, as the document writes it, to that skill's `aliases` in `{run_dir}/skill-terms.json`. Keep a version written onto the name (`Vue3`, not `Vue`): the helper finds a term only at word boundaries. Once every technology is checked, run the command above once more with the extended array, overwriting `{docMentionsFile}` (the same HALT applies), and take §2's skill rows from the new file: each such skill is in `mentioned` now, and its row, labelled with its `name`, replaces the technology's. The integrations stage then finds that skill's pairs in `candidates[]`. With no such match, skip this run.

**Detect a deliberate-removal signal (from the architecture document):** Before assigning Covered/Missing, check whether the referenced technology is explicitly marked for removal or replacement in the architecture document itself. Be conservative — recognize a removal signal only when one of these is present, and when in doubt leave it as a normal reference (a false removal signal silently drops a real coverage gap):
- The technology is listed under a section whose heading matches (case-insensitive) one of: "deprecated", "removed", "legacy", "migrating away", "being replaced", "to be removed", "sunset", "retiring".
- The technology's own mention carries an inline removal annotation, e.g. "(deprecated)", "(being replaced by …)", "(removing)", "(to be removed)", "(legacy)".

Record the cited section heading or annotation text as evidence for every technology flagged this way.

**Assign verdict:**
- **Covered** — a matching skill exists in the inventory
- **Replaced** — no matching skill exists AND a deliberate-removal signal (above) was found; the technology is intentionally being removed/replaced, so no skill should exist for it
- **Missing** — no matching skill found and no removal signal

**Tally the matrix deterministically.** Write the matrix to `{run_dir}/coverage-rows.json` as `{"rows": [{"technology": "…", "section": "<its source section, or null>", "skill": "<the matching skill's name, or null>", "verdict": "Covered|Missing|Replaced"}, …]}`, one row per technology, and run:

```bash
uv run {coverageTallyScript} --stdin < "{run_dir}/coverage-rows.json" > "{run_dir}/coverage-tally.json"
```

`{run_dir}/coverage-tally.json` holds `covered_count`, `missing_count`, `replaced_count`, `live_count` (the denominator: Covered + Missing), `total_referenced` and `coverage_percentage` (run `uv run {coverageTallyScript} --help` for the contract). When it exits non-zero, it rejected the rows and the file says why (its JSON `error`): fix them and run it again.

### 4. Detect Extra Skills

Check if any skills in the inventory are not referenced in the architecture document: a skill in the `unmentioned` or `fenced_only` list of `{docMentionsFile}`, as §3 left it.

**Subdivide them by the skill's `source_repo_basename` in `{inventoryFile}`:**
- **Extra (unreferenced)** when `source_repo_basename` is set: "Skill `{skill_name}` exists and has a resolvable `source_repo`, but no architecture reference was found."
- **Orphan (source_repo unresolvable)** when `source_repo_basename` is null (metadata.json records no `source_repo`, or none a repository name can be read from): "Skill `{skill_name}` has no resolvable `source_repo`, so it cannot be cross-referenced against the architecture. Re-run [CS] or update the skill's metadata."

Both are informational: neither affects the coverage verdict.

### 5. Display Coverage Results

Render the matrix's table rows from the §3 rows file, once, for this display and the report (§6):

```bash
uv run {coverageTallyScript} --render --stdin < "{run_dir}/coverage-rows.json" > "{run_dir}/coverage-table.md"
```

`{run_dir}/coverage-table.md` holds one row per technology, its Source Section and Skill Match `none` where the rows file names none. On a non-zero exit it holds a JSON `error` instead: fix the row it names in `{run_dir}/coverage-rows.json`, run the §3 tally again, then this call.

"**Pass 1: Technology Coverage**

| Technology | Source Section | Skill Match | Verdict |
|------------|---------------|-------------|---------|
{the rows of `{run_dir}/coverage-table.md`}

**Coverage: {covered_count}/{live_count} ({coverage_percentage}%)** (from `{run_dir}/coverage-tally.json`; `live_count` excludes **Replaced** technologies)

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

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback).

Write the **Coverage Analysis** section of `{outputFile}` (see `{feasibilitySchemaRef}`; its section headings are fixed and ordered: `## Executive Summary`, `## Coverage Analysis`, `## Integration Verdicts`, `## Recommendations`, `## Evidence Sources`). First write `{run_dir}/coverage-section.md`: the §5 header `| Technology | Source Section | Skill Match | Verdict |` and its delimiter row, a blank line, then the coverage percentage, the missing skill recommendations, the Replaced (being removed/replaced) subdivision from section 3 with its cited removal evidence and no [CS]/[QS] recommendation, the Extra (unreferenced) and Orphan (source_repo unresolvable) subdivisions from section 4, and the §5 detection limitation when it shows. The report keeps its `## Coverage Analysis` line, so the file holds no `#` or `##` heading. Then run the calls in order, stopping at the first that exits non-zero:

```bash
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Coverage Analysis' < "{run_dir}/coverage-section.md"
uv run {reportUpdateScript} fill-table --report "{outputFile}" --heading 'Coverage Analysis' < "{run_dir}/coverage-table.md"
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind coverage < "{run_dir}/coverage-tally.json"
```

On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `coverage:report`. On exit 2 with `INVALID_INPUT`, or with no JSON (a usage error), fix the file or the call its `error` or usage line names, then run that call and the ones after it again. On exit 2 with `INVALID_REPORT`, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `coverage:report`, naming its `error`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `coverage:report`, with `"path": "{outputFile}"`, naming its JSON `error`.

### 7. Auto-Proceed to Next Step

{IF the `coverage_percentage` of `{run_dir}/coverage-tally.json` is 0:} display one warning line (headless: log it), record it in the run sink, and continue; the run resolves to `NOT_FEASIBLE` in synthesize, and the report still carries a recommendation for each Missing or Replaced technology:
- when `total_referenced` is 0: "**Warning:** the architecture document names no technology, so there is nothing to verify. Name the stack's technologies in it (a Tech Stack section, say), then re-run [VS]." Record `no_technology_referenced: the architecture document names no technology`.
- when `live_count` is 0 (every referenced technology is Replaced): "**Warning:** every referenced technology is marked for removal or replacement, so nothing live is left to verify. Update the architecture document to describe the technologies that remain, then re-run [VS]." Record `no_live_technology: every referenced technology is marked for removal or replacement`.
- otherwise: "**Warning:** 0% coverage: no generated skill matches a referenced technology, so the integration and requirements passes have nothing to check. Generate skills with [CS] or [QS] for the Missing technologies, then re-run [VS]." Record `zero_coverage: no generated skill matches a referenced technology`.

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning to record>'
```

"**Proceeding to integration analysis...**"

Load, read the full file and then execute `{nextStepFile}`.
