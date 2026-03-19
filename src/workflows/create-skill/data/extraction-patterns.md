# Extraction Patterns by Tier

## Quick Tier (No AST)

Source reading via gh_bridge — infer exports from file structure and content.

### Strategy
1. `gh_bridge.list_tree(owner, repo, branch)` — map source structure
2. Identify entry points: index files, main exports, public modules
3. `gh_bridge.read_file(owner, repo, path)` — read each entry point
4. Extract: exported function names, parameter lists, return types (from signatures)
5. Infer types from JSDoc, docstrings, type annotations in source

### Confidence
- All results: T1-low (source reading without structural verification)
- No co-import detection available
- No AST-backed line numbers

### Supported Patterns
- `export function name(...)` / `export const name = ...` (JS/TS)
- `pub fn name(...)` (Rust)
- `def name(...)` with `__all__` (Python)
- `func Name(...)` (Go, capitalized = exported)

---

## Forge Tier (AST Available)

Structural extraction via ast-grep — verified exports with line-level citations.

> **Note:** `ast_bridge.*` and `qmd_bridge.*` references below are **conceptual interfaces**, not callable functions. They describe the operation to perform. Use ast-grep (MCP tool or CLI) for `ast_bridge.*` operations and QMD (MCP tool or CLI) for `qmd_bridge.*` operations. See the AST Extraction Protocol section below and the TOOL/SUBPROCESS FALLBACK rule for dispatch details.

### Strategy

1. Detect language from brief or file extensions
2. Use ast-grep to extract all exports from `path` for the given `language` (scan definitions)
3. For each export: function name, full signature, parameter types, return type, line number
4. Use ast-grep to detect co-imported symbols in `path` for the given `libraries[]`
5. Build extraction rules YAML for reproducibility

### Confidence
- Exported functions with full signatures: T1 (AST-verified)
- Type definitions and interfaces: T1
- Co-import patterns: T1
- Internal/private functions: excluded (not part of public API)

### ast-grep Patterns
- JS/TS: `export function $NAME($$$PARAMS): $RET` / `export const $NAME`
- Rust: `pub fn $NAME($$$PARAMS) -> $RET`
- Python: function definitions within `__all__` list
- Go: capitalized function definitions

---

## Deep Tier (AST + QMD)

Same extraction as Forge tier. Deep tier adds enrichment in step-04, not extraction.

### Strategy
- Identical to Forge tier extraction
- QMD enrichment happens in the next step (step-04-enrich)
- Extraction results carry forward unchanged

### Confidence
- Extraction: same as Forge (T1)
- Enrichment annotations added in step-04: T2

---

## AST Extraction Protocol

When AST tools are available (Forge/Deep tier), follow this deterministic protocol to prevent output overflow on large codebases.

**"Files in scope"** = files remaining after applying `include_patterns` and `exclude_patterns` from the brief, filtered by the target language extension. This is NOT the total repository file count from step-01's tree listing. Use the filtered count from step-03 section 2 as the decision tree input.

### Decision Tree

Apply the first matching condition:

```
Files in scope ≤ 100
  → Use ast-grep MCP tool: find_code(pattern, max_results=100, output_format="text")
  → Parse compact text output directly into extraction inventory

Files in scope 101–500
  → Use ast-grep MCP tool: find_code_by_rule(yaml, max_results=150, output_format="text")
  → Use scoped YAML rules (see recipes below) to filter at the AST level
  → Parse compact text output into extraction inventory

Files in scope > 500
  → CLI streaming fallback: ast-grep --json=stream + line-by-line Python processing
  → Process in directory batches, cap per-batch output
  → Merge batch results into extraction inventory
```

### Safety Valve

If any ast-grep operation (MCP or CLI) visibly causes a timeout, returns an error related to output size, or produces unexpectedly large output: immediately switch to the CLI streaming fallback with `--json=stream`. Do not retry the same approach. When falling back to the CLI streaming template, inject the brief's `scope.exclude` patterns into the `EXCLUDES` list (use `[]` if absent) — this applies regardless of which path triggered the fallback. Note: `max_results` in the MCP tool and `| head -N` in the CLI path provide hard caps, but this safety valve covers cases where the upstream tool itself fails before returning results (e.g., OOM during JSON serialization).

### MCP Tool Usage (Preferred)

**Simple pattern search:**

```
find_code(
  project_folder="{source_path}",
  pattern="async def $NAME($$$PARAMS)",
  language="python",
  max_results=100,
  output_format="text"
)
```

**Scoped YAML rule search (for larger repos):**

```
find_code_by_rule(
  project_folder="{source_path}",
  yaml="id: public-api\nlanguage: python\nrule:\n  pattern: 'def $NAME($$$PARAMS)'\n  inside:\n    kind: module\n    stopBy: end\nconstraints:\n  NAME:\n    regex: '^[^_]'",
  max_results=150,
  output_format="text"
)
```

### CLI Streaming Fallback

When MCP tools are unavailable or the repo exceeds 500 files in scope, use `--json=stream` (NEVER `--json` or `--json=pretty`) with line-by-line Python processing:

```bash
# Note: use $$$ for variadic params in ast-grep patterns (e.g., 'def $NAME($$$PARAMS)')
# {exclude_patterns} = Python list from brief's scope.exclude, e.g. ['tests/**', '**/test_*']
# If scope.exclude is absent or empty in the brief, inject [] as the default.
# Patterns are matched against the full file path as emitted by ast-grep.
# Ensure paths are relative to the same root as the patterns (strip ./ prefix if needed).
ast-grep -p '{pattern}' -l {language} --json=stream {path} | python3 -c "
import sys, json, fnmatch, signal
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

EXCLUDES = {exclude_patterns}

for line in sys.stdin:
    try:
        m = json.loads(line)
        f = m.get('file','')
        if EXCLUDES and any(fnmatch.fnmatch(f, pat) for pat in EXCLUDES):
            continue
        v = m.get('metaVariables',{})
        name = v.get('single',{}).get('NAME',{}).get('text','')
        if name and not name.startswith('_'):
            ln = m.get('range',{}).get('start',{}).get('line',0)+1
            sig = m.get('text','').split(chr(10))[0].strip()
            print(f'[AST:{f}:L{ln}] {sig}')
    except: pass
" | head -200
```

**Critical constraints:**

- ALWAYS use `--json=stream` — never `--json` (loads entire array into memory)
- ALWAYS process line-by-line (`for line in sys.stdin`) — never `json.load(sys.stdin)`
- ALWAYS cap output with `| head -N` as a safety valve
- For repos > 500 files, process in directory batches of 20-50 files each

### YAML Rule Recipes by Language

**Python — public functions:**

```yaml
id: python-public-functions
language: python
rule:
  pattern: 'def $NAME($$$PARAMS)'
  inside:
    kind: module
    stopBy: end
constraints:
  NAME:
    regex: '^[^_]'
```

**Python — public classes:**

```yaml
id: python-public-classes
language: python
rule:
  pattern: 'class $NAME($$$BASES)'
  inside:
    kind: module
    stopBy: end
constraints:
  NAME:
    regex: '^[^_]'
```

**JavaScript/TypeScript — exported functions:**

```yaml
id: js-exported-functions
language: typescript
rule:
  pattern: 'export function $NAME($$$PARAMS)'
```

**JavaScript/TypeScript — exported constants:**

```yaml
id: js-exported-constants
language: typescript
rule:
  pattern: 'export const $NAME = $VALUE'
```

**Rust — public functions:**

```yaml
id: rust-public-functions
language: rust
rule:
  any:
    - pattern: 'pub fn $NAME($$$PARAMS) -> $RET'
    - pattern: 'pub fn $NAME($$$PARAMS)'
```

**Go — exported functions (capitalized):**

```yaml
id: go-exported-functions
language: go
rule:
  pattern: 'func $NAME($$$PARAMS) $RET'
constraints:
  NAME:
    regex: '^[A-Z]'
```

### Re-Export Tracing

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

