---
# `{nextStepFile}` is where a repair goes on, step 4 (§5 loads it).
# `{reportFile}` takes a detect-only run, a run with no gap to repair (§2)
# and a dry run (§5).
nextStepFile: 'merge.md'
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
# `{extractPublicApiHelper}`: §4a's recipe runner. If neither exists, read
# the files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# `{buildChangeManifestHelper}`: §4's `gap-records` and §4a's `records`.
# HALT if neither exists.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
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

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Translate the Test Report's Gaps

Read the gaps of the test report at `{test_report_path}` and translate them into the change manifest (the source has not changed, so no file is compared):

1. **Read the gaps through `{parseGapsHelper}`** (resolve it ← first existing path in `{parseGapsProbeOrder}`). From `{project-root}`, run:

   ```bash
   uv run {parseGapsHelper} parse \
       --report "{test_report_path}" \
       [--source-root "{source_root}"] \
       --provenance-map "{provenance_map_path}" \
       > "{run_dir}/gaps.json"
   ```

   Pass `--source-root` unless the skill is docs-only (there is no source tree). It reads the gap ledger test-skill wrote beside the report (`test-findings-<the report's run id>.json`), which holds every gap of a run test-skill's hard gate blocked (its `stepsCompleted` ends at `hard-gate`), and for a report older than the ledger the report's `## Gap Report`. Never read gaps from the report by eye. `--provenance-map` (init.md §4 halts a repair that has none) gives each gap that names an `export` its `map_match`, the map entry §4 spot-checks, keyed on the gap's `source_citation`.

   - **Exit 0:** bullet 3 reads `{run_dir}/gaps.json` and passes each of its `warnings[]` on as `test-report: <entry>`.
   - **Exit 1** (`status: "error"` in `{run_dir}/gaps.json`, with `code` `REPORT_MISSING`, `LEDGER_MISSING`, `LEDGER_INVALID` or `INVALID_INPUT`), **any other exit, no JSON, or no candidate resolves:** HALT with status `blocked` and display "**The test report's gaps could not be read:** {code}: {error}" ("skf-parse-gaps.py is missing; re-install SKF" when no candidate resolved). The halt procedure takes `phase: "detect-changes:parse-gaps"`, `path: "{test_report_path}"`, `reason: "{code}: {error}"`.

2. **Translate each gap by its `category`** (the gap ledger's closed set of slugs), never by its severity: bullet 3's helper routes each one through the table below. A report older than the ledger gives no `category`: when bullet 3 asks, choose the row whose gap type its title and issue describe, or the Not routed slug that names it.

| `category` | Gap type (a report older than the ledger) | Change Category |
|------------|-------------------------------------------|-----------------|
| `missing-export`, `missing-type` | Missing export, type or interface documentation | NEW_EXPORT (an undocumented public export or type), unless the remediation says the export is internal or out of scope: then DELETED_EXPORT (rescope), see rule R1 |
| `split-body-mismatch` | Split-body inconsistency: the SKILL.md body and a `references/*.md` file document one export differently, with a `Source:` inside the skill package | STRUCTURAL_FIX, see rule R2 (for an older report, this row takes precedence over the Signature mismatch row below) |
| `signature-mismatch`, `fabricated-signature` | Signature mismatch | MODIFIED_EXPORT (the documentation needs updating from source) |
| `structural`, `broken-reference`, `inaccurate-reference`, `reference-escape`, `integration-pattern`, `migration-section`, `scripts-assets` | Structural or coherence drift in the output files only, no source change | STRUCTURAL_FIX, see rule R2 |
| `provenance-completeness` | Export documented in SKILL.md/references but **missing from the provenance-map** | NEW_EXPORT (provenance-completeness), see rule R3 |
| `provenance-line` | Provenance line is not the export's definition | MOVED_EXPORT (provenance line), see rule R5 |
| `metadata` | Missing metadata or examples | metadata update, see rule R4 |
| any other | any other gap | not routed |

**Not routed:** update-skill has no repair for the other categories. Such a gap takes no manifest entry, so this run writes nothing for it: no provenance entry, no `exports[]` name and no documentation removed. Bullet 3's helper lists it with the reason below, which says who repairs it. A gap with no category, or one no table holds, takes "update-skill has no repair for this category, so a person follows the gap's remediation", and one whose export is answered null "it names no export for update-skill to repair, so a person follows the gap's remediation".

- `stale-documentation` (the skill documents a name the source's enumerated surface lacks and that is not a documented extra, an Info `observation`): the source has no line to repair the name from, so a person removes its documentation when the name is gone from the source, fixes the brief's scope when the surface missed it, or, when the source still declares the name, keeps the documentation and re-runs Test Skill at a tier that classifies it.
- `metadata-drift` (divergent export counts in the metadata): update-skill recounts `stats.exports_public_api`, `stats.exports_documented` and `stats.effective_denominator` each time it writes metadata.json, so a metadata patch to them does not hold (under `--allow-workspace-drift` and for a docs-only skill it keeps the recorded public API counts and `stats.effective_denominator` instead); Create Skill rebuilds diverging barrel counts from the source and recounts a `stats.effective_denominator` the brief's `scope.tier_a_include` set disagrees with (denominator drift), a person fixes denominator deflation on a brief with no tier A list by adding `scope.tier_a_include` to it, and documented-surface counts that differ by the `Type::method` entries the named-export count leaves out need no fix.
- `provenance-unverified`: the line-check rules could not verify the line, so a person checks by hand that it defines the export and, when another line does, sets its provenance `source_line` to that line.
- `denominator-inflation`: it concerns the brief's scope and the count design, which a person decides in the skill brief, as the gap's remediation says.
- `brief-scope-stale`: a person edits the brief's scope globs by hand so each matches the files it meant, since update-skill does not rewrite them.
- `multi-denominator`: no fix is needed, since the barrel and the documented surface measure different sets by design and the report records both counts.
- `numerator-inflation`: a person documents the absent exports in SKILL.md or references/, reading each from the source.
- `scripts-assets-provenance`: a person adds the file's row to the provenance map's `file_entries`, or removes the file from the skill.
- `observation`: a person applies it only when they agree, since it is advisory, and a documented extra needs no change.
- `discovery`: a person improves the skill's description so realistic prompts route to it, or runs the discovery test Test Skill skipped.
- `description`: a person edits the description in the SKILL.md frontmatter as the gap suggests.
- `external-validator`: a person applies the skill-check diagnostic or Tessl Review suggestion to SKILL.md.

**Translation rules (referenced by the table above):**

- **R1: DELETED_EXPORT (rescope).** A coverage gap is a rescope only when its remediation text names removal (`rescope`, `remove from surface`, `out of scope`) or the export is upstream `#[doc(hidden)]` / internal. Default a `missing-export` or `missing-type` gap to NEW_EXPORT (document it); choose rescope only on that explicit signal. Bullet 3 asks `rescope` for each `missing-export` or `missing-type` gap whose remediation a person or a model wrote (any text but the one test-skill's gap ledger generates for it, which names no removal): answer it by this rule, `false` when the item's `remediation` and `issue` give no such signal, and answer a gap it does not ask about only when you found its export upstream `#[doc(hidden)]` or internal (bullet 3's `written`). **Interactive:** prompt per qualifying gap: "[D] Document the export / [R] Rescope (remove from the public surface)", and answer `rescope: true` for [R]. **GATE [default: D]**: headless answers `false` (**document**, NEW_EXPORT); `true` only when the remediation explicitly says removal *and* the export is internal/`#[doc(hidden)]`. Headless, record one decision for each `rescope` you answer, from `{project-root}`:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
  {"gate": "gap-driven.rescope", "default_action": "D", "taken_action": "<D for false, R for true>", "reason": "headless: <the rule R1 test applied>", "evidence": {"gap_id": "<gap_id>", "export": "<name>", "remediation": "<its text>"}}
  SKF_JSON
  ```

  A rescope is honest only if the reduction is expressed in the brief's scope: on `true`, bullet 3's helper will give the manifest entry a `rescope` object holding the `scope.amendments[]` entry (`category: "scope-expansion"`, `action: "excluded"`, `path`, `reason` (the remediation), `date`, `workflow: "skf-update-skill"`) **and** the export's source path for `brief.scope.exclude`, then route the entry to merge Priority 1 (removal) so steps 4 and 5 remove it and recompute stats from the amended scope. This step writes neither to the brief: step 4 §6b writes both, the first write of the repair, and skips an amendment or an exclude path the brief already holds, so a re-run never adds them twice and a run that stops before step 4 (a halt, `--dry-run`, `--detect-only`) leaves the brief as it was. In those read-only modes its `--read-only` adds `proposed-amendment: excluded {path} (scope-expansion); not written: {--dry-run or --detect-only}` to its `warnings[]`. Never close a coverage gap by editing `metadata.stats` to equal the documented count: that is denominator deflation and `skf-test-skill` will reject it.
- **R2: STRUCTURAL_FIX.** A finding whose fix edits the generated markdown only, with no source change and no provenance entry change. It carries `remediation` text describing the surgical markdown edit and routes to merge Priority 8 (generated-markdown edit only); it never adds, modifies, or removes a provenance `entries[]` row. Two kinds of finding qualify:
  - a coherence finding from `skf-scan-skill-md-structure.py` (e.g., `table_drift`, `unbalanced_fences`, a broken intra-skill anchor) that touches the generated output file only;
  - a split-body consistency finding (test-skill coverage-check §1b `cross_check_mismatches`): the SKILL.md body and a `references/*.md` file document one export differently. test-skill rates it High, as it rates a signature mismatch against the source, yet it needs nothing from the source: its `Source:` names the side the pinned source contradicts (test-skill coverage-check §5b), which bullet 3's helper keeps as the entry's `package_citation` when the ledger recorded its category, and merge Priority 8 says which file it edits. Its `category` is `split-body-mismatch`; in a report older than the ledger, recognize it by its `Source:`, which points inside the skill package (at the skill's own `SKILL.md` or at one of its `references/*.md` files, whether the path is written relative to the package or through `{skill_package}`), while its issue sets the SKILL.md body against a `references/*.md` file. Test for it before the High "Signature mismatch" row: a High signature gap whose `Source:` points into the source tree, or that has no `Source:`, stays `MODIFIED_EXPORT`.
- **R3: provenance-completeness.** An export documented in SKILL.md/`references/` but absent from the provenance-map. These are documented-and-known, so `unknown` is never correct: route to §4a's targeted re-extraction **regardless of severity**, gated only on `source_root` being pinned and readable (§4). One exception: when the map holds the name at another file than the gap cites (`map_match` `not-found` with a candidate that has a `source_file`), its provenance is not absent, so §4 records it `unknown` (`cited-elsewhere`) and never re-extracts it (§4 bullet 1). The other: no file it cites or its Remediation names that the skill brief's scope leaves out is read for it, so when no file the scope takes holds it, §4 records it `unknown` (`outside-scope`, §4 bullet 1).
- **R4: metadata update.** A `metadata` gap's patch: it changes no export's source and sets a field write.md §2's `metadata` call keeps (e.g., missing optional metadata), never a count that call recounts or `exports[]`, which is why a `metadata-drift` gap is not routed. Add no `effective_denominator_*` stats key: the recount drops each one when the denominator changes. Routes to merge Priority 8b and is applied by write.md §2 *before* the automatic stat recount (see merge.md §3 / write.md §2).
- **R5: MOVED_EXPORT (provenance line).** A `provenance-line` gap (in a report older than the ledger, a Low gap titled `Provenance line is not the definition of {export_name}`, test-skill coverage-check §4c) says the provenance map's `source_line` for that export is not the line that defines it. Its `Source:` is the map's `{source_file}:{source_line}`, so `source_citation` is set, and its remediation lists the file's definition lines. This row takes precedence over the Low `metadata update` row (R4). Route the entry to §4's spot-check only, with no public-reachability gate and no §4a.

3. **Build the change manifest through `{parseGapsHelper}`**, never by hand. From `{project-root}`, run:

   ```bash
   uv run {parseGapsHelper} translate \
       --gaps "{run_dir}/gaps.json" \
       --provenance-map "{provenance_map_path}" \
       [--judgments "{run_dir}/gap-judgments.json"] \
       [--read-only {dry-run|detect-only}] \
       -o "{run_dir}/change-manifest.json"
   ```

   Pass `--judgments` once the file exists, and `--read-only` with the run's flag in a `--detect-only` or `--dry-run` run. It routes each gap by the table and rules R1 to R5 and writes `{run_dir}/change-manifest.json`, where §4, merge and step 5 read it, as `{"mode": "gap-driven", "entries": [...]}`, each entry with the fields the "Translate" section of its docstring lists: §4 partitions on its `change_category` and merge.md §3 dispatches on it. Act on its `status`:

   - **`needs-judgment`** (it wrote nothing): for each `needs_judgment[]` item, judge from its gap's `title`, `issue` and `remediation`, which the item carries, add your answer to each of its `needs` to `{run_dir}/gap-judgments.json` under the item's `gap_id` (`{"<gap_id>": {"<need>": <answer>}}`), then run it again:
     - `category` (a report older than the ledger): the slug of the row bullet 2 says the gap's title and issue describe (`missing-export` or `missing-type` for a missing export or type), else the Not routed slug that names it (`stale-documentation` for documentation of a name the source surface lacks, `metadata-drift` for divergent export counts in the metadata), so the gap takes that category's reason, or null for a gap neither names;
     - `name`: the export the gap's title names, or null when it names none, which leaves the gap unrouted;
     - `rescope`: rule R1's answer, true or false;
     - `source_file`: the source file, relative to `{source_root}`, that defines the export (a rescope's exclude path) or that a rule R3 gap's documentation cites, or null.
   - **`written`:** set `gap_count` from its `gap_count`, keep its `not_routed[]` (the `id`, `title`, `category` and `reason` of each gap the table does not route, the reason saying why update-skill does not repair it and who does) for §2, and add each of its `warnings[]` to `warnings[]`: the parse's, as `test-report: <entry>`, `test-report: not routed: {id} ({category}): {reason}` for each gap not routed, and a read-only run's proposed amendments. When you answer `rescope` for a gap it did not ask about (rule R1: an export you found upstream internal or `#[doc(hidden)]`), add the answer to `{run_dir}/gap-judgments.json` and run it again before §2, taking that run's output in place of this one.
   - **Exit 1** (`status: "error"`) **or no JSON:** HALT with status `blocked` and display "**The test report's gaps could not be translated:** {code}: {error}". The halt procedure takes `phase: "detect-changes:parse-gaps"`, `path: "{test_report_path}"`, `reason: "{code}: {error}"`.

### 2. Display the Gap Summary and Route

Display "**Gap-driven update mode.** Translated {gap_count} test report findings into the change manifest; source drift detection skipped.", then list each gap §1 did not route, as `{id}: {title} ({category}): {reason}`, and say this run does not repair them. Then take the branch that applies:

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

**Drift gate (only when `{workspace_drift_status}` is `overridden`).** Run §4 bullet 1 now: with `--drift-status overridden` its plan checks this gate before any spot-check, and lists in `drift_blocked[]` every manifest entry whose repair needs something read from the tree: under the override that tree is HEAD, not the pinned commit, and update-skill writes nothing read there, neither a provenance line nor a signature, parameter list, return type or node kind. Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the provenance map holds the export: merge Priority 4 replaces a modified export's content with a fresh extraction, merge Priority 5 appends a new export's content, and write.md §3 adds an entry for an export the map does not hold, and in gap-driven mode each of those could only be read from the tree. That includes a gap §4 bullet 1 would send to §4a with nothing to scan (a blocking severity as bullet 1 defines it, no `source_citation` and an empty `resolved_paths[]`): under the override this gate halts on it first. Every `DELETED_EXPORT` needs the tree as well: in gap-driven mode it is a rescope (rule R1), which narrows the brief's scope, and write.md §2 must then recount `exports_public_api` and `exports_internal` over the narrowed scope from the tree, while under the override it keeps the counts metadata.json records. A rule R5 `MOVED_EXPORT`, a `STRUCTURAL_FIX` (a split-body consistency finding among them) and a `metadata update` need nothing from the tree and pass. So does, with `--brief`, a gap the brief's scope keeps from a repair before anything is read for it (§4 bullet 1 records it `outside-scope`, or `cited-elsewhere` with `citation_check` `outside-scope`, with no check run and nothing to scan). Each item gives its entry's `reason`, the first that fits, read from the entry's `map_match` (§1):

- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);
- `a line from the tree (rule R3)`: a provenance-completeness gap (`provenance_completeness: true`), which §4 bullet 1 routes to §4a;
- `a line and a signature from the tree`: an export whose `map_match` is `not-found` with no candidate that has a `source_file`;
- `a signature from the tree`: an export the map holds (`found` or `ambiguous`, or `not-found` with a candidate that has a `source_file`: a citation of another file than the map's entries of its name).

When its `status` is not `drift-blocked`, go on with its output in §4. Otherwise HALT with status `halted-for-workspace-drift` before merge runs, so merge writes nothing and §4a never runs. A rescope's amendment is not in the skill brief yet (rule R1): step 4 §6b writes it, so this halt leaves the brief as it was, and a re-run asks again. Display, with `{source_commit}` and `{source_ref}` read from metadata.json:

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

Spot-check each gap's citation instead of re-extracting the files: confirm each export the report names is still at its recorded location. Both calls below run `gap-records` (resolve `{buildChangeManifestHelper}` ← first existing path in `{buildChangeManifestProbeOrder}`) from `{project-root}`: it runs each spot-check with the definition-line rules write.md §6's verifier applies, routes each entry and writes the records, reading the gap-derived manifest §1 wrote from `{run_dir}/change-manifest.json` (each entry with its `map_match`), never from memory. The "Gap records" section of its docstring is the one statement of that routing and of each record's `verification` outcome: you answer what it asks and run the targeted re-extraction (§4a) it plans.

1. **Spot-check and route.** Run:

   ```bash
   uv run {buildChangeManifestHelper} gap-records --plan \
       --manifest "{run_dir}/change-manifest.json" \
       --provenance-map "{provenance_map_path}" \
       [--source-root "{source_root}"] \
       [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] \
       --drift-status "{workspace_drift_status}" \
       [--judgments "{run_dir}/gap-judgments.json"] \
       --files-out "{run_dir}/remediation-files.json"
   ```

   Pass `--source-root` unless the skill is docs-only, `--brief` when `{forge_data_folder}/{skill_name}/skill-brief.yaml` exists (a skill built without a brief, such as a quick skill, has no scope to keep to, so nothing is left out), and `--judgments` once the file exists. Act on its `status`:

   - **`drift-blocked`:** §3's drift gate halts.
   - **`blocked`** (`rescope_without_amendment[]`): a `DELETED_EXPORT` whose manifest entry carries no `rescope` object (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path, rule R1). HALT with status `blocked` (halt procedure: `phase: "re-extract:rescope"`, `reason: "rescope-without-amendment: {name}"`): a rescope without a brief scope amendment is denominator deflation and must not be written.
   - **`needs-judgment`:** each item is a spot-check whose `file` the definition-line rules cover no language of. Read the file and add, under the item's `gap_id` in `{run_dir}/gap-judgments.json`, its `declaring_line`: the line that declares the export itself, never a decorator or comment above it, or null when no line does. Then run it again.
   - **`planned`:** when `reextract.entries` or `reextract.signatures` is not empty, run §4a for them: the plan wrote their files to `{run_dir}/remediation-files.json`, each entry's `resolved_paths[]` and then the `file` of each export `reextract.signatures` lists (a `NEW_EXPORT` or `MODIFIED_EXPORT` its spot-check located, `verified` or `moved`, at the `line` it gives), whose signature bullet 2 takes from §4a's record of it there. A `NEW_EXPORT` whose `reachability` `{run_dir}/gap-judgments.json` does not answer yet is listed too, so its scan goes unused when bullet 2's gate finds it internal. Add none of its `warnings[]`: bullet 2's call prints them again.
   - **Exit 1 or no JSON:** HALT with status `blocked` (halt procedure: `phase: "re-extract:gap-records"`, its stderr as `reason`).

   A severity is blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or unrecognized one is blocking, like `Critical` and `High`. A blocking gap whose export the map does not hold must produce provenance read from the source or halt in this file before merge: for such an export, only a `Medium`, `Low` or `Info` gap may degrade to `unknown`. A `NEW_EXPORT` or `MODIFIED_EXPORT` whose export the map holds (its `map_match` is `found` or `ambiguous`, or `not-found` with a candidate that has a `source_file`: the gap cites another file than the map's entries of its name) never goes to §4a's targeted re-extraction (`reextract.entries`), whatever its severity: when the map holds several entries of its name (`ambiguous`, so nothing is checked), its spot-check at the entry ends `unknown` or `missing` (the entry's file is gone), or the check at a citation of another file pins no line (`unknown`, `cited-elsewhere`: that file's declaration may be another package's, so it is never re-extracted), its entry stays unchanged. Step 5's `apply` warns for it, naming the cause of an `unknown` (several map entries of its name, no definition line or several at the entry, a file no rule covers, a failed or skipped check, a citation of another file than the map's entries of its name). For a blocking gap the `provenance:` warning also names the gap and the one fix a re-run acts on: for several entries of its name, fix them by hand, or give the gap a `file:line` Source at the definition when that file holds only one of them, so the re-run's lookup takes that one; otherwise fix the entry by hand (set its `source_file` and `source_line` to the line that defines it), since the re-run checks the same entry again. Then re-run update-skill. For a `cited-elsewhere` gap, whatever its severity, the warning names the gap, the cited file and its check's cause (such as `missing` or `no-definition`), and where the map holds the name, and the fix for each side that may be wrong: when the map is right, re-run Test Skill, since the test compared another file's declaration, and if the gap comes back, exclude the cited file in the brief's scope when the skill does not cover it (not when the cited file is gone); when an export moved, fix that map entry by hand, then re-run update-skill. When its check read nothing at the cited file (no source tree, the verifier missing, a failed check), the warning says instead to give update-skill the source tree, re-install SKF, or fix what the check failed on, then re-run update-skill.

   With `--brief`, the brief's scope bounds the repair, by the in-scope test Category A applies (`scope.include` and `scope.exclude`, an exclude winning over an include): a cited file or a Remediation path the scope leaves out is never checked, scanned or repaired from, since the declaration there may be another package's, one the skill does not cover. This is the one exception to the rule above that a blocking gap whose export the map does not hold must produce provenance or halt: a gap the scope keeps from a repair ends `unknown`, whatever its severity, with no halt and nothing written for it, so a re-test raises it again. When the map holds the gap's name at another file and the scope leaves out the cited file, no check runs there: `unknown`, `cited-elsewhere`, with `citation_check` `outside-scope`. When the map does not hold the name, a gap whose files the scope all leaves out is never in the plan, and one whose files the scope takes hold no export of its name while it names a file the scope leaves out is not `unresolved`: either is `unknown`, `outside-scope`, its record's `outside_scope` listing the files left out. Step 5's `apply` adds no entry for an `outside-scope` gap, a placeholder included, and warns, naming the gap and the files left out, with the fix: when the skill covers that file, change the brief's scope so it takes it (its `scope.include` or `scope.exclude`), then re-run update-skill; otherwise re-run Test Skill, since the test compared a declaration the skill does not cover. When the gap cites a file the scope takes, the warning also names what its check there found (such as `missing` or `no-definition`), and when that check read nothing (no source tree, the verifier missing, a failed check) it gives that check's fix instead. For a `cited-elsewhere` gap whose cited file the scope leaves out, the warning gives no advice to exclude the cited file, since the scope already leaves it out, and when the export moved there it says to change the brief's scope so it takes that file (its `scope.include` or `scope.exclude`) and fix the map entry by hand. A file the scope takes is repaired from as before, so when the scope takes several packages that declare the name, check each gap's Source before the repair.
2. **Write the gap-driven records** to `{run_dir}/reextract-records.json`, before §5 sends the run on: merge reads them, and step 5's `apply` writes the provenance map from them. Run the same call without `--plan` and `--files-out`:

   ```bash
   uv run {buildChangeManifestHelper} gap-records \
       --manifest "{run_dir}/change-manifest.json" \
       --provenance-map "{provenance_map_path}" \
       [--source-root "{source_root}"] \
       [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] \
       --drift-status "{workspace_drift_status}" \
       [--judgments "{run_dir}/gap-judgments.json"] \
       [--remediation-records "{run_dir}/remediation-records.json"] \
       [--evidence "{run_dir}/evidence-records.jsonl" --tier "{forge_tier}"] \
       -o "{run_dir}/reextract-records.json"
   ```

   Pass `--brief` as bullet 1 does, and `--remediation-records`, `--evidence` and `--tier` when §4a ran. It writes one verification record per export-bearing entry, the confidence breakdown and counts, and in `files` each record of `{run_dir}/remediation-records.json` it matched by name, or by the public name the runner gives its local name in that file, to an entry §4a scanned for, within that entry's own `resolved_paths[]`, copied as `records` wrote it (one matched by that public name is copied under it, with its own name as `local`), and the record of each export `reextract.signatures` lists, whose `export_type`, `params`, `return_type`, `extraction_method` and `ast_node_type` it puts on that export's verification record, with a `provenance: ... signature not repaired` warning for one it finds no record of at its line: never type a record or count one by hand. The public-name match reads the runner's entry-point diff, so it holds at Forge tier and above: at Quick tier, or when §4a reads the files by eye after the runner exits 3, a gap that names a renamed re-export by its public name matches no record and is `unresolved` below. With `--evidence` it appends its `targeted_reextraction` record to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `targeted_reextraction`, which the evidence report (step 5 §4) shows beside the verified, moved and missing tally. Act on its `status`:

   - **`unresolved`:** an entry routed to §4a has no record of its name in its path set (nor one the runner re-exports under that name there), or had no path to scan (`files_scanned: 0`). A found export the public-reachability gate below finds internal is a resolution, not a failure. HALT with status `halted-for-remediation-path`, under `--dry-run` too (the run stops here instead of exiting `dry-run`), and display a consolidated report of every `unresolved[]` entry:

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

     Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:targeted-reextraction"`, `reason: "targeted re-extraction failed for {N} gap(s): {name} ({severity or no severity}), ..."`. **Why halt instead of degrading to `unknown`:** a null citation on a blocking gap lets the skill pass re-test while it still hides the broken behavior behind a placeholder.
   - **`needs-judgment`:** for each item, add your answer to each of its `needs` under its `gap_id` in `{run_dir}/gap-judgments.json`, then run it again:
     - **Public-reachability gate (`NEW_EXPORT` only):** `reachability`, for each `NEW_EXPORT` it located (`verified`, `moved` or `re-extracted`, at the item's `file` and `line`). Confirm the symbol is reachable as **public API**, not merely that a `pub` / `export` / top-level definition exists at the citation: resolve the symbol's module path, and confirm at least one of: (a) it is re-exported from the package entry-point barrel (`lib.rs` `pub use`, `index.ts` / `index.js` export, `__init__.py` import or `__all__`), or (b) every ancestor module on the path from that barrel is public (Rust `pub mod`, an exported TS namespace, a non-underscore Python package). A `pub(crate)` / `pub(super)` item, or one under a private module (e.g. `mod authority;` declared without `pub`), is **not** reachable. Answer `public`, or `internal-unreachable`: the helper then drops it from the export-bearing set, so it is never written to the documented `exports[]` array or SKILL.md, and lists it in `reclassified[]`. Do **not** hand-set any `stats` count: write.md §2's automatic recount derives `exports_internal` / `exports_total` from the merged surface and owns those fields. This honors the workflow rule that documented API must be importable by users, since a `pub`-but-internal symbol would otherwise inflate the documented public surface with a type users cannot import.
     - `docstring`, for each `re-extracted` export: the docstring at its line, or null when it has none. Its record in `files` takes it, so step 4 Priority 5 merges the record as it merges a normal run's extraction.
   - **`written`:** keep its `counts` for §5, and add its `warnings[]` to `warnings[]` (among them `provenance: spot-checks not run: skf-verify-provenance-completeness.py is missing; re-install SKF`, when every check recorded `unknown` for want of the verifier). Its `forwarded[]` entries (`STRUCTURAL_FIX`, rule R2, and `metadata update`, rule R4) go to merge as the manifest holds them, with no spot-check, no provenance lookup and no `entries[]` change; each export `reclassified[]` names goes to merge as a `metadata update` (rule R4) recording `reclassified: internal-unreachable` for the evidence report.
   - **Exit 1 or no JSON:** HALT with status `blocked` (halt procedure: `phase: "re-extract:gap-records"`, its stderr as `reason`).

   write.md §3 (step 5) accepts null `source_file` / `source_line` only for an `unknown` `Medium`, `Low` or `Info` gap the map does not hold, and leaves unchanged an entry whose definition lines the rules do not recognize, which may be a shape they do not cover: never call it gone.
3. Set `no_reextraction: true` in workflow context: step 5 will use this flag to skip stale `source_file`/`source_line`/`confidence` field updates for `verified` exports, except the label relabel write.md §2 applies when its stats helper flags an entry whose labels disagree with its `extraction_method`. `moved` exports get updated citations; a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` (`T1-low`) entry at that line, since the verifier's text rules found that line, not an ast-grep recipe; `re-extracted` exports get full fresh provenance from §4a's extraction records (see step 5 §3). The flag is a global gap-driven marker, not a per-entry one: step 5 dispatches on each verification outcome independently.
4. Go on to §5. §4a below runs only where bullet 1 calls it.

### 4a. Targeted Re-Extraction Branch (Helper, Called from §4 Bullet 1)

**Do not execute this section sequentially.** It is a helper procedure §4 bullet 1 invokes for the entries its plan lists in `reextract.entries` and `reextract.signatures`. A run in which §4 bullet 1 routes no entry here skips this section entirely.

**Used by:** §4 bullet 1's plan, for the entries it lists in `reextract.entries`: each scans its `resolved_paths[]` (an entry with none has nothing to scan), and §4 bullet 2 matches what this section extracts to each entry by name. For each export it lists in `reextract.signatures`, §4 bullet 2 takes the signature this section extracts at its `file` and `line`.

**Purpose:** produce AST-backed provenance for a gap with a blocking `severity` (§4 bullet 1) and no citation that pins a line, so step 5 §3 never writes `source_file: null` for a blocking finding. Honors the workflow-level rule **Never hallucinate** (every statement must have AST provenance) against the most common gap-driven trigger: a failing test report whose Gap Report `Source:` field is a region reference (e.g., `@storybook/addon-docs control primitives`) rather than a `file:line` pair. For an export a spot-check located, it reads the signature SKILL.md and the provenance map take, so neither keeps a stale one nor takes one from merge's prose.

**Procedure:**

1. **Source access:** read the files under `{source_root}`, the tree §3 confirmed holds the pinned commit, never through the gh contents API, zread or deepwiki, which may serve another commit.
2. **The file set** is `{run_dir}/remediation-files.json`, which §4 bullet 1's plan wrote: the `resolved_paths[]` of every entry routed here, as they are, less each one the brief's scope leaves out. §1's `{parseGapsHelper}` resolved them under `{source_root}` and refused, into `rejected_paths[]`, every path that leaves it (`outside-root`, or `symlink-outside-root` through a link) or names no file (`not-found`, `no-match`). The plan adds the `file` of each export `reextract.signatures` lists, where its spot-check located it under `{source_root}`; of a file only those exports bring, read by eye (item 3) only the exports they name. Remediation text is user-editable: never scan a refused path, and never expand or check a path by hand.
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

This step asks nothing after §1's rule R1 prompts. Load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode: skipping merge and write.** Loading report..." and load `{reportFile}` (report.md, NOT `{nextStepFile}`); it emits status `dry-run` describing what merge and write would have done, so a gap-driven `--dry-run` writes nothing. A halt in §3 or §4 (the drift gate, the targeted re-extraction) stops a `--dry-run` as it stops any other run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{nextStepFile}` (merge.md) to begin the merge operation.
