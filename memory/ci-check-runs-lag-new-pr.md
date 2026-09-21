---
created: "2026-04-23 18:46"
session: "25a85fef-fbc2-4fcd-906d-c1c8f434f9f6"
source: claude-mem
source_table: observations
source_ids: [7047, 7048, 7049]
---

# CI check-runs lag a new PR by up to three minutes

Right after `gh pr create`, `gh run list --branch <branch>`, `gh pr view --json statusCheckRollup` and `gh api /repos/armelhbobdad/bmad-module-skill-forge/commits/<sha>/check-runs` can all stay empty for 1.5–3 minutes: on PR #203 (created 14:45:16Z) the first run appeared at +96 s and the `pull_request`-triggered Quality & Validation run — the one carrying the 7 required contexts from `.github/workflows/quality.yaml` — only started at +166 s. An empty check list in the first few minutes therefore does not mean `quality.yaml` failed to trigger; poll every 10 s for at least 3 minutes before diagnosing triggers or branch protection. The bot-PR path in `.github/workflows/release.yaml` ("Wait for required status checks") encodes the same tolerance with its 2-minute registration poll.
