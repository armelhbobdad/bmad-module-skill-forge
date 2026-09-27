---
nextStepFile: 'detect-changes.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. §5 uses its `manual-inventory` subcommand to capture the
# exact pre-write [MANUAL] inventory (per-block byte-exact interior hashes),
# which write.md §1 (HALT gate) and validate.md Check B later verify against.
# An LLM marker-count would miss an interior truncation that leaves the marker
# count unchanged.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §1 step 4 runs
# it with `--skill` before a flat skill moves: only a flat skill whose
# metadata.json carries an SKF marker (`flat_skf`) is migrated.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{sourceTreeHelper}` by probing `{sourceTreeProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves — without it a skill forged
# from a remote repository would be read at whatever commit SKF's shared
# clone of that repository is on.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Update

## STEP GOAL:

Load the existing skill and all its provenance data, detect whether this is an individual or stack skill, load the forge tier configuration, and present a baseline summary so the user can confirm the update scope before proceeding.

## Rules

- Focus only on loading existing artifacts and establishing the baseline — read-only operations, except the flat-to-versioned migration in §1 and the private source tree §6b prepares (a folder of this run's own, never the shared workspace clone)
- Do not begin change detection (Step 02)

## Steps

### 1. Request Skill Path

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves via version-aware path resolution — see `knowledge/version-paths.md`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection
- `--allow-workspace-drift` (gap-driven mode only) to intentionally bypass the step 3 §0.a guard that halts when the local workspace HEAD does not match `metadata.source_commit`. Only use this if you know the spot-checks should read the current workspace instead of the pinned tree — step 6 will NOT automatically re-pin
- `--allow-degraded` (headless mode only) to pre-authorize the lossy degraded full re-extraction if §4 finds no provenance map — without it, a headless run halts `blocked` there rather than silently rebuilding
- `--target-ref <tag|branch|HEAD|commit>` (normal mode, a skill forged from a remote repository) to read that ref's current commit instead of the skill's recorded `source_ref` — for example the newer tag an audit checked out. When the update writes, step 6 records the ref as the new `source_ref` together with the commit it read. `HEAD` follows the remote's default branch; a full 40-character commit pins that commit
- `--detect-only` to run detect-changes only and exit; emits the change manifest with no further work and no writes
- `--dry-run` to run detect-changes + re-extract and exit before merge/write; emits what WOULD change without modifying any artifact

**Skill:** {user provides path or name}"

**Version-Aware Path Resolution:**
1. Read `{skills_output_folder}/.export-manifest.json` and look up the skill name in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to the flat path `{skills_output_folder}/{skill-name}/`. If `SKILL.md` exists there, check that SKF generated it before anything moves:
   - Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`, run `uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** if the invocation carries `--detect-only` or `--dry-run` (read them from the invocation here; the flag handling below comes later), do not migrate and HALT: those modes never move a skill, and every later step reads the versioned forge workspace, which a flat skill does not have yet. Display "**`{skill-name}` still uses the flat layout — nothing was moved.** `--detect-only` and `--dry-run` never migrate a skill, and they need the versioned layout. Run `@Ferris US {skill-name}` once without them, or AS, TS or EX, to move it into that layout, then re-run with the flag." This runs before the §1b lock, so there is no lock to release. In `{headless_mode}`, emit `SKF_UPDATE_RESULT_JSON` with `status: "blocked"`, `version` and `previous_version` = `"unknown"`, `update_mode: "normal"`, `files_written: []`, `error: {phase: "init:read-only-flat-layout", path: "{skills_output_folder}/{skill-name}/", reason: "flat-layout: read-only modes never migrate a skill; run once without --detect-only or --dry-run"}`, and exit. No `headless_decisions[]` entry. Otherwise auto-migrate per `knowledge/version-paths.md` migration rules.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill-name}` is not SKF output — nothing was moved.** `{skills_output_folder}/{skill-name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or update it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill-name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. This runs before the §1b lock, so there is no lock to release. In `{headless_mode}`, emit `SKF_UPDATE_RESULT_JSON` with `status: "blocked"`, `version` and `previous_version` = `"unknown"`, `update_mode: "normal"`, `files_written: []`, `error: {phase: "init:ownership-gate", path: "{skills_output_folder}/{skill-name}/", reason: "not-skf-output: {the reason the message shows}"}`, and exit. No `headless_decisions[]` entry — this is a hard halt, not an auto-resolved gate.
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading
6. Bind `{baseline_version}` to the pre-update version — for an update this is the version being updated, i.e. the `{active_version}` resolved in step 1 above (the flat-path fallback in step 4 has no version, so use the package version read from metadata.json in §2). Step 2 §1c passes `{baseline_version}` to `skf-provenance-gap-dispatch.py` as a required argument; leaving it unbound makes the helper search a wrong/empty directory and silently return `no-report`, dropping the major-version off-ramp.

Resolve the path to an absolute skill folder location.

**If `--from-test-report` was provided (or user references a test report):**

`skf-test-skill` writes timestamped test-report filenames (`test-report-{skill_name}-{ISO-TIMESTAMP}-{HASH}.md`) — there is no exact-name `test-report-{skill_name}.md` on disk. Locate the most recent report by glob, mirroring `skf-export-skill/references/load-skill.md §4b`:

1. Glob `{forge_data_folder}/{skill_name}/{active_version}/test-report-{skill_name}-*.md` (i.e. `{forge_version}/test-report-{skill_name}-*.md`). Sort matches descending by the parsed ISO-timestamp segment in the filename (`YYYYMMDDTHHMMSSZ` between the skill name and the hash — `sort -r` on the filename works because the timestamp is the first variable component). Take the first match.
2. If the versioned glob returns nothing, fall back to the same glob at the flat path `{forge_data_folder}/{skill_name}/test-report-{skill_name}-*.md`. Pick the newest by parsed timestamp.
3. If neither glob returns anything, look for the stable companion `skf-test-skill-result-latest.json` in the same two directories (versioned first, then flat). Read the report path from `outputs[]` per the canonical contract documented at `shared/references/output-contract-schema.md` (resolved by skf-test-skill step 6 §4c) and load that file.

If a report is located, set `test_report_path` in context to the resolved absolute path and set `update_mode: gap-driven`. Surface the actual file picked in the message (e.g. `test-report-{skill_name}-20260507T050917Z-487606-9b2f.md`) so an operator can navigate to the report from the log. If all three lookups fail, warn and continue with normal source drift mode.

**If `--allow-workspace-drift` was provided:** set `allow_workspace_drift: true` in workflow context. This flag is consumed by step 3 §0.a's pre-flight drift guard (gap-driven mode only) and has no effect in normal source-drift mode.

**If `--allow-degraded` was provided:** set `allow_degraded: true` in workflow context. This flag is consumed by §4 below when no provenance map is found under `{headless_mode}`; it has no effect interactively (the [D]/[X] prompt is shown) or when a provenance map is present.

**If `--target-ref` was provided:** set `{target_ref_override}` to its value in workflow context; §6b passes it to `{sourceTreeHelper}`. Decide this after the test-report lookup above: when `update_mode` is `gap-driven` it has no effect — gap-driven mode repairs the skill at its pinned commit — so warn the user once at flag-parse time ("`--target-ref` has no effect with `--from-test-report` — gap-driven mode repairs the skill at its pinned commit") and leave `{target_ref_override}` unset. When `--from-test-report` found no report, the run continues in normal mode and keeps `{target_ref_override}`.

**If `--detect-only` was provided:** set `detect_only_mode: true` in workflow context. After step 2 (detect-changes) completes, jump directly to step 7 (report) — skip re-extract, merge, validate, and write. The report emits the change manifest and a `SKF_UPDATE_RESULT_JSON` envelope with `status: "detect-only"`. **Compatibility:** `--detect-only` short-circuits before §0.a runs, so `--allow-workspace-drift` is silently ignored in detect-only mode (warn the user once at flag-parse time: "`--allow-workspace-drift` has no effect with `--detect-only` — workspace drift guard runs in step 3 §0.a, which is skipped").

**If `--dry-run` was provided:** set `dry_run_mode: true` in workflow context. After step 3 (re-extract) completes, jump directly to step 7 (report) — skip merge, validate, and write. The report emits what would change with `status: "dry-run"` in the envelope. No artifact on disk is modified — `--dry-run` is the "show me what an update would do without committing" mode.

**If BOTH `--detect-only` AND `--dry-run` were provided:** `--detect-only` wins (it's the more restrictive). Warn the user once: "`--detect-only` supersedes `--dry-run`; re-extract is skipped." Set `detect_only_mode: true`, ignore `dry_run_mode`.

### 1b. Concurrency Guard

**Skip this section entirely if `detect_only_mode` OR `dry_run_mode` is true.** Both inspection modes are read-only — they do not modify any artifact, the private source tree §6b prepares for them never writes to the shared workspace clone, and they are safe to run alongside a concurrent real update.

Two concurrent `skf-update-skill` runs against the same `{forge_data_folder}/{skill_name}/` can corrupt provenance: one would write metadata.json mid-way through the other's extraction. The lock below catches the common accidental-double-invoke case (user re-runs in another shell before the first finishes). It is a **best-effort PID-file guard**, not a held flock — the LLM-driven workflow spans many turn boundaries and no single bash invocation can hold flock across them. Use the workspace concurrency guard in `skf-create-skill/references/source-resolution-protocols.md` as the conceptual model; that guard's `.skf-workspace.lock` on the source clone is a separate lock, which only write.md §6b takes.

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
  # Dead PID — lock left by a prior halted or crashed run; clear + overwrite
  echo "skf-update-skill: clearing lock from a prior halted/crashed run (pid=$HELD_PID)"
fi

# Acquire: write our PID + start timestamp (one per line)
printf '%s\n%s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOCK"
```

**Halt protocol on live-PID collision:**

- Display: `"**Another update is in progress.** The skill {skill_name} is locked by pid={HELD_PID} (started {timestamp from line 2 of the lock file}). Wait for that run to finish, or — if you know that pid is no longer running — delete {LOCK} manually and re-run."`
- In `{headless_mode}`, emit `SKF_UPDATE_RESULT_JSON` with `status: "halted-for-concurrent-run"`, `error: {phase: "init:concurrency-guard", path: "{LOCK}", reason: "another update in progress (pid={HELD_PID})"}`, and exit immediately. **No `headless_decisions[]` entry** — this is a hard halt before any gate fires.

**Release contract:**

- The terminal health-check step (step 8) deletes the lock as its final action — the normal end of every non-inspection run. The init-stage headless halts below (§4 no-provenance-map, §6 invalid-source-path, §6b source tree) also delete it explicitly, since they fire right after acquisition, before the terminal step runs — except in `--detect-only` or `--dry-run`, which never acquired it.
- Mid-workflow halts (detect-changes, re-extract, merge, write) do **not** delete the lock themselves — they rely on the self-heal below. This is deliberate: several of those halt sites are also reachable under `--detect-only`/`--dry-run`, which never acquired this lock, so a blind `rm -f` there could clobber a concurrent real update's lock.
- The lock is best-effort and self-healing: whatever a halt or crash (process kill, host reboot) leaves behind is cleared by the next run's live-PID check above, since the stored PID is a short-lived bash PID that is already dead. No manual cleanup needed in the common case.
- The private source tree §6b prepares has its own contract: step 8 removes it, every HALT or ABORT after §6b removes it first (SKILL.md Workflow Rules), and a later run's §6b removes a tree a crashed or abandoned run left behind once it is seven days old.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_package}/SKILL.md`
- If missing: **ABORT** — "No SKILL.md found at `{resolved_skill_package}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_package}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_type` (when present), `source_repo`, `source_root`, `source_ref`, `source_commit`
- If missing: **ABORT** — "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

**Detect skill type from metadata:**
- If `skill_type == "single"` or absent: flag as single skill
- If `skill_type == "stack"`: flag as stack skill — the guard below redirects it

### Stack Skill Guard

After loading metadata.json, check `skill_type`:
- If `skill_type` is `"stack"`: display message:
  "**Stack skills cannot be surgically updated.** Stack skills compose exports from multiple sources — surgical re-extraction requires re-running the full composition pipeline.
  
  **To update this stack skill**, run `skf-create-stack-skill` with the same project path. It will re-analyze manifests (code-mode) or re-read constituent skills (compose-mode) and produce an updated stack.
  
  If you came here from an audit report, the drift report identifies which constituent libraries changed — use that to decide whether re-composition is needed."
- Exit the workflow (do not proceed to step 2)

**This guard is the single gate for stack skills** — every stack is redirected to `skf-create-stack-skill` here, before step 2, and no flag (`--detect-only`, `--dry-run`, `--from-test-report`, `--allow-workspace-drift`) bypasses it. Every later stage therefore runs against a single skill only and carries no stack-merge branch.

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

**In `{headless_mode}` without `--allow-degraded` (default):** do not auto-select [D]. Degraded mode is a full, lossy T1-low re-extraction — choosing it unattended would silently swap surgical update for a create-skill-equivalent rebuild, a policy call that belongs to an operator. Halt instead: release the lock unless `detect_only_mode` or `dry_run_mode` is true (`rm -f "$LOCK"`), emit `SKF_UPDATE_RESULT_JSON` with `status: "blocked"`, `error: {phase: "init:load-provenance-map", path: "{forge_version}/provenance-map.json", reason: "no provenance map at versioned or flat path; degraded full re-extraction needs a human decision"}`, and exit. No `headless_decisions[]` entry — this is a hard halt, not an auto-resolved gate.

**In `{headless_mode}` with `--allow-degraded` (`allow_degraded: true`):** the operator pre-authorized the lossy rebuild for this run, so treat it as an auto-resolved [D] rather than a halt. Set `degraded_mode = true`, proceed with full extraction scope, and append to in-context `headless_decisions[]`: `{gate: "init.degraded-rebuild", default_action: "X", taken_action: "D", reason: "headless: --allow-degraded pre-authorized degraded full re-extraction", evidence: "no provenance map at {forge_version}/provenance-map.json or flat fallback"}`. Continue to step 2.

### 5. Load [MANUAL] Section Inventory

Load {manualSectionRulesFile} to understand [MANUAL] detection patterns (the human-readable rules for markers, parent-section mapping, and orphan/nesting handling).

**Capture the [MANUAL] inventory deterministically.** The workflow's headline rule is "[MANUAL] sections survive regeneration with zero content loss" — the pre-write inventory captured here is the exact baseline that write.md §1 and validate.md Check B verify against, so it must be a per-block byte-exact hash, not an eyeballed marker count. Run the `manual-inventory` subcommand of `{hashContentHelper}` and persist its JSON:

```bash
uv run {hashContentHelper} manual-inventory {resolved_skill_package}/SKILL.md \
    > {forge_version}/.manual-inventory.json
```

The emitted JSON is `{"blocks":[{name, content_hash, byte_offset, parent_heading}...], "count":N}` — each `content_hash` covers the block's byte-exact interior, so a later interior truncation that leaves the marker count unchanged is still caught. Bind the persisted path as `{manual_inventory}` in context; write.md §1 and validate.md Check B pass it to `manual-verify`. Surface the block `count` in the baseline summary (§7 `{manual_count}`).

### 6. Resolve the Source

Bind the source fields from the `metadata.json` loaded in §2 — the provenance map does not carry `source_root`: `{source_root}` ← `source_root`, `{source_repo}` ← `source_repo`, `{source_ref}` ← `source_ref` and `{source_commit}` ← `source_commit`, each an empty string when the field is null or missing. `{source_ref}` and `{source_commit}` keep these values for the whole run: step 6 records any new commit in the artifacts only.

- **Docs-only skill** (`source_type: "docs-only"` in the brief or metadata.json, as step 3 §1 checks): there is no source tree. Skip §6b, §6c and the path check below. If `{target_ref_override}` is set, HALT as §6b's **Every §6b HALT** describes, with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository".
- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair reads the commit the skill is pinned to, and step 3 §0.a checks that `{source_root}` holds it before reading anything. Skip §6b and §6c and run the path check below.
- **Every other mode**, `--detect-only` and `--dry-run` included: run §6b. §6b runs the path check below only when the helper reports `skipped`.

**Path check:** validate that `{source_root}` exists and is accessible.

**If the source path is invalid or missing:**

"**Source path from metadata.json is invalid:** `{source_root}`

Provide the current source code path:
**Path:** {user provides path}"

Bind `{source_root}` to the path the user gives.

**In `{headless_mode}`:** there is no operator to supply a path. Halt: release the lock unless `detect_only_mode` or `dry_run_mode` is true (`rm -f "$LOCK"`), emit `SKF_UPDATE_RESULT_JSON` with `status: "blocked"`, `error: {phase: "init:resolve-source-path", path: "{source_root}", reason: "source_root from metadata.json is invalid or inaccessible and no interactive path can be supplied"}`, and exit. No `headless_decisions[]` entry — this is a hard halt, not an auto-resolved gate.

### 6b. Prepare the Source Tree

A skill forged from a remote repository at Forge tier or above records, as its `source_root`, the clone SKF keeps for that repository. Every SKF run on the repository shares that clone and leaves it at the commit it needed, so this run never reads it as it stands. `{sourceTreeHelper}` gives the run a private tree at one commit — the commit `{source_ref}` points to upstream now, or the tag, branch, `HEAD` or commit `--target-ref` names — and lists the files git changed between `{source_commit}` and that commit. Change detection, re-extraction, merge's file copies and write's citation check all read that tree. The helper never writes to the shared clone — step 6 moves the clone at the end of a real update — so this section runs in every mode.

Resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`; it stays bound for the rest of the run (every later HALT and step 8 use it). Bind `{tree_timeout}` to the seconds the helper may take: `100` when your shell tool stops a command after two minutes or you do not know its limit, otherwise a little under that limit, such as `540` under a 10-minute limit — a first fetch of a large repository is slow. The helper stops itself within `--timeout` seconds and still prints its result, so give the command a shell timeout longer than `{tree_timeout}`. From `{project-root}`, run:

```bash
uv run {sourceTreeHelper} open \
    --source-repo "{source_repo}" \
    --source-root "{source_root}" \
    --source-ref "{source_ref}" \
    --pinned-commit "{source_commit}" \
    --timeout "{tree_timeout}" \
    [--target-ref "{target_ref_override}"]
```

Pass `--target-ref` only when `{target_ref_override}` is set.

Bind `{source_tree_status}` ← `status`, `{source_tree_reason}` ← `reason`, `{source_tree_message}` ← `message`, `{source_tree}` ← `tree`, `{workspace_clone}` ← `clone`, `{target_ref}` ← `target_ref`, `{target_commit}` ← `target_commit`, `{source_moved}` ← `moved`, `{source_diff_status}` ← `diff_status`, `{source_changed_files}` ← `changed_files`, `{source_changed_counts}` ← `changed_counts` and `{source_tree_warnings}` ← `warnings`. Add each `{source_tree_warnings}` entry to `warnings[]` as `source-tree: <entry>`. `{source_tree}` is the tree itself; `{source_changed_files}` and `run.json` sit in its run folder, one level up.

What the helper does:

- **Which sources it takes.** Only the clone SKF keeps for a remote repository: `{source_repo}` names that repository and `{source_root}` is the clone path SKF computes for it (compared as resolved paths, so a trailing slash or `~` does not matter), or a clone of the same repository at `repos/<host>/<owner>/<repo>` in any SKF workspace folder, whatever the letter case of those folder names. Any other source — a local folder, or the remote URL a Quick-tier skill records — is read as it stands (`skipped`).
- **The commit.** It asks the remote which commit the ref points to (a tag before a branch of the same name; an annotated tag resolves to its commit), fetches that one commit into a folder of this run's own and checks it out there. It takes the objects from the shared clone when the clone already has them, and never writes to the clone. When the remote cannot be reached or the commit cannot be fetched, and `--target-ref` was not given, it checks out `{source_commit}` from the shared clone instead (`offline`).
- **The file list.** It writes git's list of added, modified and deleted files between `{source_commit}` and the tree's commit to `{source_changed_files}`; `{source_diff_status}` is `unavailable` when `{source_commit}` cannot be read.
- **Housekeeping.** It first removes trees earlier runs left behind for seven days or more.

Dispatch on `{source_tree_status}`:

- **`ready`** (exit 0): bind `{source_root}` ← `{source_tree}`; every later step reads source there. No step writes `{source_tree}` into an artifact.
- **`offline`** (exit 0): bind `{source_root}` ← `{source_tree}` — a tree at the skill's own `{source_commit}` — display `{source_tree_message}` as a warning, and add `source-not-fetched: {source_tree_message}` to `warnings[]`. This run compares the skill with the commit it was built from and cannot see upstream changes.
- **`skipped`** (exit 0): keep `{source_root}` from metadata.json and run §6's path check. If `{target_ref_override}` is set, HALT as below with `{source_tree_reason}` = `target-ref-needs-remote-source` and `{source_tree_message}` = "`--target-ref` applies only to a skill forged from a remote repository".
- **`unavailable`** (exit 3): no commit to read could be obtained (`{source_tree_reason}` is `invalid-ref`, `git-unavailable`, `upstream-unreachable`, `ref-not-found`, `fetch-failed`, `checkout-failed`, `tree-folder-failed` or `timed-out`). When it is `timed-out` and your shell tool allows a command longer than `{tree_timeout}` seconds, raise `{tree_timeout}` toward that limit, run the command once more and dispatch on that result. Otherwise HALT before any step reads source; display `{source_tree_message}`. The helper leaves no tree behind.
- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:** HALT with `{source_tree_reason}` = `helper-failed` and `{source_tree_message}` = "skf-source-tree.py did not finish: {the first stderr line; 'the shell stopped it before it printed a result' when your shell tool's timeout ended it; or 'it is missing; re-install SKF'}". A tree a stopped run left behind is removed by a later run once it is seven days old. Reading the shared clone as it stands is what this section exists to prevent.

**Every §6b HALT:** release the lock unless `detect_only_mode` or `dry_run_mode` is true (`rm -f "$LOCK"`). In `{headless_mode}`, emit `SKF_UPDATE_RESULT_JSON` with `status: "blocked"`, `version` and `previous_version` = the metadata.json `version`, `update_mode` from this run, `files_written: []`, `error: {phase: "init:source-tree", path: "{source_repo}", reason: "{source_tree_reason}: {source_tree_message}"}`, and exit. No `headless_decisions[]` entry — this is a hard halt, not an auto-resolved gate.

### 6c. Detect the Source Version

Run only when `{source_tree_status}` is `ready` or `offline`. Read the source's version from `{source_root}` with the Version Reconciliation rules of `skf-create-skill/references/source-resolution-protocols.md` — the version file for the detected language (`pyproject.toml`, `setup.py`, `__version__`, `package.json`, `Cargo.toml`, `go.mod`) and its monorepo `package.json` priority, matching package names against this skill's `name` — and strip build metadata as `knowledge/version-paths.md` does. When the result is a higher semantic version than the metadata.json `version`, bind `{source_version_detected}` to it: step 4 §6b and step 6 §2 name the version this update writes after it. Otherwise leave `{source_version_detected}` unset; when the source's major and minor version numbers are lower than those of `{version}` (compare the pair: 1.9.x is lower than 2.0.x), add `source-version-lower: {target_ref} reads {that version}, older than {version}; this update keeps the patch-version rule` to `warnings[]`. A source version lower only in its patch number is expected, not a regression: every update that finds no higher version increments the skill's patch number (step 4 §6b), so a skill forged at the source's 1.2.0 is 1.2.1 after one update while the source still reads 1.2.0.

### 7. Present Baseline Summary

"**Update Skill Baseline:**

| Property | Value |
|----------|-------|
| **Skill** | {skill_name} |
| **Type** | single |
| **Version** | {version} |
| **Created** | {created date} |
| **Source** | {source_display} |
| **Source commit** | {source_commit_line} |
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

`{source_display}` is `{source_repo}` at `{target_ref}` when `{source_tree_status}` is `ready` or `offline` — plus ` (re-pinned from {source_ref})` when `{target_ref_override}` is set — and `{source_root}` otherwise. `{source_commit_line}` shows commits as their first 8 characters:

- `ready` and `{source_moved}` true: `{source_commit} → {target_commit}` plus ` ({added} added, {modified} modified, {deleted} deleted files)` from `{source_changed_counts}`, or ` (file list unavailable)` when `{source_diff_status}` is `unavailable`;
- `ready` and `{source_moved}` false: `{target_commit} (no newer commit)`;
- `ready` and `{source_moved}` null: `{target_commit} (no pinned commit before this run)`;
- `offline`: `{source_commit} (upstream not reached — comparing the pinned commit only)`;
- any other source: `{source_commit} (read as it stands)`.

Steps 6 and 7 reuse `{source_display}` and `{source_commit_line}`.

### 8. Confirmation Gate

Present "**Select:** [C] Continue to Change Detection" and wait for the user to confirm; on [C], load, read the full file, then execute {nextStepFile}.

**Headless (`{headless_mode}` true):** auto-continue and append to in-context `headless_decisions[]` (step 7 surfaces it in `SKF_UPDATE_RESULT_JSON`): `{gate: "init.update-confirmation", default_action: "C", taken_action: "C", reason: "headless: no user to prompt"}`. Entry shape: `src/shared/scripts/schemas/skf-update-result-envelope.v1.json`.

