# Draft Checkpoint Lifecycle

The `.brief-draft.json` file at `{forge_data_folder}/{skill-name}/.brief-draft.json` is a step 1 in-flight-state checkpoint. It exists only while the workflow has progressed past §7 but not yet completed step 5 — once the final brief writes successfully, step 5 §4 removes it.

**Headless mode skips this entire lifecycle** — the run completes in a single invocation, so no resume is meaningful and no checkpoint is written.

The two halves of the lifecycle (resume after the target is confirmed in §3, write on §7 confirmation) form a pair. This file documents both so a single load covers them.

## Half 1 — Resume Check (loaded from §3 after the target is confirmed)

Keyed on the confirmed **target**, not the derived skill name, so the offer can fire right after §3 — before the returning user re-answers version (§3b), intent (§4), or scope (§5), which is exactly the state a draft restores. The caller (gather-intent §3) has already globbed `{forge_data_folder}/*/.brief-draft.json`, kept only drafts whose `target_repo` equals the confirmed target (or whose `doc_urls` contain it, for docs-only) with no `skill-brief.yaml` beside them, and selected the most-recently-modified survivor. Its directory basename is the candidate skill `name`. Present the resume prompt for that draft.

When a live draft is found, present:

```
**An in-progress draft for `{name}` was found** (last updated: {mtime}).
  [Y] Resume from the saved draft (jump to §8 with prior answers restored)
  [N] Start fresh (ignore this draft and keep gathering)
```

### `[Y]` — Resume

Restore the candidate `name` (the matched draft's directory basename), then load the JSON and restore the captured fields: `target_repo`, `source_type`, `source_authority`, `target_version`, `doc_urls`, `intent`, `scope_hint`, `description`, `forge_tier`, `tier_source`. Then jump directly to §8 — **skip §3b, §4, §5, §6, §7, and §7b** — so the version, intent, scope, and description the draft already holds are never re-gathered.

The skip rule for §7b is load-bearing: re-running §7b would overwrite the user's previously accepted `description` with a fresh candidate synthesized from the seed material. The restored `description` is authoritative. §6 is skipped too, so the restored `name` is used as-is — it already cleared the collision and portfolio-similarity checks in the session that wrote the draft.

The user can still revise any field at step 4 §3 if a refinement is needed after the full brief is visible.

### `[N]` — Start fresh

Leave the draft in place and continue forward to §3b — the normal gather flow (§3b version, §4 intent, §5 scope, §6 name) resumes, and the §6 collision / portfolio-similarity checks run in their usual place. Do not delete the draft here: the skill name has not been chosen yet, so there is nothing to key a deletion on. If the user lands on the same name, step 5's atomic write overwrites the stale draft; otherwise it stays a harmless orphan that the resume check offers again on a future run targeting the same repo.

## Half 2 — Checkpoint Write (loaded from §7 after summary confirmation)

After the user confirms the §7 summary, persist the captured state atomically. Write a single JSON object with all of:

- `target_repo`, `source_type`, `source_authority`
- `target_version` (if set)
- `doc_urls` (if collected)
- `intent`, `scope_hint`
- `description` (the §7b accepted text)
- `forge_tier`, `tier_source` (for diagnostics)

Atomic-write protocol: write to `.brief-draft.json.tmp` first, then `mv .brief-draft.json.tmp .brief-draft.json`. The rename is atomic on a single filesystem; a partial write never becomes visible as `.brief-draft.json`.

The file is removed by step 5 §4 after the final brief writes successfully.
