---
nextStepFile: 'report.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
cccIndexCheckData: 'references/ccc-index-check.md'
# Resolve `{skillInventoryHelper}` by probing `{skillInventoryProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §1 runs its write check before any directory is
# created; without it, §1 writes only into a skill folder that does not exist yet.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT (exit code 3, helper-missing) if neither resolves: the
# active-symlink flip (§4) goes through the atomic helper, so §2 resolves it
# before anything is written.
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
# path wins. §6 and §6b change the registry only through it, a
# comment-preserving round-trip with no prose fallback. If neither resolves,
# they skip the registry change with a warning: registration never halts the
# workflow.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# Resolve `{mergeCccExclusionsHelper}` to the first existing path. §6b
# prepares the settings.yml of SKF's workspace clone with it; if neither path
# exists, §6b skips the index of a remote source.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
# Resolve `{extractionInventoryHelper}` to the first existing path; HALT
# (exit code 3, helper-missing) if neither exists. §2 writes
# extraction-rules.yaml from the extraction inventory through its `rules`.
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
# Resolve `{promoteStagedHelper}` to the first existing path; HALT (exit
# code 3, helper-missing) if neither exists. §3 promotes the staged skill
# through it.
promoteStagedProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-promote-staged.py'
  - '{project-root}/src/shared/scripts/skf-promote-staged.py'
# Resolve `{sourceTreeHelper}` to the first existing path. §7 removes the
# private tree step 3 read a remote source from; if neither path exists, the
# tree stays until a later run removes it, seven days on; every HARD HALT
# also closes the tree through it (Rules).
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# HARD HALT helper (Rules).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Generate Artifacts

## STEP GOAL:

To publish the staged skill byte for byte: the deliverables to `{skill_package}` and the workspace artifacts to `{forge_version}`, through one helper that creates the folders it needs. Then create or update the `active` symlink.

## Rules

- Generate only `extraction-rules.yaml` (§2): every other file is promoted as steps 5 to 6 left it in the staging folder, never written again from what context holds
- All base artifact types must be written (3 deliverables + N reference files + 3 workspace files)
- A HARD HALT, once step 3 §2b has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Check Ownership

`{name}` is the skill name from the brief (kebab-case). `{version}` is the working version: the brief's `version`, unless step 3's source resolution replaced it with `target_version` or the detected source version (`source-resolution-protocols.md` "Version Reconciliation"), with build metadata stripped per `knowledge/version-paths.md`.

**Ownership check.** Run it before creating any directory, `{forge_version}` included. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

`--forge-data-folder` only tells the helper whether both settings name one folder, so the brief and forge files there count as SKF output.

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder`, `{write_detail}` ← `write_check.detail` and `{existing_generator}` ← `write_check.version_generated_by` (the build §3 replaces, for step 8; null when none). Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{name}` is not SKF output — nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{name}` yourself, and set a different `name` in the brief to create this skill beside it. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted create-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}".

Each refusal is a **HARD HALT** (exit code 5, `{halt_reason}`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with the `halt_reason` shown and `{write_folder}` as `"path"`. Nothing was written, and the command leaves out `--result-dir`: a result file would land in a folder SKF refuses to write.

The folders this step writes:

```
{skill_group}                          # {skills_output_folder}/{name}/
{skill_package}                        # {skills_output_folder}/{name}/{version}/{name}/
{forge_version}                        # {forge_data_folder}/{name}/{version}/
```

The promotion (§3) creates them. An existing `{skill_package}` is replaced whole: the ownership check accepted it, and a package left half from an earlier compile of this version would mix two runs. Only its hand-written `[MANUAL]` content carries forward: its blocks are in the staged SKILL.md (step 5), and §3 carries its files.

### 2. Generate extraction-rules.yaml

`extraction-rules.yaml` records the language and the ast-grep rules this extraction used, for reproducibility, and it is the one file this step generates. `{extractionInventoryHelper}` writes it from the extraction inventory step 3 §5 wrote, `{extraction_inventory}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`): its `extraction_rules` (`recipe_set`, the `recipes` ids the runner ran, its `scope` and `ast_grep_version`), its `tier` and extraction mode, and the brief's `language`. Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` and `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (§4's flip goes through it); if either has no path, **HARD HALT** (exit code 3, `helper-missing`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot generate the artifacts: {the missing script} is missing. Re-install SKF, then re-run create-skill." From `{project-root}`, write it into the staging folder, so the promotion carries it with the rest:

```bash
uv run {extractionInventoryHelper} rules --inventory "{extraction_inventory}" --language "{brief.language}" --target "<staging-skill-dir>/extraction-rules.yaml"
```

When it exits non-zero, **HARD HALT** (exit code 4, `write-failed`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with `"path"` the staged `extraction-rules.yaml`: "Cannot write extraction-rules.yaml: {the helper's message}. Check permissions and disk space." Nothing has been promoted yet.

### 3. Promote the Staged Skill

Resolve `{promoteStagedHelper}` ← first existing path in `{promoteStagedProbeOrder}`; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot promote the staged skill: skf-promote-staged.py is missing. Re-install SKF, then re-run create-skill." From `{project-root}`, run:

```bash
uv run {promoteStagedHelper} promote --stage "<staging-skill-dir>" --package "{skill_package}" --forge-version "{forge_version}" [--inventory "{extraction_inventory}" --source-root "{source_root}"] [--carry-manual "{skill_package}"]
```

Pass `--inventory` and `--source-root` when the inventory's `scripts_inventory` or `assets_inventory` is not empty, and `--carry-manual "{skill_package}"` when `{skill_package}` already exists. The helper copies the staged bytes, never a copy from context:

- **To `{skill_package}`:** `SKILL.md`, `context-snippet.md`, `metadata.json` (with the `doc_sources` step 5a wrote into it) and every file under the staged `references/` (the `references/full-*.md` files step 5b extracted included), plus `scripts/{name}` and `assets/{name}` for each inventory script and asset, copied from `{source_root}`, and, with `--carry-manual`, the earlier build's `scripts/[MANUAL]/` and `assets/[MANUAL]/` files. The package is built beside its target and swapped in, so a reader never sees half of it.
- **To `{forge_version}`:** `{forge_version}/provenance-map.json`, `{forge_version}/evidence-report.md` and `{forge_version}/extraction-rules.yaml`, one atomic write each, and, with a warning, `{forge_version}/manual-backup/SKILL-<UTC time>.md` (the earlier SKILL.md, a new file each run) when the staged one lacks a hand-written `[MANUAL]` block of it.
- **Not copied:** a promoted authoritative doc (`file_entries[]` with `file_type: "doc"`, from step 3 §2a) stays at its source path; the provenance map tracks it for drift detection.

Bind `{promotion}` ← its JSON: `files[]` (each promoted file's `path`, `kind`, `bytes` and `sha256`, read back and checked against the staged bytes), `counts`, `ignored` (staged files it did not promote), `manual` (what `--carry-manual` kept: `blocks`, `missing_blocks`, `files`, `backup`) and `warnings`; display each warning. Act on its exit code:

- **0:** continue to §4.
- **1** (a staged file it needs is missing, the inventory names a script or asset it cannot copy, or the earlier package cannot be read; nothing was written): **HARD HALT** (exit code 4, `staging-unreadable`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --result-dir "{forge_version}" --target stderr < "{run_dir}/halt.json"`), with the message the helper printed on stderr.
- **2** (a write failed; the earlier package stays in place when the swap itself failed): **HARD HALT** (exit code 4, `write-failed`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --result-dir "{forge_version}" --target stderr < "{run_dir}/halt.json"`): "Artifact generation failed: {the message the helper printed on stderr}. Check permissions and disk space." Once the swap succeeded, stage `"skill_package"` and `"outputs"` as the Workflow Rules say.

### 4. Create Active Symlink (atomic flip)

Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}` using the shared atomic-flip helper. The helper holds an `flock` on `{skill_group}/active.skf-lock`, refuses to replace a non-symlink at `{skill_group}/active` (protecting against accidental rm-rf of a real directory), and uses a rename-over-symlink pattern so the update is atomic from a concurrent reader's perspective:

```bash
python3 {atomicWriteHelper} flip-link \
  --link {skill_group}/active \
  --target {version}
```

The helper exits 2, with a `{"status": "error", "message": …}` line on stderr, when `{skill_group}/active` already exists as a real directory or file rather than a symlink, or when it cannot take the flip lock on `{skill_group}/active.skf-lock`. In that case **HARD HALT** (exit code 5, `active-link-blocked`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --result-dir "{forge_version}" --target stderr < "{run_dir}/halt.json"`), with `"skill_package"`, `"outputs"` and `{skill_group}/active` as `"path"`: "Refusing to flip `{skill_group}/active`: {the `message` of the helper's stderr line, else its stderr}. Investigate manually; expected a symlink pointing at a version directory, with no other flip running."

Do not `rm` + `ln -s` the active link by hand. The bare-rm pattern has two failure modes: (1) a concurrent reader sees a missing `active` mid-flip, and (2) a bug or typo that replaces `{skill_group}/active` with a plain directory turns the next manual `rm -rf {skill_group}/active` into data loss. The helper encapsulates both guards.

### 5. Verify Write Completion

The promotion's exit 0 is the write check: it refused a missing staged file, script or asset before writing (§3, exit 1) and read back every file it wrote against the staged bytes (exit 2 on a mismatch), and the flip's exit 0 (§4) means `{skill_group}/active` points at `{version}`. From `{promotion}`, bind `ref_count` ← `counts.references` for the step 8 report, and list each file of its `files[]` with its `path` and `bytes`.

`ref_count` 0 is a valid state when step 6 kept Tier-2 content inline (its evidence report says so on the Body line). When step 5b or step 6 split the body (`sections_extracted` is not empty) and `ref_count` is 0 anyway, **HARD HALT** (exit code 5, `references-missing`, phase `generate-artifacts`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --result-dir "{forge_version}" --target stderr < "{run_dir}/halt.json"`), with `"skill_package"` and `"outputs"`: "Split-body produced zero reference files. Investigate step 6 output before retrying: empty `references/` after a split is never a valid state."

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

Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}`; first existing path wins. Every registry change below goes through it: it holds `{sidecar_path}/forge-tier.yaml.lock` for its one read-modify-write of `{forgeTierConfig}`, so no step takes a lock of its own. If no candidate exists, warn "forge-tier.yaml registry not updated: skf-forge-tier-rw.py is missing; re-install SKF" and leave out every registry command below.

**Collection creation:** Create (or replace) a QMD collection from the skill artifacts. When `qmd collection add` fails after the `remove`, the collection is gone from QMD, so its registry entry goes too:

```bash
qmd collection remove {name}-extraction 2>/dev/null  # no-op if new
if qmd collection add {skill_package} --name {name}-extraction --mask "**/*"; then
  qmd embed --collection {name}-extraction
else
  uv run {forgeTierRwHelper} remove-qmd-collection --target "{forgeTierConfig}" --name {name}-extraction
fi
```

`qmd embed` generates the vector embeddings for semantic (`vec`) and HyDE query sub-types; scope it to this collection to avoid re-embedding others. If the installed qmd CLI lacks `--collection`, gate the embed behind a per-skill freshness check: read the registry with `uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"`, skip the embed when the `{name}-extraction` entry in its `data.qmd_collections` was created within the last 24 hours, and warn in evidence-report. An unscoped embed re-runs over every collection, which in a populated QMD store can cost minutes of GPU time per create-skill run; 24 hours is long enough to absorb rapid re-forges from the same brief without losing meaningful content freshness.

**Registry update:** only when `qmd collection add` succeeded, register the collection. The helper replaces the entry with the same `name`, or appends one:

```bash
uv run {forgeTierRwHelper} register-qmd-collection --target "{forgeTierConfig}" <<'SKF_REGISTRY_ENTRY'
{"name": "{name}-extraction", "type": "extraction", "source_workflow": "create-skill", "skill_name": "{name}", "created_at": "{current ISO date}"}
SKF_REGISTRY_ENTRY
```

**Error handling:**
- If QMD collection creation fails: log the error, note that indexing can be retried via [SF] setup. Do not fail the workflow.
- If a registry command fails: log the error, continue. The collection exists in QMD even if the registry entry failed.

**IF forge tier is not Deep:** Skip this section silently. No messaging.

### 6b. CCC Index Registry Registration (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml (Forge+ or Deep with ccc available):**

Ensure the source of this skill is indexed by ccc and registered in the `ccc_index_registry` array.

**Pick the folder:** bind `{ccc_root}`, the folder the index belongs to, and `{ccc_settings_owner}`:

- **Docs-only skill** (`source_type: "docs-only"`): there is no source to index. Skip the rest of this section.
- **Remote source** (`source_repo` is a GitHub URL, an `owner/repo` shorthand or another git URL): the index belongs in SKF's workspace clone, which persists, and not in the tree step 3 read the source from, which §7 removes. When step 3 bound `{remote_clone_path}`, the clone holds `source_commit`: bind `{ccc_root}` ← `{remote_clone_path}` and `{ccc_settings_owner}` ← `skf`. When it left `{remote_clone_path}` null (Quick tier, a run step 3 degraded to source reading, or a clone it did not move to this skill's commit), skip the rest of this section, including the registry update.
- **Local source:** bind `{ccc_root}` ← `{source_root}` and `{ccc_settings_owner}` ← `user`.

**Index verification:**

**Working-directory contract:** `ccc init`, `ccc index`, and `ccc status` take **no positional path argument**: each operates on the current working directory, and passing a path makes them exit non-zero with `Got unexpected extra argument`. Run them from `{ccc_root}` (`cd "{ccc_root}" && ccc …`, the same form `extract.md` step 2b and `knowledge/ccc-bridge.md` use), then return to `{project-root}` before the registry update below, which resolves `{forgeTierConfig}` relative to the project.

**Project root without settings:** check this before running any ccc command. When `{ccc_root}` is `{project-root}` and `{project-root}/.cocoindex_code/settings.yml` does not exist, do not run `ccc init` or `ccc index`: `/skf-setup` initializes the project index with the SKF exclusions, and in a project nested inside another git checkout `ccc index` would index the enclosing repository instead. Skip the rest of this section, including the registry update, note that re-running `/skf-setup` enables the index, and continue to §7.

Otherwise, `ccc index` requires the directory to be initialized first:

- `{ccc_settings_owner}` `skf`: resolve `{mergeCccExclusionsHelper}` from `{mergeCccExclusionsProbeOrder}` and, from `{project-root}`, run `uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}"`. It runs `ccc init -f` in the clone when its `settings.yml` is missing and adds the standard build and dependency exclusions the file lacks, as step 3 §2b does, so it changes nothing once step 3 prepared the clone. When no candidate resolves, the command fails or `settings_ready` is false, log it and skip the rest of this section, including the registry update.
- `{ccc_settings_owner}` `user`: run `cd "{ccc_root}" && ccc init` (idempotent: a no-op once initialized).

Then run `cd "{ccc_root}" && ccc index`, or use the ccc MCP tool. `ccc_bridge.ensure_index` is a conceptual interface, not a callable function. Indexing is a no-op if the source was already indexed during setup, step 2b or step 3.

**Nested project marker:** when `{ccc_root}` is a local source inside a git checkout whose `.git` is a folder, or inside a folder that holds `.cocoindex_code/settings.yml` (a local source such as `./packages/lib`, or a linked worktree or submodule inside such a checkout, whose `.git` file ccc does not count as a marker), `ccc init` exits non-zero with `A parent directory has a project marker`. This is expected: re-run as `cd "{ccc_root}" && ccc init -f` to initialize at the subtree anyway, then `ccc index`. Do not treat the parent-marker warning as fatal. ccc writes no `.gitignore` entry for such a project; **Keep the index out of git** below covers it.

**Verify the index is not degraded:** after `ccc index`, load `{cccIndexCheckData}` and run it with `{ccc_root}` and `{ccc_settings_owner}`. An index that misses the source language silently cripples later `skf-audit-skill` / `skf-update-skill` searches with no error surfaced. On **index unverified**, log "index unverified" and continue with **Keep the index out of git**. On **degraded**, log it and continue per the error handling below: a degraded index is not workflow-fatal, but it must be recorded so the gap is visible.

**Keep the index out of git:** once the ccc commands above are done (after the check, after "index unverified", or after a ccc command failed), return to `{project-root}` and resolve `{cccGitHygieneHelper}` from `{cccGitHygieneProbeOrder}`; first existing path wins. If no candidate exists, or the helper exits non-zero or prints no JSON, log "ccc git hygiene skipped" and continue to the registry update: this check never fails the workflow.

- **Workspace clone** (`{ccc_settings_owner}` is `skf`): run `uv run {cccGitHygieneHelper} workspace --repo "{ccc_root}"`. It undoes the edit a `ccc init` or `ccc index` made to the clone's tracked `.gitignore` and keeps the index folder out of git through the clone's `.git/info/exclude`, so a later move of the clone to another ref is not blocked. Read nothing from its output.
- **Local source** (`{ccc_settings_owner}` is `user`): run `uv run {cccGitHygieneHelper} nested --dir "{ccc_root}" --project-root "{project-root}"`. ccc gitignores its index only at the top of a git checkout whose `.git` is a folder, so for a project in a subfolder of a checkout (the `ccc init -f` case above), a linked worktree or a submodule, `git status` lists the index database and a `git add -A` would commit it. When git does not ignore `{ccc_root}/.cocoindex_code/`, the helper writes a `.gitignore` holding `*` inside that folder so the folder ignores itself; SKF never edits a project's own `.gitignore`. It also repairs a nested index an earlier run left, and does nothing for `{project-root}` itself, for a folder without `.cocoindex_code/settings.yml`, or outside a git work tree. Bind `{ccc_ignore_notice}` ← `notice` and display `{ccc_ignore_notice}` verbatim when it is not null: its remedy command is quoted for paths with spaces.

**Registry update:**

**Resolve `{forgeTierRwHelper}`** from `{forgeTierRwProbeOrder}`; first existing path wins. If no candidate exists, log it and skip the registry update.

Register the indexed folder with `register-ccc-index`, a comment-preserving round-trip on `forge-tier.yaml` that keeps the `ccc_index_registry` deduplication in the script. Like every registry change of §6, the helper holds `{sidecar_path}/forge-tier.yaml.lock` for its one read-modify-write. Write `{ccc_root}` with `/` separators, so the JSON stays valid on Windows:

```bash
uv run {forgeTierRwHelper} register-ccc-index --target "{forgeTierConfig}" <<'SKF_REGISTRY_ENTRY'
{"source_repo": "{brief.source_repo}", "path": "{ccc_root}", "skill_name": "{name}", "indexed_at": "{current ISO date}", "source_workflow": "create-skill"}
SKF_REGISTRY_ENTRY
```

Deduplicates by `source_repo` + `skill_name`, not by the local `path`.

**Error handling:** If ccc indexing or registry update fails, log and continue: do not fail the workflow.

**IF `tools.ccc` is false:** Skip this section silently.

### 7. Auto-Proceed

**Remove the private source tree.** When step 3 bound `{source_tree}`, no later step reads the source: resolve `{sourceTreeHelper}` from `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} close --tree "{source_tree}"`. Go on whatever it prints. On `left` or `refused`, a command that fails or prints no JSON, or no candidate, display "This run's source tree `{source_tree}` was not removed; a later SKF run removes it once it is seven days old." Then set `{source_tree}` to null.

No user interaction. Once the skill is promoted and verified (and optionally indexed into QMD), load `{nextStepFile}`, read it fully, then execute it. A QMD-indexing failure does not block; a promotion failure halts (§3) rather than proceeding with partial output.
