---
nextStepFile: 'requirements.md'
integrationRulesData: '{integrationRulesPath}'
coveragePatternsData: '{coveragePatternsPath}'
feasibilitySchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md'
  - '{project-root}/src/shared/references/feasibility-report-schema.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
cycleFinderProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-cycles.py'
  - '{project-root}/src/shared/scripts/skf-find-cycles.py'
outputFile: '{outputFolderPath}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{outputFolderPath}/feasibility-report-{project_slug}-latest.md'
---

<!-- Config: communicate in {communication_language}. Append the Integration Verdicts section to the report in {document_output_language}. -->

# Step 3: Integration Verification

## STEP GOAL:

Cross-reference API surfaces between library pairs that the architecture document claims work together. For each integration pair, verify language compatibility, protocol alignment, type compatibility, and documentation cross-references. Produce an evidence-backed verdict for each integration.

## Rules

- Focus only on integration pair verification using skill API surfaces
- Do not evaluate requirements coverage (Step 04) or parse Mermaid diagrams
- Every verdict must include evidence citations from the skills

## MANDATORY SEQUENCE

**Resolve `{feasibilitySchemaRef}`** from `{feasibilitySchemaProbeOrder}`; first existing path wins (installed SKF module path first, dev-checkout `src/` fallback) — used by the verdict-cap references and the append step below.

### 1. Load Integration Verification Rules

Load `{integrationRulesData}` for the cross-reference verification protocol.

Extract: verification checks (language boundary, protocol compatibility, type compatibility, documentation cross-reference), verdict criteria, and evidence requirements.

### 2. Extract Integration Claims

**Source preference:** If a stack skill assembled by `skf-create-stack-skill` is present in the inventory and its manifest (`bmad-skill-manifest.yaml` or its `metadata.json`) declares `integration_patterns`, use THAT as the primary source of integration claims. Record `source: stack manifest` on each resulting pair. Fall back to prose co-mention (below) only when no such manifest is available, and record `source: prose co-mention` on those pairs.

Parse the architecture document for statements describing two or more technologies working together.

**Detection method — prose-based co-mention analysis (fallback only):**
- Identify sentences or paragraphs where two or more technology names appear together
- Look for integration verbs: "connects to", "communicates with", "wraps", "extends", "consumes", "produces", "bridges", "integrates with", "sits between"
- Look for data flow descriptions: "{A} sends data to {B}", "{A} results are consumed by {B}"
- Look for layer boundary descriptions: "{A} at the API layer connects to {B} at the data layer"

**Mermaid Diagram Handling:** See `{coveragePatternsData}` → "Mermaid Diagram Handling" for the canonical rule (single source of truth). Summary: do not parse Mermaid diagram syntax for co-mention detection; use only prose text.

**Build integration pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted text or paraphrased description of their relationship

**Filter:** Only include pairs where BOTH libraries have a corresponding skill (Covered in Step 02). Skip pairs involving Missing skills — they cannot be verified.

### 3. Load Skill API Surfaces

<!-- Subagent delegation: read SKILL.md files in parallel, return compact JSON -->

For each library in an integration pair, delegate SKILL.md reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch if needed — same 8-way cap as step 1 §2; keeps aggregate token window manageable while still parallelizing typical stack sizes). Each subagent receives one skill's SKILL.md path and:
1. Reads the SKILL.md file
2. Extracts the API surface
3. Returns only this compact JSON — no prose, no extra commentary:

```json
{
  "skill_name": "...",
  "language": "...",
  "exports": ["functionName(params): ReturnType", "..."],
  "protocols_inferred": ["HTTP", "gRPC", "WebSocket", "message queue", "file I/O", "IPC"],
  "data_formats_inferred": ["JSON", "protobuf", "CSV", "binary", "streaming"]
}
```

**Extraction rules for subagents:**
- `skill_name`, `language`: mirror the skill's metadata fields
- `exports`: exported functions with signatures, exported types/interfaces/classes (extracted from SKILL.md prose)
- `protocols_inferred`: best-effort prose scan — protocol tokens mentioned in SKILL.md descriptions/examples; not a declared field in `metadata.json`
- `data_formats_inferred`: best-effort prose scan — format tokens mentioned in SKILL.md descriptions/examples; not a declared field in `metadata.json`
- If a field has no matches, return an empty array `[]`

**These fields are inferred, not declared.** `protocols` and `data_formats` do not exist in any skill's `metadata.json` — treat them as weak evidence from prose scanning only. When either list is used to justify compatibility in Check 2, cap the per-pair verdict at `Plausible` (see the schema's producer obligations — `{feasibilitySchemaRef}`).

**Schema validation (parent):** Each subagent response must contain the required keys (`skill_name`, `language`, `exports`). Reject responses missing required keys and exclude that skill from pair evaluation; if more than **20%** (same failure-budget threshold as step 1 §2; see the justification there) of subagent calls return malformed JSON, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with "API-surface extraction unreliable — more than 20% of subagent reads returned malformed JSON. Re-run [VS] after skills stabilize." In headless, emit the error envelope.

**Parent collects all subagent JSON summaries.** Do not load full SKILL.md content into parent context.

**From metadata.json (read in parent — lightweight), also extract:**
- `language` — primary programming language (authoritative — overrides subagent `language` if they disagree)
- `exports` — export names array (populated for individual skills; empty for stack skills)
- `stats.exports_documented` — export count
- `confidence_tier` — extraction confidence level

**mtime re-verification:** Re-stat each `metadata.json` and compare against the mtime captured in step 1. If any mtime moved during the run, abort any pair involving that skill with rationale "skill modified mid-run — re-run [VS]".

Store collected API surface summaries for cross-referencing.

### 4. Cross-Reference Each Integration Pair

For each integration pair `{library_a, library_b}`, run the four-check protocol and assign the per-pair verdict per `{integrationRulesData}` (loaded in §1): the Cross-Reference Protocol defines Check 1 (language boundary), Check 2 (protocol compatibility), Check 3 (type compatibility), and Check 4 (documentation cross-reference, required for `Verified`); the Verdict Definitions table and promotion rule define the `Verified` / `Plausible` / `Risky` / `Blocked` thresholds and the cap-at-`Plausible` rule that applies whenever Check 4 surfaces no literal citation. Do not restate those mechanics here.

**Step-specific input for Check 2:** Check 2 draws only on the `protocols_inferred` / `data_formats_inferred` lists surfaced by the §3 subagent prose scan. A shared or complementary token (e.g., "HTTP client" ↔ "HTTP server") reads as inferred compatibility; no token on either side, or conflicting tokens with no adapter, flags a risk. Any pair whose compatibility rests on this inferred evidence caps at `Plausible` per §3.

**Each verdict includes:**
- Which checks passed and which flagged
- Evidence citations: specific exports, types, or literal substrings from the skills
- `source: stack manifest` or `source: prose co-mention` tag (per section 2)
- For `Verified`: the exact Check 4 literal citation (e.g., `"see also: {lib_b}"` quoted from Skill A's SKILL.md, line N)
- **Tier annotation:** For each contributing skill, append `(evidence from Tier {n} skill)` citing that skill's `confidence_tier` (e.g., `(evidence from Tier 1 skill)`). This lets reviewers weigh evidence strength by extraction confidence.

**Cycle detection (after all pairs evaluated):** Deciding the edge set is a Check-4 judgment and stays here; the traversal is deterministic and is delegated to the shared helper (the in-prose DFS misses real multi-hop cycles or invents spurious ones as the pair count grows). 

1. **Build the directed pair graph in the prompt:** an edge `A → B` exists when skill A literally cites skill B via Check 4. Serialize the edges as JSON: `{"edges": [["A", "B"], ["B", "C"], ...]}` (each `[from, to]` pair is one Check-4 citation direction).
2. **Resolve `{cycleFinderHelper}`** from `{cycleFinderProbeOrder}`; first existing path wins. Enumerate cycles deterministically (run `uv run {cycleFinderHelper} find --help` for the contract):

   ```bash
   uv run {cycleFinderHelper} find --edges -
   ```
   piping the edges JSON on stdin (use a temp file under `{forge_data_folder}/` if stdin piping is unavailable). The script emits:
   ```json
   {"cycles": [["A", "B", "C", "A"], ...], "cycle_count": N}
   ```
   Each `cycles[]` entry is a closed node path (first node repeated at the end); every simple directed cycle appears exactly once, de-duplicated across rotations.

   **Graceful degradation:** if no `{cycleFinderProbeOrder}` candidate exists (e.g. `uv` unavailable on claude.ai web), run the equivalent DFS (visited set + recursion stack) directly per the `--help` contract and proceed with the same cycle set.
3. **For each cycle** in `cycles[]`, append a synthetic row to the verdict table with verdict `Risky` and rationale "circular integration dependency detected: `{A → B → C → A}`" (render the arrow chain from the cycle's node path). Do not otherwise modify the individual pair verdicts.

### 5. Display Integration Results

"**Pass 2: Integration Verification**

| Library A | Library B | Context | Source | Verdict | Evidence |
|-----------|-----------|---------|--------|---------|----------|
| {lib_a} | {lib_b} | {brief context} | {stack manifest / prose co-mention} | {Verified/Plausible/Risky/Blocked} | {key evidence, including Check 4 literal citation if Verified} |

**Summary:** {verified_count} Verified, {plausible_count} Plausible, {risky_count} Risky, {blocked_count} Blocked

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

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists: HALT (exit code 3, `halt_reason: "resolution-failure"`); in headless, emit the error envelope.

Write the **Integration Verdicts** section to `{outputFile}` (heading is fixed — consumers grep for `## Integration Verdicts`; the table header is the canonical `| lib_a | lib_b | verdict | rationale |` per `{feasibilitySchemaRef}`, and consumers parse that exact header, so a different one breaks them; the skill-local display table with the extra Context/Source/Evidence columns can be rendered beneath it for human readers):
- Emit the canonical `| lib_a | lib_b | verdict | rationale |` table first (verdict tokens are exactly one of `Verified`, `Plausible`, `Risky`, `Blocked`, case-sensitive — any other token is a schema violation consumers reject)
- Include the extended table with Context, Source, and Evidence columns below it
- Include recommendations for Risky and Blocked pairs (each Blocked recommendation cites a named candidate per step 5 H6, or the explicit no-candidate notice)
- Update frontmatter: append `'integrations'` to `stepsCompleted`; set `pairsVerified`, `pairsPlausible`, `pairsRisky`, `pairsBlocked` counts
- Pipe the updated full content through `python3 {atomicWriteHelper} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 7. Auto-Proceed to Next Step

**Early halt guard:** If ALL integration pairs are Blocked, present: "**All integrations are Blocked** — fundamental incompatibilities detected across all library pairs. Remaining analysis will produce limited value. **[X] Halt workflow (recommended)** | **[C] Continue anyway**" — wait for user input.

**GATE [default: C]** — Interactive-only guard. If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: continuing past all-Blocked integration gate". Headless never takes [X], so step 6 still emits the result contract — any Blocked pair resolves the run to `NOT_FEASIBLE` in synthesize.

- If X: halt with: "**Workflow halted — all integrations blocked.** Integration Verdicts saved to `{outputFile}`. Run **[VS]** after applying architectural changes. **Blocked integrations:** {list each blocked pair with reason}." HALT (exit code 8, `halt_reason: "analysis-halted"`).
- If C: continue.

{IF NOT halted (user selected C, or early halt guard did not trigger):}

"**Proceeding to requirements verification...**"

Load, read the full file and then execute `{nextStepFile}`.

