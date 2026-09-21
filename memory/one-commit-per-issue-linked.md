---
created: "2026-04-10 22:35"
session: "b944b768-4c95-4b30-9642-c834ee3be822"
source: claude-mem
source_table: observations
source_ids: [5293, 5681]
---

# One commit per GitHub issue, linked and regression-reviewed

When fixing a batch of GitHub issues or improvement-queue findings, organize the work as one conventional commit per issue where applicable, each holding every file that fixes that issue, with a `Fixes #N` / `Refs #N` / `Closes #N` trailer so the issue closes automatically (CONTRIBUTING.md § Workflow for Changes makes the commit trailer optional; the user wants it). Cross-cutting consistency follow-ups go in a separate `chore:` commit so issue commits stay surgical. Review the whole change set for breaking changes, missed impacts and regressions before pushing and opening the PR against `main`. Use same-repo issue numbers only, never `_bmad-output/todo/` ids. User: "Organize the commits the smartest way (e.g: one commit per issue if applicable). Link each commit to the related issue(s). Review all the changes for any breaking changes, or missing impacts/bugs/regressions and ect..."
