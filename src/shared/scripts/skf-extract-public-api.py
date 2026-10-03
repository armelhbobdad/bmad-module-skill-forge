# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Extract Public API: one package's public surface, by parser or by recipe.

Three modes:

  --mode quick   (the default) A pure parser: takes one logical package (one
                 manifest, one or more entry-point files) and emits its
                 package name, version, description, public exports,
                 declared dependencies and (for Maven/Gradle) sub-modules.
                 The files come as a JSON payload on stdin, or by path with
                 --manifest-file and --entry-file, which the script reads
                 from disk (the caller stages them first: skf-github-fetch.py
                 raw fetches into a folder, or a local checkout), so a file's
                 text never passes through the model or a shell string.
                 --follow also reads the modules an `export *` chain passes
                 names on from, fetching them first with --repo. Multi-module
                 monorepos are caller-orchestrated: invoke once per module,
                 aggregate.
  --mode full    The ast-grep recipe runner (skf-create-skill and the
                 workflows that extract as it does): runs the recipes in
                 src/shared/data/ast-grep-recipes.yaml over a source tree
                 and emits every export with its exact file, line, name and
                 node kind, the export surface the package's entry points
                 declare, and the counts compile needs. See "Full mode" below.
  --mode entries The files quick mode reads for one package, found in the
                 repository's file listing with full mode's entry-point
                 rules, so no caller derives an entry file from a
                 distribution name or reads a manifest by eye. See "Entries
                 mode" below.

Quick mode
----------

Supported languages (the payload's `language`, or --language; first listed
is preferred):

  js, ts, javascript, typescript    package.json     index.{js,ts}, src/index.{js,ts}
  python                            pyproject.toml   __init__.py / setup.py / setup.cfg
  rust                              Cargo.toml       src/lib.rs
  go                                go.mod           top-level *.go
  java                              pom.xml          src/main/java/**/*.java
  kotlin                            build.gradle*    src/main/kotlin/**/*.kt
  swift                             Package.swift    Sources/<target>/*.swift

Top-level exports only, read from the entry files. Quick mode reads no other
file (--follow aside, below), so a name an entry file passes on from another
module without naming it is not an export here: a warning names each such
statement, and an `unlisted[]` record gives its file, line, statement,
specifier and `module_file`, so the caller can pass that module as a
--follow-file, or have --follow read it (a module_file), or read it by eye
(none). A warning also names
each statement below whose names the file holds in a form quick mode does
not read (an anonymous default export, a destructuring declaration, an
assignment inside a block).

  JavaScript / TypeScript  read with comments, strings and regular
      expressions blanked: column-0 `export` declarations (`const`, `let`
      and `var`, every declarator of the statement, `function`,
      `function*`, `async function`, `class`, `abstract class`,
      `interface`, `type`, `enum`, `const enum`, `namespace`, each may be
      `default` or `declare`), typed by keyword; `export { ... }` and
      `export type { ... }` lists (`re-export`); `export * as ns from`
      (`namespace`); `export default <name>` (the type of that local
      declaration, else `re-export`); TypeScript's `export = <value>`, read
      as `module.exports = <value>` is; and CommonJS: each `exports.<name> =`
      and `module.exports.<name> =` (each name of a chain such as tsc's
      `exports.a = exports.b = void 0`), the keys of a `module.exports =
      { ... }` object, and the one name of `module.exports = <name>`
      (`exports = module.exports = <name>` included), a named function or a
      named class (`function`, `class`, or the local declaration's type,
      else `variable`). Warned: `export * from`, `module.exports =
      require(...)`, a spread in the `module.exports` object, a
      `module.exports` or `export =` that is anonymous or an expression, an
      `export default` that is anonymous or an expression, an `export const`
      that destructures, and a `module.exports`, `exports` or
      `exports.<name>` assignment that does not open its line (in an `if`, a
      block or a function, so which one runs the file alone cannot tell).
  Python  with `__all__` (literal lists and tuples, however the module
      builds it, read as full mode reads it), every public name it lists,
      typed by what binds it in the file: `def` (async def included),
      `class`, `variable` (an assignment), `module` (`import x`),
      `re-export` (an import, or no binding in the file); a part that is no
      literal (another module's `__all__`) is warned. Without `__all__`, the
      public def, async def and class names, and the names imported from
      the package itself (`re-export`: `from .x import Y`, or, in an
      `__init__.py`, an absolute import that names the package by any
      trailing run of its folders: `storage`, `cloud.storage` or
      `acme.cloud.storage` for acme/cloud/storage/__init__.py); a star
      import from the package is warned. Imports under `if TYPE_CHECKING:`
      do not count. A module this Python cannot parse is read from its
      text, with a warning.
  Rust  column-0 unrestricted `pub` items, qualifiers included (`const`,
      `async`, `unsafe`, `extern "C"`: `pub const fn f` is the fn `f`),
      typed by item keyword; each `#[macro_export]` `macro_rules!` macro
      (`macro`); and each name a column-0 `pub use` brings in (`re-export`,
      under its alias when it has one); a glob `pub use x::*` is warned. An
      indented `pub` item is a method or sits in an inline module, not a
      top-level export.
  Go  capitalized top-level func, type, var and const names.
  Java  public classes, interfaces, enums and records, and the classes a
      Spring or Jakarta annotation marks.
  Kotlin  declarations not marked internal or private.
  Swift  public and open declarations.

Input: a JSON payload on stdin,

  {
    "language": "python",
    "manifest": {"path": "pyproject.toml", "content": "..."},
    "entries":  [{"path": "src/foo/__init__.py", "content": "...",
                  "followed": false}, ...],
    "mode":     "quick"
  }

or the files, read from disk (stdin is then never read):

  --mode quick --language <language> [--source-root <dir>]
      [--manifest-file <path>] [--entry-file <path>]...
      [--follow-file <path>]... [--tree-file <listing>] [--fetch-list <file>]
      [--follow [--repo <owner/repo> [--ref <ref>]]]

An entry with `followed` true (a --follow-file) is a module an `unlisted[]`
record named, read as an entry is, less a JS/TS `export default`, which
`export *` does not pass on.

--follow (with --tree-file and --source-root) reads those modules itself,
so no caller loops over the files: while `unlisted[]` names a module_file
not tried yet, at most 5 rounds, each one is read as one more --follow-file
and the files are parsed again, so an `export *` chain is read to its end.
With --repo, each is first fetched into --source-root at --ref (HEAD by
default) by skf-github-fetch.py, which reads it from
raw.githubusercontent.com and through gh only for a private repository;
without it, each is read where --source-root holds it (a local checkout).
A module that cannot be fetched or read stays in `unlisted[]`, and a
warning names it and why. The output then also lists `followed`, the
modules read this way, in the order they were read.

Each path is relative to --source-root, the folder the files were staged in
laid out like the repository (or a local checkout), else to the current
folder, and is the `path` the output names (`source_file`), written with
`/`. A path under --source-root may not be absolute or lead outside it. A
file's text is read as UTF-8 (a byte order mark dropped, an invalid byte
replaced), so a quote or an apostrophe in it reaches the parser as it is.
An entry named twice is read once (a file both an --entry-file and a
--follow-file is an entry). Without --manifest-file the package metadata is
empty, as for a payload whose manifest `content` is empty. A python
manifest is read by its name: setup.py and setup.cfg by their own parsers,
any other as pyproject.toml.

Output JSON shape (stdout):

  {
    "language":    "python",
    "package_name": "foo",
    "version":      "1.2.3",
    "description":  "...",
    "exports":      [{"name": "Bar", "type": "class", "source_file": "..."}, ...],
    "dependencies": ["requests", "pydantic", ...],
    "modules":      ["server", "client"],         (Maven/Gradle only)
    "module_folders": ["server", "client"],       (each module's folder in
                                                   the repository)
    "extra":        {"group_id": "com.example"}, (Maven only)
    "warnings":     ["..."],                       (parse failures, fallbacks)
    "unlisted":     [{"file", "line", "statement", "specifier",
                      "module_file"}, ...],
    "followed":     ["src/core.ts", ...]               (--follow only)
  }

`unlisted` holds one record per statement whose names come from a module
quick mode did not read: `export * from`, `module.exports = require(...)`
(and such an assignment in a block), a spread in the `module.exports`
object, a Python star import from the package and a Rust `pub use x::*`.
`module_file` is the file of the listing (--tree-file, or a payload's
`tree`) that module is, found as full mode finds it (resolve_js_module, a
NodeNext `./x.js` naming x.ts, and _py_module_file); null without a
listing, and for a package import, a spread, a Rust glob or a module the
listing does not hold. A statement whose module_file is already an entry
file is left out, with its warning: its names are read. --fetch-list
writes each module_file still to read, one per line, so a caller fetches
them, passes them as more --follow-file and runs again until the list is
empty, which --follow does itself. `module_folders` gives each of
`modules` as a folder of the repository: the manifest's folder joined with
the module (a Gradle `core:api` read as `core/api`).

Exit codes (quick):

  0    success
  1    payload-level error (a language quick mode does not parse)
  2    input error: stdin, argparse or JSON-decode error, --language missing
       or given twice with the file inputs, a --manifest-file, --entry-file
       or --follow-file that cannot be read or leads outside --source-root,
       a --tree-file that cannot be read or a --fetch-list that cannot be
       written, --follow without --tree-file and --source-root, --repo or
       --ref without --follow (--ref without --repo), or a --repo or --ref
       skf-github-fetch.py does not accept. A module --follow could not
       read changes no exit code.

Entries mode
------------

  --mode entries --language <language> --tree-file <listing>
      --source-root <dir> [--scope <folder>] [--fetch-list <file>]

The entry files of the one package at --scope (the repository root
without it), read from the listing (skf-github-probe.py tree output, or any
listing skf-detect-language.py's --tree-file reads). The package's manifest
is read from --source-root, the folder it was fetched into (a folder not
made yet holds none):

  js, ts       the files its package.json exports map, else its
               types/module/main/browser fields, name (a build output not
               committed mapped back to its source: dist/index.js ->
               src/index.ts), else index.* or src/index.* (_js_entries)
  python       the top __init__.py of each package among its .py files
               (_py_entries), less those under a top folder named test*,
               docs, examples or benchmarks, the one whose folder is the
               manifest name as Python imports it preferred; with no
               package, <name>.py or src/<name>.py (a single-module
               package such as six). The name is the first one the
               manifests give, read in the order pyproject.toml ([project]
               or [tool.poetry]), setup.py, setup.cfg ([metadata]), and
               `manifest` is the one that gave it (else the first listed)
  rust         the crate root, `[lib] path` else src/lib.rs (_rust_entries)
  go           the .go files directly in the folder, less *_test.go
  java         src/main/java/<groupId as a path>/*.java (the pom's groupId,
               else its parent's)
  kotlin       src/main/kotlin/**/*.kt

Go, Java and Kotlin read the first 5 files in path order, and no language
more than 25. Output (stdout):

  {
    "mode":        "entries",
    "language":    "python",
    "scope":       "." | "<folder>",
    "manifest":    "<path in the listing>" | null,
    "entry_files": ["src/PIL/__init__.py", ...],
    "unresolved":  [{"package", "subpath", "targets"}, ...],
    "warnings":    ["..."]
  }

`manifest` is the manifest the language reads at the folder (null when the
listing has none), `unresolved` names what no listed file answered (a
package.json target, or the paths tried), and --fetch-list writes
`entry_files` one per line. A language quick mode parses but has no rule
here (swift) gives no entry file and a warning.

Exit codes (entries): 0 (an empty `entry_files` included); 1 for a language
quick mode does not parse; 2 for an input error (a --tree-file that cannot
be read, a --source-root that is a file, a --fetch-list that cannot be
written, a flag of another mode).

Full mode
---------

  --mode full --source-root <dir>
      [--brief <skill-brief.yaml>] [--include GLOB]... [--exclude GLOB]...
      [--tier-a-include GLOB]... [--scope-type TYPE] [--language LANG]...
      [--files-from <file>] [--recipe-set standard|component-library]
      [--tier Quick|Forge|Forge+|Deep] [--head-cap N] [--recipes <file>]
      [--timeout <seconds>] [-o <out.json>]

Which files. The files under --source-root are those git lists there
(tracked, and untracked but not ignored), or every file when it is not in
a git work tree, leaving out hidden entries and symbolic links: the files
ast-grep itself would walk. With --files-from (paths relative to
--source-root: a JSON list when the whole file is one, else one path per
line, so a first path such as `[slug]/page.tsx` is read as a path) only
the files it names are read, and a named file that is missing, or whose
language has no recipe, is listed in `file_issues`. A file is in scope when an include glob matches it (every
file when there is none) and no exclude glob does, and when its language
is one the recipes read (python, typescript, tsx, javascript, rust, go and
.vue files) and --language allows it. Globs follow
skf-resolve-authoritative-files.py's rules: `**` spans any number of path
segments, none included, and `*` and `?` stay inside one, so `src/**/*.ts`
matches `src/index.ts` and `**/test_*` matches a top-level `test_x.py`.

--brief supplies scope.include, scope.exclude, scope.tier_a_include,
scope.type and language; --include, --exclude, --tier-a-include,
--scope-type and --language replace the brief's value when given.
--language takes a language family (`typescript`, `javascript`, `ts`,
`js`, `tsx` and `vue` all select .ts, .tsx, .js and .vue files; `python`,
`rust`, `go`).

Which recipes. --recipe-set picks the recipes whose metadata.sets lists it:
`component-library` when the scope type is component-library, else
`standard`. Each recipe runs in the languages its metadata.languages
lists. A match whose name starts with `_` is never an export. --head-cap
keeps at most N matches of each recipe, in file and line order (0: no
cap); without it the cap is 200, or at Forge+ and Deep tiers 500 for a
full-library scope and 300 for a component-library one. `truncated` is
true when a recipe had more.

Merging. The matches of one name in one file become one export, at the
first line that names it (overload signatures, and a definition in both
branches of an `if`, repeat a name). When several recipes match that line,
the export records the one no other of them lists under
metadata.prefer_over, else the first in the recipe file. Its `source_line`
is the line of `$NAME` (a decorator or an `export` line can come first),
`signature_line` the whole source line holding it (the full list line for
a list item), `signature` the declaration that line opens on one line (the
lines after it joined while a ( or [ it opens is still open, each without
its line comment, and a trailing comma before the closing bracket dropped,
so a parameter list a formatter split one per line reads as its one-line
form; at most 40 lines; otherwise `signature_line`), `ast_node_type` the
kind the recipe declares, and
`export_type` its metadata.export_type (for a list, the declaration
keyword before the name picks one). A function (export_type `function`)
also gets `params`, each parameter read from `signature` as {name, type,
default, optional} (Python's through its own parser; a rest or variadic
parameter, `...rest`, `*args`, `**kwargs` or Go's `...T`, is optional, and
a Go name shares the type written after it), and `return_type`, the type
the declaration states, null when it states none. Both are null for any
other export, and for a signature the reader does not parse (one cut at
the line cap, say), which the caller then reads by eye. An item of a local `export { ... }`
list takes instead the type of the top-level binding it names in its file:
what the recipes record for that declaration exported in place (a const
bound to an arrow function or a function expression is a function), or
`re-export` for an import.

Entry points. The export surface each package declares: every subpath of a
package.json `exports` map (committed .d.ts/.d.mts targets outside src/
included, a build output mapped back to its source when the target is not
committed, a pattern subpath's `*` matched against the tree, one entry per
file, less the subpaths a `null` target takes out), else its
types/module/main fields, else index.* or src/index.*; a Python package's
top __init__.py (its __all__ when it has one, else the public names it
defines or imports from the package, and those its star imports give); a
crate's lib.rs (its `pub use` items, globs included, and column-0
unrestricted `pub` items); a Go package's capitalized top-level names
outside _test.go, package main and internal/ folders. Each entry point is
`in_scope` when it is one of the files in scope (a warning names each
JS/TS one that is not). Chains are followed to the end, a cycle cut: an
`export *`, a star import or a glob passes on what its module exports,
that module's own chains included; a re-exported name is traced through
each re-export, import and glob between to the file that defines it (a
default export to the name it declares). A namespace (`export * as ns`, a
Python submodule, a Rust `pub mod`) counts once, and what it makes
reachable is not internal: the names its module passes on, the modules
among them in turn, and for Rust every recipe match in the crate root and
in each module file a `pub mod` or `pub use` of a reachable module names.
A chain the trace cannot follow (a module no file here holds, a `#[path]`
module) is listed in `unresolved`. The diff against the recipe inventory,
one language family at a time (JavaScript/TypeScript, Python, Rust, Go):
`public` (the entry points' names), `internal` (names the recipes found
that no entry point exports or makes reachable), `extraction_gaps` (names
an entry point exports that no recipe found, defined in a file in scope or
in none the trace reached: read them by eye) and `outside_scope` (such
names defined in a file out of scope: widen scope.include to document
them). In a family with no entry point, or only empty ones, every name the
recipes found is public.

Counts. `exports_public_api` counts the public names (the package's whole
public API, `outside_scope` names included) and `exports_internal` the
internal ones. `effective_denominator` counts the public names whose
definition file matches scope.tier_a_include (else scope.include) and no
scope.exclude glob: each name once, so a type counts once whatever its
methods, and a barrel that only re-exports adds nothing of its own. `arms` gives compile's effective_denominator arms:
(a) `monorepo` from skf-detect-workspaces.py, (b) `specific_modules`
(scope type specific-modules on a repository that is not a monorepo) and
(c) `multi_subpath_exports` (an in-scope package.json whose `exports` map
has more than one non-root subpath without a `*`, on a repository that is
not a monorepo).

Output JSON (stdout, or -o):

  {
    "mode": "full",
    "status": "ok" | "incomplete" | "no-ast-grep",
    "source_root": "<as given>",
    "recipes_file": "<path>",
    "recipe_set": "standard" | "component-library",
    "ast_grep": {"path": "<exe>" | null, "version": "<x.y.z>" | null},
    "scope": {"include": [...], "exclude": [...],
              "tier_a_include": [...] | null, "type": "<type>" | null,
              "languages": [...], "files_from": "<file>" | null},
    "files_in_scope": N,
    "files_by_language": {"<language>": N, ...},
    "files_without_recipes": {".java": N, ...},  # in scope, no recipe reads them
    "file_issues": [{"file", "issue": "missing" | "no-recipes" | "not-utf8"
                       | "unreadable" | "syntax-errors",
                     "count": N, "line": N}, ...],  # count, line: syntax-errors
    "head_cap": N | null,
    "truncated": bool,
    "recipes": [{"id", "languages": [...], "matches": N, "truncated": bool}, ...],
    "exports": [{"export_name", "source_file", "source_line", "signature_line",
                 "signature", "params": [{"name", "type", "default",
                 "optional"}, ...] | null, "return_type": "<type>" | null,
                 "citation": "[AST:<file>:L<line>]", "ast_recipe",
                 "ast_node_type", "export_type", "language",
                 "from": "<module>" | null, "from_file": "<file>" | null,
                 "confidence": "T1", "extraction_method": "ast-grep"}, ...],
    "aggregates": {"exports": N, "by_type": {"function": N, ...},
                   "t1": N, "t1_low": 0},
    "entry_points": {"status": "barrel" | "empty-barrel" | "no-entry-point"
                               | null,  # null: no-ast-grep
                     "by_language": {"<family>": "<status>", ...},
                     "files": [{"language", "file", "package", "subpath",
                                "resolution": "file" | "source-guess"
                                  | "conventional" | "package",
                                "in_scope": bool}, ...],
                     "exports_maps": [{"package", "subpaths": [...],
                                       "non_root_subpaths": N,
                                       "wildcard_subpaths": N}, ...],
                     "unresolved": [{"package", "subpath", "targets"}
                                    | {"entry", "name", "from", "file"}, ...]},
    "entry_point_diff": {
        "public": [{"name", "language", "entry", "via", "from", "local",
                    "file", "line"}, ...],
        "internal": [{"name", "language", "source_file", "source_line"}, ...],
        "extraction_gaps": [{"name", "language", "entry", "file", "line"}, ...],
        "outside_scope": [{"name", "language", "entry", "file", "line"}, ...]},
    "reexport_targets": [{"name", "language", "local", "from", "entry",
                          "file", "line", "via"}, ...],
    "counts": {"exports_public_api": N, "exports_internal": N,
               "effective_denominator": N,
               "effective_denominator_basis": "tier_a_include" | "scope.include"
                                              | "all-files",
               "denominator_files": N},
    "arms": {"monorepo": bool, "monorepo_kind": "<kind>" | null,
             "specific_modules": bool, "multi_subpath_exports": bool},
    "errors": [{"reason": "ast-grep-error" | "ast-grep-timeout" | "time-limit",
                "files": N, "first_file", "detail",
                "unread": [...]}, ...],      # unread: time-limit only
    "warnings": ["..."]
  }

`via` says how an entry point exports a name: `declaration` (defined in the
entry point), `re-export` (from another file, which `file` names, `local`
giving the name it has there when it differs), `star` (through `export *`,
`from .x import *` or `pub use x::*`) or `namespace` (a module: `export *
as ns`, a Python submodule, a Rust module). `line` is null where no line
defines the name (a module, a name from another package). An `unresolved`
item names a subpath whose targets name no file, or a chain met tracing
`entry` that stops at `file`, the module `from` naming no file here.
Without ast-grep the JSON still has the entry points' `files`, the
`exports_maps`, the unresolved subpaths and the `arms`.
`file_issues` lists the files to read by eye: a file ast-grep skips (not
UTF-8), and a file where the parser met code it could not read (an ERROR
node), where a recipe can miss an export. `t1_low` is 0: every export here
comes from a recipe, and an export the caller then reads by eye (an
extraction gap, a Known Limitation #11 form) is T1-low.

Time limit. The ast-grep runs stop once --timeout seconds (540 by default,
under the 10-minute limit an agent's shell call often has) have passed
since the run started: the run going on is stopped, no other starts, and
an `errors[]` item with the reason `time-limit` lists in `unread` the
files left unread (each ast-grep call also stops after 600 seconds,
`ast-grep-timeout`). The JSON is still written, status "incomplete".

Exit codes (full):

  0    the recipes ran on every file in scope ("ok")
  1    an ast-grep run failed (exited non-zero) or timed out, or the
       --timeout ran out: its files may be unread and the result is
       incomplete ("incomplete"); `errors` lists them
  2    input error (no source root, an unreadable brief, file list or
       recipe file, a recipe without its metadata, no PyYAML, an -o file
       that cannot be written, a --timeout not above 0), or a failure the
       runner did not foresee: one line on stderr and no JSON
  3    no ast-grep the runner can run ("no-ast-grep"): none on PATH, or
       only an npm .cmd/.bat shim (Windows) with no native ast-grep.exe
       beside it (cmd.exe would read a repository path's `&` as syntax);
       the JSON has the scope and no exports; extract by source reading

CLI examples:
  uv run skf-extract-public-api.py --mode quick < {payload_json}
  uv run skf-extract-public-api.py --mode entries --language python \\
      --tree-file {tree_json} --source-root {staged_dir} --fetch-list {entries_txt}
  uv run skf-extract-public-api.py --mode quick --language rust \\
      --source-root {staged_dir} --manifest-file Cargo.toml --entry-file src/lib.rs
  uv run skf-extract-public-api.py --mode full --source-root {source_root} \\
      --brief {brief_path} --tier Forge -o {extraction_json}
  uv run skf-extract-public-api.py --mode full --source-root {source_root} \\
      --files-from {scan_list} --head-cap 0
"""

from __future__ import annotations

import argparse
import ast
import configparser
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Callable, Iterator

# --------------------------------------------------------------------------
# Manifest parsers
# --------------------------------------------------------------------------


def parse_package_json(content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"_parse_error": f"package.json JSON parse error: {e}"}
    if not isinstance(data, dict):
        return {"_parse_error": "package.json root is not an object"}
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "description": data.get("description"),
        "main": data.get("main"),
        "exports": data.get("exports"),
        "dependencies": list((data.get("dependencies") or {}).keys()),
        "modules": [],
    }


def parse_pyproject_toml(content: str) -> dict:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        return {"_parse_error": f"pyproject.toml parse error: {e}"}
    project = data.get("project") or {}
    raw_deps = project.get("dependencies") or []
    dep_names: list[str] = []
    for d in raw_deps:
        if isinstance(d, str):
            m = re.match(r"^([A-Za-z0-9_.\-]+)", d.strip())
            if m:
                dep_names.append(m.group(1))
    return {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "dependencies": dep_names,
        "modules": [],
    }


def parse_setup_py(content: str) -> dict:
    """Best-effort regex parse of setup.py — does NOT execute the file."""

    def find_kwarg(name: str) -> str | None:
        m = re.search(rf'\b{name}\s*=\s*["\']([^"\']+)["\']', content)
        return m.group(1) if m else None

    return {
        "name": find_kwarg("name"),
        "version": find_kwarg("version"),
        "description": find_kwarg("description"),
        "dependencies": [],
        "modules": [],
    }


def parse_setup_cfg(content: str) -> dict:
    """setup.cfg's [metadata] (a literal version only) and [options]
    install_requires, read with configparser."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(content)
    except configparser.Error as e:
        return {"_parse_error": f"setup.cfg parse error: {e}"}
    meta = parser["metadata"] if parser.has_section("metadata") else {}
    version = (meta.get("version") or "").strip()
    deps: list[str] = []
    if parser.has_option("options", "install_requires"):
        for line in parser.get("options", "install_requires").splitlines():
            m = re.match(r"^([A-Za-z0-9_.\-]+)", line.strip())
            if m:
                deps.append(m.group(1))
    return {
        "name": (meta.get("name") or "").strip() or None,
        "version": None if not version or version.startswith(("attr:", "file:")) else version,
        "description": (meta.get("description") or "").strip() or None,
        "dependencies": deps,
        "modules": [],
    }


def parse_cargo_toml(content: str) -> dict:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        return {"_parse_error": f"Cargo.toml parse error: {e}"}
    pkg = data.get("package") or {}
    return {
        "name": pkg.get("name"),
        "version": pkg.get("version"),
        "description": pkg.get("description"),
        "dependencies": list((data.get("dependencies") or {}).keys()),
        "modules": [],
    }


def parse_go_mod(content: str) -> dict:
    name: str | None = None
    deps: list[str] = []
    in_require_block = False
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("module "):
            name = s.split(None, 1)[1].strip()
            continue
        if s.startswith("require ("):
            in_require_block = True
            continue
        if s == ")" and in_require_block:
            in_require_block = False
            continue
        if s.startswith("require "):
            parts = s.split(None, 2)
            if len(parts) >= 2:
                deps.append(parts[1])
            continue
        if in_require_block:
            parts = s.split()
            if parts:
                deps.append(parts[0])
    return {
        "name": name,
        "version": None,
        "description": None,
        "dependencies": deps,
        "modules": [],
    }


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_pom_xml(content: str) -> dict:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return {"_parse_error": f"pom.xml parse error: {e}"}

    group_id = artifact_id = version = description = None
    modules: list[str] = []
    deps: list[str] = []

    for child in root:
        tag = _strip_ns(child.tag)
        if tag == "groupId":
            group_id = (child.text or "").strip() or None
        elif tag == "artifactId":
            artifact_id = (child.text or "").strip() or None
        elif tag == "version":
            version = (child.text or "").strip() or None
        elif tag == "description":
            description = (child.text or "").strip() or None
        elif tag == "modules":
            for m in child:
                if _strip_ns(m.tag) == "module":
                    text = (m.text or "").strip()
                    if text:
                        modules.append(text)
        elif tag == "dependencies":
            for d in child:
                d_artifact = None
                for c in d:
                    if _strip_ns(c.tag) == "artifactId":
                        d_artifact = (c.text or "").strip() or None
                if d_artifact:
                    deps.append(d_artifact)

    out = {
        "name": artifact_id,
        "version": version,
        "description": description,
        "dependencies": deps,
        "modules": modules,
    }
    if group_id:
        out["_extra"] = {"group_id": group_id}
    return out


def parse_gradle(content: str) -> dict:
    """Best-effort regex parse of build.gradle / build.gradle.kts."""

    def find_assignment(name: str) -> str | None:
        for pat in (
            rf'\b{name}\s*=\s*["\']([^"\']+)["\']',
            rf'\b{name}\s+["\']([^"\']+)["\']',
            rf'\b{name}\s*\(\s*["\']([^"\']+)["\']',
            rf'\b{name}\s*:\s*["\']([^"\']+)["\']',
        ):
            m = re.search(pat, content)
            if m:
                return m.group(1)
        return None

    return {
        "name": find_assignment("artifactId") or find_assignment("group"),
        "version": find_assignment("version"),
        "description": find_assignment("description"),
        "dependencies": [],
        "modules": [],
    }


def parse_settings_gradle(content: str) -> list[str]:
    """Extract include('...') / include(":a", ":b") entries."""
    modules: list[str] = []
    for m in re.finditer(r"include\s*\(?(.+?)\)?$", content, flags=re.MULTILINE):
        for s in re.findall(r"""['"]:?([^'"]+)['"]""", m.group(1)):
            modules.append(s)
    return modules


def parse_package_swift(content: str) -> dict:
    """Best-effort parse of a SwiftPM Package.swift manifest.

    SwiftPM has no version field in the manifest (versions come from git tags),
    so `version` is always None; the brief falls back to target_version / default.
    """
    name_m = re.search(r"\bPackage\s*\(\s*name:\s*['\"]([^'\"]+)['\"]", content, re.DOTALL)
    deps: list[str] = []
    for m in re.finditer(r"\.package\s*\(\s*url:\s*['\"]([^'\"]+)['\"]", content):
        seg = m.group(1).rstrip("/").rsplit("/", 1)[-1]
        if seg.endswith(".git"):
            seg = seg[: -len(".git")]
        if seg:
            deps.append(seg)
    return {
        "name": name_m.group(1).strip() if name_m else None,
        "version": None,
        "description": None,
        "dependencies": deps,
        "modules": [],
    }


# --------------------------------------------------------------------------
# Export scanners
# --------------------------------------------------------------------------

def _note(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _unlisted(source_file: str, line: int, statement: str) -> str:
    """The warning for a statement that exports names quick mode cannot list."""
    return (f"{source_file} line {line}: {statement} passes on names from a module quick mode does not read: "
            "pass that module as an entry too, or read it by eye")


def _note_unlisted(warnings: list[str] | None, unlisted: list[dict] | None, source_file: str, line: int,
                   statement: str, specifier: str | None = None, module: tuple | None = None,
                   shown: str | None = None) -> None:
    """Note a statement whose names come from a module quick mode does not
    read: its warning (_unlisted, naming `shown`, else the statement in
    backticks) and, when `unlisted` collects them, its record. `module` says
    how extract() finds the module's file: ("js", specifier) or ("python",
    level, module); None when it cannot (a package import, a Rust glob)."""
    message = _unlisted(source_file, line, shown or f"`{statement}`")
    _note(warnings, message)
    if unlisted is not None:
        unlisted.append({"file": source_file, "line": line, "statement": statement, "specifier": specifier,
                         "_module": module, "_warning": message})


def _exports(found: list[tuple[int, str, str]], source_file: str) -> list[dict]:
    """The export records of (offset, name, type) found, in file order, each
    name once (its first form wins)."""
    out: list[dict] = []
    seen: set[str] = set()
    for _, name, kind in sorted(found, key=lambda item: item[0]):
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "type": kind, "source_file": source_file})
    return out


# A column-0 declaration: `export` (with `declare` or `default`) when it is
# exported, its keyword and its name. A generator's `*` may touch the name.
_JS_DECL_RE = re.compile(
    r"^(export\s+(?:declare\s+)?(?:default\s+)?)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(const\s+enum|const|let|var|function\s*\*|function|class|interface|type|enum|namespace|module)"
    r"(?:(?<=\*)\s*|\s+)([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_JS_LIST_RE = re.compile(r"^export\s+(?:type\s+)?\{([^}]*)\}", re.MULTILINE)
_JS_STAR_RE = re.compile(
    r"^export\s+(?:type\s+)?\*\s*(?:as\s+([A-Za-z_$][\w$]*)\s*)?from\s*(['\"])", re.MULTILINE)
_JS_DEFAULT_RE = re.compile(r"^export\s+default\s+([A-Za-z_$][\w$]*)\s*(?:;|$)", re.MULTILINE)
_JS_ANY_DEFAULT_RE = re.compile(r"^export\s+default\b\s*", re.MULTILINE)
# `export const { a, b } = obj` or `export let [x, y] = pair`
_JS_DESTRUCTURE_RE = re.compile(r"^export\s+(?:declare\s+)?(const|let|var)\s*[{[]", re.MULTILINE)
# A name after a comma of a `const`/`let`/`var` statement: its next declarator.
_JS_DECLARATOR_RE = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*(?:[=,;:!]|$)", re.MULTILINE)
_JS_LEADING_COMMA_RE = re.compile(r"\s*,")
# TypeScript's `export = <value>`, read as `module.exports = <value>` is.
_TS_EXPORT_ASSIGN_RE = re.compile(r"^export\s*=(?![=>])\s*", re.MULTILINE)
_CJS_NAMED_RE = re.compile(r"^(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=(?![=>])", re.MULTILINE)
# A column-0 `module.exports =`, also as Express writes it: `exports =
# module.exports = <value>` (or `module.exports = exports = <value>`).
_CJS_MODULE_RE = re.compile(
    r"^(?:exports\s*=\s*)?module\.exports\s*=(?![=>])\s*(?:exports\s*=(?![=>])\s*)?", re.MULTILINE)
# Any `module.exports`, `exports` or `exports.<name>` assignment; the ones
# that do not open their line or follow a chain that does (inside an `if`, a
# block, a function) are warned, since which of them runs the entry file
# alone cannot tell. TypeScript's CommonJS output opens with a chain:
# `exports.a = exports.b = void 0;`.
_CJS_ANY_RE = re.compile(r"(?<![\w$.])(?:module\.exports|exports)(?:\.([A-Za-z_$][\w$]*))?\s*=(?![=>])")
_CJS_CHAIN_RE = re.compile(r"(?:(?:module\.)?exports(?:\.[A-Za-z_$][\w$]*)?\s*=(?![=>])\s*)*")
_JS_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*")
_JS_SPACE_RE = re.compile(r"\s*")
_JS_REQUIRE_RE = re.compile(r"require\s*\(\s*(['\"])")
_JS_NAMED_VALUE_RE = re.compile(r"(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)")
_JS_ANONYMOUS_VALUE_RE = re.compile(r"(?:async\s+)?(?:function\b|class\b|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")
_JS_FUNCTION_VALUE_RE = re.compile(r"\s*(?:async\s+)?(?:function\b|(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>)")
_JS_CLASS_VALUE_RE = re.compile(r"\s*class\b")
_JS_NAME_VALUE_RE = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*(?:[;,})\]]|$)", re.MULTILINE)
_JS_MEMBER_PREFIX_RE = re.compile(r"(?:(?:get|set|static|async)\s+(?=[\w$'\"*\[]))*\*?\s*")
# Words the name patterns can meet that name no export: `class extends
# Base`, `export default true`, and the interop flag compilers set.
_JS_NOT_NAMES = frozenset({
    "extends", "implements", "true", "false", "null", "undefined", "this", "new", "void", "typeof",
    "function", "class", "async", "await", "__esModule",
})


def _js_type(keyword: str) -> str:
    """The export type of a declaration keyword: `function*` and `async
    function` are functions, a `const enum` an enum, a `module` a
    namespace."""
    keyword = " ".join(keyword.split())
    if keyword.startswith("function"):
        return "function"
    return {"const enum": "enum", "module": "namespace"}.get(keyword, keyword)


def _js_string(content: str, code: str, quote: int) -> str:
    """The text of the string literal whose opening quote is at `quote`."""
    close = code.find(code[quote], quote + 1)
    return content[quote + 1: close if close >= 0 else len(content)]


def _js_value_type(code: str, pos: int, declared: dict[str, str]) -> str:
    """The export type of the value assigned at `pos`: a function or class
    expression, the local declaration a name refers to, else a variable."""
    if _JS_FUNCTION_VALUE_RE.match(code, pos):
        return "function"
    if _JS_CLASS_VALUE_RE.match(code, pos):
        return "class"
    name = _JS_NAME_VALUE_RE.match(code, pos)
    return declared.get(name.group(1), "variable") if name else "variable"


def _js_object_members(content: str, code: str, start: int,
                       declared: dict[str, str]) -> tuple[list[tuple[int, str, str]], list[str]]:
    """((offset, key, type) of each member of the object literal whose `{`
    is at `start` in `code`, the spread expressions it holds). A method is
    a function, `key: value` takes the value's type, a shorthand key the
    type of its local declaration; a computed key names nothing."""
    spans: list[tuple[int, int]] = []
    depth, begin = 0, start + 1
    for i in range(start, len(code)):
        ch = code[i]
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
            if depth == 0:
                spans.append((begin, i))
                break
        elif ch == "," and depth == 1:
            spans.append((begin, i))
            begin = i + 1
    members: list[tuple[int, str, str]] = []
    spreads: list[str] = []
    for b, e in spans:
        pos = b + len(code[b:e]) - len(code[b:e].lstrip())
        if pos >= e:
            continue
        if code.startswith("...", pos):
            spreads.append(" ".join(content[pos:e].split()))
            continue
        pos = _JS_MEMBER_PREFIX_RE.match(code, pos, e).end()
        if pos >= e:
            continue
        if code[pos] in "'\"":
            close = code.find(code[pos], pos + 1, e)
            if close < 0:
                continue
            key, after = content[pos + 1:close], close + 1
        else:
            ident = _JS_NAME_RE.match(code, pos, e)
            if not ident:
                continue
            key, after = ident.group(0), ident.end()
        rest = code[after:e].lstrip()
        if rest.startswith("("):
            kind = "function"
        elif rest.startswith(":"):
            kind = _js_value_type(code, code.index(":", after, e) + 1, declared)
        else:
            kind = declared.get(key, "variable")
        if key:
            members.append((pos, key, kind))
    return members, spreads


def _js_module_exports(content: str, code: str, match: re.Match, source_file: str, declared: dict[str, str],
                       found: list[tuple[int, str, str]], warnings: list[str] | None,
                       target: str = "module.exports", unlisted: list[dict] | None = None) -> None:
    """Add the names one `module.exports = <value>` (or TypeScript's
    `export = <value>`, the `target`) exports."""
    pos, line = match.end(), _line_of(code, match.start())
    assign = target if target.endswith("=") else f"{target} ="
    if code.startswith("{", pos):
        members, spreads = _js_object_members(content, code, pos, declared)
        found.extend(members)
        for spread in spreads:
            _note_unlisted(warnings, unlisted, source_file, line, spread,
                           shown=f"the `{target}` object's `{spread}`")
        return
    require = _JS_REQUIRE_RE.match(code, pos)
    if require:
        spec = _js_string(content, code, require.end(1) - 1)
        _note_unlisted(warnings, unlisted, source_file, line, f"{assign} require('{spec}')", spec, ("js", spec))
        return
    named = _JS_NAMED_VALUE_RE.match(code, pos)
    if named:
        found.append((pos, named.group(1) or named.group(2), "function" if named.group(1) else "class"))
        return
    if _JS_ANONYMOUS_VALUE_RE.match(code, pos):
        _note(warnings, f"{source_file} line {line}: `{target}` is an anonymous function or class: "
                        "the package's one export has no name here")
        return
    name = _JS_NAME_VALUE_RE.match(code, pos)
    if name and name.group(1) not in _JS_NOT_NAMES:
        found.append((pos, name.group(1), declared.get(name.group(1), "variable")))
        return
    _note(warnings, f"{source_file} line {line}: `{target}` is set to an expression quick mode does not "
                    "read: read the names it exports by eye")


def _js_more_declarators(code: str, pos: int) -> list[tuple[int, str]]:
    """(offset, name) of each declarator after the first of the `const`,
    `let` or `var` statement whose first name ends at `pos`: `export const
    a = 1, b = 2` declares `b` too. The statement ends at a `;`, a bracket
    it did not open, or a line end that no comma joins to the next line."""
    names: list[tuple[int, str]] = []
    depth, last, i = 0, "", pos
    while i < len(code):
        ch = code[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and ch == ";":
            break
        elif depth == 0 and ch == "\n":
            if last != "," and not _JS_LEADING_COMMA_RE.match(code, i):
                break
        elif depth == 0 and ch == ",":
            declarator = _JS_DECLARATOR_RE.match(code, i + 1)
            if declarator and declarator.group(1) not in _JS_NOT_NAMES:
                names.append((declarator.start(1), declarator.group(1)))
        if not ch.isspace():
            last = ch
        i += 1
    return names


def scan_exports_js(content: str, source_file: str, warnings: list[str] | None = None,
                    unlisted: list[dict] | None = None, defaults: bool = True) -> list[dict]:
    """The names a JS/TS entry file exports (see "Quick mode" above), read
    from its text with comments, string contents and regular expressions
    blanked. Without `defaults` (a module reached through `export *`) its
    `export default` is left out, unread and unwarned."""
    code = _blank(content, "js")
    declared: dict[str, str] = {}
    found: list[tuple[int, str, str]] = []
    read_defaults: set[int] = set()  # the `export default` statements a name was read from
    for m in _JS_DECL_RE.finditer(code):
        name, kind = m.group(3), _js_type(m.group(2))
        if name in _JS_NOT_NAMES:
            continue
        declared.setdefault(name, kind)
        if m.group(1):
            if "default" in m.group(1).split():
                read_defaults.add(m.start())
                if not defaults:
                    continue
            found.append((m.start(), name, kind))
        if kind in ("const", "let", "var"):
            for offset, more in _js_more_declarators(code, m.end(3)):
                declared.setdefault(more, kind)
                if m.group(1):
                    found.append((offset, more, kind))
    for m in _JS_DESTRUCTURE_RE.finditer(code):
        _note(warnings, f"{source_file} line {_line_of(code, m.start())}: `export {m.group(1)}` destructures, "
                        "and quick mode does not read the names it binds: read them by eye")
    for m in _JS_LIST_RE.finditer(code):
        for piece in m.group(1).split(","):
            # `a`, `a as b`, `type T`, `"a-b" as c`: the exposed name comes last
            words = piece.split()
            if words and _JS_NAME_RE.fullmatch(words[-1]):
                found.append((m.start(), words[-1], "re-export"))
    for m in _JS_STAR_RE.finditer(code):
        if m.group(1):
            found.append((m.start(), m.group(1), "namespace"))
        else:
            spec = _js_string(content, code, m.end(2) - 1)
            _note_unlisted(warnings, unlisted, source_file, _line_of(code, m.start()), f"export * from '{spec}'",
                           spec, ("js", spec))
    for m in _JS_DEFAULT_RE.finditer(code):
        if m.group(1) not in _JS_NOT_NAMES and defaults:
            found.append((m.start(), m.group(1), declared.get(m.group(1), "re-export")))
            read_defaults.add(m.start())
    for m in _JS_ANY_DEFAULT_RE.finditer(code):
        if m.start() in read_defaults or not defaults:
            continue
        line = _line_of(code, m.start())
        if _JS_ANONYMOUS_VALUE_RE.match(code, m.end()):
            _note(warnings, f"{source_file} line {line}: `export default` is an anonymous function or class: "
                            "the module's default export has no name here")
        else:
            _note(warnings, f"{source_file} line {line}: `export default` is set to an expression quick mode "
                            "does not read: read the names it exports by eye")
    for m in _TS_EXPORT_ASSIGN_RE.finditer(code):
        _js_module_exports(content, code, m, source_file, declared, found, warnings, "export =", unlisted)
    for m in _CJS_NAMED_RE.finditer(code):
        if m.group(1) not in _JS_NOT_NAMES:
            found.append((m.start(), m.group(1), _js_value_type(code, m.end(), declared)))
    for m in _CJS_MODULE_RE.finditer(code):
        _js_module_exports(content, code, m, source_file, declared, found, warnings, unlisted=unlisted)
    nested_lines: set[int] = set()
    for m in _CJS_ANY_RE.finditer(code):
        line_start = code.rfind("\n", 0, m.start()) + 1
        if _CJS_CHAIN_RE.fullmatch(code, line_start, m.start()):
            # A statement that opens its line, its first target read above;
            # a later `exports.<name>` of its chain is one more export.
            if m.start() > line_start and m.group(1) and m.group(1) not in _JS_NOT_NAMES:
                found.append((m.start(), m.group(1), _js_value_type(code, m.end(), declared)))
            continue
        line = _line_of(code, m.start())
        if line in nested_lines:
            continue
        nested_lines.add(line)
        target = " ".join(m.group(0).rstrip("=").split())
        require = _JS_REQUIRE_RE.match(code, _JS_SPACE_RE.match(code, m.end()).end())
        if require:
            spec = _js_string(content, code, require.end(1) - 1)
            _note_unlisted(warnings, unlisted, source_file, line, f"{target} = require('{spec}')", spec, ("js", spec))
        else:
            _note(warnings, f"{source_file} line {line}: `{target}` is assigned inside a block or a condition: "
                            "read the names it exports by eye")
    return _exports(found, source_file)


def _py_export_type(binding: dict | None) -> str:
    """The quick-mode type of a name by what binds it in the module."""
    if binding is None or binding["kind"] == "import":
        return "re-export"
    if binding["kind"] == "module-import":
        return "module"
    return binding.get("form", "def")


def _py_all_unread(node: ast.AST | None) -> bool:
    """Whether an `__all__` value holds a part that is no string literal
    (another module's `__all__`, a list built at run time)."""
    if isinstance(node, ast.Constant):
        return not isinstance(node.value, str)
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_py_all_unread(e) for e in node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _py_all_unread(node.left) or _py_all_unread(node.right)
    return True


def _py_all_unread_line(text: str) -> int | None:
    """The line of the first statement that builds `__all__` from a part
    that is no string literal, whose names no reader of this file alone can
    list; None when there is none or the module does not parse."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in _module_statements(tree.body):
        value = None
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if "__all__" in [n for t in targets for n in _target_names(t)]:
                value = node.value
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "__all__"
              and node.value.func.attr in ("extend", "append") and node.value.args):
            value = node.value.args[0]
        if value is not None and _py_all_unread(value):
            return node.lineno
    return None


def scan_exports_python(content: str, source_file: str, warnings: list[str] | None = None,
                        unlisted: list[dict] | None = None) -> list[dict]:
    """The names a Python entry file exports (see "Quick mode" above), read
    with full mode's module reader: __all__ when the module has one, else
    its public definitions and the names it imports from its own
    package."""
    try:
        all_names, bound, stars = _py_bindings(content)
    except SyntaxError as exc:
        _note(warnings, f"{source_file}: this Python cannot parse it ({exc.msg}, line {exc.lineno}); "
                        "its names are read from its text")
        all_names, bound, stars = _py_text_bindings(content)
    # The package an __init__.py opens, whose own modules its absolute imports
    # can name: by any trailing run of its folders, as a nested or namespace
    # package is imported (storage, cloud.storage, acme.cloud.storage).
    packages: list[str] = []
    if posixpath.basename(source_file) == "__init__.py":
        folders = [p for p in posixpath.dirname(source_file).split("/") if p and p != "."]
        packages = [".".join(folders[i:]) for i in range(len(folders))]

    def own(module: str | None, level: int) -> bool:
        return level > 0 or bool(module and any(module == p or module.startswith(p + ".") for p in packages))

    unread = _py_all_unread_line(content)
    if unread is not None:
        _note(warnings, f"{source_file} line {unread}: `__all__` takes names quick mode cannot read (another "
                        "module's `__all__`, or a list built at run time): read the names it exports by eye")
    if all_names is not None:
        return [{"name": name, "type": _py_export_type(bound.get(name)), "source_file": source_file}
                for name in dict.fromkeys(all_names) if name.isidentifier() and not name.startswith("_")]
    found: list[tuple[int, str, str]] = []
    for name, binding in bound.items():
        if name.startswith("_"):
            continue
        if binding["kind"] == "definition" and binding.get("form", "def") in ("def", "class"):
            found.append((binding["line"], name, binding.get("form", "def")))
        elif binding["kind"] == "import" and own(binding["module"], binding["level"]):
            found.append((binding["line"], name, "re-export"))
    for star in stars:
        if own(star["module"], star["level"]):
            source = "." * star["level"] + (star["module"] or "")
            _note_unlisted(warnings, unlisted, source_file, star["line"], f"from {source} import *", source,
                           ("python", star["level"], star["module"]))
    return _exports(found, source_file)


# A `#[macro_export]` macro, exported at the crate root wherever it sits;
# other attributes may stand between the two.
_RUST_MACRO_EXPORT_RE = re.compile(
    r"^[ \t]*#\[macro_export\b[^\]]*\](?:\s*#\[[^\]]*\])*\s*macro_rules!\s*((?:r#)?[A-Za-z_]\w*)", re.M)


def scan_exports_rust(content: str, source_file: str, warnings: list[str] | None = None,
                      unlisted: list[dict] | None = None) -> list[dict]:
    """The names a Rust entry file exports (see "Quick mode" above): its
    column-0 unrestricted `pub` items, `#[macro_export]` macros and `pub
    use` names, read with full mode's readers from its text with comments
    and strings blanked."""
    code = _blank(content, "rust")
    found = [(line, name, kind) for name, kind, line in _rust_items(code)]
    found += [(_line_of(code, m.start(1)), m.group(1), "macro") for m in _RUST_MACRO_EXPORT_RE.finditer(code)]
    for use in _RUST_USE_RE.finditer(code):
        line = _line_of(code, use.start())
        for path, alias, glob in _rust_use_leaves(use.group(1)):
            if path and path[-1] == "self" and not glob:
                path = path[:-1]
            if not path or alias == "_":
                continue
            if glob:
                _note_unlisted(warnings, unlisted, source_file, line, f"pub use {'::'.join(path)}::*",
                               "::".join(path))
            else:
                found.append((line, alias or path[-1], "re-export"))
    return _exports(found, source_file)


def scan_exports_go(content: str, source_file: str, warnings: list[str] | None = None,
                    unlisted: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"^(func|type|var|const)\s+([A-Z]\w*)", content, re.MULTILINE):
        out.append({"name": m.group(2), "type": m.group(1), "source_file": source_file})
    return out


_JAVA_PUBLIC_RE = re.compile(
    r"^\s*public\s+(?:static\s+|final\s+|abstract\s+)*(class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
_JAVA_ANNOTATION_RE = re.compile(
    r"^\s*@(RestController|Service|Component|Configuration|Controller|Repository|Bean)\b",
    re.MULTILINE,
)


def scan_exports_java(content: str, source_file: str, warnings: list[str] | None = None,
                      unlisted: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _JAVA_PUBLIC_RE.finditer(content):
        name = m.group(2)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    # Annotation-marked classes (Spring/Jakarta CDI) — find the annotation, then
    # the next class/interface/enum/record declaration after it.
    for m in _JAVA_ANNOTATION_RE.finditer(content):
        annotation = m.group(1)
        tail = content[m.end():]
        m2 = re.search(r"\b(class|interface|enum|record)\s+(\w+)", tail)
        if m2:
            name = m2.group(2)
            if name not in seen:
                seen.add(name)
                out.append({"name": name, "type": annotation.lower(), "source_file": source_file})
    return out


_KOTLIN_DECL_RE = re.compile(
    r"^(?!\s*(?:internal|private)\b)"
    r"\s*(?:open\s+|sealed\s+|data\s+|abstract\s+)*"
    r"(fun|class|object|interface)\s+(\w+)",
    re.MULTILINE,
)


def scan_exports_kotlin(content: str, source_file: str, warnings: list[str] | None = None,
                        unlisted: list[dict] | None = None) -> list[dict]:
    """Kotlin defaults to public — omit internal/private declarations."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _KOTLIN_DECL_RE.finditer(content):
        name = m.group(2)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    return out


# Swift declarations are public only when explicitly marked `public`/`open`
# (the default is internal). The lazy `[^\n]*?` skips intervening modifiers
# (final/static/class-method/@attributes) between the access keyword and the
# declaration keyword.
_SWIFT_DECL_RE = re.compile(
    r"^\s*(?:public|open)\b[^\n]*?\b"
    r"(func|class|struct|enum|protocol|actor|typealias|var|let)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)
_SWIFT_DECL_KEYWORDS = {
    "func", "class", "struct", "enum", "protocol", "actor", "typealias", "var", "let",
}


def scan_exports_swift(content: str, source_file: str, warnings: list[str] | None = None,
                       unlisted: list[dict] | None = None) -> list[dict]:
    """Swift defaults to internal — emit only public/open declarations."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _SWIFT_DECL_RE.finditer(content):
        name = m.group(2)
        # Guard the rare `public class func foo` case where the lazy skip stops
        # on the `class` modifier and captures the next keyword as the name.
        if name in _SWIFT_DECL_KEYWORDS or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    return out


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

ManifestParser = Callable[[str], dict]
# (content, source file, warnings, unlisted): a scanner may note a form it
# cannot list, and record each statement whose names another module gives.
ExportScanner = Callable[[str, str, list[str], list[dict]], list[dict]]

LANGUAGE_DISPATCH: dict[str, tuple[ManifestParser, ExportScanner]] = {
    "js": (parse_package_json, scan_exports_js),
    "ts": (parse_package_json, scan_exports_js),
    "javascript": (parse_package_json, scan_exports_js),
    "typescript": (parse_package_json, scan_exports_js),
    "python": (parse_pyproject_toml, scan_exports_python),
    "rust": (parse_cargo_toml, scan_exports_rust),
    "go": (parse_go_mod, scan_exports_go),
    "java": (parse_pom_xml, scan_exports_java),
    "kotlin": (parse_gradle, scan_exports_kotlin),
    "swift": (parse_package_swift, scan_exports_swift),
}


def _select_manifest_parser(language: str, manifest_path: str) -> ManifestParser:
    """Pick the right manifest parser, special-casing Python's setup.py and setup.cfg."""
    if language == "python" and manifest_path.endswith("setup.py"):
        return parse_setup_py
    if language == "python" and manifest_path.endswith("setup.cfg"):
        return parse_setup_cfg
    return LANGUAGE_DISPATCH[language][0]


# Release-time placeholder versions that appear in committed manifests but
# resolve to a real version only at publish time. Briefs that silently inherit
# these as the resolved version produce skills tagged with garbage version
# strings; surface them at brief-creation instead.
_PLACEHOLDER_VERSION_PREFIXES = ("workspace:",)
_PLACEHOLDER_VERSION_EXACTS = frozenset({"0.0.0-development", "0.0.0-semantically-released"})


def _detect_placeholder_version(version: str | None) -> str | None:
    """Return the original placeholder string if `version` is a known release-time sentinel, else None."""
    if not version or not isinstance(version, str):
        return None
    v = version.strip().lower()
    if v in _PLACEHOLDER_VERSION_EXACTS:
        return version
    if any(v.startswith(prefix) for prefix in _PLACEHOLDER_VERSION_PREFIXES):
        return version
    return None


def extract(payload: dict) -> dict:
    """Orchestrate manifest parse + export scan for one logical package."""
    warnings: list[str] = []
    language = (payload.get("language") or "").lower()
    if language not in LANGUAGE_DISPATCH:
        return {"_error": f"unknown language: {language!r}; expected one of {sorted(LANGUAGE_DISPATCH)}"}

    manifest = payload.get("manifest") or {}
    manifest_path = (manifest.get("path") or "").strip()
    manifest_content = manifest.get("content") or ""

    if not manifest_content:
        warnings.append("no manifest content provided; metadata will be empty")
        parsed: dict = {}
    else:
        manifest_parser = _select_manifest_parser(language, manifest_path)
        parsed = manifest_parser(manifest_content)
        if "_parse_error" in parsed:
            warnings.append(parsed["_parse_error"])
            parsed = {}

    placeholder = _detect_placeholder_version(parsed.get("version"))
    if placeholder is not None:
        warnings.append(
            f"manifest version {placeholder!r} is a release-time placeholder "
            f"(workspace protocol or semantic-release sentinel) and is not a real version; "
            f"the brief will fall back to user-supplied target_version or the default"
        )
        parsed["version"] = None

    _, scanner = LANGUAGE_DISPATCH[language]
    exports: list[dict] = []
    unlisted: list[dict] = []
    entry_paths: set[str] = set()
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") or ""
        path = entry.get("path") or ""
        entry_paths.add(path)
        if not content:
            continue
        try:
            if entry.get("followed") and scanner is scan_exports_js:
                # `export *` passes on no default export
                exports.extend(scan_exports_js(content, path, warnings, unlisted, defaults=False))
            else:
                exports.extend(scanner(content, path, warnings, unlisted))
        except Exception as e:  # noqa: BLE001 — best-effort: scanner errors are warnings, not fatal
            warnings.append(f"export scan failed for {path}: {e}")

    result = {
        "language": language,
        "package_name": parsed.get("name"),
        "version": parsed.get("version"),
        "description": parsed.get("description"),
        "exports": exports,
        "dependencies": parsed.get("dependencies", []),
        "modules": parsed.get("modules", []),
        "module_folders": [_module_folder(manifest_path, module) for module in parsed.get("modules", [])],
        "warnings": warnings,
        "unlisted": _resolve_unlisted(unlisted, payload.get("tree"), entry_paths, warnings),
    }
    if "_extra" in parsed:
        result["extra"] = parsed["_extra"]
    return result


def _module_folder(manifest_path: str, module: str) -> str:
    """The folder of a Maven or Gradle module in the repository: the
    manifest's folder joined with the module, a Gradle `core:api` read as
    `core/api`."""
    joined = posixpath.join(posixpath.dirname(manifest_path), module.strip(":").replace(":", "/"))
    return posixpath.normpath(joined)


def _resolve_unlisted(unlisted: list[dict], tree: object, entry_paths: set[str],
                      warnings: list[str]) -> list[dict]:
    """The `unlisted` records, each with its `module_file`: the file in the
    listing (`tree`) that the statement's module names, by full mode's
    resolvers (resolve_js_module for `export * from` and `module.exports =
    require(...)`, _py_module_file for a Python star import), else None. A
    record whose module is already an entry file is dropped with its
    warning: its names are read. Without a listing every module_file is
    None, since only the entry files are known."""
    listed = set(tree) if isinstance(tree, list) else None
    known = (listed or set()) | entry_paths
    records = []
    for item in unlisted:
        module, message = item.pop("_module"), item.pop("_warning")
        module_file = None
        if module and module[0] == "js":
            module_file = resolve_js_module(module[1], item["file"], known)
        elif module and module[0] == "python":
            module_file = _py_module_file(posixpath.dirname(item["file"]), module[1], module[2], known)
        if module_file is not None and module_file in entry_paths:
            if message in warnings:
                warnings.remove(message)
            continue
        item["module_file"] = module_file if listed is not None else None
        records.append(item)
    return records


# --------------------------------------------------------------------------
# Full mode: the ast-grep recipe runner
# --------------------------------------------------------------------------

RECIPES_FILE = Path(__file__).resolve().parent.parent / "data" / "ast-grep-recipes.yaml"
RECIPE_SETS = ("standard", "component-library")
RECIPE_LANGUAGES = ("python", "typescript", "tsx", "javascript", "rust", "go")
EXPORT_TYPES = ("function", "class", "const", "interface", "type", "enum", "re-export")
TIERS = ("Quick", "Forge", "Forge+", "Deep")

# A file's extension -> its language here: the ast-grep language its
# recipes run in, or `vue`, a file ast-grep reads as HTML through the
# scratch sgconfig.yml, where the typescript and tsx recipes run in its
# <script> blocks (the Vue note in extraction-patterns-by-hand.md).
EXTENSION_LANGUAGES = {
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
    ".vue": "vue",
}
JS_FAMILY = ("typescript", "tsx", "javascript", "vue")
# A file language -> the language family whose entry points declare its
# exports: TypeScript, JavaScript and .vue files share package.json barrels.
FAMILY_OF = {
    "python": "python",
    "typescript": "javascript",
    "tsx": "javascript",
    "javascript": "javascript",
    "vue": "javascript",
    "rust": "rust",
    "go": "go",
}
FAMILIES = ("javascript", "python", "rust", "go")
# --language (or a brief's language) -> the file languages it selects.
LANGUAGE_FAMILIES = {
    "python": ("python",),
    "rust": ("rust",),
    "go": ("go",),
    "golang": ("go",),
    **{name: JS_FAMILY for name in ("typescript", "ts", "tsx", "javascript", "js", "jsx", "vue")},
}
# Source files no recipe reads, counted in `files_without_recipes`.
NO_RECIPE_EXTENSIONS = frozenset({
    ".java", ".kt", ".kts", ".swift", ".rb", ".php", ".cs", ".scala", ".c", ".h",
    ".cc", ".cpp", ".hpp", ".m", ".mm", ".dart", ".ex", ".exs", ".lua", ".zig",
})
DEFAULT_HEAD_CAP = 200
# (tier, scope type) -> head cap, as extraction-patterns.md's head cap
# selection sets it; DEFAULT_HEAD_CAP otherwise.
HEAD_CAPS = {
    ("Forge+", "full-library"): 500,
    ("Deep", "full-library"): 500,
    ("Forge+", "component-library"): 300,
    ("Deep", "component-library"): 300,
}
SCAN_TIMEOUT_SEC = 600  # per ast-grep call
# The whole run's limit (--timeout), below the 10-minute cap many agents put
# on one shell call, so the JSON is written before the shell stops the run.
DEFAULT_TIMEOUT_SEC = 540
# The most source lines one export's `signature` spans (a formatter splits a
# long parameter list one parameter per line).
SIGNATURE_MAX_LINES = 40
# Characters of file paths per ast-grep call: Windows caps a whole command
# line at 32,767 characters.
ARGV_BUDGET = 24000
SGCONFIG = 'ruleDirs: []\nlanguageGlobs:\n  html: ["*.vue"]\n'
# Rules a scan runs beside the recipes; a match of one is never an export.
SYNTAX_ERROR_RULE = "skf-syntax-error"
STAR_RULE = "skf-star-reexport"
IMPORT_NAMED_RULE = "skf-import-named"
IMPORT_DEFAULT_RULE = "skf-import-default"
IMPORT_NAMESPACE_RULE = "skf-import-namespace"
IMPORT_RULES = (IMPORT_NAMED_RULE, IMPORT_DEFAULT_RULE, IMPORT_NAMESPACE_RULE)
BINDING_RULE = "skf-binding"  # skf-binding-<form>: a top-level binding a local list names
# The build folders a package.json target can name when the build output is
# not committed (`dist/index.js`): the target maps back to its source.
BUILD_DIRS = frozenset({"dist", "build", "lib", "out", "esm", "cjs", "es", "module", "umd", "types", "typings"})
JS_SOURCE_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
JS_RESOLVE_EXTENSIONS = (
    ".ts", ".tsx", ".d.ts", ".mts", ".d.mts", ".cts", ".d.cts", ".js", ".jsx", ".mjs", ".cjs",
)
# A `.js` import specifier names its TypeScript source (`./x.js` -> x.ts).
JS_SOURCE_OF = {
    ".js": (".ts", ".tsx", ".d.ts"),
    ".jsx": (".tsx",),
    ".mjs": (".mts", ".d.mts"),
    ".cjs": (".cts", ".d.cts"),
}
JS_TARGET_SUFFIXES = (".d.mts", ".d.cts", ".d.ts", ".mjs", ".cjs", ".jsx", ".js", ".mts", ".cts", ".tsx", ".ts")
PACKAGE_ENTRY_FIELDS = ("types", "typings", "module", "main", "browser")
WORKSPACE_MANIFESTS = ("package.json", "pnpm-workspace.yaml", "lerna.json", "Cargo.toml", "rush.json", "nx.json")


class RunnerError(Exception):
    """An input full mode cannot use (exit 2)."""


class _Clock:
    """The --timeout of one full run: the seconds left before it runs out."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.end = time.monotonic() + seconds

    def left(self) -> float:
        return self.end - time.monotonic()


_SIBLINGS: dict[str, object] = {}


def _sibling(filename: str):
    """A helper installed beside this script, loaded once as a module:
    skf-source-tree.py (git without the caller's hooks and git variables,
    and a tool lookup that never takes a shim planted in the current
    folder), skf-resolve-authoritative-files.py (the brief's glob rules) and
    skf-detect-workspaces.py (monorepo detection). Raises RunnerError."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        name = "skf_" + filename.removeprefix("skf-").removesuffix(".py").replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RunnerError(f"cannot load {filename} beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError) as exc:
            raise RunnerError(f"cannot load {filename} beside {Path(__file__).name}: {exc}") from exc
        _SIBLINGS[filename] = module
    return module


def _yaml():
    try:
        import yaml  # full mode only; `uv run` installs it from the header
    except ImportError as exc:
        raise RunnerError("full mode reads YAML with PyYAML: run the helper with `uv run`") from exc
    return yaml


def _norm(path: object) -> str:
    """A path or glob as the runner compares them: forward slashes, no
    leading `./` or `/`."""
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------


def _recipe_problem(doc: object) -> str | None:
    """Why `doc` is not a recipe the runner can run, or None."""
    if not isinstance(doc, dict) or not isinstance(doc.get("id"), str) or not doc["id"]:
        return "a document that is not a recipe with an id"
    rid, rule, meta = doc["id"], doc.get("rule"), doc.get("metadata")
    if doc.get("language") not in RECIPE_LANGUAGES or not isinstance(rule, dict) or not isinstance(rule.get("kind"), str):
        return f"{rid}: a language the runner does not know, or a rule that names no kind"
    if not isinstance(meta, dict):
        return f"{rid}: no metadata"
    languages, sets = meta.get("languages"), meta.get("sets")
    if (not isinstance(languages, list) or not languages or languages[0] != doc["language"]
            or not all(language in RECIPE_LANGUAGES for language in languages)):
        return f"{rid}: metadata.languages must list its own language first, then other recipe languages"
    if not isinstance(sets, list) or not sets or not all(s in RECIPE_SETS for s in sets):
        return f"{rid}: metadata.sets must list {' or '.join(RECIPE_SETS)}"
    types = meta.get("export_type")
    types = types if isinstance(types, list) else [types]
    if not types or not all(t in EXPORT_TYPES for t in types):
        return f"{rid}: metadata.export_type must be one of {', '.join(EXPORT_TYPES)}, or a list of them"
    prefer = meta.get("prefer_over", [])
    if not isinstance(prefer, list) or not all(isinstance(p, str) for p in prefer):
        return f"{rid}: metadata.prefer_over must be a list of recipe ids"
    return None


def load_recipe_file(path: Path) -> list[dict]:
    """The recipes in `path`, in file order, each checked for the metadata
    the runner reads: the `recipes` list of a YAML mapping (the module's
    data file), a list, or one recipe per YAML document, as kind-at reads
    them. Raises RunnerError."""
    yaml = _yaml()
    try:
        loaded = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError) as exc:
        raise RunnerError(f"cannot read recipes {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RunnerError(f"malformed YAML in recipes {path}: {exc}") from exc
    docs: list[object] = []
    for doc in loaded:
        if isinstance(doc, dict) and isinstance(doc.get("recipes"), list):
            docs.extend(doc["recipes"])
        elif isinstance(doc, list):
            docs.extend(doc)
        elif doc is not None:
            docs.append(doc)
    if not docs:
        raise RunnerError(f"no recipe in {path}")
    seen: set[tuple[str, str]] = set()
    for doc in docs:
        problem = _recipe_problem(doc)
        for language in [] if problem else doc["metadata"]["languages"]:
            if (doc["id"], language) in seen:
                problem = f"{doc['id']} runs in {language} twice"
            seen.add((doc["id"], language))
        if problem is not None:
            raise RunnerError(f"recipes {path}: {problem}")
    return docs


def _forms(recipes: list[dict]) -> dict[tuple[str, str], dict]:
    """(recipe id, language) -> the recipe form that runs in that language."""
    return {(r["id"], language): r for r in recipes for language in r["metadata"]["languages"]}


def _recipe_rules(recipes: list[dict], languages: set[str]) -> list[dict]:
    """One ast-grep rule per recipe form and language it runs in, among
    `languages`, with `language` rewritten and the metadata left out."""
    rules = []
    for recipe in recipes:
        for language in recipe["metadata"]["languages"]:
            if language in languages:
                rule = {k: v for k, v in recipe.items() if k != "metadata"}
                rule["language"] = language
                rules.append(rule)
    return rules


def _syntax_error_rule(language: str) -> dict:
    """An outermost ERROR node: code the parser could not read."""
    return {"id": SYNTAX_ERROR_RULE, "language": language,
            "rule": {"kind": "ERROR", "not": {"inside": {"kind": "ERROR", "stopBy": "end"}}}}


def _trace_rules(language: str) -> list[dict]:
    """A JS/TS file's `export * from` statements and its imported names,
    which one-level re-export tracing follows."""
    source = {"field": "source", "has": {"kind": "string_fragment", "pattern": "$SOURCE"}}
    clause = {"kind": "import_clause",
              "inside": {"kind": "import_statement", "inside": {"kind": "program"}, "has": source}}
    named = {"kind": "import_specifier", "inside": {"kind": "named_imports", "inside": clause},
             "any": [{"has": {"field": "alias", "pattern": "$NAME"}},
                     {"all": [{"not": {"has": {"field": "alias", "regex": "."}}},
                              {"has": {"field": "name", "pattern": "$NAME"}}]}]}
    star = {"kind": "export_statement", "inside": {"kind": "program"}, "has": source,
            "not": {"any": [{"has": {"kind": "export_clause"}}, {"has": {"kind": "namespace_export"}}]}}
    return [
        {"id": STAR_RULE, "language": language, "rule": star},
        {"id": IMPORT_NAMED_RULE, "language": language, "rule": named},
        {"id": IMPORT_DEFAULT_RULE, "language": language,
         "rule": {"kind": "identifier", "pattern": "$NAME", "inside": clause}},
        {"id": IMPORT_NAMESPACE_RULE, "language": language,
         "rule": {"kind": "identifier", "pattern": "$NAME",
                  "inside": {"kind": "namespace_import", "inside": clause}}},
    ]


# A binding's form -> the export type the recipes record for it exported in
# place, most telling first (a const bound to an arrow function or a
# function expression is a function; an import is a re-export).
BINDING_TYPES = {"function": "function", "class": "class", "enum": "enum", "arrow": "function",
                 "const": "const", "interface": "interface", "type": "type", "import": "re-export"}


def _binding_rules(language: str) -> list[dict]:
    """A JS/TS file's top-level bindings (outside every block and class
    body), one rule per form, whose id ends in it: the types a local
    `export { ... }` list's items take. TypeScript only kinds stay out of
    a javascript rule, which ast-grep would refuse."""
    top = {"not": {"inside": {"any": [{"kind": "statement_block"}, {"kind": "class_body"}], "stopBy": "end"}}}
    named = {"has": {"field": "name", "pattern": "$NAME"}}
    ts = language != "javascript"
    kinds = {
        "function": ["function_declaration", "generator_function_declaration"] + (["function_signature"] if ts else []),
        "class": ["class_declaration"] + (["abstract_class_declaration"] if ts else []),
        "interface": ["interface_declaration"] if ts else [],
        "type": ["type_alias_declaration"] if ts else [],
        "enum": ["enum_declaration"] if ts else [],
    }
    rules = [{"id": f"{BINDING_RULE}-{form}", "language": language,
              "rule": {"any": [{"kind": kind} for kind in found], **named, **top}}
             for form, found in kinds.items() if found]
    declarator = {"kind": "variable_declarator",
                  "has": {"field": "name", "kind": "identifier", "pattern": "$NAME"}, **top}
    value = {"has": {"field": "value", "any": [{"kind": "arrow_function"}, {"kind": "function_expression"},
                                               {"kind": "generator_function"}]}}
    rules.append({"id": f"{BINDING_RULE}-arrow", "language": language, "rule": dict(declarator, all=[value])})
    rules.append({"id": f"{BINDING_RULE}-const", "language": language, "rule": declarator})
    return rules + [r for r in _trace_rules(language) if r["id"] in IMPORT_RULES]


def _binding_types(matches: list[dict]) -> dict[tuple[str, str], str]:
    """(file, name) -> the export type of the top-level binding `name` has
    in that file, from the matches of _binding_rules."""
    rank = list(BINDING_TYPES)
    best: dict[tuple[str, str], str] = {}
    for m in matches:
        form = "import" if m["rule"] in IMPORT_RULES else m["rule"].removeprefix(f"{BINDING_RULE}-")
        if form in BINDING_TYPES and m["name"]:
            key = (m["file"], m["name"])
            if key not in best or rank.index(form) < rank.index(best[key]):
                best[key] = form
    return {key: BINDING_TYPES[form] for key, form in best.items()}


# --------------------------------------------------------------------------
# Files in scope
# --------------------------------------------------------------------------


def _hidden(path: str) -> bool:
    return any(part.startswith(".") for part in path.split("/"))


def _git_files(root: Path) -> list[str] | None:
    """The files git lists under `root` (tracked, and untracked but not
    ignored), or None when git is missing or `root` is no work tree."""
    try:
        res = _sibling("skf-source-tree.py")._git(
            root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    except RunnerError:
        return None
    if res is None or res[0] != 0:
        return None
    files = []
    for raw in res[1].split(b"\0"):
        rel = os.fsdecode(raw).replace("\\", "/") if raw else ""
        if rel and (root / rel).is_file() and not (root / rel).is_symlink():
            files.append(rel)
    return files


def _walked_files(root: Path) -> list[str]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d)))
        for name in filenames:
            if not name.startswith(".") and not os.path.islink(os.path.join(dirpath, name)):
                files.append(f"{rel_dir}/{name}" if rel_dir else name)
    return files


def list_tree(root: Path) -> list[str]:
    """The files under `root` a scan may read, as sorted POSIX paths
    relative to it: those git lists when `root` is in a git work tree (so
    .gitignore holds, as in ast-grep's own walk), else every file, as when
    git lists none (a folder the work tree ignores). Hidden entries and
    symbolic links are left out either way."""
    listed = _git_files(root) or _walked_files(root)
    return sorted(p for p in listed if not _hidden(p))


def _file_language(path: str) -> str | None:
    return EXTENSION_LANGUAGES.get(posixpath.splitext(path)[1].lower())


def _rule_languages(file_language: str) -> tuple[str, ...]:
    """The recipe languages that run in a file of `file_language`."""
    return ("typescript", "tsx") if file_language == "vue" else (file_language,)


def _wanted_languages(values: list[str]) -> tuple[set[str], list[str]]:
    """The file languages the --language values select, and the values no
    recipe language family knows. No value selects every language."""
    if not values:
        return set(EXTENSION_LANGUAGES.values()), []
    wanted: set[str] = set()
    unknown = []
    for value in values:
        family = LANGUAGE_FAMILIES.get(str(value).strip().lower())
        if family is None:
            unknown.append(str(value))
        else:
            wanted.update(family)
    return wanted, unknown


def _read_file_list(path: Path) -> list[str]:
    """--files-from: a JSON list of paths when the whole text is one, else
    one path per line, so a first path such as `[slug]/page.tsx` is a path."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RunnerError(f"cannot read file list {path}: {exc}") from exc
    items = None
    if text.lstrip().startswith("["):
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            items = value
    if items is None:
        items = text.splitlines()
    return list(dict.fromkeys(rel for rel in (_norm(item) for item in items) if rel))


def _read_brief(path: Path) -> dict:
    """The scope fields and language of a skill brief."""
    yaml = _yaml()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RunnerError(f"cannot read brief {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RunnerError(f"brief {path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RunnerError(f"brief {path} is not a YAML mapping")
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}

    def strings(value: object) -> list[str]:
        return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

    return {
        "language": data.get("language") if isinstance(data.get("language"), str) else None,
        "type": scope.get("type") if isinstance(scope.get("type"), str) else None,
        "include": strings(scope.get("include")),
        "exclude": strings(scope.get("exclude")),
        "tier_a_include": strings(scope.get("tier_a_include")),
    }


# --------------------------------------------------------------------------
# Running ast-grep
# --------------------------------------------------------------------------


def _batches(files: list[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    size = 0
    for rel in files:
        if batch and size + len(rel) + 3 > ARGV_BUDGET:
            yield batch
            batch, size = [], 0
        batch.append(rel)
        size += len(rel) + 3
    if batch:
        yield batch


def _position(node: object) -> int | None:
    """The 1-based line a JSON match (or metavariable) starts on."""
    if not isinstance(node, dict):
        return None
    line = ((node.get("range") or {}).get("start") or {}).get("line")
    return line + 1 if isinstance(line, int) and not isinstance(line, bool) else None


_SIGNATURE_QUOTES = {"python": "'\"", "rust": '"'}  # a Rust `'a` is a lifetime


def _code_end(text: str, language: str, depth: int) -> tuple[int, int]:
    """(the bracket depth after `text`, one source line, where its line
    comment starts, else its length): each ( or [ outside a string opens
    one, each ) or ] closes one."""
    quotes = _SIGNATURE_QUOTES.get(language, "'\"`")
    comment = "#" if language == "python" else "//"
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in quotes:
            quote = ch
        elif text.startswith(comment, i):
            return depth, i
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        i += 1
    return depth, len(text)


def _declaration_signature(rows: list[str], start: int, language: str) -> str:
    """The declaration a match names, on one line: the source line holding
    `$NAME`, and, while a ( or [ it opens is still open at a line's end (or
    a generic's < that ends the line, outside Python), the lines after it
    (at most SIGNATURE_MAX_LINES), each without its line comment, as is a
    one-line declaration. A parameter list a formatter split one parameter
    per line, its trailing comma included, reads as its one-line form does:
    `def f(a: int, b: str) -> R:`, and so does a destructured parameter
    (`({ a, b }: Props) => {`) or a split generic (`f<T, U>(a: T)`). A {
    adds no depth: it opens a body, an interface or an object as often as a
    parameter, and a ( or [ around it already holds the line open."""
    out, depth, angle = "", 0, 0
    for row in rows[start:start + SIGNATURE_MAX_LINES]:
        text = row.strip()
        if out and angle and text.startswith(">"):
            angle -= 1
        depth, end = _code_end(text, language, depth)
        piece = text[:end].rstrip()
        if language != "python" and piece.endswith("<"):
            angle += 1
        if not out:
            out = piece
        elif piece:
            if piece[0] in ")]}>" and out.endswith(","):
                out = out[:-1]
            out += piece if out[-1] in "([<" or piece[0] in ")]>" else " " + piece
        if depth <= 0 and angle <= 0:
            break
    return out


def _parse_match(raw: object) -> dict | None:
    """One `--json=stream` match: its rule, language, file, `$NAME`'s line
    (the match's own first line when it binds no `$NAME`), `$NAME`,
    `$SOURCE`, the source line holding `$NAME` (from `lines`, the whole
    lines the match spans, so a list item gives its full line), the
    declaration signature that line opens (_declaration_signature) and the
    match text."""
    first = _position(raw)
    if first is None:
        return None
    single = (raw.get("metaVariables") or {}).get("single") or {}
    name_var, source_var = single.get("NAME"), single.get("SOURCE")
    name, line = None, first
    if isinstance(name_var, dict):
        name = str(name_var.get("text") or "")
        line = _position(name_var) or first
    text = str(raw.get("text") or "")
    rows = str(raw.get("lines") or text).split("\n")
    row = min(max(line - first, 0), len(rows) - 1)
    language = str(raw.get("language") or "").lower()
    return {
        "rule": str(raw.get("ruleId") or ""),
        "language": language,
        "file": _norm(raw.get("file")),
        "line": line,
        "start_line": first,
        "name": name,
        "source": (str(source_var.get("text") or "") or None) if isinstance(source_var, dict) else None,
        "signature_line": rows[row].strip(),
        "signature": _declaration_signature(rows, row, language),
        "text": text,
    }


def _scan(exe: str, root: Path, folder: Path, rules: list[dict], files: list[str],
          errors: list[dict], clock: _Clock | None = None) -> list[dict]:
    """ast-grep's matches of `rules` in `files` (relative to `root`), in
    batches. The rules go in a file as JSON documents (YAML reads JSON),
    never on the command line. A call that times out, exits non-zero (its
    rules carry no severity, so a scan that read every file exits 0, matches
    or not) or prints other than JSON lines adds to `errors`: its batch's
    files may be unread. The matches it printed are kept. When `clock` (the
    run's --timeout) runs out, the call running is stopped and no other
    starts: one `time-limit` item names every file left unread."""
    if not rules or not files:
        return []
    rule_file = folder / "rules.yml"
    rule_file.write_text("\n---\n".join(json.dumps(r, ensure_ascii=False) for r in rules) + "\n",
                         encoding="utf-8")
    config = folder / "sgconfig.yml"
    config.write_text(SGCONFIG, encoding="utf-8")
    found = []
    batches = list(_batches(files))
    for index, batch in enumerate(batches):
        left = None if clock is None else clock.left()
        if left is not None and left <= 0:
            unread = [rel for rest in batches[index:] for rel in rest]
            errors.append({"reason": "time-limit", "files": len(unread), "first_file": unread[0],
                           "detail": f"the --timeout of {clock.seconds:g}s ran out before ast-grep read them",
                           "unread": unread})
            break
        limit = SCAN_TIMEOUT_SEC if left is None else min(SCAN_TIMEOUT_SEC, left)
        cmd = [exe, "scan", "--config", str(config), "-r", str(rule_file), "--json=stream", "--", *batch]
        failure = None
        try:
            res = subprocess.run(cmd, cwd=root, capture_output=True, timeout=limit, check=False)
        except subprocess.TimeoutExpired:
            if clock is not None and clock.left() <= 0:
                failure = ("time-limit", f"the --timeout of {clock.seconds:g}s ran out while ast-grep read them")
            else:
                failure = ("ast-grep-timeout", f"no answer in {limit:g}s")
        except (OSError, ValueError) as exc:
            failure = ("ast-grep-error", f"{type(exc).__name__}: {exc}")
        else:
            stdout = res.stdout.decode("utf-8", errors="replace")
            if res.returncode != 0:
                stderr = res.stderr.decode("utf-8", errors="replace")
                detail = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
                failure = ("ast-grep-error", f"exit {res.returncode}: {detail}")
            for raw in stdout.splitlines():
                if not raw.strip():
                    continue
                try:
                    match = _parse_match(json.loads(raw))
                except ValueError:
                    failure = failure or ("ast-grep-error", "output is not JSON lines")
                    break
                if match is not None:
                    found.append(match)
        if failure is not None:
            error = {"reason": failure[0], "files": len(batch), "first_file": batch[0], "detail": failure[1]}
            if failure[0] == "time-limit":
                error["unread"] = list(batch)
            errors.append(error)
    return found


def _native_ast_grep(exe: str) -> str | None:
    """The executable a scan runs for `exe`, the ast-grep PATH gives: `exe`
    itself, or for an npm `.cmd` or `.bat` shim (Windows) the native
    ast-grep.exe it wraps, which @ast-grep/cli's postinstall puts in its
    package folder (node_modules/@ast-grep/cli beside a global install's
    shim, ../@ast-grep/cli from node_modules/.bin), else its platform
    package's. None when neither holds one: a shim runs through cmd.exe,
    which would read the `&`, `^` and `%` of the repository paths a scan
    passes as its own syntax."""
    if not exe.lower().endswith((".cmd", ".bat")):
        return exe
    shim_dir = Path(exe).parent
    for scope in (shim_dir / "node_modules" / "@ast-grep", shim_dir.parent / "@ast-grep"):
        for package in [scope / "cli", *sorted(scope.glob("cli-win32-*"))]:
            native = package / "ast-grep.exe"
            if native.is_file():
                return str(native)
    return None


def _ast_grep() -> tuple[str | None, str | None, str | None]:
    """(the ast-grep executable a scan runs, its version, the npm shim PATH
    gives when no native binary backs it), each None when unknown."""
    exe = _sibling("skf-source-tree.py")._resolve_outside_cwd("ast-grep")
    if exe is None:
        return None, None, None
    native = _native_ast_grep(exe)
    if native is None:
        return None, None, exe
    try:
        res = subprocess.run([native, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return native, None, None
    words = res.stdout.split()
    return native, (words[-1] if res.returncode == 0 and words else None), None


# --------------------------------------------------------------------------
# Merging the matches into exports
# --------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z_$][\w$]*")


def _keyword_type(text: str, name: str, choices: list[str]) -> str:
    """The last of `choices` that stands as a word before `name` in the
    match text (`export declare const enum E` -> enum)."""
    picked = choices[0]
    for word in _WORD_RE.findall(text):
        if word == name:
            break
        if word in choices:
            picked = word
    return picked


def _export_record(match: dict, form: dict) -> dict:
    export_type = form["metadata"]["export_type"]
    if isinstance(export_type, list):
        export_type = _keyword_type(match["text"], match["name"], export_type)
    params, return_type = (signature_parts(match["signature"], match["language"], match["name"])
                           if export_type == "function" else (None, None))
    return {
        "export_name": match["name"],
        "source_file": match["file"],
        "source_line": match["line"],
        "signature_line": match["signature_line"],
        "signature": match["signature"],
        "params": params,
        "return_type": return_type,
        "citation": f"[AST:{match['file']}:L{match['line']}]",
        "ast_recipe": match["rule"],
        "ast_node_type": form["rule"]["kind"],
        "export_type": export_type,
        "language": match["language"],
        "from": match["source"],
        "from_file": None,
        "confidence": "T1",
        "extraction_method": "ast-grep",
    }


# --------------------------------------------------------------------------
# A function's parameters and return type, read from its one-line signature
# --------------------------------------------------------------------------

_OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}


def _split_top(text: str, sep: str, angle: bool = True, quotes: str = "'\"`") -> list[str]:
    """`text` split at each `sep` outside brackets and strings (`<` counts
    as a bracket when `angle`, and the `>` of `=>` or `->` closes none).
    `quotes` are the characters that open a string: only `"` in Rust, whose
    `'a` is a lifetime."""
    parts, depth, quote, start, i = [], 0, None, 0, 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in quotes:
            quote = ch
        elif ch in "([{" or (angle and ch == "<"):
            depth += 1
        elif ch in ")]}" or (angle and ch == ">" and text[i - 1:i] not in ("=", "-")):
            depth -= 1
        elif depth == 0 and text.startswith(sep, i) and not (sep == "=" and text[i + 1:i + 2] in ("=", ">")):
            parts.append(text[start:i])
            start = i + len(sep)
            i = start
            continue
        i += 1
    parts.append(text[start:])
    return parts


def _close(text: str, start: int, angle: bool = True, quotes: str = "'\"`") -> int | None:
    """The index of the bracket that closes the one at `start`, else None
    (strings as _split_top reads them)."""
    depth, quote, i = 0, None, start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in quotes:
            quote = ch
        elif ch in "([{" or (angle and ch == "<"):
            depth += 1
        elif ch in ")]}" or (angle and ch == ">" and text[i - 1:i] not in ("=", "-")):
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _param(name: str | None, type_: str | None, default: str | None, optional: bool) -> dict:
    return {"name": name or None, "type": type_ or None, "default": default or None, "optional": optional}


def _python_parts(signature: str) -> tuple[list[dict] | None, str | None]:
    """A Python def's parameters and return annotation, through its own
    parser, each as the source writes it."""
    head = signature.strip()
    if head.endswith(":"):
        head = head[:-1]
    source = head + ": pass"
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, None
    node = tree.body[0] if tree.body else None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None, None
    a = node.args
    positional = a.posonlyargs + a.args
    defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
    params = []

    def text(value):
        # the source's own text (`"x"`, `0x10`), never ast.unparse's normal form (`'x'`, `16`)
        return (ast.get_source_segment(source, value) or ast.unparse(value)) if value is not None else None

    for arg, default in zip(positional, defaults):
        params.append(_param(arg.arg, text(arg.annotation), text(default), default is not None))
    if a.vararg is not None:
        params.append(_param("*" + a.vararg.arg, text(a.vararg.annotation), None, True))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        params.append(_param(arg.arg, text(arg.annotation), text(default), default is not None))
    if a.kwarg is not None:
        params.append(_param("**" + a.kwarg.arg, text(a.kwarg.annotation), None, True))
    return params, text(node.returns)


def _js_param(part: str) -> dict | None:
    """One JS/TS parameter: `name`, `name?: T`, `name: T = d`, `...rest: T[]`
    or a destructuring pattern; None for TypeScript's `this` parameter."""
    part = part.strip()
    default = None
    pieces = _split_top(part, "=")
    if len(pieces) > 1:
        part, default = pieces[0].strip(), "=".join(pieces[1:]).strip()
    typed = _split_top(part, ":")
    name, type_ = typed[0].strip(), (":".join(typed[1:]).strip() if len(typed) > 1 else None)
    optional = default is not None or name.startswith("...")
    if name.endswith("?"):
        name, optional = name[:-1].rstrip(), True
    if name == "this":
        return None
    return _param(name, type_, default, optional)


def _js_parts(signature: str, name: str) -> tuple[list[dict] | None, str | None]:
    """An exported JS/TS function's parameters and return type: a function
    declaration (`function name<T>(...): R {`), or a const bound to an arrow
    function (`const name = async <T>(...): R => ...`, `const name = x => ...`)."""
    # `$` is an identifier character in JS, so `\b` would never bound `$fetch`
    at = re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", signature)
    if at is None:
        return None, None
    rest = signature[at.end():]
    arrow = re.match(r"\s*(?::[^=]*?)?=\s*(?:async\s+)?", rest)
    if arrow and not re.match(r"\s*\(", rest):
        rest = rest[arrow.end():]
        bare = re.match(r"([A-Za-z_$][\w$]*)\s*=>", rest)
        if bare:
            return [_param(bare.group(1), None, None, False)], None
    else:
        arrow = None
    rest = rest.lstrip()
    if rest.startswith("<"):
        end = _close(rest, 0)
        if end is None:
            return None, None
        rest = rest[end + 1:].lstrip()
    if not rest.startswith("("):
        return None, None
    end = _close(rest, 0)
    if end is None:
        return None, None
    inner = rest[1:end].strip()
    params = [p for p in (_js_param(part) for part in _split_top(inner, ",") if part.strip()) if p is not None]
    tail = rest[end + 1:].strip()
    if not tail.startswith(":"):
        return params, None
    tail = tail[1:].strip()
    if arrow is not None:
        pieces = _split_top(tail, "=>")
        if len(pieces) < 2:
            return None, None
        returns = pieces[0].strip()
    else:
        returns = tail[:-1].rstrip() if tail.endswith(("{", ";")) else tail
    return (params, returns) if returns else (None, None)


def _rust_parts(signature: str, name: str) -> tuple[list[dict] | None, str | None]:
    """A Rust fn's parameters (`self` forms included) and its `->` type."""
    at = re.search(r"\bfn\s+" + re.escape(name) + r"\b", signature)
    if at is None:
        return None, None
    rest = signature[at.end():].lstrip()
    if rest.startswith("<"):
        end = _close(rest, 0, quotes='"')
        if end is None:
            return None, None
        rest = rest[end + 1:].lstrip()
    if not rest.startswith("("):
        return None, None
    end = _close(rest, 0, angle=False, quotes='"')
    if end is None:
        return None, None
    params = []
    for part in _split_top(rest[1:end], ",", quotes='"'):
        part = part.strip()
        if not part:
            continue
        typed = _split_top(part, ":", quotes='"')
        if len(typed) == 1:
            params.append(_param(part, None, None, False))  # self, &self, &mut self
        else:
            params.append(_param(typed[0].strip(), ":".join(typed[1:]).strip(), None, False))
    tail = rest[end + 1:].strip()
    if not tail.startswith("->"):
        return params, None
    returns = re.split(r"\s+where\s+", tail[2:].strip(), maxsplit=1)[0].strip()
    returns = returns[:-1].rstrip() if returns.endswith(("{", ";")) else returns
    return (params, returns) if returns else (None, None)


_GO_TYPE_WORDS = frozenset({"chan", "func", "map", "struct", "interface"})


def _go_parts(signature: str, name: str) -> tuple[list[dict] | None, str | None]:
    """A Go func's parameters (a type shared by the names before it, as in
    `a, b int`, given to each) and its result list or type."""
    at = re.search(r"\bfunc\s+" + re.escape(name) + r"\b", signature)
    if at is None:
        return None, None
    rest = signature[at.end():].lstrip()
    if rest.startswith("["):
        end = _close(rest, 0, angle=False, quotes='"`')
        if end is None:
            return None, None
        rest = rest[end + 1:].lstrip()
    if not rest.startswith("("):
        return None, None
    end = _close(rest, 0, angle=False, quotes='"`')
    if end is None:
        return None, None
    parts = [p.strip() for p in _split_top(rest[1:end], ",", angle=False, quotes='"`') if p.strip()]
    # `a, b int` names its parameters; `chan int` alone is a type
    named = any(re.match(r"[A-Za-z_]\w*\s+\S", p) and p.split(None, 1)[0] not in _GO_TYPE_WORDS for p in parts)
    params: list[dict] = []
    pending: list[str] = []
    for part in parts:
        if not named:
            params.append(_param(None, part, None, part.startswith("...")))
            continue
        words = part.split(None, 1)
        if len(words) == 1:
            pending.append(words[0])
            continue
        type_ = words[1].strip()
        for waiting in pending + [words[0]]:
            params.append(_param(waiting, type_, None, type_.startswith("...")))
        pending = []
    if pending:
        return None, None
    tail = rest[end + 1:].strip()
    tail = tail[:-1].rstrip() if tail.endswith("{") else tail
    return params, (tail or None)


def signature_parts(signature: str, language: str, name: str) -> tuple[list[dict] | None, str | None]:
    """(params, return_type) of an exported function, read from the
    one-line `signature` its recipe matched: each parameter as {name, type,
    default, optional}, and the declared return type, null when the
    declaration states none. (None, None) when the signature is a form this
    reader does not parse, such as a declaration cut at its line cap."""
    if language == "python":
        return _python_parts(signature)
    if language in ("typescript", "tsx", "javascript"):
        return _js_parts(signature, name)
    if language == "rust":
        return _rust_parts(signature, name)
    if language == "go":
        return _go_parts(signature, name)
    return None, None


def _preferred(at_line: list[dict], forms: dict, order: dict[str, int]) -> dict:
    """The match an export records among several recipes' matches of one
    name on one line: one that no other lists under prefer_over, then the
    first in the recipe file."""
    ids = {m["rule"] for m in at_line}
    beaten = {loser for m in at_line
              for loser in forms[(m["rule"], m["language"])]["metadata"].get("prefer_over", [])
              if loser in ids and loser != m["rule"]}
    left = [m for m in at_line if m["rule"] not in beaten] or at_line
    return min(left, key=lambda m: (order[m["rule"]], m["language"]))


def merge_exports(matches: list[dict], recipes: list[dict], recipe_set: str,
                  head_cap: int | None) -> tuple[list[dict], list[dict]]:
    """(exports, per-recipe stats) from the matches of one recipe set: at
    most `head_cap` matches of each recipe, in file and line order, merged
    by (file, name) at the first line that names it."""
    forms = _forms(recipes)
    order: dict[str, int] = {}
    languages: dict[str, list[str]] = {}
    for recipe in recipes:
        if recipe_set in recipe["metadata"]["sets"]:
            order.setdefault(recipe["id"], len(order))
            langs = languages.setdefault(recipe["id"], [])
            langs.extend(lang for lang in recipe["metadata"]["languages"] if lang not in langs)
    per_recipe: dict[str, list[dict]] = {rid: [] for rid in order}
    for m in matches:
        if m["rule"] in per_recipe and m["name"] and not m["name"].startswith("_") and (m["rule"], m["language"]) in forms:
            per_recipe[m["rule"]].append(m)
    stats, kept = [], []
    for rid, found in per_recipe.items():
        found.sort(key=lambda m: (m["file"], m["line"], m["name"]))
        cut = head_cap is not None and len(found) > head_cap
        stats.append({"id": rid, "languages": languages[rid], "matches": len(found), "truncated": cut})
        kept.extend(found[:head_cap] if cut else found)
    groups: dict[tuple[str, str], list[dict]] = {}
    for m in kept:
        groups.setdefault((m["file"], m["name"]), []).append(m)
    exports = []
    for group in groups.values():
        first_line = min(m["line"] for m in group)
        chosen = _preferred([m for m in group if m["line"] == first_line], forms, order)
        exports.append(_export_record(chosen, forms[(chosen["rule"], chosen["language"])]))
    exports.sort(key=lambda e: (e["source_file"], e["source_line"], e["export_name"]))
    return exports, stats


def _syntax_issues(matches: list[dict]) -> list[dict]:
    """One `syntax-errors` issue per file with an outermost ERROR node."""
    per_file: dict[str, tuple[int, int]] = {}
    for m in matches:
        if m["rule"] == SYNTAX_ERROR_RULE:
            count, line = per_file.get(m["file"], (0, m["start_line"]))
            per_file[m["file"]] = (count + 1, min(line, m["start_line"]))
    return [{"file": f, "issue": "syntax-errors", "count": c, "line": ln}
            for f, (c, ln) in sorted(per_file.items())]


def _type_list_items(exe: str, root: Path, folder: Path, matches: list[dict], exports: list[dict],
                     errors: list[dict], clock: _Clock | None = None) -> None:
    """Give each export a local `export { ... }` list names (an
    export_specifier with no `from`) the type of the top-level binding it
    names in its file, as BINDING_TYPES has it; the recipe's own
    export_type stays when no such binding has the name (a destructured
    one)."""
    items = [e for e in exports if e["ast_node_type"] == "export_specifier" and e["from"] is None]
    if not items:
        return
    local: dict[tuple[str, str, str], str] = {}
    for m in matches:
        if m["name"] and m["source"] is None:
            local.setdefault((m["file"], m["rule"], m["name"]), _specifier_local(m["text"]))
    files = sorted({e["source_file"] for e in items})
    languages = sorted({lang for f in files for lang in _rule_languages(_file_language(f) or "")}
                       & set(RECIPE_LANGUAGES))
    rules = [rule for language in languages for rule in _binding_rules(language)]
    types = _binding_types(_scan(exe, root, folder, rules, files, errors, clock))
    for e in items:
        name = local.get((e["source_file"], e["ast_recipe"], e["export_name"]), e["export_name"])
        e["export_type"] = types.get((e["source_file"], name), e["export_type"])


# --------------------------------------------------------------------------
# Comments and strings, blanked for the text readers below
# --------------------------------------------------------------------------

_RUST_RAW_OPEN_RE = re.compile(r'r(#*)"')
_RUST_CHAR_RE = re.compile(r"'(?:\\(?:x[0-9A-Fa-f]{2}|u\{[0-9A-Fa-f]{1,6}\}|.)|[^\\'\n])'")
# What a JavaScript `/` follows when it opens a regular expression literal
# rather than dividing: punctuation no operand ends with, or a keyword.
_JS_REGEX_AFTER = frozenset("(,=:[!&|?{};")
_JS_REGEX_AFTER_WORDS = frozenset({
    "return", "typeof", "case", "do", "else", "in", "of", "instanceof", "new", "delete", "void", "throw",
    "yield", "await",
})


def _js_regex_end(text: str, done: list[str], i: int) -> int | None:
    """The index of the `/` that closes the regular expression literal the
    `/` at `i` opens, or None when that `/` divides. `done` is the text up
    to `i` with its comments and strings blanked; a literal opens a line or
    follows _JS_REGEX_AFTER or a word of _JS_REGEX_AFTER_WORDS (a `}` before
    a JSX `/>` aside), and ends on its line."""
    k = i - 1
    while k >= 0 and done[k] in " \t\r":
        k -= 1
    before = done[k] if k >= 0 else "\n"
    if before == "}" and text.startswith(">", i + 1):
        return None
    if before != "\n" and before not in _JS_REGEX_AFTER:
        end = k + 1
        while k >= 0 and (done[k].isalnum() or done[k] in "_$"):
            k -= 1
        if "".join(done[k + 1:end]) not in _JS_REGEX_AFTER_WORDS or (k >= 0 and done[k] == "."):
            return None
    in_class, j = False, i + 1
    while j < len(text) and text[j] != "\n":
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            return j
        j += 1
    return None


def _blank(text: str, language: str) -> str:
    """`text` with its comments, and the insides of its strings, turned into
    spaces, its lines kept: a pattern run over it finds code only.
    JavaScript/TypeScript (`js`): `//`, `/* */` and '...', "..." and `...`
    strings, a string followed within its line (a template literal spanning
    lines is not tracked), and the insides of a regular expression literal
    (`/\\/*$/` opens no comment). Go: `//`, `/* */`, "..." and '...' within a
    line and `...` raw strings across lines. Rust: `//`, nested `/* */`,
    "..." and r#"..."# strings across lines, and char literals."""
    out = list(text)
    n = len(text)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    quotes = "\"'`" if language in ("js", "go") else '"'
    i = 0
    while i < n:
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
            continue
        if text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if language == "rust" and text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(i, j)
            i = j
            continue
        ch = text[i]
        if language == "js" and ch == "/":
            end = _js_regex_end(text, out, i)
            if end is not None:
                blank(i + 1, end)
                i = end + 1
                continue
        if language == "rust":
            raw = _RUST_RAW_OPEN_RE.match(text, i) if ch == "r" else None
            if raw and not (i and (text[i - 1].isalnum() or text[i - 1] == "_")):
                close = '"' + raw.group(1)
                end = text.find(close, raw.end())
                end = n if end < 0 else end
                blank(raw.end(), end)
                i = end + len(close)
                continue
            char = _RUST_CHAR_RE.match(text, i) if ch == "'" else None
            if char:
                i = char.end()
                continue
        if ch in quotes:
            across = language == "rust" or (language == "go" and ch == "`")
            escapes = not (language == "go" and ch == "`")
            j = i + 1
            while j < n and text[j] != ch and (across or text[j] != "\n"):
                j += 2 if escapes and text[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1 if j < n and text[j] == ch else j
            continue
        i += 1
    return "".join(out)


def _read_text(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------------
# Entry points: JavaScript and TypeScript
# --------------------------------------------------------------------------

_JS_DECLARATION_RE = re.compile(
    r"^export\s+(?:declare\s+)?(default\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:const\s+enum|const|let|var|function\s*\*?|class|interface|type|enum|namespace|module)"
    r"\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_JS_IMPORT_EQUALS_RE = re.compile(r"^export\s+import()\s+([A-Za-z_$][\w$]*)\s*=", re.M)
_JS_DEFAULT_NAME_RE = re.compile(r"^export\s+default\s+([A-Za-z_$][\w$]*)\s*;?\s*$", re.M)
_JS_DEFAULT_EXPORT_RE = re.compile(r"export\s+default\b")


def _js_text_names(text: str) -> tuple[list[tuple[str, int, bool]], list[tuple[str, int]]]:
    """The names a JS/TS file's column-0 `export` declarations bind, read
    from its text for the forms no recipe matches (`export let`, `export
    declare const`, `export namespace`), as (name, line, is the default
    export), and its `export default <name>;` statements, as (name, line)."""
    code = _blank(text, "js")
    declared = [(m.group(2), _line_of(code, m.start(2)), bool(m.group(1)))
                for rx in (_JS_DECLARATION_RE, _JS_IMPORT_EQUALS_RE) for m in rx.finditer(code)]
    defaults = [(m.group(1), _line_of(code, m.start(1))) for m in _JS_DEFAULT_NAME_RE.finditer(code)]
    return declared, defaults


def resolve_js_module(spec: str | None, from_file: str, tree: set[str]) -> str | None:
    """The file a relative import or re-export names: the path, then with
    each JS/TS extension, then its index file, a `.js` specifier naming its
    TypeScript source first. None for a package name or a path outside the
    root."""
    if not spec or not spec.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_file), spec))
    if base == ".." or base.startswith("../"):
        return None
    base = "" if base == "." else base
    stem, ext = posixpath.splitext(base)
    candidates = [base] if base else []
    candidates += [stem + e for e in JS_SOURCE_OF.get(ext, ())]
    candidates += [base + e for e in JS_RESOLVE_EXTENSIONS]
    candidates += [posixpath.join(base, "index" + e) for e in JS_RESOLVE_EXTENSIONS]
    return next((c for c in candidates if c in tree), None)


def _targets(value: object) -> list[str]:
    """Every target path of a package.json `exports` value, conditions and
    fallbacks included."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [t for item in value for t in _targets(item)]
    if isinstance(value, dict):
        return [t for item in value.values() for t in _targets(item)]
    return []


def exports_subpaths(exports: object) -> dict[str, list[str]]:
    """A package.json `exports` value as {subpath: its target paths}."""
    if isinstance(exports, dict):
        keys = [k for k in exports if isinstance(k, str)]
        if keys and all(k.startswith(".") for k in keys):
            return {k: _targets(exports[k]) for k in keys}
    targets = _targets(exports)
    return {".": targets} if targets else {}


def _source_stems(rel: str) -> list[str]:
    """The stems a build output's source can have, in the order tried: the
    path without its extension, then with one more of its leading build
    folders swapped for `src/` or dropped at each try (`dist/esm/index.js`
    -> dist/esm/index, src/esm/index, esm/index, src/index, index)."""
    stem = next((rel[: -len(s)] for s in JS_TARGET_SUFFIXES if rel.endswith(s)), rel)
    parts = stem.split("/")
    stems = [stem]
    for depth in range(1, len(parts)):
        if parts[depth - 1] not in BUILD_DIRS:
            break
        rest = "/".join(parts[depth:])
        stems += [f"src/{rest}", rest]
    return stems


def _package_target(pkg: str, target: str, tree: set[str]) -> tuple[str | None, str]:
    """(the file a package.json target names, `file`), or, for a build
    output that is not committed, (its source, `source-guess`): each of its
    source stems with each source extension (`dist/esm/index.js` ->
    src/index.ts, `build/lib/util.js` -> lib/util.ts)."""

    def join(rel: str) -> str:
        return f"{pkg}/{rel}" if pkg else rel

    rel = posixpath.normpath(_norm(target))
    if rel in (".", "..") or rel.startswith("../"):
        return None, "unresolved"
    if join(rel) in tree:
        return join(rel), "file"
    for stem in _source_stems(rel):
        for ext in JS_SOURCE_EXTENSIONS:
            if join(stem + ext) in tree:
                return join(stem + ext), "source-guess"
    return None, "unresolved"


def _pattern_files(pkg: str, pattern: str, tree: set[str]) -> dict[str, str]:
    """{what the `*` stands for: file} of the files a path pattern with one
    `*`, which spans folders as in Node, names in package folder `pkg`."""
    head, _, tail = (f"{pkg}/{pattern}" if pkg else pattern).partition("*")
    return {path[len(head): len(path) - len(tail)]: path for path in sorted(tree)
            if path.startswith(head) and path.endswith(tail) and len(path) > len(head) + len(tail)}


def _package_pattern(pkg: str, target: str, tree: set[str]) -> tuple[dict[str, str], str]:
    """A package.json target with one `*` (a subpath pattern's): ({what the
    `*` stands for: file} of the files it names, `file`), else, for a
    build output that is not committed, those of the first source stem
    that names any (`source-guess`)."""
    rel = posixpath.normpath(_norm(target))
    if rel.count("*") != 1 or rel.startswith("../"):
        return {}, "unresolved"
    found = _pattern_files(pkg, rel, tree)
    if found:
        return found, "file"
    for stem in _source_stems(rel):
        for ext in JS_SOURCE_EXTENSIONS:
            for key, file in _pattern_files(pkg, stem + ext, tree).items():
                found.setdefault(key, file)
        if found:
            return found, "source-guess"
    return {}, "unresolved"


def _subpath_excluded(subpath: str, excluded: list[str]) -> bool:
    """Whether a subpath (or subpath pattern) the exports map maps to `null`
    takes `subpath` out of the package's surface."""
    for pattern in excluded:
        head, star, tail = pattern.partition("*")
        if subpath == pattern or (star and subpath.startswith(head) and subpath.endswith(tail)
                                  and len(subpath) >= len(head) + len(tail)):
            return True
    return False


def _owners(files: list[str], manifest: str, tree: list[str]) -> list[str]:
    """The folders ('' for the root) of the nearest `manifest` above each
    file."""
    dirs = {posixpath.dirname(p) for p in tree if posixpath.basename(p) == manifest}
    owners = set()
    for rel in files:
        folder = posixpath.dirname(rel)
        while True:
            if folder in dirs:
                owners.add(folder)
                break
            if not folder:
                break
            folder = posixpath.dirname(folder)
    return sorted(owners)


def _js_entries(root: Path, files: list[str], tree: list[str], tree_set: set[str],
                warnings: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """(entry points, exports-map facts, unresolved subpaths) of the
    packages that own the in-scope JS/TS files: the files each subpath of
    an `exports` map names (a pattern subpath, one with `*`, one entry per
    file its target matches, less those a `null` target takes out), else
    the package's types/module/main/browser fields, else its index file."""
    js_files = [f for f in files if _file_language(f) in JS_FAMILY]
    packages = _owners(js_files, "package.json", tree) or ([""] if js_files else [])
    entries: list[dict] = []
    maps: list[dict] = []
    unresolved: list[dict] = []
    for pkg in packages:
        found, facts, missing = _js_package_entries(root, pkg, tree_set, warnings)
        entries += found
        maps += facts
        unresolved += missing
    return entries, maps, unresolved


def _js_package_entries(root: Path, pkg: str, tree_set: set[str],
                        warnings: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """(entry points, exports-map facts, unresolved subpaths) of the one
    package in folder `pkg` ("" for the root), by _js_entries's rules, its
    package.json read from `root`."""
    label = pkg or "."
    entries: list[dict] = []
    maps: list[dict] = []
    unresolved: list[dict] = []

    def add(file: str, how: str, subpath: str) -> None:
        if not any(e["file"] == file and e["subpath"] == subpath for e in entries):
            entries.append({"language": _file_language(file) or "javascript", "file": file,
                            "package": label, "subpath": subpath, "resolution": how})

    manifest: dict = {}
    manifest_path = f"{pkg}/package.json" if pkg else "package.json"
    if manifest_path in tree_set:
        try:
            loaded = json.loads((root / manifest_path).read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            warnings.append(f"{manifest_path}: cannot read ({exc}); its entry points are the index files")
    subpaths = exports_subpaths(manifest.get("exports")) if "exports" in manifest else {}
    if subpaths:
        code = [s for s in subpaths if s != "." and "*" not in s
                and any(t.endswith(JS_TARGET_SUFFIXES) for t in subpaths[s])]
        maps.append({"package": label, "subpaths": sorted(subpaths),
                     "non_root_subpaths": len(code),
                     "wildcard_subpaths": sum(1 for s in subpaths if "*" in s)})
    else:
        fields = [manifest[f] for f in PACKAGE_ENTRY_FIELDS if isinstance(manifest.get(f), str)]
        subpaths = {".": fields} if fields else {}
    excluded = [s for s, targets in subpaths.items() if not targets]
    for subpath, targets in subpaths.items():
        code_targets = [t for t in targets if t.endswith(JS_TARGET_SUFFIXES)]
        found = 0
        for target in code_targets:
            if "*" in target:
                matched, how = _package_pattern(pkg, target, tree_set)
                found += len(matched)
                for key, file in matched.items():
                    named = subpath.replace("*", key, 1)
                    if not _subpath_excluded(named, excluded):
                        add(file, how, named)
                continue
            file, how = _package_target(pkg, target, tree_set)
            if file:
                add(file, how, subpath)
                found += 1
        if code_targets and not found:
            unresolved.append({"package": label, "subpath": subpath, "targets": code_targets})
    if "." in subpaths or not subpaths:
        if not any(e["subpath"] == "." for e in entries):
            folder = f"{pkg}/" if pkg else ""
            conventional = next((f"{folder}{d}index{e}" for d in ("", "src/") for e in JS_SOURCE_EXTENSIONS
                                 if f"{folder}{d}index{e}" in tree_set), None)
            if conventional:
                entries.append({"language": _file_language(conventional), "file": conventional,
                                "package": label, "subpath": ".", "resolution": "conventional"})
                unresolved = [u for u in unresolved if u["subpath"] != "."]
    return entries, maps, unresolved


def _specifier_local(text: str) -> str:
    """The local (or imported) side of an export or import specifier's text:
    `a as b` -> a, `type T` -> T, `"a-b" as c` -> a-b."""
    item = text.strip()
    if item.startswith("type ") or item.startswith("typeof "):
        item = item.split(None, 1)[1]
    return re.split(r"\s+as\s+", item, maxsplit=1)[0].strip().strip("'\"")


class _Surface:
    """The public names one language family's entry points declare:
    {name: info}, the first entry point naming it wins; the names, and the
    files, a namespace export (a module) makes reachable, which are not
    internal; and the re-exports the trace could not follow."""

    def __init__(self) -> None:
        self.names: dict[str, dict] = {}
        self.reachable: set[str] = set()
        self.reachable_files: set[str] = set()
        self.unresolved: list[dict] = []

    def add(self, name: str, entry: str, via: str, file: str | None, line: int | None,
            source: str | None = None, local: str | None = None) -> dict | None:
        if not name or name.startswith("_"):
            return None
        if name not in self.names:
            self.names[name] = {"name": name, "entry": entry, "via": via, "from": source,
                                "local": local if local and local != name else None,
                                "file": file, "line": line}
        return self.names[name]

    def unresolve(self, entry: str, name: str, source: str | None, file: str) -> None:
        """A re-export in `file`, met tracing `entry`, that names no file here."""
        item = {"entry": entry, "name": name, "from": source, "file": file}
        if item not in self.unresolved:
            self.unresolved.append(item)


def _js_facts(matches: list[dict], text: str, forms: dict, barrel_ids: set[str]) -> dict:
    """What one JS/TS module exports, read from its scan matches (the
    standard export recipes' and the trace rules') and, for the forms no
    recipe matches, its text: {"names": {exposed name: fact}, "stars":
    [(source, line)], "imports": {local name: (imported, source)}}, the
    imported name being `default` for a default import and `*` for a
    namespace import. A fact is {"how", "line", "local", "source"}:
    `declaration` (the module's own binding `local`), `re-export` (name
    `local` of module `source`: a named re-export, or a list item or the
    default export of an imported binding) or `namespace` (module `source`
    as a whole). The default export is the name `default`, `local` naming
    what it declares. Of two facts for one name, a declaration beats a list
    item, which beats a name read from the text, then the first line wins."""
    imports: dict[str, tuple[str, str | None]] = {}
    stars: list[tuple[str | None, int]] = []
    ordered = sorted(matches, key=lambda m: (m["line"], m["name"] or ""))
    for m in ordered:
        if m["rule"] in IMPORT_RULES and m["name"]:
            imported = {IMPORT_DEFAULT_RULE: "default", IMPORT_NAMESPACE_RULE: "*"}.get(m["rule"])
            imports.setdefault(m["name"], (imported or _specifier_local(m["text"]), m["source"]))
        elif m["rule"] == STAR_RULE:
            stars.append((m["source"], m["line"]))
    ranked: dict[str, tuple[tuple[int, int], dict]] = {}

    def put(name: str, rank: int, how: str, line: int | None, local: str | None, source: str | None) -> None:
        key = (rank, line or 0)
        if name and (name not in ranked or key < ranked[name][0]):
            ranked[name] = (key, {"how": how, "line": line, "local": local, "source": source})

    def bound(name: str, local: str, line: int | None, rank: int) -> None:
        """`name` exported for the module's binding `local`, which an import may bind."""
        imported, source = imports.get(local, (None, None))
        if imported == "*":
            put(name, rank, "namespace", line, None, source)
        elif imported is not None:
            put(name, rank, "re-export", line, imported, source)
        else:
            put(name, rank, "declaration", line, local, None)

    for m in ordered:
        if m["rule"] not in barrel_ids or not m["name"]:
            continue
        if forms[(m["rule"], m["language"])]["rule"]["kind"] == "export_specifier":
            if m["source"]:
                put(m["name"], 1, "re-export", m["line"], _specifier_local(m["text"]), m["source"])
            else:
                bound(m["name"], _specifier_local(m["text"]), m["line"], 1)
        elif m["source"]:
            put(m["name"], 0, "namespace", m["line"], None, m["source"])
        elif _JS_DEFAULT_EXPORT_RE.match(m["text"]):
            put("default", 0, "declaration", m["line"], m["name"], None)
        else:
            put(m["name"], 0, "declaration", m["line"], m["name"], None)
    declared, defaults = _js_text_names(text)
    for name, line, is_default in declared:
        put("default" if is_default else name, 2, "declaration", line, name, None)
    for local, line in defaults:
        bound("default", local, line, 2)
    return {"names": {name: fact for name, (_, fact) in ranked.items()}, "stars": stars, "imports": imports}


def _js_surface(root: Path, entries: list[dict], tree_set: set[str], forms: dict,
                barrel_ids: set[str], scan: Callable[[list[str]], dict[str, list[dict]]],
                surface: _Surface) -> None:
    """Add the names the JS/TS entry points export: those each declares,
    re-exports or exports as a namespace, and those its `export *`
    statements pass on through every module they chain to (a default
    export aside). A re-exported name is traced to the module that declares
    it, through each re-export, imported binding and `export *` between (a
    cycle ends the trace); a namespace export makes reachable the names its
    module passes on, traced the same way, and those of the namespaces
    among them. The modules the exports lead to are scanned a level at a
    time."""
    entry_files = sorted({e["file"] for e in entries})
    by_file = dict(scan(entry_files))
    cache: dict[str, dict] = {}

    def facts(file: str) -> dict:
        if file not in cache:
            cache[file] = _js_facts(by_file.get(file, []), _read_text(root, file) or "", forms, barrel_ids)
        return cache[file]

    def target(source: str | None, file: str) -> str | None:
        return resolve_js_module(source, file, tree_set)

    seen, level = set(entry_files), entry_files
    while level:
        found: set[str] = set()
        for file in level:
            module = facts(file)
            sources = [s for s, _ in module["stars"]] + [fact["source"] for fact in module["names"].values()]
            found.update(t for t in (target(s, file) for s in sources) if t is not None and t not in seen)
        seen |= found
        level = sorted(found)
        by_file.update(scan(level))

    closures: dict[str, list[str]] = {}
    passed: dict[str, dict[str, str]] = {}

    def closure(file: str) -> list[str]:
        """`file`, then each module its `export *` statements chain to."""
        if file not in closures:
            order: list[str] = []
            stack, visited = [file], set()
            while stack:
                module = stack.pop()
                if module in visited:
                    continue
                visited.add(module)
                order.append(module)
                stack += reversed([t for t in (target(s, module) for s, _ in facts(module)["stars"]) if t])
            closures[file] = order
        return closures[file]

    def passed_on(file: str) -> dict[str, str]:
        """{name: the module that exports it} of what `export * from` the
        module `file` passes on: its own names, then its chain's."""
        if file not in passed:
            out: dict[str, str] = {}
            for module in closure(file):
                for name in facts(module)["names"]:
                    if name != "default":
                        out.setdefault(name, module)
            passed[file] = out
        return passed[file]

    def resolve(file: str, name: str, chain: set[str]) -> tuple[str, str, int | None, dict | None]:
        """(module, its name there, line, fact) of what `name`, as module
        `file` exports it, comes from: a declaration or a namespace export,
        or a re-export from a module no file here holds, where the trace
        stops. The fact and the line are None where no module exports it;
        `chain` collects each name met."""
        visited: set[tuple[str, str]] = set()
        while (file, name) not in visited:
            visited.add((file, name))
            chain.add(name)
            fact = facts(file)["names"].get(name)
            if fact is None:
                owner = passed_on(file).get(name) if name != "default" else None
                if owner is None or owner == file:
                    return file, name, None, None
                file = owner
                continue
            follow = target(fact["source"], file) if fact["how"] == "re-export" else None
            if follow is None:
                return file, fact["local"] or name, fact["line"], fact
            file, name = follow, fact["local"]
        return file, name, None, None

    reached: set[str] = set()

    def reach(file: str | None) -> None:
        """Make reachable what the namespace module `file` passes on."""
        if file is None or file in reached:
            return
        reached.add(file)
        for name, owner in passed_on(file).items():
            chain: set[str] = set()
            where, local, _, fact = resolve(owner, name, chain)
            surface.reachable.update(chain | {local})
            if fact is not None and fact["how"] == "namespace":
                reach(target(fact["source"], where))

    def publish(entry: str, name: str, via: str, module: str, source: str | None) -> None:
        """Add public `name`, which `module` exports, traced to what it is."""
        chain: set[str] = set()
        where, local, line, fact = resolve(module, name, chain)
        surface.reachable.update(chain)
        how = fact["how"] if fact is not None else None
        if how == "namespace":
            namespace = target(fact["source"], where)
            surface.add(name, entry, "namespace", namespace, None, source)
            if namespace is None:
                surface.unresolve(entry, name, fact["source"], where)
            reach(namespace)
        elif how == "re-export":
            surface.add(name, entry, via, None, None, source, local)
            surface.unresolve(entry, name, fact["source"], where)
        else:
            surface.add(name, entry, via, where, line, source, local)

    for entry in entry_files:
        for name, fact in facts(entry)["names"].items():
            if fact["how"] == "declaration":
                surface.add(name, entry, "declaration", entry, fact["line"], local=fact["local"])
            else:
                publish(entry, name, "re-export", entry, fact["source"])
    for entry in entry_files:
        for source, _ in facts(entry)["stars"]:
            start = target(source, entry)
            if start is None:
                surface.unresolve(entry, "*", source, entry)
                continue
            for name, owner in passed_on(start).items():
                publish(entry, name, "star", owner, source)
            for module in closure(start):
                for inner, _ in facts(module)["stars"]:
                    if target(inner, module) is None:
                        surface.unresolve(entry, "*", inner, module)


# --------------------------------------------------------------------------
# Entry points: Python
# --------------------------------------------------------------------------


def _type_checking(node: ast.stmt) -> bool:
    """An `if TYPE_CHECKING:` (or `typing.TYPE_CHECKING`) block: its body
    never runs, so what it imports is no attribute of the module."""
    test = node.test if isinstance(node, ast.If) else None
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name) and test.value.id in ("typing", "typing_extensions"))


def _module_statements(body: list) -> Iterator[ast.stmt]:
    """A module's statements, those inside its module-level if, try, with,
    for, while and match blocks included, never a function's or a class's,
    nor those of an `if TYPE_CHECKING:` body (its `else` runs)."""
    for node in body:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field in ("orelse",) if _type_checking(node) else ("body", "orelse", "finalbody"):
            inner = getattr(node, field, None)
            if isinstance(inner, list):
                yield from _module_statements(inner)
        for handler in getattr(node, "handlers", None) or []:
            yield from _module_statements(handler.body)
        for case in getattr(node, "cases", None) or []:
            yield from _module_statements(case.body)


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for elt in node.elts for n in _target_names(elt)]
    if isinstance(node, ast.Starred):
        return _target_names(node.value)
    return []


def _literal_names(node: ast.AST | None) -> list[str] | None:
    """The strings of a literal `__all__` value (a list, a tuple, a sum of
    them or one string); None when it holds no literal part."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_names(node.left), _literal_names(node.right)
        if left is None and right is None:
            return None
        return (left or []) + (right or [])
    return None


def _py_bindings(text: str) -> tuple[list[str] | None, dict[str, dict], list[dict]]:
    """A Python module's (__all__ or None, the names it binds at module
    level, its star imports). A binding: {"line", "kind": "definition" |
    "import" | "module-import"}; a definition's "form" (`def` for a def or
    async def, `class`, `variable` for an assignment); an import's
    "module", "level" and "imported" name. Raises SyntaxError."""
    tree = ast.parse(text)
    all_names: list[str] | None = None
    bound: dict[str, dict] = {}
    stars: list[dict] = []
    for node in _module_statements(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            form = "class" if isinstance(node, ast.ClassDef) else "def"
            bound.setdefault(node.name, {"line": node.lineno, "kind": "definition", "form": form})
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n for t in targets for n in _target_names(t)]
            if "__all__" in names:
                listed = _literal_names(node.value)
                if isinstance(node, ast.AugAssign):
                    all_names = (all_names or []) + (listed or [])
                elif listed is not None:
                    all_names = listed
            if not isinstance(node, ast.AugAssign):
                for name in names:
                    bound.setdefault(name, {"line": node.lineno, "kind": "definition", "form": "variable"})
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    stars.append({"module": node.module, "level": node.level, "line": node.lineno})
                else:
                    bound.setdefault(alias.asname or alias.name, {
                        "line": node.lineno, "kind": "import", "module": node.module,
                        "level": node.level, "imported": alias.name})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.setdefault(alias.asname or alias.name.split(".")[0],
                                 {"line": node.lineno, "kind": "module-import"})
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "__all__"
              and node.value.func.attr in ("extend", "append") and node.value.args):
            all_names = (all_names or []) + (_literal_names(node.value.args[0]) or [])
    return all_names, bound, stars


_PY_ALL_RE = re.compile(r"^__all__\s*\+?=\s*[\[(]([^\])]*)[\])]", re.M)
_PY_DEF_RE = re.compile(r"^(?:async\s+)?(def|class)\s+(\w+)", re.M)
_PY_FROM_RE = re.compile(r"^from\s+(\.*)([\w.]*)\s+import\s+(\([^)]*\)|[^\n]+)", re.M)


def _py_text_bindings(text: str) -> tuple[list[str] | None, dict[str, dict], list[dict]]:
    """_py_bindings read from text, for a module this Python cannot parse
    (newer syntax): __all__, column-0 def and class, from-imports."""
    all_names = None
    for m in _PY_ALL_RE.finditer(text):
        all_names = (all_names or []) + re.findall(r"""['"]([^'"]+)['"]""", m.group(1))
    bound: dict[str, dict] = {}
    stars: list[dict] = []
    for m in _PY_DEF_RE.finditer(text):
        bound.setdefault(m.group(2), {"line": _line_of(text, m.start(2)), "kind": "definition", "form": m.group(1)})
    for m in _PY_FROM_RE.finditer(text):
        line, level, module = _line_of(text, m.start()), len(m.group(1)), m.group(2) or None
        for item in m.group(3).strip("() \t").split(","):
            parts = item.split()
            if parts == ["*"]:
                stars.append({"module": module, "level": level, "line": line})
            elif parts and re.fullmatch(r"\w+", parts[0]):
                name = parts[2] if len(parts) == 3 and parts[1] == "as" else parts[0]
                bound.setdefault(name, {"line": line, "kind": "import", "module": module,
                                        "level": level, "imported": parts[0]})
    return all_names, bound, stars


def _py_module_file(pkg_dir: str, level: int, module: str | None, tree: set[str]) -> str | None:
    """The file of the module `from <level dots><module> import` names, from
    a module of the package in `pkg_dir`: relative imports, or an absolute
    one within that package."""
    if level > 0:
        base = pkg_dir
        for _ in range(level - 1):
            if not base:
                return None
            base = posixpath.dirname(base)
    else:
        top = posixpath.basename(pkg_dir)
        if not top or not module or module.split(".")[0] != top:
            return None
        base = posixpath.dirname(pkg_dir)
    path = "/".join(p for p in (base, *(module.split(".") if module else [])) if p)
    candidates = ([f"{path}.py"] if module else []) + [f"{path}/__init__.py" if path else "__init__.py"]
    return next((c for c in candidates if c in tree), None)


def _py_submodule(folder: str, name: str, tree: set[str]) -> str | None:
    base = f"{folder}/{name}" if folder else name
    return next((c for c in (f"{base}.py", f"{base}/__init__.py") if c in tree), None)


def _py_entries(files: list[str], tree_set: set[str]) -> list[dict]:
    """The top __init__.py of each package that holds an in-scope file."""
    tops = set()
    for rel in files:
        if _file_language(rel) != "python":
            continue
        folder = posixpath.dirname(rel)
        if (f"{folder}/__init__.py" if folder else "__init__.py") not in tree_set:
            continue
        while folder and (f"{posixpath.dirname(folder)}/__init__.py" if posixpath.dirname(folder)
                          else "__init__.py") in tree_set:
            folder = posixpath.dirname(folder)
        tops.add(f"{folder}/__init__.py" if folder else "__init__.py")
    return [{"language": "python", "file": f, "package": posixpath.dirname(f) or ".", "subpath": None,
             "resolution": "file"} for f in sorted(tops)]


def _py_surface(root: Path, entries: list[dict], tree_set: set[str], surface: _Surface,
                warnings: list[str]) -> None:
    """Add the names each package __init__.py exports: its __all__ when it
    has one, else the public names it defines or imports from its package
    and those its star imports give, through every module they chain to.
    Each name is traced to the module that defines it, through each import
    and star import between (a cycle ends the trace); a submodule is a
    namespace, which makes reachable the names it exports, traced the same
    way, and those of the submodules among them."""
    parsed: dict[str, tuple] = {}

    def bindings(rel: str) -> tuple[list[str] | None, dict[str, dict], list[dict]]:
        if rel not in parsed:
            text = _read_text(root, rel) or ""
            try:
                parsed[rel] = _py_bindings(text)
            except SyntaxError as exc:
                warnings.append(f"{rel}: this Python cannot parse it ({exc.msg}, line {exc.lineno}); "
                                "its names are read from its text")
                parsed[rel] = _py_text_bindings(text)
        return parsed[rel]

    def module_file(rel: str, level: int, module: str | None, top: str) -> str | None:
        """The module `from <level dots><module> import` names in module
        `rel`: relative to its package, or absolute within the package in
        folder `top`."""
        return _py_module_file(posixpath.dirname(rel) if level else top, level, module, tree_set)

    def packaged(rel: str, binding: dict, top: str) -> bool:
        """A binding module `rel` defines, or imports from the package in
        folder `top`: an import from another package is not its own."""
        if binding["kind"] == "definition":
            return True
        return binding["kind"] == "import" and (
            binding["level"] > 0 or module_file(rel, 0, binding["module"], top) is not None)

    star_cache: dict[tuple[str, str], dict[str, str]] = {}

    def star_names(rel: str, top: str, missing: list[tuple[str, str]] | None = None) -> dict[str, str]:
        """{name: the module that binds it} of what `from <rel> import *`
        gives: its __all__, else the public names it defines or imports
        (from its own package) and those its own star imports give.
        `missing` collects the (module, source) of each relative star
        import that names no file."""
        if missing is None and (rel, top) in star_cache:
            return star_cache[(rel, top)]
        out: dict[str, str] = {}
        stack, visited = [rel], set()
        while stack:
            module = stack.pop()
            if module in visited:
                continue
            visited.add(module)
            listed, bound, stars = bindings(module)
            if listed is not None:
                for name in listed:
                    out.setdefault(name, module)
                continue
            for name, binding in bound.items():
                if packaged(module, binding, top) and not name.startswith("_"):
                    out.setdefault(name, module)
            chained = []
            for star in stars:
                found = module_file(module, star["level"], star["module"], top)
                if found is not None:
                    chained.append(found)
                elif star["level"] and missing is not None:
                    missing.append((module, "." * star["level"] + (star["module"] or "")))
            stack += reversed(chained)
        star_cache[(rel, top)] = out
        return out

    def resolve(rel: str, name: str, top: str, chain: set[str]) -> tuple[str | None, str, int | None, str]:
        """(module, its name there, line, what it is) that `name`, bound in
        module `rel`, comes from, `what` being `definition`, `submodule`
        (the module is it), `module` (an `import x` binding), `import` (from
        outside the package: no module) or `missing` (bound nowhere the
        trace reaches). `chain` collects each name met."""
        visited: set[tuple[str, str]] = set()
        while (rel, name) not in visited:
            visited.add((rel, name))
            chain.add(name)
            _, bound, stars = bindings(rel)
            binding = bound.get(name)
            package = posixpath.dirname(rel) if rel.endswith("__init__.py") else None
            if binding is None or binding["kind"] == "module-import":
                sub = _py_submodule(package, name, tree_set) if package is not None else None
                if sub:
                    return sub, name, None, "submodule"
                if binding is not None:
                    return rel, name, binding["line"], "module"
                owner = None
                for star in stars:
                    found = module_file(rel, star["level"], star["module"], top)
                    owner = star_names(found, top).get(name) if found is not None else None
                    if owner is not None:
                        break
                if owner is None:
                    return rel, name, None, "missing"
                rel = owner
                continue
            if binding["kind"] == "definition":
                return rel, name, binding["line"], "definition"
            found = module_file(rel, binding["level"], binding["module"], top)
            if found is None:
                return None, binding["imported"], None, "import"
            if found.endswith("__init__.py"):
                sub = _py_submodule(posixpath.dirname(found), binding["imported"], tree_set)
                if sub and sub != rel:
                    return sub, binding["imported"], None, "submodule"
            rel, name = found, binding["imported"]
        return rel, name, None, "missing"

    reached: set[str] = set()

    def reach(rel: str, top: str) -> None:
        """Make reachable what the submodule `rel` exports."""
        if rel in reached:
            return
        reached.add(rel)
        for name, owner in star_names(rel, top).items():
            chain: set[str] = set()
            where, local, _, what = resolve(owner, name, top, chain)
            surface.reachable.update(chain | {local})
            if what == "submodule" and where is not None:
                reach(where, top)

    for entry in [e["file"] for e in entries]:
        top = posixpath.dirname(entry)
        all_names, bound, stars = bindings(entry)
        names: dict[str, str | None]  # name -> the star import that gives it, if one does
        if all_names is not None:
            names = dict.fromkeys(all_names)
        else:
            names = {name: None for name, binding in bound.items() if packaged(entry, binding, top)}
            missing: list[tuple[str, str]] = []
            for star in stars:
                source = "." * star["level"] + (star["module"] or "")
                found = module_file(entry, star["level"], star["module"], top)
                if found is None:
                    if star["level"] > 0:
                        missing.append((entry, source))
                    continue
                for name in star_names(found, top, missing):
                    names.setdefault(name, source)
            for module, source in missing:
                surface.unresolve(entry, "*", source, module)
        for name, star_source in names.items():
            binding = bound.get(name)
            source = star_source
            if binding is not None and binding["kind"] == "import":
                source = "." * binding["level"] + (binding["module"] or "")
            chain: set[str] = set()
            where, local, line, what = resolve(entry, name, top, chain)
            surface.reachable.update(chain)
            if what == "submodule":
                surface.add(name, entry, "namespace", where, None, source, local)
                reach(where, top)
            elif what == "import":
                surface.add(name, entry, "re-export", None, None, source, local)
                surface.unresolve(entry, name, source, entry)
            elif binding is not None and binding["kind"] == "definition":
                surface.add(name, entry, "declaration", entry, binding["line"])
            elif binding is not None and binding["kind"] == "import":
                surface.add(name, entry, "re-export", where, line, source, local)
            elif star_source is not None or (what in ("definition", "module") and where != entry):
                surface.add(name, entry, "star", where, line, source, local)
            else:
                # __all__ lists it but nothing binds it, or an `import x`
                surface.add(name, entry, "declaration", None, None)


# --------------------------------------------------------------------------
# Entry points: Rust
# --------------------------------------------------------------------------

_RUST_ITEM_RE = re.compile(
    r'^pub\s+((?:(?:async|const|unsafe|default|extern(?:\s+"[^"]*")?)\s+)*)'
    r"(fn|struct|enum|trait|type|const|static|union|mod)\s+(?:mut\s+)?((?:r#)?[A-Za-z_]\w*)",
    re.M,
)
_RUST_USE_RE = re.compile(r"^pub\s+use\s+([^;]*);", re.M)
_RUST_MOD_RE = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?mod\s+((?:r#)?[A-Za-z_]\w*)\s*([;{])", re.M)
_RUST_TOKEN_RE = re.compile(r"r#\w+|\w+|::|[{},*]")


def _rust_items(code: str) -> list[tuple[str, str, int]]:
    """(name, kind, line) of each unrestricted column-0 `pub` item."""
    return [(m.group(3), m.group(2), _line_of(code, m.start(3))) for m in _RUST_ITEM_RE.finditer(code)]


def _rust_use_leaves(tree_text: str) -> list[tuple[list[str], str | None, bool]]:
    """Each (path, alias, glob) a `pub use` tree brings in:
    `a::{b, c::D as E, f::*}` -> (a, b), (a, c, D; E), (a, f; glob)."""
    tokens = _RUST_TOKEN_RE.findall(tree_text)
    leaves: list[tuple[list[str], str | None, bool]] = []

    def parse(i: int, prefix: list[str]) -> int:
        segments: list[str] = []
        while i < len(tokens):
            token = tokens[i]
            if token == "::":
                i += 1
            elif token == "{":
                i += 1
                while i < len(tokens) and tokens[i] != "}":
                    i = parse(i, prefix + segments)
                    if i < len(tokens) and tokens[i] == ",":
                        i += 1
                return i + 1
            elif token == "*":
                leaves.append((prefix + segments, None, True))
                return i + 1
            elif token in (",", "}"):
                break
            elif token == "as" and segments and i + 1 < len(tokens):
                leaves.append((prefix + segments, tokens[i + 1], False))
                return i + 2
            else:
                segments.append(token)
                i += 1
        if segments:
            leaves.append((prefix + segments, None, False))
        return i

    parse(0, [])
    return leaves


def _rust_file(lib: str, path: list[str], tree: set[str]) -> str | None:
    """The file of the crate module at `path` (its names from the crate
    root, whose file is `lib`): <name>.rs or <name>/mod.rs at each level;
    None for a module no such file holds (an inline one, a `#[path]` one)."""
    base, current = posixpath.dirname(lib), lib
    for seg in path:
        stem = f"{base}/{seg}" if base else seg
        current = next((c for c in (f"{stem}.rs", f"{stem}/mod.rs") if c in tree), None)
        if current is None:
            return None
        base = stem
    return current


def _rust_use_path(segments: list[str], here: list[str], mods: set[str]) -> list[str] | None:
    """A `use` path written in the module at `here` as a path from the
    crate root: `crate::` starts at the root, `self::` at `here`, each
    `super::` one module up, and a module `here` declares at `here`; None
    for another crate."""
    segs = [s.removeprefix("r#") for s in segments]
    if not segs:
        return None
    if segs[0] == "crate":
        return segs[1:]
    base = list(here)
    if segs[0] == "self":
        return base + segs[1:]
    if segs[0] == "super":
        while segs and segs[0] == "super":
            if not base:
                return None
            base, segs = base[:-1], segs[1:]
        return base + segs
    return base + segs if segs[0] in mods else None


def _rust_entries(root: Path, files: list[str], tree: list[str], tree_set: set[str]) -> list[dict]:
    """The library root (`[lib] path`, else src/lib.rs) of each crate that
    holds an in-scope file."""
    rust_files = [f for f in files if _file_language(f) == "rust"]
    entries = []
    for crate in _owners(rust_files, "Cargo.toml", tree):
        lib = "src/lib.rs"
        try:
            manifest = tomllib.loads((root / (f"{crate}/Cargo.toml" if crate else "Cargo.toml")).read_text(encoding="utf-8"))
            path = (manifest.get("lib") or {}).get("path")
            lib = _norm(path) if isinstance(path, str) and path.strip() else lib
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, AttributeError):
            pass
        file = posixpath.normpath(f"{crate}/{lib}" if crate else lib)
        if file in tree_set:
            entries.append({"language": "rust", "file": file, "package": crate or ".", "subpath": None,
                            "resolution": "file"})
    return entries


def _rust_surface(root: Path, entries: list[dict], tree_set: set[str], surface: _Surface) -> None:
    """Add the names each crate root exports: its unrestricted column-0
    `pub` items (a `pub mod` is a namespace) and its `pub use` items, each
    traced to the module file that declares it through the `pub use` items
    between (a cycle ends the trace); a glob `pub use m::*` adds what `m`
    exports, its globs included. The crate root, and each module a `pub
    mod` or a `pub use` of a reachable module names, in turn, are reachable
    files: every recipe match in them is reachable (the recipe keeps to the
    `pub mod` blocks within a file), and so is each name they export."""
    parsed: dict[str, dict] = {}

    def module(rel: str) -> dict:
        """A module file's unrestricted column-0 `pub` items, the modules it
        declares ({name: declared with `;`, its body in a file of its own})
        and its `pub use` leaves, with their lines."""
        if rel not in parsed:
            code = _blank(_read_text(root, rel) or "", "rust")
            uses = []
            for use in _RUST_USE_RE.finditer(code):
                for path, alias, glob in _rust_use_leaves(use.group(1)):
                    if path and path[-1] == "self" and not glob:
                        path = path[:-1]
                    if path and alias != "_":
                        uses.append((path, alias, glob, _line_of(code, use.start())))
            parsed[rel] = {"items": _rust_items(code), "uses": uses,
                           "mods": {m.group(1).removeprefix("r#"): m.group(2) == ";"
                                    for m in _RUST_MOD_RE.finditer(code)}}
        return parsed[rel]

    def exported(lib: str, here: list[str]) -> list[str]:
        """The names the module at `here` exports: its `pub` items, its
        `pub use` names and what its globs pass on, in that order."""
        out: dict[str, None] = {}
        stack, visited = [list(here)], set()
        while stack:
            path = stack.pop()
            file = _rust_file(lib, path, tree_set)
            if tuple(path) in visited or file is None:
                continue
            visited.add(tuple(path))
            info = module(file)
            out.update(dict.fromkeys(name for name, _, _ in info["items"]))
            globs = []
            for use, alias, glob, _ in info["uses"]:
                if not glob:
                    out.setdefault(alias or use[-1])
                elif (full := _rust_use_path(use, path, set(info["mods"]))) is not None:
                    globs.append(full)
            stack += reversed(globs)
        return list(out)

    def resolve(lib: str, here: list[str], name: str, chain: set[str]) -> tuple:
        """(file, its name there, line, module path, stop) of what `name`,
        as the module at `here` exports it, is: an item of that file, or a
        module (its path, and its file when one holds it). `stop` is the
        (`use` path, file) where the trace ends in another crate, the file
        None with it; the line is None where the trace ends at a module
        that does not export the name, or at a cycle. `chain` collects each
        name met."""
        visited: set[tuple[tuple[str, ...], str]] = set()
        while (tuple(here), name) not in visited:
            visited.add((tuple(here), name))
            chain.add(name)
            file = _rust_file(lib, here, tree_set)
            if file is None:
                return None, name, None, None, None
            info = module(file)
            item = next(((kind, line) for n, kind, line in info["items"] if n == name), None)
            if item is not None:
                if item[0] != "mod":
                    return file, name, item[1], None, None
                sub = [*here, name.removeprefix("r#")]
                sub_file = _rust_file(lib, sub, tree_set)
                return sub_file or file, name, None if sub_file else item[1], sub, None
            mods = set(info["mods"])
            use = next(((path, line) for path, alias, glob, line in info["uses"]
                        if not glob and (alias or path[-1]) == name), None)
            if use is not None:
                path = use[0]
                full = _rust_use_path(path, here, mods)
                if full is None:
                    return None, path[-1], None, None, ("::".join(path), file)
                if not path[-1][:1].isupper() and _rust_file(lib, full, tree_set) is not None:
                    return _rust_file(lib, full, tree_set), path[-1], None, full, None
                here, name = full[:-1], path[-1]
                continue
            owner = next((full for path, _, glob, _ in info["uses"] if glob
                          for full in [_rust_use_path(path, here, mods)]
                          if full is not None and name in exported(lib, full)), None)
            if owner is None:
                return file, name, None, None, None
            here = owner
        return _rust_file(lib, here, tree_set), name, None, None, None

    def reach(lib: str, here: list[str], reached: set[tuple[str, ...]]) -> None:
        """Make reachable the module at `here`: its file and the names it
        exports, then the modules its `pub mod` and `pub use` items name."""
        if tuple(here) in reached:
            return
        reached.add(tuple(here))
        file = _rust_file(lib, here, tree_set)
        if file is None:
            parent = _rust_file(lib, here[:-1], tree_set)
            if here and parent is not None and module(parent)["mods"].get(here[-1]):
                # a `pub mod name;` whose file is not name.rs or name/mod.rs
                surface.unresolve(lib, here[-1], "::".join(["crate", *here]), parent)
            return
        surface.reachable_files.add(file)
        info = module(file)
        for name, kind, _ in info["items"]:
            surface.reachable.add(name)
            if kind == "mod":
                reach(lib, [*here, name.removeprefix("r#")], reached)
        for path, alias, glob, _ in info["uses"]:
            if glob:
                full = _rust_use_path(path, here, set(info["mods"]))
                if full is not None:
                    reach(lib, full, reached)
                continue
            chain: set[str] = set()
            sub = resolve(lib, here, alias or path[-1], chain)[3]
            surface.reachable.update(chain)
            if sub is not None:
                reach(lib, sub, reached)

    def publish(lib: str, here: list[str], name: str, via: str, source: str | None,
                reached: set[tuple[str, ...]]) -> None:
        """Add public `name`, which the module at `here` exports, traced to
        what it is."""
        chain: set[str] = set()
        file, local, line, sub, stop = resolve(lib, here, name, chain)
        surface.reachable.update(chain)
        if stop is not None:
            surface.add(name, lib, via, None, None, source, local)
            surface.unresolve(lib, name, *stop)
        elif sub is not None:
            surface.add(name, lib, "namespace", file, line, "::".join(sub))
            reach(lib, sub, reached)
        else:
            surface.add(name, lib, via, file, line, source, local)

    for lib in [e["file"] for e in entries]:
        surface.reachable_files.add(lib)
        reached: set[tuple[str, ...]] = set()
        info = module(lib)
        for name, kind, line in info["items"]:
            if kind != "mod":
                surface.add(name, lib, "declaration", lib, line)
                continue
            sub = [name.removeprefix("r#")]
            sub_file = _rust_file(lib, sub, tree_set)
            surface.add(name, lib, "namespace", sub_file or lib, None if sub_file else line)
            reach(lib, sub, reached)
        for path, alias, glob, _ in info["uses"]:
            if not glob:
                publish(lib, [], alias or path[-1], "re-export", "::".join(path[:-1]) or None, reached)
                continue
            full = _rust_use_path(path, [], set(info["mods"]))
            if full is None or _rust_file(lib, full, tree_set) is None:
                # another crate's module, or one no file of its own holds
                surface.unresolve(lib, "*", "::".join(path), lib)
                continue
            for name in exported(lib, full):
                publish(lib, full, name, "star", "::".join(path), reached)


# --------------------------------------------------------------------------
# Entry points: Go
# --------------------------------------------------------------------------

_GO_FUNC_RE = re.compile(r"^func\s+([^\W\d]\w*)", re.M)
_GO_DECL_RE = re.compile(r"^(?:type|var|const)\s+([^\W\d]\w*)", re.M)
_GO_GROUP_RE = re.compile(r"^(?:type|var|const)\s*\(\s*$")
_GO_SPEC_RE = re.compile(r"^\t([^\W\d]\w*(?:[ \t]*,[ \t]*[^\W\d]\w*)*)")
_GO_MAIN_RE = re.compile(r"^package\s+main\b", re.M)


def _go_names(code: str) -> list[tuple[str, int]]:
    """(name, line) of each capitalized top-level func (not a method),
    type, var and const, grouped declarations included."""
    found = [(m.group(1), _line_of(code, m.start(1))) for rx in (_GO_FUNC_RE, _GO_DECL_RE)
             for m in rx.finditer(code)]
    lines = code.split("\n")
    i = 0
    while i < len(lines):
        if _GO_GROUP_RE.match(lines[i]):
            i += 1
            while i < len(lines) and not lines[i].startswith(")"):
                spec = _GO_SPEC_RE.match(lines[i])
                if spec:
                    found += [(n, i + 1) for n in re.split(r"[ \t]*,[ \t]*", spec.group(1))]
                i += 1
        i += 1
    return sorted((n, ln) for n, ln in found if n[0].isupper())


def _go_surface(root: Path, files: list[str], surface: _Surface, entries: list[dict]) -> None:
    """Add the capitalized top-level names of the in-scope Go files outside
    _test.go files, package main and internal/ folders."""
    packages: set[str] = set()
    for rel in files:
        if (_file_language(rel) != "go" or rel.endswith("_test.go")
                or "internal" in rel.split("/")[:-1]):
            continue
        code = _blank(_read_text(root, rel) or "", "go")
        if _GO_MAIN_RE.search(code):
            continue
        packages.add(posixpath.dirname(rel) or ".")
        for name, line in _go_names(code):
            surface.add(name, rel, "declaration", rel, line)
    entries.extend({"language": "go", "file": p, "package": p, "subpath": None, "resolution": "package"}
                   for p in sorted(packages))


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def entry_point_diff(exports: list[dict], surfaces: dict[str, _Surface], entries: list[dict],
                     in_scope: set[str]) -> tuple[dict[str, str], dict[tuple[str, str], dict], list[dict],
                                                  list[tuple[str, dict]], list[tuple[str, dict]]]:
    """The entry-point diff, one language family at a time: (status by
    family, public names {(family, name): info}, internal export records,
    and (family, info) of the extraction gaps and of the names outside
    scope). A family whose entry points declare names diffs them with its
    exports: an export no entry point names, nor traces back to, nor makes
    reachable (a name, or any export of a reachable file), is internal. A
    declared name no recipe found is a gap when a file in scope defines it
    (or the trace found no file), and is outside scope when a file out of
    scope does; a module is no recipe's target, so neither. In a family
    with no entry point, or only empty ones, every export is public."""
    statuses: dict[str, str] = {}
    public: dict[tuple[str, str], dict] = {}
    internal: list[dict] = []
    gaps: list[tuple[str, dict]] = []
    outside: list[tuple[str, dict]] = []
    entry_families = {FAMILY_OF[e["language"]] for e in entries}
    families = {FAMILY_OF[e["language"]] for e in exports} | entry_families
    for family in sorted(families | {f for f, s in surfaces.items() if s.names}):
        records = [e for e in exports if FAMILY_OF[e["language"]] == family]
        declared = surfaces[family].names
        if not declared:
            statuses[family] = "empty-barrel" if family in entry_families else "no-entry-point"
            for e in records:
                public.setdefault((family, e["export_name"]), {
                    "name": e["export_name"], "entry": None, "via": "declaration", "from": None,
                    "local": None, "file": e["source_file"], "line": e["source_line"]})
            continue
        statuses[family] = "barrel"
        surface = surfaces[family]
        names = {e["export_name"] for e in records}
        traced = {info["local"] for info in declared.values() if info["local"]} | surface.reachable
        public.update(((family, name), info) for name, info in declared.items())
        seen: set[str] = set()
        for e in records:
            name = e["export_name"]
            if (name not in declared and name not in traced and name not in seen
                    and e["source_file"] not in surface.reachable_files):
                seen.add(name)
                internal.append(e)
        for name, info in declared.items():
            if name in names or (info["local"] or name) in names or info["via"] == "namespace":
                continue
            (gaps if info["file"] is None or info["file"] in in_scope else outside).append((family, info))
    return statuses, public, internal, gaps, outside


def _head_cap(value: int | None, tier: str | None, scope_type: str | None) -> int | None:
    if value is not None:
        return value or None
    return HEAD_CAPS.get((tier, scope_type), DEFAULT_HEAD_CAP)


def _monorepo(root: Path, tree: list[str], tree_set: set[str]) -> tuple[bool, str | None]:
    """skf-detect-workspaces.py's verdict on the source root."""
    manifests = {}
    for name in WORKSPACE_MANIFESTS:
        if name in tree_set:
            text = _read_text(root, name)
            if text is not None:
                manifests[name] = text
    result = _sibling("skf-detect-workspaces.py").detect({"tree": tree, "manifests": manifests})
    return bool(result.get("is_monorepo")), result.get("manifest_kind")


def _select_files(root: Path, candidates: list[str], listed: bool, includes: list[str], excludes: list[str],
                  wanted: set[str], glob_match: Callable[[str, str], bool], issues: list[dict],
                  warnings: list[str]) -> tuple[list[str], dict[str, int]]:
    """(the files in scope, by extension the in-scope source files no recipe
    reads). A file a --files-from list names that is missing, or that no
    recipe reads, is an issue; an include glob no candidate matches, a
    warning."""
    in_scope: list[str] = []
    without_recipes: Counter = Counter()
    used = dict.fromkeys(includes, False)
    for rel in candidates:
        hits = [g for g in includes if glob_match(rel, g)]
        used.update(dict.fromkeys(hits, True))
        if (includes and not hits) or any(glob_match(rel, g) for g in excludes):
            continue
        if listed and not (root / rel).is_file():
            issues.append({"file": rel, "issue": "missing"})
            continue
        language = _file_language(rel)
        if language is None or language not in wanted:
            extension = posixpath.splitext(rel)[1].lower()
            if listed:
                issues.append({"file": rel, "issue": "no-recipes"})
            elif extension in NO_RECIPE_EXTENSIONS:
                without_recipes[extension] += 1
            continue
        in_scope.append(rel)
    warnings += [f"scope.include pattern {g!r} matches no file" for g, hit in used.items() if not hit]
    return in_scope, dict(sorted(without_recipes.items()))


def run_full(args: argparse.Namespace) -> tuple[dict, int]:
    """Run the recipes over the source tree; (result, exit code)."""
    clock = _Clock(DEFAULT_TIMEOUT_SEC if args.timeout is None else args.timeout)
    root = Path(args.source_root)
    if not root.is_dir():
        raise RunnerError(f"source root not found: {args.source_root}")
    recipes_path = Path(args.recipes) if args.recipes else RECIPES_FILE
    recipes = load_recipe_file(recipes_path)
    brief = _read_brief(Path(args.brief)) if args.brief else {}
    includes = [g for g in (_norm(v) for v in (args.include or brief.get("include") or [])) if g]
    excludes = [g for g in (_norm(v) for v in (args.exclude or brief.get("exclude") or [])) if g]
    tier_a = [g for g in (_norm(v) for v in (args.tier_a_include or brief.get("tier_a_include") or [])) if g]
    scope_type = args.scope_type or brief.get("type")
    language_values = args.language or ([brief["language"]] if brief.get("language") else [])
    wanted, unknown_languages = _wanted_languages(language_values)
    recipe_set = args.recipe_set or ("component-library" if scope_type == "component-library" else "standard")
    head_cap = _head_cap(args.head_cap, args.tier, scope_type)
    glob_match = _sibling("skf-resolve-authoritative-files.py").glob_match

    warnings: list[str] = [f"no recipe reads {value} files" for value in unknown_languages]
    errors: list[dict] = []
    issues: list[dict] = []
    tree = list_tree(root)
    tree_set = set(tree)
    listed = _read_file_list(Path(args.files_from)) if args.files_from else None
    in_scope, without_recipes = _select_files(root, tree if listed is None else listed, listed is not None,
                                              includes, excludes, wanted, glob_match, issues, warnings)
    readable = []
    for rel in in_scope:
        try:
            (root / rel).read_bytes().decode("utf-8")
        except OSError:
            issues.append({"file": rel, "issue": "unreadable"})
            continue
        except UnicodeDecodeError:
            issues.append({"file": rel, "issue": "not-utf8"})
            continue
        readable.append(rel)

    # The entry points and the arms need no ast-grep.
    in_scope_set = set(in_scope)
    surfaces = {family: _Surface() for family in FAMILIES}
    js_entries, maps, unresolved_subpaths = _js_entries(root, in_scope, tree, tree_set, warnings)
    py_entries = _py_entries(in_scope, tree_set)
    rust_entries = _rust_entries(root, in_scope, tree, tree_set)
    go_entries: list[dict] = []
    _go_surface(root, in_scope, surfaces["go"], go_entries)
    entries = js_entries + py_entries + rust_entries + go_entries
    for entry in entries:
        # a Go entry is a package folder, which the files in scope give
        entry["in_scope"] = entry["language"] == "go" or entry["file"] in in_scope_set
        if not entry["in_scope"] and entry["subpath"] is not None:
            warnings.append(f"public entry point {entry['file']} (subpath '{entry['subpath']}' of package "
                            f"{entry['package']}) is outside the files in scope: widen scope.include to document "
                            "the names it exports (entry_point_diff.outside_scope), which effective_denominator "
                            "leaves out")
    monorepo, monorepo_kind = _monorepo(root, tree, tree_set)
    arms = {
        "monorepo": monorepo,
        "monorepo_kind": monorepo_kind,
        "specific_modules": scope_type == "specific-modules" and not monorepo,
        "multi_subpath_exports": not monorepo and any(m["non_root_subpaths"] > 1 for m in maps),
    }

    exe, version, shim = _ast_grep()
    result: dict = {
        "mode": "full",
        "status": "ok",
        "source_root": args.source_root,
        "recipes_file": recipes_path.as_posix(),
        "recipe_set": recipe_set,
        "ast_grep": {"path": exe, "version": version},
        "scope": {"include": includes, "exclude": excludes, "tier_a_include": tier_a or None,
                  "type": scope_type, "languages": sorted(wanted),
                  "files_from": args.files_from},
        "files_in_scope": len(in_scope),
        "files_by_language": dict(sorted(Counter(_file_language(f) for f in in_scope).items())),
        "files_without_recipes": without_recipes,
        "file_issues": issues,
        "head_cap": head_cap,
        "truncated": False,
        "recipes": [],
        "exports": [],
        "aggregates": {"exports": 0, "by_type": {}, "t1": 0, "t1_low": 0},
        "entry_points": {"status": None, "by_language": {}, "files": entries, "exports_maps": maps,
                         "unresolved": unresolved_subpaths},
        "entry_point_diff": None,
        "reexport_targets": [],
        "counts": None,
        "arms": arms,
        "errors": errors,
        "warnings": warnings,
    }
    if exe is None:
        result["status"] = "no-ast-grep"
        result["file_issues"] = sorted(issues, key=lambda i: (i["file"], i["issue"]))
        if shim is None:
            warnings.append("ast-grep is not on PATH: no recipe ran; extract by source reading")
        else:
            warnings.append(f"ast-grep on PATH is the npm shim {shim}, with no native ast-grep.exe beside it: "
                            "a shim runs through cmd.exe, which would read the file paths a scan passes as "
                            "commands, so no recipe ran; extract by source reading, or install a native "
                            "ast-grep (pip install ast-grep-cli)")
        return result, 3

    forms = _forms(recipes)
    set_recipes = [r for r in recipes if recipe_set in r["metadata"]["sets"]]
    barrel_recipes = [r for r in recipes if "standard" in r["metadata"]["sets"]
                      and r["rule"]["kind"] in ("export_statement", "export_specifier")
                      and set(r["metadata"]["languages"]) & set(JS_FAMILY)]
    barrel_ids = {r["id"] for r in barrel_recipes}
    languages = {lang for f in readable for lang in _rule_languages(_file_language(f))}
    with tempfile.TemporaryDirectory(prefix="skf-extract-", ignore_cleanup_errors=True) as tmp:
        folder = Path(tmp)
        rules = _recipe_rules(set_recipes, languages) + [_syntax_error_rule(lang) for lang in sorted(languages)]
        matches = _scan(exe, root, folder, rules, readable, errors, clock)
        issues += _syntax_issues(matches)
        exports, stats = merge_exports(matches, recipes, recipe_set, head_cap)
        _type_list_items(exe, root, folder, matches, exports, errors, clock)

        scanned: dict[str, list[dict]] = {}

        def scan_barrels(files: list[str]) -> dict[str, list[dict]]:
            todo = [f for f in files if f not in scanned and _read_text(root, f) is not None]
            langs = {lang for f in todo for lang in _rule_languages(_file_language(f) or "")}
            barrel_rules = _recipe_rules(barrel_recipes, langs)
            barrel_rules += [r for lang in sorted(langs & set(RECIPE_LANGUAGES)) for r in _trace_rules(lang)]
            for f in todo:
                scanned[f] = []
            for m in _scan(exe, root, folder, barrel_rules, todo, errors, clock):
                scanned.setdefault(m["file"], []).append(m)
            return {f: scanned.get(f, []) for f in files}

        if js_entries:
            _js_surface(root, js_entries, tree_set, forms, barrel_ids, scan_barrels, surfaces["javascript"])
        _py_surface(root, py_entries, tree_set, surfaces["python"], warnings)
        _rust_surface(root, rust_entries, tree_set, surfaces["rust"])

    for record in exports:
        if record["from"] and record["language"] in JS_FAMILY:
            record["from_file"] = resolve_js_module(record["from"], record["source_file"], tree_set)
    statuses, public, internal, gaps, outside = entry_point_diff(exports, surfaces, entries, in_scope_set)
    if "barrel" in statuses.values():
        status = "barrel"
    else:
        status = "empty-barrel" if "empty-barrel" in statuses.values() else "no-entry-point"

    basis_globs = tier_a or includes
    basis = "tier_a_include" if tier_a else ("scope.include" if includes else "all-files")
    denominator_files = {f for f in tree if (not basis_globs or any(glob_match(f, g) for g in basis_globs))
                         and not any(glob_match(f, g) for g in excludes)}

    by_type: Counter = Counter(e["export_type"] for e in exports)
    ordered = sorted(public.items(), key=lambda item: (item[0][1], item[0][0]))
    result.update({
        "truncated": any(s["truncated"] for s in stats),
        "recipes": stats,
        "exports": exports,
        "aggregates": {"exports": len(exports), "by_type": dict(sorted(by_type.items())),
                       "t1": len(exports), "t1_low": 0},
        "entry_points": {"status": status, "by_language": statuses, "files": entries, "exports_maps": maps,
                         "unresolved": unresolved_subpaths + [u for s in surfaces.values() for u in s.unresolved]},
        "entry_point_diff": {
            "public": [dict(info, language=family) for (family, _), info in ordered],
            "internal": [{"name": e["export_name"], "language": FAMILY_OF[e["language"]],
                          "source_file": e["source_file"], "source_line": e["source_line"]} for e in internal],
            "extraction_gaps": [{"name": info["name"], "language": family, "entry": info["entry"],
                                 "file": info["file"], "line": info["line"]}
                                for family, info in sorted(gaps, key=lambda g: (g[1]["name"], g[0]))],
            "outside_scope": [{"name": info["name"], "language": family, "entry": info["entry"],
                               "file": info["file"], "line": info["line"]}
                              for family, info in sorted(outside, key=lambda g: (g[1]["name"], g[0]))],
        },
        "reexport_targets": [
            {"name": info["name"], "language": family, "local": info["local"], "from": info["from"],
             "entry": info["entry"], "file": info["file"], "line": info["line"], "via": info["via"]}
            for (family, _), info in ordered if info["via"] in ("re-export", "star", "namespace")],
        "counts": {
            "exports_public_api": len(public),
            "exports_internal": len(internal),
            "effective_denominator": sum(1 for info in public.values() if info["file"] in denominator_files),
            "effective_denominator_basis": basis,
            "denominator_files": len(denominator_files),
        },
    })
    result["file_issues"] = sorted(issues, key=lambda i: (i["file"], i["issue"]))
    if errors:
        result["status"] = "incomplete"
        return result, 1
    return result, 0


def _main_full(args: argparse.Namespace) -> int:
    if not args.source_root:
        sys.stderr.write("error: --mode full needs --source-root\n")
        return 2
    if args.head_cap is not None and args.head_cap < 0:
        sys.stderr.write("error: --head-cap must be 0 (no cap) or more\n")
        return 2
    if args.timeout is not None and not args.timeout > 0:
        sys.stderr.write("error: --timeout must be more than 0 seconds\n")
        return 2
    try:
        result, code = run_full(args)
    except RunnerError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001 - one stderr line and exit 2, never a traceback
        detail = " ".join(str(exc).split())
        sys.stderr.write(f"error: the run failed: {type(exc).__name__}: {detail}\n")
        return 2
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"error: cannot write {args.output}: {exc}\n")
            return 2
    else:
        sys.stdout.write(text)
    return code


# --------------------------------------------------------------------------
# Entries mode: the files quick mode reads, found in the listing
# --------------------------------------------------------------------------

# The quick languages entries mode finds entry files for, by family.
ENTRY_LANGUAGES = {"js": "javascript", "ts": "javascript", "javascript": "javascript",
                   "typescript": "javascript", "python": "python", "rust": "rust", "go": "go",
                   "java": "java", "kotlin": "kotlin"}
# The manifest of each family at the package folder, the first one listed read
# (Python: the first that names the package, read in this order).
ENTRY_MANIFESTS = {"javascript": ("package.json",), "python": ("pyproject.toml", "setup.py", "setup.cfg"),
                   "rust": ("Cargo.toml",), "go": ("go.mod",), "java": ("pom.xml",),
                   "kotlin": ("build.gradle.kts", "build.gradle")}
# A glob-picked family (Go, Java, Kotlin) reads at most this many files, as
# the fetch's `--limit 5` did; no family reads more than ENTRY_FILE_LIMIT.
ENTRY_GLOB_LIMIT = 5
ENTRY_FILE_LIMIT = 25
# Top folders of a Python tree that hold no package code (test* folders too).
PY_NON_CORE_TOPS = frozenset({"docs", "examples", "benchmarks"})


def _scope_folder(scope: str | None) -> str:
    """The package folder a --scope names, "" for the repository root."""
    folder = _norm(scope or "").strip("/")
    return "" if folder == "." else folder


def _import_name(name: object) -> str:
    """A distribution name the way Python imports it: lower case, each run
    of `-` and `.` read as `_` (`zope.interface` -> zope_interface)."""
    return re.sub(r"[-.]+", "_", name.strip().lower()) if isinstance(name, str) else ""


def _py_quick_entries(folder: str, tree: list[str], tree_set: set[str],
                      name: str | None) -> tuple[list[str], list[str]]:
    """(entry files, the paths tried when there is none) of the Python
    package in `folder`: the top __init__.py of each package full mode finds
    (_py_entries) among its .py files, less those under a top folder named
    test*, docs, examples or benchmarks, the one whose folder is the
    manifest's import name preferred (Pillow's src/PIL/ is kept, as no
    folder is named pillow); with no package at all, the single module
    `<name>.py` or `src/<name>.py` (six.py)."""
    prefix = f"{folder}/" if folder else ""
    files = []
    for path in tree:
        if not path.startswith(prefix) or not path.endswith(".py"):
            continue
        rest = path[len(prefix):]
        top = rest.split("/", 1)[0].lower() if "/" in rest else ""
        if top.startswith(("test", ".")) or top in PY_NON_CORE_TOPS:
            continue
        files.append(path)
    tops = [entry["file"] for entry in _py_entries(files, tree_set)]
    wanted = _import_name(name)
    if tops:
        named = [top for top in tops if posixpath.basename(posixpath.dirname(top)).lower() == wanted]
        return named or tops, []
    tried = [f"{prefix}{wanted}.py", f"{prefix}src/{wanted}.py"] if wanted else []
    return [path for path in tried if path in tree_set][:1], tried


def _py_manifest_name(manifest: str, content: str) -> str | None:
    """The distribution name a Python manifest gives: pyproject.toml's
    [project] or [tool.poetry] `name`, setup.py's `name=`, setup.cfg's
    [metadata] `name`."""
    if manifest.endswith("setup.py"):
        name = parse_setup_py(content).get("name")
    elif manifest.endswith("setup.cfg"):
        name = parse_setup_cfg(content).get("name")
    else:
        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            return None
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
        poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
        name = project.get("name") or poetry.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _pom_group(content: str) -> str | None:
    """The groupId of a pom.xml (parse_pom_xml's), else the one its <parent> gives."""
    group = (parse_pom_xml(content).get("_extra") or {}).get("group_id")
    if group:
        return group
    try:
        project = ET.fromstring(content)
    except ET.ParseError:
        return None
    for child in project:
        if _strip_ns(child.tag) == "parent":
            for item in child:
                if _strip_ns(item.tag) == "groupId" and (item.text or "").strip():
                    return item.text.strip()
    return None


def _rust_lib_path(content: str | None) -> str:
    """The crate root a Cargo.toml names (`[lib] path`), else src/lib.rs."""
    try:
        path = (tomllib.loads(content or "").get("lib") or {}).get("path")
    except (tomllib.TOMLDecodeError, AttributeError):
        path = None
    return _norm(path) if isinstance(path, str) and path.strip() else "src/lib.rs"


def find_entries(language: str, tree: list[str], root: Path, scope: str | None = None) -> dict:
    """The entry files quick mode reads for the one package at `scope` (the
    repository root by default), found in the listing `tree` with full
    mode's rules, its manifest read from `root` (the folder it was fetched
    into). See "Entries mode" above."""
    lowered = (language or "").lower()
    if lowered not in LANGUAGE_DISPATCH:
        return {"_error": f"unknown language: {language!r}; expected one of {sorted(LANGUAGE_DISPATCH)}"}
    family = ENTRY_LANGUAGES.get(lowered)
    folder = _scope_folder(scope)
    prefix = f"{folder}/" if folder else ""
    label = folder or "."
    tree_set = set(tree)
    warnings: list[str] = []
    out = {"mode": "entries", "language": lowered, "scope": label, "manifest": None,
           "entry_files": [], "unresolved": [], "warnings": warnings}
    if family is None:
        warnings.append(f"no entry-point rule for {lowered}: read its source by eye")
        return out
    listed = [prefix + name for name in ENTRY_MANIFESTS[family] if prefix + name in tree_set]
    contents: dict[str, str] = {}
    for path in listed if family == "python" else listed[:1]:
        try:
            contents[path] = (root / path).read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            warnings.append(f"{path} is in the listing but not under --source-root: fetch it first")
    manifest = listed[0] if listed else None
    py_name = None
    if family == "python":
        named = ((path, _py_manifest_name(path, text)) for path, text in contents.items())
        manifest, py_name = next(((path, name) for path, name in named if name), (manifest, None))
    out["manifest"] = manifest
    content = contents.get(manifest) if manifest else None
    files: list[str] = []
    tried: list[str] = []
    if family == "javascript":
        found, _, out["unresolved"] = _js_package_entries(root, folder, tree_set, warnings)
        files = [entry["file"] for entry in found]
        tried = [f"{prefix}index.*", f"{prefix}src/index.*"]
    elif family == "python":
        files, tried = _py_quick_entries(folder, tree, tree_set, py_name)
    elif family == "rust":
        crate = [path for path in tree if path.startswith(prefix) and path.endswith(".rs")]
        files = [entry["file"] for entry in _rust_entries(root, crate, tree, tree_set) if entry["package"] == label]
        tried = [posixpath.normpath(prefix + _rust_lib_path(content))]
    elif family == "go":
        files = sorted(path for path in tree if posixpath.dirname(path) == folder and path.endswith(".go")
                       and not path.endswith("_test.go"))[:ENTRY_GLOB_LIMIT]
        tried = [f"{prefix}*.go"]
    elif family == "java":
        group = _pom_group(content) if content else None
        base = f"{prefix}src/main/java/{group.replace('.', '/')}" if group else None
        if base:
            files = sorted(path for path in tree
                           if posixpath.dirname(path) == base and path.endswith(".java"))[:ENTRY_GLOB_LIMIT]
        tried = [f"{base}/*.java" if base else f"{prefix}src/main/java/<groupId>/*.java"]
    else:
        base = f"{prefix}src/main/kotlin/"
        files = sorted(path for path in tree if path.startswith(base) and path.endswith(".kt"))[:ENTRY_GLOB_LIMIT]
        tried = [f"{base}**/*.kt"]
    if len(files) > ENTRY_FILE_LIMIT:
        warnings.append(f"{len(files)} entry files: quick mode reads the first {ENTRY_FILE_LIMIT}")
        files = files[:ENTRY_FILE_LIMIT]
    if not files and not out["unresolved"]:
        out["unresolved"] = [{"package": label, "subpath": None, "targets": tried}]
    out["entry_files"] = files
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a package's public-API surface: from manifest and entry-point content on stdin or "
            "in files (quick, a pure parser), or by running the ast-grep recipes over a source tree (full); "
            "or find the entry files quick mode reads in a repository listing (entries)."
        ),
    )
    parser.add_argument(
        "--mode",
        default="quick",
        choices=("quick", "full", "entries"),
        help="quick (default): parse the stdin payload, or the --manifest-file and --entry-file files; "
             "full: run the recipes over --source-root; entries: list one package's entry files from "
             "--tree-file.",
    )
    quick = parser.add_argument_group("quick mode, files read from disk")
    quick.add_argument("--manifest-file", metavar="PATH",
                       help="the package manifest (relative to --source-root when given); needs --language")
    quick.add_argument("--entry-file", action="append", metavar="PATH",
                       help="an entry-point file (relative to --source-root when given), repeatable; needs --language")
    quick.add_argument("--follow-file", action="append", metavar="PATH",
                       help="a module an unlisted[] record named (a --fetch-list path), read as an entry less "
                            "its JS/TS default export, which `export *` does not pass on; repeatable")
    quick.add_argument("--follow", action="store_true",
                       help=f"read each module an unlisted[] record names as one more --follow-file, round "
                            f"after round (at most {FOLLOW_ROUNDS}), until none is left; needs --tree-file and "
                            f"--source-root")
    quick.add_argument("--repo", metavar="OWNER/REPO",
                       help="with --follow: fetch each module from this GitHub repository into --source-root "
                            "first (skf-github-fetch.py)")
    quick.add_argument("--ref", metavar="REF",
                       help="with --repo: the branch, tag or commit to fetch at (default: the default branch)")
    listing = parser.add_argument_group("entries mode, and the listing quick mode follows chains in")
    listing.add_argument("--tree-file", metavar="PATH",
                         help="the repository's file listing (skf-github-probe.py tree output, JSON, or one "
                              "path per line): entries mode finds the entry files in it, and quick mode "
                              "resolves each unlisted[] statement's module_file against it")
    listing.add_argument("--scope", metavar="FOLDER",
                         help="entries mode: the package folder to read (default: the repository root)")
    listing.add_argument("--fetch-list", metavar="FILE",
                         help="write one path per line for skf-github-fetch.py --patterns-file: the entry "
                              "files (entries mode), or each unlisted[] module_file still to read (quick mode)")
    full = parser.add_argument_group("full mode")
    full.add_argument("--source-root",
                      help="the source tree to extract from (quick mode: the folder the file paths are relative to)")
    full.add_argument("--brief", help="a skill-brief.yaml: its scope and language")
    full.add_argument("--include", action="append", metavar="GLOB",
                      help="an include glob, repeatable (replaces the brief's scope.include)")
    full.add_argument("--exclude", action="append", metavar="GLOB",
                      help="an exclude glob, repeatable (replaces the brief's scope.exclude)")
    full.add_argument("--tier-a-include", action="append", metavar="GLOB",
                      help="a tier-A glob for effective_denominator, repeatable (replaces scope.tier_a_include)")
    full.add_argument("--scope-type", help="the scope type (replaces the brief's scope.type)")
    full.add_argument("--language", action="append",
                      help="a language family to extract, repeatable (replaces the brief's language); quick "
                           "mode: the files' language, once")
    full.add_argument("--files-from", metavar="FILE",
                      help="read only these files: one path per line, or a JSON list")
    full.add_argument("--recipe-set", choices=RECIPE_SETS,
                      help="the recipe set to run (default: from the scope type)")
    full.add_argument("--recipes", metavar="FILE", help="the recipe file (default: the module's data file)")
    full.add_argument("--tier", choices=TIERS, help="the forge tier, for the default head cap")
    full.add_argument("--head-cap", type=int, metavar="N",
                      help="the most matches kept per recipe (0: no cap; default: by tier and scope type)")
    full.add_argument("--timeout", type=float, metavar="SECONDS",
                      help=f"stop the ast-grep runs after this many seconds and still write the JSON, "
                           f"status incomplete (default {DEFAULT_TIMEOUT_SEC})")
    full.add_argument("-o", "--output", metavar="FILE", help="write the JSON here instead of stdout")
    return parser


FULL_MODE_FLAGS = ("source_root", "brief", "include", "exclude", "tier_a_include", "scope_type", "language",
                   "files_from", "recipe_set", "recipes", "tier", "head_cap", "timeout", "output")
# The full mode flags quick mode takes with its file inputs, and entries mode always.
QUICK_FILE_FLAGS = ("source_root", "language")
# The flags of entries mode; quick mode takes --tree-file and --fetch-list with its file inputs.
LISTING_FLAGS = ("tree_file", "scope", "fetch_list")
# Quick mode's own flags with its file inputs: the chains it follows itself.
FOLLOW_FLAGS = ("follow", "repo", "ref")
FOLLOW_ROUNDS = 5


class QuickInputError(Exception):
    """A --manifest-file or --entry-file quick mode cannot read (exit 2)."""


def _read_quick_file(root: Path | None, value: str, flag: str) -> dict:
    """{"path", "content"} of a --manifest-file or --entry-file: the path as
    given, written with `/`, and the file's text. Raises QuickInputError."""
    given = Path(value)
    path = given
    if root is not None:
        if given.is_absolute():
            raise QuickInputError(f"{flag} must be relative to --source-root: {value}")
        path = root / given
        if not path.resolve().is_relative_to(root.resolve()):
            raise QuickInputError(f"{flag} leads outside --source-root: {value}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise QuickInputError(f"cannot read {flag} {value}: {exc.strerror or exc}") from exc
    return {"path": given.as_posix(), "content": data.decode("utf-8-sig", errors="replace")}


def _read_listing(value: str) -> tuple[list[str], bool]:
    """(paths, whether the listing was cut short) of a --tree-file, read by
    skf-detect-language.py's read_tree_file(). Raises QuickInputError."""
    try:
        return _sibling("skf-detect-language.py").read_tree_file(value)
    except (RunnerError, ValueError) as exc:  # ValueError: the sibling's TreeListingError
        raise QuickInputError(str(exc)) from exc


def _write_fetch_list(path: str, files: list[str]) -> None:
    """Write `files` one per line (LF on every platform) for --patterns-file. Raises QuickInputError."""
    try:
        Path(path).write_text("".join(f"{f}\n" for f in files), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise QuickInputError(f"cannot write --fetch-list {path}: {exc.strerror or exc}") from exc


def _quick_files_payload(args: argparse.Namespace) -> dict:
    """The quick payload of --manifest-file and --entry-file, read from
    disk, with the --tree-file listing as its `tree`. Raises
    QuickInputError."""
    root = None
    if args.source_root is not None:
        root = Path(args.source_root)
        if not root.is_dir():
            raise QuickInputError(f"--source-root is not a folder: {args.source_root}")
    manifest = {"path": "", "content": ""}
    if args.manifest_file is not None:
        manifest = _read_quick_file(root, args.manifest_file, "--manifest-file")
    entries: list[dict] = []
    for value in args.entry_file or []:
        entry = _read_quick_file(root, value, "--entry-file")
        if all(e["path"] != entry["path"] for e in entries):
            entries.append(entry)
    for value in getattr(args, "follow_file", None) or []:
        entry = _read_quick_file(root, value, "--follow-file")
        if all(e["path"] != entry["path"] for e in entries):
            entries.append({**entry, "followed": True})
    payload = {"language": args.language[0], "manifest": manifest, "entries": entries, "mode": "quick"}
    if getattr(args, "tree_file", None) is not None:
        payload["tree"] = _read_listing(args.tree_file)[0]
    return payload


def _follow_reader(args: argparse.Namespace):
    """--follow's reader: paths -> (those now under --source-root, {path:
    why not} for the rest), each fetched there first with --repo. Raises
    QuickInputError."""
    root = Path(args.source_root)
    if args.repo is None:
        def read_local(paths: list[str]) -> tuple[list[str], dict[str, str]]:
            got = [p for p in paths if (root / p).is_file() and (root / p).resolve().is_relative_to(root.resolve())]
            return got, {p: "it is not under --source-root" for p in paths if p not in got}
        return read_local
    try:
        fetch = _sibling("skf-github-fetch.py")
    except RunnerError as exc:
        raise QuickInputError(str(exc)) from exc
    try:
        # No pattern: the call checks --repo, --ref and the listing, and fetches nothing.
        checked = fetch.run(args.repo, args.ref, args.tree_file, str(root), [])
    except fetch.UsageError as exc:
        raise QuickInputError(str(exc)) from exc
    owner, repo = checked["repo"].split("/", 1)
    fetch._start_clock(fetch.DEFAULT_TIMEOUT_SEC)

    def read_remote(paths: list[str]) -> tuple[list[str], dict[str, str]]:
        out = fetch.fetch(owner, repo, checked["ref"], paths, root.absolute())
        return out["fetched"], {f["path"]: f["detail"] for f in out["failed"]}
    return read_remote


def _follow(args: argparse.Namespace, result: dict) -> dict:
    """--follow: read each module_file `unlisted[]` names as one more
    --follow-file and parse the files again, round after round, until no
    module is left untried or FOLLOW_ROUNDS have run. Raises
    QuickInputError."""
    read = _follow_reader(args)
    tried = set(args.follow_file or [])
    followed: list[str] = []
    missed: dict[str, str] = {}
    for _ in range(FOLLOW_ROUNDS):
        named = [path for path in dict.fromkeys(item["module_file"] for item in result["unlisted"])
                 if path and path not in tried]
        if not named:
            break
        tried.update(named)
        got, failed = read(named)
        missed.update(failed)
        if got:
            followed += got
            files = argparse.Namespace(**{**vars(args), "follow_file": [*(args.follow_file or []), *followed]})
            result = extract(_quick_files_payload(files))
    left = [path for path in dict.fromkeys(item["module_file"] for item in result["unlisted"])
            if path and path not in tried]
    result["warnings"] += [f"--follow could not read {path} ({why}), so the names it passes on are missing"
                           for path, why in missed.items()]
    if left:
        result["warnings"].append(f"--follow stopped after {FOLLOW_ROUNDS} rounds with modules left to read: "
                                  f"{', '.join(left)}")
    result["followed"] = followed
    return result


def _main_entries(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """`--mode entries`: the entry files of one package, as JSON on stdout."""
    if args.manifest_file is not None or args.entry_file or args.follow_file:
        parser.error("--manifest-file, --entry-file, --follow-file: quick mode only (--mode quick)")
    given = [f"--{flag.replace('_', '-')}" for flag in FULL_MODE_FLAGS
             if getattr(args, flag) is not None and flag not in QUICK_FILE_FLAGS]
    if given:
        parser.error(f"{', '.join(given)}: full mode only (--mode full)")
    if not args.language or len(args.language) != 1:
        parser.error("--mode entries takes one --language")
    if args.tree_file is None or args.source_root is None:
        parser.error("--mode entries needs --tree-file and --source-root")
    root = Path(args.source_root)
    try:
        if root.exists() and not root.is_dir():
            raise QuickInputError(f"--source-root is not a folder: {args.source_root}")
        tree, truncated = _read_listing(args.tree_file)
        result = find_entries(args.language[0], tree, root, args.scope)
        if "_error" in result:
            print(json.dumps(result, indent=2))
            return 1
        if truncated:
            result["warnings"].append("the listing was cut short (a very large tree): an entry file may be "
                                      "missing from it")
        if args.fetch_list is not None:
            _write_fetch_list(args.fetch_list, result["entry_files"])
    except QuickInputError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    files = args.manifest_file is not None or bool(args.entry_file) or bool(args.follow_file)
    listing = [f"--{flag.replace('_', '-')}" for flag in LISTING_FLAGS if getattr(args, flag) is not None]
    following = [f"--{flag}" for flag in FOLLOW_FLAGS if getattr(args, flag) not in (None, False)]
    if following and (args.mode != "quick" or not files):
        parser.error(f"{', '.join(following)}: quick mode only, with --manifest-file or --entry-file")
    if args.mode == "full":
        if files:
            parser.error("--manifest-file, --entry-file, --follow-file: quick mode only (--mode quick)")
        if listing:
            parser.error(f"{', '.join(listing)}: entries or quick mode only")
        return _main_full(args)
    if args.mode == "entries":
        return _main_entries(args, parser)
    if args.scope is not None:
        parser.error("--scope: entries mode only (--mode entries)")
    if listing and not files:
        parser.error(f"{', '.join(listing)}: quick mode takes them only with --manifest-file or --entry-file")
    given = [f"--{flag.replace('_', '-')}" for flag in FULL_MODE_FLAGS
             if getattr(args, flag) is not None and not (files and flag in QUICK_FILE_FLAGS)]
    if given:
        hint = ""
        if any(flag in given for flag in ("--source-root", "--language")):
            hint = " (quick mode takes --source-root and --language only with --manifest-file or --entry-file)"
        parser.error(f"{', '.join(given)}: full mode only (--mode full){hint}")

    if files:
        if not args.language or len(args.language) != 1:
            parser.error("--manifest-file and --entry-file take one --language")
        if (args.repo is not None or args.ref is not None) and not args.follow:
            parser.error("--repo and --ref fetch the modules --follow reads, so pass --follow")
        if args.ref is not None and args.repo is None:
            parser.error("--ref is the ref of --repo, so pass --repo")
        if args.follow and (args.tree_file is None or args.source_root is None):
            parser.error("--follow finds each module in --tree-file and reads it under --source-root: pass both")
        try:
            payload = _quick_files_payload(args)
            result = extract(payload)
            if args.follow and "_error" not in result:
                result = _follow(args, result)
            if args.fetch_list is not None and "_error" not in result:
                follow = [item["module_file"] for item in result["unlisted"] if item["module_file"]]
                _write_fetch_list(args.fetch_list, list(dict.fromkeys(follow)))
        except QuickInputError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        print(json.dumps(result, indent=2))
        return 1 if "_error" in result else 0

    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("error: no input on stdin (expected JSON payload)\n")
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"error: stdin JSON parse error: {e}\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("error: stdin payload must be a JSON object\n")
        return 2

    payload.setdefault("mode", args.mode)
    result = extract(payload)
    print(json.dumps(result, indent=2))
    return 1 if "_error" in result else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
