# Skill Brief Schema

## Required Fields

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | string | Kebab-case skill name | Must match `[a-z0-9-]+` |
| version | string | Semantic version | Must match `X.Y.Z` pattern. Auto-detect from source (see Version Detection below), fall back to "1.0.0" |
| source_repo | string | GitHub URL or local path | Must be accessible |
| language | string | Primary programming language | Must be detected or user-specified |
| scope | object | Inclusion/exclusion boundaries | Must have type + at least one pattern |
| description | string | What this skill covers | 1-3 sentences |
| forge_tier | string | Compilation tier | One of: quick, forge, deep |
| created | string | Creation date | ISO date format |
| created_by | string | User who created the brief | From config user_name |

## Optional Fields

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| source_type | string | Source mode: `source` or `docs-only` | Default `source`. When `docs-only`: `source_repo` optional, `doc_urls` required |
| doc_urls | array | Documentation URLs for T3 content | Each entry: `{url, label}`. Required when `source_type: "docs-only"` |

When `source_type: "docs-only"`:
- `source_repo` becomes optional (set to doc site URL for reference)
- `doc_urls` must have at least one entry
- `source_authority` is forced to `community` (T3 external documentation cannot be `official`)
- All extracted content gets `[EXT:{url}]` citations

## Version Detection

During brief creation, attempt to auto-detect the source version before defaulting to `"1.0.0"`. Check the first matching file in the source:

- **Python:** `pyproject.toml` (`[project] version`), `setup.py` (`version=`), or `__version__` in `__init__.py`
- **JavaScript/TypeScript:** `package.json` (`"version"`)
- **Rust:** `Cargo.toml` (`[package] version`)
- **Go:** version tag from `go.mod` or latest git tag

If the source is a remote GitHub repo, use `gh api repos/{owner}/{repo}/contents/{file}` to read the version file. If the source is local, read the file directly.

If detection succeeds, use the detected version. If it fails or returns a non-semver value, fall back to `"1.0.0"`.

The create-skill workflow (step-03-extract) also performs version reconciliation at extraction time — if the source version has changed since the brief was created, the extraction step warns and uses the source version.

## Scope Object Structure

```yaml
scope:
  type: full-library | specific-modules | public-api
  include:
    - "src/**/*.ts"           # Glob patterns for included files/directories
  exclude:
    - "**/*.test.*"           # Glob patterns for excluded files
    - "**/node_modules/**"
  notes: "Optional notes about scope decisions"
```

## YAML Template

```yaml
---
name: "{skill-name}"
version: "{detected-version or 1.0.0}"  # Auto-detect from source, fall back to 1.0.0
source_type: "source"                    # "source" (default) or "docs-only"
source_repo: "{github-url-or-local-path}"
language: "{detected-language}"
description: "{brief-description}"
forge_tier: "{quick|forge|deep}"
created: "{date}"
created_by: "{user_name}"
scope:
  type: "{full-library|specific-modules|public-api|docs-only}"
  include:
    - "{pattern}"
  exclude:
    - "{pattern}"
  notes: "{optional-scope-notes}"
# Optional: documentation URLs for T3 content (required when source_type: "docs-only")
# doc_urls:
#   - url: "https://docs.example.com/api"
#     label: "API Reference"
---
```

## Human-Readable Presentation Format

When presenting the brief for confirmation (step 04), display as:

```
Skill Brief: {name}
====================

Target:      {source_repo}
Language:    {language}
Forge Tier:  {forge_tier}
Description: {description}

Scope: {scope.type}
  Include: {scope.include patterns, one per line}
  Exclude: {scope.exclude patterns, one per line}
  Notes:   {scope.notes}

Version:    {version}
Created:    {created}
Created by: {created_by}
```

## Validation Rules

1. `name` must be unique within {forge_data_folder}
2. `source_repo` must be accessible (gh api for GitHub, path exists for local)
3. `language` must be a recognized programming language
4. `scope.type` must be one of the three defined types
5. `scope.include` must have at least one pattern
6. `forge_tier` must match the tier from forge-tier.yaml (or default to quick)
7. When `source_type: "docs-only"`: `doc_urls` must have >= 1 entry, `source_repo` becomes optional
8. Each `doc_urls` entry must have a valid `url` field
