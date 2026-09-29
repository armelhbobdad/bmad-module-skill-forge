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
- Every export is read by eye, so every entry is T1-low (source reading without structural verification): a `[SRC:...]` citation, `extraction_method: source-read` and `ast_node_type: null`
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
> - `qmd_bridge.*` → QMD MCP `query` tool (`mcp__plugin_qmd-plugin_qmd__query`) taking `searches=[{type:'lex'|'vec'|'hyde', query, intent}]`, or `qmd` CLI (`qmd search` / `qmd vector-search`). The legacy `vector_search` MCP tool has been removed; if a client surfaces a tool-not-found error, degrade gracefully per the QMD step 4 tool-probe note — do not retry the stale name.
> - `ccc_bridge.*` → `/ccc` skill (Claude Code), ccc MCP server (Cursor), or `ccc` CLI
> - `gh_bridge.*` → `gh api` commands or direct file I/O for local sources
>
> See `knowledge/tool-resolution.md` for the complete resolution table. Also see the AST Extraction Protocol section below and the TOOL/SUBPROCESS FALLBACK rule for dispatch details.

### Strategy

1. Detect language from brief or file extensions
2. Use ast-grep to extract all exports from `path` for the given `language` (scan definitions)
3. For each export: function name, full signature, parameter types, return type, line number
4. Use ast-grep to detect co-imported symbols in `path` for the given `libraries[]`
5. Build extraction rules YAML for reproducibility

### Confidence
- Each entry is labeled by the tool that produced it, not by the tier:
  - An export an ast-grep rule matched (a function with its full signature, a type definition, an interface): T1 (AST-verified), an `[AST:...]` citation, `extraction_method: ast-grep` and `ast_node_type` set to the `kind` the matching pattern or recipe declares (see the patterns below)
  - An export read by eye (ast-grep could not parse its file, the rules missed it, or the file was read instead of matched): T1-low, a `[SRC:...]` citation, `extraction_method: source-read` and `ast_node_type: null`
- Co-import patterns ast-grep detected: T1
- Internal/private functions: excluded (not part of public API)

### ast-grep Patterns

Each export shape below is matched by one recipe from the YAML Rule Recipes further down: its `id` is what the entry records as `ast_recipe`, and the `kind` it declares is what the entry records as `ast_node_type`. ast-grep's output never reports the kind of a match, so an export never records a kind guessed from the source.

| Export shape | Recipe (`ast_recipe`) | Kind (`ast_node_type`) |
|---|---|---|
| Python: a module-level `def` or `async def` | `python-public-functions` | `function_definition` |
| Python: a module-level `class` | `python-public-classes` | `class_definition` |
| JS/TS: a top-level `export function` (async, generator, generic, each overload signature, `export default function Name`, `export declare function`) | `js-exported-functions` | `export_statement` |
| JS/TS: `export const NAME = ...` | `js-exported-constants` | `export_statement` |
| JS/TS: `export const NAME = (...) => ...` | `js-exported-arrow-functions` | `export_statement` |
| JS/TS: `export class` | `js-exported-classes` | `export_statement` |
| JS/TS: each name of `export { a, b as c } from '...'` | `js-reexports` | `export_specifier` |
| JS/TS: `export * as ns from '...'` | `js-namespace-reexports` | `export_statement` |
| Rust: a top-level `pub fn`, outside `impl` blocks | `rust-public-functions` | `function_item` |
| Go: an exported function, not a method | `go-exported-functions` | `function_declaration` |
| React: `export interface NameProps` | `react-props-interfaces` | `export_statement` |
| React: a PascalCase `export function` | `react-component-functions` (`react-component-exports` in `component-extraction.md`) | `export_statement` |
| React: a PascalCase `export const Name = (...) => ...` | `react-component-arrow-functions` | `export_statement` |
| Vue: a top-level `defineProps<T>()` | `vue-define-props` (`vue-define-props-tsx` for `<script setup lang="tsx">`) | `call_expression` |

- Python: decorated or not, generic or not, including under a module-level `if` / `try` / `with` / `for` / `while` / `match`, never a method or a nested `def`, and only names that do not start with `_`. A definition directly under an `if __name__ == "__main__":` guard does not match, but one under `elif __name__ == "__main__":` or a compound guard still does (Known Limitation #11). A decorated `def` matches at its `def` line, not as `decorated_definition`. The recipes do not read `__all__`.
- Rust: a pattern such as `pub fn $NAME($$$PARAMS)` parses as a bodyless `function_signature_item` and finds no function definition (Known Limitation #8): only the recipe finds them.
- A `find_code` pattern is only the fallback of Known Limitation #4: an export it matched records the pattern as `ast_recipe` and the kind of its shape from this table.

---

## Forge+ Tier (AST + CCC)

Identical extraction to Forge tier. CCC adds an upstream semantic discovery step that pre-ranks the file extraction queue.

### When CCC Pre-Discovery Applies

CCC pre-discovery runs in ccc-discover (before this extraction step) when ALL of the following are true:
- Tier is Forge+ or Deep
- `tools.ccc: true` in forge-tier.yaml
- The source index is available: step 2b searches with `--refresh` when `ccc_index.status` is `"fresh"`, `"created"`, `"skipped"` or a status it does not know (such as a `"stale"` an older SKF recorded), and first attempts lazy indexing when it is `"none"` or `"failed"`

The discovery step stores `{ccc_discovery: [{file, score, snippet}]}` in context. This extraction step consumes those results to pre-rank the file list.

### CCC Pre-Ranking Strategy

When `{ccc_discovery}` is present and non-empty:

1. Files appearing in `{ccc_discovery}` results move to the front of the extraction queue, sorted by relevance score descending
2. Files not in CCC results remain in the queue — they are not excluded, only deprioritized
3. If the CCC intersection with scoped files produces <10 files: include all scoped files (CCC results too narrow)
4. Proceed with the AST Extraction Protocol on the pre-ranked list

### ast-grep Patterns

Same patterns as Forge tier — see Forge tier section above. CCC pre-ranking does not change which AST patterns are used, only which files are processed first.

### Confidence

Labeled by tool, exactly as at Forge tier: an export an ast-grep rule matched is T1 (AST-verified), an export read by eye is T1-low. CCC is upstream discovery only and is invisible in the output artifact.

### Important

CCC pre-discovery failures (ccc unavailable, command error, empty results) always result in standard Forge extraction behavior. This is not reported to the user as a problem — it is normal behavior when ccc has no relevant results for the skill's scope.

---

## Deep Tier (AST + QMD)

Same extraction as Forge tier. Deep tier adds enrichment in step 4, not extraction.

### Strategy
- Identical to Forge tier extraction
- QMD enrichment happens in the next step (enrich)
- Extraction results carry forward unchanged

### Confidence
- Extraction: labeled by tool, same as Forge (T1 for an ast-grep match, T1-low for an export read by eye)
- Enrichment annotations added in step 4: T2

---

## AST Extraction Protocol

When AST tools are available (Forge/Deep tier), follow this deterministic protocol to prevent output overflow on large codebases.

**"Files in scope"** = files remaining after applying `include_patterns` and `exclude_patterns` from the brief, filtered by the target language extension. This is not the total repository file count from step 1's tree listing. Use the filtered count from step 3 section 2 as the decision tree input.

### Decision Tree

Apply the first matching condition:

```
.vue files (the Vue recipes), at any scope size
  → CLI streaming with -c {scratch}/sgconfig.yml (find_code_by_rule cannot read them; see the Vue note)

Files in scope ≤ 500
  → Use ast-grep MCP tool: find_code_by_rule(yaml=<recipe>, max_results=150, output_format="json")
  → Run every recipe for the language (see recipes below), one call per recipe
  → Read $NAME (and $SOURCE) from each match's metaVariables, and its line from $NAME
  → Merge the matches into extraction inventory

Files in scope > 500
  → CLI streaming: ast-grep scan -r {recipe_file} --json=stream + line-by-line Python processing
  → Process in directory batches, cap per-batch output
  → Merge batch results into extraction inventory
```

### Safety Valve

If any ast-grep operation (MCP or CLI) visibly causes a timeout, returns an error related to output size, or produces unexpectedly large output: immediately switch to the CLI streaming template (`ast-grep scan -r {recipe_file} --json=stream`, in directory batches). Do not retry the same approach. When falling back to the CLI streaming template, inject the brief's `scope.exclude` patterns into the `EXCLUDES` list (use `[]` if absent); this applies regardless of which path triggered the fallback. Note: `max_results` in the MCP tool and `| head -N` in the CLI path provide hard caps, but this safety valve covers cases where the upstream tool itself fails before returning results (e.g., OOM during JSON serialization).

### MCP Tool Usage (Preferred)

**Recipe search (up to 500 files in scope):**

```
find_code_by_rule(
  project_folder="{source_path}",
  yaml="id: public-api\nlanguage: python\nrule:\n  pattern: 'def $NAME'\n  kind: function_definition\n  inside:\n    kind: module\n    stopBy:\n      any:\n        - kind: function_definition\n        - kind: class_definition\n  not:\n    inside:\n      kind: block\n      stopBy: end\n      inside:\n        kind: if_statement\n        has:\n          field: condition\n          regex: '^\\(?\\s*(__name__\\s*==\\s*[''\"]__main__[''\"]|[''\"]__main__[''\"]\\s*==\\s*__name__)\\s*\\)?$'\nconstraints:\n  NAME:\n    regex: '^[^_]'",
  max_results=150,
  output_format="json"
)
```

The `yaml` string carries the rule and constraints of the `python-public-functions` recipe below as a JSON string: `\n` for each line break, `\"` for each quote and `\\` for each backslash. Ask for `output_format="json"`: each match then carries `metaVariables.single.NAME` (and `SOURCE` for the re-export recipes), and its line is `$NAME`'s line (see the line-number rule below). `output_format="text"` gives only the match's text and first line, which loses `$NAME` and `$SOURCE` for a re-exported name (`js-reexports`, `js-namespace-reexports`) and cites the wrong line when `$NAME` is not on the match's first line: a decorated class (the match starts at the decorator), or an `export default` or `export function` split over lines.

**Simple pattern search (fallback only):**

```
find_code(
  project_folder="{source_path}",
  pattern="async def $NAME($$$PARAMS)",
  language="python",
  max_results=100,
  output_format="text"
)
```

`find_code` takes a pattern and no `kind` or relational clauses, so it cannot keep a recipe's scope: methods, nested and private definitions come back too. Use it only as Known Limitation #4's fallback, and record the kind of the pattern's shape from the ast-grep Patterns table above (`function_definition` here, since an `async def` is a `function_definition`).

### CLI Streaming Fallback

When MCP tools are unavailable or the repo exceeds 500 files in scope, use `--json=stream` (not `--json` or `--json=pretty`, which load the whole result set into memory) with line-by-line Python processing:

**Head cap selection:** The `| head -N` cap at the end of the pipeline controls how many exports are captured. Select `N` based on scope and tier:
- **Default (Quick/Forge, any scope):** `N = 200`
- **Forge+/Deep with `scope.type: "full-library"`:** `N = 500`
- **Forge+/Deep with `scope.type: "component-library"`:** `N = 300` (components have fewer but richer exports; props interfaces are the primary API surface)

For full-library skills at higher tiers, the larger cap prevents silently dropping internal module exports that maintainers need. The cap is applied AFTER exclude-pattern filtering, so useful results are not wasted on excluded files.

```bash
# {recipe_file} = a file holding one recipe's YAML, written in a scratch folder, never in
# the source tree. Do not pass a recipe inline in single quotes: its regexes are quoted.
# {recipe_id} = the recipe's `id`, recorded as each printed export's ast_recipe.
# {node_kind} = the `kind` the recipe declares (such as 'function_definition' for
# python-public-functions). ast-grep's JSON never reports the kind of a match, so the
# template prints this one, and each printed export records it as its ast_node_type.
# For .vue files add -c {scratch}/sgconfig.yml (see the Vue note under the recipes).
# {exclude_patterns} = Python list from brief's scope.exclude, e.g. ['tests/**', '**/test_*']
# If scope.exclude is absent or empty in the brief, inject [] as the default.
# Patterns are matched against the full file path as emitted by ast-grep.
# Ensure paths are relative to the same root as the patterns (strip ./ prefix if needed).
# {HEAD_CAP} = 200 (default) or 500 (Forge+/Deep full-library) — see head cap selection above.
# L{ln} is $NAME's line, not the match's first line (a decorated class starts at its
# decorator), and {sig} is the line of the match that holds $NAME.
ast-grep scan -r {recipe_file} --json=stream {path} | python3 -c "
import sys, json, fnmatch, signal
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

EXCLUDES = {exclude_patterns}
RECIPE = '{recipe_id}'
KIND = '{node_kind}'

for line in sys.stdin:
    try:
        m = json.loads(line)
        f = m.get('file','')
        if EXCLUDES and any(fnmatch.fnmatch(f, pat) for pat in EXCLUDES):
            continue
        v = m.get('metaVariables',{}).get('single',{})
        name = v.get('NAME',{}).get('text','')
        if name and not name.startswith('_'):
            ln = v['NAME'].get('range',{}).get('start',{}).get('line',0)+1
            first = m.get('range',{}).get('start',{}).get('line',0)+1
            text = m.get('text','').split(chr(10))
            sig = text[min(ln-first, len(text)-1)].strip()
            src = v.get('SOURCE',{}).get('text','')
            print(f'[AST:{f}:L{ln}] {RECIPE} kind={KIND} name={name}' + (f' from={src}' if src else '') + f' {sig}')
    except: pass
" | head -{HEAD_CAP}
```

**Streaming constraints (these prevent OOM on large result sets):**

- Use `--json=stream`, not `--json` — the latter loads the entire array into memory
- Process line-by-line (`for line in sys.stdin`), not `json.load(sys.stdin)`
- Cap output with `| head -N` as a safety valve
- For repos > 500 files, process in directory batches of 20-50 files each: split by top-level source directory, run the CLI streaming template per batch with the same head cap, then merge results and deduplicate by export name and file, keeping the first line (overload signatures and definitions in both branches of an `if` repeat a name within one file)

**Line numbers are 0-based in ast-grep JSON.** `range.start.line` counts from 0 in the CLI's `--json` and `--json=stream` output and in the JSON the MCP tools `find_code` / `find_code_by_rule` return with `output_format="json"`, so the template adds 1 to it to get the 1-based line an editor shows. Take the line from `$NAME`: every `[AST:{file}:L{line}]` citation and every provenance `source_line` is `metaVariables.single.NAME.range.start.line + 1`, the line that names the export, not the match's own `range.start.line`, which for a decorated class is the decorator's line and for an `export default` split over two lines is the `export` line. A line taken from the JSON without the `+1` points one line above it. The text output of the CLI and of the MCP tools is already 1-based, but gives only the match's first line.

### YAML Rule Recipes by Language

Every recipe's `rule` declares `kind`, the kind of the node it matches, and captures the export's own name as `$NAME`; each was verified on ast-grep 0.45.3 against fixtures holding the forms it must find and the forms it must skip. A JS/TS export recipe matches the whole `export_statement`, not the declaration inside it, except `js-reexports`, which matches each `export_specifier`; a pattern without `export`, such as the type-alias workaround `type $NAME = $T` (#9), matches the declaration itself (`type_alias_declaration`), even inside an `export type`. A decorated Python `def` matches the inner `function_definition`, not `decorated_definition`. ast-grep's JSON output never reports the kind of a match, so an export a recipe matched records the recipe's `kind` as its `ast_node_type`.

Most recipes are relational rules (`inside`, `has`, `not`) rather than one pattern, so pass a recipe whole: to `find_code_by_rule`, or as the CLI streaming template's `{recipe_file}`. Never drop the `kind`: without it, ast-grep rejects a pattern that is not a whole statement on its own, such as `def $NAME`. A recipe can match one name more than once (each overload signature, a `def` in both branches of an `if`), so merge its matches by name and file. Known Limitation #11 lists the forms each recipe deliberately does not cover.

**Python — public functions:**

```yaml
id: python-public-functions
language: python
rule:
  pattern: 'def $NAME'
  kind: function_definition
  inside:
    kind: module
    stopBy:
      any:
        - kind: function_definition
        - kind: class_definition
  not:
    inside:
      kind: block
      stopBy: end
      inside:
        kind: if_statement
        has:
          field: condition
          regex: '^\(?\s*(__name__\s*==\s*[''"]__main__[''"]|[''"]__main__[''"]\s*==\s*__name__)\s*\)?$'
constraints:
  NAME:
    regex: '^[^_]'
```

> **Scope note:** Both Python recipes match module-level definitions only. Their `inside: module` clause stops at the first enclosing `def` or `class`, so a method, a nested `def` and a nested class never match, while a definition under a module-level `if`, `try`, `with`, `for`, `while` or `match` (`if TYPE_CHECKING:` included) does. The `not:` clause drops a definition under `if __name__ == "__main__":` (or `"__main__" == __name__`, with or without parentheses), which exists only when the file runs as a script; the `else:` branch of that `if` still matches, and so does a definition under an `elif __name__ == "__main__":` or a compound guard (#11). The function pattern is `def $NAME`, not `def $NAME($$$PARAMS)`: in a PEP 695 generic `def name[T](...)` the type parameters sit between the name and the parameters, so the longer pattern misses it (#7). Neither recipe reads `__all__`.

**Python — public classes:**

```yaml
id: python-public-classes
language: python
rule:
  pattern: 'class $NAME'
  kind: class_definition
  inside:
    kind: module
    stopBy:
      any:
        - kind: function_definition
        - kind: class_definition
  not:
    inside:
      kind: block
      stopBy: end
      inside:
        kind: if_statement
        has:
          field: condition
          regex: '^\(?\s*(__name__\s*==\s*[''"]__main__[''"]|[''"]__main__[''"]\s*==\s*__name__)\s*\)?$'
constraints:
  NAME:
    regex: '^[^_]'
```

> **Pattern note:** The minimal `class $NAME` pattern, with `kind: class_definition`, matches every class, with or without bases, keywords, decorators or PEP 695 type parameters. The `class $NAME($$$BASES)` and `class $NAME($$$BASES):` variants return zero (see Known Limitations #7). A bare `ast-grep run -p 'class $NAME' -l python` also returns classes nested in a class or a function, since a pattern alone cannot carry the module-level scope: run the recipe as a rule file instead.

**JavaScript/TypeScript — exported functions:**

> **Language selection:** Use `language: typescript` for `.ts`, `.mts`, `.cts` and `.d.ts` files and `language: tsx` for `.tsx` files. They use different tree-sitter parsers, and a rule scans only the files of its own language, so for a mixed codebase run each recipe once per language, changing only `language`, and merge the results. For `.js`, `.jsx`, `.mjs` and `.cjs` files use `language: javascript`: `js-exported-constants`, `js-exported-arrow-functions`, `js-exported-classes`, `js-reexports`, `js-namespace-reexports` and `react-component-arrow-functions` run unchanged, `js-exported-functions` and `react-component-functions` have `javascript` forms below (ast-grep rejects their TypeScript forms there, since `function_signature` and `ambient_declaration` are not JavaScript kinds), and `react-props-interfaces` is TypeScript only.

```yaml
id: js-exported-functions
language: typescript  # Use 'tsx' for .tsx files; the javascript form below for .js
rule:
  kind: export_statement
  inside:
    kind: program
  any:
    - has:
        field: declaration
        any:
          - kind: function_declaration
          - kind: generator_function_declaration
          - kind: function_signature
        has:
          field: name
          pattern: $NAME
    - has:
        field: declaration
        kind: ambient_declaration
        has:
          kind: function_signature
          has:
            field: name
            pattern: $NAME
  not:
    has:
      field: declaration
      any:
        - kind: function_declaration
        - kind: generator_function_declaration
    follows:
      stopBy:
        not:
          kind: comment
      kind: export_statement
      has:
        field: declaration
        kind: function_signature
```

> **Overloads, defaults and scope:** Each overload signature matches, all with the same `$NAME`, and the implementation after them does not, since callers see only the signatures: the `not:` clause looks at the nearest statement before the implementation that is not a comment. Async, generator and generic functions match, and so do `export default function Name` (with `Name` as `$NAME`) and `export declare function`. The `inside: program` clause keeps the recipe to top-level exports, so an `export function` inside a `namespace`, `declare module` or `declare global` block does not match.

**JavaScript: exported functions (`.js`, `.jsx`, `.mjs`, `.cjs`):**

```yaml
id: js-exported-functions
language: javascript
rule:
  kind: export_statement
  inside:
    kind: program
  has:
    field: declaration
    any:
      - kind: function_declaration
      - kind: generator_function_declaration
    has:
      field: name
      pattern: $NAME
```

**JavaScript/TypeScript — exported constants:**

```yaml
id: js-exported-constants
language: typescript
rule:
  kind: export_statement
  inside:
    kind: program
  has:
    field: declaration
    kind: lexical_declaration
    all:
      - has:
          field: kind
          regex: '^const$'
      - has:
          kind: variable_declarator
          all:
            - has:
                field: name
                kind: identifier
                pattern: $NAME
            - has:
                field: value
                pattern: $VALUE
```

**JavaScript/TypeScript — exported arrow functions:**

```yaml
id: js-exported-arrow-functions
language: typescript
rule:
  kind: export_statement
  inside:
    kind: program
  has:
    field: declaration
    kind: lexical_declaration
    all:
      - has:
          field: kind
          regex: '^const$'
      - has:
          kind: variable_declarator
          all:
            - has:
                field: name
                kind: identifier
                pattern: $NAME
            - has:
                field: value
                kind: arrow_function
                pattern: $VALUE
```

> **JS/TS Pattern Merging:** Modern TypeScript codebases often use `export const` exclusively for all exports (arrow functions, objects, constants). Run all the JS/TS recipes (functions, arrow functions, constants, classes, re-exports) and merge results by `$NAME`. Priority when deduplicating: arrow function match > function declaration match > constant match. Both `const` recipes bind the declarator's value as `$VALUE`: for an arrow-function match that is the whole arrow, typed, `async` or generic, with its parameters and return type in it; a constant match needs `$VALUE` inspected to extract a signature. Both take `const` declarations only, with a plain identifier as the name.

**JavaScript/TypeScript — exported classes:**

```yaml
id: js-exported-classes
language: typescript
rule:
  kind: export_statement
  inside:
    kind: program
  not:
    has:
      regex: '^default$'
  has:
    field: declaration
    all:
      - has:
          field: name
          pattern: $NAME
      - has:
          field: body
          kind: class_body
```

> **Important:** The recipe matches an `export_statement` whose declaration has a name and a `class_body`, so plain, generic, `extends`, `implements`, `abstract` and decorated classes all match, with the class name as `$NAME`. A decorated class matches from its first decorator, so the match, and its line, start at the decorator. `export default class` does not match (its exposed name is `default`), and neither does `export declare class`. The `find_code` patterns are narrower: the bare `export class $NAME` returns zero with a `Pattern contains an ERROR node` warning, and `export class $NAME { $$$ }` matches only a class with no type parameters and no `extends` (see Known Limitations #9 and #10). Either way a match is the whole `export_statement`, the kind the recipe declares, not the `class_declaration` inside it.

**JavaScript/TypeScript: re-exported names:**

```yaml
id: js-reexports
language: typescript
rule:
  kind: export_specifier
  inside:
    kind: export_clause
    inside:
      kind: export_statement
      inside:
        kind: program
      has:
        field: source
        has:
          kind: string_fragment
          pattern: $SOURCE
  any:
    - has:
        field: alias
        any:
          - has:
              kind: string_fragment
              pattern: $NAME
          - not:
              kind: string
            pattern: $NAME
    - all:
        - not:
            has:
              field: alias
              regex: '.'
        - has:
            field: name
            any:
              - has:
                  kind: string_fragment
                  pattern: $NAME
              - not:
                  kind: string
                pattern: $NAME
```

**JavaScript/TypeScript: namespace re-exports:**

```yaml
id: js-namespace-reexports
language: typescript
rule:
  kind: export_statement
  inside:
    kind: program
  all:
    - has:
        field: source
        has:
          kind: string_fragment
          pattern: $SOURCE
    - has:
        kind: namespace_export
        any:
          - has:
              kind: identifier
              pattern: $NAME
          - has:
              kind: string
              has:
                kind: string_fragment
                pattern: $NAME
```

> **Re-export note:** `js-reexports` matches each name of `export { a, b as c } from '...'` on its own, as an `export_specifier` (the one JS/TS recipe whose kind is not `export_statement`): `$NAME` is the name the module exposes (the alias when there is one, without quotes when it is a string) and `$SOURCE` the module path without quotes. Type-only re-exports (`export type { T } from`, `export { type T } from`) match too, since their names are exported. `js-namespace-reexports` matches `export * as ns from '...'` as an `export_statement`, with `ns` as `$NAME`. Neither covers a local `export { x }` with no `from`, or a bare `export * from '...'`, which exposes no name of its own: follow those, and the module each `$SOURCE` names, with the Re-Export Tracing protocol in `extraction-patterns-tracing.md`.

**Rust — public functions:**

```yaml
id: rust-public-functions
language: rust
rule:
  kind: function_item
  has:
    field: name
    pattern: $NAME
  all:
    - has:
        kind: visibility_modifier
        regex: '^pub$'
    - inside:
        any:
          - kind: source_file
          - kind: declaration_list
            inside:
              kind: mod_item
    - not:
        inside:
          kind: mod_item
          stopBy: end
          not:
            has:
              kind: visibility_modifier
              regex: '^pub$'
    - not:
        inside:
          kind: block
          stopBy: end
```

> **Scope note:** The recipe matches a `function_item` with a bare `pub` (async, `const`, `unsafe`, `extern "C"` and generic functions included) at the top of the file or inside a chain of `pub mod` blocks. It does not match a `pub(crate)`, `pub(super)`, `pub(self)` or `pub(in ...)` function, a `pub fn` under a private or `pub(crate)` inline `mod`, inside a function body or a `const` block, or a `pub fn` in an `impl` block (see Known Limitation #8).

**Go — exported functions (capitalized):**

```yaml
id: go-exported-functions
language: go
rule:
  kind: function_declaration
  has:
    field: name
    pattern: $NAME
  not:
    has:
      field: receiver
      kind: parameter_list
constraints:
  NAME:
    regex: '^\p{Lu}'
```

> **Scope note:** The recipe matches every function declaration with a capitalized name, generic and bodyless (assembly-backed) ones included, whatever comments sit between the name and its parameters. Methods (`func (r T) Name()`) never match.

### Component Library YAML Rule Recipes

These patterns are used by `component-extraction.md` when `scope.type: "component-library"`. They prioritize Props interfaces and PascalCase component exports.

**React/TypeScript — Props interfaces (primary API contracts):**

```yaml
id: react-props-interfaces
language: typescript  # Use 'tsx' for .tsx files
rule:
  kind: export_statement
  inside:
    kind: program
  not:
    has:
      regex: '^default$'
  has:
    field: declaration
    kind: interface_declaration
    has:
      field: name
      pattern: $NAME
constraints:
  NAME:
    regex: '.*Props$'
```

The recipe matches plain, generic and `extends` interfaces whose name ends in `Props`, but not `export default interface`, `export declare interface` or a props type written as a type alias (`export type XProps = {...}`).

**React/TypeScript — Component function exports (PascalCase):**

> **Language note:** Use `language: tsx` for `.tsx` files and `language: typescript` for `.ts` files; the rule body is the same. The rule is `js-exported-functions` without generator functions (React cannot render one) plus a PascalCase `$NAME`, so async, generic and default-exported components match, and so does each overload signature. For `.js` and `.jsx` files use the `javascript` form below. `^\p{Lu}` accepts any uppercase first letter, non-ASCII ones included.

```yaml
id: react-component-functions
language: tsx
rule:
  kind: export_statement
  inside:
    kind: program
  any:
    - has:
        field: declaration
        any:
          - kind: function_declaration
          - kind: function_signature
        has:
          field: name
          pattern: $NAME
    - has:
        field: declaration
        kind: ambient_declaration
        has:
          kind: function_signature
          has:
            field: name
            pattern: $NAME
  not:
    has:
      field: declaration
      kind: function_declaration
    follows:
      stopBy:
        not:
          kind: comment
      kind: export_statement
      has:
        field: declaration
        kind: function_signature
constraints:
  NAME:
    regex: '^\p{Lu}'
```

**React/JavaScript: component function exports (`.js`, `.jsx`, `.mjs`, `.cjs`):**

```yaml
id: react-component-functions
language: javascript
rule:
  kind: export_statement
  inside:
    kind: program
  has:
    field: declaration
    kind: function_declaration
    has:
      field: name
      pattern: $NAME
constraints:
  NAME:
    regex: '^\p{Lu}'
```

**React/TypeScript — Component arrow function exports:**

```yaml
id: react-component-arrow-functions
language: typescript  # Use 'tsx' for .tsx files
rule:
  kind: export_statement
  inside:
    kind: program
  has:
    field: declaration
    kind: lexical_declaration
    all:
      - has:
          field: kind
          regex: '^const$'
      - has:
          kind: variable_declarator
          all:
            - has:
                field: name
                kind: identifier
                regex: '^\p{Lu}'
                pattern: $NAME
            - has:
                field: value
                kind: arrow_function
                pattern: $VALUE
constraints:
  NAME:
    regex: '^\p{Lu}'
```

The name's `regex` sits inside the declarator's `has` as well as under `constraints`: a constraint is checked after the match, so on its own it would drop `export const helper = () => 1, Card = () => null` instead of matching `Card`.

**Vue — defineProps extraction:**

```yaml
id: vue-define-props
language: typescript
rule:
  pattern: 'defineProps<$NAME>()'
  kind: call_expression
  not:
    inside:
      stopBy: end
      any:
        - kind: statement_block
        - kind: arrow_function
        - kind: class_body
        - kind: if_statement
        - kind: for_statement
        - kind: for_in_statement
        - kind: while_statement
        - kind: switch_case
```

**Vue: defineProps extraction for `<script setup lang="tsx">`:**

```yaml
id: vue-define-props-tsx
language: tsx
rule:
  pattern: 'defineProps<$NAME>()'
  kind: call_expression
  not:
    inside:
      stopBy: end
      any:
        - kind: statement_block
        - kind: arrow_function
        - kind: class_body
        - kind: if_statement
        - kind: for_statement
        - kind: for_in_statement
        - kind: while_statement
        - kind: switch_case
```

> **Vue note:** ast-grep reads a `.vue` file only when an `sgconfig.yml` maps it to HTML (`languageGlobs:` with `html: ["*.vue"]`); without one it skips every `.vue` file silently, with exit code 0. `find_code_by_rule` takes no config, so it never reaches a `.vue` file: run the Vue recipes with the CLI streaming template and add `-c {scratch}/sgconfig.yml`, a file holding those two lines that you write in a scratch folder, never in the user's source tree. With it, a `language: typescript` rule runs inside each `<script lang="ts">` block and a `language: tsx` rule inside each `<script lang="tsx">` block, at the `.vue` file's own line numbers, which is why the tsx block needs its own recipe. Both recipes match a top-level `defineProps<T>()` call, with the props type as `$NAME` whatever its form (a type name, an inline type literal, `Types.Props`, `Props<T>`, a union); the `not:` clause skips a call inside a function, an arrow function, a class, a block, or an `if`, `for`, `while` or `switch` statement, which Vue's compiler rejects anyway.

**Props-to-Component linking strategy:**

After extracting Props interfaces and component exports, link them using this 3-level fallback chain:

1. **Naming convention (primary):** Strip `Props` suffix from interface name → match to component export (e.g., `NativeLiquidButtonProps` → `NativeLiquidButton`)
2. **File co-location (fallback):** If naming doesn't match, check if a Props interface and a PascalCase export function are defined in the same file — link them
3. **Generic parameter (deep fallback):** Search for `ComponentProps<typeof $NAME>` or `React.ComponentProps<typeof $NAME>` patterns that reference the component by name

Unlinked Props interfaces are included as standalone type exports. Unlinked component exports are included with a note that no Props interface was found (signature-only, T1-low confidence for API contract).

### Known ast-grep Limitations

When using ast-grep for extraction, be aware of these documented limitations:

1. **`export class $NAME` needs a body on 0.42.x; `find_code_by_rule` takes the recipe's `kind`:** The bare `export class $NAME` pattern returns zero through **both** `find_code()` and the CLI on ast-grep 0.42.x: add the body, `export class $NAME { $$$ }` (see #9). With `find_code_by_rule`, pass the `js-exported-classes` recipe with its `kind: export_statement`: the recipe matches the whole export, so a rule naming the inner `class_declaration` finds nothing.

2. **A re-export statement holds several names:** `export { A, B as C } from './module'` is one `export_statement` with one `export_specifier` per name. The `js-reexports` recipe matches each specifier, with the name the module exposes as `$NAME` (`A`, `C`), so no splitting is needed. The pattern `export { $$$NAMES } from $SOURCE` is rejected on 0.42.2 and 0.45.3 (`Multiple AST nodes are detected`); `export { $$$NAMES } from "$SOURCE"` and `export { $$$NAMES } from '$SOURCE'` each match one quote style, as an `export_statement`.

3. **Default anonymous exports capture no name:** `export default function $NAME` works, but `export default $EXPR` (anonymous default export) captures no name in `$NAME`. Fall back to source reading (T1-low) for anonymous defaults.

4. **Fallback protocol:** If an ast-grep pattern returns errors or zero results when results are expected:
   - First: retry with `find_code()` using a simpler pattern (drop type annotations, use broader match)
   - Second: if `find_code()` also fails, fall back to source reading for that pattern category (T1-low confidence)
   - Never silently accept zero results for a pattern category that the source language commonly uses

5. **The `export function $NAME($$$PARAMS)` pattern returns zero in `.tsx` files:** on ast-grep 0.41.x and still on 0.45.3 (with plain `typescript` too, #9), through both the MCP tools and the CLI. The recipes do not use it: `js-exported-functions` with `language: tsx` and `react-component-functions` match every `export function` form their notes list in `.tsx` files, so run them instead of reading `export function` declarations by eye. Read by eye (T1-low) only the forms Known Limitation #11 lists. When a TSX codebase shows zero recipe matches for `export function` while its source clearly holds some, log it in the evidence report as an extraction gap.

6. **CLI `--json=stream` may produce no output (ast-grep 0.41.x):** On 0.41.x, `--json=stream` could produce empty output for certain patterns, and it needed the explicit `run` subcommand (`ast-grep run -p '{pattern}' --json=stream`, not `ast-grep -p '{pattern}' --json=stream`). On 0.45.3 it works with `scan`, as the CLI streaming template runs it (`ast-grep scan -r {recipe_file} --json=stream`), and with `run`. If streaming still produces no output where matches are expected, fall back to `find_code_by_rule` or source reading.

7. **Python class patterns with bases/colon return zero (ast-grep 0.42.x); `def $NAME($$$PARAMS)` misses generic functions (0.45.3):** The patterns `class $NAME($$$BASES)` and `class $NAME($$$BASES):` return zero matches on real Python sources with ast-grep 0.42.0, even on files containing dozens of subclassed public classes. `find_code_by_rule` also rejects the bare inline rule without `kind` as `Rule must specify a set of AST kinds to match. Try adding \`kind\` rule.`, and so does the function pattern `def $NAME($$$PARAMS)`. With `kind: function_definition`, `def $NAME($$$PARAMS)` matches every `def` and `async def` on 0.45.3 except a PEP 695 generic `def name[T](...)`, whose type parameters sit between the name and the parameters. **Workaround:** the recipes use the prefix patterns `class $NAME` and `def $NAME` with their `kind` (`class_definition`, `function_definition`), which match every class and every `def` / `async def`, generic or not, a decorated one at its `class` / `def` line. Their `inside: module` clause stops at the first enclosing `def` or `class`, so they return module-level definitions only, never methods or nested definitions, and their `^[^_]` constraint keeps the public names. A bare CLI `ast-grep run -p 'class $NAME' -l python` (or `'def $NAME'`) cannot carry that scope and returns nested definitions too, so run the recipes as rule files. See the Python public classes and public functions recipes above.

8. **Rust `pub fn` patterns find no function definitions (ast-grep 0.42.x and 0.45.3):** `pub fn $NAME($$$PARAMS)` and `pub fn $NAME($$$PARAMS) -> $RET` parse as a `function_signature_item` (a `fn` with no body, as in an `extern` block), so they return "No matches found" on real crates, even on crates containing 200+ public functions, and with `kind: function_item` they match nothing at all. `pub fn $NAME($$$PARAMS) { $$$ }` matches, but it also matches `pub(crate)` and `pub(super)` functions, methods, and functions in private modules, which are **not** public API. **The `rust-public-functions` recipe** has no pattern: it matches `function_item` nodes with a bare `pub` at the top of the file or in a chain of `pub mod` blocks (see the scope note under the recipe). It leaves out every `pub fn` in an `impl` block on purpose: whether a method is reachable depends on whether its type is, which one file cannot show, and a method's `$NAME` alone loses its type (every type's `new` would merge into one). Take public methods from the `impl` blocks of the public types by source reading, at T1-low confidence. Never silently accept zero results for Rust public functions.

9. **Plain `language: typescript` declaration patterns without a body return zero (ast-grep 0.42.x and 0.45.3):** The incomplete-statement patterns `export class $NAME`, `export function $NAME($$$PARAMS)`, `export type $NAME`, and `export enum $NAME` all return **zero** matches against real `.ts` sources on ast-grep 0.42.2 and 0.45.3; `export class` / `export type` / `export enum` additionally print `Pattern contains an ERROR node`. This affects the CLI (`ast-grep run -p ... -l typescript`) and the MCP `find_code()` API **identically**: `find_code()` is not a workaround. The cause is that a declaration pattern missing its body or initializer does not parse as a complete statement. The recipes do not use these patterns: `js-exported-functions`, `js-exported-classes` and `react-props-interfaces` match the `export_statement` and test its `declaration` node, so they find every function, class and interface form their notes list. **Workarounds for a `find_code` pattern outside the recipes (verified on 0.42.2 and 0.45.3 via both CLI and `find_code`):**
   - **enum:** add the body: `export enum $NAME { $$$ }` matches.
   - **type alias:** drop `export` and include the initializer: `type $NAME = $T` matches (and captures both `export type` and bare `type` declarations).
   - **class, interface, function:** use the recipes. `export class $NAME { $$$ }` and `export interface $NAME { $$$ }` carry a body and match, but miss generic and `extends` forms (#10), and `export function $NAME($$$PARAMS) { $$$ }` misses every function with a return-type annotation (and, on 0.42.2, every `async` one).

   Never silently accept zero results for a declaration form the source language commonly uses.

   Kinds (verified on 0.45.3): each `export ...` pattern above matches an `export_statement`. The type-alias workaround `type $NAME = $T` has no `export`, so it matches the `type_alias_declaration`, inside an `export type` too, and an export it matched records `type_alias_declaration`.

10. **Generic class declarations do not match non-generic class patterns (ast-grep 0.42.x and 0.45.3):** The non-generic `find_code` patterns `export class $NAME { $$$ }` and `export class $NAME extends $BASE { $$$ }` silently skip every generic form. On ast-grep 0.42.2, verified via both the CLI (`ast-grep run -p ... -l typescript`) and `find_code()`, the first matched only a plain `Plain` and the second only a plain `PlainExtends` on a fixture of `Plain` / `Generic<T>` / `GenericExtends<T> extends Base<T>` / `abstract AbstractGeneric<T>` / `PlainExtends`, and 0.45.3 does the same. The per-shape generic patterns `export class $NAME<$$$P> { $$$ }`, `export class $NAME<$$$P> extends $BASE { $$$ }`, and `export abstract class $NAME<$$$P> { $$$ }` each match exactly **one** shape. **The `js-exported-classes` recipe** has no pattern: it matches an `export_statement` whose declaration has a name and a `class_body`, so it finds all five shapes, and `implements` and decorated classes too. Use it rather than the patterns. When only `find_code` is available, run a source-read fallback `^export (abstract )?class` over the in-scope `.ts` sources (T1-low) and merge by name+file with the AST results. Never accept a class inventory that omits generic classes when the source uses them.

    Kinds (verified on 0.45.3): the recipe, and each `export class` pattern above, generic, `extends` and `abstract` forms included, match an `export_statement`. The bare `class $NAME` pattern matches the declaration itself: a `class_declaration`, or an `abstract_class_declaration` for an `abstract` class.

11. **Forms the recipes deliberately do not cover (ast-grep 0.45.3):** read these by eye at T1-low when the source uses them, or follow them with the Re-Export Tracing protocol in `extraction-patterns-tracing.md` where noted.
    - **Every JS/TS `export_statement` recipe:** `export` followed by a line break before the declaration (tree-sitter reads the bare `export` as a statement of its own, so there is no `export_statement` to match; formatters never write it); an export nested in a `namespace`, `declare module` or `declare global` block, a `.d.ts` file's `declare module "pkg" { ... }` included, since it is a member, not a module export.
    - **`js-exported-functions`, `react-component-functions`, `react-component-exports`:** an anonymous `export default function () {}` (#3); a function exported through a list (`export { f }`, `export { f as g }`, `export default f;`, `export = f`); a function bound to a `const` (the constants and arrow-function recipes find it); a wrapped default such as `export default memo(function Name() {})` or `forwardRef(...)`, whose value is a call, not a declaration; class, object-literal and interface methods; the implementation of an overloaded function (its signatures match instead). The React recipes also skip generator functions (an overload signature of one still matches, since a signature does not show it) and class components and keep a PascalCase function that is not a component (such as a Next.js `GET` handler).
    - **`js-exported-constants`, `js-exported-arrow-functions`, `react-component-arrow-functions`:** every declarator after the first one a recipe accepts in `export const a = 1, b = () => 2` (one match per statement); destructuring (`export const { x } = obj`, which has no identifier name); `let`, `var` and `export declare const`. The arrow-function recipes also skip an arrow wrapped in parentheses, `as`, `satisfies` or a call (`memo`, `forwardRef`, `lazy`), and a `function` expression; the constants recipe reports them.
    - **`js-exported-classes`, `react-props-interfaces`:** `export default class` and `export default interface` (their exposed name is `default`); `export declare class` and `export declare interface`; a class expression bound to a `const` (the constants recipe reports it); a props type written as a type alias (`export type XProps = {...}`).
    - **`js-reexports`, `js-namespace-reexports`:** a local `export { x }` or `export { x as y }` with no `from`; a bare `export * from '...'`, which exposes no name of its own; an `export { a } from '...' with { type: 'json' }` statement, or the legacy `export { a } from '...' assert { type: 'json' }`, which parse as ERROR nodes. Follow these with the Re-Export Tracing protocol.
    - **`rust-public-functions`:** a `pub fn` in an `impl` block (#8); trait methods, which carry no `pub`; `pub fn` imports in an `extern "C" { }` block; functions a macro generates (`macro_rules!` and `cfg_if!` bodies are token trees, which ast-grep does not parse). One file cannot show reachability across files: a `pub fn` at the top of `foo.rs` matches whether or not `mod foo;` is `pub`, so check `pub use` re-exports with the Re-Export Tracing protocol. `#[cfg]`-gated and `#[doc(hidden)]` functions still match, and a raw identifier keeps its prefix (`r#match`).
    - **`go-exported-functions`:** methods; an exported function-typed variable (`var F = func() {}`). `Test*`, `Benchmark*` and `Example*` functions in `_test.go` files, and the exported functions of `package main` or an `internal/` package, match but are not importable API: exclude them through `scope.exclude`.
    - **`python-public-functions`, `python-public-classes`:** a definition under `elif __name__ == "__main__":` or a compound condition (`__name__ == "__main__" or DEBUG`), which still matches; a function made by `lambda`, `partial(...)` or `exec`, or declared `global` inside another function; a class made by `type(...)`, `NamedTuple(...)`, `TypedDict(...)` or `Enum(...)`, and an alias (`X = Other`); names created at runtime (`globals()`, `setattr`); names imported into the module (`from .x import name`: Re-Export Tracing). The recipes do not read `__all__`: a public-looking name it leaves out still matches, and a name it lists but imports from elsewhere is found by Re-Export Tracing.
    - **`vue-define-props`, `vue-define-props-tsx`:** a call with two type arguments (`defineProps<A, B>()`); runtime `defineProps({ ... })` and `defineProps([...])`, which carry no type; the Options API `props:` option; `defineProps?.<X>()` and `(defineProps)<X>()`; `defineProps` inside a function, an arrow function, a class, a block, or an `if`, `for`, `while` or `switch` statement; a `<script setup>` with no `lang` (plain JavaScript, no type argument). `find_code_by_rule` never reaches a `.vue` file, and the CLI does only with a scratch `sgconfig.yml` (see the Vue note above).

### Component Library Demo/Example Auto-Exclusion

When `scope.type: "component-library"`, auto-detect and propose demo/example exclusions before extraction begins. **User confirmation is required before applying** — some `examples/` directories contain API-level code.

**Auto-detect directory patterns:**
- `**/demo/**`, `**/demos/**`
- `**/stories/**`, `**/__stories__/**`, `**/storybook/**`
- `**/examples/**`, `**/example/**`

**Auto-detect file patterns:**
- `**/*.stories.*`, `**/*.story.*`
- `**/*.example.*`, `**/*.demo.*`

If `demo_patterns` is specified in the brief, use those instead of auto-detection.

**Procedure:**
1. Scan the scoped file tree for matching directories and files
2. Count matches per pattern category
3. Present to user: "**Auto-detected {N} demo/example files** in {M} directories matching these patterns: {list}. Confirm exclusion? [Y/n] Or adjust patterns:"
4. Apply confirmed patterns to the exclude list before AST extraction
5. Record in extraction inventory: `demo_files_excluded: {count}`

### Re-Export Tracing and Script/Asset Extraction

See `extraction-patterns-tracing.md` for:
- **Re-export tracing protocol** — resolving module imports through `__init__.py`, barrel files, `pub use`
- **Script/asset extraction patterns** — detection heuristics, inclusion rules, provenance, inventory structure

