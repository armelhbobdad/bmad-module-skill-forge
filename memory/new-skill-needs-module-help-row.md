---
created: "2026-06-03 17:05"
session: "bc54efb6-8471-477b-9a57-d8c05cfddeac"
source: claude-mem
source_table: both
source_ids: [14650, 14652, 14656, 14660]
---

# A new skf-* skill is registered nowhere until its module-help.csv row is added by hand

Adding a `src/skf-<name>/` directory with a SKILL.md gets the skill installed (the installer copies every `src/skf-*` directory), but `src/module-help.csv` has no generator, `tools/cli/lib/installer.js` only copies it, and `npm test` asserts nothing about it — so `skf-campaign` shipped for a week (skill added 2026-05-27, commit 7e01c0ab; row added 2026-06-03, commit 9a288ca1) invisible to bmad-help routing. Only the external BMB validator (`bmad-module-builder` → `validate-module.py`, not part of the repo's test suite) reports it, as a high `missing-entry` finding. A new skill needs its own row with a unique 2-letter menu code plus reciprocal ordering entries on its neighbours (campaign lists `skf-setup` under `preceded-by`, and `skf-setup`'s `followed-by` gained `skf-campaign`), a row in the hand-maintained Ferris menu table in `src/skf-forger/SKILL.md`, and a matching entry in the `docs/workflows.md` reference table per CONTRIBUTING.md.
