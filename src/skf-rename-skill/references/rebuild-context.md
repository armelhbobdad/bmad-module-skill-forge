---
# Static reference loaded by execute.md §7. The carve removes ~70
# lines of context-rebuild loop logic from the main execute.md so
# the §1–§6 + §8–§10 critical-path stays tight; §7 itself is always
# reached on the success path so this file loads on every successful
# rename, but the rollback paths (§4–§6 failure jumps) skip §7
# entirely and never load this reference.
---

<!-- Config: communicate in {communication_language}. Render the rebuilt-files report in {document_output_language}. -->

# Rename: Rebuild Context Files (per-IDE managed-section sweep)

## Purpose

After §6 re-keys the manifest from `{old_name}` to `{new_name}`, every IDE's context file (`CLAUDE.md`, `.cursorrules`, `AGENTS.md`, etc.) still contains the old name in its managed-section snippet rows. This step rewrites each one in-place via the surgical between-marker swap so the on-disk managed sections reflect the new name.

Loaded by `execute.md` §7 once `manifest_updated == true` (§6 succeeded) and the rollback paths in §4–§6 were not taken.

## Resolve target_context_files

Load the `ides` list from `config.yaml`. The installer writes IDE identifiers — these must be mapped to context files and skill roots using the "IDE → Context File Mapping" table in `{managedSectionLogic}`:

1. For each entry in `config.yaml.ides`, look up its `context_file` and `skill_root` from the mapping table.
2. For any entry not found in the table, default to AGENTS.md / `.agents/skills/` and emit a warning: `Unknown IDE '{value}' in config.yaml — defaulting to AGENTS.md`.
3. Deduplicate by `context_file` — when multiple IDEs map to the same context file, use the first configured IDE's `skill_root`.
4. If `config.yaml.ides` is absent or the mapping yields an empty list, fall back to `[{context_file: "AGENTS.md", skill_root: ".agents/skills/"}]` and emit a note: `No IDEs configured in config.yaml — defaulting to AGENTS.md`.

Store the result as `target_context_files`.

## Per-file loop

For each entry in `target_context_files`:

### 1. Resolve target file

Resolve the absolute path at `{context_file}`.

### 2. Read the current file

- If the file does not exist, skip this context file (nothing to rebuild — the file will be re-created the next time export-skill runs).
- If the file exists but contains no `<!-- SKF:BEGIN -->` marker, skip this context file (no managed section to rewrite).
- If the file contains `<!-- SKF:BEGIN -->` but no matching `<!-- SKF:END -->`, record the error against that context file and continue to the next entry — do not halt the entire rename on a malformed context file.

### 3. Build the exported skill set (version-aware, deprecated-excluded)

Use the same logic as `skf-export-skill/references/update-context.md` §4b and the snippet resolution from §4c:

- Read the manifest's `exports` object (already updated in §6, so `{new_name}` is present and `{old_name}` is absent).
- For each skill, resolve its `active_version`.
- If `versions.{active_version}.status == "deprecated"`, skip that skill entirely.
- For each remaining `{skill-name, active_version}` pair, read `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`.
- If missing, fall back to the `active` symlink path; if still missing, skip with a warning.

### 4. Rewrite root paths for the current context file

Use the generic rewrite algorithm from `skf-export-skill/references/update-context.md` §4d:

For each snippet, parse the `root:` line (`root: {prefix}{skill-name}/`), strip the trailing `{skill-name}/` to extract the current prefix, and replace it with the **effective target prefix** if different. The effective target prefix is `snippet_skill_root_override` when that key is set in `config.yaml` — applied uniformly to every snippet so the managed section references the real on-disk location and never mixes override and per-IDE paths — otherwise the current entry's `skill_root`. See `skf-export-skill/references/update-context.md` §4d for full semantics.

### 5. Sort and count

Sort skills alphabetically by name. Count totals (skills, stack skills).

### 6. Assemble the new managed section

Use the format from `{managedSectionLogic}`:

```markdown
<!-- SKF:BEGIN updated:{current-date} -->
[SKF Skills]|{n} skills|{m} stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|{skill-snippet-1}
|
|{skill-snippet-2}
|
|{skill-snippet-N}
<!-- SKF:END -->
```

### 7. Surgical replacement — atomic, deterministic

Invoke `{rebuildManagedSectionsHelper}` (resolved from `{rebuildManagedSectionsProbeOrder}` in `execute.md` frontmatter) for the surgical between-marker swap:

```bash
python3 {rebuildManagedSectionsHelper} {context_file} replace --content "{new_managed_section_text}"
```

The helper handles marker location, between-marker swap, atomic temp-file + rename, and post-write verification (markers preserved, content outside markers byte-identical). It exits non-zero on any failure with a clear `stderr` reason.

### 8. Verify (deferred to helper)

The `replace` action above performs verification internally. Treat any non-zero exit code as a per-file failure (next bullet).

### 9. On per-file failure

Record the error against that context file and continue to the next entry. Do not halt the rename on a recoverable per-context-file error — the manifest and filesystem are already consistent; context files can be re-rebuilt later via `[EX] Export Skill`.

## After the loop

- Record `context_files_updated` as the list of files that were successfully rewritten.
- Record `context_files_failed` as the list of any that failed.

Report: `**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list} — re-run [EX] Export Skill to retry.'}`

## Rollback semantics

§7 failures **do not** trigger a rollback. The manifest and filesystem are the canonical state — context files are derived artifacts that can be regenerated at any time via `[EX] Export Skill`. The rename is considered successful as soon as §6 lands, even if §7 partially or fully fails to rewrite context files.
