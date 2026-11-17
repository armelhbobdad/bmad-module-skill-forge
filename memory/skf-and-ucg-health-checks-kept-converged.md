---
created: "2026-11-12 14:51"
session: "72e9f28d-d28a-41b5-917c-b01a8cd78569"
---

# SKF and UltraCode Goal health checks kept converged

The maintainer had Skill Forge's shared health check (`src/shared/health-check.md`, `src/shared/scripts/skf-health-check-seen.py`) and UltraCode Goal's (`skills/ultracode-goal/references/health-check.md`, `skills/ultracode-goal/scripts/health_check_fp.py` in bmad-module-ultracode-goal) brought together and put through the quality gate in both repositories under UCG #226, closed on 2026-11-16 once every item was ported or declined each way. The two share `test/fixtures/health-check-shared.json` byte for byte, with `.github/workflows/health-check-fixture-drift.yaml` in each repository comparing it with the other's `main`, and a change to the shared rules ships as a pair of PRs (SKF #1235 mirrors UCG #237). So a health-check fix in one repository is checked against the other before the work counts as done.
