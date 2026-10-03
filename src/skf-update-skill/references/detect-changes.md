---
nextStepFile: 're-extract.md'
noChangeReportFile: 'report.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
# `{hashContentHelper}`: Category D's hash comparison. HALT if neither exists.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# `{buildChangeManifestHelper}`: §3's `build` (and §1's for a docs-only
# skill), §2.2's `deletion-ratio` and Category C's `rename-candidates`. HALT
# if neither exists.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# `{provenanceGapDispatchHelper}`: §1c's drift-report candidates. HALT if
# neither exists.
provenanceGapDispatchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-provenance-gap-dispatch.py'
  - '{project-root}/src/shared/scripts/skf-provenance-gap-dispatch.py'
# `{detectScriptsAssetsHelper}`: Category D's script and asset walk, as
# create-skill's. HALT if neither exists.
detectScriptsAssetsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-scripts-assets.py'
  - '{project-root}/src/shared/scripts/skf-detect-scripts-assets.py'
# `{newFileDiffHelper}`: Category D's NEW_FILE set difference, bundled with
# this skill.
newFileDiffHelper: 'scripts/skf-new-file-diff.py'
# `{resolveAuthoritativeFilesHelper}`: §1b's mirror. HALT if neither exists.
resolveAuthoritativeFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-authoritative-files.py'
  - '{project-root}/src/shared/scripts/skf-resolve-authoritative-files.py'
# `{classifyChangedFilesHelper}`: §2.1 Category A. HALT if neither exists.
classifyChangedFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-classify-changed-files.py'
  - '{project-root}/src/shared/scripts/skf-classify-changed-files.py'
# `{extractPublicApiHelper}`: §2.1 Category B's recipe runner. If neither
# exists, read the files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# `{structuralDiffHelper}`: §2.1 Category B's diff. HALT if neither exists.
structuralDiffProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-structural-diff.py'
  - '{project-root}/src/shared/scripts/skf-structural-diff.py'
# `{compareDocHashesHelper}`: §1's docs-only branch, the doc-hash comparison
# audit-skill's doc-drift step runs. HALT if neither exists.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Changes

## STEP GOAL:

Compare current source code state against the provenance map to produce a complete change manifest identifying every changed, added, deleted, moved, and renamed file and export since last extraction.

## Rules

- Focus only on detecting and classifying changes: extract only what Category B's diff reads (step 3 reuses it), and merge nothing
- Run §2.1's categories in order, A, then B, then C: each reads the one before. Fan Category B's reading out in parallel batches (Pattern 4) only when its file list is long

## Steps

The helpers below and step 3 pass their JSON to each other through `{run_dir}`, the run folder SKILL.md On Activation created.

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved. Nothing this step wrote is undone: it writes the skill brief only with a person's decision or a headless deferral (§1b, §1c), both of which stand, and the read-only modes write a copy in `{run_dir}` instead.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal or degraded>"}
SKF_JSON
```

Pass `--tree` when init.md §6b bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "detect-changes:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place, with the decisions the gates below recorded before it.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Scan Current Source State

**A docs-only skill** (`source_type: "docs-only"` in the brief or metadata.json) has no source tree for §2's categories to read: its drift is in the documents `doc_sources` records with their hashes. Compare them with the helper audit-skill's doc-drift step runs: resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {compareDocHashesHelper} compare-hashes "{skill_package}/metadata.json" > "{run_dir}/doc-hashes.json"
```

It fetches each URL with a recorded hash and buckets it `changed`, `unchanged`, `fetch_failed` or `skipped_null_hash`, with `stats`: never fetch or hash a URL by hand. On exit 2, no JSON, or no candidate resolves, HALT with status `blocked` (halt procedure: `phase: "detect-changes:doc-hashes"`, `path: "{skill_package}/metadata.json"`, `reason: "<its error, or skf-detect-docs.py is missing; re-install SKF>"`). Add `doc-fetch-failed: {url} ({reason})` to `warnings[]` for each `fetch_failed` entry (a document that could not be read is not drift), `doc-not-hashed: {url}` for each `skipped_null_hash` entry, and `doc-drift-not-checked: metadata.json records no doc_sources` when `stats.total_tracked` is 0. Then skip §1b to §2.2 and §3's build, and have the helper write the change manifest from that output, never by hand:

```bash
uv run {buildChangeManifestHelper} build --doc-hashes "{run_dir}/doc-hashes.json" > "{run_dir}/change-manifest.json"
```

It writes `{"mode": "docs-only", "no_changes", "changed_urls", "fetch_failed", "counts": {"docs_changed", "docs_fetch_failed"}}`. On exit 1 or no JSON: HALT with status `blocked` (halt procedure: `phase: "detect-changes:change-manifest"`, its stderr as `reason`). §4 then reports no change only when every hashed document matches (`changed_urls` is empty); otherwise §5 routes to step 3, whose §1 re-fetches the changed URLs, and step 5 records their new hashes from `{run_dir}/doc-hashes.json`.

`{source_root}` is the tree init.md §6b prepared at `{target_commit}` when `{source_tree_status}` is `ready` or `offline`, and otherwise the skill's local source. **If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists**, HALT with status `blocked` per SKILL.md's source-tree rule (halt procedure: `phase: "detect-changes:source-tree-missing"`, `path: "{source_root}"`, `reason: "source tree {source_root} disappeared mid-run"`): reading a missing tree would report every file deleted. §2.1's helpers walk `{source_root}` themselves: build no file inventory here.

**The brief this run reads.** Bind `{brief_path}` ← `{forge_data_folder}/{skill_name}/skill-brief.yaml`. When `detect_only_mode` or `dry_run_mode` is true and that file exists, copy it to `{run_dir}/skill-brief.yaml` and bind `{brief_path}` to the copy: §1b and §1c write each decision there, Category A reads the scope from there, and the brief itself stays as it was. Each amendment a read-only run writes to the copy is a proposed one: add `proposed-amendment: {action} {path} ({category}); not written: {--dry-run or --detect-only}` to `warnings[]` as you write it, and step 6 lists them with the change manifest.

### 1b. Discovered Authoritative Files Protocol (Mirror)

**Purpose:** mirror `skf-create-skill` §2a into update-skill. `skf-create-skill` §2a catches authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.) during **creation**, but a project may add these files *after* the skill was created. Without this mirror, update-skill would either miss the new file entirely (if it doesn't match the provenance map's file patterns) or classify it as a generic ADDED file in §2 Category A with no authoritative-file treatment. The mirror surfaces the discovery with the same P/S/U prompt create-skill uses, honoring any prior amendments.

**Skip this section entirely if:**

- `metadata.json.source_type == "docs-only"` (no source tree to scan), OR
- `{brief_path}` does not exist (a skill built without a brief, such as a quick skill): there is no scope or amendment to match a document against, and no brief to amend. Display `"Authoritative files mirror: skipped (no skill brief)."`

**Procedure (the helper and buckets of create-skill §2a):**

1. **Scan, classify and hash in one call.** Resolve `{resolveAuthoritativeFilesHelper}` ← first existing path in `{resolveAuthoritativeFilesProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {resolveAuthoritativeFilesHelper} resolve \
       --source-root "{source_root}" \
       --brief "{brief_path}" \
       [--provenance-map "{provenance_map_path}"]
   ```

   Pass `--provenance-map` whenever init.md §4 found one. It finds the files create-skill §2a looks for (`llms.txt`, `AGENTS.md`, `.cursorrules` and the like), sorts each into a bucket below, and hashes and previews each one a decision needs. Never walk, match or hash these files by hand. On exit 1 (a source root, brief or provenance map it cannot read), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:authoritative-files"`, `reason: "<its stderr>"`), showing its stderr.

2. **Apply each bucket:**
   - **`already_tracked[]`:** the provenance map names the file (`entries[]` or `file_entries[]`), so §2 detects its drift. No action here.
   - **`already_in_scope[]`:** the brief's scope already takes the file (a `scope.include` glob matches it, or its latest amendment promoted it), but the map has no row for it. Add the helper's `{path, heuristic, size_bytes, line_count, content_hash}` to `promoted_docs_new[]` (the list [P] Promote below fills), with no prompt, as create-skill §2a does. Display: `"In scope: {path} scheduled for file_entries write."`
   - **`pre_decided[]` with `prior_action: "promoted"`:** a prior run promoted it, but its `file_entries[]` row is missing (e.g. provenance-map was regenerated from source without re-reading amendments). Add it to `promoted_docs_new[]` with the helper's hash, size and line count so §4 merge writes a new `file_entries[]` row. No user prompt: the decision was already made. Display: `"Honoring prior amendment: promoted {path} scheduled for file_entries write."`
   - **`pre_decided[]` with `prior_action: "skipped"`:** a person declined promotion before. Honor the skip silently. No prompt, no action.
   - **`unresolved[]`:** no one has decided the file yet (a `prior_action` of `deferred-headless` marks one a headless run met and left for a person, the legacy `skipped` amendment with reason `headless: no user to prompt` included): continue to the prompt.

3. **Prompt.** For each `unresolved[]` candidate, present the same prompt as create-skill §2a, with the helper's `path`, `line_count`, `size_bytes`, `heuristic` and `preview` as it reported them (never recomputed):

   ```
   **New authoritative file discovered since skill creation**

   Path: {relative_path_from_source_root}
   Size: {line_count} lines, {bytes} bytes
   Matched heuristic: {basename}
   Provenance age: {days since skill creation}

   First 20 lines:
   {inline preview}

   This file was not present (or not in scope) when the skill was created. How should update-skill handle it?

   [P] Promote — extract in this update run AND amend brief for future runs
   [S] Skip    — leave out of scope AND record skip in amendments (no re-prompt)
   [U] Update  — halt this run and return to skf-brief-skill to refine scope
   ```

   Steps 4 and 5 are the decision protocol for a scope candidate, which §1c follows too, with the differences it names. Every amendment they append goes to `brief.scope.amendments[]` with `path: candidate.path`, `heuristic: {basename}`, `date: {today ISO}` and `workflow: "skf-update-skill"`, and every brief write goes to `{brief_path}` (the run folder's copy in a read-only mode), preserving all other fields.

4. **GATE [default: defer]**: in headless mode (`{headless_mode}` is true), promote nothing and decide nothing: whether a path belongs in scope needs a person. Leave every candidate out of this run and record it as deferred, so the next interactive run asks: append an amendment `action: "deferred-headless"`, `reason: "headless: no user to prompt; left for the next interactive run"`, except for a candidate whose `prior_action` is `deferred-headless`, which a headless run already recorded: write no second amendment for it. A non-interactive update run must never silently add files to scope, and never records a skip no person chose. **Also record one decision per candidate path**, from `{project-root}`:

   ```bash
   uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
   {"gate": "detect-changes.promoted-doc-prompt", "default_action": "S", "taken_action": "deferred-headless", "reason": "headless: no user to prompt; left for the next interactive run", "evidence": {"path": "<candidate.path>"}}
   SKF_JSON
   ```

5. **Apply decision:**

   - **[P] Promote:** append `candidate.path` to `brief.scope.include` as a literal glob, append an amendment `action: "promoted"`, `reason: {user-provided or auto: "discovered post-creation: matched heuristic {basename}"}`, and **write the amended brief back to disk immediately**. Then append the candidate's `{path, heuristic, size_bytes, line_count, content_hash}`, as the helper reported them, to `promoted_docs_new[]`, which this section keeps as the JSON array `{run_dir}/promoted-docs.json` (each record as the helper printed it; `[]` when none): step 5's `apply` writes a new `file_entries[]` row for each (merge Priority 7). Promoted docs do NOT go through step 3's code re-extraction, which would produce ghost entries on non-code files. Display: `"Promoted {path}: brief amended, scheduled as new file_entries row for file_type doc."`
   - **[S] Skip:** leave `scope.include` as it is, append an amendment `action: "skipped"`, `reason: {user-provided or auto: "user declined promotion at update-skill §1b"}`, and write the amended brief back to disk, so neither update-skill nor create-skill re-prompts in a later run. Display: `"Skipped {path}: decision recorded in amendments."`
   - **[U] Update:** HALT with status `halted-for-brief-refinement` (halt procedure: `phase: "detect-changes:authoritative-files"`, `path: "{brief_path}"`, `reason: "the user chose to refine the brief's scope for {path}"`) and display `"Halting update-skill. Re-run skf-brief-skill to refine scope for {skill_name}, then re-run skf-update-skill."`: no partial writes.

6. **Summary.** After all candidates are resolved (or none were found):

   - `"Authoritative files mirror: {N} candidates, {P} promoted, {S} skipped, {D} deferred to an interactive run, {A} decided by the brief (in scope or amended), {T} already tracked in provenance."`, with N the helper's `summary.candidates_total`, A its `already_in_scope_count` plus `pre_decided_count` and T its `already_tracked_count`.
   - If N = 0: `"Authoritative files mirror: no candidates."`

**Record for evidence report:** append the record `authoritative_files_mirror: {candidates: N, promoted: P, skipped: S, deferred: D, pre_decided: A, already_tracked: T, decisions: [{path, action, heuristic, reason}]}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `authoritative_files_mirror`: step 5 §4 reads it there, never from context.

### 1c. Major-Version Scope Reconciliation (Pre-Detection)

**Purpose:** §1b handles new authoritative-doc files; §1c handles new **code globs** that fall outside the original scope when upstream restructures (rebrand, package restructure, major-version rewrite) so the brief's `scope.include` no longer reflects the real public API. Without it, update-skill silently misses the new public surface and pays the gap cost on every future update.

**Skip this section entirely if:**

- `metadata.json.source_type == "docs-only"` (no source tree to scope), OR
- `{brief_path}` does not exist (a skill built without a brief, such as a quick skill): there is no scope to expand and no brief to amend. Display `"Scope reconciliation: skipped (no skill brief)."`, OR
- No audit drift report is available at the path computed in step 1 below.

**Procedure:**

1. **Discover, parse, and reconcile in one call.** The helper handles drift-report discovery (glob, timestamp-DESC sort, latest wins), Out-of-Scope section extraction (both `## Out-of-Scope Observations` and `### Out-of-Scope New Public API` under `## Remediation Suggestions` heading shapes), candidate parsing (bullet and table markdown formats), and amendment reconciliation against `brief.scope.amendments[]`:

   ```bash
   uv run {provenanceGapDispatchHelper} dispatch \
       --skill-name "{skill_name}" \
       --baseline-version "{baseline_version}" \
       --forge-data-folder "{forge_data_folder}" \
       --brief "{brief_path}"
   ```

   On exit 1 (a forge folder it cannot read, or a brief that exists but cannot be read), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:scope-reconciliation"`, `path: "{brief_path}"`, `reason: "<its stderr>"`).

   Output envelope:

   ```json
   {
     "status": "no-report" | "no-candidates" | "candidates-found",
     "report_path": "<abs path>" | null,
     "candidates_total": N,
     "classified": [
       {
         "path": "<glob or file path>",
         "evidence": "<one-liner>",
         "status": "already-in-scope" | "pre-decided-skipped"
                 | "pre-decided-demoted" | "unresolved",
         "prior_action": "promoted" | "skipped"
                       | "demoted-include" | "demoted-exclude"
                       | "deferred-headless" | null
       }, ...
     ],
     "summary": {"pre_decided_count": N, "unresolved_count": N}
   }
   ```

2. **Dispatch on `status`:**

   - **`no-report`** — no drift report under `{forge_data_folder}/{skill_name}/{baseline_version}/`. **Skip §1c entirely** — proceed to step 6's summary line (omit). §2.2's post-detection deletion-ratio trigger still catches major restructures.
   - **`no-candidates`** — report exists but the Out-of-Scope section is absent or empty. Proceed to step 6's summary line with `"no out-of-scope observations in drift report."`
   - **`candidates-found`** — iterate `classified[]`:
     - `status: "already-in-scope"` → skip silently (`prior_action: "promoted"`).
     - `status: "pre-decided-skipped"` → honor silently (`prior_action: "skipped"`).
     - `status: "pre-decided-demoted"` → record as `pre_decided`; do not re-prompt (`prior_action` ∈ `demoted-include`, `demoted-exclude`).
     - `status: "unresolved"` → continue to step 3 (user prompt). A `prior_action` of `deferred-headless` marks a path a headless run deferred (the legacy `skipped` amendment with reason `headless: no user to prompt` reads the same): a person decides it now.

   **Note:** the Out-of-Scope section is an optional audit-skill output and is often absent or empty — new-file detection is update-skill's job (§1b/§2.2), not audit-skill's — so the `no-report` / `no-candidates` paths above are the common case.

3. **Prompt for each unresolved candidate.** Present the same menu shape as §1b:

   ```
   **Out-of-scope new public API discovered**

   Path:          {candidate.path}
   Evidence:      {evidence from drift report}
   Drift report:  {report relative path}

   This path was not in the brief's `scope.include` when the skill was created. How should update-skill handle it?

   [P] Promote — add to scope.include AND extract in this run
   [S] Skip    — leave out of scope AND record skip in amendments (no re-prompt)
   [U] Update  — halt this run and return to skf-brief-skill to refine scope
   ```

4. **GATE [default: defer]**: in headless mode (`{headless_mode}` is true), defer each candidate as §1b step 4 does, with this section's amendment fields (step 5) and the gate `detect-changes.scope-expansion` in its decision record: a non-interactive update run must never silently expand scope.

5. **Apply decision** as §1b step 5 does, with these differences:

   - **Amendment fields:** every amendment carries `category: "scope-expansion"` and the candidate's `evidence: {evidence string}` in place of `heuristic`. [P]'s auto reason is "out-of-scope new public API: drift report {report basename}", and [S]'s "user declined promotion at update-skill §1c".
   - **Promotion target:** [P] appends the path to `scope.include` as the drift report gives it, wildcards kept, and adds no `promoted_docs_new[]` entry and no `--exclude`: §2 Category A lists the files a promoted code glob matches as ADDED, and step 3 extracts them, unlike §1b's documents. Display: `"Promoted {path}: brief amended; §2 Category A will pick up matching files as ADDED."`
   - **[S]** leaves `scope.exclude` as it is too, and **[U]** halts with `phase: "detect-changes:scope-reconciliation"`.

6. **Summary:** After all candidates are resolved (or none were found):

   - `"Scope reconciliation: {N} candidates, {P} promoted, {S} skipped, {D} deferred to an interactive run, {A} pre-decided from amendments."`
   - If N = 0 (section absent or empty): `"Scope reconciliation: no out-of-scope observations in drift report."`
   - If §1c was skipped entirely (a docs-only skill, no skill brief or no drift report): omit this line; §2.2 will still run.

**Record for evidence report:** append the record `scope_reconciliation_pre: {drift_report: path, candidates: N, promoted: P, skipped: S, deferred: D, pre_decided: A, decisions: [{path, action, evidence}]}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `scope_reconciliation_pre` (none when §1c was skipped).

### 2. Compare Against Provenance Map

**In degraded mode (no provenance map),** run Category A without `--provenance-map`: its `full` mode lists every in-scope file as MODIFIED (with no brief, `--language` scopes the walk), so step 3 re-extracts every export. Run Category B's steps 1 and 2 only (re-extract.md §4's records come from them), and skip its step 3, Category C, Category D and §2.2: there is no map to compare against.

#### 2.0 Change-Detection Excludes

`promoted_docs_new[]` (§1b) holds documents that reach the provenance map as `file_entries[]` rows through step 4 Priority 7, never through code extraction. Category A leaves each of them out with `--exclude`: each is in scope and the map does not name it yet, so it would read as ADDED, and step 3 would send it to AST extraction, producing ghost entries. A path a `file_entries[]` row already names (a tracked document, script or asset) needs no exclude: Category A never lists one, and Category D compares its hash.

#### 2.1 Categories A, B and C, in Order

Category B reads the files Category A lists, and Category C pairs what A and B leave deleted and added. Category D (below) needs neither.

**Category A: file-level changes.** Resolve `{classifyChangedFilesHelper}` ← first existing path in `{classifyChangedFilesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {classifyChangedFilesHelper} classify \
    --source-root "{source_root}" \
    [--provenance-map "{provenance_map_path}"] \
    [--brief "{brief_path}"] \
    [--language "{language}"] \
    --tree-status "{source_tree_status}" \
    --diff-status "{source_diff_status}" \
    --changed-files "{source_changed_files}" \
    [--exclude "<promoted document path>"] \
    --lists-dir "{run_dir}" \
    > "{run_dir}/category-a.json"
```

Pass `--provenance-map` whenever init.md §4 found one; `--brief` (as §1c left it) when that file exists (a skill built without a brief, such as a quick skill after its degraded update, has none); `--language` when metadata.json records one; one `--exclude` for each `promoted_docs_new[]` path; and the three init.md §6b values as bound (an empty or `null` value counts as not given). In a tree it takes the changed files from git's list at `{source_changed_files}`, never from file times or sizes, which a checkout rewrites. Add each of its `warnings[]` to `warnings[]`. It writes `{run_dir}/modified-files.json` (the files Category B diffs) and `{run_dir}/extract-files.json` (the modified and added files and each moved file's new path, which Category B and step 3 read): never retype or re-derive a list. On exit 1 (an input it cannot read, named on stderr), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-a"`, the helper's message as `reason`).

**Category B: export-level changes.** Skip it when `{run_dir}/extract-files.json` lists no file.

1. **The recipe runner.** At Forge tier and above, resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {extractPublicApiHelper} --mode full \
       --source-root "{source_root}" \
       --files-from "{run_dir}/extract-files.json" \
       [--language "{language}"] \
       [--scope-type "{scope_type}"] \
       --head-cap 0 \
       -o "{run_dir}/extraction.json"
   ```

   Pass `--language` and `--scope-type` when metadata.json records them. It takes no `--brief`: Category A applied the scope, and a tracked file the brief's scope leaves out (gap-driven.md §1's rule R1 excludes a rescoped export's file) keeps its exports. `--head-cap 0` keeps every match, since a dropped one would read as a deleted export. Step 3 reads this file and never runs the runner again. **Exit 1** (`incomplete`): run it once more; when still incomplete, step 2 below reads by eye each listed file with no export in `exports[]`. **Exit 2 or 3, no JSON, no candidate resolves, or Quick tier:** write `{"exports": []}` to `{run_dir}/extraction.json`; step 2 reads every listed file by eye (at Quick tier, by text pattern). Tell the user which files were read by eye.

2. **What the recipes do not record.** Workers, in parallel batches (Pattern 4) when the list is long, read the modified and added files and each return ONLY `{"exports": [...]}`, with no prose and no fences. For each function export the runner found whose `params` it left null (it could not read the signature): `export_name` and `source_file` as it wrote them, with `params` (each parameter as the source writes it, `name: type`, the form the provenance map's `params` hold) and `return_type` (null when there is none), read at its `source_line`. For each export it could not find (a name `entry_point_diff.extraction_gaps[]` lists, a form Known Limitation #11 in `{extractionPatternsData}` lists, an export of a file `file_issues[]` names or that was read by eye): the same, plus `export_type`, `source_line`, `confidence: T1-low` and `extraction_method: source-read`. Write the union of their `exports` arrays to `{run_dir}/export-details.json`.

3. **The diff.** Resolve `{structuralDiffHelper}` ← first existing path in `{structuralDiffProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {structuralDiffHelper} "{provenance_map_path}" "{run_dir}/extraction.json" \
       --current-extra "{run_dir}/export-details.json" \
       --files "{run_dir}/modified-files.json" \
       -o "{run_dir}/category-b-diff.json"
   ```

   Exit 0 (no difference) and exit 1 (differences) both wrote the diff, which §3's helper maps onto Category B: never re-diff by eye. On exit 2, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-b"`, the helper's `error` as `reason`).

**Category C: rename detection.** The fixed rules pair Category A's `deleted` files with its `added` ones, and the diff's `removed[]` exports with its `added[]` ones and with the added files' exports, by script, never by eye. From `{project-root}`, run:

```bash
uv run {buildChangeManifestHelper} rename-candidates \
    --category-a "{run_dir}/category-a.json" \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    --provenance-map "{provenance_map_path}" \
    [--extraction "{run_dir}/extraction.json"] \
    [--export-details "{run_dir}/export-details.json"] \
    --tier "{forge_tier}" \
    --source-root "{source_root}" \
    [--sizes-commit "{source_commit}"] \
    -o "{run_dir}/category-c.json"
```

Pass `--category-b-diff`, `--extraction` and `--export-details` when Category B wrote them, and `--sizes-commit` only when `{source_tree_status}` is `ready` or `offline`: in that tree the helper reads a deleted file's size at the pinned commit (`git cat-file -s`), while in a local source the file is gone and the size test is skipped. Skip Category C in degraded mode (there is no map). Content similarity above 80% (fixed, not configurable) is a rename: at Quick tier a file size within 20% and export names that overlap above 70% (export names above 80% alike), at Forge and above equal export signatures. The helper keeps a pair only when it is each side's best match, so a tie pairs nothing, and writes `category_c` (`renamed_files: [{old_path, new_path}]`, `renamed_exports: [{old_name, new_name, file, old_file?}]`, `old_file` only when it differs from `file`), the `evidence` of each pair and what it left `unpaired`. On exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-c"`, its stderr as `reason`). Category A's `moved_files[]` (same-content moves) are not Category C's to pair, and §3's helper takes each pair out of the lists it was found in.

**CCC check (Forge+ and Deep, a local source only).** When `tools.ccc` is true and `{source_tree_status}` is neither `ready` nor `offline` (the tree init.md §6b prepared has no ccc index, and a search there could start indexing a folder step 7 deletes), you may pair what the rules left in `unpaired`: a deleted file with an added one that CCC ranks as the same code (`ccc_bridge.search` over the deleted file's export names; **Tool resolution:** `/ccc` skill search, ccc MCP or `ccc search`). This is the one judgment in Category C: add a pair only on CCC's evidence, name it in the report as a CCC pairing, and never undo a pair the rules made. Write only these pairs, with each path as `unpaired` gives it, to `{run_dir}/ccc-pairs.json` as `{"renamed_files": [{"old_path": "<deleted>", "new_path": "<added>"}]}`; the helpers below read `{run_dir}/category-c.json` themselves, so never copy its pairs.

**Category D: script, asset and tracked-document file changes.**

Run the bulk comparison once, keeping its output in the run folder (step 5's `apply` reads it):

```bash
uv run {hashContentHelper} compare "{source_root}" \
    --provenance-map "{provenance_map_path}" \
    > "{run_dir}/category-d-compare.json"
```

On exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-d"`, its stderr as `reason`).

The helper emits:

```json
{
  "comparisons": [
    {"source_file": "...", "classification": "UNCHANGED|MODIFIED_FILE|DELETED_FILE",
     "stored_hash": "sha256:...", "current_hash": "sha256:..."|null,
     "current_size_bytes": N|null}, ...
  ],
  "stats": {"total": N, "unchanged": U, "modified": M, "deleted": D}
}
```

The compare helper reports only tracked files; NEW_FILE detection (a file present in source but absent from the provenance map) is a set-difference, so it runs through a script rather than the prompt. Pipe the same deterministic detector create-skill step 3 §4c uses (resolved via `detectScriptsAssetsProbeOrder`) into `{newFileDiffHelper}`, which subtracts the provenance map's `file_entries[].source_file` and sets aside user-authored `[MANUAL]` paths:

```bash
uv run {detectScriptsAssetsHelper} detect "{source_root}" \
    | uv run {newFileDiffHelper} "{provenance_map_path}" \
    > "{run_dir}/new-files.json"
```

It writes `{"new_files":[{source_file, kind}], "skipped_manual":[...], "already_tracked":[...], "stats":{...}}`. §3's `build` reads both files, typing each compare row by its `file_entries[]` row's `file_type` and each new file by its `kind`: sort no row by hand. `skipped_manual[]` are user-authored files under `scripts/[MANUAL]/` or `assets/[MANUAL]/`, preserved and not touched; `already_tracked[]` were handled by the compare above.

**Write the category JSON** to `{run_dir}/categories.json`, where §2.2 and §3 read it beside the helper files: the two flags, `degraded_mode` and `update_mode: "normal"`. Category C stays in the files its steps wrote, which §2.2, §3 and step 5's `apply` take as `--category-c` and `--ccc-pairs`:

```bash
cat > "{run_dir}/categories.json" <<'SKF_JSON'
{"degraded_mode": <bool>, "update_mode": "normal"}
SKF_JSON
```

#### 2.2 — Major-Version Scope Reconciliation (Post-Detection)

**Purpose:** §1c catches the major-version case when an audit drift report supplies explicit candidates. §2.2 is the safety net that fires when no audit was run (or audit emitted no out-of-scope section): it inspects the just-built Category A/B results for the deletion-ratio signature of a major-version restructure and gives the user an off-ramp before §3 commits the change manifest.

**Trigger computation:** skip §2.2 in degraded mode (there is no map). Otherwise invoke the helper with the files §3 reads, plus the provenance map:

```bash
uv run {buildChangeManifestHelper} deletion-ratio \
    --provenance-map "{provenance_map_path}" \
    --category-a "{run_dir}/category-a.json" \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    [--category-c "{run_dir}/category-c.json"] \
    [--ccc-pairs "{run_dir}/ccc-pairs.json"] \
    --input "{run_dir}/categories.json"
```

Pass `--category-b-diff`, `--category-c` and `--ccc-pairs` when Category B, Category C and the CCC check wrote them.

The helper handles the two skip conditions internally: when the input has `degraded_mode: true`, or the provenance has zero entries, it returns `skip_reason` set and `should_trigger: false`. `should_trigger` fires when the deletion ratio reaches the fixed bundled threshold of 50% (`ratio >= 0.50`, baked into the helper, not configurable). The output envelope:

```json
{
  "skip_reason": "degraded-mode" | "zero-provenance-exports" | null,
  "deleted_export_count": N,
  "total_provenance_exports": N,
  "deletion_ratio": 0.X,
  "deleted_file_count": N,
  "added_in_scope_count": N,
  "renamed_or_moved_count": N,
  "should_trigger": <bool>
}
```

If `skip_reason` is non-null OR `should_trigger` is false, skip the prompt and continue to §3. If `should_trigger` is true, present the prompt below.

**Prompt:**

```
**Major-version scope shift detected**

Deleted exports:        {deleted_export_count} of {total_provenance_exports} ({percent}%)
Deleted files:          {deleted_file_count}
Added files (in scope): {added_in_scope_count}
Renamed/moved exports:  {renamed_or_moved_count}

The upstream surface appears to have been substantially replaced. The brief's
`scope.include` patterns may no longer reflect the real public API.

[C] Continue — proceed with re-extraction; the deletion is intentional
[B] Brief    — halt and re-run skf-brief-skill to refine scope first
[A] Audit    — halt and run skf-audit-skill to map the new surface, then re-run update-skill
```

**GATE [default: C]**: in headless mode (`{headless_mode}` is true), auto-select `[C] Continue`, append the record `scope_reconciliation_post: {trigger: "deletion-ratio", ratio: X, decision: "headless-continue"}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `scope_reconciliation_post` (step 5 §4 lists it in the evidence report), and surface the warning in step 6's report. A non-interactive run must not silently halt, but the user must be able to see the signal post-hoc. **Also record the decision**, from `{project-root}`:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "detect-changes.deletion-ratio", "default_action": "C", "taken_action": "C", "reason": "headless: deletion-ratio threshold exceeded but no user to halt", "evidence": {"deletion_ratio": <ratio>, "deleted_export_count": <N>, "total_provenance_exports": <T>}}
SKF_JSON
```

**Apply decision:**

- **[C] Continue:** unless the headless branch above appended its record, append `scope_reconciliation_post: {trigger: "deletion-ratio", ratio: X, decision: "continue"}` to `{run_dir}/evidence-records.jsonl` the same way, and proceed to §3.
- **[B] Brief:** HALT with status `halted-for-brief-refinement` (halt procedure: `phase: "detect-changes:deletion-ratio"`, `reason: "the user chose to refine the brief's scope: {deleted_export_count} of {total_provenance_exports} exports deleted"`). Display: `"Halting update-skill. Re-run skf-brief-skill to refine scope for {skill_name}, then re-run skf-update-skill."` The change manifest is discarded: no partial writes.
- **[A] Audit:** HALT with status `halted-for-audit` (halt procedure: `phase: "detect-changes:deletion-ratio"`, `reason: "the user chose to audit the new surface first"`). Display: `"Halting update-skill. Run skf-audit-skill against {skill_name} to map the new surface: its drift report will feed §1c on the next update-skill run."` The change manifest is discarded.

### 3. Build Change Manifest

Hand the helper files and the category JSON to the helper, which takes Category A from the classify output, maps the diff onto Category B, and takes each Category C pair out of the lists it was found in:

```bash
uv run {buildChangeManifestHelper} build \
    [--category-a "{run_dir}/category-a.json"] \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    [--category-c "{run_dir}/category-c.json"] \
    [--ccc-pairs "{run_dir}/ccc-pairs.json"] \
    [--file-compare "{run_dir}/category-d-compare.json" --provenance-map "{provenance_map_path}"] \
    [--new-files "{run_dir}/new-files.json"] \
    --input "{run_dir}/categories.json" \
    > "{run_dir}/change-manifest.json"
```

Pass each helper file its category wrote. On exit 1 or no JSON: HALT with status `blocked` (halt procedure: `phase: "detect-changes:change-manifest"`, its stderr as `reason`).

The helper emits the unified manifest envelope:

```json
{
  "no_changes": <bool>,
  "degraded_mode": <bool>,
  "counts": {
    "files_changed": N, "files_added": N, "files_deleted": N, "files_moved": N,
    "exports_modified": N, "exports_new": N, "exports_deleted": N,
    "exports_renamed": N, "exports_moved": N,
    "scripts_modified": N, "scripts_added": N, "scripts_deleted": N,
    "assets_modified": N, "assets_added": N, "assets_deleted": N,
    "docs_modified": N, "docs_deleted": N
  },
  "total_export_changes": N,
  "per_file": [
    {"file_path": "...", "status": "MODIFIED|ADDED|DELETED|MOVED",
     "exports_affected": [{name, change_type, old_line, new_line}, ...]}
  ],
  "category_d": {"scripts_modified": [...], ..., "docs_deleted": [...]}
}
```

`per_file` entries are sorted MODIFIED → ADDED → DELETED → MOVED, then alphabetically within each status group, so downstream stages can rely on stable ordering. MOVED entries include an extra `old_path` field. `category_d` lists the paths behind the `scripts_*`, `assets_*` and `docs_*` counts: a `docs_*` path is a tracked document, which only Category D detects, so a change to one alone is a change. `{run_dir}/change-manifest.json` is the change manifest: step 3, step 6 and step 5's `apply` read it there, so it survives a compacted context.

### 4. Check for No-Change Shortcut

**If zero changes detected across all categories** (`no_changes` is true in `{run_dir}/change-manifest.json`; for a docs-only skill, when every hashed document matched):

"**No changes detected.** Source code matches provenance map exactly.

The skill `{skill_name}` is current — no update needed.

**Skipping to report step...**"

→ Skip steps 3-5, immediately load {noChangeReportFile} with "no changes" status. A `--detect-only` or `--dry-run` run takes this route too and stays read-only there: report.md §1 prints its line with no result file and never runs `{onCompleteCommand}`.

### 5. Display Change Summary and Route

Display one line from the change manifest: "**Detected:** {modified} modified, {added} added, {deleted} deleted and {moved} moved or renamed files; {total_export_changes} exports affected." The report (step 6) shows the full counts.

For a docs-only skill, show instead the documents that changed (`changed_urls`) and the ones that could not be fetched.

This step auto-proceeds — no user choices. Once the change manifest is fully built, load and fully read the next file, then execute it, per the branch that applies:

- **`detect_only_mode == true`** → display "**Detect-only mode: skipping re-extract, merge and write.** Loading report..." and load `{noChangeReportFile}` (report.md), which emits status `detect-only`. Do not load `{nextStepFile}`.
- **No changes detected** (section 4) → load `{noChangeReportFile}` (report.md), which emits status `no-changes`.
- **Otherwise** → display "**Proceeding to re-extraction of {affected_file_count} changes...**" and load `{nextStepFile}` (re-extract.md) to begin re-extraction.

