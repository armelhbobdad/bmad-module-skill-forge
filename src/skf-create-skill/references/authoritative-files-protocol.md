# Authoritative Files Protocol

## Overview

Loaded on demand when step 3's `### 2a. Discovered Authoritative Files Protocol` sub-step runs, after `### 2b. Resolve Source Access` has resolved the source to a local tree.

**Skip this protocol entirely if `source_type: "docs-only"`** — there is no source tree to scan.

**Skip it too when `source_root` is still a remote URL** (a Quick-tier remote source, which §2b never clones, or a remote source §2b could not read into a tree): step 3 §2a's remote source guard skips the scan with a notice, because the helper below walks a local directory and refuses a URL.

Once §2b has resolved source access, scan the resolved source tree (the local source, or the private tree §2b read a remote one into) for **authoritative AI documentation files** that the brief's scope filters excluded. Project authors increasingly add files specifically written to steer AI assistants (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.), and these files often contain the **canonical** install command, quick-start, or architecture summary: information that nowhere else in the source tree provides. A brief authored from a scan of `src/**` will frequently exclude these files without the author realizing they exist.

This protocol detects such files, prompts the user, and records the decision in the brief so future runs (re-create, update, audit) honor it.

**Heuristic scan list (handled by the helper — listed here for reference):** case-insensitive basename match, any directory depth, on `llms.txt`, `llms-full.txt`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `COPILOT.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`.

## Procedure

1. **Resolve, scan, classify, and load previews in one call.** Resolve `{resolveAuthoritativeFilesHelper}` ← first existing path in `{resolveAuthoritativeFilesProbeOrder}` (step 3's frontmatter); if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot scan for authoritative files: skf-resolve-authoritative-files.py is missing. Re-install SKF, then re-run create-skill." The helper handles the source-tree walk (pruning `node_modules`, `dist`, `.git`, etc.), case-insensitive basename matching, scope-filter diff (with `**`-recursive-glob support), amendment reconciliation (most-recent action wins), preview load (first 20 lines), and SHA-256 hashing:

   ```bash
   uv run {resolveAuthoritativeFilesHelper} resolve \
       --source-root "{source_root}" \
       --brief "{brief_path}" \
       [--preview-lines 20]
   ```

   `{source_root}` is the local tree §2b resolved: the local source, or the private tree of a remote one, and `{brief_path}` the `skill-brief.yaml` step 1 loaded. The helper emits one envelope with three buckets:

   ```json
   {
     "status": "no-candidates" | "candidates-found",
     "summary": {
       "candidates_total": N, "already_in_scope_count": N,
       "pre_decided_count": N, "unresolved_count": N
     },
     "already_in_scope": [
       {"path": "...", "heuristic": "...", "size_bytes": N,
        "line_count": N, "content_hash": "sha256:..."}
     ],
     "pre_decided": [
       {"path": "...", "heuristic": "...",
        "prior_action": "promoted"|"skipped",
        "should_add_to_promoted_docs": <bool>,
        "size_bytes": N|null, "line_count": N|null,
        "content_hash": "sha256:..."|null}
     ],
     "unresolved": [
       {"path": "...", "heuristic": "...", "size_bytes": N,
        "line_count": N, "content_hash": "sha256:...",
        "preview": "<first N lines>",
        "excluded_by_pattern": "<glob>"|"not matched by any scope.include",
        "prior_action": null|"deferred-headless"}
     ]
   }
   ```

2. **Apply the helper's classification:**

   - **`already_in_scope[]`**: the file is in scope and not skipped. Append the record to in-context `promoted_docs[]`, and remove the path from §2's filtered file list when §2 built one (at Forge tier and above the recipe runner reads the brief itself and builds no list). No prompt: authoritative docs must never reach §4 code extraction even when scope.include matches.
   - **`pre_decided[]` with `prior_action: "promoted"`** — amendment says promoted; **append to `promoted_docs[]`** using the helper-supplied hash/size/lines. Deterministic replay path.
   - **`pre_decided[]` with `prior_action: "skipped"`** — user previously declined. Do nothing. Move on.
   - **`unresolved[]`**: proceed to step 3 below (user prompt). A `prior_action` of `deferred-headless` means an earlier headless run met the file and left the decision to the next interactive run.

3. **Prompt.** Present each `unresolved[]` candidate to the user. Use the helper's `preview`, `size_bytes`, `line_count`, and `excluded_by_pattern` fields verbatim so the prompt reports facts rather than recomputing them:

   ```
   **Discovered authoritative file excluded by brief scope**

   Path: {relative_path_from_source_root}
   Size: {line_count} lines, {bytes} bytes
   Matched heuristic: {basename}
   Excluded by pattern: {matching_exclude_pattern or "not matched by any scope.include"}

   First 20 lines:
   {inline preview}

   This file is typically authored for AI assistants and may contain canonical usage information not present elsewhere in the source. How should extraction handle it?

   [P] Promote — include in this extraction run AND amend brief for future runs
   [S] Skip    — honor the brief exclusion AND record skip in amendments (no re-prompt)
   [U] Update  — halt this run and return to skf-brief-skill to refine scope
   ```

4. **GATE [default: defer]**: in headless mode (`{headless_mode}` is true), promote nothing and decline nothing: whether a file enters scope is a person's decision, so this run leaves every `unresolved[]` candidate out of extraction and defers it to the next interactive run, which asks. For each candidate:
   - Record one auto-decision per path, per the Workflow Rules: stage `{"step": "extract", "gate": "authoritative-file:{path}", "decision": "deferred-headless", "rationale": "headless mode: no person to decide whether {path} enters the scope", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. The path in the gate keeps several candidates from collapsing into one row.
   - When its `prior_action` is null, record the deferral in the brief with step 5's **Write the decision** call, with one amendment per such candidate: `action: "deferred-headless"`, `reason: "headless: no person to decide; the next interactive run asks"`, `heuristic: {basename}`, `date: {today ISO}`, `workflow: "skf-create-skill"`. The helper keeps a `deferred-headless` path in `unresolved[]`, never in `pre_decided[]`. A candidate whose `prior_action` is already `deferred-headless` is not written again.

5. **Apply decision:**

   **Write the decision** to the brief at once, so a crashed run still leaves it recorded and a re-run replays it instead of asking again. Resolve `{writeSkillBriefHelper}` ← first existing path in `{writeSkillBriefProbeOrder}` and, from `{project-root}`, run `amend`: it reads the brief again, appends the paths in `include` to `scope.include` and the entries in `amendments` to `scope.amendments`, refuses an amendment that breaks the brief schema, keeps the previous brief as `{brief_path}.bak` and writes the new one atomically:

   ```bash
   uv run {writeSkillBriefHelper} amend --target "{brief_path}" <<'SKF_BRIEF_DECISION'
   {"include": ["{path}"], "amendments": [{"path": "{path}", "action": "promoted|skipped|deferred-headless", "reason": "{reason}", "heuristic": "{basename}", "date": "{today ISO}", "workflow": "skf-create-skill"}]}
   SKF_BRIEF_DECISION
   ```

   Pass `include` for a promoted path only. The helper appends it only when `scope.include` is not empty: an empty include already covers every file, and appending one path would narrow the scope to it; the `promoted` amendment replays the decision either way, through the helper's `pre_decided[]`. When the command exits non-zero or no path resolves, warn "The decision on `{path}` was not saved to the brief ({its stderr}): the next run asks again." and continue.

   - **[P] Promote:**
     1. **Do not hand the path to §4.** Authoritative documentation files are not code: the AST extraction pipeline would silently produce no exports (ghost entries). Add the path to a new in-context list `promoted_docs[]` with `{path, heuristic, size_bytes, line_count, content_hash}`, taking the values the helper reported, and remove it from §2's filtered file list when §2 built one.
     2. **Write the decision** with `include: ["{path}"]` and an amendment with `action: "promoted"`, `reason`: the user's one-sentence reason, else "authoritative AI docs, matched heuristic {basename}".
     3. Display: "**Promoted `{path}`**: tracked as documentation file, amendment recorded."

   - **[S] Skip:**
     1. Leave `scope.include` and `scope.exclude` as they are.
     2. **Write the decision** with no `include` and an amendment with `action: "skipped"`, `reason`: the user's reason, else "user declined promotion at create-skill §2a".
     3. Display: "**Skipped `{path}`**: decision recorded in amendments."

   - **[U] Update:**
     1. When `{source_tree}` is set, first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and go on whatever it prints: the scan read the tree §2b made, and nothing reads it after this halt.
     2. **HARD HALT** (exit code 6, `halted-for-brief-refinement`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "**Halting create-skill.** Re-run `skf-brief-skill` to refine the scope filters for `{skill_name}`, then re-run `skf-create-skill`. Decisions for previously prompted candidates were already persisted to the brief; the current candidate was not written."

6. **Summary.** After all candidates are resolved (or none were found), display a one-line summary:

   - `"Authoritative files scan: {N} candidates, {P} promoted, {S} skipped, {D} left for an interactive run, {A} pre-decided from amendments."`
   - If N = 0: `"Authoritative files scan: no candidates."`

**Record for evidence report:** `authoritative_files_scan: {candidates: N, promoted: P, skipped: S, deferred: D, pre_decided: A, decisions: [{path, action, heuristic, reason}]}`. Step 3 §5 writes it and `promoted_docs[]` into the extraction inventory, and step 5 writes it into `evidence-report.md`.

When step 3 §2a's remote source guard skipped the scan, the record is `authoritative_files_scan: {not_scanned: "remote source not cloned"}` instead (its own key, apart from the `skipped` count of candidates above), and step 6 lists that skip under the evidence report's Remaining Warnings.

## How promoted docs reach the provenance map

Promoted docs do not flow through §4 code extraction. Instead:

1. §2a populates the `promoted_docs[]` list with content hashes, which step 3 §5 writes into the extraction inventory.
2. **Step-05 §6** (provenance-map assembly) reads `promoted_docs[]` from the inventory and emits one `file_entries[]` entry per promoted doc with `file_type: "doc"`, `extraction_method: "promoted-authoritative"`, `confidence: "T1-low"`, and the pre-computed `content_hash`.
3. **Step 7's promotion** does not copy doc files into the skill package (unlike scripts and assets). The source file remains at its original path; only the provenance map tracks it. Future audit and update workflows compare against this tracking entry via content hash. No file copy is required, because the intent is drift detection on the *source*, not bundling documentation into the skill output.

**Re-running `skf-create-skill`** reads the amended brief. Files with `action: "promoted"` amendments already appear in `scope.include`, but §2a still runs — it detects the file is in scope AND has an existing amendment, and takes the "pre-decided" silent path. The `promoted_docs[]` list is rebuilt on each run by scanning amendments with `action: "promoted"` (this is the deterministic replay path).

## Downstream workflow consumption

Zero code changes required in consumer workflows:

- **`skf-update-skill`** reads `provenance-map.json`. Promoted docs appear as `file_entries[]` entries. Update-skill Category D (script/asset file changes) iterates `file_entries` and compares content hashes — this works identically for `file_type: "doc"` entries, giving drift detection for free.
- **`skf-audit-skill`** scans files from `provenance-map.json`. The re-index builds its list from `entries[].source_file ∪ file_entries[].source_file`, so promoted doc paths are naturally included in the audit scan.

The brief is the single source of truth for authored scope intent. The provenance map is the single source of truth for extracted state. `scope.amendments[]` is the bridge that records when those two intentionally diverged. `promoted_docs[]` is the handoff from §2a to step 5 §6, through the extraction inventory; the published form is the `file_entries[]` list in provenance-map.json.
