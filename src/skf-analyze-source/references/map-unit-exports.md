<!-- Config: communicate in {communication_language}. -->

# Map Each Unit's Exports

The per-unit export analysis, stated once for the two files that run it: map-and-detect section 2, for every qualifying unit, and discover-additional-source section 4, for the units it adds. The file that loads this one has resolved `{extractPublicApiHelper}` and `{checkUnitRecordsHelper}` and gives each unit its name, its scope type (`{unit_scope_type}`), its language, its folder (`{unit_root}`: its path under the scan root of its project path) and its file count (the `files_count` of its disqualification record, which the Files column of Identified Units shows); `{forge_tier}` is the report's. This file returns to it with the checked records.

## 1. Delegate Each Unit to a Subagent

For each unit, launch a subagent task with these explicit constraints:

- The subagent reads only that unit's directory tree
- The subagent analyzes exports / usage / CCC signals / scripts+assets for that one unit
- **The parent does not read the unit's source files before delegating** (avoid the implicit-read trap: the whole point of fan-out is to keep large source bodies out of the parent's context)
- The subagent writes its record (§3) to a file of the run folder and returns only that file's path, so the parent never copies a record: pass it `{run_dir}` and the resolved `{extractPublicApiHelper}`

**Graceful degradation.** If subagents are unavailable in the current runtime, the parent performs the per-unit analysis sequentially in the main thread with the same export-surface call and tier-aware extras. Each main-thread analysis still writes the same JSON record, so the later steps do not depend on the execution mode.

## 2. Analyze One Unit

**Export surface (every tier):** run the recipe runner on the unit's own folder. For the languages it has ast-grep recipes for (Python, JavaScript and TypeScript, Rust, Go, Vue) it lists the files, runs the recipes, follows the entry points and counts the public API, so the subagent neither greps nor counts those exports by hand:

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{unit_root}" --scope-type {unit_scope_type} --tier {forge_tier}
```

**No recipe for the unit's language:** when `files_in_scope` is 0, or `files_without_recipes` lists the extension of the unit's language (Java, Kotlin, Swift, C#, PHP, Ruby and C or C++ have no recipe), the run counted none of its exports, whatever its exit code. Read the public declarations of the unit's source files by eye, as on exit 3: `exports_count`, `api_surface` and `export_pattern` from what you read (for example "public classes: 14, interfaces: 3"), `strategy_used: "source-read"`, `confidence: "T1-low"`.

Otherwise read the JSON by the exit code:

- **0 or 1:** `exports_count` ← `counts.exports_public_api`, `api_surface` ← the names in `entry_point_diff.public[]`, `export_pattern` ← `entry_points.status` with `aggregates.by_type` (for example "barrel: 12 functions, 5 classes", marked "capped" when `truncated` is true), `strategy_used: "ast-grep"`, `confidence: "T1"`. Then read by eye what the recipes could not, and name each one in `warnings`: every `entry_point_diff.extraction_gaps[]` name (public, but no recipe found its definition: read it at its `file` and `line`) and every `file_issues[]` file (one the parser could not fully read: add the exports it shows to `api_surface`). Exit 1 (`status: "incomplete"`) means an ast-grep run failed on some files: keep what it returned and put its `errors[]` in `warnings`.
- **3** (no ast-grep the runner can run): the JSON still lists `entry_points.files`. Read the exports from those entry-point files by eye (from the unit's source files when it lists none), with `strategy_used: "source-read"` and `confidence: "T1-low"`.
- **2:** an input error, named on stderr (a wrong path or flag): fix the call and run it again.

**Tier-aware extras:**

- **Forge+ tier:**
  - If `tools.ccc` is true: run `ccc_bridge.search("{unit_name} exports public API", top_k=15)` to discover semantically relevant files beyond directory scan. Tool resolution: prefer the `/ccc` skill search (Claude Code) or ccc MCP server (Cursor); fall back to the `ccc search` CLI if neither is available; if no ccc tool resolves, skip CCC discovery and record `ccc: unavailable` in per-unit findings.
  - Record CCC signals in per-unit findings: top 3 CCC-ranked file names (or "--" if no ccc results)
- **Deep tier:**
  - If QMD available: query for temporal evolution of identified exports (deprecation signals, recent additions, refactoring patterns)
  - Record semantic relationships between exports (which exports reference/depend on each other)

**The subagent also records:**

- Script/asset presence: check for `scripts/`, `bin/`, `assets/`, `templates/` directories and files matching the detection signals in `references/unit-detection-heuristics.md`
- The export-surface call's `strategy_used`, `confidence` and `warnings`

## 3. Record Contract

Each subagent writes only this JSON object, with no prose, no commentary and no markdown fence, to `{run_dir}/unit-records/{unit_name}.json` (creating the folder), and returns that path:

```json
{
  "unit_name": "...",
  "files_count": N,
  "exports_count": N,
  "export_pattern": "...",
  "api_surface": ["..."],
  "scripts_assets": {"scripts": [], "assets": []},
  "ccc_signals": {"top_files": [], "available": <bool>},
  "strategy_used": "ast-grep|source-read",
  "confidence": "T1|T1-low",
  "warnings": []
}
```

`files_count` is the unit's file count the loading file gave (the `files_count` of its disqualification record), not the runner's `files_in_scope`, which leaves out every file no recipe reads.

## 4. Check the Records

Once every subagent has returned its path (a main-thread analysis writes its record the same way), check all the records in one call:

```bash
uv run {checkUnitRecordsHelper} --dir "{run_dir}/unit-records"
```

The script drops a wrapping markdown fence (a subagent sometimes writes one despite the contract), checks each record against the contract above and fills a missing or wrong-typed key with its empty value, so a degraded record still goes on. Its `records` are the per-unit payloads. Record each `problems` entry as the warning `{unit_name}: {problem}` and each `warnings` entry as it is, so they reach the envelope's `warnings`: one `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'` per entry, a single quote in it written as a backtick. A unit with no file in the folder, or a file the script lists in `unreadable` (it held no JSON object), is analyzed again in the main thread (graceful degradation, §1), and the check runs once more. Record only the entries of the units this pass analyzed: a record an earlier pass checked was recorded then.

Return to the file that loaded this one with the checked `records` of these units.
