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

1. **Never modify content between [MANUAL] markers** — treat as immutable
2. **Preserve marker positions** — if the surrounding generated content moves, the [MANUAL] block moves with its logical parent section
3. **Orphan detection** — if the parent section is deleted (export removed), flag as WARNING and present to user
4. **Multiple [MANUAL] blocks** — a single SKILL.md may have multiple [MANUAL] sections; preserve all
5. **Stack skill [MANUAL] blocks** — [MANUAL] markers can appear in any output file (SKILL.md, references/*.md, integrations/*.md); preserve across all files
6. **Nested [MANUAL] forbidden** — [MANUAL] blocks cannot be nested; if detected, flag as ERROR

### Conflict Types

| Conflict                                       | Severity | Resolution                                            |
|------------------------------------------------|----------|-------------------------------------------------------|
| Regenerated content overlaps [MANUAL] position | HIGH     | Present both versions, user chooses                   |
| Parent section deleted                         | WARNING  | Flag orphaned [MANUAL], user decides keep/remove      |
| [MANUAL] references deleted export             | MEDIUM   | Flag stale reference, suggest update                  |
| New export inserted adjacent to [MANUAL]       | LOW      | Auto-resolve: place new content before [MANUAL] block |

### Preservation Algorithm

1. Extract all [MANUAL] blocks with their section-name identifiers
2. Map each block to its parent section (by heading hierarchy)
3. Perform merge on generated content only
4. Re-insert [MANUAL] blocks at their mapped positions
5. If position conflict: halt and present to user
6. If clean insert: auto-place and continue
