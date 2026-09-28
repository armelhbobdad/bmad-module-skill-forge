---
created: "2026-09-28 21:22"
session: "8eea3fd3-586c-4692-a141-255bda459d73"
---

# Subagents running pytest-cov leave an unignored .coverage at the repo root

A review subagent that measures branch coverage with pytest-cov writes its data file, `.coverage`, to the repository root, and leaves it there. On 2026-09-28 the verification-gap reviewer of a `bmad-build` run did this while probing `test/test-skf-verify-provenance-completeness.py` for untested branches, leaving a 143 KB `.coverage`. `.gitignore` lists `coverage/` but not `.coverage` (`git check-ignore .coverage` prints nothing), so `git status --short` shows `?? .coverage` and a broad `git add` would commit it. After any subagent or review run that may have measured coverage, check `git status --short` for `?? .coverage` and delete the file before staging; never commit it.
