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

`skf-disqualify-candidates.py` reports the signals a boundary's file list shows, in each record's `signals` (identify-units §2): an independent manifest (`own_manifest`), a separate entry point (`entry_point`), a Docker/service definition (`service_definition`), README.md presence (`readme`), a separate test suite (`test_suite`), a CI/CD pipeline reference (`ci_reference`) and a large directory (`large_directory`). Workspace membership is reported too, as each candidate's `workspace_member` (**Candidate Boundaries**): scan-project passes the scan the workspaces `skf-detect-workspaces.py --snapshot` resolves from the workspace configuration, and a path discover-additional-source adds has none (null). The other signals are judged from the code.

## Candidate Boundaries

The boundaries scan-project and discover-additional-source propose for a project path, which identify-units then classifies, are the `candidates[]` of its `skf-scan-manifests.py` scan, which applies the rule itself: the folders that hold a manifest or a Docker, compose or serverless file, less a workspace root with no code of its own (`.` is the scan root). Name a candidate by its folder.

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
- Hard cross-boundary dependency: consumers use the constituents together, through types, traits or interfaces they share, or through one facade that re-exports them all
- Common pattern: a set of crates/packages in the same repo that implement a protocol together (e.g., plugin crates for a framework, verification + encoding halves of a cryptographic library), or a facade package over its sub-packages
- Scope type: inherits from the dominant constituent (typically `full-library` or `specific-modules`)

**Detection heuristic (map-and-detect §5, once the import graph and the integration map exist):**
1. Among the qualifying units, find groups of ≥2 boundaries where any trigger holds:
   - **Mutual hard dependency:** the constituents import each other in a cycle (`skf-find-cycles.py` over the `skf-count-imports.py` edges), AND no constituent's public API is self-contained (removing any one breaks the others)
   - **Shared integration surface:** Constituents share types/traits defined in one constituent but consumed by all others, AND the consuming constituents have no independent barrel (their value depends on the shared definitions)
   - Any of the **Cohesion Triggers** below
2. For each detected group, propose merging into a single composite unit:
   - Name: by the Unit Names rule below, for a merged unit
   - Constituents: list of merged boundary names and paths
   - Rationale: which trigger fired, with its evidence
3. The merge is a **recommendation**: the user confirms it in map-and-detect §6, and a headless run accepts it. A group that merges is not also a stack skill candidate.

### Cohesion Triggers

The one statement of when a monorepo's members belong in one cohesive skill rather than one skill per package. The `[auto]` path (step-auto-scope §3b) and the interactive chain (map-and-detect §5, and discover-additional-source for a path [D] adds) apply it. Empirically, 5/5 real monorepos (animato 15 crates, trpc, react 38 packages, aws-sdk-js-v3 442 packages, plus zod) were best served as one cohesive skill or a curated few, not one skill per package. The evidence comes from the `skf-scan-manifests.py` scan (`umbrella_candidates[]`, and each member's `name`, `private` and `internal_deps`), never from opening each member manifest.

Merge when **any** of these holds:

- **Umbrella facade:** one package re-exports the members: a root or named package whose dependencies include the other workspace members (an `umbrella_candidates[]` entry, with the members its `internal_deps` cover), or which `pub use` / `export *`s them. The facade *is* the public surface (e.g. animato's `crates/animato` re-exporting its 15 sub-crates).
- **Shared runtime contract:** the members are consumed together through one entry point, and teaching the shared invariant covers them (e.g. tRPC's adapters around `@trpc/server`; aws-sdk's `new XClient(...) → client.send(new YCommand(...))` shared by every `@aws-sdk/client-*`).
- **Internal building blocks:** the members are private/internal pieces of one product, not independently meaningful to a consumer (`private: true` on the members).

Split instead when the members are **independently published with distinct public surfaces serving different concerns**, **and no umbrella re-exports them**: e.g. `react-dom` and `react-server-dom-*` are separate installs with separate jobs, or a federated SDK where a consumer only ever wants one service. Each genuinely distinct facet earns its own skill.

## Disqualification Rules

Do not recommend a boundary as a skillable unit when:

1. **Too small**: Fewer than 3 source files or 100 lines of code. `skf-disqualify-candidates.py` counts the source files that are not generated: lockfiles, documentation, data and configuration files, manifests and build tool files (`setup.py`, `build.gradle`, `gradlew`, `vite.config.ts` and the like) are not source files
2. **Generated code**: every source file is generated (protobuf, GraphQL codegen, etc.): under a vendored or cache folder (`node_modules/`, `vendor/`, `__pycache__/` and the like) at any depth, under a build output folder (`dist/`, `build/`, `target/`) directly below the unit or beside a manifest, or opening with a generated-code header such as `@generated`. A source folder of an output folder's name further down (`src/build/`, the Java package folder `com/acme/build/`) is the unit's own code. A boundary with only some generated files stays, with those files left out of its counts, and identify-units judges it
3. **Pure configuration**: Only config files with no logic
4. **Test-only**: Test utilities with no production code
5. **Vendor/dependency**: Third-party code copied into project
6. **Already skilled**: Existing skill found in forge_data_folder (recommend update-skill instead)

## Unit Names

Every unit, composite and brief is named by `skf-skill-inventory.py derive-name`, from the same inputs on the `[auto]` path (step-auto-scope §6 and its split branch) and the interactive chain (identify-units §2, map-and-detect §5, discover-additional-source), so one unit gets one name on both:

- **A single unit** passes its own manifest's `name` and `private` flag. A private manifest names nothing, so a monorepo's workspace root or an internal app takes its folder's or repository's name; a published package takes its manifest's (`@trpc/server` gives `trpc-server`).
- **A merged unit** (a composite, or a monorepo the cohesion check merges) passes the facade's manifest name when the umbrella facade trigger fired, and its members' manifest names: a composite's constituents, a merged monorepo's published members (its private examples and tools left out). Without a facade it takes the name the members share (`trpc` for `@trpc/server` and `@trpc/client`), else the repository's.

Names that would clash in one call are told apart by their parent folders (`server-api`, `client-api`).

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

Flag units as stack skill candidates when (map-and-detect §5, in the same pass as the composite merges):

1. **Co-import frequency**: Two or more units are imported together in 3+ files (a `skf-pair-intersect.py` pair over the `skf-count-imports.py` importer lists with an `intersection_count` of 3 or more)
2. **Integration adapter**: A unit exists primarily to bridge two other units
3. **Shared state**: Multiple units read/write to the same data store
4. **Orchestration layer**: A unit coordinates calls across multiple other units

Stack skill candidates are useful separately and also together; units that only deliver value together are a Composite Boundary instead, never both.
