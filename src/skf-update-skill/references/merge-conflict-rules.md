---
type: static-reference
---

# Merge Conflict Rules

> Change-category actions and the merge priority order (deleted → moved → renamed → modified → new, plus the gap-driven priorities) are specified authoritatively in `merge.md` §3. This reference carries only the two things §3 does not: the conflict-resolution strategy table below and the inert stack-skill merge rules.

## Stack Skill Merge Rules — inert

init.md §2's Stack Skill Guard redirects every stack to `skf-create-stack-skill` before step 2, so surgical update never reaches these rules. The per-file stack merge scaffolding (SKILL.md via `merge.md` §3, per-`references/{library}.md` and per-integration merges, full `metadata.json`/`context-snippet.md` regeneration) is recoverable from git history if that guard is ever relaxed.

## Conflict Resolution Strategies

| Strategy     | When                                | Action                                    |
|--------------|-------------------------------------|-------------------------------------------|
| Auto-resolve | No [MANUAL] conflicts, clean merge  | Proceed without user input                |
| User-resolve | [MANUAL] conflicts detected         | Halt, present conflicts, require decision |
| Abort        | Critical structural incompatibility | Stop workflow, recommend full re-creation |
