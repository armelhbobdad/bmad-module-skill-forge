---
nextStepFile: 'detect-mode.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
templateFile: '{testReportTemplatePath}'
sidecarFile: '{sidecar_path}/forge-tier.yaml'
skillsOutputFolder: '{skills_output_folder}'
# frontmatterScript resolves deterministically by probing two candidate
# paths from `{project-root}` in order. There is NO silent manual fallback —
# if neither candidate exists, the step HALTs with a diagnostic.
frontmatterScriptProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §2 runs its
# `resolve` command to choose the version under test and bind its paths,
# and runs it with `--skill` before a flat skill moves: only a flat skill
# whose metadata.json carries an SKF marker (`flat_skf`) is migrated.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{versionPathsKnowledge}` to the first existing path. §2 loads only
# its "Migration: Flat to Versioned" section, and only to migrate a flat skill.
versionPathsKnowledgeProbeOrder:
  - '{project-root}/_bmad/skf/knowledge/version-paths.md'
  - '{project-root}/src/knowledge/version-paths.md'
# Resolve `{checkWorkspaceDriftHelper}` to the first existing path; §5b HALTs
# if neither exists. It runs the workspace drift guard, once per repository
# of a stack skill.
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
# Resolve `{runLockHelper}` to the first existing path; §6a HALTs if neither
# exists. §6a takes the run lock and the run id through it, and it stays
# bound for the rest of the run: report.md §4c renews the lock through it,
# and every later HALT and report.md §7 release it.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Test

## STEP GOAL:

Discover and validate the target skill, load forge tier state to determine analysis depth, and create the test report document from template.

### 1. Receive Skill Path

If skill path was provided as workflow argument, use it directly.

**Recognized flags on the invocation:**
- `--allow-workspace-drift` — bypass the section 5b pre-flight guard that halts when local workspace HEAD does not match `metadata.source_commit`. Store `allow_workspace_drift: true` in workflow context when present. No effect when `source_commit` is unpinned or the source is not a git working tree.
- `--no-discovery` — skip the §4b Discovery Testing block in step 6 (report). Store `no_discovery: true` in workflow context when present.
- `--no-health-check` — skip the §7 health-check dispatch in step 6 (report). Store `no_health_check: true` in workflow context when present.
- `--tier=<Quick|Forge|Forge+|Deep>` — bypass the §4 forge-tier.yaml sidecar HALT. Store `tier_flag: '<value>'` in workflow context when present; §4 will set `detected_tier` directly from this value and skip the sidecar probe.
- `--threshold=<N>` — override the pass threshold for this run. Consumed by `references/score.md` §1; CLI wins over per-pipeline defaults (§1b) and the `workflow.default_threshold` scalar.

If no path provided, ask:

"**Which skill would you like to test?**

Provide the skill path or name. I'll search in `{skillsOutputFolder}`.

**Path or name:**"

### 1b. Resolve Per-Pipeline Quality Threshold

If `{pipeline_alias}` is set in the workflow data context (forwarded by the forger when TS runs inside a pipeline — see `shared/references/pipeline-contracts.md` Pipeline State), look up the alias in the per-pipeline threshold defaults table:

| Pipeline Alias | Default Threshold |
|----------------|-------------------|
| `forge-auto`   | 90                |
| `forge`        | 80                |
| `forge-quick`  | 80                |
| `campaign`     | 90                |

- **If `{pipeline_alias}` is present AND found in the table:** store the corresponding value as `{pipeline_default_threshold}` in workflow context. This variable is consumed by `references/score.md` §1 as a precedence layer between CLI `--threshold` and `{defaultThreshold}`.
- **If `{pipeline_alias}` is present but NOT in the table:** `{pipeline_default_threshold}` remains unset. Score.md falls through to `{defaultThreshold}`.
- **If `{pipeline_alias}` is absent** (standalone TS invocation, not running inside a pipeline): `{pipeline_default_threshold}` remains unset. Score.md falls through to `{defaultThreshold}`.

### 1c. Check the Runtime

From §2 on, every step runs SKF's helpers through `uv run`, which also installs the dependencies each script declares (PEP 723); bare `python3` ignores them, so a helper such as the frontmatter validator fails on its PyYAML import. Confirm that `python3` and `uv` are both on `$PATH` (`command -v python3` and `command -v uv`). If either is missing, HALT: "**test-skill needs `{the missing tool}`, which is not on your PATH.** Install it (`uv` is a documented runtime prerequisite: see `docs/getting-started.md`), then re-run." Nothing is written.

### 2. Validate Skill Exists (version-aware)

The inventory helper chooses the version to test and binds its paths by the Reading Workflows rules of the version-paths knowledge (the Manifest-lag guard included), so this step never walks the export manifest or the `active` link by hand. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} resolve {skillsOutputFolder} --skill {skill_name} --forge-data-folder {forge_data_folder}
```

Bind from its `resolve` object:

- `{resolved_version}` ← `chosen_version`
- `{resolved_skill_package}` ← `skill_package`
- `{forge_version}` ← `forge_version`: the version's folder in the forge data, where this run writes its report, its result files and its lock
- `{forge_provenance_map}` ← `paths.provenance_map.path` and `{forge_evidence_report}` ← `paths.evidence_report.path`: the version folder's file when it exists, else the flat copy an older skill may still keep in `{forge_data_folder}/{skill_name}/`, else null. Every later step reads the provenance map and the evidence report through these two bindings, except coverage-check §4c: it checks the version folder's own map, whose lines update-skill moves.

Log each entry of `resolve.errors` (a broken `active` link, for example), and `resolve.manifest_error` when it is set (an export manifest that cannot be read), as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: the export manifest or the `active` link names the version, and its package is on disk. Continue.
2. `manifest-lags-link`: the `active` link names a version the manifest has not caught up with (the Manifest-lag guard). Continue, and emit the helper's `detail` as an Info note.
3. If neither: fall back to the flat path `{skillsOutputFolder}/{skill_name}/` (`reason` is `flat-layout`: `SKILL.md` sits at the skill folder root, with no version folder yet). Check that SKF generated it before anything moves:
   - Run `uv run {skillInventoryHelper} {skillsOutputFolder} --skill {skill_name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** auto-migrate per the migration rules of `{versionPathsKnowledge}` (resolve it ← first existing path in `{versionPathsKnowledgeProbeOrder}` and load only its "Migration: Flat to Versioned" section), then run the `resolve` command above again and bind its values anew: they now name the version folder.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill_name}` is not SKF output — nothing was moved.** `{skillsOutputFolder}/{skill_name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or test it. A shared `{skillsOutputFolder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill_name}` yourself. Only if `{skillsOutputFolder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. In `{headless_mode}`, emit to **stderr** `SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"not-skf-output"}`. HALT — do not proceed.
4. `missing`, or the helper stops with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version of the skill is on disk. Take the SKILL.md error below.
5. `newest-on-disk`: version folders exist, but neither the export manifest nor a working `active` link names one. The Reading Workflows rules test only a version one of them names, so take the SKILL.md error below.
6. Any other error, or no JSON: HALT with the helper's stderr message. Nothing is written.

If no helper candidate resolves, SKF can neither choose the version nor check a flat skill's marker. Nothing moves: when `{skillsOutputFolder}/{skill_name}/SKILL.md` exists, take step 3's Otherwise branch; else HALT with "Error: cannot locate skf-skill-inventory.py at `{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py` or `{project-root}/src/shared/scripts/skf-skill-inventory.py`. Install the SKF module or run from a development checkout with src/ present."

Check that the skill package contains required files:

**Required files:**
- `{resolved_skill_package}/SKILL.md` — the skill documentation
- `{resolved_skill_package}/metadata.json` — skill metadata

**If SKILL.md missing** (or step 4 or 5 found no version to test):
"**Error: SKILL.md not found at `{resolved_skill_package}/SKILL.md`**

This skill has not been created yet. Run the **create-skill** workflow first." When step 4 applies, name the skill instead of the path and add the helper's `detail` or `error`. When step 5 applies, say instead: "**Error: no version of `{skill_name}` is named for testing.** {the helper's `detail`}. Point `{skillsOutputFolder}/{skill_name}/active` at the version to test, then re-run."

**Headless envelope (if `{headless_mode}`):** emit to **stderr**:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"target-inaccessible"}
```

HALT — do not proceed.

**If metadata.json missing:**
"**Warning:** metadata.json not found. Proceeding with limited metadata. Some checks may be skipped."

### 3. Validate Frontmatter Compliance

**3a. Resolve `{frontmatterScript}` deterministically.** Probe each candidate path in `{frontmatterScriptProbeOrder}` (in order) against the filesystem:

1. `{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py` (installed module layout)
2. `{project-root}/src/shared/scripts/skf-validate-frontmatter.py` (development-tree layout)

Use the first path that exists as `{frontmatterScript}`. There is no manual fallback.

**If neither path exists, HALT** with the diagnostic below. test-skill is a quality gate; without the deterministic validator it cannot produce a trustworthy frontmatter verdict, and a silent manual check can miss subtle spec drift. The missing helper must be restored before testing continues:

```
Error: cannot locate skf-validate-frontmatter.py at either of:
  - {project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py
  - {project-root}/src/shared/scripts/skf-validate-frontmatter.py

test-skill requires the deterministic frontmatter validator. Install the
SKF module (`skf init`) or run from a development checkout with src/ present.
```

Do not proceed. No partial test report is written.

**3b. Run the validator (30s timeout: the deterministic validator should finish in under 1s, and the cap only guards against runaway python).**

```bash
timeout 30s uv run {frontmatterScript} {resolved_skill_package}/SKILL.md --skill-dir-name {skill_name}
```

If the command trips the 30s wall-clock (exit code `124`), set
`analysis_confidence: degraded` and `toolingStatus: frontmatter-validator-timeout`
in workflow context, apply the step 5 tooling-degraded cap (score capped at
`threshold - 1` → auto-FAIL), and record the reason in evidence-report.

Parse the JSON output. Treat each `status` value explicitly:

- `status: "pass"` — continue silently.
- `status: "warn"` — display the warning below, log each issue as a pre-check finding, and continue with testing. Frontmatter issues surface in the gap report alongside coverage/coherence findings.
- `status: "fail"` — **HALT with auto-FAIL.** Frontmatter failure means the skill will be rejected by `npx skills add` and `npx skill-check check`; shipping it would produce a false PASS downstream. Write the halt note into evidence-report and exit non-zero. **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting. The output document does not exist yet (created in §6), so `report_path` is `null` — matching the other pre-report init HALTs (target-inaccessible, forge-tier-missing, workspace-drift, another-run-active). A frontmatter-invalid target is the most common failure this gate exists to catch, so a headless orchestrator must be able to branch on it (route to update-skill) rather than see an unlabelled non-zero exit:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"frontmatter-invalid"}
```

```
**Warning/Error: SKILL.md frontmatter is non-compliant with agentskills.io specification.**

{list issues from the JSON output}

This skill will fail `npx skills add` and `npx skill-check check`. {If warn:} Consider fixing frontmatter before proceeding (run `npx skill-check check <skill-dir> --fix` to auto-fix deterministic issues). {If fail:} test-skill cannot proceed — halt and repair frontmatter, then re-run.
```

### 4. Load Forge Tier State

**`--tier=<...>` flag bypass (precedes the sidecar probe).** If `tier_flag` is set in workflow context (from §1's `--tier=<Quick|Forge|Forge+|Deep>` flag), validate the value against the allowed set. On valid match: set `detected_tier` directly to the flag's value, leave `ast_grep`/`gh_cli`/`qmd` availability flags unset (downstream steps treat unset as "unknown" — analysis proceeds without tool-specific enrichment), log Info note "tier — supplied via --tier flag, sidecar bypassed", and SKIP the sidecar probe and HALT below (jump straight to §4b "Apply Tier Override"). On invalid value (not one of the four), HALT with "Error: --tier=<value> is not one of Quick, Forge, Forge+, Deep".

**Otherwise (no `--tier` flag):** Read `{sidecarFile}` to determine available analysis depth.

**If forge-tier.yaml exists:**
- Read `tier` value (Quick, Forge, Forge+, or Deep)
- Read tool availability flags (ast_grep, gh_cli, qmd)

**If forge-tier.yaml missing:**
"**Cannot proceed.** forge-tier.yaml not found at `{sidecarFile}`. Please run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep), or re-run with `--tier=<Quick|Forge|Forge+|Deep>` to bypass the sidecar."

**Headless envelope (if `{headless_mode}`):** emit to **stderr**:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"forge-tier-missing"}
```

HALT — do not proceed.

### 4b. Apply Tier Override (if set)

Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), update `detected_tier` to the override value for use in subsequent steps and output documents.

### 5. Load Skill Metadata

Read `metadata.json` to extract:
- `name` — display name
- `skill_type` — single or stack (needed for mode detection)
- `source_path` — path to source code (if present)
- `source_commit` — pinned commit the skill was extracted against (may be null for docs-only skills, `"local"` for non-git sources, or a per-repo map for stack skills)
- `source_ref` — pinned ref (tag/branch/`HEAD`) used at extraction time
- `generation_date` — when skill was generated
- `confidence_tier` — tier used during creation
- `generated_by`: the SKF workflow that built the skill (coverage-check §2 reads it at Quick tier)

If source path override was provided as optional input, use that instead.

### 5b. Verify Workspace HEAD Matches Pinned Commit

Test-skill reads `source_path` during coverage and coherence analysis. If the local workspace has drifted from `metadata.source_commit`, gap and signature-mismatch findings silently reflect the drifted tree, not the skill's pinned source: false positives that downstream update-skill runs may then "repair" by corrupting correct documentation.

The guard runs through `{checkWorkspaceDriftHelper}`, never through `git` commands run by hand. Resolve it ← first existing path in `{checkWorkspaceDriftProbeOrder}`. If neither path exists, HALT with: "Error: cannot locate skf-check-workspace-drift.py at `{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py` or `{project-root}/src/shared/scripts/skf-check-workspace-drift.py`. Install the SKF module or run from a development checkout with src/ present." No test report is written.

Run it once per source tree, from `{project-root}`, passing `--allow-drift` only when the user passed `--allow-workspace-drift`:

```bash
uv run {checkWorkspaceDriftHelper} "{tree}" --pinned-commit "{pinned_commit}" [--source-ref "{source_ref}"] [--allow-drift] --workflow test-skill
```

- **One tree:** `{tree}` is `{source_path}`, `{pinned_commit}` is `metadata.source_commit` (an empty string when it is null), and `{source_ref}` is `metadata.source_ref` when it is set.
- **A stack skill** (`metadata.source_commit` is a `{repo_path: commit}` map): one call per entry, with that repo path as `{tree}`, its commit as `{pinned_commit}`, and the same key's value of `metadata.source_ref` as `{source_ref}` when that is a map too. Check every repo: do not skip stack skills.
- Make no call for a tree that is not on disk (coverage then reads the provenance map, State 2 of the source access protocol), and log `workspace_drift_check: skipped (no local source at {tree})`. The helper itself skips a tree with no pinned commit (`""` or `"local"`) and one that is not a git working tree.

Log each call's `log_message`, then act on the statuses together:

- **Any `mismatch`** (exit 2): HALT with `halt_reason: "workspace-drift"`, displaying the `halt_message` of every tree that drifted, verbatim: it names the pinned commit and ref, the workspace HEAD, the `git checkout` that re-syncs the tree, and `--allow-workspace-drift`.

  **Headless envelope (if `{headless_mode}`):** emit to **stderr**:

  ```
  SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"workspace-drift"}
  ```

  Do not proceed. The test report has not been created; no partial writes.
- **Any `overridden`, and no `mismatch`:** carry `workspaceDrift: overridden` into the report frontmatter and set `allow_workspace_drift: true` in workflow context (consumed by step 5 §5 drift override: a PASS under drift is demoted to `pass-with-drift` and `nextWorkflow` is forced to `update-skill`, never `export-skill`). Continue.
- **Otherwise** every call is `ok` or `skipped`: set `workspaceDrift: ok` when at least one tree was checked, else `not-checked`, and continue.
- A call that exits 1 or prints no JSON could not read its tree (for example, `git` is not installed): log `workspace_drift_check: skipped (helper error: {its stderr})`, count it as `skipped`, and continue.

### 6. Create Output Document

**6a. Take the run lock and the run id.** A run spans many tool calls and turns, so no process can hold a lock for it: the lock is a file, `{forge_version}/.test-skill.lock`, that names its owner and the time, and it keeps two test-skill runs against this version from writing the same result files. Resolve `{runLockHelper}` ← first existing path in `{runLockProbeOrder}`; it stays bound for the rest of the run. If neither path exists, HALT with: "Error: cannot locate skf-run-lock.py at `{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py` or `{project-root}/src/shared/scripts/skf-run-lock.py`. Install the SKF module or run from a development checkout with src/ present." From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire --lock "{forge_version}/.test-skill.lock" --owner "test-skill:{skill_name}"
```

The owner names no run id, so the helper adds one. Bind `{run_id}` ← `run_id` (the UTC time and a random suffix, safe in file names) and `{run_owner}` ← `owner`. Every per-run artifact of this and the later steps carries `{run_id}`, and every release names `{run_owner}` (SKILL.md Workflow Rules).

**6b. Act on the result:**

- `acquired` is true: the lock is this run's. When `stale_replaced` is not null, a run that ended without releasing its lock left it: log `run lock: replaced the stale lock of {stale_replaced.held_by} (held since {stale_replaced.held_since})` and continue.
- `acquired` is false (exit 3): another run holds a lock that has not gone stale. HALT with "**Another test-skill run is active for {skill_name}.** {message}": the helper's `message` names that run, the lock file to delete when no run is active, and the time the lock goes stale. **Headless envelope (if `{headless_mode}`):** emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":null,"next_workflow":null,"exit_code":1,"halt_reason":"another-run-active"}
```

- The helper exits 1 or 2, or prints no JSON: HALT with its stderr message (exit 2: the lock file could not be written, so check that `{forge_version}` is writable). This run holds no lock, so nothing is released.

**6c. Create `{outputFile}` from `{templateFile}`** — use `{forge_version}/test-report-{skill_name}-{run_id}.md` Initial frontmatter:

```yaml
---
workflowType: 'test-skill'
skillName: '{skill_name}'
skillDir: '{resolved_skill_package}'
runId: '{run_id}'
testMode: ''
forgeTier: '{detected_tier}'
hardGate: ''
testResult: ''
score: ''
threshold: ''
analysisConfidence: '{full|degraded}'
toolingStatus: '{ok|python3-missing|uv-missing|frontmatter-validator-missing|frontmatter-validator-timeout}'
workspaceDrift: '{not-checked|ok|overridden}'
testDate: '{run_id timestamp ISO-8601 UTC}'
stepsCompleted: ['init']
nextWorkflow: ''
---
```

### 7. Report Initialization Status

Report initialization to the user: the resolved skill name, path, type, forge tier, and source path. Then proceed to mode detection.

`stepsCompleted` already holds `'init'` (§6c created the report with it), so load and execute {nextStepFile}.

