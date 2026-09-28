---
nextStepFile: 'validate.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
mergeConflictRulesFile: 'references/merge-conflict-rules.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves when §6b creates a version
# folder — a folder copied in place instead of staged and renamed would
# leave a half-copied version behind on any failure.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Merge

## STEP GOAL:

Merge freshly extracted export data into the existing SKILL.md content while preserving all [MANUAL] sections. Detect and resolve conflicts where regenerated content overlaps developer-authored content.

## Rules

- Focus only on merging extractions into existing skill content
- Never delete or modify [MANUAL] section content
- Write merged SKILL.md directly to disk at section 6b — Claude Code's Edit/Write tools commit on call, so there is no held-in-memory "edit plan" primitive; subsequent steps validate and verify against the on-disk files
- If [MANUAL] conflicts detected: halt and present to user. If clean merge: auto-proceed

## Steps

### 1. Load Merge Rules

Load {manualSectionRulesFile} for [MANUAL] detection and preservation patterns.
Load {mergeConflictRulesFile} for the conflict-resolution strategy table (the change-category actions and priority order live in §3 below).

### 2. Extract [MANUAL] Blocks

From the [MANUAL] inventory captured in step 01:
- Extract every `<!-- [MANUAL:section-name] -->` ... `<!-- [/MANUAL:section-name] -->` block
- Map each block to its parent section heading
- Store blocks in a preservation map keyed by section-name

### 3. Apply Merge by Priority Order

Apply merge in the following priority order:

**Priority 1 — Process DELETED exports:**
- Remove generated content for deleted exports
- Check if deleted export has attached [MANUAL] blocks
- If [MANUAL] attached: flag as ORPHAN conflict (do not remove)
- If no [MANUAL]: remove generated content cleanly
- **Gap-driven rescopes** (`DELETED_EXPORT` from detect-changes §0 rule R1, verification `rescoped`) are processed here with the same removal. Step 6 also removes the provenance `entries[]` row and recomputes `stats` from the amended `brief.scope` (write.md §2/§3). The brief's `scope.amendments[]` (`action: "excluded"`) + `scope.exclude` entry must already exist — step 3 §0 HALTs otherwise, so no unscoped removal reaches here.

**Priority 2 — Process MOVED exports:**
- Update file:line citations in generated content
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

For each entry in the in-context `promoted_docs_new[]` list:

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

**Priority 8 — Process STRUCTURAL_FIX entries (gap-driven, from detect-changes §0 rule R2):**

For each `STRUCTURAL_FIX` entry forwarded by step 3 §0/1a:

- Apply the surgical edit described in the entry's `remediation` text to the **generated output file only** (e.g., escape an unescaped `|` inside a code span, balance a fence, repair a broken intra-skill anchor in SKILL.md or a `references/*.md`).
- Do **not** add, modify, or remove any provenance `entries[]` row — STRUCTURAL_FIX never touches the provenance map.
- Preserve any [MANUAL] blocks; if the fix location overlaps a [MANUAL] block, flag as a POSITION conflict instead of editing.
- Record in the update report: `"Structural fix: {remediation summary} at {file}:{line}"`.

**If no STRUCTURAL_FIX entries:** skip Priority 8 silently.

**Priority 8b — Process metadata-update entries (gap-driven, from detect-changes §0 rule R4):**

For each `metadata update` entry forwarded by step 3 §0/1a:

- Queue the surgical metadata patch described in the entry's `remediation` (e.g., reconcile a divergent `stats` count, add an explanatory stat) in workflow context as `metadata_patches[]` for write.md §2 to apply **before** its automatic stat recount.
- Touch no provenance `entries[]` row and no generated markdown — this priority only stages the patch; write.md §2 applies it.
- Record in the update report: `"Metadata patch queued: {remediation summary}"`.

**If no metadata-update entries:** skip Priority 8b silently.

### 4. Check for Conflicts

Scan all merge operations for flagged conflicts:

**If ZERO conflicts:**
- Report clean merge
- Auto-proceed to step 05

**If conflicts detected:**

Present each conflict to user:

"**[MANUAL] Conflict Resolution Required:**

**Conflict {N} of {total}:** {conflict_type}

{Detailed description of the conflict with before/after context}

**Options:**
- **[K]eep** — Preserve [MANUAL] content as-is, adjust generated content around it
- **[R]emove** — Remove the [MANUAL] block (content will be lost)
- **[E]dit** — Show me both versions, I'll provide the resolution

Select: [K] Keep / [R] Remove / [E] Edit"

Process each conflict with user's decision.

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

### 6b. Write Merged Files to Disk

Write the merged content produced by sections 3–4 directly to disk now. Later steps read from these files for validation and verification. The write must happen exactly once, here.

**Choose the version this update writes** and bind `{new_version}`:

- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair keeps the version it repairs — `{new_version}` is the metadata.json `version`, SKILL.md is written into the current `{skill_package}`, and the version folder below is skipped.
- **Every other mode** (normal, degraded and docs-only): `{new_version}` is `{source_version_detected}` when step 1 §6c recorded one (a higher version than the previous metadata version), otherwise the previous version with its patch number incremented, named by the Version Sanitization rules of `knowledge/version-paths.md`.

**Create the version folder** (every mode but gap-driven). Each version keeps a folder of its own (`knowledge/version-paths.md`), so the previous version stays on disk unchanged and step 6 §5b can point the `active` link at the new one:

1. **Never overwrite a version.** If `{skill_group}/{new_version}/` or `{forge_data_folder}/{skill_name}/{new_version}/` already exists, HALT with status `halted-for-write-failure` before writing anything: "**Version {new_version} of {skill_name} already exists** at `{the folder that exists}`. Update Skill writes each version into a folder of its own, never overwrites one, and updates the version the `active` link names, which is not {new_version}. If an earlier update stopped after creating {new_version}, delete `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` by hand, then re-run. If you keep {new_version} on purpose, move both folders out of the way by hand before updating. Drop Skill removes a single version only when the export manifest lists it (`@Ferris DS {skill_name}`, choose {new_version}, with `--purge`); for a skill that was never exported it can only drop every version." In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "merge:new-version-folder", path: "{the folder that exists}", reason: "version {new_version} already exists; update-skill never overwrites a version"}`).
2. **Stage the package.** Resolve `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {atomicWriteHelper} stage-dir --target "{skill_group}/{new_version}"
   ```

   Bind `{version_staging}` ← `staging`: the empty folder `{skill_group}/{new_version}.skf-tmp` it created (it clears one an interrupted run left).
3. **Copy the current package** `{skill_package}` to `{version_staging}/{skill_name}`, naming both without a trailing `/` — equivalent to `cp -a "{skill_package}" "{version_staging}/{skill_name}"`: SKILL.md, metadata.json, context-snippet.md, `references/`, `scripts/`, `assets/` and every other entry, each link copied as a link and never followed. The files this update does not rewrite carry over to the new version this way.
4. **Publish it.** Run:

   ```bash
   uv run {atomicWriteHelper} commit-dir --target "{skill_group}/{new_version}"
   ```

   It renames the staged folder to `{skill_group}/{new_version}/` in one step, so no reader ever sees a half-copied version.
5. **Create the forge folder** `{forge_data_folder}/{skill_name}/{new_version}/` and copy `provenance-map.json`, `evidence-report.md` and `extraction-rules.yaml` from `{forge_version}` into it, each when it exists: step 6 updates the provenance map and appends this update to the evidence report there, and audit-skill reads the extraction rules there. Test reports, drift reports and result files belong to the version they were made for and stay where they are.
6. **Rebind** `{skill_package}` ← `{skill_group}/{new_version}/{skill_name}` and `{forge_version}` ← `{forge_data_folder}/{skill_name}/{new_version}`. Every later step reads and writes the new version there; `{manual_inventory}` keeps the path step 1 wrote it to.

If no `{atomicWriteProbeOrder}` candidate resolves, or the stage, copy, publish or forge-folder step fails, remove what this section created — `{version_staging}`, `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, none of which existed before the first step — and HALT with status `halted-for-write-failure`, naming the failed step (for a missing helper: "skf-atomic-write.py is missing; re-install SKF"). The previous version is unchanged. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "merge:new-version-folder", path: "{skill_group}/{new_version}", reason: "..."}`).

**Write SKILL.md:**
- Use the `Edit` or `Write` tool to write merged SKILL.md content to `{skill_package}/SKILL.md` — the new version's package, or the current one in gap-driven mode
- Preserve UTF-8 encoding

**Do NOT write here:**
- `metadata.json`, `provenance-map.json`, `evidence-report.md` — derived from merge + validation output, written by step 6 sections 2–4 (the version folder above only copies the previous version's files, which step 6 then rewrites)
- `context-snippet.md` — regenerated from the on-disk SKILL.md + metadata.json by step 6 section 5

**Halt-on-tool-failure:** If any `Edit`/`Write` call errors (permission denied, disk full, path invalid, etc.), halt with status `halted-for-write-failure` and report the failure — do not proceed to step 5 validation. When this run created `{skill_group}/{new_version}/`, the previous version is unchanged: delete `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` before re-running update-skill. In gap-driven mode the skill package may be in a partial state and needs manual recovery first. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "merge:write-skill-md", path: "{skill_package}/SKILL.md", reason: "..."}`).

### 7. Display Merge Summary

"**Merge Complete:**

| Metric | Count |
|--------|-------|
| Exports updated | {count} |
| Exports added | {count} |
| Exports removed | {count} |
| [MANUAL] sections preserved | {count} |
| Conflicts resolved | {count} |"

### 8. Gate to Validation

**Clean merge (no conflicts):** display "**Clean merge — proceeding to validation...**", then load, read the full file, and execute {nextStepFile} (auto-proceed).

**Conflicts were resolved (user interaction occurred):** present "**Merge complete with conflict resolution. Select:** [C] Continue to Validation" and wait for the user to confirm before loading {nextStepFile}.

**Headless (`{headless_mode}` true):**

- Clean merge → auto-continue and append to in-context `headless_decisions[]` (surfaced via `SKF_UPDATE_RESULT_JSON` by step 7): `{gate: "merge.clean-merge-gate", default_action: "C", taken_action: "C", reason: "headless: clean merge, no conflicts to resolve"}`.
- Conflicts present → halt even in headless mode (conflicts require human judgment): status `halted-for-manual-mismatch`, emitting the halt envelope per SKILL.md §Headless (`error: {phase: "merge:conflict-resolution", reason: "..."}`); no `headless_decisions[]` entry is added.

