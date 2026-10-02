# Running the Recipes by Hand

Load this file only when the recipe runner cannot run (**When the Runner Cannot Run** in `extraction-patterns.md`). It holds what running the recipes one at a time needs besides the part of `extraction-patterns.md` from **Running the Recipes Without the Runner** on (the decision tree, the CLI streaming template and the recipes themselves, which the runner's recipe file mirrors and `kind-at` reads there): how to pass a recipe, each recipe's notes, and the Known ast-grep Limitations of patterns run by hand.

## Passing a Recipe

Every recipe's `rule` declares `kind`, the kind of the node it matches, and captures the export's own name as `$NAME`; each was verified on ast-grep 0.45.3 against fixtures holding the forms it must find and the forms it must skip. A JS/TS export recipe matches the whole `export_statement`, not the declaration inside it, except `js-reexports` and `js-local-exports`, which match each `export_specifier`; a pattern without `export`, such as the type-alias workaround `type $NAME = $T` (#9), matches the declaration itself (`type_alias_declaration`), even inside an `export type`. A decorated Python `def` matches the inner `function_definition`, not `decorated_definition`. ast-grep's JSON output never reports the kind of a match, so an export a recipe matched records the recipe's `kind` as its `ast_node_type`.

Most recipes are relational rules (`inside`, `has`, `not`) rather than one pattern, so pass a recipe whole: to `find_code_by_rule`, or as the CLI streaming template's `{recipe_file}`. Never drop the `kind`: without it, ast-grep rejects a pattern that is not a whole statement on its own, such as `def $NAME`. A recipe can match one name more than once (each overload signature, a `def` in both branches of an `if`), so merge its matches by name and file. Known Limitation #11 lists the forms each recipe deliberately does not cover.

## ast-grep Patterns

Each export shape below is matched by one recipe from the YAML Rule Recipes in `extraction-patterns.md`: its `id` is what the entry records as `ast_recipe`, and the `kind` it declares is what the entry records as `ast_node_type`.

| Export shape | Recipe (`ast_recipe`) | Kind (`ast_node_type`) |
|---|---|---|
| Python: a module-level `def` or `async def` | `python-public-functions` | `function_definition` |
| Python: a module-level `class` | `python-public-classes` | `class_definition` |
| JS/TS: a top-level `export function` (async, generator, generic, each overload signature, `export default function Name`, `export declare function`) | `js-exported-functions` | `export_statement` |
| JS/TS: `export const NAME = ...` | `js-exported-constants` | `export_statement` |
| JS/TS: `export const NAME = (...) => ...` | `js-exported-arrow-functions` | `export_statement` |
| JS/TS: `export class` | `js-exported-classes` | `export_statement` |
| TypeScript: a top-level `export interface`, `export type` alias or `export enum` (generic, `extends`, `const enum` and `export declare` forms included) | `ts-exported-types` | `export_statement` |
| JS/TS: each name of `export { a, b as c } from '...'` | `js-reexports` | `export_specifier` |
| JS/TS: `export * as ns from '...'` | `js-namespace-reexports` | `export_statement` |
| JS/TS: each name of a local `export { a, b as c }` with no `from` | `js-local-exports` | `export_specifier` |
| Rust: a top-level `pub fn`, outside `impl` blocks | `rust-public-functions` | `function_item` |
| Go: an exported function, not a method | `go-exported-functions` | `function_declaration` |
| React: `export interface NameProps` | `react-props-interfaces` | `export_statement` |
| React: a PascalCase `export function` | `react-component-functions` | `export_statement` |
| React: a PascalCase `export const Name = (...) => ...` | `react-component-arrow-functions` | `export_statement` |
| React: a PascalCase `export const Name = memo(...)`, `forwardRef(...)` or `lazy(...)`, with or without `React.` | `react-wrapped-components` | `export_statement` |
| Vue: a top-level `defineProps<T>()` | `vue-define-props` (`vue-define-props-tsx` for `<script setup lang="tsx">`) | `call_expression` |

- A `find_code` pattern is only the fallback of Known Limitation #4: an export it matched records the pattern as `ast_recipe` and the kind of its shape from this table.

## MCP Tool Usage

**Recipe search (up to 500 files in scope):**

```
find_code_by_rule(
  project_folder="{source_path}",
  yaml="id: public-api\nlanguage: python\nrule:\n  pattern: 'def $NAME'\n  kind: function_definition\n  inside:\n    kind: module\n    stopBy:\n      any:\n        - kind: function_definition\n        - kind: class_definition\n  not:\n    inside:\n      kind: block\n      stopBy: end\n      inside:\n        kind: if_statement\n        has:\n          field: condition\n          regex: '^\\(?\\s*(__name__\\s*==\\s*[''\"]__main__[''\"]|[''\"]__main__[''\"]\\s*==\\s*__name__)\\s*\\)?$'\nconstraints:\n  NAME:\n    regex: '^[^_]'",
  max_results=150,
  output_format="json"
)
```

The `yaml` string is the `python-public-functions` recipe as a JSON string (`\n` for each line break, `\"` for each quote, `\\` for each backslash). Ask for `output_format="json"`, whose matches carry `metaVariables.single.NAME` (and `SOURCE`) and `$NAME`'s line; `output_format="text"` loses both and cites a match's first line.

## When a Recipe Run Fails

**Safety valve.** If any ast-grep operation (MCP or CLI) visibly causes a timeout, returns an error related to output size, or produces unexpectedly large output: immediately switch to the CLI streaming template (`ast-grep scan -r {recipe_file} --json=stream`, in directory batches). Do not retry the same approach. When falling back to the CLI streaming template, inject the brief's `scope.exclude` patterns into the `EXCLUDES` list (use `[]` if absent); this applies regardless of which path triggered the fallback. Note: `max_results` in the MCP tool and `| head -N` in the CLI path provide hard caps, but this safety valve covers cases where the upstream tool itself fails before returning results (e.g., OOM during JSON serialization).

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

`find_code` takes a pattern and no `kind` or relational clauses, so it cannot keep a recipe's scope: methods, nested and private definitions come back too. Use it only as Known Limitation #4's fallback, and record the kind of the pattern's shape from the ast-grep Patterns table above, in this file (`function_definition` here, since an `async def` is a `function_definition`).

## Recipe Notes

### Python

**Scope note:** Both Python recipes match module-level definitions only, decorated or not (a decorated one at its `def` or `class` line) and generic or not, and only names that do not start with `_`. Their `inside: module` clause stops at the first enclosing `def` or `class`, so a method, a nested `def` and a nested class never match, while a definition under a module-level `if`, `try`, `with`, `for`, `while` or `match` (`if TYPE_CHECKING:` included) does. The `not:` clause drops a definition under `if __name__ == "__main__":` (or `"__main__" == __name__`, with or without parentheses), which exists only when the file runs as a script; the `else:` branch of that `if` still matches, and so does a definition under an `elif __name__ == "__main__":` or a compound guard (#11). The function pattern is `def $NAME`, not `def $NAME($$$PARAMS)`: in a PEP 695 generic `def name[T](...)` the type parameters sit between the name and the parameters, so the longer pattern misses it (#7). Neither recipe reads `__all__`.

**Pattern note:** The minimal `class $NAME` pattern, with `kind: class_definition`, matches every class, with or without bases, keywords, decorators or PEP 695 type parameters. The `class $NAME($$$BASES)` and `class $NAME($$$BASES):` variants return zero (see Known Limitations #7). A bare `ast-grep run -p 'class $NAME' -l python` also returns classes nested in a class or a function, since a pattern alone cannot carry the module-level scope: run the recipe as a rule file instead.

### JavaScript and TypeScript

**Language selection:** Use `language: typescript` for `.ts`, `.mts`, `.cts` and `.d.ts` files and `language: tsx` for `.tsx` files. They use different tree-sitter parsers, and a rule scans only the files of its own language, so for a mixed codebase run each recipe once per language, changing only `language`, and merge the results. For `.js`, `.jsx`, `.mjs` and `.cjs` files use `language: javascript`: `js-exported-constants`, `js-exported-arrow-functions`, `js-exported-classes`, `js-reexports`, `js-namespace-reexports`, `js-local-exports`, `react-component-arrow-functions` and `react-wrapped-components` run unchanged, `js-exported-functions` and `react-component-functions` have `javascript` forms in `extraction-patterns.md` (ast-grep rejects their TypeScript forms there, since `function_signature` and `ambient_declaration` are not JavaScript kinds), and `react-props-interfaces` and `ts-exported-types` are TypeScript only.

**Overloads, defaults and scope:** Each overload signature matches, all with the same `$NAME`, and the implementation after them does not, since callers see only the signatures: the `not:` clause looks at the nearest statement before the implementation that is not a comment. Async, generator and generic functions match, and so do `export default function Name` (with `Name` as `$NAME`) and `export declare function`. The `inside: program` clause keeps the recipe to top-level exports, so an `export function` inside a `namespace`, `declare module` or `declare global` block does not match.

**JS/TS Pattern Merging:** Modern TypeScript codebases often use `export const` exclusively for all exports (arrow functions, objects, constants). Run all the JS/TS recipes (functions, arrow functions, constants, classes, interfaces, type aliases and enums, re-exports and local export lists) and merge results by `$NAME`. Priority when deduplicating: arrow function match > function declaration match > constant match. Both `const` recipes bind the declarator's value as `$VALUE`: for an arrow-function match that is the whole arrow, typed, `async` or generic, with its parameters and return type in it; a constant match needs `$VALUE` inspected to extract a signature. Both take `const` declarations only, with a plain identifier as the name.

**Important:** The recipe matches an `export_statement` whose declaration has a name and a `class_body`, so plain, generic, `extends`, `implements`, `abstract` and decorated classes all match, with the class name as `$NAME`. A decorated class matches from its first decorator, so the match, and its line, start at the decorator. `export default class` does not match (its exposed name is `default`), and neither does `export declare class`. The `find_code` patterns are narrower: the bare `export class $NAME` returns zero with a `Pattern contains an ERROR node` warning, and `export class $NAME { $$$ }` matches only a class with no type parameters and no `extends` (see Known Limitations #9 and #10). Either way a match is the whole `export_statement`, the kind the recipe declares, not the `class_declaration` inside it.

**Types note:** The recipe matches a top-level `export interface`, `export type` alias or `export enum` as an `export_statement`, with the declared name as `$NAME`: generic and `extends` interfaces, generic type aliases, `const enum`, and the `export declare` form of each, on the name's own line when the name follows its keyword on the next line. It skips `export default interface`, whose exposed name is `default`, and an interface, type alias or enum inside a `namespace`, `declare module` or `declare global` block, a member rather than a module export. A type exported through a list (`export type { T }`, `export { type T }`) is found by `js-local-exports`, or by `js-reexports` when the list has a `from`. The recipe is TypeScript only: ast-grep rejects it under `language: javascript`, whose grammar has no interface, type alias or enum.

**Re-export note:** `js-reexports` matches each name of `export { a, b as c } from '...'` on its own, as an `export_specifier`: `$NAME` is the name the module exposes (the alias when there is one, without quotes when it is a string) and `$SOURCE` the module path without quotes. Type-only re-exports (`export type { T } from`, `export { type T } from`) match too, since their names are exported. `js-local-exports` matches each name of a local list with no `from` the same way, such as the `export { Button, buttonVariants }` that ends a shadcn/ui component file, type-only lists included: these two are the JS/TS recipes whose kind is `export_specifier`, not `export_statement`. A local list names a binding the file defines or imports, and the line cited is the list's. Both record the exposed name, so `export { x as default }` records `default`. `js-namespace-reexports` matches `export * as ns from '...'` as an `export_statement`, with `ns` as `$NAME`. None of them covers a bare `export * from '...'`, which exposes no name of its own: follow it, and the module each `$SOURCE` names, with the Re-Export Tracing protocol in `extraction-patterns-tracing.md`.

### Rust

**Scope note:** The recipe matches a `function_item` with a bare `pub` (async, `const`, `unsafe`, `extern "C"` and generic functions included) at the top of the file or inside a chain of `pub mod` blocks, which a pattern such as `pub fn $NAME($$$PARAMS)` never finds: it parses as a bodyless `function_signature_item`. It does not match a `pub(crate)`, `pub(super)`, `pub(self)` or `pub(in ...)` function, a `pub fn` under a private or `pub(crate)` inline `mod`, inside a function body or a `const` block, or a `pub fn` in an `impl` block (see Known Limitation #8).

### Go

**Scope note:** The recipe matches every function declaration with a capitalized name, generic and bodyless (assembly-backed) ones included, whatever comments sit between the name and its parameters. Methods (`func (r T) Name()`) never match.

### Component Library Recipes

**`react-props-interfaces`:** The recipe matches plain, generic and `extends` interfaces whose name ends in `Props`, but not `export default interface`, `export declare interface` or a props type written as a type alias (`export type XProps = {...}`).

**`react-component-functions`:** Use `language: tsx` for `.tsx` files and `language: typescript` for `.ts` files; the rule body is the same. The rule is `js-exported-functions` without generator functions (React cannot render one) plus a PascalCase `$NAME`, so async, generic and default-exported components match, and so does each overload signature. For `.js` and `.jsx` files use its `javascript` form in `extraction-patterns.md`. `^\p{Lu}` accepts any uppercase first letter, non-ASCII ones included.

**`react-component-arrow-functions`:** The name's `regex` sits inside the declarator's `has` as well as under `constraints`: a constraint is checked after the match, so on its own it would drop `export const helper = () => 1, Card = () => null` instead of matching `Card`.

**`react-wrapped-components`:** Use `language: tsx` for `.tsx` files, `language: typescript` for `.ts` files and `language: javascript` for `.js` and `.jsx` files; the rule body is the same. The recipe matches a top-level `export const` whose PascalCase name is bound to a call of `memo`, `forwardRef` or `lazy`, with or without `React.` and with type arguments (`React.forwardRef<HTMLDivElement, Props>(...)`): the wrapped components `react-component-arrow-functions` skips, which `js-exported-constants` reports as constants. Like the arrow-function recipe, it finds a later declarator of an `export const` list when the first one does not match.

**Vue note:** ast-grep reads a `.vue` file only when an `sgconfig.yml` maps it to HTML (`languageGlobs:` with `html: ["*.vue"]`); without one it skips every `.vue` file silently, with exit code 0. `find_code_by_rule` takes no config, so it never reaches a `.vue` file: run the Vue recipes with the CLI streaming template and add `-c {scratch}/sgconfig.yml`, a file holding those two lines that you write in a scratch folder, never in the user's source tree. With it, a `language: typescript` rule runs inside each `<script lang="ts">` block and a `language: tsx` rule inside each `<script lang="tsx">` block, at the `.vue` file's own line numbers, which is why the tsx block needs its own recipe. Both recipes match a top-level `defineProps<T>()` call, with the props type as `$NAME` whatever its form (a type name, an inline type literal, `Types.Props`, `Props<T>`, a union); the `not:` clause skips a call inside a function, an arrow function, a class, a block, or an `if`, `for`, `while` or `switch` statement, which Vue's compiler rejects anyway.

## Known ast-grep Limitations of Patterns Run by Hand

These concern patterns run by hand. Two more stay in `extraction-patterns.md`: #4, the `find_code` fallback of a recipe run by hand, and #11, the forms the recipes do not cover, which every run reads.

1. **`export class $NAME` needs a body on 0.42.x; `find_code_by_rule` takes the recipe's `kind`:** The bare `export class $NAME` pattern returns zero through **both** `find_code()` and the CLI on ast-grep 0.42.x: add the body, `export class $NAME { $$$ }` (see #9). With `find_code_by_rule`, pass the `js-exported-classes` recipe with its `kind: export_statement`: the recipe matches the whole export, so a rule naming the inner `class_declaration` finds nothing.

2. **A re-export statement holds several names:** `export { A, B as C } from './module'` is one `export_statement` with one `export_specifier` per name. The `js-reexports` recipe matches each specifier, with the name the module exposes as `$NAME` (`A`, `C`), so no splitting is needed. The pattern `export { $$$NAMES } from $SOURCE` is rejected on 0.42.2 and 0.45.3 (`Multiple AST nodes are detected`); `export { $$$NAMES } from "$SOURCE"` and `export { $$$NAMES } from '$SOURCE'` each match one quote style, as an `export_statement`.

3. **Default anonymous exports capture no name:** `export default function $NAME` works, but `export default $EXPR` (anonymous default export) captures no name in `$NAME`. Fall back to source reading (T1-low) for anonymous defaults.

5. **The `export function $NAME($$$PARAMS)` pattern returns zero in `.tsx` files:** on ast-grep 0.41.x and still on 0.45.3 (with plain `typescript` too, #9), through both the MCP tools and the CLI. The recipes do not use it: `js-exported-functions` with `language: tsx` and `react-component-functions` match every `export function` form their notes list in `.tsx` files, so run them instead of reading `export function` declarations by eye. Read by eye (T1-low) only the forms Known Limitation #11 lists. When a TSX codebase shows zero recipe matches for `export function` while its source clearly holds some, log it in the evidence report as an extraction gap.

6. **CLI `--json=stream` may produce no output (ast-grep 0.41.x):** On 0.41.x, `--json=stream` could produce empty output for certain patterns, and it needed the explicit `run` subcommand (`ast-grep run -p '{pattern}' --json=stream`, not `ast-grep -p '{pattern}' --json=stream`). On 0.45.3 it works with `scan`, as the CLI streaming template runs it (`ast-grep scan -r {recipe_file} --json=stream`), and with `run`. If streaming still produces no output where matches are expected, fall back to `find_code_by_rule` or source reading.

7. **Python class patterns with bases/colon return zero (ast-grep 0.42.x); `def $NAME($$$PARAMS)` misses generic functions (0.45.3):** The patterns `class $NAME($$$BASES)` and `class $NAME($$$BASES):` return zero matches on real Python sources with ast-grep 0.42.0, even on files containing dozens of subclassed public classes. `find_code_by_rule` also rejects the bare inline rule without `kind` as `Rule must specify a set of AST kinds to match. Try adding \`kind\` rule.`, and so does the function pattern `def $NAME($$$PARAMS)`. With `kind: function_definition`, `def $NAME($$$PARAMS)` matches every `def` and `async def` on 0.45.3 except a PEP 695 generic `def name[T](...)`, whose type parameters sit between the name and the parameters. **Workaround:** the recipes use the prefix patterns `class $NAME` and `def $NAME` with their `kind` (`class_definition`, `function_definition`), which match every class and every `def` / `async def`, generic or not, a decorated one at its `class` / `def` line. Their `inside: module` clause stops at the first enclosing `def` or `class`, so they return module-level definitions only, never methods or nested definitions, and their `^[^_]` constraint keeps the public names. A bare CLI `ast-grep run -p 'class $NAME' -l python` (or `'def $NAME'`) cannot carry that scope and returns nested definitions too, so run the recipes as rule files. See the Python public classes and public functions recipes in `extraction-patterns.md`.

8. **Rust `pub fn` patterns find no function definitions (ast-grep 0.42.x and 0.45.3):** `pub fn $NAME($$$PARAMS)` and `pub fn $NAME($$$PARAMS) -> $RET` parse as a `function_signature_item` (a `fn` with no body, as in an `extern` block), so they return "No matches found" on real crates, even on crates containing 200+ public functions, and with `kind: function_item` they match nothing at all. `pub fn $NAME($$$PARAMS) { $$$ }` matches, but it also matches `pub(crate)` and `pub(super)` functions, methods, and functions in private modules, which are **not** public API. **The `rust-public-functions` recipe** has no pattern: it matches `function_item` nodes with a bare `pub` at the top of the file or in a chain of `pub mod` blocks (see the scope note under the recipe). It leaves out every `pub fn` in an `impl` block on purpose: whether a method is reachable depends on whether its type is, which one file cannot show, and a method's `$NAME` alone loses its type (every type's `new` would merge into one). Take public methods from the `impl` blocks of the public types by source reading, at T1-low confidence. Never silently accept zero results for Rust public functions.

9. **Plain `language: typescript` declaration patterns without a body return zero (ast-grep 0.42.x and 0.45.3):** The incomplete-statement patterns `export class $NAME`, `export function $NAME($$$PARAMS)`, `export type $NAME`, and `export enum $NAME` all return **zero** matches against real `.ts` sources on ast-grep 0.42.2 and 0.45.3; `export class` / `export type` / `export enum` additionally print `Pattern contains an ERROR node`. This affects the CLI (`ast-grep run -p ... -l typescript`) and the MCP `find_code()` API **identically**: `find_code()` is not a workaround. The cause is that a declaration pattern missing its body or initializer does not parse as a complete statement. The recipes do not use these patterns: `js-exported-functions`, `js-exported-classes`, `ts-exported-types` and `react-props-interfaces` match the `export_statement` and test its `declaration` node, so they find every function, class, interface, type alias and enum form their notes list. Run them, not a `find_code` pattern. The complete patterns match (verified on 0.42.2 and 0.45.3 via both CLI and `find_code`), but on 0.45.3 each misses forms the recipes find, and each also returns the members of an `export namespace` block, which are not module exports:
   - **enum:** `export enum $NAME { $$$ }` (with the body) matches, `const enum` included, but not `export declare enum`.
   - **type alias:** `type $NAME = $T` (no `export`, with the initializer) matches `export type` and bare `type` declarations alike, but not a generic alias (`type $NAME<T> = ...`).
   - **class, interface, function:** `export class $NAME { $$$ }` and `export interface $NAME { $$$ }` carry a body and match, but miss generic and `extends` forms (#10), and `export function $NAME($$$PARAMS) { $$$ }` misses every function with a return-type annotation (and, on 0.42.2, every `async` one).

   Never silently accept zero results for a declaration form the source language commonly uses.

   Kinds (verified on 0.45.3): each `export ...` pattern above matches an `export_statement`. The type-alias workaround `type $NAME = $T` has no `export`, so it matches the `type_alias_declaration`, inside an `export type` too, and an export it matched records `type_alias_declaration`.

10. **Generic class declarations do not match non-generic class patterns (ast-grep 0.42.x and 0.45.3):** The non-generic `find_code` patterns `export class $NAME { $$$ }` and `export class $NAME extends $BASE { $$$ }` silently skip every generic form. On ast-grep 0.42.2, verified via both the CLI (`ast-grep run -p ... -l typescript`) and `find_code()`, the first matched only a plain `Plain` and the second only a plain `PlainExtends` on a fixture of `Plain` / `Generic<T>` / `GenericExtends<T> extends Base<T>` / `abstract AbstractGeneric<T>` / `PlainExtends`, and 0.45.3 does the same. The per-shape generic patterns `export class $NAME<$$$P> { $$$ }`, `export class $NAME<$$$P> extends $BASE { $$$ }`, and `export abstract class $NAME<$$$P> { $$$ }` each match exactly **one** shape. **The `js-exported-classes` recipe** has no pattern: it matches an `export_statement` whose declaration has a name and a `class_body`, so it finds all five shapes, and `implements` and decorated classes too. Use it rather than the patterns. When only `find_code` is available, run a source-read fallback `^export (abstract )?class` over the in-scope `.ts` sources (T1-low) and merge by name+file with the AST results. Never accept a class inventory that omits generic classes when the source uses them.

    Kinds (verified on 0.45.3): the recipe, and each `export class` pattern above, generic, `extends` and `abstract` forms included, match an `export_statement`. The bare `class $NAME` pattern matches the declaration itself: a `class_declaration`, or an `abstract_class_declaration` for an `abstract` class.
