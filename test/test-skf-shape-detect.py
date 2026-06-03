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


class TestLanguageReference:
    def test_npm_with_parser_dep(self, tmp_path):
        path = write_package_json(tmp_path, {
            "name": "my-grammar",
            "dependencies": {"antlr4": "4.13.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert result["confidence"] >= 0.75
        assert "parser_dep:antlr4" in result["signals"]

    def test_python_with_parser_dep(self, tmp_path):
        path = write_pyproject_toml(tmp_path, """
[project]
name = "my-parser"
version = "0.1.0"
dependencies = ["lark>=1.0", "lark-parser"]
""")
        result = mod.detect(REPO_URL, [path])
        assert_result_shape(result)
        assert result["shape"] == "language-reference"
        assert result["confidence"] >= 0.80

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
        assert result["shape"] == "language-reference"
        assert any("parser_dep:" in s for s in result["signals"])

    def test_parser_dep_beats_framework_dep(self, tmp_path):
        """language-reference fires before reference-app in the ladder."""
        path = write_package_json(tmp_path, {
            "name": "compiler-app",
            "dependencies": {"tree-sitter": "0.20.0", "express": "4.18.0"},
        })
        result = mod.detect(REPO_URL, [path])
        assert result["shape"] == "language-reference"


# --------------------------------------------------------------------------
# Shape: language-reference — PRODUCERS (issue #427)
#
# The pre-#427 heuristic only fired on parser-generator *dependencies*, i.e.
# *consumers* of parser tooling. A language tool's OWN repo doesn't depend on
# a parser generator — it IS one (pest's Cargo.toml has no `pest` dep; it
# declares `[package] name = "pest"`). Tier 1 fix: a repo whose own package
# name is itself a known parser/grammar tool is a producer and classifies as
# language-reference. The consumer path is kept (a DSL built on lalrpop is
# still a language project).
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

    def test_lalrpop_consumer_still_language_reference(self, tmp_path):
        """A DSL built ON lalrpop (build-dep) stays language-reference."""
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
        assert result["shape"] == "language-reference"


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

    def test_genuine_monorepo_app_member_still_reference_app(self, tmp_path):
        # A core (non-example) member that runtime-depends on a framework.
        root = _write(tmp_path, "package.json",
                      {"name": "root", "private": True})
        app = _write(tmp_path, "apps/web/package.json",
                     {"name": "web", "dependencies": {"next": "14"}})
        result = mod.detect(REPO_URL, [root, app])
        assert result["shape"] == "reference-app"
