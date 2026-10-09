---
nextStepFile: 'health-check.md'
# Resolve `{skillInventoryHelper}` to the first existing path when §1b names
# the version folder a dry run would create. If neither exists, §1b says
# "the next patch version" instead of a folder name.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 6: Report

## STEP GOAL:

Present a comprehensive change summary showing what was updated, [MANUAL] sections preserved, confidence tier breakdown, and recommend next workflow actions in the SKF chain.

## Rules

- Focus only on reporting: the skill's files are written. This step writes only the run's result files and prints its line, through the shared emitter (§5b, and §1's no-change exit), and changes no file of the skill
- Present clear, actionable summary with next step recommendations
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is NOT the terminal step
- **Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

## Steps

### 1. Handle No-Change Shortcut

**If routed here from step 2 (or gap-driven.md §2) with no changes detected:**

"**Update Skill Report: {skill_name}**

**Status:** No changes detected

Source code matches provenance map exactly. The skill `{skill_name}` is current — no update was needed.

**Provenance age:** {days} days since last extraction
**Forge tier:** {tier}
**Source commit:** {source_commit_line}

**Recommendation:** No action required. Run audit-skill periodically to monitor for drift."

When `{unconsumed_test_report}` is bound (step 1 §4b found a test report newer than the skill that this normal run did not apply), replace that recommendation by its `{unconsumed_test_result}`:

- `fail`: "**Recommendation:** The source has not changed, but test report `{its file name}` (fail) has not been applied to this skill. Run `@Ferris US {skill_name} --from-test-report` to repair the gaps it lists, then re-run test-skill."
- `pass-with-drift`: "**Recommendation:** The source has not changed, but test report `{its file name}` passed only under `--allow-workspace-drift`: test-skill read a workspace HEAD other than the commit this skill is pinned to. Once the workspace holds the pinned commit, re-run test-skill without `--allow-workspace-drift` before exporting."

In gap-driven mode (gap-driven.md §1 translated none of the report's gaps), replace the sentence that starts "Source code matches provenance map exactly" with "Test report `{its file name}` lists no gap update-skill repairs.", followed by each gap it did not route (`{id}: {title} ({category})`), and the recommendation with "Repair the listed gaps by hand, or re-run test-skill once the skill changes."

When `{source_moved}` is true, add before the recommendation: "Upstream moved to `{target_commit}`, but no file this skill tracks changed, so nothing was written and the skill stays pinned at `{source_commit}`." When `{target_ref_override}` is set and `{target_ref}` differs from `{source_ref}`, also add "**The re-pin to `{target_ref}` was not recorded** — an update records a new ref only when it writes, and `{target_ref}` changes no file this skill tracks." and add `target-ref-not-recorded: {target_ref} changes no file {skill_name} tracks; the skill still records {source_ref}` to `warnings[]`.

List under **Warnings:** each warning the run recorded (`{run_dir}/warnings.jsonl`, one per line), so an interactive run, which prints no line, shows them too.

**Result files, line and hook.** A normal or gap-driven run that found no change is a finished run: write its result contract and fire the hook as §5b does, with `status: "no-changes"` in the payload and `--result-dir "{forge_version}"`, the current version's forge folder (no version was written): `version` and `previous_version` both the metadata.json `version`, `files_written: []`, `error: null`, and in `result_contract` an empty `outputs` and `summary` `{"update_status": "no-changes", "exports_affected": 0, "files_modified": 0, "validation_status": "not-run"}`. The line carries `warnings[]` (`target-ref-not-recorded` among them). Then run `{onCompleteCommand}` as §5b says.

**A read-only run stays read-only here.** When `detect_only_mode` or `dry_run_mode` is true (detect-changes.md §4 and gap-driven.md §2 send a read-only run that finds no change here too), stage no `result_contract` and write no result file: in `{headless_mode}`, print the line as §1a does, with `status: "no-changes"` and no `--result-dir`, and never run `{onCompleteCommand}`. Those modes take no run lock, and the result files of the current version stay as the last finished run left them.

→ Load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.

### 1a. Handle Detect-Only Mode

**If `detect_only_mode` is true (routed here from detect-changes.md §5 or gap-driven.md §2):**

"**Update Skill Report: {skill_name} — Detect-Only Mode**

**Status:** Detect-only (no writes)
**Source commit:** {source_commit_line}

The change manifest below describes what would be updated. No artifact was modified — re-run without `--detect-only` to apply.

{render the change manifest, read from `{run_dir}/change-manifest.json`: §2's Changes Applied table, plus the per-file detail section}

{the warnings the run recorded, read from `{run_dir}/warnings.jsonl`: **Proposed skill brief amendments (not written):** each `proposed-amendment:` one, as the decision that would amend `skill-brief.yaml`; **Warnings:** each other one}

**Recommendation:** Review the manifest; if it matches expectations, re-run `skf-update-skill` without `--detect-only` to perform the actual update."

In `{headless_mode}`, print the line as §5b says, with `status: "detect-only"` and no `--result-dir`, and with no `result_contract`: a detect-only run writes no result file and does not run `{onCompleteCommand}`. `version` and `previous_version` are both the on-disk version (detect-only does not bump), `files_written: []`, `error: null`, and `update_mode` reflects the run's mode (`normal` or `gap-driven` or `degraded`) so consumers know which detection path produced the manifest. The emitter adds the `headless_decisions[]` detect-changes' §1b / §1c / §2.2 gates recorded and the `proposed-amendment:` warnings.

→ Load, read the full file, and execute `{nextStepFile}` (health-check) — even detect-only runs through the terminal health-check step.

### 1b. Handle Dry-Run Mode

**If `dry_run_mode` is true (routed here from re-extract.md §6 or gap-driven.md §5):**

"**Update Skill Report: {skill_name} — Dry-Run Mode**

**Status:** Dry-run (no writes)
**Source commit:** {source_commit_line}

The change manifest below shows what was detected; re-extraction ran to compute the planned merge but neither merge nor write executed. No artifact was modified.

{render the change manifest summary AND the re-extraction summary (what merge and write WOULD have done), read from `{run_dir}/change-manifest.json` and `{run_dir}/reextract-records.json`}

{the warnings the run recorded, read from `{run_dir}/warnings.jsonl`: **Proposed skill brief amendments (not written):** each `proposed-amendment:` one, as the decision that would amend `skill-brief.yaml` (a rescope's, rule R1, among them); **Warnings:** each other one}

**Planned writes (skipped):**
- SKILL.md re-merge with re-extracted exports
- metadata.json version bump (or hold for gap-driven)
- a new version folder beside the current one, `{dry_run_version}`, holding a copy of the current package, and its forge folder with copies of the provenance map, evidence report and extraction rules (not in gap-driven mode, which writes into the current version)
- provenance-map.json update with re-extraction results
- evidence-report.md
- context-snippet.md (only if a staleness trigger fired)
- active-symlink flip (only if version changed)
- metadata.json and provenance-map.json `source_commit` → `{target_commit}` (and `source_ref` → `{target_ref}` when `--target-ref` re-pins the skill)
- the workspace clone moved to `{target_commit}` (only when it still holds `{source_commit}`)

**Recommendation:** Review the manifest and re-extraction summary; if both match expectations, re-run `skf-update-skill` without `--dry-run` to perform the actual update."

`{dry_run_version}` names the folder the run would create, never "the next patch version" by eye: `{source_version_detected}` when step 1 §6c recorded one; otherwise resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and, from `{project-root}`, run `uv run {skillInventoryHelper} version next-patch "{version}"` with the metadata.json `version`, as merge.md §6b does, and take its `next_patch`. When no candidate resolves or the command exits 1 or prints no JSON, say "the next patch version (it could not be computed: {the helper's `error`, or skf-skill-inventory.py is missing})". In gap-driven mode leave this line out.

In `{headless_mode}`, print the line as §5b says, with `status: "dry-run"` and no `--result-dir`, and with no `result_contract`: a dry run writes no result file and does not run `{onCompleteCommand}`. `files_written: []`, `error: null`, `update_mode` from the run; the emitter adds the decisions recorded so far (everything before merge) and the `proposed-amendment:` warnings.

→ Load, read the full file, and execute `{nextStepFile}` (health-check).

### 2. Present Change Summary

"**Update Skill Report: {skill_name}**

---

### Operation Summary

| Metric | Value |
|--------|-------|
| **Skill** | {skill_name} |
| **Forge Tier** | {tier} |
| **Mode** | {update_mode}{mode_fallback_note} |
| **Source commit** | {source_commit_line} |
| **Duration** | {step count} steps |

**`{update_mode}`** is one of `normal`, `gap-driven`, or `degraded` (mirrors the `update_mode` field of `SKF_UPDATE_RESULT_JSON`).

**`{mode_fallback_note}`** surfaces weak-signal fallbacks the workflow took silently and would otherwise be buried in the evidence report. Render it inline after the mode value when any of these conditions fire; render the empty string when none did:

- `--from-test-report` was passed but no test report was found, or the one a result file named is gone, so step 1 fell back to `normal` mode → ` (gap-driven requested; test report missing, fell back to normal)`
- `gap-driven.md §3` skipped the workspace-drift guard because `source_root` is not a git working tree (or HEAD was unreadable) → ` (workspace-drift check skipped: {skip_reason})` where `{skip_reason}` is the helper's `skip_reason` field (`not-a-git-tree` or `HEAD unreadable`)
- `gap-driven.md §3` accepted a drifted workspace under `--allow-workspace-drift` (`{workspace_drift_status}` is `overridden`; this row is where the report shows §3's override warning) → ` (workspace drift accepted: spot-checks read HEAD {head_short_sha}, not pinned {pinned_short_sha}; no provenance line moved or pinned)`
- init.md §6b could not reach upstream and compared the pinned commit (`{source_tree_status}` is `offline`) → ` (upstream not reached: compared the pinned commit only)`
- init.md §6b could not read `{source_commit}`, so every tracked file was re-checked (`{source_diff_status}` is `unavailable` in a source tree) → ` (file list unavailable: every tracked file re-checked)`
- write.md §9 left the workspace clone where it was (`{advance_status}` is `skipped`) → ` (source clone not moved: {advance_skip_reason})`
- Several fired: concatenate the parenthetical notes with `; ` between them

### Changes Applied

| Category | Count |
|----------|-------|
| Files modified | {count} |
| Files added | {count} |
| Files deleted | {count} |
| Files moved/renamed | {count} |
| **Total exports affected** | {count} |

{when the change manifest's `category_d` lists a document: **Tracked documents changed upstream:** each `docs_modified` path (modified) and `docs_deleted` path (deleted)}

{when step 2 wrote `{run_dir}/new-files.json`: **New scripts and assets:** {the length of its `new_files[]`} new; set aside: {the length of `tracked_code[]`} code files the map cites, {the length of `out_of_scope[]`} outside the brief's scope, {the length of `intent_none[]`} of a kind whose intent is `none` (counted from the lists, never from `stats`)}

{in gap-driven mode, when gap-driven.md §1 left gaps unrouted: **Not repaired by this run:** each `{id}: {title} ({category})`}

### Export Changes

| Change Type | Count |
|-------------|-------|
| Updated (signature/type change) | {count} |
| Added (new exports) | {count} |
| Removed (deleted exports) | {count} |
| Moved (file relocated) | {count} |
| Renamed (identifier changed) | {count} |

{if `{provenance_spot_check_warnings}` is non-empty: **WARN, provenance entry left for a person to decide (write.md §3):** {each `export_name: outcome`}}

### Confidence Tier Breakdown

| Tier | Count | Description |
|------|-------|-------------|
| T1 | {count} | AST-verified structural extraction |
| T1-low | {count} | Read by eye, at any tier (`extraction_method: source-read`) |
| T2 | {count} | QMD-enriched semantic context |

{if `{provenance_relabels}` is non-empty: **Relabeled to match extraction_method (write.md §2):** {export names}{; **WARN, no node kind found:** {export names}}}

### [MANUAL] Section Preservation

| Metric | Count |
|--------|-------|
| Sections preserved | {count} |
| Conflicts resolved | {count} |
| Orphans kept | {count} |
| Orphans removed | {count} |
| **Integrity** | {VERIFIED / count issues} |"

### 3. Present Validation Findings

Read the Validation Summary write.md recorded for this update in `{forge_version}/evidence-report.md`: `[MANUAL] integrity` from write.md §1's `manual-verify` verdict, `Confidence tiers` from §2's relabels, `Provenance` from §6, and `Spec compliance`, `Diff` and `Security` from §7.

**If any row is WARN or FAIL:**

"### Validation Findings

| Check | Status | Issues |
|-------|--------|--------|
| Spec compliance | {PASS/WARN/FAIL/SKIP} | {count} (quality score {score}/100) |
| [MANUAL] integrity | {PASS/FAIL} | {count} |
| Confidence tiers | {PASS/WARN} | {count} |
| Provenance | {PASS/WARN} | {count} |
| Diff | {SKIP, or new and fixed counts} | {new} |
| Security | {PASS/WARN/SKIP} | {count} |

{List specific findings if WARN or FAIL}"

**Otherwise:** "### Validation: All checks passed{, with each SKIP row and its reason}."

### 4. Show Files Updated

"### Files Written

| File | Status |
|------|--------|
| `{skill_package}/SKILL.md` | Updated |
| `{skill_package}/metadata.json` | Updated |
| `{forge_version}/provenance-map.json` | Updated |
| `{forge_version}/evidence-report.md` | Appended |

Where `{skill_package}` = `{skills_output_folder}/{skill_name}/{version}/{skill_name}/` and `{forge_version}` = `{forge_data_folder}/{skill_name}/{version}/`: the new version's folders step 4 §6b created (the current version's in gap-driven mode), beside the unchanged previous version — see `knowledge/version-paths.md`."

### 5. Workflow Chaining Recommendations

"### Next Steps

Based on the update results:"

**If all validations passed:**
"- **audit-skill** — Run to verify the update resolved known drift
- **export-skill** — Package the updated skill for distribution
- **test-skill** — Run test suite against the updated skill"

When `{run_dir}/warnings.jsonl` holds a `workspace-clone-not-updated:` line, add: "- test-skill stops with `workspace-drift` until `{workspace_clone}` holds `{target_commit}` (the clone was not moved: {the reason that warning names}). Another skill built from this repository may need the clone where it is; when none does, move it yourself with `git -C "{workspace_clone}" fetch --depth 1 origin {target_commit}` and then `git -C "{workspace_clone}" checkout --detach {target_commit}`, which stops rather than overwrite a local change, and re-run test-skill." Leave out the sentence that names the two commands when that reason is `not-a-clone` or `clone-failed`: there is no SKF clone to move. When that reason is `checkout-interrupted`, keep the fetch and name `git -C "{workspace_clone}" checkout --force --detach {target_commit}` in place of the plain checkout: the time limit stopped the update's own checkout part way, so the clone may hold files of both commits, which stop a plain checkout, and it had no local changes when that checkout began. The fetch stays because no ref keeps that commit in the clone, so git may have pruned it by the time the commands run. test-skill's own message suggests a checkout of `{source_ref}`, which does not reach a new commit of a branch or of `HEAD`.

**If validation warnings/failures exist:**
"- **audit-skill** — Run to identify remaining issues
- Review validation findings above before exporting"

**If triggered by audit-skill chain:**
"- **audit-skill** — Re-run to verify CRITICAL/HIGH drift resolved
- **export-skill** — Package once audit confirms clean state"

### 5b. Result Contract

The shared emitter writes the result contract and prints the line; never type either. Stage the payload in the run folder, from the files this run wrote rather than from memory (`{run_dir}/change-manifest.json` for the counts, the artifacts write.md wrote for `files_written`, the Validation Summary §3 read for `validation_status`):

```bash
cat > "{run_dir}/result-context.json" <<'SKF_JSON'
{"status": "success", "skill_name": "{skill_name}", "version": "{new_version}", "previous_version": "{baseline_version}", "update_mode": "{update_mode}", "files_written": [<each artifact write.md wrote and verified: SKILL.md, metadata.json, provenance-map.json, evidence-report.md, context-snippet.md, active-symlink>], "error": null,
 "result_contract": {"skill": "skf-update-skill", "status": "success", "outputs": [{"type": "skill", "path": "<each modified file's path>"}], "summary": {"update_status": "success", "exports_affected": <total_export_changes, or the gap count in gap-driven mode>, "files_modified": <the files written>, "validation_status": "<passed, warnings or failures>"}}}
SKF_JSON
```

Then, from `{project-root}`, run the emitter with the run folder and the new version's forge folder:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-update-skill --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

It writes the per-run record `{forge_version}/update-skill-result-{YYYYMMDD-HHmmss}.json` (UTC, the time from the clock; `-2`, `-3` appended when a run already took that second's name) and its copy `{forge_version}/update-skill-result-latest.json` (the stable path pipeline consumers read: a copy, not a symlink), each the `result_contract` with the run's `timestamp`, `run_id`, `headless_decisions` and `warnings` stamped in (see `shared/references/output-contract-schema.md`). It folds the run's decision log and warnings in `{run_dir}` into the line, checks it against `shared/scripts/schemas/skf-update-result-envelope.v1.json` and prints it:

```
SKF_UPDATE_RESULT_JSON: {"skf_update": {"status": "success", "skill_name": ..., "version": ..., "previous_version": ..., "update_mode": ..., "files_written": [...], "headless_decisions": [...], "warnings": [...], "error": null}}
```

In `{headless_mode}`, bind `{result_envelope_line}` to that line and do not display it here: the shared health check displays it verbatim as the run's last line. An interactive run runs the command for its result files and need not show the line. When the emitter exits non-zero and its `message` names the payload, fix the payload once and run it again; a write it could not make adds `result_file_write_failed` to the line's `warnings[]`.

- `status`: `"success"` here; §1 stages `"no-changes"`, §1a `"detect-only"` and §1b `"dry-run"`; a halt prints its own `halted-for-*` or `blocked` line through its step's halt procedure and never reaches this step. The full enum lives in the schema.
- `headless_decisions[]`: every gate's record in the run's decision log (init.md §4 degraded-rebuild and §8 confirmation, detect-changes.md §1b / §1c / §2.2, gap-driven.md §1 rule R1, merge.md §8). Each entry `{gate, default_action, taken_action, reason, evidence?}`. Empty when no gate auto-resolved.
- `error`: null on every exit this step prints. A halt's line carries `{phase, path?, reason}`, and pipelines branch on `error !== null` for non-zero exit semantics.
- `warnings[]`: every entry the run recorded, among them `source-tree:`, `source-not-fetched`, `file-diff-unavailable`, `no-baseline-time`, `moved-check-skipped` and `unknown-language` (detect-changes.md §2.1 Category A), `new-files-not-checked` (Category D: a skill with no brief, so no new script or asset was looked for), `source-version-lower`, `unconsumed-test-report` (init.md §4b), `interrupted-run-cleaned` and `interrupted-run-not-cleaned` (init.md §1b), `test-report:` entries (what the test report's helpers could not read, and `test-report: not routed: {id} ({category})` for each gap gap-driven.md §1 did not route), `proposed-amendment:` (a read-only run's brief decisions, not written), `doc-fetch-failed`, `doc-not-hashed` and `doc-drift-not-checked` (a docs-only skill's documents), `workspace-clone-not-updated`, `target-ref-not-recorded`, `workspace_drift_overridden` (gap-driven.md §3), `run-state-not-finished` and `provenance:` entries (write.md §3 and §6: provenance findings left for a person, and spot-check entries §3 left for a person to decide).

**Post-finalization hook.** A finished run, this one or §1's no-change exit, fires the hook; `--detect-only`, `--dry-run` and a halt never do (customize.toml says so). If `{onCompleteCommand}` (resolved in SKILL.md On Activation §4 from `workflow.on_complete`) is non-empty, invoke it after the emitter wrote both result files:

```bash
{onCompleteCommand} --result-path={forge_version}/update-skill-result-latest.json
```

Run it with a bounded timeout (default 60s). On success, log an Info note and continue; on non-zero exit, timeout, or any failure, tell the user in one line with the reason (the line and the result files are written before the hook runs, so they cannot carry its failure) and continue. The hook must never fail the workflow: it is integration glue (notify a CI router, chain audit/export/test) orthogonal to the update outcome. Empty `{onCompleteCommand}` = no-op, no log entry.

### 6. Chain to Health Check

Once the change summary has been presented, the files-written list displayed, and the result contract saved, load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop at the report even though it reads as final.

