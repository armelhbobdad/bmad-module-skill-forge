---
created: "2026-05-26 15:09"
session: "d3f0694b-da9a-40e4-9a86-7baaa7e3f97d"
source: claude-mem
source_table: both
source_ids: [13266, 13267, 14077]
---

# No bmad tracking terminology in commit messages

Commit subjects and bodies, whether written by hand or produced by automation such as the story-automator's `commit-story` command, must never mention gitignored files, internal bmad files under `_bmad-output/`, or bmad tracking vocabulary like "story 1.1", "epic 1", "retro". Write the public conventional-commit form with the component as scope, e.g. `feat(skf-doc-detect): add doc detection chain module`, not `feat(story-1.2): Doc detection chain shared module`, and rewrite automation-produced commits (rebase or filter-branch, tree SHA unchanged) before pushing. The user's words: "Other automations should follow the existing commit message convention (never mention gitignored files, internal bmad related files, bmad keyword like story 1.1, epic 1, retro, etc..)." `CONTRIBUTING.md:49-59` documents scoped conventional commits and bans `_bmad-output/todo/` IDs but says nothing about story/epic/retro keywords, and older history such as `chore(release): ... (Story 6.3) (#224)` predates the rule and is not the style to match.
