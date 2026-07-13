---
nextStepFile: 'health-check.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a §0a: Docs-Only Short-Circuit

Reached from `step-auto-scope.md` §0c when the target is a documentation URL (not a GitHub repo or local path). It validates the URL, writes a minimal brief and analysis report, emits the result envelope, and chains directly to health-check — the standard auto-scope body (§1 through §11 in `step-auto-scope.md`) never runs for a docs-only target. `{coexistence_suffix}`, `{forge_tier}`, `{user_name}`, `{current_date}`, and the classification set upstream in §0/§0c carry into this file.

## MANDATORY SEQUENCE — §0a

### 1. Validate URL reachability

```bash
curl -sI --max-time 5 {url}
```

- On **2xx/3xx** response: URL is reachable. Continue.
- On **4xx/5xx**, DNS failure, or timeout: HARD HALT with exit code 3 (`resolution-failure`). Emit error message: `"Documentation URL unreachable: {url} — {status or error}"`, then the error envelope (shape in `references/headless-contract.md`) with `exit_code: 3`, `halt_reason: "resolution-failure"`, `mode: "auto"`, `source_type: "docs-only"`.

### 2. Derive skill name from URL domain

Extract the hostname from the URL (e.g., `docs.example.com` from `https://docs.example.com/guide/intro`), convert to kebab-case (replace `.` with `-`), yielding e.g. `docs-example-com`. If `{coexistence_suffix}` is non-empty, append it to the skill name (e.g., `docs-example-com-wiki`).

### 3. Write analysis report

Update {outputFile} with docs-only results. If the write fails, HARD HALT with exit code 4 (`write-failed`) per `references/headless-contract.md` (applies equally to the brief write in §4 and the result contract in §6).

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

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins; HALT if neither resolves.

Create directory `{forge_data_folder}/{skill_name}/` if it does not exist.

Pipe the flat context JSON below into the resolved writer with the `--from-flat` flag:

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

```bash
echo '<context-json>' | uv run {writeSkillBriefHelper} write --target {forge_data_folder}/{skill_name}/skill-brief.yaml --from-flat
```

### 5. Emit success envelope

```
SKF_ANALYZE_RESULT_JSON: {"status":"success","report_path":"{outputFile_path}","brief_paths":["{brief_path}"],"unit_counts":{"confirmed":1,"skipped":0,"maybe":0},"exit_code":0,"halt_reason":null,"mode":"auto","source_type":"docs-only"}
```

If `{coexistence_suffix}` is non-empty (i.e., [A]longside was selected in §0c), include `"coexistence":"alongside"` in the envelope.

The `source_type` field signals downstream consumers (BS) to skip repo-based enrichment.

### 6. Write result contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record and latest copy, same as `step-auto-scope.md` §10.

If `{onCompleteCommand}` is non-empty, invoke it now with `--result-path={result_json_path}`.

### 7. Chain to health check

Load, read fully, then execute {nextStepFile} to run the shared workflow health check.
