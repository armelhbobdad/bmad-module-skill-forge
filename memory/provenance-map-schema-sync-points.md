---
created: "2026-03-18 21:15"
session: "d40284ec-234d-4a3e-bacb-2d72ebd53a47"
source: claude-mem
source_table: observations
source_ids: [1803, 1804, 1806, 1807]
---

# Provenance-map schema is copied in three files plus five helpers

The `provenance-map.json` entry shape (`export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type`, `signature_source`) replaced free-text `claim` strings in commit e22da52e (#58) so `skf-update-skill` can diff param-by-param instead of rewriting prose. The schema is not held in one place: `src/skf-create-skill/assets/skill-sections.md` ("provenance-map.json Structure", which `references/compile.md` calls the full schema), `src/skf-create-stack-skill/assets/provenance-map-schema.md` ("Canonical schema templates" for stack/compose runs) and `src/knowledge/provenance-tracking.md` (which `overview.md` calls the single authoritative source, and which had already drifted to a keyed-by-name example before #58). Python consumers that parse the fields: `src/shared/scripts/skf-load-provenance.py`, `skf-verify-provenance-completeness.py`, `skf-structural-diff.py`, `skf-render-metadata-stats.py` and `src/skf-test-skill/scripts/check-metadata-coherence.py`, plus the prose consumers `skf-test-skill/references/source-access-protocol.md` State 2 and `skf-update-skill/references/write.md`. A field change must touch all of them in one commit, or the knowledge fragment and one workflow will silently disagree again.
