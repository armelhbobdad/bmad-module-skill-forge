---
nextStepFile: 'detect-changes.md'
# `{resolveAuthoritativeFilesHelper}`: §1b's mirror. HALT if neither resolves.
resolveAuthoritativeFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-authoritative-files.py'
  - '{project-root}/src/shared/scripts/skf-resolve-authoritative-files.py'
# `{provenanceGapDispatchHelper}`: §1c's drift-report candidates.
# HALT if neither resolves.
provenanceGapDispatchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-provenance-gap-dispatch.py'
  - '{project-root}/src/shared/scripts/skf-provenance-gap-dispatch.py'
# `{writeSkillBriefHelper}`: §1b's and §1c's scope decisions. If neither
# exists, each decision is a `brief-not-amended` warning and the next run asks
# again.
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
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

# Step 2a: Reconcile the Brief's Scope

## STEP GOAL:

Bind the skill brief this run reads, then reconcile its scope before step 2 compares the source: surface each authoritative file a project added since the skill was created (§1b) and each out-of-scope path an audit drift report names (§1c), and record each decision in the brief.

## Rules

- Focus only on the brief's scope: decide each candidate path and record the decision; compare no source file with the provenance map
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below. Nothing this step wrote is undone: it writes the skill brief only with a person's decision or a headless deferral (§1b, §1c), both of which stand, and the read-only modes write a copy in `{run_dir}` instead.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal or degraded>"}
SKF_JSON
```

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "detect-changes:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place, with the decisions the gates below recorded before it.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

**The brief this run reads.** Bind `{brief_path}` ← `{forge_data_folder}/{skill_name}/skill-brief.yaml`. When `detect_only_mode` or `dry_run_mode` is true and that file exists, copy it to `{run_dir}/skill-brief.yaml` and bind `{brief_path}` to the copy: §1b and §1c write each decision there, Category A reads the scope from there, and the brief itself stays as it was. Each amendment a read-only run writes to the copy is a proposed one: add `proposed-amendment: {action} {path} ({category}); not written: {--dry-run or --detect-only}` to `warnings[]` for each amendment `amend` appended (its `appended`), never for one it skipped as a duplicate (`skipped_duplicates`), and step 6 lists them with the change manifest.

`{source_root}` is the tree load-baseline.md §6b prepared at `{target_commit}` when `{source_tree_status}` is `ready` or `offline`. **If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists**, HALT with status `blocked` per SKILL.md's source-tree rule (halt procedure: `phase: "detect-changes:source-tree-missing"`, `path: "{source_root}"`, `reason: "source tree {source_root} disappeared mid-run"`): reading a missing tree would report every file deleted.

### 1b. Discovered Authoritative Files Protocol (Mirror)

**Purpose:** a project can add authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules` and the like) after the skill was created; surface each with create-skill §2a's [P]/[S]/[U] prompt.

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

   Pass `--provenance-map` whenever load-baseline.md §4 found one. It finds the files create-skill §2a looks for (`llms.txt`, `AGENTS.md`, `.cursorrules` and the like), sorts each into a bucket below, and hashes and previews each one a decision needs. Never walk, match or hash these files by hand. On exit 1 (a source root, brief or provenance map it cannot read), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:authoritative-files"`, `reason: "<its stderr>"`), showing its stderr.

2. **Apply each bucket:**
   - **`already_tracked[]`:** the provenance map names the file (`entries[]` or `file_entries[]`), so detect-changes.md §2 detects its drift. No action here.
   - **`already_in_scope[]`:** the brief's scope already takes the file (a `scope.include` glob matches it, or its latest amendment promoted it), but the map has no row for it. Add the helper's `{path, heuristic, size_bytes, line_count, content_hash}` to `promoted_docs_new[]` (the list [P] Promote below fills), with no prompt, as create-skill §2a does. Display: `"In scope: {path} scheduled for file_entries write."`
   - **`pre_decided[]` with `prior_action: "promoted"`:** a prior run promoted it, but its `file_entries[]` row is missing (e.g. provenance-map was regenerated from source without re-reading amendments). Add it to `promoted_docs_new[]` with the helper's hash, size and line count so step 5's `apply` writes a new `file_entries[]` row. No user prompt: the decision was already made. Display: `"Honoring prior amendment: promoted {path} scheduled for file_entries write."`
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

   [P] Promote: extract in this update run AND amend brief for future runs
   [S] Skip:    leave out of scope AND record skip in amendments (no re-prompt)
   [U] Update:  halt this run and return to skf-brief-skill to refine scope
   ```

   Steps 4 and 5 are the decision protocol for a scope candidate, which §1c follows too, with the differences it names. Each decision goes to `{brief_path}` (the run folder's copy in a read-only mode) at once, in one call: resolve `{writeSkillBriefHelper}` ← first existing path in `{writeSkillBriefProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {writeSkillBriefHelper} amend --target "{brief_path}" <<'SKF_BRIEF_DECISION'
   {"include": ["{path}"], "amendments": [{"path": "{path}", "action": "promoted|skipped|deferred-headless", "reason": "{reason}", "heuristic": "{basename}", "date": "{today ISO}", "workflow": "skf-update-skill"}]}
   SKF_BRIEF_DECISION
   ```

   `{path}` is `candidate.path`. Pass `include` for [P] only. Write each payload value as a JSON string: escape `"` and `\`, write a line break or tab inside a value as `\n` or `\t`, and write every path with `/`. `amend` appends it to `scope.include` only when that list is not empty (an empty include already covers every file, and one path would narrow it: the `promoted` amendment records the decision either way), skips an amendment whose path and category already have that action as their latest, keeps every other field and the previous brief as `{brief_path}.bak`, and writes the brief atomically. On a non-zero exit, no JSON or no candidate, add `brief-not-amended: {path}: {its stderr, or skf-write-skill-brief.py is missing}` to `warnings[]` and go on: the next run asks again.

4. **GATE [default: defer]**: in headless mode (`{headless_mode}` is true), promote nothing and decide nothing: whether a path belongs in scope needs a person. Leave every candidate out of this run and record it as deferred, so the next interactive run asks: write an amendment `action: "deferred-headless"`, `reason: "headless: no user to prompt; left for the next interactive run"`; `amend` skips a deferral the brief already holds. A non-interactive update run must never silently add files to scope, and never records a skip no person chose. **Also record one decision per candidate path**, from `{project-root}`:

   ```bash
   uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
   {"gate": "detect-changes.promoted-doc-prompt", "default_action": "S", "taken_action": "deferred-headless", "reason": "headless: no user to prompt; left for the next interactive run", "evidence": {"path": "<candidate.path>"}}
   SKF_JSON
   ```

5. **Apply decision:**

   - **[P] Promote:** write the decision with `include: ["{path}"]` and an amendment `action: "promoted"`, `reason: {user-provided or auto: "discovered post-creation: matched heuristic {basename}"}`. When that call exited 0 with JSON, append the candidate's `{path, heuristic, size_bytes, line_count, content_hash}`, as the helper reported them, to `promoted_docs_new[]`, which this section keeps as the JSON array `{run_dir}/promoted-docs.json` (each record as the helper printed it; `[]` when none): step 5's `apply` writes a new `file_entries[]` row for each. A promotion the brief could not record (its `brief-not-amended` warning) is not tracked either, and the next run asks again: display `"Not promoted {path}: the skill brief could not record it; the next run asks again."` instead of the line below. Promoted docs do NOT go through step 3's code re-extraction, which would produce ghost entries on non-code files. Display: `"Promoted {path}: brief amended, scheduled as new file_entries row for file_type doc."`
   - **[S] Skip:** write the decision with no `include` and an amendment `action: "skipped"`, `reason: {user-provided or auto: "user declined promotion at update-skill §1b"}`, so neither update-skill nor create-skill re-prompts in a later run. Display: `"Skipped {path}: decision recorded in amendments."`
   - **[U] Update:** HALT with status `halted-for-brief-refinement` (halt procedure: `phase: "detect-changes:authoritative-files"`, `path: "{brief_path}"`, `reason: "the user chose to refine the brief's scope for {path}"`) and display `"Halting update-skill. Re-run skf-brief-skill to refine scope for {skill_name}, then re-run skf-update-skill."`: no partial writes.

6. **Summary.** After all candidates are resolved (or none were found):

   - `"Authoritative files mirror: {N} candidates, {P} promoted, {S} skipped, {D} deferred to an interactive run, {A} decided by the brief (in scope or amended), {T} already tracked in provenance."`, with N the helper's `summary.candidates_total`, A its `already_in_scope_count` plus `pre_decided_count` and T its `already_tracked_count`.
   - If N = 0: `"Authoritative files mirror: no candidates."`

**Record for evidence report:** append the record `authoritative_files_mirror: {candidates: N, promoted: P, skipped: S, deferred: D, pre_decided: A, already_tracked: T, decisions: [{path, action, heuristic, reason}]}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `authoritative_files_mirror`: step 5 §4 reads it there, never from context.

### 1c. Major-Version Scope Reconciliation (Pre-Detection)

**Purpose:** catch new code globs outside the brief's `scope.include` after an upstream restructure (rebrand, package restructure, major-version rewrite).

**Skip this section entirely if:**

- `metadata.json.source_type == "docs-only"` (no source tree to scope), OR
- `{brief_path}` does not exist (a skill built without a brief, such as a quick skill): there is no scope to expand and no brief to amend. Display `"Scope reconciliation: skipped (no skill brief)."`, OR
- No audit drift report is available at the path computed in step 1 below.

**Procedure:**

1. **Discover, parse, and reconcile in one call.** The helper handles drift-report discovery (glob, timestamp-DESC sort, latest finished report wins: one whose frontmatter `stepsCompleted` lists `report`, so the partial report a halted or stopped audit leaves never hides the last finished one), Out-of-Scope section extraction (both `## Out-of-Scope Observations` and `### Out-of-Scope New Public API` under `## Remediation Suggestions` heading shapes), candidate parsing (bullet and table markdown formats), and amendment reconciliation against `brief.scope.amendments[]`:

   ```bash
   uv run {provenanceGapDispatchHelper} dispatch \
       --skill-name "{skill_name}" \
       --baseline-version "{baseline_version}" \
       --forge-data-folder "{forge_data_folder}" \
       --brief "{brief_path}"
   ```

   On exit 1 (a forge folder it cannot read, a brief that exists but cannot be read, or a helper beside it that cannot be loaded), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:scope-reconciliation"`, `path: "{brief_path}"` only when its stderr names the brief, `reason: "<its stderr>"`).

2. **Dispatch on `status`:**

   - **`no-report`**: no finished drift report under `{forge_data_folder}/{skill_name}/{baseline_version}/` (a report a halted audit left counts as none). **Skip §1c entirely**: proceed to step 6's summary line (omit). detect-changes.md §2.2's post-detection deletion-ratio trigger still catches major restructures.
   - **`no-candidates`**: report exists but the Out-of-Scope section is absent or empty. Proceed to step 6's summary line with `"no out-of-scope observations in drift report."`
   - **`candidates-found`**: iterate `classified[]`:
     - `status: "already-in-scope"` → skip silently (`prior_action: "promoted"`).
     - `status: "pre-decided-skipped"` → honor silently (`prior_action: "skipped"`).
     - `status: "pre-decided-demoted"` → record as `pre_decided`; do not re-prompt (`prior_action` ∈ `demoted-include`, `demoted-exclude`).
     - `status: "unresolved"` → continue to step 3 (user prompt). A `prior_action` of `deferred-headless` marks a path a headless run deferred (the legacy `skipped` amendment with reason `headless: no user to prompt` reads the same): a person decides it now.

3. **Prompt for each unresolved candidate.** Present the same menu shape as §1b:

   ```
   **Out-of-scope new public API discovered**

   Path:          {candidate.path}
   Evidence:      {evidence from drift report}
   Drift report:  {report relative path}

   This path was not in the brief's `scope.include` when the skill was created. How should update-skill handle it?

   [P] Promote: add to scope.include AND extract in this run
   [S] Skip:    leave out of scope AND record skip in amendments (no re-prompt)
   [U] Update:  halt this run and return to skf-brief-skill to refine scope
   ```

4. **GATE [default: defer]**: in headless mode (`{headless_mode}` is true), defer each candidate as §1b step 4 does, with this section's amendment fields (step 5) and the gate `detect-changes.scope-expansion` in its decision record: a non-interactive update run must never silently expand scope.

5. **Apply decision** as §1b step 5 does, with these differences:

   - **Amendment fields:** every amendment carries `category: "scope-expansion"` and the candidate's `evidence: {evidence string}` in place of `heuristic`. [P]'s auto reason is "out-of-scope new public API: drift report {report basename}", and [S]'s "user declined promotion at update-skill §1c".
   - **Promotion target:** [P] passes the path in `include` as the drift report gives it, wildcards kept, with the `category` and `evidence` above, and adds no `promoted_docs_new[]` entry and no `--exclude`: detect-changes.md §2 Category A lists the files a promoted code glob matches as ADDED, and step 3 extracts them, unlike §1b's documents. Display: `"Promoted {path}: brief amended; detect-changes.md §2 Category A will pick up matching files as ADDED."`
   - **[S]** leaves `scope.exclude` as it is too, and **[U]** halts with `phase: "detect-changes:scope-reconciliation"`.

6. **Summary:** After all candidates are resolved (or none were found):

   - `"Scope reconciliation: {N} candidates, {P} promoted, {S} skipped, {D} deferred to an interactive run, {A} pre-decided from amendments."`
   - If N = 0 (section absent or empty): `"Scope reconciliation: no out-of-scope observations in drift report."`
   - If §1c was skipped entirely (a docs-only skill, no skill brief or no drift report): omit this line; detect-changes.md §2.2 will still run.

**Record for evidence report:** append the record `scope_reconciliation_pre: {drift_report: path, candidates: N, promoted: P, skipped: S, deferred: D, pre_decided: A, decisions: [{path, action, evidence}]}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `scope_reconciliation_pre` (none when §1c was skipped).

This step auto-proceeds: once §1b and §1c are done, load, read the full file, then execute `{nextStepFile}`.
