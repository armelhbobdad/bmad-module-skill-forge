---
created: "2026-05-02 21:49"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: observations
source_ids: [8388, 8389, 8390, 8392]
---

# Inserting a numbered section breaks § cross-references

Step references under `src/*/references/*.md` use numbered sections (`### 1. Discover Forge Tier`, `### 3b. …`) and other files cite them by number — `step 1 §1` alone appears about 25 times across `src/` (e.g. `src/skf-brief-skill/references/invocation-contract.md`, `write-brief.md`), and no test or lint checks those references. Inserting a new numbered section near the top of a step file cascades renumbering through every later section and subsection and silently invalidates every `§N` citation in SKILL.md, contracts and sibling steps; this was hit when adding the skf-brief-skill pre-flight write probe as a new §1. Extend an existing section instead — the write probe lives inside `### 1. Discover Forge Tier` in `src/skf-brief-skill/references/gather-intent.md` for exactly this reason (commit caaab468). If a renumbering is unavoidable, grep `src/` for `step N §` and `§N` citations of that file and update them in the same change.
