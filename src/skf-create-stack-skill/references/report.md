---
nextStepFile: 'health-check.md'
# §2b copies the -latest result file to the stack group root with the
# atomic writer; without it, §2b skips that copy with a warning.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 9: Stack Skill Report

## STEP GOAL:

Display the final summary of the forged stack skill with confidence distribution, output file listing, and next workflow recommendations.

## Rules

- Write only the §2b result contract (the per-run record and its `-latest` copy in `{forge_version}/`, and the `-latest` copy at the stack group root), then delete the run folder (§3). The rest of the report is console output only
- Lead with the positive summary, then details, then warnings
- Recommend next workflows based on what was produced
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

### 1. Report the Forge Result

Surface the forge result to the console, leading with the win:

- **Headline:** stack `{stack_name}`: `{lib_count}` libraries, `{integration_count}` integration patterns, forge tier `{tier}`.
- **Confidence (libraries per tier, from `metadata.json` `confidence_distribution`):** T1 {n}, T1-low {n}, T2 {n}, T3 {n}. In code mode, T1 = an ast-grep rule matched every export and T1-low = at least one export was read by eye, or none was recorded. **In compose-mode**, each library keeps its constituent's own tier (`evidence_tier`), which reflects how that skill was generated, not the current compose run.
- **Output files:** the `{skill_package}` deliverables (SKILL.md, context-snippet.md with `{token_estimate}` tokens, metadata.json, `references/` per-library files, and `references/integrations/` pair files when integrations exist), the `{forge_version}` workspace (provenance-map.json, evidence-report.md), and the `{skill_group}/active -> {version}` symlink.
- **Validation:** all checks passed, or `{warning_count}` finding(s) each with its description.
- **Warnings, only if `workflow_warnings[]` is non-empty:** each line of `{run_dir}/warnings.jsonl` decoded as the JSON string it holds, which is in the `[{step}/{severity}] {code}: {message}` form. That sink (SKILL.md's *Workflow state contract*) holds every warning recorded during the run; if it is empty, omit this section.

### 2. Recommend Next Workflows

"**Next steps:**
- **[TS] test-skill**: Validate the stack skill against its own assertions
- **[EX] export-skill**: Validate the package, write its context snippet and update the managed section in CLAUDE.md, AGENTS.md or .cursorrules

- **[VS] verify-stack**: Validate the stack's integration feasibility against your architecture document{IF compose_mode:} (re-run to confirm feasibility after any architecture changes from **[RA] refine-architecture**){END IF}"

### 2b. Result Contract

The shared emitter writes the result contract (`shared/references/output-contract-schema.md`) and builds the success envelope in one call. Resolve the atomic writer first (see **Missing atomic writer** below), and `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound. Stage `{run_dir}/result-context.json`:

```json
{"status": "success", "skill_package": "{skill_package}", "skill_name": "{stack_name}",
 "stack_libraries": ["<library>"], "mode": "code|compose", "quality_score": null, "halt_reason": null,
 "result_contract": {"skill": "skf-create-stack-skill", "status": "success",
  "outputs": [{"type": "skill", "path": "{skill_package}/SKILL.md"},
              {"type": "skill", "path": "{skill_package}/context-snippet.md"},
              {"type": "skill", "path": "{skill_package}/metadata.json"},
              {"type": "report", "path": "{forge_version}/evidence-report.md"}],
  "summary": {"lib_count": 0, "integration_count": 0, "forge_tier": "<tier>", "confidence_tier": "<tier>",
              "confidence_distribution": {}, "quality_score": null}}}
```

`skill_package` is the absolute path to the committed package and `stack_libraries` the committed `metadata.json`'s `libraries`. Both `quality_score` fields are `{quality_score}`, the skill-check score step 8 §3 bound (`null` when skill-check did not run), never a test-skill score. The summary's counts, `confidence_tier` and `confidence_distribution` are the committed `metadata.json`'s `library_count`, `integration_count`, `confidence_tier` and `confidence_distribution`, and `forge_tier` its run tier. Then run:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-create-stack-skill --run-dir "{run_dir}" --result-dir "{forge_version}" < "{run_dir}/result-context.json"
```

The emitter stamps `timestamp`, `run_id`, the run's auto-decisions and its warnings into the record, writes `create-stack-skill-result-<YYYYMMDD-HHmmss>.json` (it picks the name, with `-2` for a run that ends in the same second as another) and its `create-stack-skill-result-latest.json` copy in `{forge_version}`, and prints the success line on stdout: display it when `{headless_mode}` is true. A file it cannot write becomes a `result_file_write_failed` warning in the envelope, with `result_path` `null` when the per-run record is the one that failed. If the emitter exits non-zero, fix the payload its stderr names and run it once more; if it fails again, print its error and continue: the result contract is advisory and never halts the report.

**Stable latest pointer at the stack group root.** Pipeline consumers read `{forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json`, above the version folder, without knowing the current version. Copy the record there (a copy, not a symlink, so no consumer chases a link across version folders):

```bash
python3 {atomicWriteHelper} write --target {forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json < {forge_version}/create-stack-skill-result-latest.json
```

Skip the copy when the emitter printed no line, or when its envelope's `warnings` hold a `result_file_write_failed` entry naming `create-stack-skill-result-latest.json` or `{forge_version}` itself: the `-latest` file there may then hold an earlier run's record. If the copy is skipped or fails, print "The group-root copy of the result contract was not written: {the reason}", leave any prior group-root `-latest.json` untouched, and continue: §1 has already listed the warnings.

**Missing atomic writer.** Resolve `{atomicWriteHelper}` from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists, append `{step: "step-09", severity: "warn", code: "result-contract-skipped", message: "group-root result copy skipped: skf-atomic-write.py not found (re-install SKF)"}` to `workflow_warnings[]` before the emit, so the envelope and the result files carry it, print its message, since §1 has already listed the warnings, and make no group-root copy; any prior one stays untouched. The emitter still writes the result files in `{forge_version}`, so a missing writer never halts the report.

### 2c. Post-Completion Hook (optional)

If `{onCompleteCommand}` (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) is non-empty, invoke it now, after §2b and before chaining to health-check:

```bash
{onCompleteCommand}
```

The hook runs even when §2b updated no `create-stack-skill-result-latest.json` (a failed write or emit); that file then still holds an earlier forge's record, if any.

Run it with a bounded timeout (default 60s). On success, continue. On non-zero exit, timeout, or any failure, print one report line, `on_complete failed (exit {N}): {stderr_first_line}`, and continue: §1 has already listed the warnings and §2b has emitted the envelope, so that line is where the failure shows. **The hook must never fail the workflow**: it is integration glue (catalog registration, downstream pipeline notify) orthogonal to the forged stack. When `{onCompleteCommand}` is empty (bundled default), skip this section entirely.

### 3. Chain to Health Check

After the report sections above are handled, delete the run folder, whose warnings and decisions the envelope and the result files now hold: `rm -rf "{run_dir}"`. Then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step: do not stop here even though the report reads as final.

