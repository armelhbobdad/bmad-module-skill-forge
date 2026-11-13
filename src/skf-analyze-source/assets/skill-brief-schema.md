# Skill Brief Schema

## Required Fields

| Field       | Type   | Constraint                                       | Description                                                                 |
|-------------|--------|--------------------------------------------------|-----------------------------------------------------------------------------|
| name        | string | kebab-case `[a-z0-9-]+`                          | Unique skill identifier                                                     |
| version     | string | Semantic version (`X.Y.Z` or `X.Y.Z-prerelease`) | Auto-detect from source (see Version Detection below), fall back to `1.0.0`. **Side effect on remote sources:** `skf-create-skill` treats `version` as an **implicit** `target_version` hint when `target_version` itself is absent — it will try to resolve `{version}` or `v{version}` to a git tag before cloning and fall back to HEAD with a warning if no tag matches. See `skf-create-skill/references/source-resolution-protocols.md` → "Implicit Tag Resolution". |
| source_repo | string | GitHub URL or local path                         | Repository or project root (optional when `source_type: "docs-only"`)       |
| language    | string | Non-empty                                        | Primary programming language                                                |
| scope       | object | See Scope Object below                           | Boundary definition                                                         |
| description | string | 1-3 sentences                                    | What the skill covers. Must contain a literal `Use when` clause — validators test for that exact phrase. |
| forge_tier  | string | `Quick` / `Forge` / `Forge+` / `Deep`            | The analysis report's `forge_tier` (Title Case)                             |
| created     | string | ISO date `YYYY-MM-DD`                            | Generation date                                                             |
| created_by  | string | user_name from config                            | Who generated the brief                                                     |

## Version Detection

A brief's `detected_version` starts from the manifest scan: it is the `version` that `skf-scan-manifests.py` gives the unit's own manifest (a Cargo `version.workspace = true` already resolved from its workspace), passed to the brief writer as found, null when there is none. The writer keeps a full `X.Y.Z` semver version and falls back to `"1.0.0"` otherwise, with a warning. Look a version up only in two cases, and pass what you find the same way:

- **A `version_dynamic` manifest** (Python, a version computed at build time): the extractor looks it up (`skf-extract-public-api.py --help` gives its order), `<package>` being the import package's folder under the scan root. Where the scan root holds only the manifests (step-auto-scope's remote fetch), first bring in the files it reads: `git -C "{scan_root}" sparse-checkout add '/<package>/__init__.py' '/<package>/_version.py' '/<the setup.py beside the manifest>'`. Then run:

  ```bash
  uv run {extractPublicApiHelper} --mode quick --language python --source-root "{scan_root}" --manifest-file "<the manifest>" --entry-file "<package>/__init__.py" --resolve-version
  ```

  Leave `--entry-file` out when the scan root holds no `<package>/__init__.py` (a single module, a namespace package): the extractor exits 2 on an entry file it cannot read, and without one still reads the setup.py and the release tag. Its `version` is the version, and its `version_source` (`file:<path>` or `tag:<tag>`) says where it came from. A non-zero exit or a null `version` leaves `detected_version` null.
- **A private workspace root that gives none** (JavaScript/TypeScript: the root `package.json` has `"private": true` with `"workspaces"`, or no `"version"`): the `version` the same scan gives a primary workspace package (e.g., `code/core/package.json`, or the first matching `packages/*/package.json`)

The create-skill workflow (extract) also performs version reconciliation at extraction time — if the source version has changed since the brief was created, the extraction step warns and uses the source version.

**Target version override:** When `target_version` is present in the brief, it takes precedence over auto-detection. Auto-detection still runs for informational purposes (displayed as "Detected version" alongside the user-specified "Target version"), but the `target_version` value is used as the brief's `version` field. This is particularly useful for docs-only skills (where no package manifest exists) and when the user wants to compile a skill for a specific older version.

**Pre-release handling:** If the detected version contains a pre-release tag (e.g., `1.0.0-beta.0`, `2.0.0-rc.1`), preserve it as-is. Pre-release tags are valid semver and must not be stripped. When comparing versions during reconciliation, use semver-aware comparison that respects pre-release ordering.

## Scope Object

```yaml
scope:
  type: full-library | specific-modules | public-api | component-library | reference-app | docs-only
  include:
    - 'src/**/*.ts'          # At least one required
  exclude:
    - 'src/**/*.test.ts'     # Optional
  # Optional: narrower tier-A include list for stratified-scope monorepos
  # and reference-app pattern surfaces (refined later by skf-brief-skill)
  # tier_a_include:
  #   - 'code/core/src/manager-api/**'
  notes: 'Optional rationale for scope decision'
  # Additional fields when scope.type is "component-library":
  # registry_path: "path/to/registry.ts"  # Optional — auto-detected if omitted
  # ui_variants:                           # Optional — design system variants
  #   - name: "shadcnui"
  #     package: "packages/components/react-shadcn"
  # demo_patterns:                         # Optional — auto-detected if omitted
  #   - "**/demo/**"
  #   - "**/*.stories.*"
```

### Scope Types

| Type              | Use When                                                                             |
|-------------------|--------------------------------------------------------------------------------------|
| full-library      | Entire codebase of a unit                                                            |
| specific-modules  | Selected components or packages                                                      |
| public-api        | Only exported interfaces                                                             |
| component-library | UI component libraries with registries, props-based APIs, and design system variants |
| reference-app     | Whole app whose value is wiring patterns, not public exports (embedded sidecars, CLI demos, integration-pattern demonstrators). Also the home for **language / spec references** — engine- or spec-versioned query languages, grammars, or DSLs (e.g. SurrealQL) whose value is construct idioms, not exports. These have no separate scope type; they ride `reference-app` as a sub-shape (see `skf-create-skill` Language / spec-reference sub-shape) |
| docs-only         | When source_type is docs-only — no source code available, all content from doc_urls  |

> **Documented vs source language.** The `language` field records the language the skill *documents*. For a language / spec reference this may differ from the source language it is extracted from — e.g. a SurrealQL reference extracted from a Rust engine records `language: surrealql`, not `rust`. Use the documented language and a matching code-fence default (e.g. ` ```surql `) throughout the brief.
