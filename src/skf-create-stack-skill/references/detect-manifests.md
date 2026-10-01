---
nextStepFile: 'rank-and-confirm.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Manifests

## STEP GOAL:

Take the dependency manifests of `{scan_root}` (the folder step 1 chose) from the manifest scanner and produce a raw dependency list for ranking; in compose mode, pick the constituent skills instead.

## Rules

- Render the scanner's and the candidates helper's JSON; never parse a manifest or join candidates by hand
- Do not count imports or rank dependencies (Step 03) or extract documentation (Step 04)
- If explicit dependency list was provided in step 01, use it and skip detection

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

### 0. Check Compose Mode

**If `compose_mode` is true:**

Pick the constituent skills with the shared helper, which keeps only the skills SKF generated (a `metadata.json` SKF marker: see `knowledge/version-paths.md` Ownership) and gates every candidate in one call. When step 1 kept `{skill_candidates}`, use that result: it ran this same call. Otherwise resolve `{enumerateStackSkillsHelper}` from `{enumerateStackSkillsProbeOrder}` (first existing path wins; if no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-manifests:enumerate`) with "**Cannot proceed.** `skf-enumerate-stack-skills.py` is missing, so no constituent skill can be picked. Re-install SKF, then re-run.") and run it, passing `--explicit` with the `explicit_deps` entries as given, comma-separated, when step 1 bound them (the helper reduces a package path to its skill folder):

```bash
uv run {enumerateStackSkillsHelper} candidates {skills_output_folder} [--explicit "<names>"]
```

Render its JSON as it stands, never re-joining candidates by hand. An exit `1` (no skills folder) counts as an empty `kept[]`:

- `manifest_parse_error` is not null: log `"{manifest_parse_error}: using the active links instead"` (B3).
- `not_skf_output` is not empty: display it once, "Skipped (not SKF output): {not_skf_output}".
- Each `excluded[]` entry: log its `message` as given, one line each.
- `stale_manifest_keys` is not empty (**stale manifest, H6**: the export manifest names a skill whose folder is gone): HALT (exit 3, `halt_reason: "resolution-failure"`, phase `detect-manifests:stale-manifest`) with a manifest-corruption diagnostic naming each key and pointing the user at `[SKF-update-skill]` to repair.
- `kept[]` is empty: HALT (exit 3, `halt_reason: "resolution-failure"`, phase `detect-manifests:no-skills`) with "**Cannot proceed in compose-mode.** No individual skills found in `{skills_output_folder}` (stack skills are never constituents). Run [CS] Create Skill or [QS] Quick Skill to generate individual skills first, then re-run [SS]."

A composes cycle is not an exclusion: step 4 §0 halts on one that involves a confirmed skill.

For each `kept[]` entry:
1. Store its `name`, the top-level folder, as `skill_dir` (distinct from the metadata `name`).
2. `skill_package_path` ← `{skills_output_folder}/{path}` from that entry: the package whose exports and `metadata_hash` the helper reported, so path and hash come from one resolution (the helper follows `active`, as the manifest-lag guard in `knowledge/version-paths.md` does).
3. Read `metadata.json` from `skill_package_path` for the fields the entry lacks: name, version and source_authority. The entry gives language, confidence_tier, source_repo and the export count (`exports`).
4. **Record the constituent metadata_hash (S13):** take its `metadata_hash` (a `sha256:`-prefixed digest of the raw `metadata.json`) from the same `kept[]` entry and store it in workflow state alongside `skill_package_path`. The script is the single source of this hash (never hand-compute it); step 4 §0 checks it for drift and records the provenance anchor.
5. Store as `raw_dependencies` with source: "existing_skill" (`"explicit"` for a name from `explicit_deps`)

Report the `{N}` loaded skills — for each: name, language, confidence tier, export count, and source.

Skip to [Auto-Proceed to Next Step](#4-auto-proceed-to-next-step) — this loaded-skills summary serves as the detection summary.

**If not compose_mode:** Continue with section 1 (existing flow).

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

**Headless auto-cancel (S2):** If `{headless_mode}` is true, do NOT wait for user input: HALT (exit 2, `halt_reason: "no-manifests"`, phase `detect-manifests:no-manifests`) with "**Cannot proceed.** No dependency manifests in `{scan_root}`, and a headless run needs one or an explicit `skills` list."

**Interactive mode:**

"**No dependency manifests detected** in `{scan_root}`.

Searched for: {the `searched_filenames`, comma-separated}

**Options:**
1. Provide an explicit dependency list
2. Scan a different folder
3. Cancel workflow

**Halting: please provide input.**"

STOP and wait for the user's response. Option 2 sets `{scan_root}` to the folder the user names (a relative path resolves from `project_root`) and runs the scan call above again, replacing `{manifest_scan}`. Option 3 is a HALT (exit 6, `halt_reason: "user-cancelled"`, phase `detect-manifests:no-manifests`): emit it, then delete the run folder (`rm -rf "{run_dir}"`).

Otherwise, `raw_dependencies` is `{manifest_scan}` as it stands (the scanner already deduplicates, and step 3 pipes it to the import counter). Surface any `warnings[]` to the user as parse-quality notes. When `folders[]` lists more than one folder, the detection summary says so and names `{scan_root}`, the folder step 1 §3 chose (the whole project unless `project_path` or the user's answer named one package): to stack one package, re-run with `project_path` set to its folder.

### 3. Display Detection Summary

Report `{scan_root}`, the detected manifests (for each: path, ecosystem, dependency count), and the unique dependency count split by each dependency's `scope`: runtime (`total_unique`) and dev only (`total_unique_dev`). With `explicit_deps`, report its library count instead.

### 4. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

