---
nextStepFile: 'report.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
# Resolve `{skillInventoryHelper}` by probing `{skillInventoryProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §1 runs its write check before any directory is
# created; without it, §1 writes only into a skill folder that does not exist yet.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — the active-symlink flip and registry
# writes below go through the atomic helper for concurrency safety.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's
# index folders and SKF's workspace lock out of git, and undoes the
# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path
# exists, skip the call and continue: it never gates the workflow.
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
# Resolve `{forgeTierRwHelper}` by probing `{forgeTierRwProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — §6b's ccc-index registry round-trip is
# comment-preserving and has no prose fallback.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
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

### 1. Check Ownership, Then Create Directory Structure

`{name}` is the skill name from the brief (kebab-case). `{version}` is the working version: the brief's `version`, unless step 3's source resolution replaced it with `target_version` or the detected source version (`source-resolution-protocols.md` "Version Reconciliation"), with build metadata stripped per `knowledge/version-paths.md`.

**Ownership check.** Run it before creating any directory, `{forge_version}` included. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

`--forge-data-folder` only tells the helper whether both settings name one folder, so the brief and forge files there count as SKF output.

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder` and `{write_detail}` ← `write_check.detail`. Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{name}` is not SKF output — nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{name}` yourself, and set a different `name` in the brief to create this skill beside it. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted create-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}".

Each refusal is a HARD HALT. Nothing was written, so under `{headless_mode}` emit the stderr envelope per `references/report.md` "Result Contract on HARD HALT" with `status: "failed"`, `phase: "generate-artifacts"`, `summary.halt_reason` as shown, `summary.evidence_report: null` and `skill_package: null`, and write no result file: `{forge_version}` does not exist yet. In `--batch` mode, before halting, update `{sidecar_path}/batch-state.yaml` as `references/report.md` §5 describes, with `current_index` set to the next brief and `{skill: "{name}", brief: "<brief path>", halt_reason: "<reason>"}` appended to `refused`; when this was the last brief, set `batch_active: false` instead. The next `--batch` run then resumes with the next brief instead of refusing this one again.

Then create the following directories:

```
{skill_group}                          # {skills_output_folder}/{name}/
{skill_package}                        # {skills_output_folder}/{name}/{version}/{name}/
{skill_package}/references/
{forge_version}                        # {forge_data_folder}/{name}/{version}/
```

If `scripts_inventory` is non-empty, also create: `{skill_package}/scripts/`
If `assets_inventory` is non-empty, also create: `{skill_package}/assets/`

Existing directories are fine: the ownership check accepted them, so the files below overwrite same-named files in them.

### 2. Write Deliverables to {skill_package}

Write File 3 (`metadata.json`) first, so a run interrupted mid-write leaves a package that carries the SKF marker, which the next run's ownership check accepts.

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

Promoted docs are tracked in `file_entries[]` with `file_type: "doc"` for drift detection but are **not** copied into the skill package. The source file remains at its original location outside `{skill_package}`. Step-07 must skip any `file_entries[]` row where `file_type == "doc"` when iterating for file copy — these entries exist only for provenance tracking, not bundling. Step-07 verification (§5) also does not check for doc files in the skill package.

### 3. Write Workspace Artifacts to {forge_version}

Write these 3 files from the compiled content:

**File 5:** `{forge_version}/provenance-map.json`
- Per-claim source map with AST bindings and confidence tiers

**File 6:** `{forge_version}/evidence-report.md`
- Build artifact with extraction summary, validation results, warnings
- Its `## Remaining Warnings` also lists, once each, the notices earlier steps kept for it: `{temporal_feeder_notice}` when step 5c set it (the Deep-tier temporal feeder held no files), and the skipped authoritative-files scan when step 3 §2a recorded `authoritative_files_scan.not_scanned` (a remote source that was never cloned; the `skipped` count of candidates the user skipped is not a warning)

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

Do not `rm` + `ln -s` the active link by hand. The bare-rm pattern has two failure modes: (1) a concurrent reader sees a missing `active` mid-flip, and (2) a bug or typo that replaces `{skill_group}/active` with a plain directory turns the next manual `rm -rf {skill_group}/active` into data loss. The helper encapsulates both guards.

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
- If QMD collection creation fails: log the error, note that indexing can be retried via [SF] setup. Do not fail the workflow.
- If forge-tier.yaml update fails: log the error, continue. The collection exists in QMD even if the registry entry failed.

**IF forge tier is not Deep:** Skip this section silently. No messaging.

### 6b. CCC Index Registry Registration (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml (Forge+ or Deep with ccc available):**

Ensure the source path used for extraction is indexed by ccc and registered in the `ccc_index_registry` array.

**Index verification:**

**Working-directory contract:** `ccc init`, `ccc index`, and `ccc status` take **no positional path argument** — each operates on the current working directory, and passing a path makes them exit non-zero with `Got unexpected extra argument`. Run them from `{source_root}` (`cd {source_root} && ccc …`, the same form `extract.md` step 2b and `knowledge/ccc-bridge.md` use), then return to `{project-root}` before the registry update below, which resolves `{forgeTierConfig}` relative to the project.

**Project root without settings:** check this before running any ccc command. When `{source_root}` is `{project-root}` and `{project-root}/.cocoindex_code/settings.yml` does not exist, do not run `ccc init` or `ccc index` — `/skf-setup` initializes the project index with the SKF exclusions, and in a project nested inside another git checkout `ccc index` would index the enclosing repository instead. Skip the rest of this section, including the registry update, note that re-running `/skf-setup` enables the index, and continue to §7.

Otherwise, `ccc index` requires the directory to be initialized first. Run `cd "{source_root}" && ccc init` (idempotent — a no-op once initialized) before `cd "{source_root}" && ccc index`, or use the ccc MCP tool. `ccc_bridge.ensure_index` is a conceptual interface, not a callable function. Indexing is a no-op if the source was already indexed during setup or step 2b.

**Nested project marker:** when `{source_root}` is a folder inside a git checkout whose `.git` is a folder, or inside a folder that holds `.cocoindex_code/settings.yml` — a local source such as `./packages/lib`, or a linked worktree or submodule inside such a checkout, whose `.git` file ccc does not count as a marker — `ccc init` exits non-zero with `A parent directory has a project marker`. This is expected — re-run as `cd {source_root} && ccc init -f` to initialize at the subtree anyway, then `ccc index`. Do not treat the parent-marker warning as fatal. ccc writes no `.gitignore` entry for such a project; **Keep the index out of git** below covers it.

**Verify the index is not degraded:** after `ccc index`, run `cd "{source_root}" && ccc status`. If it prints an `Indexing in progress:` line, a pass is still running and the counts below it are not final: run `cd "{source_root}" && ccc index` again, which waits for the running pass to finish and then makes a quick incremental pass, then run `ccc status` again. If the line is still there after 3 such runs, log "index unverified", skip the language check and the repairs below, and continue with **Keep the index out of git**. Once the line is gone, read the `Languages:` breakdown — a non-zero `Chunks`/`Files` total is not sufficient. Confirm the source's primary language (`{brief.language}`) reports a non-trivial chunk count. An index dominated by `markdown`/config chunks with the source language absent or near-zero means the source code was never indexed, which silently cripples later `skf-audit-skill` / `skf-update-skill` searches with no error surfaced. When the source language is absent, apply these repairs in order, stopping at the first one after which `Languages:` shows the source language:

1. **No project of its own:** `{source_root}/.cocoindex_code/settings.yml` is missing and the `Project:` line of `ccc status` names another folder, so ccc indexed an enclosing project. Run `cd "{source_root}" && ccc init -f`, then `ccc index`, then run `ccc status` and check `Languages:` again.
2. **Language not included:** ccc indexes only the file types listed in `include_patterns`, and its default list leaves some languages out (Elixir's `.ex`, for example). Take the extensions of the `{brief.language}` files in the step 3 filtered file list that no `include_patterns` entry matches, at most 3. If there are none, the files are excluded rather than left out of `include_patterns`: skip this repair and log which `exclude_patterns` entry covers the `{brief.language}` source files. For the extensions found:
   - When `{remote_clone_path}` is set and `{source_root}` is inside it (a clone SKF made), append one single-quoted `- '**/*.{ext}'` item per extension (YAML reads an unquoted leading `*` as an alias, and ccc then fails to load the file) to the existing `include_patterns` list in `{source_root}/.cocoindex_code/settings.yml`, keeping every entry. If the file has no `include_patterns` list, add nothing: a list written from scratch replaces ccc's default file types. Display "Added {patterns} to include_patterns in {source_root}/.cocoindex_code/settings.yml so ccc indexes {brief.language} files.", run a plain `cd "{source_root}" && ccc index`, then run `ccc status` and check `Languages:` again.
   - Otherwise the settings belong to the user's project, so do not edit them. Display that ccc did not index `{brief.language}` files, and the exact lines to add under `include_patterns` in `{source_root}/.cocoindex_code/settings.yml` (one `- '**/*.{ext}'` line per extension), followed by a plain `ccc index`.

A plain `ccc index` is enough after any `settings.yml` edit; nothing needs deleting first. Do not run `ccc reset`: it deletes only the index databases and keeps `settings.yml`, so it cannot repair the settings, a `ccc index` right after it can fail and leave the project with no index, and run from a folder without its own `settings.yml` it deletes the enclosing project's index. If the source language is still missing after these repairs, log it and continue per the error handling below — a degraded index is not workflow-fatal, but it must be recorded so the gap is visible.

**Keep the index out of git:** once the ccc commands above are done — after the repairs, after "index unverified", or after a ccc command failed — return to `{project-root}` and resolve `{cccGitHygieneHelper}` from `{cccGitHygieneProbeOrder}`; first existing path wins. If no candidate exists, or the helper exits non-zero or prints no JSON, log "ccc git hygiene skipped" and continue to the registry update: this check never fails the workflow.

- **Workspace clone** (`remote_clone_type` is `"workspace"`, so `{source_root}` is `{remote_clone_path}`): run `uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"`. It undoes the edit a `ccc init` or `ccc index` made to the clone's tracked `.gitignore` and keeps the index folder out of git through the clone's `.git/info/exclude`, so a later checkout of another ref is not blocked. Read nothing from its output.
- **Local source** (`{remote_clone_path}` is not set): run `uv run {cccGitHygieneHelper} nested --dir "{source_root}" --project-root "{project-root}"`. ccc gitignores its index only at the top of a git checkout whose `.git` is a folder, so for a project in a subfolder of a checkout (the `ccc init -f` case above), a linked worktree or a submodule, `git status` lists the index database and a `git add -A` would commit it. When git does not ignore `{source_root}/.cocoindex_code/`, the helper writes a `.gitignore` holding `*` inside that folder so the folder ignores itself; SKF never edits a project's own `.gitignore`. It also repairs a nested index an earlier run left, and does nothing for `{project-root}` itself, for a folder without `.cocoindex_code/settings.yml`, or outside a git work tree. Bind `{ccc_ignore_notice}` ← `notice` and display `{ccc_ignore_notice}` verbatim when it is not null: its remedy command is quoted for paths with spaces.

An ephemeral clone matches neither case: it is deleted after extraction.

**Registry update:**

**Resolve `{forgeTierRwHelper}`** from `{forgeTierRwProbeOrder}`; first existing path wins. HALT if no candidate exists.

Register the indexed source path via `register-ccc-index` — a comment-preserving round-trip on `forge-tier.yaml`. This differs from §6, which mutates the registry with an inline read→modify→atomic-write under `flock`; here the helper owns the read→modify→write internally so the `ccc_index_registry` deduplication logic stays in the script. Acquire an exclusive `flock` on `{sidecar_path}/forge-tier.yaml.lock`, then:

```bash
echo '{"source_repo":"{brief.source_repo}","path":"{source_root}","skill_name":"{name}","indexed_at":"{current ISO date}","source_workflow":"create-skill"}' \
  | uv run {forgeTierRwHelper} register-ccc-index --target {forgeTierConfig}
```

Deduplicates by `source_repo` + `skill_name` (not local `path`, which may be ephemeral). Release the lock after the command completes. If `flock` is unavailable, fall back to read-CAS-by-mtime.

**Error handling:** If ccc indexing or registry update fails, log and continue — do not fail the workflow.

**IF `tools.ccc` is false:** Skip this section silently.

### 7. Auto-Proceed

No user interaction. Once all 7 files are written and verified (and optionally indexed into QMD), load `{nextStepFile}`, read it fully, then execute it. A QMD-indexing failure does not block; a file-write failure halts (§5) rather than proceeding with partial output.

