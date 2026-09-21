---
created: "2026-06-03 21:29"
session: "68c5ada7-6915-4d75-b231-06c23d6d3b7b"
source: claude-mem
source_table: session_summaries
source_ids: [3556, 3558, 3561]
---

# Recurring defect classes in skf-* workflow audits

The June 2026 hardening sweep over all 16 `src/skf-*/` skills (PR #437, `fix(skf): close installed-mode wiring, halt-contract, and customization gaps across SKF workflows`) kept finding the same three genuine bugs: a SKILL.md "Exit Codes" table declaring a code that no step actually raises (compare each row's "Raised by" against the step files, e.g. `src/skf-test-skill/SKILL.md` §Exit Codes), `customize.toml` scalars such as `default_threshold`, `on_complete` or `*_path` declared but never read through a resolved variable in any step, and headless gates that re-prompt in a loop with no HALT branch even though `src/shared/references/headless-gate-convention.md` requires a halt on missing required input. None of these are caught by `tools/validate-skills.js` (SKILL-01..07, STEP-01/06/07 only) or `npm run quality`, so they only surface in a manual read. When auditing or hardening a workflow, check these three classes first, alongside bare `src/` script paths (recorded separately).
