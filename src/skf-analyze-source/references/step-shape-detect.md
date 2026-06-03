# Shape Detection Reference

Reference document for invoking `skf-shape-detect.py` — the shared shape classification module. Loaded by `step-auto-scope.md` for auto-scope analysis.

## Invocation Contract

**Script:** `src/shared/scripts/skf-shape-detect.py`

**Command:**
```
uv run src/shared/scripts/skf-shape-detect.py --repo-url <url> \
  --manifests <path1,path2,...> \
  --grammar-files <g1,g2,...> --tree-paths <d1/,d2/,file,...>
```

**Arguments:**

| Arg | Required | Description |
|-----|----------|-------------|
| `--repo-url` | Yes | Repository URL (context only — no cloning performed) |
| `--manifests` | Yes | Comma-separated local file paths to manifest files (may be empty when a tree-level signal carries the classification) |
| `--grammar-files` | No | Comma-separated repo-relative grammar files (`*.y`, `*.g4`, `*.pest`, `Grammar/python.gram`, ...) — a whole-language signal |
| `--tree-paths` | No | Comma-separated repo-relative directory (trailing `/`) and structural file signals harvested from the clone (a `compiler/` dir, a lexer+parser+ast triad) |

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
| 1 | Unknown shape (no heuristic matched) | Fall back to interactive mode |
| 2 | Error (invalid args, missing/unreadable files, parse failure) | HARD HALT with `resolution-failure` |

On exit code 2, error details are written to stderr as JSON: `{"error": "message", "code": "ERROR_CODE"}`

## Shape → Scope Type Mapping

| Shape | scope.type | Condition |
|-------|------------|-----------|
| `library-API` | `full-library` | export_count ≤ 200 |
| `library-API` | `public-api` | export_count > 200 (surface too large for full coverage) |
| `reference-app` | `reference-app` | Direct mapping — apps, CLIs, demos |
| `language-reference` | `full-library` | Language tools/parsers are library-shaped from a skill perspective. **Corpora-dependent** for a *whole-language* reference (a `grammar_file:`/`tree_triad:` signal — a compiler/interpreter): its value is the language's prose (guide/Book + std/library docs), not compiler internals, so step-auto-scope.md §6b seeds companion corpora and §6/§7 record an honest DEGRADED caveat when none are found (mirrors the §3b facet-coverage guard). A parser *library* (`parser_producer:`/`parser_dep:`) is exempt — its code is the product. |
| `stack-compose` | `full-library` | Decomposition candidate when `package_count > 3` — cohesion-checked in step-auto-scope.md §3b |
| `unknown` | N/A | Triggers fallback to interactive mode |

## Decomposition Thresholds

When auto-scope detects a repo exceeding complexity thresholds, it recommends multi-skill decomposition instead of producing a single unwieldy skill. The thresholds are evaluated in step-auto-scope.md §3a.

| Threshold | Value | Signal | Decomposition Path |
|-----------|-------|--------|-------------------|
| Large export surface | `export_count > 500` `[PENDING VALIDATION]` | Shape detection `export_count` | Group by top-level source directory modules |
| Multi-package / monorepo | `package_count > 3` | Shape detection `package_count` | Cohesion check (§3b): merge to one skill or split per package |

A threshold firing makes a repo a decomposition **candidate**; step-auto-scope.md §3b then decides merge-vs-split. `package_count > 3` is empirically validated (fires on real 15-, 38-, and 442-package workspaces). `export_count > 500` stays `[PENDING VALIDATION]` — not yet observed firing on a real run.

When both thresholds are met simultaneously, the monorepo path takes priority (package boundaries are explicit; export-count grouping is heuristic).

When neither threshold is met, the single-scope flow proceeds unchanged.

## Heuristic Ladder

The five-shape heuristic ladder applies in order (first match wins):

1. **language-reference** — parser/grammar/language-toolchain project. Signals, strongest first: a hand-written-compiler tree structure (a dedicated `compiler/` directory with a lexer+parser+ast triad plus a codegen/VM/type-checker member — catches rustc, TypeScript, Go); a declared grammar file (`Grammar/python.gram`, a root `parse.y`, a `*.g4` — catches CPython, Ruby); the repo's own name being a known parser/grammar tool (pest, lalrpop, lark — the producer); or a parser-generator dependency (a DSL built on antlr4/lalrpop — the consumer). Delegating consumers (formatters, linters, bundlers that depend on a parser) and markup/DSL parsers (CSS, markdown, GraphQL) are excluded.
2. **stack-compose** — multi-ecosystem composite project. Signals: manifests from 2+ distinct ecosystems
3. **reference-app** — application, CLI, or demo project. Signals: npm `bin` field, Rust `[[bin]]`, framework deps (next, fastapi, axum, etc.)
4. **library-API** — library exposing a programmatic API. Signals: `main`/`module`/`exports` fields, `[lib]` target, export count
5. **unknown** — no heuristic matched
