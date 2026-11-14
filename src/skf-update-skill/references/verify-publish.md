---
nextStepFile: 'report.md'
# `{descriptionGuardHelper}`: §0's guard around every §7 call that may edit
# SKILL.md. HALT if neither resolves: an external tool's rewrite of the
# description would stand.
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
# `{updateActiveSymlinkHelper}`: §8's atomic flip of the active link and §8a's
# check. HALT if neither resolves.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# `{verifyProvenanceCompletenessHelper}`: §6's `verify`, `fix` and `relabel`.
# Advisory: if neither exists, §6 records `Provenance: SKIP (verifier missing;
# re-install SKF)` with a warning.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# `{extractionPatternsData}`: §6's node-kind relabel. If neither exists, §6
# fixes no node kind.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# `{hashContentHelper}`: §7 also runs its `hash` subcommand around `skill-check
# --fix`, besides its [MANUAL] re-check. HALT if neither resolves.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# `{sourceTreeHelper}`: §9's `advance`. If neither exists, skip the call and
# continue: it never gates the workflow.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's
# index folders and SKF's workspace lock out of git, and undoes the
# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path
# exists, skip the call and continue: it never gates the workflow.
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
# `{checkWorkspaceDriftHelper}`: §9 passes it to the advance. If neither
# exists, run the advance without `--drift-helper`, and §9 warns.
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
# `{validateOutputHelper}`: §7's spec check when no skill-check is found. If
# neither exists, §7 records the check as skipped.
validateOutputProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
# `{securityScanHelper}`: §7 runs it on the written package. If neither exists,
# §7 records the scan as skipped.
securityScanProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-security-scan.py'
  - '{project-root}/src/shared/scripts/skf-security-scan.py'
# `{emitEnvelopeHelper}` and `{runStateHelper}`: SKILL.md binds both, and a
# lost binding resolves here, first existing path wins. The warnings go to the
# run log through the first; the halt procedure and §10's finish run the
# second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5b: Verify and Publish

## STEP GOAL:

Check the package write.md wrote (its provenance, skill-check, the [MANUAL] blocks and a security scan), and only then point the active symlink at the new version, move the workspace clone to the commit write.md §3b recorded and close the rollback window.

## Rules

- Focus only on checking the written package and publishing it: write.md wrote the derived artifacts
- Do not modify merged SKILL.md or `references/` content, apart from §6's citation line and prefix fixes outside `[MANUAL]` blocks, and §7's `skill-check check --fix` edits and body split, which moves no section that holds a `[MANUAL]` block; §7 re-checks the [MANUAL] blocks after them. Any mismatch detected during verification triggers HALT, not repair
- HALT immediately on verification failure: §8 points the `active` link at the new version only after §6 and §7, the last checks that can halt, so every halt before it rolls back a version no reader sees yet. A partial-write skill package is worse than an unchanged one
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version the run started from>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>", "files_written": [<what stands: none after a rollback; the artifacts write.md and this step wrote when the helper kept a live version>]}
SKF_JSON
```

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. Until §10 closes the window, the helper first undoes what this run wrote, keeping a version the `active` link already names (§8, its `kept`); then it removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Tell the user in one line what it restored, removed or kept, and name each path its `failed[]` lists for the user to restore or delete by hand. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "write:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 0. Description Guard Protocol

**Used by:** §7 (`skill-check check --fix`, the `skf-shard-body.py` body split and `skill-check split-body --write`).

The deterministic phases are executed via `{descriptionGuardHelper}`: §7 invokes the helper at the capture and verify-restore points around every `skill-check` call.

**Guard outputs.** Each `capture`, run while the in-context SKILL.md copy matches the file on disk, writes the description it reads from `{skill_package}/SKILL.md` to `{run_dir}/description-guard.json`, and each `verify-restore` reads it there with `--captured-file`, so the description never passes through a shell string. Bind `{guarded_description}` ← that file's `description`. Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from each `verify-restore`. When `{guard_restored}` is true, set the in-context `description` to `{guarded_description}` so later sections do not work from the tool-mutated value, and record `description_guard_restored: true` with the tool name and `description_guard_diff_kind: {guard_diff_kind}` in workflow context for the evidence report (write.md §4). A later `verify-restore` that exits 0 with `{guard_restored}` false leaves those records in place.

**Empty-snapshot rule.** `verify-restore` refuses an empty or whitespace-only description in `{run_dir}/description-guard.json`, and a file it cannot read (exit 1, file untouched). Never re-run it with the empty value: writing it back would blank the field the guard protects. If the merged description is still in context (the in-context SKILL.md copy), re-run `verify-restore` with that value: write `{"description": <that value as a JSON string>}` to `{run_dir}/description-guard.json` with a file write, never `echo` (the value can hold quotes, `$` or backticks), and run the same `verify-restore` line again, once. Otherwise, or when that re-run exits 1 too, record `description_guard_restored: false` and `description_guard_refused: empty-capture` with the tool name; the evidence report (write.md §4) renders that as a fired guard, not as a clean run.

**Description Guard population** (used by §7 Post-Write Validation when the §0 protocol fires): fill all four fields from context when `description_guard_restored == true` (triggering tool, whether restore succeeded, and what changed, based on the recorded `description_guard_diff_kind`). When `Restored: false`, each of the other three fields is the dash the `Triggering tool` and `Notes` placeholders offer, the clean-run expected state, except when `description_guard_refused == "empty-capture"` (§0's empty-snapshot rule): then set `Triggering tool` to the recorded tool name, `Original description preserved: false`, and `Notes: guard refused: empty captured snapshot (empty-capture)`, so a refused restore is distinguishable from a run where the guard never fired. Same field semantics and populator logic as create-skill step 6 §8.

### 6. Provenance Completeness

Provenance completeness is a deterministic set-diff plus citation resolution over `metadata.json` (write.md §3b) and `provenance-map.json` (write.md §3). Run it against the just-written artifacts via `{verifyProvenanceCompletenessHelper}`:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata "{skill_package}/metadata.json" \
    --provenance "{forge_version}/provenance-map.json" \
    --source-root "{source_root}" \
    --skill-dir "{skill_package}" \
    --check-node-kinds \
    -o "{forge_data_folder}/{skill_name}/.skf-update-verify.json"
```

The helper reads its `--source-root` (falling back to the provenance map's own `source_root` field when the flag is omitted); pass the resolved `{source_root}` so citation resolution runs against the same tree re-extraction read. When `{source_root}` is null, empty or a URL (a docs-only skill), leave out the `--source-root` line: an empty flag value fails the helper's arguments, and the citation check must still run. When `{source_tree_status}` is `ready` or `offline`, `{source_root}` is still the tree load-baseline.md §6b prepared (step 7 removes it), so citations resolve against the commit write.md §3b recorded. It writes its JSON to `{forge_data_folder}/{skill_name}/.skf-update-verify.json`, beside the init.md §1b lock (each run overwrites it). **Read that JSON and do NOT recompute the set operations by eye, since an LLM set-diff can silently pass a dropped or orphaned entry:**

- `missing[]`: documented exports (metadata `exports[]`) with no provenance entry: a coverage gap.
- `orphaned[]`: provenance `entries[].export_name` whose export was removed but the entry remains.
- `summary.set_diff`: `not-applicable` for a reference app (`scope_type: reference-app` in `{skill_package}/metadata.json`), whose `exports[]` is empty by design while its entries follow each citation: the helper then diffs no sets, `missing[]` and `orphaned[]` stay empty, and its `status` comes from `stale[]`, `citations[]` and `node_kinds[]` alone. `checked` for every other skill.
- `stale[]`: entries whose `source_file:source_line` no longer resolves or is not the line that defines the export; each carries a `reason` of `file-missing`, `line-out-of-bounds`, `line-invalid` or `line-not-definition`. A `line-not-definition` item lists in `definition_lines` every line of the file that defines the export (the `def` or declaration line itself, not a decorator or blank line above it), except that a Python `@overload` group gives its first stub alone. An empty list means the rules found no definition line, which may be a shape they do not cover: the entry is unverified, not gone. A bookkeeping variant (`X_def`, `X_exact`, `a11y_X`) its file never names is checked against its base `X`, and its item names that base in `folded_to`. Internal names are canonicalized through `reexport_map` before the diff, so a barrel-renamed export does not read as missing or orphaned.
- `citations[]`: `[AST:]` / `[SRC:]` citations in SKILL.md and `references/` whose prefix disagrees with the entry they cite (`prefix-mismatch`: `ast-grep` gives `[AST:]`, `source-read` gives `[SRC:]`), and `[AST:]` citations in a skill whose map has no `ast-grep` entry (`ast-without-ast-grep`). Each gives the markdown `file` and `line`, the `citation` text and its `expected_prefix`.
- `summary.stale_check`: `"checked"` when citations were resolved against the source tree, or `"skipped-no-source-root"` when no source root resolved on disk (the completeness + orphan diffs still ran; `stale` is empty by construction, not clean-by-verification).
- `summary.skill_citations_scanned` and `summary.skill_citations_matched`: when citations were scanned and none matched, no citation names a path and line the map records (the citations use another root), so the prefix check compared nothing. List that as a WARN.
- `node_kinds[]`: `ast-grep` entries whose `ast_node_type` is not shaped like a kind or that the ast-grep CLI does not know as a node kind of the entry's language (`invalid-kind`), or whose kind is `ERROR` (`error-kind`). Each gives the entry's `entry_index`, `export_name`, `source_file`, `source_line`, `ast_node_type` and `language`. `summary.node_kind_check` is `skipped-no-ast-grep` when no ast-grep CLI is on PATH, or `skipped-unrecognized-ast-grep` when the ast-grep found does not reject a kind no grammar has: either way ast-grep judged no kind. `node_kinds_unchecked[]` lists, with a `reason`, the entries whose kind ast-grep could not judge, and `summary.node_kind_check_skipped` counts the ast-grep entries in files ast-grep has no language for: list each unchecked entry, and the skipped count, as a WARN.

When the helper exits 2 it writes no JSON: record `Provenance: WARN (not run: verifier error)` with its stderr in the evidence report's Validation Summary and continue to §7. When the second run below exits 2, record the fixes already applied and `second run: verifier error` the same way and continue to §7.

**Fix the findings that have one answer**, in this order, then run the command above once more:

1. **Citation prefixes and source lines.** Never apply them by hand: from `{project-root}`, run the verifier's `fix` on the JSON the run above wrote:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} fix \
       --verify "{forge_data_folder}/{skill_name}/.skf-update-verify.json" \
       --provenance "{forge_version}/provenance-map.json" \
       --skill-dir "{skill_package}" \
       --manual-inventory "{manual_inventory}" \
       [--no-line-moves]
   ```

   Pass `--no-line-moves` when `{workspace_drift_status}` is `overridden` (gap-driven.md §3): the tree read is not the recorded commit, so its lines prove nothing about the map. `fix` prints `applied[]` (each fix it made), `left_as_warn[]` (each finding it left for a person, with its `why`), `files_written[]` and `manual_verify` (the SKILL.md [MANUAL] blocks checked against `{manual_inventory}` after its writes).
   - **`manual_verify.ok` is false** (a [MANUAL] block changed): HALT with status `halted-for-manual-mismatch`. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after the provenance fixes: ..."`, as write.md §1's does. Alert the user: "**[MANUAL] section integrity failure after the provenance fixes.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as write.md §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as write.md §1's does.
   - **Exit 2** (no JSON; its stderr line names any file it already wrote): record `Provenance: WARN (not fixed: verifier error)` with that line, re-read each file it names into context, and go on to step 2.
   - **Otherwise:** re-read each file in `files_written[]` into the in-context copies (the merged SKILL.md and `references/` content and write.md §3's provenance map), so later sections and the report read the fixed text, and add `SKILL.md` and `provenance-map.json` to `files_written[]` (report.md §5b) when `fix` wrote them.
2. **Node kinds.** Never set a kind by hand: from `{project-root}`, run the verifier's `relabel` on the `node_kinds[]` of the JSON the first run above wrote, over the map as step 1 left it:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} relabel \
       --provenance "{forge_version}/provenance-map.json" \
       --node-kinds "{forge_data_folder}/{skill_name}/.skf-update-verify.json" \
       --recipes "{extractionPatternsData}" \
       [--records "{run_dir}/reextract-records.json"] \
       [--source-root "{source_root}"] [--no-kind-at] \
       -o "{run_dir}/relabel-node-kinds.json"
   ```

   It sets each entry's `ast_node_type` to the `kind` of the recipe this run's record of the export names (`ast_recipe`, in a `files` record of `{run_dir}/reextract-records.json`, which re-extract.md §4 or gap-spot-check.md §4 wrote), else to the kind `kind-at` finds at the entry's current `source_line`, and never changes `extraction_method`. Pass `--records` when that file exists, `--source-root` when there is a local source tree, and `--no-kind-at` when `{workspace_drift_status}` is `overridden` (gap-driven.md §3: the tree read is not the recorded commit, so run no `kind-at`). On exit 0 or 1, list each `left_as_warn[]` item as a WARN with its `why`, re-read the map into write.md §3's in-context copy, and add `provenance-map.json` to `files_written[]` when its `files_written[]` names the map. With no candidate for the verifier or `{extractionPatternsData}`, or on exit 2 (then with its stderr line), fix no node kind and list each one as a WARN.

These fixes apply to any entry, a gap-driven `verified` or `moved` entry included (write.md §3). Fix nothing else: each `left_as_warn[]` item stays for a person to decide, and so do `missing` / `orphaned` exports. A `line-not-definition` item with an empty `definition_lines` is never fixed: list its export as unverified.

Map the re-run's `status` to the `Provenance:` line of the write.md §4 evidence report's Validation Summary: `PASS` when `status == "pass"`, `WARN` when `status == "findings"`. For a reference app that status comes from its stale lines, citation prefixes and node kinds alone (`summary.set_diff` `not-applicable`): note `set diff not applicable: reference app` in the Validation Summary, never as a WARN. Provenance findings are **advisory**: they do not block the update. In the evidence report's Validation Summary, list the source lines, citation prefixes and node kinds this section fixed (`fix`'s `applied[]` and the `relabeled[]` of step 2) and the unverified exports, then each `left_as_warn[]` item and each other `missing` / `orphaned` / `stale` / `citations` / `node_kinds` finding the re-run still reports as a WARN so the user can decide, and note `source lines not checked: no local source tree` when `stale_check` was `skipped-no-source-root`, `node kinds not checked: no ast-grep CLI` or `node kinds not checked: unrecognized ast-grep` when `node_kind_check` was `skipped-no-ast-grep` or `skipped-unrecognized-ast-grep`, each `node_kinds_unchecked[]` entry with its `reason`, and `summary.node_kind_check_skipped` when it is above 0. Add each of those WARNs and the unverified exports to `warnings[]` with a `provenance:` prefix (for example `provenance: search line 26 does not define it; definition lines 27, 31`); write.md §3 recorded `{provenance_spot_check_warnings}` already.

**Under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3), the verifier read `{source_root}` at HEAD, not the pinned commit, and a file or line missing at HEAD may still be at the pinned commit: end the `Provenance:` line of the Validation Summary, and each WARN this section lists for a `stale[]` finding (`file-missing`, `line-out-of-bounds`, `line-invalid`, `line-not-definition`), an unverified export or a finding `fix` left as `line-moves-skipped`, with ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`.

**Verifier missing:** if neither probe path resolves, record `Provenance: SKIP (verifier missing; re-install SKF)` in the evidence report's Validation Summary, add `provenance: verifier missing; re-install SKF to check provenance completeness` to `warnings[]`, recorded as **Warnings go to the run log** says, and go on to §7. Compare no set and check no line by hand: an LLM set-diff can silently pass a dropped or orphaned entry.

### 7. Run Post-Write Validation

skill-check runs once per update, here, against the written package, and once more after a body split (below) to read the score the split left. Check that it is available, never assume it: run `npx skill-check -h`.

**Description Guard Protocol:** every invocation below that may modify SKILL.md (`skill-check check --fix`, the `skf-shard-body.py` body split and any `split-body` write) must run inside the four-phase guard defined in §0. Invoke `{descriptionGuardHelper}` at the capture and verify-restore points around each call:

```bash
uv run {descriptionGuardHelper} capture "{skill_package}/SKILL.md" > "{run_dir}/description-guard.json"
# the snapshot lands in the run folder; read its `description` as `guarded_description`

uv run {descriptionGuardHelper} verify-restore "{skill_package}/SKILL.md" \
    --captured-file "{run_dir}/description-guard.json"
```

**If skill-check is available:**

- **Hash before --fix:** before the §0 guard's `capture` for the `--fix` call below, run `uv run {hashContentHelper} hash "{skill_package}/SKILL.md"` from `{project-root}` and keep the `content_hash` it prints.
- Run `npx skill-check check "{skill_package}" --fix --format json --no-security-scan` **inside the §0 guard**, with its output captured apart (`> "{run_dir}/skill-check.json" 2> "{run_dir}/skill-check.stderr"; echo "skill-check exited $?"` after it). One call validates the package against the spec, scores it and fixes what has one answer; `--no-security-scan` leaves the security scan to **Security scan** below. Read the JSON, not the exit code: the quality score (`scores[].score`, the entry matching the skill, or a top-level `qualityScore` on an older skill-check), and the remaining `diagnostics[]`, from the JSON object at the start of `{run_dir}/skill-check.json` (stdout can go on after it, a `Wrote <path>` line when the project config sets a report path). Give the call the longest timeout your shell tool takes. When no "skill-check exited" line came back, the shell tool stopped the call before skill-check finished: still run the guard's `verify-restore` and the second `hash` call below before reading `{run_dir}/skill-check.json`.
- **Context sync after --fix:** after that call's `verify-restore`, run `uv run {hashContentHelper} hash "{skill_package}/SKILL.md"` again. When the `content_hash` it prints differs from the one kept before the call, or either `hash` call printed no `content_hash`, re-read SKILL.md into the in-context copy, so the report does not work from a copy that differs from the file on disk. The §0 guard has already restored `description` if it diverged.
- If `body.max_lines` or `body.max_tokens` is reported, load, read the full file and follow `references/body-split.md`, **inside the §0 guard**.
- When a previous version is on disk (outside gap-driven mode), run `npx skill-check diff "{skill_group}/{baseline_version}/{skill_name}" "{skill_package}"` and record its new and fixed issues as informational; otherwise record `Diff: SKIP`.

**Re-check the [MANUAL] blocks** once `--fix` and any split have run, from `{project-root}`:

```bash
uv run {hashContentHelper} manual-verify "{skill_package}/SKILL.md" \
    --inventory "{manual_inventory}"
```

On `ok` false, HALT with status `halted-for-manual-mismatch`, as write.md §1 does. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after skill-check: modified {modified}; missing {missing}"`. Alert the user: "**[MANUAL] section integrity failure after skill-check.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as write.md §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as write.md §1's does.

**If skill-check is unavailable:** record `Diff: SKIP`, and check the structure by script instead: resolve `{validateOutputHelper}` ← first existing path in `{validateOutputProbeOrder}` and, from `{project-root}`, run `uv run {validateOutputHelper} "{skill_package}"`. Record `Spec compliance: PASS (skf-validate-output.py)` when it reports no issue, and `Spec compliance: WARN (skf-validate-output.py)` with each issue it reports otherwise; when no candidate resolves, record `Spec compliance: SKIP (skill-check unavailable, no validator)`. Nothing here changes SKILL.md, so the [MANUAL] re-check above does not run.

**Security scan**, whether or not skill-check is available: resolve `{securityScanHelper}` ← first existing path in `{securityScanProbeOrder}` and, from `{project-root}`, run `uv run {securityScanHelper} run --package "{skill_package}"` with the longest timeout your shell tool takes (it ends within two minutes). It runs Snyk Agent Scan, at the version it pins, only when `SNYK_TOKEN` is set, and reads the scanner's own JSON report, so rely on the JSON it prints, never on an exit code. Record the Validation Summary's `Security` row from its `security_result` and `note`: `Security: PASS ({note})` for `pass`, `Security: WARN ({note}: {each findings[] entry's text})` for `warn`, each finding an advisory warning, and `Security: SKIP ({note})` for `skipped`. When no `{securityScanProbeOrder}` path exists, record `Security: SKIP (skf-security-scan.py missing)`; when the call prints no JSON object, record `Security: SKIP (skf-security-scan.py printed no result)`.

Record the results in the evidence report's Validation Summary (write.md §4): `Spec compliance` from the score and the remaining `diagnostics[]`, `Diff`, and `Security` as the security scan rule above reads it (its first word `PASS`, `WARN` or `SKIP`, its note in parentheses after it), with any `description_guard_restored` event the §0 protocol recorded. They are advisory: do not block on warnings.

### 8. Update the Active Symlink

Flip `{skill_group}/active` to point at the current `{version}` via the helper, now that §6 and §7 have checked the written package. The call is **always** run: atomic, idempotent, and verified in one shot. The helper's no-op path handles the "version did not change" case (gap-driven mode, or no source drift) without writing to disk:

```bash
uv run {updateActiveSymlinkHelper} update \
    --skill-group {skill_group} \
    --version {version}
```

The helper emits a result envelope with `status` ∈ `{ok, flipped, mismatch, missing-target, busy}` and a pre-formatted `log_message`. Log the message to the evidence report.

**Dispatch on `status`:**

- **`ok`** (exit 0): symlink already points at `{version}`, so no disk write. Continue to §8a.
- **`flipped`** (exit 0): symlink was atomically updated (temp-and-replace). Continue to §8a.
- **`missing-target`** (exit 2): `{skill_group}/{version}/` does not exist on disk, so merge-write.md §6b did not create it. HALT with status `halted-for-write-failure` and display `halt_message` verbatim.
- **`mismatch`** (exit 2): the link still points elsewhere after the flip. HALT with status `halted-for-write-failure` and display `halt_message` verbatim.
- **`busy`** (exit 2): another flip of the link held its lock for the helper's whole wait, so the link is unchanged. HALT with status `halted-for-concurrent-run` and display `halt_message` verbatim.
- **Any other exit, or no JSON on stdout** (exit 1, or an exit 2 that prints no JSON: the helper could not run, could not move the link, or failed after moving it, and the last line it prints on stderr says why): HALT with status `halted-for-write-failure` and display that line, which is `exit <code>` when the helper prints nothing on stderr. The halt procedure takes `phase: "write:active-symlink"`, `path: "{skill_group}/active"`, `reason: "<that line>"`.

For each exit-2 halt, the halt procedure takes `phase: "write:active-symlink"`, `path: "{skill_group}/active"`, `reason: "<status>: <halt_message>"`. Its rollback removes the new version (the `active` link does not name it) or, in gap-driven mode, restores the package from the snapshot.

### 8a. Verify the Active Symlink

Check, read-only, that the `active` link resolves to the version write.md §3b wrote to `metadata.json`, in every mode (consumers that do not read the export manifest fall back to the link, `knowledge/version-paths.md` §Reading Workflows step 5):

```bash
uv run {updateActiveSymlinkHelper} verify \
    --skill-group {skill_group} \
    --version {version}
```

On `mismatch` (exit 2), HALT with status `halted-for-write-failure` and display the helper's `halt_message` verbatim: it names the diverged target, the expected version and the recovery command. The halt procedure takes `phase: "write:verify-active-symlink"`, `path: "{skill_group}/active"`, `reason: "mismatch: <halt_message>"`.

On `ok` (exit 0), continue to §9. On any other exit, or no JSON on stdout (exit 1, or an exit 2 that prints no JSON: the helper could not run or could not read the link, as when a real folder has replaced `active` or the skill folder is gone since §8, and the last line it prints on stderr says why), HALT with status `halted-for-write-failure` and display that line, which is `exit <code>` when the helper prints nothing on stderr. The halt procedure takes `phase: "write:verify-active-symlink"`, `path: "{skill_group}/active"`, `reason: "<that line>"`.

### 9. Move the Workspace Clone to the Recorded Commit

Run only when `{source_tree_status}` is `ready` and `{workspace_clone}` is not null. test-skill and audit-skill read the skill's source from metadata.json `source_root`, the clone SKF keeps for this repository, and test-skill compares its HEAD with the `source_commit` write.md §3b just wrote. From `{project-root}`, resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`, `{cccGitHygieneHelper}` ← first existing path in `{cccGitHygieneProbeOrder}` and `{checkWorkspaceDriftHelper}` ← first existing path in `{checkWorkspaceDriftProbeOrder}`, then run:

```bash
uv run {sourceTreeHelper} advance \
    --clone "{workspace_clone}" \
    --source-repo "{source_repo}" \
    --expect-commit "{source_commit}" \
    --target "{target_commit}" \
    --target-ref "{target_ref}" \
    --tree "{source_tree}" \
    --timeout "{tree_timeout}" \
    [--hygiene-helper "{cccGitHygieneHelper}"] \
    [--drift-helper "{checkWorkspaceDriftHelper}"]
```

Pass `--hygiene-helper` and `--drift-helper` only when they resolved. `{source_commit}` is the commit load-baseline.md §6 read from metadata.json, before write.md §3b recorded `{target_commit}`, and `{tree_timeout}` is the time limit load-baseline.md §6b chose: the helper stops itself within it.

Bind `{advance_status}` ← `status`, `{advance_skip_reason}` ← `skip_reason`, `{advance_head}` ← `head_sha`, `{advance_log}` ← `log_message` and `{advance_warnings}` ← `warnings`. Log `{advance_log}` in the evidence report and add each `{advance_warnings}` entry to `warnings[]` as `source-tree: <entry>`.

- **`advanced` or `ok`:** continue.
- **`skipped`:** add `workspace-clone-not-updated: {advance_skip_reason}; {workspace_clone} holds {advance_head or "no commit"}, so test-skill stops with workspace-drift until it holds {target_commit}` to `warnings[]`, and continue.
- **`{sourceTreeHelper}` does not resolve, or the command fails or prints no JSON:** add the same warning with reason `helper-unavailable`, and continue.

This section never halts: the skill is written, and only the clone test-skill reads is out of step.

### 10. Close the Rollback Window

Once §9 has run, this run's writes stand: from `{project-root}`, run `uv run {runStateHelper} finish --run-dir "{run_dir}"`. It marks the run finished, then deletes the snapshot: from then on a halt undoes nothing. When it fails or prints no JSON, add `run-state-not-finished: {its message}` to `warnings[]`: no step after this one halts, and step 7 removes the run folder.

### 11. Route to Next Step

This step auto-proceeds: no user choices. Once §10 has run, display "**Proceeding to report...**", then load, fully read, and execute `{nextStepFile}` to display the change report.
