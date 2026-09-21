---
created: "2026-06-01 20:08"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14084, 14085]
---

# OpenAPI/Swagger specs are never a primary input

OpenAPI/Swagger/GraphQL specs are not a primary input for SKF: they are only recognised as schema assets inside a repository (`src/shared/scripts/skf-detect-scripts-assets.py:347-348`, `ASSET_TYPE_SCHEMA`), and the brief schema's `source_type` enum is `["source", "docs-only"]` (`src/shared/scripts/schemas/skill-brief.v1.json:36`) with no api-spec scope type. There is no spec parser, no `--openapi` flag and no spec-URL ingestion, so an API-spec-first skill is unsupported; the nearest paths are a repository that contains the spec (detected as an asset) or docs-only mode pointed at the rendered API docs URL. No docs page states this limitation.
