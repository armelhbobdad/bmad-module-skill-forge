---
created: "2026-04-21 13:38"
session: "9713e66f-7f75-4067-b7c5-b6281fa6587a"
source: claude-mem
source_table: observations
source_ids: [6823, 6985, 6988, 7003]
---

# Feature-branch release dispatch never exercises the main-dispatch path

Dispatching `.github/workflows/release.yaml` from any ref other than `main` takes the tag-only path: every step gated on `if: github.ref == 'refs/heads/main'` (push to `release/bot/vX.Y.Z-<run_id>`, open the bot PR, force-run quality.yaml, wait for approval, auto-merge, anchor the tag on the merge commit) is skipped, the `release: bump to vX` commit stays a CI-ephemeral orphan reachable only through the tag, and `package.json` on the source branch keeps the old version. A green alpha cut from a feature branch is therefore no evidence that the main-dispatch steps work: the v0.10.1-alpha.0 cut was green, and the first `--ref main` dispatch (v1.0.0-rc.1, run 24829166764) was the first time that code ever ran — it failed at the old "Push commit to main" step with `GH013: Repository rule violations`, which is why the PR-flow block exists (issue #198). Any change to the main-dispatch block can only be validated by a real `--ref main` dispatch, which is also a real npm publish; the feature-branch alpha cut that `docs/_internal/RELEASING.md` recommends for re-verification proves the OIDC chain, not the PR flow.
