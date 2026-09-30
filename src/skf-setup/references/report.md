---
nextStepFile: 'health-check.md'
# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`;
# halt if neither exists when section 4 emits the envelope. The script is the
# source of truth for the SKF_SETUP_RESULT_JSON contract: do not render the
# envelope from prose (LLM schema drift is the bug this script exists to
# prevent).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}; emit user-visible report text (FORGE STATUS banner, climb hint, REQUIRED TIER NOT MET block, breadcrumb) in {document_output_language}. The JSON envelope from section 4 is a machine contract — its keys and enum values stay English regardless. -->

# Step 4: Forge Status Report

## STEP GOAL:

Stage the run's report payload, display the FORGE STATUS banner that `{emitEnvelopeHelper}` renders from it (tier, tools, tier changes and tool-set deltas on re-runs), prominently flag a required-tier miss, and (when headless or quiet) emit the schema-locked `SKF_SETUP_RESULT_JSON` envelope from the same payload.

## Rules

- Focus only on display + envelope emission
- The FORGE STATUS lines come from `render-report`: display them (translated when needed), and never compose, add or drop a line yourself
- Never inline-render the envelope JSON — the script owns the schema; drift breaks pipelines
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing status report is not the terminal step
- Display messages only when `{quiet_mode}` is false; the one exception is the envelope line section 4 builds, which section 5 displays on a tier miss and the shared health check displays last otherwise
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief
- If section 4 finds no existing path in `emitEnvelopeProbeOrder`, halt with phase `step 4:helper-missing`, `path` set to its first entry, and reason `Setup cannot proceed: skf-emit-result-envelope.py was not found. Reinstall SKF, then re-run /skf-setup.` With no envelope helper to call, display that reason alone as the run's one line (the SKILL.md halt contract)

## MANDATORY SEQUENCE

### 1. Stage the Report Payload

Sections 2 and 4 read one payload file, staged here on every run through a quoted heredoc:

```bash
cat > "{run_dir}/report-context.json" <<'SKF_JSON'
{
  "project_root": "{project-root}",
  "config_path": "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml",
  "forge_data_folder": "{forge_data_folder}",
  "ccc_index": {
    "status": "{ccc_index_result}",
    "indexed_path": {ccc_indexed_path_or_null},
    "file_count": {ccc_file_count_or_null}
  },
  "preferences_yaml_created": {preferences_yaml_created},
  "settings_yml_written": {settings_yml_written},
  "settings_yml_patterns_added": {settings_yml_patterns_added},
  "settings_yml_patterns_removed": {settings_yml_patterns_removed},
  "gitignore_updated": {gitignore_updated},
  "ccc_exclusion_warnings": {ccc_exclusion_warnings_list},
  "ccc_indexing_failed_reason": {ccc_indexing_failed_reason_or_null},
  "hygiene_orphaned_removed": {hygiene_orphaned_removed},
  "hygiene_orphaned_kept": {hygiene_orphaned_kept},
  "orphan_auto_resolution": {orphan_auto_resolution_or_null},
  "error": null
}
SKF_JSON
```

Write each value as JSON: a string in double quotes with any `"`, `\` or control character in it escaped (a newline as `\n`), every path with `/`, `null` for a value no step bound, and the lists and `{orphan_auto_resolution}` as JSON arrays and objects. Resolve `{project-root}` and `{forge_data_folder}` to absolute paths everywhere but inside the exclusion notes, which keep what step 1b bound. `error` stays `null`: a halt that names a phase never reaches this step, because it displays its own blocked envelope.

### 2. Display Forge Status Report (skip when `{quiet_mode}` is true)

Render the banner from the payload and the run folder:

```bash
uv run {emitEnvelopeHelper} render-report --run-dir "{run_dir}" --tier-rules "{skill-root}/references/tier-rules.md" < "{run_dir}/report-context.json"
```

Display its stdout as one code block, so its alignment holds, keeping every line in its order. When `{document_output_language}` is not English, translate the prose and keep paths, commands, flags, tool names and tier names as they are. If the script exits non-zero and the `message` of its stderr JSON names invalid JSON on stdin, fix `report-context.json` once and run it again. If it still exits non-zero, or no path in `emitEnvelopeProbeOrder` exists, display one line instead, `FORGE STATUS could not be rendered: <message>`, where `<message>` is that `message`, or `skf-emit-result-envelope.py was not found`, and continue: the forge is configured either way.

`render-report` follows this template, kept for reference only; its conditions and placeholders name payload and envelope fields:

```
═══════════════════════════════════════
  FORGE STATUS
═══════════════════════════════════════

  Tier:  {calculated_tier}
  {tier capability description from tier-rules.md}

  Tools Detected:
  {for each tool that is available: - <tool> <version>, where <version> is the probe's version line without the tool's name or a leading "version"; ccc has no version, so - ccc (daemon {ccc_daemon})}
  {if no tools are available: (none yet, see "Climb to next tier" below)}

  {if calculated_tier is not Deep:}
  Climb to next tier:
  {if not tools.ast_grep: - Install ast-grep (https://ast-grep.github.io): unlocks AST-backed code analysis (Forge tier)}
  {if tools.ast_grep and not tools.ccc: - Install cocoindex-code (https://github.com/cocoindex-io/cocoindex-code): adds semantic-guided precision compilation (Forge+ tier)}
  {if tools.ast_grep and not tools.gh_cli: - Install GitHub CLI (https://cli.github.com): required for Deep tier (cross-repository synthesis)}
  {if tools.ast_grep and not tools.qmd and qmd_status is "absent": - Install qmd (https://github.com/tobi/qmd): required for Deep tier (knowledge search)}
  {if tools.ast_grep and not tools.qmd and qmd_status is "daemon_stopped": - Start the qmd daemon (already installed): run `qmd start` (or your distribution's qmd service command) to unlock Deep tier (knowledge search)}
  {if tools.ccc and ccc_daemon is "error": - The ccc daemon is reporting errors: run `ccc doctor` to diagnose. CCC index will fail until resolved}
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
  QMD Registry: empty. Collections are created automatically when you run /skf-create-skill.
  {end if}

  {if hygiene_result is "qmd_unavailable":}
  QMD Registry: skipped (qmd unavailable; if the daemon is stopped, `qmd start` restores it).
  {end if}

  {if tools.ccc is true:}
  CCC Index:
  {if ccc_index_result is "fresh": up to date, semantic discovery ready}
  {if ccc_index_result is "created": indexed this run, semantic discovery ready}
  {if ccc_index_result is "skipped": skipped (--ccc-skip-index). Run `/skf-setup` without --ccc-skip-index to build or refresh the index when you're ready}
  {if ccc_index_result is "failed": indexing failed, semantic discovery unavailable this session ({ccc_indexing_failed_reason})}
  {if ccc_exclusion_warnings is non-empty:}
  CCC exclusion notes:
  {for each entry in ccc_exclusion_warnings: - {entry}}
  {end if}
  {end if}

  Files written this run:
  - forge-tier.yaml: {project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml
  {if preferences_yaml_created is true:}
  - preferences.yaml: {project-root}/_bmad/_memory/forger-sidecar/preferences.yaml (first-run defaults)
  {end if}
  - {forge_data_folder}/ (directory ensured)
  {if settings_yml_written is true:}
  - .cocoindex_code/settings.yml: {project-root}/.cocoindex_code/settings.yml ({settings_yml_patterns_added} SKF exclusion pattern(s) merged{if settings_yml_patterns_removed > 0:}, {settings_yml_patterns_removed} stale SKF pattern(s) removed{end if})
  {end if}
  {if gitignore_updated is true:}
  - .gitignore: {project-root}/.gitignore (`/.cocoindex_code/` added by `ccc init`)
  {end if}
  {if ccc_index_result is "created":}
  - .cocoindex_code/ ccc index: {ccc_file_count} files indexed
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

{if {previous_tier} is null:}
  Initial detection: {calculated_tier} tier established.

{if {tier_changed} is true:}
  {appropriate upgrade/downgrade message from tier-rules.md}

{if {tier_changed} is false and {tools_added} is empty and {tools_removed} is empty and {previous_tier} is non-null:}
  {same-tier message from tier-rules.md}
  {if preferences_yaml_created is false and settings_yml_written is false and ccc_index_result is "fresh": Your preferences and ccc settings were left untouched, and the ccc index was already current.}
  {if preferences_yaml_created is false and settings_yml_written is false and ccc_index_result is "skipped": Your preferences and ccc settings were left untouched; the ccc index was not checked (--ccc-skip-index).}
  {if preferences_yaml_created is false and ccc_index_result is "none": Your preferences were left untouched.}

{if {tier_changed} is false and ({tools_added} or {tools_removed} is non-empty) and {previous_tier} is non-null:}
  Tier unchanged: {calculated_tier}.
  {if {tools_added} non-empty:} Newly detected: {comma-separated tool names from tools_added}.{if ccc was added and tier is Deep: " ccc enhances Deep tier transparently."}
  {if {tools_removed} non-empty:} No longer detected: {comma-separated tool names from tools_removed}. Re-install to restore those capabilities.

═══════════════════════════════════════
  Forge ready. {calculated_tier} tier active.
═══════════════════════════════════════

  Next: the fastest start is `@Ferris forge-auto <repo-or-doc-url>`: one command auto-scopes, briefs, compiles, tests at a 90% quality gate, and exports a verified skill with zero configuration. Prefer to scope by hand? `/skf-brief-skill` scopes your first compilation target, or `/skf-quick-skill` is a fast template-driven path. Already have a skill? `/skf-audit-skill` drift-checks an existing skill against current sources.
```

The script renders the exclusion notes by this rule, so show them as it prints them. Each `{ccc_exclusion_warnings}` entry that names the project root in SKF's own words carries the literal `{project-root}`: render it the way the banner's own `{project-root}` paths are rendered, and show text quoted from ccc or git as it is. An entry about an unresolved template placeholder names `{project-root}` as the placeholder the helper resolves, not a folder: show that entry as it is too. Section 4 forwards the entries verbatim, so the envelope keeps the placeholder.

### 3. Display Required-Tier Failure Block (when applicable; skip when `{quiet_mode}` is true)

If `{require_tier_satisfied}` is `false`, display this block immediately after the status report (the heading gate already handles the headless/quiet skip).

When the block does fire (interactive run with require-tier failure):

```
═══════════════════════════════════════
  REQUIRED TIER NOT MET
═══════════════════════════════════════

  Required:  {require_tier}
  Detected:  {calculated_tier}
  Missing:   {require_tier_failure_missing_tools}

  Install the missing tool(s) and re-run, or relax `--require-tier`.
═══════════════════════════════════════
```

### 4. Emit Headless JSON Envelope

When `{quiet_mode}` is `true`, run `{emitEnvelopeHelper}` on the payload section 1 staged; `--run-dir` makes it read the staged helper outputs too. The script computes derived fields (`status`, `tools_added`, `tools_removed`, `tier_changed`, `files_written`, `warnings`), validates the assembled envelope against the JSON Schema at `src/shared/scripts/schemas/skf-setup-result-envelope.v1.json`, and emits the single prefixed line `SKF_SETUP_RESULT_JSON: {…}` on stdout. Bind `{setup_envelope_line}` ← that stdout line, and do not display it here. It is the only line a headless or quiet run displays, and in a standalone run it must be the run's final message: `claude -p` prints only the final message, and the health check still runs after this step. Section 5 displays it on a tier miss; otherwise the shared health check displays it when it stops (its §0). Either way it is displayed verbatim as its own line (no code fence, no preface, no commentary), with nothing of setup's after it. When `{pipeline_mode}` is true, control then returns to the forger, which keeps chaining.

```bash
uv run {emitEnvelopeHelper} emit --run-dir "{run_dir}" < "{run_dir}/report-context.json"
```

`{ccc_exclusion_warnings_list}` is `{ccc_exclusion_warnings}` as a JSON list of strings, each entry exactly as step 1b bound it: do not resolve the `{project-root}` inside an entry, even though `config_path` resolves its own.

**If the script exits non-zero:** when its error `message` names invalid JSON on stdin, fix `report-context.json` once and run it again. If it still exits non-zero, a value in the payload or in a staged helper output is malformed: set `{setup_envelope_line}` to the empty string. Display nothing and continue (a missing JSON envelope on a headless or quiet run is a degraded but non-fatal state: the pipeline observer sees no envelope and treats the run as not completed cleanly).

### 5. Chain to Health Check

After the forge status report and any failure block have been displayed (under headless or quiet, once `{setup_envelope_line}` is bound), delete the run folder:

```bash
rm -f "{run_dir}/detect-tools.json" "{run_dir}/qmd-classify.json" "{run_dir}/clean-stale.json" "{run_dir}/report-context.json" && rmdir "{run_dir}"
```

Then:

- If `{require_tier_satisfied}` is `false`, halt the workflow here without chaining to step 5. When `{quiet_mode}` is true, display `{setup_envelope_line}` verbatim as the run's final message in a standalone run (nothing when it is empty); when `{pipeline_mode}` is true, control then returns to the forger, which reads the envelope's `tier_failure` status. This halt emits no blocked envelope: the `tier_failure` envelope is its one line. The tier miss is terminal; `{onCompleteCommand}` does not fire on a failed run.
- Otherwise the forge is fully configured. If `{onCompleteCommand}` (resolved from `workflow.on_complete` at activation) is non-empty, execute it now: this is the workflow's terminal skill-specific action (e.g. trigger the first index build or notify an onboarding channel); when `{quiet_mode}` is true, display nothing about it. Then load `{nextStepFile}`, read it fully, and execute it; under headless or quiet, the shared health check it chains to ends setup's output with `{setup_envelope_line}`.

The health-check step is the true terminal step on success — do not stop after the report on a passing run even though it reads as final. Step 5 in turn delegates to `shared/health-check.md`; after that returns, the setup workflow is fully done.
