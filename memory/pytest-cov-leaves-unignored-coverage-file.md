---
created: "2026-09-28 21:22"
session: "8eea3fd3-586c-4692-a141-255bda459d73"
---

# Subagents running pytest-cov leave an unignored .coverage at the repo root

A review subagent that measures branch coverage with pytest-cov writes its data file, `.coverage`, to the root of the checkout or worktree it runs in and leaves it there. A `bmad-build` verification-gap reviewer did so on 2026-09-28 while probing `test/test-skf-verify-provenance-completeness.py`. `.gitignore` lists `coverage/` but not `.coverage` (`git check-ignore .coverage` prints nothing), so `git status --short` shows `?? .coverage` and a broad `git add` commits it. Snapshots are not exempt: on 2026-11-03 a 237,568-byte `.coverage` left in a bmad-build worktree was captured by `git add -A && git stash create`, and its index commit 67a33a0b (`index on fix/gap-driven-signatures-from-records`) became the base of four dependent worktrees, whose diffs then showed `.coverage | Bin 237568 -> 0 bytes` once the file was removed. After any subagent or review run that may have measured coverage, check `git status --short` for `?? .coverage` and run `rm -f <worktree>/.coverage` before any staging, including a `git add -A` made only to snapshot a tree or build a base commit; never commit it.
