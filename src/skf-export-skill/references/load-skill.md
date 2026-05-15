---
nextStepFile: 'package.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Load Skill

## STEP GOAL:

To load the target skill's artifacts, validate they meet agentskills.io spec compliance, parse export flags, and confirm with the user before proceeding to packaging.

## Rules

- Focus only on loading, validating, and confirming the skill — this is read-only
- Do not write any output files yet (packaging starts in Step 02)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Parse Export Arguments

"**Starting skill export...**"

Determine the skill(s) to export and any flags:

**Skill Path Discovery (version-aware — see `knowledge/version-paths.md`):**
- If user provided one or more skill names or paths as arguments, use that list directly
- If `--all` was passed, build the list from every skill in `{skills_output_folder}/.export-manifest.json.exports` whose `active_version` entry is not `status: "deprecated"` (deprecated skills are excluded from all exports — see step 4 §4b)
- If no explicit skill and no `--all`, discover available skills using the export manifest:
  1. Read `{skills_output_folder}/.export-manifest.json` — list skill names from `exports`
  2. For each skill group directory in `{skills_output_folder}/`, check for `{skill_group}/active/{skill-name}/SKILL.md`
  3. If neither manifest nor `active` symlink yields results, fall back to flat path: `{skills_output_folder}/{skill-name}/SKILL.md`
- If multiple skills are found, present the list and accept either a single selection or a comma-/space-separated multi-selection (e.g. `1, 2, 3` or `all`)
- If no skills found, halt: "No skills found in {skills_output_folder}/. Run create-skill first."

Store the resolved selection as `skill_batch` — a list of one or more skill names. `len(skill_batch) > 1` activates multi-skill mode (see §1c below).

**Flag Parsing:**
- `--all` flag: Check if provided. When true and no explicit skill list was given, `skill_batch` is the full non-deprecated manifest set (see above).
- `--context-file` flag: Check if explicitly provided (CLAUDE.md, .cursorrules, or AGENTS.md). Replaces the old `--platform` flag.
- `--dry-run` flag: Check if provided. Default: `false`

**Context File Resolution:**

If `--context-file` is explicitly provided, use that single context file as the sole target. Determine the skill root from the first configured IDE that maps to that context file (or `.agents/skills/` for AGENTS.md if no matching IDE is configured). If other IDEs are configured in config.yaml, emit a note: "**Note:** Exporting to {context-file} only. config.yaml also lists: {other-ides}. Run without `--context-file` to export to all configured IDEs."

If `--context-file` is NOT provided, read the `ides` list from config.yaml and map each IDE to its context file and skill root using the "IDE → Context File Mapping" table in `skf-export-skill/assets/managed-section-format.md`. Every IDE the installer offers has an explicit mapping — no silent skips.

For each IDE in `config.yaml.ides`:

1. Look up its `context_file` and `skill_root` from the canonical mapping table
2. If the IDE is not in the table, default to AGENTS.md / `.agents/skills/` and warn: "Unknown IDE '{value}' in config.yaml — defaulting to AGENTS.md with `.agents/skills/`"

**Deduplication:** Group by `context_file`. When multiple IDE entries map to the same context file (e.g. both `codex` and `cline` map to AGENTS.md), deduplicate so each context file appears in `target_context_files` only once. Use the **first configured IDE's** `skill_root` for that context file. Report the deduplication: "Multiple IDEs target AGENTS.md — using {first-ide}'s skill root (`{skill_root}`). Each IDE's skills are installed to its own directory."

**Missing-key handling:** If the `ides` key is absent from config.yaml (older installation or manually edited file), treat it as an empty list.

- If mapping produces one or more context files (after dedup), store as `target_context_files` list — each entry has `{context_file, skill_root}`
- If mapping produces zero entries (empty ides list and no recognized entries), fall back to `[{context_file: "AGENTS.md", skill_root: ".agents/skills/"}]` with note: "No IDEs configured in config.yaml — defaulting to AGENTS.md with `.agents/skills/`."

"**Skill(s):** {skill-batch-list} ({N} total)
**Context file(s):** {context-file-list} (skill root: {skill-root-list})
**Dry Run:** {yes/no}"

### 1b. Detect Snippet Root Prefix Mismatch

**Skip entirely if `snippet_skill_root_override` is set in `config.yaml`** — the authoring-repo escape hatch is already configured and any on-disk prefix that matches it is ground truth (see `assets/managed-section-format.md` override rules).

**Otherwise:** load `references/preflight-snippet-root-probe.md` and follow its probe + (a) Set override / (b) Proceed with IDE mapping / (c) Cancel gate protocol. The reference handles candidate snippet collection (manifest-driven), prefix observation, the mismatch warning, and headless default ((b) Proceed). Returns control to §1c on no-mismatch fast path or after a (b) choice.

### 1c. Multi-skill Mode (when `len(skill_batch) > 1`)

**If `len(skill_batch) == 1`:** single-skill mode (legacy behavior) — every section below operates on the one skill without iteration. Skip this subsection.

**If `len(skill_batch) > 1`:** load `references/multi-skill-mode.md` and apply its per-step behavior matrix. The reference partitions work so that step 1 §2–5 iterates per skill, step 1 §6 presents a single consolidated [C] gate, step 4 batches once across the whole run, and step 7 health check runs once. It also defines the all-or-nothing halt semantics if any single skill fails §2 validation.

### 2. Load and Validate Skill Artifacts

Resolve the skill's versioned path before loading artifacts:

1. Read `{skills_output_folder}/.export-manifest.json` and look up `{skill-name}` in `exports` to get `active_version`
2. If found: resolve to `{skill_package}` = `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
3. If not in manifest: check for `active` symlink at `{skills_output_folder}/{skill-name}/active` — resolve to `{skill_group}/active/{skill-name}/`
4. If neither: fall back to flat path `{skills_output_folder}/{skill-name}/`. If SKILL.md exists at the flat path, auto-migrate per `knowledge/version-paths.md` migration rules
5. Store the resolved path as `{resolved_skill_package}` for all subsequent artifact loading

Load all files from `{resolved_skill_package}`:

**Required Files (hard halt if missing):**
- `SKILL.md` — The main skill document
- `metadata.json` — Machine-readable skill metadata

**Optional Files (note presence):**
- `references/` — Progressive disclosure directory
- `context-snippet.md` — Existing snippet (will be regenerated)

**Validation Checks:**
1. `SKILL.md` exists and is non-empty
2. `metadata.json` exists and is valid JSON
3. `metadata.json` contains required fields: `name`, `version`, `skill_type`, `source_authority`, `exports`, `generation_date`, `confidence_tier`
4. `metadata.json.exports` is a non-empty array (warn if empty — graceful handling)

**If any required validation fails:**
"**Export cannot proceed.** Missing or invalid: {list failures}
Run create-skill to generate a complete skill first."

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

### 6. Present MENU OPTIONS

Display: "**Select:** [C] Continue to packaging | [X] Cancel and exit (or type `cancel` / `exit` / `:q`)" (multi-skill mode: the single [C] gate covers the whole batch)

#### Menu Handling Logic:

- IF C: Proceed with loaded skill data, then load, read entire file, then execute {nextStepFile}
- IF X (or `cancel` / `exit` / `:q`): Display "Cancelled — no packaging or context file writes were performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with the resolved `skills`, `context_files_updated: []`, and `manifest_path: null`.
- IF Any other: help user respond, then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-continue past skill confirmation"
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms the correct skill is loaded by selecting 'C' will you load and read fully `{nextStepFile}` to execute packaging.

