---
created: "2026-11-04 20:41"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Parallel ship scripts sharing the main checkout

The gitignored ship scripts under `_bmad-output/implementation-artifacts/` (`ship-stack.sh`, `stack-chain.sh`, `ship-pr.sh`) all `cd` into the one main checkout and commit there through the full-suite pre-commit hook, so two running at once share HEAD. On 2026-11-04 a merge script's `git pull` moved HEAD while `stack-chain.sh` had `ship-stack.sh` mid-hook on its own branch. The commit failed with `fatal: cannot lock ref 'HEAD': is at <sha> but expected <sha>` and `FAILED: no handoff for fix/list-item-declaration-line`, leaving its changes staged. `ship-pr.sh` ends with `git switch -q main && git pull -q --ff-only`, so it must not overlap another ship that uses the checkout. Run one checkout-using ship at a time, and refresh local `main` with `git fetch origin main:main` while another branch is checked out, which leaves the checkout alone. Only `ship-merge.sh` and `ship-after.sh`, which work through `gh` and touch no local checkout, are safe to run in parallel.
