---
nextStepFile: 're-index.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
templateFile: 'assets/drift-report-template.md'
loadProvenanceScript: '{project-root}/src/shared/scripts/skf-load-provenance.py'
compareFileHashesScript: '{project-root}/src/shared/scripts/skf-compare-file-hashes.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Audit

## STEP GOAL:

Load the existing skill artifacts, provenance map, and forge tier configuration to establish the baseline for drift detection. Create the drift report document and present a baseline summary for user confirmation before proceeding with analysis.

## Rules

- Focus only on loading skill artifacts and establishing the baseline — do not perform any diff or analysis
- Do not proceed if skill path is invalid or SKILL.md not found
- Present baseline summary clearly so user can confirm before analysis begins
- Docs-only limitation: If `metadata.json` indicates `source_type: "docs-only"` or `confidence_tier: "Quick"` with all T3 citations, inform user: "**This is a docs-only skill.** Drift detection compares against upstream documentation, not source code. Re-run `@Ferris US` to re-fetch documentation URLs and detect content changes." Recommend update-skill instead.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

**Initialize workflow context defaults.** Before entering §1, set `confidence_mode = "normal"` as the default. §4 may upgrade this to `"degraded — all findings T1-low"` if the operator opts into degraded mode. Downstream steps (report.md, drift-report-template.md) consume this variable directly — no conditional at the usage site.

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

**If user provides skill name (not full path) — version-aware path resolution (see `knowledge/version-paths.md`):**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: tentatively resolve `{skill_package}` = `{skills_output_folder}/{skill_name}/{active_version}/{skill_name}/`. **Manifest-vs-symlink drift gate:** before committing, also read the `active` symlink at `{skills_output_folder}/{skill_name}/active`. When the symlink target disagrees with `active_version`, the manifest lags behind on-disk state — typical sequence is `update-skill` flipped the symlink but `export-skill` has not yet rewritten the manifest. Auditing the older manifest version would re-audit a skill the user no longer cares about (or has already audited). Decide which version to audit:
   - Read `forge_data_folder/{skill_name}/{active_version}/provenance-map.json` (manifest version) and `forge_data_folder/{skill_name}/{symlink_target}/provenance-map.json` (symlink target). Compare their `generated_at` timestamps (or `mtime` if the field is absent).
   - If both versions exist and the symlink target's provenance is **fresher** than the manifest's `last_exported`, present a gate:

     "**Manifest lags behind active symlink.**

     | | Manifest | Symlink |
     |---|---|---|
     | Version | `{active_version}` | `{symlink_target}` |
     | Exported / forged | `{manifest.last_exported}` | `{symlink_provenance_generated_at}` |

     The manifest's `active_version` was set by an earlier export-skill run; the symlink was flipped later (typically by update-skill). Auditing the manifest version will re-audit a skill the user no longer treats as active. Options:

     - **[N] Audit symlink target ({symlink_target})** — recommended. The drift report describes the version the skill currently resolves to.
     - **[M] Audit manifest version ({active_version})** — only useful when investigating the older version specifically.
     - **[X] Abort** — halt without producing a report. Run `[EX] Export Skill` to reconcile the manifest before re-running audit-skill."

     Default is **[N]**. Headless mode auto-selects **[N]** with a loud log line: `"headless: manifest active_version ({active_version}) is older than symlink target ({symlink_target}); auditing symlink target. Run export-skill to reconcile."` This mirrors §5b's upstream-drift handling — when the manifest and the working tree disagree, the working tree is the more honest signal under automation.

   - When the symlink target's provenance is **older** than (or equal to) the manifest's `last_exported`, the symlink predates the export — this is the normal post-export shape, no gate needed. Resolve to the manifest's `active_version`.
   - When only one of the two versions has a provenance map, resolve to the version that has one (the other is inert — auditing it would degrade to text-diff). Log the choice.

3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill_name}/active` — resolve to `{skill_group}/active/{skill_name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill_name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}`. Also store `audit_target_version` = the version that was actually selected (manifest, symlink, or flat) for step 6 Provenance to surface. When the gate above fired, also record the rejected version under `manifest_symlink_drift = {manifest: {active_version}, symlink: {symlink_target}, audited: {audit_target_version}, reason: {fresher-provenance|operator-choice|headless-default}}` so reviewers can audit the choice.

**If user provides full path:**
- Use as provided

**Validate:** Check that `SKILL.md` exists at the resolved path.
- If missing → "Skill not found at `{resolved_skill_package}`. Check the path and try again."
- If found → Continue

### 2. Load Forge Tier

Load `{sidecar_path}/forge-tier.yaml` to detect available tools.

**If file missing:**
- "Setup-forge has not been run. Cannot determine tool availability. Run `[SF] Setup Forge` first."
- HALT workflow

**If found:**
- Extract tier level: Quick / Forge / Forge+ / Deep
- Extract available tools: gh_bridge, ast_bridge, qmd_bridge — see `knowledge/tool-resolution.md` for concrete tool resolution per IDE

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

### 3. Load Skill Artifacts

Load the following from the skill directory:

**Required:**
- `SKILL.md` — The skill document to audit
- `metadata.json` — Skill metadata (version, created date, export count)

**Extract from metadata.json:**
- `name`, `version`, `generation_date`, `confidence_tier` used during creation
- `source_root` — Resolved source code path used during extraction

**Detect split-body state:** If a `references/` directory exists and SKILL.md's `## Full` headings are absent or stubs, this is a split-body skill. Flag `split_body: true` in the baseline so downstream steps (especially semantic diff in step 4) know to also read `references/*.md` for complete content comparison.

### 4. Load Provenance Map

Search for provenance map at `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json` (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`:

**If found:**
- Record provenance map age (days since last extraction) from file mtime
- Normalize the map's deterministic projections in one subprocess call:

  ```bash
  uv run {loadProvenanceScript} normalize {provenanceMap}
  ```

  Parse the emitted JSON and stash these fields in workflow context (downstream steps read them directly — no re-walk):
  - `{bounded_scan_files}` — sorted POSIX list, union of `entries[].source_file` and `file_entries[].source_file`. Step 2 `re-index.md` consumes this as the bounded scan list.
  - `{is_stack_skill}`, `{legacy_stack_provenance}` — stack-skill flags (see Stack Skill Detection below for downstream branching).
  - `{source_root}`, `{baseline_commit}`, `{baseline_ref}` — used by §5 Resolve Source Path and §5b Detect Upstream Drift.
  - `{reexport_map}` — `{<internal>: <public>}` mapping consumed by `structural-diff.md` §1 to collapse public-API renames before diffing.

  If the script exits non-zero, surface the stderr as a HARD HALT — the map is structurally invalid and downstream steps cannot proceed.

**If missing at both paths:**
- "No provenance map found for `{skill_name}`. This skill may not have been created by create-skill."
- "**Degraded mode available:** I can perform text-based comparison without provenance data. Findings will have T1-low confidence."
- "**[D]egraded mode** — proceed with text-diff only"
- "**[X]** — abort audit"
- Wait for user selection. If D, set `degraded_mode: true` and `confidence_mode = "degraded — all findings T1-low"`, then skip the normalize call above (no map to normalize). If X, halt workflow.

### Stack Skill Detection

`{is_stack_skill}` and `{legacy_stack_provenance}` are already resolved by the normalize call in §4 — no additional walk needed. Apply the post-detection logic:

If `{is_stack_skill}` is true and `constituents` array is present (compose-mode stack):
- For each constituent, compute the current metadata hash: read `{constituent.skill_path}/active/{constituent.skill_name}/metadata.json` and compute SHA-256
- Compare against `constituent.metadata_hash`
- Flag any mismatches as **constituent drift** with severity HIGH
- Record constituent freshness results for the report

If `{legacy_stack_provenance}` is true: log a note that this stack uses v1 provenance format with reduced audit depth (library-level only, no per-export verification).

### 5. Resolve Source Path

**If provenance map loaded:**
- Use `{source_root}` (already extracted by §4 normalize) as source code path
- Verify source path still exists and is accessible
- `{baseline_commit}` and `{baseline_ref}` are already populated by §4. If `{baseline_commit}` is null in the projection, fall back to `metadata.source_commit`. `{baseline_ref}` may be a tag, branch, `HEAD`, or `"local"`.

**If degraded mode:**
- Ask user: "Please provide the path to the current source code."
- `baseline_commit` and `baseline_ref` are unavailable — §5b will short-circuit

**Validate:** Confirm source directory exists and contains expected files.

### 5b. Detect Upstream Drift

Upstream drift detection is the primary use case of this workflow. If the local clone is still pinned to the baseline commit while upstream has shipped newer tags, auditing against the unchanged tree will misleadingly report CLEAN even after a major release.

**Skip this section** if any of the following hold:
- `baseline_ref` is `"local"`, `null`, or unset (non-git source)
- `{source_root}` is not a git worktree (`git -C {source_root} rev-parse --git-dir` fails)
- `baseline_commit` is unavailable
- Degraded mode is active (no provenance map)

When skipping, log the reason, then set the audit-ref context variables to baseline values so step 6 renders a coherent Provenance row: `audit_ref = baseline_ref or "(unknown)"`, `audit_ref_source = "baseline"` (or `"unavailable"` if both `baseline_ref` and `baseline_commit` are unset), `audit_commit = baseline_commit or "(unknown)"`, `latest_tag = null`, `remote_head = null`. Continue to §6.

**Otherwise:**

1. **Fetch upstream refs** (read-only, no working-tree mutation):

   ```bash
   git -C {source_root} fetch --tags --quiet origin
   ```

   If fetch fails (no network, no remote, detached clone), log the reason, record `upstream_fetch: "failed:{reason}"` in context, set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`, `latest_tag = null`, `remote_head = null`, and continue to §6 without gating.

2. **Find latest remote ref:**
   - Remote default-branch HEAD: `git -C {source_root} rev-parse origin/HEAD` (fall back to `origin/main` or `origin/master` if the symbolic ref is unavailable) — record as `remote_head`.
   - Newest semver tag: `git -C {source_root} for-each-ref --sort=-v:refname --format='%(refname:short)' 'refs/tags/v*' | head -1` — record as `latest_tag`.

3. **Compare to baseline:**
   - If `baseline_commit` equals the commit that `remote_head` resolves to AND (`latest_tag` is empty OR semver-equals `baseline_ref` OR is older than `baseline_ref`), upstream has not moved. Set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`. Continue to §6.
   - Otherwise upstream has moved — proceed to the gate.

4. **User gate — Upstream drift detected:**

   "**Upstream has moved since this skill was created.**

   | | Baseline | Upstream |
   |---|---|---|
   | Ref | `{baseline_ref}` | `{latest_tag}` (newest tag) / `{remote_head}` (default HEAD) |
   | Commit | `{baseline_commit_short}` | `{latest_tag_commit_short}` / `{remote_head_short}` |

   Auditing against the baseline clone will report little-to-no structural drift even if the upstream API has changed. Options:

   - **[C] Checkout-and-audit-against-latest** — checkout `{latest_tag}` (or `{remote_head}` if no newer tag) in `{source_root}` and audit against that. Re-extraction will reflect the current upstream surface.
   - **[S] Stay-on-baseline** — keep `{source_root}` at `{baseline_ref}` and audit structural drift against the unchanged tree. The report will note `audit_ref = baseline`.
   - **[X] Abort** — halt the workflow without producing a report.

   **Select:** [C] / [S] / [X]"

   **Gate handling:**
   - **[C]:** Acquire an exclusive lock on `{source_root}/.skf-workspace.lock` (`flock -x` or `fcntl.flock(LOCK_EX)`) before mutating the working tree — matches the concurrency discipline in `src/skf-create-skill/references/source-resolution-protocols.md` and avoids racing with a concurrent create-skill / test-skill run against the same workspace clone. If `flock` is unavailable, emit a warning and proceed.

     **Dirty-worktree probe (mandatory before checkout).** Run `git -C {source_root} status --porcelain` after acquiring the lock and before the checkout. If the output is non-empty, the working tree has uncommitted changes — `git checkout {chosen_ref}` will abort with `error: Your local changes to the following files would be overwritten by checkout`, halting the workflow mid-step. The most common benign cause is a tooling-generated edit (e.g. the CCC daemon appending a `.cocoindex_code/` line to `.gitignore` after `setup-forge` pointed it at this clone), but the changes could also be the operator's in-progress work. Surface a sub-gate before mutating:

     "**Working tree has uncommitted changes.** `git status --porcelain` returned:

     ```
     {first 20 lines of porcelain output, ellipsis if more}
     ```

     A `git checkout` would abort. Options:
     - **[T] Transient stash** — `git stash push -m 'skf-audit: pre-checkout' --include-untracked`, perform the checkout, and pop the stash on the way out. Recommended when the changes look tooling-generated (e.g. a `.gitignore` line referencing `.cocoindex_code/`, lockfile churn from an indexer).
     - **[A] Abort** — halt the workflow and let the operator commit, stash, or discard manually before retrying.
     - **[F] Force checkout** — `git checkout --force` discards uncommitted changes irrecoverably. Only choose this after confirming the changes are safe to lose."

     **Gate handling:**
     - **[T]:** Run `git -C {source_root} stash push -m 'skf-audit-skill: pre-checkout {chosen_ref}' --include-untracked`. Capture the stash ref from the command output (e.g. `stash@{0}`) and store as `pre_checkout_stash_ref` in workflow context for step 6 Provenance to surface. Proceed to the checkout. (After audit completes, the operator restores the stash with `git stash pop` — step 6 puts the literal command in the report as a workflow-level convention rather than per-author ad-hoc prose.)
     - **[A]:** HALT the workflow. Do not write a drift report — the audit was never started.
     - **[F]:** Run `git -C {source_root} checkout --force {chosen_ref}` instead of the plain checkout. Record `pre_checkout_force_discard: true` in workflow context for step 6 to surface as a loud warning. Skip the stash path.
     - **Other input:** help user, redisplay the sub-gate.

     **Headless default** (when `{headless_mode}`): auto-select **[A] Abort** rather than silently mutating the working tree. Emit a loud log line: `"headless: dirty worktree detected at {source_root}; refusing to checkout {chosen_ref} or stash. Re-run interactively to choose [T]/[A]/[F]."` Stashing under automation could lose work if the operator never returns to pop; force-checkout under automation could destroy uncommitted work outright. Abort is the only safe non-interactive default.

     If `git status --porcelain` is empty, skip the sub-gate and proceed directly to the checkout.

     Then `git -C {source_root} checkout {chosen_ref}` (prefer `latest_tag` when present, else `remote_head`). Set `audit_ref = {chosen_ref}`, `audit_ref_source = "checkout-latest"`, `audit_commit = git rev-parse HEAD`. Hold the lock through step 2 re-extraction and release only after the extraction snapshot is complete.
   - **[S]:** Keep baseline. Set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`.
   - **[X]:** HALT workflow — do not create drift report.
   - **Other input:** help user, redisplay gate.

   **Headless default** (when `{headless_mode}`): auto-select **[S]** and emit a loud log line: `"headless: upstream drift detected ({baseline_ref} → {latest_tag or remote_head}); staying on baseline. Re-run interactively to audit against latest."` Do not check out in headless mode — silent ref changes under automation would mutate the user's working tree without consent.

5. **Record for report:** store `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head`, and `baseline_commit` in context. Step-06 surfaces them in the Provenance section so readers can tell which comparison actually ran.

### 6. Create Drift Report

**Re-audit detection (before creating a fresh report).** Glob `{forge_version}/drift-report-*.md`. If one or more matches exist, identify the most recent one by file mtime (or by the `{timestamp}` segment in the filename when mtime is unreliable on the filesystem). If that report's age is `< 7 days` and its frontmatter `audit_ref` matches the current `{audit_ref}` (resolved in §5b), surface a soft gate before creating a fresh report:

  "**Recent audit found:** `{prior_report_path}` (created {prior_timestamp}, audit_ref=`{audit_ref}`).
  
  Options:
  - **[F] Fresh audit** (recommended; default in headless) — start a new drift report at `{outputFile}` and ignore the prior run.
  - **[D] Diff against prior report** — compute findings delta vs the prior report and emit a `## Diff Against Prior Report` subsection in step 6 (report.md).
  - **[R] Resume the prior report** — load the prior report's frontmatter (`stepsCompleted`, `drift_score`, intermediate findings) and jump to the next un-completed step instead of starting over.
  
  **Select:** [F] / [D] / [R]"

**Gate handling:**
- **[F]:** Default. Proceed with the fresh-report creation below — ignore the prior report.
- **[D]:** Read the prior report's findings_list (parse the Structural/Semantic/Severity sections, or the appended findings tables) and stash as `prior_findings` in workflow context. Run the new audit normally. In step 6 (report.md), after the Remediation Suggestions section, emit a `## Diff Against Prior Report` subsection summarizing added / removed / changed findings vs `prior_findings`.
- **[R]:** Load the prior report's frontmatter (`stepsCompleted`, `drift_score`, any intermediate state). Set `{outputFile}` to the prior report path (do NOT create a new one). Determine the next un-completed step from `stepsCompleted` and skip forward to it; downstream steps append to the existing report.

  > **Note (resumability):** the existing template frontmatter captures `stepsCompleted` and `drift_score` but does not currently persist intermediate findings_list between stages. If [R] is selected and stepsCompleted indicates the prior run halted after structural-diff or semantic-diff, the appended sections in the report body (`## Structural Drift`, `## Semantic Drift`, `## Severity Classification`) serve as the implicit intermediate state — re-parse them on resume rather than re-running completed stages. **TODO:** if resumability proves unreliable in practice, extend the report frontmatter to carry an explicit `intermediate_findings` block (out of scope for this PR).

- **Other input:** help user, redisplay the gate.

**Headless default** (when `{headless_mode}`): auto-select **[F]** and emit a loud log line: `"headless: recent audit found at {prior_report_path}; defaulting to fresh audit. Re-run interactively to choose [D]/[R]."`

**Skip this gate** if no prior report matches the `< 7 days + same audit_ref` filter — proceed directly to creating the fresh report.

**Create the fresh report** (when [F] is selected, headless default fires, or no prior report exists):

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Set `stepsCompleted: ['init']`
- Fill Audit Summary skeleton with loaded baseline data

### 7. Present Baseline Summary (User Gate)

"**Audit Baseline Loaded**

| Field | Value |
|-------|-------|
| **Skill** | {skill_name} v{version} |
| **Created** | {generation_date} |
| **Source** | {source_path} |
| **Forge Tier** | {current_tier} (created at {original_tier}) |
| **Provenance Age** | {days} days since last extraction |
| **Export Count** | {count} exports in provenance map |
| **Mode** | {normal / degraded} |

**Analysis plan based on tier:**
- {Quick: text-diff comparison (T1-low confidence)}
- {Forge: AST structural comparison (T1 confidence)}
- {Forge+: AST structural comparison + CCC-assisted rename detection (T1 confidence)}
- {Deep: AST structural + QMD semantic comparison (T1 + T2 confidence)}

**Ready to begin drift analysis?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Analysis"

#### Menu Handling Logic:

- IF C: Save baseline to {outputFile}, update frontmatter stepsCompleted, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past baseline confirmation"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and the drift report has been created with baseline data populated, will you then load and read fully `{nextStepFile}` to execute and begin source re-indexing.

