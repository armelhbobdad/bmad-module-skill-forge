# Skill Brief Schema

## Required Fields

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| name | string | kebab-case `[a-z0-9-]+` | Unique skill identifier |
| version | string | Semantic version (`X.Y.Z` or `X.Y.Z-prerelease`) | Auto-detect from source (see Version Detection below), fall back to `1.0.0` |
| source_repo | string | GitHub URL or local path | Repository or project root (optional when `source_type: "docs-only"`) |
| language | string | Recognized language | Primary programming language |
| scope | object | See Scope Object below | Boundary definition |
| description | string | 1-3 sentences | What the skill covers |
| forge_tier | string | `Quick` / `Forge` / `Forge+` / `Deep` | Inherited from forge-tier.yaml (Title Case) |
| created | string | ISO date `YYYY-MM-DD` | Generation date |
| created_by | string | user_name from config | Who generated the brief |

## Optional Fields

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| source_type | string | `source` or `docs-only` | Default `source`. When `docs-only`: `source_repo` optional, `doc_urls` required |
| doc_urls | array | `{url, label}` objects | Documentation URLs for T3 content. Required when `source_type: "docs-only"` |
| `scripts_intent` | string | `detect` / `none` / free-text | Describes whether scripts should be extracted. Values: `detect` (auto-detect from source — default when absent), `none` (skip scripts), or a free-text description of expected scripts (e.g., "CLI validation tools in bin/"). |
| `assets_intent` | string | `detect` / `none` / free-text | Describes whether assets should be extracted. Values: `detect` (auto-detect from source — default when absent), `none` (skip assets), or a free-text description of expected assets (e.g., "JSON schemas in schemas/"). |
| `source_authority` | string | `official` / `community` / `internal` | Default `community`. Set to `official` only when the skill creator is the library maintainer. Forced to `community` when `source_type: "docs-only"`. |

When `source_type: "docs-only"`:
- `source_repo` becomes optional (set to doc site URL for reference)
- `doc_urls` must have at least one entry
- `source_authority` is forced to `community` (T3 external documentation cannot be `official`)
- All extracted content gets `[EXT:{url}]` citations

## Version Detection

During brief creation, attempt to auto-detect the source version before defaulting to `"1.0.0"`. Check the first matching file in the source:

- **Python:** `pyproject.toml` `[project] version` (static) → if `dynamic = ["version"]`, check `__init__.py` for `__version__` → `_version.py` if exists → `setup.py` `version=` → `git describe --tags --abbrev=0`
- **JavaScript/TypeScript:** `package.json` (`"version"`)
- **Rust:** `Cargo.toml` `[package] version` (static) → if `version = { workspace = true }`, resolve from workspace root `Cargo.toml` → `git describe --tags --abbrev=0`
- **Go:** version tag from `go.mod` or `git describe --tags --abbrev=0`

If the source is a remote GitHub repo, use `gh api repos/{owner}/{repo}/contents/{file}` to read the version file. If the source is local, read the file directly.

If detection succeeds, use the detected version. If it fails or returns a non-semver value, fall back to `"1.0.0"`.

The create-skill workflow (step-03-extract) also performs version reconciliation at extraction time — if the source version has changed since the brief was created, the extraction step warns and uses the source version.

**Pre-release handling:** If the detected version contains a pre-release tag (e.g., `1.0.0-beta.0`, `2.0.0-rc.1`), preserve it as-is. Pre-release tags are valid semver and must not be stripped. When comparing versions during reconciliation, use semver-aware comparison that respects pre-release ordering.

## Scope Object Structure

```yaml
scope:
  type: full-library | specific-modules | public-api | component-library | docs-only
  include:
    - "src/**/*.ts"           # Glob patterns for included files/directories
  exclude:
    - "**/*.test.*"           # Glob patterns for excluded files
    - "**/node_modules/**"
  notes: "Optional notes about scope decisions"
  # Additional fields when scope.type is "component-library":
  # registry_path: "path/to/registry.ts"  # Optional — auto-detected if omitted
  # ui_variants:                           # Optional — design system variants
  #   - name: "shadcnui"
  #     package: "packages/components/react-shadcn"
  # demo_patterns:                         # Optional — auto-detected if omitted
  #   - "**/demo/**"
  #   - "**/*.stories.*"
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
forge_tier: "{Quick|Forge|Forge+|Deep}"
created: "{date}"
created_by: "{user_name}"
scope:
  type: "{full-library|specific-modules|public-api|component-library|docs-only}"
  include:
    - "{pattern}"
  exclude:
    - "{pattern}"
  notes: "{optional-scope-notes}"
# Optional: documentation URLs for T3 content (required when source_type: "docs-only")
# doc_urls:
#   - url: "https://docs.example.com/api"
#     label: "API Reference"
# scripts_intent: detect         # Optional: detect | none | description
# assets_intent: detect          # Optional: detect | none | description
# source_authority: community    # Optional: official | community | internal
---
```

## Human-Readable Presentation Format

When presenting the brief for confirmation (brief-skill step 04 only — not applicable to analyze-source batch generation), display as:

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

{If source_type is "docs-only":}
Source Type: docs-only
Doc URLs:
  {doc_urls, one per line with labels}

{If source_type is "source" AND supplemental doc_urls collected:}
Supplemental Docs:
  {doc_urls, one per line with labels}

{If scripts_intent or assets_intent was explicitly set (not default "detect"):}
Scripts:    {scripts_intent}
Assets:     {assets_intent}

Source Authority: {source_authority}

Version:    {version}
Created:    {created}
Created by: {created_by}
```

## Validation Rules

1. `name` must be unique within {forge_data_folder}
2. `source_repo` must be accessible (gh api for GitHub, path exists for local)
3. `language` must be a recognized programming language
4. `scope.type` must be one of the five defined types
5. `scope.include` must have at least one pattern (exception: `docs-only` scope, where include patterns are optional since no source code is available)
6. `forge_tier` must be one of: Quick, Forge, Forge+, Deep (Title Case, must match the tier from forge-tier.yaml, or default to Quick)
7. When `source_type: "docs-only"`: `doc_urls` must have >= 1 entry, `source_repo` becomes optional
8. Each `doc_urls` entry must have a valid `url` field
