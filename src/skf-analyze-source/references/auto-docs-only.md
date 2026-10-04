---
nextStepFile: 'health-check.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a §0a: Docs-Only Short-Circuit

Reached from `step-auto-scope.md` §0c when the target is a documentation URL (not a repository URL or local path). It validates the URL, writes a minimal brief and analysis report, emits the result envelope, and chains directly to health-check: the standard auto-scope body (§1 through §9 in `step-auto-scope.md`) never runs for a docs-only target. `{coexistence_suffix}`, `{forge_tier}`, `{user_name}`, `{current_date}`, and the classification set upstream in §0/§0c carry into this file.

## MANDATORY SEQUENCE — §0a

Every HARD HALT in this file names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "auto", "source_type": "docs-only"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Validate URL reachability

When §0's `derive-name` call gave `git_probe` `no-git` (git is missing, so nothing asked whether `{url}` is a repository), run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning 'git_probe_unanswered: {url} was not checked for a repository: git is missing'`, a single quote in it written as a backtick (if it fails, go on). Then check that the URL answers:

```bash
curl -sI --max-time 5 {url}
```

- On **2xx/3xx** response: URL is reachable. Continue.
- On **4xx/5xx**, DNS failure, or timeout: HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `auto-docs-only:1`, path `{url}`): "Documentation URL unreachable: {url}: {status or error}".

### 2. Derive skill name from URL domain

**Resolve `{skillInventoryHelper}`** from `{skillInventoryProbeOrder}`; first existing path wins. If neither resolves, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `auto-docs-only:2`): "`skf-skill-inventory.py` is missing. Re-install SKF."

Name the skill with the helper that names every brief. It names a documentation URL after its host (`https://docs.example.com/guide/intro` gives `docs-example-com`), the name §0c's coexistence check compared:

```bash
uv run {skillInventoryHelper} derive-name --target "{url}"
```

`{skill_name}` ← `.name`. If `{coexistence_suffix}` is non-empty, append it to the skill name (e.g., `docs-example-com-wiki`).

### 3. Write analysis report

Update {outputFile} with docs-only results. If the write fails, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `auto-docs-only:3`, path `{outputFile}`): "The analysis report could not be written: {the error}."

**Update frontmatter:**
```yaml
stepsCompleted: ['init', 'auto-scope']
lastStep: 'auto-scope'
source_type: docs-only
confirmed_units:
  - name: '{skill_name}'
    shape: 'docs-only'
    confidence: 1.0
    export_count: 0
    package_count: 0
```

**Append body section:**
```markdown
## Auto-Scope Analysis

**Mode:** auto (docs-only short-circuit)
**Source Type:** docs-only
**Documentation URL:** {url}
**Skill Name:** {skill_name}
```

### 4. Write skill brief via canonical writer

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins. If neither resolves, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `auto-docs-only:4`): "`skf-write-skill-brief.py` is missing. Re-install SKF."

Write the flat context below as `{run_dir}/brief-{skill_name}.json`, a file and never an echo'd string:

```json
{
  "name":             "{skill_name}",
  "target_version":   null,
  "detected_version": null,
  "source_type":      "docs-only",
  "source_repo":      "{url}",
  "language":         "documentation",
  "description":      "Skill created from documentation at {url}",
  "forge_tier":       "{forge_tier}",
  "created":          "{current_date}",
  "created_by":       "{user_name}",
  "scope_type":       "docs-only",
  "scope_include":    [],
  "scope_exclude":    [],
  "scope_notes":      "Docs-only skill created from documentation URL",
  "scope_rationale":  null,
  "scope_tier_a_include": null,
  "scope_amendments":     null,
  "doc_urls":         [{"url": "{url}", "label": "Primary Documentation"}],
  "scripts_intent":   null,
  "assets_intent":    null,
  "source_authority": "community",
  "target_ref":       null,
  "source_ref":       null,
  "version_resolved": "1.0.0"
}
```

Then hand it to the writer, which checks it, creates the folder and writes the brief atomically:

```bash
uv run {writeSkillBriefHelper} write --target "{forge_data_folder}/{skill_name}/skill-brief.yaml" --from-flat < "{run_dir}/brief-{skill_name}.json"
```

Keep the `brief_path` it prints for §5. If it exits non-zero, the brief is rejected or unwritten: HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `auto-docs-only:4`, path `{forge_data_folder}/{skill_name}/skill-brief.yaml`): "The brief for {skill_name} was rejected or could not be written: {its `message`}."

### 5. End the run

The shared emitter writes the result files and prints the envelope; this section stages their content, in every mode. Write `{run_dir}/result-context.json`:

```json
{
  "status": "success",
  "report_path": "{outputFile as an absolute path}",
  "brief_paths": ["{the brief_path §4 printed}"],
  "unit_counts": {"confirmed": 1, "skipped": 0, "maybe": 0},
  "mode": "auto",
  "source_type": "docs-only",
  "result_contract": {
    "skill": "skf-analyze-source",
    "status": "success",
    "outputs": [{"type": "report", "path": "{outputFile as an absolute path}"}, {"type": "brief", "path": "{the brief_path §4 printed}"}],
    "summary": {"mode": "auto", "source_type": "docs-only", "brief_count": 1, "units": ["{skill_name}"]}
  }
}
```

Add `"coexistence": "alongside"` when `{coexistence_suffix}` is non-empty ([A]longside was selected in §0c). The `source_type` field signals downstream consumers (BS) to skip repo-based enrichment. Then run:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-analyze-source --run-dir "{run_dir}" --result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"
```

The emitter stamps the UTC time and the run id into the record, writes `{forge_data_folder}/analyze-source-result-{YYYYMMDD-HHmmss}.json` and its `analyze-source-result-latest.json` copy, and prints the `SKF_ANALYZE_RESULT_JSON:` line on stdout. When `{headless_mode}` is true, display the line verbatim. A result file that could not be written leaves the line's `result_path` null and a `result_file_write_failed` warning in it, and the run still finishes. If the emitter exits non-zero, correct `result-context.json` from the message on its stderr and run it once more; if it fails again, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `auto-docs-only:5`, path `{forge_data_folder}`): "The result contract could not be written: {its message}."

If `{onCompleteCommand}` is non-empty and the line's `result_path` is not null, invoke it now: `{onCompleteCommand} --result-path={forge_data_folder}/analyze-source-result-latest.json`. Display a hook failure; it never fails the run.

### 6. Chain to health check

Delete the run folder, whose payloads the emitter has read: `rm -rf "{run_dir}"`. Then load, read fully, and execute {nextStepFile} to run the shared workflow health check.
