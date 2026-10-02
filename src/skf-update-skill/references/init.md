---
nextStepFile: 'detect-changes.md'
# `{gapDrivenStepFile}`: §8 loads it in place of `{nextStepFile}` when
# `update_mode` is `gap-driven`: it translates and verifies the test
# report's gaps in place of steps 2 and 3, and goes on to step 4.
gapDrivenStepFile: 'gap-driven.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists: a [MANUAL] marker count by eye misses a truncated block.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §1 lists the
# skills SKF generated when the invocation names none (interactive only), and
# step 4 runs it with `--skill` before a flat skill moves: only a flat skill
# whose metadata.json carries an SKF marker (`flat_skf`) is migrated. If
# neither exists, §1 shows its prompt without the list and §6c records no
# source version.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{runLockHelper}` to the first existing path; HALT if neither
# candidate exists: without the run lock two updates could write one skill.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
# Resolve `{sourceTreeHelper}` to the first existing path.
# HALT if neither resolves: without it a remote skill is read at whatever
# commit SKF's shared clone of its repository is on.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# `{findTestReportHelper}`: §1 and §4b find the test report. If neither
# exists, §1 warns and keeps normal mode and §4b offers nothing.
findTestReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-test-report.py'
  - '{project-root}/src/shared/scripts/skf-find-test-report.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Update

## STEP GOAL:

Load the existing skill and all its provenance data, detect whether this is an individual or stack skill, load the forge tier configuration, and present a baseline summary so the user can confirm the update scope before proceeding.

## Rules

- Focus only on loading existing artifacts and establishing the baseline: read-only operations, except the flat-to-versioned migration in §1, the cleanup of an interrupted update §1b finds, and the private source tree §6b prepares (a folder of this run's own, never the shared workspace clone)
- Do not begin change detection (step 2)

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "<{skill_name}, or unknown before §1 resolves it>", "version": "<the metadata.json version, or unknown before §2 reads it>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded; normal before §1 decides>"}
SKF_JSON
```

Pass `--tree` once §6b has bound `{source_tree}`, `--lock` and `--owner` once §1b has bound `{lock_owner}`, and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. The emitter adds `files_written: []`. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "init:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place. No HALT in this step adds a `headless_decisions[]` entry: a halt is not an auto-resolved gate.

### 1. Request Skill Path

**The invocation's skill.** When `{requested_skill}` is set (SKILL.md On Activation), it answers the question below in either mode, and the prompt is not shown.

**No skill passed, interactive:** offer the skills SKF generated. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and, from `{project-root}`, run `uv run {skillInventoryHelper} "{skills_output_folder}"`. Above the prompt, list, numbered, the `name` and `active_version` of each `skills[]` entry whose `skf_skill` is true; a number answers with that skill's name. When no candidate resolves, the command fails or prints no JSON, or no entry qualifies, show the prompt alone.

**No skill passed, headless:** there is no one to answer, and update-skill never guesses a skill. HALT (halt procedure: `status: "blocked"`, `phase: "init:skill-name"`, `path: "{skills_output_folder}"`, `reason: "input-missing: a headless run needs the skill's name or folder path as its argument"`) and display "**No skill to update.** A headless run takes the skill's name or folder path as its argument, for example `@Ferris US <skill> --headless`."

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves via version-aware path resolution — see `knowledge/version-paths.md`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection
- `--allow-workspace-drift` (gap-driven mode only) to intentionally bypass the gap-driven.md §3 guard that halts when the local workspace HEAD does not match `metadata.source_commit`. Under it update-skill takes nothing from HEAD: it moves or pins no provenance line read there, reads no signature, parameter list, return type or node kind there and counts no public API there, and gap-driven.md §3 halts `halted-for-workspace-drift` before merge on any gap that needs one, which every new or modified export does, and on every rescope; step 5 will NOT automatically re-pin
- `--allow-degraded` (headless mode only) to pre-authorize the lossy degraded full re-extraction if §4 finds no provenance map — without it, a headless run halts `blocked` there rather than silently rebuilding
- `--target-ref <tag|branch|HEAD|commit>` (normal mode, a skill forged from a remote repository) to read that ref's current commit instead of the skill's recorded `source_ref` (for example the `upstream_ref` an audit reports). When the update writes, step 5 records the ref as the new `source_ref` together with the commit it read. `HEAD` follows the remote's default branch; a full 40-character commit pins that commit
- `--detect-only` to run detect-changes only and exit; emits the change manifest with no further work and no writes
- `--dry-run` to run detect-changes + re-extract and exit before merge/write; emits what WOULD change without modifying any artifact, and a gap-driven.md halt such as `halted-for-remediation-path` or `halted-for-workspace-drift` still stops it

**Skill:** {user provides a number from the list, a name or a path}"

**Version-Aware Path Resolution:**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: **Manifest-lag guard.** Also read the `active` link at `{skills_output_folder}/{skill-name}/active`. When it resolves to a different version than `active_version`, bind `{active_version}` to the link's target version instead and show an Info note: "manifest active_version {M} lags the active link {N}: updating {N}, the version the last update or forge wrote; run export-skill to publish it." The manifest advances only when export-skill runs, while every update that writes makes a new version and points `active` at it (step 5 §8): a manifest-first read would update the previous version again, and step 4 §6b would then stop at the version folder the last update created. Resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/` (see `knowledge/version-paths.md` "Reading Workflows")
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — bind `{active_version}` to the version it names and resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to the flat path `{skills_output_folder}/{skill-name}/`. If `SKILL.md` exists there, check that SKF generated it before anything moves:
   - Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`, run `uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** if the invocation carries `--detect-only` or `--dry-run` (read them from the invocation here; the flag handling below comes later), do not migrate and HALT: those modes never move a skill, and every later step reads the versioned forge workspace, which a flat skill does not have yet. Display "**`{skill-name}` still uses the flat layout: nothing was moved.** `--detect-only` and `--dry-run` never migrate a skill, and they need the versioned layout. Run `@Ferris US {skill-name}` once without them, or AS, TS or EX, to move it into that layout, then re-run with the flag." This runs before the §1b lock, so there is no lock to release. The halt procedure takes `status: "blocked"`, `phase: "init:read-only-flat-layout"`, `path: "{skills_output_folder}/{skill-name}/"`, `reason: "flat-layout: read-only modes never migrate a skill; run once without --detect-only or --dry-run"`, with `version` and `previous_version` `"unknown"`. Otherwise auto-migrate per `knowledge/version-paths.md` migration rules.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill-name}` is not SKF output: nothing was moved.** `{skills_output_folder}/{skill-name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or update it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill-name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. This runs before the §1b lock, so there is no lock to release. The halt procedure takes `status: "blocked"`, `phase: "init:ownership-gate"`, `path: "{skills_output_folder}/{skill-name}/"`, `reason: "not-skf-output: {the reason the message shows}"`, with `version` and `previous_version` `"unknown"`.
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading
6. Bind `{baseline_version}` to the pre-update version — for an update this is the version being updated, i.e. the `{active_version}` steps 1–3 resolved (the flat-path fallback in step 4 has no version, so use the package version read from metadata.json in §2). Step 2 §1c passes `{baseline_version}` to `skf-provenance-gap-dispatch.py` as a required argument; leaving it unbound makes the helper search a wrong/empty directory and silently return `no-report`, dropping the major-version off-ramp.

Resolve the path to an absolute skill folder location.

**If `--from-test-report` was provided (or user references a test report):** find the newest finished test report of the resolved skill with `{findTestReportHelper}` (resolve it ← first existing path in `{findTestReportProbeOrder}`). From `{project-root}`, run:

```bash
uv run {findTestReportHelper} find \
    --forge-data-folder "{forge_data_folder}" \
    --skill-name "{skill_name}" \
    [--version "{active_version}"]
```

Pass `--version` only when steps 1-3 above bound `{active_version}` (the flat fallback in step 4 has none). Never glob, sort or read a report's frontmatter by hand.

- **`status` is `found` and `report_exists` is true:** set `test_report_path` ← `path`, `{test_report_run_id}` ← `run_id` and `update_mode: gap-driven`. Name the report the helper picked (its file name, such as `test-report-{skill_name}-20260507T050917Z-487606-9b2f.md`, with its `testResult`, `score` and `source`) and each newer one it passed over as unfinished (`skipped[]`), so an operator can find them from the log, and add each of its `warnings[]` to `warnings[]` as `test-report: <entry>`.
- **Otherwise** (`not-found`; `found` with `report_exists` false, a result file naming a report that is gone; no candidate resolves; or the command fails or prints no JSON): warn that no test report was found, with the cause, and continue in normal source drift mode.

**If `--allow-workspace-drift` was provided:** set `allow_workspace_drift: true` in workflow context. This flag is consumed by gap-driven.md §3's pre-flight drift guard (gap-driven mode only) and has no effect in normal source-drift mode.

**If `--allow-degraded` was provided:** set `allow_degraded: true` in workflow context. This flag is consumed by §4 below when no provenance map is found under `{headless_mode}`; it has no effect interactively (the [D]/[X] prompt is shown) or when a provenance map is present.

**If `--target-ref` was provided:** set `{target_ref_override}` to its value in workflow context; §6b passes it to `{sourceTreeHelper}`. Decide this after the test-report lookup above: when `update_mode` is `gap-driven` it has no effect, since gap-driven mode repairs the skill at its pinned commit, so warn the user once at flag-parse time ("`--target-ref` has no effect with `--from-test-report`: gap-driven mode repairs the skill at its pinned commit") and leave `{target_ref_override}` unset. When `--from-test-report` found no report, the run continues in normal mode and keeps `{target_ref_override}`; when §4b switches a run to gap-driven mode, it unsets it with the same warning.

**If `--detect-only` was provided:** set `detect_only_mode: true` in workflow context. After step 2 (detect-changes) completes (gap-driven.md §2 in gap-driven mode), jump directly to step 6 (report): skip re-extract, merge and write. The report emits the change manifest and a `SKF_UPDATE_RESULT_JSON` envelope with `status: "detect-only"`. **Compatibility:** `--detect-only` short-circuits before gap-driven.md §3 runs, so `--allow-workspace-drift` is silently ignored in detect-only mode (warn the user once at flag-parse time: "`--allow-workspace-drift` has no effect with `--detect-only`: the workspace drift guard runs after the gaps are translated, which `--detect-only` skips").

**If `--dry-run` was provided:** set `dry_run_mode: true` in workflow context. After step 3 (re-extract) completes (gap-driven.md §5 in gap-driven mode), jump directly to step 6 (report): skip merge and write. The report emits what would change with `status: "dry-run"` in the envelope. No artifact on disk is modified, in any mode (a repair from a test report and a docs-only skill included), and step 2 reports each skill brief amendment it would make as proposed instead of writing it: `--dry-run` is the "show me what an update would do without committing" mode.

**If BOTH `--detect-only` AND `--dry-run` were provided:** `--detect-only` wins (it's the more restrictive). Warn the user once: "`--detect-only` supersedes `--dry-run`; re-extract is skipped." Set `detect_only_mode: true`, ignore `dry_run_mode`.

### 1b. Concurrency Guard

**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.** Both inspection modes are read-only, and the private source tree §6b prepares for them never writes to the shared workspace clone.

Two concurrent `skf-update-skill` runs against the same `{forge_data_folder}/{skill_name}/` can corrupt provenance: one would write metadata.json mid-way through the other's extraction. The run lock is separate from the `.skf-workspace.lock` on the source clone, which only write.md §9 takes.

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

**Clean up an interrupted update.** When `stale_replaced.held_by` is not null, the update that held the lock may have stopped without finishing (a crash, a killed session, or a wait at a gate past the stale time) and left what it was writing half done: a gap-driven repair's package edited in place, or a new version folder the `active` link never reached. Undo it now, rather than stopping later at "version already exists". From `{project-root}`, run the helper SKILL.md On Activation resolved, with that owner exactly as the acquire printed it:

```bash
uv run {runStateHelper} rollback \
    --run-root "{project-root}/_bmad-output/.skf-run" \
    --owner "{stale_replaced.held_by}" \
    --skill "{skill_name}" \
    --remove-run-dir
```

It finds that run's folder by the run id in the owner (`update-skill:{skill_name}:<run id>`), reads what the run recorded before its first write, restores a repair's package (with the version's provenance map, evidence report and skill brief) from the snapshot it took, removes the version folders it created (never one the `active` link names), and deletes its run folder (only a `.skf-run/skf-update-skill-<run id>` folder: it refuses a run id that would lead anywhere else); a run that finished its writes, or never began them, needs nothing undone. An owner of another skill or workflow, or one with no run id (an older SKF's lock), has no run folder: `status` `no-run-folder`, and nothing to report. On exit 0 with any other `status`, add `interrupted-run-cleaned: {stale_replaced.held_by}: {status}; restored {restored}; removed {removed}` to `warnings[]` and tell the user in one line what was put back. On any other exit, or no JSON, add `interrupted-run-not-cleaned: {stale_replaced.held_by}: {its failed[] or message}` and go on: a version folder it left then stops step 4 §6b, whose message says which folders to delete.

**Release contract:**

- Every exit after this section releases the lock, so a run that halts does not block the next one: step 7 on a run that reaches it, and every other exit through the halt procedure of the step file it fires in: in this step §2's ABORTs, the Stack Skill Guard, §3, the §4 and §6 halts and the §6b source tree halts, and every later step's halts through their own. The release never stops on the result: when it fails or prints no JSON, the halt helper adds `run-lock-not-released: {forge_data_folder}/{skill_name}/.skf-update.lock` to its envelope's `warnings[]`. A release deletes the lock only while `{lock_owner}` holds it, so it never removes a lock another run took; the read-only modes take no lock and release none.
- A crashed or killed run leaves its lock until it goes stale. A run that waits at a gate past that time can lose its lock to the next update, so merge.md §6b and write.md §2 renew the lock before the run writes the skill, and halt `halted-for-concurrent-run` when this run no longer holds it.
- The private source tree §6b prepares has its own contract: step 7 removes it, every HALT or ABORT after §6b removes it first (the halt procedure of its step file), and a later run's §6b removes a tree a crashed or abandoned run left behind once it is seven days old.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_package}/SKILL.md`
- If missing: HALT (halt procedure: `status: "blocked"`, `phase: "init:validate-artifacts"`, `path: "{resolved_skill_package}/SKILL.md"`, `reason: "no SKILL.md in the skill package"`): "No SKILL.md found at `{resolved_skill_package}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_package}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_type`, `scope_type` and `language` (when present), `source_repo`, `source_root`, `source_ref`, `source_commit`
- If missing: HALT (halt procedure: `status: "blocked"`, `phase: "init:validate-artifacts"`, `path: "{resolved_skill_package}/metadata.json"`, `reason: "no metadata.json in the skill package"`): "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

**Detect skill type from metadata:**
- If `skill_type == "single"` or absent: flag as single skill
- If `skill_type == "stack"`: flag as stack skill — the guard below redirects it

### Stack Skill Guard

After loading metadata.json, check `skill_type`:
- If `skill_type` is `"stack"`: display message:
  "**Stack skills cannot be surgically updated.** Stack skills compose exports from multiple sources — surgical re-extraction requires re-running the full composition pipeline.
  
  **To update this stack skill**, run `skf-create-stack-skill` with the same project path. It will re-analyze manifests (code-mode) or re-read constituent skills (compose-mode) and produce an updated stack.
  
  If you came here from an audit report, the drift report identifies which constituent libraries changed — use that to decide whether re-composition is needed."
- Then HALT (halt procedure: `status: "blocked"`, `phase: "init:stack-skill-guard"`, `path: "{resolved_skill_package}"`, `reason: "stack-skill: a stack skill is re-composed with skf-create-stack-skill, never updated"`): the redirect ends the run, and step 2 never runs

**This guard is the single gate for stack skills** — every stack is redirected to `skf-create-stack-skill` here, before step 2, and no flag (`--detect-only`, `--dry-run`, `--from-test-report`, `--allow-workspace-drift`) bypasses it. Every later stage therefore runs against a single skill only and carries no stack-merge branch.

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

### 4. Load Provenance Map

**Find `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json`** (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`. Bind `{provenance_map_path}` to the path found. Do not load the map into context: the steps that need it read the file themselves (step 2's helpers, gap-driven.md §1 and §4 in a repair, and step 5's `apply`). Read from it only what §7 shows: the number of `entries[]` (`{export_count}`) and the provenance age, the days since its `last_update`, else its `generated_at`.

**If provenance map missing at both paths:**

"**WARNING:** No provenance map found at `{forge_version}/provenance-map.json` or flat fallback.

Without a provenance map, update-skill cannot perform targeted change detection. Options:

**[D]egraded mode** — Perform full re-extraction with T1-low confidence (equivalent to re-running create-skill but preserving [MANUAL] sections)
**[X]** — Abort and run create-skill first to generate provenance data

Select: [D] Degraded / [X] Abort"

- If D: set `degraded_mode = true`, proceed with full extraction scope
- If X: HALT (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "no provenance map; the user chose to run create-skill first"`)

**In `{headless_mode}` without `--allow-degraded` (default):** do not auto-select [D]. Degraded mode is a full, lossy T1-low re-extraction: choosing it unattended would silently swap surgical update for a create-skill-equivalent rebuild, a policy call that belongs to an operator. HALT instead (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "no provenance map at versioned or flat path; degraded full re-extraction needs a human decision"`).

**In `{headless_mode}` with `--allow-degraded` (`allow_degraded: true`):** the operator pre-authorized the lossy rebuild for this run, so treat it as an auto-resolved [D] rather than a halt. Set `degraded_mode = true`, proceed with full extraction scope, and record the decision in the run's decision log, from `{project-root}`:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "init.degraded-rebuild", "default_action": "X", "taken_action": "D", "reason": "headless: --allow-degraded pre-authorized degraded full re-extraction", "evidence": {"provenance_map": "<{forge_version}/provenance-map.json, with / separators>", "flat_fallback": "missing"}}
SKF_JSON
```

Continue to step 2.

### 4b. Offer an Unconsumed Test Report

**Run this section only when `--from-test-report` was not given and `degraded_mode` is false** (a repair reads the provenance map): a user who follows a failing test often runs a plain update. Resolve `{findTestReportHelper}` as §1 does and, from `{project-root}`, run:

```bash
uv run {findTestReportHelper} find \
    --forge-data-folder "{forge_data_folder}" \
    --skill-name "{skill_name}" \
    [--version "{active_version}"] \
    --newer-than "{generation_date}" \
    --provenance-map "{provenance_map_path}"
```

The report is **unconsumed** when `status` is `found`, `report_exists` is true, `testResult` is `fail` or `pass-with-drift` (the two verdicts test-skill sends to update-skill), `newer` is not `false` (`null`, a time that cannot be read, offers the report rather than hiding it) and `applied` is not `true` (write.md §3 records the report a gap-driven repair applied). Otherwise, or when no candidate resolves or the command fails or prints no JSON, continue to §5. For an unconsumed report, bind `{unconsumed_test_report}` ← `path` and `{unconsumed_test_result}` ← `testResult`, then:

- **Interactive:** present the choice below. Its default follows the verdict: [G] for `fail`; [S] for `pass-with-drift`, which test-skill reached against a workspace HEAD other than the pinned commit, so a repair would read that same tree and halt `halted-for-workspace-drift`, while a normal update reads a fresh tree and records its commit.

  "**Test report `{its file name}` ({testResult}, score {score}) is newer than this skill and has not been applied.**

  [G] Repair the gaps it lists (gap-driven mode, as `--from-test-report` runs it)
  [S] Check the source for changes (normal mode)"

  - **[G]:** set `test_report_path` ← `{unconsumed_test_report}`, `{test_report_run_id}` ← `run_id` and `update_mode: gap-driven`, then unbind `{unconsumed_test_report}`. When `{target_ref_override}` is set, give §1's `--target-ref` warning and unset it.
  - **[S]:** keep normal mode and add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`.
- **Headless (`{headless_mode}` true):** keep normal mode, the mode the caller asked for, and add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`. It is a notice, not a gate the run resolves: no `headless_decisions[]` entry.

While `{unconsumed_test_report}` stays bound, step 6's no-change report points to it instead of saying no action is required.

### 5. Load [MANUAL] Section Inventory

**Capture the [MANUAL] inventory deterministically.** The workflow's headline rule is "[MANUAL] sections survive regeneration with zero content loss", and the pre-write inventory captured here is the exact baseline step 4 §4 amends with the user's decisions and write.md §1 verifies against, so it must be a per-block byte-exact hash, not an eyeballed marker count. Run the `manual-inventory` subcommand of `{hashContentHelper}` and persist its JSON beside the §1b lock, never in a version folder: an update that writes leaves the previous version's folders unchanged (step 4 §6b).

```bash
uv run {hashContentHelper} manual-inventory {resolved_skill_package}/SKILL.md \
    > {forge_data_folder}/{skill_name}/.skf-update-manual-inventory.json
```

When `detect_only_mode` or `dry_run_mode` is true, run the same command without the redirect and read its output instead: those modes write nothing and never verify the inventory. The emitted JSON is `{"blocks":[{name, content_hash, byte_offset, parent_heading}...], "count":N}`: each `content_hash` covers the block's byte-exact interior, so a later interior truncation that leaves the marker count unchanged is still caught. Bind the persisted path as `{manual_inventory}` in context (the read-only modes bind none); step 4 §4 amends it and rebinds `{manual_inventory}` to the amended copy that later `manual-verify` calls read. Surface the block `count` in the baseline summary (§7 `{manual_count}`).

### 6. Resolve the Source

Bind the source fields from the `metadata.json` loaded in §2 (the provenance map does not carry `source_root`): `{source_root}` ← `source_root`, `{source_repo}` ← `source_repo`, `{source_ref}` ← `source_ref` and `{source_commit}` ← `source_commit`, each an empty string when the field is null or missing. `{source_ref}` and `{source_commit}` keep these values for the whole run: step 5 records any new commit in the artifacts only.

- **Docs-only skill** (`source_type: "docs-only"` in the brief or metadata.json, as step 3 §1 checks): there is no source tree. Skip §6b, §6c and the path check below. If `{target_ref_override}` is set, HALT as §6b's **Every §6b HALT** describes, with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository".
- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair reads the commit the skill is pinned to, and gap-driven.md §3 checks that `{source_root}` holds it before reading anything. Skip §6b and §6c and run the path check below.
- **Every other mode**, `--detect-only` and `--dry-run` included: run §6b. §6b runs the path check below only when the helper reports `skipped`.

**Path check:** validate that `{source_root}` exists and is accessible.

**If the source path is invalid or missing:**

"**Source path from metadata.json is invalid:** `{source_root}`

Provide the current source code path:
**Path:** {user provides path}"

Bind `{source_root}` to the path the user gives.

**In `{headless_mode}`:** there is no operator to supply a path. HALT (halt procedure: `status: "blocked"`, `phase: "init:resolve-source-path"`, `path: "{source_root}"`, `reason: "source_root from metadata.json is invalid or inaccessible and no interactive path can be supplied"`).

### 6b. Prepare the Source Tree

A skill forged from a remote repository at Forge tier or above records, as its `source_root`, the clone SKF keeps for that repository. Every SKF run on the repository shares that clone and leaves it at the commit it needed, so this run never reads it as it stands. `{sourceTreeHelper}` gives the run a private tree at one commit (the commit `{source_ref}` points to upstream now, or the tag, branch, `HEAD` or commit `--target-ref` names) and lists the files git changed between `{source_commit}` and that commit. Change detection, re-extraction, merge's file copies and write's citation check all read that tree. The helper never writes to the shared clone (step 5 moves the clone at the end of a real update), so this section runs in every mode.

Resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`. Bind `{tree_timeout}` to the seconds the helper may take: `100` when your shell tool stops a command after two minutes or you do not know its limit, otherwise a little under that limit, such as `540` under a 10-minute limit: a first fetch of a large repository is slow. The helper stops itself within `--timeout` seconds and still prints its result, so give the command a shell timeout longer than `{tree_timeout}`. From `{project-root}`, run:

```bash
uv run {sourceTreeHelper} open \
    --source-repo "{source_repo}" \
    --source-root "{source_root}" \
    --source-ref "{source_ref}" \
    --pinned-commit "{source_commit}" \
    --timeout "{tree_timeout}" \
    [--target-ref "{target_ref_override}"]
```

Pass `--target-ref` only when `{target_ref_override}` is set.

Bind `{source_tree_status}` ← `status`, `{source_tree_reason}` ← `reason`, `{source_tree_message}` ← `message`, `{source_tree}` ← `tree`, `{workspace_clone}` ← `clone`, `{target_ref}` ← `target_ref`, `{target_commit}` ← `target_commit`, `{source_moved}` ← `moved`, `{source_diff_status}` ← `diff_status`, `{source_changed_files}` ← `changed_files`, `{source_changed_counts}` ← `changed_counts` and `{source_tree_warnings}` ← `warnings`. Add each `{source_tree_warnings}` entry to `warnings[]` as `source-tree: <entry>`. `{source_tree}` is the tree itself; `{source_changed_files}` and `run.json` sit in its run folder, one level up.

What the helper does:

- **Which sources it takes.** Only the clone SKF keeps for a remote repository: `{source_repo}` names that repository and `{source_root}` is the clone path SKF computes for it (compared as resolved paths, so a trailing slash or `~` does not matter), or a clone of the same repository at `repos/<host>/<owner>/<repo>` in any SKF workspace folder, whatever the letter case of those folder names. Any other source — a local folder, or the remote URL a Quick-tier skill records — is read as it stands (`skipped`).
- **The commit.** It asks the remote which commit the ref points to (a tag before a branch of the same name; an annotated tag resolves to its commit), fetches that one commit into a folder of this run's own and checks it out there. It takes the objects from the shared clone when the clone already has them, and never writes to the clone. When the remote cannot be reached or the commit cannot be fetched, and `--target-ref` was not given, it checks out `{source_commit}` from the shared clone instead (`offline`).
- **The file list.** It writes git's list of added, modified and deleted files between `{source_commit}` and the tree's commit to `{source_changed_files}`; `{source_diff_status}` is `unavailable` when `{source_commit}` cannot be read.
- **Housekeeping.** It first removes trees earlier runs left behind for seven days or more.

Dispatch on `{source_tree_status}`:

- **`ready`** (exit 0): bind `{source_root}` ← `{source_tree}`; every later step reads source there. No step writes `{source_tree}` into an artifact.
- **`offline`** (exit 0): bind `{source_root}` ← `{source_tree}` — a tree at the skill's own `{source_commit}` — display `{source_tree_message}` as a warning, and add `source-not-fetched: {source_tree_message}` to `warnings[]`. This run compares the skill with the commit it was built from and cannot see upstream changes.
- **`skipped`** (exit 0): keep `{source_root}` from metadata.json and run §6's path check. If `{target_ref_override}` is set, HALT as below with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository".
- **`unavailable`** (exit 3): no commit to read could be obtained (`{source_tree_reason}` is `invalid-ref`, `git-unavailable`, `upstream-unreachable`, `ref-not-found`, `fetch-failed`, `checkout-failed`, `tree-folder-failed` or `timed-out`). When it is `timed-out` and your shell tool allows a command longer than `{tree_timeout}` seconds, raise `{tree_timeout}` toward that limit, run the command once more and dispatch on that result. Otherwise HALT before any step reads source; display `{source_tree_message}`. The helper leaves no tree behind.
- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:** HALT with `{source_tree_reason}` = `helper-failed` and `{source_tree_message}` = "skf-source-tree.py did not finish: {the first stderr line; 'the shell stopped it before it printed a result' when your shell tool's timeout ended it; or 'it is missing; re-install SKF'}". A tree a stopped run left behind is removed by a later run once it is seven days old. Reading the shared clone as it stands is what this section exists to prevent.

**Every §6b HALT** runs the halt procedure with `status: "blocked"`, `phase: "init:source-tree"`, `path: "{source_repo}"`, `reason: "{source_tree_reason}: {source_tree_message}"`, and `version` and `previous_version` the metadata.json `version`. No `headless_decisions[]` entry: this is a hard halt, not an auto-resolved gate.

### 6c. Detect the Source Version

Run only when `{source_tree_status}` is `ready` or `offline`. Read the source's version from `{source_root}` with the Version Reconciliation rules of `skf-create-skill/references/source-resolution-protocols.md`: the version file for the detected language (`pyproject.toml`, `setup.py`, `__version__`, `package.json`, `Cargo.toml`, `go.mod`) and its monorepo `package.json` priority, matching package names against this skill's `name`. When no version file gives one, leave `{source_version_detected}` unset and skip the rest of this section. Otherwise compare it with the metadata.json `version` through `{skillInventoryHelper}` (resolve it ← first existing path in `{skillInventoryProbeOrder}`), from `{project-root}`:

```bash
uv run {skillInventoryHelper} version order "{the source's version}" "{version}"
```

It prints `order` and `major_minor` (the source's version against `{version}`) and `a.normalized` (the source's version as a version folder name). Never compare the two by hand.

- **`order` is `higher`** (a higher semantic version than the metadata.json `version`): bind `{source_version_detected}` ← `a.normalized`. Step 4 §6b and step 5 §2 name the version this update writes after it.
- **Otherwise** leave `{source_version_detected}` unset. When `major_minor` is `lower`, add `source-version-lower: {target_ref} reads {a.normalized}, older than {version}; this update keeps the patch-version rule` to `warnings[]`. A source version lower only in its patch number is expected, not a regression: every update that finds no higher version increments the skill's patch number (step 4 §6b), so a skill forged at the source's 1.2.0 is 1.2.1 after one update while the source still reads 1.2.0.
- **Exit 1** (`code` `NOT_A_VERSION`: a value that names no version, such as a dynamic version in `pyproject.toml`), **no candidate, or no JSON:** leave `{source_version_detected}` unset: step 4 §6b takes the next patch version.

### 7. Present Baseline Summary

"**Update Skill Baseline:**

| Property | Value |
|----------|-------|
| **Skill** | {skill_name} |
| **Type** | single |
| **Version** | {version} |
| **Created** | {created date} |
| **Source** | {source_display} |
| **Source commit** | {source_commit_line} |
| **Forge Tier** | {forge_tier} (current) vs {original_tier} (at creation) |
| **Provenance Age** | {days} days since last extraction |
| **Exports** | {export_count} tracked exports |
| **[MANUAL] Sections** | {manual_count} preserved sections |
| **Mode** | {normal/degraded/gap-driven} |

**Analysis plan:** {tier_description}
- {Quick: text pattern diff → T1-low findings}
- {Forge: AST structural diff → T1 findings where an ast-grep rule matches, T1-low where an export is read by eye}
- {Deep: AST structural + QMD semantic diff → the same labels as Forge, plus T2 findings}

**Ready to detect changes and update this skill?**"

`{source_display}` is `{source_repo}` at `{target_ref}` when `{source_tree_status}` is `ready` or `offline` — plus ` (re-pinned from {source_ref})` when `{target_ref_override}` is set — and `{source_root}` otherwise. `{source_commit_line}` shows commits as their first 8 characters:

- `ready` and `{source_moved}` true: `{source_commit} → {target_commit}` plus ` ({added} added, {modified} modified, {deleted} deleted files)` from `{source_changed_counts}`, or ` (file list unavailable)` when `{source_diff_status}` is `unavailable`;
- `ready` and `{source_moved}` false: `{target_commit} (no newer commit)`;
- `ready` and `{source_moved}` null: `{target_commit} (no pinned commit before this run)`;
- `offline`: `{source_commit} (upstream not reached — comparing the pinned commit only)`;
- any other source: `{source_commit} (read as it stands)`.

Steps 5 and 6 reuse `{source_display}` and `{source_commit_line}`.

### 8. Confirmation Gate

Present "**Select:** [C] Continue to Change Detection" ("**Select:** [C] Continue to Gap-Driven Repair" when `update_mode` is `gap-driven`) and wait for the user to confirm; on [C], load, read the full file, then execute `{gapDrivenStepFile}` when `update_mode` is `gap-driven`, else `{nextStepFile}`.

**Headless (`{headless_mode}` true):** auto-continue and record the decision in the run's decision log, from `{project-root}` (the emitter checks it against `shared/scripts/schemas/skf-update-result-envelope.v1.json`, and step 6's line carries it):

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "init.update-confirmation", "default_action": "C", "taken_action": "C", "reason": "headless: no user to prompt"}
SKF_JSON
```

