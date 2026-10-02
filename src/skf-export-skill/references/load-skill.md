---
nextStepFile: 'package.md'
# SKILL.md's On Activation resolved {manifestOpsHelper},
# {skillInventoryHelper}, {rebuildManagedSectionsHelper} and
# {validateOutputHelper}. §2 runs the inventory's `resolve` action to choose
# the version to export and bind its paths (the Manifest-lag guard included),
# and runs it with `--skill` before a flat skill moves: only a flat skill
# whose metadata.json carries an SKF marker (`flat_skf`) is migrated.
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
- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its envelope as `references/result-envelope.md` states

## MANDATORY SEQUENCE

### 1. Parse Export Arguments

"**Starting skill export...**"

Determine the skill(s) to export and any flags.

**Read the export manifest** on every run, through the helper, which returns it in the v2 shape whatever is on disk (an absent file reads as an empty `exports`), so a manifest that does not parse stops the run here, before any later step reads it:

```bash
python3 {manifestOpsHelper} {skills_output_folder} read
```

Use `result.manifest.exports`. On `status: "error"` (the file does not parse), HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §1`): "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json`: {error}. Fix or remove the file, then re-run."

**Skill Path Discovery (version-aware — see `knowledge/version-paths.md`):**
- If user provided one or more skill names or paths as arguments, use that list directly
- If `--all` was passed, build the list from every skill in `result.manifest.exports` whose `versions.{active_version}.status` is not `"deprecated"` (deprecated skills are excluded from all exports; a skill a v1 manifest marks deprecated reads as such through the helper). **First-export fallback:** if the manifest is absent or its `exports` object is empty (a fresh repo with skills on disk but no prior export), do not resolve to an empty set: enumerate skills on disk instead, with the same inventory scan as the no-argument branch below (steps 2-3), which keeps only skills SKF generated. Every disk-discovered skill is non-deprecated by definition, since deprecation status lives only in the manifest.
- If no explicit skill and no `--all`, then:
  - **Headless guard:** if `{headless_mode}` is true, HALT (exit code 2, `halt_reason: "input-missing"`, phase `load-skill §1`): a non-interactive run cannot answer the skill-selection menu; the operator must pass an explicit `skill_name` or `--all`.
  - **Interactive:** discover available skills using the export manifest:
    1. List the skill names of `result.manifest.exports`
    2. Run `uv run {skillInventoryHelper} {skills_output_folder}` once. Add every `skills[]` entry whose `skf_skill` is true and whose `flat_skf` is true or `active_version` is not null (a flat SKF skill that §2 migrates, or a versioned skill with an SKF marker and an `active` link). Leave out every other folder. Bind `{not_skf_output}` ← `not_skf_output`; when it is non-empty, display it once: "Skipped (not SKF output): {not_skf_output}".
- If multiple skills are found, present the list and accept either a single selection or a comma-/space-separated multi-selection (e.g. `1, 2, 3` or `all`)
- If no skills found, HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §1`): "No skills found in {skills_output_folder}/. Run create-skill first."

Store the resolved selection as `skill_batch` — a list of one or more skill names. `len(skill_batch) > 1` activates multi-skill mode (see §1c below).

**Flag Parsing:**
- `--all` flag: Check if provided. When true and no explicit skill list was given, `skill_batch` is the full non-deprecated manifest set — or, when no manifest exists yet, the full on-disk discovery set (see the first-export fallback above).
- `--context-file` flag: Check if explicitly provided (CLAUDE.md, .cursorrules, or AGENTS.md); `references/invocation-contract.md` lists it.
- `--dry-run` flag: Check if provided. Default: `false`

**Context File Resolution:**

Map the `ides` list of `config.yaml` (an absent key is an empty list) to the context files through the helper, which holds the IDE mapping of `shared/data/ide-context-files.json` and its rules: one target per context file with the first configured IDE's skill root, AGENTS.md with `.agents/skills/` for an IDE the mapping does not list (with a warning) and for an empty list (with a note):

```bash
python3 {rebuildManagedSectionsHelper} resolve-targets --ides "{ides}"
```

`{ides}` is the comma-joined `ides` list. Store `targets` as `target_context_files` (each entry `{context_file, skill_root, ides}`), bind `{other_context_files}` ← `other_context_files` (the known context files no configured IDE maps to, which step 4 §3b checks for a stale section), and display each `warnings[]` and `notes[]` line.

If `--context-file` was passed (CLAUDE.md, .cursorrules or AGENTS.md), run the call again with `--context-file {context-file}` added and store its `targets` as `target_context_files` instead: that file alone, with the skill root of the first configured IDE that maps to it, else the one the mapping gives that file. Drop that file from `{other_context_files}`, and display the call's `notes[]` (it names the configured IDEs this run leaves out).

A non-zero exit (an unknown `--context-file` value, or an IDE mapping the helper cannot read) is a HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §1`) with the helper's `error`.

"**Skill(s):** {skill-batch-list} ({N} total)
**Context file(s):** {context-file-list} (skill root: {skill-root-list})
**Dry Run:** {yes/no}"

### 1b. Snippet Root

**Skip this if `snippet_skill_root_override` is set in `config.yaml`**: the authoring-repo override already decides every `root:` path (see the override rules in `assets/managed-section-format.md`).

**Otherwise:** load `references/preflight-snippet-root-probe.md` and follow it. It asks the layout question when no earlier export chose a snippet root, takes the mismatch gate when an earlier export's root differs from the IDE mapping, and states each one's headless default. It returns here on its fast path, after the layout question's [I], or after the mismatch gate's (b) or (d), where (d) binds `{snippet_skill_root_override}` for this run; continue at §1c.

### 1c. Multi-skill Mode (when `len(skill_batch) > 1`)

**If `len(skill_batch) == 1`:** single-skill mode — every section below operates on the one skill without iteration. Skip this subsection.

**If `len(skill_batch) > 1`:** load `references/multi-skill-mode.md` and apply its per-step behavior matrix. The reference partitions work so that step 1 §2–5 iterates per skill, step 1 §6 presents a single consolidated [C] gate, step 4 batches once across the whole run, and step 7 health check runs once. It also defines the all-or-nothing halt semantics if any single skill fails §2 validation.

### 2. Load and Validate Skill Artifacts

The inventory helper chooses the version to export and binds its paths by the Reading Workflows rules of `knowledge/version-paths.md` (the Manifest-lag guard included), so this step never reads the export manifest or the `active` link by hand. Run:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill-name} --forge-data-folder "{forge_data_folder}"
```

Bind from its `resolve` object `{resolved_version}` ← `chosen_version`, `{resolved_skill_package}` ← `skill_package`, `{forge_version}` ← `forge_version` (the version's forge folder) and `{forge_evidence_report}` ← `paths.evidence_report.path` (that folder's `evidence-report.md`, else the flat copy an older skill keeps, else null), which step 3 derives the gotchas from. Log each `resolve.errors` entry, and `resolve.manifest_error` when it is set, as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: the export manifest or the `active` link names the version, and its package is on disk. Continue.
2. `manifest-lags-link` (the Manifest-lag guard): the `active` link names a version the manifest has not caught up with, as when a create or update run flipped `active` after the last export (the SS→TS→EX order). Continue with the link's version, and emit the helper's `detail` as an Info note, followed by "Exporting v{resolved_version}: the manifest's active_version advances to it on this export." Step 4 publishes the version in `{resolved_skill_package}/metadata.json`, so the manifest catches up here.
3. `flat-layout`: fall back to the flat path `{skills_output_folder}/{skill-name}/`, where `SKILL.md` sits at the skill folder root with no version folder yet. Check that SKF generated it before anything moves:
   - Run `uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** if `--dry-run` is set, do not migrate: use the flat folder as the resolved path (the `skill_package` bound above; `{resolved_version}` and `{forge_version}` stay null) and note "would migrate {skill-name} to the versioned layout". Otherwise auto-migrate per `knowledge/version-paths.md` migration rules, then run the `resolve` command above again and bind its values anew: they now name the version folder.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, or `skills[]` has no entry): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill-name}` is not SKF output: nothing was moved.** `{skills_output_folder}/{skill-name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or export it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill-name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), or the helper's `error` when the status is not `ok`. HALT with exit code 3 and phase `load-skill §2`.
4. `missing`, `newest-on-disk`, or the helper stops with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version named for export is on disk. `newest-on-disk` means version folders exist but neither the export manifest nor a working `active` link names one, and export publishes only a version one of them names. HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §2`): "**`{skill-name}` has no version to export.** {the helper's `detail`, or its `error`}. Run create-skill first, or point `{skills_output_folder}/{skill-name}/active` at the version to export, then re-run."
5. Any other error, or no JSON: HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §2`) with the helper's message.

Every later step reads the skill from `{resolved_skill_package}`.

Load all files from `{resolved_skill_package}`:

**Required Files (the export gate below halts when one is missing):**
- `SKILL.md` — The main skill document
- `metadata.json` — Machine-readable skill metadata

**Optional Files (note presence):**
- `references/` — Progressive disclosure directory
- `context-snippet.md` — Existing snippet (will be regenerated)

**Validation (the export gate):**

Run the export gate against the resolved package:

```bash
python3 {validateOutputHelper} {resolved_skill_package} --export-gate
```

The script emits one JSON verdict; its docstring lists every check: `SKILL.md` and `metadata.json` present and valid; the required agentskills.io fields and their enums (`confidence_tier` on the scale of the `skill_type`: Quick/Forge/Forge+/Deep for a single skill, T1/T1-low/T2/T3 for a stack, where an older stack's forge tier passes with a low warning); the recommended fields for the `skill_type`, each missing one a low warning; and the SKILL.md Section 7b (`## Scripts & Assets`) cross-reference against the package's `scripts/` and `assets/` files, where a file the section names that is absent on disk is a high issue and a file it does not name a low orphan warning. Read `result` (PASS/FAIL), `export_status` (READY/WARNINGS/NOT_READY), the issue arrays under `validation.metadata.{issues,enum_issues,recommended_missing}` and `validation.crossref_7b.{missing,orphans}`, and `validation.crossref_7b.{heading,heading_line}`, the Section 7b heading the gate matched and its line in SKILL.md. **Retain this JSON as the export verdict**: step 2 (`package.md`) renders its status from it without re-deriving the checks.

**If `result` is `FAIL` / `export_status` is `NOT_READY`** (any high-severity issue in `validation.*`):
"**Export cannot proceed.** Missing or invalid: {list the high-severity issue messages from the script's `validation.metadata.{issues,enum_issues}` and `validation.crossref_7b.missing`}
{when `validation.crossref_7b.missing` is not empty:} Section 7b is the `{validation.crossref_7b.heading}` heading at line {validation.crossref_7b.heading_line} of `{resolved_skill_package}/SKILL.md`.
Fix each one in the package: add the file Section 7b names or correct its path there, and give `metadata.json` the field or value the message names, or run update-skill or create-skill to rebuild the skill. Then re-run the export."
Then HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §2`).

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
- **[X]** / `cancel` / `exit` / `:q`: display "Cancelled: no packaging or context file writes were performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `load-skill §6`).
- **Any other input** — help the user respond, then redisplay this gate.
- **GATE [default: C]**: headless, record the decision in the run sink with the command below, log "headless: auto-continue past skill confirmation", then auto-proceed with [C]. If `record` exits non-zero, display its error line and go on: a failed `record` never stops the run.

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"load-skill.confirmation","default_action":"C","taken_action":"C","reason":"headless: auto-continue past skill confirmation"}
SKF_JSON
```

