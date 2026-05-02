# QMD Collection Registration (Deep Tier)

Loaded by step-05 §5 only when forge tier is Deep AND QMD is available. Skipped silently otherwise.

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

Build the entry JSON and pipe it to the `register-qmd-collection` subcommand:

```bash
echo '{
  "name": "{skill-name}-brief",
  "type": "brief",
  "source_workflow": "brief-skill",
  "skill_name": "{skill-name}",
  "created_at": "{current ISO date}"
  // include "status": "pending" only when embed verification failed
}' | uv run {forgeTierRwScript} register-qmd-collection --target {forgeTierFile}
```

The script handles the upsert deterministically (replace existing entry with same `name`, else append) and preserves all other forge-tier state (tools, tier, ccc_index, ccc_index_registry, other qmd_collections entries) — no need to reason about YAML re-rendering or section comments.

## Error Handling

- If `qmd embed` or `qmd collection add` fails: log the error. Do NOT fail the workflow — the brief file was already written successfully.
- If the `register-qmd-collection` script call fails: log the error JSON, continue. The brief is the user-visible artifact; the registry entry is a portfolio-search optimisation.
