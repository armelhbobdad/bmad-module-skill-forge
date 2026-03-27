---
name: 'step-02-detect-manifests'
description: 'Scan project for dependency manifests and extract raw dependency list'

nextStepFile: './step-03-rank-and-confirm.md'
manifestPatterns: '../data/manifest-patterns.md'
---

# Step 2: Detect Manifests

## STEP GOAL:

Scan the project root for dependency manifest files, parse each to extract dependency names and versions, and produce a raw dependency list for ranking.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a dependency analyst operating in Ferris Architect mode
- ✅ Prescriptive precision — report exactly what was found, nothing assumed
- ✅ Zero hallucination — only list dependencies actually present in manifest files

### Step-Specific Rules:

- 🎯 Focus ONLY on finding and parsing manifest files
- 🚫 FORBIDDEN to count imports or rank dependencies — that is step 03
- 🚫 FORBIDDEN to extract library documentation — that is step 04
- 💬 If explicit dependency list was provided in step 01, use it and skip detection

## EXECUTION PROTOCOLS:

- 🎯 Load manifest-patterns.md for detection rules
- 💾 Store manifests found and raw dependency list as workflow state
- 📖 Auto-proceed to step 03 after successful detection
- 🚫 HALT if no manifests found and no explicit list provided — **unless `compose_mode` is true** (compose mode skips manifest detection)

## CONTEXT BOUNDARIES:

- From step 01: forge tier, available tools, optional explicit_deps, project_root
- This step produces: manifests[], raw_dependencies[]
- Does NOT rank, filter, or analyze — just detect and parse

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 0. Check Compose Mode

**If `compose_mode` is true AND `explicit_deps` was provided in step 01:**

Use the explicit dependency list directly. Store the explicit list as `raw_dependencies` with `source: "explicit"` and skip to [Auto-Proceed to Next Step](#5-auto-proceed-to-next-step).

**If `compose_mode` is true AND `explicit_deps` was NOT provided:**

Scan `{skills_output_folder}` for subdirectories containing SKILL.md and metadata.json.

**Filter:** Skip any subdirectory named `{project_name}-stack` or any skill where `metadata.json` has `"skill_type": "stack"` — stack skills must not be loaded as source dependencies to avoid self-referencing loops.

**If zero skills remain after filtering:** HALT with: "**Cannot proceed in compose-mode.** No individual skills found in `{skills_output_folder}` (after filtering stack skills). Run [CS] Create Skill or [QS] Quick Skill to generate individual skills first, then re-run [SS]."

For each skill found:
1. Read metadata.json
2. Extract: name, language, confidence_tier, source_repo, exports count, version
3. Store the subdirectory name as `skill_dir` (distinct from `name` — the directory may differ from the metadata name)
4. Store as `raw_dependencies` with source: "existing_skill"

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All manifest files in project root detected
- Each manifest parsed with dependency names extracted
- Runtime vs dev-only categorization applied
- Deduplication across multiple manifests completed
- Detection summary displayed with accurate counts
- Auto-proceeded to step 03

### ❌ SYSTEM FAILURE:

- Missing manifest files that exist in the project
- Inventing dependencies not in manifest files
- Starting to rank or analyze dependencies (step 03's job)
- Not halting when no manifests found
- Displaying A/P menu (this is auto-proceed)

**Master Rule:** Detect and parse only. No ranking, no filtering, no analysis.
