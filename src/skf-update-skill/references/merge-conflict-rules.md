---
type: static-reference
---

# Merge Conflict Rules

> Change-category actions and the merge priority order (deleted → moved → renamed → modified → new, plus the gap-driven priorities) are specified authoritatively in `merge.md` §3. This reference carries only the one thing §3 does not: the conflict-resolution strategy table below.

## Conflict Resolution Strategies

| Strategy     | When                                | Action                                    |
|--------------|-------------------------------------|-------------------------------------------|
| Auto-resolve | No [MANUAL] conflicts, clean merge  | Proceed without user input                |
| User-resolve | [MANUAL] conflicts detected         | Halt, present conflicts, require decision |
| Abort        | Critical structural incompatibility | Stop workflow, recommend full re-creation |
