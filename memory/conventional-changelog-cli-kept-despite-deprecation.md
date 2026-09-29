---
created: "2026-04-20 21:32"
session: "10a74550-bf17-4196-bd75-0cb38ce14694"
source: claude-mem
source_table: observations
source_ids: [6647, 6682, 6728]
---

# conventional-changelog-cli removed: tools/changes.js renders the CHANGELOG

`conventional-changelog-cli` stayed a devDependency despite npm's "This package is no longer maintained" warning because the seeded CHANGELOG.md and every release cut used its `conventionalcommits` heading shape, `## [X.Y.Z](compare-url) (YYYY-MM-DD)`. #578 removed it, together with the Windows `npx --no-install conventional-changelog-cli --help` smoke step in quality.yaml and the "Restore CHANGELOG preamble" awk step and bogus-issue-ref grep in release.yaml. release.yaml's "Write release notes and CHANGELOG.md" step now runs `tools/changes.js release`, which renders the new block from the change fragments in `changes/*.yaml` under `## [Unreleased]`, in the same heading shape with a compare link from the last stable tag, and leaves older history byte-identical. A conventional-changelog deprecation warning in an install log now means a stale lockfile, not an expected state.
