---
created: "2026-04-23 02:52"
session: "a881dc92-dfb0-4d57-acfa-1ee2667e8c0b"
source: claude-mem
source_table: observations
source_ids: [6891, 6911, 6913, 6923]
---

# Bare #N tokens in commits become issue links

Until #578, release.yaml's `Update CHANGELOG.md` step ran `npx conventional-changelog-cli -p conventionalcommits`, which linked every `#N` in commits: `satisfy AC#3` linked issue 3, `mentions AC#4` linked a repository named `AC`, and Story 3.2's `closes #11` leaked `closes [#11]` into CHANGELOG.md. Commit text no longer reaches the CHANGELOG, since `tools/changes.js` renders notes from change fragments whose `issues` and `prs` fields accept only positive integers. GitHub still links every `#N` in commit messages and PR bodies, so a `#N` there must be a real same-repo issue or PR number (`Fixes #NNN` per CONTRIBUTING.md). Write acceptance criteria and stories as `AC 3` and `Story 3.2`, never `AC#3` or `closes #3`. The rule covers ids a plan invents for unfiled items: on 2026-09-30 the v3 step-4 planner numbered three pre-release items #9001 to #9003, and a builder agent copied `#9001` into a commit message and a comment in `test/test-skf-audit-reindex-prose.py`. Give such items a word label or the tracking issue's real number (the rebuilt branch says "#556's pre-release fix"), and grep a branch built from such a plan for the placeholder numbers before pushing.
