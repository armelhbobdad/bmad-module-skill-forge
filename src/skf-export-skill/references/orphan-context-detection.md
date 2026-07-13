---
# Static reference loaded by update-context.md §3b only when
# `orphaned_context_files` is non-empty (i.e. the cheap pre-check in
# §3b found a context file on disk with an SKF managed section that
# is no longer in the current `target_context_files`). The reference
# carries the (a)/(b)/(c) gate protocol, headless default, and
# downstream-state contract; the trigger detection itself stays
# inline in §3b so the LLM knows when to invoke this protocol.
---

<!-- Config: communicate in {communication_language}. Render the orphan list and gate prompt in {document_output_language}. -->

# Orphan Context-File Detection — Gate Protocol

## Purpose

Handle the (a) clear / (b) keep / (c) rewrite gate when one or more known context files (`CLAUDE.md`, `.cursorrules`, `AGENTS.md`) on disk contain an SKF managed section but their owning IDE is no longer listed in `config.yaml.ides`. Loaded by `update-context.md` §3b after the cheap pre-check populates `orphaned_context_files`.

## Inputs

- `orphaned_context_files` — list of `{context_file, file_path}` entries built by §3b's pre-check
- `target_context_files` — current export's IDE → context-file map (from step 1)
- `{headless_mode}` — boolean flag from workflow context

## Gate Protocol

Emit the warning and gate:

> **Orphaned context files detected.** The following files contain SKF managed sections but no configured IDEs target them:
> {list: context file → file path}
>
> The managed sections in these files are stale. Options:
>
> - **(a) clear** — remove the SKF managed section from each orphaned file (surgical marker replacement, leaves user content intact)
> - **(b) keep** — leave them untouched (they will remain stale until you re-add an IDE that targets this file or delete the file)
> - **(c) rewrite** — also rewrite the orphaned files with the current skill index (use this if the IDE was removed by mistake)

Wait for user choice.

**Headless / non-interactive default:** when `{headless_mode}` (or dry-run, or unattended), default to **(b) keep** and print the warning only — no destructive action without explicit consent.

## Choice handling

### (a) clear

The marker excision is deterministic surgery with one correct answer per input — a mis-parsed boundary silently corrupts the user's surrounding content. Delegate it to the tested `clear` action of `skf-rebuild-managed-sections.py`, the same helper `update-context.md` §9 uses for the between-marker swap; do not excise markers in-prompt. Resolve `{rebuildManagedSectionsHelper}` from `update-context.md`'s `{rebuildManagedSectionsProbeOrder}` frontmatter (first existing path wins). If no candidate exists, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) per `update-context.md` §9 — falling through to an in-prompt excision would regress the atomic-write + post-clear verify guarantee.

For each file in `orphaned_context_files`:

1. Run:

   ```bash
   python3 {rebuildManagedSectionsHelper} {file_path} clear
   ```

   The `clear` action removes the entire `<!-- SKF:BEGIN -->`…`<!-- SKF:END -->` block (and its surrounding blank lines), leaves the rest of the file intact, and performs an atomic temp-file + rename write with a post-clear verify that the section is gone. Treat any non-zero exit (or a `status: "error"` envelope) as a clear failure — HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) reporting `{file_path}: {captured stderr}`. This branch is interactive-only (the headless default is (b) keep), so it emits no result envelope here.
2. On success (`status: "ok"`, `action: "cleared"`), append the file path to `orphans_cleared`. On a non-empty list, record it in the §6 result contract as a `deviations[]` entry (`kind: "clear_orphan_context"`, `files: [...]`) — the extensible deviations mechanism summary.md §6 documents for choices that diverge from the canonical export path.

### (b) keep

Record nothing. The orphaned files remain on disk, untouched. Proceed.

### (c) rewrite

Add each entry in `orphaned_context_files` to a separate `rewrite_context_files` list. This list is kept distinct from `target_context_files` so the user's intent to only export to configured IDEs is preserved in the manifest update at §9b — `rewrite_context_files` participates in the §4–§9a write loop for this run only and is not promoted into the manifest's `ides` arrays.

Use `.agents/skills/` as the default skill root for rewritten orphans (the IDE-neutral path used when the original IDE mapping is no longer available).

Record each rewritten file in `orphans_rewritten`. On a non-empty list, record it in the §6 result contract as a `deviations[]` entry (`kind: "rewrite_orphan_context"`, `files: [...]`) — the same extensible deviations mechanism summary.md §6 documents.

## Downstream contract

After this protocol completes, §3b returns control to §4 with these workflow-context variables populated:

- `orphans_cleared: []` — set when the user chose (a) or stayed empty otherwise
- `orphans_rewritten: []` — set when the user chose (c) or stayed empty otherwise
- `rewrite_context_files: []` — extends the per-context-file iteration in §4–§9a when the user chose (c)

The §4–§9a loop iterates over `target_context_files + rewrite_context_files`. The §9b manifest update reads only `target_context_files` (rewritten orphans are not promoted into the manifest).

## Scope note

This cleanup only runs during interactive export (and the headless default explicitly does nothing destructive). Drop-skill and rename-skill operate on the manifest's declared context files and are not responsible for orphan detection — their scope is the active manifest, not arbitrary on-disk markers.
