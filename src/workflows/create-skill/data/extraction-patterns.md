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

> **Note:** `ast_bridge.*`, `qmd_bridge.*`, and `ccc_bridge.*` references below are **conceptual interfaces**, not callable functions. Resolve them as follows:
> - `ast_bridge.*` → ast-grep MCP tools (`mcp__ast-grep__find_code`, `mcp__ast-grep__find_code_by_rule`) or `ast-grep` CLI
> - `qmd_bridge.*` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI
> - `ccc_bridge.*` → `/ccc` skill (Claude Code), ccc MCP server (Cursor), or `ccc` CLI
> - `gh_bridge.*` → `gh api` commands or direct file I/O for local sources
>
> See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md) for the complete resolution table. Also see the AST Extraction Protocol section below and the TOOL/SUBPROCESS FALLBACK rule for dispatch details.

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

## Forge+ Tier (AST + CCC)

Identical extraction to Forge tier. CCC adds an upstream semantic discovery step that pre-ranks the file extraction queue.

### When CCC Pre-Discovery Applies

CCC pre-discovery runs in step-02b-ccc-discover (before this extraction step) when ALL of the following are true:
- Tier is Forge+ or Deep
- `tools.ccc: true` in forge-tier.yaml
- `ccc_index.status` is `"fresh"`, `"stale"`, `"created"`, or `"none"`/`"failed"` (step-02b attempts lazy indexing for the latter two)

The discovery step stores `{ccc_discovery: [{file, score, snippet}]}` in context. This extraction step consumes those results to pre-rank the file list.

### CCC Pre-Ranking Strategy

When `{ccc_discovery}` is present and non-empty:

1. Files appearing in `{ccc_discovery}` results move to the front of the extraction queue, sorted by relevance score descending
2. Files NOT in CCC results remain in the queue — they are not excluded, only deprioritized
3. If the CCC intersection with scoped files produces <10 files: include all scoped files (CCC results too narrow)
4. Proceed with the AST Extraction Protocol on the pre-ranked list

### ast-grep Patterns

Same patterns as Forge tier — see Forge tier section above. CCC pre-ranking does not change which AST patterns are used, only which files are processed first.

### Confidence

All results: T1 (AST-verified) — identical to Forge tier. CCC is upstream discovery only and is invisible in the output artifact.

### Important

CCC pre-discovery failures (ccc unavailable, command error, empty results) always result in standard Forge extraction behavior. This is not reported to the user as a problem — it is normal behavior when ccc has no relevant results for the skill's scope.

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

### Re-Export Tracing and Script/Asset Extraction

See `extraction-patterns-tracing.md` for:
- **Re-export tracing protocol** — resolving module imports through `__init__.py`, barrel files, `pub use`
- **Script/asset extraction patterns** — detection heuristics, inclusion rules, provenance, inventory structure

