---
nextStepFile: 'compile.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
# If neither path exists, §2 finds no enrichment collection and the step is
# skipped.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# §4 appends the T2 annotations to the extraction inventory through it.
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Enrich

## STEP GOAL:

To enrich the extraction inventory with temporal context from QMD knowledge searches — issues, PRs, changelogs, and migration notes that add T2-confidence annotations to extracted functions. Deep tier only; Quick, Forge, and Forge+ tiers skip this step entirely.

## Rules

- Focus only on QMD searches to annotate extracted functions — enrichment is additive only
- Do not begin compilation (Step 05)
- QMD failures degrade gracefully — continue without enrichment
- Quick, Forge, and Forge+ tiers: skip this step entirely, auto-proceed

## MANDATORY SEQUENCE

### 1. Check Tier Eligibility

**If tier is Quick, Forge, or Forge+:**

Auto-proceed silently. Display no message. Immediately load, read entire file, then execute `{nextStepFile}`.

**If tier is Deep:**

Continue to step 2.

### 2. Collection Inventory Pre-check (Deep Tier Only)

Before searching, find this skill's enrichment collections. Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}` and read the registry as JSON, from `{project-root}`:

```bash
uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"
```

1. Bind `{enrichment_collections}` ← the `name` of each entry of its `data.qmd_collections` whose `skill_name` is `{skill-name}` and whose `type` is `"temporal"` (issues, PRs and changelogs, from step 3b) or `"docs"` (fetched external documentation, from step 3c): at most `{skill-name}-temporal` and `{skill-name}-docs`. Another skill's collections never count, and neither do `"extraction"` or `"brief"` collections. The list is empty when `exists` is false, the command fails or no candidate resolves.
2. **If `{enrichment_collections}` is empty:** report this and auto-proceed. Display:

"**Enrichment: no enrichment collections available.**
No temporal context (issues, PRs, changelogs) or docs collection of this skill is indexed in QMD. {IF extraction_mode is 'docs-only' AND T3 items exist in extraction_inventory: 'T3 documentation content is available in the extraction inventory: enrichment through QMD is skipped, and the T3 content will be compiled.'} {ELSE: 'Enrichment skipped (expected for first-run skill creation). Enrichment becomes available when temporal or docs context is indexed into QMD collections.'}

Proceeding to compilation..."

Then immediately load, read entire file, then execute `{nextStepFile}`.

3. **Otherwise** (a temporal collection, a docs collection, or both): continue to step 3.

### 3. QMD Enrichment Searches (Deep Tier Only)

For each major exported function (the **top-level public API surface**, typically the 10-20 functions that will appear in the context-snippet, not all extracted exports), search `{enrichment_collections}` for context. Every query below passes them as its collections, so no other skill's issues or docs can annotate this one:

**Search query construction:**

Read the functions and their source files from `{extraction_inventory}`, the extraction inventory step 3 §5 wrote. For each function, derive the **module context** from its source file path (e.g., `src/graph/neo4j/index.ts` → module context `graph neo4j`). This context improves search relevance by scoping results to the function's subsystem without adding extra queries.

**Primary searches (BM25 — always runs, no GPU/VRAM dependency):**

1. **Issues/PRs:** `qmd_bridge.query(searches=[{type:'lex', query:'{module_context} {function_name}', intent:'issues-prs'}], collections={enrichment_collections})`: related discussions, scoped by module context
2. **Changelog entries:** `qmd_bridge.query(searches=[{type:'lex', query:'{function_name} changelog', intent:'changelog'}], collections={enrichment_collections})`: version history and breaking changes (kept generic, since changelogs rarely use module paths)
3. **Migration notes:** `qmd_bridge.query(searches=[{type:'lex', query:'{function_name} migration deprecated breaking', intent:'migration'}], collections={enrichment_collections})`: deprecation or migration context, by exact keyword matching

**Supplemental search (best-effort — requires GPU/VRAM, may fail):**

4. **Semantic migration context:** `qmd_bridge.query(searches=[{type:'vec', query:'{module_context} {function_name} migration deprecated', intent:'semantic-migration'}], collections={enrichment_collections})`: adds semantic matches (synonyms, paraphrases) that BM25 keyword search may miss. Merge results with search #3, deduplicating by document ID. If the `vec`-type search fails (VRAM, GPU driver, model loading), discard silently: the BM25 (`lex`) results from search #3 provide baseline coverage.

**Tool resolution for qmd_bridge:** QMD MCP exposes a single `query` tool that accepts a `searches[]` array and a `collections` list. Each search has a `type` field (`'lex'` for BM25 keyword search, `'vec'` for semantic vector search, `'hyde'` for hypothetical-document retrieval) plus `query` and `intent` fields. Claude Code: `mcp__plugin_qmd-plugin_qmd__query`. Cursor: qmd MCP server. CLI: `qmd search "{query}"` (BM25) or `qmd vsearch "{query}"` (semantic), with one `-c {collection}` for each collection of `{enrichment_collections}`. See `knowledge/tool-resolution.md`.

**Tool probe (graceful degradation):** If any tool-not-found error surfaces while invoking `query` (e.g., legacy `vector_search` still expected by an older client, or a bridge returns "tool not registered"), treat it as a non-fatal failure for that function's enrichment and continue with the remaining functions. Do not retry against the stale `vector_search` tool name — that name was removed from the QMD MCP server. Record the degradation in context for the evidence report.

**For each QMD result from a collection of `{enrichment_collections}`** (drop a result from any other collection):

- Create a T2 annotation: `[QMD:{collection}:{doc}]`
- Classify temporal relevance:
  - **T2-past:** Historical context (why it was built, what it replaced)
  - **T2-future:** Forward-looking context (planned changes, deprecation warnings)

**Handling QMD failures:**

- If qmd_bridge is unavailable: skip all enrichment, note in context
- If individual search fails: skip that function's enrichment, continue with others
- If QMD returns no results for a function: no annotation added (absence is normal)

### 4. Annotate Extraction Inventory

Add the enrichment annotations to `{extraction_inventory}` without modifying its extraction data, so compile reads them from disk. One annotation per finding, for each function that has one:

- Related issues/PRs with summary
- Changelog history (version changes, breaking changes)
- Migration/deprecation context
- T2 provenance citation for each annotation

Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` and, from `{project-root}`, append them all in one call:

```bash
uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field t2_annotations <<'SKF_T2'
[{"export_name": "...", "kind": "issue|pr|changelog|migration", "temporal": "T2-past|T2-future", "summary": "...", "citation": "[QMD:{collection}:{doc}]"}]
SKF_T2
```

When it exits non-zero, fix the JSON and run it once more: an annotation the inventory already holds is not added twice. When it fails again, or no path resolves, warn "T2 annotations were not saved to the extraction inventory: {its message}" and continue without them: enrichment never halts the workflow.

**Enrichment summary counts** come from the call's output, never counted by hand: `counts.functions_enriched` (the functions with at least one annotation), `counts.t2_annotations`, `counts.t2_past` and `counts.t2_future` (the annotations by their `temporal`). When the call failed, each is 0.

### 5. Report Enrichment (Deep Tier Only)

Display brief enrichment summary:

"**Enrichment complete.**

**Functions enriched:** {counts.functions_enriched} of {the functions §3 searched}
**T2 annotations:** {counts.t2_annotations} ({counts.t2_past} historical, {counts.t2_future} forward-looking)

Proceeding to compilation..."

### 6. Auto-Proceed

No user interaction. After enrichment completes (or is skipped for non-Deep tiers), load `{nextStepFile}`, read it fully, then execute it.

