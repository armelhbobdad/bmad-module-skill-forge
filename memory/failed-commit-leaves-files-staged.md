---
created: "2026-09-28 15:25"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# A failed commit leaves its files staged for the next commit

The pre-commit hook runs the full `npm test`, and `test:python` fetches packages through `uv run --with`, so a commit can fail on the network rather than on a test: on 2026-09-28 it stopped with `Failed to fetch: https://pypi.org/simple/jsonschema/` (`operation timed out`) and `husky - pre-commit script failed (code 2)`. A failed commit unstages nothing, and the next `git add <other paths> && git commit` swept the still-staged `src/skf-create-stack-skill/references/validate.md` into a `chore(memory):` commit, breaking the rule that memory changes get their own commits. Check each commit's exit status before starting the next one, and run `git diff --cached --stat` before adding the next set of paths. If a stray file was swept in and the commit is not pushed, `git reset --soft HEAD~1` followed by `git restore --staged <paths>` splits it back apart; a failed commit caused by the network usually passes on a plain retry.
