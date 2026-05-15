---
nextStepFile: 'requirements.md'
integrationRulesData: 'references/integration-verification-rules.md'
coveragePatternsData: 'references/coverage-patterns.md'
feasibilitySchemaRef: 'src/shared/references/feasibility-report-schema.md'
atomicWriteScript: '{project-root}/src/shared/scripts/skf-atomic-write.py'
outputFile: '{forge_data_folder}/feasibility-report-{project_slug}-{timestamp}.md'
outputFileLatest: '{forge_data_folder}/feasibility-report-{project_slug}-latest.md'
---

# Step 3: Integration Verification

## STEP GOAL:

Cross-reference API surfaces between library pairs that the architecture document claims work together. For each integration pair, verify language compatibility, protocol alignment, type compatibility, and documentation cross-references. Produce an evidence-backed verdict for each integration.

## Rules

- Focus only on integration pair verification using skill API surfaces
- Do not evaluate requirements coverage (Step 04) or parse Mermaid diagrams
- Every verdict must include evidence citations from the skills

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

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

**CRITICAL — Mermaid Diagram Handling:** See `{coveragePatternsData}` → "Mermaid Diagram Handling" for the canonical rule (single source of truth). Summary: do NOT parse Mermaid diagram syntax for co-mention detection; use only prose text.

**Build integration pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted text or paraphrased description of their relationship

**Filter:** Only include pairs where BOTH libraries have a corresponding skill (Covered in Step 02). Skip pairs involving Missing skills — they cannot be verified.

### 3. Load Skill API Surfaces

<!-- Subagent delegation: read SKILL.md files in parallel, return compact JSON -->

For each library in an integration pair, delegate SKILL.md reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch if needed — same 8-way cap as step 1 §2; keeps aggregate token window manageable while still parallelizing typical stack sizes). Each subagent receives one skill's SKILL.md path and MUST:
1. Read the SKILL.md file
2. Extract the API surface
3. ONLY return this compact JSON — no prose, no extra commentary:

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
- `protocols_inferred`: best-effort prose scan — protocol tokens mentioned in SKILL.md descriptions/examples. NOT a declared field in `metadata.json`
- `data_formats_inferred`: best-effort prose scan — format tokens mentioned in SKILL.md descriptions/examples. NOT a declared field in `metadata.json`
- If a field has no matches, return an empty array `[]`

**CRITICAL — these fields are inferred, not declared.** `protocols` and `data_formats` do not exist in any skill's `metadata.json`. Treat them as weak evidence from prose scanning only. When either list is used to justify compatibility in Check 2, the per-pair verdict MUST be capped at `Plausible` (see the schema's producer obligations — `src/shared/references/feasibility-report-schema.md`).

**Schema validation (parent):** Each subagent response must contain the required keys (`skill_name`, `language`, `exports`). Reject responses missing required keys and exclude that skill from pair evaluation; HALT if more than **20%** (same failure-budget threshold as step 1 §2; see the justification there) of subagent calls return malformed JSON.

**Parent collects all subagent JSON summaries.** Do not load full SKILL.md content into parent context.

**From metadata.json (read in parent — lightweight), also extract:**
- `language` — primary programming language (authoritative — overrides subagent `language` if they disagree)
- `exports` — export names array (populated for individual skills; empty for stack skills)
- `stats.exports_documented` — export count
- `confidence_tier` — extraction confidence level

**mtime re-verification:** Re-stat each `metadata.json` and compare against the mtime captured in step 1. If any mtime moved during the run, abort any pair involving that skill with rationale "skill modified mid-run — re-run [VS]".

Store collected API surface summaries for cross-referencing.

**Integration-evidence source preference:** If the stack was assembled by `skf-create-stack-skill` and a stack manifest (e.g., `integration_patterns` block in the stack skill's `bmad-skill-manifest.yaml` or `metadata.json`) is present in the inventory, use that as the authoritative integration source and cite `source: stack manifest` in each verdict. Fall back to prose co-mention only when no manifest is available, and cite `source: prose co-mention`.

### 4. Cross-Reference Each Integration Pair

For each integration pair `{library_a, library_b}`, apply the verification protocol from `{integrationRulesData}`:

**Check 1 — Language Boundary:**
- Same language → compatible
- Different languages → check for FFI, IPC, or network protocol bridge
- If no bridge mechanism documented → flag as risk

**Check 2 — Protocol Compatibility (best-effort prose scan):**
- Uses only the `protocols_inferred` / `data_formats_inferred` lists surfaced by the subagent prose scan — these are NOT declared metadata fields
- Both prose-scanned lists share a protocol token → treat as inferred compatibility (cap verdict at `Plausible`)
- Complementary tokens (e.g., "HTTP client" in one, "HTTP server" in the other) → inferred compatibility (cap at `Plausible`)
- Neither skill surfaces any protocol token, or tokens appear to conflict with no adapter mentioned → flag as risk
- Do NOT assert that protocols come from a declared schema field; when prose evidence is all that's available, the per-pair verdict MUST cap at `Plausible`

**Check 3 — Type Compatibility:**
- Shared types or compatible serialization formats (cited from `exports` signatures) → compatible
- Incompatible type systems with no conversion layer → flag as risk

**Check 4 — Documentation Cross-Reference (REQUIRED for `Verified`):**
- Search Skill A's SKILL.md for a literal substring/name citation of Skill B's library name (or an explicit alias declared in that skill's metadata)
- Search Skill B's SKILL.md for the reciprocal citation
- If a literal citation is found in at least one direction → Check 4 PASSES; record the exact cited substring and its location as evidence
- If neither skill literally cites the other → Check 4 FAILS (weak/missing evidence); per-pair verdict MUST be capped at `Plausible` regardless of Checks 1–3 outcomes

**Assign verdict per pair (per `src/shared/references/feasibility-report-schema.md`):**
- **Verified** — Checks 1, 3 pass with declared evidence AND Check 4 passes with a literal substring/name citation recorded in the evidence block. Check 2 is best-effort only; it cannot by itself promote a pair to `Verified`.
- **Plausible** — Checks pass, but at least one relies on inferred evidence (e.g., Check 2 prose scan) OR Check 4 is weak/missing. This is the cap whenever Check 4 fails.
- **Risky** — At least one check flags an incompatibility that a workaround may resolve (bridge layer, adapter, serialization shim).
- **Blocked** — Fundamental incompatibility: language barrier with no bridge documented anywhere in the inventory, or type/protocol mismatch with no adapter mentioned.

**Each verdict MUST include:**
- Which checks passed and which flagged
- Evidence citations: specific exports, types, or literal substrings from the skills
- `source: stack manifest` or `source: prose co-mention` tag (per section 3)
- For `Verified`: the exact Check 4 literal citation (e.g., `"see also: {lib_b}"` quoted from Skill A's SKILL.md, line N)
- **Tier annotation:** For each contributing skill, append `(evidence from Tier {n} skill)` citing that skill's `confidence_tier` (e.g., `(evidence from Tier 1 skill)`). This lets reviewers weigh evidence strength by extraction confidence.

**Cycle detection (after all pairs evaluated):** Build a directed pair graph where an edge `A → B` exists when A cites B via Check 4. Run cycle detection (DFS with visited + recursion stack). For each cycle found, append a synthetic row to the verdict table with verdict `Risky` and rationale "circular integration dependency detected: `{A → B → C → A}`". Do not otherwise modify the individual pair verdicts.

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

Write the **Integration Verdicts** section to `{outputFile}` (heading is fixed — consumers grep for `## Integration Verdicts`; the table header MUST be the canonical `| lib_a | lib_b | verdict | rationale |` per `{feasibilitySchemaRef}`; the skill-local display table with the extra Context/Source/Evidence columns can be rendered beneath it for human readers):
- Emit the canonical `| lib_a | lib_b | verdict | rationale |` table first (verdict tokens MUST be one of `Verified`, `Plausible`, `Risky`, `Blocked` — case-sensitive)
- Include the extended table with Context, Source, and Evidence columns below it
- Include recommendations for Risky and Blocked pairs (Blocked recommendations MUST cite a named candidate per step 5 H6, or the explicit no-candidate notice)
- Update frontmatter: append `'integrations'` to `stepsCompleted`; set `pairsVerified`, `pairsPlausible`, `pairsRisky`, `pairsBlocked` counts
- Pipe the updated full content through `python3 {atomicWriteScript} write --target {outputFile}` and again with `--target {outputFileLatest}`

### 7. Auto-Proceed to Next Step

**Early halt guard:** If ALL integration pairs are Blocked, present: "**All integrations are Blocked** — fundamental incompatibilities detected across all library pairs. Remaining analysis will produce limited value. **[X] Halt workflow (recommended)** | **[C] Continue anyway**" — wait for user input. If X: halt with: "**Workflow halted — all integrations blocked.** Integration Verdicts saved to `{outputFile}`. Run **[VS]** after applying architectural changes. **Blocked integrations:** {list each blocked pair with reason}." If C: continue.

{IF NOT halted (user selected C, or early halt guard did not trigger):}

"**Proceeding to requirements verification...**"

Load, read the full file and then execute `{nextStepFile}`.

