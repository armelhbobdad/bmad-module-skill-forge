---
nextStepFile: 'package.md'
managedSectionData: '{managedSectionFormatPath}'
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
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Load Skill

## STEP GOAL:

To load the target skill's artifacts, validate they meet agentskills.io spec compliance, parse export flags, and confirm with the user before proceeding to packaging.

## Rules

- Focus only on loading, validating, and confirming the skill — this is read-only
- Do not write any output files yet (packaging starts in Step 02)

## MANDATORY SEQUENCE

### 1. Parse Export Arguments

"**Starting skill export...**"

Determine the skill(s) to export and any flags:

**Skill Path Discovery (version-aware — see `knowledge/version-paths.md`):**
- If user provided one or more skill names or paths as arguments, use that list directly
- If `--all` was passed, build the list from every skill in `{skills_output_folder}/.export-manifest.json.exports` whose `active_version` entry is not `status: "deprecated"` (deprecated skills are excluded from all exports — see step 4 §4b). **First-export fallback:** if the manifest is absent or its `exports` object is empty (a fresh repo with skills on disk but no prior export), do not resolve to an empty set — enumerate skills on disk instead, using the same discovery ladder as the no-argument branch below (`active` symlinks at `{skills_output_folder}/{skill-name}/active/{skill-name}/SKILL.md`, then flat `{skills_output_folder}/{skill-name}/SKILL.md`). Every disk-discovered skill is non-deprecated by definition — deprecation status lives only in the manifest.
- If no explicit skill and no `--all`, then:
  - **Headless guard:** if `{headless_mode}` is true, HALT (exit code 2, `halt_reason: "input-missing"`) — a non-interactive run cannot answer the skill-selection menu; the operator must pass an explicit `skill_name` or `--all`. Emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.
  - **Interactive:** discover available skills using the export manifest:
    1. Read `{skills_output_folder}/.export-manifest.json` — list skill names from `exports`
    2. For each skill group directory in `{skills_output_folder}/`, check for `{skill_group}/active/{skill-name}/SKILL.md`
    3. If neither manifest nor `active` symlink yields results, fall back to flat path: `{skills_output_folder}/{skill-name}/SKILL.md`
- If multiple skills are found, present the list and accept either a single selection or a comma-/space-separated multi-selection (e.g. `1, 2, 3` or `all`)
- If no skills found, HALT (exit code 3, `halt_reason: "resolution-failure"`): "No skills found in {skills_output_folder}/. Run create-skill first." In headless, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

Store the resolved selection as `skill_batch` — a list of one or more skill names. `len(skill_batch) > 1` activates multi-skill mode (see §1c below).

**Flag Parsing:**
- `--all` flag: Check if provided. When true and no explicit skill list was given, `skill_batch` is the full non-deprecated manifest set — or, when no manifest exists yet, the full on-disk discovery set (see the first-export fallback above).
- `--context-file` flag: Check if explicitly provided (CLAUDE.md, .cursorrules, or AGENTS.md). Replaces the old `--platform` flag.
- `--dry-run` flag: Check if provided. Default: `false`

**Context File Resolution:**

If `--context-file` is explicitly provided, use that single context file as the sole target. Determine the skill root from the first configured IDE that maps to that context file (or `.agents/skills/` for AGENTS.md if no matching IDE is configured). If other IDEs are configured in config.yaml, emit a note: "**Note:** Exporting to {context-file} only. config.yaml also lists: {other-ides}. Run without `--context-file` to export to all configured IDEs."

If `--context-file` is NOT provided, read the `ides` list from config.yaml and map each entry to its `context_file` and `skill_root` using the "IDE → Context File Mapping" table plus the "Resolution rules" in `{managedSectionData}` — that canonical file carries the deduplication (group by context file; first configured IDE's skill root wins), the unknown-IDE default-and-warn, and the missing-`ides`-key (treat as empty list) behavior, each with its exact warning/report string. Every IDE the installer offers has an explicit mapping — no silent skips.

Apply those rules to `config.yaml.ides`, then:

- If mapping produces one or more context files (after dedup), store as `target_context_files` list — each entry has `{context_file, skill_root}`
- If mapping produces zero entries (empty ides list and no recognized entries), fall back to `[{context_file: "AGENTS.md", skill_root: ".agents/skills/"}]` with note: "No IDEs configured in config.yaml — defaulting to AGENTS.md with `.agents/skills/`."

"**Skill(s):** {skill-batch-list} ({N} total)
**Context file(s):** {context-file-list} (skill root: {skill-root-list})
**Dry Run:** {yes/no}"

### 1b. Detect Snippet Root Prefix Mismatch

**Skip entirely if `snippet_skill_root_override` is set in `config.yaml`** — the authoring-repo escape hatch is already configured and any on-disk prefix that matches it is ground truth (see `{managedSectionData}` override rules).

**Otherwise:** load `references/preflight-snippet-root-probe.md` and follow its probe + (a) Set override / (b) Proceed with IDE mapping / (c) Cancel gate protocol. The reference handles candidate snippet collection (manifest-driven), prefix observation, the mismatch warning, and headless default ((b) Proceed). Returns control to §1c on no-mismatch fast path or after a (b) choice.

### 1c. Multi-skill Mode (when `len(skill_batch) > 1`)

**If `len(skill_batch) == 1`:** single-skill mode — every section below operates on the one skill without iteration. Skip this subsection.

**If `len(skill_batch) > 1`:** load `references/multi-skill-mode.md` and apply its per-step behavior matrix. The reference partitions work so that step 1 §2–5 iterates per skill, step 1 §6 presents a single consolidated [C] gate, step 4 batches once across the whole run, and step 7 health check runs once. It also defines the all-or-nothing halt semantics if any single skill fails §2 validation.

### 2. Load and Validate Skill Artifacts

Resolve the skill's versioned path before loading artifacts:

1. Read `{skills_output_folder}/.export-manifest.json` and look up `{skill-name}` in `exports` to get `active_version`
2. **Manifest-lag guard.** If the skill is in the manifest, also read the `active` symlink target at `{skills_output_folder}/{skill-name}/active`. If that symlink resolves to a *different* version than `active_version`, prefer the **symlink target** as `{resolved_version}` and emit an Info note: "manifest active_version {M} lags the active symlink {N} — exporting the symlink target (the just-forged version); the manifest active_version advances to {N} on this export." This is the canonical SS→TS→EX case: create-stack-skill flipped `active` to the new version, but the manifest only advances when *this* export runs. A bare manifest-first resolution would re-export the *previously exported* version, and step 4 §4b/step-5 (`update-context.md`) — which derives the published version from `{resolved_skill_package}/metadata.json` — would then write that stale version straight back as `active_version`, so the forged version could never be published. Resolving to the symlink target here makes this export publish {N} and reconcile the manifest. When the symlink matches `active_version` (or no `active` symlink exists), use `active_version`. See `knowledge/version-paths.md` "Reading Workflows".
3. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{resolved_version}/{skill-name}/`
4. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
5. If neither: fall back to flat path `{skills_output_folder}/{skill-name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
6. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading

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

The script emits one JSON verdict covering every check this step used to derive by hand: `SKILL.md` present and non-empty; `metadata.json` present and valid JSON; the required agentskills.io fields present (`name`, `version`, `skill_type`, `source_authority`, `exports`, `generation_date`, `confidence_tier`); enum membership (`skill_type` ∈ single/stack, `source_authority` ∈ official/internal/community, `confidence_tier` ∈ Quick/Forge/Forge+/Deep); a non-empty `exports` array (empty is a low warning, not a halt); and the SKILL.md Section 7b ↔ on-disk `scripts/`/`assets/` cross-reference (a §7b-named file absent on disk is a high issue; an unreferenced on-disk file is a low orphan warning). Read `result` (PASS/FAIL), `export_status` (READY/WARNINGS/NOT_READY), and the issue arrays under `validation.metadata.{issues,enum_issues}` and `validation.crossref_7b.{missing,orphans}`. **Retain this JSON as the export verdict** — step 2 (`package.md`) renders its status from it without re-deriving the checks.

**If the script cannot run** (no `uv`/Python — e.g. claude.ai web): perform the equivalent checks by hand; `python3 {validateOutputHelper} --help` documents exactly what it verifies.

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
- `confidence_tier` — Quick/Forge/Forge+/Deep

**For stack skills, also extract:**
- `components` — Array of dependencies with versions
- `integrations` — Array of co-import patterns

### 4. Check Forge Configuration

Load `{sidecar_path}/preferences.yaml` (if exists):
- Check `passive_context` setting
- If `passive_context: false` — note that steps 03-04 (snippet + context update) will be skipped

### 4b. Check Test Report (Quality Gate)

`skf-test-skill` writes timestamped test-report filenames (`test-report-{skill_name}-{ISO-TIMESTAMP}-{HASH}.md`) — there is no exact-name `test-report-{skill_name}.md` on disk. Locate the most recent report by glob, not by exact filename:

1. Glob `{forge_data_folder}/{skill_name}/{active_version}/test-report-{skill_name}-*.md` (i.e. `{forge_version}/test-report-{skill_name}-*.md`). Sort matches descending by the parsed ISO-timestamp segment in the filename (`YYYYMMDDTHHMMSSZ` between the skill name and the hash — `sort -r` on the filename works because the timestamp is the first variable component). Take the first match.
2. If the versioned glob returns nothing, fall back to the same glob at the flat path `{forge_data_folder}/{skill_name}/test-report-{skill_name}-*.md`. Pick the newest by parsed timestamp.
3. If neither glob returns anything, look for the stable companion `skf-test-skill-result-latest.json` in the same two directories (versioned first, then flat). Read the report path from `outputs[]` per the canonical contract documented at `shared/references/output-contract-schema.md` (resolved by skf-test-skill step 6 §4c) and load that file.
4. If all three lookups fail, the skill has no test report.

**If a test report is found:**

- Read frontmatter `testResult` and `score`
- If `testResult: fail`: warn: "**Warning:** This skill failed its last test (score: {score}%). Consider running `@Ferris TS` and addressing gaps before export."
- If `testResult: pass`: note: "Last test: **PASS** ({score}%)"
- Always surface the actual file picked in the message (e.g. `test-report-my-base-ui-20260507T050917Z-487606-9b2f.md`) — not the no-longer-existent `test-report-{skill_name}.md` — so an operator can navigate to the report from the log.

**If no test report found** (all three lookups returned nothing):

- Warn: "**Note:** No test report found for this skill. Consider running `@Ferris TS` before export to verify completeness."

Continue to step 5 regardless — this is advisory, not blocking.

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
| 1 | {name-1} | {type} | {authority} | {tier} | {count} | {pass/fail/none} |
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
- **Headless** [default C]: auto-proceed with [C], log "headless: auto-continue past skill confirmation".

