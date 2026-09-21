---
created: "2026-08-07 15:44"
session: "95454060-ebf4-49ae-b369-a3ec91666870"
source: claude-mem
source_table: observations
source_ids: [32160, 32161, 32165, 32167]
---

# Local branches mirror the remote

The user's rule for this checkout is that local branches match the remote's: "we should only have 2 local branches that miror the remote ones" (said on 2026-08-07, when the remote held `main` and the since-deleted `entire/checkpoints/v1`; as of 2026-09-21 the remote holds only `main`). A local branch with no remote counterpart is either in-progress work or leftover — after `git fetch --prune`, list them with `git branch -vv` and delete the leftovers with `git branch -D <name>`. `testing` and `pitch-insitoo` are the user's own and were left for them to decide. A manifest of previously deleted branch heads written to `~/.claude/skf-branch-manifest-<sha>.txt` no longer exists, so those deletions are unrecoverable — do not count on it.
