---
nextStepFile: 'report.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — the active-symlink flip and registry
# writes below MUST go through the atomic helper for concurrency safety.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Generate Artifacts

## STEP GOAL:

To write all compiled content to disk — 4 deliverable files to `{skill_package}` and 3 workspace artifacts to `{forge_version}`, creating directories as needed. Then create or update the `active` symlink.

## Rules

- Focus only on writing files from compiled content — do not modify content during writing
- All base artifact types must be written (4 deliverables + 3 workspace files + N reference files)
- Create directories before writing files

## MANDATORY SEQUENCE

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

**Note on `file_type: "doc"` entries** (promoted authoritative docs from step 3 §2a):

Promoted docs are tracked in `file_entries[]` with `file_type: "doc"` for drift detection but are **NOT** copied into the skill package. The source file remains at its original location outside `{skill_package}`. Step-07 must skip any `file_entries[]` row where `file_type == "doc"` when iterating for file copy — these entries exist only for provenance tracking, not bundling. Step-07 verification (§5) also does not check for doc files in the skill package.

### 3. Write Workspace Artifacts to {forge_version}

Write these 3 files from the compiled content:

**File 5:** `{forge_version}/provenance-map.json`
- Per-claim source map with AST bindings and confidence tiers

**File 6:** `{forge_version}/evidence-report.md`
- Build artifact with extraction summary, validation results, warnings

**File 7:** `{forge_version}/extraction-rules.yaml`
- Language and ast-grep schema used for this extraction (for reproducibility)
- Note: This file is generated here from extraction data collected during steps 3-4, not assembled in step 5

### 4. Create Active Symlink (atomic flip)

Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}` using the shared atomic-flip helper. The helper holds an `flock` on `{skill_group}/active.skf-lock`, refuses to replace a non-symlink at `{skill_group}/active` (protecting against accidental rm-rf of a real directory), and uses a rename-over-symlink pattern so the update is atomic from a concurrent reader's perspective:

```bash
python3 {atomicWriteHelper} flip-link \
  --link {skill_group}/active \
  --target {version}
```

The helper returns non-zero (exit 2) if `{skill_group}/active` already exists as a real directory or file rather than a symlink — in that case, halt with: "Refusing to flip `{skill_group}/active` — existing path is not a symlink. Investigate manually; expected a symlink pointing at a version directory."

**Never `rm` + `ln -s` the active link manually.** The bare-rm pattern has two failure modes: (1) a concurrent reader sees a missing `active` mid-flip, and (2) a bug or typo that replaces `{skill_group}/active` with a plain directory turns the next manual `rm -rf {skill_group}/active` into data loss. The helper encapsulates both guards.

### 5. Verify Write Completion

After all files are written, verify:
- All 4 deliverable artifact types exist (SKILL.md, context-snippet.md, metadata.json, **and** either at least one file in `references/` **or** `references/` is empty AND Tier-2 content is inline in SKILL.md — see "Empty `references/` exception" below), all 3 workspace artifacts exist (provenance-map.json, evidence-report.md, extraction-rules.yaml), plus scripts/ and assets/ files when inventories are non-empty
- The `active` symlink at `{skill_group}/active` resolves to `{version}`
- Store `ref_count` = count of files written to `references/` for use in step 8 report
- List each file with its path and size

**Empty `references/` exception (Tier-2 inline):** `ref_count == 0` is a valid completion state when step 6 kept Tier-2 content inline in SKILL.md — e.g., the body was already under the size limit, or `skill-check` was unavailable and the manual fallback (step 6 §3) skipped the split. In that case, append a single line to `{forge_version}/evidence-report.md` recording the inline state so downstream tooling and audits can distinguish "inline by design" from "split-body skipped due to error":

```
ref_count: 0  # Tier-2 kept inline in SKILL.md (no split performed in step 6)
```

When `ref_count > 0` is expected (because step 6 ran a split) but no files were written, halt with: "Split-body produced zero reference files. Investigate step 6 output before retrying — empty `references/` after a split is never a valid state."

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
qmd embed --collection {name}-extraction  # generates vector embeddings for semantic (vec) and HyDE query sub-types; scope to this collection to avoid re-embedding others. If the installed qmd CLI lacks --collection, gate the embed behind a per-skill freshness check (skip when the existing {name}-extraction entry is within 24 hours — rationale: an unscoped embed re-runs over every collection, which in a populated QMD store can cost minutes of GPU time per create-skill run; 24 hours is long enough to absorb rapid re-forges from the same brief without losing meaningful content freshness) and warn in evidence-report.
```

**Registry update:**

Read `{forgeTierConfig}` and update the `qmd_collections` array **under an exclusive `flock` on `{sidecar_path}/forge-tier.yaml.lock`** (see step 3b §4 for the full pattern — acquire lock → read → modify → atomic write via `skf-atomic-write.py write` → release). If `flock` is unavailable, fall back to read-CAS-by-mtime.

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

Dispatch to ccc CLI (`ccc index {source_root}`) or ccc MCP tool — `ccc_bridge.ensure_index` is a conceptual interface, not a callable function. This is a no-op if the source was already indexed during setup or step 2b.

**Registry update:**

Read `{forgeTierConfig}` and update the `ccc_index_registry` array **under an exclusive `flock` on `{sidecar_path}/forge-tier.yaml.lock`** (same pattern as §6 — acquire lock → read → modify → atomic write via `skf-atomic-write.py write` → release). If `flock` is unavailable, fall back to read-CAS-by-mtime.

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

