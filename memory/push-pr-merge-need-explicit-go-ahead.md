---
created: "2026-05-18 17:52"
session: "900827df-c0f7-4954-b899-977f414b6435"
source: claude-mem
source_table: both
source_ids: [10105, 10290, 14687, 14746, 14857]
---

# Push, PR and merge each need the user's explicit go-ahead

Local branch creation and commits may be prepared autonomously, but `git push`, `gh pr create` and merging each require the user's explicit instruction scoped to exactly that step: push approval is not PR approval, and PR approval is not merge approval. The user merges PRs themselves in the GitHub UI and reports back with a bare "merged"; the assistant never merges. This holds even inside an autonomous `/goal` run — "/goal create a new branch off main, then fix all findings ... never push or open a PR without my authorization." — and on release prep: "commit this branch and open the PR now. I will manually merge it before you proceed with the release". Nothing in the repository records this (there is no `CLAUDE.md`; `CONTRIBUTING.md` only says branch from `main` and run `npm run quality` before pushing), so wait for the words "push" / "open the PR" before doing either.
