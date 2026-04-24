# Skill Brief Schema

## Required Fields

| Field       | Type   | Constraint                                       | Description                                                                 |
|-------------|--------|--------------------------------------------------|-----------------------------------------------------------------------------|
| name        | string | kebab-case `[a-z0-9-]+`                          | Unique skill identifier                                                     |
| version     | string | Semantic version (`X.Y.Z` or `X.Y.Z-prerelease`) | Auto-detect from source (see Version Detection below), fall back to `1.0.0`. **Side effect on remote sources:** `skf-create-skill` treats `version` as an **implicit** `target_version` hint when `target_version` itself is absent — it will try to resolve `{version}` or `v{version}` to a git tag before cloning and fall back to HEAD with a warning if no tag matches. See `skf-create-skill/references/source-resolution-protocols.md` → "Implicit Tag Resolution". |
| source_repo | string | GitHub URL or local path                         | Repository or project root (optional when `source_type: "docs-only"`)       |
| language    | string | Recognized language                              | Primary programming language                                                |
| scope       | object | See Scope Object below                           | Boundary definition                                                         |
| description | string | 1-3 sentences                                    | What the skill covers                                                       |
| forge_tier  | string | `Quick` / `Forge` / `Forge+` / `Deep`            | Inherited from forge-tier.yaml (Title Case)                                 |
| created     | string | ISO date `YYYY-MM-DD`                            | Generation date                                                             |
| created_by  | string | user_name from config                            | Who generated the brief                                                     |

## Optional Fields

| Field              | Type   | Constraint                                       | Description                                                                                                                                                                                                                    |
|--------------------|--------|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| source_type        | string | `source` or `docs-only`                          | Default `source`. When `docs-only`: `source_repo` optional, `doc_urls` required                                                                                                                                                |
| doc_urls           | array  | `{url, label}` objects                           | Documentation URLs for T3 content. Required when `source_type: "docs-only"`                                                                                                                                                    |
| `scripts_intent`   | string | `detect` / `none` / free-text                    | Describes whether scripts should be extracted. Values: `detect` (auto-detect from source — default when absent), `none` (skip scripts), or a free-text description of expected scripts (e.g., "CLI validation tools in bin/"). |
| `assets_intent`    | string | `detect` / `none` / free-text                    | Describes whether assets should be extracted. Values: `detect` (auto-detect from source — default when absent), `none` (skip assets), or a free-text description of expected assets (e.g., "JSON schemas in schemas/").        |
| `target_version`   | string | Semantic version (`X.Y.Z` or `X.Y.Z-prerelease`) | User-specified target version. When present, overrides auto-detection and becomes the skill's version. Recommended for docs-only skills where auto-detection is unavailable.                                                   |
| `source_authority` | string | `official` / `community` / `internal`            | Default `community`. Set to `official` only when the skill creator is the library maintainer. Forced to `community` when `source_type: "docs-only"`.                                                                           |
| `source_ref`       | string | Git ref (tag/branch/HEAD)                        | Resolved git ref used for source access. Set automatically during tag resolution — do not set manually.                                                                                                                        |
| `scope.tier_a_include` | array | Glob patterns                                 | Optional. Narrower tier-A include list for stratified-scope monorepo skills. When present, `skf-test-skill` re-derives the coverage denominator from this list instead of the coarse `scope.include`, so the denominator reflects the authoring surface rather than incidentally-matched internal infrastructure. See `skf-test-skill/references/source-access-protocol.md` stratified-scope resolution. |

When `source_type: "docs-only"`:
- `source_repo` becomes optional (set to doc site URL for reference)
- `doc_urls` must have at least one entry
- `source_authority` is forced to `community` (T3 external documentation cannot be `official`)
- All extracted content gets `[EXT:{url}]` citations

## Version Detection

During brief creation, attempt to auto-detect the source version before defaulting to `"1.0.0"`. Check the first matching file in the source:

- **Python:** `pyproject.toml` `[project] version` (static) → if `dynamic = ["version"]`, check `__init__.py` for `__version__` → `_version.py` if exists → `setup.py` `version=` → `git describe --tags --abbrev=0`
- **JavaScript/TypeScript:** root `package.json` (`"version"`) → if root has `"private": true` with a `"workspaces"` array or lacks a `"version"` field, fall back to a primary workspace package's `package.json` (e.g., `code/core/package.json`, or the first matching `packages/*/package.json`). For GitHub sources, prefer `gh api repos/{owner}/{repo}/releases/latest` → `tag_name` when a non-pre-release tag exists, over a default-branch pre-release. Treat a version containing `-alpha`, `-beta`, `-rc`, `-next`, or `-canary` as a pre-release.
- **Rust:** `Cargo.toml` `[package] version` (static) → if `version = { workspace = true }`, resolve from workspace root `Cargo.toml` → `git describe --tags --abbrev=0`
- **Go:** version tag from `go.mod` or `git describe --tags --abbrev=0`

If the source is a remote GitHub repo, use `gh api repos/{owner}/{repo}/contents/{file}` to read the version file. If the source is local, read the file directly.

If detection succeeds, use the detected version. If it fails or returns a non-semver value, fall back to `"1.0.0"`.

The create-skill workflow (step-03-extract) also performs version reconciliation at extraction time — if the source version has changed since the brief was created, the extraction step warns and uses the source version.

**Target version override:** When `target_version` is present in the brief, it takes precedence over auto-detection. Auto-detection still runs for informational purposes (displayed as "Detected version" alongside the user-specified "Target version"), but the `target_version` value is used as the brief's `version` field. This is particularly useful for docs-only skills (where no package manifest exists) and when the user wants to compile a skill for a specific older version.

**Pre-release handling:** If the detected version contains a pre-release tag (e.g., `1.0.0-beta.0`, `2.0.0-rc.1`), preserve it as-is. Pre-release tags are valid semver and must not be stripped. When comparing versions during reconciliation, use semver-aware comparison that respects pre-release ordering.

## Scope Object Structure

```yaml
scope:
  type: full-library | specific-modules | public-api | component-library | reference-app | docs-only
  include:
    - "src/**/*.ts"           # Glob patterns for included files/directories
  exclude:
    - "**/*.test.*"           # Glob patterns for excluded files
    - "**/node_modules/**"
  # Optional: narrower tier-A include list for stratified-scope monorepos
  # tier_a_include:
  #   - "code/core/src/manager-api/**"
  #   - "code/core/src/preview-api/**"
  notes: "Optional notes about scope decisions"
  # Optional: amendment log for scope decisions made during create-skill §2a,
  # update-skill §1b (auth-doc), and update-skill §1c (scope-expansion).
  # amendments:
  #   - path: "apps/docs/public/llms.txt"
  #     action: "promoted"          # "promoted" | "skipped" | "demoted-include" | "demoted-exclude"
  #     category: "auth-doc"        # "auth-doc" (default for legacy entries) | "scope-expansion"
  #     reason: "authoritative AI docs — only source for canonical install command"
  #     heuristic: "llms.txt"        # required for auth-doc; absent for scope-expansion
  #     date: "2026-04-11"
  #     workflow: "skf-create-skill"
  #   - path: "python/cocoindex/_internal/api.py"
  #     action: "promoted"
  #     category: "scope-expansion"
  #     reason: "out-of-scope new public API — drift report drift-report-20260424-212355.md"
  #     evidence: "~70 new exports flagged out-of-scope by audit"
  #     date: "2026-04-25"
  #     workflow: "skf-update-skill"
  # Additional fields when scope.type is "component-library":
  # registry_path: "path/to/registry.ts"  # Optional — auto-detected if omitted
  # ui_variants:                           # Optional — design system variants
  #   - name: "shadcnui"
  #     package: "packages/components/react-shadcn"
  # demo_patterns:                         # Optional — auto-detected if omitted
  #   - "**/demo/**"
  #   - "**/*.stories.*"
```

### Scope Amendments (Optional)

`scope.amendments[]` is an additive, optional audit log of scope decisions made by workflows after the brief was first authored. Two writer paths exist today:

- **Auth-doc promotions** (`category: "auth-doc"`) — `skf-create-skill` §2a and its mirror `skf-update-skill` §1b append entries when extraction discovers authoritative AI documentation files (`llms.txt`, `AGENTS.md`, etc.) that the original scope patterns excluded.
- **Scope-expansion promotions** (`category: "scope-expansion"`) — `skf-update-skill` §1c appends entries when an audit drift report flags out-of-scope new public API paths (typically a major-version restructure where the brief's `scope.include` no longer reflects the real surface).

**Entry fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Relative path (or glob, for `category: "scope-expansion"`) from source root to the file or tree being amended. For `promoted` actions this matches the literal entry added to `scope.include`. |
| `action` | string | yes | One of: `promoted` (path added to `scope.include`), `skipped` (user declined promotion; decision recorded to prevent re-prompting), `demoted-include` (path removed from `scope.include` — only valid with `category: "scope-expansion"`), `demoted-exclude` (path removed from `scope.exclude` — only valid with `category: "scope-expansion"`). |
| `category` | string | no | One of: `auth-doc` (default for entries without this field — the historical sole use case), `scope-expansion`. Distinguishes which workflow path wrote the entry and which writer-rules apply on re-runs. |
| `reason` | string | yes | Human-readable sentence explaining the decision. Either user-provided at prompt time or auto-generated. |
| `heuristic` | string | conditional | Required for `category: "auth-doc"` — the basename that matched (`llms.txt`, `AGENTS.md`, etc.). Omit for `category: "scope-expansion"`. |
| `evidence` | string | conditional | Required for `category: "scope-expansion"` — short rationale from the source signal (e.g., a drift-report finding's evidence one-liner). Omit for `category: "auth-doc"`. |
| `date` | string | yes | ISO date (`YYYY-MM-DD`) when the amendment was recorded. |
| `workflow` | string | yes | Workflow name that wrote the amendment (`skf-create-skill`, `skf-update-skill`). Identifies which workflow made the decision. |

**Promotion write-through:** When `action: "promoted"`, the workflow also appends the literal path to `scope.include`. This is a belt-and-suspenders design: future runs read `scope.include` during scope filtering and include the file in the filtered list automatically, so the §2a/§1b/§1c discovery loop finds no candidate and does not re-prompt. The `amendments[]` entry is the human-readable audit trail of *why* the path was added.

**Skip recording:** When `action: "skipped"`, the workflow does NOT modify `scope.include` or `scope.exclude`. The amendment entry alone is enough to prevent re-prompting, because the discovery loop checks `amendments[]` before prompting.

**Demotion (scope-expansion only):** `demoted-include` removes a previously-promoted path from `scope.include` — used when a prior `[P]` decision is reversed. `demoted-exclude` removes a path from `scope.exclude` — used when a previously excluded path needs to be re-evaluated. Both write the structural change and append the amendment so future runs see the rationale. Demotion is not valid for `category: "auth-doc"`: auth-doc skips already prevent re-prompting without scope mutation.

**Backward compatibility:** `scope.amendments` is optional. Briefs without this field validate unchanged. Treat missing as an empty list. Existing entries without `category` are equivalent to `category: "auth-doc"` — readers must default the field when absent.

**Who reads `amendments[]`:**

- `skf-create-skill` §2a consults it to avoid re-prompting on decided auth-doc files.
- `skf-update-skill` §1b (mirror of §2a) consults it for the same auth-doc reason.
- `skf-update-skill` §1c consults it to avoid re-prompting on decided scope-expansion candidates and to honor prior `demoted-*` decisions.
- `skf-audit-skill` may optionally report on stale promotions (promoted paths that no longer exist in source) as a future enhancement — not currently implemented.
- Humans reading the brief see the audit trail of non-obvious scope decisions.

**Who writes `amendments[]`:**

- `skf-create-skill` §2a (Discovered Authoritative Files Protocol) — `category: "auth-doc"`
- `skf-update-skill` §1b (mirror of §2a applied during change detection) — `category: "auth-doc"`
- `skf-update-skill` §1c (Major-Version Scope Reconciliation) — `category: "scope-expansion"`
- Manual edits by the brief author are permitted but should include all required fields above (and `category` when the entry is not an auth-doc decision).

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
  type: "{full-library|specific-modules|public-api|component-library|reference-app|docs-only}"
  include:
    - "{pattern}"
  exclude:
    - "{pattern}"
  notes: "{optional-scope-notes}"
# target_version: "X.Y.Z"       # Optional: overrides auto-detection when specified
# source_ref: "v0.5.0"          # Auto-resolved — do not set manually
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

{If target_version is set:}
Target Version:   {target_version} (user-specified)
Detected Version: {detected_version or "N/A"}
{Else:}
Version:    {version}
{End if}
Created:    {created}
Created by: {created_by}
```

## Validation Rules

1. `name` must be unique within {forge_data_folder}
2. `source_repo` must be accessible (gh api for GitHub, path exists for local)
3. `language` must be a recognized programming language
4. `scope.type` must be one of the six defined types
5. `scope.include` must have at least one pattern (exception: `docs-only` scope, where include patterns are optional since no source code is available)
6. `forge_tier` must be one of: Quick, Forge, Forge+, Deep (Title Case, must match the tier from forge-tier.yaml, or default to Quick)
7. When `source_type: "docs-only"`: `doc_urls` must have >= 1 entry, `source_repo` becomes optional
8. Each `doc_urls` entry must have a valid `url` field
