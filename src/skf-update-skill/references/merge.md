---
nextStepFile: 'write.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves when §6b creates a version
# folder — a folder copied in place instead of staged and renamed would
# leave a half-copied version behind on any failure.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{skillInventoryHelper}` to the first existing path when §6b needs
# the next patch version; HALT if neither resolves: never pick it by hand.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# exists: §4 amends the [MANUAL] inventory with the user's decisions and §6b
# verifies the merged SKILL.md against it before anything is published.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Merge

## STEP GOAL:

Merge freshly extracted export data into the existing SKILL.md content while preserving all [MANUAL] sections. Detect and resolve conflicts where regenerated content overlaps developer-authored content.

## Rules

- Focus only on merging extractions into existing skill content
- Never delete or modify [MANUAL] section content without the user's section 4 [R]/[E] decision
- Write the merged files to disk at section 6b, once §6b has recorded what this run writes (`{runStateHelper}` `begin`), and verify the merged SKILL.md against the [MANUAL] inventory the user approved before it is published: in a staged version folder outside gap-driven mode, in `{run_dir}` in gap-driven mode. Later steps verify the files on disk
- If [MANUAL] conflicts detected: halt and present to user (headless: HALT, nothing written). If clean merge: auto-proceed

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>"}
SKF_JSON
```

Pass `--tree` when init.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. Once §6b has run `begin`, the helper first undoes what this run wrote: in gap-driven mode it restores the package, the version's provenance map and evidence report, and the skill brief from the snapshot `begin` took; in every other mode it removes the version folders `begin` recorded (never one the `active` link names). Then it removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. Tell the user in one line what it restored and removed, and name each path its `failed[]` lists for the user to restore or delete by hand. The emitter adds `files_written: []`: after the rollback nothing this run wrote stands. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "merge:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

### 1. Load Merge Rules

Load {manualSectionRulesFile} for [MANUAL] detection and preservation patterns. The change-category actions and their priority order are in §3 below, and the conflict handling in §4.

### 2. Extract [MANUAL] Blocks

From the [MANUAL] inventory captured in step 1:
- Extract every `<!-- [MANUAL:section-name] -->` ... `<!-- [/MANUAL:section-name] -->` block
- Map each block to its parent section heading
- Store blocks in a preservation map keyed by section-name

### 3. Apply Merge by Priority Order

Read this step's inputs from disk, never from memory: the change manifest from `{run_dir}/change-manifest.json` (step 2, or gap-driven.md §1 in gap-driven mode), the extraction or verification records from `{run_dir}/reextract-records.json` (step 3, or gap-driven.md §4), and the documents step 2 §1b promoted from `{run_dir}/promoted-docs.json` when it wrote that file. A compacted context still merges what those steps found.

Apply merge in the following priority order:

**Priority 1 — Process DELETED exports:**
- Remove generated content for deleted exports
- Check if deleted export has attached [MANUAL] blocks
- If [MANUAL] attached: flag as ORPHAN conflict (do not remove)
- If no [MANUAL]: remove generated content cleanly
- **Gap-driven rescopes** (`DELETED_EXPORT` from gap-driven.md §1 rule R1, verification `rescoped`) are processed here with the same removal. §6b writes the entry's `rescope` (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path) to the skill brief before SKILL.md, and step 5 removes the provenance `entries[]` row and recomputes `stats` from the amended `brief.scope` (write.md §2/§3). gap-driven.md §4 HALTs on a rescope that carries no `rescope`, so no unscoped removal reaches here.

**Priority 2 — Process MOVED exports:**
- Update file:line citations in generated content
- **Gap-driven:** move citations only for an export whose gap-driven.md §4 spot-check recorded `moved`. A `MOVED_EXPORT` that recorded `unknown` (the drift override among the causes), `verified` or `missing` moves none: write.md §3 leaves its line as it is.
- Update provenance map file references
- [MANUAL] blocks unaffected (content unchanged)

**Priority 3 — Process RENAMED exports:**
- Replace old identifier with new identifier in generated content
- Check if [MANUAL] blocks reference old identifier name
- If referenced: flag as STALE_REFERENCE conflict

**Priority 4 — Process MODIFIED exports:**
- Replace generated content for the export with fresh extraction
- Preserve [MANUAL] blocks adjacent to the export
- Check for position conflicts (new content shifts [MANUAL] block)
- If position conflict: flag as POSITION conflict

**Priority 5 — Process NEW exports:**
- Append new export content to appropriate section
- Place before any [MANUAL] blocks at section boundary
- No conflicts expected (new content, no existing [MANUAL])
- **Gap-driven cited `NEW_EXPORT` whose spot-check pinned a line** (gap-driven.md §4 recorded `verified` or `moved` for an export the provenance map does not hold): cite it as `[SRC:{source_file}:L{line}]`, where `{line}` is the citation's line for `verified` and the `new_location` line for `moved`: the line write.md §3 records in its new `source-read` entry. The spot-check found that line by the verifier's text rules, not by an ast-grep recipe, so the prefix is `SRC`, never `AST`.

**Priority 6 — Process script/asset file changes (from Category D in change manifest):**

Category D operates on every `file_entries[]` row regardless of `file_type`. Handle each entry by its type:

- **`file_type: "script"` or `file_type: "asset"`:**
  - MODIFIED_FILE: queue file for re-copy from `{source_root}`, update `file_entries` content_hash
  - DELETED_FILE: queue file for removal from `scripts/` or `assets/`, remove from `file_entries`
  - NEW_FILE: queue file for copy from `{source_root}`, add to `file_entries`
  - Files in `scripts/[MANUAL]/` or `assets/[MANUAL]/` are never modified (user-authored)
  - Update Section 7b manifest table to reflect changes
  - Update `metadata.json` `scripts[]`/`assets[]` arrays and `stats.scripts_count`/`stats.assets_count`

- **`file_type: "doc"`** (authoritative docs promoted by §2a/§1b):
  - MODIFIED_FILE: update `file_entries` content_hash only. **Do NOT copy the file** — doc-type entries are source-tracked but not bundled. Record the drift in the update report.
  - DELETED_FILE: remove from `file_entries`. **Do NOT remove any file from the skill package** (there was nothing copied). Record the removal in the update report — a deleted authoritative doc is a meaningful upstream signal.
  - NEW_FILE: this path is not used for doc type — new doc entries come from Priority 7 below, not from Category D. If Category D reports NEW_FILE with `file_type: "doc"`, log a warning and route to Priority 7.

**Priority 7 — Process new authoritative docs (from `promoted_docs_new[]` populated by §1b):**

For each entry of `promoted_docs_new[]`, read from `{run_dir}/promoted-docs.json`:

- Add a new row to `file_entries[]` in the merged provenance map with:
  - `file_name`: `"docs/authoritative/{source_path}"` (synthetic namespace — see skill-sections.md for convention)
  - `file_type`: `"doc"`
  - `source_file`: the path from `promoted_docs_new[].path`
  - `content_hash`: the hash pre-computed by §1b
  - `confidence`: `"T1-low"`
  - `extraction_method`: `"promoted-authoritative"`
- Do NOT copy the file into the skill package (doc type is source-tracked, not bundled).
- Record in the update report: `"Added authoritative doc: {path} (heuristic: {basename})"`.

**If `promoted_docs_new[]` is empty:** skip Priority 7 silently. No report entry.

**Priority 8: Process STRUCTURAL_FIX entries (gap-driven, from gap-driven.md §1 rule R2):**

For each `STRUCTURAL_FIX` entry gap-driven.md §4 forwarded:

- Apply the surgical edit described in the entry's `remediation` text to the **generated output file only** (e.g., escape an unescaped `|` inside a code span, balance a fence, repair a broken intra-skill anchor in SKILL.md or a `references/*.md`).
- **A split-body consistency finding** (rule R2: the SKILL.md body and a `references/*.md` file document one export differently): edit the `references/*.md` file so it documents the export as the SKILL.md body does, whichever of the two files the gap's `Source:` names. The body is authoritative (test-skill coverage-check §1b), so never change the body to match the reference file.
- Do **not** add, modify, or remove any provenance `entries[]` row — STRUCTURAL_FIX never touches the provenance map.
- Preserve any [MANUAL] blocks; if the fix location overlaps a [MANUAL] block, flag as a POSITION conflict instead of editing.
- Record in the update report: `"Structural fix: {remediation summary} at {file}:{line}"`.

**If no STRUCTURAL_FIX entries:** skip Priority 8 silently.

**Priority 8b: Process metadata-update entries (gap-driven, from gap-driven.md §1 rule R4):**

For each `metadata update` entry gap-driven.md §4 forwarded:

- Queue the surgical metadata patch described in the entry's `remediation` (e.g., reconcile a divergent `stats` count, add an explanatory stat) in workflow context as `metadata_patches[]` for write.md §2 to apply **before** its automatic stat recount.
- Touch no provenance `entries[]` row and no generated markdown — this priority only stages the patch; write.md §2 applies it.
- Record in the update report: `"Metadata patch queued: {remediation summary}"`.

**If no metadata-update entries:** skip Priority 8b silently.

### 4. Check for Conflicts

Scan all merge operations for flagged conflicts.

**If ZERO conflicts:** report a clean merge.

**GATE [default: HALT]**: **if conflicts are detected, headless (`{headless_mode}` true):** conflicts require human judgment, and nothing is written yet. HALT with status `halted-for-manual-mismatch` (halt procedure: `phase: "merge:conflict-resolution"`, `reason: "{N} [MANUAL] conflict(s) need a person: {each conflict_type and section}"`). No `headless_decisions[]` entry is added.

**If conflicts detected, interactive:** present each conflict to user:

"**[MANUAL] Conflict Resolution Required:**

**Conflict {N} of {total}:** {conflict_type}

{Detailed description of the conflict with before/after context}

**Options:**
- **[K]eep** — Preserve [MANUAL] content as-is, adjust generated content around it
- **[R]emove** — Remove the [MANUAL] block (content will be lost)
- **[E]dit** — Show me both versions, I'll provide the resolution

Select: [K] Keep / [R] Remove / [E] Edit"

Process each conflict with user's decision, and record each one as it is made in the run's plan, `{run_dir}/manual-plan.json` (`{"decisions": [...]}`), one decision per [MANUAL] block by its name:

- **[K]eep:** `{"name": "<block>", "action": "keep"}`.
- **[R]emove**, and an ORPHAN the user removes: `{"name": "<block>", "action": "remove"}`.
- **[E]dit:** write the interior the user approved to `{run_dir}/manual-edit-<block>.md`, byte for byte as it goes between the block's markers, its leading and trailing newlines included, and record `{"name": "<block>", "action": "edit", "content_file": "manual-edit-<block>.md"}`. §6b writes that same file's bytes between the markers. Never type a hash: the helper below hashes the file.

**Amend the [MANUAL] inventory** (every mode, a clean merge included: then the plan holds no decision). Write `{run_dir}/manual-plan.json` (`{"decisions": []}` when there was no conflict), then, from `{project-root}`, resolve `{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}` and run:

```bash
uv run {hashContentHelper} manual-inventory-amend \
    --inventory "{manual_inventory}" \
    --plan "{run_dir}/manual-plan.json" \
    --output "{run_dir}/manual-inventory.json"
```

It writes the step 1 inventory without the blocks the user removed and with each edited block hashed from its approved interior. Rebind `{manual_inventory}` ← `{run_dir}/manual-inventory.json`: §6b's staged check, write.md §1, write.md §6's `fix` and write.md §7's re-check verify against it, so they check what the user approved and nothing else. On exit 1 or no JSON (a plan that names a block the inventory does not hold, or an edit with no interior), or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "merge:manual-plan"`, `path: "{run_dir}/manual-plan.json"`, its stderr as `reason`).

### 6. Compile Merge Results

Build merge result summary:

```
Merge Results:
  exports_updated: [count]
  exports_added: [count]
  exports_removed: [count]
  exports_moved: [count]
  exports_renamed: [count]

  manual_sections_preserved: [count]
  manual_conflicts_resolved: [count]
  manual_orphans_kept: [count]
  manual_orphans_removed: [count]
```

In gap-driven mode, write what step 5's `apply` reads from merge to `{run_dir}/merge-records.json`: for each `NEW_EXPORT` or `MODIFIED_EXPORT` the provenance map does not hold and no `re-extracted` record covers (a cited export whose spot-check pinned a line, and a `Medium`, `Low` or `Info` one recorded `unknown`), the `export_type`, `params` and `return_type` its merged documentation gives, leaving out each one it does not:

```bash
cat > "{run_dir}/merge-records.json" <<'SKF_JSON'
{"exports": [{"export_name": "<name>", "export_type": "<kind>", "params": ["<name: type>"], "return_type": "<type>"}]}
SKF_JSON
```

### 6b. Write Merged Files to Disk

Write the merged content produced by sections 3–4 to disk now. Later steps read these files from disk. The write must happen exactly once, here.

**Renew the run lock** before anything below writes: this run may have waited at a gate past the time init.md §1b's lock goes stale. From `{project-root}`, run the acquire init.md §1b ran, with this run's own owner and the `{runLockHelper}` §1b resolved:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/{skill_name}/.skf-update.lock" \
    --owner "{lock_owner}" \
    --stale-after 60
```

- **Exit 0 with `refreshed` true:** the lock is still this run's, now renewed; continue.
- **Exit 0 with `refreshed` false, or exit 3:** this run's lock lapsed while it waited, so another update may have changed the skill since this run read it. On exit 0 the lock was gone, or `stale_replaced` names another update's stale lock, and this acquire took it again; on exit 3 another update holds it. HALT with status `halted-for-concurrent-run` before this section writes anything: display "**This update of {skill_name} lost its run lock while it waited.** Another update of the skill may have run in the meantime, so this update wrote nothing to the skill package: run it again{on exit 3: once that update ends. {message}}." The halt procedure takes `phase: "merge:run-lock"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-lost: this run's lock lapsed while it waited; another update may have changed the skill since this run read it"`, or on exit 3 `reason: "another update in progress: {message}"`. The halt's release (step 3 of the halt procedure) removes a lock this acquire took.
- **Any other exit, or no JSON:** HALT with status `blocked` before this section writes anything: display "**The run lock could not be renewed:** {the message the helper printed on stderr}. This update wrote nothing to the skill package." The halt procedure takes `phase: "merge:run-lock"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-failed: {that message}"`.

**Choose the version this update writes** and bind `{new_version}`:

- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair keeps the version it repairs — `{new_version}` is the metadata.json `version`, SKILL.md is written into the current `{skill_package}`, and the version folder below is skipped.
- **Every other mode** (normal, degraded and docs-only): `{new_version}` is `{source_version_detected}` when step 1 §6c recorded one (a higher version than the previous metadata version), otherwise the previous version with its patch number incremented, as `{skillInventoryHelper}` computes it (resolve it ← first existing path in `{skillInventoryProbeOrder}`). From `{project-root}`, run `uv run {skillInventoryHelper} version next-patch "{version}"` with the metadata.json `version` and bind `{new_version}` ← `next_patch`: `1.2.3` gives `1.2.4`, and a pre-release gives its release (`1.2.3-rc.1` gives `1.2.3`). Never increment it by hand. Both values are version folder names already: the helper drops build metadata. When no candidate resolves, or the command exits 1 (`code` `NOT_A_VERSION`: the metadata.json `version` names no version) or prints no JSON, HALT with status `halted-for-write-failure` before writing anything: "**The next version of {skill_name} could not be computed:** {the helper's `error`, or 'skf-skill-inventory.py is missing; re-install SKF'}. Nothing was written. When the metadata.json `version` names no version, set the version the skill was forged at there, then re-run." The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{skill_package}/metadata.json"`, `reason: "next-version-failed: {that message}"`.

**Record what this run writes**, before its first write, so a later halt, or the next update after a crash, can undo it. From `{project-root}`, with the `{runStateHelper}` SKILL.md On Activation resolved:

- **Gap-driven mode:** snapshot everything the repair may write in place:

  ```bash
  uv run {runStateHelper} begin --run-dir "{run_dir}" --mode in-place \
      --package "{skill_package}" \
      --forge-version "{forge_version}" \
      --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"
  ```

  It copies the package (each link as a link), the version's `provenance-map.json` and `evidence-report.md`, and the brief into `{run_dir}/snapshot/`. On a non-zero exit or no JSON, HALT with status `halted-for-write-failure` before writing anything (halt procedure: `phase: "merge:snapshot"`, `path: "{skill_package}"`, `reason: "snapshot-failed: {its failed[], or its message}"`).
- **Every other mode:** record the folders the next section creates:

  ```bash
  uv run {runStateHelper} begin --run-dir "{run_dir}" --mode new-version \
      --created "{skill_group}/{new_version}" \
      --created "{forge_data_folder}/{skill_name}/{new_version}" \
      --staging "{skill_group}/{new_version}.skf-tmp" \
      --skill-group "{skill_group}"
  ```

  Exit 3 (`status` `exists`) is the version-exists halt in step 1 below, with the folder its `path` names. Any other non-zero exit, or no JSON: HALT with status `halted-for-write-failure` before writing anything (halt procedure: `phase: "merge:run-state"`, `path: "{run_dir}"`, its message as `reason`).

**Create the version folder** (every mode but gap-driven). Each version keeps a folder of its own (`knowledge/version-paths.md`), so the previous version stays on disk unchanged and step 5 §8 can point the `active` link at the new one:

1. **Never overwrite a version.** When `begin` above exited 3, `{skill_group}/{new_version}/` or `{forge_data_folder}/{skill_name}/{new_version}/` already exists: HALT with status `halted-for-write-failure` before writing anything: "**Version {new_version} of {skill_name} already exists** at `{the folder that exists}`. Update Skill writes each version into a folder of its own, never overwrites one, and updates the version the `active` link names, which is not {new_version}. If an earlier update stopped after creating {new_version}, delete `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` by hand, then re-run. If you keep {new_version} on purpose, move both folders out of the way by hand before updating. Drop Skill removes a single version only when the export manifest lists it (`@Ferris DS {skill_name}`, choose {new_version}, with `--purge`); for a skill that was never exported it can only drop every version." The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{the folder that exists}"`, `reason: "version {new_version} already exists; update-skill never overwrites a version"`; its rollback removes nothing, since `begin` recorded nothing. An interrupted update's folders rarely reach this halt: the next update's init.md §1b removes them when it takes over that run's stale lock.
2. **Stage the package.** Resolve `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {atomicWriteHelper} stage-dir --target "{skill_group}/{new_version}"
   ```

   Bind `{version_staging}` ← `staging`: the empty folder `{skill_group}/{new_version}.skf-tmp` it created (it clears one an interrupted run left).
3. **Copy the current package** `{skill_package}` to `{version_staging}/{skill_name}`, naming both without a trailing `/` — equivalent to `cp -a "{skill_package}" "{version_staging}/{skill_name}"`: SKILL.md, metadata.json, context-snippet.md, `references/`, `scripts/`, `assets/` and every other entry, each link copied as a link and never followed. The files this update does not rewrite carry over to the new version this way.
4. **Write and verify the merged SKILL.md in the staged package**, before anything is published. Use the `Edit` or `Write` tool to write the merged SKILL.md content (UTF-8) to `{version_staging}/{skill_name}/SKILL.md`, and any `references/*.md` the merge changed into `{version_staging}/{skill_name}/references/`. Then, from `{project-root}`, check the [MANUAL] blocks against the inventory §4 amended:

   ```bash
   uv run {hashContentHelper} manual-verify "{version_staging}/{skill_name}/SKILL.md" \
       --inventory "{manual_inventory}"
   ```

   On `ok` true, continue. On `ok` false, or a failing command: HALT with status `halted-for-manual-mismatch` before the version is published: "**[MANUAL] section integrity failure in the merged SKILL.md.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Nothing was published: the previous version is unchanged." The halt procedure takes `phase: "merge:verify-manual-integrity"`, `path: "{version_staging}/{skill_name}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`, and its rollback removes `{version_staging}`.
5. **Publish it.** Run:

   ```bash
   uv run {atomicWriteHelper} commit-dir --target "{skill_group}/{new_version}"
   ```

   It renames the staged folder to `{skill_group}/{new_version}/` in one step, so no reader ever sees a half-copied version.
6. **Create the forge folder** `{forge_data_folder}/{skill_name}/{new_version}/` and copy `provenance-map.json`, `evidence-report.md` and `extraction-rules.yaml` from `{forge_version}` into it, each when it exists: step 5 updates the provenance map and appends this update to the evidence report there, and audit-skill reads the extraction rules there. Test reports, drift reports and result files belong to the version they were made for and stay where they are.
7. **Rebind** `{skill_package}` ← `{skill_group}/{new_version}/{skill_name}` and `{forge_version}` ← `{forge_data_folder}/{skill_name}/{new_version}`. Every later step reads and writes the new version there; `{manual_inventory}` keeps the amended path §4 bound.

If no `{atomicWriteProbeOrder}` candidate resolves, or the stage, copy, write, publish or forge-folder step fails, HALT with status `halted-for-write-failure`, naming the failed step (for a missing helper: "skf-atomic-write.py is missing; re-install SKF"). The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{skill_group}/{new_version}"`, `reason: "<the failed step>: <its error>"`; its rollback removes what this section created, `{version_staging}`, `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, none of which existed before `begin` recorded them. The previous version is unchanged.

**Write the merged files in place** (gap-driven mode only; every other mode wrote them in step 4 above):

1. **The rescopes' brief amendments.** For each manifest entry with a `rescope` (rule R1), append its `scope.amendments[]` entry and add its path to `scope.exclude` in `{forge_data_folder}/{skill_name}/skill-brief.yaml`, preserving every other field; skip an amendment the brief already holds (same `action`, `category` and `path`) and a path `scope.exclude` already lists, so a re-run never adds them twice.
2. **Stage and verify SKILL.md in the run folder.** Write the merged SKILL.md (UTF-8) to `{run_dir}/SKILL.md`, then, from `{project-root}`:

   ```bash
   uv run {hashContentHelper} manual-verify "{run_dir}/SKILL.md" \
       --inventory "{manual_inventory}"
   ```

   On `ok` false, or a failing command: HALT with status `halted-for-manual-mismatch` before the package changes (halt procedure: `phase: "merge:verify-manual-integrity"`, `path: "{run_dir}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`); its rollback restores the brief step 1 amended.
3. **Copy it over the package.** Copy `{run_dir}/SKILL.md` to `{skill_package}/SKILL.md`, and write any `references/*.md` the merge changed (merge Priority 8) into `{skill_package}/references/`.

**Do NOT write here:**
- `metadata.json`, `provenance-map.json`, `evidence-report.md`: derived from the merge output, written by step 5 sections 2–4 (the version folder above only copies the previous version's files, which step 5 then rewrites)
- `context-snippet.md`: regenerated from the on-disk SKILL.md + metadata.json by step 5 section 5

**Halt-on-tool-failure:** If any `Edit`/`Write` call or copy errors (permission denied, disk full, path invalid, etc.), HALT with status `halted-for-write-failure` and report the failure; do not proceed to step 5. The halt procedure takes `phase: "merge:write-skill-md"`, `path: "{the file that failed}"`, `reason: "<the error>"`, and its rollback puts the skill back as it was: it removes `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` when this run created them, and in gap-driven mode restores the package and the brief from the snapshot.

### 7. Report Progress

Display one line from §6's counts: "**Merged:** {exports_updated} updated, {exports_added} added, {exports_removed} removed, {manual_sections_preserved} [MANUAL] sections preserved, {manual_conflicts_resolved} conflicts resolved." The report (step 6) shows the full counts.

### 8. Route to Write

**Clean merge (no conflicts):** display "**Clean merge: proceeding to write...**", then load, read the full file, and execute {nextStepFile} (auto-proceed).

**Conflicts were resolved (user interaction occurred):** present "**Merge complete with conflict resolution. Select:** [C] Continue to Write" and wait for the user to confirm before loading {nextStepFile}.

**GATE [default: C]** (`{headless_mode}` true): a headless run reaches this gate only with a clean merge (§4 halts on a conflict before anything is written). Auto-continue and record the decision, from `{project-root}`:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "merge.clean-merge-gate", "default_action": "C", "taken_action": "C", "reason": "headless: clean merge, no conflicts to resolve"}
SKF_JSON
```
