---
created: "2026-09-27 22:15"
session: "c33c9199-5464-4490-bac5-d3d511b89070"
---

# Autosquash conflicts when a fixup moves ahead of a commit built in parallel

When commit groups are implemented in parallel worktrees and applied in order (G1, then G2), a later `git commit --fixup=<G1>` is written against a tree that already holds G2's edits. `git rebase --autosquash` then replays that fixup before G2 and stops with `CONFLICT (content)` wherever G2 touched the same lines (on the #500-#506 branch: `docs/troubleshooting.md`, `test/test-skf-ownership-gates.py`, `skf-skill-inventory.py`, `test/test-skf-skill-inventory.py`). Resolving by hand is error-prone. The reliable resolution for each conflicted file is its pre-rebase final version with the diffs of every commit that replays after this point reversed, newest first (`git show <old-head>:<file>`, then `git apply -R` of `git diff C^ C -- <file>` for each later C). When the stop is at the fixup itself, the file is the fixup's content minus the dependent group's additions. Then `git add` and `GIT_EDITOR=true git rebase --continue`. Check the rewrite by comparing `git rev-parse HEAD^{tree}` before and after the rebase (it must be identical), and run the Python suite at each rewritten commit.
