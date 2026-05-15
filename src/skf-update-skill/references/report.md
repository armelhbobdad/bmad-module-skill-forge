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

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Handle No-Change Shortcut

**If routed here from step 02 with no changes detected:**

"**Update Skill Report: {skill_name}**

**Status:** No changes detected

Source code matches provenance map exactly. The skill `{skill_name}` is current — no update was needed.

**Provenance age:** {days} days since last extraction
**Forge tier:** {tier}

**Recommendation:** No action required. Run audit-skill periodically to monitor for drift."

→ Load, read the full file, and execute `{nextStepFile}` — the health-check step is the true terminal step of this workflow.

### 1a. Handle Detect-Only Mode

**If `detect_only_mode` is true (routed here from detect-changes.md §6):**

"**Update Skill Report: {skill_name} — Detect-Only Mode**

**Status:** Detect-only (no writes)

The change manifest below describes what would be updated. No artifact was modified — re-run without `--detect-only` to apply.

{render the change manifest summary table from detect-changes.md §5, plus the per-file detail section}

**Recommendation:** Review the manifest; if it matches expectations, re-run `skf-update-skill` without `--detect-only` to perform the actual update."

The headless envelope (`SKF_UPDATE_RESULT_JSON`) carries `status: "detect-only"`, `files_written: []`, and any `headless_decisions[]` recorded by detect-changes' §1b / §1c / §2.2 gates. `version` and `previous_version` are both equal to the on-disk version (detect-only does not bump). `update_mode` reflects the run's mode (`normal` or `gap-driven` or `degraded`) so consumers know which detection path produced the manifest.

→ Load, read the full file, and execute `{nextStepFile}` (health-check) — even detect-only runs through the terminal health-check step.

### 1b. Handle Dry-Run Mode

**If `dry_run_mode` is true (routed here from re-extract.md §6):**

"**Update Skill Report: {skill_name} — Dry-Run Mode**

**Status:** Dry-run (no writes)

The change manifest below shows what was detected; re-extraction ran to compute the planned merge but neither merge nor write executed. No artifact was modified.

{render the change manifest summary AND the re-extraction summary — what merge+validate+write WOULD have done}

**Planned writes (skipped):**
- SKILL.md re-merge with re-extracted exports
- metadata.json version bump (or hold for gap-driven)
- provenance-map.json update with re-extraction results
- evidence-report.md
- context-snippet.md (only if a staleness trigger fired)
- active-symlink flip (only if version changed)

**Recommendation:** Review the manifest and re-extraction summary; if both match expectations, re-run `skf-update-skill` without `--dry-run` to perform the actual update."

The headless envelope carries `status: "dry-run"`, `files_written: []`, the `headless_decisions[]` recorded so far (everything before merge), and `update_mode` from the run.

→ Load, read the full file, and execute `{nextStepFile}` (health-check).

### 2. Present Change Summary

"**Update Skill Report: {skill_name}**

---

### Operation Summary

| Metric | Value |
|--------|-------|
| **Skill** | {skill_name} ({single/stack}) |
| **Forge Tier** | {tier} |
| **Mode** | {normal/degraded} |
| **Duration** | {step count} steps |

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
| T1-low | {count} | Pattern-matched (Quick tier or degraded) |
| T2 | {count} | QMD-enriched semantic context |

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
| `{resolved_skill_package}/SKILL.md` | Updated |
| `{resolved_skill_package}/metadata.json` | Updated |
| `{forge_version}/provenance-map.json` | Updated |
| `{forge_version}/evidence-report.md` | Appended |
| {stack reference files if applicable} | Updated |

Where `{resolved_skill_package}` = `{skills_output_folder}/{skill_name}/{version}/{skill_name}/` and `{forge_version}` = `{forge_data_folder}/{skill_name}/{version}/` — see `knowledge/version-paths.md`."

### 5. Workflow Chaining Recommendations

"### Next Steps

Based on the update results:"

**If all validations passed:**
"- **audit-skill** — Run to verify the update resolved known drift
- **export-skill** — Package the updated skill for distribution
- **test-skill** — Run test suite against the updated skill"

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
SKF_UPDATE_RESULT_JSON: {"skf_update":{"status":"success|no-changes|halted-for-*|blocked","skill_name":"<name>","version":"<v>","previous_version":"<v>","update_mode":"normal|gap-driven|degraded","files_written":[...],"headless_decisions":[...],"warnings":[...],"error":null|{...}}}
```

- `headless_decisions[]` — verbatim from the in-context array populated by gates (init.md §confirmation, detect-changes.md §1b/§1c/§2.2, merge.md §gate). Each entry `{gate, default_action, taken_action, reason, evidence?}`. Empty when no gates auto-resolved (e.g. no-changes path skipped detect-changes' gates).
- `status` — single-field outcome for pipeline branching. `"success"` when the run wrote artifacts and produced no halts; `"no-changes"` when §1 short-circuited; one of the documented `halted-for-*` codes when a halt fired; `"blocked"` as the catch-all.
- `error` — null on success or no-changes. Object `{phase, path?, reason}` describing the failure when a halt or write error fired. Pipelines branch on `error !== null` for non-zero exit semantics.

The headless envelope is the structured channel; the per-run JSON written above is the audit trail. Both coexist — the envelope is one line on stdout for grep-friendly consumption, the per-run JSON is the full record on disk.

### 6. Chain to Health Check

ONLY WHEN the change summary has been presented, files-written list displayed, and result contract saved will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

