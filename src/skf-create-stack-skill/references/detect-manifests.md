---
nextStepFile: 'rank-and-confirm.md'
manifestPatterns: 'references/manifest-patterns.md'
---

# Step 2: Detect Manifests

## STEP GOAL:

Scan the project root for dependency manifest files, parse each to extract dependency names and versions, and produce a raw dependency list for ranking.

## Rules

- Focus only on finding and parsing manifest files
- Do not count imports or rank dependencies (Step 03) or extract documentation (Step 04)
- If explicit dependency list was provided in step 01, use it and skip detection

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

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

### 2. Scan for Manifest Files

Load `{manifestPatterns}` for supported ecosystem detection patterns.

Scan the project root (depth 0-1) for manifest files, **excluding directories listed in the Scan Exclusion Patterns section of `{manifestPatterns}`**:

- Search for each supported manifest filename
- Record: file path, ecosystem type, file size
- **Apply exclusion patterns** from `{manifestPatterns}` — skip `node_modules/`, `.venv/`, `vendor/`, `dist/`, `build/`, `target/`, `.git/`, and all hidden directories when globbing
- Note any unusual structures (monorepo with multiple manifests, workspace configurations)

**If no manifest files found:**

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

### 3. Parse Each Manifest

For each discovered manifest file:

1. Read the file contents
2. Extract dependency names and version constraints using ecosystem-specific parsing:
   - JSON manifests: parse dependencies/devDependencies keys
   - TOML manifests: parse [dependencies] sections
   - Text manifests: parse line-by-line (name==version or name>=version)
   - XML manifests: parse dependency elements
   - Gradle: parse implementation/api/compile declarations
3. Categorize: runtime vs dev-only
4. Normalize dependency names across ecosystems

Deduplicate dependencies found across multiple manifests.

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

