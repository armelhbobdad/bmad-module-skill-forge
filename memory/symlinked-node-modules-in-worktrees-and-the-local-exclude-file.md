---
created: "2026-09-30 12:05"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Symlinked node_modules in worktrees and the local exclude file

A new worktree (`.claude/worktrees/<lane>` or any `git worktree add`) has no `node_modules`, so `npm test` and the husky pre-commit hook fail there until `npm ci --ignore-scripts` runs or the main checkout's `node_modules` and `website/node_modules` are symlinked in. The committed `.gitignore` entry `node_modules/` matches only real directories, never a symlink; what hides those links here is the local `.git/info/exclude` pair `/node_modules` and `/website/node_modules`, shared by every worktree through the common git dir but absent from a fresh clone. Without it the links show as `?? node_modules` and a broad `git add -A` commits them. For another repository's worktree, add the lines to that repository's exclude, but `git -C <repo> rev-parse --git-common-dir` prints a relative `.git` resolved against the shell's cwd, which on 2026-09-30 wrote them into SKF's file instead. Guard the link with `[ -e node_modules ] || ln -s <main>/node_modules node_modules`, because `ln -s` where `node_modules` already exists creates the self-referencing `node_modules/node_modules` link the main checkout still carries. Symlinks are enough for `npm test`, but not for `npm run docs:build`.
