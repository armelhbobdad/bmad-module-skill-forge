---
created: "2026-06-03 14:03"
session: "56051077-ffb7-41ac-a86a-8e9182d7c6a8"
source: claude-mem
source_table: observations
source_ids: [14591, 14592, 14593]
---

# Backticked Fixes trailer skips GitHub auto-close

GitHub only parses closing keywords (`Fixes`/`Closes`/`Resolves #N`) when they are bare text in the PR body; PR #429 had `Fixes #427` wrapped in backticks, so `closingIssuesReferences` stayed empty and issue #427 was still open after the PR merged to `main` (merge commit b17c41cf) until it was closed by hand with a comment citing the merge commit. `CONTRIBUTING.md` itself writes the trailer as code-formatted `` `Fixes #NNN` ``, which invites the mistake. After `gh pr create`, run `gh pr view <n> --json closingIssuesReferences` and expect a non-empty list; if it is empty, edit the body to the bare keyword before merging, or close the issue manually with the merge-commit reference. Closing keywords also fire only when the PR merges into the default branch (`main`). User: "issue 427 is still open after the previous merge. is it normal?"
