---
# `{nextStepFile}` is where a repair goes on, its spot-checks (§3 loads it).
# `{reportFile}` takes a detect-only run and a run with no gap to repair (§2).
nextStepFile: 'gap-spot-check.md'
reportFile: 'report.md'
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
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# The warnings and §1's gate decisions go to the run log through the first,
# and the halt procedure runs the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Gap-Driven Repair

## STEP GOAL:

Repair the gaps a test report found, at the commit the skill is pinned to. When `update_mode` is `gap-driven` (set in step 1 by `--from-test-report` or by load-baseline.md §4b's offer), load-baseline.md §8 loads this file, which with gap-spot-check.md stands in for steps 2a to 3: it translates the report's gaps into the change manifest and checks that `{source_root}` holds the pinned commit, and gap-spot-check.md spot-checks each gap's export there. The source has not drifted, so no file is compared.

## Rules

- Focus only on the gaps the report lists: merge nothing, and read no source file here: the source lines and files gap-spot-check.md §4 and §4a name are read there
- Write nothing outside `{run_dir}`, in any mode
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

The helpers below pass their JSON to gap-spot-check.md and steps 4 and 5 through `{run_dir}`, the run folder SKILL.md On Activation created.

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

   Pass `--source-root` unless the skill is docs-only (there is no source tree). It reads the gap ledger test-skill wrote beside the report (`test-findings-<the report's run id>.json`), which holds every gap of a run test-skill's hard gate blocked (its `stepsCompleted` ends at `hard-gate`), and for a report older than the ledger the report's `## Gap Report`. Never read gaps from the report by eye. `--provenance-map` (load-baseline.md §4 halts a repair that has none) gives each gap that names an `export` its `map_match`, the map entry gap-spot-check.md §4 spot-checks, keyed on the gap's `source_citation`.

   - **Exit 0:** bullet 3 reads `{run_dir}/gaps.json` and passes each of its `warnings[]` on as `test-report: <entry>`.
   - **Exit 1** (`status: "error"` in `{run_dir}/gaps.json`, with `code` `REPORT_MISSING`, `LEDGER_MISSING`, `LEDGER_INVALID` or `INVALID_INPUT`), **any other exit, no JSON, or no candidate resolves:** HALT with status `blocked` and display "**The test report's gaps could not be read:** {code}: {error}" ("skf-parse-gaps.py is missing; re-install SKF" when no candidate resolved). The halt procedure takes `phase: "detect-changes:parse-gaps"`, `path: "{test_report_path}"`, `reason: "{code}: {error}"`.

2. **Translate each gap by its `category`** (the gap ledger's closed set of slugs), never by its severity: bullet 3's helper routes each one through the table below. A report older than the ledger gives no `category`: when bullet 3 asks, choose the row whose gap type its title and issue describe, or the Not routed slug that names it.

| `category` | Gap type (a report older than the ledger) | Change Category |
|------------|-------------------------------------------|-----------------|
| `missing-export`, `missing-type` | Missing export, type or interface documentation | NEW_EXPORT (an undocumented public export or type), unless the remediation says the export is internal or out of scope: then DELETED_EXPORT (rescope), see rule R1 |
| `split-body-mismatch` | Split-body inconsistency: two files of the skill (the SKILL.md body or a `references/*.md` file) document one export differently, with a `Source:` inside the skill package | STRUCTURAL_FIX, see rule R2 (for an older report, this row takes precedence over the Signature mismatch row below) |
| `signature-mismatch`, `fabricated-signature` | Signature mismatch | MODIFIED_EXPORT (the documentation needs updating from source) |
| `structural`, `broken-reference`, `inaccurate-reference`, `reference-escape`, `integration-pattern`, `migration-section`, `scripts-assets` | Structural or coherence drift in the output files only, no source change | STRUCTURAL_FIX, see rule R2 |
| `provenance-completeness` | Export documented in SKILL.md/references but **missing from the provenance-map** | NEW_EXPORT (provenance-completeness), see rule R3 |
| `provenance-line` | Provenance line is not the export's definition, or its citation does not resolve | MOVED_EXPORT (provenance line), see rule R5 |
| `metadata` | Missing metadata or examples | metadata update, see rule R4 |
| any other | any other gap | not routed |

**Not routed:** update-skill has no repair for the other categories. Such a gap takes no manifest entry, so this run writes nothing for it: no provenance entry, no `exports[]` name and no documentation removed. Bullet 3's helper lists it with the reason below, which says who repairs it. A gap with no category, or one no table holds, takes "update-skill has no repair for this category, so a person follows the gap's remediation", one whose export is answered null "it names no export for update-skill to repair, so a person follows the gap's remediation", and a signature mismatch whose export is a method's form, `{owner}.{member}` (a dotted name no map entry has as its `export_name` or `reexported_as`), "it names a method's form, `{owner}.{member}`, not an export the provenance map holds, so a person corrects the method form the gap quotes to the signature its Source cites, then re-runs Test Skill": routed, it would write the method into the provenance map and metadata `exports[]`.

- `stale-documentation` (the skill documents a name the source's enumerated surface lacks and that is not a documented extra, an Info `observation`): the source has no line to repair the name from, so a person removes its documentation when the name is gone from the source, fixes the brief's scope when the surface missed it, or, when the source still declares the name, keeps the documentation and re-runs Test Skill at a tier that classifies it.
- `metadata-drift` (divergent export counts in the metadata): update-skill recounts `stats.exports_public_api`, `stats.exports_documented` and `stats.effective_denominator` each time it writes metadata.json, so a metadata patch to them does not hold (under `--allow-workspace-drift` and for a docs-only skill it keeps the recorded public API counts and `stats.effective_denominator` instead); Create Skill rebuilds diverging barrel counts from the source and recounts a `stats.effective_denominator` the brief's `scope.tier_a_include` set disagrees with (denominator drift), a person fixes denominator deflation on a brief with no tier A list by adding `scope.tier_a_include` to it, and documented-surface counts that differ by the `Type::method` entries the named-export count leaves out need no fix.
- `provenance-unverified`: the line-check rules could not verify the line, or the recorded line is not a number, so a person checks by hand which line defines the export and, when it is not the recorded one, sets its provenance `source_line` to that line; when the gap names an alias, no line of the cited file defines the export, so a person records the rename in its provenance entry (`export_name` the name the alias renames, `reexported_as` the export) only when no other entry has that `export_name` and the alias does not rename a default export, and otherwise cites the alias line, as the remediation says.
- `denominator-inflation`: it concerns the brief's scope and the count design, which a person decides in the skill brief, as the gap's remediation says.
- `brief-scope-stale`: a person edits the brief's scope globs by hand so each matches the files it meant, since update-skill does not rewrite them, and adds a `scope.include` glob for each restored file whose exports the skill documents (a `scope.exclude` one for each it leaves out), because a restored export stays only while an include glob matches no file.
- `multi-denominator`: no fix is needed, since the barrel and the documented surface measure different sets by design and the report records both counts.
- `numerator-inflation`: a person documents the absent exports in SKILL.md or references/, reading each from the source.
- `scripts-assets-provenance`: a person adds the file's row to the provenance map's `file_entries`, or removes the file from the skill.
- `observation` (`Annotation contradicted: {name}` included, which needs no skill edit: its remediation is an upstream report of the source's annotation): a person applies it only when they agree, since it is advisory, and a documented extra needs no change.
- `discovery`: a person improves the skill's description so realistic prompts route to it, or runs the discovery test Test Skill skipped.
- `description`: a person edits the description in the SKILL.md frontmatter as the gap suggests.
- `external-validator`: a person applies the skill-check diagnostic or Tessl Review suggestion to SKILL.md, or makes skill-check run again when the gap says it did not run.

**Translation rules (referenced by the table above):**

- **R1: DELETED_EXPORT (rescope).** A coverage gap is a rescope only when its remediation text names removal (`rescope`, `remove from surface`, `out of scope`) or the export is upstream `#[doc(hidden)]` / internal. Default a `missing-export` or `missing-type` gap to NEW_EXPORT (document it); choose rescope only on that explicit signal. Bullet 3 asks `rescope` for each `missing-export` or `missing-type` gap whose remediation a person or a model wrote (any text but the one test-skill's gap ledger generates for it, which names no removal): answer it by this rule, `false` when the item's `remediation` and `issue` give no such signal, and answer a gap it does not ask about only when you found its export upstream `#[doc(hidden)]` or internal (bullet 3's `written`). **Interactive:** prompt per qualifying gap: "[D] Document the export / [R] Rescope (remove from the public surface)", and answer `rescope: true` for [R]. **GATE [default: D]**: headless answers `false` (**document**, NEW_EXPORT); `true` only when the remediation explicitly says removal *and* the export is internal/`#[doc(hidden)]`. Headless, record one decision for each `rescope` you answer, from `{project-root}`:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
  {"gate": "gap-driven.rescope", "default_action": "D", "taken_action": "<D for false, R for true>", "reason": "headless: <the rule R1 test applied>", "evidence": {"gap_id": "<gap_id>", "export": "<name>", "remediation": "<its text>"}}
  SKF_JSON
  ```

  A rescope is honest only if the reduction is expressed in the brief's scope: on `true`, bullet 3's helper will give the manifest entry a `rescope` object holding the `scope.amendments[]` entry (`category: "scope-expansion"`, `action: "excluded"`, `path`, `reason` (the remediation), `date`, `workflow: "skf-update-skill"`) **and** the export's source path for `brief.scope.exclude`, then route the entry to merge Priority 1 (removal) so steps 4 and 5 remove it and recompute stats from the amended scope. This step writes neither to the brief: merge-write.md §6b writes both, the first write of the repair, and skips an amendment or an exclude path the brief already holds, so a re-run never adds them twice and a run that stops before step 4 (a halt, `--dry-run`, `--detect-only`) leaves the brief as it was. In those read-only modes its `--read-only` adds `proposed-amendment: excluded {path} (scope-expansion); not written: {--dry-run or --detect-only}` to its `warnings[]`. Never close a coverage gap by editing `metadata.stats` to equal the documented count: that is denominator deflation and `skf-test-skill` will reject it.
- **R2: STRUCTURAL_FIX.** A finding whose fix edits the generated markdown only, with no source change and no provenance entry change. It carries `remediation` text describing the surgical markdown edit and routes to merge Priority 8 (generated-markdown edit only); it never adds, modifies, or removes a provenance `entries[]` row. Two kinds of finding qualify:
  - a coherence finding from `skf-scan-skill-md-structure.py` (e.g., `table_drift`, `unbalanced_fences`, a broken intra-skill anchor) that touches the generated output file only;
  - a split-body consistency finding (test-skill coverage-check §1b `cross_check_mismatches`): two files of the skill (the SKILL.md body or a `references/*.md` file) document one export differently. test-skill rates it High, as it rates a signature mismatch against the source, yet it needs nothing from the source: its `Source:` names the side the pinned source contradicts (test-skill coverage-check §5b), which bullet 3's helper keeps as the entry's `package_citation` when the ledger recorded its category, and merge Priority 8 says which file it edits. Its `category` is `split-body-mismatch`; in a report older than the ledger, recognize it by its `Source:`, which points inside the skill package (at the skill's own `SKILL.md` or at one of its `references/*.md` files, whether the path is written relative to the package or through `{skill_package}`), while its issue sets the SKILL.md body against a `references/*.md` file. Test for it before the High "Signature mismatch" row: a High signature gap whose `Source:` points into the source tree, or that has no `Source:`, stays `MODIFIED_EXPORT`.
- **R3: provenance-completeness.** An export documented in SKILL.md/`references/` but absent from the provenance-map. These are documented-and-known, so `unknown` is never correct: route to gap-spot-check.md §4a's targeted re-extraction **regardless of severity**, gated only on `source_root` being pinned and readable (gap-spot-check.md §4). One exception: when the map holds the name at another file than the gap cites (`map_match` `not-found` with a candidate that has a `source_file`), its provenance is not absent, so gap-spot-check.md §4 records it `unknown` (`cited-elsewhere`) and never re-extracts it (gap-spot-check.md §4 bullet 1). The other: no file it cites or its Remediation names that the skill brief's scope leaves out is read for it, so when no file the scope takes holds it, gap-spot-check.md §4 records it `unknown` (`outside-scope`, gap-spot-check.md §4 bullet 1).
- **R4: metadata update.** A `metadata` gap's patch: it changes no export's source and sets a field write.md §3b's `metadata` call keeps (e.g., missing optional metadata), never a count that call recounts or `exports[]`, which is why a `metadata-drift` gap is not routed. Add no `effective_denominator_*` stats key: the recount drops each one when the denominator changes. Routes to merge Priority 8b and is applied by write.md §2 *before* the automatic stat recount (see merge.md §3 / write.md §2).
- **R5: MOVED_EXPORT (provenance line).** A `provenance-line` gap (in a report older than the ledger, a Low gap titled `Provenance line is not the definition of {export_name}`, test-skill coverage-check §4c) says the provenance map's `source_line` for that export is not the line that defines it, or that its citation does not resolve: a file the pinned source lacks, or a line past its end or below 1. Its `Source:` is the map's `{source_file}:{source_line}`, so `source_citation` is set, and the remediation of a line that is not the definition lists the file's definition lines. This row takes precedence over the Low `metadata update` row (R4). Route the entry to gap-spot-check.md §4's spot-check only, with no public-reachability gate and no gap-spot-check.md §4a.

3. **Build the change manifest through `{parseGapsHelper}`**, never by hand. From `{project-root}`, run:

   ```bash
   uv run {parseGapsHelper} translate \
       --gaps "{run_dir}/gaps.json" \
       --provenance-map "{provenance_map_path}" \
       [--judgments "{run_dir}/gap-judgments.json"] \
       [--read-only {dry-run|detect-only}] \
       -o "{run_dir}/change-manifest.json" \
       > "{run_dir}/translate.json"
   ```

   Pass `--judgments` once the file exists, and `--read-only` with the run's flag in a `--detect-only` or `--dry-run` run. It routes each gap by the table and rules R1 to R5 and writes `{run_dir}/change-manifest.json`, where gap-spot-check.md §4, merge and step 5 read it, as `{"mode": "gap-driven", "entries": [...]}`, each entry with the fields the "Translate" section of its docstring lists: gap-spot-check.md §4 partitions on its `change_category` and merge.md §3 dispatches on it. Its JSON goes to `{run_dir}/translate.json` (a rescope re-run's to its own file, below): act on its `status` there:

   - **`needs-judgment`** (it wrote nothing): for each `needs_judgment[]` item, judge from its gap's `title`, `issue` and `remediation`, which the item carries, add your answer to each of its `needs` to `{run_dir}/gap-judgments.json` under the item's `gap_id` (`{"<gap_id>": {"<need>": <answer>}}`), then run it again:
     - `category` (a report older than the ledger): the slug of the row bullet 2 says the gap's title and issue describe (`missing-export` or `missing-type` for a missing export or type), else the Not routed slug that names it (`stale-documentation` for documentation of a name the source surface lacks, `metadata-drift` for divergent export counts in the metadata), so the gap takes that category's reason, or null for a gap neither names;
     - `name`: the export the gap's title names, or null when it names none, which leaves the gap unrouted;
     - `rescope`: rule R1's answer, true or false;
     - `source_file`: the source file, relative to `{source_root}`, that defines the export (a rescope's exclude path) or that a rule R3 gap's documentation cites, or null.
   - **`written`:** set `gap_count` from its `gap_count`, keep its `not_routed[]` (the `id`, `title`, `category` and `reason` of each gap the table does not route, the reason saying why update-skill does not repair it and who does) for §2, and add each of its `warnings[]` to `warnings[]`: the parse's, as `test-report: <entry>`, `test-report: not routed: {id} ({category}): {reason}` for each gap not routed, and a read-only run's proposed amendments. Record them right away, in one call in place of one call per warning, from `{project-root}`: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warnings-file "{run_dir}/translate.json"`. When you answer `rescope` for a gap it did not ask about (rule R1: an export you found upstream internal or `#[doc(hidden)]`), add the answer to `{run_dir}/gap-judgments.json` and run it again before §2, its output redirected to `{run_dir}/translate-rerun.json` in place of `translate.json`, taking that run's output in place of this one: act on its `status` as above, and record a `written` re-run's warnings the same way from `{run_dir}/translate-rerun.json` (the emitter drops a warning recorded twice).
   - **Exit 1** (`status: "error"` in the file it wrote) **or no JSON:** HALT with status `blocked` and display "**The test report's gaps could not be translated:** {code}: {error}". The halt procedure takes `phase: "detect-changes:parse-gaps"`, `path: "{test_report_path}"`, `reason: "{code}: {error}"`.

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

Pass `--allow-drift` only when the user provided `--allow-workspace-drift` to update-skill.

Bind `{workspace_drift_status}` ← `status` and `{head_short_sha}` ← `head_short_sha` in workflow context, and `{pinned_short_sha}` ← the first 7 characters of `metadata.source_commit`. Then write `{run_dir}/run-context.json` again, as load-baseline.md §8 wrote it, with the keys `workspace_drift_status`, `head_short_sha` and `pinned_short_sha` added, keeping every other key as the file holds it. Only `overridden` (`--allow-workspace-drift` was passed and HEAD is not the pinned commit) changes what later steps do: nothing read at HEAD says anything about the pinned commit, so update-skill takes no provenance line, signature, parameter list, return type or node kind from it. gap-spot-check.md §3b's drift gate halts on every gap whose repair needs a line, signature, parameter list or return type from the tree, and on every rescope, whose stats recount would count the public API there. `ok` (HEAD holds the pinned commit, with or without the flag) and `skipped` change nothing: lines move and node kinds are looked up as usual.

**Dispatch on `status`:**

- **`ok` or `skipped`** (helper exit 0): log `log_message`, then load, read the full file and execute `{nextStepFile}`.
- **`overridden`** (helper exit 0): log `log_message`, add `workspace_drift_overridden: HEAD {head_short_sha} is not pinned {pinned_short_sha}` to `warnings[]`, and surface the override in the final report: report.md §2's Mode row is where the report shows it, in the one text that section gives. Then load, read the full file and execute `{nextStepFile}`: gap-spot-check.md §3b's drift gate runs before any spot-check. The override does not automatically re-pin `metadata.source_commit`; re-pinning is explicit user work (a normal-mode update records the commit it reads as `source_commit`; or re-create the skill).
- **`mismatch`** (helper exit 2): HALT immediately with status `halted-for-workspace-drift`. Display the helper's `halt_message` verbatim: it already substitutes `{pinned_commit}`, `{source_ref or "unset"}`, `{source_root}`, `{head_sha}`, and the suggested `git checkout` command. Do not proceed to gap-spot-check.md §4. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "workspace HEAD {head_short_sha} is not the pinned commit {pinned_short_sha}"`.
- **Any other result** (the helper exits non-zero without a `mismatch` envelope, prints no JSON, or returns a status not listed above): HALT with status `blocked`, since the guard could not tell which commit the spot-checks would read. Show the helper's stderr. Do not proceed to gap-spot-check.md §4. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "drift-check-failed: {what the helper printed, or no JSON}"`.
