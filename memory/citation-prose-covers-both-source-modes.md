---
created: "2026-04-25 17:28"
session: "2a66cf80-107e-443d-9038-c8f0fa1171f6"
source: claude-mem
source_table: observations
source_ids: [7532, 7533, 7536, 7541, 7547, 7550]
---

# Citation prose must cover both source modes

SKF compiles from either a source repo (citations `file:line@SHA` at a pinned commit) or published docs (`source_type: "docs-only"`, `doc_urls` required, citations `[EXT:{url}]` with no SHA), and it does not restrict skills to public APIs: scope is a brief choice among Full Library, Specific Modules, Public API Only, Component Library and Reference App (`src/skf-brief-skill/assets/scope-templates.md`), and `source_authority: internal` is a valid value in `src/shared/scripts/schemas/skill-brief.v1.json`. Any prose about citations, falsifiability, or "not for you if" boundaries must describe both modes and must not claim SKF "extracts public APIs". In April 2026 `docs/why-skf.md` and the README lede, comparison table and "Verifying a Skill" section each described only the file:line form and were rewritten; `docs/verifying-a-skill.md:6` still opens with source-only wording ("a specific file, a specific line, and a specific commit in the upstream source"), so the blind spot is easy to reintroduce.
