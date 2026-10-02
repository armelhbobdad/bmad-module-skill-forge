---
# Step 1 §5b loads this file only when upstream moved past the skill's
# baseline (the helper's `moved` status). Once the choice has bound the
# audit-ref values, the run goes back to step 1 at its §6: this file has no
# nextStepFile, since a step loaded from it would start init.md again at §1.
resumeStepFile: 'init.md'
# Resolve `{sourceTreeHelper}` to the first existing path: [C] reads the
# upstream ref into a private tree with `resolve`, and every later HALT and
# step 6 remove that tree with `close`.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
---

<!-- Config: communicate in {communication_language}. -->

# Upstream Checkout

## STEP GOAL:

Upstream has moved past the commit the skill was built from (step 1 §5b). Ask whether to audit the ref upstream moved to, read into a private source tree of this run's own, to stay on the baseline, or to stop, then bind the audit-ref values and go back to step 1 §6.

## Rules

- Read the upstream ref into a private tree only: SKF's clone at `{source_root}` keeps the commit it holds, and this step takes no lock
- Bind `audit_ref`, `audit_ref_source` and `audit_commit` (and, after [C], `{source_tree}`) before going back: step 1 §6 writes them into the drift report

## MANDATORY SEQUENCE

**Halt envelope.** The one HALT here, **[X]**, comes before any private tree exists, so it has no tree to remove. It exits 6 with `halt_reason: "user-cancelled"` at phase `init:upstream-drift`. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "init:upstream-drift", "reason": "<the halt message>", "halt_reason": "user-cancelled", "skill_name": "{skill_name}"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with exit code 6. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Present the Gate

**User gate: upstream moved.**

"**Upstream has moved since this skill was created.**

| | Baseline | Upstream |
|---|---|---|
| Ref | `{baseline_ref}` | `{upstream_ref}` |
| Commit | `{baseline_commit_short}` | `{upstream_commit_short}` |

The remote's default branch is at `{remote_head_short}`. Auditing the baseline tree reports little or no structural drift even when the upstream API changed. Options:

- **[C] Audit `{upstream_ref}`** (default): read `{upstream_ref}` into a private source tree of this run's own and audit against it. Nothing on disk changes: SKF's clone at `{source_root}` stays at the commit it holds.
- **[S] Stay on the baseline**: audit the unchanged tree at `{baseline_ref}`. The report says upstream moved and recommends `[US] Update Skill` with `--target-ref {upstream_ref}`.
- **[X] Abort**: halt the workflow without producing a report.

**Select:** [C] / [S] / [X]"

### 2. Act on the Choice

**Gate handling:**
- **[C]:** Resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`; it stays bound for the rest of the run (step 6 and every HALT use it). Bind `{tree_timeout}` to the seconds the helper may take: `100` when your shell tool stops a command after two minutes or you do not know its limit, otherwise a little under that limit, such as `540` under a 10-minute limit. The helper stops itself within `--timeout` seconds and still prints its result, so give the command a shell timeout longer than `{tree_timeout}`. From `{project-root}`, run:

  ```bash
  uv run {sourceTreeHelper} resolve --source-repo "{source_repo}" --source-root "{source_root}" --target-ref "{upstream_ref}" --timeout "{tree_timeout}"
  ```

  It reads `{upstream_ref}` into a private tree, from SKF's clone when the clone holds the commit and from the remote otherwise, and never writes to the clone (the call passes no `--update-clone`), so this run holds no lock and leaves the clone's checkout as it found it. Display each entry of its `warnings`, then:
  - **`status` is `ready` and `tag_resolution.status` is `target-ref`:** bind `{source_tree}` ← `tree` and `{source_root}` ← `{source_tree}`: every later step reads the source in this tree. Set `audit_ref = {upstream_ref}`, `audit_ref_source = "checkout-latest"` and `audit_commit` ← `source_commit`.
  - **Anything else** (`skipped`, because `{source_repo}` is no remote repository; `unavailable`, with its `reason` and `message`; a `ready` tree read at another ref, whose `tree` you first remove with `uv run {sourceTreeHelper} close --tree "<tree>"`; no candidate; a command that fails or prints no JSON): this run cannot read `{upstream_ref}` without changing a folder it does not own. Display "Could not read `{upstream_ref}` into a private tree ({the message or reason}); auditing the baseline instead. Run `[US] Update Skill` with `--target-ref {upstream_ref}` to update the skill to it.", record the warning by its code alone, which holds no quote: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "upstream_tree_unavailable: <code>"`, the code being `skipped`, the `reason` of an `unavailable` result, `other-ref` or `helper-unavailable`. Then continue as **[S]**.
- **[S]:** Keep the baseline: set `audit_ref`, `audit_ref_source` and `audit_commit` to the values of those names in the JSON of step 1 §5b's upstream check.
- **[X]:** do not create a drift report. HALT (exit 6, `halt_reason: "user-cancelled"`, phase `init:upstream-drift`): "Audit stopped before any report was written. Upstream moved past `{baseline_ref}`: run `[US] Update Skill` with `--target-ref {upstream_ref}` to update the skill to `{upstream_ref}`."
- **Other input:** help user, redisplay gate.

**Headless default** (when `{headless_mode}`): consume the pre-supplied `upstream_drift_choice` from the Invocation Contract. Unset or `C` runs **[C]**, the default: it reads a private tree and changes nothing on disk, so it needs no consent. `S` runs **[S]**, and `X` halts as **[X]** does. Log `"headless: upstream moved ({baseline_ref} -> {upstream_ref}); <auditing {upstream_ref} | staying on the baseline | aborting> per upstream_drift_choice=<value or 'default C'>."` and record the decision in the run sink once the choice has run, and before an [X] halt: stage `{run_dir}/decision.json` as `{"gate": "init.upstream-drift", "default_action": "C", "taken_action": "<C, S or X>", "reason": "<the log line>", "evidence": {"baseline_ref": "{baseline_ref}", "upstream_ref": "{upstream_ref}"}}`, with `taken_action` `S` and `"fallback": "<code>"` in the evidence when [C] could not read the tree and the run stayed on the baseline, and run `uv run {emitEnvelopeHelper} record --workflow skf-audit-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

### 3. Go Back to Step 1

Once **[C]** or **[S]** has bound `audit_ref`, `audit_ref_source` and `audit_commit`, load and read the full file `{resumeStepFile}`, and continue it at §5b's **Record for report**, then §6 (Create Drift Report): do not run its §1 to §5b again.
