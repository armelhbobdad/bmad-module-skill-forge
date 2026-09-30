---
nextStepFile: 're-index.md'
# A compose-mode stack (§4) has no source tree: on confirmation §7 loads this
# step in place of steps 2 to 4.
composeStepFile: 'constituent-freshness.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
templateFile: '{driftReportTemplatePath}'
loadProvenanceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-load-provenance.py'
  - '{project-root}/src/shared/scripts/skf-load-provenance.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §1 runs its
# `resolve` command to choose the audited version and bind its paths, and
# runs it with `--skill` before a flat skill moves: only a flat skill whose
# metadata.json carries an SKF marker (`flat_skf`) is migrated.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's
# index folders and SKF's workspace lock out of git, and undoes the
# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path
# exists, skip the call and continue: it never gates the workflow.
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
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

**Initialize workflow context defaults.** Before entering §1, set `confidence_mode = "normal"` as the default. §4 may upgrade this to `"degraded — all findings T1-low"` if the operator opts into degraded mode. Downstream steps (report.md, drift-report-template.md) consume this variable directly — no conditional at the usage site.

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`. It chooses the version to audit and binds its paths by the Reading Workflows rules of `knowledge/version-paths.md`, the Manifest-lag guard included, so this step never walks the export manifest or the `active` link by hand.

**If the user provides a skill name** (not a full path), run:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill_name} --forge-data-folder "{forge_data_folder}"
```

Log each entry of `resolve.errors` (a broken `active` link, for example), and `resolve.manifest_error` when it is set (an export manifest that cannot be read), as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: the export manifest or the `active` link names the version, and its package is on disk. Bind it (below).
2. `manifest-lags-link`: the `active` link names a version the export manifest has not caught up with (a writing workflow, typically update-skill, flipped the link after the last export), and the helper chose the link's version. Present the manifest-vs-symlink gate, filled from the `resolve` object:

   "**The export manifest lags behind the `active` link.**

   | | Manifest | `active` link |
   |---|---|---|
   | Version | `{active_version}` | `{symlink_target}` |
   | Exported / forged | `{manifest_last_exported}` | `{candidates.symlink.generated_at}` |

   Auditing the manifest's version would re-audit a version the skill no longer resolves to. Options:

   - **[N] Audit the link's version ({symlink_target})**: recommended. The drift report describes the version the skill resolves to now.
   - **[M] Audit the manifest's version ({active_version})**: only useful when investigating the older version specifically.
   - **[X] Abort**: halt without producing a report (exit 6, `halt_reason: "user-cancelled"`). Run `[EX] Export Skill` to reconcile the manifest before re-running audit-skill."

   When `paths.provenance_map.path` is null but `candidates.manifest.provenance_map` is set (the link's version has no provenance map and the manifest's has one), the gate adds: "`{symlink_target}` has no provenance map, so **[N]** audits it in degraded mode (text diff, T1-low findings); **[M]** audits `{active_version}` against its map." The headless log adds: `"{symlink_target} has no provenance map: pass degraded=true, or set skill_path to the {active_version} package to audit that version against its map."`

   **[N]**, the default, binds the helper's values. **[M]** runs the command above again with `--version {active_version}` and binds that run's values (its `reason` is `requested`). Headless mode auto-selects **[N]** and logs: `"headless: the manifest names {active_version} but the active link names {symlink_target}; auditing the link's version. Run export-skill to reconcile."`
3. If neither: fall back to the flat path `{skills_output_folder}/{skill_name}/` (`reason` is `flat-layout`: `SKILL.md` sits at the skill folder root, with no version folder yet). Check that SKF generated it before anything moves:
   - Run `uv run {skillInventoryHelper} "{skills_output_folder}" --skill {skill_name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** auto-migrate per `knowledge/version-paths.md` migration rules, then run the `resolve` command above again and bind its values anew: they now name the version folder.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill_name}` is not SKF output — nothing was moved.** `{skills_output_folder}/{skill_name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or audit it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill_name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. HALT with **exit 3** (the headless envelope is in the block below).
4. `missing`, or the helper stops with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version of the skill is on disk. Take the "Skill not found" halt below, naming the skill and adding the helper's `detail` or `error`.
5. `newest-on-disk`: version folders exist, but neither the export manifest nor a working `active` link names one, and the Reading Workflows rules audit only a version one of them names. Take the "Skill not found" halt below with the helper's `detail`, and add: "Point `{skills_output_folder}/{skill_name}/active` at the version to audit, then re-run."
6. Any other error, or no JSON: HALT with **exit 3**, `halt_reason: "skill-not-found"`, showing the helper's message. Nothing is written.

If no helper candidate resolves, SKF can neither choose the version nor check a flat skill's marker, and nothing moves: when `{skills_output_folder}/{skill_name}/SKILL.md` exists, take item 3's Otherwise branch; else HALT with **exit 3**, `halt_reason: "skill-not-found"`, and the message "Cannot locate `skf-skill-inventory.py` at `{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py` or `{project-root}/src/shared/scripts/skf-skill-inventory.py`. Install the SKF module or run from a development checkout with `src/` present."

**If the user provides a full path** (or the `skill_path` input is set): audit the package at that path, bypassing the export manifest and the `active` link. Read the `metadata.json` in it, bind `{skill_name}` ← its `name` (else the folder's name), and run the command above with `--version {version}` from the same file (`reason` is `requested`). When the helper stops with `SKILL_NOT_FOUND` (a package outside `{skills_output_folder}` that the manifest does not list), bind these values from the same file instead: `{audited_version}` ← that `version`, `{audited_version_reason}` ← `requested`, `{forge_version}` ← `{forge_data_folder}/{skill_name}/{version}` (the version folder `knowledge/version-paths.md` defines), and `{provenanceMap}` ← `{forge_version}/provenance-map.json` when that file exists, else null. A `metadata.json` that is missing or names no `version` leaves no version to audit: take the "Skill not found" halt below.

**Bind** the audited version from the `resolve` object, so every later step reads and writes one version folder:

- `{audited_version}` ← `chosen_version`
- `{audited_version_reason}` ← `reason`
- `{manifest_version}` ← `active_version`, kept only when it differs from `chosen_version` (else null)
- `{resolved_skill_package}` ← `skill_package` (a full path keeps the path as given)
- `{forge_version}` ← `forge_version`: the audited version's folder in the forge data, where §4 reads the provenance map and every step writes its outputs (the drift report, the extraction snapshot, the stage data and the result files)
- `{provenanceMap}` ← `paths.provenance_map.path`: the version folder's map when it exists, else the flat copy an older skill may still keep in `{forge_data_folder}/{skill_name}/`, else null

§6 writes the audited version, its reason and the manifest's version into the drift report's frontmatter, and step 6 shows them in its Provenance table.

**Validate:** Check that `SKILL.md` exists at the resolved path.
- If missing → "Skill not found at `{resolved_skill_package}`. Check the path and try again."
- If found → Continue

**Headless default** (when `{headless_mode}`): the interactive prompt and its "check the path and try again" re-prompt cannot be answered under automation, so §1 halts deterministically instead of looping. This is the origin site for the exit-2 / exit-3 rows the Exit Codes table attributes to step 1 §1 — emit the `SKF_AUDIT_RESULT_JSON` error envelope on **stderr** (shape per SKILL.md → Result Contract; `status: "error"`, `drift_score: null`, `report_path: null`, `next_workflow: null`, `audit_ref: null`) at each halt:
- **No `skill_name` supplied** (neither name nor path given): HALT with **exit 2**, `halt_reason: "input-missing"`, `skill_name: null`. Log: `"headless: no skill_name supplied; cannot resolve interactively. Re-run with skill_name set."`
- **No version to audit, or `SKILL.md` missing at `{resolved_skill_package}`** (items 4 to 6 above, a missing helper, or a full path with no usable `metadata.json`): HALT with **exit 3**, `halt_reason: "skill-not-found"`, `skill_name: {skill_name}`. Log: `"headless: skill not found at {resolved_skill_package}; no interactive retry. Check the exported skill name/path."`
- **Flat `SKILL.md` that SKF did not generate** (item 3's ownership gate): HALT with **exit 3**, `halt_reason: "not-skf-output"`, `skill_name: {skill_name}`. Log: `"headless: {skill_name} is not SKF output; nothing was moved. SKF leaves the skills it did not generate alone, so manage it yourself; relocate skills_output_folder only if it holds a module's own source."`

### 2. Load Forge Tier

Load `{sidecar_path}/forge-tier.yaml` to detect available tools.

**If file missing:**
- "Setup-forge has not been run. Cannot determine tool availability. Run `[SF] Setup Forge` first."
- HALT with **exit 3**, `halt_reason: "forge-tier-missing"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract) and log: `"headless: forge-tier.yaml missing at {sidecar_path}; run setup-forge. Aborting."`

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

### 4. Load Provenance Map

Load the provenance map at `{provenanceMap}`, the path §1 bound: the audited version's map, or the flat copy an older skill may still keep.

**Resolve `{loadProvenanceHelper}`** from `{loadProvenanceProbeOrder}`; first existing path wins. HALT if no candidate exists.

**If `{provenanceMap}` is set:**
- Normalize the map's deterministic projections in one subprocess call:

  ```bash
  uv run {loadProvenanceHelper} normalize {provenanceMap}
  ```

  Parse the emitted JSON and stash these fields in workflow context (downstream steps read them directly — no re-walk):
  - `{bounded_scan_files}` — sorted POSIX list, union of `entries[].source_file` and `file_entries[].source_file`. Step 2 `re-index.md` consumes this as the bounded scan list.
  - `{is_stack_skill}`, `{legacy_stack_provenance}` and `{compose_mode_stack}`: stack-skill flags (see Stack Skill Detection below for downstream branching).
  - `{source_root}`, `{baseline_commit}`, `{baseline_ref}` — used by §5 Resolve Source Path and §5b Detect Upstream Drift.
  - `{export_count}` ← `export_count`, `{provenance_generated_at}` ← `generated_at` and `{provenance_age_days}` ← `age_days`: the baseline facts §7 shows and §6 records. `age_days` counts from the map's `generated_at`, or from the file's modification time when the map has none.

  If the script exits non-zero, surface the stderr as a hard halt — the map is structurally invalid and downstream steps cannot proceed.

**If `{provenanceMap}` is null** (no map in the version folder, nor a flat copy):
- "No provenance map found for `{skill_name}`. This skill may not have been created by create-skill."
- "**Degraded mode available:** I can perform text-based comparison without provenance data. Findings will have T1-low confidence."
- "**[D]egraded mode** — proceed with text-diff only"
- "**[X]** — abort audit"
- Wait for user selection. If D, set `degraded_mode: true` and `confidence_mode = "degraded — all findings T1-low"`, then skip the normalize call above (no map to normalize). If X, halt workflow (exit 6, `halt_reason: "user-cancelled"`).

**Headless default** (when `{headless_mode}`): consume the pre-supplied `degraded` input from the Invocation Contract. If `degraded=true`, auto-select **[D]** (set `degraded_mode: true`, `confidence_mode = "degraded — all findings T1-low"`, skip the normalize call) and log: `"headless: no provenance map for {skill_name}; proceeding in degraded mode (text-diff, T1-low) per pre-supplied degraded=true."` If `degraded` is unset or false, auto-select **[X] abort** (exit 6, `halt_reason: "user-cancelled"`) and log: `"headless: no provenance map for {skill_name} and degraded not pre-supplied; aborting. Re-run with degraded=true for text-diff."` Never silently emit a low-confidence report under automation without explicit opt-in — same stance as the [A]-abort default at §5b's dirty-worktree sub-gate.

### Stack Skill Detection

`{is_stack_skill}`, `{legacy_stack_provenance}` and `{compose_mode_stack}` are already resolved by the normalize call in §4: no additional walk needed. Apply the post-detection logic:

If `{compose_mode_stack}` is true (a stack whose map holds `constituents[]`: a compose-mode stack), the audit takes the compose route. Its provenance entries record the constituent skills it was composed from, not a source tree, so §5 and §5b skip, and on confirmation §7 loads `{composeStepFile}` (step 1c), which checks each constituent's freshness in place of steps 2 to 4. Comparing hashes is analysis, which this step does not do.

If `{legacy_stack_provenance}` is true: log a note that this stack uses v1 provenance format with reduced audit depth (library-level only, no per-export verification).

### 5. Resolve Source Path

**A compose-mode stack** (`{compose_mode_stack}`) has no source tree to resolve: skip this section, and §5b skips too.

**If provenance map loaded:**
- Use `{source_root}` (already extracted by §4 normalize) as source code path
- Verify source path still exists and is accessible
- `{baseline_commit}` and `{baseline_ref}` are already populated by §4. If `{baseline_commit}` is null in the projection, fall back to `metadata.source_commit`. `{baseline_ref}` may be a tag, branch, `HEAD`, or `"local"`.

**If degraded mode:**
- Ask user: "Please provide the path to the current source code."
- `baseline_commit` and `baseline_ref` are unavailable — §5b will short-circuit

**Validate:** Confirm the source directory exists and is accessible. If it is missing or unreadable → HALT with **exit 3**, `halt_reason: "source-dir-missing"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract) and log: `"headless: source directory {source_root} from the provenance map no longer exists; aborting."`

### 5b. Detect Upstream Drift

Upstream drift detection is the primary use case of this workflow. If the local clone is still pinned to the baseline commit while upstream has shipped newer tags, auditing against the unchanged tree will misleadingly report CLEAN even after a major release.

**Skip this section** if any of the following hold:
- `baseline_ref` is `"local"`, `null`, or unset (non-git source)
- `{source_root}` is not a git worktree (`git -C {source_root} rev-parse --git-dir` fails)
- `baseline_commit` is unavailable
- Degraded mode is active (no provenance map)
- The skill is a compose-mode stack (`{compose_mode_stack}`): it has no source tree

When skipping, log the reason, then set the audit-ref context variables to baseline values so step 6 renders a coherent Provenance row: `audit_ref = baseline_ref or "(unknown)"`, `audit_ref_source = "baseline"` (or `"unavailable"` if both `baseline_ref` and `baseline_commit` are unset), `audit_commit = baseline_commit or "(unknown)"`, `latest_tag = null`, `remote_head = null`, and `upstream_fetch = "skipped: {reason}"`. Continue to §6.

**Otherwise:**

1. **Fetch upstream refs** (read-only, no working-tree mutation):

   ```bash
   git -C {source_root} fetch --tags --quiet origin
   ```

   When the fetch succeeds, set `upstream_fetch = "ok"`. If fetch fails (no network, no remote, detached clone), log the reason, record `upstream_fetch: "failed:{reason}"` in context, set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`, `latest_tag = null`, `remote_head = null`, and continue to §6 without gating.

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

     **Clear what SKF and ccc left in the clone before probing.** While holding the lock, run `uv run {cccGitHygieneHelper} workspace --repo "{source_root}"` from `{project-root}` (resolve `{cccGitHygieneHelper}` from `{cccGitHygieneProbeOrder}`). In an SKF workspace clone it lists `.cocoindex_code/` and `/.skf-workspace.lock` in the clone's `.git/info/exclude`, so neither ccc's index folder nor the lock file just taken shows in `git status` or goes into a `git stash --include-untracked`, and it restores a `.gitignore` whose only change is the `# CocoIndex Code (ccc)` / `/.cocoindex_code/` pair an earlier create-skill `ccc init` appended (or deletes a `.gitignore` holding only that pair). It changes nothing else, and nothing outside SKF's workspace. Read nothing from its output; if the helper does not resolve or fails, run the probe below as it stands.

     **Dirty-worktree probe (mandatory before checkout).** Run `git -C {source_root} status --porcelain` after the clean-up above and before the checkout. If the output is non-empty, the working tree has uncommitted changes — `git checkout {chosen_ref}` will abort with `error: Your local changes to the following files would be overwritten by checkout`, halting the workflow mid-step. The clean-up above already cleared the `.gitignore` edit `ccc init` leaves in a workspace clone and SKF's lock file, so what remains is most likely the operator's in-progress work or another tool's output. Surface a sub-gate before mutating:

     "**Working tree has uncommitted changes.** `git status --porcelain` returned:

     ```
     {first 20 lines of porcelain output, ellipsis if more}
     ```

     A `git checkout` would abort. Options:
     - **[T] Transient stash** — `git stash push -m 'skf-audit-skill: pre-checkout {chosen_ref}' --include-untracked`, then perform the checkout. The stash stays in `{source_root}` until the operator restores it with `git -C {source_root} stash pop`.
     - **[A] Abort** — halt the workflow and let the operator commit, stash, or discard manually before retrying.
     - **[F] Force checkout** — `git checkout --force` discards uncommitted changes irrecoverably. Only choose this after confirming the changes are safe to lose."

     **Gate handling:**
     - **[T]:** Run `git -C {source_root} stash push -m 'skf-audit-skill: pre-checkout {chosen_ref}' --include-untracked`. Capture the stash ref from the command output (e.g. `stash@{0}`) and store as `pre_checkout_stash_ref` in workflow context for step 6 Provenance to surface. Proceed to the checkout. (After audit completes, the operator restores the stash with `git stash pop` — step 6 puts the literal command in the report as a workflow-level convention rather than per-author ad-hoc prose.)
     - **[A]:** HALT the workflow. Do not write a drift report — the audit was never started.
     - **[F]:** Run `git -C {source_root} checkout --force {chosen_ref}` instead of the plain checkout. Record `pre_checkout_force_discard: true` in workflow context for step 6 to surface as a loud warning. Skip the stash path.
     - **Other input:** help user, redisplay the sub-gate.

     **Headless default** (when `{headless_mode}`): consume the pre-supplied `dirty_worktree_choice` from the Invocation Contract — the operator's explicit answer is the consent that a silent working-tree mutation would otherwise lack.
     - **`dirty_worktree_choice=T`**: run the `[T]` transient-stash path. Log: `"headless: dirty worktree at {source_root}; stashing before checkout per pre-supplied dirty_worktree_choice=T."`
     - **`dirty_worktree_choice=F` with `force=true`**: run the `[F]` force-checkout path — `force=true` is the required consent to discard uncommitted changes irrecoverably. Log: `"headless: dirty worktree at {source_root}; force-discarding uncommitted changes per pre-supplied dirty_worktree_choice=F force=true."`
     - **`dirty_worktree_choice=A`, unset, or `=F` without `force=true`**: auto-select **[A] Abort** (exit 6, `halt_reason: "user-cancelled"`). Abort is the safe default, and a force-discard without `force=true` consent is refused rather than executed. Log: `"headless: dirty worktree detected at {source_root}; refusing to checkout {chosen_ref} (dirty_worktree_choice={value or 'unset'}). Pass dirty_worktree_choice=T, or =F with force=true, to proceed non-interactively."` Stashing that is never popped could lose work; force-checkout without consent could destroy uncommitted work outright — so both require an explicit pre-supplied choice.

     If `git status --porcelain` is empty, skip the sub-gate and proceed directly to the checkout.

     Then `git -C {source_root} checkout {chosen_ref}` (prefer `latest_tag` when present, else `remote_head`). Set `audit_ref = {chosen_ref}`, `audit_ref_source = "checkout-latest"`, `audit_commit = git rev-parse HEAD`. Hold the lock through step 2 re-extraction and release only after the extraction snapshot is complete.
   - **[S]:** Keep baseline. Set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`.
   - **[X]:** HALT workflow — do not create drift report.
   - **Other input:** help user, redisplay gate.

   **Headless default** (when `{headless_mode}`): consume the pre-supplied `upstream_drift_choice` from the Invocation Contract.
   - **`upstream_drift_choice=S`, or unset**: auto-select **[S] Stay-on-baseline** (default). Set `audit_ref = baseline_ref`, `audit_ref_source = "baseline"`, `audit_commit = baseline_commit`. Log: `"headless: upstream drift detected ({baseline_ref} → {latest_tag or remote_head}); staying on baseline per upstream_drift_choice={value or 'default S'}. Pass upstream_drift_choice=C to audit against latest."` Defaulting to a checkout would mutate the working tree without consent, so `[S]` remains the default when no choice is supplied.
   - **`upstream_drift_choice=C`**: run the `[C] Checkout-and-audit-against-latest` path above — the operator's pre-supplied choice is the explicit consent that a silent ref change would otherwise lack. The dirty-worktree sub-gate still applies and consults its own pre-supplied `dirty_worktree_choice`. Log: `"headless: upstream drift detected; checking out {latest_tag or remote_head} per pre-supplied upstream_drift_choice=C."`
   - **`upstream_drift_choice=X`**: HALT the workflow (exit 6, `halt_reason: "user-cancelled"`) — do not create a drift report. Log: `"headless: upstream drift detected; aborting per pre-supplied upstream_drift_choice=X."`

5. **Record for report:** keep `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head`, `upstream_fetch`, `baseline_ref` and `baseline_commit`: §6 writes them into the drift report's frontmatter, and step 6 builds its Provenance section from there, so readers can tell which comparison actually ran.

### 6. Create Drift Report

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Record the run context in the frontmatter, so later steps read it from the file rather than from a session that may have been compacted: `confidence_mode`; `audited_version`, `audited_version_reason` and `manifest_version` (§1); `provenance_map` (`{provenanceMap}`), `provenance_generated_at` and `provenance_age_days` (§4); `baseline_ref`, `baseline_commit`, `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head` and `upstream_fetch` (§5b). Write null for a value the run does not have.
- Set `stepsCompleted: ['init']`
- Fill Audit Summary skeleton with loaded baseline data

If the write fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract).

### 7. Present Baseline Summary and Confirm (User Gate)

"**Audit Baseline Loaded**

| Field | Value |
|-------|-------|
| **Skill** | {skill_name} v{audited_version} ({audited_version_reason}) |
| **Created** | {generation_date} |
| **Source** | {source_path} |
| **Forge Tier** | {current_tier} (created at {original_tier}) |
| **Provenance Age** | {provenance_age_days} days since last extraction |
| **Export Count** | {export_count} exports in provenance map |
| **Mode** | {normal / degraded} |

**Analysis plan based on tier:**
- {Quick: text-diff comparison → T1-low for every export (read by eye)}
- {Forge: AST structural comparison → T1 for each export an ast-grep rule matches, T1-low for each export read by eye}
- {Forge+: AST structural comparison + CCC-assisted rename detection → the same labels as Forge}
- {Deep: AST structural + QMD semantic comparison → the same labels as Forge, plus T2}
- {Compose-mode stack, at any tier: constituent freshness by metadata hash (step 1c), with no source re-index}

**Ready to begin drift analysis?**"

Halt and wait for the user's go-ahead. Only proceed once the drift report has been created with baseline data populated. On confirmation (§6 already wrote the baseline and `stepsCompleted`), load, read the entire file, and execute `{nextStepFile}`, or `{composeStepFile}` when `{compose_mode_stack}` is true. On any other input, help the user, then re-ask.

**GATE [default: proceed]** — if `{headless_mode}`, auto-proceed and log: "headless: auto-continue past baseline confirmation".

