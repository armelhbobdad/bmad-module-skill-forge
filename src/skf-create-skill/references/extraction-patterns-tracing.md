# Extraction Patterns: Tracing and File-Level Extraction

This file covers re-export tracing protocols and script/asset file-level extraction patterns. For core tier strategies and AST extraction protocol, see `extraction-patterns.md`.

---

## Re-Export Tracing

After initial AST extraction, some top-level exports may resolve to **module imports** rather than direct function definitions. This is common in Python libraries that use `__init__.py` re-exports for a clean public API.

**Detection heuristic:** For each top-level export from `__init__.py` (or equivalent entry point), check if the import path resolves to a directory (contains `__init__.py`) rather than a `.py` file with a matching `def` or `class`. If the initial AST scan found no function/class definition for a known public export, it is likely a module re-export.

**Tracing protocol:**

1. Read the entry point file (e.g., `{package}/__init__.py`) and extract all `from .X import Y` statements
2. For each import where Y was NOT found by the initial AST scan:
   - Check if the import path resolves to a directory (e.g., `{package}/api/v1/delete/` exists with `__init__.py`)
   - If directory: read its `__init__.py` to find the actual re-exported symbol
   - **Handle aliases:** Check for `from .module import A as B` patterns in the intermediate `__init__.py`. If the parent imports `B`, trace through to `A` in `.module`. If the parent imports `A` but the `__init__.py` only exports it as `B` (via `from .module import A as B`), match by original name `A` and note the alias
   - Trace the symbol to its definition file and run AST extraction on that file
3. Cite the actual definition location: `[AST:{definition_file}:L{line}]`

**Examples:**

```python
# Module re-export — follow required
from .api.v1.delete import delete    # delete/ is a directory → read delete/__init__.py

# Direct function import — no follow needed
from .api.v1.add.add import add      # add.py exists with def add()

# Aliased re-export — follow through alias
# In cognee/api/v1/visualize/__init__.py:
#   from .start_visualization_server import visualization_server
# In cognee/__init__.py:
#   from .api.v1.visualize import start_visualization_server
# → Match start_visualization_server against both definition names AND alias names
#   in the intermediate __init__.py to resolve the chain
```

**Unresolvable imports:** If the import statement is a star-import (`from .X import *`) or a conditional import (`try`/`except`), the symbol cannot be reliably traced via this protocol. Record it with `[SRC:{package}/__init__.py:L{line}]` (T1-low) and a note: "star/conditional import — manual trace required."

**Scope limit:** Only trace re-exports for symbols listed in the top-level entry point's public API. Do not recursively trace beyond one level of `__init__.py` indirection. If a re-export cannot be resolved after one level, record it with a `[SRC:{package}/__init__.py:L{line}]` citation (T1-low) from the import statement itself.

**Other languages:** JS/TS barrel files (`index.ts` with `export { X } from './module'`) follow the same principle — trace the re-export to the definition file. Rust `pub use` and Go package-level re-exports are less common but follow the same heuristic when encountered.

---

## Script/Asset Extraction Patterns

Scripts and assets are file-level artifacts, not code exports. They follow the **file-copy extraction method** — detected in source, copied with provenance citations.

### Detection Heuristics

**Script directories:** `scripts/`, `bin/`, `tools/`, `cli/`
**Asset directories:** `assets/`, `templates/`, `schemas/`, `configs/`, `examples/`

**Script file signals:**

| Signal                  | Strength | Pattern                                                                              |
|-------------------------|----------|--------------------------------------------------------------------------------------|
| Entry point declaration | Strong   | `package.json` `bin` field, Cargo.toml `[[bin]]`, pyproject.toml `[project.scripts]` |
| Shebang + executable    | Strong   | `#!/bin/bash`, `#!/usr/bin/env python`, `#!/usr/bin/env node`                        |
| CLI argument parser     | Moderate | `argparse`, `yargs`, `commander`, `cobra`, `clap` imports in file                    |
| Directory convention    | Moderate | File in `scripts/`, `bin/`, `tools/` directory                                       |
| CI/CD reference         | Moderate | Script referenced in `.github/workflows/*.yml`                                       |

**Asset file signals:**

| Signal           | Strength | Pattern                                             |
|------------------|----------|-----------------------------------------------------|
| JSON Schema      | Strong   | `*.schema.json`, file contains `"$schema"` key      |
| Config template  | Strong   | `*.example`, `*.template.*`, `*.sample` extension   |
| Official example | Moderate | File in `examples/` directory, referenced in README |
| OpenAPI/GraphQL  | Moderate | `openapi.json`, `*.graphql`, `swagger.yaml`         |
| Design tokens    | Weak     | `tokens.json`, `theme.json` in `assets/`            |

### Inclusion Rules

- Only include files within brief's `scope.include` patterns (or auto-detected directories)
- Exclude binary files (check extension: `.so`, `.dll`, `.jar`, `.wasm`, `.exe`)
- Exclude generated files (`dist/`, `build/`, `.webpack/` output)
- Exclude vendored/third-party files
- Flag files >500 lines for user confirmation (may be too large for skill package)
- If `scripts_intent` is absent from the brief, treat as `"detect"` (auto-detection is the default). If `scripts_intent` is explicitly `"none"`, skip scripts detection. Same rule applies to `assets_intent`.

### Provenance and Hashing

Each extracted file receives:
- Citation: `[SRC:{source_path}:L1]` (T1-low — file verified to exist but content not AST-analyzed)
- Content hash: SHA-256 of file content (for drift detection in audit-skill)
- Extraction method: `"file-copy"` (distinct from `"ast_bridge"` for code exports)

### Inventory Structure

**Script inventory entry:**
- `name`: filename (e.g., `validate-config.sh`)
- `source_file`: path relative to source root
- `purpose`: extracted from file header comments or README reference (if none found, use filename)
- `language`: detected from extension or shebang
- `content_hash`: SHA-256
- `confidence`: T1-low

**Asset inventory entry:**
- `name`: filename (e.g., `config-schema.json`)
- `source_file`: path relative to source root
- `purpose`: extracted from file header or schema `title`/`description` field
- `type`: `template`, `schema`, `config`, `example`
- `content_hash`: SHA-256
- `confidence`: T1-low
