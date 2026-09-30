<!-- Config: communicate in {communication_language}. -->

# Manifest Detection Patterns

## Supported Ecosystems

`skf-scan-manifests.py` (invoked in detect-manifests.md §2) finds exactly the manifest files below and no others; the same list is its `searched_filenames[]`. The Ecosystem column is the value it writes in each manifest's `ecosystem` field. The table mirrors the script's `MANIFEST_ECOSYSTEMS`, and `test/test-skf-scan-manifests.py` fails when the two drift.

| Ecosystem  | Language              | Manifest files                                                           | Runtime dependencies                                                                     | Dev dependencies (`scope: dev`)                                                     | Import syntax counted                                      |
|------------|-----------------------|--------------------------------------------------------------------------|------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|------------------------------------------------------------|
| `npm`      | JavaScript/TypeScript | `package.json`                                                           | `dependencies`                                                                           | `devDependencies`                                                                   | `import ... from '...'`, `import('...')`, `require('...')` |
| `python`   | Python                | `pyproject.toml`, `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile` | `[project] dependencies`, `[tool.poetry.dependencies]`, `install_requires`, `[packages]` | `[dependency-groups]`, dev extras, Poetry groups, `tests_require`, `[dev-packages]` | `import ...`, `from ... import ...`                        |
| `rust`     | Rust                  | `Cargo.toml`                                                             | `[dependencies]`                                                                         | `[dev-dependencies]`                                                                | `use ...`, `extern crate ...`, `crate_name::path`          |
| `go`       | Go                    | `go.mod`                                                                 | `require`                                                                                | none                                                                                | `import "..."`                                             |
| `maven`    | Java/Kotlin           | `pom.xml`                                                                | `<dependency>` outside the `test`, `provided` and `system` scopes                        | `<scope>test</scope>`                                                               | `import ...`                                               |
| `gradle`   | Java/Kotlin           | `build.gradle`, `build.gradle.kts`                                       | `implementation`, `api`, `compile`, `runtimeOnly`                                        | `test*` and `androidTest*` configurations                                           | `import ...`                                               |
| `ruby`     | Ruby                  | `Gemfile`                                                                | `gem`                                                                                    | `gem` inside a `group :development` or `:test` block                                | `require '...'`                                            |
| `composer` | PHP                   | `composer.json`                                                          | `require` (not `php` or `ext-*`)                                                         | `require-dev`                                                                       | `use ...`                                                  |
| `swift`    | Swift                 | `Package.swift`                                                          | `.package(url: ...)`                                                                     | none                                                                                | `import ...`                                               |

The scanner reports runtime dependencies by default; `--include-dev` adds the dev ones, each tagged `scope: dev`. For each manifest it also reports the package's own `name`, whether it is `private` (not published) and its `internal_deps`, the other scanned packages of the same ecosystem it depends on at runtime; `umbrella_candidates` lists the published packages that depend on at least 2, and at least half, of the other published members of their ecosystem (a facade that may re-export them). The script's docstring states the exact rules.

## Scan Exclusion Patterns

The scanner never descends into `node_modules/`, `.venv/`, `venv/`, `.env/`, `vendor/`, `Pods/`, `dist/`, `build/`, `out/`, `target/`, `__pycache__/`, `.next/`, `.nuxt/`, `.output/` or `.git/`, nor into any other directory whose name starts with a dot.

## Import Counting

Import counts follow these rules, which `skf-count-imports.py` implements:

- Count the distinct files that import each dependency, not the import statements: a file counts once, with the first line that imports the dependency.
- Match on module boundaries: `react` counts `import ... from 'react'` and `'react/jsx-runtime'`, never `react-dom` or `react-router`; `yaml` counts `yaml` and `yaml.loader`, never `yamlordereddict`.
- Map distribution names to import names: `PyYAML` is imported as `yaml`, `Pillow` as `PIL`, `beautifulsoup4` as `bs4`, `scikit-learn` as `sklearn`. A name outside the script's tables is guessed by a naming rule: a Python distribution as its name with `-` read as `_`, `google-cloud-storage` as `google.cloud.storage`, `@types/react` as `react`, `symfony/framework-bundle` as `Symfony\Bundle\FrameworkBundle`. A guess that matches no file goes to `unresolved[]` for you to judge instead of counting 0.
- A dependency imported by 2 or more files is `above_threshold`.

Excluded paths (a pattern ending in `/` names a directory at any depth; a pattern with no `/` matches a file name at any depth):

- Hidden files and directories: `.*/`, `.*`
- Tests: `test/`, `tests/`, `__tests__/`, `spec/`, `*.test.*`, `*.spec.*`, `*_test.*`, `test_*.py`, `*_spec.rb`, `conftest.py`
- Config and build scripts: `*.config.*`, `setup.py`, `noxfile.py`, `*.gradle.kts`, `Package.swift`
- Build output and vendored code: `dist/`, `build/`, `out/`, `target/`, `node_modules/`, `vendor/`, `venv/`, `Pods/`, `__pycache__/`
