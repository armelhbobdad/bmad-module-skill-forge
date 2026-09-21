---
created: "2026-06-04 21:16"
session: "fd6d65dc-56e5-4596-8f20-d00d4b025b8e"
source: claude-mem
source_table: observations
source_ids: [15579]
---

# actions/checkout held at v5, not v6

All eight `actions/checkout` uses across `.github/workflows/` (docs.yaml, quality.yaml, release.yaml:55) are pinned at v5, and that stop is deliberate: in the June 2026 Node 24 runtime bump (commit eee13a34, PR #445) checkout v6 was skipped because it moves the git credentials into a separate file, which touches the path release.yaml relies on when it does `git push origin` (lines 286 and 707) with the token checkout received via `with: token: ${{ secrets.GITHUB_TOKEN }}` (line 58). Every other action went to its Node 24 line in the same PR (setup-node v6, github-script v9, action-gh-release v3, setup-uv v8.2.0 exact-pinned because v8 stopped publishing floating major tags, upload-pages-artifact v5, deploy-pages v5). The workflow files carry no comment about this — the reason lives only in the commit body — so a bump to checkout v6 needs its own validated release cut, not a routine version sweep.
