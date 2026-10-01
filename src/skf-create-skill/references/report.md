---
nextStepFile: 'health-check.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. §5 rewrites metadata.json through it only when the emitter is
# missing; if neither resolves, that write is skipped.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Report

## STEP GOAL:

To display the final compilation summary (skill name, version, source, export count, confidence distribution, tier used, file list and any warnings), suggest next steps, then end the brief: its result contract and `on_complete` call, every brief of a `--batch` run included, and the health check once the run's last brief is done.

## Rules

- Write only the brief's result files (through the emitter, §5) and, outside `--batch`, the removal of the brief's run folder. Change no skill artifact, except in §5's fallback when `{emitEnvelopeHelper}` resolved no path: `validation_status` in `{skill_package}/metadata.json` and one warning appended to `{forge_version}/evidence-report.md`
- Deliver structured report with confidence breakdown
- The user-facing report is not the end of the run: §5 and §6 follow it in order, and §6 chains to the health check via `{nextStepFile}`, or under `--batch` back to `references/batch-mode.md`, which runs it once the last brief is recorded

## MANDATORY SEQUENCE

### 1. Display Forge Completion Banner

"**Skill forged: {name} v{version} — {export_count} functions, {primary_confidence} confidence.**"

Where `{primary_confidence}` is the `confidence` label most provenance-map entries carry, counted from the entries' own labels. Never infer it from the forge tier: a Forge or Deep run whose exports were read by eye is T1-low. On a tie, report the weaker label (T1-low over T1), so the headline never overstates confidence.

### 2. Display Compilation Summary

"**Compilation Summary**

| Field | Value |
|-------|-------|
| **Skill** | {name} v{version} |
| **Source** | {source_repo} @ {branch} ({commit_short}) |
| **Language** | {language} |
| **Forge Tier** | {tier} — {tier_description} |
| **Files Scanned** | {file_count} |
| **Exports Documented** | {documented_count} public API ({public_api_coverage}%) / {total_count} total ({total_coverage}%) |

**Confidence Distribution:**
| Tier | Count | Description |
|------|-------|-------------|
| T1 (AST) | {t1_count} | Structurally verified via ast-grep |
| T1-low (Source) | {t1_low_count} | Inferred from source reading |
| T2 (QMD) | {t2_count} | QMD-enriched semantic context |
| T3 (External) | {t3_count} | Sourced from external documentation URLs |

**Output Files:**
- `{skill_package}/SKILL.md` — Active skill with trigger-based usage
- `{skill_package}/context-snippet.md` — Passive context snippet (used by export-skill)
- `{skill_package}/metadata.json` — Machine-readable birth certificate
- `{skill_package}/references/` — Progressive disclosure ({ref_count} files)
- `{forge_version}/provenance-map.json` — Source map with AST bindings
- `{forge_version}/evidence-report.md` — Build audit trail
- `{forge_version}/extraction-rules.yaml` — Reproducible extraction schema
- `{skill_group}/active` -> `{version}` — Symlink to current version"

### 3. Display Warnings (If Any)

If there were warnings from extraction, validation, or enrichment, display them:

"**Warnings:**
- {warning_1}
- {warning_2}
- ..."

If no warnings, omit this section entirely.

### 4. Suggest Next Steps

"**Recommended next steps:**
- **[TS] Test Skill** — verify completeness and accuracy before export
- **[EX] Export Skill** — publish to your skill library or agentskills.io
- **[US] Update Skill** — edit specific sections or add manual content

To use this skill immediately, add the context snippet to your CLAUDE.md:
```
{context_snippet_content}
```"

### 5. Result Contract and Post-Completion Hook

Every brief that reaches this step gets its own result contract and `on_complete` call, each brief of a `--batch` run included. A HARD HALT in steps 1 to 7 never reaches this step: it emits its envelope where it fires, by the SKILL.md Workflow Rules, and writes its result file there once step 7 has created `{forge_version}`.

**Write the result contract through the emitter.** `{emitEnvelopeHelper}` (SKILL.md On Activation) writes `{forge_version}/create-skill-result-{YYYYMMDD-HHmmss}.json` and its `create-skill-result-latest.json` copy (a stable path for pipeline consumers; a copy, not a symlink), stamps the timestamp, the run id and the run sink's decisions and warnings into them, checks the brief's `SKF_CREATE_SKILL_RESULT_JSON` line against `skf-create-skill-result-envelope.v1.json` and prints it. First read the run sink, from `{project-root}`:

```bash
grep -c . "{run_dir}/headless-decisions.jsonl" 2>/dev/null; grep -c '"gate":"zero-exports"' "{run_dir}/headless-decisions.jsonl" 2>/dev/null
```

Bind `{auto_decision_count}` ← the first count (0 when the file is missing), the rows of the evidence report's `## Auto-Decisions` table, so a consumer can tell from the result alone whether any gate auto-resolved. Bind `{run_status}` ← `partial` when the second count is above 0 (a headless run went on past zero exports at step 3), else `success`. Take `exports_documented` (`stats.exports_documented`) and `confidence_distribution` from the promoted `metadata.json`. Stage the payload with these values and `{auto_decision_count}` in place of the template's zeros, in both `summary` objects, adding `"warning": "zero-exports"` to both when `{run_status}` is `partial`, and run the emitter:

```bash
cat > "{run_dir}/result-context.json" <<'SKF_JSON'
{"status": "{run_status}", "phase": null, "halt_reason": null, "error": null, "skill_package": "{skill_package}", "outputs": {"skill_md": "{skill_package}/SKILL.md", "context_snippet": "{skill_package}/context-snippet.md", "metadata": "{skill_package}/metadata.json", "references": "{skill_package}/references", "provenance_map": "{forge_version}/provenance-map.json", "evidence_report": "{forge_version}/evidence-report.md", "extraction_rules": "{forge_version}/extraction-rules.yaml"}, "summary": {"skill_name": "{name}", "version": "{version}", "forge_tier": "{tier}", "exports_documented": 0, "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}, "auto_decision_count": 0}, "result_contract": {"skill": "skf-create-skill", "status": "{run_status}", "outputs": [{"type": "skill", "path": "{skill_package}/SKILL.md"}, {"type": "skill", "path": "{skill_package}/context-snippet.md"}, {"type": "skill", "path": "{skill_package}/metadata.json"}, {"type": "report", "path": "{forge_version}/evidence-report.md"}], "summary": {"skill_name": "{name}", "version": "{version}", "exports_documented": 0, "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}, "auto_decision_count": 0}}}
SKF_JSON
uv run {emitEnvelopeHelper} emit --workflow skf-create-skill --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

The evidence report in `outputs` carries the `## Auto-Decisions` audit table: a pipeline consumer follows its path to audit the run. Display the line the emitter prints. If it exits non-zero, fix `result-context.json` once (its `message` names the problem) and run it again. When it fails again, display its `message`: this brief has no result contract.

**If `{emitEnvelopeHelper}` resolved no path** (an incomplete install), write no result contract: append "Result contract skipped: skf-emit-result-envelope.py is missing." under `{forge_version}/evidence-report.md`'s `## Remaining Warnings`, and set `validation_status: 'schema-unavailable'` in `{skill_package}/metadata.json`, rewritten through `python3 {atomicWriteHelper} write --target {skill_package}/metadata.json` when `{atomicWriteHelper}` resolves. Pipeline consumers observe the missing `-latest.json` and the metadata flag.

**Post-completion hook.** When `{onCompleteCommand}` is non-empty (SKILL.md On Activation §3 resolved it from `workflow.on_complete`) and the emitter wrote this brief's result contract (its `emit` exited 0), run it as a shell command from `{project-root}`, for this brief:

```bash
{onCompleteCommand} --result-path={forge_version}/create-skill-result-latest.json
```

The hook runs after the contract, so a git-add, registry registration or notifier sees a complete package. A hook failure never fails the brief, since the skill is written and its result contract is final: display "on_complete failed for `{name}`: {its exit code and first stderr line}" and go on. When the emitter wrote no result contract for this brief (no `{emitEnvelopeHelper}`, or `emit` failed twice), `--result-path` would name a missing file or an earlier compile's: skip the hook and display "on_complete skipped for `{name}`: no result contract was written ({the reason})". When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

**Remove the run folder.** The brief finished, so outside `--batch` delete `{run_dir}` (`rm -rf "{run_dir}"`); under `--batch`, batch-mode.md §3 reads the staged `result-context.json` there and removes the folder itself. A halted brief keeps its folder, with the decisions it recorded and its staged payloads.

### 6. Chain to the Next Step

**Under `--batch`:** go to `references/batch-mode.md` §3, which records this brief from the `result-context.json` §5 staged and hands out the next one. The health check waits for the batch summary.

**Otherwise:** load `{nextStepFile}`, read it fully, and execute it. The health check runs once per run, after the brief's result contract and hook.
