---
name: 'step-04-enrich'
description: 'QMD knowledge enrichment for extracted functions — Deep tier only, skip for Quick/Forge/Forge+'
nextStepFile: './step-05-compile.md'
---

# Step 4: Enrich

## STEP GOAL:

To enrich the extraction inventory with temporal context from QMD knowledge searches — issues, PRs, changelogs, and migration notes that add T2-confidence annotations to extracted functions. Deep tier only; Quick, Forge, and Forge+ tiers skip this step entirely.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing knowledge enrichment
- ✅ QMD enrichment adds temporal depth — it never replaces AST extraction
- ✅ Enrichment failure is graceful degradation, not an error

### Step-Specific Rules:

- 🎯 Focus ONLY on QMD searches to annotate extracted functions
- 🚫 FORBIDDEN to modify extraction results — enrichment is additive only
- 🚫 FORBIDDEN to begin compilation — that's step-05
- 💬 QMD failures degrade gracefully — continue without enrichment
- ⏱️ Quick, Forge, and Forge+ tiers: skip this step entirely, auto-proceed

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Enrichment annotations are added to extraction inventory in context
- 📖 QMD results become T2-confidence annotations
- 🚫 Never replace T1 extraction data with QMD findings

## CONTEXT BOUNDARIES:

- Available: extraction_inventory from step-03, brief_data, tier from step-01
- Focus: Adding temporal context to extracted functions
- Limits: Do NOT modify extraction results, only annotate them
- Dependencies: Extraction inventory must exist from step-03

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tier Eligibility

**If tier is Quick, Forge, or Forge+:**

Auto-proceed silently. Display no message. Immediately load, read entire file, then execute `{nextStepFile}`.

**If tier is Deep:**

Continue to step 2.

### 2. Collection Inventory Pre-check (Deep Tier Only)

Before searching, check which QMD collections are available:

1. Read the sidecar `forge-tier.yaml` to get registered `qmd_collections` entries
2. Identify which collections contain enrichment context — collections with `type` equal to `"temporal"` (issues, PRs, changelogs) or `"docs"` (fetched external documentation). Do NOT include `"extraction"` or `"brief"` type collections.
3. **If no enrichment collections exist** (no `"temporal"` or `"docs"` type collections): report this and auto-proceed. Display:

"**Enrichment: no enrichment collections available.**
Only brief-type or extraction-type QMD collections found — no temporal context (issues, PRs, changelogs) or docs collections indexed. {IF extraction_mode is 'docs-only' AND T3 items exist in extraction_inventory: 'T3 documentation content is available in extraction inventory — enrichment via QMD is skipped but T3 content will be compiled.'} {ELSE: 'Enrichment skipped (expected for first-run skill creation). Enrichment becomes available when temporal or docs context is indexed into QMD collections.'}

Proceeding to compilation..."

Then immediately load, read entire file, then execute `{nextStepFile}`.

4. **If temporal collections exist:** Continue to step 3.

### 3. QMD Enrichment Searches (Deep Tier Only)

For each major exported function — limited to the **top-level public API surface** (typically 10-20 functions that will appear in the context-snippet), not all extracted exports — search the temporal QMD collections for context:

**Search query construction:**

For each function, derive the **module context** from the extraction inventory's source file path (e.g., `src/graph/neo4j/index.ts` → module context `graph neo4j`). This context improves search relevance by scoping results to the function's subsystem without adding extra queries.

**Primary searches (BM25 — always runs, no GPU/VRAM dependency):**

1. **Issues/PRs:** `qmd_bridge.search("{module_context} {function_name}")` — find related discussions scoped by module context
2. **Changelog entries:** `qmd_bridge.search("{function_name} changelog")` — find version history, breaking changes (kept generic — changelogs rarely use module paths)
3. **Migration notes:** `qmd_bridge.search("{function_name} migration deprecated breaking")` — find deprecation or migration context using exact keyword matching

**Supplemental search (best-effort — requires GPU/VRAM, may fail):**

4. **Semantic migration context:** `qmd_bridge.vector_search("{module_context} {function_name} migration deprecated")` — adds semantic matches (synonyms, paraphrases) that BM25 keyword search may miss. Merge results with search #3, deduplicating by document ID. If `vector_search` fails (VRAM, GPU driver, model loading), discard silently — the BM25 results from search #3 provide baseline coverage.

**Tool resolution for qmd_bridge:** Use QMD MCP tools — `mcp__plugin_qmd-plugin_qmd__search` for BM25 search, `mcp__plugin_qmd-plugin_qmd__vector_search` for semantic search (Claude Code). Cursor: qmd MCP server. CLI: `qmd search "{query}"` / `qmd vector_search "{query}"`. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

**For each QMD result:**

- Create a T2 annotation: `[QMD:{collection}:{doc}]`
- Classify temporal relevance:
  - **T2-past:** Historical context (why it was built, what it replaced)
  - **T2-future:** Forward-looking context (planned changes, deprecation warnings)

**Handling QMD failures:**

- If qmd_bridge is unavailable: skip all enrichment, note in context
- If individual search fails: skip that function's enrichment, continue with others
- If QMD returns no results for a function: no annotation added (absence is normal)

### 4. Annotate Extraction Inventory

Add enrichment annotations to the extraction inventory without modifying extraction data:

**Per-function enrichment (if found):**
- Related issues/PRs with summary
- Changelog history (version changes, breaking changes)
- Migration/deprecation context
- T2 provenance citation for each annotation

**Enrichment summary counts:**
- Functions enriched: {count} of {total}
- T2 annotations added: {count}
- T2-past annotations: {count}
- T2-future annotations: {count}

### 5. Report Enrichment (Deep Tier Only)

Display brief enrichment summary:

"**Enrichment complete.**

**Functions enriched:** {enriched_count} of {total_count}
**T2 annotations:** {t2_count} ({t2_past} historical, {t2_future} forward-looking)

Proceeding to compilation..."

### 6. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After enrichment is complete (or skipped for non-Deep tiers), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Quick/Forge/Forge+ tiers skip directly to next step with no output
- Deep tier displays brief enrichment summary then auto-proceeds
- QMD failures do not halt — degrade and proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN enrichment is complete (Deep tier) or the step is skipped (Quick/Forge/Forge+) will you proceed to load `{nextStepFile}` for SKILL.md compilation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Quick/Forge/Forge+ tiers: skipped silently with no output, auto-proceeded
- Deep tier: collection inventory checked before searching
- Deep tier: no temporal collections → reported and auto-proceeded (not silently skipped)
- Deep tier: temporal collections exist → QMD searches performed per public API function (10-20, not all exports) with module context derived from extraction inventory source paths
- T2 annotations added with proper provenance citations
- Extraction data unmodified — enrichment is additive only
- QMD failures handled gracefully (skip and continue)
- Auto-proceeded to step-05

### ❌ SYSTEM FAILURE:

- Halting on QMD unavailability or search failures
- Modifying T1 extraction results with QMD data
- Displaying skip messages for Quick/Forge/Forge+ tiers (should be silent)
- Pre-emptively skipping all searches without checking the collection inventory
- Searching all 800+ exports instead of scoping to public API surface (10-20)
- Using bare function names without module context when source path is available in extraction inventory
- Beginning compilation or SKILL.md assembly in this step
- Not labeling QMD annotations as T2 confidence

**Master Rule:** Enrichment is additive and optional. QMD adds temporal depth but never replaces structural extraction. Failures degrade gracefully.
