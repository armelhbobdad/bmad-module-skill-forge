---
created: "2026-04-27 14:08"
session: "a7b342bc-609e-43bf-aba3-bf0dd1badb48"
source: claude-mem
source_table: session_summaries
source_ids: [7780, 7781]
---

# Vendor SKILL.md-only review action declined as CI

PR #172 ("Improve/skill review optimization", closed 2026-04-27) offered the `tesslio/skill-review` GitHub Action plus SKILL.md rewrites and was closed, not merged: SKF skills are multi-file trees (`SKILL.md` + `references/` + `scripts/` + `schemas/` + `shared/`), so a SKILL.md-only scorer cannot see script delegation, headless/envelope contracts, `nextStepFile` referential integrity or the load-bearing persona rules in `skf-forger`, and a vendor-submitted evaluator arriving in the vendor's own PR with a moving `@v1` tag is not added as CI; only description/trigger-phrase improvements were worth cherry-picking. Module-level validation is the bmad-builder `quality-analysis` workflow (<https://github.com/bmad-code-org/bmad-builder/>), whose graded reports land in `skills/reports/<skill>/quality-analysis/<timestamp>/quality-report.html` — local only, since `.gitignore` ignores `skills`. Keep the distinction: the `tessl` CLI is still used as a per-skill content scorer by skf-test-skill and recommended in `CONTRIBUTING.md`; only the CI action was declined. User: "SKF is validated using Bmad builder module (<https://github.com/bmad-code-org/bmad-builder/>) that include a dedicated workflow with a full report on each module. [...] In the next releases, All the other workflows with be validated until we have an excellence score too."
