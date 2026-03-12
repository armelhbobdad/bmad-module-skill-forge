# Skill Template — Quick Skill Output

## SKILL.md Section Structure

The following sections should be populated in the generated SKILL.md. Best-effort — not all sections will have data for every skill.

### Required Sections

```markdown
---
name: {skill_name}
description: >
  {README-derived description, trigger-optimized for agent discovery.
  Include what the package does and when to use it.
  Mention what NOT to use it for if applicable.}
---

# {skill_name}

## Overview
- **Package:** {package_name}
- **Repository:** {repo_url}
- **Language:** {language}
- **Source Authority:** community
- **Generated:** {date}

## Description
{README-derived description of what the package does}

## Key Exports
{List of public exports with brief descriptions}

## Usage Patterns
{Common usage patterns extracted from README examples}
```

### Optional Sections (include when data available)

```markdown
## Configuration
{Configuration options if found in source}

## Dependencies
{Key dependencies from manifest file}

## Notes
{Any caveats, limitations, or observations about the extraction}
```

## context-snippet.md Format (ADR-L)

Two-line format targeting ~30 tokens per skill:

```markdown
{skill_name}: {top-5 exports as comma-separated list}
  → {skills_output_folder}/{skill_name}/SKILL.md
```

## metadata.json Format

```json
{
  "name": "{skill_name}",
  "version": "0.1.0",
  "source_authority": "community",
  "source_repo": "{repo_url}",
  "source_package": "{package_name}",
  "language": "{language}",
  "generated_by": "quick-skill",
  "generated_date": "{date}",
  "exports_count": {number},
  "confidence": "best-effort"
}
```
