#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Verify Provenance Completeness — deterministic Check D for update-skill.

update-skill's Check D (Provenance Completeness, now in write.md §6)
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

Four more subcommands act on the same rules: `fix` applies the citation
prefix and source-line fixes a `verify` result has one answer for,
`definition-lines` gives the lines that define one export,
`classify-stale` decides which stale names are fabricated signatures, and
`kind-at` gives the node kind of the recipe that matches a source line.

An LLM set-diff can silently pass a dropped or orphaned entry, and eyeballing
whether a cited line still exists is not something the model can do reliably.
Both inputs are machine-readable — `metadata.json` (`exports[]`, a list of
export-name strings) and `provenance-map.json` (`entries[]` with
`export_name` / `source_file` / `source_line`, plus an optional
`reexport_map` for stack-skill barrel renames) are written by
`write.md` §2 and §3. This script diffs the two sets and re-checks the
citations exactly, so Check D consumes JSON rather than computing it.

Timing: update-skill runs it **post-write**, in write.md §6, after
`metadata.json` (§2) and `provenance-map.json` (§3) are on disk.
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
name (`App.update`) it is the last segment. The rules follow the
`source_file` extension:

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
    extraction could not trace is cited at its star import).
  - TS/JS (`.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`): a
    `function` (or `function*`), `class`, `interface`, `type`, `enum`,
    `namespace`, `const`, `let` or `var` declaration of NAME, with any of
    `export`, `default`, `async`, `declare`, `abstract` and decorators
    (`@name`, `@a.b`, `@name(...)`, before `export` or between `export`
    and `class`; a name inside a decorator's arguments is not declared);
    a later declarator of a `const`, `let` or `var` list
    (`export const a = 1, NAME = 2;`, or `export const a = 1,` then
    `  NAME = 2;` as Prettier writes it: see Declarator lists below); NAME
    on the line right after a line that ends in its declaration keyword
    (`export function`, `export interface`, `export const` and so on),
    which is the line cited;
    `export import NAME =`; `export * as NAME from` (NAME may be quoted);
    `export default NAME`;
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
a name), up to a top-level `;`, and a destructuring pattern declares
nothing. The list goes on to the next line when a line ends inside a
bracket, after a top-level comma or after an operator waiting for its
operand, or when the next line starts with an operator (a member chain or
a ternary broken over lines), so a declarator on a line of its own
counts. A `<` where an expression begins (JSX, a type assertion, a generic
arrow function's type parameters) is not followed: no later declarator of
the list counts after it.

Indentation: for a dotted name every match counts. For an undotted name,
matches at any indentation count, but when the file has a column-0 match
the indented ones are dropped, so a local shadow never outranks the
module-level definition. A line inside a multi-line import, export list
or `module.exports` object takes the column of the line its statement
starts on, and so do the name line of a declaration split after its
keyword and a later declarator on a line of its own. When the recorded
line is itself an indented match that this rule dropped (a method
recorded under an undotted name beside a module-level function of the
same name), the finding lists the recorded line too, so it carries
several lines and no caller auto-moves it.

Entries in other files, and entries whose `export_type` is `module` or
`package` (case-insensitive; neither has a definition line), are skipped
and counted in `summary.line_check_skipped`. A `line-not-definition` item
lists every defining line in the file in `definition_lines`. An empty list
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
           "definition_lines": [<int>, ...]},   # line-not-definition only
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

    `fix` handles no `missing`, `orphaned` or `node_kinds` finding: read
    those from the verify result. Run `verify` again after it.

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
        "line_is_definition": <bool> | null        # --line, checked only
      }

    With `--line`, a recorded line that is an indented match the column-0
    rule dropped joins `definition_lines`, as in `verify`.

  classify-stale --names <coverage.json> --provenance <provenance-map.json>
                 --source-root <path> [-o <out.json>]

    test-skill's fabricated-signature test, for each stale name (a
    documented name the enumerated source surface lacks): the
    definition-lines rules above, run for every provenance entry whose raw
    `export_name` is the name, at its `source_file` and `source_line`, with
    its `export_type`. `--names` holds reconcile-coverage.py's result (its
    `stale` names) or a JSON array of names.

    Emit JSON, one item per name, in the order given (a repeated name once):
      [
        {"name": "<as given>",
         "fabricated": <bool>,
         "source": "<source_file>:<source_line>" | "<source_file>" | null,
         "reason": "not-defined" | "defined" | "unchecked" | "no-entry",
         "entries": [{"source_file": "<as recorded>",
                      "source_line": <as recorded>,
                      "line_check": "checked" | "file-missing"
                                    | "skipped-export-type"
                                    | "skipped-language" | "unreadable"
                                    | "no-file",
                      "definition_lines": [<int>, ...] | null}, ...]},
        ...
      ]

    `fabricated` is true, with reason `not-defined`, when the name has an
    entry and every entry's `line_check` is `file-missing`, or `checked`
    with an empty `definition_lines`: the export is in neither the surface
    nor the cited file. Otherwise the reason is `defined` (a cited file
    defines the name), `unchecked` (no rule could check a cited file, and
    none defines it) or `no-entry` (the map has no entry for the name).
    An entry with no `source_file` (update-skill writes one for an
    `unknown` NEW_EXPORT) cites no file to check: its `line_check` is
    `no-file`, which, like a skipped or unreadable check, neither proves
    the name fabricated nor shows it defined, so the name is `unchecked`
    unless another entry defines it. `source` is the citation of the first
    entry with a `source_file` (the file alone when its line is not a
    number), null when no entry has one.

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
  uv run skf-verify-provenance-completeness.py definition-lines \\
      --source-root {source_root} --file src/api.py --name search --line 26
  uv run skf-verify-provenance-completeness.py classify-stale \\
      --names {run_dir}/coverage.json \\
      --provenance {forge_version}/provenance-map.json \\
      --source-root {source_root} -o {run_dir}/stale.json
  uv run skf-verify-provenance-completeness.py kind-at \\
      --source-root {source_root} --file src/api.ts --line 12 --name Store \\
      --recipes {extractionPatternsData}

Exit codes:
  verify
    0  verification ran and found nothing (status "pass")
    1  verification ran and found missing / orphaned / stale entries,
       citation findings or node-kind findings (status "findings");
       advisory: the caller decides how to surface it
  fix
    0  nothing left as a WARN (and manual_verify ok when it ran)
    1  something left as a WARN, or manual_verify not ok
  definition-lines
    0  the rules answered (whatever `line_check` says)
  classify-stale
    0  every name was classified (whatever `fabricated` says)
  kind-at
    0  status "found"
    1  any other status
  2  error, for every subcommand (an input file or folder not found,
     --skill-dir without a SKILL.md, malformed JSON or YAML, a verify
     result without stale[] and citations[], --names without a list of
     names, no recipe in --recipes, no PyYAML for kind-at, an atomic
     write that failed, an -o file that cannot be written, or any
     unexpected failure, such as an unreadable
     file; once fix has started writing, stderr names the files already
     written); one line on stderr and no JSON
"""

from __future__ import annotations

import argparse
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
# A `const`, `let` or `var` statement: its declarator list.
_JS_VAR_DECL_RE = re.compile(
    rf"^\s*{_JS_MODIFIERS}(?:const|let|var)\s+(?!enum(?![\w$]))(.*)$"
)
# A declaration whose name is on the next line: the line ends in its keyword.
_JS_SPLIT_DECL_RE = re.compile(
    rf"^\s*{_JS_MODIFIERS}(?P<kind>function(?:\s*\*)?|class|interface|type"
    r"|enum|namespace|let|var|const(?:\s+enum)?)$"
)
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


def _read_lines(path: Path) -> list[str] | None:
    """Read a text file as lines numbered like `check_citation` counts them
    (universal newlines; a UTF-8 BOM is dropped so it never hides line 1).
    None when the file cannot be read."""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return [ln.rstrip("\n") for ln in fh]
    except OSError:
        return None


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
    """Source lines, Python statement starts and TS/JS comment-free lines,
    read once per file, and TS/JS declarator lists, split once per line
    (the split does not depend on the export looked up)."""

    def __init__(self) -> None:
        self._lines: dict[Path, list[str] | None] = {}
        self._starts: dict[Path, set[int] | None] = {}
        self._js_code: dict[Path, list[str]] = {}
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

    def js_declarators(
        self, text: str, opened: str = "", fresh: bool = True
    ) -> _DeclSplit:
        key = (text, opened, fresh)
        if key not in self._js_decl:
            self._js_decl[key] = _js_declarators(text, opened, fresh)
        return self._js_decl[key]


def _py_import_binds(items: str, name: str, from_import: bool) -> bool:
    """True when an import item list binds `name`."""
    items = items.split("#", 1)[0]
    for raw in items.replace("(", " ").replace(")", " ").replace("\\", " ").split(","):
        m = _PY_IMPORT_ITEM_RE.match(raw.strip())
        if not m:
            continue
        target, alias = m.group(1), m.group(2)
        if alias is not None:
            bound = alias
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
    lines: list[str], name: str, starts: set[int] | None
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    A line inside a parenthesized or backslash-continued import takes the
    column of the line the import statement starts on, and so does the name
    line of a `def \\` or `class \\` whose name is on the next line. A
    `from X import *` line counts only when no other line defines `name` (a
    re-export the extraction could not trace further is cited at its star
    import).
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
            if _py_import_binds(code, name, from_import):
                found.append((number, top))
            continue
        if starts is not None and number not in starts:
            continue
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
            star_imports.append((number, top))
            continue
        if from_import and rest.lstrip().startswith("(") and ")" not in rest:
            cont = ("paren", top, True)
        elif rest.rstrip().endswith("\\"):
            cont = ("backslash", top, from_import)
            rest = rest.rstrip()[:-1]
        if _py_import_binds(rest, name, from_import):
            found.append((number, top))
    return found or star_imports


def _js_export_item_binds(item: str, name: str) -> bool:
    """True when one `export { ... }` item exposes `name`: the name after
    `as`, else the item's own name, an identifier or a string."""
    m = _JS_EXPORT_ITEM_RE.match(item.strip())
    if not m:
        return False
    exposed = m.group(2) or m.group(1)
    if exposed[:1] in ("'", '"'):
        exposed = exposed[1:-1]
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


def _tsjs_definition_lines(
    lines: list[str],
    code_lines: list[str],
    name: str,
    dotted: bool,
    declarators: Callable[..., _DeclSplit] = _js_declarators,
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    `code_lines` are `lines` with comments removed (`_js_code_lines`), so a
    JSDoc line or a commented-out declaration never matches. A line inside
    a multi-line `export { ... }` list or `module.exports = { ... }` object
    takes the column of the line the statement starts on, and so do the
    name line of a declaration whose keyword ends the line above it and a
    later declarator on a line of its own. Class members count only for a
    dotted export name. `declarators` splits a declarator list
    (`_js_declarators`, or `_SourceCache.js_declarators`, which splits each
    line once for every export looked up).
    """
    esc = re.escape(name)
    end = r"(?![\w$])"
    statements = (
        re.compile(rf"^\s*{_JS_MODIFIERS}{_JS_KINDS}{esc}{end}"),
        re.compile(rf"^\s*export\s+import\s+(?:type\s+)?{esc}\s*=(?![=>])"),
        re.compile(
            rf"^\s*export\s+(?:type\s+)?\*\s+as\s+"
            rf"(?:{esc}\s+|([\"']){esc}\1\s*)from{end}"
        ),
        re.compile(rf"^\s*export\s+default\s+{esc}\s*;?\s*$"),
        re.compile(rf"^\s*(?:module\.)?exports\.{esc}\s*=(?![=>])"),
    )
    # One declarator of a `const` / `let` / `var` list: `NAME = v`,
    # `NAME: T = v`, `NAME!: T`, or a bare `NAME`. A destructuring pattern
    # starts with `{` or `[` and never matches.
    declarator = re.compile(rf"^\s*{esc}{end}\s*(?:!?\s*:|=|$)")
    leading_name = re.compile(rf"^\s*{esc}{end}")
    object_key = re.compile(
        rf"^\s*(?:(?:async|get|set)\s+|\*\s*)*(?:(['\"]){esc}\1|{esc}{end})"
        rf"\s*(?:[:(]|$)"
    )
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
    for number, (text, code) in enumerate(zip(lines, code_lines), start=1):
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
                if any(declarator.match(p) for p in pieces):
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
                hit = any(declarator.match(p) for p in pieces)
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
                hit = any(_js_export_item_binds(p, name) for p in pieces)
            else:
                hit = any(object_key.match(p) for p in pieces)
            if hit:
                found.append((number, top))
            continue
        top = _is_column_0(text)
        if any(p.match(code) for p in statements):
            found.append((number, top))
            continue
        m = _JS_VAR_DECL_RE.match(code)
        if m:
            carry, pieces = declarators(m.group(1))
            if carry is not None:
                decls.append((top, *carry))
            if any(declarator.match(p) for p in pieces):
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
            if any(_js_export_item_binds(p, name) for p in pieces):
                found.append((number, top))
            continue
        m = _JS_MODULE_EXPORTS_OBJECT_RE.match(code)
        if m:
            depth, pieces = _js_depth1_pieces(m.group(1), 1)
            if depth > 0:
                cont = ("object", top, depth)
            if any(object_key.match(p) for p in pieces):
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
) -> tuple[list[int], set[int]] | None:
    """(definition lines to report, every matching line) for an export.

    The first item applies the column-0 rule; the second keeps the indented
    matches that rule dropped. None when the file's extension has no
    definition rule or the file cannot be read.
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
    name = definition_name(export_name)
    if not name:
        return [], set()
    dotted = "." in export_name
    if suffix in PYTHON_EXTENSIONS:
        starts = cache.py_statement_starts(path, lines)
        found = _python_definition_lines(lines, name, starts)
    else:
        code_lines = cache.js_code_lines(path, lines)
        found = _tsjs_definition_lines(
            lines, code_lines, name, dotted, cache.js_declarators
        )
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


def definition_lines_report(
    source_file: str,
    export_name: str,
    source_root: Path,
    line: int | None = None,
    export_type: str | None = None,
) -> dict:
    """What `verify` would say about one entry's line (the definition-lines
    subcommand). Raises ValueError when the file exists but cannot be read.

    `line_check` is `file-missing`, `skipped-export-type` (a `module` or
    `package`, no definition line), `skipped-language` (no rule for the
    extension) or `checked`. With `line`, a recorded line that is an
    indented match the column-0 rule dropped joins `definition_lines`, as in
    `verify`, so the answer carries several lines.
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
    matches = _definition_matches(source_file, export_name, source_root)
    if matches is None:
        raise ValueError(f"failed to read source file {source_root / rel}")
    defs, every = matches
    if line is not None:
        report["line_is_definition"] = line in defs
        if line not in defs and line in every:
            defs = sorted(set(defs) | {line})
    report["definition_lines"] = defs
    return report


# --------------------------------------------------------------------------
# Stale names (classify-stale)
# --------------------------------------------------------------------------

STALE_NOT_DEFINED = "not-defined"
STALE_DEFINED = "defined"
STALE_UNCHECKED = "unchecked"
STALE_NO_ENTRY = "no-entry"


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
    """(line_check, definition_lines) of one provenance entry of a stale name."""
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
        )
    except ValueError:
        # the file exists but cannot be read: nothing proves it
        return "unreadable", None
    return report["line_check"], report["definition_lines"]


def classify_stale(names: list[str], prov: dict, source_root: Path) -> list[dict]:
    """The fabricated-signature test for each stale name: the definition-lines
    rules at every provenance entry whose raw `export_name` is the name. The
    classify-stale section of the module docstring gives each reason, what a
    `no-file` entry means and which entry gives `source`.
    """
    entries = [e for e in prov.get("entries") or [] if isinstance(e, dict)]
    results: list[dict] = []
    for name in names:
        mine = [e for e in entries if e.get("export_name") == name]
        checks: list[dict] = []
        for entry in mine:
            line_check, defs = _stale_line_check(entry, name, source_root)
            checks.append(
                {
                    "source_file": entry.get("source_file"),
                    "source_line": entry.get("source_line"),
                    "line_check": line_check,
                    "definition_lines": defs,
                }
            )
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
        results.append(
            {
                "name": name,
                "fabricated": reason == STALE_NOT_DEFINED,
                "source": source,
                "reason": reason,
                "entries": checks,
            }
        )
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
                matches = _definition_matches(sf, name, source_root, cache)
                if matches is None:
                    line_check_skipped += 1
                    continue
                defs, every = matches
                if line not in defs:
                    if line in every:
                        # The recorded line is an indented match the
                        # column-0 rule dropped: keep it, so the finding
                        # lists several lines and nobody auto-moves it.
                        defs = sorted(set(defs) | {line})
                    item["reason"] = STALE_LINE_NOT_DEFINITION
                    item["definition_lines"] = defs
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
            if c.get("new_prefix") or c.get("shift")
        ]
        if not edits:
            return None
        text = self.text
        for start, end, new in sorted(edits, reverse=True):
            text = text[:start] + new + text[end:]
        return text


def _rewritten_citation(cit: dict) -> str:
    """A citation with its new prefix and its lines shifted: a range moves
    both ends by the same amount (`L10-12` to `L13-15`)."""
    m = cit["match"]
    base = m.start()
    subs: list[tuple[int, int, str]] = []
    if cit.get("new_prefix"):
        subs.append((m.start(1) - base, m.end(1) - base, cit["new_prefix"]))
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

    recorded: dict[tuple[str, int], set[int]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        sf = entry.get("source_file")
        line = _coerce_line(entry.get("source_line"))
        if isinstance(sf, str) and sf.strip() and isinstance(line, int):
            recorded.setdefault((normalize_path(sf), line), set()).add(index)
    movers: dict[tuple[str, int], dict[int, int]] = {}
    for index, new in moves.items():
        entry = entries[index]
        key = (normalize_path(entry["source_file"]), _coerce_line(entry["source_line"]))
        movers.setdefault(key, {})[index] = new

    line_fixes: list[tuple[dict, dict, list[str]]] = []
    for rel in rels:
        doc = files[rel]
        for cit in doc.citations:
            key = (normalize_path(cit["cited_file"]), cit["cited_line"])
            moving = movers.get(key)
            if not moving:
                continue
            here = recorded.get(key, set()) | set(moving)
            names = sorted(
                {n for n in (entries[i].get("export_name") for i in here)
                 if isinstance(n, str) and n}
            )
            targets = set(moving.values())
            if here - set(moving) or len(targets) > 1:
                why = "shared-line"  # it may cite the other entry's export
            elif doc.in_manual(cit["start"]):
                why = "inside-manual-block"
            else:
                cit["shift"] = targets.pop() - cit["cited_line"]
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
    root = Path(args.source_root)
    for label, path in (("names", names_path), ("provenance map", prov_path)):
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
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        result = classify_stale(names, prov, root)
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
    verify_path = Path(args.verify)
    prov_path = Path(args.provenance)
    skill_dir = Path(args.skill_dir)
    for path, label in ((verify_path, "verify result"), (prov_path, "provenance map")):
        if not path.is_file():
            print(f"error: {label} not found: {path}", file=sys.stderr)
            return 2
    problem = _skill_dir_error(skill_dir)
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    try:
        verify_result = load_json_object(verify_path, "verify result")
        prov = load_json_object(prov_path, "provenance map")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not all(
        isinstance(verify_result.get(key), list) for key in ("stale", "citations")
    ):
        print(
            f"error: {verify_path} is not a verify result (no stale[] and "
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
        plan = plan_fixes(verify_result, prov, skill_dir, not args.no_line_moves)
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
    if not _emit(result, args.output, written):
        return 2
    return 0 if not left and (manual is None or manual.get("ok")) else 1


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
            "has one answer for"
        ),
    )
    p.add_argument(
        "--verify", required=True, help="path to the JSON a verify run wrote"
    )
    p.add_argument(
        "--provenance",
        required=True,
        help="path to the provenance-map.json that verify run read",
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
        help="fix citation prefixes only; list every source-line finding",
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
            "decide which stale names are fabricated signatures: no cited "
            "file defines them"
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
