---
created: "2026-04-19 23:05"
session: "44975342-f9b4-4072-b830-579c3d7090d8"
source: claude-mem
source_table: session_summaries
source_ids: [1897, 1898, 1900, 1904, 1912]
---

# Hand-rolled release.yaml over release-please and changesets

`.github/workflows/release.yaml` is the single, hand-written release pipeline (it consolidated the former `publish.yaml`, `manual-release.yaml` and the `release:*` npm scripts, all since deleted). release-please, changesets and semantic-release were evaluated in April 2026 and rejected: the existing conventional-commits workflow already covered roughly 80% of what release-please does, and changesets is aimed at monorepos while this is a single-package repo. That research lives only in the gitignored `_bmad-output/planning-artifacts/research/` folder, so nothing tracked in the repo says the alternatives were considered. If release-please is ever revisited, the maintained action is `googleapis/release-please-action`; `google-github-actions/release-please-action` was archived on 2024-08-15.
