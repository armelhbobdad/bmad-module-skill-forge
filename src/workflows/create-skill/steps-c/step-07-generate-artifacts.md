---
name: 'step-07-generate-artifacts'
description: 'Write all output files — 4 deliverables to skills/ and 3 workspace artifacts to forge-data/'
nextStepFile: './step-08-report.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
---

# Step 7: Generate Artifacts

## STEP GOAL:

To write all compiled content to disk — 4 deliverable files to `{skills_output_folder}/{name}/` and 3 workspace artifacts to `{forge_data_folder}/{name}/`, creating directories as needed.

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

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Create Directory Structure

Create the following directories:

```
{skills_output_folder}/{name}/
{skills_output_folder}/{name}/references/
{forge_data_folder}/{name}/
```

If `scripts_inventory` is non-empty, also create: `{skills_output_folder}/{name}/scripts/`
If `assets_inventory` is non-empty, also create: `{skills_output_folder}/{name}/assets/`

Where `{name}` is the skill name from the brief (kebab-case).

If directories already exist, do not error — proceed with file writing (overwrites existing files).

### 2. Write Deliverables to {skills_output_folder}/{name}/

Write these 4 files from the compiled content:

**File 1:** `{skills_output_folder}/{name}/SKILL.md`
- The complete compiled skill document
- agentskills.io-compliant format with all sections
- [MANUAL] markers seeded

**File 2:** `{skills_output_folder}/{name}/context-snippet.md`
- Compressed 2-line format for CLAUDE.md integration

**File 3:** `{skills_output_folder}/{name}/metadata.json`
- Machine-readable birth certificate with stats and provenance

**File 4:** `{skills_output_folder}/{name}/references/*.md`
- One file per function group or type
- Progressive disclosure detail files

**Files 4b (conditional):** `{skills_output_folder}/{name}/scripts/*`
- One file per detected script, copied from source with content preserved
- Only created when `scripts_inventory` is non-empty

**Files 4c (conditional):** `{skills_output_folder}/{name}/assets/*`
- One file per detected asset, copied from source with content preserved
- Only created when `assets_inventory` is non-empty

### 3. Write Workspace Artifacts to {forge_data_folder}/{name}/

Write these 3 files from the compiled content:

**File 5:** `{forge_data_folder}/{name}/provenance-map.json`
- Per-claim source map with AST bindings and confidence tiers

**File 6:** `{forge_data_folder}/{name}/evidence-report.md`
- Build artifact with extraction summary, validation results, warnings

**File 7:** `{forge_data_folder}/{name}/extraction-rules.yaml`
- Language and ast-grep schema used for this extraction (for reproducibility)

### 4. Verify Write Completion

After all files are written, verify:
- All 4 deliverable artifact types exist (SKILL.md, context-snippet.md, metadata.json, at least one file in references/), all 3 workspace artifacts exist (provenance-map.json, evidence-report.md, extraction-rules.yaml), plus scripts/ and assets/ files when inventories are non-empty
- Store `ref_count` = count of files written to `references/` for use in step-08 report
- List each file with its path and size

**If any write failed:**
Halt with: "Artifact generation failed: could not write `{file_path}`. Check permissions and disk space."

**If all writes succeeded:**
Display brief confirmation:

"**Artifacts generated.**

**Deliverables ({skills_output_folder}/{name}/):**
- SKILL.md
- context-snippet.md
- metadata.json
{if scripts: - scripts/ ({scripts_count} files)}
{if assets: - assets/ ({assets_count} files)}
- references/ ({reference_count} files)

**Workspace ({forge_data_folder}/{name}/):**
- provenance-map.json
- evidence-report.md
- extraction-rules.yaml

Proceeding to compilation report..."

### 5. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:**

Index the generated skill artifacts into a QMD collection so that audit-skill and update-skill can perform high-signal searches against curated extraction data instead of raw source files.

**Collection creation:** Create (or replace) a QMD collection from the skill artifacts:
```bash
qmd collection remove {name}-extraction 2>/dev/null  # no-op if new
qmd collection add {skills_output_folder}/{name} --name {name}-extraction --mask "**/*"
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
- If QMD collection creation fails: log the error, note that indexing can be retried via [SF] setup-forge. Do NOT fail the workflow.
- If forge-tier.yaml update fails: log the error, continue. The collection exists in QMD even if the registry entry failed.

**IF forge tier is NOT Deep:** Skip this section silently. No messaging.

### 5b. CCC Index Registry Registration (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml (Forge+ or Deep with ccc available):**

Ensure the source path used for extraction is indexed by ccc and registered in the `ccc_index_registry` array.

**Index verification:**

Dispatch to ccc CLI (`ccc index {source_root}`) or ccc MCP tool — `ccc_bridge.ensure_index` is a conceptual interface, not a callable function. This is a no-op if the source was already indexed during setup-forge or step-02b.

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

### 6. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After all artifacts are written, verified, and optionally indexed into QMD, immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed file writing step with no user choices
- All 7 files must be written before proceeding
- QMD indexing failure does NOT block proceeding
- File write failures are real errors — halt, do not proceed with partial output
- Proceed directly to next step after successful generation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 7 artifact files are written and verified will you proceed to load `{nextStepFile}` for the compilation report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Directory structure created ({skills_output_folder}/{name}/, {forge_data_folder}/{name}/)
- All 4 deliverable files written to {skills_output_folder}/{name}/
- All 3 workspace artifact files written to {forge_data_folder}/{name}/
- Write completion verified — all 7 files exist
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

**Master Rule:** This step writes artifacts and registers QMD collections. All content was compiled and validated in previous steps. Write faithfully, verify completely. QMD indexing failures never block the workflow.
