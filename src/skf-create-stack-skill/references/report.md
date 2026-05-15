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

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Display Stack Forged Banner

"**Stack forged: {project_name}-stack — {lib_count} libraries, {integration_count} integration patterns**

Forge tier: **{tier}**"

### 2. Display Confidence Distribution

"**Confidence distribution:**

| Tier | Count | Description |
|------|-------|-------------|
| T1 | {count} | AST-verified structural extraction |
| T1-low | {count} | Source reading inference |
| T2 | {count} | QMD-enriched temporal context |

{IF compose_mode:}
*Note: Confidence tiers above are inherited from source skills — they reflect the extraction method used when those skills were originally generated, not the current compose run.*
{END IF}"

### 3. Display Output File Summary

"**Output files:**

**Deliverables** (`{skill_package}`):
- SKILL.md — Integration patterns, library summaries, conventions
- context-snippet.md — Compressed stack index ({token_estimate} tokens)
- metadata.json — Skill metadata and library registry
- references/ — {lib_count} per-library reference files
{If integrations:} - references/integrations/ — {pair_count} integration pair files

**Workspace** (`{forge_version}`):
- provenance-map.json — Extraction source tracking
- evidence-report.md — Evidence and confidence breakdown

**Symlink:** `{skill_group}/active` -> `{version}`"

### 4. Display Validation Summary

**If validation passed with no findings:**

"**Validation:** All checks passed"

**If validation had findings:**

"**Validation:** {warning_count} warning(s) found
{For each finding:}
- ⚠ {description}"

### 5. Display Warnings (Conditional)

Read from the `workflow_warnings[]` accumulator defined in the Workflow Rules of `SKILL.md` (M4). Every step that emitted a warning during this run pushed a structured entry there — this section is the single sink that surfaces them.

**Only display if `workflow_warnings[]` is non-empty:**

"**Warnings:**
{For each entry in workflow_warnings[]:}
- [{step}/{severity}] {code}: {message}"

**If `workflow_warnings[]` is empty:** Skip this section entirely.

### 6. Recommend Next Workflows

"**Next steps:**
- **[TS] test-skill** — Validate the stack skill against its own assertions
- **[EX] export-skill** — Package for distribution or agent loading

- **[VS] verify-stack** — Validate the stack's integration feasibility against your architecture document{IF compose_mode:} (re-run to confirm feasibility after any architecture changes from **[RA] refine-architecture**){END IF}"

### 6b. Result Contract

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

### 7. Chain to Health Check

ONLY WHEN the forge banner, confidence distribution, output file summary, validation summary, warnings (if any), next-workflow recommendations, and result contract have all been handled will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

