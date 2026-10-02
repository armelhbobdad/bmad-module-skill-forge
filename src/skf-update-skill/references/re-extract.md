---
nextStepFile: 'merge.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
extractionPatternsTracingData: 'skf-create-skill/references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
# Resolve `{checkWorkspaceDriftHelper}` to the first existing path; HALT if
# neither candidate exists. §0.a relies on the helper for the deterministic
# workspace-pinning guard (git rev-parse + short-SHA prefix match + halt
# message rendering). Falling back to prose-driven git invocation would
# lose the four-state dispatch (ok / skipped / mismatch / overridden).
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
# Resolve `{verifyProvenanceCompletenessHelper}` to the first existing path
# when §0 bullet 2 first needs it. Advisory: if neither resolves, each
# spot-check records `unknown`, never a line found by eye.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# `{extractPublicApiHelper}`: §0a's recipe runner. If neither exists, read
# the files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 2, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 4.

## Rules

- Focus only on extracting changed exports — do not merge or modify existing skill
- Only extract files in the change manifest: do not touch unchanged files. **Exception (gap-driven mode):** §0a's Targeted Re-Extraction Branch also scans the files in the `resolved_paths[]` of each entry §0 bullet 2 routes to it, such as a blocking gap with no citation that pins a line (any severity but `Medium`, `Low` or `Info`, a missing or unrecognized one included).
- For each changed file, launch a subprocess (Pattern 2) that reads its exports at the lines step 2's recipe runner found (§1b); if unavailable, extract sequentially

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved. This step writes nothing outside `{run_dir}`, so there is nothing to undo, `--dry-run` included.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>"}
SKF_JSON
```

Pass `--tree` when init.md §6b bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "re-extract:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

### 0. Check for Gap-Driven Mode

**If `update_mode == "gap-driven"` (set in step 1 by `--from-test-report` or by its §4b offer):**

Source code has not drifted — the gap-derived manifest from step 2 contains export-level findings translated from the test report, not file-level changes. Perform citation spot-checks instead of full re-extraction to verify each gap-affected export is still at its recorded location.

**0.a Pre-flight: verify workspace HEAD matches pinned commit.** Gap-driven spot-checks read source at recorded `source_line` positions and must see the exact bytes the skill was pinned against. A drifted workspace silently verifies against the wrong tree — moved/renamed symbols appear "verified" because the recorded line now points at different code. Before reading any source, run the guard via `{checkWorkspaceDriftHelper}`:

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

Bind `{workspace_drift_status}` ← `status` and `{head_short_sha}` ← `head_short_sha` in workflow context, and `{pinned_short_sha}` ← the first 7 characters of `metadata.source_commit`. Only `overridden` (`--allow-workspace-drift` was passed and HEAD is not the pinned commit) changes what later steps do: nothing read at HEAD says anything about the pinned commit, so update-skill takes no provenance line, signature, parameter list, return type or node kind from it. The drift gate below halts on every gap whose repair needs a line, signature, parameter list or return type from the tree, and on every rescope, whose stats recount would count the public API there; no spot-check in bullet 2 moves a line, write.md §3 and §6 move none, write.md §2 and §6 look up no node kind there, and write.md §2 keeps the public API counts metadata.json records. `ok` (HEAD holds the pinned commit, with or without the flag) and `skipped` change nothing: lines move and node kinds are looked up as usual.

**Dispatch on `status`:**

- **`ok` or `skipped`** (helper exit 0): log `log_message` and continue to bullet 1.
- **`overridden`** (helper exit 0): log `log_message`, add `workspace_drift_overridden: HEAD {head_short_sha} is not pinned {pinned_short_sha}` to `warnings[]`, and surface the override in the final report: report.md §2's Mode row is where the report shows it, in the one text that section gives. Then run the drift gate below, and continue to bullet 1 only when it passes. The override does not automatically re-pin `metadata.source_commit`; re-pinning is explicit user work (a normal-mode update records the commit it reads as `source_commit`; or re-create the skill).
- **`mismatch`** (helper exit 2): HALT immediately with status `halted-for-workspace-drift`. Display the helper's `halt_message` verbatim: it already substitutes `{pinned_commit}`, `{source_ref or "unset"}`, `{source_root}`, `{head_sha}`, and the suggested `git checkout` command. Do not proceed to bullet 1. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "workspace HEAD {head_short_sha} is not the pinned commit {pinned_short_sha}"`.
- **Any other result** (the helper exits non-zero without a `mismatch` envelope, prints no JSON, or returns a status not listed above): HALT with status `blocked`, since the guard could not tell which commit the spot-checks would read. Show the helper's stderr. Do not proceed to bullet 1. Step 4 (merge) has not run; no partial writes. The halt procedure takes `phase: "re-extract:workspace-drift"`, `path: "{source_root}"`, `reason: "drift-check-failed: {what the helper printed, or no JSON}"`.

**Drift gate (only when `{workspace_drift_status}` is `overridden`).** Before bullet 1, collect every manifest entry whose repair needs something read from the tree: under the override that tree is HEAD, not the pinned commit, and update-skill writes nothing read there, neither a provenance line nor a signature, parameter list, return type or node kind. Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the provenance map holds the export: merge Priority 4 replaces a modified export's content with a fresh extraction, merge Priority 5 appends a new export's content, and write.md §3 adds an entry for an export the map does not hold, and in gap-driven mode each of those could only be read from the tree. That includes a gap bullet 2 would send to §0a with nothing to scan (a blocking severity as bullet 2 defines it, no `source_citation` and an empty `resolved_paths[]`): under the override this gate halts on it first. Every `DELETED_EXPORT` needs the tree as well: in gap-driven mode it is a rescope (rule R1), which narrows the brief's scope, and write.md §2 must then recount `exports_public_api` and `exports_internal` over the narrowed scope from the tree, while under the override it keeps the counts metadata.json records. A rule R5 `MOVED_EXPORT`, a `STRUCTURAL_FIX` (a split-body consistency finding among them) and a `metadata update` need nothing from the tree and pass. Look each export up in the provenance map as bullet 2 does, and give each entry that needs the tree the first reason that fits:

- `a public API recount from the tree (rule R1)`: a rescope (`DELETED_EXPORT`);
- `a line from the tree (rule R3)`: a provenance-completeness gap (`provenance_completeness: true`), which bullet 2 routes to §0a;
- `a line and a signature from the tree`: an export the lookup does not find in the map;
- `a signature from the tree`: an export the lookup finds in the map.

When no entry needs the tree, continue to bullet 1. Otherwise HALT with status `halted-for-workspace-drift` before merge runs, so merge writes nothing and §0a never runs. A rescope's amendment is not in the skill brief yet (rule R1): step 4 §6b writes it, so this halt leaves the brief as it was, and a re-run asks again. Display, with `{source_commit}` and `{source_ref}` read from metadata.json:

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

1. Read the gap-derived manifest at `{run_dir}/change-manifest.json` (step 2 §0 wrote it), and look exports up in the provenance map at `{provenance_map_path}` (init.md §4); read both from disk, never from memory
2. **Partition by change category, then iterate the export-bearing entries.** Entries that do not name an export skip the per-export verification below — they have no symbol to resolve against source:
   - **`STRUCTURAL_FIX`** (detect-changes §0 rule R2): forward verbatim to the merge step (its `remediation` text describes a generated-markdown edit). No spot-check, no provenance lookup, no `entries[]` change.
   - **`metadata update`** (rule R4): forward the metadata-patch payload to the merge step. No spot-check, no provenance lookup.

   Carry both through workflow context to merge.md unchanged. Then, for each export-bearing entry (`NEW_EXPORT`, `MODIFIED_EXPORT`, `MOVED_EXPORT`, `DELETED_EXPORT`):
   - **If the entry is `DELETED_EXPORT` (rescope, rule R1):** do not resolve against source: the export is being removed from the public surface. Record `verification: rescoped` and flag for merge Priority 1 (removal). Confirm the manifest entry carries the `rescope` object step 2 R1 recorded (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path), which step 4 §6b writes to the brief; if it has none, HALT with status `blocked` (halt procedure: `phase: "re-extract:rescope"`, `reason: "rescope-without-amendment: {name}"`): a rescope without a brief scope amendment is denominator deflation and must not be written.
   - **If the entry is `MOVED_EXPORT` (a provenance line that is not the export's definition, rule R5):** run only the spot-check below, for an export the provenance map holds. Look it up by its `source_citation`, not by name alone: take the entry whose `source_file:source_line` equals the citation, since two entries can share an `export_name` in different files. The public-reachability gate is not run for it, and it is never routed to §0a. Record in `pinned_definition_lines` the definition lines its `remediation` lists (test-skill read them at the commit its report pinned), for write.md §3's WARNs. Under the drift override (`{workspace_drift_status}` is `overridden`) its spot-check moves no line: it records `unknown` with `unknown_reason: drift-override` where it would record `moved` (outcome rules below). When the export is not in the provenance map, record `unknown`, even when the entry has a `source_citation`: there is no entry to move, it is never flagged `NEW_EXPORT`, and write.md §3 adds no entry for it.
   - Look up the export in the provenance map's `entries[]`: take the entries whose `export_name` equals the name. **With a `source_citation`,** keep those whose `source_file`, normalized as write.md §6 normalizes a path (a leading `./` dropped, backslashes turned to `/`), equals the citation's file normalized the same way. One left: the export is found. Several left: take the one whose `source_line` equals the citation's line, or else record `unknown` and leave them as they are. None left: take the "not found" branch below. **Without a `source_citation`,** exactly one entry means the export is found; several record `unknown` and stay as they are (a spot-check of the wrong one would move another export's line); none takes the "not found" branch. Read the found entry's `source_file` and `source_line`.
   - **If export not found in provenance map:**
     - **If the manifest entry has a `source_citation` (propagated from the test report by step 2 §0 bullet 3) and is not a `MOVED_EXPORT`:** run the "export found" branch's `definition-lines` call on the file and line that citation names (`--file` and `--line` from the citation, no `--export-type`), and record a full `verified` / `moved` entry with the citation's line as the recorded line: the same spot-check logic as the "export found" branch below, keyed on the manifest-supplied citation instead of the provenance map. The export is still flagged `NEW_EXPORT` for the merge step; this branch only upgrades the provenance entry from `unknown` to a live spot-check result, so write.md §3 adds a full entry at the line it pins (its bullet for a cited export the map does not hold, labeled `source-read` and `T1-low` because the spot-check finds lines by the verifier's text rules, not by an ast-grep recipe) instead of writing `null`. When that spot-check gives `unknown` or `missing`, the citation pins no line: go on to the branches below as if the entry had no `source_citation`.
     - **If the entry is a provenance-completeness gap (rule R3 — documented in SKILL.md/`references/` but missing from the provenance-map) AND `source_root` is pinned and readable:** route this entry to §0a (Targeted Re-Extraction Branch) **regardless of severity**. These exports are documented-and-known; `unknown` is never the correct outcome for them. §0a resolves them against pinned source and records a full `re-extracted` provenance entry. This route takes precedence over the severity-gated branches below.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line) and a blocking `severity`, and the rule R3 branch above did not take it:** a `severity` is blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or unrecognized one is blocking, like `Critical` and `High` (detect-changes §0 and write.md §3 apply the same rule). Route this entry to §0a (Targeted Re-Extraction Branch), whatever its `resolved_paths[]`. With a non-empty list, §0a scans those files with the tier-appropriate extractor and, on success, records a full verification record with `verification: re-extracted`, a live `provenance_citation`, and full signature/params/return-type fields for the merge step to consume as a NEW_EXPORT. With an empty list it has nothing to scan and lists the entry in `unresolved[]` with `files_scanned: 0`. Either way an entry §0a cannot resolve halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included: a blocking gap never degrades to `unknown`. See §0a for the procedure, the consolidated halt protocol, and the output record shape.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line), the branches above did not take it, and it asks to document a missing export or type** (its `category` is `missing-export` or `missing-type`): route it to §0a when its `resolved_paths[]` is not empty, whatever its severity. The route follows the gap's category, not its severity: test-skill rates a missing export `Medium`, and targeted re-extraction is how gap-driven repair gives it provenance. When §0a finds the export in none of those files, or there are none, record it `unknown` as the bullet below does: its severity is `Medium`, `Low` or `Info`, so it does not halt.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line), is not a provenance-completeness gap, and its `severity` is `Medium`, `Low` or `Info`:** record as new (`provenance_citation: unknown`): no spot-check possible; flag for merge step to handle as `NEW_EXPORT`. write.md §3 (step 5) accepts null `source_file` / `source_line` only for these; a blocking gap never gets here, whatever its `resolved_paths[]`, since the blocking-severity bullet above sends it to §0a.
   - **If export found:** ask `{verifyProvenanceCompletenessHelper}` (resolve it ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`) for the lines of its `source_file` that define the export, by the rules write.md §6's verifier applies after the write. From `{project-root}`, run:

     ```bash
     uv run {verifyProvenanceCompletenessHelper} definition-lines \
         --source-root "{source_root}" \
         --file "{source_file}" --name "{export_name}" --line {source_line} \
         [--export-type "{export_type}"]
     ```

     Pass `--export-type` when the entry records one. Take the definition lines from its output, never by eye: read its `line_check`. `checked` gives `line_is_definition` and `definition_lines`, which the outcome below reads; `file-missing` means the recorded file no longer exists; `skipped-export-type` means a `module` or `package` entry, which has no definition line and is `verified` while its file exists; `skipped-language` means the rules cover no such file: read the file and take the line that declares the export itself, never a decorator or comment above it. Record `unknown` for an entry whose call exits 2 or prints no JSON. When no candidate resolves, record `unknown` for every entry and add `provenance: spot-checks not run: skf-verify-provenance-completeness.py is missing; re-install SKF` to `warnings[]`.
   - Record verification outcome: `verified` (the recorded `source_line` is itself one of those definition lines, `line_is_definition` true; under the drift override a rule R5 `MOVED_EXPORT` still records `verified` and its entry stays unchanged, but write.md §3 lists a drift WARN for it, since test-skill found that line wrong at the pinned commit), `moved` (the file defines the export on exactly one line, and not the recorded one: `definition_lines` holds that one line; record it as `new_location`; under the drift override, when `{workspace_drift_status}` is `overridden` (§0.a), record `unknown` with `unknown_reason: drift-override` instead and set no `new_location`, because HEAD is not the pinned commit and a line read there never moves an entry), `missing` (the recorded file no longer exists: `line_check` is `file-missing`), `re-extracted` (resolved via §0a from `resolved_paths[]` or rule R3), `rescoped` (DELETED_EXPORT, flagged for removal), or `unknown` (no usable provenance data; or the file defines the export on several lines, none of them the recorded one, or on no line the rules recognize (an empty `definition_lines`), which may be a shape they do not cover: never call it gone; or, with `unknown_reason: drift-override`, a `moved` the drift override turned into `unknown`. Leave it for a person, since write.md §3 leaves such an entry unchanged)
   - **Public-reachability gate (`NEW_EXPORT` only):** before an entry is flagged `NEW_EXPORT` for the merge step, confirm the symbol is reachable as **public API**, not merely that a `pub` / `export` / top-level definition exists at the citation. Read `source_file` and resolve the symbol's module path, and confirm at least one of: (a) it is re-exported from the package entry-point barrel (`lib.rs` `pub use`, `index.ts` / `index.js` export, `__init__.py` import or `__all__`), or (b) every ancestor module on the path from that barrel is public (Rust `pub mod`, an exported TS namespace, a non-underscore Python package). A `pub(crate)` / `pub(super)` item, or one under a private module (e.g. `mod authority;` declared without `pub`), is **not** reachable. **On failure:** do not document it as public: drop it from the export-bearing set so it is never written to the documented `exports[]` array or SKILL.md, and re-queue it as a `metadata update` (rule R4) recording `reclassified: internal-unreachable` for the evidence report. Do **not** hand-set any `stats` count: write.md §2's automatic recount derives `exports_internal` / `exports_total` from the merged surface and owns those fields. This honors the workflow rule that documented API must be importable by users, since a `pub`-but-internal symbol would otherwise inflate the documented public surface with a type users cannot import.
3. Write the gap-driven records to `{run_dir}/reextract-records.json`, before bullet 5 sends the run on: merge reads them, and step 5's `apply` writes the provenance map from them. One verification record per export-bearing entry, and the per-file extractions §0a produced:

   ```bash
   cat > "{run_dir}/reextract-records.json" <<'SKF_JSON'
   {
     "mode": "gap-driven",
     "files_extracted": <count, non-zero only when §0a scanned resolved_paths[]>,
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
        "unknown_reason": "<drift-override, set only when the drift override (§0.a) made the outcome unknown, else null>",
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

   `files` holds only §0a's `re-extracted` records (`[]` when §0a ran on nothing).
4. Set `no_reextraction: true` in workflow context: step 5 will use this flag to skip stale `source_file`/`source_line`/`confidence` field updates for `verified` exports, except the label relabel write.md §2 applies when its stats helper flags an entry whose labels disagree with its `extraction_method`. `moved` exports get updated citations; a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` entry at that line; `re-extracted` exports get full fresh provenance from §0a's extraction records (see step 5 §3). Under the drift override no line moves: a spot-check that would move one records `unknown` with `unknown_reason: drift-override`. The flag is a global gap-driven marker, not a per-entry one: step 5 dispatches on each verification outcome independently.
5. **Skip sections 1–5 of step 3**: they are source-drift extraction paths that do not apply. Display the summary below, then go straight to §6 (Route to Next Step), whose branches hold in gap-driven mode too: with `dry_run_mode` true it loads `report.md` (status `dry-run`) and never merge.md, so a gap-driven `--dry-run` writes nothing; otherwise it loads `{nextStepFile}` to proceed directly to the merge step. A halt in this section (the drift gate, §0a) stops a `--dry-run` as it stops any other run.

"**Gap-driven re-extraction.** Verified {verified_count}/{gap_count} citations against live source. Moved: {moved_count}. Missing: {missing_count}. Re-extracted (via remediation paths or provenance-completeness, §0a): {re_extracted_count}. Rescoped (removed from surface): {rescoped_count}. Unknown (not in provenance map, a `Medium`, `Low` or `Info` gap §0a found nothing for, no single definition line, or a line the drift override kept from being moved): {unknown_count}."

When `{workspace_drift_status}` is `overridden`, add: "Every check read HEAD {head_short_sha}, not pinned {pinned_short_sha}: no line was moved or pinned."

**If normal mode (`update_mode` unset or not `gap-driven`):** Continue with docs-only check and source extraction below.

### 0a. Targeted Re-Extraction Branch (Helper — Called from §0 bullet 2)

**Do not execute this section sequentially.** It is a helper procedure invoked by §0 bullet 2 when specific conditions are met (see below). Normal-mode runs, and gap-driven runs in which §0 bullet 2 routes no entry here, skip this section entirely. §0's "skip sections 1–5" instruction does not apply here: §0a is addressed by name from §0, not by sequential fall-through.

**Used by:** §0 bullet 2, in one of three cases:

- a manifest entry for an export the provenance map does not hold, with no `source_citation` (or one whose spot-check pinned no line) and a blocking `severity` (anything but `Medium`, `Low` or `Info`, a missing one included), that the rule R3 case below does not take, whatever its `resolved_paths[]`: a non-empty list is the path set to scan, and an empty one leaves nothing to scan, so step 4 puts the entry straight into `unresolved[]` with `files_scanned: 0`; **or**
- such an entry with a `Medium`, `Low` or `Info` severity that §0 bullet 2 routes here by its `category` (a missing export or type): its `resolved_paths[]` is the path set to scan; **or**
- a provenance-completeness gap (rule R3: documented but missing from the provenance-map), routed here **regardless of severity** as long as `source_root` is pinned and readable. Its `resolved_paths[]` is the path set to scan: step 2 §0 filled them from the source file its documentation cites when its remediation named none.

Never under the drift override (`{workspace_drift_status}` is `overridden`): §0.a's drift gate halts on every entry that would reach this section, since it reads `{source_root}` at HEAD rather than the pinned commit.

**Purpose:** produce AST-backed provenance for blocking gaps with no citation that pins a line (any severity but `Medium`, `Low` or `Info`, a missing or unrecognized one included), so step 5 §3 never writes `source_file: null` for a blocking finding. Honors the workflow-level rule **Never hallucinate** (every statement must have AST provenance) against the most common gap-driven trigger: a failing test report whose Gap Report `Source:` field is a region reference (e.g., `@storybook/addon-docs control primitives`) rather than a `file:line` pair. Gap-driven mode skips §1 through §5, so §0a is also the only place §1b's source-access and extraction machinery is invoked during gap-driven runs.

**Procedure:**

1. **Source access** — read files under `{source_root}` (§1b **Source access**), the tree §0.a confirmed holds the pinned commit.
2. **The file set** is the `resolved_paths[]` of every entry routed here, as they are: step 2 §0's `{parseGapsHelper}` resolved them under `{source_root}` and refused, into `rejected_paths[]`, every path that leaves it (`outside-root`, or `symlink-outside-root` through a link) or names no file (`not-found`, `no-match`). Remediation text is user-editable: never scan a refused path, and never expand or check a path by hand.
3. **Extract:** read the file set with the tier-appropriate extractor and label each export by the tool that produced it, at any tier: an export an ast-grep rule matched is T1 (`extraction_method: ast-grep`), an export read by eye is T1-low (`extraction_method: source-read`). At Forge tier and above, write the file set as a JSON array to `{run_dir}/remediation-files.json` and run the recipe runner over it (resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`), from `{project-root}`:

   ```bash
   uv run {extractPublicApiHelper} --mode full \
       --source-root "{source_root}" \
       --files-from "{run_dir}/remediation-files.json" \
       [--scope-type "{scope_type}"] \
       --head-cap 0 \
       -o "{run_dir}/remediation-exports.json"
   ```

   Pass `--scope-type` when step 1 read a `scope_type` from metadata.json, so a component library runs its recipe set. It takes no `--brief`: a test report can name a file the brief's scope leaves out as an export's home, and the runner would skip it. On exit 1 (`incomplete`) run it once more; on exit 2 or 3, no JSON, or no candidate resolves, or at Quick tier, read the files by eye (by text pattern). Read by eye only what the recipes leave out, as §1b says. Launch subprocesses in parallel (Pattern 4) when available; sequential fallback otherwise. Follow the tier-degradation rules in `{tierDegradationRulesData}` when AST tools fail on individual files.
4. **Match by name**: for each manifest entry routed here with a path set to scan, search the extraction results of its own `resolved_paths[]` for an export whose `name` matches the manifest entry's `name`. An entry with no path set to scan (an empty `resolved_paths[]`) is not matched: it goes straight to `unresolved[]` with `files_scanned: 0`. Record the first hit as:
   - `verification: re-extracted`
   - `provenance_citation: {file}:{start_line}` from the AST result
   - `new_location: {file}:{start_line}` (same value — satisfies the existing consumer contract)
   - `resolution_source: remediation-paths`
   - `confidence: T1`, `extraction_method: ast-grep`, `ast_node_type` set to the `kind` the matching recipe declares and `ast_recipe` naming that recipe when an ast-grep rule matched the export, or `confidence: T1-low`, `extraction_method: source-read`, `ast_node_type: null` and `ast_recipe: null` when it was read by eye
   - the full extraction signature (type, params, return_type, docstring) — mirror the shape of §4's per-file extraction record so step 4 Priority 5 can merge it with the same code path used in normal mode.

   Then apply the §0 bullet 2 **public-reachability gate** to each matched symbol before recording it as a NEW_EXPORT: §0a has full source access, so resolve the symbol's module path and confirm barrel re-export or a fully-`pub` module chain. If it is unreachable (`pub(crate)` / private module), do **not** record `re-extracted`: drop it from the export-bearing set and re-queue the entry as a `metadata update` (rule R4, `reclassified: internal-unreachable`), exactly as the gate specifies. A re-extracted symbol that is not public API is not a documentable NEW_EXPORT. This is a resolution, not an `unresolved[]` failure (step 5): the symbol was found, just not public, so it does not trigger step 5's HALT.
5. **Track failures across all qualifying entries.** Collect every entry whose symbol was not found in any file of its path set, and every entry step 4 had nothing to scan for (`files_scanned: 0`), into an `unresolved[]` list, except a `Medium`, `Low` or `Info` missing export or type (the second case of **Used by**): record that one `unknown`, as §0 bullet 2's `unknown` branch does. After processing every qualifying entry, if `unresolved[]` is non-empty: HALT with a consolidated report listing every unresolved entry (`name`, `severity`, `remediation_paths`, `rejected_paths`, `files_scanned`, `exports_found_in_scan`). Template:

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

6. **Success summary:** append the record `targeted_reextraction: {resolved_count, files_scanned, exports_matched, tier}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `targeted_reextraction`, and each matched record in the `files` of §0 bullet 3's `{run_dir}/reextract-records.json`. The evidence report (step 5 §4) surfaces this alongside the verified / moved / missing tally.

**Why halt instead of degrading to `unknown`:** a Critical or High gap by definition blocks skill usefulness (a wrong or fabricated signature, or a broken or inaccurate reference, as test-skill's Gap Severity table rates them; a missing export is Medium since the hard-gate re-rating, though a report older than the gap ledger may still rate it Critical), and a gap with a missing or unrecognized severity counts as blocking rather than being guessed to matter less. Silently writing `source_file: null` for a blocking gap produces a skill that passes re-test but still hides the broken behavior behind a placeholder. The halt forces the test report to carry usable remediation information: a one-time fix-up that is far cheaper than a downstream audit trying to track why the "repaired" skill still fails.

### 1. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the original brief or metadata:**

"**Docs-only skill detected.** This skill was generated from external documentation, not source code. Re-extraction re-fetches the documents whose hash changed (step 2 §1) for their updated content."

- Re-fetch each URL in `changed_urls` of `{run_dir}/change-manifest.json` using whatever web fetching capability is available; leave every other document as it is
- Extract updated API information with T3 `[EXT:{url}]` citations
- Write the updated extraction inventory to `{run_dir}/reextract-records.json`, from which merge and step 5's `apply` work, as `{"mode": "docs-only", "changed_urls": [<the URLs re-fetched>], "exports": [{"name": "<export>", "type": "<kind>", "params": [<each parameter>], "return_type": "<type, or null>", "url": "<the URL it came from>"}]}`
- Skip sections 1b to 5 (source code extraction), then go straight to §6 (Route to Next Step), whose `dry_run_mode` branch holds for a docs-only skill too: a docs-only `--dry-run` never loads merge.md

**If `source_type: "source"` (default):** Continue with source extraction below.

### 1b. Determine Extraction Strategy by Tier

**Source access (every tier):** read every changed file from `{source_root}`. When `{source_tree_status}` is `ready` or `offline`, that is the tree init.md §6b prepared at `{target_commit}`, the commit step 2 compared, so detection, extraction, merge and write read one tree; otherwise it is the local source init.md §6 validated (in gap-driven mode, the tree §0.a confirmed holds the pinned commit). Do not fetch changed files through the gh contents API, zread or deepwiki: the gh contents API serves the default branch unless given a ref, and the zread and deepwiki indexes may sit at another commit, so a citation read there would not point into the commit this update records. If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists, HALT with status `blocked` per SKILL.md's source-tree rule (halt procedure: `phase: "re-extract:source-tree-missing"`, `path: "{source_root}"`, `reason: "source tree {source_root} disappeared mid-run"`). If one changed file cannot be read, limit its analysis to the provenance-map baseline (State 2: each baseline entry keeps its own confidence label from compilation-time data) and warn: "Could not read {path} from {source_root}. Its analysis is limited to the provenance-map baseline."

**Quick tier (text pattern matching):**
- Extract function/class/type names via regex patterns
- Extract export statements via text matching
- Label every export T1-low (pattern-matched, not AST-verified) with `extraction_method: source-read` and `ast_node_type: null`

**Forge tier (AST structural extraction):**

- Step 2's Category B ran the recipe runner (`{extractPublicApiHelper}` `--mode full`, the recipes of the AST Extraction Protocol in `{extractionPatternsData}`) over every file to extract, `{run_dir}/extract-files.json`, and wrote `{run_dir}/extraction.json`: never run it again here (§0a runs it over its own file set). The per-file workers (§2) take their file's exports from its `exports[]`, each at the line of its name, never a decorator or `export` line above it: T1 (AST-verified structural truth) with `extraction_method: ast-grep`, and `ast_node_type` and `ast_recipe` copied, never inferred.
- Read by eye only what the recipes leave out: an export a file defines in a form Known Limitation #11 in `{extractionPatternsData}` lists, a file `file_issues[]` names (not UTF-8, or code the parser could not read, where a recipe can miss an export), a name `entry_point_diff.extraction_gaps[]` lists, and each file step 2 told the user it read by eye. Step 2 already read those of the modified and added files into `{run_dir}/export-details.json` (its entries with an `export_type`): take them from there. An export read by eye is T1-low with `extraction_method: source-read` and `ast_node_type: null`.
- At each export's line the workers read what the recipes do not record: its signature (a function's, a type definition, a class's members, a constant's value) and JSDoc or docstring, and its parameter types and return type unless `{run_dir}/export-details.json` holds them.

**Tier degradation handling (Forge/Forge+/Deep):** If step 2's runner could run no ast-grep, or left files unread (step 2 told the user which), follow `{tierDegradationRulesData}` for fallback strategy and user notification requirements. Silent degradation is forbidden: the user must always know which files were read by eye instead of matched, and why.

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions, labeled by tool as at Forge tier
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: structural entries labeled by tool (T1 for an ast-grep match, T1-low for an export read by eye), T2 for semantic enrichment

**Tool resolution:** `ast_bridge` → `{extractPublicApiHelper}` `--mode full` (step 2 and §0a), which runs every recipe through the ast-grep CLI; `find_code` only as the fallback of Known Limitation #4, for a recipe that errors or finds nothing where a file clearly holds exports. `qmd_bridge` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Extract Changed Files

Step 2's Category A left every promoted or tracked document out of the files to extract (its §2.0): a document must not reach AST extraction, which would produce ghost entries; step 2's Category D and step 4's Priority 6/7 handle doc-type drift.

For each file `{run_dir}/extract-files.json` lists (step 2 wrote it: the MODIFIED and ADDED files and each MOVED file's new path), launch a subprocess that:

1. Loads the source file
2. At Forge tier and above, takes this file's exports from step 2's `{run_dir}/extraction.json` and `export-details.json` (§1b); at Quick tier, matches the file's text as §1b says
3. Extract each export into the per-file return contract shown in bullet 4.
4. **Return contract.** Each extraction worker returns ONLY this per-file block — no prose, no commentary, no markdown fences (the parent strips wrapping fences before parsing). The shape is exactly the per-file record §4 aggregates (the `Per-file extractions` block, lines below), so the parent appends it verbatim rather than re-parsing free text:

   ```json
   {
     "file_path": "...",
     "exports": [
       {"name": "...", "type": "function|class|type|constant",
        "signature": "...", "location": "{file}:{start_line}-{end_line}",
        "confidence": "T1|T1-low|T2",
        "extraction_method": "ast-grep|source-read",
        "ast_node_type": "<the kind the matching ast-grep recipe declares, or null>",
        "ast_recipe": "<id of the recipe that matched, or the find_code pattern, or null>",
        "parameters": [{"name": "...", "type": "..."}],
        "return_type": "...", "docstring": "...",
        "qmd_evidence": "<if Deep tier, else omit>"}
     ]
   }
   ```

**For DELETED files:** No extraction needed — deletions handled in merge step.

**For MOVED files:** Re-extract at new location to update file:line references.

**Re-export tracing (Forge/Deep only):** After extracting changed files, check if any public exports from the package entry point (`__init__.py`, `index.ts`, `lib.rs`) are unresolved — particularly when a changed file is part of a module re-export chain. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` to trace unresolved symbols to their actual definition files.

### 3. Deep Tier QMD Enrichment (Conditional)

**ONLY if forge_tier == Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the skill being updated AND `type` is `"extraction"`.

**If a matching extraction collection is found:**
Launch a subprocess that loads qmd_bridge and for each changed export:
1. Queries the `{skill_name}-extraction` collection for semantic context related to the export
2. Searches for usage patterns, documentation references, temporal history
3. Returns T2 evidence per export (usage frequency, context snippets, related concepts)

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. T2 enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment: extraction still produces its structural results, labeled by tool.

**If forge_tier != Deep:** Skip this section with notice: "QMD enrichment skipped (tier: {forge_tier})"

### 4. Compile Extraction Results

Write every worker's per-file block, exactly as §2's return contract shapes it (`qmd_evidence` added at Deep tier), to `{run_dir}/reextract-records.json`, where merge and step 5's `apply` read them:

```bash
cat > "{run_dir}/reextract-records.json" <<'SKF_JSON'
{"mode": "normal", "files": [<each per-file block: {"file_path", "exports": [...]}>]}
SKF_JSON
```

Count from that file, never from memory: `files_extracted` (its `files`), `exports_extracted` (their `exports`), and the confidence breakdown, each export by its `confidence` (T1, T1-low, T2).

### 5. Display Extraction Summary and Auto-Proceed

Display one line from §4's results: "**Re-extracted** {exports} exports from {files} files ({t1} T1, {t1_low} T1-low, {t2} T2)." The report (step 6) shows the confidence tier breakdown.

### 6. Route to Next Step

This step auto-proceeds — no user choices. Once all changed files are extracted and results compiled, load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode: skipping merge and write.** Loading report..." and load `report.md` (NOT `{nextStepFile}`); it emits status `dry-run` describing what merge+write would have done. Every route out of this step comes here, the gap-driven (§0 bullet 5) and docs-only (§1) ones included, so no artifact is modified on disk by this run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{nextStepFile}` (merge.md) to begin the merge operation.

