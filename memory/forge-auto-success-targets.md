---
created: "2026-05-25 22:28"
session: "426d2e5c-f0d3-4a7a-9547-1b222bc80a76"
source: claude-mem
source_table: observations
source_ids: [12857]
---

# forge-auto success targets: 70% auto-brief, ~3 min happy path

The success bars for `forge-auto` are: auto-brief accepted without interactive fallback on 70% of public repos with detectable docs, with 80% as the stretch goal; ~3 minutes time-to-skill on the happy path (the PRD records it as 3-5 minutes), 5-7 minutes when interactive fallback is needed. The user set them: "Keep the ~3 min target for the happy path, but note the fallback time in the PRD. ... I'd set the initial target at 70% and treat 80% as the stretch goal". They are written only in the gitignored `_bmad-output/planning-artifacts/prds/prd-bmad-module-skill-forge-2026-05-25/prd.md` (success criteria, SM-1 and SM-2) and the matching brief; no public doc (`docs/forge-auto.md`, `ROADMAP.md`) states them. The 90%/80% figures in the docs are the Test Skill quality threshold, not this acceptance rate.
