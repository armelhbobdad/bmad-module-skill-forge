---
created: "2026-04-25 21:12"
session: "2a66cf80-107e-443d-9038-c8f0fa1171f6"
source: claude-mem
source_table: observations
source_ids: [7538, 7539, 7540]
---

# Provenance-map entries carry no URL for docs-only claims

`provenance-map.json` entries (schema under "provenance-map.json Structure" in `src/skf-create-skill/assets/skill-sections.md`, mirrored in `src/knowledge/provenance-tracking.md`) carry only `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type` and `signature_source` — there is no `source_url` or `doc_url` field. Docs-only skills (`source_type: "docs-only"`, `src/skf-create-skill/references/sub/fetch-docs.md` §5) cite `[EXT:{url}]` inline in SKILL.md, but that URL never lands in a provenance entry; doc drift is tracked out-of-band instead — `metadata.json` `doc_sources[]` (`url` + `content_hash`, read by `skf-audit-skill` `references/step-doc-drift.md`) and `skf-update-skill` `references/re-extract.md` re-fetching the brief's `doc_urls`. Promoted authoritative docs appear only as `file_entries[]` rows with `file_type: "doc"` and are not copied into the skill. So audit cannot verify a T3 claim against its cited URL from the provenance map alone; treat this as a known open schema gap, not an oversight in a single file to patch in isolation.
