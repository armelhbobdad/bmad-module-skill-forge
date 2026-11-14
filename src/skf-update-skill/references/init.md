---
nextStepFile: 'load-baseline.md'
# Resolve `{skillInventoryHelper}` to the first existing path. §1 lists the
# skills SKF generated when the invocation names none (interactive only),
# resolves the version to update with its `resolve`, and runs it with
# `--skill` before a flat skill moves: only a flat skill whose metadata.json
# carries an SKF marker (`flat_skf`) is migrated. If neither exists, §1 shows
# its prompt without the list and halts with no version to update (a flat
# skill takes its not-SKF-output halt).
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{runLockHelper}` to the first existing path; HALT if neither
# candidate exists: without the run lock two updates could write one skill.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
# `{findTestReportHelper}`: §1 finds the test report. If neither exists, §1
# halts a headless run and warns an interactive one, which keeps normal mode.
findTestReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-test-report.py'
  - '{project-root}/src/shared/scripts/skf-find-test-report.py'
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# The warnings go to the run log through the first; the halt procedure and
# §1b's cleanup run the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Update

## STEP GOAL:

Resolve the skill to update and the run's flags, take the run lock, check the skill's artifacts, redirect a stack skill and load the forge tier configuration, so load-baseline.md can load the baseline the user confirms.

## Rules

- Focus only on resolving the skill and checking its artifacts: read-only operations, except the flat-to-versioned migration in §1 and the cleanup of an interrupted update §1b finds
- Do not load the baseline (load-baseline.md) or begin change detection (step 2)
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "<{skill_name}, or unknown before §1 resolves it>", "version": "<the metadata.json version, or unknown before §2 reads it>", "previous_version": "<the same>", "update_mode": "<normal or gap-driven; normal before §1 decides>"}
SKF_JSON
```

Pass `--lock` and `--owner` once §1b has bound `{lock_owner}`, and `--emit` in `{headless_mode}`. It releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`run-lock-not-released`) when it could not release it: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "init:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place. No HALT in this step adds a `headless_decisions[]` entry: a halt is not an auto-resolved gate.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Request Skill Path

**The invocation's skill.** When `{requested_skill}` is set (SKILL.md On Activation), it answers the question below in either mode, and the prompt is not shown.

**No skill passed, interactive:** offer the skills SKF generated. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and, from `{project-root}`, run `uv run {skillInventoryHelper} "{skills_output_folder}"`. Above the prompt, list, numbered, the `name` and `active_version` of each `skills[]` entry whose `skf_skill` is true; a number answers with that skill's name. When no candidate resolves, the command fails or prints no JSON, or no entry qualifies, show the prompt alone.

**No skill passed, headless:** there is no one to answer, and update-skill never guesses a skill. HALT (halt procedure: `status: "blocked"`, `phase: "init:skill-name"`, `path: "{skills_output_folder}"`, `reason: "input-missing: a headless run needs the skill's name or folder path as its argument"`) and display "**No skill to update.** A headless run takes the skill's name or folder path as its argument, for example `@Ferris US <skill> --headless`."

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves via version-aware path resolution — see `knowledge/version-paths.md`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection

Add `--dry-run` to preview what would change without writing anything; `references/invocation-contract.md` lists the other flags.

**Skill:** {user provides a number from the list, a name or a path}"

**Version-Aware Path Resolution:**

Bind `{skill_name}` ← the name given (a folder path gives the name of its skill folder directly under `{skills_output_folder}`). Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill_name} --forge-data-folder "{forge_data_folder}"
```

It chooses the version by the Reading Workflows rules of `knowledge/version-paths.md`, the Manifest-lag guard included, and checks that its package is on disk, so this step never reads the export manifest or the `active` link by hand. Show each `resolve.errors` entry, and `resolve.manifest_error` when it is set, as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: bind below.
2. `manifest-lags-link` (the **Manifest-lag guard**): bind below, which takes the link's version, and show an Info note with the `resolve` object's `active_version` and `symlink_target`: "manifest active_version {active_version} lags the active link {symlink_target}: updating {symlink_target}, the version the last update or forge wrote; run export-skill to publish it." The manifest advances only when export-skill runs, while every update that writes makes a new version and points `active` at it (verify-publish.md §8): a manifest-first read would update the previous version again, and merge-write.md §6b would then stop at the version folder the last update created.
3. `newest-on-disk`: neither the manifest nor the `active` link names a version whose package is on disk (a link to an empty version folder, say), and the newest version folder holds one. Bind below, show the helper's `detail` as an Info note and add `version-newest-on-disk: {detail}` to `warnings[]`.
4. `flat-layout`: fall back to the flat path `{skills_output_folder}/{skill-name}/`, where `SKILL.md` sits at the skill folder root with no version folder yet. Check that SKF generated it before anything moves:
   - Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`, run `uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** if the invocation carries `--detect-only` or `--dry-run` (read them from the invocation here; the flag handling below comes later), do not migrate and HALT: those modes never move a skill, and every later step reads the versioned forge workspace, which a flat skill does not have yet. Display "**`{skill-name}` still uses the flat layout: nothing was moved.** `--detect-only` and `--dry-run` never migrate a skill, and they need the versioned layout. Run `@Ferris US {skill-name}` once without them, or AS, TS or EX, to move it into that layout, then re-run with the flag." This runs before the §1b lock, so there is no lock to release. The halt procedure takes `status: "blocked"`, `phase: "init:read-only-flat-layout"`, `path: "{skills_output_folder}/{skill-name}/"`, `reason: "flat-layout: read-only modes never migrate a skill; run once without --detect-only or --dry-run"`, with `version` and `previous_version` `"unknown"`. Otherwise run `uv run {skillInventoryHelper} migrate "{skills_output_folder}" --skill {skill-name} --forge-data-folder "{forge_data_folder}"` and show its `message` as an Info note, then run `uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill-name} --forge-data-folder "{forge_data_folder}"` and bind from its `resolve` object `{active_version}` ← `chosen_version` and `{skill_package}` ← `skill_package`, and every other binding below, anew: they now name the version folder. When `migrate` exits 1, HALT with its `error`. This runs before the §1b lock, so there is no lock to release. The halt procedure takes `status: "blocked"`, `phase: "init:migrate"`, `path: "{skills_output_folder}/{skill-name}/"`, `reason: "migrate: {its error}"`, with `version` and `previous_version` `"unknown"`.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill-name}` is not SKF output: nothing was moved.** `{skills_output_folder}/{skill-name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or update it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill-name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. This runs before the §1b lock, so there is no lock to release. The halt procedure takes `status: "blocked"`, `phase: "init:ownership-gate"`, `path: "{skills_output_folder}/{skill-name}/"`, `reason: "not-skf-output: {the reason the message shows}"`, with `version` and `previous_version` `"unknown"`.
5. `missing`, or the helper exits 1 with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version of the skill is on disk. Bind `{resolved_skill_package}` ← `skill_package`, else `{skills_output_folder}/{skill_name}`, and HALT at once with §2's missing-SKILL.md payload and message (halt procedure: `status: "blocked"`, `phase: "init:validate-artifacts"`, `path: "{resolved_skill_package}/SKILL.md"`, `reason: "no SKILL.md in the skill package"`). This runs before the §1b lock, so there is no lock to release.
6. Any other result (exit 1 with another `code`, another exit, or no JSON): HALT (halt procedure: `status: "blocked"`, `phase: "init:resolve"`, `path: "{skills_output_folder}/{skill_name}"`, `reason: "resolve-failed: {its error, or its first stderr line}"`), with `version` and `previous_version` `"unknown"`. When no candidate resolves: take item 4's **Otherwise** branch if `{skills_output_folder}/{skill_name}/SKILL.md` exists, else this HALT with "skf-skill-inventory.py is missing; re-install SKF" as its error. Either runs before the §1b lock, so there is no lock to release.

**Bind** from the `resolve` object: `{active_version}` and `{baseline_version}` ← `chosen_version`, `{skill_package}` and `{resolved_skill_package}` ← `skill_package` (every later step loads the skill's artifacts there), and `{forge_version}` ← `forge_version`. `{baseline_version}` is the pre-update version, which reconcile-scope.md §1c passes to `skf-provenance-gap-dispatch.py` as a required argument.

`update_mode` is `normal` until the test-report lookup below or load-baseline.md §4b's [G] sets `gap-driven`, or load-baseline.md §4 sets `degraded`.

**If `--from-test-report` was provided (or user references a test report):** find the newest finished test report of the resolved skill with `{findTestReportHelper}` (resolve it ← first existing path in `{findTestReportProbeOrder}`). From `{project-root}`, run:

```bash
uv run {findTestReportHelper} find \
    --forge-data-folder "{forge_data_folder}" \
    --skill-name "{skill_name}" \
    [--version "{active_version}"]
```

Pass `--version`: §1 always binds `{active_version}`. Never glob, sort or read a report's frontmatter by hand.

- **`status` is `found` and `report_exists` is true:** set `test_report_path` ← `path`, `{test_report_run_id}` ← `run_id` and `update_mode: gap-driven`, and `{test_report_cap}` ← `cap_reason` when it is not null (a cap forced that FAIL, and no repair lifts it: report.md says to restore the tooling it names). Name the report the helper picked (its file name, such as `test-report-{skill_name}-20260507T050917Z-487606-9b2f.md`, with its `testResult`, `score` and `source`, and its `cap_reason` when not null) and each newer one it passed over as unfinished (`skipped[]`), so an operator can find them from the log, and add each of its `warnings[]` to `warnings[]` as `test-report: <entry>`.
- **Otherwise** (`not-found`; `found` with `report_exists` false, a result file naming a report that is gone; no candidate resolves; or the command fails or prints no JSON): `<cause>` is, for `not-found`, "no finished test report of {skill_name} {active_version}" (with ", {n} unfinished passed over" when `skipped[]` is not empty, `{n}` its length); for `found` with `report_exists` false, "the report a result file names, {path}, is gone"; with no candidate, "skf-find-test-report.py is missing; re-install SKF"; else the command's first stderr line, or "no JSON".
  - **Headless** (`{headless_mode}` true): HALT (halt procedure: `status: "blocked"`, `phase: "init:test-report"`, `path: "{forge_data_folder}/{skill_name}"`, `reason: "input-missing: --from-test-report found no finished test report: <cause>"`, with `version` and `previous_version` `"unknown"`) and display "**No finished test report of {skill_name} to repair from:** <cause>. Run `@Ferris TS {skill_name}` first, or re-run without `--from-test-report` to check the source for changes." This runs before the §1b lock, so there is no lock to release.
  - **Interactive:** warn that no test report was found, with the cause, add `test-report-missing: <cause>` to `warnings[]`, and continue in normal source drift mode.

**If `--allow-workspace-drift` was provided:** set `allow_workspace_drift: true` in workflow context. This flag is consumed by gap-driven.md §3's pre-flight drift guard (gap-driven mode only) and has no effect in normal source-drift mode. Under it update-skill takes nothing from HEAD, so gap-spot-check.md §3b halts `halted-for-workspace-drift` before merge on each gap that needs the pinned tree, every new or modified export and every rescope among them, and step 5 does not re-pin `metadata.source_commit`.

**If `--allow-degraded` was provided:** set `allow_degraded: true` in workflow context. This flag is consumed by load-baseline.md §4 when no provenance map is found under `{headless_mode}`; it has no effect interactively (the [D]/[X] prompt is shown), when a provenance map is present, or in gap-driven mode, where that section halts `blocked` instead.

**If `--target-ref` was provided:** set `{target_ref_override}` to its value in workflow context; load-baseline.md §6b passes it to `skf-source-tree.py`. Decide this after the test-report lookup above: when `update_mode` is `gap-driven` it has no effect, since gap-driven mode repairs the skill at its pinned commit, so warn the user once at flag-parse time ("`--target-ref` has no effect with `--from-test-report`: gap-driven mode repairs the skill at its pinned commit") and leave `{target_ref_override}` unset. When `--from-test-report` found no report, the run continues in normal mode and keeps `{target_ref_override}` (interactive only: a headless run halted above); when load-baseline.md §4b switches a run to gap-driven mode, it unsets it with the same warning.

**If `--source-root` was provided:** set `{source_root_override}` to its path, made absolute (a relative path is read from `{project-root}`) and written with `/`. load-baseline.md §6 applies it in every mode: it replaces the `source_root` metadata.json records for a skill read from a local folder, and halts for any other.

**If `--detect-only` was provided:** set `detect_only_mode: true` in workflow context. After step 2 (detect-changes) completes (gap-driven.md §2 in gap-driven mode), jump directly to step 6 (report): skip re-extract, merge and write. The report emits the change manifest and a `SKF_UPDATE_RESULT_JSON` envelope with `status: "detect-only"`. **Compatibility:** `--detect-only` short-circuits before gap-driven.md §3 runs, so `--allow-workspace-drift` is silently ignored in detect-only mode (warn the user once at flag-parse time: "`--allow-workspace-drift` has no effect with `--detect-only`: the workspace drift guard runs after the gaps are translated, which `--detect-only` skips").

**If `--dry-run` was provided:** set `dry_run_mode: true` in workflow context. After step 3 (re-extract) completes (gap-spot-check.md §5 in gap-driven mode), jump directly to step 6 (report): skip merge and write. The report emits what would change with `status: "dry-run"` in the envelope. No artifact on disk is modified, in any mode (a repair from a test report and a docs-only skill included), and step 2 reports each skill brief amendment it would make as proposed instead of writing it: `--dry-run` is the "show me what an update would do without committing" mode.

**If BOTH `--detect-only` AND `--dry-run` were provided:** `--detect-only` wins (it's the more restrictive). Warn the user once: "`--detect-only` supersedes `--dry-run`; re-extract is skipped." Set `detect_only_mode: true`, ignore `dry_run_mode`.

### 1b. Concurrency Guard

**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.** Both inspection modes are read-only, and the private source tree load-baseline.md §6b prepares for them never writes to the shared workspace clone.

Two concurrent `skf-update-skill` runs against the same `{forge_data_folder}/{skill_name}/` can corrupt provenance: one would write metadata.json mid-way through the other's extraction. The run lock is separate from the `.skf-workspace.lock` on the source clone, which only verify-publish.md §9 takes.

Resolve `{runLockHelper}` ← first existing path in `{runLockProbeOrder}`; it stays bound for the rest of the run. The lock's owner carries this run's `{run_id}`, the name of its run folder, so a later update that finds the lock stale knows which run folder holds what this run wrote. From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/{skill_name}/.skf-update.lock" \
    --owner "update-skill:{skill_name}:{run_id}" \
    --stale-after 60
```

It prints one JSON line. Dispatch on its exit code:

- **0** (`acquired` true): bind `{lock_owner}` ← `owner`; every renewal and release passes that value. When `stale_replaced` is not null, this run replaced a stale lock, left by a run that stopped without releasing it or held by one still waiting at a gate, whose renewal will then halt. Display the helper's `message` and add `run-lock-replaced: {stale_replaced.held_by} since {stale_replaced.held_since}` to `warnings[]` (`an unnamed owner` in place of a null `held_by`, as in a lock file an older SKF version wrote), then clean up after it as below.
- **3** (`acquired` false): another run holds a fresh lock. HALT (halt procedure: `status: "halted-for-concurrent-run"`, `phase: "init:concurrency-guard"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "another update in progress: {message}"`, with `version` and `previous_version` `"unknown"`, since §2 reads metadata.json later) and display "**Another update of {skill_name} is in progress.** {message}", with the helper's `message`, which names that run, the lock file to delete when no update of the skill is running and when the lock goes stale. This run took no lock, so it releases none.
- **No candidate resolves, any other exit, or no JSON:** HALT (halt procedure: `status: "blocked"`, `phase: "init:concurrency-guard"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-failed: {that message}"`) and display "**The run lock could not be taken:** {the `message` the helper printed on stderr, or 'skf-run-lock.py is missing; re-install SKF'}". No lock was taken, so none is released.

**Clean up an interrupted update.** When `stale_replaced.held_by` is not null, the update that held the lock may have stopped without finishing (a crash, a killed session, or a wait at a gate past the stale time) and left what it was writing half done: a gap-driven repair's package edited in place, or a new version folder the `active` link never reached. Undo it now, rather than stopping later at "version already exists". From `{project-root}`, run the `{runStateHelper}` `rollback` call below, with that owner exactly as the acquire printed it:

```bash
uv run {runStateHelper} rollback \
    --run-root "{project-root}/_bmad-output/.skf-run" \
    --owner "{stale_replaced.held_by}" \
    --skill "{skill_name}" \
    --remove-run-dir
```

It finds that run's folder by the run id in the owner (`update-skill:{skill_name}:<run id>`), reads what the run recorded before its first write, restores a repair's package (with the version's provenance map, evidence report and skill brief) from the snapshot it took, removes the version folders it created (never one the `active` link names), and deletes its run folder (only a `.skf-run/skf-update-skill-<run id>` folder: it refuses a run id that would lead anywhere else); a run that finished its writes, or never began them, needs nothing undone. An owner of another skill or workflow, or one with no run id (an older SKF's lock), has no run folder: `status` `no-run-folder`, and nothing to report. On exit 0 with any other `status`, add `interrupted-run-cleaned: {stale_replaced.held_by}: {status}; restored {restored}; removed {removed}` to `warnings[]` and tell the user in one line what was put back. On any other exit, or no JSON, add `interrupted-run-not-cleaned: {stale_replaced.held_by}: {its failed[] or message}` and go on: a version folder it left then stops merge-write.md §6b, whose message says which folders to delete.

**Release contract:** every exit after this section releases the lock, so a run that halts does not block the next one: step 7, or the halt procedure of the step file it fires in (in this step §2's ABORTs, the Stack Skill Guard and §3, then load-baseline.md's §4 and §6 halts and load-baseline.md's §6b source tree halts, and every later step's halts), whose helper adds `run-lock-not-released: {forge_data_folder}/{skill_name}/.skf-update.lock` to `warnings[]` when the release fails. A release deletes the lock only while `{lock_owner}` holds it, and a run that waits at a gate past the stale time can lose it, so merge-write.md §6b renews the lock before the run writes the skill. The private source tree load-baseline.md §6b prepares has its own contract: step 7 or the halt procedure removes it.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_package}/SKILL.md`
- If missing: HALT (halt procedure: `status: "blocked"`, `phase: "init:validate-artifacts"`, `path: "{resolved_skill_package}/SKILL.md"`, `reason: "no SKILL.md in the skill package"`): "No SKILL.md found at `{resolved_skill_package}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_package}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_type`, `scope_type` and `language` (when present), `source_repo`, `source_root`, `source_ref`, `source_commit`
- If missing: HALT (halt procedure: `status: "blocked"`, `phase: "init:validate-artifacts"`, `path: "{resolved_skill_package}/metadata.json"`, `reason: "no metadata.json in the skill package"`): "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

### Stack Skill Guard

After loading metadata.json, check `skill_type` (absent means `single`):
- If `skill_type` is `"stack"`: display message:
  "**Stack skills cannot be surgically updated.** Stack skills compose exports from multiple sources — surgical re-extraction requires re-running the full composition pipeline.
  
  **To update this stack skill**, run `skf-create-stack-skill` with the same project path. It will re-analyze manifests (code-mode) or re-read constituent skills (compose-mode) and produce an updated stack.
  
  If you came here from an audit report, the drift report identifies which constituent libraries changed — use that to decide whether re-composition is needed."
- Then HALT (halt procedure: `status: "blocked"`, `phase: "init:stack-skill-guard"`, `path: "{resolved_skill_package}"`, `reason: "stack-skill: a stack skill is re-composed with skf-create-stack-skill, never updated"`): the redirect ends the run, and step 2 never runs

No flag (`--detect-only`, `--dry-run`, `--from-test-report`, `--allow-workspace-drift`) bypasses this guard.

### 3. Load Forge Tier Configuration

**Load `{sidecar_path}/forge-tier.yaml`:**
- Extract: `tier` (Quick, Forge, Forge+, or Deep), available tools
- If missing: HALT (halt procedure: `status: "blocked"`, `phase: "init:forge-tier"`, `path: "{sidecar_path}/forge-tier.yaml"`, `reason: "no forge-tier.yaml; run setup first"`): "No forge-tier.yaml found. Run setup first to detect available tools."

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**Determine analysis capabilities:**
- **Quick:** text pattern matching only → T1-low confidence
- **Forge:** AST structural extraction → T1 for each export an ast-grep rule matches, T1-low for each export read by eye
- **Forge+:** AST structural extraction, plus a CCC check of rename candidates in a local source (step 2 Category C) → the same labels as Forge
- **Deep:** AST + QMD semantic enrichment → the same labels as Forge, plus T2

This step auto-proceeds: once §3 is done, load, read the full file, then execute `{nextStepFile}`.
