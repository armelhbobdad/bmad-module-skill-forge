---
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. With neither, Half 2 writes no checkpoint.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

# Draft Checkpoint Lifecycle

The `.brief-draft.json` file at `{forge_data_folder}/{skill-name}/.brief-draft.json` is the in-flight checkpoint of an interactive run. Half 2 writes it twice: after step 1 §7b, when the gathered intent and the accepted description exist, and again after step 3's scope decisions (scope-definition.md §5c), so it then holds the scope too. Once the final brief writes successfully, step 5 §3 removes it.

**Headless mode skips this entire lifecycle** — the run completes in a single invocation, so no resume is meaningful and no checkpoint is written.

The two halves of the lifecycle (resume after the target is confirmed in §3, write after §7b and after step 3) form a pair. This file documents both so a single load covers them.

## Half 1: Resume Check (loaded from §3 after the target is confirmed)

Keyed on the confirmed **target**, not the derived skill name, so the offer can fire right after §3, before the returning user re-answers version (§3b), intent (§4), or scope (§5), which is exactly the state a draft restores. The caller (gather-intent §3) has selected the candidate draft; its directory basename is the candidate skill `name`. Present the resume prompt for that draft.

When a live draft is found, present:

```
**An in-progress draft for `{name}` was found** (last updated: {mtime}).
  [Y] Resume from the saved draft (prior answers restored)
  [N] Start fresh (ignore this draft and keep gathering)
```

### `[Y]` — Resume

Restore the candidate `name` (the matched draft's directory basename), then load the JSON and restore the step 1 fields it holds: `target_repo`, `source_type`, `source_authority`, `target_version`, `target_ref`, `doc_urls`, `intent`, `scope_hint`, `description`, `forge_tier`, `tier_source`.

- **A draft written after step 3** (it holds `scope`): restore its step 3 fields too, `language`, `detected_version`, `analysis_ref` and `monorepo_workspace`, `scripts_intent` and `assets_intent`, and `scope.type` / `scope.include` / `scope.exclude` / `scope.tier_a_include` / `scope.notes` / `scope.rationale` / `scope.registry_path` / `scope.ui_variants` / `scope.demo_patterns` ← `draft.scope.*`, each kept verbatim as gather-intent §3.1a keeps a ratified brief's. Then load, read entire file, and execute `references/confirm-brief.md` (step 4): steps 2 and 3 already ran in the session that wrote the draft. A `[R] Revise Scope` there re-runs step 2 first, because this session has no staged analysis (scope-definition.md Rules).
- **A draft written after step 1 §7b** (no `scope`): jump directly to §8.

Either way **§3b, §4, §5, §6, §7, and §7b are skipped**, so the version, intent, scope, and description the draft already holds are never re-gathered.

The skip rule for §7b is load-bearing: re-running §7b would overwrite the user's previously accepted `description` with a fresh candidate synthesized from the seed material. The restored `description` is authoritative. §6 is skipped too, so the restored `name` is used as-is — it already cleared the collision and portfolio-similarity checks in the session that wrote the draft.

The user can still revise any field at step 4 §3 if a refinement is needed after the full brief is visible.

### `[N]` — Start fresh

Leave the draft in place and continue forward to §3b: the normal gather flow (§3b version, §4 intent, §5 scope, §6 name) resumes, and the §6 collision / portfolio-similarity checks run in their usual place. Do not delete the draft here: the skill name has not been chosen yet, so there is nothing to key a deletion on. If the user lands on the same name, the next checkpoint write replaces the stale draft; otherwise it stays a harmless orphan that the resume check offers again on a future run targeting the same repo.

## Half 2: Checkpoint Write (loaded from step 1 §7b, and from step 3 §5c)

Write one JSON object with every field the run holds so far:

- After step 1 §7b: `target_repo`, `source_type`, `source_authority`, `target_version` (if set), `target_ref` (if set), `doc_urls` (if collected), `intent`, `scope_hint`, `description` (the §7b accepted text), and `forge_tier`, `tier_source` (for diagnostics).
- After step 3 (§5c), the same fields plus the scope: `language`, `detected_version` (step 2's, or null), `analysis_ref`, `monorepo_workspace` (if set), `scripts_intent`, `assets_intent`, and `scope` with `type`, `include`, `exclude`, `notes` and, when set, `tier_a_include`, `rationale`, `registry_path`, `ui_variants` and `demo_patterns`.

Stage the object in the run folder, then write it with `{atomicWriteHelper}` (resolved from `{atomicWriteProbeOrder}`), which creates the skill's folder when it does not exist yet and renames a complete file into place, so a partial write never becomes visible as `.brief-draft.json`:

```bash
cat > "{run_dir}/draft.json" <<'SKF_JSON'
<the draft, as one JSON object>
SKF_JSON
uv run {atomicWriteHelper} write --target "{forge_data_folder}/{skill-name}/.brief-draft.json" < "{run_dir}/draft.json"
```

The checkpoint is a convenience: when the helper has no path or the write fails, log `warn: draft checkpoint not written ({reason})` and continue.

The file is removed by step 5 §3 after the final brief writes successfully.
