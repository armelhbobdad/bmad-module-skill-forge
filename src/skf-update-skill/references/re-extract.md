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
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 02, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 04.

## Rules

- Focus only on extracting changed exports — do not merge or modify existing skill
- Only extract files in the change manifest: do not touch unchanged files. **Exception (gap-driven mode):** §0a's Targeted Re-Extraction Branch also scans files listed in each manifest entry's `remediation_paths[]` to resolve blocking gaps with no citation that pins a line (any severity but `Medium`, `Low` or `Info`, a missing or unrecognized one included).
- For each changed file, launch a subprocess for deep AST analysis (Pattern 2); if unavailable, extract sequentially

## Steps

### 0. Check for Gap-Driven Mode

**If `update_mode == "gap-driven"` (set in step 1 via `--from-test-report`, confirmed in step 2 section 0):**

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

Bind `{workspace_drift_status}` ← `status` and `{head_short_sha}` ← `head_short_sha` in workflow context, and `{pinned_short_sha}` ← the first 7 characters of `metadata.source_commit`. Only `overridden` (`--allow-workspace-drift` was passed and HEAD is not the pinned commit) changes what later steps do: nothing read at HEAD says anything about the pinned commit, so update-skill takes no provenance line, signature, parameter list, return type or node kind from it. The drift gate below halts on every gap whose repair needs a line, signature, parameter list or return type from the tree, no spot-check in bullet 2 moves a line, write.md §3 and §6a move none, and write.md §2 and §6a look up no node kind there. `ok` (HEAD holds the pinned commit, with or without the flag) and `skipped` change nothing: lines move and node kinds are looked up as usual.

**Dispatch on `status`:**

- **`ok` or `skipped`** (helper exit 0): log `log_message` and continue to bullet 1.
- **`overridden`** (helper exit 0): log `log_message`, add `workspace_drift_overridden: HEAD {head_short_sha} is not pinned {pinned_short_sha}` to `warnings[]`, and surface the override in the final report: report.md §2's Mode row is where the report shows it, in the one text that section gives. Then run the drift gate below, and continue to bullet 1 only when it passes. The override does not automatically re-pin `metadata.source_commit`; re-pinning is explicit user work (a normal-mode update records the commit it reads as `source_commit`; or re-create the skill).
- **`mismatch`** (helper exit 2): HALT immediately with status `halted-for-workspace-drift`. Display the helper's `halt_message` verbatim — it already substitutes `{pinned_commit}`, `{source_ref or "unset"}`, `{source_root}`, `{head_sha}`, and the suggested `git checkout` command. Do not proceed to bullet 1. Step-04 merge has not run; no partial writes. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "re-extract:workspace-drift", path: "{source_root}", reason: "..."}`).
- **Any other result** (the helper exits non-zero without a `mismatch` envelope, prints no JSON, or returns a status not listed above): HALT with status `blocked`, since the guard could not tell which commit the spot-checks would read. Show the helper's stderr. Do not proceed to bullet 1. Step-04 merge has not run; no partial writes. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "re-extract:workspace-drift", path: "{source_root}", reason: "drift-check-failed: {what the helper printed, or no JSON}"}`).

**Drift gate (only when `{workspace_drift_status}` is `overridden`).** Before bullet 1, collect every manifest entry whose repair needs something read from the tree: under the override that tree is HEAD, not the pinned commit, and update-skill writes nothing read there, neither a provenance line nor a signature, parameter list, return type or node kind. Every `NEW_EXPORT` and every `MODIFIED_EXPORT` needs it, whatever its `severity` and whether the provenance map holds the export: merge Priority 4 replaces a modified export's content with a fresh extraction, merge Priority 5 appends a new export's content, and write.md §3 adds an entry for an export the map does not hold, and in gap-driven mode each of those could only be read from the tree. That includes a gap bullet 2 would send to §0a with nothing to scan (a blocking severity as bullet 2 defines it, no `source_citation` and an empty `remediation_paths[]`): under the override this gate halts on it first. A `DELETED_EXPORT`, a rule R5 `MOVED_EXPORT`, a `STRUCTURAL_FIX` (a split-body consistency finding among them) and a `metadata update` need nothing from the tree and pass. Look each export up in the provenance map as bullet 2 does, and give each entry that needs the tree the first reason that fits:

- `a line from the tree (rule R3)`: a provenance-completeness gap (`provenance_completeness: true`), which bullet 2 routes to §0a;
- `a line and a signature from the tree`: an export the lookup does not find in the map;
- `a signature from the tree`: an export the lookup finds in the map.

When no entry needs the tree, continue to bullet 1. Otherwise HALT with status `halted-for-workspace-drift` before merge runs, so nothing is written and §0a never runs. Display, with `{source_commit}` and `{source_ref}` read from metadata.json:

```
Workspace drift blocks {N} gap(s) that need the pinned tree.

  pinned (metadata.source_commit): {source_commit}
  {if source_ref is set: pinned ref (metadata.source_ref): {source_ref}}
  workspace HEAD ({source_root}):  {head_short_sha}

--allow-workspace-drift reads HEAD, not the pinned commit, and update-skill
writes nothing read at HEAD: no provenance line, signature, parameter list,
return type or node kind.

Gaps that need the pinned tree:
  {for each entry: - {name} ({change_category}, {severity or "no severity"}): {a line from the tree (rule R3) | a line and a signature from the tree | a signature from the tree}}

Fix one of the following, then re-run update-skill:
  a) Check out the pinned commit: git -C "{source_root}" checkout {source_commit}
     Then re-run --from-test-report without --allow-workspace-drift.
  b) Run a normal update (without --from-test-report), which records the commit
     it reads as the new pin, then re-run test-skill.
```

In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "re-extract:workspace-drift", path: "{source_root}", reason: "drift-override: {N} gap(s) need the pinned tree: {name} ({reason}), ..."}`).

1. Use the provenance map already loaded in step 1 (at `{forge_version}/provenance-map.json`) — do not re-read
2. **Partition by change category, then iterate the export-bearing entries.** Entries that do not name an export skip the per-export verification below — they have no symbol to resolve against source:
   - **`STRUCTURAL_FIX`** (detect-changes §0 rule R2): forward verbatim to the merge step (its `remediation` text describes a generated-markdown edit). No spot-check, no provenance lookup, no `entries[]` change.
   - **`metadata update`** (rule R4): forward the metadata-patch payload to the merge step. No spot-check, no provenance lookup.

   Carry both through workflow context to merge.md unchanged. Then, for each export-bearing entry (`NEW_EXPORT`, `MODIFIED_EXPORT`, `MOVED_EXPORT`, `DELETED_EXPORT`):
   - **If the entry is `DELETED_EXPORT` (rescope, rule R1):** do not resolve against source — the export is being removed from the public surface. Record `verification: rescoped` and flag for merge Priority 1 (removal). Confirm the brief carries the matching `scope.amendments[]` (`action: "excluded"`) + `scope.exclude` entry that step 2 R1 wrote; if absent, HALT — a rescope without a brief scope amendment is denominator deflation and must not be written.
   - **If the entry is `MOVED_EXPORT` (a provenance line that is not the export's definition, rule R5):** run only the spot-check below, for an export the provenance map holds. Look it up by its `source_citation`, not by name alone: take the entry whose `source_file:source_line` equals the citation, since two entries can share an `export_name` in different files. The public-reachability gate is not run for it, and it is never routed to §0a. Record in `pinned_definition_lines` the definition lines its `remediation` lists (test-skill read them at the commit its report pinned), for write.md §3's WARNs. Under the drift override (`{workspace_drift_status}` is `overridden`) its spot-check moves no line: it records `unknown` with `unknown_reason: drift-override` where it would record `moved` (outcome rules below). When the export is not in the provenance map, record `unknown`, even when the entry has a `source_citation`: there is no entry to move, it is never flagged `NEW_EXPORT`, and write.md §3 adds no entry for it.
   - Look up the export in the provenance map's `entries[]`: take the entries whose `export_name` equals the name. **With a `source_citation`,** keep those whose `source_file`, normalized as write.md §6a normalizes a path (a leading `./` dropped, backslashes turned to `/`), equals the citation's file normalized the same way. One left: the export is found. Several left: take the one whose `source_line` equals the citation's line, or else record `unknown` and leave them as they are. None left: take the "not found" branch below. **Without a `source_citation`,** exactly one entry means the export is found; several record `unknown` and stay as they are (a spot-check of the wrong one would move another export's line); none takes the "not found" branch. Read the found entry's `source_file` and `source_line`.
   - **If export not found in provenance map:**
     - **If the manifest entry has a `source_citation` (propagated from the test report by step 2 §0 bullet 4) and is not a `MOVED_EXPORT`:** under the drift override (`{workspace_drift_status}` is `overridden`, §0.a) no entry reaches this branch: the §0.a drift gate halted on every `NEW_EXPORT` and `MODIFIED_EXPORT` before bullet 1, since a citation read at HEAD pins no line whatever that file holds there. Otherwise read the file that citation names and find the lines that define the export, by the rules of the "export found" branch below. Record a full `verified` / `moved` entry with the citation's line as the recorded line: the same spot-check logic as the "export found" branch below, keyed on the manifest-supplied citation instead of the provenance map. The export is still flagged `NEW_EXPORT` for the merge step; this branch only upgrades the provenance entry from `unknown` to a live spot-check result, so write.md §3 adds a full entry at the line it pins (its bullet for a cited export the map does not hold, labeled `source-read` and `T1-low` because the spot-check reads by eye) instead of writing `null`. When that spot-check gives `unknown` or `missing`, the citation pins no line: go on to the branches below as if the entry had no `source_citation`.
     - **If the entry is a provenance-completeness gap (rule R3 — documented in SKILL.md/`references/` but missing from the provenance-map) AND `source_root` is pinned and readable:** route this entry to §0a (Targeted Re-Extraction Branch) **regardless of severity**. These exports are documented-and-known; `unknown` is never the correct outcome for them. §0a resolves them against pinned source and records a full `re-extracted` provenance entry. This route takes precedence over the severity-gated branches below.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line) and a blocking `severity`, and the rule R3 branch above did not take it:** a `severity` is blocking unless it is `Medium`, `Low` or `Info`, compared case-insensitively, so a missing or unrecognized one is blocking, like `Critical` and `High` (detect-changes §0 and write.md §3 apply the same rule). Route this entry to §0a (Targeted Re-Extraction Branch), whatever its `remediation_paths[]`. With a non-empty list, §0a scans those paths with the tier-appropriate extractor and, on success, records a full verification record with `verification: re-extracted`, a live `provenance_citation`, and full signature/params/return-type fields for the merge step to consume as a NEW_EXPORT. With an empty list it has nothing to scan and lists the entry in `unresolved[]` with `files_scanned: 0`. Either way an entry §0a cannot resolve halts the workflow with `halted-for-remediation-path` before merge, `--dry-run` included: a blocking gap never degrades to `unknown`. See §0a for the procedure, the consolidated halt protocol, and the output record shape.
     - **If the manifest entry has no `source_citation` (or one whose spot-check above pinned no line), is not a provenance-completeness gap, and its `severity` is `Medium`, `Low` or `Info`:** record as new (`provenance_citation: unknown`): no spot-check possible; flag for merge step to handle as `NEW_EXPORT`. Step-06 §3 accepts null `source_file` / `source_line` only for these; a blocking gap never gets here, whatever its `remediation_paths[]`, since the bullet above sends it to §0a.
   - **If export found:** read the whole source file and find every line that defines the export, by the rules write.md §6a's verifier applies. A line defines it only when it is the definition line itself, never a decorator, comment or blank line above it. NAME is the export name, or the last segment of a dotted name (`App.update`).
     - **Python:** the `def` / `async def` / `class NAME` line; an assignment binding NAME (`NAME =`, `NAME: T =`, annotation-only `NAME: T`, a target list `A, NAME = ...`, PEP 695 `type NAME =`); an import that binds NAME (`import NAME`, `import X as NAME`, `from X import NAME`, `from X import Y as NAME`), including NAME on its own line inside a parenthesized or backslash-continued import. A line inside a docstring or inside a call's arguments is not a statement and never counts.
     - **TS/JS:** a `function`, `class`, `interface`, `type`, `enum`, `namespace`, `const`, `let` or `var` declaration of NAME (with any of `export`, `default`, `async`, `declare`, `abstract`); `export import NAME =`; `export * as NAME from`; `export default NAME`; an `export { ... }` list that exposes NAME; CommonJS `exports.NAME =`, `module.exports.NAME =`, or NAME as a key or shorthand inside `module.exports = { ... }`. For a dotted name, an indented class member declaring NAME (method, property or accessor) also counts.
     - **Indentation:** for a dotted name, indented lines count. For an undotted name, when the file defines NAME on a line at column 0, the indented lines do not count, so a local variable of the same name never outranks the module-level definition.
     - **Another language:** the line that declares NAME the same way.
     - An entry whose `export_type` is `module` or `package` has no definition line: it is `verified` while `source_file` exists and `missing` when it does not.
   - Record verification outcome: `verified` (the recorded `source_line` is itself one of those definition lines; a definition one line away is `moved`, never `verified`; under the drift override a rule R5 `MOVED_EXPORT` still records `verified` and its entry stays unchanged, but write.md §3 lists a drift WARN for it, since test-skill found that line wrong at the pinned commit), `moved` (the file defines the export on exactly one line, and not the recorded one: record that exact line as `new_location`; under the drift override, when `{workspace_drift_status}` is `overridden` (§0.a), record `unknown` with `unknown_reason: drift-override` instead and set no `new_location`, because HEAD is not the pinned commit and a line read there never moves an entry), `missing` (the recorded file no longer exists), `re-extracted` (resolved via §0a from `remediation_paths[]` or rule R3), `rescoped` (DELETED_EXPORT, flagged for removal), or `unknown` (no usable provenance data; or the file defines the export on several lines, none of them the recorded one, or on no line the rules recognize, which may be a shape they do not cover: never call it gone; or, with `unknown_reason: drift-override`, a `moved` the drift override turned into `unknown`. Leave it for a person, since write.md §3 leaves such an entry unchanged)
   - **Public-reachability gate (`NEW_EXPORT` only):** before an entry is flagged `NEW_EXPORT` for the merge step, confirm the symbol is reachable as **public API**, not merely that a `pub` / `export` / top-level definition exists at the citation. The spot-check already read `source_file`; extend that read to resolve the symbol's module path and confirm at least one of: (a) it is re-exported from the package entry-point barrel (`lib.rs` `pub use`, `index.ts` / `index.js` export, `__init__.py` import or `__all__`), or (b) every ancestor module on the path from that barrel is public (Rust `pub mod`, an exported TS namespace, a non-underscore Python package). A `pub(crate)` / `pub(super)` item, or one under a private module (e.g. `mod authority;` declared without `pub`), is **not** reachable. **On failure:** do not document it as public: drop it from the export-bearing set so it is never written to the documented `exports[]` array or SKILL.md, and re-queue it as a `metadata update` (rule R4) recording `reclassified: internal-unreachable` for the evidence report. Do **not** hand-set any `stats` count: write.md §2's automatic recount derives `exports_internal` / `exports_total` from the merged surface and owns those fields. This honors the workflow rule that documented API must be importable by users, since a `pub`-but-internal symbol would otherwise inflate the documented public surface with a type users cannot import. **Under the drift override** (`{workspace_drift_status}` is `overridden`) no entry reaches this gate: the §0.a drift gate halted on every `NEW_EXPORT` and `MODIFIED_EXPORT` before bullet 1, and barrels and module chains read at HEAD say nothing about the pinned commit either.
3. Build a minimal extraction results block matching section 4's shape, with `mode: gap-driven` and per-export verification records:

   ```
   Extraction Results:
     mode: gap-driven
     files_extracted: {count}  # non-zero only when §0a scanned remediation_paths[]
     exports_extracted: {gap_count}
     confidence_breakdown:   # count each verified, moved or re-extracted entry by the label its extraction_method implies, never by the tier
       T1: {entries whose extraction_method is ast-grep (or ast_bridge)}
       T1-low: {entries whose extraction_method is source-read (or source_reading), and each cited export not in the map that the spot-check pinned and the public-reachability gate passed, which write.md §3 writes as source-read}
       unlabeled: {entries whose extraction_method is unknown or missing, such as direct-read, other than a pinned cited export that passed the reachability gate (counted under T1-low); write.md §2 relabels them}
       T2: 0

     Per-export verification:
       {export_name}:
         provenance_citation: {source_file}:{source_line}
         verification: verified|moved|missing|unknown|re-extracted|rescoped
         unknown_reason: drift-override         # set only when the drift override (§0.a) made the outcome unknown
         pinned_definition_lines: [{line}, ...] # MOVED_EXPORT (rule R5) only: the definition lines its test-report
                                                # remediation lists, read at the commit the test report pinned
         new_location: {source_file}:{new_line}  # set when moved OR re-extracted
         resolution_source: remediation-paths    # set only when verification == re-extracted
         gap_category: NEW_EXPORT|MODIFIED_EXPORT|MOVED_EXPORT|DELETED_EXPORT|metadata_update

     Per-file extractions:   # populated only when §0a produced re-extracted records
       {file_path}:
         exports:
           - name: {export_name}
             type: function|class|type|constant
             signature: {full signature}
             location: {file}:{start_line}-{end_line}
             confidence: T1|T1-low   # T1 for an ast-grep match, T1-low for an export read by eye
             extraction_method: ast-grep|source-read
             ast_node_type: {the kind the matching ast-grep recipe declares, or null}
             ast_recipe: {id of the recipe that matched, or the find_code pattern, or null}
             params: [{name, type}]
             return_type: {type}
             docstring: {summary}
   ```

4. Set `no_reextraction: true` in workflow context: step 6 will use this flag to skip stale `source_file`/`source_line`/`confidence` field updates for `verified` exports, except the label relabel write.md §2 applies when its stats helper flags an entry whose labels disagree with its `extraction_method`. `moved` exports get updated citations; a cited `NEW_EXPORT` whose spot-check pinned a line gets a new `source-read` entry at that line; `re-extracted` exports get full fresh provenance from §0a's extraction records (see step 6 §3). Under the drift override no line moves or is pinned: a spot-check that would move one records `unknown` with `unknown_reason: drift-override`, and §0.a's drift gate has already halted on every `NEW_EXPORT` and `MODIFIED_EXPORT`, so §0a never runs. The flag is a global gap-driven marker, not a per-entry one: step 6 dispatches on each verification outcome independently.
5. **Skip sections 1–5 of step 3**: they are source-drift extraction paths that do not apply. Display the summary below, then go straight to §6 (Route to Next Step), whose branches hold in gap-driven mode too: with `dry_run_mode` true it loads `report.md` (status `dry-run`) and never merge.md; otherwise it loads `{nextStepFile}` to proceed directly to the merge step. A halt in this section (the drift gate, §0a) stops a `--dry-run` as it stops any other run.

"**Gap-driven re-extraction.** Verified {verified_count}/{gap_count} citations against live source. Moved: {moved_count}. Missing: {missing_count}. Re-extracted (via remediation paths or provenance-completeness, §0a): {re_extracted_count}. Rescoped (removed from surface): {rescoped_count}. Unknown (not in provenance map, no single definition line, or a line the drift override kept from being moved): {unknown_count}."

When `{workspace_drift_status}` is `overridden`, add: "Every check read HEAD {head_short_sha}, not pinned {pinned_short_sha}: no line was moved or pinned."

**If normal mode (`update_mode` unset or not `gap-driven`):** Continue with docs-only check and source extraction below.

### 0a. Targeted Re-Extraction Branch (Helper — Called from §0 bullet 2)

**Do not execute this section sequentially.** It is a helper procedure invoked by §0 bullet 2 when specific conditions are met (see below). Normal-mode runs, and gap-driven runs in which §0 bullet 2 routes no entry here, skip this section entirely. §0's "skip sections 1–5" instruction does not apply here: §0a is addressed by name from §0, not by sequential fall-through.

**Used by:** §0 bullet 2, in either of two cases:

- a manifest entry for an export the provenance map does not hold, with no `source_citation` (or one whose spot-check pinned no line) and a blocking `severity` (anything but `Medium`, `Low` or `Info`, a missing one included), that the second case below does not take, whatever its `remediation_paths[]`: a non-empty list is the path set to scan, and an empty one leaves nothing to scan, so step 4 puts the entry straight into `unresolved[]` with `files_scanned: 0`; **or**
- a provenance-completeness gap (rule R3 — documented but missing from the provenance-map), routed here **regardless of severity** as long as `source_root` is pinned and readable. For this case, treat the export's documented `source` reference (or `remediation_paths[]` when present) as the path set to scan.

Never under the drift override (`{workspace_drift_status}` is `overridden`): §0.a's drift gate halts on every entry that would reach this section, since it reads `{source_root}` at HEAD rather than the pinned commit.

**Purpose:** produce AST-backed provenance for blocking gaps with no citation that pins a line (any severity but `Medium`, `Low` or `Info`, a missing or unrecognized one included), so step 6 §3 never writes `source_file: null` for a blocking finding. Honors the workflow-level rule **Never hallucinate** (every statement must have AST provenance) against the most common gap-driven trigger: a failing test report whose Gap Report `Source:` field is a region reference (e.g., `@storybook/addon-docs control primitives`) rather than a `file:line` pair. Gap-driven mode skips §1 through §5, so §0a is also the only place §1b's source-access and extraction machinery is invoked during gap-driven runs.

**Procedure:**

1. **Source access** — read files under `{source_root}` (§1b **Source access**), the tree §0.a confirmed holds the pinned commit.
2. **Expand `remediation_paths[]`** — for each path across all qualifying entries:
   - Literal source file (ends in a recognized source extension): use as-is.
   - Directory or glob: expand under `{source_root}` using the provenance map's file patterns.
   - **Security boundary:** reject and skip any path that resolves outside `{source_root}`. Remediation text is user-editable and must never be allowed to escape the source tree.
   - Deduplicate the resolved file set across all entries routed to §0a — each physical file is scanned at most once.
3. **Extract:** run the tier-appropriate extractor from §1b over the resolved file set and label each export by the tool that produced it, at any tier: an export an ast-grep rule matched is T1 (`extraction_method: ast-grep`), an export read by eye is T1-low (`extraction_method: source-read`). Launch subprocesses in parallel (Pattern 4) when available; sequential fallback otherwise. Follow the AST Extraction Protocol in `{extractionPatternsData}` for Forge/Deep tiers, and the tier-degradation rules in `{tierDegradationRulesData}` when AST tools fail on individual files.
4. **Match by name**: for each manifest entry routed here with a path set to scan, search the aggregated extraction results for an export whose `name` matches the manifest entry's `name`. An entry with no path set to scan (a blocking gap with an empty `remediation_paths[]`, or a rule R3 gap with neither a documented `source` reference nor remediation paths) is not matched: it goes straight to `unresolved[]` with `files_scanned: 0`. Record the first hit as:
   - `verification: re-extracted`
   - `provenance_citation: {file}:{start_line}` from the AST result
   - `new_location: {file}:{start_line}` (same value — satisfies the existing consumer contract)
   - `resolution_source: remediation-paths`
   - `confidence: T1`, `extraction_method: ast-grep`, `ast_node_type` set to the `kind` the matching recipe declares and `ast_recipe` naming that recipe when an ast-grep rule matched the export, or `confidence: T1-low`, `extraction_method: source-read`, `ast_node_type: null` and `ast_recipe: null` when it was read by eye
   - the full extraction signature (type, params, return_type, docstring) — mirror the shape of §4's per-file extraction record so step 4 Priority 5 can merge it with the same code path used in normal mode.

   Then apply the §0 bullet 2 **public-reachability gate** to each matched symbol before recording it as a NEW_EXPORT: §0a has full source access, so resolve the symbol's module path and confirm barrel re-export or a fully-`pub` module chain. If it is unreachable (`pub(crate)` / private module), do **not** record `re-extracted`: drop it from the export-bearing set and re-queue the entry as a `metadata update` (rule R4, `reclassified: internal-unreachable`), exactly as the gate specifies. A re-extracted symbol that is not public API is not a documentable NEW_EXPORT. This is a resolution, not an `unresolved[]` failure (step 5): the symbol was found, just not public, so it does not trigger step 5's HALT.
5. **Track failures across all qualifying entries.** Collect every entry whose symbol was not found in any scanned remediation path, and every entry step 4 had nothing to scan for (`files_scanned: 0`), into an `unresolved[]` list. After processing every qualifying entry, if `unresolved[]` is non-empty: HALT with a consolidated report listing every unresolved entry (`name`, `severity`, `remediation_paths`, `files_scanned`, `exports_found_in_scan`). Template:

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
         files_scanned:     {count}
         exports_matched:   0

   Fix one of the following, then re-run update-skill:
     a) Add a `file:line` citation to the Gap Report `Source:` field.
     b) Edit the Remediation text to name the file(s) that actually contain the export(s).
     c) Downgrade the gap(s) to Medium/Low/Info (accepts the degraded documentation outcome).
   ```

   Exit with status `halted-for-remediation-path`, under `--dry-run` too (the run stops here instead of exiting `dry-run`). Step-04 merge has not run; no partial writes. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "re-extract:targeted-reextraction", reason: "..."}`).

6. **Success summary** — record `targeted_reextraction: {resolved_count, files_scanned, exports_matched, tier}` in workflow context. The evidence report (step 6 §4) surfaces this alongside the verified / moved / missing tally.

**Why halt instead of degrading to `unknown`:** a Critical or High gap by definition blocks skill usefulness (it is either missing documentation for a public API or a wrong signature), and a gap with a missing or unrecognized severity counts as blocking rather than being guessed to matter less. Silently writing `source_file: null` for a blocking gap produces a skill that passes re-test but still hides the broken behavior behind a placeholder. The halt forces the test report to carry usable remediation information: a one-time fix-up that is far cheaper than a downstream audit trying to track why the "repaired" skill still fails.

### 1. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the original brief or metadata:**

"**Docs-only skill detected.** This skill was generated from external documentation, not source code. Re-extraction will re-fetch the original `doc_urls` to check for updated content."

- Re-fetch each URL from `doc_urls` (from the brief or metadata) using whatever web fetching capability is available
- Extract updated API information with T3 `[EXT:{url}]` citations
- Build the updated extraction inventory from fetched content
- Skip all source code extraction below — proceed directly to the merge step (section 5 or equivalent)

**If `source_type: "source"` (default):** Continue with source extraction below.

### 1b. Determine Extraction Strategy by Tier

**Source access (every tier):** read every changed file from `{source_root}`. When `{source_tree_status}` is `ready` or `offline`, that is the tree init.md §6b prepared at `{target_commit}`, the commit step 2 compared, so detection, extraction, merge and write read one tree; otherwise it is the local source init.md §6 validated (in gap-driven mode, the tree §0.a confirmed holds the pinned commit). Do not fetch changed files through the gh contents API, zread or deepwiki: the gh contents API serves the default branch unless given a ref, and the zread and deepwiki indexes may sit at another commit, so a citation read there would not point into the commit this update records. If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists, HALT with status `blocked` per SKILL.md's source-tree rule (`error.phase` `re-extract:source-tree-missing`). If one changed file cannot be read, limit its analysis to the provenance-map baseline (State 2: each baseline entry keeps its own confidence label from compilation-time data) and warn: "Could not read {path} from {source_root}. Its analysis is limited to the provenance-map baseline."

**Quick tier (text pattern matching):**
- Extract function/class/type names via regex patterns
- Extract export statements via text matching
- Label every export T1-low (pattern-matched, not AST-verified) with `extraction_method: source-read` and `ast_node_type: null`

**Forge tier (AST structural extraction):**

Load and follow the **AST Extraction Protocol** from `{extractionPatternsData}`. Use the decision tree based on the number of changed files: prefer MCP `find_code()` for small sets, `find_code_by_rule()` with scoped YAML rules for medium sets, and CLI `--json=stream` with line-by-line streaming for large sets. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases.

- Extract: function signatures, type definitions, class members, exported constants
- Extract: parameter types, return types, JSDoc/docstring comments
- Label each export by the tool that produced it: an export an ast-grep rule matched is T1 (AST-verified structural truth) with `extraction_method: ast-grep`, the `kind` the matching recipe in `{extractionPatternsData}` declares as `ast_node_type` (copied, never inferred) and the recipe as `ast_recipe`; an export read by eye (ast-grep could not parse its file, the rules missed it, or the file was read instead of matched) is T1-low with `extraction_method: source-read` and `ast_node_type: null`

**Tier degradation handling (Forge/Forge+/Deep):** If ast-grep is unavailable or fails on individual files, follow `{tierDegradationRulesData}` for fallback strategy and user notification requirements. Silent degradation is forbidden — the user must always know when AST extraction was skipped.

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions, labeled by tool as at Forge tier
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: structural entries labeled by tool (T1 for an ast-grep match, T1-low for an export read by eye), T2 for semantic enrichment

**Tool resolution:** `ast_bridge` → ast-grep MCP tools (`find_code`, `find_code_by_rule`) or `ast-grep` CLI. `qmd_bridge` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Extract Changed Files

**Skip authoritative doc paths.** Before iterating the change manifest, build a skip set from `promoted_docs_new[]` (populated by step 2 §1b) and any existing `file_entries[]` entries with `file_type: "doc"` from the provenance map. These are documentation files tracked for drift detection only — they must not reach AST extraction, which would produce ghost entries on non-code content. If a change manifest entry matches the skip set, skip it silently and continue; doc-type drift is handled by step 2 Category D and step 4 Priority 6/7.

For each remaining file in the change manifest with status MODIFIED, ADDED, or RENAMED, launch a subprocess that:

1. Loads the source file
2. Performs tier-appropriate extraction (Quick/Forge/Forge+/Deep)
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

### 2b. CCC Semantic Ranking (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml:**

**Skip this section when `{source_tree_status}` is `ready` or `offline`:** the tree init.md §6b prepared has no ccc index, and a search there could start indexing a folder step 8 deletes. Log "ccc ranking skipped: private source tree" and treat all changes equally.

Before aggregating extraction results, use CCC to assess semantic significance of changes:

1. Run `ccc_bridge.search("{skill_name}", source_root, top_k=15)` — **Tool resolution:** `/ccc` skill search (Claude Code), ccc MCP (Cursor), `ccc search` (CLI) — to get the skill's most semantically central files
2. Cross-reference the change manifest files with CCC results
3. Files appearing in BOTH the change manifest AND CCC's top results are **semantically significant changes** — flag them for priority in the merge step
4. Store `{ccc_significant_changes: [{file, score}]}` in context

This helps the merge step (section 4) prioritize which changes are most likely to affect the skill's core content vs. peripheral modifications.

CCC failures: skip ranking silently, all changes treated equally.

**Note:** a local source keeps using its own index; `ccc search --refresh` updates it with what changed.

**IF `tools.ccc` is false:** Skip this section silently.

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

Aggregate all subprocess results into structured extraction data:

```
Extraction Results:
  files_extracted: [count]
  exports_extracted: [count]
  confidence_breakdown:
    T1: [count]
    T1-low: [count]
    T2: [count]

  Per-file extractions:
    {file_path}:
      exports:
        - name: {export_name}
          type: function|class|type|constant
          signature: {full signature}
          location: {file}:{start_line}-{end_line}
          confidence: T1|T1-low|T2
          extraction_method: ast-grep|source-read
          ast_node_type: {the kind the matching ast-grep recipe declares, or null}
          ast_recipe: {id of the recipe that matched, or the find_code pattern, or null}
          parameters: [{name, type}]
          return_type: {type}
          docstring: {summary}
          qmd_evidence: {if Deep tier}
```

### 5. Display Extraction Summary and Auto-Proceed

"**Re-Extraction Complete:**

| Metric | Count |
|--------|-------|
| Files extracted | {count} |
| Exports extracted | {count} |
| T1 (AST-verified) | {count} |
| T1-low (pattern-matched) | {count} |
| T2 (QMD-enriched) | {count} |

**Proceeding to merge with existing skill...**"

### 6. Route to Next Step

This step auto-proceeds — no user choices. Once all changed files are extracted and results compiled, load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode — skipping merge/validate/write.** Loading report..." and load `report.md` (NOT `{nextStepFile}`); it emits status `dry-run` describing what merge+write would have done. No artifact is modified on disk by this run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{nextStepFile}` (merge.md) to begin the merge operation.

