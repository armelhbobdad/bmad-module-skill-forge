---
shapeDetectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shape-detect.py'
  - '{project-root}/src/shared/scripts/skf-shape-detect.py'
---

# Shape Detection Reference

Reference document for invoking `skf-shape-detect.py` — the shared shape classification module. Loaded by `step-auto-scope.md` for auto-scope analysis.

## Invocation Contract

**Resolve `{shapeDetectHelper}`** from `{shapeDetectProbeOrder}`; first existing path wins. If neither resolves, step-auto-scope.md §3 HARD HALTs with exit code 3 (`resolution-failure`).

**Command** (step-auto-scope.md §3 runs it on the manifest scan and the file list §2 wrote to `{run_dir}/manifests-1.json` and `{run_dir}/tree.txt`):
```bash
uv run {shapeDetectHelper} --repo-url "<url>" --manifests-file "{run_dir}/manifests-1.json" --manifest-dir "{scan_root}" --tree-file "{run_dir}/tree.txt"
```

**Arguments:**

| Arg | Required | Description |
|-----|----------|-------------|
| `--repo-url` | Yes | Repository URL (context only — no cloning performed) |
| `--manifests-file` | One of the two | The JSON envelope `skf-scan-manifests.py scan` printed: the script keeps the manifest types it classifies (the supported manifests below) and resolves each `path` against `--manifest-dir`, so no caller filters, resolves or joins the list |
| `--manifest-dir` | With `--manifests-file` | The folder the scan ran on, the scan root |
| `--manifests` | One of the two | Comma-separated local file paths to manifest files, in place of `--manifests-file` (may be empty when a tree-level signal carries the classification) |
| `--tree-file` | No | The repository's whole file list, one path per line (`git ls-tree -r --name-only HEAD`, `git ls-files` or `find` output) or JSON. The script finds the tree-level signals in it itself (grammar files such as `*.y`, `*.g4`, `Grammar/python.gram` or a root `grammar.js`; a `compiler/` folder or a lexer+parser+ast triad), with its own gates, so no caller filters the list first |
| `--grammar-files`, `--tree-paths` | No | The older way to pass the same signals, harvested by the caller; not with `--tree-file` |

**Supported manifests:** `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Package.swift`

## Output Schema

JSON object on stdout:

| Field | Type | Description |
|-------|------|-------------|
| `shape` | string | `library-API` \| `reference-app` \| `language-reference` \| `stack-compose` \| `unknown` |
| `signals` | array[string] | Human-readable evidence strings |
| `confidence` | float | 0.0–1.0 |
| `export_count` | integer | Total public-facing exports detected |
| `package_count` | integer | Distinct packages detected |

## Exit Codes

| Code | Meaning | Consumer Action |
|------|---------|-----------------|
| 0 | Shape classified (not unknown) | Use shape result for scope mapping |
| 1 | Unknown shape (no heuristic matched) | Fall back to interactive mode: set the report's `mode: 'interactive'` first, so a resumed session takes the interactive chain |
| 2 | Error (invalid args, missing/unreadable files, parse failure) | HARD HALT with `resolution-failure` |

On exit code 2, error details are written to stderr as JSON: `{"error": "message", "code": "ERROR_CODE"}`

## Shape → Scope Type Mapping

| Shape | scope.type | Condition |
|-------|------------|-----------|
| `library-API` | `full-library` | export_count ≤ 200 |
| `library-API` | `public-api` | export_count > 200 (surface too large for full coverage) |
| `reference-app` | `reference-app` | Direct mapping — apps, CLIs, demos |
| `reference-app` with an `app_or_library:framework_dep` signal | `reference-app`, or the `library-API` mapping | The only app signal is a framework dependency, which a library that extends the framework declares too. An application or demo built on the framework stays `reference-app`; a library that extends or wraps the framework takes the `library-API` mapping (`full-library` or `public-api` by `export_count`). step-auto-scope.md §4 judges which |
| Any shape with a `language_or_user:parser_dep` signal | That shape's mapping, or `language-reference`'s | A parser library among the runtime dependencies (`parser_dep:`) fits a language built on it and a project that only reads its input with it alike. A repository that implements a language, DSL, query language or grammar on it (a compiler, an interpreter, a rule or template engine) takes `language-reference`; one that parses a data format, a config file, command-line text or source code in existing languages with it (an editor, a linter, code search or an indexer) keeps its shape. step-auto-scope.md §4 judges which |
| `language-reference` | `full-library` | Language tools/parsers are library-shaped from a skill perspective. **Corpora-dependent** for a *whole-language* reference (a `grammar_file:`/`tree_triad:` signal: a compiler/interpreter): its value is the language's prose (guide/Book + std/library docs), not compiler internals, so step-auto-scope-corpora.md, which step-auto-scope.md §6 loads for that signal, seeds companion corpora, and §6/§7 record an honest DEGRADED caveat when none are found (mirrors the §3b facet-coverage guard). A parser library, or a language built on one (`parser_producer:`/`parser_dep:`), is exempt: no `grammar_file:` or `tree_triad:` signal, so §6 seeds no corpora. |
| `stack-compose` | `full-library` | Decomposition candidate when `package_count > 3` — cohesion-checked in step-auto-scope.md §3b |
| `unknown` | N/A | Triggers fallback to interactive mode |

## Decomposition Thresholds

When auto-scope detects a multi-package monorepo, it may recommend multi-skill decomposition instead of producing one unwieldy skill. The threshold is evaluated in step-auto-scope.md §3a.

| Threshold | Value | Signal | Decomposition Path |
|-----------|-------|--------|-------------------|
| Multi-package / monorepo | `package_count > 3` | Shape detection `package_count` | Cohesion check (§3b): merge to one skill or split per package |

`package_count > 3` makes a **monorepo** a decomposition candidate; step-auto-scope.md §3b then decides merge-vs-split. It is empirically validated (fires on real 15-, 38-, and 442-package workspaces). A *single* package with a large API surface is **not** decomposed — it produces one cohesive skill that `skf-create-skill`'s auto-shard splits into `references/` shards at the 400-line ceiling.

When neither threshold is met, the single-scope flow proceeds unchanged.

## Heuristic Ladder

The five-shape heuristic ladder applies in order (first match wins):

1. **language-reference**: parser/grammar/language-toolchain project. Signals, strongest first: a hand-written-compiler tree structure (a dedicated `compiler/` directory with a lexer+parser+ast triad plus a codegen/VM/type-checker member, as in rustc, TypeScript, Go); a declared grammar file (`Grammar/python.gram`, a root `parse.y`, a `*.g4`, as in CPython, Ruby); or the repo's own name being a known parser/grammar tool (pest, lalrpop, lark: the producer). A parser library among the core members' runtime dependencies (the consumer) decides only when no rung below answers and no manifest declares a bin (a bare DSL manifest); otherwise the shape that answers carries the `language_or_user:parser_dep` question. Delegating consumers (formatters, linters, bundlers that depend on a parser) and markup/DSL parsers (CSS, markdown, GraphQL) are excluded.
2. **stack-compose** — multi-ecosystem composite project. Signals: manifests from 2+ distinct ecosystems
3. **reference-app** — application, CLI, or demo project. Signals: npm `bin` field, Rust `[[bin]]`, framework deps (next, fastapi, axum, etc.)
4. **library-API** — library exposing a programmatic API. Signals: `main`/`module`/`exports` fields, `[lib]` target, export count
5. **unknown** — no heuristic matched
