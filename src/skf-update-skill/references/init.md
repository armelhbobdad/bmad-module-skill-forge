---
nextStepFile: 'detect-changes.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Update

## STEP GOAL:

Load the existing skill and all its provenance data, detect whether this is an individual or stack skill, load the forge tier configuration, and present a baseline summary so the user can confirm the update scope before proceeding.

## Rules

- Focus only on loading existing artifacts and establishing the baseline — read-only operations
- Do not begin change detection (Step 02)

## MANDATORY SEQUENCE

### 1. Request Skill Path

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves via version-aware path resolution — see `knowledge/version-paths.md`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection
- `--allow-workspace-drift` (gap-driven mode only) to intentionally bypass the step 3 §0.a guard that halts when the local workspace HEAD does not match `metadata.source_commit`. Only use this if you know the spot-checks should read the current workspace instead of the pinned tree — step 6 will NOT automatically re-pin
- `--detect-only` to run detect-changes only and exit; emits the change manifest with no further work and no writes
- `--dry-run` to run detect-changes + re-extract and exit before merge/write; emits what WOULD change without modifying any artifact

**Skill:** {user provides path or name}"

**Version-Aware Path Resolution:**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill-name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading

Resolve the path to an absolute skill folder location.

**If `--from-test-report` was provided (or user references a test report):**
Search for the test report at `{forge_data_folder}/{skill_name}/{active_version}/test-report-{skill_name}.md` (i.e., `{forge_version}/test-report-{skill_name}.md`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/test-report-{skill_name}.md`. If found, set `test_report_path` in context and `update_mode: gap-driven`. If not found at either path, warn and continue with normal source drift mode.

**If `--allow-workspace-drift` was provided:** set `allow_workspace_drift: true` in workflow context. This flag is consumed by step 3 §0.a's pre-flight drift guard (gap-driven mode only) and has no effect in normal source-drift mode.

**If `--detect-only` was provided:** set `detect_only_mode: true` in workflow context. After step 2 (detect-changes) completes, jump directly to step 7 (report) — skip re-extract, merge, validate, and write. The report emits the change manifest and a `SKF_UPDATE_RESULT_JSON` envelope with `status: "detect-only"`. **Compatibility:** `--detect-only` short-circuits before §0.a runs, so `--allow-workspace-drift` is silently ignored in detect-only mode (warn the user once at flag-parse time: "`--allow-workspace-drift` has no effect with `--detect-only` — workspace drift guard runs in step 3 §0.a, which is skipped").

**If `--dry-run` was provided:** set `dry_run_mode: true` in workflow context. After step 3 (re-extract) completes, jump directly to step 7 (report) — skip merge, validate, and write. The report emits what would change with `status: "dry-run"` in the envelope. No artifact on disk is modified — `--dry-run` is the "show me what an update would do without committing" mode.

**If BOTH `--detect-only` AND `--dry-run` were provided:** `--detect-only` wins (it's the more restrictive). Warn the user once: "`--detect-only` supersedes `--dry-run`; re-extract is skipped." Set `detect_only_mode: true`, ignore `dry_run_mode`.

### 1b. Concurrency Guard

**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.** Both inspection modes are read-only — they do not modify any artifact and are safe to run alongside a concurrent real update.

Two concurrent `skf-update-skill` runs against the same `{forge_data_folder}/{skill_name}/` can corrupt provenance: one would write metadata.json mid-way through the other's extraction. The lock below catches the common accidental-double-invoke case (user re-runs in another shell before the first finishes). It is a **best-effort PID-file guard**, not a held flock — the LLM-driven workflow spans many turn boundaries and no single bash invocation can hold flock across them. Use the pattern from `skf-create-skill/references/source-resolution-protocols.md:87` (workspace concurrency guard) as the conceptual model.

**Mirror this exactly so the guard works the same way every run:**

```bash
# Lock file path — one per skill, lives next to skill-brief.yaml
LOCK={forge_data_folder}/{skill_name}/.skf-update.lock
mkdir -p "$(dirname "$LOCK")"

if [ -f "$LOCK" ]; then
  HELD_PID=$(head -n1 "$LOCK" 2>/dev/null | awk '{print $1}')
  if [ -n "$HELD_PID" ] && kill -0 "$HELD_PID" 2>/dev/null; then
    # Live PID — another update is running. HALT.
    echo "skf-update-skill: another update is in progress (pid=$HELD_PID, started $(awk 'NR==2' "$LOCK" 2>/dev/null))"
    # (LLM emits SKF_UPDATE_RESULT_JSON status=halted-for-concurrent-run, see below)
    exit 1
  fi
  # Stale lock (PID is dead) — log + overwrite
  echo "skf-update-skill: clearing stale lock from pid=$HELD_PID"
fi

# Acquire: write our PID + start timestamp (one per line)
printf '%s\n%s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOCK"
```

**Halt protocol on live-PID collision:**

- Display: `"**Another update is in progress.** The skill {skill_name} is locked by pid={HELD_PID} (started {timestamp from line 2 of the lock file}). Wait for that run to finish, or — if you know that pid is no longer running — delete {LOCK} manually and re-run."`
- In `{headless_mode}`, emit `SKF_UPDATE_RESULT_JSON` with `status: "halted-for-concurrent-run"`, `error: {phase: "init:concurrency-guard", path: "{LOCK}", reason: "another update in progress (pid={HELD_PID})"}`, and exit immediately. **No `headless_decisions[]` entry** — this is a hard halt before any gate fires.

**Release contract:**

- The terminal health-check step (step 8) deletes the lock file as its final action.
- **Every halted-for-\* path in this workflow must delete the lock before exiting** — otherwise the next attempt would see a stale lock from this run. The lock-release is a single `rm -f "$LOCK"` per halt site; do not skip it.
- The lock is best-effort: a crash mid-workflow (process kill, host reboot) leaves a stale lock that the next run will clear via the live-PID check above. No manual cleanup needed in the common case.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_package}/SKILL.md`
- If missing: **ABORT** — "No SKILL.md found at `{resolved_skill_package}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_package}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_root`
- If missing: **ABORT** — "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

**Detect skill type from metadata:**
- If `skill_type == "single"` or absent: flag as single skill
- If `skill_type == "stack"`: flag as stack skill (multi-file update mode)

### Stack Skill Guard

After loading metadata.json, check `skill_type`:
- If `skill_type` is `"stack"`: display message:
  "**Stack skills cannot be surgically updated.** Stack skills compose exports from multiple sources — surgical re-extraction requires re-running the full composition pipeline.
  
  **To update this stack skill**, run `skf-create-stack-skill` with the same project path. It will re-analyze manifests (code-mode) or re-read constituent skills (compose-mode) and produce an updated stack.
  
  If you came here from an audit report, the drift report identifies which constituent libraries changed — use that to decide whether re-composition is needed."
- Exit the workflow (do not proceed to step 2)

### 3. Load Forge Tier Configuration

**Load `{sidecar_path}/forge-tier.yaml`:**
- Extract: `tier` (Quick, Forge, Forge+, or Deep), available tools
- If missing: **ABORT** — "No forge-tier.yaml found. Run setup first to detect available tools."

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**Determine analysis capabilities:**
- **Quick:** text pattern matching only → T1-low confidence
- **Forge:** AST structural extraction → T1 confidence
- **Forge+:** AST structural extraction + CCC semantic ranking → T1 confidence (with ccc signals)
- **Deep:** AST + QMD semantic enrichment → T1 + T2 confidence

### 4. Load Provenance Map

**Load `{forge_data_folder}/{skill_name}/{active_version}/provenance-map.json`** (i.e., `{forge_version}/provenance-map.json`). If not found at the versioned path, fall back to `{forge_data_folder}/{skill_name}/provenance-map.json`:
- Extract: export list, file mappings, extraction timestamps, confidence tiers
- Calculate provenance age (days since last extraction)

**If provenance map missing at both paths:**

"**WARNING:** No provenance map found at `{forge_version}/provenance-map.json` or flat fallback.

Without a provenance map, update-skill cannot perform targeted change detection. Options:

**[D]egraded mode** — Perform full re-extraction with T1-low confidence (equivalent to re-running create-skill but preserving [MANUAL] sections)
**[X]** — Abort and run create-skill first to generate provenance data

Select: [D] Degraded / [X] Abort"

- If D: set `degraded_mode = true`, proceed with full extraction scope
- If X: **ABORT**

### 5. Load [MANUAL] Section Inventory

Load {manualSectionRulesFile} to understand [MANUAL] detection patterns.

**Scan SKILL.md for [MANUAL] sections:**
- Count all `<!-- [MANUAL:*] -->` markers
- Map each [MANUAL] block to its parent section (by heading hierarchy)
- Record section names and approximate line positions

**For stack skills, also scan:**
- All `references/*.md` files for [MANUAL] markers
- All `references/integrations/*.md` files for [MANUAL] markers

### 6. Resolve Source Code Path

**From provenance map (if available):**
- Extract `source_root` path
- Validate source path exists and is accessible

**If source path invalid or missing:**

"**Source path from provenance map is invalid:** `{source_root}`

Provide the current source code path:
**Path:** {user provides path}"

### 7. Present Baseline Summary

"**Update Skill Baseline:**

| Property | Value |
|----------|-------|
| **Skill** | {skill_name} |
| **Type** | {single/stack} |
| **Version** | {version} |
| **Created** | {created date} |
| **Source** | {source_root} |
| **Forge Tier** | {forge_tier} (current) vs {original_tier} (at creation) |
| **Provenance Age** | {days} days since last extraction |
| **Exports** | {export_count} tracked exports |
| **[MANUAL] Sections** | {manual_count} preserved sections |
| **Mode** | {normal/degraded/gap-driven} |

**Analysis plan:** {tier_description}
- {Quick: text pattern diff → T1-low findings}
- {Forge: AST structural diff → T1 findings}
- {Deep: AST structural + QMD semantic diff → T1 + T2 findings}

**Ready to detect changes and update this skill?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Change Detection"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past update confirmation". **Also append to in-context `headless_decisions[]`** (step 7 surfaces this list in `SKF_UPDATE_RESULT_JSON`): `{gate: "init.update-confirmation", default_action: "C", taken_action: "C", reason: "headless: no user to prompt"}`. The headless_decisions[] array is the structured audit trail for non-interactive runs — see `src/shared/scripts/schemas/skf-update-result-envelope.v1.json` for the entry shape.
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C] is selected and baseline has been established with all required artifacts loaded, will you then load and read fully `{nextStepFile}` to execute change detection.

