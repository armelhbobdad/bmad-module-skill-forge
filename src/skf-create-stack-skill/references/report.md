---
nextStepFile: 'health-check.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 9: Stack Skill Report

## STEP GOAL:

Display the final summary of the forged stack skill with confidence distribution, output file listing, and next workflow recommendations.

## Rules

- Do not write or modify any files — report is console output only
- Lead with the positive summary, then details, then warnings
- Recommend next workflows based on what was produced
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

### 1. Report the Forge Result

Surface the forge result to the console, leading with the win:

- **Headline:** stack `{project_name}-stack` — `{lib_count}` libraries, `{integration_count}` integration patterns, forge tier `{tier}`.
- **Confidence distribution:** the T1 / T1-low / T2 counts (T1 = AST-verified structural extraction, T1-low = source-reading inference, T2 = QMD-enriched temporal context). **In compose-mode**, note the tiers are inherited from the source skills — they reflect the extraction method used when those skills were originally generated, not the current compose run.
- **Output files:** the `{skill_package}` deliverables (SKILL.md, context-snippet.md with `{token_estimate}` tokens, metadata.json, `references/` per-library files, and `references/integrations/` pair files when integrations exist), the `{forge_version}` workspace (provenance-map.json, evidence-report.md), and the `{skill_group}/active -> {version}` symlink.
- **Validation:** all checks passed, or `{warning_count}` finding(s) each with its description.
- **Warnings — only if `workflow_warnings[]` is non-empty:** the accumulated entries rendered as `[{step}/{severity}] {code}: {message}`. `workflow_warnings[]` (defined in SKILL.md's *Workflow state contract*) is the single sink surfacing every warning pushed during the run; if it is empty, omit this section.

### 2. Recommend Next Workflows

"**Next steps:**
- **[TS] test-skill** — Validate the stack skill against its own assertions
- **[EX] export-skill** — Package for distribution or agent loading

- **[VS] verify-stack** — Validate the stack's integration feasibility against your architecture document{IF compose_mode:} (re-run to confirm feasibility after any architecture changes from **[RA] refine-architecture**){END IF}"

### 2b. Result Contract

Write the result contract per `shared/references/output-contract-schema.md` using the shared atomic writer. Two artifacts — both written via `skf-atomic-write.py write`:

**Per-run record (inside the version dir):**

```bash
<json-content> | python3 {atomicWriteHelper} write \
  --target {forge_version}/create-stack-skill-result-{YYYYMMDD-HHmmss}-{pid}-{rand}.json
```

- `{YYYYMMDD-HHmmss}` is a UTC timestamp with seconds resolution.
- Append `-{pid}-{rand}` (process id + short random suffix) to the filename to avoid same-second collisions when multiple runs land in the same second (S16).

**Stable latest pointer (ABOVE the version dir, at the stack group root):**

```bash
<json-content> | python3 {atomicWriteHelper} write \
  --target {forge_data_folder}/{project_name}-stack/create-stack-skill-result-latest.json
```

- Note the path: the `-latest.json` lives at `{forge_data_folder}/{project_name}-stack/` (the stack group root), NOT inside `{forge_version}/`. Pipeline consumers read this stable path without knowing the current version.
- Write the same JSON body as the timestamped record (this is a copy, not a symlink, so pipeline consumers never chase a link across version boundaries).

Include `SKILL.md`, `context-snippet.md`, and `metadata.json` paths in `outputs`; include `lib_count`, `integration_count`, `forge_tier`, `confidence_tier`, and confidence distribution in `summary`.

If either atomic write fails, log the error, leave any prior `-latest.json` untouched, and continue — the report is advisory and should not block the health-check chain.

**Headless success envelope.** When `{headless_mode}` is true, emit the single-line result envelope on **stdout** (the success counterpart to the error envelopes every HARD HALT emits on stderr) before chaining to step 10. `skill_package` is the absolute path to the committed package; `stack_libraries` is the included library names:

```
SKF_STACK_RESULT_JSON: {"status":"success","skill_package":"{skill_package}","skill_name":"{project_name}-stack","stack_libraries":["<lib>", "..."],"mode":"{code|compose}","exit_code":0,"halt_reason":null}
```

### 2c. Post-Completion Hook (optional)

If `{onCompleteCommand}` (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) is non-empty, invoke it now — after the result contract (§2b) is written, before chaining to health-check:

```bash
{onCompleteCommand}
```

Run it with a bounded timeout (default 60s). On success, continue. On non-zero exit, timeout, or any failure, append the reason to `workflow_warnings[]` (e.g. `on_complete — failed (exit {N}): {stderr_first_line}`) and continue. **The hook must never fail the workflow** — it is integration glue (catalog registration, downstream pipeline notify) orthogonal to the forged stack. When `{onCompleteCommand}` is empty (bundled default), skip this section entirely.

### 3. Chain to Health Check

After the report sections above are handled, load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

