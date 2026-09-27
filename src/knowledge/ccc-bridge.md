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

ccc_bridge operations are available when `tools.ccc: true` in forge-tier.yaml (verified by `ccc --help` + `ccc doctor` in setup). When it is false, calling steps skip ccc discovery silently and proceed with direct ast-grep or source reading. This is standard Forge tier behavior — not a degradation.

With ccc available, `ccc_index.status` decides how a step reaches the project index:
- `"fresh"`, `"created"`, `"skipped"`, or a status the step does not know (such as a `"stale"` an older SKF recorded): the index is usable, and the discovery steps search it with `ccc search --refresh`. After `"skipped"` there may be no index yet, but setup's `--ccc-skip-index` lane still wrote `settings.yml` with the SKF exclusions, so the first refresh search builds the index safely.
- `"none"` or `"failed"`: setup built no index. Create-skill discovery indexes lazily with `ensure_index`; a step without a lazy path skips ccc silently.

## Operations

### `ccc_bridge.search(query, path?, top_k?)`

**Resolves to:** `cd {path} && ccc search --limit {top_k} "{query}"` (CLI) or the `ccc` MCP search tool (preferred). Note: `ccc search` operates on the index in the current working directory — there is no flag to specify a project directory. The `--path` flag is a file path glob filter within the index, not a project selector.

Returns: list of `{file, score, snippet}` entries ranked by semantic relevance to the query. These are **candidates** for ast-grep extraction — not verified exports.

**Usage context:** Called before ast-grep in Forge+ and Deep tier extraction steps to discover semantically relevant source regions. Results pre-rank the file extraction queue so ast-grep processes the most relevant files first.

### `ccc_bridge.ensure_index(path)`

**Resolves to:** Check `ccc_index.status` in forge-tier.yaml. If `"none"` or the indexed_path does not match, run `cd {path} && ccc init` then `ccc index` and update forge-tier.yaml. Note: `ccc init` takes no positional arguments — it initializes the index for the current working directory. Exception: when `{path}` is `{project-root}` and `{project-root}/.cocoindex_code/settings.yml` does not exist, do not run `ccc init` or `ccc index` — setup's `skf-merge-ccc-exclusions.py` owns initializing the project root with the SKF exclusions, and in a project nested inside another git checkout `ccc index` would index the enclosing repository instead. Treat the index as unavailable and suggest re-running `/skf-setup`.

When `ccc init` exits non-zero with `A parent directory has a project marker`, run `ccc init -f` in `{path}`. Run `ccc index` only once `{path}/.cocoindex_code/settings.yml` exists: without it, `ccc index` initializes the enclosing git checkout with ccc's defaults and none of the SKF exclusions. Afterwards `skf-ccc-git-hygiene.py nested` keeps a project in a subfolder out of git (see Exclusion Patterns).

**Usage context:** Called lazily by extraction steps when `ccc_index.status` is `"none"` or `"failed"` but ccc is available. Setup step 1b does not call it: its helper runs `ccc init` and decides whether to index.

### `ccc_bridge.status()`

**Resolves to:** Two-step verification:
1. `ccc --help` — confirms binary exists (exit 0) AND output contains the `CocoIndex Code` identity marker (rejects unrelated `ccc`-named binaries shadowing PATH)
2. `ccc doctor` — confirms daemon is running, extracts version string, validates embedding model

**Usage context:** Called exclusively by setup step 1 during tool detection. Downstream workflows read the result from forge-tier.yaml — they do not re-verify.

## Confidence

ccc discovery does not produce a confidence tier. The provenance chain is:

1. ccc discovers candidate files (internal hint — not cited)
2. ast-grep verifies exports in those files → **T1** citation `[AST:file:Lnn]`
3. Or source reading verifies → **T1-low** citation `[SRC:file:Lnn]`

The ccc search is invisible in the output artifact. A Forge+ skill's citations are indistinguishable from a Forge skill's citations — the difference is in extraction coverage, not citation format.

## Indexing Lifecycle

### When Indexing Happens

1. **setup step 1b:** Indexes the project root when setup runs. This is the primary indexing point.
2. **Workflow discovery steps:** Create-skill discovery and create-stack-skill integration detection search setup's index with `ccc search --refresh`, which first indexes what changed since (after `--ccc-skip-index`, the whole project). When `ccc_index.status` is `"none"` or `"failed"`, create-skill discovery indexes lazily and integration detection skips ccc. Discovery never blocks.
3. **ccc daemon:** Incremental indexing means re-indexing unchanged files is a near-no-op.
4. **create-skill step 7:** Indexes the folder the skill was extracted from and records it in `ccc_index_registry`: the workspace clone, or a local source folder, which becomes a ccc project of its own (`ccc init -f`) when it sits inside another git checkout or ccc project.

### Freshness

- setup is the designated authority for the `ccc_index` status in forge-tier.yaml. It records `"fresh"` (a re-run kept the index), `"created"`, `"failed"`, `"none"` or `"skipped"` (`--ccc-skip-index`); no status records staleness
- Staleness threshold: 24 hours (configurable via `ccc_index.staleness_threshold_hours` in forge-tier.yaml). A setup re-run compares `last_indexed` against it to decide whether to keep the index or index again
- A workflow step never computes staleness. Create-skill discovery and create-stack-skill integration detection search setup's index with `ccc search --refresh`, one incremental pass that indexes what changed since and costs almost nothing when nothing did; the refresh does not change the recorded status. Other steps search the index as it stands

### Exclusion Patterns

CCC stores its configuration at `{project-root}/.cocoindex_code/settings.yml`. `ccc init` creates it with `exclude_patterns` and `include_patterns` holding ccc's defaults (hidden directories, `node_modules`, `__pycache__`, its own `.cocoindex_code`, and more) and, at the top of a git checkout, adds `/.cocoindex_code/` to `.gitignore`. An `exclude_patterns` list in the file replaces ccc's default exclusions, so SKF only ever extends a list that `ccc init` wrote.

ccc adds that line only when it creates a project at the top of a git checkout whose `.git` is a folder, and the line matches only that top-level folder; a `ccc index` that finds no `settings.yml` initializes the project the same way. A ccc project in a subfolder of a checkout (the `ccc init -f` case), in a linked worktree or in a submodule, whose `.git` is a file, therefore gets no entry, and git lists its index database as untracked. SKF never edits a project's own `.gitignore`. After create-skill runs ccc in a local source folder other than the project root, `skf-ccc-git-hygiene.py nested` runs `git check-ignore -q --no-index` there, once each for `settings.yml`, `target_sqlite.db` and `cocoindex.db/mdb/data.mdb` under `.cocoindex_code/`, and when any of them is not ignored writes `.cocoindex_code/.gitignore` holding `*` so the folder ignores itself. In an SKF workspace clone, `skf-ccc-git-hygiene.py workspace` instead undoes ccc's `.gitignore` edit and lists `.cocoindex_code/` and `/.skf-workspace.lock` in the clone's `.git/info/exclude` (see Deferred Discovery). ccc reads only `.gitignore` files and excludes `**/.cocoindex_code` by default, so neither changes what it indexes.

ccc reads `settings.yml` again on every index run. After an edit to `exclude_patterns` or `include_patterns`, a plain `ccc index` (or `ccc search --refresh`) drops the files a pattern now leaves out and indexes the ones it brings in, with the daemon already running; the index never needs deleting and the daemon never needs restarting. A plain `ccc search` does not re-index a project the daemon already has loaded, so run `ccc index` before a search that must reflect an edit.

**SKF infrastructure exclusions:** setup step 1b runs `skf-merge-ccc-exclusions.py`, which runs `ccc init` when the file is missing, rebuilds a file that lacks the ccc defaults (keeping user entries), and keeps these patterns in it:

| Pattern | Purpose |
|---------|---------|
| `**/_bmad` | SKF framework module (workflow instructions, agents, knowledge) |
| `**/_bmad-output` | Build output artifacts (TODO files, reports) |
| `**/.claude` | Claude Code configuration |
| `**/_skf-learn` | SKF learning materials |
| `{skills_output_folder}` | Generated skill files (default `skills`), anchored to the project root — a nested folder with the same name stays indexed. In a folder that also holds content SKF did not generate, one `{skills_output_folder}/<entry>` pattern per SKF entry instead |
| `{forge_data_folder}` | Compilation workspace (default `forge-data`), anchored to the project root. Per SKF entry in a folder that also holds other content, as above |

The folder values come from `_bmad/skf/config.yaml` and are used relative to the project root. Setup lists each folder with git, honouring only `.gitignore` files as ccc does. A skill folder in `{skills_output_folder}` counts as SKF output by the rule the workflows use before they write into, move or delete a skill (see `knowledge/version-paths.md` Ownership): its `metadata.json`, or a version's, carries an SKF marker, or it is `_batch`. The versioned layout, an `active` link, a manifest key or a result file do not count on their own, so a module's skills that an earlier SKF moved into that layout stay indexed. A folder in `{forge_data_folder}` counts as SKF output by the rule drop and rename use for a skill's forge folder: its name contains `.skf-`, it is `_campaign` or `improvement-queue`, or it holds a brief, `.brief-draft.json` or `*-result*.json` file directly, or a provenance map, evidence report, extraction rules or `*-result*.json` file in a folder directly inside it. Both rules read the folder on disk, so a file `.gitignore` hides still counts, and a linked folder never does. Setup handles each folder in one of four ways:

- **Only SKF output** (neutral files such as `.gitkeep` or a README do not count, and loose files directly in the folder beside SKF output are excluded with it): the bare folder pattern.
- **SKF output next to content SKF did not generate**, for example skills installed from elsewhere: one pattern per SKF entry, so the other content stays indexed. The forms are `{folder}/<entry>` for each SKF skill group or file, plus `{folder}/_batch`, `{folder}/.export-manifest.json`, `{folder}/export-skill-result*.json` and `{folder}/drop-skill-result*.json` whether or not they exist yet. The forge folder gets `{folder}/_campaign`, `{folder}/improvement-queue` and one `{folder}/<report prefix>*` per SKF report instead. Glob characters in an entry name are written as character classes, so `[x]` becomes `[[]x[]]`. A skill created there after setup stays indexed, twice through its version folder and its `active` link, until setup runs again. Setup warns and names the other entries.
- **No SKF output, only other content**, for example a module whose own source lives under `skills/`: setup leaves the folder out and warns, naming the setting to change.
- **Already in `exclude_patterns`**, added by the user: once a setup run with ccc has saved SKF's record (below), setup leaves it alone and adds no pattern for it. Without that record, setup treats a folder of only SKF output as its own, and keeps a folder that also holds other content with a one-time warning.

SKF never writes a `!` negation. ccc applies a negation against every exclude pattern, its own defaults included, so it would re-include `node_modules`, hidden folders and the user's own excludes inside the other content, and a `!{folder}/…` entry cancels a bare `{folder}` pattern entirely.

`ccc_index.exclude_patterns` in forge-tier.yaml records the patterns SKF owns, per-entry patterns included. Each setup run removes a recorded pattern the current config no longer produces (for example after `skills_output_folder` changes, after a skill in a shared folder is dropped or renamed, or when a folder starts or stops holding other content), never removes entries it did not add, and keeps the record unchanged on a run without ccc. Ownership goes by the entry's text, so an entry identical to one SKF manages counts as SKF's: a user's copy of a bare folder pattern SKF already writes goes when SKF removes that pattern, and an entry present before a run with ccc first saved the record (an earlier run without ccc leaves it empty, which setup does not trust) is adopted when the folder holds only SKF output. To exclude a folder SKF leaves indexed, the user adds the entry after setup has run with ccc. Once that record exists, a folder value the user lists in `exclude_patterns` that the record does not hold stays the user's: setup never adopts it into the record and never removes it. The one exception is a record that still names per-entry patterns for that folder when none of them is left in `exclude_patterns`: a setup run swapped them for the bare pattern and stopped before it saved its record, so the bare pattern is SKF's and setup checks the folder again.

### Deferred Discovery (Remote Sources)

For remote repository sources (GitHub URLs), CCC cannot operate during step 2b because no local code exists yet. The workspace clone or ephemeral clone happens in step 3. To provide CCC pre-ranking for remote sources:

1. **step 2b:** Detects remote source, sets `{ccc_discovery: []}`, displays deferred message
2. **step 3:** After source resolution succeeds, detects the deferred scenario (`tools.ccc == true AND {ccc_discovery} is empty AND remote_clone_path is set AND tier is Forge+/Deep`)
3. **step 3 (workspace reuse):** If `{remote_clone_path}/.cocoindex_code/settings.yml` already exists, skips `ccc init`, appends any missing standard exclusions, and runs a plain `ccc index`. The pass is incremental, so an unchanged repository costs almost nothing, and an edited exclude or include pattern takes effect in the same pass.
4. **step 3 (first-time path):** If no existing CCC index, runs `cd {remote_clone_path} && ccc init`, applies standard build/dependency exclusions (node_modules, dist, .git, vendor, etc.) to `settings.yml`, then runs `ccc index`. Brief-specific `include_patterns`/`exclude_patterns` are NOT written to `settings.yml` — the CCC index is general-purpose. Filtering happens at search result time.
5. **step 3:** Executes CCC search and populates `{ccc_discovery}` before AST extraction begins
6. **step 3 (leave the workspace clone clean):** The first `ccc init` in a workspace clone, or a `ccc index` that initializes it, appends `# CocoIndex Code (ccc)` and `/.cocoindex_code/` to the clone's tracked `.gitignore`, a local change that makes git refuse a later checkout of another ref. Once the block is done with a workspace clone, `skf-ccc-git-hygiene.py workspace` restores the tracked `.gitignore` (or deletes one holding only those lines) and lists `.cocoindex_code/` and `/.skf-workspace.lock` in the clone's `.git/info/exclude`. Every workspace hit in create-skill and update-skill runs the same check before its fetch, which also repairs a clone an earlier SKF left edited, and audit-skill's `[C]` checkout runs it before its dirty-worktree probe. Any other local change is left alone, and a checkout it blocks falls back to an ephemeral clone.

For workspace repos, the CCC index persists at `{workspace_repo_path}/.cocoindex_code/` and is reused across forges, projects, and sessions. For ephemeral fallback clones, the index is not registered in `ccc_index_registry` — the clone is deleted after extraction.

### Relationship to QMD Registry

ccc_index and qmd_collections are **orthogonal**:
- `ccc_index` in forge-tier.yaml tracks the persistent source code index (one per project)
- `qmd_collections[]` in forge-tier.yaml tracks per-skill workflow artifact collections
- ccc indexes source code for semantic search; QMD indexes curated artifacts for temporal/knowledge search
- The janitor role for QMD (setup step 3) operates independently of ccc_index

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
- Indexing without configuring exclusions — for project root indexes, apply SKF exclusions (framework/output directories); for workspace repo indexes, apply standard build artifact exclusions in the `**/name` form (`**/node_modules`, `**/dist`, `**/build`, etc.), each written as a single-quoted YAML list item (`- '**/build'`), because ccc matches nothing with a trailing-slash form such as `build/`, and YAML reads an unquoted leading `*` as an alias, so ccc cannot load the file
- Writing brief-specific `exclude_patterns` to a workspace repo's `settings.yml` — workspace indexes are general-purpose and serve multiple briefs. Apply brief patterns at search result time, not index time. (Exception: ephemeral fallback clones are single-use, so brief exclusions may be applied to their `settings.yml` to reduce indexing time.)
- Running `ccc reset` to apply edited patterns or to repair an index missing the source language — a plain `ccc index` applies pattern edits, and a missing language is fixed in `include_patterns`. `ccc reset` deletes the index databases but keeps `settings.yml`; a `ccc index` right after it can fail and leave the project with no index until `ccc daemon restart`; and run from a folder without its own `settings.yml`, it deletes the enclosing project's index. Its real uses (switching the embedding model, or an index database `ccc doctor` reports as unreadable) are outside SKF.
- Skipping CCC discovery for remote sources without deferring to step 3 — remote repos deserve the same pre-ranking as local sources

## Related Fragments

- [tool-resolution.md](tool-resolution.md) — canonical bridge-to-tool and subprocess-to-tool mapping per IDE
- [progressive-capability.md](progressive-capability.md) — Forge+ tier definition and positive framing
- [confidence-tiers.md](confidence-tiers.md) — why ccc does not create a new confidence tier
- [qmd-registry.md](qmd-registry.md) — the parallel but separate registry for QMD collections

_Source: designed as part of the Forge+ tier integration for cocoindex-code semantic code search_
