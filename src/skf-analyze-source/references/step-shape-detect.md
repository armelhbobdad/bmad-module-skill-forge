# Shape Detection Reference

Reference document for invoking `skf-shape-detect.py` — the shared shape classification module. Loaded by `step-auto-scope.md` for auto-scope analysis.

## Invocation Contract

**Script:** `src/shared/scripts/skf-shape-detect.py`

**Command:**
```
uv run python src/shared/scripts/skf-shape-detect.py --repo-url <url> --manifests <path1,path2,...>
```

**Arguments:**

| Arg | Required | Description |
|-----|----------|-------------|
| `--repo-url` | Yes | Repository URL (context only — no cloning performed) |
| `--manifests` | Yes | Comma-separated local file paths to manifest files |

**Supported manifests:** `package.json`, `pyproject.toml`, `Cargo.toml`

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
| `language-reference` | `full-library` | Language tools/parsers are library-shaped from a skill perspective |
| `stack-compose` | `full-library` | Multi-skill decomposition when `package_count > 3` `[PENDING VALIDATION]` — see step-auto-scope.md §3a |
| `unknown` | N/A | Triggers fallback to interactive mode |

## Decomposition Thresholds

When auto-scope detects a repo exceeding complexity thresholds, it recommends multi-skill decomposition instead of producing a single unwieldy skill. The thresholds are evaluated in step-auto-scope.md §3a.

| Threshold | Value | Signal | Decomposition Path |
|-----------|-------|--------|-------------------|
| Large export surface | `export_count > 500` `[PENDING VALIDATION]` | Shape detection `export_count` | Group by top-level source directory modules |
| Multi-package / monorepo | `package_count > 3` `[PENDING VALIDATION]` | Shape detection `package_count` | One skill per workspace package |

Both thresholds are marked `[PENDING VALIDATION]` — no empirical data exists yet for real-world repos. Expected tuning: after running deepwiki against 5–10 real repos, adjust thresholds based on whether decomposition produces useful skill boundaries or noise.

When both thresholds are met simultaneously, the monorepo path takes priority (package boundaries are explicit; export-count grouping is heuristic).

When neither threshold is met, the single-scope flow proceeds unchanged.

## Heuristic Ladder

The five-shape heuristic ladder applies in order (first match wins):

1. **language-reference** — parser/grammar/language-toolchain project. Signals: parser-related deps (pest, antlr4, tree-sitter, lark, etc.)
2. **stack-compose** — multi-ecosystem composite project. Signals: manifests from 2+ distinct ecosystems
3. **reference-app** — application, CLI, or demo project. Signals: npm `bin` field, Rust `[[bin]]`, framework deps (next, fastapi, axum, etc.)
4. **library-API** — library exposing a programmatic API. Signals: `main`/`module`/`exports` fields, `[lib]` target, export count
5. **unknown** — no heuristic matched
