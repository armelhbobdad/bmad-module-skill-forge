---
tierRulesData: 'references/tier-rules.md'
nextStepFile: 'health-check.md'
# Resolve `{emitEnvelopeHelper}` by probing `{emitEnvelopeProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves when the headless envelope must be emitted
# — the script is the source of truth for the SKF_SETUP_RESULT_JSON contract;
# never inline-render the envelope from prose (LLM schema drift is the bug
# this script exists to prevent).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}; emit user-visible report text (FORGE STATUS banner, climb hint, REQUIRED TIER NOT MET block, breadcrumb) in {document_output_language}. The JSON envelope from section 4 is a machine contract — its keys and enum values stay English regardless. -->

# Step 4: Forge Status Report

## STEP GOAL:

Display the forge status report with positive capability framing, surface tier changes and tool-set deltas on re-runs, prominently flag a required-tier miss, and (when headless) emit the schema-locked `SKF_SETUP_RESULT_JSON` envelope via `{emitEnvelopeHelper}`.

## Rules

- Focus only on display + envelope emission
- Do not use negative framing ("missing", "lacking", "unavailable")
- Do not list tools that are not available
- Use tier capability descriptions from tier-rules.md
- Never inline-render the envelope JSON — the script owns the schema; drift breaks pipelines
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing status report is NOT the terminal step

## Headless Mode Display Rule

When `{headless_mode}` is `true` OR `{quiet_mode}` is `true`, sections 2 (the human-readable banner) and 3 (the REQUIRED TIER NOT MET human prose block) are **skipped entirely**. The single line of stdout in those modes is the `SKF_SETUP_RESULT_JSON: {…}` envelope from section 4 — every signal the human banner would have surfaced is already in the envelope (`tier`, `previous_tier`, `tier_changed`, `tools`, `tools_added`, `tools_removed`, `files_written`, `tier_override_*`, `require_tier_satisfied`, `warnings`, `error`). Parent skills, CI pipelines, and expert re-runners consume the envelope alone; they should not be forced to scroll past 30 lines of ASCII-art they cannot use.

When both `{headless_mode}` and `{quiet_mode}` are `false`, sections 2 and 3 display normally and section 4 is skipped (interactive runs read the human banner; envelope emission would just be log noise).

## MANDATORY SEQUENCE

### 1. Load Capability Descriptions

Load and read {tierRulesData} for the tier capability descriptions and re-run messages. Needed by section 2; safe to load unconditionally — the data load itself is silent.

### 2. Display Forge Status Report (skip when `{headless_mode}` or `{quiet_mode}` is true)

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
  {if tools.ccc and ccc_daemon is "error": - The ccc daemon is reporting errors — run `ccc doctor` to diagnose. CCC index will fail until resolved (mirrors the qmd daemon-stopped pattern above for parity)}
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
  QMD Registry: empty — collections are created automatically when you run /skf-create-skill.
  {end if}

  {if hygiene_result is "qmd_unavailable":}
  QMD Registry: skipped (daemon error — retry after `qmd start`).
  {end if}

  {if tools.ccc is true:}
  CCC Index:
  {if ccc_index_result is "fresh": up to date — semantic discovery ready}
  {if ccc_index_result is "created": indexed this run — semantic discovery ready}
  {if ccc_index_result is "skipped": skipped (--ccc-skip-index) — run `/skf-setup` without --ccc-skip-index to build the index when you're ready}
  {if ccc_index_result is "failed": indexing failed — semantic discovery unavailable this session}
  {end if}

  Files written this run:
  - forge-tier.yaml — {project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml
  {if preferences_yaml_created is true:}
  - preferences.yaml — {project-root}/_bmad/_memory/forger-sidecar/preferences.yaml (first-run defaults)
  {end if}
  - {forge_data_folder}/ (directory ensured)
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
        {if tier_override_invalid_suggestion is non-null: Did you mean "{tier_override_invalid_suggestion}"?}
        Valid values are case-sensitive: Quick, Forge, Forge+, Deep. Using detected tier {calculated_tier}.

{if tier_override_unsafe is true:}
  Warning: tier_override is forcing {calculated_tier} but the underlying tool prerequisites are not satisfied.
           Missing: {tier_override_unsafe_missing}. The override is honored, but downstream skills that
           rely on the missing tool(s) will fail at runtime. Install the missing tool(s) or remove
           the override from preferences.yaml.

{if {tier_changed} is true:}
  {appropriate upgrade/downgrade message from tier-rules.md}

{if {tier_changed} is false and {tools_added} is empty and {tools_removed} is empty and {previous_tier} is non-null:}
  {same-tier message from tier-rules.md}
  {if preferences_yaml_created is false and (ccc_index_result is "fresh" or ccc_index_result is "none" or ccc_index_result is "skipped"): Nothing changed — your preferences were left untouched and the index was already current. You're good.}

{if {tier_changed} is false and ({tools_added} or {tools_removed} is non-empty):}
  Tier unchanged: {calculated_tier}.
  {if {tools_added} non-empty:} Newly detected: {comma-separated tool names from tools_added}{if ccc was added and tier is Deep: " — ccc enhances Deep tier transparently."}
  {if {tools_removed} non-empty:} No longer detected: {comma-separated tool names from tools_removed} — re-install to restore those capabilities.

═══════════════════════════════════════
  Forge ready. {calculated_tier} tier active.
═══════════════════════════════════════

{if {headless_mode} is false:}
  Next: the fastest start is `@Ferris forge-auto <repo-or-doc-url>` — one command auto-scopes, briefs, compiles, tests at a 90% quality gate, and exports a verified skill with zero configuration. Prefer to scope by hand? `/skf-brief-skill` scopes your first compilation target, or `/skf-quick-skill` is a fast template-driven path. Already have a skill? `/skf-audit-skill` drift-checks an existing skill against current sources.
```

All re-run-delta context flags (`{tools_added}`, `{tools_removed}`, `{tier_changed}`) come from the detector's `deltas` block bound in stage 1 — no LLM-side recomputation, no set arithmetic in prose.

**Tool display rules:**

- Only show tools that ARE available with their version strings
- Do NOT list unavailable tools
- Do NOT show a "missing" column or section

### 3. Display Required-Tier Failure Block (when applicable; skip when `{headless_mode}` or `{quiet_mode}` is true)

If `{require_tier_satisfied}` is `false` AND both `{headless_mode}` and `{quiet_mode}` are `false`, display this block immediately after the status report. In headless or quiet modes the failure surfaces via the envelope's `require_tier_satisfied: false` and the synthesized `warnings` entry — the human prose block would be log noise.

When the block does fire (interactive run with require-tier failure):

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

### 4. Emit Headless JSON Envelope

When `{headless_mode}` is `true` OR `{quiet_mode}` is `true`, build the context payload from this step's accumulated flags and forward it to `{emitEnvelopeHelper}` on stdin. Invoke via `uv run` so the script's PEP 723 dependency declarations are honored (the canonical runtime invocation per `docs/getting-started.md`'s uv prereq — bare `python3` skips the metadata block and breaks on a fresh interpreter). The script computes derived fields (`tools_added`, `tools_removed`, `tier_changed`, `warnings`), validates the assembled envelope against the JSON Schema at `src/shared/scripts/schemas/skf-setup-result-envelope.v1.json`, and emits the single prefixed line `SKF_SETUP_RESULT_JSON: {…}` on stdout.

```bash
echo '{
  "tier": "{calculated_tier}",
  "previous_tier": {previous_tier_or_null},
  "tools": {tools_dict_from_step_01_or_skf_detect_tools_output},
  "previous_tools": {previous_tools_or_null},
  "config_path": "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml",
  "ccc_index": {
    "status": "{ccc_index_result}",
    "indexed_path": {ccc_indexed_path_or_null},
    "file_count": {ccc_file_count_or_null}
  },
  "files_written": {
    "forge-tier.yaml": true,
    "preferences.yaml": {preferences_yaml_created},
    "settings.yml": {settings_yml_written},
    "ccc_index": {ccc_index_result_was_created}
  },
  "tier_override_active": {tier_override_active},
  "tier_override_invalid": {tier_override_invalid},
  "tier_override_invalid_value": {tier_override_invalid_value_or_null},
  "tier_override_unsafe": {tier_override_unsafe},
  "tier_override_unsafe_missing": {tier_override_unsafe_missing_list},
  "require_tier_satisfied": {require_tier_satisfied_or_null},
  "require_tier_failure_missing": {require_tier_failure_missing_tools_list},
  "qmd_status": "{qmd_status}",
  "ccc_exclusion_warnings": {ccc_exclusion_warnings_list},
  "ccc_registry_stale_removed": {ccc_registry_stale_removed_paths_list},
  "ccc_indexing_failed_reason": {ccc_indexing_failed_reason_or_null},
  "orphan_auto_resolution": {orphan_auto_resolution_or_null},
  "error": {error_object_or_null}
}' | uv run {emitEnvelopeHelper} emit
```

The script's documented context-payload shape (see `src/shared/scripts/skf-emit-result-envelope.py` docstring) tolerates two `tools` shapes — bare booleans OR `skf-detect-tools.py`'s `{key: {available: bool, ...}}` output — so either step 1's normalized booleans OR the raw detect-tools output forwarded as-is will produce the correct envelope.

**If the script exits non-zero:** the assembled envelope failed schema validation, which means a context flag from an earlier step is malformed. Surface the error to stderr and continue (the human-readable banner is already displayed; missing JSON envelope on a headless run is a degraded but non-fatal state — the pipeline observer will see no envelope and treat that as "agent did not complete cleanly").

**When both `{headless_mode}` and `{quiet_mode}` are `false`, do NOT invoke the script** — interactive runs read the human-readable banner.

### 5. Chain to Health Check

After the forge status report (and any failure block + JSON envelope) has been displayed, load `{nextStepFile}`, read it fully, and execute it — UNLESS `{require_tier_satisfied}` is `false`, in which case halt the workflow here without chaining to step 5. The health-check step is the true terminal step on success — do not stop after the report on a passing run even though it reads as final. step 5 in turn delegates to `shared/health-check.md`; after that returns, the setup workflow is fully done.
