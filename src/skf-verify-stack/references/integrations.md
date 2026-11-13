---
nextStepFile: 'requirements.md'
integrationRulesData: 'references/integration-verification-rules.md'
coverageTallyScript: 'scripts/skf-coverage-tally.py'
skillSummariesScript: 'scripts/skf-skill-summaries.py'
reportUpdateScript: 'scripts/skf-report-update.py'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
# §3 re-enumerates the skills against step 1's inventory (--expect-hashes)
# to find a skill that changed mid-run.
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
# §4 lists the literal citations between the paired skills' SKILL.md
# (Check 4 evidence and the cycle edges) with its cross-reference mode.
scanSkillMdStructureProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-skill-md-structure.py'
  - '{project-root}/src/shared/scripts/skf-scan-skill-md-structure.py'
cycleFinderProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-cycles.py'
  - '{project-root}/src/shared/scripts/skf-find-cycles.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
inventoryFile: '{run_dir}/skill-inventory.json'
docMentionsFile: '{run_dir}/doc-mentions.json'
---

<!-- Config: communicate in {communication_language}. Append the Integration Verdicts section to the report in {document_output_language}. -->

# Step 3: Integration Verification

## STEP GOAL:

Cross-reference API surfaces between library pairs that the architecture document claims work together. For each integration pair, verify language compatibility, protocol alignment, type compatibility, and documentation cross-references. Produce an evidence-backed verdict for each integration.

## Rules

- Focus only on integration pair verification using skill API surfaces
- Do not evaluate requirements coverage (Step 04) or read the architecture document again: step 2's mentions run holds its candidate pairs
- Every verdict must include evidence citations from the skills

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback). The append step below uses it.

### 1. Load Integration Verification Rules

Load `{integrationRulesData}` for the cross-reference verification protocol.

### 2. Extract Integration Claims

**Prose co-mention:** step 2's mentions run already found the candidate pairs. Take each entry of `candidates[]` in `{docMentionsFile}` whose two skills (`a` and `b`) are both Covered in Step 02, and judge it from its `evidence[]` (`unit_excerpt`, with its `header` and `unit_line`): it is an integration claim when an entry describes an *integration relationship* (data flowing between the two, one wrapping, bridging, extending or consuming the other, or a layer boundary connecting them), not mere co-mention in the same text. A pair outside `candidates[]` is not claimed: no paragraph names both, the document only lists them together, or it draws them only in fenced code, such as a Mermaid diagram, which the mentions helper never reads.

**Build integration pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted `unit_excerpt` of the evidence entry that shows the relationship

**Filter:** Only include pairs where BOTH libraries have a corresponding skill (Covered in Step 02). Skip pairs involving Missing skills: they cannot be verified. Drop a pair whose two technologies step 2 matched to the same skill: it is one library, with no integration to verify, and §5 lists it.

**Stage the pairs** for the §4 citation scan: write `{run_dir}/integration-pairs.json` as `{"pairs": [["<skill_a>", "<skill_b>"], ...]}`, naming each pair once by the two skills step 2 matched its technologies to (the Skill Match column), as `{inventoryFile}` names them. With no pair, write `{"pairs": []}`.

### 3. Load Skill API Surfaces

<!-- Subagent delegation: read SKILL.md files in parallel, each writes its compact JSON to a file -->

For every skill step 2 matched to a Covered technology (the Skill Match column), in an integration pair or not, delegate SKILL.md reading to a parallel subagent: step 4 maps requirements from these summaries, so no later stage reads a SKILL.md in this context. Create the folder `{run_dir}/summaries/` first. Launch up to **8 subagents concurrently**, in batches of 8 when more skills need reading (the cap keeps the aggregate token window manageable while still parallelizing typical stack sizes). Each subagent receives one skill's SKILL.md path and its summary file, `{run_dir}/summaries/<skill>.json` named for the skill as `{inventoryFile}` names it, and:
1. Reads the SKILL.md file
2. Extracts the API surface and what the library can do
3. Writes only this compact JSON to the summary file, with no prose and no extra commentary, and replies with nothing else:

```json
{
  "skill_name": "...",
  "exports": ["functionName(params): ReturnType", "..."],
  "protocols_inferred": ["HTTP", "gRPC", "WebSocket", "message queue", "file I/O", "IPC"],
  "data_formats_inferred": ["JSON", "protobuf", "CSV", "binary", "streaming"],
  "capabilities": ["offline-first sync", "server-side rendering", "..."]
}
```

**Extraction rules for subagents:**
- `skill_name`: the `name` in the SKILL.md frontmatter
- `exports`: exported functions with signatures, exported types/interfaces/classes (extracted from SKILL.md prose)
- `protocols_inferred`, `data_formats_inferred`: protocol and format tokens mentioned in the SKILL.md descriptions and examples
- `capabilities`: up to 10 short phrases naming what the library does, from the SKILL.md description and its sections (the requirements stage matches each requirement against them)
- If a field has no matches, write an empty array `[]`

**When subagents are unavailable**, read the SKILL.md files yourself, one at a time and in the same order: for each skill, read its SKILL.md, write its compact JSON by the rules above to `{run_dir}/summaries/<skill>.json` at once, then go on to the next. Each summary is on disk as its read ends, so a context compaction loses none.

**These two lists are inferred from prose, not declared** (no skill's `metadata.json` has `protocols` or `data_formats`), so they are weak evidence: Check 2 reads them as `{integrationRulesData}` says.

**Merge the summaries.** Run the helper with `--skills` naming every skill this section reads and `--subagent-skills` the ones a subagent read, each list comma-separated as `{inventoryFile}` names the skills, and empty when no skill is read; the fallback leaves out `--subagent-skills`:

```bash
uv run {skillSummariesScript} merge --dir "{run_dir}/summaries" --inventory "{inventoryFile}" --skills "<every name>" --subagent-skills "<names>" -o "{run_dir}/skill-summaries.json"
```

It writes `{run_dir}/skill-summaries.json`, the file the requirements stage reads, and prints `accepted`, `rejected[]` (each `skill` with its `reason`), `malformed_ratio` and `over_budget` (run `uv run {skillSummariesScript} --help` for the contract). Each summary takes the skill's `language`, `exports_documented` and its inventory `exports` (as `inventory_exports`) from `{inventoryFile}`, which the enumerate helper read from `metadata.json`, so the parent never opens it. When it exits 2, its JSON `error` names a skill the call should not hold: fix the names and run it again. When it exits 3, it could not write `{run_dir}/skill-summaries.json`: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `integrations:api-surfaces`, with `"path": "{run_dir}/skill-summaries.json"`, naming its JSON `error`. When it exits 1 or prints no JSON, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `integrations:api-surfaces`.

**Re-read each rejected skill once.** When `rejected[]` is not empty, read the SKILL.md of each skill it names yourself, one at a time as the fallback does, and overwrite its `{run_dir}/summaries/<skill>.json` (a SKILL.md you cannot open leaves its file as it was). Then run the same merge again and read only that second result. Apart from the fallback's reads and these re-reads, never load a full SKILL.md into the parent context.

**If `over_budget` is true**, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) at phase `integrations:api-surfaces` with "API-surface reads failed for more than 20% of the skills; the skills themselves may be fine: re-run [VS]." Only the skills a subagent read count toward it, after their re-read, so the fallback never halts here.

**A skill still rejected is unreadable.** A pair involving it is not rated: its row in every table and in `verdict-rows.json` (§4) carries the verdict `Risky` and the rationale "API surface unreadable: re-run [VS]", the requirements stage names the skill as not read, and each such skill is recorded once in the run sink:

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'skill_summary_unreadable: <skill>'
```

A pair with a skill the mid-run check below also names takes that check's rationale instead; record both warnings.

**Mid-run change check.** Resolve `{enumerateStackSkillsHelper}` from `{enumerateStackSkillsProbeOrder}`; first existing path wins. Re-enumerate against the inventory step 1 wrote, which compares each skill's `metadata_hash` with the one recorded then:

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --expect-hashes "{inventoryFile}" > "{run_dir}/inventory-recheck.json"
```

If no candidate exists, or the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `integrations:change-check`. Read only its `changed_skills` and `missing_skills`: a pair involving one of those skills is not rated. Its row in every table and in `verdict-rows.json` (§4) carries the verdict `Risky` and the rationale "skill modified mid-run: re-run [VS]", and each such skill is recorded once in the run sink:

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'skill_modified_mid_run: <skill>'
```

The recheck's `new_skills` appeared after step 1 and are not part of this run.

### 4. Cross-Reference Each Integration Pair

For each integration pair `{library_a, library_b}`, run the four-check protocol and assign the per-pair verdict per `{integrationRulesData}` (loaded in §1): its Cross-Reference Protocol defines Checks 1 to 4, and its Verdict Definitions define the four verdicts and the Plausible cap. Apply them as written there. Checks 1 to 3 read each skill's record in the `summaries` of `{run_dir}/skill-summaries.json` (§3): its `language`, `exports` and the `protocols_inferred` / `data_formats_inferred` lists.

**Run the citation scan once**, before rating the first pair. Resolve `{scanSkillMdStructureHelper}` from `{scanSkillMdStructureProbeOrder}`; first existing path wins. Then run:

```bash
uv run {scanSkillMdStructureHelper} cross-reference --skills "{inventoryFile}" --skills-root "{skills_output_folder}" --pairs "{run_dir}/integration-pairs.json" > "{run_dir}/citations.json"
```

If no candidate exists, or the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `integrations:citations`, naming its first stderr line. Check 4 reads each citing direction of `citations[]` in `{run_dir}/citations.json`: `from`, `to` and its `hits[]`, each with its `line`, the `substring` as written and an `excerpt`. Its `warnings[]` name a SKILL.md the scanner could not read, whose skill then cites nothing.

**Each verdict includes:**
- Which checks passed and which flagged
- Evidence citations: specific exports, types, or literal substrings from the skills
- For `Verified`: the Check 4 citation from `{run_dir}/citations.json`, its `substring` and `line` in the citing skill's SKILL.md with the hit's `excerpt` (e.g., `"react-query"` at line 42 of `next`'s SKILL.md)
- **Tier annotation:** For each contributing skill, append `(evidence from a {evidence_tier} skill)` with that skill's `evidence_tier` from `skill_inventory` (e.g., `(evidence from a T1 skill)`), so reviewers weigh the evidence by the tier its skill rests on.

**Cycle detection (after all pairs evaluated):** an edge `A → B` exists when skill A literally cites skill B (Check 4). Two skills that cite each other are not a cycle: their mutual citation is Check 4 evidence for their own pair, and a loop built only from such pairs is no cycle either.

1. **Record the rejected directions:** write `{run_dir}/rejected-edges.json` as `{"edges": [["<from>", "<to>"], ...]}`, one entry per citing direction of `{run_dir}/citations.json` whose every hit Check 4 rejected as a common word, and `{"edges": []}` when it rejected none.
2. **Resolve `{cycleFinderHelper}`** from `{cycleFinderProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `integrations:cycles`. Enumerate cycles deterministically (run `uv run {cycleFinderHelper} find --help` for the contract):

   ```bash
   uv run {cycleFinderHelper} find --edges "{run_dir}/citations.json" --exclude-edges "{run_dir}/rejected-edges.json" --skip-mutual > "{run_dir}/cycles.json"
   ```
   It reads the `edges` of the citations file (one `[from, to]` pair per citing direction), leaves out the rejected directions and every cycle whose edges are all mutual citations, and writes:
   ```json
   {"cycles": [["A", "B", "C", "A"], ...], "cycle_count": N}
   ```
   Each `cycles[]` entry is a closed node path (first node repeated at the end) through three or more skills, with at least one one-way citation; every such cycle appears exactly once, de-duplicated across rotations. With no pair it writes an empty list.
3. **For each cycle** in `cycles[]`, the canonical table holds one more `Risky` row, which §6 renders after the pair rows. Its `lib_a`, `cycle`, keeps the row apart from every pair row, since the next run's delta keys rows on their two libraries. Leave the pair verdicts as they are.

**Count the verdicts deterministically.** Write `{run_dir}/verdict-rows.json` as `{"rows": [{"lib_a": "…", "lib_b": "…", "verdict": "Verified|Plausible|Risky|Blocked", "rationale": "<the checks and evidence behind the verdict, one line>"}, …]}`, one row per pair and no cycle row (§6 renders the canonical rows from it), and run:

```bash
uv run {coverageTallyScript} --kind integrations --cycles "{run_dir}/cycles.json" --pairs "{run_dir}/integration-pairs.json" --stdin < "{run_dir}/verdict-rows.json" > "{run_dir}/verdict-tally.json"
```

`{run_dir}/verdict-tally.json` holds `pairs_verified`, `pairs_plausible`, `pairs_risky` (each cycle counted as one `Risky` row), `pairs_blocked`, `pair_count`, `cycle_count` and `row_count` (run `uv run {coverageTallyScript} --help` for the contract). When it exits non-zero, it rejected its input and the file says why (its JSON `error`, which names each staged pair that no row names by its two skills; a row that names a pair by a technology or an alias still counts for it): fix the rows and run it again.

### 5. Display Integration Results

The Summary line shows the counts of `{run_dir}/verdict-tally.json` (`pairs_risky` includes each cycle row).

"**Pass 2: Integration Verification**

| Library A | Library B | Context | Verdict | Evidence |
|-----------|-----------|---------|---------|----------|
| {lib_a} | {lib_b} | {brief context} | {Verified/Plausible/Risky/Blocked} | {key evidence, including Check 4 literal citation if Verified} |

**Summary:** {pairs_verified} Verified, {pairs_plausible} Plausible, {pairs_risky} Risky, {pairs_blocked} Blocked

{IF §2 dropped a pair whose technologies are one skill:}
**Not verified (one skill):** `{tech_a}` and `{tech_b}` both match `{skill}`, so there is no integration between two skills to check.

{IF zero integration pairs found:}
**No integration claims detected in the architecture document prose.** Ensure your architecture document describes relationships between technologies in text form (not exclusively in Mermaid diagrams). Coverage-only analysis was performed.

{IF any Risky:}
**Risky Integrations — Recommendations:**
{For each risky pair:}
- `{lib_a}` ↔ `{lib_b}`: {specific concern}. **Recommendation:** {prescriptive action}

{IF any Blocked:}
**Blocked Integrations — Action Required:**
{For each blocked pair:}
- `{lib_a}` ↔ `{lib_b}`: {fundamental incompatibility}. **Recommendation:** {prescriptive action}"

### 6. Append to Report

Write the **Integration Verdicts** section of `{outputFile}`. The report template already holds the canonical table under `## Integration Verdicts`: the header `| lib_a | lib_b | verdict | rationale |` (per `{feasibilitySchemaRef}`) and its delimiter row. Consumers read that table and reject a report that holds it twice, so fill it in place instead of appending another one. Render its rows from the §4 rows file and the cycles, one per pair and one per §4 cycle, each verdict a schema token and each rationale kept in its cell:

```bash
uv run {coverageTallyScript} --kind integrations --render --cycles "{run_dir}/cycles.json" --stdin < "{run_dir}/verdict-rows.json" > "{run_dir}/verdict-table.md"
```

On a non-zero exit, `{run_dir}/verdict-table.md` holds a JSON `error` instead: fix the row it names in `{run_dir}/verdict-rows.json`, run the §4 tally again, then this call. With zero integration pairs, leave the table with its header and delimiter rows only.

Write `{run_dir}/integration-details.md`: the §5 display table with the extra Context and Evidence columns for human readers, the one-skill and zero-pair notes when they show, and the recommendations for Risky and Blocked pairs (a Blocked one that proposes a replacement names at least one alternative library with a one-line justification, or says no named candidate was found and gives the selection criteria). Its `### Integration Details` subsection sits below the canonical table, which consumers read alone. The helper writes that `###` line, so the file holds no `#`, `##` or `###` heading. Then run the calls in order, stopping at the first that exits non-zero:

```bash
uv run {reportUpdateScript} fill-table --report "{outputFile}" --heading 'Integration Verdicts' < "{run_dir}/verdict-table.md"
uv run {reportUpdateScript} replace-section --report "{outputFile}" --heading 'Integration Verdicts' --subsection 'Integration Details' < "{run_dir}/integration-details.md"
uv run {reportUpdateScript} set-counts --report "{outputFile}" --kind integrations < "{run_dir}/verdict-tally.json"
```

On exit 1, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `integrations:report`. On exit 2 with `INVALID_INPUT`, or with no JSON (a usage error), fix the file or the call its `error` or usage line names, then run that call and the ones after it again. On exit 2 with `INVALID_REPORT`, HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `integrations:report`, naming its `error`. On exit 3, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `integrations:report`, with `"path": "{outputFile}"`, naming its JSON `error`.

### 7. Auto-Proceed to Next Step

{IF the `pair_count` of `{run_dir}/verdict-tally.json` is not 0 and its `pairs_blocked` equals `pair_count` (every pair is Blocked):} display one warning line (headless: log it), record it in the run sink, and continue, so synthesize can recommend a way past each Blocked pair: "**Warning:** every integration pair is Blocked; the run will resolve to `NOT_FEASIBLE`, and the report will name a replacement library or a bridge for each Blocked pair."

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'all_pairs_blocked: every integration pair is Blocked'
```

"**Proceeding to requirements verification...**"

Load, read the full file and then execute `{nextStepFile}`.
