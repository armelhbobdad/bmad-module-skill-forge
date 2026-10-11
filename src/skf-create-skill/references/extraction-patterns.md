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

> **Note:** `ast_bridge.*`, `qmd_bridge.*`, `ccc_bridge.*` and `gh_bridge.*` below are **conceptual interfaces**, not callable functions: `ast_bridge.*` is the ast-grep MCP tools (`find_code`, `find_code_by_rule`) or the `ast-grep` CLI; `qmd_bridge.*` the QMD MCP `query` tool or the `qmd` CLI (`qmd search` / `qmd vsearch`), whose tool-not-found error is non-fatal, as step 4's tool probe says; `ccc_bridge.*` the `/ccc` skill, the ccc MCP server or the `ccc` CLI; `gh_bridge.*` `gh api` or direct file reads of a local source. `knowledge/tool-resolution.md` has the full table.

### Strategy

1. Run the AST Extraction Protocol below: the recipe runner finds every export in the files in scope, each with its file, `$NAME`'s line, recipe and node kind, and a function's signature, parameters and return type
2. For each export: take its `signature`, `params` and `return_type` from the runner's record; read them from the source at its line only for a function whose `params` is null
3. Use ast-grep to detect co-imported symbols in `path` for the given `libraries[]`
4. Record the recipe set, the recipes and the ast-grep version the runner reports, for reproducibility

### Confidence
- Each entry is labeled by the tool that produced it, not by the tier:
  - An export an ast-grep rule matched (a function with its full signature, a type definition, an interface): T1 (AST-verified), an `[AST:...]` citation, `extraction_method: ast-grep` and `ast_node_type` set to the `kind` the matching recipe declares (see the recipes below)
  - An export read by eye (ast-grep could not parse its file, the rules missed it, or the file was read instead of matched): T1-low, a `[SRC:...]` citation, `extraction_method: source-read` and `ast_node_type: null`
- Co-import patterns ast-grep detected: T1
- Internal/private functions: excluded (not part of public API)

### ast-grep Patterns

One recipe matches each export shape: the recipes are under **YAML Rule Recipes by Language** below, and the table that gives each shape its recipe and kind, a `find_code` pattern's included, is in `extraction-patterns-by-hand.md`.

---

## Forge+ Tier (AST + CCC)

Identical extraction to Forge tier. CCC adds an upstream semantic discovery step that ranks the files extraction reads one at a time.

### When CCC Pre-Discovery Applies

CCC pre-discovery runs in ccc-discover (before this extraction step) when ALL of the following are true:
- Tier is Forge+ or Deep
- `tools.ccc: true` in forge-tier.yaml
- The source index is available: step 2b searches with `--refresh` when `ccc_index.status` is `"fresh"`, `"created"`, `"skipped"` or a status it does not know (such as a `"stale"` an older SKF recorded), and first attempts lazy indexing when it is `"none"` or `"failed"`

The discovery step stores `{ccc_discovery: [{file, score, snippet}]}` in context. This extraction step ranks by those results the files it reads one at a time.

### CCC Pre-Ranking Strategy

When `{ccc_discovery}` is present and non-empty, rank the files extraction reads one at a time: those the recipe runner leaves to source reading (its `file_issues`, its extraction gaps and the files of a language no recipe reads), or the filtered file list when extraction runs without the runner.

1. Files appearing in `{ccc_discovery}` results come first, sorted by relevance score descending
2. Files not in CCC results follow them: they are not excluded, only deprioritized
3. If the CCC intersection with scoped files produces <10 files: include all scoped files (CCC results too narrow)

### ast-grep Patterns

Same recipes as Forge tier. CCC pre-ranking changes no recipe.

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

When AST tools are available (Forge, Forge+ and Deep tiers) and the step that runs this protocol gives the recipe runner's command, the runner extracts: `skf-extract-public-api.py --mode full` runs the recipes below over the files in scope in one call and writes every export, with its exact file, line, name and node kind, as JSON. The command names `--source-root` and either the brief (`--brief`, for its scope globs, scope type and language) or the files to read (`--files-from`, one path per line relative to the source root), and `-o` for the JSON, a file the step removes before the call, so that a JSON there after the call is this call's. While the runner can run, never run the recipes one at a time, batch them, or merge and dedupe their matches by hand.

### Recipe Runner

- **Files in scope:** a file is in scope when an include glob matches it (every file, when there is none) and no exclude glob does. `**` spans any number of path segments, none included, and `*` and `?` stay inside one, so `src/**/*.ts` matches `src/index.ts` and `**/test_*` matches a top-level `test_x.py`. The runner reads those a recipe reads (`.vue` files included) and counts them in `files_in_scope`, the filtered file count; `files_without_recipes` counts by extension those it leaves, in a language no recipe reads. `skf-extract-public-api.py --help` gives the rest of its rules.
- **Recipes:** the recipes below, which SKF's shared recipe file, `ast-grep-recipes.yaml`, holds too: the `standard` set, or the `component-library` set for that scope type.
- **Head cap:** each recipe keeps at most 200 matches, or at Forge+ and Deep 500 for `scope.type: "full-library"` and 300 for `scope.type: "component-library"`, in file and line order. `truncated` is true, and so is that recipe's `truncated` in `recipes[]`, when a recipe matched more: the matches past the cap are missing, so warn about them.
- **Each export** is one name in one file, and gives `export_name`, `source_file`, `source_line` (`$NAME`'s line), `signature_line` (the source line holding it), `citation` (`[AST:{file}:L{line}]`), `ast_recipe`, `ast_node_type` (the `kind` its recipe declares), `export_type`, `from` (a re-export's module), `signature` (the declaration on one line), `params`, `return_type`, `confidence: T1` and `extraction_method: ast-grep`. Record them as they are.
- **Signatures:** a function's `params` lists each parameter (its name, type, default and whether it is optional), and is null for any other export and for a declaration the runner does not parse; `return_type` is null when the declaration states none.
- **Entry points:** `entry_point_diff` diffs the names the package's entry points export with the recipe matches (`public`, `internal`, `extraction_gaps`, `outside_scope`; a `namespace` item's `members` stand in for it), `counts` gives `exports_public_api`, `exports_internal` and `effective_denominator`, and `arms` the monorepo, specific-modules and multi-subpath `exports` flags.
- **Read by eye (T1-low)** only what it leaves: each file in `file_issues` (a syntax error where a recipe can miss an export, or a file that is not UTF-8, unreadable or missing), the files `files_without_recipes` counts that hold public API (by the Quick tier Strategy), the forms Known Limitation #11 below lists, and the `extraction_gaps` names.

Act on its `status`, not its exit code: `ok`, every file in scope was read; `incomplete`, an ast-grep run failed or timed out: keep its exports and warn that the files of each `errors[]` item (how many, and the first) may be unread; `no-ast-grep`, no ast-grep it can run, so no recipe ran.

### When the Runner Cannot Run

There is no runner result when the step gives no runner command, no runner path resolves, or no JSON is at the `-o` path after the call (`uv` missing or failing, an input error, which prints one line on stderr, a crash, or a shell timeout that stopped it). Then, and when its `status` is `no-ast-grep`, run the recipes as **Running the Recipes Without the Runner** below says, on the filtered file list: read this file on from that heading (a run the runner serves stops there), and first load `extraction-patterns-by-hand.md`, beside this file, completely: it holds each recipe's notes and the limitations of patterns run by hand. When no JSON is there and a stderr line holds `error:` (the runner's input error or crash, or `uv` failing; a shell timeout prints none), warn "**Recipe runner failed:** {that line}. Extraction ran without it." and keep the warning with the step's other warnings. When no ast-grep can run them either (no `ast-grep` CLI and no ast-grep MCP tool), extraction degrades to source reading: see `tier-degradation-rules.md` "AST Tool Unavailable". When the runner's `scope.languages` is empty, whatever its `status`, no recipe reads the brief's language (the runner warns `no recipe reads {language} files` and reads no file): extract by the Quick tier Strategy (source reading, T1-low).

**"Files in scope"** are the files the brief's include and exclude globs keep, filtered by the language's extensions, never the repository's whole file count: use the filtered count from step 3 section 2 as the decision tree input.

### Known ast-grep Limitations

Limitation #11 applies to every run: the runner reads with the same recipes. #4 is the fallback of a recipe run by hand, which `find_code` serves; #1 to #3 and #5 to #10 concern patterns run by hand too, and are in `extraction-patterns-by-hand.md`.

4. **Fallback protocol:** If an ast-grep pattern returns errors or zero results when results are expected:
   - First: retry with `find_code()` using a simpler pattern (drop type annotations, use broader match)
   - Second: if `find_code()` also fails, fall back to source reading for that pattern category (T1-low confidence)
   - Never silently accept zero results for a pattern category that the source language commonly uses

Read the forms #11 lists by eye whether or not the runner ran:

11. **Forms the recipes deliberately do not cover (ast-grep 0.45.3):** read these by eye at T1-low when the source uses them, or follow them with the Re-Export Tracing protocol in `extraction-patterns-tracing.md` where noted.
    - **Every JS/TS `export_statement` recipe:** `export` followed by a line break before the declaration (tree-sitter reads the bare `export` as a statement of its own, so there is no `export_statement` to match; formatters never write it); an export nested in a `namespace`, `declare module` or `declare global` block, a `.d.ts` file's `declare module "pkg" { ... }` included, since it is a member, not a module export.
    - **`js-exported-functions`, `react-component-functions`:** an anonymous `export default function () {}` (#3); a function exported through a list (`export { f }` and `export { f as g }`, which `js-local-exports` finds at the list's line), `export default f;` or `export = f`; a function bound to a `const` (the constants and arrow-function recipes find it); a wrapped default such as `export default memo(function Name() {})` or `forwardRef(...)`, whose value is a call, not a declaration; class, object-literal and interface methods; the implementation of an overloaded function (its signatures match instead). The React recipes also skip generator functions (an overload signature of one still matches, since a signature does not show it) and class components and keep a PascalCase function that is not a component (such as a Next.js `GET` handler).
    - **`js-exported-constants`, `js-exported-arrow-functions`, `react-component-arrow-functions`, `react-wrapped-components`:** every declarator after the first one a recipe accepts in `export const a = 1, b = () => 2` (one match per statement); destructuring (`export const { x } = obj`, which has no identifier name); `let`, `var` and `export declare const`. The arrow-function recipes also skip an arrow wrapped in parentheses, `as`, `satisfies` or a call, and a `function` expression; the constants recipe reports them, and `react-wrapped-components` reports a PascalCase `memo`, `forwardRef` or `lazy` call. `react-wrapped-components` skips any other wrapper (`observer(...)`, `styled.div`, `connect(...)(Component)`), a wrapped call cast with `as` or `satisfies`, and `export default memo(...)`, whose exposed name is `default`.
    - **`js-exported-classes`, `react-props-interfaces`:** `export default class` and `export default interface` (their exposed name is `default`); `export declare class`, and `export declare interface` (`ts-exported-types` finds it); a class expression bound to a `const` (the constants recipe reports it); a props type written as a type alias (`export type XProps = {...}`, which `ts-exported-types` finds); a type exported through a list (`export type { T }`, which `js-local-exports` or `js-reexports` finds).
    - **`ts-exported-types`:** `export default interface` (its exposed name is `default`); an interface, type alias or enum inside a `namespace`, `declare module` or `declare global` block, a member rather than a module export; a type exported through a list (`export type { T }`, `export { type T }`), which `js-local-exports` finds, or `js-reexports` when the list has a `from`.
    - **`js-reexports`, `js-namespace-reexports`, `js-local-exports`:** a bare `export * from '...'`, which exposes no name of its own; an `export { a } from '...' with { type: 'json' }` statement, or the legacy `export { a } from '...' assert { type: 'json' }`, which parse as ERROR nodes; `export default x;` and `export = x`; a list inside a `namespace`, `declare module` or `declare global` block, a member rather than a module export; in a `.js` file, `default` as a list item's name or alias (`export { default } from '...'`, `export { x as default }`), a keyword token there that no `$NAME` captures (TypeScript parses it as a name). Follow these with the Re-Export Tracing protocol.
    - **`rust-public-functions`:** a `pub fn` in an `impl` block (#8); trait methods, which carry no `pub`; `pub fn` imports in an `extern "C" { }` block; functions a macro generates (`macro_rules!` and `cfg_if!` bodies are token trees, which ast-grep does not parse). One file cannot show reachability across files: a `pub fn` at the top of `foo.rs` matches whether or not `mod foo;` is `pub`, so check `pub use` re-exports with the Re-Export Tracing protocol. `#[cfg]`-gated and `#[doc(hidden)]` functions still match, and a raw identifier keeps its prefix (`r#match`).
    - **`go-exported-functions`:** methods; an exported function-typed variable (`var F = func() {}`). `Test*`, `Benchmark*` and `Example*` functions in `_test.go` files, and the exported functions of `package main` or an `internal/` package, match but are not importable API: exclude them through `scope.exclude`.
    - **`python-public-functions`, `python-public-classes`:** a definition under `elif __name__ == "__main__":` or a compound condition (`__name__ == "__main__" or DEBUG`), which still matches; a function made by `lambda`, `partial(...)` or `exec`, or declared `global` inside another function; a class made by `type(...)`, `NamedTuple(...)`, `TypedDict(...)` or `Enum(...)`, and an alias (`X = Other`); names created at runtime (`globals()`, `setattr`); names imported into the module (`from .x import name`: Re-Export Tracing). The recipes do not read `__all__`: a public-looking name it leaves out still matches, and a name it lists but imports from elsewhere is found by Re-Export Tracing.
    - **`vue-define-props`, `vue-define-props-tsx`:** a call with two type arguments (`defineProps<A, B>()`); runtime `defineProps({ ... })` and `defineProps([...])`, which carry no type; the Options API `props:` option; `defineProps?.<X>()` and `(defineProps)<X>()`; `defineProps` inside a function, an arrow function, a class, a block, or an `if`, `for`, `while` or `switch` statement; a `<script setup>` with no `lang` (plain JavaScript, no type argument). `find_code_by_rule` never reaches a `.vue` file, and the CLI does only with a scratch `sgconfig.yml` (see the Vue note in `extraction-patterns-by-hand.md`).

### Re-Export Tracing and Script/Asset Extraction

See `extraction-patterns-tracing.md` for:
- **Re-export tracing protocol:** resolving module imports through `__init__.py`, barrel files, `pub use`
- **Script/asset extraction patterns:** detection heuristics, inclusion rules, provenance, inventory structure

---

## Relabel Rule

The rule that sets a provenance entry's labels from its `extraction_method` is in `relabel-rule.md`, beside this file, which compile.md §4 and validate.md §7 and §7a load themselves: load it when another reader, such as update-skill's write.md, meets a `provenance.entries[<i>].*` violation.

---

## Running the Recipes Without the Runner

Read this part only when **When the Runner Cannot Run** sends you here: a run the recipe runner serves stops reading this file at this heading. It holds how to run the recipes one at a time, the CLI streaming template, and the recipes themselves, which the runner's recipe file, `ast-grep-recipes.yaml`, mirrors and `kind-at` reads here.

### Decision Tree

Apply the first matching condition:

```
.vue files (the Vue recipes), at any scope size
  → CLI streaming with -c {scratch}/sgconfig.yml (find_code_by_rule cannot read them; see the Vue note in extraction-patterns-by-hand.md)

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

`extraction-patterns-by-hand.md`'s MCP Tool Usage shows the call with a recipe as its `yaml`.

### CLI Streaming Fallback

When MCP tools are unavailable or more than 500 files are in scope, stream the matches (`--json=stream`, never `--json`, which loads them all into memory) through line-by-line Python:

The `| head -N` at the end of the pipeline caps the exports kept, after the exclude filter, at the Recipe Runner's head cap for the tier and scope type (`{HEAD_CAP}` below).

```bash
# {recipe_file}: one recipe's YAML in a scratch file (never inline: its regexes are quoted).
# {recipe_id}, {node_kind}: its id and declared kind, each export's ast_recipe and ast_node_type.
# .vue files: add -c {scratch}/sgconfig.yml (the by-hand file's Vue note). {HEAD_CAP}: the Recipe Runner's head cap.
# {exclude_patterns}: the brief's scope.exclude as a Python list, [] when it has none.
# fnmatch is not the Files in scope rule above: its `*` also crosses `/`, and `**/x`
# needs a folder before x, so add x too for a top-level file ('test_*' beside '**/test_*').
# The patterns match ast-grep's file paths, relative to the root they name (no ./).
ast-grep scan -r {recipe_file} --json=stream {path} | python3 -c "
import sys, json, fnmatch, signal
if hasattr(signal, 'SIGPIPE'):  # POSIX only; Windows has no SIGPIPE
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

Past 500 files, run the template per top-level source folder, 20 to 50 files a batch, with the same head cap, then merge the results by export name and file, keeping the first line (overloads and a definition in both branches of an `if` repeat a name in one file).

**Line numbers are 0-based in ast-grep JSON** (the CLI's and the MCP tools'), and the line to cite is `$NAME`'s: every `[AST:{file}:L{line}]` citation and provenance `source_line` is `metaVariables.single.NAME.range.start.line + 1`, never the match's own first line, which for a decorated class is the decorator's.

### YAML Rule Recipes by Language

Each recipe declares the `kind` of the node it matches (an export it matched records it as its `ast_node_type`) and captures the export's name as `$NAME`; each was verified on ast-grep 0.45.3. The runner's recipe file, `ast-grep-recipes.yaml`, holds the same rules, and `kind-at` reads them here. To run one without the runner, `extraction-patterns-by-hand.md` gives each recipe's notes, and Known Limitation #11 above lists the forms each recipe deliberately does not cover.

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

**JavaScript/TypeScript — exported functions:**

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

**TypeScript: exported interfaces, type aliases and enums:**

```yaml
id: ts-exported-types
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
    any:
      - any:
          - kind: interface_declaration
          - kind: type_alias_declaration
          - kind: enum_declaration
        has:
          field: name
          pattern: $NAME
      - kind: ambient_declaration
        has:
          any:
            - kind: interface_declaration
            - kind: type_alias_declaration
            - kind: enum_declaration
          has:
            field: name
            pattern: $NAME
```

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

**JavaScript/TypeScript: local export lists:**

```yaml
id: js-local-exports
language: typescript  # Use 'tsx' for .tsx files, 'javascript' for .js files
rule:
  kind: export_specifier
  inside:
    kind: export_clause
    inside:
      kind: export_statement
      inside:
        kind: program
      not:
        has:
          field: source
          kind: string
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
            pattern: $NAME
```

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

**React/TypeScript — Component function exports (PascalCase):**

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

**React: wrapped component exports (`memo`, `forwardRef`, `lazy`):**

```yaml
id: react-wrapped-components
language: tsx
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
                kind: call_expression
                has:
                  field: function
                  regex: '^(React\.)?(memo|forwardRef|lazy)$'
constraints:
  NAME:
    regex: '^\p{Lu}'
```

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
