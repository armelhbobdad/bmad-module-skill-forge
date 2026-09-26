---
nextStepFile: '../extract.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2b: CCC Semantic Discovery

## STEP GOAL:

If tier is Forge+ or Deep AND ccc is available, perform a semantic discovery pass over the source code to identify the most relevant files for the skill being created. Store ranked discovery results in context to pre-rank the file extraction queue in step 3.

For Quick and Forge tiers, or when ccc is unavailable, skip silently and proceed.

## Rules

- Focus only on running ccc semantic search and storing results — do not extract exports
- Do not block the workflow if ccc fails
- Quick and Forge tiers: skip this step entirely and silently

## MANDATORY SEQUENCE

### 1. Check Tier Eligibility

**If tier is Quick or Forge:**

Set `{ccc_discovery: []}` in context. Auto-proceed silently. Display no message. Immediately load, read entire file, then execute `{nextStepFile}`.

**If tier is Forge+ or Deep:**

Check `tools.ccc` from forge-tier.yaml. If `tools.ccc` is false, set `{ccc_discovery: []}` in context and auto-proceed to section 5.

If `tools.ccc` is true, check the remote source guard **before** proceeding to section 2:

**Remote source guard:** If `source_root` is a remote URL (GitHub repository — workspace clone or ephemeral clone happens in step 3), CCC cannot operate yet. Set `{ccc_discovery: []}` and display: "CCC discovery deferred — remote source will be indexed after clone in step 3." Auto-proceed to section 5 (step completion). Step-03 will detect the deferred scenario and run CCC discovery on the resolved clone (workspace or ephemeral) before AST extraction begins.

If `source_root` is a local path, continue to section 2.

### 2. Check CCC Index State

Read `ccc_index` from forge-tier.yaml and branch on `ccc_index.status`:

- `"fresh"`, `"created"` or `"skipped"`: continue to section 3. Section 4 searches with `--refresh`, which brings the index up to date first, so its age never needs checking here. `"skipped"` belongs here because setup's `--ccc-skip-index` lane still writes `settings.yml` with the SKF exclusions and only defers the indexing cost: the first refresh search builds the index safely, and takes longer.
- `"none"` or `"failed"`: attempt lazy indexing via `ccc_bridge.ensure_index(source_root)`. If indexing succeeds, continue to section 3. If indexing fails, set `{ccc_discovery: []}` and auto-proceed to section 5.
- Any other status, for example a `"stale"` an older SKF recorded: treat it like `"fresh"`.

**Tool resolution for ccc_bridge.ensure_index:** Use `/ccc` skill indexing (Claude Code), ccc MCP server (Cursor), or `cd {source_root} && ccc init` + `ccc index` (CLI). Note: `ccc init` takes no positional arguments — it initializes the index for the current working directory. See `knowledge/tool-resolution.md`. Exception: when `{source_root}` is `{project-root}` and `{project-root}/.cocoindex_code/settings.yml` does not exist, do not run `ccc init` or `ccc index` — `/skf-setup` initializes the project index with the SKF exclusions. Set `{ccc_discovery: []}`, note that re-running `/skf-setup` enables semantic discovery, and auto-proceed to section 5.

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

**Setup's index (every section 2 status except `"none"` and `"failed"`):** search with `cd "{source_root}" && ccc search --refresh --limit 20 "{query}"` (the `/ccc` skill or the CLI), with an extended timeout, because the refresh pass runs before the search. The ccc MCP search tool refreshes by default: leave its `refresh_index` set to true. No status says that the index still matches the source (after `"skipped"` there may be no index yet), and a plain `ccc search` does not re-index a project the daemon already has loaded. The pass is incremental: it re-reads `settings.yml`, indexes new and changed files, and drops deleted files and the ones a pattern now leaves out, so on an unchanged project it returns almost as fast as a plain search. If the refresh search fails or times out, run the plain `cd "{source_root}" && ccc search --limit 20 "{query}"` once, with the same timeout, before treating the search as failed: the daemon finishes the pass on its own, and the plain search reads the index as it stands. After lazy indexing in section 2, the plain search is enough.

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

Do not halt. This is not an error.

**If search returns empty results:**

Set `{ccc_discovery: []}` in context.

No message needed — empty results are normal for small or highly focused libraries.

### 5. Auto-Proceed

No user interaction. Load `{nextStepFile}`, read it fully, then execute it. CCC failures degrade and proceed — they never halt.

