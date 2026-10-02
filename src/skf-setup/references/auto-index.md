---
nextStepFile: 'report.md'
# `{qmdClassifyHelper}` and `{forgeTierRwHelper}` = first existing path in
# their `*ProbeOrder` arrays; halt if neither exists for a helper a section
# actually invokes.
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

Reconcile the `qmd_collections` registry with the live QMD collections, and prune `ccc_index_registry` entries whose source paths no longer exist. Classification, removal and every registry edit go through `{qmdClassifyHelper}` and `{forgeTierRwHelper}`, which stage their results in the run folder for step 4; this step runs them and makes the orphan-removal decision.

## Rules

- Never reimplement the forge-namespace suffix filter or the path check in prose: the classifier owns them
- Run `qmd collection remove`, through the classifier's `remove-orphans`, only on the interactive **[R]** or an explicit `--orphan-action=remove`: that flag is the consent, and `{orphan_auto_resolution}` records the decision, so the envelope's `warnings` name each collection the removal deleted
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line a halt displays
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If a section needs a helper whose probe order has no existing path, halt (an install fault, not a hygiene error) with phase `step 3:helper-missing`, `path` set to that array's first entry, and reason `Setup cannot proceed: <script file name> was not found. Reinstall SKF, then re-run /skf-setup.`
- Every halt follows the SKILL.md halt contract: when `{quiet_mode}` is true, run `uv run {emitEnvelopeHelper} emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"`, which builds the payload itself (no `--path` for a halt without one, `--stderr-from` where the halt names it, and `--customization-resolver-unavailable "<reason>"` once SKILL.md On Activation item 6 bound `{customization_resolver_unavailable}` to a reason, escaped as the halt contract says), and display its stdout line verbatim and nothing else (the reason alone if `{emitEnvelopeHelper}` resolves to no path, or the helper exits non-zero or prints no line); otherwise display the reason
- Do not fail the workflow if hygiene encounters errors; a missing helper is not a hygiene error

## MANDATORY SEQUENCE

### 1. Check Tier

Set `{orphan_auto_resolution}` to null. When `{require_tier_satisfied}` (from step 1) is `false`, go to section 5 with no output: a run that ends `tier_failure` runs no hygiene, so it removes no collection and prunes no registry entry, and step 4 reports none. Otherwise the QMD sections (2 and 3) run only when `{calculated_tier}` is Deep, and section 4 runs when `{calculated_tier}` is Deep or `{ccc}` is true. Go to section 2 at Deep tier, else to section 4 when `{ccc}` is true, else to section 5 with no output.

### 2. Classify Live QMD Collections vs Registry

```bash
uv run {qmdClassifyHelper} classify \
    --registry-from-yaml "{sidecar_path}/forge-tier.yaml" \
    --project-root "{project-root}" \
    > "{run_dir}/qmd-classify.json" && cat "{run_dir}/qmd-classify.json"
```

**If the script exits non-zero** (qmd is not running), go to section 4: step 4 reports QMD hygiene as skipped.

Otherwise bind `{orphaned_collections}` ← `orphaned` and `{orphan_paths}` ← `orphaned_paths`.

### 3. Handle Orphaned Collections

**If `{orphaned_collections}` is empty:** go to section 4.

**Non-interactive resolution.** Resolve the gate without prompting in the first case that applies:

- `{orphan_action}` is non-null (activation lets through only `keep` or `remove`) → act on that value, with `source: "orphan-action-flag"`
- `{quiet_mode}` is true → the default **Keep**, with `source: "headless-default"` when `{headless_mode}` is true and `source: "quiet-default"` otherwise (a `--quiet` run)

Set `{orphan_auto_resolution: {action: <keep|remove>, source: <as above>}}`: step 4 adds the count and, after a removal, the collections removed and not removed, so the envelope's `warnings` audit a decision nobody confirmed. On keep, unless `{quiet_mode}` is true, display `"Auto-decision (--orphan-action=keep): kept {count} orphaned forge collection(s)"`, where `{count}` is the number of names in `{orphaned_collections}`, then go to section 4. On remove, run the removal below, still with no prompt.

**GATE [default: K]**: reached only when none of the cases above applies, so `{orphan_action}` is null and `{quiet_mode}` is false. Display to the user:

"**QMD Hygiene: Found {count} orphaned collection(s) in this project that its forge registry does not list:**

{each name in `{orphaned_collections}`, with its path from `{orphan_paths}`}

QMD indexes them from folders inside this project, but no skill workflow recorded them: a run may have stopped before it registered one, or one was added by hand.

**[R]emove** orphaned collections — clean up QMD
**[K]eep** orphaned collections — leave them as-is (default)"

On the user's **[K]**, go to section 4.

**On remove** (the user's **[R]**, or the non-interactive remove):

```bash
uv run {qmdClassifyHelper} remove-orphans \
    --classification-from "{run_dir}/qmd-classify.json" \
    --project-root "{project-root}" \
    > "{run_dir}/qmd-remove.json" && cat "{run_dir}/qmd-remove.json"
```

It reads each orphan's path again just before removing it, removes only a collection that still lies inside this project, and lists the names under `removed` and `failed` (each failure's reason under `errors`). After a non-interactive remove, unless `{quiet_mode}` is true, display `"Auto-decision (--orphan-action=remove): removed {removed, comma-separated}"`, followed by `"; could not remove: {failed, comma-separated}"` when `failed` is non-empty.

### 4. Stale Registry Cleanup

Pass `--prune-missing-ccc-paths` when `{ccc}` is true, and leave it out otherwise:

```bash
uv run {forgeTierRwHelper} clean-stale \
    --target "{sidecar_path}/forge-tier.yaml" \
    --qmd-live-from "{run_dir}/qmd-classify.json" \
    [--prune-missing-ccc-paths] \
    > "{run_dir}/clean-stale.json" && cat "{run_dir}/clean-stale.json"
```

The script removes the `qmd_collections` entries no live collection matches, reading the live names from section 2's output; with no such output (below Deep tier, or a classifier that failed) it leaves `qmd_collections` alone.

**If the script exits non-zero:** the registry stays as it was. Unless `{quiet_mode}` is true, display one line: "Registry cleanup skipped: {message}.", where `{message}` is the `message` of the stderr JSON `{"status":"error","message":...}`. Then continue to section 5: hygiene errors never fail the workflow.

**Otherwise**, when `qmd_removed` is non-empty and `{quiet_mode}` is false, display: "**Cleaned {n} stale QMD registry entry/entries** (collection no longer exists in QMD).", where `{n}` is the number of names in `qmd_removed`.

Removed ccc registry paths are not displayed here: the step 4 report's CCC Registry line counts them, and the envelope's `warnings` lists each one.

### 5. Auto-Proceed

Load `{nextStepFile}`, read it fully, and execute it.
