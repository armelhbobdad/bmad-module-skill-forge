---
created: "2026-09-21 20:14"
session: "f71394da-c254-432d-8ee7-d91d9c8ba833"
---

# Memory changes get their own commits

A commit touches either the memory store (`memory/`, `MEMORY.md`, `.iwe/`) or the project's code, docs and tooling — never both. The user's rule, stated 2026-09-21: "all related memory should be committed in an isolated commit (we should never have a commit with both memory files and features files)." Memory commits record what the project *remembers*; feature commits change what it *does*. Keeping them apart means `git log` and `git blame` on `src/`, `docs/` and `tools/` never show note churn, a memory commit can be reverted or cherry-picked without touching behaviour, and code review stays focused on code. In practice: stage the memory paths on their own (`git add memory/ MEMORY.md .iwe/`), commit them with the `chore(memory):` prefix, and when a feature session also produced notes, make the notes a second commit — same branch or PR is fine, same commit is not.
