# Draft Checkpoint Lifecycle

The `.brief-draft.json` file at `{forge_data_folder}/{skill-name}/.brief-draft.json` is a step-01 in-flight-state checkpoint. It exists only while the workflow has progressed past §7 but not yet completed step-05 — once the final brief writes successfully, step-05 §4 removes it.

**Headless mode skips this entire lifecycle** — the run completes in a single invocation, so no resume is meaningful and no checkpoint is written.

The two halves of the lifecycle (resume on entry, write on §7 confirmation) form a pair. This file documents both so a single load covers them.

## Half 1 — Resume Check (loaded from §6 after name confirmation)

After the skill name is confirmed in §6, check for an in-progress draft at `{forge_data_folder}/{name}/.brief-draft.json`. **Only present the resume prompt** when the file exists AND no `skill-brief.yaml` sits beside it (a finished brief uses the same dir; if a finished brief exists, the draft is stale and step-05's overwrite gate is the right control point).

When the precondition is met, present:

```
**An in-progress draft for `{name}` was found** (last updated: {mtime}).
  [Y] Resume from the saved draft (jump to §8 with prior answers restored)
  [N] Start fresh (delete the draft and re-gather)
```

### `[Y]` — Resume

Load the JSON and restore the captured fields: `target_repo`, `source_type`, `source_authority`, `target_version`, `doc_urls`, `intent`, `scope_hint`, `description`, `forge_tier`, `tier_source`. Then jump directly to §8 — **skip the rest of §6, all of §7, and all of §7b**.

The skip rule for §7b is load-bearing: re-running §7b would overwrite the user's previously accepted `description` with a fresh candidate synthesized from the seed material. The restored `description` is authoritative.

The user can still revise any field at step-04 §3 if a refinement is needed after the full brief is visible.

### `[N]` — Start fresh

Delete `.brief-draft.json` and continue forward to §7 — the collision check and portfolio-similarity check have already executed earlier in §6 (before the resume prompt fired) and do not repeat. §7 / §7b then proceed in their normal order.

## Half 2 — Checkpoint Write (loaded from §7 after summary confirmation)

After the user confirms the §7 summary, persist the captured state atomically. Write a single JSON object with all of:

- `target_repo`, `source_type`, `source_authority`
- `target_version` (if set)
- `doc_urls` (if collected)
- `intent`, `scope_hint`
- `description` (the §7b accepted text)
- `forge_tier`, `tier_source` (for diagnostics)

Atomic-write protocol: write to `.brief-draft.json.tmp` first, then `mv .brief-draft.json.tmp .brief-draft.json`. The rename is atomic on a single filesystem; a partial write never becomes visible as `.brief-draft.json`.

The file is removed by step-05 §4 after the final brief writes successfully.
