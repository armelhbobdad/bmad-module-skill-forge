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

## context-snippet.md Format (Vercel-Aligned)

Indexed format targeting ~80-120 tokens per stack:

```markdown
[{project}-stack v{version}]|root: skills/{project}-stack/
|IMPORTANT: {project}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {1-2 most critical integration pitfalls}
```

## metadata.json Structure

```json
{
  "skill_type": "stack",
  "name": "{project}-stack",
  "version": "1.0.0",
  "generation_date": "{ISO-8601}",
  "confidence_tier": "{Quick|Forge|Forge+|Deep}",
  "spec_version": "1.3",
  "source_authority": "{official|community|internal}",
  "generated_by": "create-stack-skill",
  "exports": [],
  "library_count": 0,
  "integration_count": 0,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "language": "{primary language or list of languages from constituent skills}",
  "ast_node_count": "{number-or-omitted-if-no-ast}",
  "confidence_distribution": {
    "t1": 0,
    "t1_low": 0,
    "t2": 0,
    "t3": 0
  },
  "tool_versions": {
    "ast_grep": "{version-or-null}",
    "qmd": "{version-or-null}",
    "skf": "{skf_version}"
  },
  "stats": {
    "exports_documented": 0,
    "exports_public_api": 0,
    "exports_internal": 0,
    "exports_total": 0,
    "public_api_coverage": 0.0,
    "total_coverage": 0.0,
    "scripts_count": 0,
    "assets_count": 0
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

## references/{library}.md Structure

```markdown
# {library_name} Reference

**Version:** {version_from_manifest}
**Import count:** {count} files *(compose-mode: replace with **Export count:** {count} exports)*
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
**Confidence:** {T1/T1-low/T2 [composed]}

## Integration Pattern
[Detailed description of how these libraries connect]

## Key Files
[Files demonstrating the integration with line references]

## Usage Convention
[How this integration is typically structured in the project]
```
