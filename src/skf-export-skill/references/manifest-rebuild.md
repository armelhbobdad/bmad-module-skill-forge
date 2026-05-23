---
# Static reference loaded by update-context.md §4a only when manifest
# schema documentation is needed (the in-prompt schema is otherwise
# delegated to skf-manifest-ops.py which handles v2 enforcement and
# v1→v2 migration internally).
---

<!-- Config: communicate in {communication_language}. -->

# Export Manifest v2 — Schema Reference

## Purpose

Reference for the v2 export manifest schema enforced by `skf-manifest-ops.py` and consumed by every workflow that touches `{skills_output_folder}/.export-manifest.json`. This file is the source of truth for the v2 shape; the helper script implements it; downstream skills (drop-skill, rename-skill, update-skill) read this same file to stay aligned.

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

## v1 → v2 migration (handled by `skf-manifest-ops.py`)

Pre-rename v2 manifests used a `platforms` array at the version level. If a version entry contains `platforms` instead of (or in addition to) `ides`, the helper treats `platforms` as `ides` and rewrites it on the next manifest write — silent in-place upgrade, no user prompt.

For v1 manifests (no `schema_version` field), the helper migrates in-place on the first read:

1. For each entry in `exports`, read its `last_exported`
2. Resolve the skill's current version from `{resolved_skill_package}/metadata.json`
3. Wrap in v2 structure: `active_version` ← resolved version, single entry in `versions` with `status: "active"`, `ides: []` (unknown — fills on next successful export), and `last_exported`
4. Set `schema_version: "2"` at root

Workflows that load the manifest via `skf-manifest-ops.py read` receive a `{"status": "ok", "manifest": {...}}` envelope; the `manifest` value is always in canonical v2 shape regardless of on-disk state (parse `result["manifest"]`, not the top-level object).

## Integrity invariant

`active_version` must resolve to a `versions` entry. If `active_version` is set but there is no matching key under `versions`, the manifest is inconsistent (possible corruption or a botched v1→v2 migration). Workflows must skip the affected skill and surface a loud warning rather than fall through to a degraded state. The recommended recovery is to re-run `[EX] Export Skill` on the affected skill — the export pass rebuilds the version entry from `metadata.json` ground truth.
