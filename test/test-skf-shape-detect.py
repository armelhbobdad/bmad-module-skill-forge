#!/usr/bin/env python3
"""Tests for skf-shape-detect.py.

Pure-function tests for each shape classification, plus subprocess tests
to verify CLI wiring (argparse, stdout JSON, exit codes).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-shape-detect.py"
)

spec = importlib.util.spec_from_file_location("skf_shape_detect", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REPO_URL = "https://github.com/example/repo"


def assert_result_shape(out: dict) -> None:
    assert set(out.keys()) >= {
        "shape", "signals", "confidence", "export_count", "package_count",
    }, f"Missing keys in output: {out}"
    assert out["shape"] in {
        "library-API", "reference-app", "language-reference",
        "stack-compose", "unknown",
    }, f"Invalid shape: {out['shape']}"
    assert isinstance(out["signals"], list)
    assert isinstance(out["confidence"], (int, float))
    assert 0.0 <= out["confidence"] <= 1.0
    assert isinstance(out["export_count"], int)
    assert isinstance(out["package_count"], int)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def write_package_json(tmp_path: Path, data: dict) -> str:
    p = tmp_path / "package.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def write_pyproject_toml(tmp_path: Path, content: str) -> str:
    p = tmp_path / "pyproject.toml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def write_cargo_toml(tmp_path: Path, content: str) -> str:
    p = tmp_path / "Cargo.toml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def write_go_mod(tmp_path: Path, content: str, subdir: str = "") -> str:
    base = tmp_path / subdir if subdir else tmp_path
    base.mkdir(parents=True, exist_ok=True)
    p = base / "go.mod"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _write_manifest(tmp_path: Path, filename: str, content: str, subdir: str = "") -> str:
    base = tmp_path / subdir if subdir else tmp_path
    base.mkdir(parents=True, exist_ok=True)
    p = base / filename
    p.write_text(content, encoding="utf-8")
    return str(p)


def write_pom_xml(tmp_path: Path, content: str, subdir: str = "") -> str:
    return _write_manifest(tmp_path, "pom.xml", content, subdir)


def write_gradle(tmp_path: Path, content: str, kts: bool = False, subdir: str = "") -> str:
    return _write_manifest(tmp_path, "build.gradle.kts" if kts else "build.gradle", content, subdir)


def write_package_swift(tmp_path: Path, content: str, subdir: str = "") -> str:
    return _write_manifest(tmp_path, "Package.swift", content, subdir)


# --------------------------------------------------------------------------
# Shape: library-API
# --------------------------------------------------------------------------


class TestLibraryAPI:
    def test_npm_library_with_main_and_exports(self, tmp_path):
        exports = {f"./{k}": f"./dist/{k}.js" for k in range(60)}
        path = write_package_json(tmp_path, {
            "name": "my-lib",
            "main": "dist/index.js",
            "module": "dist/index.mjs",
            "exports": exports,
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["confidence"] >= 0.85
        assert result["export_count"] == 60
        assert result["package_count"] == 1
        assert "has_library_structure" in result["signals"]
        assert "exports_count_gt_50" in result["signals"]
        assert "no_bin_field" in result["signals"]

    def test_npm_library_with_main_only(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "small-lib",
            "main": "index.js",
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["export_count"] == 1

    def test_python_library_without_scripts(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[project]
name = "my-python-lib"
version = "1.0.0"
dependencies = ["requests>=2.28"]
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["confidence"] >= 0.75

    def test_rust_library_with_lib_target(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-crate"
version = "0.1.0"

[lib]
name = "my_crate"

[dependencies]
serde = "1.0"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"

    def test_npm_library_moderate_exports(self, tmp_path):
        exports = {f"./{k}": f"./dist/{k}.js" for k in range(20)}
        path = write_package_json(tmp_path, {
            "name": "mid-lib",
            "main": "dist/index.js",
            "exports": exports,
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["confidence"] >= 0.75
        assert result["export_count"] == 20


# --------------------------------------------------------------------------
# Shape: reference-app
# --------------------------------------------------------------------------


class TestReferenceApp:
    def test_npm_with_bin_field(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "my-cli",
            "bin": {"my-cli": "./bin/cli.js"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"
        assert result["confidence"] >= 0.80
        assert "has_bin_field" in result["signals"]

    def test_npm_with_framework_dep(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "my-app",
            "dependencies": {"next": "14.0.0", "react": "18.0.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"
        assert any("framework_dep:" in s for s in result["signals"])

    def test_npm_with_bin_and_framework(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "full-app",
            "bin": {"app": "./bin/app.js"},
            "dependencies": {"express": "4.18.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"
        assert result["confidence"] >= 0.85

    def test_python_with_framework_dep(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[project]
name = "my-api"
version = "1.0.0"
dependencies = ["fastapi>=0.100", "uvicorn>=0.23"]
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"

    def test_rust_with_bin_target(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-tool"
version = "0.1.0"

[[bin]]
name = "my-tool"
path = "src/main.rs"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"
        assert "has_bin_field" in result["signals"]

    def test_rust_with_framework_dep(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-server"
version = "0.1.0"

[dependencies]
axum = "0.7"
tokio = { version = "1", features = ["full"] }
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"


# --------------------------------------------------------------------------
# Shape: language-reference
# --------------------------------------------------------------------------


PARSER_QUESTION = "language_or_user:parser_dep"


class TestLanguageReference:
    def test_npm_with_parser_dep(self, tmp_path):
        """A bare DSL manifest: the parser dependency is its only signal, so it
        still gives language-reference, with no question left to ask."""
        path = write_package_json(tmp_path, {
            "name": "my-grammar",
            "dependencies": {"antlr4": "4.13.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert result["confidence"] == 0.75
        assert "parser_dep:antlr4" in result["signals"]
        assert PARSER_QUESTION not in result["signals"]

    def test_python_with_parser_dep(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[project]
name = "my-parser"
version = "0.1.0"
dependencies = ["lark>=1.0", "lark-parser"]
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert {"parser_dep:lark", "parser_dep:lark-parser", PARSER_QUESTION} <= set(result["signals"])

    def test_rust_with_pest_dep(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-lang"
version = "0.1.0"

[dependencies]
pest = "2.0"
pest_derive = "2.0"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert {"parser_dep:pest", "parser_dep:pest_derive", PARSER_QUESTION} <= set(result["signals"])

    def test_a_framework_app_with_a_parser_dep_asks(self, tmp_path):
        """The parser dependency no longer outranks the framework: the app
        answers, and the question goes with it to the caller."""
        path = write_package_json(tmp_path, {
            "name": "compiler-app",
            "dependencies": {"tree-sitter": "0.20.0", "express": "4.18.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert {"parser_dep:tree-sitter", "framework_dep:express", PARSER_QUESTION} <= set(result["signals"])


# --------------------------------------------------------------------------
# Shape: language-reference — PRODUCERS (issue #427)
#
# The pre-#427 heuristic only fired on parser-generator *dependencies*, i.e.
# *consumers* of parser tooling. A language tool's OWN repo doesn't depend on
# a parser generator — it IS one (pest's Cargo.toml has no `pest` dep; it
# declares `[package] name = "pest"`). Tier 1 fix: a repo whose own package
# name is itself a known parser/grammar tool is a producer and classifies as
# language-reference. A consumer (a parser tool among the runtime deps)
# decides no shape: it raises the question TestParserConsumers pins.
# --------------------------------------------------------------------------


class TestLanguageReferenceProducers:
    def test_rust_pest_own_repo_is_producer(self, tmp_path):
        """pest-parser/pest: own name in parser-gen set, no pest dep."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "pest"
version = "2.7.0"

[lib]
name = "pest"

[dependencies]
ucd-trie = "0.1"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert any("parser_producer" in s for s in result["signals"])

    def test_npm_peggy_own_repo_is_producer(self, tmp_path):
        """peggy: a parser generator publishing itself, no parser dep."""
        path = write_package_json(tmp_path, {
            "name": "peggy",
            "main": "lib/peg.js",
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert any("parser_producer" in s for s in result["signals"])

    def test_python_lark_own_repo_is_producer(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[project]
name = "lark"
version = "1.1.0"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"

    def test_lalrpop_consumer_asks_and_its_grammar_answers(self, tmp_path):
        """A DSL built ON lalrpop: its runtime lalrpop-util asks the question,
        and the grammar file it compiles makes it language-reference."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-query-lang"
version = "0.1.0"

[lib]
name = "my_query_lang"

[build-dependencies]
lalrpop = "0.20"

[dependencies]
lalrpop-util = "0.20"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert {"parser_dep:lalrpop-util", PARSER_QUESTION} <= set(result["signals"])
        assert "parser_dep:lalrpop" not in result["signals"], "a build dependency is no consumer"
        result = mod.detect(REPO_URL, [path], ["src/grammar.lalrpop"], [])
        assert result["shape"] == "language-reference"
        assert "grammar_file:grammar.lalrpop" in result["signals"]


# --------------------------------------------------------------------------
# language-reference NEGATIVE controls (issue #427 ship gate)
#
# These must NOT classify as language-reference. They lock in the conservative
# Tier-1 decision: producer detection keys on own-name ∈ parser-gen-set ONLY,
# NOT on substring name tokens like "parser"/"lang"/"compiler" — those are
# false-positive farms (a markdown parser, a CLI arg parser, compiler-builtins
# are all ordinary libraries, not whole-language references).
# --------------------------------------------------------------------------


class TestLanguageReferenceNegativeControls:
    def test_clap_arg_parser_is_library(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "clap"
version = "4.5.0"

[lib]
name = "clap"
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] != "language-reference"

    def test_serde_is_library(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[package]
name = "serde"
version = "1.0.0"

[lib]
name = "serde"
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] != "language-reference"

    def test_markdown_lib_is_not_language_reference(self, tmp_path):
        """comrak: a CommonMark parser library — parses a format, not a lang."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "comrak"
version = "0.20.0"

[lib]
name = "comrak"
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] != "language-reference"

    def test_trap_token_parser_in_name_is_not_language_reference(self, tmp_path):
        """A '*-parser' library parses an existing format; the token is a trap."""
        path = write_package_json(tmp_path, {
            "name": "css-parser",
            "main": "index.js",
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] != "language-reference"

    def test_trap_token_compiler_substring_is_not_language_reference(self, tmp_path):
        """compiler-builtins / rustc-demangle: 'compiler'/'rustc' substring,
        but ordinary libraries. Guards against naive name-token matching."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "compiler-builtins"
version = "0.1.0"

[lib]
name = "compiler_builtins"
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] != "language-reference"


# --------------------------------------------------------------------------
# language-reference — GRAMMAR-FILE rung (Rung A, issue #427)
#
# A repo that ships a declared grammar authors a language — even when it has no
# parser-generator dependency and even when it has NO supported manifest at all
# (CPython, Ruby). Two guard gates suppress delegating consumers and markup/DSL
# parsers that merely carry a grammar-ish file.
# --------------------------------------------------------------------------


class TestLanguageReferenceGrammarRung:
    def test_cpython_grammar_file_no_manifest(self):
        """python/cpython: PEG grammar at Grammar/python.gram, no manifest."""
        result = mod.detect(REPO_URL, [], ["Grammar/python.gram"], [])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert "grammar_file:python.gram" in result["signals"]
        assert result["confidence"] >= 0.85

    def test_ruby_root_grammar_outranks_jit_cargo(self, tmp_path):
        """ruby/ruby: root parse.y outranks the Rust JIT Cargo.toml library."""
        jit = write_cargo_toml(tmp_path, """
[package]
name = "yjit"
version = "0.1.0"

[lib]
name = "yjit"
crate-type = ["staticlib"]
""")
        result = mod.detect(REPO_URL, [jit], ["parse.y"], [])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert "grammar_file:parse.y" in result["signals"]

    def test_g4_grammar_fires(self):
        result = mod.detect(REPO_URL, [], ["src/MyLang.g4"], [])
        assert result["shape"] == "language-reference"

    def test_grammar_substring_does_not_fire(self):
        """A file merely named like a grammar (no grammar extension) is inert."""
        result = mod.detect(REPO_URL, [], ["docs/grammar_overview.md"], [])
        assert result["shape"] == "unknown"

    def test_delegating_consumer_with_grammar_is_suppressed(self, tmp_path):
        """A formatter that depends on a real parser must not fire even with a
        stray grammar file in its tree (gate G)."""
        pkg = write_package_json(tmp_path, {
            "name": "prettier",
            "bin": {"prettier": "./bin.js"},
            "dependencies": {"@babel/parser": "7.0.0"},
        })
        result = mod.detect(REPO_URL, [pkg], ["test/fixtures/x.g4"], [])
        assert result["shape"] != "language-reference"
        assert "delegating_consumer" in result["signals"]

    def test_markup_identity_with_grammar_is_suppressed(self, tmp_path):
        """A repo whose identity is a markup/DSL parser is not a whole-language
        reference even with a grammar file (gate L)."""
        pkg = write_package_json(tmp_path, {
            "name": "graphql",
            "main": "index.js",
        })
        result = mod.detect(REPO_URL, [pkg], ["src/schema.g4"], [])
        assert result["shape"] != "language-reference"


# --------------------------------------------------------------------------
# language-reference — TREE-TRIAD rung (Rung B, issue #427)
#
# Hand-written compilers (rustc, TypeScript, Go) declare no parser-generator
# dependency and ship no grammar file. They are caught by a dedicated compiler/
# directory holding a lexer+parser+AST triad plus a codegen/VM/type-checker
# member. The six false-positive controls (webpack, postcss, prettier,
# graphql-js, dart-sass, marked) each have a near-miss shape and must stay out.
# --------------------------------------------------------------------------

# Faithful reconstructions of each repo's real compiler tree.
RUST_TREE = [
    "compiler/", "compiler/rustc_lexer/", "compiler/rustc_parse/",
    "compiler/rustc_ast/", "compiler/rustc_codegen_llvm/",
]
TS_TREE = [
    "src/compiler/", "src/compiler/scanner.ts", "src/compiler/parser.ts",
    "src/compiler/binder.ts", "src/compiler/checker.ts",
]
GO_TREE = [
    "cmd/compile/", "cmd/compile/internal/syntax/",
    "cmd/compile/internal/syntax/scanner.go",
    "cmd/compile/internal/syntax/parser.go",
    "go/ast/", "go/ast/ast.go", "go/types/", "go/types/check.go",
]


class TestLanguageReferenceTreeTriadRung:
    def test_rust_compiler_triad(self):
        result = mod.detect(REPO_URL, [], [], RUST_TREE)
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert any(s.startswith("tree_triad:") for s in result["signals"])

    def test_typescript_triad_outranks_bin(self, tmp_path):
        """TypeScript ships `tsc` (a bin) — the triad must outrank reference-app."""
        pkg = write_package_json(tmp_path, {
            "name": "typescript",
            "bin": {"tsc": "./bin/tsc.js", "tsserver": "./bin/tsserver.js"},
        })
        result = mod.detect(REPO_URL, [pkg], [], TS_TREE)
        assert result["shape"] == "language-reference"

    def test_go_toolchain_triad(self):
        result = mod.detect(REPO_URL, [], [], GO_TREE)
        assert result["shape"] == "language-reference"

    # --- negative controls: each near-miss must stay out ---

    def test_webpack_parser_file_not_dir(self, tmp_path):
        """lib/Parser.js is a FILE, not a Parser/ dir; plus acorn dep (gate G)."""
        pkg = write_package_json(tmp_path, {
            "name": "webpack",
            "bin": {"webpack": "./bin.js"},
            "dependencies": {"acorn": "8.0.0"},
        })
        result = mod.detect(REPO_URL, [pkg], [], ["lib/", "lib/Parser.js"])
        assert result["shape"] != "language-reference"

    def test_postcss_no_compiler_dir(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "postcss", "main": "lib/postcss.js"})
        tree = ["lib/", "lib/tokenize.js", "lib/parser.js", "lib/node.js"]
        result = mod.detect(REPO_URL, [pkg], [], tree)
        assert result["shape"] != "language-reference"

    def test_graphql_js_src_language_not_compiler(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "graphql", "main": "index.js"})
        tree = ["src/language/", "src/language/lexer.ts",
                "src/language/parser.ts", "src/language/ast.ts"]
        result = mod.detect(REPO_URL, [pkg], [], tree)
        assert result["shape"] != "language-reference"

    def test_dart_sass_compiler_is_a_file(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "sass", "main": "sass.dart.js"})
        tree = ["lib/src/", "lib/src/parse/", "lib/src/compiler.dart",
                "lib/src/syntax.dart"]
        result = mod.detect(REPO_URL, [pkg], [], tree)
        assert result["shape"] != "language-reference"

    def test_marked_bare_src_dir(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "marked", "main": "lib/marked.js"})
        tree = ["src/", "src/Lexer.ts", "src/Parser.ts", "src/Tokenizer.ts"]
        result = mod.detect(REPO_URL, [pkg], [], tree)
        assert result["shape"] != "language-reference"

    def test_w_gate_is_load_bearing(self, tmp_path):
        """A repo with a real compiler/ dir AND a full lexer+parser+AST triad but
        NO codegen/VM/type-checker (a markdown-shaped lib) must stay out. Proves
        gate W, not the compiler-dir alone, is the discriminator."""
        pkg = write_package_json(tmp_path, {"name": "quaxmark", "main": "index.js"})
        tree = ["src/compiler/", "src/compiler/lexer.ts",
                "src/compiler/parser.ts", "src/compiler/ast.ts"]
        result = mod.detect(REPO_URL, [pkg], [], tree)
        assert result["shape"] != "language-reference"


# --------------------------------------------------------------------------
# Phase B plumbing (issue #427): optional --grammar-files / --tree-paths args
# and the relaxed MISSING_MANIFESTS guard. These inputs do not yet change
# classification (the grammar/tree rungs land in later commits) — this commit
# only proves the interface is wired and behaviour-neutral on the existing
# manifest path.
# --------------------------------------------------------------------------


class TestPhaseBPlumbing:
    def test_existing_two_arg_call_unchanged(self, tmp_path):
        """The 2-arg detect() signature still works (regression)."""
        path = write_package_json(tmp_path, {"name": "lib", "main": "index.js"})
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"

    def test_all_inputs_empty_still_errors(self):
        """The load-bearing pin: every input empty → exit 2, unchanged."""
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [], [], [])
        assert exc_info.value.code == 2

    def test_grammar_only_no_longer_errors(self):
        """Empty manifests but a grammar file present → no longer exit 2.

        With the grammar rung in place a manifest-less grammar repo classifies
        as language-reference rather than hard-erroring.
        """
        result = mod.detect(REPO_URL, [], ["Grammar/python.gram"], [])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"

    def test_tree_only_inert_until_triad_rung(self):
        """A lone directory signal does not yet classify (the compiler-triad
        rung lands in a later commit); the point here is it no longer exit-2s."""
        result = mod.detect(REPO_URL, [], [], ["some/dir/"])
        assert_result_shape(result)
        assert result["shape"] == "unknown"

    def test_cli_all_empty_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL,
             "--manifests", "", "--grammar-files", "", "--tree-paths", ""],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2

    def test_cli_grammar_only_not_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL,
             "--manifests", "", "--grammar-files", "Grammar/python.gram"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode != 2
        out = json.loads(proc.stdout)
        assert_result_shape(out)


# --------------------------------------------------------------------------
# Ecosystem: Go (go.mod) — issue #427 ecosystem expansion
#
# The scanner already recognises go.mod; shape-detect now parses it too, so a
# Go repo reaches classification instead of hard-halting. Most Go libraries
# resolve to library-API; the Go toolchain itself is caught by the tree-triad
# rung (golang/go).
# --------------------------------------------------------------------------


class TestGoMod:
    def test_go_library_is_library_api(self, tmp_path):
        path = write_go_mod(tmp_path, """
module github.com/spf13/cobra

go 1.21

require (
\tgithub.com/inconshreveable/mousetrap v1.1.0
\tgithub.com/spf13/pflag v1.0.5
)
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert "has_go_mod" in result["signals"]

    def test_go_mod_does_not_hard_halt(self, tmp_path):
        """A go.mod handed directly parses cleanly (no UNSUPPORTED_MANIFEST)."""
        path = write_go_mod(tmp_path, "module example.com/x\n\ngo 1.21\n")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] in {"library-API", "unknown"}

    def test_go_single_line_require(self, tmp_path):
        path = write_go_mod(tmp_path, """
module example.com/tool

go 1.21

require github.com/spf13/pflag v1.0.5
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"

    def test_go_cmd_member_has_bin(self, tmp_path):
        """A go.mod under cmd/ marks a command (binary) member."""
        path = write_go_mod(tmp_path, "module acme.dev/app/cmd/tool\n\ngo 1.21\n",
                            subdir="cmd/tool")
        result = mod.detect(REPO_URL, [path])
        assert "has_bin_field" in result["signals"]
        assert result["shape"] == "reference-app"

    def test_cli_go_mod_exit_0(self, tmp_path):
        path = write_go_mod(tmp_path, "module example.com/x\n\ngo 1.21\n")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", path],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["shape"] == "library-API"


# --------------------------------------------------------------------------
# Ecosystem reach: Maven / Gradle / Swift (issue #433)
# --------------------------------------------------------------------------


class TestMaven:
    _LIB_POM = """<?xml version="1.0"?>
<project>
  <groupId>com.google.guava</groupId>
  <artifactId>guava</artifactId>
  <version>33.0.0</version>
  <packaging>jar</packaging>
  <dependencies>
    <dependency>
      <groupId>com.google.code.findbugs</groupId>
      <artifactId>jsr305</artifactId>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
"""

    def test_maven_library_is_library_api(self, tmp_path):
        path = write_pom_xml(tmp_path, self._LIB_POM)
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert "has_pom_xml" in result["signals"]

    def test_maven_does_not_hard_halt(self, tmp_path):
        path = write_pom_xml(
            tmp_path,
            "<project><artifactId>x</artifactId></project>",
        )
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] in {"library-API", "unknown"}

    def test_maven_spring_boot_app_is_reference_app(self, tmp_path):
        pom = """<?xml version="1.0"?>
<project>
  <artifactId>my-service</artifactId>
  <version>1.0.0</version>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""
        path = write_pom_xml(tmp_path, pom)
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert "has_bin_field" in result["signals"]

    def test_maven_artifact_id_not_taken_from_parent(self, tmp_path):
        pom = """<?xml version="1.0"?>
<project>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.0.0</version>
  </parent>
  <artifactId>my-lib</artifactId>
</project>
"""
        path = write_pom_xml(tmp_path, pom)
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"


class TestGradle:
    def test_gradle_groovy_library_is_library_api(self, tmp_path):
        path = write_gradle(tmp_path, """
plugins {
    id 'java-library'
}
dependencies {
    api 'com.google.guava:guava:33.0.0'
    implementation 'org.slf4j:slf4j-api:2.0.9'
}
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert "has_build_gradle" in result["signals"]

    def test_gradle_kts_library_is_library_api(self, tmp_path):
        path = write_gradle(tmp_path, """
plugins {
    `java-library`
}
dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.0")
}
""", kts=True)
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"
        assert "has_build_gradle" in result["signals"]

    def test_gradle_application_plugin_is_reference_app(self, tmp_path):
        path = write_gradle(tmp_path, """
plugins {
    id 'application'
}
application {
    mainClass = 'com.example.Main'
}
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert "has_bin_field" in result["signals"]


class TestSwift:
    def test_swift_library_is_library_api(self, tmp_path):
        path = write_package_swift(tmp_path, """
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Alamofire",
    products: [
        .library(name: "Alamofire", targets: ["Alamofire"]),
    ],
    targets: [
        .target(name: "Alamofire"),
    ]
)
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert "has_package_swift" in result["signals"]

    def test_swift_does_not_hard_halt(self, tmp_path):
        path = write_package_swift(
            tmp_path, 'let package = Package(name: "x")\n'
        )
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] in {"library-API", "unknown"}

    def test_swift_executable_is_reference_app(self, tmp_path):
        path = write_package_swift(tmp_path, """
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "swift-format",
    products: [
        .executable(name: "swift-format", targets: ["swift-format"]),
    ],
    targets: [
        .executableTarget(name: "swift-format"),
    ]
)
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert "has_bin_field" in result["signals"]

    def test_cli_package_swift_exit_0(self, tmp_path):
        path = write_package_swift(
            tmp_path,
            'let package = Package(name: "Lib", products: [.library(name: "Lib", targets: [])])\n',
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", path],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["shape"] == "library-API"


# --------------------------------------------------------------------------
# Shape: stack-compose
# --------------------------------------------------------------------------


class TestStackCompose:
    def test_npm_plus_python(self, tmp_path):
        pkg = write_package_json(tmp_path, {
            "name": "frontend",
            "main": "index.js",
        })
        py_dir = tmp_path / "backend"
        py_dir.mkdir()
        py = write_pyproject_toml(py_dir, """
[project]
name = "backend"
version = "1.0.0"
dependencies = []
""")
        result = mod.detect(REPO_URL, [pkg, py])
        assert_result_shape(result)
        assert result["shape"] == "stack-compose"
        assert result["confidence"] >= 0.80
        assert "multiple_ecosystems" in result["signals"]
        assert result["package_count"] == 2

    def test_npm_plus_rust(self, tmp_path):
        pkg = write_package_json(tmp_path, {
            "name": "wasm-app",
            "main": "index.js",
        })
        rs_dir = tmp_path / "native"
        rs_dir.mkdir()
        cargo = write_cargo_toml(rs_dir, """
[package]
name = "native"
version = "0.1.0"
""")
        result = mod.detect(REPO_URL, [pkg, cargo])
        assert result["shape"] == "stack-compose"
        assert "ecosystem:npm" in result["signals"]
        assert "ecosystem:rust" in result["signals"]

    def test_three_ecosystems(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "fe"})
        py_dir = tmp_path / "api"
        py_dir.mkdir()
        py = write_pyproject_toml(py_dir, '[project]\nname = "api"\n')
        rs_dir = tmp_path / "core"
        rs_dir.mkdir()
        rs = write_cargo_toml(rs_dir, '[package]\nname = "core"\n')
        result = mod.detect(REPO_URL, [pkg, py, rs])
        assert result["shape"] == "stack-compose"
        assert result["confidence"] >= 0.85

    def test_stack_compose_beats_reference_app(self, tmp_path):
        """Multi-ecosystem fires before reference-app in the ladder."""
        pkg = write_package_json(tmp_path, {
            "name": "app",
            "bin": {"app": "bin/app.js"},
        })
        rs_dir = tmp_path / "core"
        rs_dir.mkdir()
        rs = write_cargo_toml(rs_dir, '[package]\nname = "core"\n')
        result = mod.detect(REPO_URL, [pkg, rs])
        assert result["shape"] == "stack-compose"


# --------------------------------------------------------------------------
# Shape: unknown
# --------------------------------------------------------------------------


class TestUnknown:
    def test_empty_package_json(self, tmp_path):
        path = write_package_json(tmp_path, {})
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "unknown"
        assert result["confidence"] <= 0.3
        assert result["export_count"] == 0

    def test_minimal_package_json_no_exports(self, tmp_path):
        path = write_package_json(tmp_path, {"name": "mystery", "version": "1.0.0"})
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "unknown"

    def test_package_json_with_only_devdeps(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "config-only",
            "devDependencies": {"typescript": "5.0.0", "prettier": "3.0.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "unknown"


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


class TestErrors:
    def test_missing_manifest_file(self, tmp_path):
        missing = str(tmp_path / "nonexistent" / "package.json")
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [missing])
        assert exc_info.value.code == 2

    def test_empty_manifest_list(self):
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [])
        assert exc_info.value.code == 2

    def test_unsupported_manifest_type(self, tmp_path):
        p = tmp_path / "Makefile"
        p.write_text("all: build", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [str(p)])
        assert exc_info.value.code == 2

    def test_invalid_json_manifest(self, tmp_path):
        p = tmp_path / "package.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [str(p)])
        assert exc_info.value.code == 2

    def test_invalid_toml_manifest(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text("[[invalid\nbroken = ", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [str(p)])
        assert exc_info.value.code == 2

    def test_non_object_json_root(self, tmp_path):
        p = tmp_path / "package.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod.detect(REPO_URL, [str(p)])
        assert exc_info.value.code == 2


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_exports_field(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "empty-exports",
            "exports": {},
            "main": "index.js",
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["export_count"] == 0

    def test_manifest_with_no_name(self, tmp_path):
        path = write_package_json(tmp_path, {"main": "index.js"})
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"

    def test_string_exports_field(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "str-exports",
            "exports": "./index.js",
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "library-API"
        assert result["export_count"] == 1

    def test_cargo_workspace_without_package(self, tmp_path):
        path = write_cargo_toml(tmp_path, """
[workspace]
members = ["crate-a", "crate-b"]
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)

    def test_pyproject_with_poetry_deps(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[tool.poetry]
name = "my-poetry-proj"
version = "1.0.0"

[tool.poetry.dependencies]
python = "^3.9"
requests = "^2.28"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)

    def test_multiple_manifests_same_ecosystem(self, tmp_path):
        """Two npm manifests = same ecosystem = not stack-compose."""
        p1 = tmp_path / "a"
        p1.mkdir()
        f1 = write_package_json(p1, {"name": "pkg-a", "main": "index.js"})
        p2 = tmp_path / "b"
        p2.mkdir()
        f2 = write_package_json(p2, {"name": "pkg-b", "main": "index.js"})
        result = mod.detect(REPO_URL, [f1, f2])
        assert result["shape"] != "stack-compose"
        assert result["package_count"] == 2

    def test_rust_with_both_lib_and_bin(self, tmp_path):
        """Rust project with [lib] + [[bin]] → reference-app (bin wins)."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "dual"
version = "0.1.0"

[lib]
name = "dual"

[[bin]]
name = "dual-cli"
path = "src/main.rs"
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "reference-app"

    def test_confidence_is_float(self, tmp_path):
        path = write_package_json(tmp_path, {"name": "lib", "main": "index.js"})
        result = mod.detect(REPO_URL, [path])
        assert isinstance(result["confidence"], float)


# --------------------------------------------------------------------------
# TOML manifests are read with tomllib (issue #562): the hand-written
# fallback parser, which the Python 3.9 and 3.10 floors reached, is gone
# --------------------------------------------------------------------------


class TestTomllib:
    def test_a_pep508_extra_and_a_bracketed_comment_keep_every_dependency(self, tmp_path):
        """The fallback ended a multi-line array at the first `]`, the one of
        `requests[socks]` or of a trailing comment, and lost lark and flask."""
        path = write_pyproject_toml(tmp_path, """
[project]
name = "demo"
version = "0.1.0"
dependencies = [
  "requests[socks]>=2",  # pinned [2.28]
  "lark>=1",
  "flask",
]
""")
        result = mod.detect(REPO_URL, [path])
        assert "parser_dep:lark" in result["signals"]
        assert "framework_dep:flask" in result["signals"]
        assert result["shape"] == "reference-app"
        assert {"app_or_library:framework_dep", PARSER_QUESTION} <= set(result["signals"])

    def test_a_dotted_cargo_key_names_the_dependency(self, tmp_path):
        """`pest.workspace = true` is the dependency pest, which the fallback
        read as one flat key `pest.workspace`."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-lang"
version = "0.1.0"

[dependencies]
pest.workspace = true
""")
        result = mod.detect(REPO_URL, [path])
        assert "parser_dep:pest" in result["signals"]

    def test_no_fallback_parser_is_left(self):
        for name in ("_split_preserving_nesting", "_decode_toml_value", "_loads_toml_fallback"):
            assert not hasattr(mod, name), name
        assert mod.tomllib is sys.modules["tomllib"]

    def test_without_tomllib_the_script_does_not_start(self, tmp_path):
        """Below Python 3.11 (tomllib hidden here) the script stops at its
        import instead of classifying from a misread manifest."""
        path = write_pyproject_toml(tmp_path, '[project]\nname = "demo"\n')
        runner = (
            "import runpy, sys\n"
            "sys.modules['tomllib'] = None\n"
            "script = sys.argv[1]\n"
            "sys.argv = [script, '--repo-url', sys.argv[2], '--manifests', sys.argv[3]]\n"
            "runpy.run_path(script, run_name='__main__')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", runner, str(SCRIPT_PATH), REPO_URL, path],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        assert proc.returncode != 0
        assert "tomllib" in proc.stderr
        assert proc.stdout == ""


# --------------------------------------------------------------------------
# CLI wiring (subprocess)
# --------------------------------------------------------------------------


class TestCLI:
    def test_cli_library_exit_0(self, tmp_path):
        path = write_package_json(tmp_path, {"name": "lib", "main": "index.js"})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", path],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert_result_shape(out)
        assert out["shape"] == "library-API"

    def test_cli_unknown_exit_1(self, tmp_path):
        path = write_package_json(tmp_path, {})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", path],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["shape"] == "unknown"

    def test_cli_error_exit_2(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", missing],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2
        err = json.loads(proc.stderr)
        assert "error" in err
        assert "code" in err

    def test_cli_comma_separated_manifests(self, tmp_path):
        pkg = write_package_json(tmp_path, {"name": "fe", "main": "index.js"})
        py_dir = tmp_path / "api"
        py_dir.mkdir()
        py = write_pyproject_toml(py_dir, '[project]\nname = "api"\n')
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--repo-url", REPO_URL, "--manifests", f"{pkg},{py}"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["shape"] == "stack-compose"

    def test_cli_missing_repo_url(self, tmp_path):
        path = write_package_json(tmp_path, {"name": "lib"})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--manifests", path],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2

    def test_cli_missing_manifests(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 2


# --------------------------------------------------------------------------
# Monorepo: app-shape signals must not leak from non-product members
# (examples / devtools / dev-deps / peer-deps / coordinator root).
# --------------------------------------------------------------------------


def _write(tmp_path: Path, rel: str, data: dict) -> str:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


class TestMonorepoAppSignals:
    def test_library_monorepo_with_example_app_is_library(self, tmp_path):
        # Core lib packages + an examples/ app that depends on a framework.
        core_a = _write(tmp_path, "packages/core/package.json",
                        {"name": "@scope/core", "exports": {".": "./i.js"}})
        core_b = _write(tmp_path, "packages/utils/package.json",
                        {"name": "@scope/utils", "main": "u.js"})
        example = _write(tmp_path, "examples/demo/package.json",
                         {"name": "demo", "dependencies": {"next": "14"}})
        result = mod.detect(REPO_URL, [core_a, core_b, example])
        assert result["shape"] == "library-API"
        assert "framework_dep_noncore:next" in result["signals"]

    def test_devtools_member_with_framework_is_library(self, tmp_path):
        core = _write(tmp_path, "packages/lib/package.json",
                      {"name": "thing", "exports": {".": "./i.js"}})
        devtools = _write(tmp_path, "packages/thing-devtools/package.json",
                          {"name": "thing-devtools",
                           "dependencies": {"electron": "30"}})
        result = mod.detect(REPO_URL, [core, devtools])
        assert result["shape"] == "library-API"

    def test_lone_bin_in_library_monorepo_is_library(self, tmp_path):
        # A tooling package with a bin among libraries must not flip the repo.
        core = _write(tmp_path, "packages/lib/package.json",
                      {"name": "lib", "main": "i.js", "exports": {".": "./i.js"}})
        cli = _write(tmp_path, "packages/lib-healthcheck/package.json",
                     {"name": "lib-healthcheck", "bin": {"hc": "./hc.js"},
                      "main": "hc.js"})
        result = mod.detect(REPO_URL, [core, cli])
        assert result["shape"] == "library-API"

    def test_dev_dependency_framework_is_not_app(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "lib", "exports": {".": "./i.js"},
            "devDependencies": {"express": "4"},
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"
        assert "framework_dep_dev:express" in result["signals"]

    def test_peer_dependency_framework_is_not_app(self, tmp_path):
        # An adapter library peer-depends on the framework it integrates with.
        path = write_package_json(tmp_path, {
            "name": "lib-next-adapter", "exports": {".": "./i.js"},
            "peerDependencies": {"next": "14"},
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"

    def test_coordinator_root_framework_excluded(self, tmp_path):
        # Private root coordinator (no library structure) carries express for
        # scripts; the members are libraries.
        root = _write(tmp_path, "package.json",
                      {"name": "root", "private": True,
                       "dependencies": {"express": "4"}})
        member = _write(tmp_path, "packages/lib/package.json",
                        {"name": "lib", "exports": {".": "./i.js"}})
        result = mod.detect(REPO_URL, [root, member])
        assert result["shape"] == "library-API"
        assert "monorepo_root_coordinator_excluded" in result["signals"]

    def test_root_that_is_the_library_stays_in(self, tmp_path):
        # Root IS the published library (has exports) + benchmark members; the
        # root must not be excluded, and benchmark frameworks must not leak.
        root = _write(tmp_path, "package.json",
                      {"name": "weblib", "exports": {".": "./i.js"}})
        bench = _write(tmp_path, "benchmarks/x/package.json",
                       {"name": "bench-x", "dependencies": {"express": "4"}})
        result = mod.detect(REPO_URL, [root, bench])
        assert result["shape"] == "library-API"

    def test_genuine_app_still_reference_app(self, tmp_path):
        # A single package that depends on a framework at runtime is an app.
        path = write_package_json(tmp_path, {
            "name": "my-app", "dependencies": {"next": "14"},
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        # No main or exports: nothing says it is a library, so no question is left.
        assert "app_or_library:framework_dep" not in result["signals"]

    def test_genuine_monorepo_app_member_still_reference_app(self, tmp_path):
        # A core (non-example) member that runtime-depends on a framework.
        root = _write(tmp_path, "package.json",
                      {"name": "root", "private": True})
        app = _write(tmp_path, "apps/web/package.json",
                     {"name": "web", "dependencies": {"next": "14"}})
        result = mod.detect(REPO_URL, [root, app])
        assert result["shape"] == "reference-app"


# --------------------------------------------------------------------------
# --tree-file (issue #592): the script reads the whole tree itself, so no
# grep pre-filter decides which paths its gates see
# --------------------------------------------------------------------------

# A tree-sitter grammar repository: its grammar sits at the root.
TREE_SITTER_FILES = ["grammar.js", "package.json", "src/parser.c", "src/tree_sitter/parser.h",
                     "bindings/node/index.js", "queries/highlights.scm"]
# A CPython-shaped tree whose only corroborating member (gate W) is the VM
# file Python/ceval.c.
CPYTHON_FILES = ["Parser/lexer/lexer.c", "Parser/parser.c", "Parser/asdl.py", "Python/ast.c",
                 "Python/ceval.c", "Include/Python.h", "README.rst"]
# A Go-toolchain-shaped tree whose only corroborating member is the type
# checker file go/types/check.go.
GO_CHECK_FILES = ["internal/syntax/scanner.go", "internal/syntax/parser.go", "go/ast/ast.go",
                  "go/types/check.go", "README.md"]
# TypeScript's Go port: internal/compiler/ beside internal/parser/,
# internal/scanner/, internal/ast/ and internal/checker/.
TSGO_FILES = ["internal/compiler/program.go", "internal/parser/parser.go", "internal/scanner/scanner.go",
              "internal/ast/ast.go", "internal/checker/checker.go", "go.mod"]
# A compiler folder with a lexer+parser+AST triad and no corroborating member.
NO_W_MEMBER = ["src/compiler/lexer.ts", "src/compiler/parser.ts", "src/compiler/ast.ts", "src/index.ts"]
# A sympy-shaped tree: a docs tree, many modules (codegen/ among them, a
# corroborating member for gate W), and the grammars of the input formats its
# parsing/ folder reads, two of them within _GRAMMAR_MAX_DEPTH.
SYMPY_FILES = ["README.md", "doc/src/index.rst", "doc/src/modules/parsing.rst", "sympy/__init__.py",
               "sympy/core/basic.py", "sympy/core/expr.py", "sympy/functions/elementary/trigonometric.py",
               "sympy/matrices/dense.py", "sympy/solvers/solvers.py", "sympy/printing/latex.py",
               "sympy/codegen/ast.py", "sympy/parsing/__init__.py", "sympy/parsing/ast_parser.py",
               "sympy/parsing/sympy_parser.py", "sympy/parsing/latex/LaTeX.g4",
               "sympy/parsing/latex/_antlr/latexlexer.py", "sympy/parsing/latex/_antlr/latexparser.py",
               "sympy/parsing/latex/lark/grammar/latex.lark", "sympy/parsing/autolev/Autolev.g4",
               "sympy/parsing/autolev/_antlr/autolevparser.py", "sympy/parsing/smtlib/lark/grammar/smtlib.lark"]


def _tree_file(tmp_path: Path, paths, name: str = "tree.txt") -> str:
    """A listing of `paths`, one per line, as git ls-tree prints them."""
    path = tmp_path / name
    path.write_bytes("".join(f"{p}\n" for p in paths).encode("utf-8"))
    return str(path)


def run_tree(tmp_path: Path, paths, *extra: str, manifests: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", manifests,
         "--tree-file", _tree_file(tmp_path, paths), *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


class TestTreeFile:
    @pytest.mark.parametrize(
        "files,signal",
        [
            pytest.param(TREE_SITTER_FILES, "grammar_file:grammar.js", id="root-grammar-js"),
            pytest.param(CPYTHON_FILES, "tree_triad:Parser:lexer,parser,ast", id="python-ceval"),
            # go/ast/ sits outside internal/, so the triad near internal/syntax/ is its lexer and parser
            pytest.param(GO_CHECK_FILES, "tree_triad:internal/syntax:lexer,parser", id="go-check"),
            pytest.param(TSGO_FILES, "tree_triad:internal/compiler:lexer,parser,ast", id="go-port-of-typescript"),
        ],
    )
    def test_the_script_classifies_the_tree_it_reads(self, tmp_path, files, signal):
        proc = run_tree(tmp_path, files)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert_result_shape(out)
        assert out["shape"] == "language-reference"
        assert signal in out["signals"]

    @pytest.mark.parametrize(
        "files,member",
        [
            pytest.param(CPYTHON_FILES, "Python/ceval.c", id="ceval"),
            pytest.param(GO_CHECK_FILES, "go/types/check.go", id="check"),
        ],
    )
    def test_the_corroborating_member_is_load_bearing(self, tmp_path, files, member):
        """Gate W, not a filter, decides: without its one corroborating file
        the same tree stays out."""
        proc = run_tree(tmp_path, [f for f in files if f != member])
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["shape"] == "unknown"

    def test_tree_signals_keep_every_folder_and_file(self):
        grammar, tree = mod.tree_signals(["./grammar.js", "a/b/c/d/e/deep.y", "x/parse.y", "x/y/", "", "a/b/c/d/e/f.go"])
        assert grammar == ["grammar.js", "x/parse.y"]
        # folders first (x/y/ is one), then files; a deep grammar is still a tree path
        assert tree == ["a/", "a/b/", "a/b/c/", "a/b/c/d/", "a/b/c/d/e/", "x/", "x/y/",
                        "a/b/c/d/e/deep.y", "a/b/c/d/e/f.go", "grammar.js", "x/parse.y"]

    def test_tree_signals_leave_out_hidden_and_non_core_paths(self):
        """A CI workflow, a script, a test fixture or a doc is not the
        repository's own code: neither list holds it, in any case."""
        grammar, tree = mod.tree_signals([
            ".github/workflows/check.yml", "scripts/check.sh", "test/fixtures/a/b/c/vm.js", "Tools/peg/meta.gram",
            "docs/grammar.ebnf", "Lib/test/test_eval.py", "examples/calc/parser.y", "src/.cache/vm.js",
            "src/utils/check.ts", "Grammar/python.gram",
        ])
        assert grammar == ["Grammar/python.gram"]
        assert tree == ["Grammar/", "src/", "src/utils/", "Grammar/python.gram", "src/utils/check.ts"]

    def test_a_deep_grammar_is_a_fixture(self, tmp_path):
        """A grammar deeper than _GRAMMAR_MAX_DEPTH segments is a vendored or
        test fixture, not the repository's own."""
        proc = run_tree(tmp_path, ["README.md", "tests/fixtures/grammars/c/parse.y"])
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["shape"] == "unknown"

    def test_a_library_that_reads_formats_stays_a_library(self, tmp_path):
        """sympy: a library with a docs tree and many modules, whose
        sympy/parsing/ holds the grammars of the formats it reads (LaTeX,
        Autolev). They are no language of its own, so it is a library."""
        manifest = write_pyproject_toml(tmp_path, '[project]\nname = "sympy"\ndependencies = ["mpmath>=1.1.0"]\n')
        proc = run_tree(tmp_path, ["pyproject.toml", *SYMPY_FILES], manifests=manifest)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["shape"] == "library-API"
        assert not any(sig.startswith(("grammar_file:", "tree_triad:")) for sig in out["signals"])
        # without the manifest the tree carries no language signal at all
        assert json.loads(run_tree(tmp_path, SYMPY_FILES).stdout)["shape"] == "unknown"

    @pytest.mark.parametrize(
        "path,kept",
        [
            pytest.param("sympy/parsing/latex/LaTeX.g4", False, id="below-a-package-parsing-folder"),
            pytest.param("lib/parsers/sql.y", False, id="below-a-parsers-folder"),
            pytest.param("parsing/parser.y", True, id="a-top-parsing-folder"),
            pytest.param("vyper/ast/grammar.lark", True, id="in-a-package"),
            pytest.param("src/backend/parser/gram.y", True, id="a-parser-folder"),
        ],
    )
    def test_a_grammar_below_a_parsing_folder_is_a_format_reader(self, path, kept):
        grammar, tree = mod.tree_signals([path])
        assert grammar == ([path] if kept else [])
        assert path in tree

    @pytest.mark.parametrize(
        "files,pkg",
        [
            pytest.param(["src/Lexer.ts", "src/Parser.ts", "src/Tokenizer.ts", "src/Renderer.ts", "test/specs/x.js"],
                         {"name": "marked", "main": "lib/marked.js"}, id="marked"),
            pytest.param(["lib/Parser.js", "lib/Compiler.js", "lib/javascript/JavascriptParser.js",
                          "test/cases/parsing/ast/index.js"],
                         {"name": "webpack", "bin": {"webpack": "./bin.js"}, "dependencies": {"acorn": "8.0.0"}},
                         id="webpack"),
            pytest.param(NO_W_MEMBER, {"name": "quaxmark", "main": "index.js"}, id="no-w-member"),
            # one incidental file outside the code is no corroborating member
            pytest.param([*NO_W_MEMBER, ".github/workflows/check.yml"], {"name": "quaxmark", "main": "index.js"},
                         id="ci-workflow-check"),
            pytest.param([*NO_W_MEMBER, "scripts/check.sh"], {"name": "quaxmark", "main": "index.js"},
                         id="script-check"),
            pytest.param([*NO_W_MEMBER, "test/fixtures/a/b/c/vm.js"], {"name": "quaxmark", "main": "index.js"},
                         id="deep-test-fixture-vm"),
            # glimmer-vm: a compiler folder of its integration tests, an ast.ts six levels down
            pytest.param(["packages/@glimmer-workspace/integration-tests/test/compiler/compile-options-test.ts",
                          "packages/@glimmer/syntax/lib/parser.ts", "packages/@glimmer/syntax/lib/v1/ast.ts",
                          "packages/@glimmer/vm/index.ts"],
                         {"name": "glimmer-engine", "private": True}, id="glimmer-vm"),
        ],
    )
    def test_negative_controls_stay_out_with_the_whole_tree(self, tmp_path, files, pkg):
        manifest = write_package_json(tmp_path, pkg)
        proc = run_tree(tmp_path, ["package.json", *files], manifests=manifest)
        assert json.loads(proc.stdout)["shape"] != "language-reference"

    def test_a_core_corroborating_member_still_counts(self, tmp_path):
        """The filter leaves out only non-core paths: a core src/utils/check.ts
        completes the triad, as a core vm or eval file does."""
        manifest = write_package_json(tmp_path, {"name": "quaxmark", "main": "index.js"})
        proc = run_tree(tmp_path, ["package.json", *NO_W_MEMBER, "src/utils/check.ts"], manifests=manifest)
        assert json.loads(proc.stdout)["shape"] == "language-reference"

    def test_a_triad_far_from_the_compiler_folder_is_no_compiler(self, tmp_path):
        """PyTorch: torch/compiler/ is the torch.compile API package, its
        lexer and parser are TorchScript's, four levels below torch/, and
        its codegen is Inductor's. The triad is judged near each compiler
        folder, so the library stays a library."""
        pyproject = write_pyproject_toml(tmp_path, '[project]\nname = "torch"\nversion = "2.9.0"\n')
        files = ["pyproject.toml", "torch/__init__.py", "torch/compiler/__init__.py", "torch/compiler/config.py",
                 "torch/csrc/jit/frontend/lexer.cpp", "torch/csrc/jit/frontend/parser.cpp",
                 "torch/_inductor/codegen/common.py"]
        proc = run_tree(tmp_path, files, manifests=pyproject)
        out = json.loads(proc.stdout)
        assert out["shape"] != "language-reference"
        assert not any(sig.startswith("tree_triad:") for sig in out["signals"])
        # the same members beside the compiler folder make it one
        _, near = mod.tree_signals(["torch/compiler/lexer.cpp", "torch/compiler/parser.cpp",
                                    "torch/_inductor/codegen/common.py"])
        assert mod._whole_language_tree(near) == ("torch/compiler", "lexer,parser")

    @pytest.mark.parametrize(
        "path,near",
        [
            pytest.param("src/compiler", True, id="the-folder"),
            pytest.param("src/compiler/deep/er/parser.ts", True, id="under-it"),
            pytest.param("src/parser/", True, id="a-sibling"),
            pytest.param("src/parser/parser.go", True, id="in-a-sibling"),
            pytest.param("src/parser/x/parser.go", False, id="three-below-the-parent"),
            pytest.param("lib/parser.ts", False, id="outside-the-parent"),
            pytest.param("src/compiler2/parser.ts", True, id="two-below-the-parent"),
        ],
    )
    def test_near_a_compiler_folder(self, path, near):
        assert mod._near_compiler_dir(path, "src/compiler") is near
        # a root compiler folder: everything two levels deep is near it
        assert mod._near_compiler_dir("Python/ast.c", "Parser") is True
        assert mod._near_compiler_dir("Objects/x/ast.c", "Parser") is False

    def test_a_listing_of_only_non_core_paths_is_unknown(self, tmp_path):
        """The listing was read but holds no path the gates read: unknown
        (exit 1), not a missing --manifests."""
        proc = run_tree(tmp_path, [".github/workflows/ci.yml", "docs/index.md", "tests/test_a.py"])
        assert proc.returncode == 1, proc.stderr
        assert json.loads(proc.stdout) == {"shape": "unknown", "signals": [], "confidence": 0.0,
                                           "export_count": 0, "package_count": 0}

    @pytest.mark.parametrize(
        "listing",
        [
            pytest.param(json.dumps({"status": "ok", "tree": [], "count": 0, "truncated": False}), id="probe"),
            pytest.param(json.dumps({"sha": "abc", "tree": [{"path": "src", "type": "tree"}]}), id="no-blob"),
        ],
    )
    def test_a_listing_that_holds_no_path_is_a_tree_file_error(self, tmp_path, listing):
        probe = tmp_path / "tree.json"
        probe.write_bytes(listing.encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", "", "--tree-file", str(probe)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert proc.returncode == 2
        err = json.loads(proc.stderr)
        assert err["code"] == "TREE_FILE_ERROR" and "holds no file path" in err["error"]

    def test_a_tree_past_10000_files_is_read_whole(self, tmp_path):
        """More than 10,000 files: the one corroborating file is the last
        path, so a listing cut short, or a filter's head -n cap, loses it."""
        paths = [f"src/lib/m{i // 100}/f{i}.c" for i in range(12000)]
        paths += ["Parser/lexer/lexer.c", "Parser/parser.c", "Python/ast.c", "Python/ceval.c"]
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "ok", "tree": paths, "count": len(paths),
                                      "truncated": False}).encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", "", "--tree-file", str(probe)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["shape"] == "language-reference"

    def test_a_cut_short_listing_adds_a_signal(self, tmp_path):
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "ok", "tree": TREE_SITTER_FILES, "truncated": True}).encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", "", "--tree-file", str(probe)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert "tree_truncated" in json.loads(proc.stdout)["signals"]

    def test_the_tree_file_reads_stdin(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", "", "--tree-file", "-"],
            input="\n".join(TREE_SITTER_FILES), capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert "grammar_file:grammar.js" in json.loads(proc.stdout)["signals"]

    @pytest.mark.parametrize(
        "extra",
        [pytest.param(["--grammar-files", "parse.y"], id="grammar-files"),
         pytest.param(["--tree-paths", "compiler/"], id="tree-paths")],
    )
    def test_the_tree_is_passed_once(self, tmp_path, extra):
        proc = run_tree(tmp_path, TREE_SITTER_FILES, *extra)
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == "INVALID_ARGS"

    def test_a_failed_listing_exits_2(self, tmp_path):
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "unavailable", "message": "gh is not logged in"}).encode("utf-8"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, "--manifests", "", "--tree-file", str(probe)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert proc.returncode == 2
        err = json.loads(proc.stderr)
        assert err["code"] == "TREE_FILE_ERROR" and "gh is not logged in" in err["error"]

    def test_the_installed_layout_needs_the_listing_reader(self, tmp_path):
        scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("skf-shape-detect.py", "skf-detect-language.py"):
            (scripts / name).write_bytes((SCRIPT_PATH.parent / name).read_bytes())
        cmd = [sys.executable, str(scripts / "skf-shape-detect.py"), "--repo-url", REPO_URL, "--manifests", "",
               "--tree-file", _tree_file(tmp_path, TREE_SITTER_FILES)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stderr
        (scripts / "skf-detect-language.py").unlink()
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 2
        assert "cannot load skf-detect-language.py" in json.loads(proc.stderr)["error"]


# --------------------------------------------------------------------------
# --manifests-file: the scan envelope in place of a model-built list
# (the W4 determinism-6 residual)
# --------------------------------------------------------------------------

SCAN_SCRIPT = SCRIPT_PATH.parent / "skf-scan-manifests.py"


def _write_bytes(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _envelope_file(tmp_path: Path, paths: list[str], name: str = "manifests-1.json") -> str:
    """A skf-scan-manifests.py envelope listing `paths` (the fields the script reads)."""
    out = tmp_path / name
    manifests = [{"path": p, "ecosystem": "x", "name": None, "private": None, "deps": [], "internal_deps": []}
                 for p in paths]
    out.write_bytes(json.dumps({"manifests": manifests, "total_unique": 0, "monorepo": False}).encode("utf-8"))
    return str(out)


def run_manifests_file(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT_PATH), "--repo-url", REPO_URL, *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


class TestManifestsFile:
    def test_the_scanner_envelope_is_read_whole(self, tmp_path):
        """The real scan of a monorepo feeds shape detection with no list in between:
        the same answer as the comma list of the resolved paths gives."""
        root = tmp_path / "repo"
        _write_bytes(root, "package.json", json.dumps({"name": "root", "private": True,
                                                       "workspaces": ["packages/*"]}).encode("utf-8"))
        _write_bytes(root, "packages/core/package.json",
                     json.dumps({"name": "@acme/core", "main": "index.js"}).encode("utf-8"))
        _write_bytes(root, "packages/api/pyproject.toml", b'[project]\nname = "acme-api"\n')
        _write_bytes(root, "requirements.txt", b"requests\n")
        scan = subprocess.run([sys.executable, str(SCAN_SCRIPT), "scan", str(root)],
                              capture_output=True, timeout=60)
        assert scan.returncode == 0, scan.stderr
        envelope = tmp_path / "manifests-1.json"
        envelope.write_bytes(scan.stdout)
        by_file = run_manifests_file("--manifests-file", str(envelope), "--manifest-dir", str(root))
        assert by_file.returncode == 0, by_file.stderr
        listed = ",".join(str(root / p) for p in ("package.json", "packages/api/pyproject.toml",
                                                  "packages/core/package.json"))
        by_list = run_manifests_file("--manifests", listed)
        out = json.loads(by_file.stdout)
        assert out["shape"] == json.loads(by_list.stdout)["shape"] == "stack-compose"
        assert out["package_count"] == 3, "requirements.txt is a type the script does not classify"

    def test_only_the_classified_types_are_kept(self, tmp_path):
        """A type the script cannot parse is left out, not refused as UNSUPPORTED_MANIFEST."""
        _write_bytes(tmp_path, "Cargo.toml", b'[package]\nname = "lib"\n\n[lib]\npath = "src/lib.rs"\n')
        envelope = _envelope_file(tmp_path, ["Gemfile", "requirements.txt", "Cargo.toml", "setup.cfg"])
        proc = run_manifests_file("--manifests-file", envelope, "--manifest-dir", str(tmp_path))
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert (out["shape"], out["package_count"]) == ("library-API", 1)
        assert mod.read_manifests_file(envelope) == ["Cargo.toml"]

    def test_core_and_depth_read_the_path_below_the_scan_root(self, tmp_path):
        """A repository checked out under a folder named examples/ is still its own
        core package: the path the envelope gives, not where the root sits, decides."""
        root = tmp_path / "examples" / "cli"
        _write_bytes(root, "package.json", json.dumps({
            "name": "acme-cli", "bin": {"acme": "bin/acme.js"}, "dependencies": {"commander": "^12"},
        }).encode("utf-8"))
        envelope = _envelope_file(tmp_path, ["package.json"])
        proc = run_manifests_file("--manifests-file", envelope, "--manifest-dir", str(root))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["shape"] == "reference-app"
        assert mod.is_core_manifest("package.json", "acme-cli")
        assert not mod.is_core_manifest((root / "package.json").as_posix(), "acme-cli")

    def test_an_envelope_with_no_classified_manifest_still_reads_the_tree(self, tmp_path):
        """A manifest-less language toolchain (CPython) is classified from its files."""
        envelope = _envelope_file(tmp_path, [])
        proc = run_manifests_file("--manifests-file", envelope, "--manifest-dir", str(tmp_path),
                                  "--tree-file", _tree_file(tmp_path, CPYTHON_FILES))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["shape"] == "language-reference"

    @pytest.mark.parametrize(
        "args, code",
        [
            pytest.param(["--manifests", "a/package.json"], "INVALID_ARGS", id="both-forms"),
            pytest.param([], "INVALID_ARGS", id="no-manifest-dir"),
        ],
    )
    def test_the_manifests_are_passed_once_with_their_root(self, tmp_path, args, code):
        envelope = _envelope_file(tmp_path, ["package.json"])
        extra = [] if args == [] else ["--manifest-dir", str(tmp_path)]
        proc = run_manifests_file("--manifests-file", envelope, *extra, *args)
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == code

    def test_the_manifest_dir_goes_with_the_file(self, tmp_path):
        proc = run_manifests_file("--manifests", "", "--manifest-dir", str(tmp_path))
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == "INVALID_ARGS"

    @pytest.mark.parametrize(
        "content",
        [pytest.param(b"not json", id="not-json"),
         pytest.param(b'{"warnings": []}', id="no-manifests"),
         pytest.param(b'{"manifests": [{"ecosystem": "npm"}]}', id="entry-without-path")],
    )
    def test_a_file_that_is_no_scan_envelope_exits_2(self, tmp_path, content):
        path = tmp_path / "manifests-1.json"
        path.write_bytes(content)
        proc = run_manifests_file("--manifests-file", str(path), "--manifest-dir", str(tmp_path))
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == "MANIFESTS_FILE_ERROR"

    def test_a_missing_manifest_names_the_resolved_path(self, tmp_path):
        envelope = _envelope_file(tmp_path, ["pkg/package.json"])
        proc = run_manifests_file("--manifests-file", envelope, "--manifest-dir", str(tmp_path / "root"))
        assert proc.returncode == 2
        err = json.loads(proc.stderr)
        assert err["code"] == "MANIFEST_NOT_FOUND"
        assert (tmp_path / "root" / "pkg" / "package.json").as_posix() in err["error"]

    def test_neither_form_is_an_error(self):
        proc = run_manifests_file()
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == "MISSING_MANIFESTS"


# --------------------------------------------------------------------------
# A library that extends a framework declares what an app on it declares: the
# script reports the facts and the caller judges (step 5b determinism-1)
# --------------------------------------------------------------------------

FASTAPI_PYPROJECT = b"""[project]
name = "fastapi"
version = "0.115.0"
description = "FastAPI framework, high performance, easy to learn, fast to code, ready for production"
dependencies = ["starlette>=0.40.0,<0.42.0", "pydantic>=1.7.4,!=1.8,<3.0.0", "typing-extensions>=4.8.0"]
"""
SQLADMIN_PYPROJECT = b"""[project]
name = "sqladmin"
version = "0.19.0"
description = "SQLAlchemy admin for FastAPI and Starlette"
dependencies = ["starlette", "sqlalchemy >=1.4", "wtforms >=3.1, <3.2", "jinja2", "python-multipart"]
"""
AXUM_EXTRA_CARGO = b"""[package]
name = "axum-extra"
version = "0.9.4"
description = "Extra utilities for axum"

[lib]
path = "src/lib.rs"

[dependencies]
axum = { path = "../axum", version = "0.7.7", default-features = false }
bytes = "1.1.0"
"""


class TestFrameworkExtensionLibraries:
    @pytest.mark.parametrize(
        ("filename", "content", "framework"),
        [pytest.param("pyproject.toml", FASTAPI_PYPROJECT, "starlette", id="fastapi"),
         pytest.param("pyproject.toml", SQLADMIN_PYPROJECT, "starlette", id="sqladmin"),
         pytest.param("Cargo.toml", AXUM_EXTRA_CARGO, "axum", id="axum-extra")],
    )
    def test_the_scan_envelope_call_reports_the_open_question(self, tmp_path, filename, content, framework):
        """The step-auto-scope call (scan envelope and tree file) keeps the shape and its
        confidence and adds the signal the caller judges from the README or description."""
        root = tmp_path / "repo"
        _write_bytes(root, filename, content)
        scan = subprocess.run([sys.executable, str(SCAN_SCRIPT), "scan", str(root)], capture_output=True, timeout=60)
        assert scan.returncode == 0, scan.stderr
        envelope = tmp_path / "manifests-1.json"
        envelope.write_bytes(scan.stdout)
        tree = _tree_file(tmp_path, [filename, "src/lib.rs" if filename == "Cargo.toml" else "README.md"])
        proc = run_manifests_file("--manifests-file", str(envelope), "--manifest-dir", str(root), "--tree-file", tree)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert (out["shape"], out["confidence"]) == ("reference-app", 0.8)
        assert f"framework_dep:{framework}" in out["signals"]
        assert "has_library_structure" in out["signals"] and "app_or_library:framework_dep" in out["signals"]

    def test_a_bin_settles_it(self, tmp_path):
        """A framework app that ships a binary is an app: no question for the caller."""
        path = write_cargo_toml(tmp_path, """
[package]
name = "my-server"
version = "0.1.0"

[[bin]]
name = "my-server"
path = "src/main.rs"

[dependencies]
axum = "0.7"
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert "app_or_library:framework_dep" not in result["signals"]

    def test_a_library_monorepo_member_on_a_framework_still_asks(self, tmp_path):
        """In a monorepo the framework of a core member raises the same question."""
        root = _write(tmp_path, "package.json", {"name": "root", "private": True})
        plugin = _write(tmp_path, "packages/plugin/package.json",
                        {"name": "fastify-plugin-x", "main": "index.js", "dependencies": {"fastify": "4"}})
        result = mod.detect(REPO_URL, [root, plugin])
        assert result["shape"] == "reference-app"
        assert "app_or_library:framework_dep" in result["signals"]


# --------------------------------------------------------------------------
# A parser consumer decides no shape: a parser tool among the runtime
# dependencies fits a language built on it and a project that only reads its
# input with it alike, so the ladder goes on and its shape carries the
# question the caller judges from the README or the manifest description.
# --------------------------------------------------------------------------

LOGTAIL_CARGO = b"""[package]
name = "logtail"
version = "0.3.0"

[[bin]]
name = "logtail"
path = "src/main.rs"

[dependencies]
nom = "7"
clap = "4"
"""
MATPLOTLIB_PYPROJECT = b"""[project]
name = "matplotlib"
version = "3.9.0"
description = "Python plotting package"
dependencies = ["contourpy>=1.0.1", "cycler>=0.10", "numpy>=1.23", "pyparsing>=2.3.1", "pillow>=8"]
"""
TOML_EDIT_CARGO = b"""[package]
name = "toml_edit"
version = "0.22.0"

[lib]
path = "src/lib.rs"

[dependencies]
winnow = "0.6"
indexmap = "2"
"""


class TestParserConsumers:
    @pytest.mark.parametrize(
        ("filename", "content", "source", "shape", "dep"),
        [pytest.param("Cargo.toml", LOGTAIL_CARGO, "src/main.rs", "reference-app", "nom", id="cli-on-nom"),
         pytest.param("pyproject.toml", MATPLOTLIB_PYPROJECT, "lib/matplotlib/__init__.py", "library-API",
                      "pyparsing", id="matplotlib-on-pyparsing"),
         pytest.param("Cargo.toml", TOML_EDIT_CARGO, "src/lib.rs", "library-API", "winnow",
                      id="toml_edit-on-winnow")],
    )
    def test_the_scan_envelope_call_answers_and_asks(self, tmp_path, filename, content, source, shape, dep):
        """The step-auto-scope call gives the shape the rest of the ladder finds,
        exit 0, and adds the question the caller judges."""
        root = tmp_path / "repo"
        _write_bytes(root, filename, content)
        scan = subprocess.run([sys.executable, str(SCAN_SCRIPT), "scan", str(root)], capture_output=True, timeout=60)
        assert scan.returncode == 0, scan.stderr
        envelope = tmp_path / "manifests-1.json"
        envelope.write_bytes(scan.stdout)
        tree = _tree_file(tmp_path, [filename, source])
        proc = run_manifests_file("--manifests-file", str(envelope), "--manifest-dir", str(root), "--tree-file", tree)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["shape"] == shape
        assert {f"parser_dep:{dep}", PARSER_QUESTION} <= set(out["signals"])

    @pytest.mark.parametrize(
        ("write", "content"),
        [pytest.param(write_cargo_toml, '[package]\nname = "my-crate"\n\n[lib]\nname = "my_crate"\n\n'
                      '[dev-dependencies]\nnom = "7"\n', id="cargo-dev-dependency"),
         pytest.param(write_cargo_toml, '[package]\nname = "my-crate"\n\n[lib]\nname = "my_crate"\n\n'
                      '[build-dependencies]\npest = "2"\n', id="cargo-build-dependency"),
         pytest.param(write_package_json, {"name": "my-lib", "main": "index.js", "devDependencies": {"moo": "0.5"}},
                      id="npm-dev-dependency")],
    )
    def test_a_dev_or_build_dependency_is_no_consumer(self, tmp_path, write, content):
        result = mod.detect(REPO_URL, [write(tmp_path, content)])
        assert result["shape"] == "library-API"
        assert not any(s.startswith("parser_dep:") for s in result["signals"])
        assert PARSER_QUESTION not in result["signals"]

    def test_a_framework_library_with_a_parser_dep_asks_both(self, tmp_path):
        """A FastAPI package that also depends on lark carries both questions."""
        path = write_pyproject_toml(tmp_path, """
[project]
name = "my-api"
version = "0.1.0"
dependencies = ["fastapi>=0.110", "lark>=1"]
""")
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert {"app_or_library:framework_dep", "parser_dep:lark", PARSER_QUESTION} <= set(result["signals"])

    def test_an_npm_bin_cli_on_moo_asks(self, tmp_path):
        path = write_package_json(tmp_path, {"name": "logfmt-cli", "bin": {"logfmt": "cli.js"},
                                             "dependencies": {"moo": "0.5"}})
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "reference-app"
        assert {"has_bin_field", "parser_dep:moo", PARSER_QUESTION} <= set(result["signals"])

    def test_a_stack_compose_repo_asks(self, tmp_path):
        js = _write(tmp_path, "package.json", {"name": "web", "main": "index.js", "dependencies": {"chevrotain": "11"}})
        py = write_pyproject_toml(tmp_path, '[project]\nname = "core"\nversion = "1.0.0"\n')
        result = mod.detect(REPO_URL, [js, py])
        assert result["shape"] == "stack-compose"
        assert PARSER_QUESTION in result["signals"]

    def test_gate_g_keeps_a_delegating_consumer_out(self, tmp_path):
        """A repo that delegates parsing to a concrete parser is no language
        reference, so its parser dependency raises no question."""
        path = write_package_json(tmp_path, {"name": "my-linter", "main": "index.js",
                                             "dependencies": {"acorn": "8", "moo": "0.5"}})
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "library-API"
        assert {"delegating_consumer", "parser_dep:moo"} <= set(result["signals"])
        assert PARSER_QUESTION not in result["signals"]

    def test_gate_g_leaves_a_bare_manifest_unknown(self, tmp_path):
        """Gate G also keeps the bare-manifest rung from answering: with no
        other signal, a parser dependency beside a concrete parser (yaml) is
        unknown, and the caller analyzes the repository interactively."""
        path = write_package_json(tmp_path, {"name": "logq", "description": "A query language for logs",
                                             "dependencies": {"chevrotain": "11", "yaml": "2"}})
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "unknown"
        assert {"delegating_consumer", "parser_dep:chevrotain"} <= set(result["signals"])
        assert PARSER_QUESTION not in result["signals"]

    @pytest.mark.parametrize("parser", [True, False], ids=["with-moo", "without-moo"])
    def test_a_monorepo_of_bin_only_members_stays_unknown(self, tmp_path, parser):
        """Rung 3 does not count the bins of a monorepo's members, but a bin is
        no bare DSL manifest: a toolbox of CLIs, one of them on moo, is unknown
        (exit 1) like its twin with no parser, never language-reference."""
        root = tmp_path / "repo"
        deps = {"moo": "0.5", "chalk": "5"} if parser else {"chalk": "5"}
        for rel, data in {"package.json": {"name": "tools-root", "private": True, "workspaces": ["packages/*"]},
                          "packages/logfmt/package.json": {"name": "logfmt-cli", "bin": {"logfmt": "cli.js"},
                                                           "dependencies": deps},
                          "packages/jsonl/package.json": {"name": "jsonl-cli", "bin": {"jsonl": "cli.js"},
                                                          "dependencies": {"chalk": "5"}}}.items():
            _write_bytes(root, rel, json.dumps(data).encode("utf-8"))
        scan = subprocess.run([sys.executable, str(SCAN_SCRIPT), "scan", str(root)], capture_output=True, timeout=60)
        assert scan.returncode == 0, scan.stderr
        envelope = tmp_path / "manifests-1.json"
        envelope.write_bytes(scan.stdout)
        tree = _tree_file(tmp_path, ["package.json", "packages/logfmt/package.json", "packages/logfmt/cli.js",
                                     "packages/jsonl/package.json", "packages/jsonl/cli.js"])
        proc = run_manifests_file("--manifests-file", str(envelope), "--manifest-dir", str(root), "--tree-file", tree)
        assert proc.returncode == 1, proc.stdout
        out = json.loads(proc.stdout)
        assert out["shape"] == "unknown"
        assert ("parser_dep:moo" in out["signals"]) is parser
        assert PARSER_QUESTION not in out["signals"]

    def test_a_parser_in_an_example_member_is_no_consumer(self, tmp_path):
        """As with frameworks, only the core members' runtime dependencies
        count: a parser used by an examples/ member raises no question."""
        core = _write(tmp_path, "packages/core/package.json", {"name": "@acme/core", "main": "index.js"})
        demo = _write(tmp_path, "examples/dsl-demo/package.json",
                      {"name": "dsl-demo", "dependencies": {"chevrotain": "11"}})
        result = mod.detect(REPO_URL, [core, demo])
        assert result["shape"] == "library-API"
        assert not any(s.startswith("parser_dep:") for s in result["signals"])
        assert PARSER_QUESTION not in result["signals"]

    def test_a_producer_still_decides(self, tmp_path):
        """A package named after a parser tool is one: no question."""
        path = write_cargo_toml(tmp_path, '[package]\nname = "winnow"\n\n[lib]\nname = "winnow"\n\n'
                                          '[dependencies]\nnom = "7"\n')
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "language-reference"
        assert "parser_producer:winnow" in result["signals"]
        assert PARSER_QUESTION not in result["signals"]
