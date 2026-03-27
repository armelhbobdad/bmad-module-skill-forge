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

## context-snippet.md Format (Vercel-Aligned)

Indexed format targeting ~80-120 tokens per skill:

```markdown
[{skill_name} v{version}]|root: skills/{skill_name}/
|IMPORTANT: {skill_name} v{version} — read SKILL.md before writing {skill_name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top-5 exports with () for functions}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

## metadata.json Format

```json
{
  "name": "{skill_name}",
  "version": "{source-version or 1.0.0}",
  "description": "{brief description of the skill}",
  "skill_type": "single",
  "source_authority": "community",
  "source_repo": "{repo_url}",
  "source_root": "{resolved_source_path}",
  "source_commit": "{commit_sha_if_available}",
  "source_package": "{package_name}",
  "language": "{language}",
  "generated_by": "quick-skill",
  "generation_date": "{date}",
  "confidence_tier": "Quick",
  "spec_version": "1.3",
  "exports": ["{export_1}", "{export_2}"],
  "confidence_distribution": {
    "t1": 0,
    "t1_low": "{exports_count (integer, not string)}",
    "t2": 0,
    "t3": 0
  },
  "tool_versions": {
    "ast_grep": null,
    "qmd": null,
    "skf": "{skf_version}"
  },
  "stats": {
    "exports_documented": "{number}",
    "exports_public_api": "{number}",
    "exports_internal": 0,
    "exports_total": "{number}",
    "public_api_coverage": 1.0,
    "total_coverage": 1.0,
    "scripts_count": 0,
    "assets_count": 0
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```
