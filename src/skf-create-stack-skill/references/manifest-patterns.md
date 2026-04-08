# Manifest Detection Patterns

## Supported Ecosystems

| Ecosystem             | Manifest File(s)                                    | Dependency Key                           | Import Pattern                            |
|-----------------------|-----------------------------------------------------|------------------------------------------|-------------------------------------------|
| JavaScript/TypeScript | package.json                                        | dependencies, devDependencies            | `import ... from '...'`, `require('...')` |
| Python                | requirements.txt, setup.py, pyproject.toml, Pipfile | install_requires, [project.dependencies] | `import ...`, `from ... import`           |
| Rust                  | Cargo.toml                                          | [dependencies]                           | `use ...`, `extern crate`                 |
| Go                    | go.mod                                              | require                                  | `import "..."`                            |
| Java                  | pom.xml, build.gradle                               | dependencies                             | `import ...`                              |
| Ruby                  | Gemfile                                             | gem                                      | `require '...'`, `require_relative`       |
| PHP                   | composer.json                                       | require, require-dev                     | `use ...`, `require_once`                 |
| .NET                  | *.csproj                                            | PackageReference                         | `using ...`                               |

## Detection Priority

1. Search project root for manifest files (depth 0-1)
2. Parse each found manifest to extract dependency names
3. Normalize names across ecosystems (e.g., `@scope/package` → `package`)
4. Deduplicate across multiple manifests

## Scan Exclusion Patterns

When scanning for manifest files, ALWAYS exclude these directories from glob results:

**Dependency/Vendor Directories:**
- `node_modules/`
- `.venv/` / `venv/` / `.env/`
- `vendor/` (PHP Composer, Go modules)
- `Pods/` (iOS CocoaPods)

**Build Output Directories:**
- `dist/` / `build/` / `out/`
- `target/` (Rust, Java/Maven)
- `__pycache__/`
- `.next/` / `.nuxt/` / `.output/`

**Hidden and VCS Directories:**
- `.git/`
- Any directory starting with `.` (except project root hidden config files like `.csproj`)

**Monorepo Note:** For monorepo structures (e.g., `packages/*/package.json`), the depth 0-1 scan rule already limits scope. If monorepo manifest detection is needed at deeper levels, these exclusions become critical to prevent scanning dependency trees within each package.

## Filtering Rules

- Exclude dev-only dependencies unless they appear in production imports
- Exclude build tools (webpack, babel, eslint, etc.) unless significantly imported
- Include all runtime dependencies by default
- Flag transitive dependencies that appear in direct imports

## Import Counting

For each dependency, count distinct files that import it:
- Use grep patterns from Import Pattern column
- Count unique file paths, not total import statements
- Exclude test files (`*/test/*`, `*_test.*`, `*.spec.*`, `*.test.*`), config files (`*.config.*`, `.eslintrc`, etc.), and build artifacts (`dist/`, `build/`, `node_modules/`, `target/`, `__pycache__/`) from count
