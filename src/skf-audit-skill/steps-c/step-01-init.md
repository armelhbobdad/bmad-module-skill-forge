---
nextStepFile: './step-02-re-index.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
templateFile: 'assets/drift-report-template.md'
---

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

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

**If user provides skill name (not full path) — version-aware path resolution (see `knowledge/version-paths.md`):**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill_name}/{active_version}/{skill_name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill_name}/active` — resolve to `{skill_group}/active/{skill_name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill_name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}`

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

**Detect split-body state:** If a `references/` directory exists and SKILL.md's `## Full` headings are absent or stubs, this is a split-body skill. Flag `split_body: true` in the baseline so downstream steps (especially semantic diff in step-04) know to also read `references/*.md` for complete content comparison.

### 4. Load Provenance Map

Search for provenance map at `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json` (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`:

**If found:**
- Load and extract: export list, file mappings, extraction timestamps, confidence tiers
- Record provenance map age (days since last extraction)

**If missing at both paths:**
- "No provenance map found for `{skill_name}`. This skill may not have been created by create-skill."
- "**Degraded mode available:** I can perform text-based comparison without provenance data. Findings will have T1-low confidence."
- "**[D]egraded mode** — proceed with text-diff only"
- "**[X]** — abort audit"
- Wait for user selection. If D, set `degraded_mode: true`. If X, halt workflow.

### Stack Skill Detection

After loading provenance-map.json, detect skill type:
- If `provenance_version` is `"2.0"` and `skill_type` is `"stack"`: set `{is_stack_skill}` = true
- If provenance-map has top-level `libraries` key (v1 stack format): set `{is_stack_skill}` = true, `{legacy_stack_provenance}` = true
- Otherwise: `{is_stack_skill}` = false

If `{is_stack_skill}` is true and `constituents` array is present (compose-mode stack):
- For each constituent, compute the current metadata hash: read `{constituent.skill_path}/active/{constituent.skill_name}/metadata.json` and compute SHA-256
- Compare against `constituent.metadata_hash`
- Flag any mismatches as **constituent drift** with severity HIGH
- Record constituent freshness results for the report

If `{legacy_stack_provenance}` is true: log a note that this stack uses v1 provenance format with reduced audit depth (library-level only, no per-export verification).

### 5. Resolve Source Path

**If provenance map loaded:**
- Use `source_root` from provenance map as source code path
- Verify source path still exists and is accessible
- Extract `baseline_commit` = `provenance-map.source_commit` (fall back to `metadata.source_commit` if absent from the provenance map)
- Extract `baseline_ref` = `metadata.source_ref` (may be a tag, branch, `HEAD`, or `"local"`)

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

When skipping, log the reason, then set the audit-ref context variables to baseline values so step-06 renders a coherent Provenance row: `audit_ref = baseline_ref or "(unknown)"`, `audit_ref_source = "baseline"` (or `"unavailable"` if both `baseline_ref` and `baseline_commit` are unset), `audit_commit = baseline_commit or "(unknown)"`, `latest_tag = null`, `remote_head = null`. Continue to §6.

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
   - **[C]:** Acquire an exclusive lock on `{source_root}/.skf-workspace.lock` (`flock -x` or `fcntl.flock(LOCK_EX)`) before mutating the working tree — matches the concurrency discipline in `src/skf-create-skill/references/source-resolution-protocols.md` and avoids racing with a concurrent create-skill / test-skill run against the same workspace clone. If `flock` is unavailable, emit a warning and proceed. Then `git -C {source_root} checkout {chosen_ref}` (prefer `latest_tag` when present, else `remote_head`). Set `audit_ref = {chosen_ref}`, `audit_ref_source = "checkout-latest"`, `audit_commit = git rev-parse HEAD`. Hold the lock through step-02 re-extraction and release only after the extraction snapshot is complete.
   - **[S]:** Keep baseline. Set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`.
   - **[X]:** HALT workflow — do not create drift report.
   - **Other input:** help user, redisplay gate.

   **Headless default** (when `{headless_mode}`): auto-select **[S]** and emit a loud log line: `"headless: upstream drift detected ({baseline_ref} → {latest_tag or remote_head}); staying on baseline. Re-run interactively to audit against latest."` Do not check out in headless mode — silent ref changes under automation would mutate the user's working tree without consent.

5. **Record for report:** store `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head`, and `baseline_commit` in context. Step-06 surfaces them in the Provenance section so readers can tell which comparison actually ran.

### 6. Create Drift Report

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Set `stepsCompleted: ['step-01-init']`
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

