---
created: "2026-08-07 15:44"
session: "95454060-ebf4-49ae-b369-a3ec91666870"
source: claude-mem
source_table: observations
source_ids: [32160, 32161, 32165, 32167]
---

# Local branches mirror the remote; prune Entire checkpoint branches

The remote has exactly two branches, `main` and `entire/checkpoints/v1`, and the user's rule is that local branches match them: "we should only have 2 local branches that miror the remote ones." The Entire hooks wired in `.claude/settings.json` (strategy `manual-commit` in `.entire/settings.json`) keep creating local `entire/<short-sha>-e3b0c4` checkpoint branches whose commit subjects are the session's prompts; they are not feature branches, none is reachable from `entire/checkpoints/v1`, and they accumulate fast (144 were removed with `git branch -D` on 2026-08-07, and `entire/96d7188-e3b0c4` has since reappeared). Delete those with `git branch -D entire/<sha>-e3b0c4`; never delete `entire/checkpoints/v1`, which exists on the remote. `testing` and one other local non-Entire branch were left for the user to decide on. The manifest of deleted branch heads that the cleanup wrote outside the repo (`~/.claude/skf-branch-manifest-<sha>.txt`) no longer exists, so those deletions are unrecoverable now — do not count on it.
