---
created: "2026-11-06 20:54"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# One closing keyword per issue in a PR body

GitHub links only the first issue after a closing keyword: PR #896's body "Closes #886 and #887." set `closingIssuesReferences` to [886] alone, so #887 stayed open after the merge and was closed by hand on 2026-11-06. A keyword per issue works: PR #939's "Closes #905. Closes #906." closed both. This repository often fixes two to four issues in one PR, and CONTRIBUTING.md only says to reference issues with `Fixes #NNN`. So write a separate `Closes #N` (or `Fixes #N`) for every issue, and before merging check that `gh pr view <n> --json closingIssuesReferences` lists them all. Related: [Backticked Fixes trailer skips GitHub auto-close](backticked-fixes-trailer-skips-auto-close.md).
