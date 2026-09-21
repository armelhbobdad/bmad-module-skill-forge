---
created: "2026-04-23 02:52"
session: "a881dc92-dfb0-4d57-acfa-1ee2667e8c0b"
source: claude-mem
source_table: observations
source_ids: [6891, 6911, 6913, 6923]
---

# Bare #N tokens in commits become CHANGELOG issue links

release.yaml's `Update CHANGELOG.md` step (line 163) runs `npx conventional-changelog-cli -p conventionalcommits -i CHANGELOG.md -s`, and that preset linkifies every `#N` in a commit. Verified against this repo's node_modules: the subject `feat: satisfy AC#3` renders as `satisfy AC[#3](…/issues/3)`, a body line `mentions AC#4` renders as `closes [AC#4](https://github.com/<owner>/AC/issues/4)` (parsed as a cross-repo reference with repository `AC`), and `closes #11` for a story number links issue 11 — which is how Story 3.2's commits leaked `closes [#11]/[#12]` into CHANGELOG.md. The release guard at release.yaml:205 (`grep -iE '(closes|fixes|resolves) \[#[^0-9]'`) only catches `[#<non-digit>` and would not catch `[AC#4]`. So a `#N` in a commit subject or body may only ever be a real same-repo issue number: `Fixes #NNN` per CONTRIBUTING.md:59 is correct and renders as intended (CHANGELOG.md:30-36 for v2.1.0), while acceptance criteria and story numbers are written `AC 3` and `Story 3.2`, never `AC#3` or `closes #3`.
