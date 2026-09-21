---
created: "2026-04-17 22:31"
session: "32e9eb66-b5be-4352-bf0c-d38d8793dc64"
source: claude-mem
source_table: observations
source_ids: [6222, 6223]
---

# Apply every review recommendation in the same turn

When a critique or design review yields a list of recommendations — a frontend-design pass on `website/`, party-mode critics on `docs/`, or a code-review layer — apply all of them in the same turn that produced the list, rather than presenting proposals and waiting for per-item approval. The user's standing instruction after a docs-site design-review list was only partly applied: "we should apply all the recommendations everytime. I say ALL". Frame genuinely uncertain items as alternatives not chosen; if the list contains something unwanted, that is a defect in the review itself, not a reason to gate application. Nothing in CONTRIBUTING.md or docs/_internal/ records this expectation.
