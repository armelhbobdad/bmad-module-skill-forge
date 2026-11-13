---
nextStepFile: 'rank-and-confirm.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
runFile: '{run_dir}/run.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Manifests

## STEP GOAL:

Take the dependency manifests of `{scan_root}` (the folder step 1 chose) from the manifest scanner and produce a raw dependency list for ranking.

## Rules

- Render the scanner's JSON; never parse a manifest by hand
- Do not count imports or rank dependencies (Step 03) or extract documentation (Step 04)
- If explicit dependency list was provided in step 01, use it and skip detection

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "code"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

### 1. Check for Explicit Dependency List

**If `explicit_deps` was provided in step 01:**

"**Using provided dependency list.** Skipping manifest auto-detection.

**Dependencies:** {explicit_deps_count} libraries provided"

Store the explicit list as `raw_dependencies` and skip to [Display Detection Summary](#3-display-detection-summary).

**If no explicit list:** Continue to section 2.

### 2. Scan and Parse Manifests

Step 1 §3 ran the deterministic manifest scanner on `{scan_root}` and kept its JSON as `{manifest_scan}`: use it. Run the scanner again only on a folder the user names below. **Resolve `{scanManifestsHelper}`** from `{scanManifestsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-manifests:scan`) with "**Cannot proceed.** `skf-scan-manifests.py` is missing, so no manifest can be read. Re-install SKF, then re-run."

```bash
uv run {scanManifestsHelper} scan {scan_root} --include-dev
```

`references/manifest-patterns.md` documents the manifest files and dependency sections the scanner reads and the folders it skips; the script implements exactly that table. The JSON it emits (its docstring has every field):

```
{
  "manifests": [
    {"path": "<rel-from-scan-root>", "ecosystem": "<name>", "name": "<package name>" | null,
     "deps": [{"name": "...", "version": "...", "scope": "dev"}]},   // `scope` only on a dev dependency
    ...
  ],
  "total_unique": N,                            // unique runtime dependency names
  "total_unique_dev": N,                        // unique names that are dev dependencies only
  "monorepo": <bool>,
  "folders": [{"path": "<folder>", "names": ["..."]}, ...],  // each manifest folder ("." for {scan_root})
  "searched_filenames": ["package.json", ...],  // every manifest name looked for
  "warnings": ["..."]                           // only when a manifest did not parse
}
```

If `manifests` is empty:

**GATE [default: HALT]**, headless auto-cancel: if `{headless_mode}` is true, do NOT wait for user input: HALT (exit 2, `halt_reason: "no-manifests"`, phase `detect-manifests:no-manifests`) with "**Cannot proceed.** No dependency manifests in `{scan_root}`, and a headless run needs one or an explicit `skills` list."

**Interactive mode:**

"**No dependency manifests detected** in `{scan_root}`.

Searched for: {the `searched_filenames`, comma-separated}

**Options:**
1. Provide an explicit dependency list
2. Scan a different folder
3. Cancel workflow

**Halting: please provide input.**"

STOP and wait for the user's response. Option 1 binds `explicit_deps` to the names the user gives (comma-separated or one per line) and stores them as `raw_dependencies` as §1 does. It then saves `explicit_deps` as **Save the new binding** below shows, and only then goes on to [Display Detection Summary](#3-display-detection-summary). Option 2 sets `{scan_root}` to the folder the user names (a relative path resolves from `project_root`) and runs the scan call above again, replacing `{manifest_scan}`. Option 3 is a HALT (exit 6, `halt_reason: "user-cancelled"`, phase `detect-manifests:no-manifests`): emit it, then delete the run folder (`rm -rf "{run_dir}"`).

**Save the new binding.** When option 1 binds `explicit_deps` or option 2 sets `{scan_root}`, save it in `{runFile}` before going on, so a later step that lost it to compaction reads this value and not step 1's: read `{runFile}`, set its `explicit_deps` (the list of names) or `scan_root` to the new value, stage the whole object as `{run_dir}/run-bindings.json` with a file write and run:

```bash
uv run {atomicWriteHelper} write --target "{runFile}" < "{run_dir}/run-bindings.json"
```

resolving `{atomicWriteHelper}` from `{atomicWriteProbeOrder}` if it is not bound (step 1 §5 found it). If it exits non-zero, HALT (exit 4, `halt_reason: "write-failure"`, phase `detect-manifests:run-state`) with "**Cannot proceed.** The new `explicit_deps` could not be saved to `{runFile}`: {the first stderr line}.", naming `scan_root` in place of `explicit_deps` after option 2.

When `manifests` is not empty, `raw_dependencies` is `{manifest_scan}` as it stands (the scanner already deduplicates, and step 3 pipes it to the import counter). Surface any `warnings[]` to the user as parse-quality notes. When `folders[]` lists more than one folder, the detection summary says so and names `{scan_root}`, the folder step 1 §3 chose (the whole project unless `project_path` or the user's answer named one package): to stack one package, re-run with `project_path` set to its folder.

### 3. Display Detection Summary

Report `{scan_root}`, the detected manifests (for each: path, ecosystem, dependency count), and the unique dependency count split by each dependency's `scope`: runtime (`total_unique`) and dev only (`total_unique_dev`). With `explicit_deps`, report its library count instead.

### 4. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

