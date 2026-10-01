---
nextStepFile: 'structural-diff.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder: the scan list, the recipe runner's JSON and
# the files of exports read by eye, which the snapshot is built from.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
extractionSnapshotProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-snapshot.py'
  - '{project-root}/src/shared/scripts/skf-extraction-snapshot.py'
# Every HALT after step 1 §5b's [C] closes the private tree with it.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Re-Index Source

## STEP GOAL:

Re-scan the source code using the current forge tier tools to build a fresh extraction snapshot. This snapshot will be compared against the original provenance map in Step 03 to detect structural drift.

## Rules

- Focus only on extracting current source state — do not compare yet (that's Step 03)
- Extract every file in the bounded scan list: a file skipped here makes step 3 flag its exports as false "removed" drift. The snapshot helper gives each file a status and says whether the snapshot is complete (§3), so never judge completeness by eye
- At Forge, Forge+ and Deep the recipe runner extracts; read by eye only what it leaves (§3), using subprocess Pattern 2 (per-file deep analysis) when available to read those files; if unavailable, read them in the main thread file by file

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (step 1 §5b's [C]), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Determine Extraction Strategy

Label every export by the tool that produced it, never by the tier: an export an ast-grep rule matched is T1 with `extraction_method: ast-grep` and, as `ast_node_type`, the `kind` the matching pattern or recipe declares in `{extractionPatternsData}` (ast-grep's output does not report it); an export read by eye is T1-low with `extraction_method: source-read` and `ast_node_type: null`.

Based on forge tier detected in Step 01:

**Quick tier (no AST tools):**
- Read source files via gh_bridge or direct file I/O
- Extract export names by text pattern matching (function/class/type declarations)
- Label every export T1-low (read by eye, not matched by ast-grep) with `extraction_method: source-read` and `ast_node_type: null`

**Forge tier (ast-grep available):**
- The recipe runner extracts, as the **AST Extraction Protocol** in `{extractionPatternsData}` says: one `skf-extract-public-api.py --mode full` call over the bounded scan list from §2 (§3 gives the command) runs every recipe for the language in one process, reads only the files on the list, and keeps every match (`--head-cap 0`: a match past a cap would read as a removed export in step 3). While it can run, never run the recipes one at a time, batch them, or merge and dedupe their matches by hand
- Each export it returns is T1 as it stands: its name (`$NAME`), type, file, line (`$NAME`'s line, as create-skill records it, not the match's first line, which a decorator or an `export` line can hold), `ast_node_type` and `signature`, the declaration on one line even when a formatter split its parameters over several
- Read by eye only what the runner leaves (§3): the forms the recipes leave out (Known Limitation #11 in `{extractionPatternsData}`) when a file uses them, the names an entry point exports that no recipe found, and the files it could not parse or read. Label each export by the tool that produced it: T1 with `extraction_method: ast-grep` for a runner export, T1-low with `extraction_method: source-read` and `ast_node_type: null` for an export read by eye

**Tier degradation handling (Forge/Forge+/Deep):** If the runner cannot run and ast-grep is unavailable, follow `{tierDegradationRulesData}` (AST Tool Unavailable, Per-File AST Failure) for the fallback and the user notification. A file ast-grep cannot parse falls back to reading that file only: its exports are T1-low with `extraction_method: source-read` and `ast_node_type: null`, and exports the runner matched in other files stay T1. Silent degradation is forbidden: the snapshot names each file's status, and the run names each file read after an ast-grep failure, and why (§3, §4); when ast-grep is unavailable for the whole run, every export is T1-low.

**Forge+ tier (ast-grep + ccc available):**
- Identical extraction to Forge tier (the AST Extraction Protocol, above)
- Label each export by tool, as at Forge tier
- CCC rename detection runs in step 3 (`structural-diff.md` §1b), over the exports the diff reports removed

**Deep tier (ast-grep + QMD available):**
- Identical extraction to Forge tier, labeled by tool as at Forge tier
- No QMD query at this step: step 4 (semantic diff) queries QMD itself

**Tool resolution:** `gh_bridge` → `gh api` commands or direct file I/O if local. `ast_bridge`, only when the runner cannot run (the protocol's **When the Runner Cannot Run**): the ast-grep MCP tool `find_code_by_rule` with a recipe and `output_format="json"`, or the protocol's CLI streaming template (`ast-grep scan -r {recipe_file} --json=stream`); `find_code` only as the fallback of Known Limitation #4. See `knowledge/tool-resolution.md`.

### 2. Build Bounded Scan List

Audit-skill detects drift on files that were in scope during create-skill. The authoritative record of "what was in scope" is the provenance map loaded in step 1. Scan only those files: **audit-skill does NOT discover new files**. New-file detection is the responsibility of `skf-update-skill`, which maintains its own change manifest; public API a package's entry points export from files outside that list reaches the drift report through the runner's entry-point diff (§3), for update-skill's scope reconciliation. To audit a project that has grown new files since creation, run update-skill first, then audit-skill.

**Why bounded:** without this constraint, files that were deliberately excluded by the original brief's scope patterns (test fixtures, vendored code, generated artifacts, demo code, unrelated modules) get scanned on every audit and their exports are flagged by step 3 structural diff as "added" — false-positive drift that obscures real structural changes.

**If a provenance map was loaded in step 1** (normal mode):

1. The **bounded scan list** is `{bounded_scan_files}`, the union of `entries[].source_file` and `file_entries[].source_file` that step 1 §4's `skf-load-provenance.py normalize` call returned. Do **not** re-walk the provenance map to rebuild it. Resolve `{extractionSnapshotHelper}` ← first existing path in `{extractionSnapshotProbeOrder}` (if none exists, HALT with **exit 3**, `halt_reason: "helper-missing"`, phase `re-index:scan-list`) and write the list where the runner reads it, from `{project-root}`:

   ```bash
   mkdir -p "{auditDataFolder}"
   uv run {extractionSnapshotHelper} scan-list "{provenanceMap}" -o "{auditDataFolder}/scan-files.json"
   ```

   It writes the same list as a JSON list of paths, the form the runner's `--files-from` reads: never retype it. If the folder or the file cannot be written (`status: "error"`), HALT with **exit 4**, `halt_reason: "write-failed"`, phase `re-index:scan-list`, `"path": "{auditDataFolder}"`.
2. Files that existed at creation time but are now missing under `{source_root}` are **not** errors at this stage: keep them in the list. The snapshot marks them `missing`, and step 3 classifies their exports as DELETED.
3. Report:

   "**Bounded scan:** {count} files from provenance map ({provenance_date})."

**If degraded mode** (no provenance map was loaded: the user confirmed `[D]egraded mode` at step 1 §4): the scan falls back to the source tree. At Forge tier and above, §3's second runner command reads it (the files of `{language}`, the `language` of `metadata.json`, less the generic exclusions it passes); at Quick tier, list all source files under `{source_root}` with the project's primary language extensions (derive from `metadata.json.language`: `*.ts` / `*.tsx` for typescript, `*.py` for python, `*.rs` for rust, `*.go` for go), leaving out the same exclusions: `**/tests/**`, `**/test/**`, `**/__tests__/**`, `**/*.test.*`, `**/*.spec.*`, `**/node_modules/**`, `**/dist/**`, `**/build/**`, `**/target/**`, `**/__pycache__/**`, `**/.venv/**`, `**/vendor/**`. Create the stage data folder (`mkdir -p "{auditDataFolder}"`). Report:

   "**Degraded mode scan:** files from the source tree (no provenance map, so results may include files out of the original brief scope)."

### 3. Extract Current Exports

**1. The recipe runner** (Forge, Forge+ and Deep). Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and, from `{project-root}`, remove the JSON an earlier run left and run the runner over the scan list, so that a JSON at `-o` after the call is this call's:

```bash
rm -f "{auditDataFolder}/extraction.json"
uv run {extractPublicApiHelper} --mode full \
    --source-root "{source_root}" \
    --files-from "{auditDataFolder}/scan-files.json" \
    --head-cap 0 \
    [--timeout "{runner_timeout}"] \
    -o "{auditDataFolder}/extraction.json"
```

In degraded mode, run instead:

```bash
rm -f "{auditDataFolder}/extraction.json"
uv run {extractPublicApiHelper} --mode full \
    --source-root "{source_root}" \
    --language "{language}" \
    --exclude "**/tests/**" --exclude "**/test/**" --exclude "**/__tests__/**" \
    --exclude "**/*.test.*" --exclude "**/*.spec.*" --exclude "**/node_modules/**" \
    --exclude "**/dist/**" --exclude "**/build/**" --exclude "**/target/**" \
    --exclude "**/__pycache__/**" --exclude "**/.venv/**" --exclude "**/vendor/**" \
    --head-cap 0 \
    [--timeout "{runner_timeout}"] \
    -o "{auditDataFolder}/extraction.json"
```

The runner stops its ast-grep runs after 540 seconds and still writes its JSON (status `incomplete`), so give the command your shell tool's longest timeout; when that is under 10 minutes, pass `--timeout` as `{runner_timeout}`, a little under it (`100` under a two-minute limit). Never open the JSON: item 2's helper reads it and prints what this step acts on, its `status` included (never the exit code). At Quick tier no runner runs.

**2. Build the snapshot.** Resolve `{extractionSnapshotHelper}` ← first existing path in `{extractionSnapshotProbeOrder}` (if none exists, HALT with **exit 3**, `halt_reason: "helper-missing"`, phase `re-index:snapshot`) and, from `{project-root}`, run:

```bash
uv run {extractionSnapshotHelper} build \
    --source-root "{source_root}" \
    --source-path "{source_path}" \
    --tier "{tier}" \
    --date "{timestamp}" \
    [--provenance-map "{provenanceMap}"] \
    [--extraction "{auditDataFolder}/extraction.json"] \
    [--details "{auditDataFolder}/export-details-{n}.json"]... \
    -o "{forge_version}/extraction-snapshot.json"
```

Pass `--provenance-map` unless the run is in degraded mode, `--extraction` when the runner wrote its JSON, and one `--details` for each file item 3 wrote (none on the first build). The helper merges the runner's exports with the ones read by eye, gives every file on the list one status (`extracted`, `read-by-eye`, `hash-tracked` for a script, asset or doc only `file_entries[]` names, which step 3 compares by content hash, `missing`, `parse-failed` or `unread`) and prints one line. Act on its fields:

- **`runner_status` is `incomplete`** on the first build (an ast-grep run failed, or the time limit ran out): run item 1 once more, then this command again.
- **`runner_status` is `no-ast-grep`, or null at Forge tier and above** (no JSON at `-o` after the call, or no runner candidate): the runner cannot run. Follow **When the Runner Cannot Run** in `{extractionPatternsData}` over the files in `to_read`, recording each export as item 3 does, T1 with `ast-grep` for one the recipes match.
- **`to_read` or `extraction_gaps` is not empty**, or a file uses the forms the recipes leave out: item 3 reads them, then run this command again with its details. When `complete` is still false, the files `to_read` lists could not be read: HALT with **exit 3**, `halt_reason: "source-unreadable"`, phase `re-index:snapshot`, naming them. Step 3 never reads an incomplete snapshot.
- **`complete` is true** and nothing is left to read: go on to §4.
- **`status: "error"`:** an `error` that starts `cannot write` is a failed write: HALT with **exit 4**, `halt_reason: "write-failed"`, phase `re-index:snapshot`, `"path": "{forge_version}/extraction-snapshot.json"`. Any other names a file this step wrote: fix it and run the command again.
- **The command fails otherwise, or prints no JSON:** HALT with **exit 3**, `halt_reason: "helper-missing"`, phase `re-index:snapshot`, showing the first stderr line.

**3. What the runner leaves.** Read by eye (T1-low, `extraction_method: source-read`, `ast_node_type: null`) only:

- each file in `to_read`: a `parse-failed` one (its `issue`: a syntax error, where a recipe can miss an export; not UTF-8; unreadable), with the warning "**AST fallback:** ast-grep could not parse {file} ({issue}); its exports were read from source and labeled T1-low.", and an `unread` one (an incomplete run, or no runner: then every file, by text pattern matching at Quick tier). In degraded mode with no runner result the helper knows no file yet: read the files §2 lists at Quick tier;
- each name in `extraction_gaps`, in its `file` (an entry point exports it, no recipe found it);
- the forms the recipes leave out (Known Limitation #11 in `{extractionPatternsData}`) in a file that uses them.

For each file to read, launch a subprocess (Pattern 2) that loads it and returns ONLY `{"files": [...], "exports": [...]}`, with no prose and no fences: `files` lists the file when the worker read the whole of it (also when it holds no export), and each export gives `name`, `type`, `signature` (the declaration on one line), `file` (relative to `{source_root}`, with forward slashes), `line` (`$NAME`'s line), `confidence: "T1-low"`, `extraction_method: "source-read"` and `ast_node_type: null`. Save each worker's JSON as it returned it, as `{auditDataFolder}/export-details-{n}.json` (`{n}` counting from 1), never merged by hand; without subprocesses, read the files in the main thread, one by one, and save one such file. A stack's export needs no library: the snapshot helper gives each one its file's `source_library` from the provenance map (the map `normalize` returns as `source_library_by_file`).

**The snapshot.** The command writes `{forge_version}/extraction-snapshot.json`, which step 3 (`structural-diff.md`) reads directly: `exports[]` (for a stack, each with its file's `source_library`), `files[]` with each file's status, `files_by_status`, `counts` and `cap_hits` (§4) and `outside_scope` (step 6's Out-of-Scope New Public API table); `skf-extraction-snapshot.py --help` gives the full shape. Record the written path as `{extractionSnapshot}` in workflow context: step 3 passes it to the structural-diff helper.

### 4. Validate Extraction Completeness

Take every value from the snapshot (`files_by_status`, `counts`, `cap_hits`) and the build's line (`ast_fallback_files`), never a recount:

"**Extraction complete.**

| Metric | Value |
|--------|-------|
| Scan mode | {bounded (provenance-map) / degraded (source-tree)} |
| Files scanned | {files_scanned}: {extracted} extracted, {read-by-eye} read by eye, {hash-tracked} tracked by hash, {missing} missing |
| Exports found | {counts.exports} |
| By type | {each counts.by_type entry as `{type}` ×{count}} |
| Labels | {t1_count} T1 (`ast-grep`), {t1_low_count} T1-low (`source-read`) |
| AST fallback files | {count and names from `ast_fallback_files`, or none; n/a at Quick} |
| Cap hits | {cap_hits, or none} |

**Proceeding to structural comparison...**"

`ast_fallback_files` names the files read by eye after the runner could not parse or read them, not one read again for a gap or a Known Limitation #11 form (`all files (ast-grep unavailable)` when the runner could not run, none at Quick tier).

### 5. Update Report and Auto-Proceed

Update {outputFile} frontmatter: append `'re-index'` to `stepsCompleted` and set `ast_fallback_files` to the last build's `ast_fallback_files`. Once the snapshot helper reports `complete: true`, load, read fully, and execute `{nextStepFile}` (structural diff).
