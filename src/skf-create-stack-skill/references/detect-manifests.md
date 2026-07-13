---
nextStepFile: 'rank-and-confirm.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Manifests

## STEP GOAL:

Scan the project root for dependency manifest files, parse each to extract dependency names and versions, and produce a raw dependency list for ranking.

## Rules

- Focus only on finding and parsing manifest files
- Do not count imports or rank dependencies (Step 03) or extract documentation (Step 04)
- If explicit dependency list was provided in step 01, use it and skip detection

## MANDATORY SEQUENCE

### 0. Check Compose Mode

**If `compose_mode` is true AND `explicit_deps` was provided in step 01:**

Use the explicit dependency list directly. Store the explicit list as `raw_dependencies` with `source: "explicit"` and skip to [Auto-Proceed to Next Step](#4-auto-proceed-to-next-step).

**If `compose_mode` is true AND `explicit_deps` was NOT provided:**

Discover skills in `{skills_output_folder}` using version-aware resolution — see `knowledge/version-paths.md` for path templates.

**Version-aware skill enumeration:**

1. **Primary: Export manifest** — Read `{skills_output_folder}/.export-manifest.json`. For each entry in `exports`, resolve the active version path: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/` — this directory must contain both `SKILL.md` and `metadata.json`.

   **Stale manifest fallback (H6):** If a manifest entry resolves to a path that does not exist (broken `active_version`, deleted version dir, missing `SKILL.md` / `metadata.json`), do NOT HALT for that single entry. Instead:
   a. Fall back to the symlink scan (rule 2) **for that one skill only**: probe `{skills_output_folder}/{skill-name}/active/{skill-name}/SKILL.md`.
   b. If the symlink-based path resolves, use it and log a warning: `"export-manifest entry '{skill-name}' is stale — resolved via active symlink instead"`.
   c. If BOTH the manifest path AND the symlink path fail, only then HALT with a manifest-corruption diagnostic naming the affected skill and pointing the user at `[SKF-update-skill]` to repair. Emit the result envelope on stderr per the Result Contract in SKILL.md, then STOP:

   ```
   SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":"compose","exit_code":3,"halt_reason":"resolution-failure"}
   ```

   **Manifest JSON parse guard (B3):** Wrap the `.export-manifest.json` parse in try/except. If JSON parsing fails for any reason, fall through entirely to the `active` symlink scan (rule 2) across all skills; log a warning and validate each symlink target exists before including it.

2. **Fallback: `active` symlinks** — If the manifest does not exist, is empty, JSON-parse fails, or an individual manifest entry fails to resolve, scan for `{skills_output_folder}/*/active/*/SKILL.md`. Each match resolves to a skill package at `{skills_output_folder}/{skill-name}/active/{skill-name}/` (the `{active_skill}` template). Verify the active symlink target actually exists and contains both `SKILL.md` and `metadata.json`.

**Filter & cycle guard (B4):** Skip any skill where the filter below matches:

- Skill name equals `{project_name}-stack`, OR
- `metadata.json` has `"skill_type": "stack"`, OR
- `metadata.json` is missing or unreadable (treat `skill_type: unknown` as non-loadable — exclude to avoid loading a partially-written or self-referential skill).

Maintain a **visited set keyed by `skill_dir`** (the top-level dir under `{skills_output_folder}`) while resolving. If a skill would be revisited via a circular reference (e.g., a constituent that claims another stack as dependency), skip the duplicate and log a warning `"cycle detected at {skill_dir} — skipping"`. Stack skills must not be loaded as source dependencies to avoid self-referencing loops.

**If zero skills remain after filtering:** HALT with: "**Cannot proceed in compose-mode.** No individual skills found in `{skills_output_folder}` (after filtering stack skills). Run [CS] Create Skill or [QS] Quick Skill to generate individual skills first, then re-run [SS]." Then emit the result envelope on stderr per the Result Contract in SKILL.md, and STOP:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":"compose","exit_code":3,"halt_reason":"resolution-failure"}
```

**Deterministic metadata hashing (S13) — script-driven:** Do NOT compute `sha256` in-prompt (a model cannot reproduce a digest, so a hand-computed hash would false-diverge against step 4's script-computed hash). Invoke the same enumeration helper step 4 §0 uses to obtain every constituent's `metadata_hash` in one deterministic call:

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. HALT if no candidate exists.

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder}
```

Key the emitted `skills[].metadata_hash` (a `sha256:`-prefixed digest of the raw `metadata.json`, or `null` when no metadata.json is present) by `skills[].name` for use in rule 5 below. The script's `name` is the top-level subdirectory under `{skills_output_folder}` — i.e. the `skill_dir` captured in rule 3, not the metadata `name` — so join on `skill_dir`.

For each skill found:
1. Read `metadata.json` from the resolved version-aware path (`{skill_package}` or `{active_skill}`). **Skill-type gate (S1):** the sibling `metadata.json` MUST be present AND parseable AND contain a `skill_type` field whose value is one of the known set (`skill`, `stack`, or any future values explicitly recognised by this workflow). Directories lacking a qualifying `metadata.json`/`skill_type` are NOT treated as skills — log `"{dir_name}: not a skill (no valid metadata.json/skill_type) — excluding"` and skip.
2. Extract: name, language, confidence_tier, source_repo, exports count, version
3. Store the skill group directory name as `skill_dir` (the top-level name under `{skills_output_folder}`, distinct from `name` — the directory may differ from the metadata name)
4. Store the resolved package path as `skill_package_path` for use in later steps
5. **Record the constituent metadata_hash (S13):** take this skill's `metadata_hash` from the enumerate-script inventory above (matched on `skill_dir`) and store it in workflow state alongside `skill_package_path`. The script is the single source of this hash — never hand-compute — so the step-4 drift check compares script-hash to script-hash and never false-positives on a model recomputation. Step-07 uses this stored hash (not a re-read) for `constituents[].metadata_hash` in `provenance-map.json`, so drift between step 2 read and step 7 write is captured.
6. Store as `raw_dependencies` with source: "existing_skill"

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

Invoke the deterministic manifest scanner — it walks the project root, parses every recognised manifest, dedupes the production dep set, and flags monorepo layout:

**Resolve `{scanManifestsHelper}`** from `{scanManifestsProbeOrder}`; first existing path wins. HALT if no candidate exists.

```bash
uv run {scanManifestsHelper} scan {scan_root}
```

Where `{scan_root}` is the project root path. Load `{manifestPatternsPath}` for the ecosystem reference table that documents supported filenames, dependency keys, and normalisation rules; the script implements exactly that table (npm/pnpm/yarn, python pip/poetry/pdm, rust cargo, go modules, java/kotlin maven + gradle, ruby bundler, composer, swift package manager). Exclusion patterns (`node_modules/`, `.venv/`, `vendor/`, `dist/`, `build/`, `target/`, `.git/`, hidden dirs) are applied internally.

Parse the JSON output — shape:

```
{
  "manifests": [
    {"path": "<rel-from-root>", "ecosystem": "<name>", "deps": [{"name": "...", "version": "..."}]},
    ...
  ],
  "total_unique": N,
  "monorepo": <bool>,
  "warnings": ["..."]   // optional, only if any parse warning fired
}
```

If `manifests` is empty:

**Headless auto-cancel (S2):** If `{headless_mode}` is true, do NOT wait for user input. Emit the result envelope on stderr per the Result Contract in SKILL.md and exit `2`. Headless mode cannot proceed without an explicit dependency list.

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":"code","exit_code":2,"halt_reason":"no-manifests"}
```

**Interactive mode:**

"**No dependency manifests detected** in the project root.

Searched for: package.json, requirements.txt, Cargo.toml, go.mod, pom.xml, build.gradle, Gemfile, composer.json, *.csproj

**Options:**
1. Provide an explicit dependency list
2. Specify a different project root path
3. Cancel workflow

**Halting — please provide input.**"

STOP — wait for user response.

Otherwise, store the parsed `manifests[]` and `total_unique` as `raw_dependencies` (dedup is already applied by the scanner), surface any `warnings[]` to the user as parse-quality notes, and inspect the `monorepo` flag: if `true`, mention the monorepo layout in the detection summary so the user can decide whether to scope the ranking to a specific package or proceed across all manifests.

### 3. Display Detection Summary

Report the detected manifests (for each: path, ecosystem, dependency count) and the total unique dependency count split into runtime vs dev-only.

### 4. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

