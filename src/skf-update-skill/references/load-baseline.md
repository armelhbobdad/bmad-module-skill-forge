---
nextStepFile: 'reconcile-scope.md'
# `{gapDrivenStepFile}`: §8 loads it in place of `{nextStepFile}` when
# `update_mode` is `gap-driven`.
gapDrivenStepFile: 'gap-driven.md'
# `{loadProvenanceHelper}`: §4's export count and provenance age. If neither
# exists, §7 shows both as `unknown`.
loadProvenanceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-load-provenance.py'
  - '{project-root}/src/shared/scripts/skf-load-provenance.py'
# `{findTestReportHelper}`: §4b's offer of an unconsumed test report. If
# neither exists, §4b offers nothing.
findTestReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-test-report.py'
  - '{project-root}/src/shared/scripts/skf-find-test-report.py'
# `{hashContentHelper}`: §5's [MANUAL] inventory. HALT if neither resolves: a
# marker count by eye misses a truncated block.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# `{sourceTreeHelper}`: §6's `classify` and §6b's `open`.
# HALT if neither resolves: a remote skill would be read at whatever commit
# SKF's shared clone is on.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# `{extractPublicApiHelper}`: §6c's source version.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# `{skillInventoryHelper}`: §6c's version comparison. If neither exists, §6c
# records no source version.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# `{emitEnvelopeHelper}` and `{runStateHelper}`: SKILL.md binds both, and a
# lost binding resolves here, first existing path wins. The warnings and gate
# decisions go to the run log through the first; the halt procedure runs the
# second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Load the Baseline

## STEP GOAL:

Load the skill's provenance map, offer an unconsumed test report, capture the [MANUAL] inventory, resolve and prepare the source and detect its version, then present a baseline summary so the user can confirm the update scope before proceeding.

## Rules

- Focus only on loading the baseline: read-only operations, except the private source tree §6b prepares (a folder of this run's own, never the shared workspace clone)
- Do not begin change detection (step 2)
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>"}
SKF_JSON
```

Pass `--tree` once §6b has bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "init:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place. No HALT in this step adds a `headless_decisions[]` entry: a halt is not an auto-resolved gate.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 4. Load Provenance Map

**Bind `{provenance_map_path}`** ← the `paths.provenance_map.path` of init.md §1's `resolve` object: `{forge_version}/provenance-map.json`, else the flat `{forge_data_folder}/{skill_name}/provenance-map.json` an older skill keeps, else null. Do not load the map into context: the steps that need it read the file through their helpers (step 2's, gap-driven.md §1's in a repair, and step 5's `apply`). For what §7 shows, when `{provenance_map_path}` is not null, resolve `{loadProvenanceHelper}` ← first existing path in `{loadProvenanceProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {loadProvenanceHelper} normalize "{provenance_map_path}" --age-from-last-update
```

Bind `{export_count}` ← `export_count` (the map's `entries[]`) and `{provenance_age_days}` ← `age_days`, the days since the map's `last_update`, else its `generated_at`, else the file's last change. On exit 1 (a map that is not JSON, or not a JSON object, which every later helper refuses too), HALT (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{provenance_map_path}"`, `reason: "provenance-invalid: {its first stderr line}"`). When no candidate resolves or it prints no JSON, bind both `unknown`.

**If `{provenance_map_path}` is null:**

**When `update_mode` is `gap-driven`, offer no [D]**, interactive or headless, `--allow-degraded` included: a repair spot-checks the report's gaps against this map. HALT (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "gap-driven-needs-provenance-map: run a normal update first, which offers the degraded rebuild and writes a map, then re-run test-skill"`) and display "**A repair from a test report needs a provenance map, and `{skill_name}` has none.** Run a normal update first, which offers the degraded rebuild and writes a map, then re-run test-skill."

Otherwise:

"**WARNING:** No provenance map found at `{forge_version}/provenance-map.json` or flat fallback.

Without a provenance map, update-skill cannot perform targeted change detection. Options:

**[D]egraded mode**: Perform full re-extraction with T1-low confidence (equivalent to re-running create-skill but preserving [MANUAL] sections)
**[X]**: Abort and run create-skill first to generate provenance data

Select: [D] Degraded / [X] Abort"

- If D: set `degraded_mode = true` and `update_mode: degraded`, proceed with full extraction scope
- If X: HALT (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "no provenance map; the user chose to run create-skill first"`)

**GATE [default: HALT unless `--allow-degraded`]**: in `{headless_mode}` without `--allow-degraded` (default), do not auto-select [D]. Degraded mode is a full, lossy T1-low re-extraction: choosing it unattended would silently swap surgical update for a create-skill-equivalent rebuild, a policy call that belongs to an operator. HALT instead (halt procedure: `status: "blocked"`, `phase: "init:load-provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "no provenance map at versioned or flat path; degraded full re-extraction needs a human decision"`).

**In `{headless_mode}` with `--allow-degraded` (`allow_degraded: true`):** the operator pre-authorized the lossy rebuild for this run, so treat it as an auto-resolved [D] rather than a halt. Set `degraded_mode = true` and `update_mode: degraded`, proceed with full extraction scope, and record the decision in the run's decision log, from `{project-root}`:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "init.degraded-rebuild", "default_action": "X", "taken_action": "D", "reason": "headless: --allow-degraded pre-authorized degraded full re-extraction", "evidence": {"provenance_map": "<{forge_version}/provenance-map.json, with / separators>", "flat_fallback": "missing"}}
SKF_JSON
```

Continue to §4b, which skips itself in degraded mode.

### 4b. Offer an Unconsumed Test Report

**Run this section only when `--from-test-report` was not given and `degraded_mode` is false** (a repair reads the provenance map): a user who follows a failing test often runs a plain update. Resolve `{findTestReportHelper}` as init.md §1 does and, from `{project-root}`, run:

```bash
uv run {findTestReportHelper} find \
    --forge-data-folder "{forge_data_folder}" \
    --skill-name "{skill_name}" \
    [--version "{active_version}"] \
    --newer-than "{generation_date}" \
    --provenance-map "{provenance_map_path}"
```

The report is **unconsumed** when `status` is `found`, `report_exists` is true, `testResult` is `fail` or `pass-with-drift` (the two verdicts test-skill sends to update-skill), `newer` is not `false` (`null`, a time that cannot be read, offers the report rather than hiding it) and `applied` is not `true` (write.md §3 records the report a gap-driven repair applied). Otherwise, or when no candidate resolves or the command fails or prints no JSON, continue to §5. For an unconsumed report, bind `{unconsumed_test_report}` ← `path` and `{unconsumed_test_result}` ← `testResult`, and `{test_report_cap}` ← `cap_reason` when it is not null, then:

- **Interactive:** present the choice below. Its default follows the verdict: [G] for a `fail` whose `cap_reason` is null; [S] for `pass-with-drift`, which test-skill reached against a workspace HEAD other than the pinned commit, so a repair would read that same tree and halt `halted-for-workspace-drift`, while a normal update reads a fresh tree and records its commit; [S] too for a `fail` whose `cap_reason` is not null: a cap forced that FAIL, and no skill edit lifts a cap, so test-skill's report says to restore the tooling the cap names and test again first. For that `fail`, add "A cap forced this FAIL ({cap_reason}), and no repair lifts it: restore the tooling it names and re-run test-skill." under the first line below.

  "**Test report `{its file name}` ({testResult}, score {score}) is newer than this skill and has not been applied.**

  [G] Repair the gaps it lists (gap-driven mode, as `--from-test-report` runs it)
  [S] Check the source for changes (normal mode)"

  - **[G]:** set `test_report_path` ← `{unconsumed_test_report}`, `{test_report_run_id}` ← `run_id` and `update_mode: gap-driven`, then unbind `{unconsumed_test_report}`. When `{target_ref_override}` is set, give init.md §1's `--target-ref` warning and unset it.
  - **[S]:** keep normal mode and add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`.
- **GATE [default: S]**: headless (`{headless_mode}` true), keep normal mode, the mode the caller asked for, and add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`. The warning is the notice, so the gate adds no `headless_decisions[]` entry.

While `{unconsumed_test_report}` stays bound, step 6's no-change report points to it instead of saying no action is required.

### 5. Load [MANUAL] Section Inventory

**Capture the [MANUAL] inventory deterministically.** The workflow's headline rule is "[MANUAL] sections survive regeneration with zero content loss", and the pre-write inventory captured here is the exact baseline step 4 §4 amends with the user's decisions and write.md §1 verifies against, so it must be a per-block byte-exact hash, not an eyeballed marker count. Run the `manual-inventory` subcommand of `{hashContentHelper}` and persist its JSON beside the init.md §1b lock, never in a version folder: an update that writes leaves the previous version's folders unchanged (merge-write.md §6b).

```bash
uv run {hashContentHelper} manual-inventory {resolved_skill_package}/SKILL.md \
    > {forge_data_folder}/{skill_name}/.skf-update-manual-inventory.json
```

When `detect_only_mode` or `dry_run_mode` is true, run the same command without the redirect and read its output instead: those modes write nothing and never verify the inventory. The emitted JSON is `{"blocks":[{name, content_hash, byte_offset, parent_heading}...], "count":N}`: each `content_hash` covers the block's byte-exact interior, so a later interior truncation that leaves the marker count unchanged is still caught. Bind the persisted path as `{manual_inventory}` in context (the read-only modes bind none); step 4 §4 amends it and rebinds `{manual_inventory}` to the amended copy that later `manual-verify` calls read. Surface the block `count` in the baseline summary (§7 `{manual_count}`).

### 6. Resolve the Source

Bind the source fields from the `metadata.json` loaded in init.md §2 (the provenance map does not carry `source_root`): `{source_root}` ← `source_root`, `{source_repo}` ← `source_repo`, `{source_ref}` ← `source_ref` and `{source_commit}` ← `source_commit`, each an empty string when the field is null or missing. `{source_ref}` and `{source_commit}` keep these values for the whole run: step 5 records any new commit in the artifacts only.

**A remote skill takes no `--source-root`.** When `{source_root_override}` is set, resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}` and, from `{project-root}`, run `uv run {sourceTreeHelper} classify --source-repo "{source_repo}" --source-root "{source_root}"`. It makes no network call and builds no tree: it prints the verdict §6b's `open` starts from, with `remote` true when `{source_repo}` names a remote repository, whatever `{source_root}` holds. On `remote` true, the skill is read from that repository, in every mode, gap-driven included, never from a local folder: HALT as §6b's **Every §6b HALT** describes, with `{source_tree_reason}` = `source-root-needs-local-source` and `{source_tree_message}` = "`--source-root` applies only to a skill read from a local folder". When no candidate resolves, or the command exits non-zero or prints no JSON, HALT the same way with `helper-failed` and the message §6b's last bullet gives.

- **Docs-only skill** (`source_type: "docs-only"` in the brief or metadata.json, as step 3 §1 checks): there is no source tree. Skip §6b, §6c and the path check below. If `{target_ref_override}` is set, HALT as §6b's **Every §6b HALT** describes, with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository". If `{source_root_override}` is set, HALT the same way, with `source-root-needs-local-source` and the message above.
- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair reads the commit the skill is pinned to, and gap-driven.md §3 checks that `{source_root}` holds it before reading anything. Skip §6b and §6c and run the path check below.
- **Every other mode**, `--detect-only` and `--dry-run` included: run §6b, whose `open` takes the `source_root` metadata.json records, never `{source_root_override}`. §6b runs the path check below only when the helper reports `skipped`; with `{source_root_override}` set it always does, since the `classify` call above lets through only a skill that is not remote.

**Path check:** when `{source_root_override}` is set, first bind `{source_root}` ← `{source_root_override}`; when that path is not a folder, HALT in either mode (halt procedure: `status: "blocked"`, `phase: "init:resolve-source-path"`, `path: "{source_root_override}"`, `reason: "source-root-missing: --source-root {source_root_override} is not a folder"`). Then validate that `{source_root}` exists and is accessible.

**If the source path is invalid or missing:** first run the `classify` call above when it has not run, halting `helper-failed` as above when it fails (`remote` true does not halt here: no `--source-root` was passed), and bind `{source_remote}` ← its `remote` (false when it ran above: a remote skill halted there).

"**Source path from metadata.json is invalid:** `{source_root}`

Provide the current source code path:
**Path:** {user provides path}"

Bind `{source_root}` to the path the user gives, made absolute as init.md §1's `--source-root` handler does, and ask again until it names a folder. When `{source_remote}` is false, bind `{source_root_override}` to it too, so step 5 records the folder the source moved to. A remote skill reads it for this run only: `{source_root_override}` stays unset, and metadata.json keeps the `source_root` it records.

**In `{headless_mode}`:** there is no operator to supply a path. HALT (halt procedure: `status: "blocked"`, `phase: "init:resolve-source-path"`, `path: "{source_root}"`, `reason: "source_root from metadata.json is invalid or inaccessible and no interactive path can be supplied; re-run with --source-root <path>"`) and display "**The source folder `{source_root}` is gone.** Re-run with `--source-root <path>` naming the folder the source moved to." For a remote skill (`{source_remote}` true), which takes no `--source-root`, the `reason` ends at "can be supplied" and the display keeps only its first sentence.

Whenever `{source_root}` takes `{source_root_override}` and that folder is not the `source_root` metadata.json records, add `source-root-overridden: {the source_root metadata.json records, or none} -> {source_root_override}` to `warnings[]`: step 5 records the new folder in metadata.json when the update writes (write.md §2).

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

Dispatch on `{source_tree_status}`:

- **`ready`** (exit 0): bind `{source_root}` ← `{source_tree}`; every later step reads source there. No step writes `{source_tree}` into an artifact.
- **`offline`** (exit 0): bind `{source_root}` ← `{source_tree}` (a tree at the skill's own `{source_commit}`), display `{source_tree_message}` as a warning, and add `source-not-fetched: {source_tree_message}` to `warnings[]`. This run compares the skill with the commit it was built from and cannot see upstream changes.
- **`skipped`** (exit 0): keep `{source_root}` from metadata.json and run §6's path check. If `{target_ref_override}` is set, HALT as below with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository".
- **`unavailable`** (exit 3): no commit to read could be obtained (`{source_tree_reason}` is `invalid-ref`, `git-unavailable`, `upstream-unreachable`, `ref-not-found`, `fetch-failed`, `checkout-failed`, `tree-folder-failed` or `timed-out`). When it is `timed-out` and your shell tool allows a command longer than `{tree_timeout}` seconds, raise `{tree_timeout}` toward that limit, run the command once more and dispatch on that result. Otherwise HALT before any step reads source; display `{source_tree_message}`. The helper leaves no tree behind.
- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:** HALT with `{source_tree_reason}` = `helper-failed` and `{source_tree_message}` = "skf-source-tree.py did not finish: {the first stderr line; 'the shell stopped it before it printed a result' when your shell tool's timeout ended it; or 'it is missing; re-install SKF'}". A tree a stopped run left behind is removed by a later run once it is seven days old. Reading the shared clone as it stands is what this section exists to prevent.

**Every §6b HALT** runs the halt procedure with `status: "blocked"`, `phase: "init:source-tree"`, `path: "{source_repo}"`, `reason: "{source_tree_reason}: {source_tree_message}"`, and `version` and `previous_version` the metadata.json `version`. No `headless_decisions[]` entry: this is a hard halt, not an auto-resolved gate.

### 6c. Detect the Source Version

Run only when `{source_tree_status}` is `ready` or `offline`. Read the source's version from `{source_root}` by the Version Reconciliation section of `skf-create-skill/references/source-resolution-protocols.md` (its `{extractPublicApiHelper}` call, from `{extractPublicApiProbeOrder}`), with `{skill_name}` as `{brief.name}` and the metadata.json `language` as `{brief.language}`. When no version file gives one, leave `{source_version_detected}` unset and skip the rest of this section. Otherwise compare it with the metadata.json `version` through `{skillInventoryHelper}` (resolve it ← first existing path in `{skillInventoryProbeOrder}`), from `{project-root}`:

```bash
uv run {skillInventoryHelper} version order "{the source's version}" "{version}"
```

It prints `order` and `major_minor` (the source's version against `{version}`) and `a.normalized` (the source's version as a version folder name). Never compare the two by hand.

- **`order` is `higher`** (a higher semantic version than the metadata.json `version`): bind `{source_version_detected}` ← `a.normalized`. merge-write.md §6b and step 5 §2 name the version this update writes after it.
- **Otherwise** leave `{source_version_detected}` unset. When `major_minor` is `lower`, add `source-version-lower: {target_ref} reads {a.normalized}, older than {version}; this update keeps the patch-version rule` to `warnings[]`. A source version lower only in its patch number is expected, not a regression: every update that finds no higher version increments the skill's patch number (merge-write.md §6b), so a skill forged at the source's 1.2.0 is 1.2.1 after one update while the source still reads 1.2.0.
- **Exit 1** (`code` `NOT_A_VERSION`: a value that names no version), **no candidate, or no JSON:** leave `{source_version_detected}` unset: merge-write.md §6b takes the next patch version.

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
| **Provenance Age** | {provenance_age_days} days since last extraction |
| **Exports** | {export_count} tracked exports |
| **[MANUAL] Sections** | {manual_count} preserved sections |
| **Mode** | {update_mode} |

**Analysis plan:** {tier_description}
- {Quick: text pattern diff → T1-low findings}
- {Forge: AST structural diff → T1 findings where an ast-grep rule matches, T1-low where an export is read by eye}
- {Deep: AST structural + QMD semantic diff → the same labels as Forge, plus T2 findings}

**Ready to detect changes and update this skill?**"

In degraded mode, the Provenance Age and Exports rows read `no provenance map`.

`{source_display}` is `{source_repo}` at `{target_ref}` when `{source_tree_status}` is `ready` or `offline` (plus ` (re-pinned from {source_ref})` when `{target_ref_override}` is set), and `{source_root}` otherwise. `{source_commit_line}` shows commits as their first 8 characters:

- `ready` and `{source_moved}` true: `{source_commit} → {target_commit}` plus ` ({added} added, {modified} modified, {deleted} deleted files)` from `{source_changed_counts}`, or ` (file list unavailable)` when `{source_diff_status}` is `unavailable`;
- `ready` and `{source_moved}` false: `{target_commit} (no newer commit)`;
- `ready` and `{source_moved}` null: `{target_commit} (no pinned commit before this run)`;
- `offline`: `{source_commit} (upstream not reached: comparing the pinned commit only)`;
- any other source: `{source_commit} (read as it stands)`.

Steps 5 and 6 reuse `{source_display}` and `{source_commit_line}`.

### 8. Confirmation Gate

**Record the run context** first, in every mode (`--detect-only` and `--dry-run` too): a later step reads back from it a binding its context lost (SKILL.md's Workflow Rules). From `{project-root}`, run:

```bash
cat > "{run_dir}/run-context.json" <<'SKF_JSON'
{"skill_name": "{skill_name}", "baseline_version": "{baseline_version}", "forge_tier": "{forge_tier}", "update_mode": "<normal, gap-driven or degraded>", "headless_mode": {headless_mode}, "degraded_mode": {degraded_mode}, "detect_only_mode": {detect_only_mode}, "dry_run_mode": {dry_run_mode}, "allow_workspace_drift": {allow_workspace_drift}, "allow_degraded": {allow_degraded}, "test_report_path": "{test_report_path}", "test_report_run_id": "{test_report_run_id}", "test_report_cap": "{test_report_cap}", "target_ref_override": "{target_ref_override}", "source_root_override": "{source_root_override}", "lock_owner": "{lock_owner}", "skill_package": "{skill_package}", "forge_version": "{forge_version}", "provenance_map_path": "{provenance_map_path}", "manual_inventory": "{manual_inventory}", "source_root": "{source_root}", "source_repo": "{source_repo}", "source_ref": "{source_ref}", "source_commit": "{source_commit}", "source_tree_status": "{source_tree_status}", "source_tree": "{source_tree}", "workspace_clone": "{workspace_clone}", "target_ref": "{target_ref}", "target_commit": "{target_commit}", "source_moved": {source_moved}, "source_diff_status": "{source_diff_status}", "source_changed_files": "{source_changed_files}", "tree_timeout": {tree_timeout}, "source_version_detected": "{source_version_detected}", "source_display": "{source_display}", "source_commit_line": "{source_commit_line}"}
SKF_JSON
```

Write each value as JSON: a string with `"` and `\` escaped and every path with `/`, a flag `true` or `false` (`false` for one this run never set), `tree_timeout` a number, `source_moved` `true`, `false` or `null`, and a bare `null`, with no quotes, for a binding this run did not bind (in gap-driven mode, every source-tree binding §6b would make). It holds no `version`: write.md §2 rebinds `{version}` to the version the update writes. merge-write.md §6b and gap-driven.md §3 rewrite the file with what they bind.

Present "**Select:** [C] Continue to Change Detection" ("**Select:** [C] Continue to Gap-Driven Repair" when `update_mode` is `gap-driven`) and wait for the user to confirm; on [C], load, read the full file, then execute `{gapDrivenStepFile}` when `update_mode` is `gap-driven`, else `{nextStepFile}`.

**GATE [default: C]**: headless (`{headless_mode}` true), auto-continue and record the decision in the run's decision log, from `{project-root}` (the emitter checks it against `shared/scripts/schemas/skf-update-result-envelope.v1.json`, and step 6's line carries it):

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "init.update-confirmation", "default_action": "C", "taken_action": "C", "reason": "headless: no user to prompt"}
SKF_JSON
```
