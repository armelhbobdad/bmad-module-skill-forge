<!-- Config: communicate in {communication_language}. -->

# Export Manifest v2 — Schema Reference

The v2 shape of `{skills_output_folder}/.export-manifest.json`, which `skf-manifest-ops.py` reads, migrates and writes for export-skill, drop-skill and rename-skill: no step edits the manifest in the prompt or loads this file.

## v2 Schema

```json
{
  "schema_version": "2",
  "exports": {
    "skill-name": {
      "active_version": "0.6.0",
      "versions": {
        "0.1.0": {
          "ides": ["claude-code"],
          "last_exported": "2026-01-15",
          "status": "deprecated"
        },
        "0.5.0": {
          "ides": ["claude-code"],
          "last_exported": "2026-03-15",
          "status": "archived"
        },
        "0.6.0": {
          "ides": ["claude-code", "github-copilot"],
          "last_exported": "2026-04-04",
          "status": "active"
        }
      }
    }
  }
}
```

## Status enum

- `"active"` — currently exported; snippet appears in managed sections
- `"archived"` — previously exported, not active; files retained for rollback
- `"deprecated"` — dropped via drop-skill workflow; excluded from all exports (files may or may not exist on disk)
- `"draft"` — created but never exported
