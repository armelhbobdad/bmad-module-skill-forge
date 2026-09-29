---
created: "2026-04-23 02:52"
session: "a881dc92-dfb0-4d57-acfa-1ee2667e8c0b"
source: claude-mem
source_table: observations
source_ids: [6891, 6911, 6913, 6923]
---

# Bare #N tokens in commits become issue links

Until #578, release.yaml's `Update CHANGELOG.md` step ran `npx conventional-changelog-cli -p conventionalcommits`, which linked every `#N` in commit subjects and bodies: `satisfy AC#3` became a link to issue 3, `mentions AC#4` a cross-repo link to a repository named `AC`, and Story 3.2's `closes #11` leaked `closes [#11]` into CHANGELOG.md. Commit text no longer reaches the CHANGELOG: `tools/changes.js` renders the notes from change fragments, and a fragment's `issues` and `prs` fields accept only positive integers. GitHub itself still links every `#N` in commit messages and PR bodies, so a `#N` there may only ever be a real same-repo issue or PR number (`Fixes #NNN` per CONTRIBUTING.md); acceptance criteria and story numbers are written `AC 3` and `Story 3.2`, never `AC#3` or `closes #3`.
