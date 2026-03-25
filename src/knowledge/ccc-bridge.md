# CCC Bridge

## Principle

`ccc_bridge.*` references in workflow steps are **conceptual interfaces**, not callable functions. They describe a semantic code discovery operation to perform. Use the `ccc` MCP server tools (when available) or `ccc` CLI commands to execute these operations. See the TOOL/SUBPROCESS FALLBACK rule — if ccc is unavailable, the calling step falls back to direct ast-grep or source reading without ccc pre-discovery.

## Rationale

Without ccc pre-discovery, extraction steps scan all source files uniformly — processing them in directory order or entry-point-first order. On large codebases (500+ files), this means AST extraction in CLI streaming mode uses `head -N` cutoffs that may miss relevant exports in files that appear late in the scan. Integration detection in Stack Skill relies on grep-based co-import counting, which misses semantic relationships between libraries that don't appear in the same file.

With ccc pre-discovery:
- Extraction steps receive a relevance-ranked file queue — the most semantically important files are processed first, before any streaming cutoff
- Integration detection gains semantic augmentation — pairs below the 2-file co-import threshold can be evaluated via natural language queries
- Audit workflows can detect renamed/moved exports via semantic search before classifying them as deleted

The key architectural constraint: ccc discovers, ast-grep verifies. Discovery method is orthogonal to confidence tier. This keeps the 4-tier confidence system (T1/T1-low/T2/T3) clean and avoids tier proliferation.

## When ccc Is Used

ccc is a **discovery layer only**. It answers "where should I look?" — it does not produce citations or structural claims. Every path or symbol returned by ccc_bridge must be verified by `ast_bridge` (T1) or source reading (T1-low) before it enters the extraction inventory. ccc results never appear in provenance citations.

ccc is available at **Forge+** and **Deep** tiers (when `tools.ccc: true` in forge-tier.yaml).

## Availability

ccc_bridge operations are available when:
- `tools.ccc: true` in forge-tier.yaml (verified by `ccc --help` + `ccc doctor` in setup-forge)
- `ccc_index.status` is `"fresh"` or `"stale"` in forge-tier.yaml (an index exists for the project)

When either condition is false, calling steps skip ccc discovery silently and proceed with direct ast-grep or source reading. This is standard Forge tier behavior — not a degradation.

## Operations

### `ccc_bridge.search(query, path?, top_k?)`

**Resolves to:** `ccc search "{query}" --path {path} --top {top_k}` (CLI) or the `ccc` MCP search tool (preferred)

Returns: list of `{file, score, snippet}` entries ranked by semantic relevance to the query. These are **candidates** for ast-grep extraction — not verified exports.

**Usage context:** Called before ast-grep in Forge+ and Deep tier extraction steps to discover semantically relevant source regions. Results pre-rank the file extraction queue so ast-grep processes the most relevant files first.

### `ccc_bridge.ensure_index(path)`

**Resolves to:** Check `ccc_index.status` in forge-tier.yaml. If `"none"` or the indexed_path does not match, run `ccc init {path}` then `ccc index` and update forge-tier.yaml.

**Usage context:** Called by setup-forge step-01b to ensure the project root is indexed. Called lazily by extraction steps when `ccc_index.status` is `"none"` but ccc is available.

### `ccc_bridge.status()`

**Resolves to:** Two-step verification:
1. `ccc --help` — confirms binary exists (exit 0)
2. `ccc doctor` — confirms daemon is running, extracts version string, validates embedding model

**Usage context:** Called exclusively by setup-forge step-01 during tool detection. Downstream workflows read the result from forge-tier.yaml — they do not re-verify.

## Confidence

ccc discovery does not produce a confidence tier. The provenance chain is:

1. ccc discovers candidate files (internal hint — not cited)
2. ast-grep verifies exports in those files → **T1** citation `[AST:file:Lnn]`
3. Or source reading verifies → **T1-low** citation `[SRC:file:Lnn]`

The ccc search is invisible in the output artifact. A Forge+ skill's citations are indistinguishable from a Forge skill's citations — the difference is in extraction coverage, not citation format.

## Indexing Lifecycle

### When Indexing Happens

1. **setup-forge step-01b:** Indexes the project root when setup-forge runs. This is the primary indexing point.
2. **Workflow discovery steps:** If `ccc_index.status` is `"stale"` or `"none"`, discovery steps trigger a re-index and warn the user. They do not block.
3. **ccc daemon:** Incremental indexing means re-indexing unchanged files is a near-no-op.

### Freshness

- Staleness threshold: 24 hours (configurable via `ccc_index.staleness_threshold_hours` in forge-tier.yaml)
- A stale index still produces useful results — the workflow proceeds with the stale index and notes the staleness
- setup-forge is the designated refresh authority

### Relationship to QMD Registry

ccc_index and qmd_collections are **orthogonal**:
- `ccc_index` in forge-tier.yaml tracks the persistent source code index (one per project)
- `qmd_collections[]` in forge-tier.yaml tracks per-skill workflow artifact collections
- ccc indexes source code for semantic search; QMD indexes curated artifacts for temporal/knowledge search
- The janitor role for QMD (setup-forge step-03) operates independently of ccc_index

## Query Volume Bounds

To prevent excessive daemon calls, workflow steps cap ccc queries:
- **create-skill extraction:** max 2 queries per skill (discovery + optional scope refinement)
- **analyze-source mapping:** max 1 query per qualifying unit
- **create-stack-skill integration detection:** max 1 query per library pair
- **audit-skill re-index:** max 1 query per export missing from its recorded location

## Anti-Patterns

- Using ccc_bridge results as citations without ast-grep verification — ccc output is never a provenance citation
- Blocking a workflow because ccc is unavailable — ccc is always optional
- Running ccc_bridge.ensure_index() without checking ccc_index.status first — unnecessary re-indexing
- Passing ccc results directly to the extraction inventory — they are candidates, not extractions
- Listing ccc as "unavailable" in reports for Quick/Forge tiers — ccc is a Forge+ capability, not something Quick/Forge tiers are missing

## Related Fragments

- [progressive-capability.md](progressive-capability.md) — Forge+ tier definition and positive framing
- [confidence-tiers.md](confidence-tiers.md) — why ccc does not create a new confidence tier
- [qmd-registry.md](qmd-registry.md) — the parallel but separate registry for QMD collections

_Source: designed as part of the Forge+ tier integration for cocoindex-code semantic code search_
