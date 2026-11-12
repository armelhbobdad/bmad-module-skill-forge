---
created: "2026-11-05 02:12"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Detached HEAD after stack-chain.sh

`_bmad-output/implementation-artifacts/stack-chain.sh` (gitignored) ends with `git switch -q --detach "$BASE"`, so after a chain, or a queue script that wraps it, the main checkout sits on a detached HEAD at the last PR's head while the local `fix/...` branches keep their old heads. On 2026-11-05 a follow-up `Changelog: none` commit for #873 landed there, and `git push origin fix/annotation-contradicted-note` sent nothing: `git ls-remote` still showed 946397c0 and `git status` said `HEAD detached from 946397c0`. Run `git branch --show-current` before a follow-up commit, and push with `git push origin HEAD:<branch>` or switch to the branch first. Then restart the merge wait with the new head SHA, because `ship-merge.sh` waits for the PR's `headRefOid` to equal the SHA it was given and never merges a newer head.
