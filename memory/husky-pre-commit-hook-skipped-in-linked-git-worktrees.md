---
created: "2026-10-01 02:18"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Husky pre-commit hook skipped in linked git worktrees

`core.hooksPath` is the relative `.husky/_`, which git resolves inside each worktree, and that folder is untracked (`.husky/_/.gitignore` is `*`; `git ls-files .husky` lists only `.husky/pre-commit`) and generated only by `husky` through `"prepare": "husky || exit 0"` on `npm install`. A `git worktree add` checkout (scratch worktrees, `.claude/worktrees/<lane>`) therefore has no `.husky/_`, and every `git commit` there silently skips lint-staged and `npm test`, with no error and no `--no-verify`. A lane whose `node_modules` is a symlink to the main checkout's never runs `npm install` to create it, and CONTRIBUTING.md says the hook runs automatically without mentioning worktrees. It hit scratch worktrees in the v3.0.0 work and every lane of the 7.0.0 series, where #893's PR body had to be corrected to say `npm test` was "run by hand in the worktree". Before committing in a worktree, run the gate yourself (`npm run quality`, `npm run changes:pr`) with its own `TMPDIR`, or run `npm install` there; never read a fast, silent commit as a passed hook, and never write in a PR that the hook ran.
