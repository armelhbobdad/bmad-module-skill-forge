#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Verify Provenance Completeness — deterministic Check D for update-skill.

update-skill's Check D (Provenance Completeness, now in verify-publish.md §6)
previously asked the model to perform three deterministic set/citation
operations by eye, against in-context data:

  1. **Completeness** — verify every documented export has a provenance-map
     entry (metadata `exports[]` \\ provenance `entries[].export_name`).
  2. **Orphans** — flag provenance entries whose export was removed
     (provenance `entries[].export_name` \\ metadata `exports[]`).
  3. **Stale citations** — flag entries whose `source_file:source_line`
     no longer resolves (file gone, or line past end of file), or whose
     line is not a line that defines the export (`line-not-definition`).
  4. **Citation prefixes** (only with `--skill-dir`): flag each `[AST:]` /
     `[SRC:]` citation in the skill's markdown whose prefix disagrees with
     the provenance entry it cites, or an `[AST:]` citation in a skill whose
     map holds no ast-grep entry at all.
  5. **Node kinds** (only with `--check-node-kinds`): flag each ast-grep
     entry whose `ast_node_type` is not a node kind ast-grep knows for the
     entry's language.

Reference apps: when `--metadata` has `scope_type: reference-app`, 1 and 2
do not run. A reference app's `exports[]` is empty by design while its
entries are per-citation, so the two sets measure different surfaces:
`missing` and `orphaned` stay empty and `summary.set_diff` is
`not-applicable` (`checked` otherwise).

Five more subcommands act on the same rules: `fix` applies the citation
prefix and source-line fixes a `verify` result has one answer for, or,
with `--moves`, moves the citations of a run's moved exports,
`definition-lines` gives the lines that define one export,
`classify-stale` decides which stale names are fabricated signatures and
where the source declares the others, `kind-at` gives the node kind of
the recipe that matches a source line, and `relabel` applies the Relabel
Rule to the label violations of a stats result and the node kinds of a
verify result.

An LLM set-diff can silently pass a dropped or orphaned entry, and eyeballing
whether a cited line still exists is not something the model can do reliably.
Both inputs are machine-readable — `metadata.json` (`exports[]`, a list of
export-name strings) and `provenance-map.json` (`entries[]` with
`export_name` / `source_file` / `source_line`, plus an optional
`reexport_map` for stack-skill barrel renames) are written by
`write.md` §3b and §3. This script diffs the two sets and re-checks the
citations exactly, so Check D consumes JSON rather than computing it.

Timing: update-skill runs it **post-write**, in verify-publish.md §6, after
write.md's `provenance-map.json` (§3) and `metadata.json` (§3b) are on disk.
create-skill runs it too, at validate §7a against the staged package (with
`--skill-dir` and `--check-node-kinds`, as update-skill does), and
test-skill at coverage-check §4c (line check only); test-skill's
coverage-check §2c runs `classify-stale`.

Determinism:
  - Set operations are pure over the two JSON inputs.
  - Citation resolution reads the source tree at `source_root` (from the
    provenance map, or `--source-root`). When no source root resolves on
    disk, the stale check is SKIPPED (`summary.stale_check` reports it) and
    only completeness + orphan diffs run — those need no source tree. Same
    input tree → same output.

Stack-skill canonicalization: a provenance entry's `export_name` may be the
internal name of a barrel-renamed export (e.g. `_Impl` re-exported as
`Public`). Names are canonicalized through `reexport_map`
(`{internal: public}`) before the set-diff, mirroring
`skf-load-provenance.extract_reexport_map`, so an internal-named entry does
not read as a missing public export nor as an orphan.

Definition lines: after a citation resolves (the file exists and the line
is in range, so the older reasons win), the line must define the entry's
export. NAME is the raw `export_name` (not canonicalized); for a dotted
name (`App.update`) it is the last segment. A bookkeeping variant
(`X_def`, `X_exact`, `a11y_X`, test-skill's Source Access Protocol fold
without `--fold-prefix` or `--keep`) that the cited file never names (no
whole identifier in its text) is checked against its base `X` instead,
its finding carries `folded_to`, and `summary.line_check_folded` counts
it; the raw name always comes first, so an export really named
`parse_exact`, or bound in a shape the rules do not cover, is judged as
written. classify-stale never folds. The rules
follow the `source_file` extension:

  - Python (`.py`, `.pyi`): the `def` / `async def` / `class NAME` line
    itself (a decorator line above it does not count); an assignment
    binding NAME (`NAME =`, `NAME: T =`, annotation-only `NAME: T`, a
    target list `A, NAME = ...`, a chain `A = NAME = ...`, PEP 695
    `type NAME =`); an import that binds NAME (`import NAME`,
    `import X as NAME`, `from X import NAME`, `from X import Y as NAME`),
    including NAME on its own line inside a parenthesized or
    backslash-continued import; a `def` / `async def` / `class` line
    ending in a backslash counts through the next line when that line
    starts with NAME, and the name's line is the definition line (the one
    the recipes cite). These count only on a line where a
    statement begins (the stdlib tokenizer says so), so a docstring line,
    a keyword argument or a parameter never matches; a file that does not
    tokenize is matched line by line. A `from X import *` line counts only
    when no other line of the file defines NAME (a re-export the
    extraction could not trace is cited at its star import). An
    `@overload` group, where every line found is a `def` / `async def
    NAME` line at one indentation in one enclosing block (one class, not
    two) and every one but at most the last has `@overload` or
    `@<module>.overload` (`@typing.overload`,
    `@typing_extensions.overload`, `@t.overload` after
    `import typing as t`) in its contiguous decorator block, defines NAME
    at each of its lines, the stubs and the implementation. A comment line
    may sit in the decorator block, and so may a decorator's arguments on
    lines of their own, unless the file does not tokenize. A recorded line
    that misses the group gives its first line alone, which is its first
    stub: the public-API runner, its merge rule and the structural diff
    all record that line, so `fix` can move the entry there.
  - TS/JS (`.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`): a
    `function` (or `function*`), `class`, `interface`, `type`, `enum`,
    `namespace`, `const`, `let` or `var` declaration of NAME, with any of
    `export`, `default`, `async`, `declare`, `abstract` and decorators
    (`@name`, `@a.b`, `@name(...)`, before `export` or between `export`
    and `class`; a name inside a decorator's arguments is not declared);
    a later declarator of a `const`, `let` or `var` list
    (`export const a = 1, NAME = 2;`, or `export const a = 1,` then
    `  NAME = 2;` as Prettier writes it: see Declarator lists below);
    NAME bound by a destructuring pattern that begins such a list
    (`export const { a, b: NAME } = obj;`, `const [NAME] = list`, the
    pattern on one line or several), on the line where NAME appears (see
    Declarator lists below); NAME
    on the line right after a line that ends in its declaration keyword
    (`export function`, `export interface`, `export const` and so on),
    which is the line cited;
    `export import NAME =`; `export * as NAME from` (NAME may be quoted);
    `export default NAME`; for the name `default`, the one SKF's extraction
    gives a module's default export, any `export default` line at column 0,
    whatever follows it (`export default storybookTest;`,
    `export default async function postinstall() {}`, an anonymous
    function or class, an object or any other expression, the value on
    the next line), decorators before `export` allowed;
    an `export { ... }` list whose exposed name is NAME, an identifier or
    a quoted string on either side of `as`; CommonJS
    `exports.NAME =`, `module.exports.NAME =`, or NAME as a key or
    shorthand inside `module.exports = { ... }`. A list or object spanning
    several lines counts on the line where NAME appears. For a dotted
    name, an indented class member declaring NAME (method, property or
    accessor, with any of `public`, `private`, `protected`, `static`,
    `readonly`, `async`, `abstract`, `override`, `declare`, `get`, `set`)
    also counts. An indented `NAME(...)` with no modifier, followed by `;`
    or another expression rather than a body `{` or a return type `:`, is
    a call, not a member; an indented `NAME: ...` or `NAME = ...` ending
    with `,` is an object-literal entry or a destructuring default.
    Comments never match: `//` to the end of the line and `/* ... */`
    across lines are removed first, outside '...', "..." and `...` strings,
    and brackets inside a string do not count toward a `module.exports`
    object's depth. Strings are followed within one line only, so a
    template literal spanning lines can hide or expose a comment marker.

Declarator lists: a `const`, `let` or `var` list is split at its
top-level commas, outside strings, regular expression literals and
brackets, a type-argument list included (`Map<K, V>`: a `<` right after
a name), up to a top-level `;`. The list goes on to the next line when a
line ends inside a bracket, after a top-level comma or after an operator
waiting for its operand, or when the next line starts with an operator (a
member chain or a ternary broken over lines), so a declarator on a line
of its own counts. A `<` where an expression begins (JSX, a type assertion, a generic
arrow function's type parameters) is not followed: no later declarator of
the list counts after it. A destructuring pattern that begins the list,
on the keyword's line, declares the names it binds: a shorthand key, the
target after `key:`, an array element, a rest `...NAME` and the names of
a nested pattern, each on the line where it appears (the pattern may
span lines), with its statement's column. A renamed or computed key, a
default value, the type annotation after the pattern and anything inside
a string or a comment bind nothing, and neither does a pattern that does
not close. The later declarators after a pattern count as any others. A
pattern that is a later declarator (`export const a = 1, { b } = c`) or
that sits on the line after a split keyword (`export const`, then
`  { b } = c;`) is not covered: it declares nothing.

Indentation: for a dotted name every match counts. For an undotted name,
matches at any indentation count, but when the file has a column-0 match
the indented ones are dropped, so a local shadow never outranks the
module-level definition. A line inside a multi-line import, export list
or `module.exports` object takes the column of the line its statement
starts on, and so do the name line of a declaration split after its
keyword, a later declarator on a line of its own and the line of a name
a destructuring pattern binds. When the recorded
line is itself an indented match that this rule dropped (a method
recorded under an undotted name beside a module-level function of the
same name), the finding lists the recorded line too, so it carries
several lines and no caller auto-moves it.

Entries in other files, and entries whose `export_type` is `module` or
`package` (case-insensitive; neither has a definition line), are skipped
and counted in `summary.line_check_skipped`. A `line-not-definition` item
lists every defining line in the file in `definition_lines`, the recorded
line included when it is an indented match the column-0 rule dropped (see
Indentation). The one exception is a Python `@overload` group: it lists
the group's first line alone, unless the recorded line is such a dropped
indented match, which still gives several lines. An empty list
means the rules found no definition line, which may be a shape they do not
cover: the entry is unverified, not gone, and no caller auto-fixes it.

Citation check (`--skill-dir DIR`, which must hold a `SKILL.md`): scans
`DIR/SKILL.md` and `DIR/references/**/*.md` for `[AST:path:Ln]` /
`[SRC:path:Ln]`, ranges `Ln-m` / `Ln-Lm` included (the first line counts);
a citation with no line is ignored. A citation matches an entry when its
normalized path equals `source_file` and its line equals `source_line`.
`summary.skill_citations_matched` counts the citations that matched an
entry: 0 with citations scanned means the skill cites paths under another
root. Reasons, one per citation:

  - `prefix-mismatch`: the matched entry's `extraction_method` implies the
    other prefix (`ast-grep` / `ast_bridge` give AST, `source-read` /
    `source_reading` give SRC). It wins over the reason below.
  - `ast-without-ast-grep`: an `[AST:]` citation in a skill whose map has
    no `ast-grep` or `ast_bridge` entry, raised only when every entry with
    a source line carries a known `extraction_method` (a missing or
    unknown method may hide an ast-grep entry).

When several entries share the cited line, the citation is a
`prefix-mismatch` only when none of them implies its prefix. An
`extraction_method` that is not a string reads as unknown (it implies no
prefix). Unmatched citations are not findings unless the second reason
applies.

Node-kind check (`--check-node-kinds`): ast-grep's JSON output never
reports the kind of the node a rule matched, so an entry's `ast_node_type`
is copied from the recipe that matched it, and nothing else proves it is a
real kind. For each entry whose `extraction_method` is `ast-grep` or
`ast_bridge` and whose `ast_node_type` is a non-blank string, the
`source_file` extension picks an ast-grep language (`.py` / `.pyi` python,
`.ts` / `.mts` / `.cts` typescript, `.tsx` tsx, `.js` / `.jsx` / `.mjs` /
`.cjs` javascript, `.rs` rust, `.go` go, `.java` java, `.kt` / `.kts`
kotlin, `.cs` csharp, `.rb` ruby, `.swift` swift, `.php` php); an entry in
any other file is skipped and counted in `summary.node_kind_check_skipped`.
Reasons, one per entry:

  - `error-kind`: the kind is `ERROR`, the node tree-sitter makes of code
    it cannot parse. ast-grep accepts it in a rule, so it is not asked.
  - `invalid-kind`: the kind is not shaped like a kind
    (`[A-Za-z_][A-Za-z0-9_]*`, so no whitespace or shell characters reach
    ast-grep), judged without ast-grep; or ast-grep rejected it (its error
    names an invalid kind).

Those two are judged whatever the ast-grep lookup finds. Every other kind is
asked once per distinct (language, kind): `ast-grep scan --config
<sgconfig.yml> --inline-rules <rule> --stdin` with a rule matching only that
kind, over an empty stdin, from a temporary folder holding a minimal
sgconfig.yml that `--config` names (so no other sgconfig.yml is read).
ast-grep parses the rule before reading input and rejects a kind the
language's grammar lacks. Before that, ast-grep is asked about a kind no
grammar has; unless it rejects it, its answers cannot be read and the check
is `skipped-unrecognized-ast-grep`. When no `ast-grep` executable resolves
(the CWD-shim guard applies), the check is `skipped-no-ast-grep`. With no
kind left to ask, ast-grep is not looked up and the check is `checked`.

An ast-grep failure that does not name the kind proves nothing about it: the
entry is listed in `node_kinds_unchecked[]`, not as a finding, with reason
`ast-grep-error`, `ast-grep-timeout` (after the first timeout the remaining
kinds are not asked) or `temp-folder-error` (the temporary folder could not
be made or written). Without the flag the output keeps its shape: there are
no `node_kinds` / `node_kinds_unchecked` keys, and the one key added is
`summary.node_kind_check: "not-requested"`.

Subcommands:
  verify --metadata <metadata.json> --provenance <provenance-map.json>
         [--source-root <path>] [--skill-dir <dir>] [--check-node-kinds]
         [-o <out.json>]

    Emit JSON:
      {
        "status": "pass" | "findings",
        "missing":  ["<export documented but not in provenance>", ...],
        "orphaned": ["<provenance entry with no documented export>", ...],
        "stale": [
          {"export_name": "<raw entry name>",
           "entry_index": <int>,           # position in entries[]
           "source_file": "<rel path>",
           "source_line": <int|null>,
           "reason": "file-missing" | "line-out-of-bounds" | "line-invalid"
                     | "line-not-definition",
           "definition_lines": [<int>, ...],    # line-not-definition only
           "folded_to": "<base name>"},         # line-not-definition only,
                                                # a variant checked as its base
          ...
        ],
        "citations": [
          {"file": "<markdown path relative to --skill-dir>",
           "line": <int>,                  # line of the markdown file
           "citation": "[AST:<path>:L<n>]",
           "prefix": "AST" | "SRC",
           "cited_file": "<path as written>",
           "cited_line": <int>,
           "reason": "prefix-mismatch" | "ast-without-ast-grep",
           "expected_prefix": "AST" | "SRC",
           "export_name": "<matched entry name>" | null},
          ...
        ],
        "node_kinds": [                    # --check-node-kinds only
          {"export_name": "<raw entry name>" | null,
           "entry_index": <int>,           # position in entries[]
           "source_file": "<rel path>",
           "source_line": <as recorded>,
           "ast_node_type": "<recorded kind>",
           "language": "<ast-grep language>",
           "reason": "invalid-kind" | "error-kind"},
          ...
        ],
        "node_kinds_unchecked": [          # --check-node-kinds only
          {... the same keys ...,
           "reason": "ast-grep-error" | "ast-grep-timeout"
                     | "temp-folder-error"},
          ...
        ],
        "summary": {
          "exports_checked":  <int>,   # documented exports (metadata)
          "entries_checked":  <int>,   # provenance entries with export_name
          "missing_count":    <int>,
          "orphaned_count":   <int>,
          "set_diff": "checked" | "not-applicable",  # reference-app
          "stale_count":      <int>,
          "citations_checked": <int>,  # entries whose citation was resolved
          "line_check_skipped": <int>, # resolved entries with no line rule
          "line_check_folded": <int>,  # variants checked against their base
          "stale_check": "checked" | "skipped-no-source-root",
          "skill_citations_scanned": <int>,  # [AST:]/[SRC:] with a line
          "skill_citations_matched": <int>,  # of those, citing an entry
          "citation_findings_count": <int>,
          "citation_check": "checked" | "skipped-no-skill-dir",
          "node_kind_check": "checked" | "skipped-no-ast-grep"
                             | "skipped-unrecognized-ast-grep"
                             | "not-requested",
          # the four below appear with --check-node-kinds only
          "node_kinds_checked": <int>,       # entries judged, ERROR included
          "node_kind_check_skipped": <int>,  # entries in an unmapped file
          "node_kind_check_errors": <int>,   # len(node_kinds_unchecked)
          "node_kind_findings_count": <int>
        }
      }

    `missing` / `orphaned` are sorted, deduplicated public names.
    `stale` is sorted by (export_name, source_file).
    `citations` is sorted by (file, line, column).
    `node_kinds` / `node_kinds_unchecked` are sorted by (export_name,
    source_file, entry_index).

  fix --verify <verify.json> --provenance <provenance-map.json>
      --skill-dir <dir> [--manual-inventory <inventory.json>]
      [--no-line-moves] [--dry-run] [-o <out.json>]

    Applies the fixes a `verify` result (the JSON a `verify` run wrote, over
    the same provenance map and skill folder) has one answer for:

      1. Citation prefixes: each `citations[]` item's citation, found by its
         `file`, `line` and `citation` text, takes `expected_prefix`; its
         path and line stay.
      2. Source lines: each `line-not-definition` item with exactly one
         `definition_lines` value moves its entry's `source_line` there (the
         entry at its `entry_index`, or the entries with its name, file and
         line). Every move is planned before any is made. The citations each
         move takes are those of either prefix, in `SKILL.md` and
         `references/**/*.md` as they stand after step 1, whose path,
         normalized as the citation check normalizes it, and first line are
         the entry's. Every planned move is applied in one pass, so a
         citation moves at most once (`LIMIT` moving from 6 to 7 and
         `DEFAULT` from 7 to 8 move a citation of line 6 to 7, never on to
         8), and a range moves both ends (`L10-12` to `L13-15`). A citation
         of a line another entry also records in that file stays: it may
         cite that other export (`shared-line`).

    A citation inside a `<!-- [MANUAL:name] -->` block never changes
    (`inside-manual-block`); the blocks are paired as skf-hash-content.py
    pairs them. Each changed file (markdown first, the provenance map last,
    as JSON indented by two spaces, non-ASCII kept, with a final newline;
    bytes that are not UTF-8 survive in markdown) is written through
    skf-atomic-write.py beside this script. `--manual-inventory` (the JSON
    `skf-hash-content.py manual-inventory` wrote for SKILL.md) is checked
    again after the writes. `--no-line-moves` leaves every source-line
    finding for a person (the drift override). `--dry-run` writes nothing.

    Emit JSON:
      {
        "applied": [
          {"kind": "citation-prefix", "file": "<rel md>", "line": <int>,
           "citation": "<as it was>", "fixed": "<as written>"},
          {"kind": "source-line", "entry_index": <int>,
           "export_name": "<name>", "source_file": "<rel path>",
           "from": <int>, "to": <int>},
          {"kind": "citation-line", "file": "<rel md>", "line": <int>,
           "citation": "<as it was>", "fixed": "<as written>",
           "export_names": ["<name>", ...]},
          ...
        ],
        "left_as_warn": [
          {... the verify item ..., "kind": "citation-prefix",
           "why": "citation-not-found" | "inside-manual-block"},
          {... the verify item ..., "kind": "source-line",
           "why": "no-definition-line"       # unverified, never moved
                  | "several-definition-lines" | "needs-decision"
                  | "line-moves-skipped" | "entry-not-found"},
          {"kind": "citation-line", "file", "line", "citation",
           "export_names": [...],
           "why": "shared-line" | "inside-manual-block"},
          ...
        ],
        "files_changed": ["<path>", ...],   # as the arguments name them
        "files_written": ["<path>", ...],   # [] with --dry-run
        "dry_run": <bool>,
        "manual_verify": null | {"preserved", "modified", "missing",
                                 "moved", "ok"},
        "summary": {"citation_prefixes_fixed": <int>,
                    "source_lines_moved": <int>,
                    "citations_moved": <int>,
                    "left_as_warn_count": <int>}
      }

    `fix` handles no `missing` or `orphaned` finding: read those from the
    verify result; `relabel --node-kinds` settles the `node_kinds` ones.
    Run `verify` again after it.

  fix --moves <moves.json> --provenance <provenance-map.json>
      --skill-dir <dir> [--manual-inventory <inventory.json>]
      [--dry-run] [-o <out.json>]

    Moves the citations of a run's moved exports, the second input `fix`
    takes in place of `--verify` (exactly one of the two; `--no-line-moves`
    goes with `--verify` only). `--moves` is either a change manifest, each
    of whose `per_file[].exports_affected[]` items with `change_type`
    `MOVED_EXPORT` moves from (its `old_file`, else the item's
    `file_path`, and its `old_line`) to (the item's `file_path`, its
    `new_line`), or gap-records' output (`mode` `gap-driven`), each of
    whose `verification[]` records that is `moved` and `in_map` moves from
    its `provenance_citation` to its `new_location`; any other JSON exits
    2. Every move goes through the one-pass rule of step 2 above: a
    citation of either prefix whose normalized path and first line are a
    move's old location takes the new line, a range shifts both ends by
    the same amount, a move across files rewrites the cited path to the
    new file as `--moves` writes it, and the prefix stays. A citation
    stays (`shared-line`) when another export claims its old location: a
    `--provenance` entry recorded there under a name the moves from it do
    not hold, moves from it to two targets, or an export `--moves` places
    there (a manifest `NEW_EXPORT` or `MODIFIED_EXPORT` at its file and
    `new_line`; another gap-driven record's located line: a `verified`
    one's `provenance_citation`, a `moved` or `re-extracted` one's
    `new_location`). A `MOVED_EXPORT`'s own new line is no claim, since
    merge writes the claimed exports' citations at their new lines before
    the move runs and a chain (`LIMIT` 6 to 7, `DEFAULT` 7 to 8) must still
    move each citation once. A citation inside a [MANUAL] block stays
    (`inside-manual-block`). It writes markdown only, through the atomic
    helper as above: `--provenance` is read, never written (the map the
    update started from, which update-skill's `apply` rewrites).

    Emit JSON: the keys above, `applied[]` and `left_as_warn[]` holding
    `citation-line` items only, with one more key:
        "warnings": ["provenance: citation <citation> at <file>:<line> not
                      moved (<why>): <export names>", ...]  # one per left item

  definition-lines --file <source_file> --name <export_name>
                   [--source-root <path>] [--line <n>]
                   [--export-type <type>] [-o <out.json>]

    The definition-line rules above for one export (update-skill's
    spot-check). `--file` is relative to `--source-root` (default: the
    current folder).

    Emit JSON:
      {
        "source_file": "<as given>",
        "export_name": "<as given>",
        "line_check": "checked" | "file-missing" | "skipped-export-type"
                      | "skipped-language",
        "definition_lines": [<int>, ...] | null,   # checked only
        "source_line": <int> | null,               # --line
        "line_is_definition": <bool> | null,       # --line, checked only
        "folded_to": "<base name>"                 # a folded variant only
      }

    With `--line`, a recorded line that is an indented match the column-0
    rule dropped joins `definition_lines`, and one that misses a Python
    `@overload` group gives its first line alone, as in `verify`. A
    bookkeeping variant the file never names is checked against its base,
    as in `verify`, and only then does the key `folded_to` appear.

  classify-stale --names <coverage.json> --provenance <provenance-map.json>
                 --source-root <path> [--inventory <inventory.json>]
                 [--brief <skill-brief.yaml>] [-o <out.json>]

    test-skill's fabricated-signature test, for each stale name (a
    documented name the enumerated source surface lacks): the
    definition-lines rules above, run for every provenance entry whose raw
    `export_name` is the name, at its `source_file` and `source_line`, with
    its `export_type`, and with no bookkeeping-variant fold (the name is
    judged as written). `--names` holds reconcile-coverage.py's result (its
    `stale` names) or a JSON array of names. `--inventory` holds the
    documented inventory, validate-inventory.py's `--output` file or its
    whole result: the `kind` it gives each name decides the module rule
    below. `--brief` holds the skill brief, whose `scope.include` and
    `scope.exclude` globs decide below which walked files count.

    Emit JSON, one item per name, in the order given (a repeated name once):
      [
        {"name": "<as given>",
         "fabricated": <bool>,
         "source": "<source_file>:<source_line>" | "<source_file>" | null,
         "defined_at": "<path>:<line>" | null,
         "declared_in": ["<path>:<line>", ...] | null,
         "reason": "not-defined" | "aliased" | "defined" | "unchecked"
                   | "no-entry",
         "entries": [{"source_file": "<as recorded>",
                      "source_line": <as recorded>,
                      "line_check": "checked" | "file-missing"
                                    | "skipped-export-type"
                                    | "skipped-language" | "unreadable"
                                    | "no-file",
                      "definition_lines": [<int>, ...] | null,
                      "star": "<module>"},  # an `export *` line only
                     ...],
         "renames": "<L>"},             # an `aliased` item only
        ...
      ]

    `fabricated` is true, with reason `not-defined`, when the name has an
    entry and every entry's `line_check` is `file-missing`, or `checked`
    with an empty `definition_lines`: the export is in neither the surface
    nor the cited file, and no line elsewhere renames to it, directly or
    through a chain of renames, the declaration a cited file holds. Such a
    rename gives the reason `aliased` and `fabricated` false, and its line
    is the `defined_at`: the first, per file of the name's declarations the
    lookup below finds (its `declared_in`, else the cited file's) and per
    candidate line of that file in order, that renames to NAME a name `L`
    which a file of a `checked` entry of the name declares by the same
    rule (no module or package so named counting; for `L` `default`, a
    column-0 `export default`, `export { X as default }` or
    `exports.default =`), or which a file the rename resolves to declares
    or renames, by the chain below, the chain ending at such a cited
    declaration. The name that cited file declares where the chain ends
    (for a one-step rename, the `L` the line at `defined_at` renames) is
    the item's `renames`, a key no other item has, so that test-skill's
    provenance line gap can say how to record the rename.
    The renames read:
      - an export-list item `L as NAME` (`export { ... }`,
        `export type { ... }`, on one line or an item of a multi-line
        list), `L` `default` when the list has a `from`
        (`export { default as NAME } from './m'`), a string side unquoted
        only when the string is the whole side (`L as "NAME"`,
        `"L" as NAME`), the list's opening line at column 0 as written, so
        that a comment may open it;
      - a local `export { NAME }` or `export type { NAME }` item without
        `as`, when a column-0 import binds NAME to another name
        (`import { L as NAME }`, or `import NAME from`, `L` `default`), at
        the export;
      - a column-0 `const`, `let` or `var NAME = L`, annotated or not
        (`const NAME: <type> = L`, the type on the line, holding no `;`
        and no `=` but in `=>`), `type NAME = L` or a generic
        `type NAME<P1, ...> = L<P1, ...>` whose arguments are its bare
        parameters, the same names in the same order, exported or not,
        `L` a bare identifier and the statement ending on its line;
      - for NAME `default`, a column-0 `export default L` (the `;`
        optional), `L` a bare identifier that a column-0 import or
        declaration of the same file binds and the statement ending on its
        line (`import { createEntry } from './api'` then
        `export default createEntry;`);
      - a Python `from X import L as NAME` item (on one line, in
        parentheses or after a backslash), the statement at column 0, one
        level in a column-0 `try`, `except`, `else`, `if`, `elif`, `with`
        or `finally` block or as such a header's one-line body after its
        first colon (`try: from X import L as NAME`), as compatibility
        imports are written, and a column-0 Python `NAME = L` or
        `NAME: <type> = L` (the type holding no `;` or `=`), `L` a bare
        identifier.
    A TS/JS line is read with its comments removed (an export list split
    on a copy whose one-line strings are blanked), a Python line with its
    `#` comment cut. `L` comes from the rename's `from` module, else from
    the column-0 import that binds `L`, whose imported name `L` becomes
    (`default` for a default import; a namespace import binds none). The
    module is resolved below the source root, under the lookup's guards
    for a cited file: a TS/JS `./` or `../` module from the renaming
    file's folder, as the path itself, a `.js`-family path's TypeScript
    twin (`./m.js` names `m.ts`), `<path><ext>` or `<path>/index<ext>`
    (`.d.ts` included); a Python relative module from the file's folder
    (`.` the folder's own `__init__`), or an absolute one below the parent
    of the file's package root, as `m.py`, `m.pyi`, `m/__init__.py` or
    `m/__init__.pyi`. An `L` with no module resolves to the renaming file
    itself. When one of the files the rename resolves to that declare `L`
    is a cited file, the rename is an alias. Otherwise the rename is
    followed as a chain through each of those files that declares `L` or
    renames it (a middle file): each candidate line of `L` there that
    renames it, by a form above (an export-list alias, a compatibility
    import in a block or on one line, an import then a plain re-export,
    an assignment of a bare `L`, annotated or not, an `export default L`
    of a bound `L`, which a rename of `default` reaches:
    `export { default as NAME } from`, or `import NAME from` re-exported)
    or by a Python column-0 `L = M.L2`, annotated or not, whose `M` a
    column-0 `from X import M` binds (the module `X` joined with `M`, `.`
    prefixes kept), is the next step, read and resolved the same way, until
    a step reaches a cited file that declares its name (an alias) or none
    does (fabricated, so a rename of another file's same-named `L` stays
    fabricated). Each (file, name) pair, a resolved file that declares
    or renames the name, is followed once per first rename, so a chain that
    loops ends, fabricated. When the first rename's module resolves to no
    file (a package name, never looked up in `node_modules`, a tsconfig
    `paths` alias, a package `exports` map, a path with no such file) or
    to files that declare no `L` (a barrel that re-exports it), any cited
    file that declares `L` clears the name; at a later step of a chain,
    such a module ends the chain, fabricated, unless one of those files
    renames `L` (a middle file, followed as above). The suspects' cited pass
    settles no such name at line 1 of a cited module or package so named
    before the walk, even when the module is itself the export (a column-0
    `export default` or `module.exports =`), so the walk always runs; the
    walk keeps its module rule, so `declared_in` may list that module at
    its line 1 when the walk reads its folder. Any other rename stays
    fabricated: a TS type assertion (`x as NAME`), a
    call or any other expression (`const NAME = make()`, and `NAME = a.b`
    at the documented name's own line: `L = M.L2` is only a later step of
    a chain), a default export of any other expression
    (`export default make();`, an object, an arrow, a value that goes on
    to the next line, an indented `export default L`, an `L` no import or
    declaration of the file binds), a generic alias whose parameters are
    constrained, defaulted, swapped or instantiated
    (`type NAME<T extends X> = L<T>`, `type NAME<T = X> = L<T>`,
    `type NAME<K, V> = L<V, K>`, `type NAME = L<string>`),
    `export * as NAME from`, Python
    `import M as NAME`, a rename of a module (`import * as L`,
    `from . import L as NAME`: no module or package so named declares
    `L`), a rename inside a `def`, a `class` or a deeper block (two levels
    in a `with` block included), `as NAME` in a comment or a string, a
    `default as NAME` whose module has only `module.exports =`, and a
    chain that leaves the files the resolver reads, loops or ends at
    another declaration.
    Otherwise the reason is `defined` (a cited file defines the name),
    `unchecked` (no rule could check a cited file, and none defines it) or
    `no-entry` (the map has no entry for the name).
    An entry with no `source_file` (update-skill writes one for an
    `unknown` NEW_EXPORT) cites no file to check: its `line_check` is
    `no-file`, which, like a skipped or unreadable check, neither proves
    the name fabricated nor shows it defined, so the name is `unchecked`
    unless another entry defines it. `source` is the citation of the first
    entry with a `source_file` (the file alone when its line is not a
    number), null when no entry has one.
    A `checked` entry with an empty `definition_lines` whose line, in a
    TS/JS file, is an `export * from` or `export type * from` statement
    gains `star`, the module that statement names: the line written at
    column 0 (a comment may open it), and the whole statement on the line
    once its comments are removed (`export * as NS from`, an indented
    star and a star split over lines get none). Such a line passes on
    another module's names, which no rule here reads, so test-skill can
    read the entry like the star (#1070). It changes no verdict: the item
    and its other keys stay as they are.

    `defined_at` is where the source declares a name that is not
    fabricated, so test-skill can tell a documented extra (a name outside
    the surface that the source still declares) from stale documentation;
    a fabricated name has none and no `declared_in` (both null), the
    lookup reading it only for an alias. A declaration is a line at
    column 0 that the definition-line rules match with imports left out:
    a `def`, `class`, assignment, annotation, type alias, TS/JS
    declaration, `exports.NAME =`, or an alias that renames
    (`import X as NAME`, `from X import Y as NAME`,
    `export { Y as NAME }`, `export * as NAME from`), a
    `module.exports` key with a value or a method, or, for the name
    `default`, any `export default` line. A plain or star import,
    an `as` that keeps the imported name (`from m import NAME as NAME`,
    `export { NAME as NAME }`), `export import NAME =`,
    `export default NAME`, an export-list item without `as`, a
    `module.exports` shorthand key, a binding whose value is an import
    (`require(...)` or `(await) import(...)`, on its line or the next:
    `const NAME = require(...)`, `const { NAME } = require(...)`,
    `exports.NAME = require(...)`, `{ NAME: require(...) }`), an
    indented line and any line of a Python
    file that does not tokenize never count, except that for the name
    `default` a column-0 `export default` line counts whatever follows it,
    an import or an imported local included (an item of a multi-line list
    counts at its own line, the list's opening line at column 0, so an
    `aliased` name's `defined_at` is its rename's line). For a
    `not-defined` name the alias check reads more lines than this rule: a
    file's candidate lines are every column-0 line that declares the name,
    a Python `from X import L as NAME` item one level in a column-0
    `try`, `except`, `else`, `if` or `elif` block, and a TS/JS local
    `export { NAME }` item when a column-0 import binds NAME to another
    name, and its `declared_in` lists the file at the first of them. A
    module or package named NAME (`NAME.py`, `NAME/__init__.py`, a TS/JS
    `NAME.<ext>` or `NAME/index.<ext>`) declares NAME too: at its line 1
    when no line of it
    declares NAME, unless `--inventory` gives NAME a `function`, `hook`,
    `class`, `interface`, `enum` or `type` kind (any of its kinds, when it
    gives several; a `method` kind is not read), no entry of NAME is a
    `module` or `package` one, and the file is not a TS/JS one that is
    itself the export (a column-0 `export default` or `module.exports =`),
    so that a removed function named after its file is no declaration
    (the inventory has no `module` kind). `declared_line` gives this
    answer for one file, the module rule optional, to a script that loads
    this one, and
    `baseline_gaps` applies it to the map's entries an extraction left
    out (skf-extraction-snapshot.py's baseline gaps and
    skf-build-change-manifest.py's `baseline-gaps`, which apply the module
    rule only to a `module` or `package` entry).

    The files: when a file the name's entries cite declares it,
    `defined_at` is that file's first declaration (the files in entry
    order), and `declared_in` is null. Otherwise `declared_in` lists, as
    sorted `<path>:<line>`, every file of the walk that declares the name,
    at its first declaration (a type stub, `NAME.pyi` or `NAME.d.ts`,
    beside its implementation is one file with it: the implementation),
    and `defined_at` is the one item when the list has exactly one and no
    walked Python file that does not tokenize holds the name (a homonym,
    two files or more, gives null: test-skill decides it by the files the
    skill cites), save for an `aliased` name, whose `defined_at` is its
    alias whatever the list holds. The walk reads, sorted by path, every
    file below the walk root: the deepest folder that the files of the
    map's entries share, widened to its package root (Python: the nearest
    folder at or above it that holds `__init__.py`, then up while the
    parent holds
    one, never the source root itself; TS/JS: the nearest folder at or
    above it that holds `package.json`), leaving out the entries whose
    file lies outside every package; the source root when none lies in
    one. Only the rule families (Python, TS/JS) the map's entries cite are
    read (both when no entry cites a file). The walk skips symlinks, hidden folders, test
    files and test configuration files (`conftest.py`, `jest.config.*`),
    `*.min.js`, and the folders generated, built, installed, vendored or
    test output lives in (`node_modules`, `dist`, `build`, `vendor`,
    `_vendor`, `tests`, `testing`, `fixtures`, `__mocks__`,
    `site-packages`, `env`, `bower_components`, `esm`, `cjs`, `umd` and
    the like), each judged on the path below the walk root, the
    end-to-end test folders `e2e` and `__fixtures__` wherever they lie,
    and, as the first folder below the walk root or below a package root
    inside it (a folder that holds `package.json`, the top of an
    `__init__.py` chain), `example`, `demo`, `demos`, `sample`, `samples`,
    `scripts`, `playground`, `bench`, `benchmark`, `migrations`, `docs`,
    `examples` and `benchmarks` unless it holds a file an entry cites
    (deeper in a package such a folder can be package code, as Storybook's
    `code/addons/docs/`). A cited file is read in any folder, a hidden one
    and one the walk skips included, but only inside the source root (a
    path that is absolute or climbs out of it is not read), with no
    symlink on its path and under a name the walk reads (no test file,
    test configuration file or `*.min.js`). The path is relative to the
    source root. With `--brief`, in the walk of the names that are not
    fabricated, a file the brief scopes out declares a name only when no
    walked file in the brief's scope does, its path matched as
    skf-extract-public-api.py matches it with
    skf-resolve-authoritative-files.py's glob rules: a `scope.exclude` glob
    matches it, or the brief has `scope.include` globs and none matches it
    (a sibling app's copy of a file then declares nothing beside the file
    in scope, while a name declared only outside the scope keeps its
    declarations). A cited file still settles a name wherever it lies, and
    the walk of the `not-defined` names counts every file, so that an
    alias in a file the brief scopes out still clears its name. A dotted
    name, or a map whose entries cite files
    but no Python or TS/JS one, is not looked up (`defined_at` and
    `declared_in` null, as for a fabricated name). A filesystem error
    during the lookup of the names that are not fabricated gives each of
    them null in both (the exit code stays 0). The `not-defined` names are
    looked up apart, after the others and whether or not that lookup
    failed: an error in their walk or their alias check keeps only them
    fabricated, and clears no other name's answer.

  kind-at --file <path> --line <n> --recipes <recipes>
          [--language <lang>] [--name <export_name>]
          [--source-root <path>] [-o <out.json>]

    The `kind` the matching recipe declares for a source line, the value an
    ast-grep entry records as `ast_node_type`. `--recipes` is a markdown
    file whose ```yaml fences hold the recipes (extraction-patterns.md) or
    a YAML file: one recipe per document, a list of recipes, or a mapping
    whose `recipes` key holds that list. A recipe is a mapping with `id`,
    `language` and a `rule` naming its `kind`. The file's language
    (`--language`, else its extension, mapped as for `--check-node-kinds`)
    picks the recipes: each id's form for that language, else its
    typescript or tsx form (for javascript, a form whose kinds the grammar
    lacks is skipped), with `language` rewritten. Each runs once through
    `ast-grep scan --stdin` on the file's bytes, from a temporary folder
    with a minimal sgconfig.yml. A recipe matches when its `$NAME` is on
    `--line` (and, with `--name`, is that name's last segment).

    Emit JSON:
      {
        "file": "<as given>",
        "language": "<ast-grep language>" | null,
        "line": <int>,
        "name": "<as given>" | null,
        "status": "found" | "ambiguous" | "no-match" | "incomplete"
                  | "skipped-no-language" | "skipped-no-recipes"
                  | "skipped-no-ast-grep",
        "kind": "<the one kind the matches declare>" | null,   # found only
        "matches": [{"recipe": "<id>", "kind": "<kind>",
                     "name": "<$NAME>"}, ...],
        "errors": [{"recipe": "<id>" | null, "language": "<language>",
                    "reason": "ast-grep-error" | "ast-grep-timeout"
                              | "temp-folder-error",
                    "detail": "<text>"}, ...]
      }

    `incomplete`: a recipe run failed, so no kind is given even when others
    matched. Never invent a kind: anything but `found` leaves the entry as
    it is.

  relabel --provenance <provenance-map.json> --recipes <recipes>
          [--violations <stats.json>] [--node-kinds <verify.json>]
          [--records <reextract-records.json>] [--source-root <path>]
          [--no-kind-at] [-o <out.json>]

    Applies create-skill's relabel-rule.md to a provenance map and writes
    it, so no prompt relabels an entry by hand. It needs at least one of
    `--violations` (skf-render-metadata-stats.py's JSON: each
    `coherence.violations[]` item on `provenance.entries[<i>].<field>`)
    and `--node-kinds` (a verify result's `node_kinds[]`). Each item names
    its entry by index, confirmed by its `export_name` (and, for a node
    kind, its `source_file`), else it is left as `entry-not-found`. An
    entry's record is the record of its `export_name` in the `--records`
    block of its `source_file` (the one at its `source_line` when there are
    several).

      1. Labels: a `confidence`, `signature_source` or null `ast_node_type`
         violation sets the field to the violation's `expected`. An
         `extraction_method` violation sets the method of the entry's
         record (`ast-grep` or `source-read`), else `source-read`, and the
         entry is checked once more by skf-render-metadata-stats.py's
         `check_label_agreement` (loaded from beside this script) and
         relabeled by what it reports.
      2. Node kind: an `ast_node_type` whose `expected` is `non-null`, and
         each `node_kinds[]` item, takes the `rule.kind` of the recipe the
         entry's record names in `ast_recipe` (that id's form for the
         file's language, as kind-at picks it, else the kind all its forms
         share), else the `kind-at` kind at the entry's current
         `source_line` when its status is `found`. It never changes
         `extraction_method`. With `--no-kind-at` (the drift override), or
         with no `--source-root` folder, no kind is looked up.

    A map that changed is written as `fix` writes it (two-space JSON,
    non-ASCII kept, a final newline, through skf-atomic-write.py beside
    this script).

    Emit JSON:
      {
        "relabeled": [{"entry_index", "export_name", "source_file",
                       "field", "from", "to"}, ...],
        "left_as_warn": [{"entry_index", "export_name", "source_file",
                          "field",
                          "why": "entry-not-found" | "kind-at-skipped"
                                 | "no-source-root" | "kind-at-failed"
                                 | <a kind-at status: "ambiguous",
                                    "no-match", "incomplete",
                                    "skipped-..." >}, ...],
        "files_written": ["<path>", ...],
        "summary": {"relabeled_count": <int>, "left_as_warn_count": <int>}
      }

CLI examples:
  uv run skf-verify-provenance-completeness.py verify \\
      --metadata {skill_package}/metadata.json \\
      --provenance {forge_version}/provenance-map.json \\
      --source-root {source_root} \\
      --skill-dir {skill_package} \\
      --check-node-kinds -o {verify_json}
  uv run skf-verify-provenance-completeness.py fix --verify {verify_json} \\
      --provenance {forge_version}/provenance-map.json \\
      --skill-dir {skill_package}
  uv run skf-verify-provenance-completeness.py fix \\
      --moves {run_dir}/change-manifest.json \\
      --provenance {provenance_map_path} --skill-dir {staged_package} \\
      -o {run_dir}/citation-moves.json
  uv run skf-verify-provenance-completeness.py definition-lines \\
      --source-root {source_root} --file src/api.py --name search --line 26
  uv run skf-verify-provenance-completeness.py classify-stale \\
      --names {run_dir}/coverage.json \\
      --provenance {forge_version}/provenance-map.json \\
      --source-root {source_root} --inventory {run_dir}/inventory.json \\
      --brief {forge_data_folder}/{skill_name}/skill-brief.yaml \\
      -o {run_dir}/stale.json
  uv run skf-verify-provenance-completeness.py kind-at \\
      --source-root {source_root} --file src/api.ts --line 12 --name Store \\
      --recipes {extractionPatternsData}
  uv run skf-verify-provenance-completeness.py relabel \\
      --provenance {forge_version}/provenance-map.json \\
      --violations {run_dir}/stats.json --recipes {extractionPatternsData} \\
      --records {run_dir}/reextract-records.json --source-root {source_root}

Exit codes:
  verify
    0  verification ran and found nothing (status "pass")
    1  verification ran and found missing / orphaned / stale entries,
       citation findings or node-kind findings (status "findings");
       advisory: the caller decides how to surface it
  fix (either input)
    0  nothing left as a WARN (and manual_verify ok when it ran)
    1  something left as a WARN, or manual_verify not ok
  definition-lines
    0  the rules answered (whatever `line_check` says)
  classify-stale
    0  every name was classified (whatever `fabricated` says)
  kind-at
    0  status "found"
    1  any other status
  relabel
    0  nothing left as a WARN
    1  something left as a WARN
  2  error, for every subcommand (an input file or folder not found,
     --skill-dir without a SKILL.md, malformed JSON or YAML, a verify
     result without stale[] and citations[], a --moves file that is
     neither a change manifest nor gap-records' output, --verify and
     --moves together or neither, relabel with neither --violations nor
     --node-kinds, a --violations file with no coherence.violations[], a
     --node-kinds file with no node_kinds[], --names without a list of
     names, --inventory without an `exports` list, a --brief that is not
     a YAML mapping, no recipe in --recipes, no PyYAML for kind-at,
     relabel or --brief, an atomic write that failed, an -o
     file that cannot be written, or any unexpected failure, such as an
     unreadable file; once fix has started writing, stderr names the files
     already written); one line on stderr and no JSON
"""

from __future__ import annotations

import argparse
import bisect
import copy
import importlib.util
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path
from typing import Callable


STALE_FILE_MISSING = "file-missing"
STALE_LINE_OOB = "line-out-of-bounds"
STALE_LINE_INVALID = "line-invalid"
STALE_LINE_NOT_DEFINITION = "line-not-definition"

CITATION_PREFIX_MISMATCH = "prefix-mismatch"
CITATION_AST_WITHOUT_AST_GREP = "ast-without-ast-grep"

PYTHON_EXTENSIONS = frozenset({".py", ".pyi"})
TSJS_EXTENSIONS = frozenset(
    {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
)
# export_type values that name a whole module or package: no definition line.
NO_DEFINITION_EXPORT_TYPES = frozenset({"module", "package"})
# The scope_type whose exports[] is empty by design (entries are per-citation).
REFERENCE_APP = "reference-app"

# extraction_method -> the citation prefix it implies
METHOD_PREFIX = {
    "ast-grep": "AST",
    "ast_bridge": "AST",
    "source-read": "SRC",
    "source_reading": "SRC",
}
AST_METHODS = frozenset({"ast-grep", "ast_bridge"})
# Every extraction_method SKF writes (the same list skf-render-metadata-stats
# checks labels against).
KNOWN_METHODS = frozenset(
    {
        "ast-grep",
        "source-read",
        "ast_bridge",
        "source_reading",
        "qmd_bridge",
        "compose-from-skill",
    }
)

NODE_KIND_INVALID = "invalid-kind"
NODE_KIND_ERROR = "error-kind"
# Why an entry's kind went unjudged (node_kinds_unchecked[].reason).
UNCHECKED_AST_GREP_ERROR = "ast-grep-error"
UNCHECKED_TIMEOUT = "ast-grep-timeout"
UNCHECKED_TEMP_FOLDER = "temp-folder-error"
# The node tree-sitter makes of code it cannot parse. ast-grep accepts it as
# a kind, but no recipe declares it, so an entry recording it guessed.
ERROR_NODE_KIND = "ERROR"
# Every named node kind of a grammar ast-grep ships has this shape. Anything
# else is judged without ast-grep: ast-grep trims surrounding whitespace, and
# `& | % ^` would reach cmd.exe through an npm `.cmd` shim on Windows.
NODE_KIND_SHAPE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A kind no grammar has. ast-grep must reject it before its answers are read.
BOGUS_NODE_KIND = "skf_no_such_node_kind"
# An explicit, valid sgconfig.yml, so no sgconfig.yml in the temporary
# folder's ancestors is read.
MINIMAL_SGCONFIG = "ruleDirs: []\n"
# source_file extension -> the ast-grep language whose grammar names its kinds
AST_GREP_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
}
NODE_KIND_TIMEOUT_SEC = 20  # per ast-grep call; each parses one tiny rule

# kind-at: a ```yaml fence in a markdown recipe file (extraction-patterns.md).
_MD_YAML_FENCE_RE = re.compile(r"^```yaml[ \t]*\n(.*?)^```", re.M | re.S)
# file language -> the recipe languages whose form of a recipe it runs, with
# `language:` rewritten, when the recipe has no form of its own for it (the
# language selection note in extraction-patterns-by-hand.md): typescript and tsx
# share their recipes, and javascript runs a TypeScript recipe with no
# javascript form (one whose kinds the grammar lacks is skipped).
RECIPE_LANGUAGE_FALLBACKS = {
    "typescript": ("tsx",),
    "tsx": ("typescript",),
    "javascript": ("typescript", "tsx"),
}
KIND_AT_TIMEOUT_SEC = 30  # per ast-grep call; each scans one file

# fix: what each applied or left item fixes.
FIX_CITATION_PREFIX = "citation-prefix"
FIX_SOURCE_LINE = "source-line"
FIX_CITATION_LINE = "citation-line"
# The [MANUAL] markers skf-hash-content.py pairs (its _OPEN_RE / _CLOSE_RE,
# on text instead of bytes; the test pins the two copies together). ASCII,
# so `\s` is the whitespace a bytes pattern knows: a marker spaced with
# U+00A0 is no marker to either.
_MANUAL_OPEN_RE = re.compile(r"<!--\s*\[MANUAL:([^\]]+)\]\s*-->", re.ASCII)
_MANUAL_CLOSE_RE = re.compile(r"<!--\s*\[/MANUAL:([^\]]+)\]\s*-->", re.ASCII)
# One line with its ending, split where `check_citation` counts a line.
_LINE_WITH_END_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")
ATOMIC_WRITE_HELPER = "skf-atomic-write.py"
HASH_CONTENT_HELPER = "skf-hash-content.py"
# classify-stale's `--brief`: a skill brief's YAML and scope glob rules
BRIEF_RESOLVER_HELPER = "skf-resolve-authoritative-files.py"
ATOMIC_WRITE_TIMEOUT_SEC = 60


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def load_json_object(path: Path, label: str) -> dict:
    """Read a JSON file and require a top-level object. Raises ValueError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {label} {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{label} {path} must be a JSON object at top level; "
            f"got {type(data).__name__}"
        )
    return data


# --------------------------------------------------------------------------
# Extraction / canonicalization
# --------------------------------------------------------------------------


def extract_export_names(metadata: dict) -> list[str]:
    """Pull documented export names from metadata.exports.

    `exports` is a list of export-name strings (per the skill templates).
    Defensively also accept dict items carrying `name` / `export_name`.
    Non-string / unnamed items are skipped. Order preserved; caller dedupes.
    """
    names: list[str] = []
    exports = metadata.get("exports")
    if not isinstance(exports, list):
        return names
    for item in exports:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            nm = item.get("name") or item.get("export_name")
            if isinstance(nm, str) and nm:
                names.append(nm)
    return names


def extract_reexport_map(prov: dict) -> dict[str, str]:
    """Build the `{internal: public}` re-export map.

    Mirrors `skf-load-provenance.extract_reexport_map`: top-level
    `reexport_map` is authoritative; per-entry `reexported_as` fills gaps.
    Non-string keys/values skipped.
    """
    out: dict[str, str] = {}
    top = prov.get("reexport_map")
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    entries = prov.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            internal = entry.get("export_name")
            public = entry.get("reexported_as")
            if isinstance(internal, str) and isinstance(public, str):
                out.setdefault(internal, public)
    return out


def is_reference_app(metadata: dict) -> bool:
    """True when metadata.json's `scope_type` is `reference-app`."""
    scope_type = metadata.get("scope_type")
    return isinstance(scope_type, str) and scope_type.strip() == REFERENCE_APP


def canon(name: str, reexport_map: dict[str, str]) -> str:
    """Canonicalize an export name to its public form via reexport_map.

    Idempotent for names that are not internal (public names are not keys).
    """
    return reexport_map.get(name, name)


def provenance_entry_names(prov: dict) -> list[str]:
    """Raw `export_name` of every well-formed provenance entry (order kept)."""
    names: list[str] = []
    entries = prov.get("entries")
    if not isinstance(entries, list):
        return names
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nm = entry.get("export_name")
        if isinstance(nm, str) and nm:
            names.append(nm)
    return names


# --------------------------------------------------------------------------
# Citation resolution
# --------------------------------------------------------------------------


def _coerce_line(value: object) -> int | None | str:
    """Return an int line number, None (tolerated), or a sentinel str for
    an un-coercible non-null value (reported as line-invalid)."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass — a boolean line number is nonsense
        return "invalid"
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return "invalid"
    return "invalid"


def check_citation(
    source_file: object, source_line: object, source_root: Path
) -> str | None:
    """Resolve a single `source_file:source_line` citation under source_root.

    Returns a stale reason (one of the STALE_* constants) when the citation
    does not resolve, or None when it is valid OR tolerated.

    Tolerated (returns None): source_file missing/empty, or source_line null
    or empty — `unknown`-outcome entries legitimately carry null citations
    (write.md §3), so an absent citation is not "stale".
    """
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    line = _coerce_line(source_line)
    if line is None:
        return None
    if isinstance(line, str):  # sentinel for un-coercible non-null value
        return STALE_LINE_INVALID

    rel = source_file.strip().replace("\\", "/")
    target = (source_root / rel).resolve()
    if not target.is_file():
        return STALE_FILE_MISSING

    if line < 1:
        return STALE_LINE_OOB
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            line_count = sum(1 for _ in fh)
    except OSError:
        return STALE_FILE_MISSING
    if line > line_count:
        return STALE_LINE_OOB
    return None


# --------------------------------------------------------------------------
# Definition lines
# --------------------------------------------------------------------------

_PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(.*)$")
_PY_IMPORT_RE = re.compile(r"^\s*import\s+(.*)$")
_PY_IMPORT_ITEM_RE = re.compile(r"^([\w.]+)(?:\s+as\s+(\w+))?$")
_PY_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
# `A = value`, `A = B = value`: every name left of an `=` that is not `==`.
_PY_ASSIGN_CHAIN_RE = re.compile(r"^\s*((?:[A-Za-z_]\w*\s*=(?!=)\s*)+)")
# `A, B = value`, `(A, *B) = value`, `A, = value`.
_PY_TARGET_LIST_RE = re.compile(
    r"^\s*[(\[]?\s*"
    r"(\*?[A-Za-z_]\w*\s*,(?:\s*\*?[A-Za-z_]\w*\s*,)*(?:\s*\*?[A-Za-z_]\w*)?)"
    r"\s*[)\]]?\s*=(?!=)"
)
# `def \` or `class \`: the name is on the next line.
_PY_SPLIT_DECL_RE = re.compile(r"^\s*(?:async\s+def|def|class)\s*\\$")
# A line that can matter to a name it does not hold: an import (which may go
# on over the next lines) or a `def \` / `class \` whose name is on the next.
_PY_NAMELESS_MATCH_RE = re.compile(r"^\s*(?:from|import|async|def|class)\b")
# The decorator of an `@overload` stub, imported by name or used through its
# module under any name (`typing`, `typing_extensions`, `t` after
# `import typing as t`).
_PY_OVERLOAD_RE = re.compile(r"^\s*@\s*(?:[A-Za-z_]\w*\.)?overload\s*$")
# Tokens that never begin a statement.
_PY_LAYOUT_TOKENS = frozenset(
    {
        tokenize.NL,
        tokenize.COMMENT,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
)

# `@name`, `@a.b`, `@name(...)` (one level of nested brackets in the call).
_JS_DECORATOR = r"@[\w$]+(?:\.[\w$]+)*(?:\((?:[^()]|\([^()]*\))*\))?"
_JS_MODIFIERS = (
    rf"(?:(?:export|default|async|declare|abstract)\s+|{_JS_DECORATOR}\s*)*"
)
_JS_KINDS = (
    r"(?:function(?:\s*\*\s*|\s+)"
    r"|(?:class|interface|type|enum|namespace|let|var)\s+"
    r"|const\s+(?:enum\s+)?)"
)
_JS_MEMBER_MODIFIERS = (
    r"(?:(?:public|private|protected|static|readonly|async|abstract"
    r"|override|declare|get|set)\s+)*"
)
# An identifier, or a string name (`"a-b"`) in an export list.
_JS_NAME_OR_STRING = r"(?:[\w$]+|\"[^\"]*\"|'[^']*')"
_JS_EXPORT_LIST_RE = re.compile(r"^\s*export\s+(?:type\s+)?\{(.*)$")
_JS_EXPORT_ITEM_RE = re.compile(
    rf"^(?:type\s+)?({_JS_NAME_OR_STRING})(?:\s+as\s+({_JS_NAME_OR_STRING}))?$"
)
_JS_MODULE_EXPORTS_OBJECT_RE = re.compile(r"^\s*module\.exports\s*=\s*\{(.*)$")
# A bound value that is an import: `require(...)`, `import(...)`, awaited, in
# parentheses (`(await import("./m")).X`) or in one helper call
# (`__importDefault(require("./m"))`).
_JS_IMPORT_VALUE_RE = re.compile(
    r"^[\s(]*(?:await\s+)?(?:[\w$.]+\s*\(\s*)?(?:await\s+)?(?:require|import)\s*\("
)
# The start of such a value that goes on on the next line: nothing yet, a
# parenthesis, or a helper call's name and parenthesis.
_JS_IMPORT_VALUE_OPEN_RE = re.compile(r"^[\s(]*(?:await\s+)?(?:[\w$.]+\s*\(\s*)?$")
# A `const`, `let` or `var` statement: its declarator list.
_JS_VAR_DECL_RE = re.compile(
    rf"^\s*{_JS_MODIFIERS}(?:const|let|var)\s+(?!enum(?![\w$]))(.*)$"
)
# A declaration whose name is on the next line: the line ends in its keyword.
_JS_SPLIT_DECL_RE = re.compile(
    rf"^\s*{_JS_MODIFIERS}(?P<kind>function(?:\s*\*)?|class|interface|type"
    r"|enum|namespace|let|var|const(?:\s+enum)?)$"
)
# The keywords every line that opens a statement going on below holds (a
# `const` / `let` / `var` list, a split declaration, `export {`,
# `module.exports = {`): a line with none of them, and not the name, can
# match no rule while no statement is open.
_JS_OPENING_WORDS = ("const", "let", "var", "function", "class", "interface", "type", "enum", "namespace",
                     "export", "module")


def _js_quiet_lines(code_lines: list[str]) -> list[bool]:
    """For each comment-free line, True when it holds none of
    `_JS_OPENING_WORDS`."""
    return [not any(word in code for word in _JS_OPENING_WORDS) for code in code_lines]
_JS_VAR_KEYWORDS = frozenset({"const", "let", "var"})
# How a `const` / `let` / `var` list that did not end on its line goes on
# (`_js_declarators`): the next line begins a declarator (this one ended
# with a top-level comma); it finishes the current one (this one ended
# inside a bracket, or after an operator waiting for its operand); or it
# goes on only when it starts with an operator (this one ended with a
# value, as a member chain or a ternary broken over lines does).
_DECL_NEXT = "next"
_DECL_OPEN = "open"
_DECL_MAYBE = "maybe"
# What `_js_declarators` gives: None, or (brackets left open, how) the list
# goes on with, and the pieces that begin a declarator.
_DeclSplit = tuple[tuple[str, str] | None, list[str]]
# What `_js_destructured` gives for a `const` / `let` / `var` statement
# whose first declarator is a destructuring pattern: the (name, line) of
# each name it binds, and the (line, text after the `=` on that line) its
# initializer starts at, None when it has none.
_PatternDecl = tuple[list[tuple[str, int]], tuple[int, str] | None]
# After one of these, `/` begins a regular expression and `<` begins JSX, a
# type assertion or a generic arrow function's type parameters.
_JS_EXPRESSION_START = frozenset("([{,;=?:&|^%+-*/<>!~")
# A line that ends in one of these leaves an operator waiting for its operand.
_JS_OPERAND_PENDING = frozenset("=?:&|^%+-*/<>.")
# A line that begins with one of these goes on with the expression above it.
_JS_CONTINUATION_START = frozenset(".?:,&|^%+-*/=<>")


def definition_name(export_name: str) -> str:
    """The name a definition line must carry: the last segment of a dotted
    export name (`App.update` -> `update`), else the name itself."""
    return export_name.rsplit(".", 1)[-1]


# Bookkeeping variants folded to their base name, in rule order: test-skill's
# Source Access Protocol defines the fold (`X_def`, `X_exact`, `a11y_X` -> `X`).
# Keep identical to FOLD_SUFFIXES and FOLD_PREFIX in load-coverage-inputs.py.
FOLD_SUFFIXES = ("_def", "_exact")
FOLD_PREFIX = "a11y_"


def fold_base(export_name: str) -> str | None:
    """The base name a bookkeeping variant folds to, None for a name that is
    no variant: a suffix in FOLD_SUFFIXES first, else FOLD_PREFIX, never the
    whole name (`_def` alone is no variant). The rules of
    load-coverage-inputs.py `fold_names`, without `--fold-prefix` or
    `--keep`: the line check tries the raw name first, so a real export
    named like a variant is never folded."""
    for suffix in FOLD_SUFFIXES:
        if export_name.endswith(suffix) and len(export_name) > len(suffix):
            return export_name[: -len(suffix)]
    if export_name.startswith(FOLD_PREFIX) and len(export_name) > len(FOLD_PREFIX):
        return export_name[len(FOLD_PREFIX):]
    return None


def _read_lines(path: Path) -> list[str] | None:
    """Read a text file as lines numbered like `check_citation` counts them
    (universal newlines; a UTF-8 BOM is dropped so it never hides line 1).
    None when the file cannot be read."""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return [ln.rstrip("\n") for ln in fh]
    except OSError:
        return None


def _read_source(path: Path) -> str:
    """A text file's content, decoded as `_read_lines` decodes it. Raises
    OSError when the file cannot be read."""
    with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def _text_lines(text: str) -> list[str]:
    """`_read_source`'s text as the lines `_read_lines` gives for the file."""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _is_column_0(text: str) -> bool:
    """True when a line starts at column 0 (no leading whitespace)."""
    return not text[:1].isspace()


def _py_statement_starts(lines: list[str]) -> set[int] | None:
    """Line numbers on which a Python statement begins.

    Uses the stdlib tokenizer, so a line inside a string or inside brackets
    (a docstring, a keyword argument, a dict entry, a parameter on its own
    line) never reads as a definition. None when the file does not tokenize:
    every line is then a candidate.
    """
    starts: set[int] = set()
    at_start = True
    readline = io.StringIO("\n".join(lines) + "\n").readline
    try:
        for tok in tokenize.generate_tokens(readline):
            if tok.type == tokenize.NEWLINE:
                at_start = True
            elif tok.type in _PY_LAYOUT_TOKENS:
                continue
            elif at_start:
                starts.add(tok.start[0])
                at_start = False
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    return starts


def _js_code_lines(lines: list[str]) -> list[str]:
    """Each TS/JS line with its comments removed: `//` to the end of the
    line, and `/* ... */` across lines, both only outside a '...', "..." or
    `...` string. A string is followed within its line only: a template
    literal that spans lines is not tracked, so each line starts outside
    any string. A backslash outside a string escapes the next character, so
    a regex literal such as `/\\/*/` opens no comment."""
    out: list[str] = []
    in_block = False
    for text in lines:
        buf: list[str] = []
        quote: str | None = None
        i, n = 0, len(text)
        while i < n:
            if in_block:
                end = text.find("*/", i)
                if end < 0:
                    break
                in_block = False
                buf.append(" ")
                i = end + 2
                continue
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                buf.append(text[i : i + 2])
                i += 2
                continue
            if quote is not None:
                if ch == quote:
                    quote = None
            elif ch in "'\"`":
                quote = ch
            elif text.startswith("//", i):
                break
            elif text.startswith("/*", i):
                in_block = True
                i += 2
                continue
            buf.append(ch)
            i += 1
        out.append("".join(buf).rstrip())
    return out


class _SourceCache:
    """Source lines, Python statement starts, TS/JS comment-free lines and
    the names TS/JS destructuring patterns bind, read once per file, and
    TS/JS declarator lists, split once per line (neither depends on the
    export looked up)."""

    def __init__(self) -> None:
        self._lines: dict[Path, list[str] | None] = {}
        self._starts: dict[Path, set[int] | None] = {}
        self._js_code: dict[Path, list[str]] = {}
        self._js_quiet: dict[Path, list[bool]] = {}
        self._js_patterns: dict[Path, dict[int, _PatternDecl]] = {}
        self._js_decl: dict[tuple[str, str, bool], _DeclSplit] = {}

    def lines(self, path: Path) -> list[str] | None:
        if path not in self._lines:
            self._lines[path] = _read_lines(path)
        return self._lines[path]

    def py_statement_starts(self, path: Path, lines: list[str]) -> set[int] | None:
        if path not in self._starts:
            self._starts[path] = _py_statement_starts(lines)
        return self._starts[path]

    def js_code_lines(self, path: Path, lines: list[str]) -> list[str]:
        if path not in self._js_code:
            self._js_code[path] = _js_code_lines(lines)
        return self._js_code[path]

    def js_quiet_lines(self, path: Path, code_lines: list[str]) -> list[bool]:
        if path not in self._js_quiet:
            self._js_quiet[path] = _js_quiet_lines(code_lines)
        return self._js_quiet[path]

    def js_destructured(
        self, path: Path, code_lines: list[str]
    ) -> dict[int, _PatternDecl]:
        if path not in self._js_patterns:
            self._js_patterns[path] = _js_destructured(code_lines)
        return self._js_patterns[path]

    def js_declarators(
        self, text: str, opened: str = "", fresh: bool = True
    ) -> _DeclSplit:
        key = (text, opened, fresh)
        if key not in self._js_decl:
            self._js_decl[key] = _js_declarators(text, opened, fresh)
        return self._js_decl[key]


def _py_import_binds(
    items: str, name: str, from_import: bool, alias_only: bool = False
) -> bool:
    """True when an import item list binds `name` (with `alias_only`, only
    through an explicit `as name` that renames: `from m import name as
    name` and `import a.name as name` keep the imported name)."""
    items = items.split("#", 1)[0]
    for raw in items.replace("(", " ").replace(")", " ").replace("\\", " ").split(","):
        m = _PY_IMPORT_ITEM_RE.match(raw.strip())
        if not m:
            continue
        target, alias = m.group(1), m.group(2)
        if alias is not None:
            if alias_only and alias == target.rsplit(".", 1)[-1]:
                continue
            bound = alias
        elif alias_only:
            continue
        elif from_import:
            bound = target
        else:
            bound = target.split(".", 1)[0]  # `import a.b` binds `a`
        if bound == name:
            return True
    return False


def _py_assigned_names(code: str) -> set[str]:
    """Names an assignment statement binds (`A = B = v`, `A, *B = v`)."""
    names: set[str] = set()
    m = _PY_ASSIGN_CHAIN_RE.match(code)
    if m:
        names.update(_PY_IDENT_RE.findall(m.group(1)))
    m = _PY_TARGET_LIST_RE.match(code)
    if m:
        names.update(_PY_IDENT_RE.findall(m.group(1)))
    return names


def _python_definition_lines(
    lines: list[str],
    name: str,
    starts: set[int] | None,
    declarations_only: bool = False,
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    A line inside a parenthesized or backslash-continued import takes the
    column of the line the import statement starts on, and so does the name
    line of a `def \\` or `class \\` whose name is on the next line. A
    `from X import *` line counts only when no other line defines `name` (a
    re-export the extraction could not trace further is cited at its star
    import). With `declarations_only`, an import counts only when it binds
    `name` through an explicit `as name` that renames (`_py_import_binds`),
    and a star import never does.
    """
    esc = re.escape(name)
    decl = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{esc}(?!\w)")
    leading_name = re.compile(rf"^\s*{esc}(?!\w)")
    annotated = re.compile(rf"^\s*{esc}\s*:(?!=)")
    type_alias = re.compile(rf"^\s*type\s+{esc}\s*(?:\[[^\]]*\]\s*)?=(?!=)")
    found: list[tuple[int, bool]] = []
    star_imports: list[tuple[int, bool]] = []
    # An import statement that continues on the next line:
    # (closing mark "paren" or "backslash", column 0, from-import).
    cont: tuple[str, bool, bool] | None = None
    for number, text in enumerate(lines, start=1):
        code = text.split("#", 1)[0]
        if cont is not None:
            mark, top, from_import = cont
            if mark == "paren":
                if ")" in code:
                    code = code.split(")", 1)[0]
                    cont = None
            else:
                stripped = code.rstrip()
                if stripped.endswith("\\"):
                    code = stripped[:-1]
                else:
                    cont = None
            if _py_import_binds(code, name, from_import, declarations_only):
                found.append((number, top))
            continue
        if starts is not None and number not in starts:
            continue
        if name not in code and not _PY_NAMELESS_MATCH_RE.match(code):
            continue  # no rule below can match it: spares a scan per name
        top = _is_column_0(text)
        if (
            decl.match(code)
            or annotated.match(code)
            or type_alias.match(code)
            or name in _py_assigned_names(code)
        ):
            found.append((number, top))
            continue
        if _PY_SPLIT_DECL_RE.match(code.rstrip()):
            # `def \` then the name: cite the name's line, as the recipes do.
            if number < len(lines) and leading_name.match(
                lines[number].split("#", 1)[0]
            ):
                found.append((number + 1, top))
            continue
        m = _PY_FROM_IMPORT_RE.match(code)
        from_import = m is not None
        if m is None:
            m = _PY_IMPORT_RE.match(code)
        if m is None:
            continue
        rest = m.group(1)
        if from_import and rest.strip() == "*":
            if not declarations_only:
                star_imports.append((number, top))
            continue
        if from_import and rest.lstrip().startswith("(") and ")" not in rest:
            cont = ("paren", top, True)
        elif rest.rstrip().endswith("\\"):
            cont = ("backslash", top, from_import)
            rest = rest.rstrip()[:-1]
        if _py_import_binds(rest, name, from_import, declarations_only):
            found.append((number, top))
    return found or star_imports


def _py_overloaded(lines: list[str], number: int, starts: set[int] | None) -> bool:
    """True when the `def` on line `number` has `@overload` or
    `@<module>.overload` (`@typing.overload`, `@t.overload`) in its
    contiguous decorator block: the decorator lines at its indentation
    right above it, up to a blank line or a line that is not a decorator.
    A comment line is passed over, and so, in a file that tokenizes, is a
    line on which no statement begins (a decorator's arguments over
    several lines)."""
    text = lines[number - 1]
    indent = text[: len(text) - len(text.lstrip())]
    i = number - 1
    while i >= 1:
        text = lines[i - 1]
        code = text.split("#", 1)[0]
        if not text.strip():
            return False
        if not code.strip() or (starts is not None and i not in starts):
            i -= 1
            continue
        if not code.lstrip().startswith("@") or text[: len(text) - len(text.lstrip())] != indent:
            return False
        if _PY_OVERLOAD_RE.match(code):
            return True
        i -= 1
    return False


def _py_enclosing_line(
    lines: list[str], number: int, indent: str, starts: set[int] | None
) -> int | None:
    """The line of the block that holds the statement on line `number`,
    indented by `indent`: the nearest line above it where a statement
    begins with less indentation. None at module level."""
    i = number - 1
    while indent and i >= 1:
        text = lines[i - 1]
        if text.split("#", 1)[0].strip() and (starts is None or i in starts):
            if len(text) - len(text.lstrip()) < len(indent):
                return i
        i -= 1
    return None


def _python_overload_start(
    lines: list[str], name: str, defs: list[int], starts: set[int] | None
) -> int | None:
    """The first of `defs` when they are one `@overload` group: two lines
    or more, each a `def` / `async def NAME` line, all at one indentation
    in one enclosing block (`_py_enclosing_line`, so two classes'
    methods never make one group), and each but at most the last
    decorated as an overload (`_py_overloaded`). None otherwise."""
    if len(defs) < 2:
        return None
    decl = re.compile(rf"^(\s*)(?:async\s+def|def)\s+{re.escape(name)}(?!\w)")
    indents = set()
    for number in defs:
        m = decl.match(lines[number - 1].split("#", 1)[0])
        if m is None:
            return None
        indents.add(m.group(1))
    if len(indents) > 1:
        return None
    (indent,) = indents
    if len({_py_enclosing_line(lines, number, indent, starts) for number in defs}) > 1:
        return None
    if not all(_py_overloaded(lines, number, starts) for number in defs[:-1]):
        return None
    return defs[0]


def _js_export_item_binds(item: str, name: str, alias_only: bool = False) -> bool:
    """True when one `export { ... }` item exposes `name`: the name after
    `as`, else (unless `alias_only`) the item's own name, an identifier or
    a string. With `alias_only`, an `as` that keeps the item's own name
    (`NAME as NAME`) does not count either."""
    m = _JS_EXPORT_ITEM_RE.match(item.strip())
    if not m or (alias_only and m.group(2) is None):
        return False
    own, exposed = (
        s[1:-1] if s[:1] in ("'", '"') else s
        for s in (m.group(1), m.group(2) or m.group(1))
    )
    if alias_only and exposed == own:
        return False
    return exposed == name


def _js_regex_end(text: str, start: int) -> int | None:
    """The end of the regular expression literal whose opening `/` is at
    `start`, flags included. None when it does not close on the line, or
    when the `/` begins a comment."""
    if text.startswith(("//", "/*"), start):
        return None
    in_class = False
    i, n = start + 1, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            i += 1
            while i < n and (text[i].isalnum() or text[i] in "_$"):
                i += 1
            return i
        i += 1
    return None


def _js_declarators(text: str, opened: str = "", fresh: bool = True) -> _DeclSplit:
    """The declarators of a `const` / `let` / `var` list that begin in
    `text`: the pieces between its top-level commas.

    `text` is the list's first line after the keyword, or a later line with
    the brackets the line above left open (`opened`, innermost last) and
    whether it begins a declarator (`fresh`) or finishes one, whose piece is
    then left out. Brackets, '...', "..." and `...` strings, a regular
    expression literal where an expression begins and a type-argument list
    (`Map<K, V>`: a `<` right after a name, closed by a `>` that is not the
    one of `=>`) are skipped. The list ends at a top-level `;`, at a bracket
    that closes one opened before it, and at a `<` where an expression
    begins: JSX, a type assertion or a generic arrow function's type
    parameters, which are not followed.

    Returns None when the list ends on this line, else the (brackets left
    open, `_DECL_NEXT` | `_DECL_OPEN` | `_DECL_MAYBE`) it goes on with, and
    the pieces.
    """
    pieces: list[str] = []
    buf: list[str] = []
    stack = list(opened)
    keep = fresh  # the current piece begins a declarator
    last = "," if fresh else "="  # the last character outside a string
    quote: str | None = None
    escaped = False
    ended = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        i += 1
        if quote is not None:
            buf.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        prev = text[i - 2] if i > 1 else ""
        if ch in "/<" and last in _JS_EXPRESSION_START and prev + ch != "<<":
            end = _js_regex_end(text, i - 1) if ch == "/" else None
            if end is None:
                ended = True
                break
            buf.append(text[i - 1 : end])
            i = end
            last = "a"  # the literal is a value, as a name is
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == "<" and (prev.isalnum() or prev in ("_", "$")) and (
            text[i : i + 1] not in ("<", "=")
        ):
            stack.append(ch)  # `Map<K, V>`, where `a < b` compares
        elif ch == ">" and stack[-1:] == ["<"] and prev != "=":
            stack.pop()
            buf.append(ch)
            last = "a"  # the type is a value's, as a name is
            continue
        elif ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            while stack[-1:] == ["<"]:
                stack.pop()  # a `<` that compared, written without spaces
            if not stack:
                ended = True
                break
            stack.pop()
        elif ch == ";" and all(b == "<" for b in stack):
            ended = True
            break
        elif ch == "," and not stack:
            if keep:
                pieces.append("".join(buf))
            buf, keep, last = [], True, ch
            continue
        if not ch.isspace():
            last = ch
        buf.append(ch)
    if keep:
        pieces.append("".join(buf))
    if ended or quote is not None:
        return None, pieces
    if stack:
        return ("".join(stack), _DECL_OPEN), pieces
    if last == ",":
        return ("", _DECL_NEXT), pieces
    return ("", _DECL_OPEN if last in _JS_OPERAND_PENDING else _DECL_MAYBE), pieces


def _js_depth1_pieces(text: str, depth: int) -> tuple[int, list[str]]:
    """Split the text of a `module.exports = { ... }` object or an
    `export { ... }` list into its top-level pieces (the text between commas
    at depth 1).

    Returns the bracket depth after `text` (0 once the object closed) and
    the pieces. An opening bracket at depth 1 stays in its piece, so a
    method shorthand `name(` and a key `name: {` keep their marker. Brackets
    and commas inside a string on the line are not counted.
    """
    pieces: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    for ch in text:
        if quote is not None:
            # text inside a string: kept in its piece, never counted
            if depth == 1:
                buf.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
            if depth == 1:
                buf.append(ch)
        elif ch in "([{":
            if depth == 1:
                buf.append(ch)
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1:
            if ch == ",":
                pieces.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
    pieces.append("".join(buf))
    return depth, pieces


def _js_paren_tail_is_call(after_open: str) -> bool:
    """For `name(` on an indented line: True when the text after the
    parameters says a call, not a method (`name(x);`). A method's
    parameters are followed by its body `{` or a return type `:`, or they
    continue on the next line."""
    depth = 1
    for i, ch in enumerate(after_open):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                rest = after_open[i + 1 :].strip()
                return not (rest == "" or rest[0] in "{:")
    return False


def _js_pattern_bindings(
    text: str, start: int
) -> tuple[list[tuple[str, int]], int | None]:
    """The names the destructuring pattern whose `{` or `[` is at
    `text[start]` binds, each with its offset in `text`, and the offset
    just past the pattern's closing bracket.

    An object pattern's property is `...target`, a shorthand key or
    `key: target` (a key is a name, a string, a number or a computed
    `[...]`, and only a shorthand key binds itself); an array pattern's
    element is `...target`, a target or a hole; a target is a name or a
    nested pattern. A `= default` is skipped to the next comma at the
    pattern's depth, and so is a property or element of any other shape,
    which binds nothing. '...', "..." and `...` strings are skipped
    whole, so no bracket or comma inside one counts. Whitespace, newlines
    included, may sit anywhere between the parts.

    Returns ([], None) when `text[start]` opens no pattern, the pattern
    does not close in `text`, a string in it does not end, or a bracket in
    it closes one it did not open. A pure function of its arguments (no
    module state), so another script can carry a copy of it.
    """
    n = len(text)
    names: list[tuple[str, int]] = []

    def space(i: int) -> int:
        while i < n and text[i].isspace():
            i += 1
        return i

    def name_end(i: int) -> int:
        """The end of the identifier at `i`, `i` itself when none starts there."""
        if i < n and (text[i].isalpha() or text[i] in "_$"):
            i += 1
            while i < n and (text[i].isalnum() or text[i] in "_$"):
                i += 1
        return i

    def string_end(i: int) -> int | None:
        """The offset past the string whose quote is at `i`."""
        quote = text[i]
        i += 1
        while i < n:
            if text[i] == "\\":
                i += 2
            elif text[i] == quote:
                return i + 1
            else:
                i += 1
        return None

    def skip(i: int, to_comma: bool = True) -> int | None:
        """From `i`, the offset of the next comma (unless not `to_comma`)
        or closing bracket at depth 0; with `to_comma` False, `text[i]`
        opens a bracket and the offset past the one closing it."""
        depth = 0
        while i < n:
            ch = text[i]
            if ch in "'\"`":
                end = string_end(i)
                if end is None:
                    return None
                i = end
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    return i
                depth -= 1
                if depth == 0 and not to_comma:
                    return i + 1
            elif ch == "," and depth == 0 and to_comma:
                return i
            i += 1
        return None

    def default(i: int) -> int | None:
        """After a target: past its `= default`, when it has one."""
        i = space(i)
        if i < n and text[i] == "=" and text[i + 1 : i + 2] not in ("=", ">"):
            return skip(i + 1)
        return i

    def bind(i: int, end: int, close: str) -> int | None:
        """The name `text[i:end]` is bound when its property or element
        ends after it or takes a default (any other text: another shape)."""
        after = space(end)
        if after < n and (
            text[after] in (",", close)
            or text[after] == "=" and text[after + 1 : after + 2] not in ("=", ">")
        ):
            names.append((text[i:end], i))
            return default(after)
        return after

    def target(i: int, close: str) -> int | None:
        if i < n and text[i] in "{[":
            end = pattern(i)
            return None if end is None else default(end)
        end = name_end(i)
        return i if end == i else bind(i, end, close)

    def element(i: int, close: str) -> int | None:
        """One property or element at `i`: the offset after it."""
        if text.startswith("...", i):
            return target(space(i + 3), close)
        if close == "]":
            return target(i, close)
        if text[i] in "'\"":
            end = string_end(i)
        elif text[i] == "[":
            end = skip(i, to_comma=False)  # a computed key
        else:
            end = name_end(i)
            if end > i:
                after = space(end)
                if after < n and text[after] == ":":
                    return target(space(after + 1), close)
                return bind(i, end, close)  # a shorthand key
            while end < n and (text[end].isalnum() or text[end] in "._"):
                end += 1  # a number key
        if end is None:
            return None
        after = space(end)
        if end > i and after < n and text[after] == ":":
            return target(space(after + 1), close)
        return after

    def pattern(i: int) -> int | None:
        """The pattern opening at `i`: the offset past its closing bracket."""
        close = "}" if text[i] == "{" else "]"
        i += 1
        while True:
            i = space(i)
            if i >= n:
                return None
            if text[i] == close:
                return i + 1
            if text[i] in ")]}":
                return None
            if text[i] == ",":
                i += 1  # a hole, or a stray comma
                continue
            end = element(i, close)
            if end is None:
                return None
            end = space(end)
            if end < n and text[end] not in (",", close):
                end = skip(end)  # any other shape binds nothing
                if end is None:
                    return None
            i = end + 1 if end < n and text[end] == "," else end

    if not (0 <= start < n and text[start] in "{["):
        return [], None
    end = pattern(start)
    return (names, end) if end is not None else ([], None)


def _js_initializer_start(text: str, end: int) -> int | None:
    """The offset just past the `=` that begins the initializer of a
    declarator whose name or pattern ends at `end`, a type annotation
    (`: T`, brackets, strings and `=>` in it included) skipped. None when
    neither `=` nor `:` follows, or when a `,` or `;` outside the
    annotation's brackets, or the end of `text`, comes first."""
    n = len(text)
    i = end
    while i < n and text[i].isspace():
        i += 1
    if i < n and text[i] == "=":
        return None if text[i + 1 : i + 2] == "=" else i + 1
    if not (i < n and text[i] == ":"):
        return None
    i += 1
    depth = 0
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            i += 1
            while i < n and text[i] != ch:
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("=>", i):
            i += 1
        elif ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
            if depth < 0:
                return None
        elif ch in ",;" and depth == 0:
            return None
        elif ch == "=" and depth == 0:
            return None if text[i + 1 : i + 2] == "=" else i + 1
        i += 1
    return None


def _js_destructured(code_lines: list[str]) -> dict[int, _PatternDecl]:
    """For each line that opens a `const` / `let` / `var` statement whose
    first declarator is a destructuring pattern (`_JS_VAR_DECL_RE`, the
    rest starting with `{` or `[`): the names the pattern binds, each with
    the line it appears on, and where its initializer starts.

    The patterns are read from the comment-free lines joined with `\\n`
    (`_js_pattern_bindings`), so a pattern may span lines and a name's
    offset maps back to its line. A pattern that does not close, or that
    nests deeper than the interpreter's recursion limit, binds nothing and
    gives no item.
    """
    starts: list[tuple[int, int]] = []
    for number, code in enumerate(code_lines, start=1):
        if "{" not in code and "[" not in code:
            continue
        m = _JS_VAR_DECL_RE.match(code)
        if m is not None and m.group(1)[:1] in ("{", "["):
            starts.append((number, m.start(1)))
    if not starts:
        return {}
    text = "\n".join(code_lines)
    offsets: list[int] = []
    pos = 0
    for code in code_lines:
        offsets.append(pos)
        pos += len(code) + 1

    def line_of(offset: int) -> int:
        return bisect.bisect_right(offsets, offset)

    out: dict[int, _PatternDecl] = {}
    for number, column in starts:
        try:
            names, end = _js_pattern_bindings(text, offsets[number - 1] + column)
        except RecursionError:
            continue  # patterns nested past the interpreter's limit: none bound
        if end is None:
            continue
        value = _js_initializer_start(text, end)
        at = None
        if value is not None:
            line = line_of(value)
            at = (line, code_lines[line - 1][value - offsets[line - 1] :])
        out[number] = ([(name, line_of(offset)) for name, offset in names], at)
    return out


def _tsjs_definition_lines(
    lines: list[str],
    code_lines: list[str],
    name: str,
    dotted: bool,
    declarators: Callable[..., _DeclSplit] = _js_declarators,
    declarations_only: bool = False,
    quiet: list[bool] | None = None,
    destructured: dict[int, _PatternDecl] | None = None,
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    `quiet` is `_js_quiet_lines(code_lines)` when the caller has it (it does
    not depend on the name): a quiet line without the name is passed over
    while no statement is open. `code_lines` are `lines` with comments removed (`_js_code_lines`), so a
    JSDoc line or a commented-out declaration never matches. A line inside
    a multi-line `export { ... }` list or `module.exports = { ... }` object
    takes the column of the line the statement starts on, and so do the
    name line of a declaration whose keyword ends the line above it, a
    later declarator on a line of its own and the line of a name that a
    destructuring pattern binds. `destructured` is
    `_js_destructured(code_lines)` when the caller has it (it does not
    depend on the name either): a name its pattern binds counts when the
    `const` / `let` / `var` line it is keyed by opens a statement here.
    Class members count only for a
    dotted export name. For the undotted name `default`, the name SKF's
    extraction gives a module's default export, a column-0 `export default`
    line counts whatever follows it, with `declarations_only` too, and
    whatever block holds it; an indented one (as in a formatted
    `declare module` block) does not. `declarators` splits
    a declarator list (`_js_declarators`, or `_SourceCache.js_declarators`, which splits each
    line once for every export looked up). With `declarations_only`,
    `export import NAME =`, `export default NAME`, an export-list item
    without an `as` that renames, a `module.exports` shorthand key and an
    import-valued binding (a declarator, a destructured name, `exports.NAME =`
    or a `module.exports` key whose value starts with `require(` or an
    `(await) import(`, on its line or the next one) never count, nor does
    a class member.
    """
    esc = re.escape(name)
    end = r"(?![\w$])"
    statements = [
        re.compile(rf"^\s*{_JS_MODIFIERS}{_JS_KINDS}{esc}{end}"),
        re.compile(
            rf"^\s*export\s+(?:type\s+)?\*\s+as\s+"
            rf"(?:{esc}\s+|([\"']){esc}\1\s*)from{end}"
        ),
        re.compile(rf"^\s*(?:module\.)?exports\.{esc}\s*=(?![=>])"),
    ]
    if not declarations_only:
        statements += [
            re.compile(rf"^\s*export\s+import\s+(?:type\s+)?{esc}\s*=(?![=>])"),
            re.compile(rf"^\s*export\s+default\s+{esc}\s*;?\s*$"),
        ]
    if name == "default" and not dotted:
        # the export named `default`: a column-0 `export default` line,
        # whatever follows it (a name, a declaration, an expression, or
        # nothing, the value on the next line), decorators before it
        statements.append(re.compile(rf"^(?:{_JS_DECORATOR}\s*)*export\s+default{end}"))
    # One declarator of a `const` / `let` / `var` list: `NAME = v`,
    # `NAME: T = v`, `NAME!: T`, or a bare `NAME`. A destructuring pattern
    # starts with `{` or `[` and never matches: the names a pattern that
    # begins the list binds come from `destructured` (`_js_pattern_bindings`).
    declarator = re.compile(rf"^\s*{esc}{end}\s*(?:!?\s*:|=|$)")
    # With declarations_only, the value bound to NAME (the rest of a
    # declarator, of `exports.NAME =` or of a `module.exports` key), to
    # test for an import.
    # (A type annotation holds no `=` but in `=>`: `NAME: () => T = v`.)
    declarator_value = re.compile(
        rf"^\s*{esc}{end}\s*(?:!?\s*:(?:[^=]|=>)*)?=(?![=>])(.*)$"
    )
    var_statement = re.compile(rf"^\s*{_JS_MODIFIERS}(?:const|let|var)\s+(.*)$")
    exports_value = re.compile(rf"^\s*(?:module\.)?exports\.{esc}\s*=(?![=>])(.*)$")
    key_value = re.compile(rf"^\s*(?:(['\"]){esc}\1|{esc}{end})\s*:(.*)$")

    def imported(value: str, number: int) -> bool:
        """True when a bound value is an import: `require(...)`, or an
        `import(...)` awaited or not, alone or in one helper call. A value
        that goes on on the next line (`NAME =`, `NAME = (` or
        `NAME = helper(` ends line `number`) is read there too."""
        if _JS_IMPORT_VALUE_OPEN_RE.match(value):
            value += next((c for c in code_lines[number:] if c.strip()), "")
        return _JS_IMPORT_VALUE_RE.match(value) is not None

    def declares(piece: str, number: int) -> bool:
        if declarator.match(piece) is None:
            return False
        if not declarations_only:
            return True
        m = declarator_value.match(piece)
        return m is None or not imported(m.group(1), number)

    def is_statement(code: str, number: int) -> bool:
        if not any(p.match(code) for p in statements):
            return False
        if not declarations_only:
            return True
        m = var_statement.match(code)
        if m is not None:
            m = declarator_value.match(m.group(1))
        else:
            m = exports_value.match(code)
        return m is None or not imported(m.group(1), number)

    leading_name = re.compile(rf"^\s*{esc}{end}")
    # A key with a value, a method, or (unless declarations_only) a shorthand.
    key_end = r"[:(]" if declarations_only else r"[:(]|$"
    object_key = re.compile(
        rf"^\s*(?:(?:async|get|set)\s+|\*\s*)*(?:(['\"]){esc}\1|{esc}{end})"
        rf"\s*(?:{key_end})"
    )

    def binds_key(piece: str, number: int) -> bool:
        if object_key.match(piece) is None:
            return False
        if not declarations_only:
            return True
        m = key_value.match(piece)
        return m is None or not imported(m.group(2), number)

    dotted = dotted and not declarations_only
    member = re.compile(
        rf"^\s+(?P<mods>{_JS_MEMBER_MODIFIERS})(?:\*\s*)?{esc}{end}\s*[?!]?\s*"
        rf"(?:<[^>]*>\s*)?(?P<tail>[(:=;]|$)"
    )
    found: list[tuple[int, bool]] = []
    # A statement that continues on the next line:
    # ("list" or "object", column 0, bracket depth).
    cont: tuple[str, bool, int] | None = None
    # A declaration whose keyword ends the line: (keyword, column 0).
    split: tuple[str, bool] | None = None
    # The `const` / `let` / `var` lists that go on on the next line, one
    # nested in another's initializer included: (column 0, brackets left
    # open, how, as `_js_declarators` gives them).
    decls: list[tuple[bool, str, str]] = []
    if quiet is None:
        quiet = _js_quiet_lines(code_lines)
    if destructured is None:
        destructured = _js_destructured(code_lines)

    def pattern_binds(number: int) -> list[int]:
        """The lines on which the pattern that begins the `const` / `let` /
        `var` list of line `number` binds `name` (none with
        `declarations_only` when its value is an import)."""
        decl = destructured.get(number)
        if decl is None:
            return []
        bound, value = decl
        at = [line for bound_name, line in bound if bound_name == name]
        if at and declarations_only and value is not None and imported(value[1], value[0]):
            return []
        return at

    for number, (text, code) in enumerate(zip(lines, code_lines), start=1):
        if quiet[number - 1] and not (decls or split or cont) and name not in code:
            continue  # no rule below can match it: spares a scan per name
        # A line of a list carried from above still goes through the rules
        # below: it may hold a class member or a local of an arrow function.
        if decls and code.strip():
            going_on = code.lstrip()[0] in _JS_CONTINUATION_START
            carried = []
            for decl_top, opened, how in decls:
                if how == _DECL_MAYBE and not going_on:
                    continue  # the statement ended with the line above
                carry, pieces = declarators(code, opened, how == _DECL_NEXT)
                if carry is not None:
                    carried.append((decl_top, *carry))
                if any(declares(p, number) for p in pieces):
                    # a later declarator on a line of its own, as Prettier
                    # writes it: `export const a = 1,` then `  NAME = 2;`
                    found.append((number, decl_top))
            decls = carried
        if split is not None:
            keyword, top = split
            split = None
            if keyword in _JS_VAR_KEYWORDS:
                carry, pieces = declarators(code)
                if carry is not None:
                    decls.append((top, *carry))
                hit = any(declares(p, number) for p in pieces)
            else:
                hit = leading_name.match(code) is not None
            if hit:
                # the name's line, as the recipes cite it
                found.append((number, top))
                continue
        if cont is not None:
            kind, top, depth = cont
            depth, pieces = _js_depth1_pieces(code, depth)
            cont = (kind, top, depth) if depth > 0 else None
            if kind == "list":
                hit = any(
                    _js_export_item_binds(p, name, declarations_only) for p in pieces
                )
            else:
                hit = any(binds_key(p, number) for p in pieces)
            if hit:
                found.append((number, top))
            continue
        top = _is_column_0(text)
        # every rule that matches a line needs the name in it, but for a
        # destructuring pattern, whose names may sit on the lines below
        named = name in code
        if named and is_statement(code, number):
            found.append((number, top))
            continue
        m = _JS_VAR_DECL_RE.match(code)
        if m:
            carry, pieces = declarators(m.group(1))
            if carry is not None:
                decls.append((top, *carry))
            # `export const { a, b: NAME } = obj;`, on one line or several:
            # each name's line, at the statement's column
            found.extend((line, top) for line in pattern_binds(number))
            if named and any(declares(p, number) for p in pieces):
                # a later declarator: `export const a = 1, NAME = 2;`
                found.append((number, top))
                continue
        m = _JS_SPLIT_DECL_RE.match(code)
        if m:
            split = (m.group("kind"), top)
            continue
        m = _JS_EXPORT_LIST_RE.match(code)
        if m:
            depth, pieces = _js_depth1_pieces(m.group(1), 1)
            if depth > 0:
                cont = ("list", top, depth)
            if any(_js_export_item_binds(p, name, declarations_only) for p in pieces):
                found.append((number, top))
            continue
        m = _JS_MODULE_EXPORTS_OBJECT_RE.match(code)
        if m:
            depth, pieces = _js_depth1_pieces(m.group(1), 1)
            if depth > 0:
                cont = ("object", top, depth)
            if any(binds_key(p, number) for p in pieces):
                found.append((number, top))
            continue
        if not dotted:
            continue
        m = member.match(code)
        if not m:
            continue
        tail = m.group("tail")
        if tail == "(":
            if not m.group("mods") and _js_paren_tail_is_call(code[m.end():]):
                continue
        elif code.endswith(","):
            continue  # an object-literal entry or a destructuring default
        elif tail == "=" and code[m.end() : m.end() + 1] in ("=", ">"):
            continue
        found.append((number, top))
    return found


def _prefer_module_level(found: list[tuple[int, bool]], dotted: bool) -> list[int]:
    """The definition lines to report. For an undotted name, a column-0
    match drops the indented ones, so a local shadow never outranks the
    module-level definition; a dotted name keeps every match."""
    if not dotted:
        top = [n for n, at_column_0 in found if at_column_0]
        if top:
            return sorted(set(top))
    return sorted({n for n, _ in found})


def line_rule_applies(source_file: str, export_type: object) -> bool:
    """True when the definition-line rules cover this entry: a Python or
    TS/JS file, and an export that is not a whole module or package."""
    if isinstance(export_type, str) and (
        export_type.strip().lower() in NO_DEFINITION_EXPORT_TYPES
    ):
        return False
    suffix = Path(source_file.strip().replace("\\", "/")).suffix.lower()
    return suffix in PYTHON_EXTENSIONS or suffix in TSJS_EXTENSIONS


def _definition_matches(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache | None = None,
    declarations_only: bool = False,
) -> tuple[list[int], set[int]] | None:
    """(definition lines to report, every matching line) for an export.

    The first item applies the column-0 rule; the second keeps the indented
    matches that rule dropped. None when the file's extension has no
    definition rule or the file cannot be read.

    `declarations_only` (classify-stale's `defined_at` lookup) keeps the
    lines that declare the name at column 0, both items alike: no plain
    import, star import or re-export (`_python_definition_lines` and
    `_tsjs_definition_lines` say which), and nothing in a Python file that
    does not tokenize.
    """
    rel = source_file.strip().replace("\\", "/")
    suffix = Path(rel).suffix.lower()
    if suffix not in PYTHON_EXTENSIONS and suffix not in TSJS_EXTENSIONS:
        return None
    cache = cache if cache is not None else _SourceCache()
    path = (source_root / rel).resolve()
    lines = cache.lines(path)
    if lines is None:
        return None
    return _line_matches(suffix, path, lines, export_name, cache, declarations_only)


def _folded_matches(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache | None = None,
) -> tuple[tuple[list[int], set[int]] | None, str | None]:
    """(`_definition_matches` of the name the line check judges, the base
    name a bookkeeping variant was folded to, else None).

    The raw name comes first. Only when the file never names it (no whole
    identifier in its text, so no shape the rules miss can define it) and
    `fold_base` gives a base that some line matches are the base's matches
    returned, with the base; otherwise the raw name's, with None. So a real
    export named like a variant (`parse_exact` defined as itself, or bound
    in a shape the rules do not cover) is judged as written, and
    classify-stale, which never folds, does not call this.
    """
    cache = cache if cache is not None else _SourceCache()
    matches = _definition_matches(source_file, export_name, source_root, cache)
    if matches is None or matches[1]:
        return matches, None
    base = fold_base(export_name)
    if base is None:
        return matches, None
    # the variant's own identifiers: `mockChannel_def`, or `a11y_App` of `a11y_App.update`
    own = sorted(set(export_name.split(".")) - set(base.split(".")))
    named = re.compile(r"(?<![\w$])(?:" + "|".join(map(re.escape, own)) + r")(?![\w$])")
    lines = cache.lines((source_root / source_file.strip().replace("\\", "/")).resolve())
    if not own or lines is None or any(named.search(text) for text in lines):
        return matches, None
    folded = _definition_matches(source_file, base, source_root, cache)
    if folded is None or not folded[1]:
        return matches, None
    return folded, base


def _line_matches(
    suffix: str,
    path: Path,
    lines: list[str],
    export_name: str,
    cache: _SourceCache,
    declarations_only: bool = False,
) -> tuple[list[int], set[int]]:
    """`_definition_matches` over the lines of a Python or TS/JS file already
    read: `suffix`, the cited file's extension, picks the rules, and `path`
    keys `cache`."""
    name = definition_name(export_name)
    if not name:
        return [], set()
    dotted = "." in export_name
    if suffix in PYTHON_EXTENSIONS:
        starts = cache.py_statement_starts(path, lines)
        if declarations_only and starts is None:
            # every line would be a candidate, a docstring line included
            return [], set()
        found = _python_definition_lines(lines, name, starts, declarations_only)
    else:
        code_lines = cache.js_code_lines(path, lines)
        found = _tsjs_definition_lines(
            lines, code_lines, name, dotted, cache.js_declarators, declarations_only,
            cache.js_quiet_lines(path, code_lines), cache.js_destructured(path, code_lines),
        )
    if declarations_only:
        top = {n for n, at_column_0 in found if at_column_0}
        return sorted(top), top
    return _prefer_module_level(found, dotted), {n for n, _ in found}


def find_definition_lines(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache | None = None,
) -> list[int] | None:
    """Every line of `source_file` that defines `export_name`, in order,
    after the column-0 rule.

    Returns None when the file's extension has no definition rule or the
    file cannot be read.
    """
    matches = _definition_matches(source_file, export_name, source_root, cache)
    return None if matches is None else matches[0]


def _missed_definition_lines(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache,
    line: int,
    defs: list[int],
    every: set[int],
) -> list[int]:
    """The `definition_lines` a finding lists for a recorded `line` that is
    not one of `defs` (`_definition_matches` over the same `cache`).

    A recorded line that is an indented match the column-0 rule dropped
    joins them, so the finding carries several lines and nobody moves it.
    Otherwise a Python file's `@overload` group gives its first line alone
    (`_python_overload_start`), the line to move the entry to, and any
    other answer gives `defs` as they are.
    """
    if line in every:
        return sorted(set(defs) | {line})
    rel = source_file.strip().replace("\\", "/")
    if Path(rel).suffix.lower() not in PYTHON_EXTENSIONS or len(defs) < 2:
        return defs
    path = (source_root / rel).resolve()
    lines = cache.lines(path)
    if lines is None:
        return defs
    first = _python_overload_start(
        lines, definition_name(export_name), defs, cache.py_statement_starts(path, lines)
    )
    return defs if first is None else [first]


def definition_lines_report(
    source_file: str,
    export_name: str,
    source_root: Path,
    line: int | None = None,
    export_type: str | None = None,
    fold: bool = True,
) -> dict:
    """What `verify` would say about one entry's line (the definition-lines
    subcommand). Raises ValueError when the file exists but cannot be read.

    `line_check` is `file-missing`, `skipped-export-type` (a `module` or
    `package`, no definition line), `skipped-language` (no rule for the
    extension) or `checked`. With `line`, a recorded line that is not a
    definition line gets the lines `verify` would list
    (`_missed_definition_lines`): an indented match the column-0 rule
    dropped joins `definition_lines`, so the answer carries several lines,
    and a Python `@overload` group gives its first line alone.

    With `fold` (the default, as `verify` checks), a bookkeeping variant the
    file never names is checked against its base name (`_folded_matches`),
    and the report gains `folded_to`, the base, only when it folded.
    classify-stale passes `fold=False`: the fabricated-signature test judges
    the documented name as written.
    """
    report: dict = {
        "source_file": source_file,
        "export_name": export_name,
        "line_check": "checked",
        "definition_lines": None,
        "source_line": line,
        "line_is_definition": None,
    }
    rel = source_file.strip().replace("\\", "/")
    if not rel or not (source_root / rel).is_file():
        report["line_check"] = "file-missing"
        return report
    if not line_rule_applies(source_file, export_type):
        suffix = Path(rel).suffix.lower()
        covered = suffix in PYTHON_EXTENSIONS or suffix in TSJS_EXTENSIONS
        report["line_check"] = "skipped-export-type" if covered else "skipped-language"
        return report
    cache = _SourceCache()
    if fold:
        matches, folded_to = _folded_matches(source_file, export_name, source_root, cache)
    else:
        matches, folded_to = _definition_matches(source_file, export_name, source_root, cache), None
    if matches is None:
        raise ValueError(f"failed to read source file {source_root / rel}")
    if folded_to is not None:
        report["folded_to"] = folded_to
    judged = folded_to or export_name
    defs, every = matches
    if line is not None:
        report["line_is_definition"] = line in defs
        if line not in defs:
            defs = _missed_definition_lines(
                source_file, judged, source_root, cache, line, defs, every
            )
    report["definition_lines"] = defs
    return report


# --------------------------------------------------------------------------
# Stale names (classify-stale)
# --------------------------------------------------------------------------

STALE_NOT_DEFINED = "not-defined"
STALE_DEFINED = "defined"
STALE_UNCHECKED = "unchecked"
STALE_NO_ENTRY = "no-entry"
# a not-defined name a declaration renames to it from a name a cited file declares
STALE_ALIASED = "aliased"


def stale_names(data: object) -> list[str]:
    """The names `--names` holds: reconcile-coverage.py's `stale`, or a JSON
    array of names, each once in the order given. Raises ValueError."""
    names = data.get("stale") if isinstance(data, dict) else data
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError(
            "--names must hold a `stale` list of names or a JSON array of names"
        )
    return list(dict.fromkeys(n for n in names if n))


def _entry_file(entry: dict) -> str | None:
    """The entry's `source_file`, None when it records none."""
    source_file = entry.get("source_file")
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    return source_file


def _entry_citation(entry: dict) -> str | None:
    source_file = _entry_file(entry)
    if source_file is None:
        return None
    line = _coerce_line(entry.get("source_line"))
    return f"{source_file}:{line}" if isinstance(line, int) else source_file


def _stale_line_check(
    entry: dict, name: str, source_root: Path
) -> tuple[str, list[int] | None]:
    """(line_check, definition_lines) of one provenance entry of a stale name.

    The documented name is judged as written, with no bookkeeping-variant
    fold: a variant the cited file never defines stays fabricated."""
    source_file = _entry_file(entry)
    if source_file is None:
        # no file to check: it neither proves the name fabricated nor clears it
        return "no-file", None
    line = _coerce_line(entry.get("source_line"))
    export_type = entry.get("export_type")
    try:
        report = definition_lines_report(
            source_file,
            name,
            source_root,
            line if isinstance(line, int) else None,
            export_type if isinstance(export_type, str) else None,
            fold=False,
        )
    except ValueError:
        # the file exists but cannot be read: nothing proves it
        return "unreadable", None
    return report["line_check"], report["definition_lines"]


# A TS/JS `export * from` or `export type * from` statement, comments removed
# and stripped, the module it names in group 2 (#1070).
_JS_STAR_LINE_RE = re.compile(
    r"""export\s*(?:type\s*)?\*\s*from\s*(['"])([^'"]+)\1\s*;?"""
)


def _star_line(entry: dict, source_root: Path) -> str | None:
    """The module the `export *` or `export type *` statement at an entry's
    cited TS/JS line names, else None (#1070): the line as written at
    column 0, and the whole statement on that line once its comments are
    removed. Read for a `checked` entry with no definition line, whose file
    `definition_lines_report` resolved the same way."""
    source_file = _entry_file(entry)
    line = _coerce_line(entry.get("source_line"))
    if source_file is None or not isinstance(line, int):
        return None
    rel = source_file.strip().replace("\\", "/")
    if Path(rel).suffix.lower() not in TSJS_EXTENSIONS:
        return None
    lines = _read_lines(source_root / rel)
    if lines is None or not 1 <= line <= len(lines):
        return None
    if not _is_column_0(lines[line - 1]):
        return None
    code = _js_code_lines(lines)[line - 1].strip()
    match = _JS_STAR_LINE_RE.fullmatch(code)
    return match.group(2) if match else None


# The folders and files the `defined_at` walk leaves out, judged
# case-insensitively on the path below its walk root: generated, built and
# installed output, a vendored copy of another package, and tests and their
# configuration. The folders are the walk's alone: a file the map cites
# is read in any of them, a test file, its configuration or a minified
# bundle never.
# Keep identical to EXCLUDED_DIR_NAMES in skf-resolve-authoritative-files.py.
EXCLUDED_DIR_NAMES = {
    "node_modules", "__pycache__", "dist", "build", ".webpack",
    "target", ".next", ".nuxt", "out", "coverage", ".git",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".vscode",
}
# Keep identical to _VENDORED_SEGMENTS in skf-detect-language.py.
_VENDORED_SEGMENTS = frozenset(
    {"vendor", "vendored", "third_party", "third-party", "thirdparty"}
)
# Keep identical to TEST_FOLDERS in skf-disqualify-candidates.py.
TEST_FOLDERS = frozenset({"test", "tests", "__tests__", "spec", "specs"})
# Keep identical to TEST_CONFIG_NAMES in skf-disqualify-candidates.py.
TEST_CONFIG_NAMES = frozenset({
    "conftest.py", "pytest.ini", "phpunit.xml", "phpunit.xml.dist", ".rspec",
})
# Keep identical to TEST_CONFIG_PREFIXES in skf-disqualify-candidates.py.
TEST_CONFIG_PREFIXES = (
    "jest.config.", "vitest.config.", "karma.conf.", "playwright.config.",
    "cypress.config.",
)
# Keep identical to TEST_FILE_RE in skf-disqualify-candidates.py.
TEST_FILE_RE = re.compile(
    r"(\.(test|spec)\.[^./]+$)|(_test\.[^./]+$)|(^test_.+\.py$)|(_spec\.rb$)"
)
# Keep identical to PY_NON_CORE_TOPS in skf-extract-public-api.py.
PY_NON_CORE_TOPS = frozenset({"docs", "examples", "benchmarks"})
# The walk's own additions: pip's and setuptools' `_vendor`, test helpers
# (`testing`, `fixtures`, `__mocks__`), installed packages (`site-packages`,
# a virtualenv named `env`, `bower_components`) and the ESM, CommonJS and
# UMD builds a JS package commits.
LOOKUP_EXTRA_FOLDERS = frozenset({
    "_vendor", "testing", "fixtures", "__mocks__", "site-packages", "env",
    "bower_components", "esm", "cjs", "umd",
})
LOOKUP_SKIPPED_FOLDERS = frozenset(
    EXCLUDED_DIR_NAMES | _VENDORED_SEGMENTS | TEST_FOLDERS | LOOKUP_EXTRA_FOLDERS
)
# The test folders the walk alone skips wherever they lie (end-to-end tests,
# Jest's `__fixtures__` beside the code): a file the map cites in one is
# still read.
LOOKUP_WALK_FOLDERS = frozenset({"e2e", "__fixtures__"})
# The folders the walk alone skips as the first folder below its walk root
# or below a package root it passes through (`_package_root`'s roots):
# examples and demos, samples, scripts, playgrounds, benchmarks, migrations
# and docs (`PY_NON_CORE_TOPS`, which skf-extract-public-api.py also leaves
# out only as a top folder), which hold code that uses, changes or documents
# the package rather than its API. Deeper in a package such a folder can be
# live package code (cognee's `cognee/modules/migrations/`, Storybook's
# `code/addons/docs/`), so it is walked there; one that holds a file the map
# cites is walked too, and that file is still read.
LOOKUP_TOP_FOLDERS = frozenset({
    "example", "demo", "demos", "sample", "samples", "scripts", "playground",
    "bench", "benchmark", "migrations",
}) | PY_NON_CORE_TOPS
# The kinds of a documented inventory (validate-inventory.py's `kind`) that a
# module cannot be: such a name takes no line 1 from a module so named. A
# `method` is left out: reconcile-coverage.py never lists a method as stale,
# and a module may share a method's name.
NO_MODULE_KINDS = frozenset({"function", "hook", "class", "interface", "enum", "type"})
# A TS/JS file that is itself the export: its module so named declares the
# name whatever its kind.
_SELF_EXPORT_RE = re.compile(r"^(?:export\s+default\b|module\.exports\s*=(?!=))", re.M)
# A minified bundle: built output, whatever folder holds it.
LOOKUP_SKIPPED_SUFFIXES = (".min.js",)
# The errors a lookup gives up on: every `defined_at` is then null.
_LOOKUP_ERRORS = (OSError, ValueError, RuntimeError)


def _rule_family(path: str) -> str | None:
    """The definition rules a file's extension picks: `python`, `tsjs` or
    None."""
    suffix = posixpath.splitext(path)[1].lower()
    if suffix in PYTHON_EXTENSIONS:
        return "python"
    return "tsjs" if suffix in TSJS_EXTENSIONS else None


def _lookup_skips_folder(segment: str) -> bool:
    """True when the `defined_at` walk never goes into this folder."""
    segment = segment.lower()
    return segment.startswith(".") or segment in LOOKUP_SKIPPED_FOLDERS


def _lookup_skips_file(filename: str) -> bool:
    """True when the `defined_at` lookup never reads this file: a test file,
    as skf-disqualify-candidates.py's `_is_test_file` judges its name (a
    test configuration file included), or a minified bundle."""
    name = filename.lower()
    return (
        name in TEST_CONFIG_NAMES
        or name.startswith(TEST_CONFIG_PREFIXES)
        or TEST_FILE_RE.search(name) is not None
        or name.endswith(LOOKUP_SKIPPED_SUFFIXES)
    )


def _walk_skips_folder(segment: str, top: bool) -> bool:
    """True when the `defined_at` walk never goes into this folder: one
    `_lookup_skips_folder` names, a `LOOKUP_WALK_FOLDERS` one and, when
    `top` (right below the walk root or a package root, holding no cited
    file), a `LOOKUP_TOP_FOLDERS` one."""
    lower = segment.lower()
    return (
        _lookup_skips_folder(segment)
        or lower in LOOKUP_WALK_FOLDERS
        or (top and lower in LOOKUP_TOP_FOLDERS)
    )


def _symlinked(root: Path, parts: tuple[str, ...]) -> bool:
    """True when a path below `root` goes through a symlink, itself
    included."""
    return any(root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1))


def _readable_below(root: Path, parts: tuple[str, ...], real_root: Path | None = None) -> bool:
    """True when the `defined_at` lookup may read the file at `parts` below
    `root`: not a file it skips (`_lookup_skips_file`), no symlink on its
    path, and its real path a file inside the root (`real_root`, the root
    resolved)."""
    if _lookup_skips_file(parts[-1]) or _symlinked(root, parts):
        return False
    real = root.joinpath(*parts).resolve()
    return real.is_relative_to(real_root or root.resolve()) and real.is_file()


def _cited_parts(source_file: str) -> tuple[str, ...] | None:
    """A recorded `source_file` as path segments below the source root, None
    when it is absolute or climbs out of the root."""
    path = normalize_path(source_file)
    if not path or path == "." or posixpath.isabs(path):
        return None
    parts = tuple(path.split("/"))
    return None if parts[0] == ".." or ":" in parts[0] else parts


def _lookup_families(recorded: list[str]) -> set[str]:
    """The rule families the lookup reads: those of the files the entries
    cite (`recorded`), both when they cite none."""
    families = {_rule_family(f) for f in recorded}
    return families - {None} if recorded else {"python", "tsjs"}


def _cited_folders(recorded: list[str]) -> set[tuple[str, ...]]:
    """The folders below the source root that hold a cited file, each as
    its segments: the walk goes into a `LOOKUP_TOP_FOLDERS` one."""
    return {
        parts[:i]
        for parts in filter(None, map(_cited_parts, recorded))
        for i in range(1, len(parts))
    }


def lookup_skips_declaration(
    name: str, path: str, entries: list[dict], roots: list[str]
) -> bool:
    """True when classify-stale's lookup (`_DeclarationLookup`) over the
    provenance `entries` never finds `name` declared in the file at `path`
    below the source root, judged from the path alone: a file of a rule
    family it does not read (`_lookup_families`) or one `_lookup_skips_file`
    names; else, unless an entry of the name cites it (a cited file is read
    in any folder), a file in a folder the walk never goes into
    (`_walk_skips_folder`), a folder right below the source root or one of
    `roots` (package roots, as `_package_root` finds them) being `top` when
    no cited file lies in it. It reads no file, so it judges no symlink and
    no walk root. load-coverage-inputs.py leaves such a declaration out of
    `internalDeclarations`."""
    parts = _cited_parts(path)
    if parts is None:
        return True
    recorded = [f for f in map(_entry_file, entries) if f is not None]
    if _rule_family(parts[-1]) not in _lookup_families(recorded):
        return True
    if _lookup_skips_file(parts[-1]):
        return True
    own = {
        _cited_parts(f)
        for f in map(_entry_file, (e for e in entries if e.get("export_name") == name))
        if f is not None
    }
    if parts in own:
        return False
    cited = _cited_folders(recorded)
    tops = {()} | set(filter(None, map(_cited_parts, roots)))
    return any(
        _walk_skips_folder(parts[i], parts[:i] in tops and parts[: i + 1] not in cited)
        for i in range(len(parts) - 1)
    )


# The file whose folder is a package, by rule family.
_PACKAGE_MARKERS = {"python": "__init__.py", "tsjs": "package.json"}
# Type stubs: a declaration file beside the module it types.
_STUB_SUFFIXES = {".pyi": "python", ".d.ts": "tsjs", ".d.mts": "tsjs", ".d.cts": "tsjs"}


def _stub_of(path: str) -> tuple[str, str] | None:
    """(the path without its suffix, family) of a type stub (`NAME.pyi`,
    `NAME.d.ts`), None for any other file."""
    lower = path.lower()
    for suffix, family in _STUB_SUFFIXES.items():
        if lower.endswith(suffix):
            return path[: -len(suffix)], family
    return None


def _without_stubs(hits: list[str]) -> list[str]:
    """`file:line` items less each stub whose implementation (`NAME.py`
    beside `NAME.pyi`, a TS/JS `NAME.<ext>` beside `NAME.d.ts`) is an item
    too: the two are one declaring file, the implementation."""
    files = [h.rsplit(":", 1)[0] for h in hits]
    implementations = {
        (posixpath.splitext(f)[0], _rule_family(f))
        for f in files
        if _stub_of(f) is None and _rule_family(f) is not None
    }
    return [h for h, f in zip(hits, files) if _stub_of(f) not in implementations]


def _module_name(parts: tuple[str, ...]) -> str | None:
    """The name a file is the module or package of, which it declares at
    its line 1: `NAME.py`, `NAME/__init__.py`, a TS/JS `NAME.<ext>` or
    `NAME/index.<ext>`. None for any other file, and for a package file
    with no folder above it below the source root."""
    stem, ext = posixpath.splitext(parts[-1])
    ext = ext.lower()
    if ext == ".py":
        package = "__init__"
    elif ext in TSJS_EXTENSIONS:
        package = "index"
    else:
        return None
    if stem != package:
        return stem
    return parts[-2] if len(parts) > 1 else None


def _exports_itself(parts: tuple[str, ...], text: str) -> bool:
    """True for a TS/JS file that is itself the export, with a column-0
    `export default` or `module.exports =`: its module so named declares
    the name whatever kind the inventory gives it."""
    return _rule_family(parts[-1]) == "tsjs" and _SELF_EXPORT_RE.search(text) is not None


def declared_line(
    source_file: str | tuple[str, ...],
    name: str,
    source_root: Path | None = None,
    *,
    lines: list[str] | None = None,
    cache: _SourceCache | None = None,
    module_fallback: bool = True,
) -> int | None:
    """The line at which one file declares `name`, by classify-stale's
    `defined_at` rule (see the module docstring): its first line at column
    0 that the definition-line rules match with imports left out (a `def`,
    `class`, assignment, annotation, type alias, TS/JS declaration, or an
    alias that renames, such as `from X import Y as NAME`; a plain or star
    import, an `as` that keeps the imported name, a re-export and an
    import-valued binding never count, except that for the name `default`
    a column-0 `export default` line counts whatever follows it, an import
    or an imported local included), else, with `module_fallback`, its
    line 1 when it is the module or package so named (`_module_name`).

    `source_file` is the file's path below the source root, as recorded
    (one that is absolute or climbs out of the root gives None) or as its
    segments. `lines` are its lines when the caller read them already;
    otherwise the file is read below `source_root` under the lookup's
    guards (`_readable_below`: no symlink on its path, its real path
    inside the root, not a file the lookup skips). Pass one `cache` for
    the names of one source root, and each file is read and parsed once.
    None when no line declares the name, the name is empty or dotted, the
    file is not a Python or TS/JS one, or it cannot be read.
    """
    parts = _cited_parts(source_file) if isinstance(source_file, str) else tuple(source_file)
    if not name or "." in name or not parts or _rule_family(parts[-1]) is None:
        return None
    cache = cache if cache is not None else _SourceCache()
    if lines is None:
        if source_root is None:
            raise ValueError("declared_line reads the file below source_root when no lines are given")
        if not _readable_below(source_root, parts):
            return None
        lines = cache.lines(source_root.joinpath(*parts))
        if lines is None:
            return None
    path = Path(*parts)
    top, _ = _line_matches(path.suffix.lower(), path, lines, name, cache, True)
    if top:
        return top[0]
    return 1 if module_fallback and _module_name(parts) == name else None


# declared_line's `cache`, public for a script that loads this one.
SourceCache = _SourceCache


def _baseline_path(path: str) -> str:
    """A cited path as an extraction writes it: forward slashes, no
    leading `./`."""
    rel = path.strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _declaration_refused(source_root: Path, file: str) -> bool:
    """True when `declared_line` would not read a file that is there: a
    path outside the source root, a file the lookup skips (a test file, a
    minified bundle) or one with a symlink on its path. A file that is gone
    is not refused: its entries are deleted."""
    parts = _cited_parts(file)
    if parts is None:
        return True
    path = source_root.joinpath(*parts)
    return os.path.lexists(path) and not _readable_below(source_root, parts)


def baseline_gaps(
    provenance: dict,
    source_root: Path,
    held: set[tuple[str, str]],
    files: set[str],
    listed: set[tuple] | frozenset = frozenset(),
    *,
    cache: _SourceCache | None = None,
) -> tuple[list[dict], list[dict]]:
    """The provenance entries an extraction left out whose cited file still
    declares them: the recipe runner never reports a module, an alias that
    renames, a dunder such as `__version__` or another Python or Rust
    underscore name, so a diff would read each as removed.

    `held` holds the (name, file) of every export the extraction found,
    `files` the files whose entries are checked (the ones read), and
    `listed` the (name, file) of the gaps already listed elsewhere (the
    runner's own extraction gaps), each path with forward slashes. An
    entry is left out when its name is dotted (a member) and it is no
    `module` or `package` entry, when its file is not in `files`, when the
    extraction holds the name or its re-export target (`reexport_map`,
    else the entry's `reexported_as`) at that file, or when it is listed
    already. Each name and file is taken once.

    Returns (gaps, unchecked). A gap is {"name", "file", "line", "entry":
    null}, plus the entry's `export_type` when it has one, at the line
    `declared_line` gives (only a `module` or `package` entry takes the
    module rule); an entry whose file declares it no more is no gap.
    `unchecked` holds {"name", "file", "export_type"} for each entry no
    rule can check, to read by eye: one whose file is neither Python nor
    TS/JS, one whose file the lookup will not read (outside the source
    root, a test file or a minified bundle, a symlink on its path), and a
    dotted `module` or `package` entry (`api.v1`). The entries are read
    file by file over one cache, so each file is read and parsed once."""
    checkable = PYTHON_EXTENSIONS | TSJS_EXTENSIONS
    renamed = extract_reexport_map(provenance)
    seen = set(listed)
    by_file: dict[str, list[tuple[str, object]]] = {}
    unchecked: list[dict] = []
    entries = provenance.get("entries")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name, cited = entry.get("export_name"), entry.get("source_file")
        if not isinstance(name, str) or not isinstance(cited, str):
            continue
        name, file, kind = name.strip(), _baseline_path(cited), entry.get("export_type")
        module = isinstance(kind, str) and kind.strip().lower() in NO_DEFINITION_EXPORT_TYPES
        if not name or ("." in name and not module) or (name, file) in seen:
            continue
        if cited.replace("\\", "/") not in files and file not in files:
            continue
        if (name, file) in held or (renamed.get(name), file) in held:
            continue
        seen.add((name, file))
        if "." in name or Path(file).suffix.lower() not in checkable or _declaration_refused(source_root, file):
            unchecked.append({"name": name, "file": file, "export_type": kind})
            continue
        by_file.setdefault(file, []).append((name, kind))
    cache = cache if cache is not None else _SourceCache()
    gaps = []
    for file, named in by_file.items():
        for name, kind in named:
            module = isinstance(kind, str) and kind.strip().lower() in NO_DEFINITION_EXPORT_TYPES
            line = declared_line(file, name, source_root, cache=cache, module_fallback=module)
            if line is None:
                continue
            gap = {"name": name, "file": file, "line": line, "entry": None}
            if kind is not None:
                gap["export_type"] = kind
            gaps.append(gap)
    return gaps, unchecked


# A one-line TS/JS string literal: an export list is split into items on a
# copy of its lines whose strings are blanked, quotes and length kept.
_JS_STRING_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`")
_JS_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
# The `from` clause after an export list's closing brace, and its module.
_JS_FROM_RE = re.compile(r"""^\s*from\s*(["'])([^"']*)\1""")
# An import statement (not `import(...)` nor `import.meta`); its clause
# and module (`import X, { a as b } from './m'`); `import X = ...`; a
# side-effect import (`import './m'`); an item of its brace list.
_JS_IMPORT_RE = re.compile(r"^\s*import(?![\w$])(?!\s*[(.])")
_JS_IMPORT_CLAUSE_RE = re.compile(
    r"""^\s*import\s+(?:type\s+(?!from(?![\w$])))?(.*?)\s*(?<![\w$])from\s*(["'])([^"']*)\2""",
    re.S,
)
_JS_IMPORT_EQUALS_RE = re.compile(r"^\s*import\s+(?:type\s+)?([\w$]+)\s*=(?!=)")
_JS_IMPORT_BARE_RE = re.compile(r"""^\s*import\s*["']""")
_JS_IMPORT_ITEM_RE = re.compile(rf"^(?:type\s+)?({_JS_NAME_OR_STRING})(?:\s+as\s+([\w$]+))?$")
_JS_IMPORT_DEFAULT_RE = re.compile(r"^([\w$]+)\s*(?:,|$)")
_JS_IMPORT_NAMESPACE_RE = re.compile(r"^\*\s*as\s+([\w$]+)")
# `const|let|var NAME = L` (or `NAME: <type> = L`, the type on the line,
# holding no `;`, no `=` but in `=>` and no `,` that opens another
# declarator) and `type NAME = L` (or `type NAME<P1, ...> = L<A1, ...>`,
# one trailing comma allowed in either list), exported or not:
# NAME (`var` or `type`), the type's parameters, L, its arguments, and the
# `;` when the line ends the statement (`end`). `renames` reads a generic
# one only when its arguments are its bare parameters in order
# (`_js_passes_parameters`).
_JS_NAME_IS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:(?:const|let|var)\s+(?P<var>[\w$]+)"
    r"(?:\s*:(?!=)\s*(?:[^=;,\s]|=>|,(?!\s*[\w$]+\s*=(?![=>])))(?:[^=;,]|=>|,(?!\s*[\w$]+\s*=(?![=>])))*?)?"
    r"|type\s+(?P<type>[\w$]+)(?:\s*<(?P<params>[^<>]*)>)?)"
    r"\s*(?<![=!])=(?![=>])\s*(?P<value>[A-Za-z_$][\w$]*)(?:\s*<(?P<args>[^<>]*)>)?\s*(?P<end>;?)$"
)
# `export default L`, `L` a bare identifier, and the `;` when the line ends
# the statement (`end`): for the name `default`, `renames` reads it as a
# rename of `L` when an import or a declaration of the same file binds `L`.
_JS_EXPORT_DEFAULT_IS_RE = re.compile(r"^\s*export\s+default\s+(?P<value>[A-Za-z_$][\w$]*)\s*(?P<end>;?)\s*$")
# A line that begins with one of these goes on with the value above it (a
# member, an operator, a call, an index or a tagged template).
_JS_VALUE_GOES_ON = _JS_CONTINUATION_START | frozenset("([`")
# Python's `from X import ...`, with its module.
_PY_FROM_CLAUSE_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.*)$")
# The column-0 header of a block whose body may hold a compatibility import.
_PY_BLOCK_HEADER_RE = re.compile(r"^(?:try|except|else|if|elif|with|finally)(?!\w)")
# A column-0 Python `NAME = L` or `NAME: <type> = L`, the type holding no
# `=` or `;` (`{name}` escaped): L.
_PY_NAME_IS = r"^{name}\s*(?::(?!=)[^=;]+?)?(?<![=!<>])=(?!=)\s*([A-Za-z_]\w*)\s*$"
# A column-0 Python `NAME = M.L2` or `NAME: <type> = M.L2` (`{name}`
# escaped): (M, L2), a step of a rename chain only (`_Renames.member`).
_PY_NAME_IS_MEMBER = r"^{name}\s*(?::(?!=)[^=;]+?)?(?<![!<>])=(?!=)\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*$"
# The files a relative TS/JS module names, after the path itself:
# `<path><ext>`, then `<path>/index<ext>`.
_TSJS_MODULE_EXTENSIONS = (".ts", ".tsx", ".d.ts", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
# The TypeScript files a `.js`-family module names (`./m.js` is `m.ts`).
_TSJS_TWINS = {
    ".js": (".ts", ".tsx", ".d.ts"), ".jsx": (".tsx",), ".mjs": (".mts", ".d.mts"),
    ".cjs": (".cts", ".d.cts"),
}

# One name an import binds: (line from 1, local name, imported name, module).
# A namespace import binds its local name to no imported name (None).
_Binding = tuple[int, str, str | None, str | None]


def _js_blanked(code: str) -> str:
    """A comment-free TS/JS line with each one-line string's contents
    blanked, its quotes and its length kept."""
    return _JS_STRING_RE.sub(lambda m: m[0][0] + " " * (len(m[0]) - 2) + m[0][-1], code)


def _js_export_sides(item: str) -> tuple[str, str | None] | None:
    """(own name, the name after `as`, None without one) of an export-list
    item, a string side unquoted only when the string is the whole side
    (`L as "NAME"`, `"L" as NAME`). None for any other text."""
    m = _JS_EXPORT_ITEM_RE.match(item.strip())
    if m is None:
        return None
    own, exposed = (s[1:-1] if s and s[:1] in "'\"" else s for s in (m.group(1), m.group(2)))
    return own, exposed


def _js_passes_parameters(params: str | None, args: str | None) -> bool:
    """True when a `NAME = L` line's type parameters (`type NAME<P1, ...>`)
    reach `L` unchanged: neither parameters nor arguments, or bare
    parameters given as `L`'s arguments, the same names in the same order
    (`type NAME<K, V> = L<K, V>`). False for a constraint or a default
    (`<T extends X>`, `<T = X>`), a swap (`L<V, K>`), an instantiation
    (`L<string>`) and arguments with no parameters."""
    if params is None or args is None:
        return params is None and args is None
    names = [p.strip() for p in params.strip().removesuffix(",").split(",")]
    given = [a.strip() for a in args.strip().removesuffix(",").split(",")]
    return all(_JS_IDENT_RE.fullmatch(n) for n in names) and names == given


def _js_export_lists(
    lines: list[str], code: list[str]
) -> list[tuple[list[tuple[int, str]], str | None]]:
    """Each export list (`export { ... }`, `export type { ... }`) whose
    opening line is at column 0 as written (a comment may open the line):
    its items, as (line from 1, the item's comment-free text), and the
    module its `from` names, None for a local list. `code` holds the lines
    with comments removed (`_js_code_lines`). The list is split on a copy
    whose strings are blanked (`_js_blanked`), so a comma or a brace in a
    string splits nothing, and an item keeps its strings."""
    blank = [_js_blanked(c) for c in code]
    lists: list[tuple[list[tuple[int, str]], str | None]] = []
    i, n = 0, len(code)
    while i < n:
        opened = _JS_EXPORT_LIST_RE.match(blank[i]) if _is_column_0(lines[i]) else None
        if opened is None:
            i += 1
            continue
        j, col, items = i, opened.start(1), []
        while True:
            segment = blank[j][col:]
            end = segment.find("}")
            pos = col
            for piece in (segment if end < 0 else segment[:end]).split(","):
                text = code[j][pos : pos + len(piece)].strip()
                if text:
                    items.append((j + 1, text))
                pos += len(piece) + 1
            if end >= 0 or j + 1 >= n:
                break
            j, col = j + 1, 0
        module = None
        if end >= 0:
            after, k = code[j][col + end + 1 :], j + 1
            while not after.strip() and k < n:  # `}` then `from` on the next line
                after, k = code[k], k + 1
            found = _JS_FROM_RE.match(after)
            module = found.group(2) if found else None
        lists.append((items, module))
        i = j + 1
    return lists


def _js_import_bindings(lines: list[str], code: list[str]) -> list[_Binding]:
    """The names each column-0 import binds (`_Binding`): `import X from`
    binds X to the imported name `default`, `import { L as X }` binds X to
    L and `import { X }` X to X, on one line or over several, and a
    namespace import (`import * as X`, `import X = ...`) binds X to none."""
    found: list[_Binding] = []
    i, n = 0, len(code)
    while i < n:
        opens = _is_column_0(lines[i]) and _JS_IMPORT_RE.match(code[i]) is not None
        if not opens or _JS_IMPORT_BARE_RE.match(code[i]):
            i += 1
            continue
        j, text = i, code[i]
        while "{" in text and "}" not in text and j + 1 < n:
            j += 1
            text += "\n" + code[j]
        clause = _JS_IMPORT_CLAUSE_RE.match(text)
        if clause is None and j + 1 < n and _JS_FROM_RE.match(code[j + 1]):
            j += 1
            text += "\n" + code[j]
            clause = _JS_IMPORT_CLAUSE_RE.match(text)
        line = i + 1
        if clause is not None:
            names, module = clause.group(1).strip(), clause.group(3)
            default = _JS_IMPORT_DEFAULT_RE.match(names)
            if default is not None:
                found.append((line, default.group(1), "default", module))
                names = names[default.end() :].strip()
            if names.startswith("*"):
                namespace = _JS_IMPORT_NAMESPACE_RE.match(names)
                if namespace is not None:
                    found.append((line, namespace.group(1), None, module))
            elif names.startswith("{"):
                for item in names[1:].split("}", 1)[0].split(","):
                    m = _JS_IMPORT_ITEM_RE.match(item.strip())
                    if m is None:
                        continue
                    imported = m.group(1)
                    imported = imported[1:-1] if imported[:1] in "'\"" else imported
                    local = m.group(2) or imported
                    if _JS_IDENT_RE.fullmatch(local):
                        found.append((line, local, imported, module))
        else:
            equals = _JS_IMPORT_EQUALS_RE.match(text)
            if equals is not None:
                found.append((line, equals.group(1), None, None))
        i = j + 1
    return found


def _py_from_clause(code: str) -> re.Match[str] | None:
    """The `from X import` clause (`_PY_FROM_CLAUSE_RE`) a Python statement
    line opens, its `#` comment cut: the line itself, or the one-line body
    after the first colon of a column-0 `try`, `except`, `else`, `if`,
    `elif`, `with` or `finally` header (`try: from X import L as NAME`)."""
    found = _PY_FROM_CLAUSE_RE.match(code)
    if found is None and _PY_BLOCK_HEADER_RE.match(code) and ":" in code:
        found = _PY_FROM_CLAUSE_RE.match(code.split(":", 1)[1])
    return found


def _py_block_imports(lines: list[str], code: list[str], starts: set[int]) -> set[int]:
    """The lines (from 1) on which a `from X import` statement starts one
    level under a column-0 `try`, `except`, `else`, `if`, `elif`, `with` or
    `finally` (a compatibility import), or as the one-line body of such a
    header, after its first colon (`try: from X import L as NAME`), never
    in a `def`, a `class` or deeper. `code` holds the lines with their `#`
    comments cut, `starts` the statement starts (`_py_statement_starts`)."""
    found: set[int] = set()
    header, level = False, None
    for number in sorted(starts):
        text = lines[number - 1]
        if _is_column_0(text):
            header, level = _PY_BLOCK_HEADER_RE.match(code[number - 1]) is not None, None
            if header and _py_from_clause(code[number - 1]) is not None:
                found.add(number)  # the header's own one-line body
            continue
        indent = len(text) - len(text.lstrip())
        if level is None:
            level = indent  # the block's first statement sets its level
        if header and indent == level and _PY_FROM_CLAUSE_RE.match(code[number - 1]):
            found.add(number)
    return found


def _py_from_clauses(
    code: list[str], starts: set[int], keep: Callable[[int], bool]
) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """(line from 1, module, items) of each `from X import` statement that
    starts on a line `keep` accepts, an item as (line from 1, its text):
    on one line, in parentheses or continued with a backslash, a block
    header's one-line body included (`_py_from_clause`)."""
    clauses: list[tuple[int, str, list[tuple[int, str]]]] = []
    i, n = 0, len(code)
    while i < n:
        opened = _py_from_clause(code[i]) if i + 1 in starts and keep(i + 1) else None
        if opened is None:
            i += 1
            continue
        rest, items, j = opened.group(2).strip(), [], i
        paren = rest.startswith("(")
        if paren:
            rest = rest[1:]
        while True:
            if paren:
                done = ")" in rest
                piece = rest.split(")", 1)[0]
            else:
                piece = rest.rstrip()
                done = not piece.endswith("\\")
                piece = piece if done else piece[:-1]
            items += [(j + 1, t.strip()) for t in piece.split(",") if t.strip()]
            if done or j + 1 >= n:
                break
            j += 1
            rest = code[j]
        clauses.append((i + 1, opened.group(1), items))
        i = j + 1
    return clauses


class _Renames:
    """The renames one file makes, read once for the suspects' lookup (see
    `renames`), and the lines it adds to a name's declarations
    (`candidates`). `parts` is the file's path below the source root,
    `lines` its lines, `cache` the `_SourceCache` its rules ran with. A
    TS/JS line is read with its comments removed and an export list split
    with its strings blanked (`_js_export_lists`), a Python line with its
    `#` comment cut; a Python file that does not tokenize renames
    nothing."""

    def __init__(self, parts: tuple[str, ...], lines: list[str], cache: _SourceCache) -> None:
        self.parts = parts
        self.lines = lines
        self.cache = cache
        self.text = "\n".join(lines)
        path = Path(*parts)
        self.python = _rule_family(parts[-1]) == "python"
        self.starts: set[int] | None = None
        if self.python:
            self.code = [line.split("#", 1)[0] for line in lines]
            self.starts = cache.py_statement_starts(path, lines)
        else:
            self.code = cache.js_code_lines(path, lines)
        self._clauses: list[tuple[int, str, list[tuple[int, str]]]] | None = None
        self._lists: list[tuple[list[tuple[int, str]], str | None]] | None = None
        self._bindings: list[_Binding] | None = None

    # -- reading, once per file ---------------------------------------------

    def _py_clauses(self) -> list[tuple[int, str, list[tuple[int, str]]]]:
        """The `from X import` statements at column 0, one level in a
        column-0 block or a block header's one-line body
        (`_py_block_imports`)."""
        if self._clauses is None:
            if self.starts is None:
                self._clauses = []
            else:
                blocks = _py_block_imports(self.lines, self.code, self.starts)
                self._clauses = _py_from_clauses(
                    self.code, self.starts,
                    lambda n: _is_column_0(self.lines[n - 1]) or n in blocks,
                )
        return self._clauses

    def _js_lists(self) -> list[tuple[list[tuple[int, str]], str | None]]:
        if self._lists is None:
            self._lists = _js_export_lists(self.lines, self.code)
        return self._lists

    def _imports(self) -> list[_Binding]:
        """The names the file's column-0 imports bind (`_Binding`); a
        compatibility import, one level in a block or a block header's
        one-line body, binds none."""
        if self._bindings is None:
            if not self.python:
                self._bindings = _js_import_bindings(self.lines, self.code)
            elif self.starts is None:
                self._bindings = []
            else:
                found: list[_Binding] = []
                for start, module, items in self._py_clauses():
                    if not _is_column_0(self.lines[start - 1]) or (
                        _PY_FROM_CLAUSE_RE.match(self.code[start - 1]) is None  # `try: from ...`
                    ):
                        continue
                    for _, item in items:
                        m = _PY_IMPORT_ITEM_RE.match(item)
                        if m is not None and _PY_IDENT_RE.fullmatch(m.group(1)):
                            found.append((start, m.group(2) or m.group(1), m.group(1), module))
                for number in sorted(self.starts):
                    m = _PY_IMPORT_RE.match(self.code[number - 1])
                    if m is None or not _is_column_0(self.lines[number - 1]):
                        continue
                    for item in m.group(1).split(","):
                        bound = _PY_IMPORT_ITEM_RE.match(item.strip())
                        if bound is not None:  # `import a.b as c`, `import a`: a namespace
                            local = bound.group(2) or bound.group(1).split(".", 1)[0]
                            found.append((number, local, None, None))
                found.sort(key=lambda b: b[0])
                self._bindings = found
        return self._bindings

    def binding(self, local: str, number: int) -> tuple[str | None, str | None] | None:
        """(imported name, module) of the column-0 import that binds `local`
        for line `number` (from 1): the last one at or above it, else, in
        TS/JS, where imports are hoisted, the first below. The imported name
        is None for a namespace import (it binds no name). None when no
        import binds it."""
        above = below = None
        for line, name, imported, module in self._imports():
            if name != local:
                continue
            if line <= number:
                above = (imported, module)
            elif below is None:
                below = (imported, module)
        return above if above is not None or self.python else below

    def _bound(self, local: str, number: int) -> tuple[str | None, str | None]:
        """`local` as a rename's `L` with no `from`: the imported name and
        module of the import that binds it (no name for a namespace import),
        else `local` and no module."""
        return self.binding(local, number) or (local, None)

    def _goes_on(self, index: int) -> bool:
        """True when the TS/JS statement on line `index` (from 0) goes on
        with the next line that holds code."""
        for code in self.code[index + 1 :]:
            if code.strip():
                return code.lstrip()[0] in _JS_VALUE_GOES_ON
        return False

    # -- the answers --------------------------------------------------------

    def candidates(self, name: str, cache: _SourceCache, module_fallback: bool) -> list[int]:
        """The lines (from 1, sorted) of the file the suspects' lookup reads
        for `name`: every column-0 line that declares it (`declared_line`'s
        rule; with `module_fallback`, line 1 of the module or package so
        named when none does), a Python `from X import L as NAME` item one
        level in a column-0 `try`, `except`, `else`, `if`, `elif`, `with`
        or `finally` block or as such a header's one-line body
        (`try: from X import L as NAME`), and a TS/JS local export-list
        item `NAME` without `as` when a column-0 import binds NAME to
        another name (`import { L as NAME }`, `import NAME from`)."""
        if not name or "." in name:
            return []
        path = Path(*self.parts)
        top, _ = _line_matches(path.suffix.lower(), path, self.lines, name, cache, True)
        found = set(top)
        if not found and module_fallback and _module_name(self.parts) == name:
            found.add(1)
        esc = re.escape(name)
        if self.python:
            if re.search(rf"(?<!\w)as\s+{esc}(?!\w)", self.text):
                found.update(
                    line for _, _, items in self._py_clauses() for line, item in items
                    if self._py_renames(item, name) is not None
                )
        elif re.search(rf"(?<![\w$])(?:as|import(?:\s+type)?)\s+{esc}(?![\w$])", self.text) and any(
            local == name and imported not in (None, name)
            for _, local, imported, _ in self._imports()
        ):
            found.update(
                line for items, module in self._js_lists() if module is None
                for line, item in items if _js_export_sides(item) == (name, None)
            )
        return sorted(found)

    @staticmethod
    def _py_renames(item: str, name: str) -> str | None:
        """`L` of a `from X import` item `L as NAME`, L another identifier."""
        m = _PY_IMPORT_ITEM_RE.match(item)
        if m is None or m.group(2) != name or m.group(1) == name:
            return None
        return m.group(1) if _PY_IDENT_RE.fullmatch(m.group(1)) else None

    def renames(self, number: int, name: str) -> list[tuple[str, str | None]]:
        """(`L`, the module it comes from, None when unknown) for each
        rename to `name` on line `number` (from 1), `L` an identifier other
        than `name`:

        - an export-list item `L as NAME` (`export { ... }`, `export type
          { ... }`, the list's opening line at column 0 as written, a string
          side unquoted when the string is the whole side), `L` `default`
          included when the list has a `from`;
        - a local export-list item `NAME` without `as`, when a column-0
          import binds NAME to another name (`import { L as NAME }`, or
          `import NAME from`, `L` `default`);
        - a column-0 `const`, `let` or `var NAME = L`, annotated or not
          (`const NAME: <type> = L`, the type on the line, holding no `;`
          and no `=` but in `=>`), `type NAME = L` or a generic
          `type NAME<P1, ...> = L<P1, ...>` whose arguments are its bare
          parameters, the same names in the same order, exported or not,
          `L` a bare identifier and the statement ending there;
        - for `name` `default`, a column-0 `export default L`
          (`_JS_EXPORT_DEFAULT_IS_RE`, the `;` optional), `L` a bare
          identifier and the statement ending there: `L` taken from the
          import that binds it (`binding`) or, when the file declares `L`
          (`declared_line`, no module so named), from the file itself;
        - a Python `from X import L as NAME` item, the statement at column 0,
          one level in a column-0 `try`, `except`, `else`, `if`, `elif`,
          `with` or `finally` block or as such a header's one-line body
          (`try: from X import L as NAME`), and a column-0 `NAME = L` or
          `NAME: <type> = L` (the type holding no `;` or `=`), `L` a bare
          identifier.

        The module is the list's or the clause's `from`; a rename with none
        takes the column-0 import that binds `L` (`binding`), `L` becoming
        its imported name, and a namespace import's name renames nothing.
        Empty for any other line: `as NAME` in a comment or a string, a TS
        type assertion (`const NAME = x as NAME`), a call or any other
        expression (`NAME = a.b` included: `member` reads it, as a step of
        a chain only), a default export of anything but a bare `L` an
        import or a declaration of the file binds (`export default make()`,
        an object, an arrow, a value that goes on to the next line, a
        namespace import's `L`), a generic alias whose parameters are
        constrained, defaulted, swapped or instantiated (`type NAME<T
        extends X> = L<T>`, `type NAME<K, V> = L<V, K>`, `type NAME =
        L<string>`), a Python `import M as NAME` and a rename inside a
        `def` or a `class`."""
        if not 0 < number <= len(self.lines):
            return []
        found: list[tuple[str | None, str | None]] = []
        index = number - 1
        if self.python:
            for _, module, items in self._py_clauses():
                for line, item in items:
                    local = self._py_renames(item, name) if line == number else None
                    if local is not None:
                        found.append((local, module))
            starts = self.starts or set()
            if number in starts and _is_column_0(self.lines[index]):
                m = re.match(_PY_NAME_IS.format(name=re.escape(name)), self.code[index])
                if m is not None and m.group(1) != name:
                    found.append(self._bound(m.group(1), number))
            return [(local, module) for local, module in found if local is not None]
        for items, module in self._js_lists():
            for line, item in items:
                sides = _js_export_sides(item) if line == number else None
                if sides is None:
                    continue
                own, exposed = sides
                if exposed is None and own == name and module is None:
                    bound = self.binding(name, number)  # a plain re-export of an import
                    if bound is not None and bound[0] != name:
                        found.append(bound)
                elif exposed == name and own != name and _JS_IDENT_RE.fullmatch(own):
                    if module is not None:
                        found.append((own, module))
                    elif own != "default":
                        found.append(self._bound(own, number))
        m = _JS_NAME_IS_RE.match(self.code[index]) if _is_column_0(self.lines[index]) else None
        if (
            m is not None and (m["var"] or m["type"]) == name and m["value"] != name
            and (m["end"] or not self._goes_on(index))
            and _js_passes_parameters(m["params"], m["args"])
        ):
            found.append(self._bound(m["value"], number))
        m = (
            _JS_EXPORT_DEFAULT_IS_RE.match(self.code[index])
            if name == "default" and _is_column_0(self.lines[index]) else None
        )
        if m is not None and m["value"] != name and (m["end"] or not self._goes_on(index)):
            bound = self.binding(m["value"], number)  # a namespace import's (None, module) renames nothing
            if bound is not None:
                found.append(bound)
            elif declared_line(self.parts, m["value"], lines=self.lines, cache=self.cache,
                               module_fallback=False) is not None:
                found.append((m["value"], None))
        return [(local, module) for local, module in found if local is not None]

    def member(self, number: int, name: str) -> tuple[str, str] | None:
        """(`L2`, its module) of a column-0 Python `NAME = M.L2` (or
        `NAME: <type> = M.L2`) on line `number` (from 1) whose `M` a
        column-0 `from X import M` binds: the module is `X` joined with
        `M`'s imported name, `.` prefixes kept (`from . import _core` gives
        `._core`). A step of a rename chain only
        (`_DeclarationLookup._aliases`): at the documented name's own line
        it renames nothing. None for any other line, an `M` an
        `import a.b as M` binds included."""
        if not self.python or not 0 < number <= len(self.lines):
            return None
        if number not in (self.starts or set()) or not _is_column_0(self.lines[number - 1]):
            return None
        m = re.match(_PY_NAME_IS_MEMBER.format(name=re.escape(name)), self.code[number - 1])
        bound = None if m is None else self.binding(m.group(1), number)
        if bound is None or bound[0] is None or bound[1] is None:
            return None
        imported, module = bound
        return m.group(2), (module if module.endswith(".") else module + ".") + imported


class _DeclarationLookup:
    """Where the source declares the stale names (classify-stale's
    `defined_at`): a column-0 declaration, an alias that renames included, a
    plain or star import and a re-export never counting.

    A module or package named after the name (`_module_name`) declares it,
    at its line 1 when no line of it does, unless `find` takes the name as
    `strict` and the file is not a TS/JS one that is itself the export
    (`_exports_itself`). A file the name's entries cite that declares it
    gives its first such line. Otherwise the walk lists every file that
    declares it (`declared_in`), and exactly one must: the walk reads,
    sorted, the files below the walk root (`_walk_root`), leaving out the
    folders `_lookup_skips_folder` names, the `LOOKUP_WALK_FOLDERS`, the
    `LOOKUP_TOP_FOLDERS` right below the walk root and a package root
    (`_is_package_root`) that hold no cited file, the files
    `_lookup_skips_file` names and every symlink. With a `scope`
    (`read_brief_scope`), until `keep_declaring`, a walked file the brief
    scopes out declares a name only when no walked file in its scope does
    (`find`). Only the rule families
    (Python, TS/JS) the entries cite are read (both when no entry cites a
    file). A cited file is read in any folder, a hidden one and one the walk
    skips included, but only inside the source root, with no symlink on its
    path and under a name `_lookup_skips_file` accepts (`_readable_below`).
    The walk runs once for all the names no cited file settles: each file is
    read once, and only a file whose text holds a name goes through the
    rules. In the suspects' pass (`keep_declaring`), a file's declarations
    are its candidate lines (`_Renames.candidates`: every column-0
    declaring line, a Python compatibility import one level in a column-0
    block or as a block header's one-line body, and a TS/JS re-export of a
    renaming import), the file listed at the first, and `renamed` then
    tells which of a name's candidate lines is an alias of the declaration
    a cited file holds, from the lines the lookup read, reading too the
    files a rename's `from` resolves to (`_resolve`) and, along a chain of
    renames (`_aliases`), the files each later step resolves to. The
    renames read include an annotated `const`, `let` or `var` or Python
    `NAME: <type> = L`, a generic `type NAME<P1, ...> = L<P1, ...>`, an
    import one level in a `with` or `finally` block or as a block header's
    one-line body, a column-0 `export default L` of an `L` an import or a
    declaration of the file binds, and a middle step `L = M.L2`; a chain
    that leaves the resolved files, loops or ends at another declaration,
    a constrained, defaulted, swapped or instantiated generic, a call and
    a default export of any other expression stay fabricated.
    Any error of the filesystem raises (`_LOOKUP_ERRORS`)."""

    def __init__(
        self, entries: list[dict], source_root: Path, scope: BriefScope | None = None
    ) -> None:
        self.root = source_root
        self.real_root = source_root.resolve()
        # the brief's scope, which `find` applies to the walk until `keep_declaring`
        self.scope = scope
        recorded = [f for f in map(_entry_file, entries) if f is not None]
        # a map that cites no file names no language: both families
        self.families = _lookup_families(recorded)
        self.folder = self._walk_root(recorded)
        # the folders that hold a cited file: a LOOKUP_TOP_FOLDERS one is walked
        self._cited_folders = _cited_folders(recorded)
        # the cited files read, kept for the walk: a few files at most
        self._cited: dict[tuple[str, ...], list[str] | None] = {}
        self._cited_cache = _SourceCache()
        # during the suspects' pass only (`keep_declaring`): the renames of
        # each file a declaration was found in, by path, and each (path, name)
        # its candidate lines, which `renamed` reads
        self._declaring: dict[str, _Renames] | None = None
        self._candidates: dict[tuple[str, str], list[int]] = {}
        # the files a rename's `from` resolves to and the renaming files, that no entry cites
        self._resolved: dict[tuple[str, ...], list[str] | None] = {}
        # the renames of each file a rename chain goes through (`_aliases`), by path
        self._chain: dict[tuple[str, ...], _Renames | None] = {}

    # -- the walk root ------------------------------------------------------

    def _symlinked(self, parts: tuple[str, ...]) -> bool:
        """True when a path below the source root goes through a symlink,
        itself included."""
        return _symlinked(self.root, parts)

    def _real_folder(self, parts: tuple[str, ...]) -> tuple[str, ...]:
        """The deepest folder of a path below the source root that is one,
        with no symlink on its path."""
        while parts and (
            self._symlinked(parts) or not self.root.joinpath(*parts).is_dir()
        ):
            parts = parts[:-1]
        return parts

    def _holds(self, folder: tuple[str, ...], filename: str) -> bool:
        return (self.root.joinpath(*folder) / filename).is_file()

    def _package_root(
        self, folder: tuple[str, ...], family: str
    ) -> tuple[str, ...] | None:
        """The root of the package a folder below the source root lies in,
        None when it lies in none. Python: the nearest folder at or above it
        that holds `__init__.py`, then up while the parent holds one, never
        the source root itself (a stray `__init__.py` there would make the
        whole tree one package). TS/JS: the nearest folder at or above it
        that holds `package.json`."""
        marker = _PACKAGE_MARKERS[family]
        python = family == "python"
        here = folder
        while not (self._holds(here, marker) and (here or not python)):
            if not here:
                return None
            here = here[:-1]
        if python:
            while len(here) > 1 and self._holds(here[:-1], marker):
                here = here[:-1]
        return here

    def _walk_root(self, recorded: list[str]) -> tuple[str, ...]:
        """The folder the walk reads: the deepest folder the entries' files
        share, widened to its package root, leaving out an entry outside
        every package (the source root when no entry lies in one)."""
        folders: list[tuple[str, ...]] = []
        widen: set[str] = set()
        for source_file in recorded:
            parts = _cited_parts(source_file)
            family = _rule_family(source_file) if parts else None
            if family is None:
                continue
            if self._package_root(self._real_folder(parts[:-1]), family) is None:
                continue  # outside every package: a script, a docs page
            folders.append(parts[:-1])
            widen.add(family)
        if not folders:
            return ()
        shared = self._real_folder(tuple(os.path.commonprefix(folders)))
        roots = [self._package_root(shared, family) for family in sorted(widen)]
        return min((r for r in roots if r is not None), key=len, default=shared)

    # -- reading ------------------------------------------------------------

    def _reads_cited(self, parts: tuple[str, ...]) -> bool:
        """True when the lookup reads a cited file: one of a family the
        entries cite, in any folder (one the walk skips or a hidden one
        included), with no symlink on its path, inside the source root and
        under a name `_lookup_skips_file` accepts (`_readable_below`)."""
        return _rule_family(parts[-1]) in self.families and _readable_below(
            self.root, parts, self.real_root
        )

    def _cited_lines(self, parts: tuple[str, ...]) -> list[str] | None:
        if parts not in self._cited:
            readable = self._reads_cited(parts)
            path = self.root.joinpath(*parts)
            self._cited[parts] = _text_lines(_read_source(path)) if readable else None
        return self._cited[parts]

    def _lines_of(self, parts: tuple[str, ...]) -> list[str] | None:
        """The lines of a file the alias check reads, a cited one or one a
        rename's `from` resolves to, under `_reads_cited`'s guards, or the
        renaming file, whose lines `renamed` keeps; each file read once."""
        if parts in self._cited:
            return self._cited[parts]
        if parts not in self._resolved:
            readable = self._reads_cited(parts)
            path = self.root.joinpath(*parts)
            self._resolved[parts] = _text_lines(_read_source(path)) if readable else None
        return self._resolved[parts]

    def _declares(self, parts: tuple[str, ...], local: str) -> bool:
        """True when a file declares `local` by `declared_line`'s rule, no
        module or package so named counting."""
        lines = self._lines_of(parts)
        return lines is not None and declared_line(
            parts, local, lines=lines, cache=self._cited_cache, module_fallback=False
        ) is not None

    def _resolve(self, parts: tuple[str, ...], module: str) -> list[tuple[str, ...]]:
        """The files below the source root that a rename's module names, from
        the renaming file `parts`, each one the lookup may read
        (`_reads_cited`). TS/JS: a `./` or `../` module only, from the file's
        folder: the path itself, a `.js`-family path's TypeScript twin
        (`./m.js` names `m.ts`), `<path><ext>` and `<path>/index<ext>`
        (`_TSJS_MODULE_EXTENSIONS`). Python: a relative module (`.m`, `..m`,
        `.` the folder's own `__init__`) from the file's folder, or an
        absolute one below the parent of the file's package root
        (`_package_root`): `m.py`, `m.pyi`, `m/__init__.py` and
        `m/__init__.pyi`. Empty for a bare package name, a tsconfig `paths`
        alias, a module that climbs out of the source root and one with no
        such file."""
        if _rule_family(parts[-1]) == "python":
            dots = len(module) - len(module.lstrip("."))
            names = module[dots:].split(".") if module[dots:] else []
            if any(not n for n in names):
                return []
            if dots:
                if dots > len(parts):
                    return []
                base = parts[: len(parts) - dots]
            else:
                root = self._package_root(self._real_folder(parts[:-1]), "python")
                if root is None or not names:
                    return []
                base = root[:-1]
            here = (*base, *names)
            tried = [(*here[:-1], here[-1] + ext) for ext in (".py", ".pyi")] if names else []
            tried += [(*here, "__init__.py"), (*here, "__init__.pyi")]
        else:
            if module not in (".", "..") and not module.startswith(("./", "../")):
                return []  # a package name or a `paths` alias: not read
            path = posixpath.normpath(posixpath.join(*parts[:-1], module))
            if path == ".." or path.startswith("../"):
                return []
            here = () if path == "." else tuple(path.split("/"))
            tried = []
            if here:
                stem, ext = posixpath.splitext(here[-1])
                if ext.lower() in TSJS_EXTENSIONS:
                    tried.append(here)
                    twins = _TSJS_TWINS.get(ext.lower(), ())
                    tried += [(*here[:-1], stem + twin) for twin in twins]
                tried += [(*here[:-1], here[-1] + ext) for ext in _TSJS_MODULE_EXTENSIONS]
            tried += [(*here, "index" + ext) for ext in _TSJS_MODULE_EXTENSIONS]
        return [p for p in dict.fromkeys(tried) if self._reads_cited(p)]

    def _is_package_root(self, folder: tuple[str, ...], filenames: list[str]) -> bool:
        """True when a walked folder (its `filenames`) is a package root of a
        family the walk reads, as `_package_root` finds one: TS/JS, a folder
        that holds `package.json`; Python, the top of an `__init__.py`
        chain, never the source root."""
        if "tsjs" in self.families and "package.json" in filenames:
            return True
        return (
            "python" in self.families and bool(folder) and "__init__.py" in filenames
            and (len(folder) == 1 or not self._holds(folder[:-1], "__init__.py"))
        )

    def _tree(self) -> list[tuple[str, ...]]:
        """The files the walk reads, as segments below the source root,
        sorted."""
        top = self.root.joinpath(*self.folder)
        found: list[tuple[str, ...]] = []

        def fail(exc: OSError) -> None:
            raise exc

        for dirpath, dirnames, filenames in os.walk(top, onerror=fail):
            here = Path(dirpath)
            inner = here.relative_to(top).parts
            below = self.folder + inner
            # a LOOKUP_TOP_FOLDERS name is skipped right below the walk root
            # and a package root, unless it holds a cited file
            root = not inner or self._is_package_root(below, filenames)
            dirnames[:] = [
                d for d in dirnames
                if not _walk_skips_folder(
                    d, root and (*below, d) not in self._cited_folders
                )
                and not (here / d).is_symlink()
            ]
            for filename in filenames:
                path = here / filename
                if (
                    _rule_family(filename) in self.families
                    and not _lookup_skips_file(filename)
                    and not path.is_symlink()
                    and path.is_file()
                ):
                    found.append((*below, filename))
        return sorted(found)

    def _first(
        self,
        parts: tuple[str, ...],
        lines: list[str],
        name: str,
        cache: _SourceCache,
        module_fallback: bool = True,
    ) -> str | None:
        """`file:line` of the first line of a file that declares `name`, else,
        with `module_fallback`, its line 1 when it is the module or package
        so named (`declared_line`). After `keep_declaring`, the first of the
        file's candidate lines (`_Renames.candidates`, which adds a Python
        compatibility import and a TS/JS re-export of a renaming import),
        each kept, with the file's renames, for `renamed`."""
        file = "/".join(parts)
        if self._declaring is None:
            line = declared_line(
                parts, name, lines=lines, cache=cache, module_fallback=module_fallback
            )
            return None if line is None else f"{file}:{line}"
        renames = self._declaring.get(file) or _Renames(parts, lines, cache)
        candidates = renames.candidates(name, cache, module_fallback)
        if not candidates:
            return None
        self._declaring[file] = renames
        self._candidates[(file, name)] = candidates
        return f"{file}:{candidates[0]}"

    # -- the answer ---------------------------------------------------------

    def find(
        self,
        cited: dict[str, list[str]],
        strict: frozenset[str] = frozenset(),
        cited_fallback: bool = True,
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        """For the names of `cited` (name -> the source_file values its
        entries record): name -> `file:line` for each one the source
        declares, and name -> the sorted `file:line` of every walked file
        that declares it, for each name the walk looked for (the names no
        cited file settles). A dotted name is never looked up, and a name of
        `strict` takes no line 1 from a module or package so named that is
        not itself the export (`_exports_itself`), in a cited file or in
        the walk. Without `cited_fallback` (the suspects' pass), a cited
        file takes no line 1 from its module or package so named, the export
        or not, so that the walk runs and finds the renames; the walk keeps
        its module rule. With a `scope`, a walked file the brief scopes out
        declares a name, and makes it unsure, only when no walked file in
        the brief's scope declares it (#1007)."""
        found: dict[str, str] = {}
        if not self.families:
            return found, {}
        pending: list[str] = []
        for name, files in cited.items():
            if not name or "." in name:
                continue
            for parts in dict.fromkeys(filter(None, map(_cited_parts, files))):
                lines = self._cited_lines(parts)
                hit = None if lines is None else self._first(
                    parts, lines, name, self._cited_cache,
                    cited_fallback
                    and (name not in strict or _exports_itself(parts, "\n".join(lines))),
                )
                if hit is not None:
                    found[name] = hit
                    break
            else:
                pending.append(name)
        declared, unsure = self._walk(pending, strict) if pending else ({}, {})
        if self.scope is not None:
            scoped_out = self.scope.scoped_out
            for name, hits in declared.items():
                # a copy outside the brief's scope is no second declaration
                kept = [h for h in hits if not scoped_out(h.rsplit(":", 1)[0])]
                if kept:
                    declared[name] = kept
                    unsure[name] = [f for f in unsure.get(name, []) if not scoped_out(f)]
        # exactly one walked file must declare a name, and none it holds
        # in an untokenizable Python file may
        found.update({
            name: h[0] for name, h in declared.items()
            if len(h) == 1 and not unsure.get(name)
        })
        return found, declared

    def _walk(
        self, names: list[str], strict: frozenset[str] = frozenset()
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """name -> the sorted `file:line` of each walked file that declares
        it, at the file's first declaration (a stub beside its
        implementation left out: `_without_stubs`; a module so named
        declaring no name of `strict` unless it is the export), and name ->
        the Python files that do not tokenize and hold it, which may
        declare it."""
        hits: dict[str, list[str]] = {name: [] for name in names}
        unsure: dict[str, list[str]] = {}
        for parts in self._tree():
            module = _module_name(parts)
            lines = self._cited.get(parts)
            text = (
                _read_source(self.root.joinpath(*parts))
                if lines is None
                else "\n".join(lines)  # a cited file, read already
            )
            # a strict name's module so named counts when it is the export
            fallback = module not in strict or _exports_itself(parts, text)
            # the substring test spares the rules most files and names
            here = sorted(
                n for n in names if n in text or (n == module and fallback)
            )
            if not here:
                continue
            if lines is None:
                lines = _text_lines(text)
            # this file's rules only; a declaring file's `_Renames` keeps it
            # for `renamed`
            cache = _SourceCache()
            path = Path(*parts)
            if path.suffix.lower() in PYTHON_EXTENSIONS and (
                cache.py_statement_starts(path, lines) is None
            ):
                for n in here:
                    if n in text:
                        unsure.setdefault(n, []).append("/".join(parts))
            for name in here:
                hit = self._first(parts, lines, name, cache, fallback)
                if hit is not None:
                    hits[name].append(hit)
        return {name: sorted(_without_stubs(h)) for name, h in hits.items()}, unsure

    def keep_declaring(self) -> None:
        """From now on, keep the candidate lines and the renames of each file
        a declaration is found in, for `renamed`: the suspects' pass, which
        comes last. Its walk counts the files the brief scopes out like any
        other, so that an alias in one still clears its name."""
        self._declaring = {}
        self._candidates = {}
        self.scope = None

    def _renames_of(self, parts: tuple[str, ...]) -> _Renames | None:
        """The renames of a file a rename chain goes through, read once
        (`_lines_of`); None when the lookup does not read it."""
        if parts not in self._chain:
            lines = self._lines_of(parts)
            self._chain[parts] = None if lines is None else _Renames(parts, lines, self._cited_cache)
        return self._chain[parts]

    def _steps(self, parts: tuple[str, ...], local: str) -> list[tuple[str, str | None]]:
        """The renames of `local` a file a rename chain goes through makes,
        each a next step (`L2`, its module, None when unknown): per
        candidate line of `local` in order (`_Renames.candidates`), each
        rename the line makes (`_Renames.renames`) and a Python
        `local = M.L2` (`_Renames.member`). Empty when the file renames no
        `local` or the lookup does not read it."""
        renames = self._renames_of(parts)
        steps: list[tuple[str, str | None]] = []
        for line in [] if renames is None else renames.candidates(local, self._cited_cache, False):
            steps.extend(renames.renames(line, local))
            member = renames.member(line, local)
            if member is not None:
                steps.append(member)
        return steps

    def _aliases(
        self, parts: tuple[str, ...], local: str, module: str | None,
        cited: list[tuple[str, ...]], seen: set[tuple[tuple[str, ...], str]],
        first: bool = True,
    ) -> str | None:
        """The name a cited file declares when a rename in the file `parts`
        of `local` from `module` (None when unknown) renames that
        declaration, directly (`local` itself) or through a chain of
        renames (the name at the chain's end); None when it does not. The
        files `local` resolves to are the file `parts` when `module` is
        None, else the files the module resolves to (`_resolve`). When one
        of them that declares `local` is cited, the rename is an alias.
        Otherwise the chain follows each of them that declares `local` or
        renames it (`_steps`: an export-list alias, a compatibility import
        in a block or on one line, an import then a plain re-export, an
        assignment of a bare `L`, annotated or not, an `export default L`
        of a bound `L`, or a Python `local = M.L2`): each rename is the
        next step, until a step reaches a cited file that declares its
        name, or none does. When no file declares `local` (a package name,
        a path that names no file, a file that declares no `local`, such as
        a barrel that re-exports it), a cited file that declares `local`
        clears the name at the `first` rename only; at a later step that
        case ends the chain unless a resolved file renames `local`. `seen`
        holds the (file, name) pairs the chain followed, each a resolved
        file that declares or renames the name, fresh for each first
        rename: a chain that comes back to one (a loop) ends. No module or
        package so named counts."""
        resolved = [parts] if module is None else self._resolve(parts, module) if module else []
        declaring = [p for p in resolved if self._declares(p, local)]
        if not declaring and first and any(self._declares(p, local) for p in cited):
            return local
        if any(p in cited for p in declaring):
            return local
        for file in resolved:
            if (file, local) in seen:
                continue
            seen.add((file, local))
            for name, source in self._steps(file, local):
                end = self._aliases(file, name, source, cited, seen, first=False)
                if end is not None:
                    return end
        return None

    def renamed(
        self, name: str, hits: list[str], files: list[str]
    ) -> tuple[str, str] | None:
        """(`file:line`, `L`) of the first rename to `name` that is an alias
        of the declaration of `L` a file of `files` (source_file values, as
        recorded) holds (`_aliases`), directly or through a chain of renames
        across the files it resolves: per file of `hits` (`file:line`
        declarations of `name` the lookup found, sorted), per candidate
        line in order (`_Renames.candidates`), each rename the line makes
        (`_Renames.renames`). `L` is the name the cited file declares where
        the chain ends: for a one-step rename, the name that rename
        renames. The lines are the ones the lookup read after
        `keep_declaring` (`_first`), never read again; a file a rename's
        module resolves to is read once. None when no line is such an
        alias."""
        cited = list(dict.fromkeys(filter(None, map(_cited_parts, files))))
        for hit in sorted(hits):
            file, _, number = hit.rpartition(":")
            renames = (self._declaring or {}).get(file)
            if renames is None or not number.isdigit():
                continue
            if renames.parts not in self._cited:  # read already, and `_aliases` may check it
                self._resolved.setdefault(renames.parts, renames.lines)
            for line in self._candidates.get((file, name), [int(number)]):
                for local, module in renames.renames(line, name):
                    end = self._aliases(renames.parts, local, module, cited, set())
                    if end is not None:
                        return f"{file}:{line}", end
        return None


def inventory_kinds(data: object, path: str) -> dict[str, frozenset[str]]:
    """name -> the kinds a documented inventory gives it (`--inventory`):
    validate-inventory.py's `--output` file, `{"exports": [...]}`, or its
    whole result, the inventory under `inventory`. An item without a string
    `name` and `kind` is left out, and a kind is kept in lower case. Raises
    ValueError when no `exports` list is there."""
    if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
        data = data["inventory"]  # validate-inventory.py's whole result
    if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
        raise ValueError(f"--inventory {path} holds no `exports` list")
    kinds: dict[str, set[str]] = {}
    for item in data["exports"]:
        if not isinstance(item, dict):
            continue
        name, kind = item.get("name"), item.get("kind")
        if isinstance(name, str) and isinstance(kind, str):
            kinds.setdefault(name, set()).add(kind.strip().lower())
    return {name: frozenset(k) for name, k in kinds.items()}


def _module_entry(entry: dict) -> bool:
    """True for a `module` or `package` entry."""
    kind = entry.get("export_type")
    return isinstance(kind, str) and kind.strip().lower() in NO_DEFINITION_EXPORT_TYPES


class BriefScope:
    """A skill brief's `scope.include` and `scope.exclude` globs
    (`read_brief_scope`), applied to a path relative to the source root as
    skf-extract-public-api.py applies them to choose its files in scope,
    with skf-resolve-authoritative-files.py's `glob_match`."""

    def __init__(
        self, includes: list[str], excludes: list[str],
        glob_match: Callable[[str, str], bool],
    ) -> None:
        self.includes = includes
        self.excludes = excludes
        self._match = glob_match

    def scoped_out(self, rel: str) -> bool:
        """True when an exclude glob matches `rel`, or the brief has include
        globs and none matches it."""
        if any(self._match(rel, g) for g in self.excludes):
            return True
        return bool(self.includes) and not any(self._match(rel, g) for g in self.includes)


def _brief_globs(value: object) -> list[str]:
    """The string globs of a brief's scope list, as skf-extract-public-api.py
    normalizes them: forward slashes, no leading `./` or `/`, none empty."""
    globs: list[str] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, str):
            continue
        text = item.strip().replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        if text.lstrip("/"):
            globs.append(text.lstrip("/"))
    return globs


def read_brief_scope(path: Path) -> BriefScope:
    """The scope globs of a skill brief (`--brief`), read with
    skf-resolve-authoritative-files.py's `parse_brief_yaml`. Raises
    ValueError when the brief cannot be read, is not YAML or is not a
    mapping, and ImportError when PyYAML or that helper does not load."""
    try:
        import yaml  # only --brief reads YAML here; `uv run` installs it
    except ImportError as exc:
        raise ImportError(
            "classify-stale reads --brief with PyYAML: run the helper with "
            "`uv run`, which installs it"
        ) from exc
    resolver = _load_sibling_module(BRIEF_RESOLVER_HELPER, "skf_resolve_authoritative_files")
    try:
        data = resolver.parse_brief_yaml(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"failed to read brief {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"malformed YAML in brief {path}: {' '.join(str(exc).split())}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"brief {path} is not a YAML mapping")
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    return BriefScope(
        _brief_globs(scope.get("include")), _brief_globs(scope.get("exclude")),
        resolver.glob_match,
    )


def classify_stale(
    names: list[str],
    prov: dict,
    source_root: Path,
    kinds: dict[str, frozenset[str]] | None = None,
    scope: BriefScope | None = None,
) -> list[dict]:
    """The fabricated-signature test for each stale name: the definition-lines
    rules at every provenance entry whose raw `export_name` is the name, and
    for a name that is not fabricated, where the source declares it
    (`defined_at`, and `declared_in` when the walk looked for it). A name
    the cited files do not define is looked up too, after the others and
    in a lookup of its own (an error there keeps it fabricated and clears
    no other name), with no line 1 from a cited module or package so named,
    and none in the walk unless it is the export, and is `aliased`, not
    fabricated, when one of its candidate lines renames to it the
    declaration a `checked` entry's file holds, directly or through a
    chain of renames across the files it resolves
    (`_DeclarationLookup.renamed`, which resolves the rename's `from` and
    follows the chain until it reaches a cited declaration, leaves the
    files it reads, loops or ends at another declaration), and its
    `renames` then holds the name the cited file declares where the chain
    ends, for a one-step rename the name that line renames (no other item
    has the key); any other such name keeps both null. The renames read
    include an annotated `const`, `let` or `var` or Python
    `NAME: <type> = L`, a generic `type NAME<P1, ...> = L<P1, ...>`, an
    import one level in a `with` or `finally` block or as a block header's
    one-line body, a column-0 `export default L` of an `L` an import or a
    declaration of the file binds, and a middle step `L = M.L2`; a chain
    that leaves the resolved files, loops or ends at another declaration,
    a constrained, defaulted, swapped or instantiated generic, a call and
    a default export of any other expression stay fabricated.
    The classify-stale section of the module docstring gives each reason,
    what a `no-file` entry means, which entry gives `source` and how
    `defined_at` and `declared_in` are found. A `checked` entry with no
    definition line at an `export *` or `export type *` line gains `star`,
    the module it names (`_star_line`, #1070), and no verdict changes for
    it. `kinds` (`inventory_kinds`,
    None without `--inventory`) keeps a name of a `NO_MODULE_KINDS` kind
    from a module or package so named, unless an entry of the name is a
    `module` or `package` one. `scope` (`read_brief_scope`, None without
    `--brief`) keeps a walked file the brief scopes out from declaring a
    name that is not fabricated when a walked file in its scope declares
    it, so that a copy in a sibling app does not count as a second
    declaration; the suspects' walk still counts it.
    """
    entries = [e for e in prov.get("entries") or [] if isinstance(e, dict)]
    results: list[dict] = []
    # the names to look up that are not fabricated: name -> its cited files
    cited: dict[str, list[str]] = {}
    # the not-defined names an alias may clear: name -> its checked entries' files
    suspects: dict[str, list[str]] = {}
    # the names a module so named does not declare
    strict: set[str] = set()
    for name in names:
        mine = [e for e in entries if e.get("export_name") == name]
        checks: list[dict] = []
        for entry in mine:
            line_check, defs = _stale_line_check(entry, name, source_root)
            check = {
                "source_file": entry.get("source_file"),
                "source_line": entry.get("source_line"),
                "line_check": line_check,
                "definition_lines": defs,
            }
            if line_check == "checked" and not defs:
                # what the line is, for test-skill to read: never a verdict
                star = _star_line(entry, source_root)
                if star is not None:
                    check["star"] = star
            checks.append(check)
        if not checks:
            reason = STALE_NO_ENTRY
        elif all(
            c["line_check"] == "file-missing"
            or (c["line_check"] == "checked" and not c["definition_lines"])
            for c in checks
        ):
            reason = STALE_NOT_DEFINED
        elif any(
            c["line_check"] == "checked" and c["definition_lines"] for c in checks
        ):
            reason = STALE_DEFINED
        else:
            reason = STALE_UNCHECKED
        source = next(filter(None, map(_entry_citation, mine)), None)
        fabricated = reason == STALE_NOT_DEFINED
        if fabricated:
            # a missing file declares nothing an alias could rename
            checked = [c["source_file"] for c in checks if c["line_check"] == "checked"]
            if checked:
                suspects[name] = checked
        else:
            cited[name] = [f for f in map(_entry_file, mine) if f is not None]
            documented = (kinds or {}).get(name, frozenset())
            if documented & NO_MODULE_KINDS and not any(map(_module_entry, mine)):
                strict.add(name)
        results.append(
            {
                "name": name,
                "fabricated": fabricated,
                "source": source,
                "defined_at": None,
                "declared_in": None,
                "reason": reason,
                "entries": checks,
            }
        )
    lookup: _DeclarationLookup | None = None
    try:
        lookup = _DeclarationLookup(entries, source_root, scope)
        found, declared = lookup.find(cited, frozenset(strict))
    except _LOOKUP_ERRORS:
        # a lookup that fails proves nothing: every name stays null
        found, declared = {}, {}
    # the suspects' own lookup, after: an error there clears no name settled
    # above, and keeps every suspect fabricated
    aliased: dict[str, tuple[str, str]] = {}  # name -> (the rename's `file:line`, the chain-end `L`)
    suspect_declared: dict[str, list[str]] = {}
    if suspects and lookup is not None:
        try:
            # a suspect is strict, and a cited module so named never settles
            # it before the walk, which finds the renames
            lookup.keep_declaring()
            suspect_found, suspect_declared = lookup.find(
                suspects, frozenset(suspects), cited_fallback=False
            )
            for name, files in suspects.items():
                hits = suspect_declared[name] if name in suspect_declared else (
                    [suspect_found[name]] if name in suspect_found else []
                )
                alias = lookup.renamed(name, hits, files)
                if alias is not None:
                    aliased[name] = alias
        except _LOOKUP_ERRORS:
            aliased, suspect_declared = {}, {}
    for item in results:
        name = item["name"]
        if name in suspects:
            if name in aliased:
                defined_at, local = aliased[name]
                item.update(
                    fabricated=False, reason=STALE_ALIASED,
                    defined_at=defined_at, declared_in=suspect_declared.get(name), renames=local,
                )
            continue  # any other suspect stays fabricated, both null
        item["defined_at"] = found.get(name)
        item["declared_in"] = declared.get(name)
    return results


# --------------------------------------------------------------------------
# Skill citations ([AST:] / [SRC:] prefixes)
# --------------------------------------------------------------------------

# `[AST:path:L12]`, `[SRC:path:L12-34]`, `[SRC:path:L12-L34]`. A citation
# with no `:L<n>` part does not match and is ignored. Groups: prefix, path,
# first line, the `L` of a range's end (may be empty), the range's end.
_SKILL_CITATION_RE = re.compile(
    r"\[(AST|SRC):([^\[\]\n]+?):L(\d+)(?:-(L?)(\d+))?\]"
)


def normalize_path(path: str) -> str:
    """Normalize a cited or recorded source path for comparison."""
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return posixpath.normpath(p) if p else p


def skill_markdown_files(skill_dir: Path) -> list[Path]:
    """`SKILL.md` then every `references/**/*.md`, in a stable order."""
    files: list[Path] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        files.append(skill_md)
    refs = skill_dir / "references"
    if refs.is_dir():
        files.extend(sorted(p for p in refs.rglob("*.md") if p.is_file()))
    return files


def scan_skill_citations(skill_dir: Path) -> list[dict]:
    """Every `[AST:]` / `[SRC:]` citation with a line, in file order."""
    found: list[dict] = []
    for md in skill_markdown_files(skill_dir):
        rel = md.relative_to(skill_dir).as_posix()
        lines = _read_lines(md) or []
        for number, text in enumerate(lines, start=1):
            for m in _SKILL_CITATION_RE.finditer(text):
                found.append(
                    {
                        "file": rel,
                        "line": number,
                        "column": m.start() + 1,
                        "citation": m.group(0),
                        "prefix": m.group(1),
                        "cited_file": m.group(2).strip(),
                        "cited_line": int(m.group(3)),
                    }
                )
    return found


def _extraction_method(entry: dict) -> str | None:
    """The entry's `extraction_method`, or None when it is not a string
    (a list or object there reads as an unknown method, never a crash)."""
    method = entry.get("extraction_method")
    return method if isinstance(method, str) else None


def check_skill_citations(
    prov: dict, skill_dir: Path
) -> tuple[list[dict], int, int]:
    """Compare each skill citation's prefix with the entry it cites.

    Returns (findings, citations_scanned, citations_matched): a citation is
    matched when its path and line name at least one provenance entry.
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    by_location: dict[tuple[str, int], list[dict]] = {}
    has_ast_entry = False
    # `ast-without-ast-grep` needs proof that no entry came from ast-grep:
    # every entry with a source line must carry a known method.
    methods_known = True
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        method = _extraction_method(entry)
        if method in AST_METHODS:
            has_ast_entry = True
        sf = entry.get("source_file")
        line = _coerce_line(entry.get("source_line"))
        if not isinstance(sf, str) or not sf.strip() or not isinstance(line, int):
            continue
        if method not in KNOWN_METHODS:
            methods_known = False
        by_location.setdefault((normalize_path(sf), line), []).append(entry)

    scanned = sorted(
        scan_skill_citations(skill_dir),
        key=lambda c: (c["file"], c["line"], c["column"]),
    )
    findings: list[dict] = []
    matched_count = 0
    for cit in scanned:
        prefix = cit["prefix"]
        other = "SRC" if prefix == "AST" else "AST"
        matched = by_location.get(
            (normalize_path(cit["cited_file"]), cit["cited_line"]), []
        )
        if matched:
            matched_count += 1
        implied = [(METHOD_PREFIX.get(_extraction_method(e)), e) for e in matched]
        agrees = any(p == prefix for p, _ in implied)
        mismatch = next((e for p, e in implied if p == other), None)
        reason = None
        export_name = None
        if not agrees and mismatch is not None:
            reason = CITATION_PREFIX_MISMATCH
            export_name = mismatch.get("export_name")
        elif prefix == "AST" and not has_ast_entry and methods_known:
            reason = CITATION_AST_WITHOUT_AST_GREP
            if matched:
                export_name = matched[0].get("export_name")
        if reason is None:
            continue
        item = {k: v for k, v in cit.items() if k != "column"}
        item.update(
            {
                "reason": reason,
                "expected_prefix": other,
                "export_name": export_name
                if isinstance(export_name, str) and export_name
                else None,
            }
        )
        findings.append(item)
    return findings, len(scanned), matched_count


# --------------------------------------------------------------------------
# Node kinds (--check-node-kinds)
# --------------------------------------------------------------------------


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here may be a repository SKF does not control: a bare-name
    lookup resolving into CWD would execute a planted shim (e.g.
    ast-grep.cmd). Such a resolution is treated as not-found. Explicit
    paths supplied by callers (containing a separator) are honored as-is.
    Keep the code identical to the sibling guards in
    skf-merge-ccc-exclusions.py, skf-detect-tools.py,
    skf-qmd-classify-collections.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py and skf-tessl-review.py
    (test/test-skf-verify-provenance-completeness.py pins it against
    skf-merge-ccc-exclusions.py).
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    if os.sep in command or (os.altsep and os.altsep in command):
        return resolved
    resolved_dir = os.path.dirname(resolved)
    if resolved_dir:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        if os.path.normcase(os.path.abspath(resolved_dir)) == cwd:
            return None
    return resolved


def ast_grep_language(source_file: object) -> str | None:
    """The ast-grep language for `source_file`'s extension, or None."""
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    ext = posixpath.splitext(normalize_path(source_file))[1].lower()
    return AST_GREP_LANGUAGES.get(ext)


def ast_grep_judges_kind(exe: str, language: str, kind: str, folder: str) -> str:
    """Ask ast-grep whether `kind` is a node kind of `language`.

    Runs one rule that matches only `kind` over an empty stdin: ast-grep
    parses the rule before it reads input and rejects a kind the grammar
    does not have. Returns "valid", "invalid" (the rule was rejected and the
    error names an invalid kind), "timeout", or "unknown" (a failed spawn or
    any other error, which proves nothing about the kind). `folder` holds
    the minimal sgconfig.yml passed with `--config` and is the working
    folder, so no other sgconfig.yml is read. The rule is JSON, which YAML
    reads as a flow mapping.
    """
    rule = json.dumps(
        {"id": "skf-node-kind", "language": language, "rule": {"kind": kind}}
    )
    config = os.path.join(folder, "sgconfig.yml")
    try:
        result = subprocess.run(
            [exe, "scan", "--config", config, "--inline-rules", rule, "--stdin"],
            input="",
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=NODE_KIND_TIMEOUT_SEC,
            cwd=folder,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode == 0:
        return "valid"
    if "invalid kind" in (result.stderr or "").lower():
        return "invalid"
    return "unknown"


def _judge_kinds(
    exe: str, pairs: list[tuple[str, str]]
) -> tuple[str, dict[tuple[str, str], str]]:
    """Ask ast-grep about each (language, kind) pair, in order.

    Returns (node_kind_check, verdicts): each verdict is "valid", "invalid"
    or the reason the pair went unjudged. ast-grep is first asked about a
    kind no grammar has; unless it answers "invalid", its answers cannot be
    read and the check is "skipped-unrecognized-ast-grep" with no verdicts.
    After one timeout the remaining pairs are not asked. When the temporary
    folder cannot be made or written, the pairs not yet asked go unjudged.
    """
    verdicts: dict[tuple[str, str], str] = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="skf-node-kind-", ignore_cleanup_errors=True
        ) as folder:
            with open(
                os.path.join(folder, "sgconfig.yml"), "w", encoding="utf-8"
            ) as fh:
                fh.write(MINIMAL_SGCONFIG)
            calibration = ast_grep_judges_kind(
                exe, pairs[0][0], BOGUS_NODE_KIND, folder
            )
            if calibration != "invalid":
                return "skipped-unrecognized-ast-grep", {}
            timed_out = False
            for language, kind in pairs:
                if timed_out:
                    verdicts[(language, kind)] = UNCHECKED_TIMEOUT
                    continue
                verdict = ast_grep_judges_kind(exe, language, kind, folder)
                if verdict == "timeout":
                    timed_out = True
                    verdict = UNCHECKED_TIMEOUT
                elif verdict == "unknown":
                    verdict = UNCHECKED_AST_GREP_ERROR
                verdicts[(language, kind)] = verdict
    except OSError:
        for pair in pairs:
            verdicts.setdefault(pair, UNCHECKED_TEMP_FOLDER)
    return "checked", verdicts


def _node_kind_item(
    index: int, entry: dict, kind: str, language: str, reason: str
) -> dict:
    name = entry.get("export_name")
    return {
        "export_name": name if isinstance(name, str) and name else None,
        "entry_index": index,
        "source_file": entry.get("source_file"),
        "source_line": entry.get("source_line"),
        "ast_node_type": kind,
        "language": language,
        "reason": reason,
    }


def check_node_kinds(prov: dict) -> tuple[list[dict], list[dict], dict]:
    """Check each ast-grep entry's `ast_node_type` against ast-grep itself.

    Returns (findings, unchecked, summary fields). `ERROR` and a kind that
    is not kind-shaped are judged without ast-grep, whatever the binary
    lookup finds; every other kind is asked once per (language, kind).
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    findings: list[dict] = []
    unchecked: list[dict] = []
    pending: list[tuple[int, dict, str, str]] = []
    judged = 0
    skipped = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if _extraction_method(entry) not in AST_METHODS:
            continue
        kind = entry.get("ast_node_type")
        if not isinstance(kind, str) or not kind.strip():
            continue
        language = ast_grep_language(entry.get("source_file"))
        if language is None:
            skipped += 1
            continue
        if kind == ERROR_NODE_KIND:
            reason = NODE_KIND_ERROR
        elif not NODE_KIND_SHAPE.fullmatch(kind):
            reason = NODE_KIND_INVALID
        else:
            pending.append((index, entry, language, kind))
            continue
        judged += 1
        findings.append(_node_kind_item(index, entry, kind, language, reason))

    check = "checked"
    if pending:
        exe = _resolve_outside_cwd("ast-grep")
        if exe is None:
            check = "skipped-no-ast-grep"
        else:
            pairs = sorted({(lang, kind) for _, _, lang, kind in pending})
            check, verdicts = _judge_kinds(exe, pairs)
            if check == "checked":
                for index, entry, language, kind in pending:
                    verdict = verdicts[(language, kind)]
                    item = _node_kind_item(index, entry, kind, language, verdict)
                    if verdict == "valid":
                        judged += 1
                    elif verdict == "invalid":
                        judged += 1
                        item["reason"] = NODE_KIND_INVALID
                        findings.append(item)
                    else:
                        unchecked.append(item)

    def order(item: dict) -> tuple:
        return (item["export_name"] or "", str(item["source_file"]),
                item["entry_index"])

    findings.sort(key=order)
    unchecked.sort(key=order)
    summary = {
        "node_kind_check": check,
        "node_kinds_checked": judged,
        "node_kind_check_skipped": skipped,
        "node_kind_check_errors": len(unchecked),
        "node_kind_findings_count": len(findings),
    }
    return findings, unchecked, summary


# --------------------------------------------------------------------------
# The recipe kind at a line (kind-at)
# --------------------------------------------------------------------------


def _is_recipe(doc: object) -> bool:
    """A recipe: a mapping with a string `id` and `language`, and a `rule`
    mapping that names its node `kind`."""
    if not isinstance(doc, dict):
        return False
    rule = doc.get("rule")
    return (
        isinstance(doc.get("id"), str)
        and isinstance(doc.get("language"), str)
        and isinstance(rule, dict)
        and isinstance(rule.get("kind"), str)
    )


def load_recipes(path: Path) -> list[dict]:
    """Every ast-grep recipe in `path`, first copy of each (id, language).

    A markdown file (`.md`) gives the recipes in its ```yaml fences; any
    other file is read as YAML: one recipe per document, a list of recipes,
    or a mapping whose `recipes` key holds that list. Raises ValueError when
    the file cannot be read, and ImportError without PyYAML.
    """
    import yaml  # only kind-at reads recipes; `uv run` installs it

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"failed to read recipes {path}: {exc}") from exc
    docs: list[object] = []
    if path.suffix.lower() in (".md", ".markdown"):
        for block in _MD_YAML_FENCE_RE.findall(text):
            try:
                docs.append(yaml.safe_load(block))
            except yaml.YAMLError:
                continue  # a template, not a recipe
    else:
        try:
            docs = list(yaml.safe_load_all(text))
        except yaml.YAMLError as exc:
            raise ValueError(f"malformed YAML in recipes {path}: {exc}") from exc
    candidates: list[object] = []
    for doc in docs:
        if isinstance(doc, dict) and isinstance(doc.get("recipes"), list):
            candidates.extend(doc["recipes"])
        elif isinstance(doc, list):
            candidates.extend(doc)
        else:
            candidates.append(doc)
    recipes: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for doc in candidates:
        if not _is_recipe(doc):
            continue
        key = (doc["id"], doc["language"].strip().lower())
        if key not in seen:
            seen.add(key)
            recipes.append(doc)
    return recipes


def recipe_runs(recipes: list[dict], language: str) -> list[dict]:
    """The recipes to run on a file of `language`, each with its `language`
    set to it: an id's own form for that language, else its form for the
    first language `RECIPE_LANGUAGE_FALLBACKS` lists (in recipe order)."""
    forms: dict[str, dict[str, dict]] = {}
    for recipe in recipes:
        lang = recipe["language"].strip().lower()
        forms.setdefault(recipe["id"], {}).setdefault(lang, recipe)
    runs: list[dict] = []
    for recipe_id, by_language in forms.items():
        for lang in (language, *RECIPE_LANGUAGE_FALLBACKS.get(language, ())):
            if lang in by_language:
                run = dict(by_language[lang], language=language)
                run["_rewritten"] = lang != language
                runs.append(run)
                break
    return runs


def _scan_recipe(
    exe: str, run: dict, source: bytes, folder: str
) -> tuple[str, list[tuple[int, str]] | str]:
    """Run one recipe over `source` on stdin.

    Returns ("ok", [($NAME's 1-based line, $NAME's text), ...]),
    ("not-applicable", []) for a recipe whose `language` was rewritten and
    whose kinds that grammar lacks, ("timeout", detail) or ("error",
    detail). The rule goes in a file as JSON (YAML reads it as a flow
    mapping), never on the command line, where an npm `.cmd` shim on
    Windows would hand its `|` and `^` to cmd.exe.
    """
    rule = {k: v for k, v in run.items() if not k.startswith("_")}
    rule_path = os.path.join(folder, "recipe.yml")
    with open(rule_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rule, ensure_ascii=False))
    config = os.path.join(folder, "sgconfig.yml")
    try:
        result = subprocess.run(
            [exe, "scan", "--config", config, "-r", rule_path, "--stdin",
             "--json=stream"],
            input=source,
            capture_output=True,
            timeout=KIND_AT_TIMEOUT_SEC,
            cwd=folder,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", f"no answer in {KIND_AT_TIMEOUT_SEC}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return "error", f"{type(exc).__name__}: {exc}"
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    if result.returncode != 0 and not stdout.strip():
        if run.get("_rewritten") and "invalid kind" in stderr.lower():
            return "not-applicable", []
        detail = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        return "error", f"exit {result.returncode}: {detail}"
    found: list[tuple[int, str]] = []
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        try:
            match = json.loads(raw)
        except ValueError:
            return "error", "output is not JSON lines"
        single = (match.get("metaVariables") or {}).get("single") or {}
        name = single.get("NAME")
        if not isinstance(name, dict):
            continue
        start = (name.get("range") or {}).get("start") or {}
        line = start.get("line")
        if isinstance(line, int) and not isinstance(line, bool):
            found.append((line + 1, str(name.get("text") or "")))
    return "ok", found


def _unquote(name: str) -> str:
    """A string name without its quotes (`"a-b"` -> `a-b`)."""
    if len(name) >= 2 and name[0] == name[-1] and name[0] in "'\"":
        return name[1:-1]
    return name


def kinds_at(
    source: bytes,
    language: str | None,
    targets: list[tuple[int, str | None]],
    recipes: list[dict],
) -> list[dict]:
    """The node kind the recipes give each (line, export name or None)
    target of one file, running each recipe once.

    Each result: {line, name, status, kind, matches[], errors[]}. A match is
    a recipe whose `$NAME` is on the target line (and, with a name, is that
    name's last segment). `status` is `found` (one kind among the matches),
    `ambiguous` (several), `no-match`, `incomplete` (a recipe run failed, so
    no kind is given), `skipped-no-language`, `skipped-no-recipes` or
    `skipped-no-ast-grep`.
    """
    results = [
        {"line": line, "name": name, "status": "", "kind": None,
         "matches": [], "errors": []}
        for line, name in targets
    ]

    def skip(status: str) -> list[dict]:
        for result in results:
            result["status"] = status
        return results

    if language is None:
        return skip("skipped-no-language")
    runs = recipe_runs(recipes, language)
    if not runs:
        return skip("skipped-no-recipes")
    exe = _resolve_outside_cwd("ast-grep")
    if exe is None:
        return skip("skipped-no-ast-grep")

    matched: list[tuple[dict, list[tuple[int, str]]]] = []
    errors: list[dict] = []
    try:
        with tempfile.TemporaryDirectory(
            prefix="skf-kind-at-", ignore_cleanup_errors=True
        ) as folder:
            with open(
                os.path.join(folder, "sgconfig.yml"), "w", encoding="utf-8"
            ) as fh:
                fh.write(MINIMAL_SGCONFIG)
            timed_out = False
            for run in runs:
                if timed_out:
                    errors.append({"recipe": run["id"], "language": language,
                                   "reason": UNCHECKED_TIMEOUT, "detail": ""})
                    continue
                outcome, found = _scan_recipe(exe, run, source, folder)
                if outcome == "ok":
                    matched.append((run, found))
                elif outcome in ("timeout", "error"):
                    timed_out = outcome == "timeout"
                    errors.append({
                        "recipe": run["id"],
                        "language": language,
                        "reason": UNCHECKED_TIMEOUT if timed_out
                        else UNCHECKED_AST_GREP_ERROR,
                        "detail": found,
                    })
    except OSError as exc:
        errors.append({"recipe": None, "language": language,
                       "reason": UNCHECKED_TEMP_FOLDER, "detail": str(exc)})

    for result in results:
        wanted = definition_name(result["name"]) if result["name"] else None
        for run, found in matched:
            for line, text in found:
                if line != result["line"]:
                    continue
                if wanted is not None and _unquote(text) != wanted:
                    continue
                item = {"recipe": run["id"], "kind": run["rule"]["kind"],
                        "name": text}
                if item not in result["matches"]:
                    result["matches"].append(item)
        result["matches"].sort(key=lambda m: (m["recipe"], m["name"]))
        result["errors"] = [dict(e) for e in errors]
        kinds = sorted({m["kind"] for m in result["matches"]})
        if errors:
            result["status"] = "incomplete"
        elif not kinds:
            result["status"] = "no-match"
        elif len(kinds) == 1:
            result["status"] = "found"
            result["kind"] = kinds[0]
        else:
            result["status"] = "ambiguous"
    return results


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def resolve_source_root(prov: dict, override: str | None) -> Path | None:
    """Pick the source root for citation resolution.

    `--source-root` override wins; otherwise the provenance map's top-level
    `source_root`. Returns None when neither resolves to an on-disk dir.
    """
    candidate: str | None = None
    if override:
        candidate = override
    else:
        sr = prov.get("source_root")
        if isinstance(sr, str) and sr:
            candidate = sr
    if not candidate:
        return None
    root = Path(candidate)
    return root if root.is_dir() else None


def verify(
    metadata: dict,
    prov: dict,
    source_root: Path | None,
    skill_dir: Path | None = None,
    check_kinds: bool = False,
) -> dict:
    """Compute the completeness / orphan / stale / citation / node-kind
    report."""
    reexport_map = extract_reexport_map(prov)

    documented = extract_export_names(metadata)
    documented_canon = {canon(n, reexport_map) for n in documented}

    raw_entry_names = provenance_entry_names(prov)
    entry_canon = {canon(n, reexport_map) for n in raw_entry_names}

    # A reference app documents no exports (`exports[]` is empty by design)
    # while its entries are per-citation, so the two sets measure different
    # surfaces and their difference means nothing.
    set_diff_applies = not is_reference_app(metadata)
    if set_diff_applies:
        missing = sorted(documented_canon - entry_canon)
        orphaned = sorted(entry_canon - documented_canon)
    else:
        missing, orphaned = [], []

    stale: list[dict] = []
    citations_checked = 0
    line_check_skipped = 0
    line_check_folded = 0
    if source_root is not None:
        cache = _SourceCache()
        entries = prov.get("entries")
        if isinstance(entries, list):
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                name = entry.get("export_name")
                if not isinstance(name, str) or not name:
                    continue
                sf = entry.get("source_file")
                sl = entry.get("source_line")
                line = _coerce_line(sl)
                # Only count a resolvable (non-null) citation as "checked".
                if isinstance(sf, str) and sf.strip() and line is not None:
                    citations_checked += 1
                reason = check_citation(sf, sl, source_root)
                item = {
                    "export_name": name,
                    "entry_index": index,
                    "source_file": sf if isinstance(sf, str) else None,
                    "source_line": sl if isinstance(sl, int)
                    and not isinstance(sl, bool) else sl,
                }
                if reason is not None:
                    item["reason"] = reason
                    stale.append(item)
                    continue
                # The citation resolves (or is tolerated): check that the
                # line defines the export. A tolerated null or blank
                # citation has no line to check and is not counted.
                if (
                    not isinstance(sf, str)
                    or not sf.strip()
                    or not isinstance(line, int)
                ):
                    continue
                if not line_rule_applies(sf, entry.get("export_type")):
                    line_check_skipped += 1
                    continue
                # A bookkeeping variant the file never names is checked
                # against its base name (`folded_to`).
                matches, folded_to = _folded_matches(sf, name, source_root, cache)
                if matches is None:
                    line_check_skipped += 1
                    continue
                if folded_to is not None:
                    line_check_folded += 1
                defs, every = matches
                if line not in defs:
                    # An indented match the column-0 rule dropped joins
                    # the lines, so nobody auto-moves it; an @overload
                    # group gives its first line alone, the move target.
                    item["reason"] = STALE_LINE_NOT_DEFINITION
                    item["definition_lines"] = _missed_definition_lines(
                        sf, folded_to or name, source_root, cache, line, defs, every
                    )
                    if folded_to is not None:
                        item["folded_to"] = folded_to
                    stale.append(item)
        stale.sort(key=lambda s: (s["export_name"], s.get("source_file") or ""))

    citations: list[dict] = []
    skill_citations_scanned = 0
    skill_citations_matched = 0
    if skill_dir is not None:
        citations, skill_citations_scanned, skill_citations_matched = (
            check_skill_citations(prov, skill_dir)
        )

    node_kinds: list[dict] = []
    node_kinds_unchecked: list[dict] = []
    kind_summary: dict = {"node_kind_check": "not-requested"}
    if check_kinds:
        node_kinds, node_kinds_unchecked, kind_summary = check_node_kinds(prov)

    status = (
        "pass"
        if not (missing or orphaned or stale or citations or node_kinds)
        else "findings"
    )
    result: dict = {
        "status": status,
        "missing": missing,
        "orphaned": orphaned,
        "stale": stale,
        "citations": citations,
    }
    if check_kinds:
        result["node_kinds"] = node_kinds
        result["node_kinds_unchecked"] = node_kinds_unchecked
    result["summary"] = {
        "exports_checked": len(documented_canon),
        "entries_checked": len(raw_entry_names),
        "missing_count": len(missing),
        "orphaned_count": len(orphaned),
        "set_diff": "checked" if set_diff_applies else "not-applicable",
        "stale_count": len(stale),
        "citations_checked": citations_checked,
        "line_check_skipped": line_check_skipped,
        "line_check_folded": line_check_folded,
        "stale_check": "checked"
        if source_root is not None
        else "skipped-no-source-root",
        "skill_citations_scanned": skill_citations_scanned,
        "skill_citations_matched": skill_citations_matched,
        "citation_findings_count": len(citations),
        "citation_check": "checked"
        if skill_dir is not None
        else "skipped-no-skill-dir",
        **kind_summary,
    }
    return result


# --------------------------------------------------------------------------
# Fixes with one answer (fix)
# --------------------------------------------------------------------------


def manual_interiors(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of the interior of every [MANUAL] block, paired
    as skf-hash-content.py pairs them: an opening marker with the earliest
    following close marker of the same name. An unclosed marker is
    skipped."""
    closes = [
        (m.start(), m.group(1).strip()) for m in _MANUAL_CLOSE_RE.finditer(text)
    ]
    spans: list[tuple[int, int]] = []
    for om in _MANUAL_OPEN_RE.finditer(text):
        name = om.group(1).strip()
        close = min(
            (start for start, n in closes if start >= om.end() and n == name),
            default=None,
        )
        if close is not None:
            spans.append((om.end(), close))
    return spans


class _SkillFile:
    """One skill markdown file: its text, its [MANUAL] interiors and every
    citation in it, found line by line as `scan_skill_citations` finds them.
    Bytes that are not UTF-8 survive the round trip (surrogateescape)."""

    def __init__(self, skill_dir: Path, rel: str) -> None:
        self.rel = rel
        self.path = skill_dir / rel
        self.text = self.path.read_bytes().decode("utf-8", errors="surrogateescape")
        self.manual = manual_interiors(self.text)
        self.citations: list[dict] = []
        offset = 0
        for number, chunk in enumerate(_LINE_WITH_END_RE.findall(self.text), 1):
            content = chunk.rstrip("\r\n")
            for m in _SKILL_CITATION_RE.finditer(content):
                self.citations.append(
                    {
                        "line": number,
                        "start": offset + m.start(),
                        "end": offset + m.end(),
                        "match": m,
                        "text": m.group(0),
                        "prefix": m.group(1),
                        "cited_file": m.group(2).strip(),
                        "cited_line": int(m.group(3)),
                    }
                )
            offset += len(chunk)

    def in_manual(self, offset: int) -> bool:
        return any(start <= offset < end for start, end in self.manual)

    def fixed_text(self) -> str | None:
        """The text with every changed citation rewritten, or None when no
        citation changed."""
        edits = [
            (c["start"], c["end"], _rewritten_citation(c))
            for c in self.citations
            if c.get("new_prefix") or c.get("shift") or c.get("new_path")
        ]
        if not edits:
            return None
        text = self.text
        for start, end, new in sorted(edits, reverse=True):
            text = text[:start] + new + text[end:]
        return text


def _rewritten_citation(cit: dict) -> str:
    """A citation with its new prefix, its new path (a move across files) and
    its lines shifted: a range moves both ends by the same amount (`L10-12`
    to `L13-15`)."""
    m = cit["match"]
    base = m.start()
    subs: list[tuple[int, int, str]] = []
    if cit.get("new_prefix"):
        subs.append((m.start(1) - base, m.end(1) - base, cit["new_prefix"]))
    if cit.get("new_path"):
        raw = m.group(2)
        lead = raw[: len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        subs.append((m.start(2) - base, m.end(2) - base, lead + cit["new_path"] + trail))
    shift = cit.get("shift", 0)
    if shift:
        subs.append((m.start(3) - base, m.end(3) - base, str(int(m.group(3)) + shift)))
        if m.group(5) is not None:
            subs.append(
                (m.start(5) - base, m.end(5) - base, str(int(m.group(5)) + shift))
            )
    text = m.group(0)
    for start, end, new in sorted(subs, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def _dict_items(value: object) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _stale_entry_indices(entries: list, item: dict) -> list[int]:
    """The provenance entries a `stale[]` item names: the one at its
    `entry_index` when that entry still has the item's name, file and line,
    else every entry that has them."""
    name = item.get("export_name")
    source_file = item.get("source_file")
    line = _coerce_line(item.get("source_line"))

    def same(entry: object) -> bool:
        return (
            isinstance(entry, dict)
            and entry.get("export_name") == name
            and isinstance(source_file, str)
            and bool(source_file.strip())
            and entry.get("source_file") == source_file
            and isinstance(line, int)
            and _coerce_line(entry.get("source_line")) == line
        )

    index = item.get("entry_index")
    if (
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(entries)
        and same(entries[index])
    ):
        return [index]
    return [i for i, entry in enumerate(entries) if same(entry)]


def _recorded_lines(entries: list) -> dict[tuple[str, int], set[int]]:
    """The indices of the provenance entries recorded at each (normalized
    source file, source line)."""
    recorded: dict[tuple[str, int], set[int]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        sf = entry.get("source_file")
        line = _coerce_line(entry.get("source_line"))
        if isinstance(sf, str) and sf.strip() and isinstance(line, int):
            recorded.setdefault((normalize_path(sf), line), set()).add(index)
    return recorded


def _plan_line_moves(
    files: dict[str, "_SkillFile"],
    rels: list[str],
    planned: dict[tuple[str, int], tuple[set, list[str], bool]],
) -> tuple[list[tuple["_SkillFile", dict, list[str]]], list[dict]]:
    """The one-pass citation-line rule `fix` applies to every planned move.

    `planned` maps a (normalized path, line) a move leaves to (its targets,
    each (the new path as the input writes it, or None to keep the cited
    path; the new line), the export names there, whether another export
    claims that line). Each citation of either prefix whose normalized path
    and first line are a planned key takes its one target, read from the
    citation as it stands, before any move: so a citation moves at most
    once. It stays (`shared-line`) when another export claims its line or
    the moves there go to two targets, and inside a [MANUAL] block
    (`inside-manual-block`). Returns (the moves, each (file, citation,
    names), and the citations left)."""
    line_fixes: list[tuple[_SkillFile, dict, list[str]]] = []
    left: list[dict] = []
    for rel in rels:
        doc = files[rel]
        for cit in doc.citations:
            key = (normalize_path(cit["cited_file"]), cit["cited_line"])
            move = planned.get(key)
            if move is None:
                continue
            targets, names, claimed = move
            if claimed or len(targets) > 1:
                why = "shared-line"  # it may cite the other export
            elif doc.in_manual(cit["start"]):
                why = "inside-manual-block"
            else:
                (path, new), = targets
                cit["shift"] = new - cit["cited_line"]
                if path is not None and normalize_path(path) != key[0]:
                    cit["new_path"] = path.strip()
                line_fixes.append((doc, cit, names))
                continue
            left.append({
                "kind": FIX_CITATION_LINE,
                "file": rel,
                "line": cit["line"],
                "citation": cit["text"],
                "export_names": names,
                "why": why,
            })
    return line_fixes, left


def plan_fixes(
    verify_result: dict, prov: dict, skill_dir: Path, line_moves: bool = True
) -> dict:
    """Plan the fixes a `verify` result has one answer for.

    1. Citation prefixes: each `citations[]` item's citation, found by its
       file, line and text, takes `expected_prefix`.
    2. Source lines: each `line-not-definition` item with exactly one
       `definition_lines` value moves its entry's `source_line` there, and
       the citations of either prefix whose normalized path and first line
       are the entry's (as they stand after step 1, before any move) move
       with it, all in one pass, so a citation moves at most once. A
       citation of a line another entry also records in that file stays.

    A citation inside a [MANUAL] block never changes. Returns {applied,
    left_as_warn, markdown: {rel: new text}, provenance: the new map or
    None}; nothing is written.
    """
    rels = [
        p.relative_to(skill_dir).as_posix() for p in skill_markdown_files(skill_dir)
    ]
    files = {rel: _SkillFile(skill_dir, rel) for rel in rels}
    applied: list[dict] = []
    left: list[dict] = []
    prefix_fixes: list[tuple[dict, dict]] = []

    # 1. Citation prefixes.
    groups: dict[tuple[str, int, str, str], list[dict]] = {}
    for item in _dict_items(verify_result.get("citations")):
        key = (item.get("file"), item.get("line"), item.get("citation"),
               item.get("expected_prefix"))
        if (
            not isinstance(key[0], str)
            or not isinstance(key[1], int)
            or not isinstance(key[2], str)
            or key[3] not in ("AST", "SRC")
        ):
            left.append(dict(item, kind=FIX_CITATION_PREFIX, why="citation-not-found"))
            continue
        groups.setdefault(key, []).append(item)
    for (rel, line, text, expected), items in groups.items():
        doc = files.get(rel)
        found = [] if doc is None else [
            c for c in doc.citations if c["line"] == line and c["text"] == text
        ]
        if not found:
            for item in items:
                left.append(
                    dict(item, kind=FIX_CITATION_PREFIX, why="citation-not-found")
                )
            continue
        for cit in found:
            if doc.in_manual(cit["start"]):
                left.append(dict(items[0], kind=FIX_CITATION_PREFIX,
                                 why="inside-manual-block"))
            elif cit["prefix"] != expected:
                cit["new_prefix"] = expected
                prefix_fixes.append((doc, cit))

    # 2. Source lines: plan every move before making any.
    entries = prov.get("entries") if isinstance(prov.get("entries"), list) else []
    moves: dict[int, int] = {}
    for item in _dict_items(verify_result.get("stale")):
        defs = item.get("definition_lines")
        new = defs[0] if isinstance(defs, list) and len(defs) == 1 else None
        if item.get("reason") != STALE_LINE_NOT_DEFINITION:
            why = "needs-decision"
        elif not isinstance(defs, list) or not defs:
            why = "no-definition-line"
        elif len(defs) > 1:
            why = "several-definition-lines"
        elif not isinstance(new, int) or isinstance(new, bool) or new < 1:
            why = "needs-decision"
        elif not line_moves:
            why = "line-moves-skipped"
        else:
            indices = _stale_entry_indices(entries, item)
            if indices:
                for index in indices:
                    moves[index] = new
                continue
            why = "entry-not-found"
        left.append(dict(item, kind=FIX_SOURCE_LINE, why=why))

    recorded = _recorded_lines(entries)
    movers: dict[tuple[str, int], dict[int, int]] = {}
    for index, new in moves.items():
        entry = entries[index]
        key = (normalize_path(entry["source_file"]), _coerce_line(entry["source_line"]))
        movers.setdefault(key, {})[index] = new
    planned: dict[tuple[str, int], tuple[set, list[str], bool]] = {}
    for key, moving in movers.items():
        here = recorded.get(key, set()) | set(moving)
        names = sorted(
            {n for n in (entries[i].get("export_name") for i in here)
             if isinstance(n, str) and n}
        )
        # another entry recorded there: the citation may cite its export
        planned[key] = ({(None, new) for new in moving.values()}, names,
                        bool(here - set(moving)))
    line_fixes, moved_left = _plan_line_moves(files, rels, planned)
    left.extend(moved_left)

    for doc, cit in prefix_fixes:
        applied.append({
            "kind": FIX_CITATION_PREFIX,
            "file": doc.rel,
            "line": cit["line"],
            "citation": cit["text"],
            "fixed": _rewritten_citation(cit),
        })
    new_prov = None
    if moves:
        new_prov = copy.deepcopy(prov)
        for index in sorted(moves):
            entry = new_prov["entries"][index]
            applied.append({
                "kind": FIX_SOURCE_LINE,
                "entry_index": index,
                "export_name": entry.get("export_name"),
                "source_file": entry.get("source_file"),
                "from": _coerce_line(entry.get("source_line")),
                "to": moves[index],
            })
            entry["source_line"] = moves[index]
    for doc, cit, names in line_fixes:
        applied.append({
            "kind": FIX_CITATION_LINE,
            "file": doc.rel,
            "line": cit["line"],
            "citation": cit["text"],
            "fixed": _rewritten_citation(cit),
            "export_names": names,
        })

    markdown = {}
    for rel in rels:
        text = files[rel].fixed_text()
        if text is not None:
            markdown[rel] = text
    return {
        "applied": applied,
        "left_as_warn": left,
        "markdown": markdown,
        "provenance": new_prov,
    }


# --------------------------------------------------------------------------
# A run's moved exports (fix --moves)
# --------------------------------------------------------------------------


def _location(value: object) -> tuple[str, int] | None:
    """(file as written, line) of a `file:line` string, or None."""
    if not isinstance(value, str) or ":" not in value:
        return None
    path, _, rest = value.rpartition(":")
    line = _coerce_line(rest)
    if not path.strip() or not isinstance(line, int) or line < 1:
        return None
    return path.strip(), line


def _line_number(value: object) -> int | None:
    line = _coerce_line(value)
    return line if isinstance(line, int) and line >= 1 else None


def load_moves(doc: dict) -> tuple[list[dict], list[dict]]:
    """(moves, claims) of a change manifest or of gap-records' output.

    A move is {name, from: (path, line), to: (path as written, line)}; a
    claim is {name, at: (path, line)}, an export the input places at a line
    with its citation already written there. A manifest gives a move per
    `per_file[].exports_affected[]` MOVED_EXPORT, from its `old_file` (else
    the item's `file_path`) and `old_line` to the item's `file_path` and
    its `new_line`, and a claim per NEW_EXPORT and MODIFIED_EXPORT at the
    item's `file_path` and its `new_line`. Gap-records' output (`mode`
    `gap-driven`) gives a move per `verification[]` record that is `moved`
    and `in_map`, from its `provenance_citation` to its `new_location`, and
    a claim per located record: a `verified` one at its
    `provenance_citation`, a `moved` or `re-extracted` one at its
    `new_location`, but for a moved MOVED_EXPORT, whose citation is the one
    that moves there. A move that stays where it is moves nothing. Raises
    ValueError for any other JSON."""
    moves: list[dict] = []
    claims: list[dict] = []
    if isinstance(doc.get("per_file"), list):
        for item in _dict_items(doc["per_file"]):
            path = item.get("file_path")
            if not isinstance(path, str) or not path.strip():
                continue
            for change in _dict_items(item.get("exports_affected")):
                name = change.get("name")
                kind = change.get("change_type")
                new = _line_number(change.get("new_line"))
                if new is None:
                    continue
                if kind in ("NEW_EXPORT", "MODIFIED_EXPORT"):
                    claims.append({"name": name, "at": (path, new)})
                elif kind == "MOVED_EXPORT":
                    old_file = change.get("old_file")
                    old_path = old_file if isinstance(old_file, str) and old_file.strip() else path
                    old = _line_number(change.get("old_line"))
                    if old is not None:
                        moves.append({"name": name, "from": (old_path, old), "to": (path, new)})
    elif doc.get("mode") == "gap-driven" and isinstance(doc.get("verification"), list):
        for record in _dict_items(doc["verification"]):
            name = record.get("export_name")
            outcome = record.get("verification")
            if outcome == "moved" and record.get("in_map") is True:
                old = _location(record.get("provenance_citation"))
                new = _location(record.get("new_location"))
                if old is not None and new is not None:
                    moves.append({"name": name, "from": old, "to": new})
                if record.get("gap_category") == "MOVED_EXPORT":
                    continue  # its new line is no claim: its citation moves there
            at = record.get("provenance_citation") if outcome == "verified" else (
                record.get("new_location") if outcome in ("moved", "re-extracted") else None)
            where = _location(at)
            if where is not None:
                claims.append({"name": name, "at": where})
    else:
        raise ValueError(
            "--moves is neither a change manifest (per_file[]) nor gap-records' "
            "output (mode gap-driven, verification[])"
        )
    moves = [
        m for m in moves
        if (normalize_path(m["from"][0]), m["from"][1])
        != (normalize_path(m["to"][0]), m["to"][1])
    ]
    return moves, claims


def plan_moves(moves_doc: dict, prov: dict, skill_dir: Path) -> dict:
    """Plan the citation moves of a run's moved exports (`load_moves`).

    Every move goes through `_plan_line_moves`, the one-pass rule `fix`
    gives its source-line moves: a citation of either prefix whose
    normalized path and first line are a move's old location takes the new
    line, and the new file on a move across files. Another export claims
    that location, so its citations stay (`shared-line`), when the map
    records an entry there under a name the moves from it do not hold, the
    moves from it go to two targets, or the input places an export there (a
    claim). A `MOVED_EXPORT`'s own new line is no claim, so a chain (6 to
    7, then 7 to 8) moves each citation once. The provenance map is read,
    never changed. Returns {applied, left_as_warn, markdown: {rel: new text},
    provenance: None}; nothing is written."""
    moves, claims = load_moves(moves_doc)
    rels = [
        p.relative_to(skill_dir).as_posix() for p in skill_markdown_files(skill_dir)
    ]
    files = {rel: _SkillFile(skill_dir, rel) for rel in rels}
    entries = prov.get("entries") if isinstance(prov.get("entries"), list) else []
    recorded = _recorded_lines(entries)
    claimed: dict[tuple[str, int], set[str]] = {}
    for claim in claims:
        key = (normalize_path(claim["at"][0]), claim["at"][1])
        claimed.setdefault(key, set()).add(claim["name"] if isinstance(claim["name"], str) else "")
    grouped: dict[tuple[str, int], list[dict]] = {}
    for move in moves:
        key = (normalize_path(move["from"][0]), move["from"][1])
        grouped.setdefault(key, []).append(move)
    planned: dict[tuple[str, int], tuple[set, list[str], bool]] = {}
    for key, here in grouped.items():
        movers = {m["name"] for m in here if isinstance(m["name"], str)}
        others = {
            n for n in (entries[i].get("export_name") for i in recorded.get(key, set()))
            if n not in movers
        } | claimed.get(key, set())
        names = sorted(n for n in movers | others if isinstance(n, str) and n)
        targets = {(m["to"][0], m["to"][1]) for m in here}
        if len({(normalize_path(p), n) for p, n in targets}) == 1:
            targets = {min(targets)}  # one target, however the input spells its path
        planned[key] = (targets, names, bool(others))
    line_fixes, left = _plan_line_moves(files, rels, planned)
    applied = [
        {
            "kind": FIX_CITATION_LINE,
            "file": doc.rel,
            "line": cit["line"],
            "citation": cit["text"],
            "fixed": _rewritten_citation(cit),
            "export_names": names,
        }
        for doc, cit, names in line_fixes
    ]
    markdown = {}
    for rel in rels:
        text = files[rel].fixed_text()
        if text is not None:
            markdown[rel] = text
    return {
        "applied": applied,
        "left_as_warn": left,
        "markdown": markdown,
        "provenance": None,
    }


def move_warnings(left: list[dict]) -> list[str]:
    """One `provenance:` warning per citation `fix --moves` left in place."""
    return [
        f"provenance: citation {item['citation']} at {item['file']}:{item['line']} "
        f"not moved ({item['why']}): {', '.join(item['export_names']) or 'no export named'}"
        for item in left
    ]


# --------------------------------------------------------------------------
# The Relabel Rule (relabel)
# --------------------------------------------------------------------------


# A label violation skf-render-metadata-stats.py reports on one entry.
_ENTRY_FIELD_RE = re.compile(r"^provenance\.entries\[(\d+)\]\.([A-Za-z_]+)$")
RELABEL_FIELDS = ("confidence", "signature_source", "ast_node_type", "extraction_method")
STATS_HELPER = "skf-render-metadata-stats.py"
# The methods part 1 sets an unknown or missing extraction_method to.
RELABEL_METHODS = ("ast-grep", "source-read")
# Why relabel left a label: the entry is not where the item says, or no kind
# was looked up (--no-kind-at, no source tree, a lookup that failed); any
# other `why` is the kind-at status.
RELABEL_ENTRY_NOT_FOUND = "entry-not-found"
RELABEL_KIND_AT_SKIPPED = "kind-at-skipped"
RELABEL_NO_SOURCE_ROOT = "no-source-root"
RELABEL_KIND_AT_FAILED = "kind-at-failed"


def _record_blocks(records: dict | None) -> dict[str, list[dict]]:
    """The records of a reextract-records.json, by normalized file path."""
    blocks: dict[str, list[dict]] = {}
    if not isinstance(records, dict):
        return blocks
    for block in _dict_items(records.get("files")):
        path = block.get("file_path")
        if isinstance(path, str) and path.strip():
            blocks.setdefault(normalize_path(path), []).extend(
                _dict_items(block.get("exports"))
            )
    return blocks


def entry_record(blocks: dict[str, list[dict]], entry: dict) -> dict | None:
    """This run's record of a provenance entry: the record of its
    `export_name` in the block of its `source_file`, the one at its
    `source_line` when several are, else None."""
    sf, name = entry.get("source_file"), entry.get("export_name")
    if not isinstance(sf, str) or not sf.strip() or not isinstance(name, str) or not name:
        return None
    named = [
        r for r in blocks.get(normalize_path(sf), [])
        if name in (r.get("name"), r.get("export_name"), r.get("local"))
    ]
    if len(named) > 1:
        line = _coerce_line(entry.get("source_line"))
        named = [r for r in named if (_location(r.get("location")) or ("", None))[1] == line]
    return named[0] if len(named) == 1 else None


def recipe_kind(recipes: list[dict], recipe_id: object, language: str | None) -> str | None:
    """The `rule.kind` of recipe `recipe_id`: its form for `language`, as
    `recipe_runs` picks it, else the kind all its forms share; None when
    there is no such recipe or its forms disagree."""
    if not isinstance(recipe_id, str) or not recipe_id:
        return None
    forms = [r for r in recipes if r["id"] == recipe_id]
    if not forms:
        return None
    if language is not None:
        runs = recipe_runs(forms, language)
        if runs:
            return runs[0]["rule"]["kind"]
    kinds = {r["rule"]["kind"] for r in forms}
    return kinds.pop() if len(kinds) == 1 else None


def plan_relabel(
    prov: dict,
    violations: list[dict],
    node_kinds: list[dict],
    recipes: list[dict],
    records: dict | None,
    source_root: Path | None,
    kind_at: bool = True,
    label_check=None,
) -> dict:
    """Apply relabel-rule.md to a copy of the map.

    Part 1: a `confidence`, `signature_source` or null `ast_node_type`
    violation takes the violation's `expected`; an `extraction_method` one
    takes the method of this run's record of the entry (`ast-grep` or
    `source-read`), else `source-read`, and the entry is then checked once
    more by `label_check` (skf-render-metadata-stats.py's
    `check_label_agreement`) and relabeled by what it reports. Part 2: an
    `ast_node_type` the label check wants `non-null`, and each `node_kinds[]`
    item, takes the kind of the recipe the entry's record names
    (`ast_recipe`), else the `kinds_at` kind at its current `source_line`
    when that is `found`. A node kind never changes `extraction_method`.
    Each item names its entry by index, confirmed by `export_name` (and a
    node kind by `source_file`). Returns {relabeled, left_as_warn,
    provenance: the new map or None}."""
    new = copy.deepcopy(prov)
    entries = new.get("entries") if isinstance(new.get("entries"), list) else []
    blocks = _record_blocks(records)
    relabeled: list[dict] = []
    left: list[dict] = []
    kinds_wanted: dict[int, None] = {}  # entry indices whose kind part 2 settles, in order

    def item_of(index: object, entry: dict | None, field: str) -> dict:
        entry = entry if isinstance(entry, dict) else {}
        return {"entry_index": index, "export_name": entry.get("export_name"),
                "source_file": entry.get("source_file"), "field": field}

    def set_field(index: int, field: str, value: object) -> None:
        entry = entries[index]
        old = entry.get(field)
        if old == value and field in entry:
            return
        entry[field] = value
        relabeled.append(dict(item_of(index, entry, field), **{"from": old, "to": value}))

    def apply_label(index: int, field: str, expected: object) -> None:
        if field == "ast_node_type":
            if expected is None:
                set_field(index, field, None)
            else:
                kinds_wanted.setdefault(index)
        elif field in ("confidence", "signature_source") and isinstance(expected, str):
            set_field(index, field, expected)

    def confirmed(index: object, name: object, source_file: object = None,
                  check_file: bool = False) -> bool:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(entries):
            return False
        entry = entries[index]
        if not isinstance(entry, dict) or entry.get("export_name") != name:
            return False
        return not check_file or entry.get("source_file") == source_file

    for violation in violations:
        m = _ENTRY_FIELD_RE.match(str(violation.get("field") or ""))
        if m is None or m.group(2) not in RELABEL_FIELDS:
            continue
        index, field = int(m.group(1)), m.group(2)
        if not confirmed(index, violation.get("export_name")):
            left.append(dict(item_of(index, None, field),
                             export_name=violation.get("export_name"), why=RELABEL_ENTRY_NOT_FOUND))
            continue
        if field != "extraction_method":
            apply_label(index, field, violation.get("expected"))
            continue
        record = entry_record(blocks, entries[index]) or {}
        method = record.get("extraction_method")
        set_field(index, field, method if method in RELABEL_METHODS else "source-read")
        for again in label_check({"entries": [entries[index]]}):
            m2 = _ENTRY_FIELD_RE.match(str(again.get("field") or ""))
            if m2 is not None and m2.group(2) in RELABEL_FIELDS[:3]:
                apply_label(index, m2.group(2), again.get("expected"))

    for item in node_kinds:
        index = item.get("entry_index")
        if not confirmed(index, item.get("export_name"), item.get("source_file"), True):
            left.append(dict(item_of(index, None, "ast_node_type"),
                             export_name=item.get("export_name"),
                             source_file=item.get("source_file"), why=RELABEL_ENTRY_NOT_FOUND))
            continue
        kinds_wanted.setdefault(index)

    lookups: dict[str, list[int]] = {}
    for index in kinds_wanted:
        entry = entries[index]
        language = ast_grep_language(entry.get("source_file"))
        record = entry_record(blocks, entry) or {}
        kind = recipe_kind(recipes, record.get("ast_recipe"), language)
        if kind is not None:
            set_field(index, "ast_node_type", kind)
        elif not kind_at:
            left.append(dict(item_of(index, entry, "ast_node_type"), why=RELABEL_KIND_AT_SKIPPED))
        elif source_root is None:
            left.append(dict(item_of(index, entry, "ast_node_type"), why=RELABEL_NO_SOURCE_ROOT))
        else:
            lookups.setdefault(normalize_path(entry.get("source_file") or ""), []).append(index)

    for path, wanted in lookups.items():
        indices = []
        for index in wanted:
            if isinstance(_coerce_line(entries[index].get("source_line")), int):
                indices.append(index)
            else:  # no line to look a kind up at
                left.append(dict(item_of(index, entries[index], "ast_node_type"),
                                 why=RELABEL_KIND_AT_FAILED))
        if not indices:
            continue
        try:
            if not path or posixpath.isabs(path) or path.split("/")[0] == ".." \
                    or re.match(r"[A-Za-z]:", path):
                raise ValueError(f"{path!r} is not a path below the source root")
            source = (source_root / path).read_bytes()
            targets = [(_coerce_line(entries[i].get("source_line")),
                        entries[i].get("export_name") or None) for i in indices]
            results = kinds_at(source, ast_grep_language(path), targets, recipes)
        except Exception:  # noqa: BLE001 - this file's lookups only, never a kind
            for index in indices:
                left.append(dict(item_of(index, entries[index], "ast_node_type"),
                                 why=RELABEL_KIND_AT_FAILED))
            continue
        for index, result in zip(indices, results):
            if result["status"] == "found":
                set_field(index, "ast_node_type", result["kind"])
            else:
                left.append(dict(item_of(index, entries[index], "ast_node_type"),
                                 why=result["status"]))

    return {
        "relabeled": relabeled,
        "left_as_warn": left,
        "provenance": new if relabeled else None,
    }


def _sibling_helper(filename: str) -> Path | None:
    """A helper installed beside this script (dev `src/shared/scripts/`
    and installed `_bmad/skf/shared/scripts/` alike), or None."""
    path = Path(__file__).resolve().parent / filename
    return path if path.is_file() else None


def _load_sibling_module(filename: str, module_name: str):
    """Import a sibling helper as a module. Raises ImportError."""
    path = _sibling_helper(filename)
    spec = (
        importlib.util.spec_from_file_location(module_name, path)
        if path is not None
        else None
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"{filename} not found beside {Path(__file__).name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_write(helper: Path, target: Path, data: bytes) -> None:
    """Write `data` to `target` through `skf-atomic-write.py write`.
    Raises OSError when the helper fails."""
    try:
        result = subprocess.run(
            [sys.executable, str(helper), "write", "--target", str(target)],
            input=data,
            capture_output=True,
            timeout=ATOMIC_WRITE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"atomic write of {target} failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise OSError(f"atomic write of {target} failed: {detail}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _skill_dir_error(skill_dir: Path) -> str | None:
    """Why `skill_dir` is not a skill package folder, or None."""
    if not skill_dir.exists():
        return f"skill dir not found: {skill_dir}"
    if not skill_dir.is_dir():
        return f"skill dir is not a directory: {skill_dir}"
    if not (skill_dir / "SKILL.md").is_file():
        return f"skill dir has no SKILL.md: {skill_dir}"
    return None


def _unexpected(what: str, exc: Exception, written: list[str] | None = None) -> int:
    """Report an unexpected failure on one stderr line; exit code 2. With
    `written` (fix), the line also names the files already written."""
    detail = " ".join(str(exc).split())
    note = ""
    if written is not None:
        note = f"; already written: {', '.join(written) if written else 'nothing'}"
    print(
        f"error: {what} failed: {type(exc).__name__}: {detail}{note}",
        file=sys.stderr,
    )
    return 2


def _emit(result: dict, output: str | None, written: list[str] | None = None) -> bool:
    """Write the JSON result to `output`, or to stdout when it is absent or
    `-`. False, after one stderr line (naming `written`, as `_unexpected`
    does), when it cannot be written."""
    out_text = json.dumps(result, indent=2) + "\n"
    to_file = bool(output) and output != "-"
    try:
        if to_file:
            Path(output).write_text(out_text, encoding="utf-8")
        else:
            sys.stdout.write(out_text)
    except OSError as exc:
        _unexpected(f"writing {output if to_file else 'stdout'}", exc, written)
        return False
    return True


def _cmd_verify(args: argparse.Namespace) -> int:
    meta_path = Path(args.metadata)
    prov_path = Path(args.provenance)
    if not meta_path.is_file():
        print(f"error: metadata not found: {meta_path}", file=sys.stderr)
        return 2
    if not prov_path.is_file():
        print(f"error: provenance map not found: {prov_path}", file=sys.stderr)
        return 2
    try:
        metadata = load_json_object(meta_path, "metadata")
        prov = load_json_object(prov_path, "provenance map")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    skill_dir: Path | None = None
    if args.skill_dir is not None:
        skill_dir = Path(args.skill_dir)
        problem = _skill_dir_error(skill_dir)
        if problem is not None:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    source_root = resolve_source_root(prov, args.source_root)
    if args.verbose:
        if source_root is None:
            print(
                "verbose: no source root resolved — skipping stale-citation "
                "check (completeness + orphan diffs only)",
                file=sys.stderr,
            )
        else:
            print(f"verbose: resolving citations under {source_root}", file=sys.stderr)

    try:
        result = verify(
            metadata, prov, source_root, skill_dir, args.check_node_kinds
        )
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as findings
        return _unexpected("verification", exc)

    if not _emit(result, args.output):
        return 2
    return 0 if result["status"] == "pass" else 1


def _cmd_definition_lines(args: argparse.Namespace) -> int:
    root = Path(args.source_root) if args.source_root else Path.cwd()
    if not root.is_dir():
        print(f"error: source root not found: {root}", file=sys.stderr)
        return 2
    try:
        report = definition_lines_report(
            args.file, args.name, root, args.line, args.export_type
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as an answer
        return _unexpected("definition lookup", exc)
    return 0 if _emit(report, args.output) else 2


def _cmd_classify_stale(args: argparse.Namespace) -> int:
    names_path, prov_path = Path(args.names), Path(args.provenance)
    inv_path = Path(args.inventory) if args.inventory is not None else None
    brief_path = Path(args.brief) if args.brief is not None else None
    root = Path(args.source_root)
    inputs = [("names", names_path), ("provenance map", prov_path)]
    if inv_path is not None:
        inputs.append(("inventory", inv_path))
    if brief_path is not None:
        inputs.append(("brief", brief_path))
    for label, path in inputs:
        if not path.is_file():
            print(f"error: {label} not found: {path}", file=sys.stderr)
            return 2
    if not root.is_dir():
        print(f"error: source root not found: {root}", file=sys.stderr)
        return 2
    try:
        text = names_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: failed to read names {names_path}: {exc}", file=sys.stderr)
        return 2
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"error: malformed JSON in names {names_path}: {exc}", file=sys.stderr)
        return 2
    try:
        names = stale_names(data)
        prov = load_json_object(prov_path, "provenance map")
        kinds = None if inv_path is None else inventory_kinds(
            load_json_object(inv_path, "inventory"), args.inventory
        )
        scope = None if brief_path is None else read_brief_scope(brief_path)
    except (ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        result = classify_stale(names, prov, root, kinds, scope)
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as an answer
        return _unexpected("stale-name classification", exc)
    return 0 if _emit(result, args.output) else 2


def _cmd_kind_at(args: argparse.Namespace) -> int:
    # a `source_file` as a provenance entry records it, as `verify` reads it
    path = Path(args.file.strip().replace("\\", "/"))
    if args.source_root and not path.is_absolute():
        path = Path(args.source_root) / path
    if not path.is_file():
        print(f"error: source file not found: {path}", file=sys.stderr)
        return 2
    recipes_path = Path(args.recipes)
    if not recipes_path.is_file():
        print(f"error: recipes not found: {recipes_path}", file=sys.stderr)
        return 2
    try:
        recipes = load_recipes(recipes_path)
        source = path.read_bytes()
    except ImportError:
        print(
            "error: kind-at reads recipes with PyYAML: run the helper with "
            "`uv run`, which installs it",
            file=sys.stderr,
        )
        return 2
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not recipes:
        print(f"error: no ast-grep recipe in {recipes_path}", file=sys.stderr)
        return 2
    language = (
        args.language.strip().lower() if args.language
        else ast_grep_language(args.file)
    )
    try:
        (result,) = kinds_at(source, language, [(args.line, args.name)], recipes)
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as an answer
        return _unexpected("kind lookup", exc)
    report = {"file": args.file, "language": language, **result}
    if not _emit(report, args.output):
        return 2
    return 0 if report["status"] == "found" else 1


def _cmd_fix(args: argparse.Namespace) -> int:
    moving = args.moves is not None
    if moving and args.no_line_moves:
        print("error: --no-line-moves goes with --verify, not --moves", file=sys.stderr)
        return 2
    input_path = Path(args.moves if moving else args.verify)
    input_label = "moves file" if moving else "verify result"
    prov_path = Path(args.provenance)
    skill_dir = Path(args.skill_dir)
    for path, label in ((input_path, input_label), (prov_path, "provenance map")):
        if not path.is_file():
            print(f"error: {label} not found: {path}", file=sys.stderr)
            return 2
    problem = _skill_dir_error(skill_dir)
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    try:
        verify_result = load_json_object(input_path, input_label)
        prov = load_json_object(prov_path, "provenance map")
        if moving:
            load_moves(verify_result)  # refuse any other JSON before planning
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not moving and not all(
        isinstance(verify_result.get(key), list) for key in ("stale", "citations")
    ):
        print(
            f"error: {input_path} is not a verify result (no stale[] and "
            f"citations[])",
            file=sys.stderr,
        )
        return 2

    inventory: list[dict] | None = None
    hash_content = None
    if args.manual_inventory is not None:
        try:
            hash_content = _load_sibling_module(
                HASH_CONTENT_HELPER, "skf_hash_content"
            )
            inventory = hash_content.load_inventory_blocks(Path(args.manual_inventory))
        except (ImportError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        plan = (
            plan_moves(verify_result, prov, skill_dir) if moving
            else plan_fixes(verify_result, prov, skill_dir, not args.no_line_moves)
        )
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as a fix
        return _unexpected("fix", exc)

    changes: list[tuple[Path, bytes]] = [
        (skill_dir / rel, text.encode("utf-8", errors="surrogateescape"))
        for rel, text in sorted(plan["markdown"].items())
    ]
    if plan["provenance"] is not None:
        text = json.dumps(plan["provenance"], indent=2, ensure_ascii=False) + "\n"
        changes.append((prov_path, text.encode("utf-8")))
    written: list[str] = []
    if changes and not args.dry_run:
        helper = _sibling_helper(ATOMIC_WRITE_HELPER)
        if helper is None:
            print(
                f"error: {ATOMIC_WRITE_HELPER} not found beside "
                f"{Path(__file__).name}; nothing written",
                file=sys.stderr,
            )
            return 2
        for target, data in changes:
            try:
                atomic_write(helper, target, data)
            except OSError as exc:
                print(
                    f"error: {exc}; already written: "
                    f"{', '.join(written) if written else 'nothing'}",
                    file=sys.stderr,
                )
                return 2
            written.append(str(target))

    manual = None
    if hash_content is not None and inventory is not None and not args.dry_run:
        try:
            current = hash_content.find_manual_blocks(
                (skill_dir / "SKILL.md").read_bytes()
            )
            manual = hash_content.classify_manual_blocks(inventory, current)
        except Exception as exc:  # noqa: BLE001 - exit 2, never read as a WARN
            return _unexpected("the [MANUAL] re-check", exc, written)

    applied = plan["applied"]
    left = plan["left_as_warn"]
    result = {
        "applied": applied,
        "left_as_warn": left,
        "files_changed": [str(target) for target, _ in changes],
        "files_written": written,
        "dry_run": bool(args.dry_run),
        "manual_verify": manual,
        "summary": {
            "citation_prefixes_fixed": sum(
                1 for a in applied if a["kind"] == FIX_CITATION_PREFIX
            ),
            "source_lines_moved": sum(
                1 for a in applied if a["kind"] == FIX_SOURCE_LINE
            ),
            "citations_moved": sum(
                1 for a in applied if a["kind"] == FIX_CITATION_LINE
            ),
            "left_as_warn_count": len(left),
        },
    }
    if moving:
        result["warnings"] = move_warnings(left)
    if not _emit(result, args.output, written):
        return 2
    return 0 if not left and (manual is None or manual.get("ok")) else 1


def _cmd_relabel(args: argparse.Namespace) -> int:
    if args.violations is None and args.node_kinds is None:
        print("error: relabel needs --violations, --node-kinds or both", file=sys.stderr)
        return 2
    prov_path = Path(args.provenance)
    inputs = [(prov_path, "provenance map"), (Path(args.recipes), "recipes")]
    for value, label in ((args.violations, "violations"), (args.node_kinds, "node kinds"),
                         (args.records, "records")):
        if value is not None:
            inputs.append((Path(value), label))
    for path, label in inputs:
        if not path.is_file():
            print(f"error: {label} not found: {path}", file=sys.stderr)
            return 2
    violations: list[dict] = []
    node_kinds: list[dict] = []
    try:
        prov = load_json_object(prov_path, "provenance map")
        records = (
            load_json_object(Path(args.records), "records") if args.records else None
        )
        if args.violations is not None:
            stats = load_json_object(Path(args.violations), "violations")
            coherence = stats.get("coherence")
            if not isinstance(coherence, dict) or not isinstance(
                coherence.get("violations"), list
            ):
                raise ValueError(
                    f"{args.violations} is not a stats result (no coherence.violations[])"
                )
            violations = _dict_items(coherence["violations"])
        if args.node_kinds is not None:
            found = load_json_object(Path(args.node_kinds), "node kinds")
            if not isinstance(found.get("node_kinds"), list):
                raise ValueError(
                    f"{args.node_kinds} is not a verify result with node_kinds[] "
                    "(run verify with --check-node-kinds)"
                )
            node_kinds = _dict_items(found["node_kinds"])
        recipes = load_recipes(Path(args.recipes))
    except ImportError:
        print(
            "error: relabel reads recipes with PyYAML: run the helper with "
            "`uv run`, which installs it",
            file=sys.stderr,
        )
        return 2
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not recipes:
        print(f"error: no ast-grep recipe in {args.recipes}", file=sys.stderr)
        return 2
    label_check = None
    if any(
        (m := _ENTRY_FIELD_RE.match(str(v.get("field") or ""))) is not None
        and m.group(2) == "extraction_method"
        for v in violations
    ):
        try:
            label_check = _load_sibling_module(
                STATS_HELPER, "skf_render_metadata_stats"
            ).check_label_agreement
        except Exception as exc:  # noqa: BLE001 - nothing is written without it
            print(f"error: {STATS_HELPER} could not be loaded: {exc}; nothing written",
                  file=sys.stderr)
            return 2
    root = Path(args.source_root) if args.source_root else None
    try:
        plan = plan_relabel(
            prov, violations, node_kinds, recipes, records,
            root if root is not None and root.is_dir() else None,
            kind_at=not args.no_kind_at, label_check=label_check,
        )
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as a relabel
        return _unexpected("relabel", exc)
    written: list[str] = []
    if plan["provenance"] is not None:
        helper = _sibling_helper(ATOMIC_WRITE_HELPER)
        if helper is None:
            print(
                f"error: {ATOMIC_WRITE_HELPER} not found beside "
                f"{Path(__file__).name}; nothing written",
                file=sys.stderr,
            )
            return 2
        text = json.dumps(plan["provenance"], indent=2, ensure_ascii=False) + "\n"
        try:
            atomic_write(helper, prov_path, text.encode("utf-8"))
        except OSError as exc:
            print(f"error: {exc}; nothing written", file=sys.stderr)
            return 2
        written.append(str(prov_path))
    left = plan["left_as_warn"]
    result = {
        "relabeled": plan["relabeled"],
        "left_as_warn": left,
        "files_written": written,
        "summary": {"relabeled_count": len(plan["relabeled"]),
                    "left_as_warn_count": len(left)},
    }
    if not _emit(result, args.output, written):
        return 2
    return 0 if not left else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-verify-provenance-completeness",
        description=(
            "Cross-reference documented exports (metadata.json) against "
            "provenance-map entries: completeness, orphans, stale or "
            "non-definition file:line citations, (with --skill-dir) "
            "citation prefixes and (with --check-node-kinds) ast-grep node "
            "kinds, emitting findings as JSON; fix the findings with one "
            "answer; look up an export's definition lines, the stale names "
            "no cited file defines, or the recipe kind at a line."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "verify",
        help=(
            "emit provenance completeness / orphan / stale-citation / "
            "citation-prefix / node-kind findings"
        ),
    )
    p.add_argument("--metadata", required=True, help="path to metadata.json")
    p.add_argument(
        "--provenance", required=True, help="path to provenance-map.json"
    )
    p.add_argument(
        "--source-root",
        default=None,
        help=(
            "source tree root for citation resolution; overrides the "
            "provenance map's source_root. Stale check is skipped when no "
            "root resolves on disk."
        ),
    )
    p.add_argument(
        "--skill-dir",
        default=None,
        help=(
            "skill package folder holding a SKILL.md; scans it and "
            "references/**/*.md for [AST:]/[SRC:] citations and checks each "
            "prefix against the provenance entry it cites. Citation check is "
            "skipped when absent."
        ),
    )
    p.add_argument(
        "--check-node-kinds",
        action="store_true",
        help=(
            "ask the ast-grep CLI whether each ast-grep entry's ast_node_type "
            "is a node kind of its file's language; skipped when ast-grep is "
            "not found."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.add_argument(
        "--verbose", action="store_true", help="diagnostics to stderr"
    )
    p.set_defaults(func=_cmd_verify)

    p = sub.add_parser(
        "fix",
        help=(
            "apply the citation-prefix and source-line fixes a verify result "
            "has one answer for, or move the citations of a run's moved exports"
        ),
    )
    given = p.add_mutually_exclusive_group(required=True)
    given.add_argument("--verify", help="path to the JSON a verify run wrote")
    given.add_argument(
        "--moves",
        help=(
            "a change manifest (its MOVED_EXPORT items) or gap-records' output "
            "(its moved in-map records): move their citations only, never the map"
        ),
    )
    p.add_argument(
        "--provenance",
        required=True,
        help=(
            "path to the provenance-map.json that verify run read (with --moves: "
            "the map the update started from, read only)"
        ),
    )
    p.add_argument(
        "--skill-dir",
        required=True,
        help="skill package folder holding a SKILL.md and references/",
    )
    p.add_argument(
        "--manual-inventory",
        default=None,
        help=(
            "a [MANUAL] inventory of SKILL.md (skf-hash-content.py "
            "manual-inventory); checked again after the writes"
        ),
    )
    p.add_argument(
        "--no-line-moves",
        action="store_true",
        help="with --verify: fix citation prefixes only; list every source-line finding",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="plan the fixes, write nothing"
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.set_defaults(func=_cmd_fix)

    p = sub.add_parser(
        "definition-lines",
        help="emit the lines of a source file that define an export",
    )
    p.add_argument(
        "--file", required=True, help="source file, relative to --source-root"
    )
    p.add_argument("--name", required=True, help="the entry's export_name")
    p.add_argument(
        "--source-root",
        default=None,
        help="source tree root (default: the current folder)",
    )
    p.add_argument(
        "--line",
        type=int,
        default=None,
        help="the recorded source_line: report whether it defines the export",
    )
    p.add_argument(
        "--export-type",
        default=None,
        help="the entry's export_type (module and package have no line)",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.set_defaults(func=_cmd_definition_lines)

    p = sub.add_parser(
        "classify-stale",
        help=(
            "decide which stale names are fabricated signatures (no cited "
            "file defines them) and where the source declares the others"
        ),
    )
    p.add_argument(
        "--names",
        required=True,
        help=(
            "reconcile-coverage.py's result (its `stale` names) or a JSON "
            "array of names"
        ),
    )
    p.add_argument(
        "--provenance", required=True, help="path to provenance-map.json"
    )
    p.add_argument(
        "--source-root",
        required=True,
        help="source tree root the entries' source_file paths are under",
    )
    p.add_argument(
        "--inventory",
        default=None,
        help=(
            "validate-inventory.py's documented inventory: a name it gives a "
            "function, hook, class, interface, enum or type kind takes no "
            "line 1 from a module so named, unless a provenance map entry of "
            "the name is a module or package one or the module is a TS/JS "
            "file that is itself the export"
        ),
    )
    p.add_argument(
        "--brief",
        default=None,
        help=(
            "the skill brief: in the walk of the names that are not "
            "fabricated, a file a scope.exclude glob matches or, when the "
            "brief has scope.include globs, none of them matches declares a "
            "name only when no walked file in scope does"
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.set_defaults(func=_cmd_classify_stale)

    p = sub.add_parser(
        "kind-at",
        help="emit the node kind of the recipe that matches a source line",
    )
    p.add_argument(
        "--file",
        required=True,
        help="source file, relative to --source-root when that is given",
    )
    p.add_argument(
        "--line", type=int, required=True, help="the line $NAME must be on"
    )
    p.add_argument(
        "--recipes",
        required=True,
        help=(
            "the recipes: a markdown file (its ```yaml fences, such as "
            "extraction-patterns.md) or a YAML file"
        ),
    )
    p.add_argument(
        "--language",
        default=None,
        help="ast-grep language (default: from the file's extension)",
    )
    p.add_argument(
        "--name",
        default=None,
        help="export name: count only matches whose $NAME is its last segment",
    )
    p.add_argument("--source-root", default=None, help="source tree root")
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.set_defaults(func=_cmd_kind_at)

    p = sub.add_parser(
        "relabel",
        help=(
            "apply the Relabel Rule to the label violations of a stats result "
            "and the node kinds of a verify result, and write the map"
        ),
    )
    p.add_argument(
        "--provenance", required=True, help="path to provenance-map.json, rewritten"
    )
    p.add_argument(
        "--violations",
        default=None,
        help=(
            "skf-render-metadata-stats.py's JSON: its coherence.violations[] on "
            "provenance.entries[<i>].*"
        ),
    )
    p.add_argument(
        "--node-kinds",
        default=None,
        help="a verify result's JSON (with --check-node-kinds): its node_kinds[]",
    )
    p.add_argument(
        "--recipes",
        required=True,
        help=(
            "the recipes: a markdown file (its ```yaml fences, such as "
            "extraction-patterns.md) or a YAML file"
        ),
    )
    p.add_argument(
        "--records",
        default=None,
        help=(
            "this run's reextract-records.json: the record of an entry names "
            "its ast_recipe and extraction_method"
        ),
    )
    p.add_argument(
        "--source-root",
        default=None,
        help="the source tree kind-at reads; without it no kind is looked up",
    )
    p.add_argument(
        "--no-kind-at",
        action="store_true",
        help="look no kind up in the tree (the drift override): list it as a WARN",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.set_defaults(func=_cmd_relabel)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
