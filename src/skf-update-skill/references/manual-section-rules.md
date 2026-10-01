---
type: static-reference
---

# [MANUAL] Section Rules

## Detection Pattern

[MANUAL] sections are developer-authored content blocks within generated SKILL.md files that must survive regeneration.

### Identification

A [MANUAL] section is delimited by markers in the SKILL.md:

```markdown
<!-- [MANUAL:section-name] -->
Developer-authored content here.
This content was added by the developer after skill generation.
It must be preserved during any update operation.
<!-- [/MANUAL:section-name] -->
```

### Rules

1. **Never delete or modify content between [MANUAL] markers without the user's merge §4 [R]emove or [E]dit decision**: treat it as immutable otherwise. The decision is recorded in the run's manual plan, and the post-merge check verifies the blocks against the inventory that plan amends
2. **Preserve marker positions**: if the surrounding generated content moves, the [MANUAL] block moves with its logical parent section
3. **Multiple [MANUAL] blocks**: a single SKILL.md may have multiple [MANUAL] sections; preserve all
4. **Nested [MANUAL] forbidden**: [MANUAL] blocks cannot be nested; if detected, flag as ERROR

merge.md §3 and §4 name the conflicts (ORPHAN, STALE_REFERENCE, POSITION) and how each is resolved.
