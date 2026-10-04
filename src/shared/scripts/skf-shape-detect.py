# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Shape Detect — classify repos into known skill shapes from manifest files.

Single source of truth for shape-level classification consumed by
skf-analyze-source (AN auto-scope), skf-brief-skill (BS auto-brief),
and skf-test-skill (TS threshold selection).  Moving shape heuristics
into a shared script eliminates duplicate classification logic across
three pipelines.

The five-shape heuristic ladder (apply in order, first match wins):

  1. language-reference — parser/grammar/language-toolchain project
     Signals: a compiler tree, a grammar file, a package named after a
     parser tool (pest, antlr4, tree-sitter, lark ...)
  2. stack-compose     — multi-ecosystem composite project
     Signals: manifests from 2+ distinct ecosystems
  3. reference-app     — application, CLI, or demo project
     Signals: npm bin field, Rust [[bin]], framework deps
  4. library-API       — library exposing a programmatic API
     Signals: main/module/exports fields, [lib] target, export count
  5. unknown           — no heuristic matched

A reference-app that rests on a framework dependency alone (no bin) in a
package that names itself a library also carries the signal
`app_or_library:framework_dep`: an app built on the framework and a
library that extends it (FastAPI, a Flask or Django extension, axum-extra)
declare the same dependencies, so the caller judges which one it is from
the README or the manifest description. The shape stays reference-app.

A parser tool among the runtime dependencies (a consumer: nom, pyparsing,
tree-sitter ...) decides no shape: a language or DSL built on it and an app
or library that only reads its input with it declare the same dependency.
The ladder goes on and its shape carries the signal
`language_or_user:parser_dep`, so the caller judges which one it is from the
README or the manifest description. A dev or build dependency is no
consumer, nor is one in a non-core member (examples/, docs/) or the monorepo
coordinator root, as with frameworks. Only when the parser dependency is the
repository's only signal (a bare DSL manifest: no rung answers and no
manifest declares a bin) does it still give language-reference, in place of
unknown.

CLI:
  uv run src/shared/scripts/skf-shape-detect.py \\
      --repo-url <url> --manifests <path1,path2,...>
  uv run src/shared/scripts/skf-shape-detect.py \\
      --repo-url <url> --manifests <path1,path2,...> --tree-file <file>
  uv run src/shared/scripts/skf-shape-detect.py \\
      --repo-url <url> --manifests-file <scan.json> --manifest-dir <root> \\
      --tree-file <file>

Input:
  --repo-url      repository URL (required; context only, no cloning)
  --manifests     comma-separated local file paths to manifest files (may be
                  empty when a tree-level signal is supplied instead)
  --manifests-file the JSON envelope `skf-scan-manifests.py scan <root>`
                  printed, in place of --manifests: its `manifests[]`
                  entries of the types this script classifies (the _PARSERS
                  file names) are read, each `path` resolved against
                  --manifest-dir, so no caller filters, resolves or joins
                  the manifest list. A manifest's own path below that root
                  (not where the root sits) decides whether it is core and
                  how deep it is.
  --manifest-dir  the folder the scan ran on (required with
                  --manifests-file)
  --tree-file     the repository's whole file list (`-` reads it from stdin),
                  read by skf-detect-language.py's read_tree_file() (the
                  sibling in this folder, which must sit beside this
                  script), whose --tree-file text lists the listings it
                  reads (`git -c core.quotePath=false ls-tree -r --name-only
                  HEAD` prints one). The script finds the tree-level signals
                  in it itself (tree_signals()), in place of --grammar-files
                  and --tree-paths
  --grammar-files comma-separated repo-relative grammar files (*.y, *.g4,
                  *.pest, Grammar/python.gram, ...); a whole-language signal
  --tree-paths    comma-separated repo-relative directory/structural signals
                  harvested from the clone (compiler/ dir, lexer/parser/ast)
Passing --tree-file with --grammar-files or --tree-paths is an error, and
so is passing --manifests with --manifests-file.

tree_signals() reads every file of the listing and every folder that holds
one, so no caller's filter drops a path the gates accept (a root
`grammar.js`, `Python/ceval.c`, `check.go`), but leaves out a path with a
hidden segment or a segment of _NON_CORE_PATH_SEGMENTS (tests and fixtures,
docs, examples, benchmarks, scripts and tools): a CI workflow's check.yml,
scripts/check.sh or a test fixture's vm.js is not the repository's own
code. The grammar files are the paths _is_grammar_file() accepts at most
_GRAMMAR_MAX_DEPTH segments deep (a grammar deeper in the tree is a vendored
or test fixture) and outside a parsing folder below the top of the tree (a
library's reader of an input format, such as sympy/parsing/latex/LaTeX.g4,
_FORMAT_PARSER_DIRS), and the tree paths are every folder (with a trailing /)
and every file, which the compiler-folder, triad and corroborating-member
gates of _whole_language_tree() then judge: the triad among the paths near a
compiler folder, the corroborating member anywhere. A listing that says it
was cut short (a GitHub tree's `truncated`) adds the signal
`tree_truncated`.

Output (JSON on stdout):
  shape         library-API | reference-app | language-reference
                | stack-compose | unknown
  signals       array of human-readable evidence strings
  confidence    float 0.0-1.0
  export_count  integer (total public-facing exports)
  package_count integer (distinct packages detected)

Exit codes:
  0  shape classified (not unknown)
  1  unknown shape (no heuristic matched)
  2  error (invalid args, missing/unreadable files, a tree listing that
     cannot be read, holds no path or reports a failure, a manifests file
     that is not a scan envelope, parse failure)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Parser/grammar tools: a package named after one is a language-reference
# producer; one among the runtime deps raises the language_or_user:parser_dep
# question (detect() below)
# ---------------------------------------------------------------------------

_PARSER_DEPS_NPM = frozenset({
    "antlr4", "antlr4-runtime", "tree-sitter", "nearley",
    "chevrotain", "pegjs", "peggy", "ohm-js", "jison",
    "moo", "lezer", "@lezer/generator",
})
_PARSER_DEPS_PYTHON = frozenset({
    "antlr4-tools", "antlr4-runtime", "lark", "lark-parser",
    "ply", "tree-sitter", "textx", "parso", "pyparsing",
    "sly", "tatsu",
})
_PARSER_DEPS_RUST = frozenset({
    "pest", "pest_derive", "lalrpop", "lalrpop-util",
    "tree-sitter", "nom", "chumsky", "winnow", "logos",
})

_ALL_PARSER_DEPS = _PARSER_DEPS_NPM | _PARSER_DEPS_PYTHON | _PARSER_DEPS_RUST

# ---------------------------------------------------------------------------
# Tree-level whole-language signals (issue #427)
#
# A hand-written compiler (rustc, TypeScript, Go) declares no parser-generator
# dependency, and a language's own repo may carry no supported manifest at all
# (CPython, Ruby). These sets drive the grammar-file and compiler-directory
# rungs that classify such repos from tree evidence rather than manifests.
# ---------------------------------------------------------------------------

# Declared grammars — the strongest, most intentional whole-language signal.
# Matched on extension or whole basename, NEVER on substring.
_GRAMMAR_EXTS = frozenset({
    ".g4", ".pest", ".lalrpop", ".y", ".gram", ".lark", ".ebnf", ".peg",
    ".ungram",
})
_GRAMMAR_BASENAMES = frozenset({"grammar.js", "grammar.json", "python.gram"})
# A grammar file deeper than this many path segments is a vendored or test
# fixture, not the repo's own grammar (Grammar/python.gram is 2 deep).
_GRAMMAR_MAX_DEPTH = 4
# A library keeps its readers of other formats in a parsing folder of its own
# package: sympy's sympy/parsing/latex/LaTeX.g4 and
# sympy/parsing/autolev/Autolev.g4 sit beside sympy/core/ and the library's
# other modules. A grammar below such a folder parses an input the library
# reads, not the language the repository implements. A parsing folder at the
# top of the tree is not one of these: there the parser is the repository's
# own.
_FORMAT_PARSER_DIRS = frozenset({"parsing", "parsers"})

# Concrete parsers a repo CONSUMES. If a repo's own runtime deps contain one of
# these it delegates parsing — a formatter/linter/bundler, never a
# whole-language reference (prettier→@babel/parser, eslint→espree).
_CONSUMED_PARSERS = frozenset({
    "espree", "acorn", "@babel/parser", "babel-parser", "flow-parser",
    "swc_ecma_parser", "deno_ast", "graphql", "remark-parse", "yaml",
    "esquery", "estree", "@types/estree", "@webassemblyjs/ast", "smol-toml",
})

# Tools that own a parser-ish module but consume an external parser and are NOT
# whole-language references — bundlers, formatters, linters, markup/CSS libs.
_DELEGATING_TOOL_NAMES = frozenset({
    "prettier", "eslint", "stylelint", "biome", "rome",
    "webpack", "rollup", "esbuild", "vite", "parcel", "terser",
    "marked", "remark", "remark-parse", "markdown-it", "micromark", "commonmark",
    "postcss", "css-tree", "less", "sass", "node-sass",
})

# Markup / DSL / query languages — a real lexer+parser+AST for a
# non-general-purpose language (CSS, markdown, GraphQL, JSON). Their identity is
# a format parser, not a programming-language toolchain.
_MARKUP_DSL_NAMES = frozenset({
    "css", "less", "scss", "sass", "html", "markdown", "graphql",
    "graphql-schema", "json", "yaml", "toml", "xml",
})

# Dedicated compiler directories — the primary gate for the tree-triad rung
# (Rung B). Matched on a real DIRECTORY by exact path-tail, never a file and
# never a bare src/lib/language/parser dir. 'Parser' is case-sensitive
# (CPython's Parser/) so it does not match a lib/parser/ dir.
_COMPILER_DIRS = frozenset({
    "compiler", "src/compiler", "cmd/compile", "internal/syntax",
})
_COMPILER_DIRS_CASE = frozenset({"Parser"})

# Triad member name stems. A hand-written compiler spreads a lexer, a parser,
# and an AST across these conventional file/dir names.
_LEXER_STEMS = frozenset({"scanner", "lexer", "tokenizer"})
_PARSER_STEMS = frozenset({"parser", "parse"})
_AST_STEMS = frozenset({"ast"})

# Corroborating whole-language member (gate W). A markdown/CSS parser ships a
# lexer+parser+AST but no code generator, VM, or type checker — so requiring one
# of these excludes a markup library that merely sits under a compiler/ dir.
_CODEGEN_STEMS = frozenset({"codegen", "compile", "ssagen"})
_VM_STEMS = frozenset({"interpreter", "vm", "eval", "ceval"})
_CHECK_STEMS = frozenset({"checker", "check", "binder", "typeck", "typecheck"})

# ---------------------------------------------------------------------------
# Framework deps that signal reference-app shape
# ---------------------------------------------------------------------------

_FRAMEWORK_DEPS_NPM = frozenset({
    "next", "nuxt", "express", "fastify", "koa", "hono",
    "@nestjs/core", "gatsby", "electron",
})
_FRAMEWORK_DEPS_PYTHON = frozenset({
    "django", "flask", "fastapi", "uvicorn", "starlette",
    "tornado", "aiohttp", "sanic", "streamlit", "gradio",
})
_FRAMEWORK_DEPS_RUST = frozenset({
    "actix-web", "axum", "rocket", "warp", "tide",
    "tauri", "dioxus", "leptos", "yew",
})

_ALL_FRAMEWORK_DEPS = _FRAMEWORK_DEPS_NPM | _FRAMEWORK_DEPS_PYTHON | _FRAMEWORK_DEPS_RUST


# ---------------------------------------------------------------------------
# Core vs non-core members
#
# In a monorepo, a `bin` field or framework dependency from an examples /
# devtools / tooling member must NOT flip the whole repo to `reference-app`.
# A manifest is "non-core" when it lives under a non-core directory or its
# package name marks it as a demo / example / dev-tool. Only core members
# drive the app-shape (`reference-app`) signals; library detection still uses
# every manifest.
# ---------------------------------------------------------------------------

_NON_CORE_PATH_SEGMENTS = frozenset({
    "example", "examples", "demo", "demos", "sample", "samples",
    "playground", "playgrounds", "e2e", "benchmark", "benchmarks", "bench",
    "fixture", "fixtures", "website", "websites", "www",
    "docs", "doc", "scripts", "tools", "tooling", "devtools", "dev-tools",
    "test", "tests", "__tests__", "integration", "smoke",
})

_NON_CORE_NAME_FRAGMENTS = (
    "devtools", "dev-tools", "example", "playground", "benchmark",
    "fixture", "e2e", "codemod", "upgrade", "eslint-plugin", "eslint-config",
)


def is_core_manifest(rel_path: str, pkg_name: str) -> bool:
    """Whether a manifest counts toward app-shape (`reference-app`) signals.

    Non-core when any path segment is a known non-core directory, or the
    package name contains a dev/demo/tooling fragment. Keeps a single CLI,
    example, or devtools package in a library monorepo from masquerading the
    whole repo as an application.
    """
    for seg in Path(rel_path).parts:
        if seg.lower() in _NON_CORE_PATH_SEGMENTS:
            return False
    name = (pkg_name or "").lower()
    return not any(frag in name for frag in _NON_CORE_NAME_FRAGMENTS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _die(message: str, code: str = "INTERNAL_ERROR") -> None:
    json.dump({"error": message, "code": code}, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.exit(2)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _is_grammar_file(path: str) -> bool:
    """Whether a repo-relative path is a declared grammar file.

    Matched on whole basename (tree-sitter `grammar.js`, CPython
    `python.gram`) or extension (`.y`, `.g4`, `.pest`, ...) — never substring,
    so a file merely named `grammar_test_data.txt` does not match.
    """
    name = Path(path).name.lower()
    if name in _GRAMMAR_BASENAMES:
        return True
    return Path(name).suffix in _GRAMMAR_EXTS


def _whole_language_tree(tree_paths: list[str]) -> tuple[str, str] | None:
    """Detect a hand-written compiler from directory/structural signals.

    Returns ``(compiler_dir, member_summary)`` when ``tree_paths`` satisfies all
    three structural gates from issue #427, else ``None``:

      (C) a DEDICATED compiler directory — a real directory (trailing ``/``)
          whose path-tail is in ``_COMPILER_DIRS`` (case-insensitive) or
          ``_COMPILER_DIRS_CASE`` (case-sensitive ``Parser``). A file named
          ``Parser.js`` or ``compiler.dart`` never satisfies this; a bare
          ``src/`` / ``lib/`` / ``src/language/`` directory never does either.
      (D) a lexer+parser+AST triad, parser MANDATORY, at least 2 of 3 present,
          among the members NEAR that compiler directory (_near_compiler_dir):
          a large library's lexer and parser in an unrelated corner of the
          tree (PyTorch's TorchScript frontend beside its torch/compiler/ API
          package) are no compiler's triad.
      (W) a corroborating codegen / VM / type-checker member anywhere in the
          tree, so a markdown or CSS library (lexer+parser+AST only) does not
          qualify.

    Gates G (delegating consumer) and L (markup identity) depend on manifest
    data and are applied by the caller.
    """
    if not tree_paths:
        return None

    compiler_dirs: list[str] = []
    members_of: list[tuple[str, str, str]] = []  # (path, basename, stem)
    for tp in tree_paths:
        norm = tp.rstrip("/")
        if not norm:
            continue
        base = norm.rsplit("/", 1)[-1]
        members_of.append((norm, base, base.rsplit(".", 1)[0].lower() if "." in base else base.lower()))
        if tp.endswith("/"):
            low = norm.lower()
            if any(low == m or low.endswith("/" + m) for m in _COMPILER_DIRS) or \
               any(norm == m or norm.endswith("/" + m) for m in _COMPILER_DIRS_CASE):
                compiler_dirs.append(norm)

    # (C)
    if not compiler_dirs:
        return None

    # (W): a corroborating compiler-grade member, anywhere in the tree
    stems = {stem for _, _, stem in members_of}
    w = bool(stems & (_CODEGEN_STEMS | _VM_STEMS | _CHECK_STEMS)) or \
        any(base.startswith("rustc_codegen") for _, base, _ in members_of)
    if not w:
        return None

    # (D): a triad near a compiler directory, parser mandatory, >= 2 of 3
    for compiler_dir in compiler_dirs:
        near = [(base, stem) for path, base, stem in members_of if _near_compiler_dir(path, compiler_dir)]
        stems = {stem for _, stem in near}
        basenames = {base for base, _ in near}
        lexer = bool(stems & _LEXER_STEMS) or "rustc_lexer" in basenames
        parser = bool(stems & _PARSER_STEMS) or "rustc_parse" in basenames
        ast = (bool(stems & _AST_STEMS) or "rustc_ast" in basenames
               or ("binder" in stems and "checker" in stems))
        if parser and (lexer + parser + ast) >= 2:
            members = ",".join(
                m for m, present in (("lexer", lexer), ("parser", parser), ("ast", ast))
                if present
            )
            return compiler_dir, members
    return None


def _near_compiler_dir(path: str, compiler_dir: str) -> bool:
    """Whether a tree path is near a compiler directory, for gate D: the
    directory itself or a path under it, or a path at most two levels below
    the directory that holds it (CPython's Parser/ has Python/ast.c beside
    it, the Go port's internal/compiler/ has internal/parser/parser.go)."""
    if path == compiler_dir or path.startswith(compiler_dir + "/"):
        return True
    parent = compiler_dir.rsplit("/", 1)[0] if "/" in compiler_dir else ""
    if parent and not path.startswith(parent + "/"):
        return False
    return path[len(parent) + 1 if parent else 0:].count("/") <= 1


def tree_signals(files: list[str]) -> tuple[list[str], list[str]]:
    """(grammar files, tree paths) of a repository's whole file list, the
    tree-level inputs of detect(): the grammar files _is_grammar_file()
    accepts at most _GRAMMAR_MAX_DEPTH segments deep and not below a
    _FORMAT_PARSER_DIRS folder under the top one, and every folder (with
    a trailing /) then every file as tree paths, so the gates of
    _whole_language_tree(), not a name filter, decide what counts. A path
    with a hidden segment or a segment of _NON_CORE_PATH_SEGMENTS (tests and
    fixtures, docs, examples, benchmarks, scripts and tools) is left out of
    both: a CI workflow, a script or a test fixture is not the repository's
    own code. An entry that ends in / is a folder."""
    grammar: set[str] = set()
    dirs: set[str] = set()
    names: set[str] = set()
    for raw in files:
        entry = raw.strip()
        parts = [p for p in entry.split("/") if p and p != "."]
        if not parts or any(p.startswith(".") or p.lower() in _NON_CORE_PATH_SEGMENTS for p in parts):
            continue
        path = "/".join(parts)
        if entry.endswith("/"):
            dirs.add(path + "/")
        else:
            names.add(path)
            if (len(parts) <= _GRAMMAR_MAX_DEPTH and _is_grammar_file(path)
                    and not any(p.lower() in _FORMAT_PARSER_DIRS for p in parts[1:-1])):
                grammar.add(path)
        for depth in range(1, len(parts)):
            dirs.add("/".join(parts[:depth]) + "/")
    return sorted(grammar), sorted(dirs) + sorted(names)


_SIBLINGS: dict[str, Any] = {}


def _sibling(filename: str) -> Any:
    """A helper of this folder, loaded once as a module: skf-detect-language.py
    reads a --tree-file listing. Raises ImportError when it does not sit
    beside this script."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        name = "skf_" + filename.removeprefix("skf-").removesuffix(".py").replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {filename} beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, SyntaxError) as exc:
            raise ImportError(f"cannot load {filename} beside {Path(__file__).name}: {exc}") from exc
        _SIBLINGS[filename] = module
    return module


def _parse_toml(content: str) -> dict[str, Any]:
    return tomllib.loads(content)


# ---------------------------------------------------------------------------
# Manifest parsers — each returns a normalised dict
# ---------------------------------------------------------------------------

def _parse_package_json(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}  # unreachable

    if not isinstance(data, dict):
        _die(f"Expected JSON object in {path.as_posix()}, got {type(data).__name__}", "MANIFEST_PARSE_ERROR")
        return {}  # unreachable

    deps: set[str] = set()
    runtime_deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section)
            # Only hard `dependencies` signal app-ness: a framework in
            # devDependencies means "tested against", in peerDependencies means
            # "this is an adapter for it" — both are library behaviour.
            if key == "dependencies":
                runtime_deps.update(section)

    exports_field = data.get("exports")
    export_count = 0
    if isinstance(exports_field, dict):
        export_count = len(exports_field)
    elif isinstance(exports_field, str):
        export_count = 1
    elif data.get("main") or data.get("module"):
        export_count = 1

    return {
        "ecosystem": "npm",
        "name": data.get("name", ""),
        "deps": deps,
        "runtime_deps": runtime_deps,
        "has_bin": bool(data.get("bin")),
        "has_library_structure": bool(
            data.get("main") or data.get("module") or exports_field
        ),
        "export_count": export_count,
    }


def _dep_name_from_pep508(spec: str) -> str:
    """Extract package name from a PEP 508 dependency string."""
    for ch in (">", "<", "=", "!", "[", ";", " "):
        spec = spec.split(ch, 1)[0]
    return spec.strip().lower()


def _parse_pyproject_toml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = _parse_toml(content)
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}
    except Exception as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}

    project = data.get("project", {})
    if not isinstance(project, dict):
        project = {}

    deps: set[str] = set()
    for raw in project.get("dependencies", []):
        if isinstance(raw, str):
            name = _dep_name_from_pep508(raw)
            if name:
                deps.add(name)
    poetry_deps = (
        data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    )
    if isinstance(poetry_deps, dict):
        deps.update(k.lower() for k in poetry_deps if k.lower() != "python")

    scripts = project.get("scripts", {})
    gui_scripts = project.get("gui-scripts", {})
    if not isinstance(scripts, dict):
        scripts = {}
    if not isinstance(gui_scripts, dict):
        gui_scripts = {}
    export_count = len(scripts) + len(gui_scripts)
    if export_count == 0 and project.get("name"):
        export_count = 1

    return {
        "ecosystem": "python",
        "name": project.get("name", ""),
        "deps": deps,
        "runtime_deps": set(deps),
        "has_bin": False,
        "has_library_structure": bool(project.get("name")),
        "export_count": export_count,
    }


def _parse_cargo_toml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = _parse_toml(content)
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}
    except Exception as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}

    pkg = data.get("package", {})
    if not isinstance(pkg, dict):
        pkg = {}

    deps: set[str] = set()
    runtime_deps: set[str] = set()
    for dep_key in ("dependencies", "dev-dependencies", "build-dependencies"):
        section = data.get(dep_key, {})
        if isinstance(section, dict):
            deps.update(k.lower() for k in section)
            if dep_key == "dependencies":
                runtime_deps.update(k.lower() for k in section)

    has_lib = "lib" in data and isinstance(data["lib"], dict)
    bin_targets = data.get("bin", [])
    if not isinstance(bin_targets, list):
        bin_targets = []
    has_bin = len(bin_targets) > 0

    export_count = (1 if has_lib else 0) + len(bin_targets)
    if export_count == 0 and pkg.get("name"):
        export_count = 1

    workspace_members = data.get("workspace", {}).get("members", [])
    if not isinstance(workspace_members, list):
        workspace_members = []

    return {
        "ecosystem": "rust",
        "name": pkg.get("name", ""),
        "deps": deps,
        "runtime_deps": runtime_deps,
        "has_bin": has_bin,
        "has_library_structure": has_lib or bool(pkg.get("name")),
        "export_count": export_count,
    }


def _parse_go_mod(path: Path) -> dict[str, Any]:
    """Parse a go.mod: the module path (name) and required modules (deps).

    go.mod is line-oriented — `module <path>`, single-line `require <mod> <ver>`,
    and a `require ( ... )` block. The scanner already recognises go.mod; this
    mirror lets shape-detect classify Go repos (most resolve to library-API;
    the Go toolchain itself is caught by the tree-triad rung).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}  # unreachable

    module = ""
    deps: set[str] = set()
    in_require_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if in_require_block:
            if stripped.startswith(")"):
                in_require_block = False
                continue
            deps.add(stripped.split()[0].lower())
            continue
        if stripped.startswith("module "):
            module = stripped[len("module "):].strip()
        elif stripped.startswith("require ("):
            in_require_block = True
        elif stripped.startswith("require "):
            parts = stripped[len("require "):].split()
            if parts:
                deps.add(parts[0].lower())

    return {
        "ecosystem": "go",
        "name": module,
        "deps": deps,
        "runtime_deps": set(deps),
        # A go.mod under a cmd/ path marks a command (binary) member.
        "has_bin": "cmd" in Path(path).parts,
        "has_library_structure": bool(module),
        "export_count": 0,
    }


# Maven build plugins that turn a jar into an executable/deployable app — used
# to mark a pom.xml as a binary (reference-app) rather than a library.
_MAVEN_APP_PLUGINS = (
    "spring-boot-maven-plugin",
    "maven-shade-plugin",
    "exec-maven-plugin",
    "maven-assembly-plugin",
)


def _parse_pom_xml(path: Path) -> dict[str, Any]:
    """Parse a Maven pom.xml: artifactId (name) and non-test dependency coords.

    The scanner already recognises pom.xml; this mirror lets shape-detect
    classify Maven repos (most resolve to library-API via the artifactId; an
    app/exec/assembly plugin or `war` packaging marks a deployable app).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}  # unreachable

    # Project artifactId: strip <parent>/<dependencies>/<build> first so the
    # project's own artifactId is matched, not a parent's or a dependency's.
    trimmed = content
    for tag in ("parent", "dependencies", "dependencyManagement", "build"):
        trimmed = re.sub(rf"<{tag}>.*?</{tag}>", "", trimmed, flags=re.DOTALL | re.IGNORECASE)
    aid = re.search(r"<artifactId>\s*(.*?)\s*</artifactId>", trimmed, re.DOTALL)
    name = aid.group(1).strip() if aid else ""

    deps: set[str] = set()
    for block in re.finditer(r"<dependency>(.*?)</dependency>", content, re.DOTALL):
        body = block.group(1)
        scope_m = re.search(r"<scope>\s*(.*?)\s*</scope>", body, re.DOTALL)
        if scope_m and scope_m.group(1).strip().lower() in {"test", "provided", "system"}:
            continue
        d_aid = re.search(r"<artifactId>\s*(.*?)\s*</artifactId>", body, re.DOTALL)
        if d_aid:
            deps.add(d_aid.group(1).strip().lower())

    pkg_m = re.search(r"<packaging>\s*(.*?)\s*</packaging>", content, re.DOTALL)
    packaging = pkg_m.group(1).strip().lower() if pkg_m else "jar"
    lc = content.lower()
    has_bin = packaging == "war" or any(p in lc for p in _MAVEN_APP_PLUGINS)

    return {
        "ecosystem": "maven",
        "name": name,
        "deps": deps,
        "runtime_deps": set(deps),
        "has_bin": has_bin,
        "has_library_structure": bool(name),
        "export_count": 0,
    }


def _parse_gradle(path: Path) -> dict[str, Any]:
    """Parse a Gradle build script (Groovy or Kotlin DSL): dependency coords.

    Gradle scripts rarely declare their own coordinate name, so — like go.mod's
    bool(module) precedent — a present build script marks a buildable module
    (has_library_structure=True). An `application` plugin (or an Android/Spring
    app plugin) marks a deployable app (reference-app).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}  # unreachable

    deps: set[str] = set()
    for m in re.finditer(
        r"(?:implementation|api|compile|runtimeOnly)\s*\(?\s*['\"]([^'\"]+)['\"]",
        content,
    ):
        parts = m.group(1).split(":")
        if len(parts) >= 2:
            deps.add((parts[0] + ":" + parts[1]).lower())

    has_bin = bool(
        re.search(
            r"id\s*\(?\s*['\"]application['\"]"
            r"|apply\s+plugin:\s*['\"]application['\"]"
            r"|^\s*application\s*\{"
            r"|com\.android\.application"
            r"|org\.springframework\.boot",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
    )

    return {
        "ecosystem": "gradle",
        "name": "",
        "deps": deps,
        "runtime_deps": set(deps),
        "has_bin": has_bin,
        "has_library_structure": True,
        "export_count": 0,
    }


def _parse_package_swift(path: Path) -> dict[str, Any]:
    """Parse a SwiftPM Package.swift: package name and dependency package names.

    A `.library`/`.target` declaration (or a name) marks a library; an
    `.executableTarget`/`.executable` product marks a CLI (reference-app).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}  # unreachable

    name_m = re.search(r"\bPackage\s*\(\s*name:\s*['\"]([^'\"]+)['\"]", content, re.DOTALL)
    name = name_m.group(1).strip() if name_m else ""

    deps: set[str] = set()
    for m in re.finditer(r"\.package\s*\(\s*url:\s*['\"]([^'\"]+)['\"]", content):
        seg = m.group(1).rstrip("/").rsplit("/", 1)[-1]
        if seg.endswith(".git"):
            seg = seg[: -len(".git")]
        if seg:
            deps.add(seg.lower())

    has_exec = bool(re.search(r"\.executableTarget\s*\(|\.executable\s*\(", content))
    has_lib = bool(re.search(r"\.library\s*\(|\.target\s*\(", content)) or bool(name)

    return {
        "ecosystem": "swift",
        "name": name,
        "deps": deps,
        "runtime_deps": set(deps),
        "has_bin": has_exec,
        "has_library_structure": has_lib,
        "export_count": 0,
    }


_PARSERS = {
    "package.json": _parse_package_json,
    "pyproject.toml": _parse_pyproject_toml,
    "Cargo.toml": _parse_cargo_toml,
    "go.mod": _parse_go_mod,
    "pom.xml": _parse_pom_xml,
    "build.gradle": _parse_gradle,
    "build.gradle.kts": _parse_gradle,
    "Package.swift": _parse_package_swift,
}


def _parse_manifest(path: Path) -> dict[str, Any]:
    parser = _PARSERS.get(path.name)
    if parser is None:
        _die(f"Unsupported manifest type: {path.name}", "UNSUPPORTED_MANIFEST")
    return parser(path)


def read_manifests_file(path: str) -> list[str]:
    """The manifest paths of a skf-scan-manifests.py envelope that this
    script classifies (a _PARSERS file name), in the envelope's order and
    as the envelope spells them: relative to the folder the scan ran on."""
    try:
        envelope = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _die(f"cannot read the manifests file {path}: {exc}", "MANIFESTS_FILE_ERROR")
    entries = envelope.get("manifests") if isinstance(envelope, dict) else None
    if not isinstance(entries, list):
        _die(f"{path} is not a skf-scan-manifests.py envelope: it has no manifests list",
             "MANIFESTS_FILE_ERROR")
    paths: list[str] = []
    for entry in entries:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or not rel:
            _die(f"{path}: a manifests entry has no path", "MANIFESTS_FILE_ERROR")
        rel = rel.replace("\\", "/")
        if rel.rsplit("/", 1)[-1] in _PARSERS and rel not in paths:
            paths.append(rel)
    return paths


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def detect(
    repo_url: str,
    manifest_paths: list[str],
    grammar_files: list[str] | None = None,
    tree_paths: list[str] | None = None,
    manifest_dir: str | None = None,
) -> dict[str, Any]:
    """Classify a repo into a skill shape from its manifest files.

    `grammar_files` (grammar files like Grammar/python.gram, *.y, *.g4) and
    `tree_paths` (repo-relative directory/structural signals) are optional
    tree-level signals harvested from the clone; they let whole-language repos
    that carry no parser-generator dependency — and even manifest-less ones —
    be classified. When all three inputs are empty there is nothing to
    classify and we error, exactly as before. With `manifest_dir`, each
    manifest path is relative to it: the file read is the joined path, and
    the core and depth checks see the relative one.
    """
    grammar_files = grammar_files or []
    tree_paths = tree_paths or []
    if not manifest_paths and not grammar_files and not tree_paths:
        _die("--manifests requires at least one path", "MISSING_MANIFESTS")

    parsed: list[dict[str, Any]] = []
    for mp in manifest_paths:
        p = Path(manifest_dir) / mp if manifest_dir is not None else Path(mp)
        if not p.is_file():
            _die(f"Manifest not found: {p.as_posix()}", "MANIFEST_NOT_FOUND")
        m = _parse_manifest(p)
        m["_path"] = mp
        m["_core"] = is_core_manifest(mp, m.get("name", ""))
        parsed.append(m)

    all_deps: set[str] = set()
    all_runtime_deps: set[str] = set()
    core_runtime_deps: set[str] = set()
    ecosystems: set[str] = set()
    total_exports = 0
    signals: list[str] = []
    has_bin = False         # any manifest
    core_has_bin = False    # app-eligible manifests only
    has_library_structure = False

    package_count = len(parsed)

    # In a monorepo, a *coordinator* root (the unique shallowest manifest that has
    # no library structure of its own) holds build/script deps, not the product —
    # exclude it from app-shape signals. A root that is itself the published
    # library (has main/exports) stays in.
    depths = [len(Path(m["_path"]).parts) for m in parsed]
    min_depth = min(depths) if depths else -1
    root_coord_idx = -1
    if package_count > 1 and depths.count(min_depth) == 1:
        cand = depths.index(min_depth)
        if not parsed[cand].get("has_library_structure"):
            root_coord_idx = cand
    if root_coord_idx >= 0:
        signals.append("monorepo_root_coordinator_excluded")

    for idx, m in enumerate(parsed):
        eco = m["ecosystem"]
        ecosystems.add(eco)
        signals.append(f"has_{path_to_manifest_name(eco)}")
        all_deps.update(m.get("deps", set()))
        all_runtime_deps.update(m.get("runtime_deps", set()))
        total_exports += m.get("export_count", 0)
        if m.get("has_bin"):
            has_bin = True
        if m.get("has_library_structure"):
            has_library_structure = True
        # App-shape signals: core members, excluding the monorepo root coordinator.
        if m.get("_core") and idx != root_coord_idx:
            core_runtime_deps.update(m.get("runtime_deps", set()))
            if m.get("has_bin"):
                core_has_bin = True

    # `reference-app` signals come from core members' RUNTIME deps only: a
    # framework in devDependencies (testing/building against it), in an
    # examples/devtools member, or in the monorepo coordinator root does not make
    # the repo an application.
    app_has_bin = core_has_bin
    app_runtime = core_runtime_deps
    framework_deps = sorted(d for d in app_runtime if d.lower() in _ALL_FRAMEWORK_DEPS)
    has_framework = len(framework_deps) > 0

    # Excluded app signals are surfaced separately so the classification stays
    # explainable: non-core runtime frameworks, and dev-only frameworks.
    noncore_framework = sorted(
        d for d in (all_runtime_deps - app_runtime) if d.lower() in _ALL_FRAMEWORK_DEPS
    )
    dev_framework = sorted(
        d for d in (all_deps - all_runtime_deps) if d.lower() in _ALL_FRAMEWORK_DEPS
    )
    noncore_has_bin = has_bin and not app_has_bin

    if total_exports > 50:
        signals.append("exports_count_gt_50")
    if app_has_bin:
        signals.append("has_bin_field")
    elif has_library_structure:
        signals.append("no_bin_field")
    if noncore_has_bin:
        signals.append("has_bin_field_noncore")
    if has_library_structure:
        signals.append("has_library_structure")

    # Collect parser/grammar signals — both directions of the relationship.
    #
    # PRODUCER (issue #427): a repo whose own published package name is itself a
    # known parser/grammar tool IS language tooling — pest, lalrpop, lark, peggy
    # name *themselves*. A language tool's repo does not depend on a parser
    # generator; it is one, so the old dependency-only check never fired for it.
    # This keys on own-name ∈ parser-gen-set ONLY — never on substring tokens
    # like "parser"/"compiler"/"lang", which are false-positive farms (a CSS
    # parser, compiler-builtins, an arg parser are ordinary libraries).
    #
    # CONSUMER: a project with a parser tool among its core members' RUNTIME
    # deps, read like the framework signals above: a dev or build dependency
    # tests or builds the project, and an examples/ member or the coordinator
    # root is not the product. It may be a language built on the tool (a DSL
    # on lalrpop) or only read its input with it (a CLI on nom), so it
    # decides no shape: the ladder asks (below). Exclude the repo's own
    # producer name from the consumer list so a self-reference isn't
    # double-counted as "uses".
    own_names = {
        (m.get("name") or "").strip().lower() for m in parsed if m.get("name")
    }
    parser_producers = sorted(n for n in own_names if n in _ALL_PARSER_DEPS)
    parser_deps = sorted(
        d for d in core_runtime_deps
        if d.lower() in _ALL_PARSER_DEPS and d.lower() not in parser_producers
    )

    for d in parser_producers:
        signals.append(f"parser_producer:{d}")
    for d in parser_deps:
        signals.append(f"parser_dep:{d}")

    # Tree-level whole-language signals (issue #427). A grammar file is the
    # strongest, most intentional signal; the compiler-directory triad (a later
    # rung) catches hand-written compilers. Two guard gates keep formatters,
    # linters, bundlers, and markup/DSL parsers out.
    grammar_matches = sorted(
        {Path(g).name for g in grammar_files if _is_grammar_file(g)}
    )
    for g in grammar_matches:
        signals.append(f"grammar_file:{g}")

    # Gate G — delegating-consumer exclusion. A repo that depends on a concrete
    # parser (prettier→@babel/parser, eslint→espree) or whose own name is a
    # known formatter/linter/bundler delegates parsing; never a whole-language
    # reference, even if it ships a parser-ish module of its own.
    runtime_deps_lc = {d.lower() for d in all_runtime_deps}
    delegating_consumer = bool(runtime_deps_lc & _CONSUMED_PARSERS) or bool(
        own_names & _DELEGATING_TOOL_NAMES
    )
    if delegating_consumer:
        signals.append("delegating_consumer")
    # Gate L — language identity. A markup/DSL/format parser (postcss, marked,
    # graphql-js) has a real lexer+parser+AST but is not a general-purpose
    # programming-language reference.
    markup_identity = bool(
        own_names & (_MARKUP_DSL_NAMES | _DELEGATING_TOOL_NAMES)
    )

    for d in framework_deps:
        signals.append(f"framework_dep:{d}")
    for d in noncore_framework:
        signals.append(f"framework_dep_noncore:{d}")
    for d in dev_framework:
        signals.append(f"framework_dep_dev:{d}")
    if len(ecosystems) > 1:
        signals.append("multiple_ecosystems")
        for eco in sorted(ecosystems):
            signals.append(f"ecosystem:{eco}")

    result_base = {
        "export_count": total_exports,
        "package_count": package_count,
    }

    # --- Heuristic ladder (first match wins) ---

    # 1a-pre. language-reference — a hand-written compiler detected from tree
    # structure (issue #427): a dedicated compiler/ directory holding a
    # lexer+parser+AST triad plus a codegen/VM/type-checker member. This catches
    # rustc, TypeScript, and the Go toolchain, which declare no parser-generator
    # dependency and carry no grammar file. Ranked first so it outranks the
    # bin→reference-app rung (TypeScript ships `tsc`). Gates G and L still apply.
    tree_triad = _whole_language_tree(tree_paths)
    if tree_triad and not delegating_consumer and not markup_identity:
        compiler_dir, members = tree_triad
        signals.append(f"tree_triad:{compiler_dir}:{members}")
        return {"shape": "language-reference", "signals": signals,
                "confidence": 0.85, **result_base}

    # 1a. language-reference — a declared grammar file (issue #427). A repo that
    # ships a grammar (Grammar/python.gram, parse.y, a *.g4) authors a language.
    # This is the strongest signal and ranks above the dependency-based rung so
    # a real grammar outranks an incidental parser dep from a sub-tool. Gate G
    # excludes delegating consumers; gate L excludes markup/DSL parsers.
    if grammar_matches and not delegating_consumer and not markup_identity:
        confidence = _clamp(0.85 + len(grammar_matches) * 0.02, 0.85, 0.90)
        return {"shape": "language-reference", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 1b. language-reference: a parser/grammar producer (own name).
    if parser_producers:
        n_sig = len(parser_producers) + len(parser_deps)
        confidence = _clamp(0.80 + n_sig * 0.05, 0.80, 0.90)
        return {"shape": "language-reference", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # A consumer dep fits a language built on the parser tool and a project
    # that only reads its input with it alike: the dependency names alone
    # cannot tell them apart, so the rungs below answer with their own shape
    # and this signal hands that question to the caller. Gates G and L hold
    # here too: a repo they exclude is no language reference either way.
    parser_question = bool(parser_deps) and not delegating_consumer and not markup_identity
    if parser_question:
        signals.append("language_or_user:parser_dep")

    # 2. stack-compose
    if len(ecosystems) > 1:
        confidence = _clamp(0.80 + (len(ecosystems) - 2) * 0.05, 0.80, 0.90)
        return {"shape": "stack-compose", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 3. reference-app — an application/CLI built on a framework. In a monorepo
    # a lone `bin` (a tooling package among libraries) is not enough; require a
    # core runtime framework. A single-package repo with a bin is an app.
    app_trigger = has_framework if package_count > 1 else (app_has_bin or has_framework)
    if app_trigger:
        # A framework dependency with no bin, in a package that names itself a
        # library, fits an app built on the framework and a library that
        # extends it (FastAPI on starlette, axum-extra on axum) alike: the
        # dependency names alone cannot tell them apart, so the signal hands
        # that question to the caller and the shape stays reference-app.
        if not app_has_bin and has_library_structure:
            signals.append("app_or_library:framework_dep")
        strength = (1 if app_has_bin else 0) + (1 if has_framework else 0)
        confidence = _clamp(0.80 + (strength - 1) * 0.05, 0.80, 0.90)
        return {"shape": "reference-app", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 4. library-API
    if has_library_structure or total_exports > 0:
        base = 0.65
        if has_library_structure:
            base = 0.80
        if total_exports > 50:
            base = max(base, 0.90)
        elif total_exports > 10:
            base = max(base, 0.80)
        confidence = _clamp(base, 0.65, 0.95)
        return {"shape": "library-API", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 5. language-reference: a consumer dep is the repository's only signal (a
    # bare DSL manifest: no rung above answered and no manifest declares a
    # bin), so no other shape is left to weigh the question against. A bin
    # that rung 3 does not count (the bin-only members of a monorepo) is an
    # app signal all the same: such a repository stays unknown, like its twin
    # with no parser dependency, and the caller analyzes it interactively.
    if parser_question and not has_bin:
        signals.remove("language_or_user:parser_dep")
        return {"shape": "language-reference", "signals": signals,
                "confidence": 0.75, **result_base}

    # 6. unknown: the interactive fallback weighs the parser itself, with no
    # shape for the question to qualify.
    if parser_question:
        signals.remove("language_or_user:parser_dep")
    return {"shape": "unknown", "signals": signals,
            "confidence": 0.0, **result_base}


def path_to_manifest_name(ecosystem: str) -> str:
    return {"npm": "package_json", "python": "pyproject_toml",
            "rust": "cargo_toml", "go": "go_mod",
            "maven": "pom_xml", "gradle": "build_gradle",
            "swift": "package_swift"}.get(ecosystem, ecosystem)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8 (issue #465).

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (ensure_ascii=False output, raw UTF-8 input). Preserves
    each stream's existing error handler — reconfigure(encoding=...) alone
    would reset it to 'strict', downgrading e.g. an already-UTF-8 stderr on
    Linux. For stdin this must run before the first read. Skips in-process
    test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str]) -> int:
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    parser = argparse.ArgumentParser(
        description="Classify a repo into a known skill shape from its manifest files.",
    )
    parser.add_argument("--repo-url", required=True, help="Repository URL")
    parser.add_argument(
        "--manifests", default=None,
        help="Comma-separated local file paths to manifest files (may be empty "
             "when --tree-file, --grammar-files or --tree-paths carry the signal); "
             "required unless --manifests-file is given",
    )
    parser.add_argument(
        "--manifests-file", default=None,
        help="The JSON envelope skf-scan-manifests.py scan printed, in place of "
             "--manifests: its manifests of the types this script classifies, "
             "each path resolved against --manifest-dir",
    )
    parser.add_argument(
        "--manifest-dir", default=None,
        help="The folder the scan ran on (required with --manifests-file)",
    )
    parser.add_argument(
        "--tree-file", default=None,
        help="The repository's whole file list: JSON (a `tree` list, or a list) or "
             "one path per line; - reads stdin. Replaces --grammar-files and --tree-paths",
    )
    parser.add_argument(
        "--grammar-files", default="",
        help="Comma-separated repo-relative grammar file paths (*.y, *.g4, "
             "*.pest, Grammar/python.gram, ...)",
    )
    parser.add_argument(
        "--tree-paths", default="",
        help="Comma-separated repo-relative directory (trailing /) and "
             "structural file signals harvested from the clone",
    )
    args = parser.parse_args(argv)

    if args.manifests_file is not None:
        if args.manifests is not None:
            _die("pass the manifests once: --manifests or --manifests-file", "INVALID_ARGS")
        if args.manifest_dir is None:
            _die("--manifests-file needs --manifest-dir, the folder the scan ran on", "INVALID_ARGS")
        manifest_paths = read_manifests_file(args.manifests_file)
    elif args.manifests is None:
        _die("--manifests or --manifests-file is required", "MISSING_MANIFESTS")
    else:
        if args.manifest_dir is not None:
            _die("--manifest-dir goes with --manifests-file", "INVALID_ARGS")
        manifest_paths = [p.strip() for p in args.manifests.split(",") if p.strip()]
    grammar_files = [p.strip() for p in args.grammar_files.split(",") if p.strip()]
    tree_paths = [p.strip() for p in args.tree_paths.split(",") if p.strip()]
    truncated = False
    if args.tree_file is not None:
        if grammar_files or tree_paths:
            _die("pass the tree once: --tree-file, or --grammar-files and --tree-paths", "INVALID_ARGS")
        try:
            files, truncated = _sibling("skf-detect-language.py").read_tree_file(args.tree_file)
        except (ImportError, ValueError) as exc:  # ValueError: the sibling's TreeListingError
            _die(str(exc), "TREE_FILE_ERROR")
        grammar_files, tree_paths = tree_signals(files)
    if not manifest_paths and not grammar_files and not tree_paths:
        if args.tree_file is None:
            _die("--manifests requires at least one path", "MISSING_MANIFESTS")
        # The listing holds only paths tree_signals() leaves out (hidden,
        # tests, docs, scripts): no signal to classify.
        result = {"shape": "unknown", "signals": [], "confidence": 0.0, "export_count": 0, "package_count": 0}
    else:
        result = detect(args.repo_url, manifest_paths, grammar_files, tree_paths, args.manifest_dir)
    if truncated:
        result["signals"].append("tree_truncated")
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    return 1 if result["shape"] == "unknown" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
