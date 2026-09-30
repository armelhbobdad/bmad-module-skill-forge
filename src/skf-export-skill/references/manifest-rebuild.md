---
# Static reference named by update-context.md §9b, loaded only when
# manifest schema documentation is needed (skf-manifest-ops.py enforces
# the v2 shape and migrates v1 internally, so no step edits the manifest
# in the prompt).
---

<!-- Config: communicate in {communication_language}. -->

# Export Manifest v2 — Schema Reference

## Purpose

Reference for the v2 export manifest schema that `skf-manifest-ops.py` enforces for every workflow that touches `{skills_output_folder}/.export-manifest.json`. This file documents the v2 shape and the helper implements it: export-skill, drop-skill and rename-skill read and edit manifest entries through the helper (`read`, `get`, `set`, `deprecate`, `remove`, `rename`), and `skf-rebuild-managed-sections.py assemble` reads it through the same code. Rename-skill's rollback is the one write outside it: it restores the byte copy of the manifest it kept before the re-key.

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

For v1 manifests (no `schema_version` field), every read returns the v2 shape, and the next write through the helper stores it:

1. Each entry's `versions` list becomes a map with one record per version: `ides: []` (unknown, filled on the next successful export) and `last_exported` from the manifest's `updated_at`
2. The entry's `active_version` keeps its value; that version's record gets `status: "active"`, or `"deprecated"` when the entry carries `deprecated: true`, and every other version `status: "archived"`
3. The `deprecated` and `deprecated_versions` keys are dropped and `schema_version: "2"` is set at the root

Workflows that load the manifest via `skf-manifest-ops.py read` receive a `{"status": "ok", "manifest": {...}}` envelope; the `manifest` value is always in canonical v2 shape regardless of on-disk state (parse `result["manifest"]`, not the top-level object).

## Integrity invariant

`active_version` must resolve to a `versions` entry. If `active_version` is set but there is no matching key under `versions`, the manifest is inconsistent (possible corruption or a botched v1→v2 migration). Workflows must skip the affected skill and surface a loud warning rather than fall through to a degraded state. The recommended recovery is to re-run `[EX] Export Skill` on the affected skill — the export pass rebuilds the version entry from `metadata.json` ground truth.
