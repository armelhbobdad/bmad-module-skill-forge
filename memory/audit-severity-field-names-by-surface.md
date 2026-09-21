---
created: "2026-04-09 14:14"
session: "43564723-f0c6-47d6-826c-097212da743c"
source: claude-mem
source_table: observations
source_ids: [5021]
---

# Audit severity field name differs by surface

The drift severity (`CLEAN|MINOR|SIGNIFICANT|CRITICAL`) that skf-audit-skill produces has two names depending on surface: the on-disk result contract `{forge_version}/audit-skill-result-latest.json` exposes it as `summary.severity` (the result-contract write in `src/skf-audit-skill/references/report.md`), while the headless stdout envelope `SKF_AUDIT_RESULT_JSON` (`src/skf-audit-skill/SKILL.md` § Result Contract) and the drift-report markdown frontmatter (`src/skf-audit-skill/assets/drift-report-template.md`) call the same value `drift_score`. `src/shared/references/pipeline-contracts.md` once documented the AS→US hand-off as reading `drift_score` from the JSON — a field that does not exist there — and was corrected to `summary.severity` (mirrored in `src/skf-forger/references/pipeline-mode.md`). When touching the forger, the pipeline contract or any consumer of the result JSON, read `summary.severity`; `drift_score` is only correct for the stdout line and the report frontmatter.
