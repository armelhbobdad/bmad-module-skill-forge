# CCC Bridge

## Principle

`ccc_bridge.*` references in workflow steps are **conceptual interfaces**, not callable functions. They describe a semantic code discovery operation to perform. Use the `ccc` MCP server tools (when available) or `ccc` CLI commands to execute these operations. See the TOOL/SUBPROCESS FALLBACK rule — if ccc is unavailable, the calling step falls back to direct ast-grep or source reading without ccc pre-discovery. For the complete bridge-to-tool resolution table covering all IDE environments, see [tool-resolution.md](tool-resolution.md).

## Rationale

Without ccc pre-discovery, extraction steps scan all source files uniformly — processing them in directory order or entry-point-first order. On large codebases (500+ files), this means AST extraction in CLI streaming mode uses `head -N` cutoffs that may miss relevant exports in files that appear late in the scan. Integration detection in Stack Skill relies on grep-based co-import counting, which misses semantic relationships between libraries that don't appear in the same file.

With ccc pre-discovery:
- Extraction steps receive a relevance-ranked file queue — the most semantically important files are processed first, before any streaming cutoff
- Integration detection gains semantic augmentation — pairs below the 2-file co-import threshold can be evaluated via natural language queries
- Audit workflows can detect renamed/moved exports via semantic search before classifying them as deleted

The key architectural constraint: ccc discovers, ast-grep verifies. Discovery method is orthogonal to confidence tier. This keeps the 4-tier confidence system (T1/T1-low/T2/T3) clean and avoids tier proliferation.

## When ccc Is Used

ccc is a **discovery layer only**. It answers "where should I look?" — it does not produce citations or structural claims. Every path or symbol returned by ccc_bridge must be verified by `ast_bridge` (T1) or source reading (T1-low) before it enters the extraction inventory. ccc results never appear in provenance citations.

ccc is **required** at the Forge+ tier (it defines Forge+) and **optionally available** at the Deep tier as an enhancement (when `tools.ccc: true` in forge-tier.yaml).

## Availability

ccc_bridge operations are available when:
- `tools.ccc: true` in forge-tier.yaml (verified by `ccc --help` + `ccc doctor` in setup)
- `ccc_index.status` is `"fresh"` or `"stale"` in forge-tier.yaml (an index exists for the project)

When either condition is false, calling steps skip ccc discovery silently and proceed with direct ast-grep or source reading. This is standard Forge tier behavior — not a degradation.

## Operations

### `ccc_bridge.search(query, path?, top_k?)`

**Resolves to:** `cd {path} && ccc search --limit {top_k} "{query}"` (CLI) or the `ccc` MCP search tool (preferred). Note: `ccc search` operates on the index in the current working directory — there is no flag to specify a project directory. The `--path` flag is a file path glob filter within the index, not a project selector.

Returns: list of `{file, score, snippet}` entries ranked by semantic relevance to the query. These are **candidates** for ast-grep extraction — not verified exports.

**Usage context:** Called before ast-grep in Forge+ and Deep tier extraction steps to discover semantically relevant source regions. Results pre-rank the file extraction queue so ast-grep processes the most relevant files first.

### `ccc_bridge.ensure_index(path)`

**Resolves to:** Check `ccc_index.status` in forge-tier.yaml. If `"none"` or the indexed_path does not match, run `cd {path} && ccc init` then `ccc index` and update forge-tier.yaml. Note: `ccc init` takes no positional arguments — it initializes the index for the current working directory.

**Usage context:** Called by setup step-01b to ensure the project root is indexed. Called lazily by extraction steps when `ccc_index.status` is `"none"` but ccc is available.

### `ccc_bridge.status()`

**Resolves to:** Two-step verification:
1. `ccc --help` — confirms binary exists (exit 0)
2. `ccc doctor` — confirms daemon is running, extracts version string, validates embedding model

**Usage context:** Called exclusively by setup step-01 during tool detection. Downstream workflows read the result from forge-tier.yaml — they do not re-verify.

## Confidence

ccc discovery does not produce a confidence tier. The provenance chain is:

1. ccc discovers candidate files (internal hint — not cited)
2. ast-grep verifies exports in those files → **T1** citation `[AST:file:Lnn]`
3. Or source reading verifies → **T1-low** citation `[SRC:file:Lnn]`

The ccc search is invisible in the output artifact. A Forge+ skill's citations are indistinguishable from a Forge skill's citations — the difference is in extraction coverage, not citation format.

## Indexing Lifecycle

### When Indexing Happens

1. **setup step-01b:** Indexes the project root when setup runs. This is the primary indexing point.
2. **Workflow discovery steps:** If `ccc_index.status` is `"stale"` or `"none"`, discovery steps trigger a re-index and warn the user. They do not block.
3. **ccc daemon:** Incremental indexing means re-indexing unchanged files is a near-no-op.

### Freshness

- Staleness threshold: 24 hours (configurable via `ccc_index.staleness_threshold_hours` in forge-tier.yaml)
- A stale index still produces useful results — the workflow proceeds with the stale index and notes the staleness
- setup is the designated refresh authority

### Exclusion Patterns

CCC stores its configuration at `{project-root}/.cocoindex_code/settings.yml`. This file contains `exclude_patterns` and `include_patterns` arrays in glob format. `ccc init` creates the file with sensible defaults (excludes `node_modules`, `__pycache__`, hidden dirs, etc.).

**SKF infrastructure exclusions:** setup step-01b appends SKF-specific exclusion patterns after `ccc init` creates the default config. These patterns prevent indexing of framework and output directories that have zero value for source extraction:

| Pattern | Purpose |
|---------|---------|
| `**/_bmad` | SKF framework module (workflow instructions, agents, knowledge) |
| `**/_bmad-output` | Build output artifacts (TODO files, reports) |
| `**/.claude` | Claude Code configuration |
| `**/_skf-learn` | SKF learning materials |
| `**/{skills_output_folder}` | Generated skill files (from manifest, default: `skills`) |
| `**/{forge_data_folder}` | Compilation workspace (from manifest, default: `forge-data`) |

The `skills_output_folder` and `forge_data_folder` values are resolved from the workflow activation context (sourced from `_bmad/skf/config.yaml`), falling back to the defaults `skills` and `forge-data`. Patterns are appended only if not already present — user customizations to `settings.yml` are preserved.

The configured exclusion patterns are stored in `ccc_index.exclude_patterns` in forge-tier.yaml for reference.

### Deferred Discovery (Remote Sources)

For remote repository sources (GitHub URLs), CCC cannot operate during step-02b because no local code exists yet. The workspace clone or ephemeral clone happens in step-03. To provide CCC pre-ranking for remote sources:

1. **step-02b:** Detects remote source, sets `{ccc_discovery: []}`, displays deferred message
2. **step-03:** After source resolution succeeds, detects the deferred scenario (`tools.ccc == true AND {ccc_discovery} is empty AND remote_clone_path is set AND tier is Forge+/Deep`)
3. **step-03 (workspace fast path):** If `{remote_clone_path}/.cocoindex_code/` already exists (persisted workspace index), skips init/index and uses `ccc search --refresh` — CCC daemon re-indexes only if files changed since last index. This is near-instant for unchanged repos.
4. **step-03 (first-time path):** If no existing CCC index, runs `cd {remote_clone_path} && ccc init`, applies standard build/dependency exclusions (node_modules, dist, .git, vendor, etc.) to `settings.yml`, then runs `ccc index`. Brief-specific `include_patterns`/`exclude_patterns` are NOT written to `settings.yml` — the CCC index is general-purpose. Filtering happens at search result time.
5. **step-03:** Executes CCC search and populates `{ccc_discovery}` before AST extraction begins

For workspace repos, the CCC index persists at `{workspace_repo_path}/.cocoindex_code/` and is reused across forges, projects, and sessions. For ephemeral fallback clones, the index is not registered in `ccc_index_registry` — the clone is deleted after extraction.

### Relationship to QMD Registry

ccc_index and qmd_collections are **orthogonal**:
- `ccc_index` in forge-tier.yaml tracks the persistent source code index (one per project)
- `qmd_collections[]` in forge-tier.yaml tracks per-skill workflow artifact collections
- ccc indexes source code for semantic search; QMD indexes curated artifacts for temporal/knowledge search
- The janitor role for QMD (setup step-03) operates independently of ccc_index

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
- Indexing without configuring exclusions — for project root indexes, apply SKF exclusions (framework/output directories); for workspace repo indexes, apply standard build artifact exclusions (node_modules, dist, .git, etc.)
- Writing brief-specific `exclude_patterns` to a workspace repo's `settings.yml` — workspace indexes are general-purpose and serve multiple briefs. Apply brief patterns at search result time, not index time. (Exception: ephemeral fallback clones are single-use, so brief exclusions may be applied to their `settings.yml` to reduce indexing time.)
- Skipping CCC discovery for remote sources without deferring to step-03 — remote repos deserve the same pre-ranking as local sources

## Related Fragments

- [tool-resolution.md](tool-resolution.md) — canonical bridge-to-tool and subprocess-to-tool mapping per IDE
- [progressive-capability.md](progressive-capability.md) — Forge+ tier definition and positive framing
- [confidence-tiers.md](confidence-tiers.md) — why ccc does not create a new confidence tier
- [qmd-registry.md](qmd-registry.md) — the parallel but separate registry for QMD collections

_Source: designed as part of the Forge+ tier integration for cocoindex-code semantic code search_
