# Stack Skill Template

## SKILL.md Section Structure

```markdown
---
name: {stack_name}
description: >
  Stack skill for {project_name} — {lib_count} libraries with
  {integration_count} integration patterns. Use when working with
  this project's technology stack.
---

# {project_name} Stack Skill

> {lib_count} libraries | {integration_count} integration patterns | Forge tier: {tier}

## Integration Patterns

### Cross-Cutting Patterns
[Patterns that span 3+ libraries — middleware chains, shared config, etc.]

### Library Pair Integrations
[For each detected integration pair:]
#### {LibraryA} + {LibraryB}
**Type:** {pattern_type}
**Pattern:** {description}
**Key files:** {file_list}
**Confidence:** {T1/T1-low/T2/T3}

## Library Reference Index

| Library | Imports | Key Exports | Confidence | Reference |
|---------|---------|-------------|------------|-----------|
| {name} | {count} | {top_exports} | {tier} | [ref](references/{name}.md) |

## Per-Library Summaries

### {library_name}
**Role in stack:** {one-line description of what this library does in this project}
**Key exports used:** {comma-separated list}
**Usage pattern:** {brief pattern description}
**Confidence:** {T1/T1-low/T2/T3}

## Conventions

[Project-specific conventions for library usage:]
- {convention_1}
- {convention_2}
```

## Sizing Guidance for Large Stacks

A stack capstone grows monotonically as patterns and libraries are added, so a
mature stack eventually pushes SKILL.md past skill-check's `body.max_lines`
budget (default **500**) and/or the `description` past 1024 chars. Pre-empt both
ceilings at compile time:

- **Catalog placement.** The `Library Reference Index` table and `Per-Library
  Summaries` are the largest, most reference-like sections. For a **large stack**
  (heuristic: **> 6 libraries OR > 6 integration patterns**, the point at which
  the inline catalog crowds the 500-line budget), author both into
  `references/stack-catalog.md` and leave only an inline pointer in SKILL.md (see
  below). For a **small stack**, keep them inline — inline passive context yields
  higher task accuracy than on-demand retrieval, and small stacks fit comfortably.
  Integration Patterns and Conventions stay inline regardless (Tier 1, load-bearing).
  Whenever the catalog moves into `references/stack-catalog.md`, at compile time
  or in a later body-size split, its Reference links become file-relative,
  `[ref]({name}.md)`, because a link resolves from the file that holds it (see
  "references/stack-catalog.md Structure" below).
- **Inline pointer form** (replaces the two sections above when extracted):

  ```markdown
  ## Library Catalog

  {lib_count} libraries indexed in [references/stack-catalog.md](references/stack-catalog.md) —
  reference-index table + per-library summaries. Load it for a specific library's exports or role.
  ```

- **Description cap.** Keep `description` ≤ 1024 chars. Do NOT enumerate every
  library by name; the generic "{lib_count} libraries with {integration_count}
  integration patterns" form already scales. If a per-library parenthetical is
  used, cap it to the top libraries by import/export count with a `+{N} more`
  suffix — the full list lives in `metadata.json` `libraries[]` and the catalog.

## context-snippet.md Format (Vercel-Aligned)

Indexed format targeting ~80-120 tokens per stack:

```markdown
[{stack_name} v{version}]|root: skills/{stack_name}/
|IMPORTANT: {stack_name} — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {1-2 most critical integration pitfalls}
```

## references/stack-catalog.md Structure

Written **only for large stacks** (see Sizing Guidance) when the catalog is
extracted out of SKILL.md. Holds the two sections from the inline form with
their links rewritten: a link resolves from the file that holds it, and this
file sits in `references/` beside the per-library files, so a link to one of
them is `{name}.md` (the Reference column's `[ref]({name}.md)`). The inline
form's `references/{name}.md` would resolve to `references/references/{name}.md`
from here.

```markdown
# {project_name} Stack — Library Catalog

> Reference index + per-library summaries extracted from SKILL.md to keep the
> capstone under the body-size budget. See SKILL.md for integration patterns.

## Library Reference Index

| Library | Imports | Key Exports | Confidence | Reference |
|---------|---------|-------------|------------|-----------|
| {name} | {count} | {top_exports} | {tier} | [ref]({name}.md) |

## Per-Library Summaries

### {library_name}
**Role in stack:** {one-line description of what this library does in this project}
**Key exports used:** {comma-separated list}
**Usage pattern:** {brief pattern description}
**Confidence:** {T1/T1-low/T2/T3}
```

## references/{library}.md Structure

```markdown
# {library_name} Reference

**Version:** {version_from_manifest}
**Import count:** {count} files *(compose-mode: replace with **Export count:** {count} exports)*
**Confidence:** {T1/T1-low/T2/T3}

## Key Exports
[Top exports used in this project with signatures]

## Usage Patterns
[How this library is typically used in this codebase]

## Common Imports
[Most frequent import statements]
```

## references/integrations/{pair}.md Structure

```markdown
# {LibraryA} + {LibraryB} Integration

**Type:** {pattern_type}
**Co-import files:** {count}
**Confidence:** {T1/T1-low/T2/T3 [composed]}

## Integration Pattern
[Detailed description of how these libraries connect]

## Key Files
[Files demonstrating the integration with line references]

## Usage Convention
[How this integration is typically structured in the project]
```
