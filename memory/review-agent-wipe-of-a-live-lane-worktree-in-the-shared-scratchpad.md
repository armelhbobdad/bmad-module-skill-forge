---
created: "2026-10-12 12:47"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# Review agent wipe of a live lane worktree in the shared scratchpad

Subagents share the parent session's scratchpad, so a reviewer told to probe in a scratch copy can pick the path of a live bmad-build lane worktree kept there as `$S/wt<issue>`. On 2026-10-12 the #733 blind-hunter reviewer ran `rm -rf` on `$S/wt733` and then `git init` there, leaving 408 tracked files and `node_modules` gone and `wt733/.git` an empty repo on `master` that a `git add -A && git commit` would have used. The work survived in the registered gitdir `.git/worktrees/wt733`: back up the changed files, `rm -rf wt733/.git`, write a `.git` file reading `gitdir: <main checkout>/.git/worktrees/wt733`, run `git ls-files --deleted -z | xargs -0 git checkout HEAD --` and `npm ci`, then diff against the backup. Every reviewer or probe prompt sent beside live lanes must forbid writing to, deleting or running `git init` in any lane worktree or the main checkout. Give each reviewer its own new folder (`mktemp -d`, or per-role names like `rev-<label>-blind`, `-edge`, `-gap`; two reviewers once shared one and collided), and before committing in a lane check that its `.git` is still a `gitdir:` file.
