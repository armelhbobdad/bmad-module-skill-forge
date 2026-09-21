---
created: "2026-04-13 16:31"
session: "a5591f15-f074-4f5f-b70e-8260eba1d5ef"
source: claude-mem
source_table: observations
source_ids: [6110, 6122, 6124]
---

# camelCase for inter-step frontmatter state fields

Frontmatter fields that carry state between a skill's step files (report templates and `references/*.md` producers/consumers) are camelCase — `previousReport`, `coveragePercentage`, `recommendationCount`, `pairsVerified`, `deltaImproved`, `thresholdFallback` — per `src/shared/references/feasibility-report-schema.md` (v1.0) and `src/skf-verify-stack/assets/feasibility-report-template.md`. The headless `SKF_*_RESULT_JSON` envelopes in each `SKILL.md` deliberately use snake_case keys (`coverage_percentage`, `recommendation_count`, `halt_reason`), so a value changes convention only at the envelope boundary. Before v1.0, snake_case variants (`previous_report`, `coverage_percentage`, `integrations_*`) were mixed into step files and producers/consumers silently mismatched; `test/test-workflow-state.js` initially expected snake_case and failed 24 of 38 checks until aligned. That test (`npm run test:workflow`) is the only thing that checks spelling, and only for verify-stack, refine-architecture and compose mode, so a new state field in any other skill must be camelCase and spelled identically in every step that reads it — nothing else catches the mismatch. Neither CONTRIBUTING.md nor docs/ states this convention.
