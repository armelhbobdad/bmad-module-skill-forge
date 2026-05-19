---
nextStepFile: 'rank-and-confirm.md'
manifestPatterns: 'references/manifest-patterns.md'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
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

Use the explicit dependency list directly. Store the explicit list as `raw_dependencies` with `source: "explicit"` and skip to [Auto-Proceed to Next Step](#5-auto-proceed-to-next-step).

**If `compose_mode` is true AND `explicit_deps` was NOT provided:**

Discover skills in `{skills_output_folder}` using version-aware resolution — see `knowledge/version-paths.md` for path templates.

**Version-aware skill enumeration:**

1. **Primary: Export manifest** — Read `{skills_output_folder}/.export-manifest.json`. For each entry in `exports`, resolve the active version path: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/` — this directory must contain both `SKILL.md` and `metadata.json`.

   **Stale manifest fallback (H6):** If a manifest entry resolves to a path that does not exist (broken `active_version`, deleted version dir, missing `SKILL.md` / `metadata.json`), do NOT HALT for that single entry. Instead:
   a. Fall back to the symlink scan (rule 2) **for that one skill only**: probe `{skills_output_folder}/{skill-name}/active/{skill-name}/SKILL.md`.
   b. If the symlink-based path resolves, use it and log a warning: `"export-manifest entry '{skill-name}' is stale — resolved via active symlink instead"`.
   c. If BOTH the manifest path AND the symlink path fail, only then HALT with a manifest-corruption diagnostic naming the affected skill and pointing the user at `[SKF-update-skill]` to repair.

   **Manifest JSON parse guard (B3):** Wrap the `.export-manifest.json` parse in try/except. If JSON parsing fails for any reason, fall through entirely to the `active` symlink scan (rule 2) across all skills; log a warning and validate each symlink target exists before including it.

2. **Fallback: `active` symlinks** — If the manifest does not exist, is empty, JSON-parse fails, or an individual manifest entry fails to resolve, scan for `{skills_output_folder}/*/active/*/SKILL.md`. Each match resolves to a skill package at `{skills_output_folder}/{skill-name}/active/{skill-name}/` (the `{active_skill}` template). Verify the active symlink target actually exists and contains both `SKILL.md` and `metadata.json`.

**Filter & cycle guard (B4):** Skip any skill where the filter below matches:

- Skill name equals `{project_name}-stack`, OR
- `metadata.json` has `"skill_type": "stack"`, OR
- `metadata.json` is missing or unreadable (treat `skill_type: unknown` as non-loadable — exclude to avoid loading a partially-written or self-referential skill).

Maintain a **visited set keyed by `skill_dir`** (the top-level dir under `{skills_output_folder}`) while resolving. If a skill would be revisited via a circular reference (e.g., a constituent that claims another stack as dependency), skip the duplicate and log a warning `"cycle detected at {skill_dir} — skipping"`. Stack skills must not be loaded as source dependencies to avoid self-referencing loops.

**If zero skills remain after filtering:** HALT with: "**Cannot proceed in compose-mode.** No individual skills found in `{skills_output_folder}` (after filtering stack skills). Run [CS] Create Skill or [QS] Quick Skill to generate individual skills first, then re-run [SS]."

For each skill found:
1. Read `metadata.json` from the resolved version-aware path (`{skill_package}` or `{active_skill}`). **Skill-type gate (S1):** the sibling `metadata.json` MUST be present AND parseable AND contain a `skill_type` field whose value is one of the known set (`skill`, `stack`, or any future values explicitly recognised by this workflow). Directories lacking a qualifying `metadata.json`/`skill_type` are NOT treated as skills — log `"{dir_name}: not a skill (no valid metadata.json/skill_type) — excluding"` and skip.
2. Extract: name, language, confidence_tier, source_repo, exports count, version
3. Store the skill group directory name as `skill_dir` (the top-level name under `{skills_output_folder}`, distinct from `name` — the directory may differ from the metadata name)
4. Store the resolved package path as `skill_package_path` for use in later steps
5. **Hash the constituent metadata at read-time (S13):** compute `sha256` of the raw `metadata.json` bytes just read, and store it in workflow state as `metadata_hash` alongside `skill_package_path`. Step-07 uses this stored hash (not a re-read) for `constituents[].metadata_hash` in `provenance-map.json`, so drift between step 2 read and step 7 write is captured.
6. Store as `raw_dependencies` with source: "existing_skill"

Display:
"**Loaded {N} existing skills as dependencies.**

| Skill | Language | Tier | Exports | Source |
|-------|----------|------|---------|--------|
| {name} | {lang} | {tier} | {count} | {repo} |

**Proceeding to scope confirmation...**"

Skip to [Auto-Proceed to Next Step](#5-auto-proceed-to-next-step) — the skills table above serves as the detection summary.

**If not compose_mode:** Continue with section 1 (existing flow).

### 1. Check for Explicit Dependency List

**If `explicit_deps` was provided in step 01:**

"**Using provided dependency list.** Skipping manifest auto-detection.

**Dependencies:** {explicit_deps_count} libraries provided"

Store the explicit list as `raw_dependencies` and skip to [Display Detection Summary](#4-display-detection-summary).

**If no explicit list:** Continue to section 2.

### 2. Scan and Parse Manifests

Invoke the deterministic manifest scanner — it walks the project root, parses every recognised manifest, dedupes the production dep set, and flags monorepo layout:

**Resolve `{scanManifestsHelper}`** from `{scanManifestsProbeOrder}`; first existing path wins. HALT if no candidate exists.

```bash
uv run {scanManifestsHelper} scan {scan_root}
```

Where `{scan_root}` is the project root path. Load `{manifestPatterns}` for the ecosystem reference table that documents supported filenames, dependency keys, and normalisation rules; the script implements exactly that table (npm/pnpm/yarn, python pip/poetry/pdm, rust cargo, go modules, java/kotlin maven + gradle, ruby bundler, composer, swift package manager). Exclusion patterns (`node_modules/`, `.venv/`, `vendor/`, `dist/`, `build/`, `target/`, `.git/`, hidden dirs) are applied internally.

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

**Headless auto-cancel (S2):** If `{headless_mode}` is true, do NOT wait for user input. Emit a structured error contract `{"status":"error","skill":"skf-create-stack-skill","stage":"step 2","reason":"no manifests found, headless cannot prompt"}` on stderr and exit non-zero. Headless mode cannot proceed without an explicit dependency list.

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

### 4. Display Detection Summary

"**Manifest detection complete.**

**Manifests found:** {count}
{For each manifest:}
- `{file_path}` ({ecosystem}) — {dep_count} dependencies

**Total unique dependencies:** {total_count}
- Runtime: {runtime_count}
- Dev-only: {dev_count}

**Proceeding to dependency ranking...**"

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

