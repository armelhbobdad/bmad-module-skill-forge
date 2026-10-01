# QMD Collection Registration (Deep Tier)

Loaded by step 5 §3b only when forge tier is Deep AND QMD is available, before step 5 prints the result envelope. Skipped silently otherwise.

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

After `qmd embed` completes, verify the collection was embedded:

- Run `qmd status` or `qmd collection list` and confirm `{skill-name}-brief` shows document count > 0
- If verification succeeds: proceed to registry update with no `status` field
- If verification fails: log warning "QMD embed verification failed for {skill-name}-brief — collection may not be searchable yet", proceed to registry update but include `status: "pending"` in the entry

## Registry Update (Delegated to Script)

Stage the entry in the run folder through a quoted heredoc, then run the `register-qmd-collection` subcommand on the file. Add `"status": "pending"` to the object only when embed verification failed:

```bash
cat > "{run_dir}/qmd-entry.json" <<'SKF_JSON'
{"name": "{skill-name}-brief", "type": "brief", "source_workflow": "brief-skill", "skill_name": "{skill-name}", "created_at": "{current ISO date}"}
SKF_JSON
uv run {forgeTierRwHelper} register-qmd-collection --target {forgeTierFile} < "{run_dir}/qmd-entry.json"
```

The script handles the upsert deterministically (replace existing entry with same `name`, else append) and preserves all other forge-tier state (tools, tier, ccc_index, ccc_index_registry, other qmd_collections entries) — no need to reason about YAML re-rendering or section comments.

## Error Handling

- If `qmd embed` or `qmd collection add` fails: log the error. Do NOT fail the workflow — the brief file was already written successfully.
- If the `register-qmd-collection` script call fails: log the error JSON, continue. The brief is the user-visible artifact; the registry entry is a portfolio-search optimisation.
- If `{forgeTierRwHelper}` has no path (step 5 §3b found no `skf-forge-tier-rw.py`): skip the Registry Update. Step 5 has added the warning to `workflow_warnings[]`.
