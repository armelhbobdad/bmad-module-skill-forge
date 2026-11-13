<!-- Config: communicate in {communication_language}. -->

# Map Each Unit's Exports

The per-unit export analysis, stated once for the two files that run it: map-and-detect section 2, for every qualifying unit, and discover-additional-source section 4, for the units it adds. The file that loads this one has resolved `{extractPublicApiHelper}` and `{checkUnitRecordsHelper}` and gives each unit its name (`{unit_name}`), its scope type (`{unit_scope_type}`), its language (`{language}`), its folder (`{unit_root}`: its path under the scan root of its project path) and its file count (`{files_count}`: the `files_count` of its disqualification record, which the Files column of Identified Units shows); `{forge_tier}` is the report's. This file returns to it with the checked records.

## 1. Write Each Record, Then Delegate What Is Left

For each unit, the parent runs §2's line itself: the extraction, then the script that writes the unit's record (§3) from it. It reads only the one JSON line the script prints, never the extraction's output and never the unit's source files (the implicit-read trap: the whole point of the fan-out is to keep large source bodies out of the parent's context).

Launch a subagent task only for a unit whose printed `to_read` is not empty, or for every unit when `tools.ccc` is true (the ccc search of §2): a unit with nothing to read and no ccc search needs none. Give it these explicit constraints:

- The subagent reads only that unit's directory tree, and there only what §2 says its `to_read` asks for
- It edits the record the line printed (`record`) in place and returns only that file's path, so the parent never copies a record: pass it that path and the `to_read` list

**Graceful degradation.** If subagents are unavailable in the current runtime, the parent does the same reading and the same ccc search sequentially in the main thread, in the same record file, so the later steps do not depend on the execution mode.

## 2. Analyze One Unit

**Export surface (every tier):** one line per unit, which the parent runs (§1). The extractor writes its output to the run folder, and `from-extract` writes the unit's record from it to `{run_dir}/unit-records/{unit_name}.json` with every field of §3 set (a namespace given as its members' names), so no one maps the extractor's JSON into the record by hand. A Java, Kotlin or Swift unit runs quick mode's parser over every source file the language's scope patterns include (`--all-sources`, its tests left out), with `strategy_used: "parser"` and `confidence: "T1"`:

```bash
mkdir -p "{run_dir}/extract" && uv run {extractPublicApiHelper} --mode quick --language {language} --source-root "{unit_root}" --all-sources > "{run_dir}/extract/{unit_name}.json"; uv run {checkUnitRecordsHelper} from-extract --extract "{run_dir}/extract/{unit_name}.json" --exit-code $? --unit-name "{unit_name}" --files-count {files_count} --language {language} --dir "{run_dir}/unit-records"
```

Every other unit runs the recipe runner on its own folder. For the languages it has ast-grep recipes for (Python, JavaScript and TypeScript, Rust, Go, Vue) it lists the files, runs the recipes, follows the entry points and counts the public API, with `strategy_used: "ast-grep"` and `confidence: "T1"`:

```bash
mkdir -p "{run_dir}/extract" && uv run {extractPublicApiHelper} --mode full --source-root "{unit_root}" --scope-type {unit_scope_type} --tier {forge_tier} -o "{run_dir}/extract/{unit_name}.json"; uv run {checkUnitRecordsHelper} from-extract --extract "{run_dir}/extract/{unit_name}.json" --exit-code $? --unit-name "{unit_name}" --files-count {files_count} --language {language} --dir "{run_dir}/unit-records"
```

The script prints one JSON line: `record` (the file it wrote), `strategy_used`, `exports_count` and `to_read`. It exits 2 and writes nothing on the extractor's own input error (a wrong path or flag) and on a wrong argument of its own, naming either on stderr: fix what it names and run the line again.

**What is left to read** (`to_read`), each item by its `why`:

- `extraction-gap` (an `entry_point_diff.extraction_gaps[]` row): a public name no recipe found the definition of, already in `api_surface` and `warnings`. Read it at its `file` and `line`.
- `file-issue` (a `file_issues[]` item): a file the parser could not fully read (`issue` says why), named in `warnings`. Add the exports it shows to `api_surface`.
- `entry-point` or `unit-sources`: no script counted the unit's exports, so the record has `strategy_used: "source-read"`, `confidence: "T1-low"` and no export. The runner found no ast-grep it could run (exit 3, and `entry-point` names each entry-point file it listed), read no file of the unit (for the parser, `--all-sources` found no source file of the language), or the unit's language has neither a recipe nor the parser (C#, PHP, Ruby, C or C++ and the rest). Read the public declarations by eye, of those entry-point files or of the unit's source files, and fill `exports_count`, `api_surface` and `export_pattern` from what you read (for example "public classes: 14, interfaces: 3").

**Tier-aware extras:** when `tools.ccc` is true (Forge+, or Deep with ccc installed), search `"{unit_name} exports public API"` (top 15) with the ccc tool the runtime offers (the `/ccc` skill, a ccc MCP server or the `ccc search` CLI) and record the top 3 files in `ccc_signals.top_files`, with `available: true`; with no ccc tool, record `available: false`.

The subagent changes no other field: the script set `unit_name`, `files_count`, `strategy_used`, `confidence` and `warnings`.

## 3. Record Contract

`from-extract` writes this JSON object to `{run_dir}/unit-records/{unit_name}.json` (creating the folder). A subagent that edits it keeps it this object only, with no prose, no commentary and no markdown fence, and returns its path:

```json
{
  "unit_name": "...",
  "files_count": N,
  "exports_count": N,
  "export_pattern": "...",
  "api_surface": ["..."],
  "ccc_signals": {"top_files": [], "available": <bool>},
  "strategy_used": "ast-grep|parser|source-read",
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
