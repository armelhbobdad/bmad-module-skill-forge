---
nextStepFile: './step-08-report.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
---

# Step 7: Generate Artifacts

## STEP GOAL:

To write all compiled content to disk — 4 deliverable files to `{skill_package}` and 3 workspace artifacts to `{forge_version}`, creating directories as needed. Then create or update the `active` symlink.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing artifact generation
- ✅ All content was assembled in step-05 and validated in step-06
- ✅ This step ONLY writes — it does not modify, compile, or validate content

### Step-Specific Rules:

- 🎯 Focus ONLY on writing files from the compiled content in context
- 🚫 FORBIDDEN to modify content during writing — write exactly what was compiled
- 🚫 FORBIDDEN to skip any artifact — all base artifact types must be written (4 deliverables + 3 workspace files + N reference files)
- 💬 Report each file written with its path
- 📁 Create directories before writing files

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Write files using the compiled content from context
- 📖 Create directory structure first, then write files
- 🚫 Halt with error if a file write fails — do not continue with partial output

## CONTEXT BOUNDARIES:

- Available: All compiled content from step-05, validation results from step-06, source_root from step-01 (needed for section 5b CCC registration)
- Focus: File system operations — create directories, write files
- Limits: Do NOT modify content during writing
- Dependencies: All content must be compiled and validated in context
- Path resolution: See `knowledge/version-paths.md` for canonical path templates (`{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Create Directory Structure

Resolve `{version}` from the skill brief's `version` field. Create the following directories:

```
{skill_group}                          # {skills_output_folder}/{name}/
{skill_package}                        # {skills_output_folder}/{name}/{version}/{name}/
{skill_package}/references/
{forge_version}                        # {forge_data_folder}/{name}/{version}/
```

If `scripts_inventory` is non-empty, also create: `{skill_package}/scripts/`
If `assets_inventory` is non-empty, also create: `{skill_package}/assets/`

Where `{name}` is the skill name from the brief (kebab-case) and `{version}` is the semver version from the brief (with build metadata stripped per `knowledge/version-paths.md`).

If directories already exist, do not error — proceed with file writing (overwrites existing files).

### 2. Write Deliverables to {skill_package}

Write these 4 files from the compiled content:

**File 1:** `{skill_package}/SKILL.md`
- The complete compiled skill document
- agentskills.io-compliant format with all sections
- [MANUAL] markers seeded

**File 2:** `{skill_package}/context-snippet.md`
- Compressed 2-line format for CLAUDE.md integration

**File 3:** `{skill_package}/metadata.json`
- Machine-readable birth certificate with stats and provenance

**File 4:** `{skill_package}/references/*.md`
- One file per function group or type
- Progressive disclosure detail files

**Files 4b (conditional):** `{skill_package}/scripts/*`
- One file per detected script, copied from source with content preserved
- Only created when `scripts_inventory` is non-empty

**Files 4c (conditional):** `{skill_package}/assets/*`
- One file per detected asset, copied from source with content preserved
- Only created when `assets_inventory` is non-empty

### 3. Write Workspace Artifacts to {forge_version}

Write these 3 files from the compiled content:

**File 5:** `{forge_version}/provenance-map.json`
- Per-claim source map with AST bindings and confidence tiers

**File 6:** `{forge_version}/evidence-report.md`
- Build artifact with extraction summary, validation results, warnings

**File 7:** `{forge_version}/extraction-rules.yaml`
- Language and ast-grep schema used for this extraction (for reproducibility)

### 4. Create Active Symlink

Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}`:

```
{skill_group}/active -> {version}
```

If the symlink already exists, remove it first and recreate. This ensures `{skill_group}/active/{name}/` resolves to the just-written skill package.

### 5. Verify Write Completion

After all files are written, verify:
- All 4 deliverable artifact types exist (SKILL.md, context-snippet.md, metadata.json, at least one file in references/), all 3 workspace artifacts exist (provenance-map.json, evidence-report.md, extraction-rules.yaml), plus scripts/ and assets/ files when inventories are non-empty
- The `active` symlink at `{skill_group}/active` resolves to `{version}`
- Store `ref_count` = count of files written to `references/` for use in step-08 report
- List each file with its path and size

**If any write failed:**
Halt with: "Artifact generation failed: could not write `{file_path}`. Check permissions and disk space."

**If all writes succeeded:**
Display brief confirmation:

"**Artifacts generated.**

**Deliverables ({skill_package}):**
- SKILL.md
- context-snippet.md
- metadata.json
{if scripts: - scripts/ ({scripts_count} files)}
{if assets: - assets/ ({assets_count} files)}
- references/ ({reference_count} files)

**Workspace ({forge_version}):**
- provenance-map.json
- evidence-report.md
- extraction-rules.yaml

**Symlink:** {skill_group}/active -> {version}

Proceeding to compilation report..."

### 6. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:**

Index the generated skill artifacts into a QMD collection so that audit-skill and update-skill can perform high-signal searches against curated extraction data instead of raw source files.

**Collection creation:** Create (or replace) a QMD collection from the skill artifacts:
```bash
qmd collection remove {name}-extraction 2>/dev/null  # no-op if new
qmd collection add {skill_package} --name {name}-extraction --mask "**/*"
qmd embed  # generates vector embeddings for vector_search/deep_search
```

**Registry update:**

Read `{forgeTierConfig}` and update the `qmd_collections` array.

If an entry with `name: "{name}-extraction"` already exists, replace it. Otherwise, append:

```yaml
  - name: "{name}-extraction"
    type: "extraction"
    source_workflow: "create-skill"
    skill_name: "{name}"
    created_at: "{current ISO date}"
```

Write the updated forge-tier.yaml.

**Error handling:**
- If QMD collection creation fails: log the error, note that indexing can be retried via [SF] setup. Do NOT fail the workflow.
- If forge-tier.yaml update fails: log the error, continue. The collection exists in QMD even if the registry entry failed.

**IF forge tier is NOT Deep:** Skip this section silently. No messaging.

### 6b. CCC Index Registry Registration (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml (Forge+ or Deep with ccc available):**

Ensure the source path used for extraction is indexed by ccc and registered in the `ccc_index_registry` array.

**Index verification:**

Dispatch to ccc CLI (`ccc index {source_root}`) or ccc MCP tool — `ccc_bridge.ensure_index` is a conceptual interface, not a callable function. This is a no-op if the source was already indexed during setup or step-02b.

**Registry update:**

Read `{forgeTierConfig}` and update the `ccc_index_registry` array.

Deduplicate by `source_repo` + `skill_name` (NOT local `path`, which may be ephemeral). Replace existing match or append:

```yaml
  - source_repo: "{brief.source_repo}"
    path: "{source_root}"
    skill_name: "{name}"
    indexed_at: "{current ISO date}"
    source_workflow: "create-skill"
```

Write the updated forge-tier.yaml.

**Error handling:** If ccc indexing or registry update fails, log and continue — do NOT fail the workflow.

**IF `tools.ccc` is false:** Skip this section silently.

### 7. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After all artifacts are written, verified, and optionally indexed into QMD, immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed file writing step with no user choices
- All 7 files must be written before proceeding
- QMD indexing failure does NOT block proceeding
- File write failures are real errors — halt, do not proceed with partial output
- Proceed directly to next step after successful generation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 7 artifact files are written, the active symlink is created, and verification is complete will you proceed to load `{nextStepFile}` for the compilation report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Directory structure created ({skill_group}, {skill_package}, {forge_version})
- All 4 deliverable files written to {skill_package}
- All 3 workspace artifact files written to {forge_version}
- Active symlink created at {skill_group}/active -> {version}
- Write completion verified — all 7 files exist and symlink resolves
- Deep tier: QMD collection `{name}-extraction` created/updated and registered in forge-tier.yaml
- Non-Deep tier: QMD indexing skipped silently
- Brief confirmation displayed with file list
- Auto-proceeded to step-08

### ❌ SYSTEM FAILURE:

- Modifying content during the write step
- Skipping any of the 7 required files
- Proceeding with partial output if a write fails
- Not creating directories before writing
- Not verifying all files were written
- Failing the workflow due to QMD indexing errors (should degrade gracefully)

**Master Rule:** This step writes artifacts, creates the active symlink, and registers QMD collections. All content was compiled and validated in previous steps. Write faithfully, verify completely. QMD indexing failures never block the workflow.
