---
tierRulesData: 'references/tier-rules.md'
nextStepFile: './step-05-health-check.md'
---

# Step 4: Forge Status Report

## STEP GOAL:

Display the forge status report with positive capability framing and report tier changes on re-run.

## Rules

- Focus only on displaying the status report
- Do not use negative framing ("missing", "lacking", "unavailable")
- Do not list tools that are not available
- Use tier capability descriptions from tier-rules.md
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing status report is NOT the terminal step

## MANDATORY SEQUENCE

### 1. Load Capability Descriptions

Load and read {tierRulesData} for the tier capability descriptions and re-run messages.

### 2. Display Forge Status Report

**Format the report as follows:**

```
═══════════════════════════════════════
  FORGE STATUS
═══════════════════════════════════════

  Tier:  {calculated_tier}
  {tier capability description from tier-rules.md}

  Tools Detected:
  {for each tool that is available, show: tool name — version}
  {if no tools are available: (none yet — see "Climb to next tier" below)}

  {if calculated_tier is not Deep:}
  Climb to next tier:
  {if not tools.ast_grep: - Install ast-grep (https://ast-grep.github.io) — unlocks AST-backed code analysis (Forge tier)}
  {if tools.ast_grep and not tools.ccc: - Install cocoindex-code (https://github.com/cocoindex-io/cocoindex-code) — adds semantic-guided precision compilation (Forge+ tier)}
  {if tools.ast_grep and not tools.gh_cli: - Install GitHub CLI (https://cli.github.com) — required for Deep tier (cross-repository synthesis)}
  {if tools.ast_grep and not tools.qmd and qmd_status is "absent": - Install qmd (https://github.com/tobi/qmd) — required for Deep tier (knowledge search)}
  {if tools.ast_grep and not tools.qmd and qmd_status is "daemon_stopped": - Start the qmd daemon (already installed) — run `qmd start` (or your distribution's qmd service command) to unlock Deep tier (knowledge search)}
  {end if}

  {if hygiene_result is "completed":}
  QMD Registry:
  {hygiene_healthy} collection(s) healthy
  {if hygiene_orphaned_removed > 0: {hygiene_orphaned_removed} orphaned collection(s) removed}
  {if hygiene_orphaned_kept > 0: {hygiene_orphaned_kept} orphaned collection(s) kept}
  {if hygiene_stale_cleaned > 0: {hygiene_stale_cleaned} stale QMD registry entry/entries cleaned}
  {end if}

  {if ccc_registry_stale_cleaned > 0:}
  CCC Registry: {ccc_registry_stale_cleaned} stale entry/entries cleaned
  {end if}

  {if hygiene_result is "completed" and hygiene_healthy is 0:}
  QMD Registry: empty — collections are created automatically when you run [CS] Create Skill.
  {end if}

  {if tools.ccc is true:}
  CCC Index:
  {if ccc_index_result is "fresh": up to date — semantic discovery ready}
  {if ccc_index_result is "created": indexed this run — semantic discovery ready}
  {if ccc_index_result is "failed": indexing failed — semantic discovery unavailable this session}
  {end if}

  Files written this run:
  - forge-tier.yaml — {project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml
  {if preferences_yaml_created is true:}
  - preferences.yaml — {project-root}/_bmad/_memory/forger-sidecar/preferences.yaml (first-run defaults)
  {end if}
  {if forge_data_dir_created is true:}
  - {forge_data_folder}/ (directory created)
  {end if}
  {if settings_yml_written is true:}
  - .cocoindex_code/settings.yml — {project-root}/.cocoindex_code/settings.yml ({settings_yml_patterns_added} SKF exclusion pattern(s) merged)
  {end if}
  {if ccc_index_result is "created":}
  - .cocoindex_code/ ccc index — {ccc_file_count} files indexed
  {end if}

{if tier_override is active:}
  Note: Tier override active (set in preferences.yaml)

{if tier_override_invalid is true:}
  Note: tier_override value "{tier_override_invalid_value}" in preferences.yaml is not valid.
        Valid values are case-sensitive: Quick, Forge, Forge+, Deep. Using detected tier {calculated_tier}.

{if tier_override_unsafe is true:}
  Warning: tier_override is forcing {calculated_tier} but the underlying tool prerequisites are not satisfied.
           Missing: {tier_override_unsafe_missing}. The override is honored, but downstream skills that
           rely on the missing tool(s) will fail at runtime. Install the missing tool(s) or remove
           the override from preferences.yaml.

{if re-run with tier change:}
  {appropriate upgrade/downgrade message from tier-rules.md}

{if re-run with same tier and {tools_added} is empty and {tools_removed} is empty:}
  {same-tier message from tier-rules.md}

{if re-run with same tier and ({tools_added} or {tools_removed} is non-empty):}
  Tier unchanged: {calculated_tier}.
  {if {tools_added} non-empty:} Newly detected: {comma-separated tool names from tools_added}{if ccc was added and tier is Deep: " — ccc enhances Deep tier transparently."}
  {if {tools_removed} non-empty:} No longer detected: {comma-separated tool names from tools_removed} — re-install to restore those capabilities.

═══════════════════════════════════════
  Forge ready. {calculated_tier} tier active.
═══════════════════════════════════════

{if {headless_mode} is false:}
  Next: try [BS] Brief Skill to scope your first compilation target, or [QS] Quick Skill for a fast template-driven path. Already have a skill? [AS] Audit Skill drift-checks an existing skill against current sources.
```

**Tool delta computation rules:**
- Compute `{tools_added}` as the list of tool keys where `tools.{key}` is true now but was false (or absent) in `{previous_tools}`.
- Compute `{tools_removed}` as the list of tool keys where `tools.{key}` is true in `{previous_tools}` but false now.
- On a first run (`{previous_tools}` empty), `{tools_added}` equals the currently-detected tools and `{tools_removed}` is empty — but the same-tier branch does not fire on first runs (there is no previous tier to compare against), so this is not displayed in that case.

**Tool display rules:**
- Only show tools that ARE available with their version strings
- Do NOT list unavailable tools
- Do NOT show a "missing" column or section

### 3. Display Required-Tier Failure Block (when applicable)

If `{require_tier_satisfied}` is `false`, display this block immediately after the status report and BEFORE the JSON envelope:

```
═══════════════════════════════════════
  REQUIRED TIER NOT MET
═══════════════════════════════════════

  Required:  {require_tier}
  Detected:  {calculated_tier}
  Missing:   {require_tier_failure_missing_tools}

  Install the missing tool(s) and re-run, or relax `--require-tier`.
  See "Climb to next tier" above for install URLs.
═══════════════════════════════════════
```

This block exists to make pipeline failures visible without the operator parsing the JSON envelope.

### 4. Emit Headless JSON Envelope (when `{headless_mode}` is true)

When `{headless_mode}` is `true`, emit a single line at the end of step-04's output (after the human-readable banner and any required-tier failure block) using the literal prefix `SKF_SETUP_RESULT_JSON: ` followed by a one-line JSON document. This lets a CI pipeline grep one line out of the workflow log without parsing ASCII-art and without racing the forge-tier.yaml writer.

**Schema (one line, no embedded newlines):**

```json
{
  "skf_setup": {
    "tier": "Quick|Forge|Forge+|Deep",
    "previous_tier": "Quick|Forge|Forge+|Deep|null",
    "tier_changed": true|false,
    "tools": {"ast_grep": true|false, "gh_cli": true|false, "qmd": true|false, "ccc": true|false},
    "tools_added": ["ccc"],
    "tools_removed": [],
    "config_path": "{absolute path to forge-tier.yaml}",
    "ccc_index": {"status": "fresh|created|failed|none", "indexed_path": "{abs}|null", "file_count": <int>|null},
    "files_written": ["forge-tier.yaml", "preferences.yaml", "settings.yml", "ccc_index"],
    "tier_override_active": true|false,
    "tier_override_invalid": true|false,
    "require_tier_satisfied": true|false|null,
    "warnings": ["..."],
    "error": null
  }
}
```

**Field rules:**

- `previous_tier` — value of `{previous_tier}` from step-01 §2 (the tier read from existing forge-tier.yaml at workflow start). `null` on first runs.
- `tier_changed` — `true` when `previous_tier` is non-null AND differs from `tier`; `false` otherwise (covers both first runs and same-tier re-runs). Lets a pipeline react to upgrades without re-reading forge-tier.yaml.
- `tools_added` / `tools_removed` — same set deltas the human-facing same-tier re-run message displays (see §2 "Tool delta computation rules"). Empty arrays when nothing changed; on first runs `tools_added` equals the current detected tools and `tools_removed` is empty.
- `files_written` — include only the keys whose write actually occurred this run. Always includes `"forge-tier.yaml"` on success. Includes `"preferences.yaml"` only when `{preferences_yaml_created}` is true. Includes `"settings.yml"` only when `{settings_yml_written}` is true. Includes `"ccc_index"` only when `{ccc_index_result}` is `"created"`. Empty array when a write failure halted the run before any file was written.
- `require_tier_satisfied` — `null` when `--require-tier` was not set; otherwise the boolean from §3.
- `error` — `null` on success; otherwise an object `{"phase": "<step name>", "path": "<file>", "reason": "<message>"}` describing the failure. Set when forge-tier.yaml or preferences.yaml could not be written (step-02 §1 / §2 halt paths). Pipelines branch on `error !== null` for "exit code 2" semantics described in SKILL.md Invocation Contract.
- `warnings` — collect any non-fatal anomalies surfaced during the run. At minimum, fold in:
  - `"tier_override_invalid: <value>"` when `{tier_override_invalid}` is true.
  - `"tier_override_unsafe: missing <tools>"` when `{tier_override_unsafe}` is true.
  - Each entry of `{ccc_exclusion_warnings}` from step-01b §2b (config-value validation rejections — empty/absolute/glob-meta).
  - Each entry of `{ccc_registry_stale_removed_paths}` from step-03 §5b (paths the cleanup pruned, framed as `"ccc_registry_stale_removed: <path>"` so CI observers can detect ephemeral-mount churn).
  - `"qmd_daemon_stopped"` when `{qmd_status}` is `"daemon_stopped"` (binary present, daemon not running).
  - `"qmd_unavailable"`, `"ccc_indexing_failed"`, etc. as they occur.
  Empty array when none.

When `{headless_mode}` is `false`, do NOT emit the envelope — interactive runs read the human-readable banner.

### 5. Chain to Health Check

After the forge status report (and any failure block + JSON envelope) has been displayed, load `{nextStepFile}`, read it fully, and execute it — UNLESS `{require_tier_satisfied}` is `false`, in which case halt the workflow here without chaining to step-05. The health-check step is the true terminal step on success — do not stop after the report on a passing run even though it reads as final. step-05 in turn delegates to `shared/health-check.md`; after that returns, the setup workflow is fully done.

