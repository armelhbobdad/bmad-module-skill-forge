---
# `{nextStepFile}` is where a repair goes on, step 4, and `{reportFile}` takes
# a dry run (§5).
nextStepFile: 'merge.md'
reportFile: 'report.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
# `{extractPublicApiHelper}`: §4's whole-scope run and §4a's recipe runner. If
# neither exists, §4 runs nothing (the gate asks each answer) and §4a reads the
# files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# `{buildChangeManifestHelper}`: §4's `gap-records` and §4a's `records`.
# HALT if neither resolves.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# `{emitEnvelopeHelper}` and `{runStateHelper}`: SKILL.md binds both, and a
# lost binding resolves here, first existing path wins. The warnings go to the
# run log through the first; the halt procedure runs the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Gap Spot-Check

## STEP GOAL:

Spot-check each gap's export at the commit gap-driven.md §3 confirmed, re-extract only the exports the report gives no line for (§4a), and send the repair on to merge, or a dry run to the report. Under the drift override, §3b's drift gate runs first.

## Rules

- Focus only on the gaps the report lists: merge nothing, and read only the source lines and files §4 and §4a name
- Write nothing outside `{run_dir}`, in any mode
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

The helpers below pass their JSON to steps 4 and 5 through `{run_dir}`, the run folder SKILL.md On Activation created.

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below. This step writes nothing outside `{run_dir}`, so there is nothing to undo, `--dry-run` included.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "gap-driven"}
SKF_JSON
```

Pass `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`run-lock-not-released`) when it could not release it: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "re-extract:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 3b. Drift Gate (only when {workspace_drift_status} is overridden)

Run §4 bullet 1 now: with `--drift-status overridden` its plan checks this gate before any spot-check, and lists in `drift_blocked[]` each entry whose repair needs the tree, with its reason; never classify by hand.

When its `status` is not `drift-blocked`, go on with its output in §4. Otherwise HALT with status `halted-for-workspace-drift` before merge runs, so merge writes nothing and §4a never runs. A rescope's amendment is not in the skill brief yet (rule R1): merge-write.md §6b writes it, so this halt leaves the brief as it was, and a re-run asks again. Display, with `{source_commit}` and `{source_ref}` read from metadata.json:

```
Workspace drift blocks {N} gap(s) that need the pinned tree.

  pinned (metadata.source_commit): {source_commit}
  {if source_ref is set: pinned ref (metadata.source_ref): {source_ref}}
  workspace HEAD ({source_root}):  {head_short_sha}

--allow-workspace-drift reads HEAD, not the pinned commit, and update-skill
writes nothing read at HEAD: no provenance line, signature, parameter list,
return type or node kind.

Gaps that need the pinned tree:
  {for each entry: - {name} ({change_category}, {severity or "no severity"}): {a public API recount from the tree (rule R1) | a line from the tree (rule R3) | a line and a signature from the tree | a signature from the tree}}

Fix one of the following, then re-run update-skill:
  a) Check out the pinned commit: git -C "{source_root}" checkout {source_commit}
     Then re-run --from-test-report without --allow-workspace-drift.
  b) Run a normal update (without --from-test-report), which records the commit
     it reads as the new pin, then re-run test-skill.
```

The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "drift-override: {N} gap(s) need the pinned tree: {name} ({reason}), ..."`.

### 4. Spot-Check Each Gap's Export

Spot-check each gap's citation instead of re-extracting the files: confirm each export the report names is still at its recorded location. Both calls below run `gap-records` (resolve `{buildChangeManifestHelper}` ← first existing path in `{buildChangeManifestProbeOrder}`) from `{project-root}`: it runs each spot-check with the definition-line rules verify-publish.md §6's verifier applies, routes each entry and writes the records, reading the gap-derived manifest gap-driven.md §1 wrote from `{run_dir}/change-manifest.json` (each entry with its `map_match`), never from memory. The "Gap records" section of its docstring is the one statement of that routing and of each record's `verification` outcome: you answer what it asks and run the targeted re-extraction (§4a) it plans.

**The public API, once.** At Forge tier and above, for a skill with a source tree (not docs-only), when `{workspace_drift_status}` is not `overridden` (the drift gate halts every `NEW_EXPORT` then), first run write.md §3b's whole-scope recipe runner call over `{source_root}`, the pinned tree gap-driven.md §3 confirmed. Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and, from `{project-root}`, run it with the longest timeout your shell tool takes (a large tree takes minutes):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" \
    [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] \
    [--language "{language}"] [--scope-type "{scope_type}"] \
    --head-cap 0 -o "{run_dir}/public-api.json"
```

Pass `--brief`, `--language` and `--scope-type` as write.md §3b passes them: the brief when it exists, the other two when metadata.json records them. On exit 1 (`incomplete`) run it once more. When it wrote its JSON (exit 0 or 1), pass `--extraction "{run_dir}/public-api.json"` to both `gap-records` calls below: its entry-point diff answers bullet 2's public-reachability gate wherever it decides it, as a normal update's public surface does, and write.md §3b reuses its counts. After exit 2 or 3, no JSON or no candidate, pass no `--extraction`: the gate then asks for each export it located.

1. **Spot-check and route.** Run:

   ```bash
   uv run {buildChangeManifestHelper} gap-records --plan \
       --manifest "{run_dir}/change-manifest.json" \
       --provenance-map "{provenance_map_path}" \
       [--source-root "{source_root}"] \
       [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] \
       --drift-status "{workspace_drift_status}" \
       [--extraction "{run_dir}/public-api.json"] \
       [--judgments "{run_dir}/gap-judgments.json"] \
       --files-out "{run_dir}/remediation-files.json"
   ```

   Pass `--source-root` unless the skill is docs-only, `--brief` when `{forge_data_folder}/{skill_name}/skill-brief.yaml` exists (a skill built without a brief, such as a quick skill, has no scope to keep to, so nothing is left out), `--extraction` when the run above wrote its JSON, and `--judgments` once the file exists. Act on its `status`:

   - **`drift-blocked`:** §3b halts.
   - **`blocked`** (`rescope_without_amendment[]`): a `DELETED_EXPORT` whose manifest entry carries no `rescope` object (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path, rule R1). HALT with status `blocked` (halt procedure: `phase: "re-extract:rescope"`, `reason: "rescope-without-amendment: {name}"`): a rescope without a brief scope amendment is denominator deflation and must not be written.
   - **`needs-judgment`:** each item is a spot-check whose `file` the definition-line rules cover no language of. Read the file and add, under the item's `gap_id` in `{run_dir}/gap-judgments.json`, its `declaring_line`: the line that declares the export itself, never a decorator or comment above it, or null when no line does. Then run it again.
   - **`planned`:** when `reextract.entries` or `reextract.signatures` is not empty, run §4a for them: the plan wrote their files to `{run_dir}/remediation-files.json`, each entry's `resolved_paths[]` and then the `file` of each export `reextract.signatures` lists (a `NEW_EXPORT` or `MODIFIED_EXPORT` its spot-check located, `verified` or `moved`, at the `line` it gives), whose signature bullet 2 takes from §4a's record of it there. A `NEW_EXPORT` whose `reachability` neither `--extraction` nor `{run_dir}/gap-judgments.json` answers yet is listed too, so its scan goes unused when bullet 2's gate finds it internal. Add none of its `warnings[]`: bullet 2's call prints them again.
   - **Exit 1 or no JSON:** HALT with status `blocked` (halt procedure: `phase: "re-extract:gap-records"`, its stderr as `reason`).

   A severity is blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or unrecognized one is blocking, like `Critical` and `High`. A blocking gap whose export the map does not hold must produce provenance read from the source or halt in this file before merge: for such an export, only a `Medium`, `Low` or `Info` gap may degrade to `unknown`. A `NEW_EXPORT` or `MODIFIED_EXPORT` whose export the map holds (its `map_match` is `found` or `ambiguous`, or `not-found` with a candidate that has a `source_file`: the gap cites another file than the map's entries of its name) never goes to §4a's targeted re-extraction (`reextract.entries`), whatever its severity: when the map holds several entries of its name (`ambiguous`, so nothing is checked), its spot-check at the entry ends `unknown` or `missing` (the entry's file is gone), or the check at a citation of another file pins no line (`unknown`, `cited-elsewhere`: that file's declaration may be another package's, so it is never re-extracted), its entry stays unchanged. Step 5's `apply` warns for it, naming the cause of an `unknown` (several map entries of its name, no definition line or several at the entry, a file no rule covers, a failed or skipped check, a citation of another file than the map's entries of its name). For a blocking gap the `provenance:` warning also names the gap and the one fix a re-run acts on: for several entries of its name, fix them by hand, or give the gap a `file:line` Source at the definition when that file holds only one of them, so the re-run's lookup takes that one; otherwise fix the entry by hand (set its `source_file` and `source_line` to the line that defines it), since the re-run checks the same entry again. Then re-run update-skill. A rule R5 `MOVED_EXPORT` whose spot-check ends `missing` (its map entry's file is gone) keeps its entry unchanged too, whatever its severity, since R5 moves a line, never a file: its `provenance:` warning names the gap, the gone file and the same hand fix. For a `cited-elsewhere` gap, whatever its severity, the warning names the gap, the cited file and its check's cause (such as `missing` or `no-definition`), and where the map holds the name, and the fix for each side that may be wrong: when the map is right, re-run Test Skill, since the test compared another file's declaration, and if the gap comes back, exclude the cited file in the brief's scope when the skill does not cover it (not when the cited file is gone); when an export moved, fix that map entry by hand, then re-run update-skill. When its check read nothing at the cited file (no source tree, the verifier missing, a failed check), the warning says instead to give update-skill the source tree, re-install SKF, or fix what the check failed on, then re-run update-skill.

   With `--brief`, the brief's scope bounds the repair, by the in-scope test Category A applies (`scope.include` and `scope.exclude`, an exclude winning over an include): a cited file or a Remediation path the scope leaves out is never checked, scanned or repaired from, since the declaration there may be another package's, one the skill does not cover. This is the one exception to the rule above that a blocking gap whose export the map does not hold must produce provenance or halt: a gap the scope keeps from a repair ends `unknown`, whatever its severity, with no halt and nothing written for it, so a re-test raises it again. When the map holds the gap's name at another file and the scope leaves out the cited file, no check runs there: `unknown`, `cited-elsewhere`, with `citation_check` `outside-scope`. When the map does not hold the name, a gap whose files the scope all leaves out is never in the plan, and one whose files the scope takes hold no export of its name while it names a file the scope leaves out is not `unresolved`: either is `unknown`, `outside-scope`, its record's `outside_scope` listing the files left out. Step 5's `apply` adds no entry for an `outside-scope` gap, a placeholder included, and warns, naming the gap and the files left out, with the fix: when the skill covers that file, change the brief's scope so it takes it (its `scope.include` or `scope.exclude`), then re-run update-skill; otherwise re-run Test Skill, since the test compared a declaration the skill does not cover. When the gap cites a file the scope takes, the warning also names what its check there found (such as `missing` or `no-definition`), and when that check read nothing (no source tree, the verifier missing, a failed check) it gives that check's fix instead. For a `cited-elsewhere` gap whose cited file the scope leaves out, the warning gives no advice to exclude the cited file, since the scope already leaves it out, and when the export moved there it says to change the brief's scope so it takes that file (its `scope.include` or `scope.exclude`) and fix the map entry by hand. A file the scope takes is repaired from as before, so when the scope takes several packages that declare the name, check each gap's Source before the repair.
2. **Write the gap-driven records** to `{run_dir}/reextract-records.json`, before §5 sends the run on: merge reads them, and step 5's `apply` writes the provenance map from them. Run the same call without `--plan` and `--files-out`:

   ```bash
   uv run {buildChangeManifestHelper} gap-records \
       --manifest "{run_dir}/change-manifest.json" \
       --provenance-map "{provenance_map_path}" \
       [--source-root "{source_root}"] \
       [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] \
       --drift-status "{workspace_drift_status}" \
       [--extraction "{run_dir}/public-api.json"] \
       [--judgments "{run_dir}/gap-judgments.json"] \
       [--remediation-records "{run_dir}/remediation-records.json"] \
       [--evidence "{run_dir}/evidence-records.jsonl" --tier "{forge_tier}"] \
       -o "{run_dir}/reextract-records.json" \
       > "{run_dir}/gap-records.json"
   ```

   Pass `--brief` and `--extraction` as bullet 1 does, and `--remediation-records`, `--evidence` and `--tier` when §4a ran. It writes one verification record per export-bearing entry, the confidence breakdown and counts, and in `files` each record of `{run_dir}/remediation-records.json` it matched by name, or by the public name the runner gives its local name in that file, to an entry §4a scanned for, within that entry's own `resolved_paths[]`, copied as `records` wrote it (one matched by that public name is copied under it, with its own name as `local`), and the record of each export `reextract.signatures` lists, whose `export_type`, `params`, `return_type`, `extraction_method` and `ast_node_type` it puts on that export's verification record, with a `provenance: ... signature not repaired` warning for one it finds no record of at its line: never type a record or count one by hand. The public-name match reads the runner's entry-point diff, so it holds at Forge tier and above: at Quick tier, or when §4a reads the files by eye after the runner exits 3, a gap that names a renamed re-export by its public name matches no record and is `unresolved` below. With `--evidence` it appends its `targeted_reextraction` record to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `targeted_reextraction`, which the evidence report (step 5 §4) shows beside the verified, moved and missing tally. Its JSON goes to `{run_dir}/gap-records.json`. Act on its `status` there:

   - **`unresolved`:** an entry routed to §4a has no record of its name in its path set (nor one the runner re-exports under that name there), or had no path to scan (`files_scanned: 0`). A found export the public-reachability gate below finds internal is a resolution, not a failure. HALT with status `halted-for-remediation-path`, under `--dry-run` too (the run stops here instead of exiting `dry-run`), and display a consolidated report of every `unresolved[]` entry:

     ```
     Targeted re-extraction failed for {N} gap(s).

     A blocking gap (any severity but Medium, Low or Info, a missing or
     unrecognized one included) must resolve to source provenance. The Remediation
     text for the entries below does not name a file that contains the expected
     export, so the workflow cannot produce a non-null `source_file` /
     `source_line` without hallucinating.

     Unresolved entries:
       {for each entry in unresolved[]:}
         - {name} ({severity or "no severity"})
           remediation_paths: {paths, or "none named"}
           rejected_paths:    {each refused path (its reason), or "none"}
           files_scanned:     {count}
           exports_matched:   0

     Fix one of the following, then re-run update-skill:
       a) Add a `file:line` citation to the Gap Report `Source:` field.
       b) Edit the Remediation text to name the file(s) that actually contain the export(s).
       c) Downgrade the gap(s) to Medium/Low/Info (accepts the degraded documentation outcome).
     ```

     Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:targeted-reextraction"`, `reason: "targeted re-extraction failed for {N} gap(s): {name} ({severity or no severity}), ..."`. **Why halt instead of degrading to `unknown`:** a null citation on a blocking gap lets the skill pass re-test while it still hides the broken behavior behind a placeholder.
   - **`needs-judgment`:** for each item, add your answer to each of its `needs` under its `gap_id` in `{run_dir}/gap-judgments.json`, then run it again:
     - **Public-reachability gate (`NEW_EXPORT` only):** `reachability`, for each `NEW_EXPORT` it located (`verified`, `moved` or `re-extracted`, at the item's `file` and `line`) that `--extraction` did not answer. The runner's entry-point diff answers the rest, `public` or `internal-unreachable`, so the call asks only where that diff cannot decide: no `--extraction` (Quick tier, a runner exit 2 or 3), an incomplete run or one with errors, an entry point the runner could not trace (`entry_points.unresolved`), a name it lists in `extraction_gaps`, or a file outside its `files_in_scope_list` or in a language no recipe reads; it also asks for a name its diff lists neither as public nor as internal at that file. Answer `public` when users can import the name from the package's entry point, not merely because a `pub` / `export` / top-level definition exists at the citation, else `internal-unreachable` (a `pub(crate)` / `pub(super)` item, one under a private module): the helper then drops it from the export-bearing set, so it is never written to the documented `exports[]` array or SKILL.md, and lists it in `reclassified[]`, as it does an export the diff finds internal. Do **not** hand-set any `stats` count: write.md §3b's automatic recount derives `exports_internal` / `exports_total` from the merged surface and owns those fields.
     - `docstring`, for each `re-extracted` export: the docstring at its line, or null when it has none. Its record in `files` takes it, so step 4 Priority 5 merges the record as it merges a normal run's extraction.
   - **`written`:** keep its `counts` for §5, and add its `warnings[]` to `warnings[]` (among them `provenance: spot-checks not run: skf-verify-provenance-completeness.py is missing; re-install SKF`, when every check recorded `unknown` for want of the verifier), recording them in one call, from `{project-root}`: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warnings-file "{run_dir}/gap-records.json"`. Its `forwarded[]` entries (`STRUCTURAL_FIX`, rule R2, and `metadata update`, rule R4) go to merge as the manifest holds them, with no spot-check, no provenance lookup and no `entries[]` change. For each export `reclassified[]` names, append the record `reclassified: {export, reachability: "internal-unreachable"}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `reclassified`, which the evidence report (step 5 §4) and the update report list; nothing goes to merge for it.
   - **Exit 1 or no JSON:** HALT with status `blocked` (halt procedure: `phase: "re-extract:gap-records"`, its stderr as `reason`).

   write.md §3 (step 5) accepts null `source_file` / `source_line` only for an `unknown` `Medium`, `Low` or `Info` gap the map does not hold, and leaves unchanged an entry whose definition lines the rules do not recognize, which may be a shape they do not cover: never call it gone. It also leaves unchanged a rule R5 `MOVED_EXPORT` whose map entry's file is gone, with the warning bullet 1 names.
3. Go on to §5. §4a below runs only where bullet 1 calls it.

### 4a. Targeted Re-Extraction Branch (Helper, Called from §4 Bullet 1)

Runs only for the entries §4 bullet 1's plan lists in `reextract.entries` and `reextract.signatures`; a run that routes none here skips it. It produces source provenance for a gap with a blocking `severity` (§4 bullet 1) and no citation that pins a line, so step 5 §3 never writes `source_file: null` for a blocking finding, and reads the signature SKILL.md and the provenance map take for an export a spot-check located.

**Procedure:**

1. **Source access:** read the files under `{source_root}`, the tree gap-driven.md §3 confirmed holds the pinned commit, never through the gh contents API, zread or deepwiki, which may serve another commit.
2. **The file set** is `{run_dir}/remediation-files.json`, which §4 bullet 1's plan wrote: the `resolved_paths[]` of every entry routed here, as they are, less each one the brief's scope leaves out. gap-driven.md §1's `skf-parse-gaps.py` resolved them under `{source_root}` and refused, into `rejected_paths[]`, every path that leaves it (`outside-root`, or `symlink-outside-root` through a link) or names no file (`not-found`, `no-match`). The plan adds the `file` of each export `reextract.signatures` lists, where its spot-check located it under `{source_root}`; of a file only those exports bring, read by eye (item 3) only the exports they name. Remediation text is user-editable: never scan a refused path, and never expand or check a path by hand.
3. **Extract:** read the file set with the tier-appropriate extractor: `records` below labels each export by the tool that produced it, T1 (`extraction_method: ast-grep`) for an ast-grep match and T1-low (`extraction_method: source-read`) for an export read by eye. At Forge tier and above, run the recipe runner over the file set (resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`), from `{project-root}`:

   ```bash
   uv run {extractPublicApiHelper} --mode full \
       --source-root "{source_root}" \
       --files-from "{run_dir}/remediation-files.json" \
       [--scope-type "{scope_type}"] \
       --head-cap 0 \
       -o "{run_dir}/remediation-exports.json"
   ```

   Pass `--scope-type` when step 1 read a `scope_type` from metadata.json, so a component library runs its recipe set. It takes no `--brief`: §4 bullet 1's plan already left out each file a gap cites or its Remediation names that the brief's scope leaves out. On exit 1 (`incomplete`, its JSON written) run it once more. When it is still incomplete, read by eye each file of the file set that has no export in `exports[]` or that an `errors[]` item lists in `unread`, and tell the user which files were read by eye. On exit 2 (an input error, such as a file list it cannot read, or a failure it did not foresee, named in one stderr line with no JSON; `uv` failing to start it exits 2 too), HALT with status `blocked` (halt procedure: `phase: "re-extract:records"`, the stderr line that holds `error:` as `reason`): no by-eye read stands in for it, since this step has written nothing to the skill and reading the files by eye would hide the error. On exit 3, no JSON on another exit, or no candidate resolves, or at Quick tier, read the files by eye (by text pattern). Read by eye only what the recipes leave out: an export a file defines in a form Known Limitation #11 in `{extractionPatternsData}` lists, a file `file_issues[]` names, a name `entry_point_diff.extraction_gaps[]` lists and a file the rule above reads after a still-incomplete run. Write each export read by eye, and the `params` and `return_type` of each function export whose `params` the runner left null, in the shape detect-changes.md §2.1 Category B step 2 gives them, to `{run_dir}/remediation-details.json` as `{"exports": [...]}`. Launch subprocesses in parallel (Pattern 4) when available; sequential fallback otherwise. Follow the tier-degradation rules in `{tierDegradationRulesData}` when AST tools fail on individual files. Then, from `{project-root}`, build the file set's records:

   ```bash
   uv run {buildChangeManifestHelper} records \
       [--extraction "{run_dir}/remediation-exports.json"] \
       [--export-details "{run_dir}/remediation-details.json"] \
       --files-from "{run_dir}/remediation-files.json" \
       -o "{run_dir}/remediation-records.json"
   ```

   Pass each input this item wrote. It writes one record per export, with its labels and `params` in the provenance map's typed form: never type a record. On exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "re-extract:records"`, its stderr as `reason`).

### 5. Display the Repair Summary and Route

Display the summary below, with the `counts` §4 bullet 2 printed:

"**Gap-driven re-extraction.** Verified {verified_count}/{gap_count} citations against live source. Moved: {moved_count}. Missing (entry left unchanged): {missing_count}. Re-extracted (via remediation paths or provenance-completeness, §4a): {re_extracted_count}. Rescoped (removed from surface): {rescoped_count}. Unknown (not in provenance map, a `Medium`, `Low` or `Info` gap §4a found nothing for, a file the brief's scope leaves out, several map entries of its name, a citation of another file than the map's entries of its name, no single definition line, or a line the drift override kept from being moved): {unknown_count}."

A `NEW_EXPORT` or `MODIFIED_EXPORT` the provenance map holds that ends `missing` or `unknown` keeps its entry unchanged, whatever its severity: step 5's `apply` warns for each, with the cause of an `unknown`, and for a blocking gap says what to fix (§4 bullet 1). One whose gap cites another file than the map's entries of its name (`cited-elsewhere`) is never re-extracted, and its warning says what to fix whatever its severity: re-run Test Skill when the map is right, or fix the map entry by hand when the export moved. One the brief's scope keeps from a repair (`outside-scope`, or `cited-elsewhere` with `citation_check` `outside-scope`) is never checked, scanned or repaired from a file the scope leaves out, whatever its severity and with no halt: the provenance map and the export's documentation stay as they were, and its warning says to change the brief's scope so it takes that file (its `scope.include` or `scope.exclude`) when the skill covers it, else to re-run Test Skill.

When `{workspace_drift_status}` is `overridden`, add: "Every check read HEAD {head_short_sha}, not pinned {pinned_short_sha}: no line was moved or pinned."

This step asks nothing after gap-driven.md §1's rule R1 prompts. Load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode: skipping merge and write.** Loading report..." and load `{reportFile}` (report.md, NOT `{nextStepFile}`); it emits status `dry-run` describing what merge and write would have done, so a gap-driven `--dry-run` writes nothing. A halt in §3b or §4 (the drift gate, the targeted re-extraction) stops a `--dry-run` as it stops any other run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{nextStepFile}` (merge.md) to begin the merge operation.
