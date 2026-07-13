<!-- Config: communicate in {communication_language}. -->

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

<!-- Manifest scanning, name normalization, dedup, exclusion-dir filtering, and
dev/build-tool filtering are performed by `skf-scan-manifests.py` (invoked in
detect-manifests.md §2), which implements exactly the ecosystem table above.
This file is loaded only for that reference table and the import-counting
exclusions below — see the script's `--help` for the operative scan contract. -->

## Import Counting

For each dependency, count distinct files that import it:
- Use grep patterns from Import Pattern column
- Count unique file paths, not total import statements
- Exclude test files (`*/test/*`, `*_test.*`, `*.spec.*`, `*.test.*`), config files (`*.config.*`, `.eslintrc`, etc.), and build artifacts (`dist/`, `build/`, `node_modules/`, `target/`, `__pycache__/`) from count
