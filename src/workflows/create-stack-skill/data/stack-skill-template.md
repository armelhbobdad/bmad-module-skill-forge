# Stack Skill Template

## SKILL.md Section Structure

```markdown
---
name: {project_name}-stack
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
**Confidence:** {T1/T1-low/T2}

## Library Reference Index

| Library | Imports | Key Exports | Confidence | Reference |
|---------|---------|-------------|------------|-----------|
| {name} | {count} | {top_exports} | {tier} | [ref](./references/{name}.md) |

## Per-Library Summaries

### {library_name}
**Role in stack:** {one-line description of what this library does in this project}
**Key exports used:** {comma-separated list}
**Usage pattern:** {brief pattern description}
**Confidence:** {T1/T1-low/T2}

## Conventions

[Project-specific conventions for library usage:]
- {convention_1}
- {convention_2}
```

## context-snippet.md Format (ADR-L)

Two-line format per library, targeting ~30 tokens per entry:

```markdown
**{library}** ({import_count} imports): {top_3_exports}
  → integrates with: {comma-separated integration partners}
```

## metadata.json Structure

```json
{
  "skill_type": "stack",
  "skill_name": "{project}-stack",
  "version": "1.0.0",
  "created": "{date}",
  "forge_tier": "{Quick|Forge|Deep}",
  "library_count": 0,
  "integration_count": 0,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "confidence_distribution": {
    "T1": 0,
    "T1-low": 0,
    "T2": 0
  }
}
```

## references/{library}.md Structure

```markdown
# {library_name} Reference

**Version:** {version_from_manifest}
**Import count:** {count} files
**Confidence:** {T1/T1-low/T2}

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
**Confidence:** {T1/T1-low}

## Integration Pattern
[Detailed description of how these libraries connect]

## Key Files
[Files demonstrating the integration with line references]

## Usage Convention
[How this integration is typically structured in the project]
```
