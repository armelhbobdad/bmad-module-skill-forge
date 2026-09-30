---
nextStepFile: 'report.md'
# `{qmdClassifyHelper}` and `{forgeTierRwHelper}` = first existing path in
# their `*ProbeOrder` arrays; halt if neither exists for a helper a section
# actually invokes. Both scripts own classification / registry-cleanup
# contracts with no prose fallback.
qmdClassifyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-qmd-classify-collections.py'
  - '{project-root}/src/shared/scripts/skf-qmd-classify-collections.py'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`,
# for the blocked envelope a halt in this step emits under headless or quiet.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. The orphan-removal prompt and the `--orphan-action` auto-decision message (interactive runs only) render in the user's language. -->

# Step 3: QMD + CCC Registry Hygiene

## STEP GOAL:

When the detected tier is Deep, classify live QMD collections against the `qmd_collections` registry and remove orphans only on the user's **[R]** or `--orphan-action=remove`. Whenever ccc is available (Forge+ or Deep), prune `ccc_index_registry` entries whose source paths no longer exist. All set-arithmetic and YAML mutation goes through scripts (`{qmdClassifyHelper}` and `{forgeTierRwHelper}`); the workflow only orchestrates external CLI calls (`qmd collection list`, `qmd collection remove`) and the user-prompt branch.

For Quick and Forge tiers, skip silently and proceed (QMD is not available; ccc registry cleanup only runs when ccc is available regardless of tier).

## Rules

- Focus only on registry hygiene — no new collection creation (that belongs to create-skill)
- Never reimplement the forge-namespace suffix filter in prose — the classifier owns it
- Run `qmd collection remove` only on the interactive **[R]** or an explicit `--orphan-action=remove`: that flag is the consent, and `{orphan_auto_resolution}` records each collection the removal deleted, by name, in the envelope's `warnings`
- Headless and quiet runs must auto-resolve the orphan prompt to the documented default (Keep) unless `--orphan-action` sets it
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If a section needs a helper whose probe order has no existing path, halt (an install fault, not a hygiene error) with phase `step 3:helper-missing`, `path` set to that array's first entry, and reason `Setup cannot proceed: <script file name> was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, pipe `{phase, reason, path}` to `uv run {emitEnvelopeHelper} emit-blocked` and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason
- Do not fail the workflow if hygiene encounters errors; a missing helper is not a hygiene error

## MANDATORY SEQUENCE

### 1. Check Tier

Read `{calculated_tier}` and `{ccc}` from context (set by step 1).

Default `{orphan_auto_resolution}` to null at the top of this step; only the non-interactive branch in section 3 overrides it.

**If `{calculated_tier}` is Quick or Forge AND `{ccc}` is false:** No registry hygiene needed. Set `{hygiene_result: "skipped", hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0}`. Proceed directly to section 5 (Auto-Proceed): no output, no messaging.

**If `{calculated_tier}` is Quick or Forge AND `{ccc}` is true:** No QMD work, but ccc registry needs pruning. Set QMD-related flags to defaults (`hygiene_result: "skipped"`, all hygiene_* counts = 0). Skip directly to section 4 (Stale Registry Cleanup), running it with the ccc-prune flag only.

**If `{calculated_tier}` is Forge+:** Same as Quick/Forge with ccc — no QMD work (qmd unavailable at Forge+), but ccc registry hygiene runs.

**If `{calculated_tier}` is Deep:** Continue to section 2.

### 2. Classify Live QMD Collections vs Registry

Run the classifier, which owns the `qmd collection list` invocation and stdout parsing, into the run folder. Invoke via `uv run`:

```bash
uv run {qmdClassifyHelper} \
    --registry-from-yaml "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" \
    > "{run_dir}/qmd-classify.json" && cat "{run_dir}/qmd-classify.json"
```

The script (see `src/shared/scripts/skf-qmd-classify-collections.py` docstring for the full schema) invokes `qmd collection list` itself, applies the forge-namespace suffix filter (`-brief | -temporal | -docs | -extraction`) before classifying, and exits non-zero with an error message on stderr if the daemon is down. Collections owned by unrelated tools are silently excluded from the orphan / healthy / stale sets and counted under `foreign_filtered_count` for telemetry only — foreign collections never enter any classification that could lead to data loss.

**Error handling:** If the script exits non-zero, set `{hygiene_result: "qmd_unavailable", hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0}` and skip directly to section 4 (which will still run the ccc-prune branch if `{ccc}` is true).

**Parse the JSON output and set context flags:**

- `{orphaned_collections}` ← `orphaned` (the list, used in section 3)
- `{live_collections}` ← comma-join of `live_names` (used in §4's clean-stale invocation; the script owns the raw set, the prompt only forwards it)

Set `{hygiene_result: "completed"}`.

### 3. Handle Orphaned Collections

**If `{orphaned_collections}` is empty:** Set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0}` and skip to section 4.

**Non-interactive resolution.** Resolve the gate without prompting in the first case that applies:

- `{orphan_action}` is non-null (activation lets through only `keep` or `remove`) → act on that value, with `source: "orphan-action-flag"`
- `{quiet_mode}` is true → the default **Keep**, with `source: "headless-default"` when `{headless_mode}` is true and `source: "quiet-default"` otherwise (a `--quiet` run)

Set `{orphan_auto_resolution: {action: <keep|remove>, count: len(orphaned_collections), source: <as above>}}` so step 4 can fold it into the envelope warnings (the audit trail matters most when `remove` deletes collections without a prompt). On keep, set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: len(orphaned_collections)}`, and unless `{quiet_mode}` is true, display `"Auto-decision (--orphan-action=keep): kept {len(orphaned_collections)} orphaned forge collection(s)"`; then skip to section 4. On remove, go on to the removal block below (still no user prompt), which records each name. (On an interactive resolution, through the prompt below, leave `{orphan_auto_resolution}` null; the human chose, so there is no auto-decision to audit.)

**GATE [default: K]**: reached only when none of the cases above applies, so `{orphan_action}` is null and `{quiet_mode}` is false. Display to the user:

"**QMD Hygiene: Found {count} orphaned collection(s) not tracked in the forge registry:**

{list orphaned collection names}

These collections exist in QMD but are not managed by any skill workflow. They may be from a previous auto-index run or manual creation.

**[R]emove** orphaned collections — clean up QMD
**[K]eep** orphaned collections — leave them as-is (default)"

**If user selects R (Remove), or the non-interactive resolution chose remove:** For each name in `{orphaned_collections}`:

```bash
qmd collection remove <name>
```

Collect the names whose removal succeeded as `{orphan_removed_names}` and the others as `{orphan_remove_failed}`, then set `{hygiene_orphaned_removed: len(orphan_removed_names), hygiene_orphaned_kept: 0}`. When `{orphan_auto_resolution}` is set, add `removed: {orphan_removed_names}` and `failed: {orphan_remove_failed}` to it, so the envelope's `warnings` names every collection deleted without a prompt and every one that could not be deleted; unless `{quiet_mode}` is true, also display `"Auto-decision (--orphan-action=remove): removed {len(orphan_removed_names)} orphaned forge collection(s): {orphan_removed_names, comma-separated}"`, followed by `"; could not remove: {orphan_remove_failed, comma-separated}"` when that list is non-empty.

**If user selects K (Keep) or no orphans:** Set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: len(orphaned_collections)}`.

### 4. Stale Registry Cleanup

This section runs whenever reachable — it handles both `qmd_collections` stale entries (Deep tier) and `ccc_index_registry` stale entries (whenever ccc is true). The script's flags are mutually independent.

Build the invocation. Always include `--target` for the forge-tier.yaml path. Include `--qmd-live-names "{live_collections}"` ONLY when section 2 ran successfully (i.e. `{hygiene_result}` is `"completed"`); omit the flag entirely otherwise so the script skips QMD cleanup. Include `--prune-missing-ccc-paths` ONLY when `{ccc}` is true; omit it otherwise.

```bash
uv run {forgeTierRwHelper} clean-stale \
    --target "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" \
    [--qmd-live-names "{live_collections}"]  \
    [--prune-missing-ccc-paths] \
    > "{run_dir}/clean-stale.json" && cat "{run_dir}/clean-stale.json"
```

The script reads the registry, computes set-difference operations (qmd: registry − live; ccc: filter where `path` does not exist on disk), and atomically rewrites forge-tier.yaml only when something actually changed (mtime preserved on idempotent re-runs). The script prints only its JSON result. A registered ccc path that is missing during this run is pruned even when it sits on a mount attached only at other times, such as a CI runner's ephemeral mount; the step 4 report counts the pruned paths and the envelope's `warnings` lists each one.

**If the script exits non-zero:** set `{hygiene_stale_cleaned: 0}`; the registry stays as it was. Unless `{quiet_mode}` is true, display one line: "Registry cleanup skipped: {message}.", where `{message}` is the `message` of the stderr JSON `{"status":"error","message":...}`. Then continue to section 5: hygiene errors never fail the workflow.

**Otherwise parse the JSON output:** `{hygiene_stale_cleaned}` ← `len(qmd_removed)`.

If `{hygiene_stale_cleaned}` > 0, unless `{quiet_mode}` is true, display: "**Cleaned {hygiene_stale_cleaned} stale QMD registry entry/entries** (collection no longer exists in QMD)."

Removed ccc registry paths are not displayed here: the step 4 report's CCC Registry line counts them, and the envelope's `warnings` lists each one.

### 5. Auto-Proceed

After hygiene completes (or is skipped for non-Deep tiers without ccc), unless `{quiet_mode}` is true, display "**Proceeding to forge status report...**". Then load `{nextStepFile}`, read it fully, and execute it.
