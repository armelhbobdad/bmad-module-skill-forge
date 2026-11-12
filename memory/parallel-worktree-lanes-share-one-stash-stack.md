---
created: "2026-11-11 19:37"
session: "72e9f28d-d28a-41b5-917c-b01a8cd78569"
---

# Parallel worktree lanes share one git stash stack

Every worktree of a repository shares one `refs/stash`, so a `git stash` run in `.claude/worktrees/<lane>` lands on the same stack the main checkout and every other lane see, and a `git stash pop` in one lane can take another lane's changes. On 2026-11-11, with ten bmad-build lanes running in parallel worktrees, subagents ran `git stash -q && npm run -s docs:validate-drift; git stash pop -q` to get a baseline. The lanes were stopped, `git stash list` was empty (nothing had crossed over), and they were resumed with a rule appended to every agent prompt: never run `git stash` in any form; to show a test fails without a fix, copy the changed files aside, restore each with `git show HEAD:<path>`, then copy them back; for a baseline comparison, run the tests in a pristine export (`git archive HEAD | tar -x -C <dir>`). `npx lint-staged` also pushes a transient `stash@{0}: lint-staged automatic backup` onto that shared stack during each commit and drops it when it finishes (`--no-stash` skips it). Put the no-stash rule in the brief of any agents that work in parallel worktrees, and watch `git -C <main checkout> stash list` while they run.
