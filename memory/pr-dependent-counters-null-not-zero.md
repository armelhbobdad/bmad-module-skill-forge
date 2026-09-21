---
created: "2026-03-28 00:23"
session: "e7113361-9c87-40bc-84ee-5635215965d2"
source: claude-mem
source_table: session_summaries
source_ids: [883, 884]
---

# PRD-dependent report counters initialize to null

In `src/skf-verify-stack/assets/feasibility-report-template.md` the always-computed counters (`coveragePercentage`, `pairsVerified`, `recommendationCount`, ...) start at `0`, but the PRD-dependent ones (`requirementsFulfilled`, `requirementsPartial`, `requirementsNotAddressed`, `deltaImproved`, `deltaRegressed`, `deltaNew`, `deltaUnchanged`) start at `null`. `references/report.md` renders them as `{fulfilled_count or 'N/A — no PRD'}`: `null` means "not computed" and falls through to N/A, while a real `0` prints as `0`. `references/requirements.md` only sets those counts when `prdAvailable` is true, so normalizing the `null`s to `0` for tidiness would make a run without a PRD report zero requirements fulfilled instead of N/A. Keep the null/0 split when adding optional counters to any report template that uses an `or 'N/A'` fallback.
