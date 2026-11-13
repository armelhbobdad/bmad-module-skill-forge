---
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
qmdPortfolioSimilarityProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-qmd-portfolio-similarity.py'
  - '{project-root}/src/shared/scripts/skf-qmd-portfolio-similarity.py'
---

# QMD Collection Registration (Deep Tier)

Loaded by step 5 §3b and, for an `[auto]` brief, step-auto-validate.md §3, only when forge tier is Deep AND QMD is available, before the run builds its result envelope. Skipped silently otherwise.

Index the skill brief into a QMD collection so portfolio-level searches can find existing briefs and avoid duplicate skill creation across large monorepos.

## Collection Creation

Create a QMD collection targeting only the brief file:

```bash
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

If the collection already exists (re-briefing): remove and recreate for atomic replace:

```bash
qmd collection remove {skill-name}-brief
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

## Embed Verification

After `qmd embed` completes, check that the collection holds the brief: resolve `{qmdPortfolioSimilarityHelper}` from `{qmdPortfolioSimilarityProbeOrder}` (first existing path wins) and run

```bash
uv run {qmdPortfolioSimilarityHelper} verify-collection "{skill-name}-brief"
```

It prints `{name, documents}`, the number of files QMD lists for the collection: 0 when it is not listed, null when QMD gives no count.

- `documents` above 0: proceed to registry update with no `status` field
- `documents` 0 or null, a non-zero exit, no JSON, or no helper path: log the warning `QMD embed verification failed for {skill-name}-brief: collection may not be searchable yet`, record it with `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "QMD embed verification failed for {skill-name}-brief: collection may not be searchable yet"`, then proceed to registry update but include `status: "pending"` in the entry

## Registry Update (Delegated to Script)

Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}` (first existing path wins; with no path, see Error Handling). Stage the entry in the run folder through a quoted heredoc, then run the `register-qmd-collection` subcommand on the file. Add `"status": "pending"` to the object only when embed verification failed:

```bash
cat > "{run_dir}/qmd-entry.json" <<'SKF_JSON'
{"name": "{skill-name}-brief", "type": "brief", "source_workflow": "brief-skill", "skill_name": "{skill-name}", "created_at": "{current ISO date}"}
SKF_JSON
uv run {forgeTierRwHelper} register-qmd-collection --target {forgeTierFile} < "{run_dir}/qmd-entry.json"
```

The script upserts the entry by `name`.

## Error Handling

- If `qmd embed` or `qmd collection add` fails: log the error, write `QMD collection not created: <the first line of its stderr>` to `{run_dir}/warning.txt` with a file write, never `echo`, and run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The brief is already written, so go on.
- If the `register-qmd-collection` script call fails: log the error JSON, write `QMD registry not updated: <its message>` to `{run_dir}/warning.txt` with a file write, never `echo`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, and continue. The brief is the user-visible artifact; the registry entry is a portfolio-search optimisation.
- If `{forgeTierRwHelper}` has no path (neither path of `{forgeTierRwProbeOrder}` exists): the brief is already written, so do not HALT. Skip the Registry Update and record the warning: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "QMD registry not updated: skf-forge-tier-rw.py not found"`.
