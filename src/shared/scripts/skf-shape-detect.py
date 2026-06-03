# /// script
# requires-python = ">=3.9"
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
     Signals: parser-related deps (pest, antlr4, tree-sitter, lark ...)
  2. stack-compose     — multi-ecosystem composite project
     Signals: manifests from 2+ distinct ecosystems
  3. reference-app     — application, CLI, or demo project
     Signals: npm bin field, Rust [[bin]], framework deps
  4. library-API       — library exposing a programmatic API
     Signals: main/module/exports fields, [lib] target, export count
  5. unknown           — no heuristic matched

CLI:
  uv run src/shared/scripts/skf-shape-detect.py \\
      --repo-url <url> --manifests <path1,path2,...>

Input:
  --repo-url      repository URL (required; context only, no cloning)
  --manifests     comma-separated local file paths to manifest files (may be
                  empty when a tree-level signal is supplied instead)
  --grammar-files comma-separated repo-relative grammar files (*.y, *.g4,
                  *.pest, Grammar/python.gram, ...); a whole-language signal
  --tree-paths    comma-separated repo-relative directory/structural signals
                  harvested from the clone (compiler/ dir, lexer/parser/ast)

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
  2  error (invalid args, missing/unreadable files, parse failure)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Parser/grammar deps that signal language-reference shape
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
      (D) a lexer+parser+AST triad, parser MANDATORY, at least 2 of 3 present.
      (W) a corroborating codegen / VM / type-checker member, so a markdown or
          CSS library (lexer+parser+AST only) does not qualify.

    Gates G (delegating consumer) and L (markup identity) depend on manifest
    data and are applied by the caller.
    """
    if not tree_paths:
        return None

    compiler_dirs: list[str] = []
    stems: set[str] = set()
    basenames: set[str] = set()
    for tp in tree_paths:
        norm = tp.rstrip("/")
        if not norm:
            continue
        base = norm.rsplit("/", 1)[-1]
        basenames.add(base)
        stems.add(base.rsplit(".", 1)[0].lower() if "." in base else base.lower())
        if tp.endswith("/"):
            low = norm.lower()
            if any(low == m or low.endswith("/" + m) for m in _COMPILER_DIRS) or \
               any(norm == m or norm.endswith("/" + m) for m in _COMPILER_DIRS_CASE):
                compiler_dirs.append(norm)

    # (C)
    if not compiler_dirs:
        return None

    # (D) — triad, parser mandatory, >= 2 of 3
    lexer = bool(stems & _LEXER_STEMS) or "rustc_lexer" in basenames
    parser = bool(stems & _PARSER_STEMS) or "rustc_parse" in basenames
    binder, checker = "binder" in stems, "checker" in stems
    ast = (bool(stems & _AST_STEMS) or "rustc_ast" in basenames
           or (binder and checker))
    if not parser or (lexer + parser + ast) < 2:
        return None

    # (W) — corroborating compiler-grade member
    w = bool(stems & (_CODEGEN_STEMS | _VM_STEMS | _CHECK_STEMS)) or \
        any(b.startswith("rustc_codegen") for b in basenames)
    if not w:
        return None

    members = ",".join(
        m for m, present in (("lexer", lexer), ("parser", parser), ("ast", ast))
        if present
    )
    return compiler_dirs[0], members


# ---------------------------------------------------------------------------
# Minimal TOML parser (Python < 3.11 fallback)
# ---------------------------------------------------------------------------

def _split_preserving_nesting(s: str, sep: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = ""
    for ch in s:
        if in_str:
            buf.append(ch)
            if ch == in_str:
                in_str = ""
            continue
        if ch in ('"', "'"):
            in_str = ch
            buf.append(ch)
            continue
        if ch in ("[", "{"):
            depth += 1
            buf.append(ch)
            continue
        if ch in ("]", "}"):
            depth -= 1
            buf.append(ch)
            continue
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _decode_toml_value(raw: str) -> Any:
    s = raw.strip()
    if not s:
        return ""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    if s.startswith("["):
        idx = s.rfind("]")
        if idx < 0:
            return []
        inner = s[1:idx].strip()
        if not inner:
            return []
        items = []
        for item in _split_preserving_nesting(inner, ","):
            item = item.strip()
            if item and item[0] != "#":
                items.append(_decode_toml_value(item))
        return items
    if s.startswith("{"):
        idx = s.rfind("}")
        if idx < 0:
            return {}
        inner = s[1:idx].strip()
        result: dict[str, Any] = {}
        for pair in _split_preserving_nesting(inner, ","):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                result[k.strip()] = _decode_toml_value(v.strip())
        return result
    try:
        return int(s) if "." not in s else float(s)
    except ValueError:
        return s


def _loads_toml_fallback(content: str) -> dict[str, Any]:
    """Parse the TOML subset found in pyproject.toml / Cargo.toml."""
    root: dict[str, Any] = {}
    current = root
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        stripped = raw.strip()
        if not stripped or stripped[0] == "#":
            continue

        # [[array.of.tables]]
        if stripped.startswith("[["):
            end = stripped.find("]]")
            if end < 0:
                continue
            path = [p.strip() for p in stripped[2:end].split(".")]
            target = root
            for key in path[:-1]:
                target = target.setdefault(key, {})
            arr = target.setdefault(path[-1], [])
            if not isinstance(arr, list):
                arr = [arr]
                target[path[-1]] = arr
            entry: dict[str, Any] = {}
            arr.append(entry)
            current = entry
            continue

        # [table]
        if stripped.startswith("[") and not stripped.startswith("[["):
            end = stripped.find("]")
            if end < 0:
                continue
            path = [p.strip() for p in stripped[1:end].split(".")]
            current = root
            for key in path:
                nxt = current.setdefault(key, {})
                if not isinstance(nxt, dict):
                    nxt = {}
                    current[key] = nxt
                current = nxt
            continue

        # key = value
        eq = stripped.find("=")
        if eq < 0:
            continue
        key = stripped[:eq].strip().strip('"')
        val_str = stripped[eq + 1:].strip()

        # Remove trailing comment outside strings
        if val_str and val_str[0] not in ('"', "'", "[", "{"):
            ci = val_str.find(" #")
            if ci >= 0:
                val_str = val_str[:ci].strip()

        # Multi-line array
        if val_str.startswith("[") and "]" not in val_str:
            while i < len(lines):
                val_str += " " + lines[i].strip()
                i += 1
                if "]" in val_str:
                    break

        current[key] = _decode_toml_value(val_str)
    return root


def _parse_toml(content: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(content)
    return _loads_toml_fallback(content)


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


_PARSERS = {
    "package.json": _parse_package_json,
    "pyproject.toml": _parse_pyproject_toml,
    "Cargo.toml": _parse_cargo_toml,
}


def _parse_manifest(path: Path) -> dict[str, Any]:
    parser = _PARSERS.get(path.name)
    if parser is None:
        _die(f"Unsupported manifest type: {path.name}", "UNSUPPORTED_MANIFEST")
    return parser(path)


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def detect(
    repo_url: str,
    manifest_paths: list[str],
    grammar_files: list[str] | None = None,
    tree_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Classify a repo into a skill shape from its manifest files.

    `grammar_files` (grammar files like Grammar/python.gram, *.y, *.g4) and
    `tree_paths` (repo-relative directory/structural signals) are optional
    tree-level signals harvested from the clone; they let whole-language repos
    that carry no parser-generator dependency — and even manifest-less ones —
    be classified. When all three inputs are empty there is nothing to
    classify and we error, exactly as before.
    """
    grammar_files = grammar_files or []
    tree_paths = tree_paths or []
    if not manifest_paths and not grammar_files and not tree_paths:
        _die("--manifests requires at least one path", "MISSING_MANIFESTS")

    parsed: list[dict[str, Any]] = []
    for mp in manifest_paths:
        p = Path(mp)
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
    # CONSUMER: a project that depends on a parser generator (a DSL built on
    # lalrpop) is also a language project. Exclude the repo's own producer name
    # from the consumer list so a self-reference isn't double-counted as "uses".
    own_names = {
        (m.get("name") or "").strip().lower() for m in parsed if m.get("name")
    }
    parser_producers = sorted(n for n in own_names if n in _ALL_PARSER_DEPS)
    parser_deps = sorted(
        d for d in all_deps
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

    # 1b. language-reference — a parser/grammar producer (own name) or a project
    # built on a parser generator (consumer dep).
    if parser_producers or parser_deps:
        # A producer (named itself a grammar tool) is a stronger signal than a
        # consumer (merely depends on one).
        base = 0.80 if parser_producers else 0.75
        n_sig = len(parser_producers) + len(parser_deps)
        confidence = _clamp(base + n_sig * 0.05, base, 0.90)
        return {"shape": "language-reference", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

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

    # 5. unknown
    return {"shape": "unknown", "signals": signals,
            "confidence": 0.0, **result_base}


def path_to_manifest_name(ecosystem: str) -> str:
    return {"npm": "package_json", "python": "pyproject_toml",
            "rust": "cargo_toml"}.get(ecosystem, ecosystem)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Classify a repo into a known skill shape from its manifest files.",
    )
    parser.add_argument("--repo-url", required=True, help="Repository URL")
    parser.add_argument(
        "--manifests", required=True,
        help="Comma-separated local file paths to manifest files (may be empty "
             "when --grammar-files or --tree-paths carry the signal)",
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

    manifest_paths = [p.strip() for p in args.manifests.split(",") if p.strip()]
    grammar_files = [p.strip() for p in args.grammar_files.split(",") if p.strip()]
    tree_paths = [p.strip() for p in args.tree_paths.split(",") if p.strip()]
    if not manifest_paths and not grammar_files and not tree_paths:
        _die("--manifests requires at least one path", "MISSING_MANIFESTS")

    result = detect(args.repo_url, manifest_paths, grammar_files, tree_paths)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    return 1 if result["shape"] == "unknown" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
