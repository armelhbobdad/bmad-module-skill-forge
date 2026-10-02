---
# `{resumeStepFile}` is where a repair goes on, step 4 (§5 loads it).
# `{reportFile}` takes a detect-only run, a run with no gap to repair (§2)
# and a dry run (§5).
resumeStepFile: 'merge.md'
reportFile: 'report.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
# `{parseGapsHelper}`: §1 reads the test report's gaps. HALT if neither exists.
parseGapsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-parse-gaps.py'
  - '{project-root}/src/shared/scripts/skf-parse-gaps.py'
# Resolve `{checkWorkspaceDriftHelper}` to the first existing path; HALT if
# neither candidate exists. §3 relies on the helper for the deterministic
# workspace-pinning guard (git rev-parse + short-SHA prefix match + halt
# message rendering). Falling back to prose-driven git invocation would
# lose the four-state dispatch (ok / skipped / mismatch / overridden).
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
# Resolve `{verifyProvenanceCompletenessHelper}` to the first existing path
# when §4 bullet 2 first needs it. Advisory: if neither resolves, each
# spot-check records `unknown`, never a line found by eye.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# `{extractPublicApiHelper}`: §4a's recipe runner. If neither exists, read
# the files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

<!-- Config: communicate in {communication_language}. -->

# Gap-Driven Repair

## STEP GOAL:

Repair the gaps a test report found, at the commit the skill is pinned to. When `update_mode` is `gap-driven` (set in step 1 by `--from-test-report` or by its §4b offer), init.md §8 loads this file in place of steps 2 and 3: it translates the report's gaps into the change manifest, checks that `{source_root}` holds the pinned commit, spot-checks each gap's export there and re-extracts only the exports the report gives no line for. The source has not drifted, so no file is compared.

## Rules

- Focus only on the gaps the report lists: merge nothing, and read only the source lines and files §4 and §4a name
- Write nothing outside `{run_dir}`, in any mode

## Steps

The helpers below pass their JSON to steps 4 and 5 through `{run_dir}`, the run folder SKILL.md On Activation created.

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved. This step writes nothing outside `{run_dir}`, so there is nothing to undo, `--dry-run` included.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "gap-driven"}
SKF_JSON
```

Pass `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`run-lock-not-released`); it never stops on a result. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "re-extract:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

### 1. Translate the Test Report's Gaps

Read the gaps of the test report at `{test_report_path}` and translate them:

1. **Read the gaps through `{parseGapsHelper}`** (resolve it ← first existing path in `{parseGapsProbeOrder}`). From `{project-root}`, run:

   ```bash
   uv run {parseGapsHelper} parse \
       --report "{test_report_path}" \
       [--source-root "{source_root}"] \
       [--provenance-map "{provenance_map_path}"]
   ```

   Pass `--source-root` unless the skill is docs-only (there is no source tree), and `--provenance-map` whenever init.md §4 loaded one. It reads the gap ledger test-skill wrote beside the report (`test-findings-<the report's run id>.json`), which holds every gap of a run test-skill's hard gate blocked (its `stepsCompleted` ends at `hard-gate`), and for a report older than the ledger the report's `## Gap Report`. Never read gaps from the report by eye.

   - **Exit 0:** take its `gaps[]`, and add each of its `warnings[]` to `warnings[]` as `test-report: <entry>`.
   - **Exit 1** (`status: "error"`, with `code` `REPORT_MISSING`, `LEDGER_MISSING`, `LEDGER_INVALID` or `INVALID_INPUT`), **any other exit, no JSON, or no candidate resolves:** HALT with status `blocked` and display "**The test report's gaps could not be read:** {code}: {error}" ("skf-parse-gaps.py is missing; re-install SKF" when no candidate resolved). The halt procedure takes `phase: "detect-changes:parse-gaps"`, `path: "{test_report_path}"`, `reason: "{code}: {error}"`.

2. **Translate each gap by its `category`** (the gap ledger's closed set of slugs), never by its severity. A report older than the ledger gives no `category`: take the row whose gap type its title and issue describe.

| `category` | Gap type (a report older than the ledger) | Change Category |
|------------|-------------------------------------------|-----------------|
| `missing-export`, `missing-type` | Missing export, type or interface documentation | NEW_EXPORT (an undocumented public export or type), unless the remediation says the export is internal or out of scope: then DELETED_EXPORT (rescope), see rule R1 |
| `split-body-mismatch` | Split-body inconsistency: the SKILL.md body and a `references/*.md` file document one export differently, with a `Source:` inside the skill package | STRUCTURAL_FIX, see rule R2 (for an older report, this row takes precedence over the Signature mismatch row below) |
| `signature-mismatch`, `fabricated-signature`, `stale-documentation` | Signature mismatch; stale documentation (the skill documents an export the source no longer has) | MODIFIED_EXPORT (the documentation needs updating from source) |
| `structural`, `broken-reference`, `inaccurate-reference`, `reference-escape`, `integration-pattern`, `migration-section`, `scripts-assets` | Structural or coherence drift in the output files only, no source change | STRUCTURAL_FIX, see rule R2 |
| `provenance-completeness` | Export documented in SKILL.md/references but **missing from the provenance-map** | NEW_EXPORT (provenance-completeness), see rule R3 |
| `provenance-line` | Provenance line is not the export's definition | MOVED_EXPORT (provenance line), see rule R5 |
| `metadata-drift`, `metadata` | Divergent export counts in the metadata; missing metadata or examples | metadata update, see rule R4 |
| any other | any other gap | not routed |

**Not routed:** update-skill has no repair for the other categories. `provenance-unverified` asks for a check by hand, `denominator-inflation` and `multi-denominator` concern the brief's scope and the count design, and `numerator-inflation`, `scripts-assets-provenance`, `observation`, `discovery`, `description` and `external-validator` need a person or another workflow. Such a gap takes no manifest entry (bullet 4 below).

**Translation rules (referenced by the table above):**

- **R1: DELETED_EXPORT (rescope).** A coverage gap is a rescope only when its remediation text names removal (`rescope`, `remove from surface`, `out of scope`) or the export is upstream `#[doc(hidden)]` / internal. Default a `missing-export` or `missing-type` gap to NEW_EXPORT (document it); choose rescope only on that explicit signal. **Interactive:** prompt per qualifying gap: "[D] Document the export / [R] Rescope (remove from the public surface)". **Headless:** default to **document** (NEW_EXPORT); choose rescope only when the remediation explicitly says removal *and* the export is internal/`#[doc(hidden)]`. A rescope is honest only if the reduction is expressed in the brief's scope: give the manifest entry a `rescope` object holding the `scope.amendments[]` entry (`category: "scope-expansion"`, `action: "excluded"`, `path`, `reason` (the remediation), `date`, `workflow: "skf-update-skill"`) **and** the export's source path for `brief.scope.exclude`, then route the entry to merge Priority 1 (removal) so steps 4 and 5 remove it and recompute stats from the amended scope. This step writes neither to the brief: step 4 §6b writes both, the first write of the repair, and skips an amendment or an exclude path the brief already holds, so a re-run never adds them twice and a run that stops before step 4 (a halt, `--dry-run`, `--detect-only`) leaves the brief as it was. In those read-only modes add `proposed-amendment: excluded {path} (scope-expansion); not written: {--dry-run or --detect-only}` to `warnings[]`. Never close a coverage gap by editing `metadata.stats` to equal the documented count: that is denominator deflation and `skf-test-skill` will reject it.
- **R2: STRUCTURAL_FIX.** A finding whose fix edits the generated markdown only, with no source change and no provenance entry change. It carries `remediation` text describing the surgical markdown edit and routes to merge Priority 8 (generated-markdown edit only); it never adds, modifies, or removes a provenance `entries[]` row. Two kinds of finding qualify:
  - a coherence finding from `skf-scan-skill-md-structure.py` (e.g., `table_drift`, `unbalanced_fences`, a broken intra-skill anchor) that touches the generated output file only;
  - a split-body consistency finding (test-skill coverage-check §1b `cross_check_mismatches`): the SKILL.md body and a `references/*.md` file document one export differently. test-skill rates it High, as it rates a signature mismatch against the source, yet it needs nothing from the source: merge Priority 8 edits the `references/*.md` file to match the body. Its `category` is `split-body-mismatch`; in a report older than the ledger, recognize it by its `Source:`, which points inside the skill package (at the skill's own `SKILL.md` or at one of its `references/*.md` files, whether the path is written relative to the package or through `{skill_package}`), while its issue sets the SKILL.md body against a `references/*.md` file. Test for it before the High "Signature mismatch" row: a High signature gap whose `Source:` points into the source tree, or that has no `Source:`, stays `MODIFIED_EXPORT`.
- **R3: provenance-completeness.** An export documented in SKILL.md/`references/` but absent from the provenance-map. These are documented-and-known, so `unknown` is never correct: route to §4a's targeted re-extraction **regardless of severity**, gated only on `source_root` being pinned and readable (§4 bullet 2).
- **R4: metadata update.** A metadata-coherence patch that changes no export's source (e.g., reconcile a divergent `stats` count). Routes to merge Priority 8b and is applied by write.md §2 *before* the automatic stat recount (see merge.md §3 / write.md §2).
- **R5: MOVED_EXPORT (provenance line).** A `provenance-line` gap (in a report older than the ledger, a Low gap titled `Provenance line is not the definition of {export_name}`, test-skill coverage-check §4c) says the provenance map's `source_line` for that export is not the line that defines it. Its `Source:` is the map's `{source_file}:{source_line}`, so `source_citation` is set, and its remediation lists the file's definition lines. This row takes precedence over the Low `metadata update` row (R4). Route the entry to §4's spot-check only, with no public-reachability gate and no §4a.

3. Build the change manifest from the translated gaps (the source has not changed, so no file is compared). Each entry takes these fields from the helper's gap, never from the report by eye:

   - **`name`**: the gap's `export`, else the export its `title` names.
   - **`gap_id`** and **`category`**: the gap's `id` and `category`. For a report older than the ledger, `category` is the slug of the row bullet 2 chose that names the gap's type (`missing-export` or `missing-type` for a missing export or type), so §4 routes on `category` alone.
   - **`severity`**: the gap's `severity` (`Critical`, `High`, `Medium`, `Low`, `Info`, or null when the report gave none). A severity is blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or unrecognized one is blocking, like `Critical` and `High`. §4 and write.md §3 gate the null-citation fallback on this one rule: a blocking gap must produce provenance read from the source or halt in this file before merge, and only a `Medium`, `Low` or `Info` gap may degrade to `unknown`.
   - **`source_citation: {file, line}`**: the gap's `source_citation`, which §4 spot-checks against the source rather than flagging the export as `unknown`. Leave it out when it is null (a `Source:` that is a region reference such as `@storybook/addon-docs control primitives`, or none) or names a line inside the skill package (a split-body finding's `SKILL.md:42`, rule R2), which names generated markdown, not source.
   - **`remediation_paths`**, **`resolved_paths`** and **`rejected_paths`**: the gap's: the path tokens of its `Remediation:` text, the source files they name under `{source_root}`, and each one the helper refused with its reason (`outside-root`, `symlink-outside-root`, `not-found`, `no-match`). For a rule R3 gap with no `resolved_paths`, take both lists from the helper's root check of the source file its documentation cites, from `{project-root}`: `uv run {parseGapsHelper} paths --source-root "{source_root}" "<the cited source file>"`. §4a scans only `resolved_paths`.
   - **`change_category`**: the Change Category resolved from the table above (`NEW_EXPORT`, `MODIFIED_EXPORT`, `MOVED_EXPORT`, `DELETED_EXPORT`, `STRUCTURAL_FIX`, or `metadata update`). §4 bullet 2 partitions on this field; merge.md §3 dispatches on it.
   - **`remediation`**: the gap's full `remediation` text, verbatim. Required for `STRUCTURAL_FIX` (the surgical markdown edit), `metadata update` (the patch description), and `DELETED_EXPORT` rescope (the removal rationale recorded in the `scope.amendments[]` entry). For `NEW_EXPORT` / `MODIFIED_EXPORT` it is informational.
   - **`provenance_completeness: true`**: set on a `NEW_EXPORT` entry whose gap is rule R3 (documented in SKILL.md/`references/` but absent from the provenance-map). §4 routes these to §4a regardless of severity.
   - **`rescope`**: on a rule R1 `DELETED_EXPORT`, the amendment and the exclude path above.

   Write the entries to `{run_dir}/change-manifest.json`, where §4 and step 5 read them, as `{"mode": "gap-driven", "entries": [...]}`:

   ```bash
   cat > "{run_dir}/change-manifest.json" <<'SKF_JSON'
   {"mode": "gap-driven", "entries": [<each entry, with the fields above>]}
   SKF_JSON
   ```
4. Set `gap_count` from the total number of translated entries. Add each gap the table does not route to `warnings[]` as `test-report: not routed: {id} ({category})`, and keep its `id`, `title` and `category` for §2.

### 2. Display the Gap Summary and Route

Display "**Gap-driven update mode.** Translated {gap_count} test report findings into the change manifest; source drift detection skipped.", then list each gap §1 did not route, as `{id}: {title} ({category})`, and say this run does not repair them. Then take the branch that applies:

- **`detect_only_mode == true`** → display "**Detect-only mode: skipping re-extract, merge and write.** Loading report..." and load, read the full file, then execute `{reportFile}` (report.md), which emits status `detect-only`.
- **No gap translated** (`gap_count` is 0, an empty manifest) → load, read the full file, then execute `{reportFile}` (report.md), which emits status `no-changes`.
- **Otherwise** → continue to §3.

### 3. Verify the Workspace Holds the Pinned Commit

The spot-checks read source at recorded `source_line` positions and must see the exact bytes the skill was pinned against. A drifted workspace silently verifies against the wrong tree: moved or renamed symbols appear "verified" because the recorded line now points at different code. Before reading any source, run the guard via `{checkWorkspaceDriftHelper}`:

```bash
uv run {checkWorkspaceDriftHelper} <source-root> \
    --pinned-commit "<metadata.source_commit>" \
    [--source-ref "<metadata.source_ref>"] \
    [--allow-drift]
```

Pass `--allow-drift` only when the user provided `--allow-workspace-drift` to update-skill. The helper accepts `""` and `"local"` as the "no pinned commit" sentinels; it also auto-skips when `source_root` is not a git working tree (bare checkout, tarball extract, etc.).

The helper emits a result envelope:

```json
{
  "status": "ok" | "skipped" | "mismatch" | "overridden",
  "skip_reason": "no-pinned-commit" | "not-a-git-tree" | null,
  "head_sha": "...", "head_short_sha": "...", "match_kind": "full" | "short-prefix" | null,
  "log_message": "workspace_drift_check: ...",
  "halt_message": "<multi-line user-facing message>" | null
}
```

Bind `{workspace_drift_status}` ← `status` and `{head_short_sha}` ← `head_short_sha` in workflow context, and `{pinned_short_sha}` ← the first 7 characters of `metadata.source_commit`. Only `overridden` (`--allow-workspace-drift` was passed and HEAD is not the pinned commit) changes what later steps do: nothing read at HEAD says anything about the pinned commit, so update-skill takes no provenance line, signature, parameter list, return type or node kind from it. The drift gate below halts on every gap whose repair needs a line, signature, parameter list or return type from the tree, and on every rescope, whose stats recount would count the public API there. `ok` (HEAD holds the pinned commit, with or without the flag) and `skipped` change nothing: lines move and node kinds are looked up as usual.

**Dispatch on `status`:**

- **`ok` or `skipped`** (helper exit 0): log `log_message` and continue to §4.
- **`overridden`** (helper exit 0): log `log_message`, add `workspace_drift_overridden: HEAD {head_short_sha} is not pinned {pinned_short_sha}` to `warnings[]`, and surface the override in the final report: report.md §2's Mode row is where the report shows it, in the one text that section gives. Then run the drift gate below, and continue to §4 only when it passes. The override does not automatically re-pin `metadata.source_commit`; re-pinning is explicit user work (a normal-mode update records the commit it reads as `source_commit`; or re-create the skill).
- **`mismatch`** (helper exit 2): HALT immediately with status `halted-for-workspace-drift`. Display the helper's `halt_message` verbatim: it already substitutes `{pinned_commit}`, `{source_ref or "unset"}`, `{source_root}`, `{head_sha}`, and the suggested `git checkout` command. Do not proceed to §4. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "workspace HEAD {head_short_sha} is not the pinned commit {pinned_short_sha}"`.
- **Any other result** (the helper exits non-zero without a `mismatch` envelope, prints no JSON, or returns a status not listed above): HALT with status `blocked`, since the guard could not tell which commit the spot-checks would read. Show the helper's stderr. Do not proceed to §4. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "drift-check-failed: {what the helper printed, or no JSON}"`.

**Drift gate (only when `{workspace_drift_status}` is `overridden`).** Before §4, collect every manifest entry whose repair needs something read from the tree: under the override that tree is HEAD, not the pinned commit, and update-skill writes nothing read there, neither a provenance line nor a signature, parameter list, return type or node kind. Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the provenance map holds the export: merge Priority 4 replaces a modified export's content with a fresh extraction, merge Priority 5 appends a new export's content, and write.md §3 adds an entry for an export the map does not hold, and in gap-driven mode each of those could only be read from the tree. That includes a gap §4 bullet 2 would send to §4a with nothing to scan (a blocking severity as bullet 2 defines it, no `source_citation` and an empty `resolved_paths[]`): under the override this gate halts on it first. Every `DELETED_EXPORT` needs the tree as well: in gap-driven mode it is a rescope (rule R1), which narrows the brief's scope, and write.md §2 must then recount `exports_public_api` and `exports_internal` over the narrowed scope from the tree, while under the override it keeps the counts metadata.json records. A rule R5 `MOVED_EXPORT`, a `STRUCTURAL_FIX` (a split-body consistency finding among them) and a `metadata update` need nothing from the tree and pass. Look each export up in the provenance map as §4 bullet 2 does, and give each entry that needs the tree the first reason that fits:

- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);
- `a line from the tree (rule R3)`: a provenance-completeness gap (`provenance_completeness: true`), which §4 bullet 2 routes to §4a;
- `a line and a signature from the tree`: an export the lookup does not find in the map;
- `a signature from the tree`: an export the lookup finds in the map.

When no entry needs the tree, continue to §4. Otherwise HALT with status `halted-for-workspace-drift` before merge runs, so merge writes nothing and §4a never runs. A rescope's amendment is not in the skill brief yet (rule R1): step 4 §6b writes it, so this halt leaves the brief as it was, and a re-run asks again. Display, with `{source_commit}` and `{source_ref}` read from metadata.json:

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

Spot-check each gap's citation instead of re-extracting the files: confirm each export the report names is still at its recorded location.

1. Read the gap-derived manifest at `{run_dir}/change-manifest.json` (§1 wrote it), and look exports up in the provenance map at `{provenance_map_path}` (init.md §4); read both from disk, never from memory
2. **Partition by change category, then iterate the export-bearing entries.** Entries that do not name an export have no symbol to resolve against source, so they skip the per-export verification below:
   - **`STRUCTURAL_FIX`** (rule R2): forward verbatim to the merge step (its `remediation` text describes a generated-markdown edit). No spot-check, no provenance lookup, no `entries[]` change.
   - **`metadata update`** (rule R4): forward the metadata-patch payload to the merge step. No spot-check, no provenance lookup.

   Carry both through workflow context to merge.md unchanged. Then, for each export-bearing entry (`NEW_EXPORT`, `MODIFIED_EXPORT`, `MOVED_EXPORT`, `DELETED_EXPORT`):
   - **If the entry is `DELETED_EXPORT` (rescope, rule R1):** do not resolve against source: the export is being removed from the public surface. Record `verification: rescoped` and flag for merge Priority 1 (removal). Confirm the manifest entry carries the `rescope` object §1 rule R1 recorded (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path), which step 4 §6b writes to the brief; if it has none, HALT with status `blocked` (halt procedure: `phase: "re-extract:rescope"`, `reason: "rescope-without-amendment: {name}"`): a rescope without a brief scope amendment is denominator deflation and must not be written.
   - **If the entry is `MOVED_EXPORT` (a provenance line that is not the export's definition, rule R5):** run only the spot-check below, for an export the provenance map holds. Look it up by its `source_citation`, not by name alone: take the entry whose `source_file:source_line` equals the citation, since two entries can share an `export_name` in different files. The public-reachability gate is not run for it, and it is never routed to §4a. Record in `pinned_definition_lines` the definition lines its `remediation` lists (test-skill read them at the commit its report pinned), for write.md §3's WARNs. Under the drift override (`{workspace_drift_status}` is `overridden`) its spot-check moves no line: it records `unknown` with `unknown_reason: drift-override` where it would record `moved`, and sets no `new_location`. When the export is not in the provenance map, record `unknown`, even when the entry has a `source_citation`: there is no entry to move, it is never flagged `NEW_EXPORT`, and write.md §3 adds no entry for it.
   - Look up the export in the provenance map's `entries[]`: take the entries whose `export_name` equals the name. **With a `source_citation`,** keep those whose `source_file`, normalized as write.md §6 normalizes a path (a leading `./` dropped, backslashes turned to `/`), equals the citation's file normalized the same way. One left: the export is found. Several left: take the one whose `source_line` equals the citation's line, or else record `unknown` and leave them as they are. None left: take the "not found" branch below. **Without a `source_citation`,** exactly one entry means the export is found; several record `unknown` and stay as they are (a spot-check of the wrong one would move another export's line); none takes the "not found" branch. Read the found entry's `source_file` and `source_line`.
   - **If export not found in provenance map:**
     - **If the manifest entry has a `source_citation` (§1 bullet 3 carried it over from the test report) and is not a `MOVED_EXPORT`:** run the "export found" branch's `definition-lines` call on the file and line that citation names (`--file` and `--line` from the citation, no `--export-type`), and record a full `verified` / `moved` entry with the citation's line as the recorded line: the same spot-check logic as the "export found" branch below, keyed on the manifest-supplied citation instead of the provenance map. The export is still flagged `NEW_EXPORT` for the merge step; this branch only upgrades the provenance entry from `unknown` to a live spot-check result, so write.md §3 adds a full entry at the line it pins (its bullet for a cited export the map does not hold, labeled `source-read` and `T1-low` because the spot-check finds lines by the verifier's text rules, not by an ast-grep recipe) instead of writing `null`. When that spot-check gives `unknown` or `missing`, the citation pins no line: go on to the branches below as if the entry had no `source_citation`.
     - **If the entry is a provenance-completeness gap (rule R3: documented in SKILL.md/`references/` but missing from the provenance-map) AND `source_root` is pinned and readable:** route this entry to §4a (Targeted Re-Extraction Branch) **regardless of severity**. These exports are documented-and-known; `unknown` is never the correct outcome for them. §4a resolves them against pinned source and records a full `re-extracted` provenance entry. This route takes precedence over the severity-gated branches below.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line) and a blocking `severity` (§1 bullet 3), and the rule R3 branch above did not take it:** route this entry to §4a (Targeted Re-Extraction Branch), whatever its `resolved_paths[]`. With a non-empty list, §4a scans those files with the tier-appropriate extractor and, on success, records a full verification record with `verification: re-extracted`, a live `provenance_citation`, and full signature/params/return-type fields for the merge step to consume as a NEW_EXPORT. With an empty list it has nothing to scan and lists the entry in `unresolved[]` with `files_scanned: 0`. Either way an entry §4a cannot resolve halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included: a blocking gap never degrades to `unknown`. See §4a for the procedure, the consolidated halt protocol, and the output record shape.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line), the branches above did not take it, and it asks to document a missing export or type** (its `category` is `missing-export` or `missing-type`): route it to §4a when its `resolved_paths[]` is not empty, whatever its severity. The route follows the gap's category, not its severity: test-skill rates a missing export `Medium`, and targeted re-extraction is how gap-driven repair gives it provenance. When §4a finds the export in none of those files, or there are none, record it `unknown` as the bullet below does: its severity is `Medium`, `Low` or `Info`, so it does not halt.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line), is not a provenance-completeness gap, and its `severity` is `Medium`, `Low` or `Info`:** record as new (`provenance_citation: unknown`): no spot-check possible; flag for merge step to handle as `NEW_EXPORT`. write.md §3 (step 5) accepts null `source_file` / `source_line` only for these; a blocking gap never gets here, whatever its `resolved_paths[]`, since the blocking-severity bullet above sends it to §4a.
   - **If export found:** ask `{verifyProvenanceCompletenessHelper}` (resolve it ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`) for the lines of its `source_file` that define the export, by the rules write.md §6's verifier applies after the write. From `{project-root}`, run:

     ```bash
     uv run {verifyProvenanceCompletenessHelper} definition-lines \
         --source-root "{source_root}" \
         --file "{source_file}" --name "{export_name}" --line {source_line} \
         [--export-type "{export_type}"]
     ```

     Pass `--export-type` when the entry records one. Take the definition lines from its output, never by eye: read its `line_check`. `checked` gives `line_is_definition` and `definition_lines`, which the outcome below reads; `file-missing` means the recorded file no longer exists; `skipped-export-type` means a `module` or `package` entry, which has no definition line and is `verified` while its file exists; `skipped-language` means the rules cover no such file: read the file and take the line that declares the export itself, never a decorator or comment above it. Record `unknown` for an entry whose call exits 2 or prints no JSON. When no candidate resolves, record `unknown` for every entry and add `provenance: spot-checks not run: skf-verify-provenance-completeness.py is missing; re-install SKF` to `warnings[]`.
   - Record verification outcome: `verified` (the recorded `source_line` is itself one of those definition lines, `line_is_definition` true), `moved` (the file defines the export on exactly one line, and not the recorded one: `definition_lines` holds that one line; record it as `new_location`), `missing` (the recorded file no longer exists: `line_check` is `file-missing`), `re-extracted` (resolved via §4a from `resolved_paths[]` or rule R3), `rescoped` (DELETED_EXPORT, flagged for removal), or `unknown` (no usable provenance data; or the file defines the export on several lines, none of them the recorded one, or on no line the rules recognize (an empty `definition_lines`), which may be a shape they do not cover: never call it gone. Leave it for a person, since write.md §3 leaves such an entry unchanged)
   - **Public-reachability gate (`NEW_EXPORT` only):** before an entry is flagged `NEW_EXPORT` for the merge step, confirm the symbol is reachable as **public API**, not merely that a `pub` / `export` / top-level definition exists at the citation. Read `source_file` and resolve the symbol's module path, and confirm at least one of: (a) it is re-exported from the package entry-point barrel (`lib.rs` `pub use`, `index.ts` / `index.js` export, `__init__.py` import or `__all__`), or (b) every ancestor module on the path from that barrel is public (Rust `pub mod`, an exported TS namespace, a non-underscore Python package). A `pub(crate)` / `pub(super)` item, or one under a private module (e.g. `mod authority;` declared without `pub`), is **not** reachable. **On failure:** do not document it as public: drop it from the export-bearing set so it is never written to the documented `exports[]` array or SKILL.md, and re-queue it as a `metadata update` (rule R4) recording `reclassified: internal-unreachable` for the evidence report. Do **not** hand-set any `stats` count: write.md §2's automatic recount derives `exports_internal` / `exports_total` from the merged surface and owns those fields. This honors the workflow rule that documented API must be importable by users, since a `pub`-but-internal symbol would otherwise inflate the documented public surface with a type users cannot import.
3. Write the gap-driven records to `{run_dir}/reextract-records.json`, before §5 sends the run on: merge reads them, and step 5's `apply` writes the provenance map from them. One verification record per export-bearing entry, and the per-file extractions §4a produced:

   ```bash
   cat > "{run_dir}/reextract-records.json" <<'SKF_JSON'
   {
     "mode": "gap-driven",
     "files_extracted": <count, non-zero only when §4a scanned resolved_paths[]>,
     "exports_extracted": <gap_count>,
     "confidence_breakdown": {
       "T1": <entries whose extraction_method is ast-grep (or ast_bridge)>,
       "T1-low": <entries whose extraction_method is source-read (or source_reading), and each cited export not in the map that the spot-check pinned and the public-reachability gate passed, which write.md §3 writes as source-read>,
       "unlabeled": <entries whose extraction_method is unknown or missing, such as direct-read, other than a pinned cited export that passed the reachability gate (counted under T1-low); write.md §2 relabels them>,
       "T2": 0
     },
     "verification": [
       {"export_name": "<name>", "gap_category": "<NEW_EXPORT|MODIFIED_EXPORT|MOVED_EXPORT|DELETED_EXPORT|metadata_update>",
        "severity": "<the entry's severity, or null>",
        "verification": "<verified|moved|missing|unknown|re-extracted|rescoped>",
        "in_map": <true when the provenance map holds an entry of this name>,
        "map_entry": <{"source_file": "<file>", "source_line": <line>} of the one entry the lookup took, or null>,
        "provenance_citation": "<source_file>:<source_line>",
        "source_citation": <the entry's {"file", "line"}, or null>,
        "new_location": "<source_file>:<new_line>, set when moved OR re-extracted, else null",
        "unknown_reason": "<drift-override, set only when the drift override (§3) made the outcome unknown, else null>",
        "pinned_definition_lines": <MOVED_EXPORT (rule R5) only: the definition lines its test-report remediation lists, read at the commit the test report pinned; else null>,
        "resolution_source": "<remediation-paths, set only when verification is re-extracted, else null>",
        "reachability": "<public or internal-unreachable, from the public-reachability gate (NEW_EXPORT only), else null>",
        "export_type": "<the node the spot-check read at that line, for a cited export the map does not hold, else null>"}
     ],
     "files": [
       {"file_path": "<file>", "exports": [
         {"name": "<export_name>", "type": "<function|class|type|constant>", "signature": "<full signature>",
          "location": "<file>:<start_line>-<end_line>", "confidence": "<T1 for an ast-grep match, T1-low for an export read by eye>",
          "extraction_method": "<ast-grep|source-read>", "ast_node_type": "<the kind the matching ast-grep recipe declares, or null>",
          "ast_recipe": "<id of the recipe that matched, or the find_code pattern, or null>",
          "params": ["<name: type>"], "return_type": "<type>", "docstring": "<summary>"}]}
     ]
   }
   SKF_JSON
   ```

   `files` holds only §4a's `re-extracted` records (`[]` when §4a ran on nothing).
4. Set `no_reextraction: true` in workflow context: step 5 will use this flag to skip stale `source_file`/`source_line`/`confidence` field updates for `verified` exports, except the label relabel write.md §2 applies when its stats helper flags an entry whose labels disagree with its `extraction_method`. `moved` exports get updated citations; a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` entry at that line; `re-extracted` exports get full fresh provenance from §4a's extraction records (see step 5 §3). The flag is a global gap-driven marker, not a per-entry one: step 5 dispatches on each verification outcome independently.
5. Go on to §5. §4a below runs only where bullet 2 calls it.

### 4a. Targeted Re-Extraction Branch (Helper, Called from §4 Bullet 2)

**Do not execute this section sequentially.** It is a helper procedure §4 bullet 2 invokes when specific conditions are met (see below). A run in which §4 bullet 2 routes no entry here skips this section entirely.

**Used by:** §4 bullet 2, in one of three cases:

- a manifest entry for an export the provenance map does not hold, with no `source_citation` (or one whose spot-check pinned no line) and a blocking `severity` (§1 bullet 3), that the rule R3 case below does not take, whatever its `resolved_paths[]`: a non-empty list is the path set to scan, and an empty one leaves nothing to scan, so item 4 puts the entry straight into `unresolved[]` with `files_scanned: 0`; **or**
- such an entry with a `Medium`, `Low` or `Info` severity that §4 bullet 2 routes here by its `category` (a missing export or type): its `resolved_paths[]` is the path set to scan; **or**
- a provenance-completeness gap (rule R3: documented but missing from the provenance-map), routed here **regardless of severity** as long as `source_root` is pinned and readable. Its `resolved_paths[]` is the path set to scan: §1 filled them from the source file its documentation cites when its remediation named none.

**Purpose:** produce AST-backed provenance for a gap with a blocking `severity` (§1 bullet 3) and no citation that pins a line, so step 5 §3 never writes `source_file: null` for a blocking finding. Honors the workflow-level rule **Never hallucinate** (every statement must have AST provenance) against the most common gap-driven trigger: a failing test report whose Gap Report `Source:` field is a region reference (e.g., `@storybook/addon-docs control primitives`) rather than a `file:line` pair.

**Procedure:**

1. **Source access:** read the files under `{source_root}`, the tree §3 confirmed holds the pinned commit, never through the gh contents API, zread or deepwiki, which may serve another commit.
2. **The file set** is the `resolved_paths[]` of every entry routed here, as they are: §1's `{parseGapsHelper}` resolved them under `{source_root}` and refused, into `rejected_paths[]`, every path that leaves it (`outside-root`, or `symlink-outside-root` through a link) or names no file (`not-found`, `no-match`). Remediation text is user-editable: never scan a refused path, and never expand or check a path by hand.
3. **Extract:** read the file set with the tier-appropriate extractor and label each export by the tool that produced it, at any tier: an export an ast-grep rule matched is T1 (`extraction_method: ast-grep`), an export read by eye is T1-low (`extraction_method: source-read`). At Forge tier and above, write the file set as a JSON array to `{run_dir}/remediation-files.json` and run the recipe runner over it (resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`), from `{project-root}`:

   ```bash
   uv run {extractPublicApiHelper} --mode full \
       --source-root "{source_root}" \
       --files-from "{run_dir}/remediation-files.json" \
       [--scope-type "{scope_type}"] \
       --head-cap 0 \
       -o "{run_dir}/remediation-exports.json"
   ```

   Pass `--scope-type` when step 1 read a `scope_type` from metadata.json, so a component library runs its recipe set. It takes no `--brief`: a test report can name a file the brief's scope leaves out as an export's home, and the runner would skip it. On exit 1 (`incomplete`) run it once more; on exit 2 or 3, no JSON, or no candidate resolves, or at Quick tier, read the files by eye (by text pattern). Read by eye only what the recipes leave out: an export a file defines in a form Known Limitation #11 in `{extractionPatternsData}` lists, a file `file_issues[]` names and a name `entry_point_diff.extraction_gaps[]` lists. Launch subprocesses in parallel (Pattern 4) when available; sequential fallback otherwise. Follow the tier-degradation rules in `{tierDegradationRulesData}` when AST tools fail on individual files.
4. **Match by name**: for each manifest entry routed here with a path set to scan, search the extraction results of its own `resolved_paths[]` for an export whose `name` matches the manifest entry's `name`. An entry with no path set to scan (an empty `resolved_paths[]`) is not matched: it goes straight to `unresolved[]` with `files_scanned: 0`. Record the first hit as:
   - `verification: re-extracted`
   - `provenance_citation: {file}:{start_line}` from the AST result
   - `new_location: {file}:{start_line}` (the same value, for the consumers that read `new_location`)
   - `resolution_source: remediation-paths`
   - `confidence: T1`, `extraction_method: ast-grep`, `ast_node_type` set to the `kind` the matching recipe declares and `ast_recipe` naming that recipe when an ast-grep rule matched the export, or `confidence: T1-low`, `extraction_method: source-read`, `ast_node_type: null` and `ast_recipe: null` when it was read by eye
   - the full extraction signature (type, params, return_type, docstring), in the shape of a `files` record of §4 bullet 3, so step 4 Priority 5 merges it as it merges a normal run's extraction.

   Then apply the §4 bullet 2 **public-reachability gate** to each matched symbol before recording it as a NEW_EXPORT: this section has full source access, so resolve the symbol's module path and confirm barrel re-export or a fully-`pub` module chain. If it is unreachable (`pub(crate)` / private module), do **not** record `re-extracted`: drop it from the export-bearing set and re-queue the entry as a `metadata update` (rule R4, `reclassified: internal-unreachable`), exactly as the gate specifies. A re-extracted symbol that is not public API is not a documentable NEW_EXPORT. This is a resolution, not an `unresolved[]` failure (item 5): the symbol was found, just not public, so it does not trigger item 5's HALT.
5. **Track failures across all qualifying entries.** Collect every entry whose symbol was not found in any file of its path set, and every entry item 4 had nothing to scan for (`files_scanned: 0`), into an `unresolved[]` list, except a `Medium`, `Low` or `Info` missing export or type (the second case of **Used by**): record that one `unknown`, as §4 bullet 2's `unknown` branch does. After processing every qualifying entry, if `unresolved[]` is non-empty: HALT with a consolidated report listing every unresolved entry (`name`, `severity`, `remediation_paths`, `rejected_paths`, `files_scanned`, `exports_found_in_scan`). Template:

   ```
   Targeted re-extraction failed for {N} gap(s).

   A blocking gap (any severity but Medium, Low or Info, a missing or
   unrecognized one included) must resolve to AST provenance. The Remediation
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

   Exit with status `halted-for-remediation-path`, under `--dry-run` too (the run stops here instead of exiting `dry-run`). Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:targeted-reextraction"`, `reason: "targeted re-extraction failed for {N} gap(s): {name} ({severity or no severity}), ..."`.

6. **Success summary:** append the record `targeted_reextraction: {resolved_count, files_scanned, exports_matched, tier}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `targeted_reextraction`, and each matched record in the `files` of §4 bullet 3's `{run_dir}/reextract-records.json`. The evidence report (step 5 §4) surfaces this alongside the verified / moved / missing tally.

**Why halt instead of degrading to `unknown`:** a null citation on a blocking gap lets the skill pass re-test while it still hides the broken behavior behind a placeholder.

### 5. Display the Repair Summary and Route

Display the summary below:

"**Gap-driven re-extraction.** Verified {verified_count}/{gap_count} citations against live source. Moved: {moved_count}. Missing: {missing_count}. Re-extracted (via remediation paths or provenance-completeness, §4a): {re_extracted_count}. Rescoped (removed from surface): {rescoped_count}. Unknown (not in provenance map, a `Medium`, `Low` or `Info` gap §4a found nothing for, no single definition line, or a line the drift override kept from being moved): {unknown_count}."

When `{workspace_drift_status}` is `overridden`, add: "Every check read HEAD {head_short_sha}, not pinned {pinned_short_sha}: no line was moved or pinned."

This step auto-proceeds: no user choices. Load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode: skipping merge and write.** Loading report..." and load `{reportFile}` (report.md, NOT `{resumeStepFile}`); it emits status `dry-run` describing what merge and write would have done, so a gap-driven `--dry-run` writes nothing. A halt in §3 or §4a (the drift gate, the targeted re-extraction) stops a `--dry-run` as it stops any other run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{resumeStepFile}` (merge.md) to begin the merge operation.
