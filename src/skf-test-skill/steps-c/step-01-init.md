---
nextStepFile: './step-02-detect-mode.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
templateFile: 'templates/test-report-template.md'
sidecarFile: '{sidecar_path}/forge-tier.yaml'
skillsOutputFolder: '{skills_output_folder}'
# frontmatterScript resolves deterministically by probing two candidate
# paths from `{project-root}` in order. There is NO silent manual fallback —
# if neither candidate exists, the step HALTs with a diagnostic.
frontmatterScriptProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
versionPathsKnowledge: 'knowledge/version-paths.md'
---

# Step 1: Initialize Test

## STEP GOAL:

Discover and validate the target skill, load forge tier state to determine analysis depth, and create the test report document from template.

## Rules

- Focus only on input discovery and validation — do not begin analysis
- Validate all required files exist before proceeding

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Receive Skill Path

If skill path was provided as workflow argument, use it directly.

**Recognized flags on the invocation:**
- `--allow-workspace-drift` — bypass the section 5b pre-flight guard that halts when local workspace HEAD does not match `metadata.source_commit`. Store `allow_workspace_drift: true` in workflow context when present. No effect when `source_commit` is unpinned or the source is not a git working tree.

If no path provided, ask:

"**Which skill would you like to test?**

Provide the skill path or name. I'll search in `{skillsOutputFolder}`.

**Path or name:**"

### 2. Validate Skill Exists (version-aware)

Resolve the skill path using version-aware resolution (see `{versionPathsKnowledge}`):

1. Read `{skillsOutputFolder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skillsOutputFolder}/{skill_name}/{active_version}/{skill_name}/`
3. If not in manifest: check for `active` symlink at `{skillsOutputFolder}/{skill_name}/active` — resolve to `{skill_group}/active/{skill_name}/`
4. If neither: fall back to flat path `{skillsOutputFolder}/{skill_name}/`. If SKILL.md exists at the flat path, auto-migrate per `{versionPathsKnowledge}` migration rules
5. Store the resolved path as `{resolved_skill_package}`

Check that the skill package contains required files:

**Required files:**
- `{resolved_skill_package}/SKILL.md` — the skill documentation
- `{resolved_skill_package}/metadata.json` — skill metadata

**If SKILL.md missing:**
"**Error: SKILL.md not found at `{resolved_skill_package}/SKILL.md`**

This skill has not been created yet. Run the **create-skill** workflow first."

HALT — do not proceed.

**If metadata.json missing:**
"**Warning:** metadata.json not found. Proceeding with limited metadata. Some checks may be skipped."

### 3. Validate Frontmatter Compliance

**3a. Resolve `{frontmatterScript}` deterministically.** Probe each candidate path in `{frontmatterScriptProbeOrder}` (in order) against the filesystem:

1. `{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py` (installed module layout)
2. `{project-root}/src/shared/scripts/skf-validate-frontmatter.py` (development-tree layout)

Use the FIRST path that exists as `{frontmatterScript}`. There is no manual fallback.

**If neither path exists, HALT** with the diagnostic below. test-skill is a quality gate; without the deterministic validator it cannot produce a trustworthy frontmatter verdict, and silent manual checks have been known to miss subtle spec drift. The missing helper must be restored before testing continues:

```
Error: cannot locate skf-validate-frontmatter.py at either of:
  - {project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py
  - {project-root}/src/shared/scripts/skf-validate-frontmatter.py

test-skill requires the deterministic frontmatter validator. Install the
SKF module (`skf init`) or run from a development checkout with src/ present.
```

Do not proceed. No partial test report is written.

**3b. Run the validator (30s timeout — deterministic validator should finish in <1s; the cap only guards against runaway python).** Invoke via `uv run` so the script's PEP 723 PyYAML dependency resolves automatically; bare `python3` would fail with `ModuleNotFoundError: No module named 'yaml'` on a fresh interpreter (`docs/getting-started.md` documents uv as the runtime prereq for exactly this).

```bash
timeout 30s uv run {frontmatterScript} {resolved_skill_package}/SKILL.md --skill-dir-name {skill_name}
```

If the command trips the 30s wall-clock (exit code `124`), set
`analysis_confidence: degraded` and `toolingStatus: frontmatter-validator-timeout`
in workflow context, apply the step-05 tooling-degraded cap (score capped at
`threshold - 1` → auto-FAIL), and record the reason in evidence-report.

Parse the JSON output. Per B2, treat each `status` value explicitly:

- `status: "pass"` — continue silently.
- `status: "warn"` — display the warning below, log each issue as a pre-check finding, and continue with testing. Frontmatter issues surface in the gap report alongside coverage/coherence findings.
- `status: "fail"` — **HALT with auto-FAIL.** Frontmatter failure indicates the skill will be rejected by `npx skills add` and `npx skill-check check`; shipping it would produce a false PASS downstream. Write the halt note into the evidence-report and exit the workflow. If `{headless_mode}`, set `testResult: fail` in the output frontmatter before exiting so the result contract records the terminal state.

```
**Warning/Error: SKILL.md frontmatter is non-compliant with agentskills.io specification.**

{list issues from the JSON output}

This skill will fail `npx skills add` and `npx skill-check check`. {If warn:} Consider fixing frontmatter before proceeding (run `npx skill-check check <skill-dir> --fix` to auto-fix deterministic issues). {If fail:} test-skill cannot proceed — halt and repair frontmatter, then re-run.
```

**3c. Python runtime probe.** Before the first invocation, confirm both `python3` AND `uv` are on `$PATH` (`command -v python3` and `command -v uv`). Both are required: `uv run` shells through to `python3` under the hood AND honors the script's PEP 723 PyYAML dependency declaration that bare `python3` ignores. If either is missing, set `analysis_confidence: degraded` in workflow context and carry a **score cap** into step-05: `capped_score = threshold - 1` → forces auto-FAIL until the runtime is restored. Record the reason in evidence-report and the test report frontmatter (`analysisConfidence: degraded`, `toolingStatus: python3-missing` or `uv-missing` as appropriate). `uv` is a documented runtime prerequisite — see `docs/getting-started.md` for install instructions.

### 4. Load Forge Tier State

Read `{sidecarFile}` to determine available analysis depth.

**If forge-tier.yaml exists:**
- Read `tier` value (Quick, Forge, Forge+, or Deep)
- Read tool availability flags (ast_grep, gh_cli, qmd)

**If forge-tier.yaml missing:**
"**Cannot proceed.** forge-tier.yaml not found at `{sidecarFile}`. Please run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."

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

If source path override was provided as optional input, use that instead.

### 5b. Verify Workspace HEAD Matches Pinned Commit

Test-skill reads `source_path` during coverage and coherence analysis. If the local workspace has drifted from `metadata.source_commit`, gap and signature-mismatch findings will silently reflect the drifted tree, not the skill's pinned source — producing false positives that downstream update-skill runs may then "repair" by corrupting correct documentation.

- Resolve `pinned_commit` from `metadata.source_commit`.
- **If `pinned_commit` is null, empty, or `"local"`:** skip the guard; log `workspace_drift_check: skipped (no pinned commit)` and continue to section 6.
- **If `pinned_commit` is a per-repo map (stack skills):** iterate each `{repo_path: commit}` entry — for each repo run `git -C "{repo_path}" rev-parse HEAD` and compare to its pinned commit (accept full-SHA or short-SHA-prefix match). If ANY repo diverges and the user did not pass `--allow-workspace-drift`, HALT with exit status `halted-for-workspace-drift` listing every mismatched repo. On all-match: log `workspace_drift_check: ok (stack, {N} repos verified)` and continue to section 6. Per B6, this guard MUST iterate every repo — do not skip stack skills.
- **If `source_path` is not a git working tree** (bare checkout, tarball extract, docs-only source) — detect by `git -C "{source_path}" rev-parse --is-inside-work-tree`, non-zero exit means skip: log `workspace_drift_check: skipped (not a git working tree)` and continue to section 6.
- **Otherwise** run `git -C "{source_path}" rev-parse HEAD` and compare to `pinned_commit`. Accept full-SHA or short-SHA-prefix match (stored pins are often 8-char short hashes — see `src/knowledge/provenance-tracking.md`).
  - **On match:** log `workspace_drift_check: ok ({short_sha})` and continue.
  - **On mismatch, AND the user did not pass `--allow-workspace-drift`:** HALT with exit status `halted-for-workspace-drift`. Display:

    ```
    Workspace HEAD does not match the commit this skill was pinned against.

      pinned (metadata.source_commit): {pinned_commit}
      pinned ref (metadata.source_ref): {source_ref or "unset"}
      workspace HEAD ({source_path}):  {head_sha}

    Test-skill verifies against the source the skill was extracted from.
    Testing against a drifted tree produces false gaps/mismatches. Re-sync:

      git -C "{source_path}" checkout {source_ref or pinned_commit}

    Or re-run test-skill with `--allow-workspace-drift` to test against the
    current workspace (accepts that findings reflect HEAD, not the pin).
    ```

    Do not proceed. The test report has not been created; no partial writes.
  - **On mismatch WITH `--allow-workspace-drift`:** log `workspace_drift_check: overridden (pinned={pinned_commit}, head={head_sha})`, carry the warning into the final report frontmatter (`workspaceDrift: overridden`), and set `allow_workspace_drift: true` in workflow context (consumed by step-05 §5 M5 — a PASS under drift is demoted to `pass-with-drift` and `nextWorkflow` is forced to `update-skill`, never `export-skill`). Continue.

### 6. Create Output Document

**6a. Generate `{run_id}`** per B5: a per-run identifier of the form `{YYYYMMDDTHHmmssZ}-{pid}-{rand4}` (UTC timestamp + process PID + 4-char random hex). Store in workflow context. All per-run artifacts in this and subsequent steps MUST carry this suffix; step-06 verifies `testDate` in the resulting report matches the run's stamp and fail-fast otherwise.

**6b. Acquire the per-skill test lock** (B4): `flock {forge_version}/.test-skill.lock` for the duration of this run to serialize concurrent `skf-test-skill` invocations against the same skill. If the lock is already held by another run, HALT with "another test-skill run is active for {skill_name}".

**6c. Create `{outputFile}` from `{templateFile}`** — use `{forge_version}/test-report-{skill_name}-{run_id}.md` per B5. Initial frontmatter:

```yaml
---
workflowType: 'test-skill'
skillName: '{skill_name}'
skillDir: '{skill_path}'
runId: '{run_id}'
testMode: ''
forgeTier: '{detected_tier}'
testResult: ''
score: ''
threshold: ''
analysisConfidence: '{full|degraded}'
toolingStatus: '{ok|python3-missing|uv-missing|frontmatter-validator-missing|frontmatter-validator-timeout}'
workspaceDrift: '{not-checked|ok|overridden}'
testDate: '{run_id timestamp ISO-8601 UTC}'
stepsCompleted: ['step-01-init']
nextWorkflow: ''
---
```

### 7. Report Initialization Status

"**Test initialization complete.**

**Skill:** {skill_name}
**Path:** {skill_path}
**Type:** {skill_type}
**Forge Tier:** {detected_tier}
**Source:** {source_path}

**Proceeding to mode detection...**"

### 8. Auto-Proceed

Display: "**Proceeding to mode detection...**"

#### Menu Handling Logic:

- After initialization is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices
- Proceed directly to next step after setup

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all required files are validated, forge tier is loaded, output document is created, and initialization status is reported, will you then load and read fully `{nextStepFile}` to execute mode detection.

