---
nextStepFile: '../step-03-extract.md'
---

# Step 2b: CCC Semantic Discovery

## STEP GOAL:

If tier is Forge+ or Deep AND ccc is available, perform a semantic discovery pass over the source code to identify the most relevant files for the skill being created. Store ranked discovery results in context to pre-rank the file extraction queue in step-03.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## Rules

- Focus only on running ccc semantic search and storing results — do not extract exports
- Do not block the workflow if ccc fails
- Quick and Forge tiers: skip this step entirely and silently

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tier Eligibility

**If tier is Quick or Forge:**

Set `{ccc_discovery: []}` in context. Auto-proceed silently. Display no message. Immediately load, read entire file, then execute `{nextStepFile}`.

**If tier is Forge+ or Deep:**

Check `tools.ccc` from forge-tier.yaml. If `tools.ccc` is false, set `{ccc_discovery: []}` in context and auto-proceed to section 5.

If `tools.ccc` is true, check the remote source guard **before** proceeding to section 2:

**Remote source guard:** If `source_root` is a remote URL (GitHub repository — workspace clone or ephemeral clone happens in step-03), CCC cannot operate yet. Set `{ccc_discovery: []}` and display: "CCC discovery deferred — remote source will be indexed after clone in step-03." Auto-proceed to section 5 (step completion). Step-03 will detect the deferred scenario and run CCC discovery on the resolved clone (workspace or ephemeral) before AST extraction begins.

If `source_root` is a local path, continue to section 2.

### 2. Check CCC Index State

Read `ccc_index` from forge-tier.yaml:

- If `ccc_index.status` is `"fresh"` or `"created"`: continue to section 3.
- If `ccc_index.status` is `"stale"`: display brief note — "CCC index is stale — discovery results may miss recent changes." Continue to section 3.
- If `ccc_index.status` is `"none"` or `"failed"`: attempt lazy indexing via `ccc_bridge.ensure_index(source_root)`. If indexing succeeds, continue to section 3. If indexing fails, set `{ccc_discovery: []}` and auto-proceed to section 5.

**Tool resolution for ccc_bridge.ensure_index:** Use `/ccc` skill indexing (Claude Code), ccc MCP server (Cursor), or `cd {source_root} && ccc init` + `ccc index` (CLI). Note: `ccc init` takes no positional arguments — it initializes the index for the current working directory. See `knowledge/tool-resolution.md`.

### 3. Construct Semantic Query

Build the discovery query from the brief data:

**Primary query:** `"{brief.name} {brief.scope}"`

Where:
- `brief.name` is the skill name from the brief
- `brief.scope` is the scope field (e.g., "Full library", "Public API", or specific module names)

**Query length cap:** Truncate to 80 characters if longer — ccc semantic search is sensitive to overly long queries. When truncating, keep the full skill name and trim `brief.scope` from the end. If `brief.scope` is very short (< 10 chars), append terms from `brief.description` to fill the remaining space.

### 4. Execute CCC Semantic Search

Run `ccc_bridge.search(query, source_root, top_k=20)`:

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {source_root} && ccc search --limit 20 "{query}"` (CLI). Note: `ccc search` operates on the index in the current working directory — there is no flag to specify a project directory. See `knowledge/tool-resolution.md`.

**If search succeeds:**

Store results as `{ccc_discovery: [{file, score, snippet}]}` in context.

Display brief discovery summary:

"**CCC semantic discovery: {N} relevant regions identified across {M} unique files.**"

Where:
- `{N}` is the total result count
- `{M}` is the count of unique file paths in results

**If search fails (any error):**

Set `{ccc_discovery: []}` in context.

Display: "CCC discovery unavailable — proceeding with standard extraction."

Do NOT halt. This is not an error.

**If search returns empty results:**

Set `{ccc_discovery: []}` in context.

No message needed — empty results are normal for small or highly focused libraries.

### 5. Auto-Proceed

Immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Quick/Forge tiers skip directly with no output
- Forge+/Deep with ccc displays brief discovery summary then auto-proceeds
- CCC failures do not halt — degrade and proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN discovery is complete (Forge+/Deep with ccc) or the step is skipped (Quick/Forge or ccc unavailable) will you proceed to load `{nextStepFile}` for AST extraction.

