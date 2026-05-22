---
nextStepFile: 'token-report.md'
managedSectionData: '{managedSectionFormatPath}'
# Resolve `{rebuildManagedSectionsHelper}` by probing
# `{rebuildManagedSectionsProbeOrder}` in order (installed SKF module path
# first, src/ dev-checkout fallback); first existing path wins. §9 uses
# the `replace` action for the surgical between-marker swap with
# atomic temp-file + rename, marker preservation, and post-write verify.
# HALT if no candidate exists — the in-prompt prose path silently regresses
# the Case 4 (malformed markers) HARD HALT guarantee.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# Resolve `{manifestOpsHelper}` similarly. §9b uses `read` / `set` for
# atomic v2-schema-aware manifest mutation (handles v1→v2 migration and
# `platforms`→`ides` rename internally).
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# Resolve `{atomicWriteHelper}` similarly. §6 Case 1 (Create) and §6
# Case 2 (Append) use it via `write` for safe artifact emission — the
# in-prompt write would risk half-written files on process kill.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. Render the change preview and managed section in {document_output_language}. -->

# Step 4: Update Context

## STEP GOAL:

To update the managed `<!-- SKF:BEGIN/END -->` section in the platform-appropriate context file (CLAUDE.md/AGENTS.md/.cursorrules) using the four-case logic defined by ADR-J (Create, Append, Regenerate, Malformed Markers halt), rebuilding the complete skill index from all exported skills.

## Rules

- Focus only on the managed section update in the target context file
- Do not modify any content outside `<!-- SKF:BEGIN -->` and `<!-- SKF:END -->` markers
- Do not write without user confirmation — this modifies shared project files
- If `passive_context: false` was detected in step 1, skip this step entirely
- **Multi-skill mode:** this step executes ONCE for the whole batch, not once per skill. §4b already builds the exported skill set from the manifest (plus current export targets), so a multi-skill run naturally appears as a single rebuild. The only batch adjustment is in §9b: update the manifest entry for every skill in `skill_batch` (not just one), and include all of them when computing `ides_written`. See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step 1:**

"**Passive context disabled in preferences.yaml. Skipping context update.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to step 2.

### 2. Load Managed Section Format

Load {managedSectionData} and read the complete format template and four-case logic.

### 3. Determine Target File(s)

Using the `target_context_files` list resolved in step 1, determine all target files. Each entry has `{context_file, skill_root}` — the context file to write and the IDE's skill directory for root path resolution.

For each entry in `target_context_files`, resolve target file path: `{context_file}`

**If multiple context files:** Sections 4-9a execute as a loop — one full pass per target context file. Each iteration uses the same skill index but rewrites root paths per context file's `skill_root` (section 4d) and writes to the target context file. Section 9b executes once after all iterations complete.

**Processing order:** Process context files in the order listed in `target_context_files`.

#### 3b. Detect Orphaned Platform Files (Stale Managed Sections)

A context file becomes orphaned when its IDE is removed from `config.yaml` after a prior export. The file still contains an SKF managed section pointing to stale skill versions, but no future export will rewrite it.

**Cheap pre-check (always run, ~3 file existence checks):** build `orphaned_context_files` — for each known context file in `{CLAUDE.md, .cursorrules, AGENTS.md}` that is NOT in `target_context_files`, check whether it exists on disk and contains the `<!-- SKF:BEGIN -->` marker. If yes, add `{context_file, file_path}` to `orphaned_context_files`.

**If `orphaned_context_files` is non-empty:** load `references/orphan-context-detection.md` and follow its (a) clear / (b) keep / (c) rewrite gate protocol. The reference handles user prompting, headless default (keep), and downstream-state recording (`orphans_cleared`, `orphans_rewritten`, `rewrite_context_files`). When the user chooses (c), the §4–§9a loop iterates over `target_context_files + rewrite_context_files`.

**If `orphaned_context_files` is empty:** proceed to §4.

### 4. Rebuild Complete Skill Index

#### 4a. Read Export Manifest (v2 — version-aware)

Read the manifest via `{manifestOpsHelper}` (resolved at §9 from `{manifestOpsProbeOrder}` — see frontmatter):

```bash
python3 {manifestOpsHelper} {skills_output_folder} read
```

The helper handles v2-schema enforcement, v1→v2 migration, and the `platforms`→`ides` rename internally. The returned JSON is always in canonical v2 shape regardless of on-disk state.

**Schema reference:** `references/manifest-rebuild.md` documents the v2 shape, the status enum (`active`/`archived`/`deprecated`/`draft`), the v1 migration path, and the `active_version` integrity invariant. Load that file only when an inline schema reminder is needed — the helper enforces the shape so the in-prompt prose is not load-bearing.

**Integrity guard:** if the helper returns an entry where `active_version` does not resolve to a key in `versions`, the manifest is inconsistent. Skip the affected skill and log: "**Manifest integrity warning:** `{skill-name}.active_version = v{active_version}` has no matching entry under `versions`. Skipping. Re-run `[EX] Export Skill` on `{skill-name}` to repair the manifest entry."

**If the manifest does not exist** (first export or fresh forge): the helper returns `{"schema_version": "2", "exports": {}}`. Only the current export target will appear in the rebuilt index.

#### 4b. Build Exported Skill Set (version-aware)

Determine the set of skills to include in the rebuilt index:

1. Start with all skill names listed in the manifest's `exports` object (if manifest exists)
2. For each skill, record its `active_version` from the manifest (v2 schema)
3. **Integrity guard — `active_version` must resolve to a versions entry:** Check that `versions[active_version]` exists as a key. If `active_version` is set but there is no matching entry under `versions`, the manifest is inconsistent (possible corruption or a botched v1→v2 migration). Skip this skill and log a loud warning: "**Manifest integrity warning:** `{skill-name}.active_version = v{active_version}` has no matching entry under `versions`. Skipping. Re-run `[EX] Export Skill` on `{skill-name}` to repair the manifest entry."
4. **Exclude deprecated skills:** If the `active_version` entry in `versions.{active_version}` has `status: "deprecated"`, skip this skill entirely — it has been dropped via drop-skill workflow and must not appear in the managed section. Log: "Skipping {skill-name} — active version v{active_version} is deprecated"
5. Add the current export target skill name (ensures it is always included even before manifest is written) — use the version from `{resolved_skill_package}/metadata.json` as its `active_version`
6. This is the **exported skill set** — each entry has a skill name and its resolved `active_version`

#### 4c. Resolve and Filter Snippets (manifest-driven — replaces glob scan)

Instead of globbing `{skills_output_folder}/*/context-snippet.md`, resolve snippets from the exported skill set built in 4b:

**For each skill in the exported skill set:**
1. Resolve `{skill_package}` using the skill's `active_version`: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. Read `{skill_package}/context-snippet.md`
3. **If snippet exists:** Add to skill index
4. **If snippet does not exist at the versioned path:** Check for `active` symlink at `{skills_output_folder}/{skill-name}/active/{skill-name}/context-snippet.md`. If still not found, skip with warning: "Snippet missing for {skill-name} v{active_version} — skipping from managed section"

**Skills NOT in the exported skill set are never scanned** — they have not been through export-skill and must not appear in the managed section (ADR-K).

**If no snippets pass the filter:** Generate managed section with zero skills — header only, no skill entries.

#### 4c.1 Detect Orphaned Managed-Section Rows (manifest-absent skills)

A managed-section row becomes orphaned when a `[skill-name v...]` entry already exists in the prior managed section but the skill is not in the exported skill set built in 4b — typically an externally-installed skill authored in a different repo and dropped into `{skills_output_folder}` without going through export-skill. Strict ADR-K would silently drop such rows, but the user's managed section is load-bearing — silent removal is a regression.

**Cheap pre-check (always run before §5 assembly).** Scan **every** target context file (not just the first), deduplicate by `(skill_name, version)`, and present one consolidated gate. Asymmetric orphans — a row present in `.cursorrules` but absent from `CLAUDE.md`, or vice versa — must be detected; otherwise the §4 rebuild loop silently overwrites the orphan-bearing file's content (ADR-J violation: silent loss of user content).

1. Initialize `orphan_managed_rows = []` (a list of `{skill_name, version, snippet_text, source_files: []}` entries — `source_files` carries provenance for the gate display and the audit `deviations[]` entry).
2. **Iterate every entry in `target_context_files`:**
   a. Read the prior managed section from `{entry.context_file}`. If the file does not exist or has no `<!-- SKF:BEGIN -->` marker, skip this entry — it has no orphans by definition.
   b. Parse the `[skill-name v...]` rows between `<!-- SKF:BEGIN -->` and `<!-- SKF:END -->` into `file_rows` — a list of `{skill_name, version, snippet_text}` triples (capture the original snippet line(s) verbatim so they can be re-emitted unchanged if (b) is chosen).
   c. For each `row` in `file_rows`:
      - If `row.skill_name` is in the exported skill set built in 4b (manifest entries plus current-export targets), skip — not an orphan.
      - Otherwise look up `(row.skill_name, row.version)` in `orphan_managed_rows`:
        - If already present, append `entry.context_file` to that row's `source_files` list (deduplicated). Keep the first-encountered `snippet_text` — divergent snippets across files for the same `(skill, version)` are themselves a user-content asymmetry but the `(b) Preserve verbatim` semantic writes one canonical row to every target file, so picking the first is deterministic and avoids silently choosing.
        - If new, append `{skill_name: row.skill_name, version: row.version, snippet_text: row.snippet_text, source_files: [entry.context_file]}`.

**If `orphan_managed_rows` is non-empty:** load `references/orphan-row-detection.md` and follow its (a) Drop / (b) Preserve verbatim / (c) Cancel gate protocol. The reference handles user prompting (with per-orphan `source_files` provenance), headless default (Preserve verbatim), `deviations[]` recording (including `source_files` per orphan for audit), and §6 result-contract integration.

**If `orphan_managed_rows` is empty:** proceed to §4d.

#### 4d. Rewrite Root Paths for Target Context File

The context-snippet.md files on disk contain root paths for the IDE they were originally exported to. When assembling the managed section for the current target context file, rewrite root paths if they differ from the target's `skill_root`.

**Generic root path rewrite algorithm** (no hardcoded prefix list):

For each snippet being included in the managed section:

1. Read the `root:` value from the snippet's first line — it has the form `root: {prefix}{skill-name}/`
2. Extract the current prefix by stripping the trailing `{skill-name}/` from the root value
3. **Resolve the effective target prefix:** If `snippet_skill_root_override` is set in config.yaml, use the override value as the effective target prefix for this rebuild — by the override contract every skill in the repo lives under that single shared on-disk directory, so the managed section must reference the override for *every* snippet (not just the ones that already match it). Otherwise, use the current target's `skill_root` as the effective target prefix.
4. Compare the extracted prefix against the effective target prefix
5. If they differ, replace the prefix with the effective target prefix, preserving the skill name. When the override is set, this rewrites stale per-IDE prefixes carried by sibling snippets that were exported before the override was adopted, so the rebuilt managed section uniformly references the real on-disk location instead of mixing override and per-IDE paths.
6. Example: if snippet has `root: .claude/skills/my-lib/` but target skill_root is `.windsurf/skills/`, rewrite to `root: .windsurf/skills/my-lib/`
7. Example: if `snippet_skill_root_override: skills/` is set, the effective target prefix is `skills/` regardless of the IDE mapping. A snippet with `root: skills/my-lib/` passes through unchanged; a sibling snippet with `root: .claude/skills/my-other/` (carried over from a pre-override export) is rewritten to `root: skills/my-other/`.

This algorithm handles any IDE's skill root path — including future IDEs — without enumerating known prefixes. The legacy `skills/` prefix (no leading dot) may appear in draft snippets generated by create-skill/quick-skill before export.

**Sort skills alphabetically by name.**

Count totals:
- Total skills (single type)
- Total stack skills

### 5. Generate Managed Section

Assemble the managed section in **two shapes** — the §9 write paths consume different forms, and conflating them double-wraps the markers.

**`{managed_section_inner}`** — the between-marker body only, **no** `<!-- SKF:BEGIN/END -->` markers. The `insert` and `replace` helper actions supply the markers (and the `updated:` timestamp) themselves, so they take this inner form:

```markdown
[SKF Skills]|{n} skills|{m} stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|{skill-snippet-1}
|
|{skill-snippet-2}
|
|{skill-snippet-N}
```

**`{managed_section_full}`** — `{managed_section_inner}` wrapped in markers. Used for the new-file create path (atomic write, which writes the text verbatim) and the §7 preview:

```markdown
<!-- SKF:BEGIN updated:{current-date} -->
{managed_section_inner}
<!-- SKF:END -->
```

### 6. Detect Case and Prepare Changes

**Check target file at `{target-file}`:**

**Case 1: Create (file does not exist)**
- Action: Create new file with managed section only
- Diff: Show entire managed section as new content

**Case 2: Append (file exists, no `<!-- SKF:BEGIN` marker found)**
- Action: Read existing content, append managed section at end
- Diff: Show managed section being appended after existing content
- Preserved: ALL existing content untouched

**Case 3: Regenerate (file contains `<!-- SKF:BEGIN` and `<!-- SKF:END -->`)**
- Action: Replace everything between markers (inclusive) with new managed section
- Diff: Show old managed section vs new managed section
- Preserved: ALL content before `<!-- SKF:BEGIN` and after `<!-- SKF:END -->`

**Case 4: Malformed markers (file contains `<!-- SKF:BEGIN` but no `<!-- SKF:END -->`)**
- Action: HALT (exit code 5, `halt_reason: "malformed-markers"`) with warning: "Malformed SKF markers detected in `{target-file}` — `<!-- SKF:BEGIN` found but `<!-- SKF:END -->` is missing. Please restore the end marker manually before running export."
- Do NOT attempt to write or append — the file is in an inconsistent state.
- In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `manifest_path: null`, `context_files_updated: []`.

### 7. Present Change Preview

"**Context update prepared.{if multi-platform: ' (platform {i}/{total}: {platform})'}**

**Target:** `{target-file}`
**Case:** {1: Create / 2: Append / 3: Regenerate}
**Skills in index:** {n} skills, {m} stack

**Changes:**

{Show diff preview:}
- For Case 1: Show full file content to be created
- For Case 2: Show `...existing content preserved...\n\n{managed section}`
- For Case 3: Show old section vs new section with surrounding context preserved

**Content outside markers:** {preserved / n/a (new file)}

**Ready to write changes?**"

### 8. Present MENU OPTIONS

**If dry-run mode:**

"**[DRY RUN] No files will be written. Preview above shows what would change.**

**Proceeding to token report...**"

Auto-proceed to {nextStepFile}.

**If NOT dry-run:**

Display: "**Select:** [C] Continue — write changes to {target-file} | [X] Cancel and exit (or type `cancel` / `exit` / `:q`)"

**Multi-target behavior:** When processing multiple context files, present all previews together before asking for a single confirmation. After confirmation, write all target files sequentially, verifying each one.

"**Targets:** {list all context-file → target-file pairs}
**Ready to write changes to all targets?**"

Display: "**Select:** [C] Continue — write changes to all targets | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Write the changes to all target files (or single target), verify each write succeeded, then load, read entire file, then execute {nextStepFile}
- IF X (or `cancel` / `exit` / `:q`): Display "Cancelled — no context files were written." and HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with the resolved `skills`, `context_files_updated: []`, and `manifest_path: null`.
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-approve context file update"
- ONLY proceed to next step when user selects 'C'
- In dry-run mode, auto-proceed without writing

### 9. Write and Verify (Non-Dry-Run Only)

After user confirms with 'C', resolve the helpers in parallel — these are independent file-existence checks that batch into one tool-call message:

- `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` (used for Cases 2 and 3)
- `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (used for Case 1)
- `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}` (used in §9b)

If any helper has no existing candidate, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) and emit the error envelope per SKILL.md "Result Contract (Headless)" — the rewrite's safety guarantees depend on these helpers and a fall-through to LLM-driven writes would silently regress atomicity, marker preservation, and the Case 4 malformed-marker HARD HALT contract.

For each target context file, dispatch by case:

**Case 1 (Create — file does not exist):**

```bash
echo "{managed_section_full}" | python3 {atomicWriteHelper} write "{target-file}"
```

The helper stages the content into `<target>.skf-tmp`, fsyncs, and atomically renames into place. This path writes verbatim, so it takes the **marker-bearing** `{managed_section_full}`.

**Case 2 (Append — file exists, no `<!-- SKF:BEGIN` marker):**

```bash
python3 {rebuildManagedSectionsHelper} {target-file} insert --content "{managed_section_inner}"
```

The helper appends the managed section to the end of the file via the same atomic temp-file + rename pattern. Pass the **inner-only** `{managed_section_inner}` — the helper adds the markers and `updated:` timestamp itself; passing marker-bearing text double-wraps them.

**Case 3 (Regenerate — file contains `<!-- SKF:BEGIN` and `<!-- SKF:END -->`):**

```bash
python3 {rebuildManagedSectionsHelper} {target-file} replace --content "{managed_section_inner}"
```

The helper performs the surgical between-marker swap with post-write verification (markers present, content outside markers byte-identical). Pass the **inner-only** `{managed_section_inner}` — as with `insert`, the helper supplies the markers; marker-bearing text double-wraps them.

**Case 4 (malformed markers — already HALTed in §6):** never reaches here.

**Verification (deferred to helpers):** the `replace`/`insert`/`write` actions above each perform their own verification. Treat any non-zero exit as a write failure:

- HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) and report `{target-file}: {captured stderr}`.
- In headless mode, emit the error envelope.
- Continue to the next target file only on success — partial-batch writes are acceptable in single-skill mode but the overall envelope reports per-target outcomes.

On success per file, report: "**{target-file} updated successfully.** Verified by `{rebuildManagedSectionsHelper}` (or `{atomicWriteHelper}` for Case 1)."

### 9b. Update Export Manifest (Non-Dry-Run Only)

**This section executes ONCE after all context-file iterations complete** (outside the per-context-file loop defined in section 3). Only IDEs whose target context files were successfully written and verified in section 9 are recorded.

**`ides` field definition:** `ides` is the list of IDE identifiers from `config.yaml.ides` (e.g. `claude-code`, `cursor`, `github-copilot`) whose context files were successfully written and verified in section 9. It is NOT the context file name (`CLAUDE.md`) and NOT the skill root path (`.claude/skills/`). Each IDE → context file → skill root mapping is defined in `skf-export-skill/assets/managed-section-format.md`.

1. Read `{skills_output_folder}/.export-manifest.json` (or start with `{"schema_version": "2", "exports": {}}` if it does not exist)
2. Ensure `schema_version` is `"2"` (if v1 was migrated in section 4a, the migrated structure is already in context). If any version entry still has a legacy `platforms` key, rename it to `ides` in place (see §4a).
3. Compute `ides_written` — the set of IDE identifiers from `config.yaml.ides` whose mapped context file was successfully written in section 9 (deduplicated, sorted). When `--context-file` was passed explicitly, `ides_written` contains only the IDEs that map to that single context file.
4. For each skill in `skill_batch` (multi-skill mode) — or the single current skill (single-skill mode) — add or update its entry in v2 format:
   ```json
   "{skill-name}": {
     "active_version": "{version}",
     "versions": {
       "{version}": {
         "ides": ["{ides_written}"],
         "last_exported": "{current-date}",
         "status": "active"
       }
     }
   }
   ```
   - `{version}` is the version from each skill's `{resolved_skill_package}/metadata.json`
   - If the skill already has a manifest entry:
     - Set `active_version` to the current version
     - If the version already exists in `versions`, union its existing `ides` with `ides_written` (deduplicate, keep sorted), refresh `last_exported`, and set `status: "active"`
     - If this is a new version, add it to `versions` with `status: "active"` and set any previously-active version's status to `"archived"`
     - Preserve all other version entries in `versions` (do not delete archived versions)
5. Write the updated manifest atomically via `{manifestOpsHelper}` after all skills in the batch have been applied. For each skill / version pair, invoke:

   ```bash
   python3 {manifestOpsHelper} {skills_output_folder} set {skill-name} {version} --ides {ides_written}
   ```

   `{ides_written}` is the comma-joined sorted IDE set computed in step 3. The helper handles v2-schema validation, v1→v2 migration, and `platforms`→`ides` rename internally — no in-prompt JSON manipulation needed. Each `set` invocation unions the supplied `--ides` into the version entry's existing `ides` (deduplicated, sorted) server-side and refreshes `last_exported`. After all skills have been set, re-read the manifest via `{manifestOpsHelper} {skills_output_folder} read` to confirm the final state matches expectations.

**Dry-run mode:** Do NOT update the manifest. Display: "**[DRY RUN] Export manifest would be updated for {skill-name-list} — ides: {ides_written}.**" (list every skill in `skill_batch`)

**Error handling:** If `{manifestOpsHelper}` exits non-zero, HALT (exit code 4, `halt_reason: "manifest-write-failed"`) with the captured `stderr`. The managed section was already written successfully; the operator's recovery path is to manually reconcile the on-disk managed section with the manifest, then re-run `[EX] Export Skill --all` to refresh the manifest. In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `manifest_path: null` and the partial `context_files_updated` list.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms changes by selecting 'C' (or auto-proceed in dry-run) and the write is verified will you load and read fully `{nextStepFile}` to execute the token report.

