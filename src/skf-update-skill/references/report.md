---
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Report

## STEP GOAL:

Present a comprehensive change summary showing what was updated, [MANUAL] sections preserved, confidence tier breakdown, and recommend next workflow actions in the SKF chain.

## Rules

- Focus only on reporting — all operations are complete; do not modify any files
- Present clear, actionable summary with next step recommendations
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing summary is NOT the terminal step

## Steps

### 1. Handle No-Change Shortcut

**If routed here from step 02 with no changes detected:**

"**Update Skill Report: {skill_name}**

**Status:** No changes detected

Source code matches provenance map exactly. The skill `{skill_name}` is current — no update was needed.

**Provenance age:** {days} days since last extraction
**Forge tier:** {tier}
**Source commit:** {source_commit_line}

**Recommendation:** No action required. Run audit-skill periodically to monitor for drift."

When `{source_moved}` is true, add before the recommendation: "Upstream moved to `{target_commit}`, but no file this skill tracks changed, so nothing was written and the skill stays pinned at `{source_commit}`." When `{target_ref_override}` is set and `{target_ref}` differs from `{source_ref}`, also add "**The re-pin to `{target_ref}` was not recorded** — an update records a new ref only when it writes, and `{target_ref}` changes no file this skill tracks." and add `target-ref-not-recorded: {target_ref} changes no file {skill_name} tracks; the skill still records {source_ref}` to `warnings[]`.

The headless envelope (`SKF_UPDATE_RESULT_JSON`, §5b shape) carries `status: "no-changes"`, `files_written: []` and `warnings[]`.

→ Load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.

### 1a. Handle Detect-Only Mode

**If `detect_only_mode` is true (routed here from detect-changes.md §6):**

"**Update Skill Report: {skill_name} — Detect-Only Mode**

**Status:** Detect-only (no writes)
**Source commit:** {source_commit_line}

The change manifest below describes what would be updated. No artifact was modified — re-run without `--detect-only` to apply.

{render the change manifest summary table from detect-changes.md §5, plus the per-file detail section}

**Recommendation:** Review the manifest; if it matches expectations, re-run `skf-update-skill` without `--detect-only` to perform the actual update."

The headless envelope (`SKF_UPDATE_RESULT_JSON`) carries `status: "detect-only"`, `files_written: []`, and any `headless_decisions[]` recorded by detect-changes' §1b / §1c / §2.2 gates. `version` and `previous_version` are both equal to the on-disk version (detect-only does not bump). `update_mode` reflects the run's mode (`normal` or `gap-driven` or `degraded`) so consumers know which detection path produced the manifest.

→ Load, read the full file, and execute `{nextStepFile}` (health-check) — even detect-only runs through the terminal health-check step.

### 1b. Handle Dry-Run Mode

**If `dry_run_mode` is true (routed here from re-extract.md §6):**

"**Update Skill Report: {skill_name} — Dry-Run Mode**

**Status:** Dry-run (no writes)
**Source commit:** {source_commit_line}

The change manifest below shows what was detected; re-extraction ran to compute the planned merge but neither merge nor write executed. No artifact was modified.

{render the change manifest summary AND the re-extraction summary — what merge+validate+write WOULD have done}

**Planned writes (skipped):**
- SKILL.md re-merge with re-extracted exports
- metadata.json version bump (or hold for gap-driven)
- a new version folder beside the current one, named `{source_version_detected}` when step 1 §6c recorded one and otherwise the next patch version, holding a copy of the current package, and its forge folder with copies of the provenance map, evidence report and extraction rules (not in gap-driven mode, which writes into the current version)
- provenance-map.json update with re-extraction results
- evidence-report.md
- context-snippet.md (only if a staleness trigger fired)
- active-symlink flip (only if version changed)
- metadata.json and provenance-map.json `source_commit` → `{target_commit}` (and `source_ref` → `{target_ref}` when `--target-ref` re-pins the skill)
- the workspace clone moved to `{target_commit}` (only when it still holds `{source_commit}`)

**Recommendation:** Review the manifest and re-extraction summary; if both match expectations, re-run `skf-update-skill` without `--dry-run` to perform the actual update."

The headless envelope carries `status: "dry-run"`, `files_written: []`, the `headless_decisions[]` recorded so far (everything before merge), and `update_mode` from the run.

→ Load, read the full file, and execute `{nextStepFile}` (health-check).

### 2. Present Change Summary

"**Update Skill Report: {skill_name}**

---

### Operation Summary

| Metric | Value |
|--------|-------|
| **Skill** | {skill_name} |
| **Forge Tier** | {tier} |
| **Mode** | {update_mode}{mode_fallback_note} |
| **Source commit** | {source_commit_line} |
| **Duration** | {step count} steps |

**`{update_mode}`** is one of `normal`, `gap-driven`, or `degraded` (mirrors the `update_mode` field of `SKF_UPDATE_RESULT_JSON`).

**`{mode_fallback_note}`** surfaces weak-signal fallbacks the workflow took silently and would otherwise be buried in the evidence report. Render it inline after the mode value when any of these conditions fire; render the empty string when none did:

- `--from-test-report` was passed but the test report was missing at the expected path, so step 1 fell back to `normal` mode → ` (gap-driven requested; test report missing — fell back to normal)`
- `re-extract.md §0.a` skipped the workspace-drift guard because `source_root` is not a git working tree (or HEAD was unreadable) → ` (workspace-drift check skipped: {skip_reason})` where `{skip_reason}` is the helper's `skip_reason` field (`not-a-git-tree` or `HEAD unreadable`)
- init.md §6b could not reach upstream and compared the pinned commit (`{source_tree_status}` is `offline`) → ` (upstream not reached: compared the pinned commit only)`
- init.md §6b could not read `{source_commit}`, so every tracked file was re-checked (`{source_diff_status}` is `unavailable` in a source tree) → ` (file list unavailable: every tracked file re-checked)`
- write.md §6b left the workspace clone where it was (`{advance_status}` is `skipped`) → ` (source clone not moved: {advance_skip_reason})`
- Several fired: concatenate the parenthetical notes with `; ` between them

These signals also appear in `warnings[]` on the headless envelope; the Mode row makes them visible to interactive users who scan the report without parsing the envelope.

### Changes Applied

| Category | Count |
|----------|-------|
| Files modified | {count} |
| Files added | {count} |
| Files deleted | {count} |
| Files moved/renamed | {count} |
| **Total exports affected** | {count} |

### Export Changes

| Change Type | Count |
|-------------|-------|
| Updated (signature/type change) | {count} |
| Added (new exports) | {count} |
| Removed (deleted exports) | {count} |
| Moved (file relocated) | {count} |
| Renamed (identifier changed) | {count} |

### Confidence Tier Breakdown

| Tier | Count | Description |
|------|-------|-------------|
| T1 | {count} | AST-verified structural extraction |
| T1-low | {count} | Read by eye, at any tier (`extraction_method: source-read`) |
| T2 | {count} | QMD-enriched semantic context |

{if `{provenance_relabels}` is non-empty: **Relabeled to match extraction_method (write.md §2):** {export names}{; **WARN, no node kind found:** {export names}}}

### [MANUAL] Section Preservation

| Metric | Count |
|--------|-------|
| Sections preserved | {count} |
| Conflicts resolved | {count} |
| Orphans kept | {count} |
| Orphans removed | {count} |
| **Integrity** | {VERIFIED / count issues} |"

### 3. Present Validation Findings (If Any)

**If validation findings exist from step 05:**

"### Validation Findings

| Check | Status | Issues |
|-------|--------|--------|
| Spec compliance | {PASS/WARN/FAIL} | {count} |
| [MANUAL] integrity | {PASS/WARN/FAIL} | {count} |
| Confidence tiers | {PASS/WARN/FAIL} | {count} |
| Provenance | {PASS/WARN/FAIL} | {count} |

{List specific findings if WARN or FAIL}"

**If all validations passed:** "### Validation: All checks passed."

### 4. Show Files Updated

"### Files Written

| File | Status |
|------|--------|
| `{skill_package}/SKILL.md` | Updated |
| `{skill_package}/metadata.json` | Updated |
| `{forge_version}/provenance-map.json` | Updated |
| `{forge_version}/evidence-report.md` | Appended |

Where `{skill_package}` = `{skills_output_folder}/{skill_name}/{version}/{skill_name}/` and `{forge_version}` = `{forge_data_folder}/{skill_name}/{version}/`: the new version's folders step 4 §6b created (the current version's in gap-driven mode), beside the unchanged previous version — see `knowledge/version-paths.md`."

### 5. Workflow Chaining Recommendations

"### Next Steps

Based on the update results:"

**If all validations passed:**
"- **audit-skill** — Run to verify the update resolved known drift
- **export-skill** — Package the updated skill for distribution
- **test-skill** — Run test suite against the updated skill"

When `warnings[]` holds `workspace-clone-not-updated`, add: "- test-skill stops with `workspace-drift` until `{workspace_clone}` holds `{target_commit}` (the clone was not moved: {the reason that warning names}). Another skill built from this repository may need the clone where it is; when none does, move it yourself with `git -C "{workspace_clone}" fetch --depth 1 origin {target_commit}` and then `git -C "{workspace_clone}" checkout --detach {target_commit}`, which stops rather than overwrite a local change, and re-run test-skill." Leave out the sentence that names the two commands when that reason is `not-a-clone` or `clone-failed`: there is no SKF clone to move. When that reason is `checkout-interrupted`, keep the fetch and name `git -C "{workspace_clone}" checkout --force --detach {target_commit}` in place of the plain checkout: the time limit stopped the update's own checkout part way, so the clone may hold files of both commits, which stop a plain checkout, and it had no local changes when that checkout began. The fetch stays because no ref keeps that commit in the clone, so git may have pruned it by the time the commands run. test-skill's own message suggests a checkout of `{source_ref}`, which does not reach a new commit of a branch or of `HEAD`.

**If validation warnings/failures exist:**
"- **audit-skill** — Run to identify remaining issues
- Review validation findings above before exporting"

**If triggered by audit-skill chain:**
"- **audit-skill** — Re-run to verify CRITICAL/HIGH drift resolved
- **export-skill** — Package once audit confirms clean state"

### 5b. Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{forge_version}/update-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_version}/update-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include all modified file paths in `outputs`; include `exports_affected`, `files_modified`, and `validation_status` (passed/warnings/failures) in `summary`.

**Headless envelope (`SKF_UPDATE_RESULT_JSON`):** when `{headless_mode}` is true, ALSO emit a single-line JSON envelope to stdout prefixed with the literal `SKF_UPDATE_RESULT_JSON: `. Schema: `src/shared/scripts/schemas/skf-update-result-envelope.v1.json`. Construct the envelope from in-context state:

```json
SKF_UPDATE_RESULT_JSON: {"skf_update":{"status":"success|no-changes|detect-only|dry-run|halted-for-*|blocked","skill_name":"<name>","version":"<v>","previous_version":"<v>","update_mode":"normal|gap-driven|degraded","files_written":[...],"headless_decisions":[...],"warnings":[...],"error":null|{...}}}
```

- `headless_decisions[]` — verbatim from the in-context array populated by gates (init.md §confirmation and §4 degraded-rebuild, detect-changes.md §1b/§1c/§2.2, merge.md §gate). Each entry `{gate, default_action, taken_action, reason, evidence?}`. Empty when no gates auto-resolved (e.g. no-changes path skipped detect-changes' gates).
- `status` — single-field outcome for pipeline branching. `"success"` when the run wrote artifacts and produced no halts; `"no-changes"` when §1 short-circuited; `"detect-only"` / `"dry-run"` for the §1a/§1b read-only exits; one of the documented `halted-for-*` codes when a halt fired; `"blocked"` as the catch-all. The full enum lives in the schema (this step emits the value already resolved in context).
- `error` — null on success or no-changes. Object `{phase, path?, reason}` describing the failure when a halt or write error fired. Pipelines branch on `error !== null` for non-zero exit semantics.
- `warnings[]` — every entry the run added, among them `source-tree:`, `source-not-fetched`, `file-diff-unavailable`, `source-version-lower`, `workspace-clone-not-updated` and `target-ref-not-recorded` entries.

The headless envelope is the structured channel; the per-run JSON written above is the audit trail. Both coexist — the envelope is one line on stdout for grep-friendly consumption, the per-run JSON is the full record on disk.

**Post-finalization hook.** If `{onCompleteCommand}` (resolved in SKILL.md On Activation §3 from `workflow.on_complete`) is non-empty, invoke it after both result-JSON writes complete:

```bash
{onCompleteCommand} --result-path={forge_version}/update-skill-result-latest.json
```

Run it with a bounded timeout (default 60s). On success, log an Info note and continue; on non-zero exit, timeout, or any failure, append the reason to `warnings[]` (surfaced on the headless envelope) and continue. The hook must never fail the workflow — it is integration glue (notify a CI router, chain audit/export/test) orthogonal to the update outcome. Empty `{onCompleteCommand}` = no-op, no log entry.

### 6. Chain to Health Check

Once the change summary has been presented, the files-written list displayed, and the result contract saved, load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop at the report even though it reads as final.

