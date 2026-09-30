---
nextStepFile: 'package.md'
# Resolve `{manifestOpsHelper}` and `{rebuildManagedSectionsHelper}` to the
# first existing path of their probe orders (installed SKF module path first,
# src/ dev-checkout fallback). §1 reads the export manifest through
# `skf-manifest-ops.py` (`read`), which returns it in the v2 shape whatever
# is on disk, and resolves the context files through `resolve-targets`, the
# IDE mapping drop-skill and rename-skill also use.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# Resolve `{validateOutputHelper}` by probing `{validateOutputProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §2 runs it with `--export-gate` to obtain the
# agentskills.io export verdict — required-field presence, enum membership,
# JSON validity, and the SKILL.md Section 7b <-> scripts/assets cross-reference
# — as one deterministic JSON result, instead of re-deriving those checks
# in-prompt each run. package.md §1-4 renders its status from the same verdict.
validateOutputProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
# Resolve `{skillInventoryHelper}` to the first existing path. §2 runs its
# `resolve` action to choose the version to export and bind its paths (the
# Manifest-lag guard included), and runs it with `--skill` before a flat
# skill moves: only a flat skill whose metadata.json carries an SKF marker
# (`flat_skf`) is migrated.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Resolve `{findTestReportHelper}` to the first existing path. §4b runs its
# `find` action for the newest finished test report of the version §2 chose.
findTestReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-find-test-report.py'
  - '{project-root}/src/shared/scripts/skf-find-test-report.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Load Skill

## STEP GOAL:

To load the target skill's artifacts, validate they meet agentskills.io spec compliance, parse export flags, and confirm with the user before proceeding to packaging.

## Rules

- Focus only on loading, validating, and confirming the skill — this is read-only, except the flat-to-versioned migration in §2
- Do not write any output files yet (packaging starts in Step 02)

## MANDATORY SEQUENCE

### 1. Parse Export Arguments

"**Starting skill export...**"

Determine the skill(s) to export and any flags.

**Resolve the helpers** in parallel: `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}`, and `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}`. If either has no existing candidate, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`): "`{the missing helper}` is missing. Nothing was changed. Re-install SKF." In headless, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

**Read the export manifest** on every run, through the helper, which returns it in the v2 shape whatever is on disk (an absent file reads as an empty `exports`), so a manifest that does not parse stops the run here, before any later step reads it:

```bash
python3 {manifestOpsHelper} {skills_output_folder} read
```

Use `result.manifest.exports`. On `status: "error"` (the file does not parse), HALT (exit code 3, `halt_reason: "resolution-failure"`): "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json`: {error}. Fix or remove the file, then re-run." In headless, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

**Skill Path Discovery (version-aware — see `knowledge/version-paths.md`):**
- If user provided one or more skill names or paths as arguments, use that list directly
- If `--all` was passed, build the list from every skill in `result.manifest.exports` whose `versions.{active_version}.status` is not `"deprecated"` (deprecated skills are excluded from all exports; a skill a v1 manifest marks deprecated reads as such through the helper). **First-export fallback:** if the manifest is absent or its `exports` object is empty (a fresh repo with skills on disk but no prior export), do not resolve to an empty set: enumerate skills on disk instead, with the same inventory scan as the no-argument branch below (steps 2-3), which keeps only skills SKF generated. Every disk-discovered skill is non-deprecated by definition, since deprecation status lives only in the manifest.
- If no explicit skill and no `--all`, then:
  - **Headless guard:** if `{headless_mode}` is true, HALT (exit code 2, `halt_reason: "input-missing"`) — a non-interactive run cannot answer the skill-selection menu; the operator must pass an explicit `skill_name` or `--all`. Emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.
  - **Interactive:** discover available skills using the export manifest:
    1. List the skill names of `result.manifest.exports`
    2. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run `uv run {skillInventoryHelper} {skills_output_folder}` once. Add every `skills[]` entry whose `skf_skill` is true and whose `flat_skf` is true or `active_version` is not null (a flat SKF skill that §2 migrates, or a versioned skill with an SKF marker and an `active` link). Leave out every other folder. Bind `{not_skf_output}` ← `not_skf_output`; when it is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}".
    3. If no helper candidate resolves, add only the groups that have `{skills_output_folder}/{skill-name}/active/{skill-name}/SKILL.md`, and skip the flat path: without the helper SKF cannot check that a flat folder is its own.
- If multiple skills are found, present the list and accept either a single selection or a comma-/space-separated multi-selection (e.g. `1, 2, 3` or `all`)
- If no skills found, HALT (exit code 3, `halt_reason: "resolution-failure"`): "No skills found in {skills_output_folder}/. Run create-skill first." In headless, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

Store the resolved selection as `skill_batch` — a list of one or more skill names. `len(skill_batch) > 1` activates multi-skill mode (see §1c below).

**Flag Parsing:**
- `--all` flag: Check if provided. When true and no explicit skill list was given, `skill_batch` is the full non-deprecated manifest set — or, when no manifest exists yet, the full on-disk discovery set (see the first-export fallback above).
- `--context-file` flag: Check if explicitly provided (CLAUDE.md, .cursorrules, or AGENTS.md). Replaces the old `--platform` flag.
- `--dry-run` flag: Check if provided. Default: `false`

**Context File Resolution:**

Map the `ides` list of `config.yaml` (an absent key is an empty list) to the context files through the helper, which holds the IDE mapping of `shared/data/ide-context-files.json` and its rules: one target per context file with the first configured IDE's skill root, AGENTS.md with `.agents/skills/` for an IDE the mapping does not list (with a warning) and for an empty list (with a note):

```bash
python3 {rebuildManagedSectionsHelper} resolve-targets --ides "{ides}"
```

`{ides}` is the comma-joined `ides` list. Store `targets` as `target_context_files` (each entry `{context_file, skill_root, ides}`), bind `{other_context_files}` ← `other_context_files` (the known context files no configured IDE maps to, which step 4 §3b checks for a stale section), and display each `warnings[]` and `notes[]` line.

If `--context-file` was passed (CLAUDE.md, .cursorrules or AGENTS.md), run the call again with `--context-file {context-file}` added and store its `targets` as `target_context_files` instead: that file alone, with the skill root of the first configured IDE that maps to it, else the one the mapping gives that file. Drop that file from `{other_context_files}`, and display the call's `notes[]` (it names the configured IDEs this run leaves out).

A non-zero exit (an unknown `--context-file` value, or an IDE mapping the helper cannot read) is a HALT (exit code 3, `halt_reason: "resolution-failure"`) with the helper's `error`. In headless, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

"**Skill(s):** {skill-batch-list} ({N} total)
**Context file(s):** {context-file-list} (skill root: {skill-root-list})
**Dry Run:** {yes/no}"

### 1b. Detect Snippet Root Prefix Mismatch

**Skip entirely if `snippet_skill_root_override` is set in `config.yaml`**: the authoring-repo escape hatch is already configured and any on-disk prefix that matches it is ground truth (see the override rules in `assets/managed-section-format.md`).

**Otherwise:** load `references/preflight-snippet-root-probe.md` and follow its probe + (a) Set override / (b) Proceed with IDE mapping / (c) Cancel gate protocol. The reference handles candidate snippet collection (manifest-driven), prefix observation, the mismatch warning, and headless default ((b) Proceed). Returns control to §1c on no-mismatch fast path or after a (b) choice.

### 1c. Multi-skill Mode (when `len(skill_batch) > 1`)

**If `len(skill_batch) == 1`:** single-skill mode — every section below operates on the one skill without iteration. Skip this subsection.

**If `len(skill_batch) > 1`:** load `references/multi-skill-mode.md` and apply its per-step behavior matrix. The reference partitions work so that step 1 §2–5 iterates per skill, step 1 §6 presents a single consolidated [C] gate, step 4 batches once across the whole run, and step 7 health check runs once. It also defines the all-or-nothing halt semantics if any single skill fails §2 validation.

### 2. Load and Validate Skill Artifacts

The inventory helper chooses the version to export and binds its paths by the Reading Workflows rules of `knowledge/version-paths.md` (the Manifest-lag guard included), so this step never reads the export manifest or the `active` link by hand. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill-name} --forge-data-folder "{forge_data_folder}"
```

Bind from its `resolve` object `{resolved_version}` ← `chosen_version`, `{resolved_skill_package}` ← `skill_package`, `{forge_version}` ← `forge_version` (the version's forge folder) and `{forge_evidence_report}` ← `paths.evidence_report.path` (that folder's `evidence-report.md`, else the flat copy an older skill keeps, else null), which step 3 derives the gotchas from. Log each `resolve.errors` entry, and `resolve.manifest_error` when it is set, as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: the export manifest or the `active` link names the version, and its package is on disk. Continue.
2. `manifest-lags-link` (the Manifest-lag guard): the `active` link names a version the manifest has not caught up with, as when a create or update run flipped `active` after the last export (the SS→TS→EX order). Continue with the link's version, and emit the helper's `detail` as an Info note, followed by "Exporting v{resolved_version}: the manifest's active_version advances to it on this export." Step 4 publishes the version in `{resolved_skill_package}/metadata.json`, so the manifest catches up here.
3. `flat-layout`: fall back to the flat path `{skills_output_folder}/{skill-name}/`, where `SKILL.md` sits at the skill folder root with no version folder yet. Check that SKF generated it before anything moves:
   - Run `uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** if `--dry-run` is set, do not migrate: use the flat folder as the resolved path (the `skill_package` bound above; `{resolved_version}` and `{forge_version}` stay null) and note "would migrate {skill-name} to the versioned layout". Otherwise auto-migrate per `knowledge/version-paths.md` migration rules, then run the `resolve` command above again and bind its values anew: they now name the version folder.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill-name}` is not SKF output — nothing was moved.** `{skills_output_folder}/{skill-name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or export it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill-name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. HALT with exit code 3. In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, `manifest_path: null`, `halt_reason: "not-skf-output"`.
4. `missing`, `newest-on-disk`, or the helper stops with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version named for export is on disk. `newest-on-disk` means version folders exist but neither the export manifest nor a working `active` link names one, and export publishes only a version one of them names. HALT (exit code 3, `halt_reason: "resolution-failure"`): "**`{skill-name}` has no version to export.** {the helper's `detail`, or its `error`}. Run create-skill first, or point `{skills_output_folder}/{skill-name}/active` at the version to export, then re-run." In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, `manifest_path: null`.
5. Any other error, or no JSON: HALT (exit code 3, `halt_reason: "resolution-failure"`) with the helper's message. In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, `manifest_path: null`.

If no helper candidate resolves, SKF can neither choose the version nor check a flat skill's marker, and nothing moves: when `{skills_output_folder}/{skill-name}/SKILL.md` exists, take item 3's **Otherwise** branch (the `not-skf-output` HALT); else HALT (exit code 4, `halt_reason: "context-rebuild-failed"`): "`skf-skill-inventory.py` is missing. Nothing was changed. Re-install SKF." In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, `manifest_path: null`.

Every later step reads the skill from `{resolved_skill_package}`.

Load all files from `{resolved_skill_package}`:

**Required Files (hard halt if missing):**
- `SKILL.md` — The main skill document
- `metadata.json` — Machine-readable skill metadata

**Optional Files (note presence):**
- `references/` — Progressive disclosure directory
- `context-snippet.md` — Existing snippet (will be regenerated)

**Validation (deterministic — the export gate):**

Run the export gate against the resolved package. Resolve `{validateOutputHelper}` from `{validateOutputProbeOrder}` (first existing path wins):

```bash
python3 {validateOutputHelper} {resolved_skill_package} --export-gate
```

The script emits one JSON verdict covering every check this step used to derive by hand: `SKILL.md` present and non-empty; `metadata.json` present and a valid JSON object; the required agentskills.io fields present (`name`, `version`, `skill_type`, `source_authority`, `exports`, `generation_date`, `confidence_tier`); enum membership (`skill_type` ∈ single/stack, `source_authority` ∈ official/internal/community, and `confidence_tier` on the scale of the `skill_type`: Quick/Forge/Forge+/Deep for a single skill, T1/T1-low/T2/T3 for a stack; a stack that still holds a forge tier, as older stacks do, passes with a low warning under `validation.metadata.issues`); a non-empty `exports` array (empty is a low warning, not a halt); the recommended metadata fields for the `skill_type`, each missing or empty one a low warning under `validation.metadata.recommended_missing` (`description`, `source_repo`, `language` and `tool_versions` for a single skill, plus `ast_node_count` when `confidence_distribution.t1` is above 0; `language` and `tool_versions` for a stack); and the SKILL.md Section 7b ↔ on-disk `scripts/`/`assets/` cross-reference (only a path that starts with `scripts/` or `assets/`, optionally after `./`, names a bundled file; a §7b-named file absent on disk is a high issue; an unreferenced on-disk file is a low orphan warning). Read `result` (PASS/FAIL), `export_status` (READY/WARNINGS/NOT_READY), and the issue arrays under `validation.metadata.{issues,enum_issues,recommended_missing}` and `validation.crossref_7b.{missing,orphans}`. **Retain this JSON as the export verdict**: step 2 (`package.md`) renders its status from it without re-deriving the checks.

**If the script cannot run** (no `uv`/Python, e.g. claude.ai web): perform the checks listed above by hand, with the same severities; the docstring at the top of `{validateOutputHelper}` documents exactly what it verifies.

**If `result` is `FAIL` / `export_status` is `NOT_READY`** (any high-severity issue in `validation.*`):
"**Export cannot proceed.** Missing or invalid: {list the high-severity issue messages from the script's `validation.metadata.{issues,enum_issues}` and `validation.crossref_7b.missing`}
Run create-skill to generate a complete skill first."
Then HALT (exit code 3, `halt_reason: "resolution-failure"`). In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, `manifest_path: null`.

### 3. Read Skill Metadata

Extract from `metadata.json`:
- `name` — Skill display name
- `skill_type` — `single` or `stack`
- `source_authority` — `official`, `internal`, or `community`
- `exports` — Array of exported functions/types
- `generation_date` — When the skill was last generated
- `confidence_tier`: for a single skill, the forge tier it was compiled at (Quick/Forge/Forge+/Deep); for a stack, the dominant confidence tier of its libraries (T1/T1-low/T2/T3), with the forge tier in `forge_tier` (an older stack may hold its forge tier here instead, which the export gate reports as a low warning)

**For stack skills, also extract:**
- `components` — Array of dependencies with versions
- `integrations` — Array of co-import patterns

### 4. Check Forge Configuration

Load `{sidecar_path}/preferences.yaml` (if exists):
- Check `passive_context` setting
- If `passive_context: false`, note that steps 3 and 4 skip the snippet and the context files; step 4 still records the export in the manifest

### 4b. Check Test Report (Quality Gate)

The shared helper finds the newest finished test report of the version §2 chose. Resolve `{findTestReportHelper}` ← first existing path in `{findTestReportProbeOrder}` and run:

```bash
uv run {findTestReportHelper} find --forge-data-folder "{forge_data_folder}" --skill-name {skill-name} [--version {resolved_version}]
```

Pass `--version` with the `{resolved_version}` §2 chose, never the manifest's `active_version`, which lags a version created or updated since the last export; leave it out when `{resolved_version}` is null (a flat skill in a dry run). Build the message from its JSON (`{score}` reads `n/a` when it is null), and display each `warnings[]` line as it is:

- `status: "found"`: name the report the helper picked, the file name of its `path` (for example `test-report-my-base-ui-20260507T050917Z-487606-9b2f.md`), so an operator can open it from the log, with its verdict by `testResult`:
  - `pass`: note "Last test: **PASS** ({score}%)"
  - `fail`: warn "**Warning:** This skill failed its last test (score: {score}%). Consider running `@Ferris TS` and addressing gaps before export."
  - `pass-with-drift`: warn "**Warning:** This skill passed its last test only with `--allow-workspace-drift` (score: {score}%), against source that differs from its pinned commit. Re-test it against the pinned commit before export."
  - `inconclusive`: warn "**Warning:** This skill's last test was inconclusive (score: {score}%). Review the report before export."
  - no `testResult` (a result file that records no verdict): note "Last test report: no verdict recorded."
- `status: "not-found"`: warn "**Note:** No test report found for this skill. Consider running `@Ferris TS` before export to verify completeness."

If no helper candidate resolves, or the helper exits non-zero, note "**Note:** SKF could not check this skill's test report: {reason}." instead.

Continue to step 5 regardless: this is advisory, not blocking.

### 5. Present Skill Summary

**Single-skill mode:**

"**Skill loaded and validated.**

| Field | Value |
|-------|-------|
| **Name** | {name} |
| **Type** | {skill_type} |
| **Authority** | {source_authority} |
| **Confidence** | {confidence_tier} |
| **Exports** | {count} functions/types |
| **Generated** | {generation_date} |
| **References** | {count files or 'none'} |

**Export Configuration:**
| Setting | Value |
|---------|-------|
| **Context File(s)** | {context-file-list} (skill root: {skill-root-list}) |
| **Explicit --context-file** | {yes (user-specified) / no (from config.yaml)} |
| **Dry Run** | {yes/no} |
| **Passive Context** | {enabled/disabled} |

**Top Exports:**
{list top 5 exports from metadata}

**Is this the correct skill to export?**"

**Multi-skill mode** (`len(skill_batch) > 1`):

"**{N} skills loaded and validated.**

| # | Name | Type | Authority | Tier | Exports | Test |
|---|------|------|-----------|------|---------|------|
| 1 | {name-1} | {type} | {authority} | {tier} | {count} | {testResult, or none} |
| 2 | {name-2} | ... | ... | ... | ... | ... |
| N | {name-N} | ... | ... | ... | ... | ... |

**Export Configuration (applies to all):**
| Setting | Value |
|---------|-------|
| **Context File(s)** | {context-file-list} (skill root: {skill-root-list}) |
| **Explicit --context-file** | {yes / no (from config.yaml)} |
| **Dry Run** | {yes/no} |
| **Passive Context** | {enabled/disabled} |

**Are these the correct skills to export?**"

### 6. Confirmation Gate

Display: "**Select:** [C] Continue to packaging | [X] Cancel and exit (or type `cancel` / `exit` / `:q`)" (multi-skill mode: the single [C] gate covers the whole batch), then wait for the reply.

- **[C]** — proceed with the loaded skill data: load, read entirely, and execute `{nextStepFile}`.
- **[X]** / `cancel` / `exit` / `:q` — Display "Cancelled — no packaging or context file writes were performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []`, and `manifest_path: null`.
- **Any other input** — help the user respond, then redisplay this gate.
- **Headless** [default C]: record the decision in the run sink with the command below, log "headless: auto-continue past skill confirmation", then auto-proceed with [C]. If `record` exits non-zero, display its error line and go on: a failed `record` never stops the run.

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"load-skill.confirmation","default_action":"C","taken_action":"C","reason":"headless: auto-continue past skill confirmation"}
SKF_JSON
```

