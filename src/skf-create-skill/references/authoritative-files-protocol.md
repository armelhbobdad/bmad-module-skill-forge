# Authoritative Files Protocol

## Overview

Carved from `extract.md §2a`. Loaded on demand when step 3's `### 2a. Discovered Authoritative Files Protocol` sub-step runs.

**Skip this protocol entirely if `source_type: "docs-only"`** — there is no source tree to scan.

Before resolving source access for extraction, scan the source tree for **authoritative AI documentation files** that the brief's scope filters excluded. Project authors increasingly add files specifically written to steer AI assistants (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.), and these files often contain the **canonical** install command, quick-start, or architecture summary — information that nowhere else in the source tree provides. A brief authored from a scan of `src/**` will frequently exclude these files without the author realizing they exist.

This protocol detects such files, prompts the user, and records the decision in the brief so future runs (re-create, update, audit) honor it.

**Heuristic scan list (handled by the helper — listed here for reference):** case-insensitive basename match, any directory depth, on `llms.txt`, `llms-full.txt`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `COPILOT.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`.

## Procedure

1. **Resolve, scan, classify, and load previews in one call.** The helper handles the source-tree walk (pruning `node_modules`, `dist`, `.git`, etc.), case-insensitive basename matching, scope-filter diff (with `**`-recursive-glob support), amendment reconciliation (most-recent action wins), preview load (first 20 lines), and SHA-256 hashing:

   ```bash
   uv run {resolveAuthoritativeFilesHelper} resolve \
       --source-root {source_root} \
       --brief {forge_data_folder}/{skill_name}/skill-brief.yaml \
       [--preview-lines 20]
   ```

   The helper emits one envelope with three buckets:

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
        "excluded_by_pattern": "<glob>"|"not matched by any scope.include"}
     ]
   }
   ```

2. **Apply the helper's classification:**

   - **`already_in_scope[]`** — file is in scope and not skipped. **Remove the path from §2's filtered file list** and append the record to in-context `promoted_docs[]`. No prompt — authoritative docs must never reach §4 code extraction even when scope.include matches.
   - **`pre_decided[]` with `prior_action: "promoted"`** — amendment says promoted; **append to `promoted_docs[]`** using the helper-supplied hash/size/lines. Deterministic replay path.
   - **`pre_decided[]` with `prior_action: "skipped"`** — user previously declined. Do nothing. Move on.
   - **`unresolved[]`** — proceed to step 3 below (user prompt).

3. **Prompt.** Present each `unresolved[]` candidate to the user. Use the helper's `preview`, `size_bytes`, `line_count`, and `excluded_by_pattern` fields verbatim — they replace what the LLM previously had to compute itself:

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

4. **Headless mode (`{headless_mode}` is true):** auto-select `[S] Skip` for every candidate. Record amendment entries with `action: "skipped"` and `reason: "headless: no user to prompt"`. A non-interactive run must never silently promote files into scope — the decision requires a human.

5. **Apply decision:**

   - **[P] Promote:**
     1. **Do NOT add the path to the filtered file list from §2.** Authoritative documentation files are not code — they must not go through the AST extraction pipeline in §4, which would silently produce no exports (ghost entries). Instead, add the path to a new in-context list `promoted_docs[]` with `{path, heuristic, size_bytes, line_count, content_hash}`. Compute the SHA-256 content hash of the file now.
     2. Append to `brief.scope.include`: add the exact `candidate.path` as a literal glob (no wildcards — the amendment targets this specific file). This write ensures that a re-run of `skf-create-skill` against the amended brief sees the path in scope and skips re-prompting.
     3. Append to `brief.scope.amendments[]` a new entry with `action: "promoted"`, `path: candidate.path`, `reason: {user-provided one-sentence reason or auto-generated "authoritative AI docs — matched heuristic {basename}"}`, `heuristic: {basename}`, `date: {today ISO}`, `workflow: "skf-create-skill"`.
     4. **Write the amended brief back to disk immediately** at `{forge_data_folder}/{skill_name}/skill-brief.yaml`. Immediate write (not deferred to step 7) ensures a crashed run still leaves the amendment recorded. Preserve all other brief fields and formatting. **Use atomic write + backup:** before writing, copy the original brief to `{forge_data_folder}/{skill_name}/skill-brief.yaml.bak` (overwriting any prior `.bak` — the most recent pre-amendment snapshot is the useful one). Then pipe the amended YAML through the shared atomic writer so a crash mid-write cannot corrupt the brief:

        ```bash
        # 1. Backup
        cp {forge_data_folder}/{skill_name}/skill-brief.yaml \
           {forge_data_folder}/{skill_name}/skill-brief.yaml.bak

        # 2. Atomic write (stdin → tmp → fsync → rename)
        cat <<'AMENDED_YAML' | python3 {atomicWriteHelper} write \
            --target {forge_data_folder}/{skill_name}/skill-brief.yaml
        {amended brief YAML}
        AMENDED_YAML
        ```

        The helper stages into `{brief}.skf-tmp`, fsyncs, then `os.replace()`s — readers never see a half-written brief.
     5. Display: "**Promoted `{path}`** — tracked as documentation file, amendment recorded."

   - **[S] Skip:**
     1. Do NOT modify `scope.include` or `scope.exclude`.
     2. Append to `brief.scope.amendments[]` a new entry with `action: "skipped"`, `path: candidate.path`, `reason: {user-provided reason or auto-generated "user declined promotion at create-skill §2a"}`, `heuristic: {basename}`, `date: {today ISO}`, `workflow: "skf-create-skill"`.
     3. **Write the amended brief back to disk** so future runs do not re-prompt. Use the same backup-then-atomic-write pattern as the [P] Promote path (copy to `skill-brief.yaml.bak` first, then pipe through `skf-atomic-write.py write --target {brief_path}`).
     4. Display: "**Skipped `{path}`** — decision recorded in amendments."

   - **[U] Update:**
     1. Halt the workflow immediately.
     2. Display: "**Halting create-skill.** Re-run `skf-brief-skill` to refine the scope filters for `{skill_name}`, then re-run `skf-create-skill`. Decisions for previously prompted candidates were already persisted to the brief; the current candidate was not written."
     3. Exit with status `halted-for-brief-refinement`.

6. **Summary.** After all candidates are resolved (or none were found), display a one-line summary:

   - `"Authoritative files scan: {N} candidates, {P} promoted, {S} skipped, {A} pre-decided from amendments."`
   - If N = 0: `"Authoritative files scan: no candidates."`

**Record for evidence report:** `authoritative_files_scan: {candidates: N, promoted: P, skipped: S, pre_decided: A, decisions: [{path, action, heuristic, reason}]}` — step 7 includes this in `evidence-report.md`.

## How promoted docs reach the provenance map

Promoted docs do NOT flow through §4 code extraction. Instead:

1. §2a populates the in-context `promoted_docs[]` list with content hashes.
2. **Step-05 §6** (provenance-map assembly) reads `promoted_docs[]` and emits one `file_entries[]` entry per promoted doc with `file_type: "doc"`, `extraction_method: "promoted-authoritative"`, `confidence: "T1-low"`, and the pre-computed `content_hash`.
3. **Step-07 §2** does NOT copy doc files into the skill package (unlike scripts and assets). The source file remains at its original path; only the provenance map tracks it. Future audit and update workflows compare against this tracking entry via content hash — no file copy is required because the intent is drift detection on the *source*, not bundling documentation into the skill output.

**Re-running `skf-create-skill`** reads the amended brief. Files with `action: "promoted"` amendments already appear in `scope.include`, but §2a still runs — it detects the file is in scope AND has an existing amendment, and takes the "pre-decided" silent path. The `promoted_docs[]` list is rebuilt on each run by scanning amendments with `action: "promoted"` (this is the deterministic replay path).

## Downstream workflow consumption

Zero code changes required in consumer workflows:

- **`skf-update-skill`** reads `provenance-map.json`. Promoted docs appear as `file_entries[]` entries. Update-skill Category D (script/asset file changes) iterates `file_entries` and compares content hashes — this works identically for `file_type: "doc"` entries, giving drift detection for free.
- **`skf-audit-skill`** (after the bounded re-index fix) scans files from `provenance-map.json`. The re-index builds its list from `entries[].source_file ∪ file_entries[].source_file`, so promoted doc paths are naturally included in the audit scan.

The brief is the single source of truth for authored scope intent. The provenance map is the single source of truth for extracted state. `scope.amendments[]` is the bridge that records when those two intentionally diverged. `promoted_docs[]` is the in-memory handoff from §2a to step 5 §6; it is not persisted — the persisted form is the `file_entries[]` list in provenance-map.json.
