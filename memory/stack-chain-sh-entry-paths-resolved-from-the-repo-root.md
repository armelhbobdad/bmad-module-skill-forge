---
created: "2026-11-05 09:24"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# stack-chain.sh entry paths resolved from the repo root

`_bmad-output/implementation-artifacts/stack-chain.sh` (gitignored) takes entries shaped `branch|patch|msg|body|spec|frag1,frag2`, runs `cd` to the repository root, then calls `git switch -q -c "$BR" "$BASE"`, `git apply --3way --index "$PATCH"` and `head -1 "$MSG"`; only SPEC is joined to the implementation-artifacts folder. `ship-stack.sh` also reads the body file from the root and writes its logs beside the msg file. A bare or scratchpad-relative patch, msg or body name therefore fails, as on 2026-11-05 with `error: can't open patch 'final-gate600.patch': No such file or directory` and `FAILED: apply final-gate600.patch`, after the branch was already created. Pass absolute paths for patch, msg and body (fragments stay repo-relative `changes/*.yaml` paths). Before retrying, drop the empty branch with `git switch -q main && git branch -D <branch>`; nothing reached GitHub.
