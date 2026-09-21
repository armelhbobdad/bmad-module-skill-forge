---
created: "2026-04-19 16:51"
session: "4125f6a8-222c-4739-9ed7-b0612704757b"
source: claude-mem
source_table: observations
source_ids: [6299]
---

# Consult the published oms-* SKILL.md before writing about a library

When SKF prose (README.md, docs/, announcement or article drafts) characterises a library that already has a published oms-* skill, read `skills/<oms-name>/<version>/<oms-name>/SKILL.md` in the oh-my-skills clone (`oh_my_skills_path` in `docs/_data/pinned.yaml`, default `../oh-my-skills`) first: it is the SKF-produced, provenance-cited API description and the authoritative characterisation. A draft once described `cognee.add()` with `**kwargs` that the oms-cognee SKILL.md does not show. `npm run docs:validate-drift` only checks pinned versions/commits and the library whitelist, not API claims, so a wrong signature in prose passes CI.
