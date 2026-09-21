---
created: "2026-03-25 21:38"
session: "0771053e-7d8d-4cca-9f95-e05ce34e7621"
source: claude-mem
source_table: observations
source_ids: [2324, 2334, 2346]
---

# Capability-tier list hardcoded in many independent places

There is no single source for the Quick/Forge/Forge+/Deep tier list; every consumer re-enumerates it: `VALID_TIERS` in src/shared/scripts/skf-detect-tools.py and skf-emit-result-envelope.py, the `confidence_tier` tuple in skf-validate-output.py, `tierColors` in tools/cli/commands/status.js, the `forge_tier` enums in src/skf-brief-skill/assets/skill-brief-schema.md and src/skf-analyze-source/assets/skill-brief-schema.md, `confidence_tier` in src/skf-create-skill/assets/skill-sections.md, plus prose in the package.json description, src/skf-setup/SKILL.md, src/shared/health-check.md, src/knowledge/overview.md, docs/concepts.md and every step that branches on tier. Adding Forge+ took two review passes because each place was missed separately. Also, `Quick/Forge` in step prose usually means "non-Deep" (e.g. extraction-patterns.md "Default (Quick/Forge, any scope)", ccc-bridge.md, skf-setup ccc-index.md), not an exhaustive list, so a new or renamed tier has to be checked against those branches one by one. When tiers change, grep `Quick/Forge`, `Quick|Forge`, `VALID_TIERS`, `confidence_tier` and `forge_tier` across src/, tools/, docs/ and package.json before calling it done.
