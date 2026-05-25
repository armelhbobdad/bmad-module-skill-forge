<!-- Config: communicate in {communication_language}. -->

# Unit Detection Heuristics

## Purpose

Rules for identifying discrete skillable units within a project. A "skillable unit" is a self-contained component with clear boundaries that can be documented as an independent skill.

## Detection Signals

### Strong Signals (High Confidence)

| Signal                                         | Description                                  | Example                            |
|------------------------------------------------|----------------------------------------------|------------------------------------|
| Independent package.json / Cargo.toml / go.mod | Unit has its own dependency manifest         | `packages/auth/package.json`       |
| Separate entry point                           | Unit has a main/index file                   | `services/api/src/index.ts`        |
| Docker/service definition                      | Unit runs as an independent service          | `docker-compose.yml` service entry |
| Distinct export surface                        | Unit exports a public API consumed by others | `src/lib/index.ts` with re-exports |
| Workspace member                               | Listed in root workspace configuration       | `pnpm-workspace.yaml` packages     |

### Moderate Signals (Medium Confidence)

| Signal                   | Description                                       | Example                             |
|--------------------------|---------------------------------------------------|-------------------------------------|
| Directory depth boundary | Top-level directory with self-contained structure | `src/modules/payments/`             |
| Naming convention        | Follows organizational naming pattern             | `@org/package-name`                 |
| Separate test suite      | Has its own test directory or config              | `packages/auth/__tests__/`          |
| README.md presence       | Has documentation at directory level              | `libs/utils/README.md`              |
| CI/CD pipeline reference | Referenced in build/deploy configuration          | `.github/workflows/deploy-auth.yml` |

### Weak Signals (Low Confidence — Require Corroboration)

| Signal             | Description                                 | Example                       |
|--------------------|---------------------------------------------|-------------------------------|
| Large directory    | Many files in a subtree                     | 50+ files under one directory |
| Comment boundaries | Code comments marking sections              | `// --- Auth Module ---`      |
| Import clustering  | Files that import primarily from each other | Tight import graph cluster    |

## Boundary Classification

### Service Boundary
- Independent deployable unit
- Own process, port, or container
- Clear network interface (REST, gRPC, message queue)
- Scope type: `full-library`

### Package Boundary
- Workspace member or independently versioned package
- Own dependency manifest
- Exports consumed by other packages
- Scope type: `full-library` or `specific-modules`

### Module Boundary
- Logical grouping within a single package
- Shared namespace or directory structure
- Internal cohesion, external coupling through defined interface
- Scope type: `specific-modules` or `public-api`

### Library Boundary
- Third-party dependency with significant project-specific usage patterns
- Custom wrappers, configurations, or integration code
- Scope type: `public-api`

### Component Library Boundary
- Contains a component registry or catalog file (array of component definitions with IDs, names, categories)
- Has `components/`, `packages/components/`, or similar multi-component directory structure
- Multiple design system variant directories (e.g., `react-shadcn/`, `react-baseui/`, `react-carbon/`)
- Significant demo/story/example file ratio (>30% of total files)
- CLI-based installation pattern (e.g., `npx <tool> add <component-id>`)
- Props interfaces outnumber function signatures as primary API surface
- Scope type: `component-library`

### Composite Boundary
- Two or more Package or Module boundaries that only deliver value together (no constituent is independently useful to the skill consumer)
- Hard cross-boundary dependency: constituents share types, traits, or interfaces that are not re-exported through a single barrel — consumers must import from multiple constituents to use the integration
- Common pattern: a set of crates/packages in the same repo that implement a protocol together (e.g., plugin crates for a framework, verification + encoding halves of a cryptographic library)
- Scope type: inherits from the dominant constituent (typically `full-library` or `specific-modules`)

**Detection heuristic (apply after initial classification, before user confirmation):**
1. Among the qualifying units, find groups of ≥2 boundaries where EITHER:
   - **Mutual hard dependency:** Every constituent imports from at least one other constituent in the group, AND no constituent's public API is self-contained (removing any one breaks the others)
   - **Shared integration surface:** Constituents share types/traits defined in one constituent but consumed by all others, AND the consuming constituents have no independent barrel (their value depends on the shared definitions)
2. For each detected group, propose merging into a single composite unit:
   - Name: `{common-prefix}` or `{integration-name}` (derive from shared namespace or repo name)
   - Constituents: list of merged boundary names and paths
   - Rationale: which heuristic triggered (mutual hard dependency or shared integration surface)
3. The merge is a **recommendation** — present to user for confirmation in identify-units §3b

## Disqualification Rules

Do NOT recommend as a skillable unit if:

1. **Too small**: Fewer than 3 source files or 100 lines of code
2. **Generated code**: Auto-generated files (protobuf, GraphQL codegen, etc.)
3. **Pure configuration**: Only config files with no logic
4. **Test-only**: Test utilities with no production code
5. **Vendor/dependency**: Third-party code copied into project
6. **Already skilled**: Existing skill found in forge_data_folder (recommend update-skill instead)

## Script/Asset Detection Signals

During per-unit analysis, check for scripts and assets alongside code exports.

**Script signals:**

| Strength | Signal                                                                                        | Example                                             |
|----------|-----------------------------------------------------------------------------------------------|-----------------------------------------------------|
| Strong   | Entry point in `package.json` `bin`, Cargo.toml `[[bin]]`, pyproject.toml `[project.scripts]` | `"bin": { "migrate": "scripts/migrate.js" }`        |
| Strong   | Shebang + executable file                                                                     | `#!/usr/bin/env python` in `scripts/setup.py`       |
| Moderate | File in `scripts/`, `bin/`, `tools/`, `cli/` directory                                        | `scripts/validate.sh`                               |
| Moderate | CI/CD reference to script                                                                     | `.github/workflows/test.yml` runs `scripts/test.sh` |

**Asset signals:**

| Strength | Signal                                                                         | Example                          |
|----------|--------------------------------------------------------------------------------|----------------------------------|
| Strong   | JSON Schema file with `$schema` key                                            | `schemas/config.schema.json`     |
| Strong   | Config template with `.example` or `.template` extension                       | `config.yaml.example`            |
| Moderate | File in `assets/`, `templates/`, `schemas/`, `configs/`, `examples/` directory | `templates/report.hbs`           |
| Moderate | OpenAPI/GraphQL definition                                                     | `openapi.json`, `schema.graphql` |

**Per-unit output:** Record `has_scripts: boolean`, `has_assets: boolean`, `script_files: string[]`, `asset_files: string[]`.

**Disqualify:** Generated files (dist/, build/), vendored dependencies, IDE configs (.vscode/, .idea/), binary files (.so, .dll, .jar).

## Stack Skill Candidate Detection

Flag units as stack skill candidates when:

1. **Co-import frequency**: Two or more units are imported together in 3+ files
2. **Integration adapter**: A unit exists primarily to bridge two other units
3. **Shared state**: Multiple units read/write to the same data store
4. **Orchestration layer**: A unit coordinates calls across multiple other units

## Tier-Aware Scanning Depth

| Forge Tier | Scanning Approach                                                                                  |
|------------|----------------------------------------------------------------------------------------------------|
| Quick      | File structure analysis: directory trees, manifest files, entry points, naming conventions         |
| Forge      | AST analysis: export surfaces, import graphs, dependency trees, type hierarchies                   |
| Forge+     | AST + CCC: semantic file pre-ranking before structural analysis, CCC signals for relevance scoring |
| Deep       | AST + QMD: temporal evolution, refactoring patterns, semantic relationships, architectural drift   |
