# Shape Detection Reference

## Judged Signals

| Shape | scope.type | Condition |
|-------|------------|-----------|
| `reference-app` with an `app_or_library:framework_dep` signal | An app: the printed `scope_type` (`reference-app`). A library: `full-library`, or `public-api` over 200 exports | The only app signal is a framework dependency, which a library that extends the framework declares too. An application or demo built on the framework stays `reference-app`; a library that extends or wraps the framework takes `library-API`. step-auto-scope.md §4 judges which |
| Any shape with a `language_or_user:parser_dep` signal | A language: `full-library`. Otherwise the printed `scope_type` | A parser library among the runtime dependencies (`parser_dep:`) fits a language built on it and a project that only reads its input with it alike. A repository that implements a language, DSL, query language or grammar on it (a compiler, an interpreter, a rule or template engine) takes `language-reference`; one that parses a data format, a config file, command-line text or source code in existing languages with it (an editor, a linter, code search or an indexer) keeps its shape. step-auto-scope.md §4 judges which |

## Heuristic Ladder

The five-shape heuristic ladder applies in order (first match wins):

1. **language-reference**: parser/grammar/language-toolchain project. Signals, strongest first: a hand-written-compiler tree structure (a dedicated `compiler/` directory with a lexer+parser+ast triad plus a codegen/VM/type-checker member, as in rustc, TypeScript, Go); a declared grammar file (`Grammar/python.gram`, a root `parse.y`, a `*.g4`, as in CPython, Ruby); or the repo's own name being a known parser/grammar tool (pest, lalrpop, lark: the producer). A parser library among the core members' runtime dependencies (the consumer) decides only when no rung below answers and no manifest declares a bin (a bare DSL manifest); otherwise the shape that answers carries the `language_or_user:parser_dep` question. Delegating consumers (formatters, linters, bundlers that depend on a parser) and markup/DSL parsers (CSS, markdown, GraphQL) are excluded.
2. **stack-compose** — multi-ecosystem composite project. Signals: manifests from 2+ distinct ecosystems
3. **reference-app** — application, CLI, or demo project. Signals: npm `bin` field, Rust `[[bin]]`, framework deps (next, fastapi, axum, etc.)
4. **library-API** — library exposing a programmatic API. Signals: `main`/`module`/`exports` fields, `[lib]` target, export count
5. **unknown** — no heuristic matched
