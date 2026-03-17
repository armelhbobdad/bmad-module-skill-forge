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

Structural extraction via ast_bridge — verified exports with line-level citations.

### Strategy
1. Detect language from brief or file extensions
2. `ast_bridge.scan_definitions(path, language)` — extract all exports
3. For each export: function name, full signature, parameter types, return type, line number
4. `ast_bridge.detect_co_imports(path, libraries[])` — find integration points
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

If any ast-grep operation (MCP or CLI) visibly causes a timeout, returns an error related to output size, or produces unexpectedly large output: immediately switch to the CLI streaming fallback with `--json=stream`. Do not retry the same approach. Note: `max_results` in the MCP tool and `| head -N` in the CLI path provide hard caps, but this safety valve covers cases where the upstream tool itself fails before returning results (e.g., OOM during JSON serialization).

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
ast-grep -p '{pattern}' -l {language} --json=stream {path} | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        m = json.loads(line)
        v = m.get('metaVariables',{})
        name = v.get('single',{}).get('NAME',{}).get('text','')
        if name and not name.startswith('_'):
            f = m.get('file','')
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

---

## Tier Degradation Rules

### Remote Source at Forge/Deep Tier

When `source_repo` is a remote URL (GitHub URL or owner/repo format) and the tier is Forge or Deep:

- **ast-grep requires local files** — it cannot operate on remote URLs

**Ephemeral clone strategy (preferred):**

1. Check `git` availability (`git --version`). `git` is effectively guaranteed at Deep tier (via `gh` dependency) but NOT guaranteed at Forge tier.
2. If `git` is available: perform an ephemeral shallow clone to a system temp path (`{system_temp}/skf-ephemeral-{skill-name}-{timestamp}/`).
3. For create-skill: use `--depth 1 --single-branch --filter=blob:none`; if `include_patterns` are specified, convert glob patterns to directory roots before passing to `sparse-checkout set` — `git sparse-checkout` expects directories, not globs. Use `--skip-checks` when any individual file paths (no glob characters) are present. Apply original glob patterns as file-level filters after checkout. See step-03-extract.md for the full conversion rules.
4. For update-skill: use sparse-checkout with `--skip-checks` scoped to the changed files from the change manifest only (file paths require `--skip-checks`). No `--branch` flag — uses the remote default branch (must match the branch used during original create-skill run).
5. If clone succeeds: use the local clone path for AST extraction. All results are T1 with `[AST:...]` citations.
6. Cleanup: delete the temp directory after extraction inventory is built and all data is in context. The clone never persists beyond the extraction step.

**Fallback (clone fails or `git` unavailable):**

- The extraction step MUST warn the user explicitly before degrading
- **create-skill:** Warning must include actionable guidance — clone locally and update `source_repo` in the brief to the local path
- **update-skill:** Warning must include actionable guidance — clone locally, re-run [CS] Create Skill with the local path to regenerate provenance data, then re-run the update
- Extraction proceeds using Quick tier strategy (source reading via gh_bridge)
- All results labeled T1-low with `[SRC:...]` citations
- The degradation reason is recorded in the evidence report

Silent degradation is **forbidden**. The user must always know when AST extraction was skipped and why.

### AST Tool Unavailable at Forge/Deep Tier

When the tier is Forge or Deep but ast-grep is not functional:

- The extraction step MUST warn the user explicitly before degrading
- Warning must include actionable guidance: run [SF] Setup Forge to detect tools
- Extraction proceeds using Quick tier strategy
- All results labeled T1-low
- The degradation reason is recorded in the evidence report

### Per-File AST Failure

When ast-grep fails on an individual file (parse error, unsupported syntax):

- Fall back to source reading for **that file only**
- Other files continue with AST extraction
- The affected file's results are labeled T1-low; unaffected files retain T1
- Log a warning noting which file degraded and why
