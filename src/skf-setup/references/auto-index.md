---
nextStepFile: 'report.md'
# Resolve `{qmdClassifyHelper}` and `{forgeTierRwHelper}` by probing the
# corresponding `*ProbeOrder` arrays (installed SKF module path first, src/
# dev-checkout fallback); first existing path wins. HALT if neither resolves
# for the helper a section actually invokes — both scripts own classification
# / registry-cleanup contracts that have no prose fallback.
qmdClassifyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-qmd-classify-collections.py'
  - '{project-root}/src/shared/scripts/skf-qmd-classify-collections.py'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
---

<!-- Config: communicate in {communication_language}. The orphan-removal prompt and the headless-resolution log message render in the user's language. -->

# Step 3: QMD + CCC Registry Hygiene

## STEP GOAL:

When the detected tier is Deep, classify live QMD collections against the `qmd_collections` registry and prompt the user before removing orphans. Whenever ccc is available (Forge+ or Deep), prune `ccc_index_registry` entries whose source paths no longer exist. All set-arithmetic and YAML mutation goes through scripts (`{qmdClassifyHelper}` and `{forgeTierRwHelper}`); the workflow only orchestrates external CLI calls (`qmd collection list`, `qmd collection remove`) and the user-prompt branch.

For Quick and Forge tiers, skip silently and proceed (QMD is not available; ccc registry cleanup only runs when ccc is available regardless of tier).

## Rules

- Focus only on registry hygiene — no new collection creation (that belongs to create-skill)
- Never reimplement the forge-namespace suffix filter in prose — the classifier owns it
- Never silently delete collections — always prompt before `qmd collection remove`
- Headless runs must auto-resolve the orphan prompt to the documented default (Keep)
- Do not fail the workflow if hygiene encounters errors

## MANDATORY SEQUENCE

### 1. Check Tier

Read `{calculated_tier}` and `{ccc}` from context (set by step 1).

**If `{calculated_tier}` is Quick or Forge AND `{ccc}` is false:** No registry hygiene needed. Set `{hygiene_result: "skipped", hygiene_healthy: 0, hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0, hygiene_stale_cleaned: 0, ccc_registry_stale_cleaned: 0, ccc_registry_stale_removed_paths: []}`. Proceed directly to section 5 (Auto-Proceed) — no output, no messaging.

**If `{calculated_tier}` is Quick or Forge AND `{ccc}` is true:** No QMD work, but ccc registry needs pruning. Set QMD-related flags to defaults (`hygiene_result: "skipped"`, all hygiene_* counts = 0). Skip directly to section 4 (Stale Registry Cleanup), running it with the ccc-prune flag only.

**If `{calculated_tier}` is Forge+:** Same as Quick/Forge with ccc — no QMD work (qmd unavailable at Forge+), but ccc registry hygiene runs.

**If `{calculated_tier}` IS Deep:** Continue to section 2.

### 2. Classify Live QMD Collections vs Registry

Run the classifier — it owns the `qmd collection list` invocation and stdout parsing. Invoke via `uv run`:

```bash
uv run {qmdClassifyHelper} \
    --registry-from-yaml "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml"
```

The script (see `src/shared/scripts/skf-qmd-classify-collections.py` docstring for the full schema) invokes `qmd collection list` itself, applies the forge-namespace suffix filter (`-brief | -temporal | -docs | -extraction`) before classifying, and exits non-zero with an error message on stderr if the daemon is down. Collections owned by unrelated tools are silently excluded from the orphan / healthy / stale sets and counted under `foreign_filtered_count` for telemetry only. This is the PR #244 incident protection: foreign collections never enter any classification that could lead to data loss.

**Error handling:** If the script exits non-zero, set `{hygiene_result: "qmd_unavailable", hygiene_healthy: 0, hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0, hygiene_stale_cleaned: 0}` and skip directly to section 4 (which will still run the ccc-prune branch if `{ccc}` is true).

**Parse the JSON output and set context flags:**

- `{hygiene_healthy}` ← `len(healthy)`
- `{orphaned_collections}` ← `orphaned` (the list — used in section 3)
- `{stale_collections}` ← `stale` (the list — used in section 4)
- `{live_collections}` ← comma-join of `live_names` (used in §4's clean-stale invocation; the script owns the raw set, the prompt only forwards it)
- `{foreign_filtered_count}` ← `foreign_filtered_count`

Set `{hygiene_result: "completed"}`.

### 3. Handle Orphaned Collections

**If `{orphaned_collections}` is empty:** Set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: 0}` and skip to section 4.

**Non-interactive resolution.** If `{orphan_action}` is non-null, resolve the gate without prompting using that value: log `"Auto-decision (--orphan-action={value}): kept|removed {len(orphaned_collections)} orphaned forge collection(s)"`. If `{orphan_action}` is `"keep"`, set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: len(orphaned_collections)}` and skip to section 4. If `"remove"`, fall through to the removal block below (still no user prompt). Independently, if `{headless_mode}` is true and `{orphan_action}` is null, auto-resolve to the default **Keep** with the equivalent log line and skip to section 4. The two paths compose: `--orphan-action` overrides the headless default; `--headless` without `--orphan-action` keeps backward-compatible behavior.

**If `{headless_mode}` is false**, display to the user:

"**QMD Hygiene: Found {count} orphaned collection(s) not tracked in the forge registry:**

{list orphaned collection names}

These collections exist in QMD but are not managed by any skill workflow. They may be from a previous auto-index run or manual creation.

**[R]emove** orphaned collections — clean up QMD
**[K]eep** orphaned collections — leave them as-is (default)"

**If user selects R (Remove):** For each name in `{orphaned_collections}`:

```bash
qmd collection remove <name>
```

Track the count of successful removals as `{hygiene_orphaned_removed}`. Set `{hygiene_orphaned_kept: 0}`.

**If user selects K (Keep) or no orphans:** Set `{hygiene_orphaned_removed: 0, hygiene_orphaned_kept: len(orphaned_collections)}`.

### 4. Stale Registry Cleanup

This section ALWAYS runs when reachable — it handles both `qmd_collections` stale entries (Deep tier) and `ccc_index_registry` stale entries (whenever ccc is true). The script's flags are mutually independent.

Build the invocation. Always include `--target` for the forge-tier.yaml path. Include `--qmd-live-names "{live_collections}"` ONLY when section 2 ran successfully (i.e. `{hygiene_result}` is `"completed"`); omit the flag entirely otherwise so the script skips QMD cleanup. Include `--prune-missing-ccc-paths` ONLY when `{ccc}` is true; omit it otherwise.

```bash
uv run {forgeTierRwHelper} clean-stale \
    --target "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" \
    [--qmd-live-names "{live_collections}"]  \
    [--prune-missing-ccc-paths]
```

The script reads the registry, computes set-difference operations (qmd: registry − live; ccc: filter where `path` does not exist on disk), and atomically rewrites forge-tier.yaml only when something actually changed (mtime preserved on idempotent re-runs). The CI ephemeral-mount caveat for ccc-registry pruning is logged in the script's WARNING message (per PR #248).

**Parse the JSON output and set context flags for step 4:**

- `{hygiene_stale_cleaned}` ← `len(qmd_removed)`
- `{ccc_registry_stale_cleaned}` ← `len(ccc_removed)`
- `{ccc_registry_stale_removed_paths}` ← `ccc_removed` (the list — step 4 folds individual paths into envelope warnings)

If `{hygiene_stale_cleaned}` > 0, display: "**Cleaned {hygiene_stale_cleaned} stale QMD registry entry/entries** (collection no longer exists in QMD)."

(The script already logs each ccc removal as a WARNING line; no additional display needed.)

### 5. Auto-Proceed

After hygiene completes (or is skipped for non-Deep tiers without ccc), display "**Proceeding to forge status report...**", then load `{nextStepFile}`, read it fully, and execute it.
