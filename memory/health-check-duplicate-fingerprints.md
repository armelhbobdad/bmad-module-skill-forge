---
created: "2026-04-21 04:15"
session: "879710db-7b7f-4dc8-a67a-376c488babfc"
source: claude-mem
source_table: observations
source_ids: [6653, 6654, 6655]
---

# Open health-check issues may duplicate already-fixed bugs under a new fingerprint

Health-check fingerprints are `sha1(severity|workflow|step_file|section-slug)[:7]` (`src/shared/health-check.md` §Fingerprint) and `.github/workflows/health-check-dedup.yaml` closes a report only when its `fp-*` label matches an earlier open issue exactly, so a section that was renamed or relocated, or a report slugged slightly differently, lands as a fresh open issue for a defect already fixed (health-check.md itself calls this 'safe but unlinked'). Hit on 2026-04-21: #188 (fp-66e0afd) and #189 (fp-55194e8) duplicated closed #183 (fp-b98e2f2) and #185 (fp-551fc4d) in skf-test-skill's coherence check, already fixed by 4e1a759 and a03ddef with `Fixes #183` / `Fixes #185` trailers. An open auto-filed issue is therefore not proof the bug is still present. Before re-fixing one, run `git log --oneline -S'<section term>' -- src/skf-<workflow>/references/<step>.md` and `gh issue list --state closed --search '<section>'` for a `Fixes #N` commit touching the same section; if found, close the duplicate pointing at the canonical issue instead of editing the step again.
