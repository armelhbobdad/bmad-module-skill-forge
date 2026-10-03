#!/usr/bin/env python3
"""Tests for skf-extract-public-api.py.

Quick mode does no I/O: it parses content passed in via JSON. Tests
build payloads inline, call extract() directly, and assert on the
shape of the returned envelope. Per-language manifest parsers and
export scanners are also exercised individually. --follow, which reads
the modules a chain names (fetched first with --repo), runs on staged
folders with the fetch helper's raw read stubbed.

Full mode runs the ast-grep recipes over a source tree (#584). Its file
selection, glob rules, recipe file checks, merge, entry-point readers and
CLI are tested without ast-grep; the runs over small source trees, which
pin the exact exports, the entry-point diff and the counts, need the
ast-grep version package.json's test:python pins and are skipped without
it.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-extract-public-api.py"
DATA_FILE = REPO / "src" / "shared" / "data" / "ast-grep-recipes.yaml"

spec = importlib.util.spec_from_file_location("skf_extract_public_api", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# JS / TS
# --------------------------------------------------------------------------


class TestPackageJson:
    def test_basic(self):
        out = mod.parse_package_json('{"name":"foo","version":"1.0","description":"d","dependencies":{"a":"1","b":"2"}}')
        assert out["name"] == "foo"
        assert out["version"] == "1.0"
        assert out["description"] == "d"
        assert out["dependencies"] == ["a", "b"]

    def test_malformed_records_warning(self):
        out = mod.parse_package_json("{ this is not json")
        assert "_parse_error" in out
        assert "JSON parse error" in out["_parse_error"]

    def test_root_must_be_object(self):
        out = mod.parse_package_json('["array", "not", "object"]')
        assert "_parse_error" in out


class TestJsExportScanner:
    def test_decl_forms(self):
        src = (
            "export const VERSION = 1;\n"
            "export function helloFn() {}\n"
            "export class FooClass {}\n"
            "export interface Bar {}\n"
            "export type Quux = string;\n"
            "export enum State { On }\n"
            "export default function defaulted() {}\n"
        )
        names = [e["name"] for e in mod.scan_exports_js(src, "src/index.ts")]
        assert names == ["VERSION", "helloFn", "FooClass", "Bar", "Quux", "State", "defaulted"]

    def test_re_exports_with_alias(self):
        src = 'export { Quux as Pub, Other } from "./internal";\n'
        names = [e["name"] for e in mod.scan_exports_js(src, "src/index.ts")]
        assert names == ["Pub", "Other"]

    def test_dedup_across_decl_and_reexport(self):
        # If both forms surface the same name, we only keep one entry.
        src = "export const Foo = 1;\nexport { Foo } from './other';\n"
        names = [e["name"] for e in mod.scan_exports_js(src, "src/index.ts")]
        assert names == ["Foo"]


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------


class TestPyprojectToml:
    def test_basic(self):
        toml = (
            '[project]\n'
            'name = "foo"\n'
            'version = "1.2.3"\n'
            'description = "d"\n'
            'dependencies = ["requests>=2", "pydantic>=1.10", "click==8.0"]\n'
        )
        out = mod.parse_pyproject_toml(toml)
        assert out["name"] == "foo"
        assert out["version"] == "1.2.3"
        assert out["dependencies"] == ["requests", "pydantic", "click"]

    def test_malformed_records_warning(self):
        out = mod.parse_pyproject_toml("not valid = toml = [")
        assert "_parse_error" in out


class TestSetupPy:
    def test_extracts_kwargs(self):
        src = 'from setuptools import setup\nsetup(\n  name="foo",\n  version="0.1.0",\n  description="legacy package",\n)\n'
        out = mod.parse_setup_py(src)
        assert out["name"] == "foo"
        assert out["version"] == "0.1.0"
        assert out["description"] == "legacy package"


class TestPythonExportScanner:
    def test_skips_underscore_private(self):
        src = "def public_fn(): pass\nclass Public: pass\ndef _private(): pass\nclass _Hidden: pass\n"
        names = [e["name"] for e in mod.scan_exports_python(src, "x.py")]
        assert names == ["public_fn", "Public"]

    def test_honours_dunder_all(self):
        src = (
            '__all__ = ["public_fn", "Public"]\n'
            "def public_fn(): pass\n"
            "class Public: pass\n"
            "def also_public_in_source(): pass\n"  # excluded because not in __all__
        )
        names = [e["name"] for e in mod.scan_exports_python(src, "x.py")]
        assert names == ["public_fn", "Public"]


# --------------------------------------------------------------------------
# Rust
# --------------------------------------------------------------------------


class TestCargoToml:
    def test_basic(self):
        toml = '[package]\nname = "my-crate"\nversion = "0.5.0"\ndescription = "rust thing"\n[dependencies]\nserde = "1"\ntokio = "1"\n'
        out = mod.parse_cargo_toml(toml)
        assert out["name"] == "my-crate"
        assert out["version"] == "0.5.0"
        assert out["dependencies"] == ["serde", "tokio"]


class TestRustExportScanner:
    def test_pub_items(self):
        src = (
            "pub fn hello() {}\n"
            "pub struct Config;\n"
            "pub enum State { On, Off }\n"
            "pub trait T {}\n"
            "pub mod sub {}\n"
            "pub type Alias = u32;\n"
            "pub const C: u32 = 0;\n"
            "fn private_fn() {}\n"
        )
        kinds = {(e["name"], e["type"]) for e in mod.scan_exports_rust(src, "src/lib.rs")}
        assert kinds == {
            ("hello", "fn"),
            ("Config", "struct"),
            ("State", "enum"),
            ("T", "trait"),
            ("sub", "mod"),
            ("Alias", "type"),
            ("C", "const"),
        }


# --------------------------------------------------------------------------
# Go
# --------------------------------------------------------------------------


class TestGoMod:
    def test_module_and_require_block(self):
        src = (
            "module github.com/example/foo\n\n"
            "go 1.22\n\n"
            "require (\n"
            "    github.com/stretchr/testify v1.8.0\n"
            "    github.com/spf13/cobra v1.7.0\n"
            ")\n"
        )
        out = mod.parse_go_mod(src)
        assert out["name"] == "github.com/example/foo"
        assert "github.com/stretchr/testify" in out["dependencies"]
        assert "github.com/spf13/cobra" in out["dependencies"]

    def test_single_line_require(self):
        out = mod.parse_go_mod("module example.com/x\n\nrequire example.com/y v1.0.0\n")
        assert out["dependencies"] == ["example.com/y"]


class TestGoExportScanner:
    def test_capitalized_only(self):
        src = "package foo\n\nfunc PublicFn() {}\nfunc privateFn() {}\ntype PublicType struct{}\ntype privateType struct{}\nvar PublicVar = 1\nconst PublicConst = 2\n"
        names = [e["name"] for e in mod.scan_exports_go(src, "main.go")]
        assert names == ["PublicFn", "PublicType", "PublicVar", "PublicConst"]


# --------------------------------------------------------------------------
# Java / Maven
# --------------------------------------------------------------------------


class TestPomXml:
    def test_basic(self):
        xml = (
            '<?xml version="1.0"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">'
            "<groupId>com.example</groupId>"
            "<artifactId>myapp</artifactId>"
            "<version>2.0</version>"
            "<description>java thing</description>"
            "<dependencies>"
            "<dependency><groupId>junit</groupId><artifactId>junit</artifactId></dependency>"
            "</dependencies>"
            "</project>"
        )
        out = mod.parse_pom_xml(xml)
        assert out["name"] == "myapp"
        assert out["version"] == "2.0"
        assert out["dependencies"] == ["junit"]
        assert out["_extra"]["group_id"] == "com.example"

    def test_multi_module(self):
        xml = (
            '<?xml version="1.0"?>'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">'
            "<groupId>g</groupId><artifactId>parent</artifactId><version>1</version>"
            "<modules><module>core</module><module>server</module></modules>"
            "</project>"
        )
        out = mod.parse_pom_xml(xml)
        assert out["modules"] == ["core", "server"]

    def test_malformed_records_warning(self):
        out = mod.parse_pom_xml("<project>not closed")
        assert "_parse_error" in out


class TestJavaExportScanner:
    def test_public_decls(self):
        src = (
            "public class Foo {\n"
            "  public void m() {}\n"
            "}\n"
            "public interface Bar {}\n"
            "public enum E { A }\n"
            "public record R(int x) {}\n"
            "class PackagePrivate {}\n"
        )
        names = [e["name"] for e in mod.scan_exports_java(src, "Foo.java")]
        assert names == ["Foo", "Bar", "E", "R"]

    def test_annotation_classes(self):
        src = (
            "@RestController\n"
            "class Endpoints {}\n"
            "@Service\n"
            "public class Svc {}\n"  # should still be picked up via public decl, not duplicated
        )
        results = mod.scan_exports_java(src, "x.java")
        names_and_types = {(e["name"], e["type"]) for e in results}
        assert ("Endpoints", "restcontroller") in names_and_types
        # Svc is captured as a public class (not annotation) since the public decl wins
        assert ("Svc", "class") in names_and_types
        # And the annotation pass does not duplicate Svc
        svc_count = sum(1 for e in results if e["name"] == "Svc")
        assert svc_count == 1


# --------------------------------------------------------------------------
# Kotlin / Gradle
# --------------------------------------------------------------------------


class TestGradle:
    def test_extracts_group_and_version(self):
        src = 'group = "com.example"\nversion = "1.0"\n'
        out = mod.parse_gradle(src)
        assert out["name"] == "com.example"
        assert out["version"] == "1.0"

    def test_settings_gradle_includes(self):
        src = 'include(":core", ":server")\ninclude ":legacy"\n'
        modules = mod.parse_settings_gradle(src)
        assert "core" in modules and "server" in modules and "legacy" in modules


class TestKotlinExportScanner:
    def test_defaults_to_public(self):
        src = (
            "class Public {}\n"
            "internal class Hidden {}\n"
            "private class Secret {}\n"
            "fun publicFn() {}\n"
            "private fun secret() {}\n"
            "open class OpenThing {}\n"
            "data class Pair(val a: Int)\n"
        )
        names = [e["name"] for e in mod.scan_exports_kotlin(src, "Foo.kt")]
        assert names == ["Public", "publicFn", "OpenThing", "Pair"]


class TestPackageSwift:
    def test_extracts_name_and_deps(self):
        src = (
            'let package = Package(\n'
            '    name: "Alamofire",\n'
            '    dependencies: [\n'
            '        .package(url: "https://github.com/apple/swift-nio.git", from: "2.0.0"),\n'
            '    ]\n'
            ')\n'
        )
        out = mod.parse_package_swift(src)
        assert out["name"] == "Alamofire"
        assert out["version"] is None  # SwiftPM versions come from git tags
        assert "swift-nio" in out["dependencies"]


class TestSwiftExportScanner:
    def test_only_public_and_open_emitted(self):
        src = (
            "public struct Request {}\n"
            "struct Internal {}\n"            # default internal — omitted
            "private class Secret {}\n"
            "open class Session {}\n"
            "public func send() {}\n"
            "public enum Method { case get }\n"
            "public protocol Codable {}\n"
            "internal func helper() {}\n"
            "public final class Manager {}\n"
            "public var shared = 1\n"
        )
        out = mod.scan_exports_swift(src, "Alamofire.swift")
        names = [e["name"] for e in out]
        assert names == [
            "Request", "Session", "send", "Method", "Codable", "Manager", "shared",
        ]
        assert {"name": "Request", "type": "struct", "source_file": "Alamofire.swift"} in out

    def test_class_method_does_not_leak_keyword_as_name(self):
        # `public class func` is a type method — must not emit "func" as a name.
        src = "public class func makeDefault() {}\n"
        names = [e["name"] for e in mod.scan_exports_swift(src, "x.swift")]
        assert "func" not in names


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------


class TestExtract:
    def test_unknown_language_returns_error(self):
        result = mod.extract({"language": "fortran", "manifest": {"path": "x", "content": ""}, "entries": []})
        assert "_error" in result

    def test_no_manifest_content_warns_but_succeeds(self):
        result = mod.extract(
            {
                "language": "python",
                "manifest": {"path": "pyproject.toml", "content": ""},
                "entries": [{"path": "foo.py", "content": "def hello(): pass\n"}],
            }
        )
        assert "_error" not in result
        assert any("no manifest content" in w for w in result["warnings"])
        assert [e["name"] for e in result["exports"]] == ["hello"]

    def test_setup_py_path_routes_to_setup_parser(self):
        result = mod.extract(
            {
                "language": "python",
                "manifest": {"path": "setup.py", "content": 'setup(name="legacy", version="0.1")'},
                "entries": [],
            }
        )
        assert result["package_name"] == "legacy"
        assert result["version"] == "0.1"

    def test_full_python_envelope(self):
        result = mod.extract(
            {
                "language": "python",
                "manifest": {
                    "path": "pyproject.toml",
                    "content": '[project]\nname = "foo"\nversion = "1.0"\ndescription = "d"\ndependencies = ["a"]\n',
                },
                "entries": [{"path": "foo/__init__.py", "content": "def public_fn(): pass\n"}],
                "mode": "quick",
            }
        )
        assert result["language"] == "python"
        assert result["package_name"] == "foo"
        assert result["version"] == "1.0"
        assert result["description"] == "d"
        assert result["dependencies"] == ["a"]
        assert result["modules"] == []
        assert result["warnings"] == []
        assert result["exports"] == [
            {"name": "public_fn", "type": "def", "source_file": "foo/__init__.py"}
        ]

    def test_workspace_placeholder_version_warns_and_nulls(self):
        result = mod.extract(
            {
                "language": "js",
                "manifest": {
                    "path": "package.json",
                    "content": '{"name":"foo","version":"workspace:*"}',
                },
                "entries": [],
            }
        )
        assert result["version"] is None
        assert any("placeholder" in w and "workspace:*" in w for w in result["warnings"])

    def test_development_sentinel_warns_and_nulls(self):
        result = mod.extract(
            {
                "language": "js",
                "manifest": {
                    "path": "package.json",
                    "content": '{"name":"foo","version":"0.0.0-development"}',
                },
                "entries": [],
            }
        )
        assert result["version"] is None
        assert any("placeholder" in w and "0.0.0-development" in w for w in result["warnings"])

    def test_semantic_release_sentinel_warns_and_nulls(self):
        result = mod.extract(
            {
                "language": "js",
                "manifest": {
                    "path": "package.json",
                    "content": '{"name":"foo","version":"0.0.0-semantically-released"}',
                },
                "entries": [],
            }
        )
        assert result["version"] is None
        assert any("placeholder" in w and "0.0.0-semantically-released" in w for w in result["warnings"])

    def test_real_version_passes_through_unmolested(self):
        result = mod.extract(
            {
                "language": "js",
                "manifest": {
                    "path": "package.json",
                    "content": '{"name":"foo","version":"1.2.3"}',
                },
                "entries": [],
            }
        )
        assert result["version"] == "1.2.3"
        assert all("placeholder" not in w for w in result["warnings"])

    def test_scanner_failure_recorded_as_warning(self, monkeypatch):
        def boom(content, source_file, warnings):
            raise RuntimeError("scanner exploded")

        # Replace the python scanner's slot in the dispatch table.
        original = mod.LANGUAGE_DISPATCH["python"]
        monkeypatch.setitem(mod.LANGUAGE_DISPATCH, "python", (original[0], boom))
        result = mod.extract(
            {
                "language": "python",
                "manifest": {"path": "pyproject.toml", "content": "[project]\nname = \"x\"\n"},
                "entries": [{"path": "x.py", "content": "def hello(): pass"}],
            }
        )
        assert any("scan failed" in w for w in result["warnings"])
        assert result["exports"] == []


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    def test_stdin_payload_round_trip(self, monkeypatch, capsys):
        payload = {
            "language": "rust",
            "manifest": {"path": "Cargo.toml", "content": '[package]\nname = "x"\nversion = "0.1"\n'},
            "entries": [{"path": "src/lib.rs", "content": "pub fn foo() {}"}],
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        rc = mod.main(["--mode", "quick"])
        assert rc == 0
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert envelope["language"] == "rust"
        assert envelope["package_name"] == "x"
        assert envelope["exports"][0]["name"] == "foo"

    def test_empty_stdin_returns_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        rc = mod.main([])
        assert rc == 2

    def test_invalid_json_returns_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = mod.main([])
        assert rc == 2

    def test_unknown_language_returns_1(self, monkeypatch, capsys):
        payload = {"language": "fortran", "manifest": {"path": "", "content": ""}, "entries": []}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        rc = mod.main([])
        assert rc == 1


# --------------------------------------------------------------------------
# Quick mode: the export forms each scanner reads or warns about (#592)
# --------------------------------------------------------------------------


def _scan(scanner, content: str, source_file: str) -> tuple[list[tuple[str, str]], list[str]]:
    warnings: list[str] = []
    exports = scanner(content, source_file, warnings)
    assert all(e["source_file"] == source_file for e in exports)
    return [(e["name"], e["type"]) for e in exports], warnings


class TestQuickPythonForms:
    def test_reexports_async_defs_and_the_package_imports(self):
        src = (
            "from typing import TYPE_CHECKING, Any\n"
            "from .core import Engine, run as start\n"
            "from mypkg.tools import tool\n"
            "from otherpkg import Foreign\n"
            "from . import sub\n"
            "import json\n"
            "if TYPE_CHECKING:\n    from .hints import Hint\n"
            "VERSION = '1.0'\n"
            "async def fetch(url): return url\n"
            "def configure(): pass\n"
            "class Client: pass\n"
            "def _private(): pass\n"
        )
        names, warnings = _scan(mod.scan_exports_python, src, "src/mypkg/__init__.py")
        # Foreign and Any come from other packages, Hint only under TYPE_CHECKING
        assert names == [("Engine", "re-export"), ("start", "re-export"), ("tool", "re-export"),
                         ("sub", "re-export"), ("fetch", "def"), ("configure", "def"), ("Client", "class")]
        assert warnings == []

    def test_dunder_all_however_it_is_built(self):
        src = (
            "from .core import Engine\n"
            "from ._impl import helper as public_helper\n"
            "import json\n"
            "VERSION: str = '1.0'\n"
            "__all__ = ('Engine', 'VERSION')\n"
            "__all__ += ['public_helper', 'configure']\n"
            "__all__.append('json')\n"
            "__all__.extend(['from_star', '_hidden', 'Engine'])\n"
            "def configure(): pass\n"
            "async def unlisted(): pass\n"
        )
        names, _ = _scan(mod.scan_exports_python, src, "pkg/__init__.py")
        # the names bound by assignment, imported or bound nowhere in the file count as __all__ lists them
        assert names == [("Engine", "re-export"), ("VERSION", "variable"), ("public_helper", "re-export"),
                         ("configure", "def"), ("json", "module"), ("from_star", "re-export")]

    @pytest.mark.parametrize(
        "src,line",
        [
            pytest.param("from .events import *\nfrom . import events\n__all__ = (events.__all__ +\n    ['run'])\n"
                         "def run(): pass\n", 3, id="another-modules-all"),
            pytest.param("__all__ = ['run']\nfrom . import unix\n__all__ += unix.__all__\ndef run(): pass\n", 3,
                         id="augmented"),
            pytest.param("__all__ = [n for n in dir() if not n.startswith('_')]\n", 1, id="computed"),
            pytest.param("__all__ = ['a']\n__all__.extend(NAMES)\n", 2, id="extended"),
        ],
    )
    def test_an_all_built_from_another_module_is_warned(self, src, line):
        """asyncio builds its __all__ from its submodules' __all__: the file
        alone cannot give those names, so quick mode says so."""
        _, warnings = _scan(mod.scan_exports_python, src, "pkg/__init__.py")
        assert warnings == [
            f"pkg/__init__.py line {line}: `__all__` takes names quick mode cannot read (another module's `__all__`, "
            "or a list built at run time): read the names it exports by eye"
        ]

    def test_a_star_import_from_the_package_is_warned(self):
        src = "from .star import *\nfrom os.path import *\nfrom pkg.more import *\ndef run(): pass\n"
        names, warnings = _scan(mod.scan_exports_python, src, "src/pkg/__init__.py")
        assert names == [("run", "def")]
        assert warnings == [
            "src/pkg/__init__.py line 1: `from .star import *` passes on names from a module quick mode does not "
            "read: pass that module as an entry too, or read it by eye",
            "src/pkg/__init__.py line 3: `from pkg.more import *` passes on names from a module quick mode does not "
            "read: pass that module as an entry too, or read it by eye",
        ]

    @pytest.mark.parametrize("entry", ["acme/cloud/storage/__init__.py", "src/acme/cloud/storage/__init__.py"])
    def test_a_nested_package_names_itself_by_its_dotted_path(self, entry):
        """A nested or namespace package imports its own modules by the
        dotted path of its folders, not by its last folder alone."""
        src = (
            "from acme.cloud.storage.blob import Blob\n"
            "from acme.cloud.storage.client import *\n"
            "from cloud.storage.retry import Retry\n"
            "from storage import Bucket\n"
            "from acme.cloud.other import Thing\n"
            "from acme.cloud.storage_utils import Helper\n"
        )
        names, warnings = _scan(mod.scan_exports_python, src, entry)
        assert names == [("Blob", "re-export"), ("Retry", "re-export"), ("Bucket", "re-export")]
        assert warnings == [
            f"{entry} line 2: `from acme.cloud.storage.client import *` passes on names from a module quick mode "
            "does not read: pass that module as an entry too, or read it by eye"
        ]

    def test_newer_syntax_is_read_from_the_text(self):
        src = "type Alias = int\nasync def f[T](x: T) -> T: ...\nclass Box[T]: pass\nfrom .m import (x,\n    y as w)\n"
        names, warnings = _scan(mod.scan_exports_python, src, "pkg/__init__.py")
        assert names == [("f", "def"), ("Box", "class"), ("x", "re-export"), ("w", "re-export")]
        # a Python older than the syntax reads the names from the text, and says so
        assert len(warnings) == (1 if sys.version_info < (3, 12) else 0)
        assert all("cannot parse it" in w for w in warnings)


class TestQuickRustForms:
    def test_qualified_functions_and_pub_use(self):
        src = (
            "//! This crate's API: pub fn in_a_comment() {}\n"
            "pub const fn f() -> u32 { 0 }\n"
            "pub async fn fetch<'a>(s: &'a str) -> &'a str { s }\n"
            "pub unsafe fn raw() {}\n"
            'pub extern "C" fn ffi() {}\n'
            "pub const C: u32 = 0;\n"
            "pub use crate::client::{Client, Builder as ClientBuilder, self as client_mod};\n"
            "pub use serde::Serialize;\n"
            "pub use crate::hidden as _;\n"
            "pub mod client;\n"
            "impl Client {\n    pub fn method(&self) {}\n}\n"
            "pub(crate) fn internal() {}\n"
            "pub struct Config;\n"
        )
        names, warnings = _scan(mod.scan_exports_rust, src, "src/lib.rs")
        # `pub const fn f` is the fn f (the old scanner named it `fn`); a method is no top-level export
        assert names == [("f", "fn"), ("fetch", "fn"), ("raw", "fn"), ("ffi", "fn"), ("C", "const"),
                         ("Client", "re-export"), ("ClientBuilder", "re-export"), ("client_mod", "re-export"),
                         ("Serialize", "re-export"), ("client", "mod"), ("Config", "struct")]
        assert warnings == []

    def test_exported_macros(self):
        src = (
            "#[macro_export]\nmacro_rules! my_vec { () => {} }\n"
            "/// docs\n#[macro_export(local_inner_macros)]\n#[doc(hidden)]\nmacro_rules! other { () => {} }\n"
            "macro_rules! private_one { () => {} }\n"
            "mod inner {\n    #[macro_export]\n    macro_rules! from_inner { () => {} }\n}\n"
            "pub fn f() {}\n"
        )
        names, warnings = _scan(mod.scan_exports_rust, src, "src/lib.rs")
        # a #[macro_export] macro is exported at the crate root wherever it sits
        assert names == [("my_vec", "macro"), ("other", "macro"), ("from_inner", "macro"), ("f", "fn")]
        assert warnings == []

    def test_a_glob_pub_use_is_warned(self):
        names, warnings = _scan(mod.scan_exports_rust, "pub use self::prelude::*;\npub fn f() {}\n", "src/lib.rs")
        assert names == [("f", "fn")]
        assert warnings == ["src/lib.rs line 1: `pub use self::prelude::*` passes on names from a module quick mode "
                            "does not read: pass that module as an entry too, or read it by eye"]


class TestQuickJsForms:
    def test_declaration_forms(self):
        src = (
            "// export const commented = 1;\n"
            "export async function load() {}\n"
            "export let counter = 0;\n"
            "export var legacy = 'it\\'s';\n"
            "export abstract class Base {}\n"
            "export declare const VERSION: string;\n"
            "export declare function declared(): void;\n"
            "export function* gen() {}\n"
            "export function *gen2() {}\n"
            "export default async function main() {}\n"
            "export const enum Color { Red }\n"
            "export declare namespace NS {}\n"
            "export default class extends Base {}\n"
            "export const a = 1, b = f(1, 2), c = { d: 1, e: [2, 3] },\n  g = (x, y) => x;\n"
            "export let h, i: number;\n"
            "export declare const j: Map<string, number>, k: string;\n"
            "export const l = 1\nexport const m = 2\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "src/index.ts")
        # every declarator of a const, let or var statement, never a key or an argument inside it
        assert names == [("load", "function"), ("counter", "let"), ("legacy", "var"), ("Base", "class"),
                         ("VERSION", "const"), ("declared", "function"), ("gen", "function"), ("gen2", "function"),
                         ("main", "function"), ("Color", "enum"), ("NS", "namespace"), ("a", "const"),
                         ("b", "const"), ("c", "const"), ("g", "const"), ("h", "let"), ("i", "let"), ("j", "const"),
                         ("k", "const"), ("l", "const"), ("m", "const")]
        # the anonymous class is the module's default export, which has no name to list
        assert warnings == ["src/index.ts line 13: `export default` is an anonymous function or class: the module's "
                            "default export has no name here"]

    @pytest.mark.parametrize(
        "src,warning",
        [
            pytest.param("export default function () {}\n", "is an anonymous function or class", id="function"),
            pytest.param("export default function* () {}\n", "is an anonymous function or class", id="generator"),
            pytest.param("export default async () => 1;\n", "is an anonymous function or class", id="async-arrow"),
            pytest.param("export default () => 1\n", "is an anonymous function or class", id="arrow"),
            pytest.param("export default { a, b };\n", "is set to an expression", id="object"),
            pytest.param("export default connect(state)(View);\n", "is set to an expression", id="call"),
        ],
    )
    def test_an_anonymous_or_expression_default_is_warned(self, src, warning):
        names, warnings = _scan(mod.scan_exports_js, "const a = 1, b = 2;\n" + src, "src/index.ts")
        assert names == []
        assert len(warnings) == 1 and warnings[0].startswith("src/index.ts line 2: `export default` ")
        assert warning in warnings[0]

    def test_a_destructuring_export_is_warned(self):
        names, warnings = _scan(mod.scan_exports_js, "export const { a, b: c } = obj;\nexport let [x] = pair;\n",
                                "src/index.ts")
        assert names == []
        assert warnings == [
            "src/index.ts line 1: `export const` destructures, and quick mode does not read the names it binds: "
            "read them by eye",
            "src/index.ts line 2: `export let` destructures, and quick mode does not read the names it binds: "
            "read them by eye",
        ]

    @pytest.mark.parametrize(
        "src,names",
        [
            pytest.param("const s = 'x'.replace(/\\/*$/, '');\nexport function b() {}\n", [("b", "function")],
                         id="a-slash-star-in-a-regex"),
            pytest.param("const r = /[/*'\"]/g;\nexport function c() {}\nconst d = a / b / c;\nexport function e() {}\n",
                         [("c", "function"), ("e", "function")], id="a-class-and-division"),
            pytest.param("function f(y) { return /\\/*x/.test(y); }\nexport function g() {}\n", [("g", "function")],
                         id="after-return"),
            pytest.param("const el = <Box x={1} />; // export const fake = 1\nexport function h() {}\n",
                         [("h", "function")], id="a-jsx-self-closing-tag"),
        ],
    )
    def test_a_regular_expression_opens_no_comment_or_string(self, src, names):
        """`/\\/*$/` is a regular expression: read as a `/*`, it hid every
        export up to the next `*/` without a word."""
        assert _scan(mod.scan_exports_js, src, "src/index.ts") == (names, [])

    def test_star_exports_lists_and_the_default_name(self):
        src = (
            "export * from './utils';\n"
            'export * as helpers from "./helpers";\n'
            "export type * from './types';\n"
            "export { a, b as c, type T, default as D } from './x';\n"
            "export type { Shape } from './shapes';\n"
            "function helper() {}\n"
            "export default helper;\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "src/index.ts")
        assert names == [("helpers", "namespace"), ("a", "re-export"), ("c", "re-export"), ("T", "re-export"),
                         ("D", "re-export"), ("Shape", "re-export"), ("helper", "function")]
        assert warnings == [
            "src/index.ts line 1: `export * from './utils'` passes on names from a module quick mode does not read: "
            "pass that module as an entry too, or read it by eye",
            "src/index.ts line 3: `export * from './types'` passes on names from a module quick mode does not read: "
            "pass that module as an entry too, or read it by eye",
        ]

    def test_commonjs_module_exports_object(self):
        src = (
            "'use strict';\n"
            "const util = require('./util');\n"
            "function create(opts) {}\n"
            "class Store {}\n"
            "const VERSION = '1.0';\n"
            "module.exports = {\n"
            "  create,\n  Store,\n  VERSION,\n  'kebab-name': 1,\n"
            "  helper: function () {},\n  arrow: (x) => x,\n  method() {},\n"
            "  get getter() { return 1; },\n  async asyncMethod() {},\n"
            "  nested: { a: 1, b: [1, 2] },\n  [computed]: 2,\n  ...util,\n"
            "};\n"
            "module.exports.extra = class Extra {};\n"
            "exports.more = (a, b) => a + b;\n"
            "exports.__esModule = true;\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "index.js")
        assert names == [("create", "function"), ("Store", "class"), ("VERSION", "const"), ("kebab-name", "variable"),
                         ("helper", "function"), ("arrow", "function"), ("method", "function"),
                         ("getter", "function"), ("asyncMethod", "function"), ("nested", "variable"),
                         ("extra", "class"), ("more", "function")]
        assert warnings == ["index.js line 6: the `module.exports` object's `...util` passes on names from a module "
                            "quick mode does not read: pass that module as an entry too, or read it by eye"]

    @pytest.mark.parametrize(
        "src,names,warning",
        [
            pytest.param("function createApplication() {}\nmodule.exports = createApplication;\n",
                         [("createApplication", "function")], None, id="a-local-name"),
            pytest.param("module.exports = function debounce(fn) {};\n", [("debounce", "function")], None,
                         id="a-named-function"),
            pytest.param("module.exports = class Queue {};\n", [("Queue", "class")], None, id="a-named-class"),
            pytest.param("module.exports = require('./lib/express');\n", [],
                         "`module.exports = require('./lib/express')` passes on names", id="a-require"),
            pytest.param("module.exports = function (req, res) {};\n", [], "is an anonymous function or class",
                         id="an-anonymous-function"),
            pytest.param("module.exports = (x) => x;\n", [], "is an anonymous function or class", id="an-arrow"),
            pytest.param("module.exports = createApp();\n", [], "is set to an expression", id="an-expression"),
        ],
    )
    def test_commonjs_module_exports_value(self, src, names, warning):
        found, warnings = _scan(mod.scan_exports_js, src, "index.js")
        assert found == names
        if warning is None:
            assert warnings == []
        else:
            assert len(warnings) == 1 and warning in warnings[0] and warnings[0].startswith("index.js line ")

    def test_express_exports_its_application_function(self):
        """Express's lib/express.js line 27 sets the package's one function
        export through `exports = module.exports = ...`."""
        src = (
            "var proto = require('./application');\n"
            "var req = require('./request');\n"
            "exports = module.exports = createApplication;\n"
            "function createApplication() {\n  var app = function(req, res, next) {};\n  return app;\n}\n"
            "exports.application = proto;\n"
            "exports.request = req;\n"
            "module.exports = exports = createApplication;\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "lib/express.js")
        assert names == [("createApplication", "function"), ("application", "var"), ("request", "var")]
        assert warnings == []

    @pytest.mark.parametrize(
        "src,lines",
        [
            pytest.param("'use strict';\n\nif (process.env.NODE_ENV === 'production') {\n"
                         "  module.exports = require('./cjs/react.production.js');\n} else {\n"
                         "  module.exports = require('./cjs/react.development.js');\n}\n",
                         {4: "./cjs/react.production.js", 6: "./cjs/react.development.js"}, id="react-npm-index"),
            pytest.param("/**\n * Detect Electron renderer\n */\n\nif (typeof process === 'undefined') {\n"
                         "\tmodule.exports = require('./browser.js');\n} else {\n"
                         "\tmodule.exports = require('./node.js');\n}\n",
                         {6: "./browser.js", 8: "./node.js"}, id="debug-src-index"),
        ],
    )
    def test_a_module_exports_in_a_branch_is_warned(self, src, lines):
        """React's packages/react/npm/index.js and debug's src/index.js pick
        their export in an if/else: each branch is named, not dropped."""
        names, warnings = _scan(mod.scan_exports_js, src, "index.js")
        assert names == []
        assert warnings == [
            f"index.js line {line}: `module.exports = require('{spec}')` passes on names from a module quick mode "
            "does not read: pass that module as an entry too, or read it by eye"
            for line, spec in lines.items()
        ]

    def test_an_assignment_in_a_block_is_warned(self):
        src = (
            "(function (root, factory) {\n"
            "  if (typeof module === 'object' && module.exports) {\n"
            "    exports = module.exports = factory();\n"
            "  }\n"
            "}(this, function () { return {}; }));\n"
            "if (debug) exports.trace = trace;\n"
            "module.exports.version = '1.0';\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "umd.js")
        assert names == [("version", "variable")]
        assert warnings == [
            "umd.js line 3: `exports` is assigned inside a block or a condition: read the names it exports by eye",
            "umd.js line 6: `exports.trace` is assigned inside a block or a condition: read the names it exports by eye",
        ]

    def test_typescript_commonjs_output_lists_its_export_chain(self):
        """tsc's CommonJS output names every export in the chain it opens
        with: no name of it is warned as nested, or dropped."""
        src = (
            '"use strict";\n'
            'Object.defineProperty(exports, "__esModule", { value: true });\n'
            "exports.parse = exports.stringify = exports.VERSION = void 0;\n"
            'var x_1 = require("./x");\n'
            'Object.defineProperty(exports, "stringify", { enumerable: true, get: function () { return x_1.stringify; } });\n'
            "function parse() {}\n"
            "exports.parse = parse;\n"
        )
        names, warnings = _scan(mod.scan_exports_js, src, "dist/index.js")
        assert names == [("parse", "variable"), ("stringify", "variable"), ("VERSION", "variable")]
        assert warnings == []

    @pytest.mark.parametrize(
        "src,names,warning",
        [
            pytest.param("declare class Client {}\nexport = Client;\n", [("Client", "class")], None, id="a-name"),
            pytest.param("export = { parse, stringify };\nfunction parse() {}\n",
                         [("parse", "function"), ("stringify", "variable")], None, id="an-object"),
            pytest.param("export = function () {};\n", [], "`export =` is an anonymous function or class",
                         id="anonymous"),
        ],
    )
    def test_typescript_export_assignment(self, src, names, warning):
        found, warnings = _scan(mod.scan_exports_js, src, "index.d.ts")
        assert found == names
        assert warnings == ([] if warning is None else [warnings[0]])
        if warning is not None:
            assert warning in warnings[0]

    def test_the_forms_reach_the_envelope_warnings(self):
        result = mod.extract({"language": "ts", "manifest": {"path": "package.json", "content": '{"name": "x"}'},
                              "entries": [{"path": "src/index.ts", "content": "export * from './a';\n"}]})
        assert result["exports"] == []
        assert any("`export * from './a'`" in w for w in result["warnings"])


# --------------------------------------------------------------------------
# Quick mode: --manifest-file and --entry-file (#592)
# --------------------------------------------------------------------------

RUST_LIB = (
    "//! This skill's crate: lifetimes like 'a and \"quotes\" stay as they are.\n"
    "pub fn parse<'a>(input: &'a str) -> &'a str { input }\n"
    "pub use crate::inner::{Token, Span as Range};\n"
)
CARGO = '[package]\nname = "demo"\nversion = "0.3.0"\ndescription = "it\'s a demo"\n[dependencies]\nserde = "1"\n'


def _stage(root: Path, files: dict[str, str | bytes]) -> Path:
    """Write `files` under `root` as bytes, a folder laid out like the repository."""
    for rel, content in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return root


def _quick(capsys, *argv: str) -> tuple[int, dict | None]:
    code = mod.main(["--mode", "quick", *argv])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


class TestQuickFiles:
    def test_the_files_give_what_the_payload_gives(self, tmp_path, capsys, monkeypatch):
        root = _stage(tmp_path / "staged", {"Cargo.toml": CARGO, "src/lib.rs": RUST_LIB})
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # never read
        code, from_files = _quick(capsys, "--language", "rust", "--source-root", str(root),
                                  "--manifest-file", "Cargo.toml", "--entry-file", "src/lib.rs")
        assert code == 0
        from_payload = mod.extract({"language": "rust", "manifest": {"path": "Cargo.toml", "content": CARGO},
                                    "entries": [{"path": "src/lib.rs", "content": RUST_LIB}], "mode": "quick"})
        assert from_files == from_payload
        assert (from_files["package_name"], from_files["description"], from_files["dependencies"]) == (
            "demo", "it's a demo", ["serde"])
        assert [(e["name"], e["source_file"]) for e in from_files["exports"]] == [
            ("parse", "src/lib.rs"), ("Token", "src/lib.rs"), ("Range", "src/lib.rs")]

    def test_a_source_file_with_an_apostrophe_reaches_the_parser_unchanged(self, tmp_path):
        """The bytes on disk are the text the parser reads: no shell string
        or JSON escaping stands between them."""
        js = "export const greeting = 'it\\'s';\nexport function say(msg = \"don't\") {}\n"
        py = 'def run():\n    """This skill\'s entry point."""\n'
        root = _stage(tmp_path / "staged", {"src/lib.rs": RUST_LIB, "index.js": js, "pkg/__init__.py": py})
        args = argparse.Namespace(source_root=str(root), manifest_file=None, language=["rust"],
                                  entry_file=["src/lib.rs", "./index.js", "pkg/__init__.py", "src/lib.rs"])
        payload = mod._quick_files_payload(args)
        # each path as given, written with /, and each file read once
        assert [(e["path"], e["content"]) for e in payload["entries"]] == [
            ("src/lib.rs", RUST_LIB), ("index.js", js), ("pkg/__init__.py", py)]
        assert payload["manifest"] == {"path": "", "content": ""}
        assert [e["name"] for e in mod.scan_exports_js(js, "index.js")] == ["greeting", "say"]
        assert [e["name"] for e in mod.scan_exports_python(py, "pkg/__init__.py")] == ["run"]

    def test_without_source_root_the_paths_are_read_as_given(self, tmp_path, capsys, monkeypatch):
        _stage(tmp_path, {"pyproject.toml": '[project]\nname = "foo"\nversion = "1.0"\n',
                          "foo/__init__.py": "def hello(): pass\n"})
        monkeypatch.chdir(tmp_path)
        code, out = _quick(capsys, "--language", "python", "--manifest-file", "pyproject.toml",
                           "--entry-file", "foo/__init__.py")
        assert code == 0
        assert (out["package_name"], out["exports"]) == (
            "foo", [{"name": "hello", "type": "def", "source_file": "foo/__init__.py"}])

    def test_a_byte_order_mark_goes_and_a_bad_byte_is_replaced(self, tmp_path, capsys):
        root = _stage(tmp_path, {"package.json": b'\xef\xbb\xbf{"name": "bom"}',
                                 "index.js": b"export const ok = 'caf\xe9';\n"})
        code, out = _quick(capsys, "--language", "js", "--source-root", str(root),
                           "--manifest-file", "package.json", "--entry-file", "index.js")
        assert (code, out["package_name"], [e["name"] for e in out["exports"]]) == (0, "bom", ["ok"])
        args = argparse.Namespace(source_root=str(root), manifest_file="package.json", language=["js"],
                                  entry_file=["index.js"])
        payload = mod._quick_files_payload(args)
        assert payload["manifest"]["content"] == '{"name": "bom"}'
        assert payload["entries"][0]["content"] == "export const ok = 'caf\ufffd';\n"

    def test_an_entry_alone_needs_no_manifest(self, tmp_path, capsys):
        root = _stage(tmp_path, {"lib.go": "package demo\n\nfunc Run() {}\n"})
        code, out = _quick(capsys, "--language", "go", "--source-root", str(root), "--entry-file", "lib.go")
        assert code == 0
        assert out["exports"] == [{"name": "Run", "type": "func", "source_file": "lib.go"}]
        assert any("no manifest content" in w for w in out["warnings"])

    @pytest.mark.parametrize(
        "argv,message",
        [
            pytest.param(["--entry-file", "src/lib.rs"], "take one --language", id="no-language"),
            pytest.param(["--language", "rust", "--language", "go", "--entry-file", "src/lib.rs"],
                         "take one --language", id="two-languages"),
        ],
    )
    def test_the_file_inputs_take_one_language(self, argv, message, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "quick", *argv])
        assert exc.value.code == 2
        assert message in capsys.readouterr().err

    @pytest.mark.parametrize(
        "flag,value,message",
        [
            pytest.param("--entry-file", "missing.rs", "cannot read --entry-file missing.rs", id="missing"),
            pytest.param("--entry-file", "src", "cannot read --entry-file src", id="a-folder"),
            pytest.param("--entry-file", "../outside.rs", "leads outside --source-root", id="outside"),
            pytest.param("--manifest-file", "ABSOLUTE", "must be relative to --source-root", id="absolute"),
        ],
    )
    def test_a_file_that_cannot_be_read_exits_2(self, tmp_path, capsys, flag, value, message):
        root = _stage(tmp_path / "staged", {"src/lib.rs": "pub fn f() {}\n"})
        _stage(tmp_path, {"outside.rs": "pub fn g() {}\n"})
        if value == "ABSOLUTE":
            value = (root / "src" / "lib.rs").as_posix()
        code = mod.main(["--mode", "quick", "--language", "rust", "--source-root", str(root), flag, value])
        captured = capsys.readouterr()
        assert (code, captured.out) == (2, "")
        assert message in captured.err

    def test_a_source_root_that_is_no_folder_exits_2(self, tmp_path, capsys):
        code = mod.main(["--mode", "quick", "--language", "rust", "--source-root", str(tmp_path / "absent"),
                         "--entry-file", "src/lib.rs"])
        assert code == 2 and "--source-root is not a folder" in capsys.readouterr().err

    def test_an_unknown_language_exits_1(self, tmp_path, capsys):
        root = _stage(tmp_path, {"main.f90": "program x\nend program x\n"})
        code, out = _quick(capsys, "--language", "fortran", "--source-root", str(root), "--entry-file", "main.f90")
        assert code == 1 and "unknown language" in out["_error"]

    def test_quick_file_flags_are_quick_mode_only(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "full", "--source-root", ".", "--entry-file", "a.py"])
        assert exc.value.code == 2
        assert "quick mode only" in capsys.readouterr().err

    def test_source_root_and_language_need_the_file_inputs_in_quick_mode(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--language", "rust"])
        assert exc.value.code == 2
        assert "--manifest-file or --entry-file" in capsys.readouterr().err

    def test_the_cli_reads_the_files(self, tmp_path):
        root = _stage(tmp_path / "staged", {"Cargo.toml": CARGO, "src/lib.rs": RUST_LIB})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "quick", "--language", "rust", "--source-root", str(root),
             "--manifest-file", "Cargo.toml", "--entry-file", "src/lib.rs"],
            capture_output=True, text=True, encoding="utf-8", timeout=60, stdin=subprocess.DEVNULL,
        )
        assert proc.returncode == 0, proc.stderr
        assert [e["name"] for e in json.loads(proc.stdout)["exports"]] == ["parse", "Token", "Range"]


# --------------------------------------------------------------------------
# Full mode: shared helpers and source trees
# --------------------------------------------------------------------------


def _pinned_ast_grep() -> bool:
    """True when the ast-grep on PATH is the version package.json's
    test:python pins."""
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


needs_ast_grep = pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")


def _tree(root: Path, files: dict[str, str | bytes]) -> Path:
    """Write `files` under `root` as bytes, so they keep LF line ends on Windows."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return root


def _full(capsys, root: Path, *flags: str) -> tuple[int, dict | None]:
    code = mod.main(["--mode", "full", "--source-root", str(root), *flags])
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


@pytest.fixture
def no_ast_grep(monkeypatch):
    """Full mode on a machine with no ast-grep: it stops before any scan,
    with the files in scope worked out (exit 3)."""
    monkeypatch.setattr(mod, "_ast_grep", lambda: (None, None, None))


# A package with an exports map: a root barrel built to dist/ (so traced to
# its source), a committed .d.mts outside src/, a build-output subpath, a
# metadata subpath and a wildcard one; named, aliased, star, namespace and
# imported re-exports, a default export of an imported binding, and the
# `export let` / `export declare const` forms no recipe matches.
TS_PACKAGE = {
    "package.json": json.dumps({
        "name": "demo",
        "exports": {
            ".": {"types": "./dist/index.d.ts", "import": "./dist/index.mjs"},
            "./macro": {"types": "./macro/index.d.mts"},
            "./utils": "./dist/utils/index.js",
            "./package.json": "./package.json",
            "./features/*": "./dist/features/*.js",
        },
    }),
    "src/index.ts": (
        "import { Helper as H2 } from './utils/helper';\n"
        "import Def from './def';\n"
        "export { format, parse as parseValue } from './utils/format';\n"
        "export * from './shapes';\n"
        "export * as internals from './internal/impl';\n"
        "export { H2 };\n"
        'export const VERSION = "1.0";\n'
        "export let mutable = 1;\n"
        "export declare const declared: number;\n"
        "export default Def;\n"
    ),
    "src/utils/format.ts": (
        "export function format(v: string): string { return v; }\n"
        "export function parse(v: string): number { return 1; }\n"
        "export function unused() {}\n"
    ),
    "src/utils/helper.ts": "export class Helper {}\n",
    "src/utils/index.ts": "export { format } from './format';\n",
    "src/def.ts": "export default function def() {}\n",
    "src/shapes.ts": (
        "export interface Shape { area(): number }\n"
        'export type Kind = "a" | "b";\n'
        "export const makeShape = () => ({});\n"
        "export default class Ignored {}\n"
    ),
    "src/internal/impl.ts": "export function secret() {}\n",
    "macro/index.d.mts": (
        "export declare function macro(): void;\n"
        "export interface MacroOptions { x: number }\n"
    ),
}

# A Python package (an __init__ with imports, a star import, a submodule, a
# name imported under TYPE_CHECKING, which is no attribute at run time) and
# one with __all__; a crate whose lib.rs has
# pub mods, pub use items (aliased, grouped, glob, from another crate) and
# restricted items; a Go package with grouped declarations, a test file
# and an internal/ package.
POLYGLOT = {
    "src/mypkg/__init__.py": (
        '"""Package docs."""\n'
        "from .core import Engine, run as start\n"
        "from . import sub\n"
        "from .helpers import *\n"
        "from typing import TYPE_CHECKING\n"
        "import os\n"
        "\n"
        'VERSION = "1.0"\n'
        "\n"
        "def configure():\n"
        "    pass\n"
        "\n"
        "def _private():\n"
        "    pass\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    from .types import Hint\n"
    ),
    "src/mypkg/core.py": (
        "class Engine:\n"
        "    def method(self):\n"
        "        pass\n"
        "\n"
        "def run():\n"
        "    pass\n"
        "\n"
        "def internal_helper():\n"
        "    pass\n"
    ),
    "src/mypkg/helpers.py": '__all__ = ["helper_a"]\n\ndef helper_a():\n    pass\n\ndef helper_b():\n    pass\n',
    "src/mypkg/sub/__init__.py": "def sub_fn():\n    pass\n",
    "src/mypkg/types.py": "class Hint:\n    pass\n",
    "src/other/__init__.py": '__all__ = ["Alpha", "missing_name", "beta"]\nfrom .alpha import Alpha\n',
    "src/other/alpha.py": "class Alpha:\n    pass\n",
    "src/other/beta.py": "x = 1\n",
    "crate/Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\n',
    "crate/src/lib.rs": (
        "//! Crate docs. pub fn not_real() {}\n"
        "pub mod client;\n"
        "mod error;\n"
        "mod util;\n"
        "pub use client::Client;\n"
        "pub use error::{Error, Result as DemoResult};\n"
        "pub use util::*;\n"
        "pub use serde::Serialize;\n"
        "pub(crate) use util::hidden;\n"
        "pub fn top_level() -> u32 { 1 }\n"
        "pub const LIMIT: u32 = 5;\n"
        "pub(crate) fn crate_only() {}\n"
        "/* pub fn in_block() {} */\n"
    ),
    "crate/src/client/mod.rs": (
        "pub struct Client;\n"
        "pub struct Builder;\n"
        "impl Client { pub fn new() -> Self { Client } }\n"
    ),
    "crate/src/error.rs": "pub enum Error { A }\npub type Result<T> = std::result::Result<T, Error>;\n",
    "crate/src/util.rs": "pub fn util_fn() {}\npub(crate) fn hidden() {}\n",
    "gopkg/api.go": (
        "package gopkg\n"
        "\n"
        "// func Commented() {}\n"
        "var raw = `\n"
        "func InRaw() {}\n"
        "`\n"
        "\n"
        "func Exported() {}\n"
        "func (r *T) Method() {}\n"
        "func unexported() {}\n"
        "\n"
        "type T struct{}\n"
        "\n"
        "const (\n"
        "\tA = iota\n"
        "\tb\n"
        "\tC, D = 1, 2\n"
        ")\n"
        "\n"
        "var (\n"
        "\tDefault = New(\n"
        "\t\tOption,\n"
        "\t)\n"
        ")\n"
        "\n"
        "func New(o int) int { return o }\n"
    ),
    "gopkg/api_test.go": "package gopkg\nfunc TestX() {}\n",
    "gopkg/internal/x/x.go": "package x\nfunc Hidden() {}\n",
}

# A Rush monorepo: rush.json is JSON with comments and trailing commas.
RUSH_MONOREPO = {
    "rush.json": (
        "{\n"
        "  // the projects\n"
        '  "rushVersion": "5.0.0",\n'
        '  "projects": [\n'
        '    { "packageName": "@acme/a", "projectFolder": "libs/a" },\n'
        '    { "packageName": "@acme/b", "projectFolder": "apps/b", },\n'
        "  ],\n"
        "}\n"
    ),
    "libs/a/package.json": json.dumps({
        "name": "@acme/a",
        "exports": {".": "./src/index.ts", "./x": "./src/x.ts", "./y": "./src/y.ts"},
    }),
    "libs/a/src/index.ts": "export const a = 1;\n",
    "libs/a/src/x.ts": "export const x = 1;\n",
    "libs/a/src/y.ts": "export const y = 1;\n",
    "apps/b/package.json": json.dumps({"name": "@acme/b"}),
}


# Chains more than one hop from the barrel: `export *` through two modules
# (and on to another package), a named re-export through an aliased list of
# an imported binding, and a namespace export whose module passes its
# names on through `export *`.
JS_CHAINS = {
    "package.json": json.dumps({"name": "ui"}),
    "src/index.ts": "export * from './components';\nexport * as icons from './icons';\nexport function top() {}\n",
    "src/components/index.ts": (
        "export * from './button';\n"
        "export { Card as Tile } from './card';\n"
        "export * from 'external-pkg';\n"
    ),
    "src/components/button/index.ts": "export function Button() {}\nexport const buttonVariants = 1;\n",
    "src/components/card.ts": "import { Inner } from './inner';\nexport { Inner as Card };\n",
    "src/components/inner.ts": "export class Inner {}\n",
    "src/icons/index.ts": "export * from './set';\n",
    "src/icons/set.ts": "export const Star = 1;\n",
}

# Pattern subpaths: a build output traced back to its sources, one a `null`
# target takes out, and committed files matched as they are.
JS_WILDCARDS = {
    "package.json": json.dumps({"name": "ui", "exports": {
        ".": "./src/index.ts",
        "./components/*": {"types": "./dist/components/*.d.ts", "import": "./dist/components/*.js"},
        "./components/internal/*": None,
        "./locale/*": "./locale/*.js",
        "./gone/*": "./dist/gone/*.js",
    }}),
    "src/index.ts": "export const VERSION = 1;\n",
    "src/components/button.ts": "export function Button() {}\n",
    "src/components/internal/secret.ts": "export function secret() {}\n",
    "locale/en.js": "export const en = {};\n",
}

# Star imports through two modules (and one that names no file), and a
# submodule a star-imported module imports; imports from other packages
# and private names stay out.
PY_CHAINS = {
    "mypkg/__init__.py": "from .core import *\nfrom .missing import *\n\ndef configure():\n    pass\n",
    "mypkg/core/__init__.py": "from .engine import *\nfrom . import tools\n",
    "mypkg/core/engine.py": "import json\nfrom typing import Any\n\ndef run():\n    pass\n\ndef _hidden():\n    pass\n",
    "mypkg/core/tools.py": "def tool():\n    pass\n",
}

# A `pub mod` chain two modules deep, with a `pub use` of a private module's
# item, an inline `pub mod`, and a `#[path]` module the trace cannot follow;
# a glob whose module globs another.
RUST_CHAINS = {
    "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\n',
    "src/lib.rs": "pub mod client;\nmod util;\npub use util::*;\n",
    "src/client/mod.rs": (
        "pub mod builder;\n"
        "mod private;\n"
        "pub use private::helper;\n"
        '#[path = "weird/place.rs"]\n'
        "pub mod odd;\n"
        "pub mod inline {\n"
        "    pub fn nested() {}\n"
        "}\n"
    ),
    "src/client/builder.rs": "pub fn build() {}\n",
    "src/client/private.rs": "pub fn helper() {}\npub fn unexported() {}\n",
    "src/client/weird/place.rs": "pub fn odd_fn() {}\n",
    "src/util.rs": "pub use self::more::*;\nmod more;\n",
    "src/util/more.rs": "pub fn deep() {}\n",
}

# Local export lists naming each kind of top-level binding (#559): an item
# takes the type of what it names.
LOCAL_LISTS = {
    "src/button.tsx": (
        'import { cva } from "cva"\n'
        'import * as Radix from "radix"\n'
        'const buttonVariants = cva("x")\n'
        "const Button = React.forwardRef((p, r) => null)\n"
        "const Icon = () => null\n"
        "function Card() { return null }\n"
        "interface DialogProps { open: boolean }\n"
        'type Size = "sm"\n'
        "enum Tone { A }\n"
        "class Store {}\n"
        "const { picked } = obj\n"
        "export { buttonVariants, Button, Icon, Card, Store, picked, cva, Radix }\n"
        "export type { DialogProps, Size }\n"
        "export { Tone as default }\n"
    ),
}


def _names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items]


# --------------------------------------------------------------------------
# Full mode: which files
# --------------------------------------------------------------------------


class TestGlobRules:
    @pytest.mark.parametrize(
        ("path", "pattern", "matches"),
        [
            ("src/index.ts", "src/**/*.ts", True),
            ("src/a/b/c.ts", "src/**/*.ts", True),
            ("test_x.py", "**/test_*", True),
            ("pkg/test_x.py", "**/test_*", True),
            ("src", "src/**", False),
            ("src/x", "src/**", True),
            ("a/b.ts", "*.ts", False),
            ("b.ts", "*.ts", True),
            ("a/b.ts", "a/?.ts", True),
        ],
        ids=lambda value: str(value),
    )
    def test_the_runner_matches_as_resolve_authoritative_files_does(self, path, pattern, matches) -> None:
        resolver_spec = importlib.util.spec_from_file_location(
            "skf_resolve_authoritative_files_test", SCRIPTS / "skf-resolve-authoritative-files.py")
        resolver = importlib.util.module_from_spec(resolver_spec)
        resolver_spec.loader.exec_module(resolver)
        runner_match = mod._sibling("skf-resolve-authoritative-files.py").glob_match
        assert runner_match(path, pattern) is resolver.glob_match(path, pattern) is matches

    def test_double_star_matches_a_file_right_under_it(self, tmp_path, capsys, no_ast_grep) -> None:
        # the #584 acceptance case: src/**/*.ts matches src/index.ts
        root = _tree(tmp_path, {"src/index.ts": "", "src/a/b/c.ts": "", "lib/x.ts": ""})
        code, out = _full(capsys, root, "--include", "src/**/*.ts")
        assert (code, out["status"], out["files_in_scope"]) == (3, "no-ast-grep", 2)

    def test_test_prefix_glob_drops_a_top_level_file(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"test_foo.py": "", "pkg/test_bar.py": "", "pkg/mod.py": ""})
        _, out = _full(capsys, root, "--exclude", "**/test_*")
        assert out["files_in_scope"] == 1

    def test_patterns_are_normalised_and_unmatched_ones_warn(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"src/a.ts": "", "src/b.ts": ""})
        _, out = _full(capsys, root, "--include", "./src/**", "--include", "docs/**", "--exclude", "src\\b.ts")
        assert out["files_in_scope"] == 1
        assert out["scope"]["include"] == ["src/**", "docs/**"] and out["scope"]["exclude"] == ["src/b.ts"]
        assert "scope.include pattern 'docs/**' matches no file" in out["warnings"]


class TestFileSelection:
    @pytest.mark.skipif(shutil.which("git") is None, reason="no git")
    def test_a_git_work_tree_lists_what_git_does(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path / "repo", {".gitignore": "ignored.ts\nbuild/\n", "a.ts": "", "ignored.ts": "",
                                         "build/out.ts": "", ".hidden/h.ts": ""})
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        _, out = _full(capsys, root)
        assert out["files_in_scope"] == 1

    @pytest.mark.skipif(shutil.which("git") is None, reason="no git")
    def test_a_folder_the_work_tree_ignores_is_walked(self, tmp_path, capsys, no_ast_grep) -> None:
        repo = _tree(tmp_path / "repo", {".gitignore": "vendor/\n", "vendor/lib/a.py": "", "vendor/lib/b.py": ""})
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        _, out = _full(capsys, repo / "vendor" / "lib")
        assert out["files_in_scope"] == 2

    def test_elsewhere_every_file_but_hidden_ones(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"a.ts": "", ".hidden/b.ts": "", ".c.ts": "", "node_modules/x/y.ts": ""})
        _, out = _full(capsys, root)
        assert out["files_in_scope"] == 2

    def test_symbolic_links_are_left_out(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path / "root", {"a.ts": ""})
        outside = _tree(tmp_path / "outside", {"b.ts": ""})
        try:
            os.symlink(outside / "b.ts", root / "link.ts")
            os.symlink(outside, root / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("no symbolic links here")
        _, out = _full(capsys, root)
        assert out["files_in_scope"] == 1

    @pytest.mark.parametrize("form", ["lines", "json"])
    def test_files_from_lists_the_files_to_read(self, form, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path / "root", {"a.ts": "", "b.py": "", "notes.md": "", "c.ts": ""})
        listed = ["a.ts", "./b.py", "gone.ts", "notes.md", "a.ts"]
        text = json.dumps(listed) if form == "json" else "\n".join(listed) + "\n"
        list_file = _tree(tmp_path, {"list.txt": text}) / "list.txt"
        _, out = _full(capsys, root, "--files-from", str(list_file))
        assert out["files_in_scope"] == 2
        assert out["file_issues"] == [{"file": "gone.ts", "issue": "missing"},
                                      {"file": "notes.md", "issue": "no-recipes"}]

    @pytest.mark.parametrize(
        ("text", "issues"),
        [("[slug]/page.tsx\nb.ts\n", []),
         ('["a.ts", 1]\n', [{"file": '["a.ts", 1]', "issue": "missing"}]),
         ('["[slug]/page.tsx", "b.ts"]', [])],
        ids=["bracket-path-first", "json-of-non-paths", "json-list"],
    )
    def test_a_list_is_json_only_when_the_whole_file_is_a_list_of_paths(self, text, issues, tmp_path, capsys,
                                                                           no_ast_grep) -> None:
        """A Next.js route folder such as `[slug]/` opens a line with `[`: the
        file is read one path per line unless all of it parses as a JSON
        list of strings, so the list never stops the run (exit 2)."""
        root = _tree(tmp_path / "root", {"[slug]/page.tsx": "", "b.ts": "", "a.ts": ""})
        list_file = _tree(tmp_path, {"list.txt": text}) / "list.txt"
        code, out = _full(capsys, root, "--files-from", str(list_file))
        assert code == 3 and out["file_issues"] == issues
        assert out["files_in_scope"] == (0 if issues else 2)

    @pytest.mark.parametrize(
        ("language", "count"),
        [("typescript", 4), ("js", 4), ("python", 1), ("rust", 1), ("go", 1)],
    )
    def test_language_selects_a_family(self, language, count, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"a.ts": "", "b.tsx": "", "c.js": "", "d.vue": "", "e.py": "", "f.rs": "", "g.go": ""})
        _, out = _full(capsys, root, "--language", language)
        assert out["files_in_scope"] == count

    def test_a_language_no_recipe_reads(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"A.java": "", "b.kt": "", "c.md": "", "d.ts": ""})
        _, out = _full(capsys, root, "--language", "java")
        assert out["files_in_scope"] == 0
        assert "no recipe reads java files" in out["warnings"]
        _, out = _full(capsys, root)
        assert out["files_without_recipes"] == {".java": 1, ".kt": 1}

    def test_the_brief_supplies_the_scope_and_flags_replace_it(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path / "root", {"src/core/a.py": "", "src/gen/b.py": "", "src/c.py": "", "src/d.ts": ""})
        brief = _tree(tmp_path, {"skill-brief.yaml": (
            "name: demo\nlanguage: python\nscope:\n  type: specific-modules\n"
            "  include: ['src/**']\n  exclude: ['src/gen/**']\n  tier_a_include: ['src/core/**']\n"
            "  notes: tiered\n")}) / "skill-brief.yaml"
        _, out = _full(capsys, root, "--brief", str(brief))
        assert out["scope"] == {"include": ["src/**"], "exclude": ["src/gen/**"], "tier_a_include": ["src/core/**"],
                                "type": "specific-modules", "languages": ["python"], "files_from": None}
        assert out["files_in_scope"] == 2
        _, out = _full(capsys, root, "--brief", str(brief), "--include", "src/core/**", "--language", "ts")
        assert out["files_in_scope"] == 0 and out["scope"]["include"] == ["src/core/**"]

    def test_a_file_ast_grep_skips_is_an_issue(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"ok.ts": "export const a = 1;\n", "latin.ts": b"export const b = '\xe9';\n"})
        _, out = _full(capsys, root)
        assert out["files_in_scope"] == 2
        assert out["file_issues"] == [{"file": "latin.ts", "issue": "not-utf8"}]


# --------------------------------------------------------------------------
# Full mode: the recipe file and the merge
# --------------------------------------------------------------------------


class TestRecipeFile:
    def test_the_data_file_loads(self) -> None:
        recipes = mod.load_recipe_file(DATA_FILE)
        assert len(recipes) == 20
        ids = {r["id"] for r in recipes}
        assert {"js-local-exports", "ts-exported-types", "react-wrapped-components"} <= ids
        assert all(set(r["metadata"]["sets"]) <= set(mod.RECIPE_SETS) for r in recipes)

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("id: a\nlanguage: python\nrule:\n  kind: function_definition\n", "a: no metadata"),
            ("id: a\nlanguage: cobol\nrule:\n  kind: x\nmetadata: {}\n", "a language the runner does not know"),
            ("id: a\nlanguage: python\nrule:\n  kind: function_definition\nmetadata:\n  languages: [go]\n"
             "  sets: [standard]\n  export_type: function\n", "must list its own language first"),
            ("id: a\nlanguage: python\nrule:\n  kind: function_definition\nmetadata:\n  languages: [python]\n"
             "  sets: [other]\n  export_type: function\n", "metadata.sets"),
            ("id: a\nlanguage: python\nrule:\n  kind: function_definition\nmetadata:\n  languages: [python]\n"
             "  sets: [standard]\n  export_type: method\n", "metadata.export_type"),
            ("id: a\nlanguage: python\nrule:\n  kind: k\nmetadata:\n  languages: [python]\n  sets: [standard]\n"
             "  export_type: function\n---\nid: a\nlanguage: python\nrule:\n  kind: k\nmetadata:\n"
             "  languages: [python]\n  sets: [standard]\n  export_type: function\n", "runs in python twice"),
            ("id: [\n", "malformed YAML"),
            ("", "no recipe in"),
        ],
        ids=["no-metadata", "language", "languages", "sets", "export-type", "twice", "malformed", "empty"],
    )
    def test_a_bad_recipe_file_is_refused(self, content, message, tmp_path, capsys) -> None:
        recipes = _tree(tmp_path, {"recipes.yaml": content}) / "recipes.yaml"
        root = _tree(tmp_path / "root", {"a.py": ""})
        code = mod.main(["--mode", "full", "--source-root", str(root), "--recipes", str(recipes)])
        captured = capsys.readouterr()
        assert (code, captured.out) == (2, "")
        assert message in captured.err


class TestMerge:
    RECIPES = mod.load_recipe_file(DATA_FILE)

    @staticmethod
    def _match(rule: str, file: str, line: int, name: str, language: str = "typescript",
               text: str | None = None) -> dict:
        return {"rule": rule, "language": language, "file": file, "line": line, "start_line": line,
                "name": name, "source": None, "signature_line": text or name, "signature": text or name,
                "text": text or name}

    def test_first_line_then_the_preferred_recipe(self) -> None:
        m = self._match
        matches = [m("js-exported-constants", "a.ts", 3, "f"), m("js-exported-arrow-functions", "a.ts", 3, "f"),
                   m("js-exported-functions", "a.ts", 9, "f"), m("js-exported-constants", "b.ts", 1, "f")]
        exports, stats = mod.merge_exports(matches, self.RECIPES, "standard", None)
        assert [(e["source_file"], e["source_line"], e["export_name"], e["ast_recipe"], e["export_type"])
                for e in exports] == [("a.ts", 3, "f", "js-exported-arrow-functions", "function"),
                                      ("b.ts", 1, "f", "js-exported-constants", "const")]
        assert exports[0]["citation"] == "[AST:a.ts:L3]" and exports[0]["confidence"] == "T1"
        assert {s["id"]: s["matches"] for s in stats}["js-exported-constants"] == 2

    def test_private_names_and_the_head_cap(self) -> None:
        m = self._match
        matches = [m("js-exported-constants", "a.ts", n, name) for n, name in enumerate(["_p", "c", "a", "b"], 1)]
        exports, stats = mod.merge_exports(matches, self.RECIPES, "standard", 2)
        assert [e["export_name"] for e in exports] == ["c", "a"]
        (stat,) = [s for s in stats if s["id"] == "js-exported-constants"]
        assert (stat["matches"], stat["truncated"]) == (3, True)

    def test_other_recipe_sets_are_left_out(self) -> None:
        matches = [self._match("react-props-interfaces", "a.ts", 1, "XProps")]
        exports, stats = mod.merge_exports(matches, self.RECIPES, "standard", None)
        assert exports == [] and "react-props-interfaces" not in {s["id"] for s in stats}

    @pytest.mark.parametrize(
        ("text", "name", "kind"),
        [("export declare const enum E { A }", "E", "enum"), ("export interface\n  I {}", "I", "interface"),
         ("export type T = 1", "T", "type"), ("export /* type */ interface J {}", "J", "interface")],
    )
    def test_the_keyword_picks_the_type(self, text, name, kind) -> None:
        exports, _ = mod.merge_exports([self._match("ts-exported-types", "t.ts", 1, name, text=text)],
                                       self.RECIPES, "standard", None)
        assert exports[0]["export_type"] == kind

    def test_a_match_cites_the_name_line(self) -> None:
        raw = {"text": "@dec\nexport class C {}", "file": ".\\src\\c.ts", "ruleId": "js-exported-classes",
               "language": "TypeScript", "range": {"start": {"line": 4}},
               "metaVariables": {"single": {"NAME": {"text": "C", "range": {"start": {"line": 5}}}}}}
        match = mod._parse_match(raw)
        assert (match["file"], match["line"], match["start_line"], match["signature_line"]) == (
            "src/c.ts", 6, 5, "export class C {}")
        assert mod._parse_match({"text": "x"}) is None
        # a list item matches its specifier alone; `lines` gives the whole line
        item = {"text": "Button", "lines": "export { Button,", "file": "b.tsx", "ruleId": "js-local-exports",
                "language": "Tsx", "range": {"start": {"line": 9}},
                "metaVariables": {"single": {"NAME": {"text": "Button", "range": {"start": {"line": 9}}}}}}
        assert mod._parse_match(item)["signature_line"] == "export { Button,"

    @pytest.mark.parametrize(
        ("lines", "language", "signature"),
        [
            ("@dec\ndef f(\n    a: int,  # the (\n    b: str = \"(\",\n) -> dict[str, int]:\n    return {}",
             "Python", 'def f(a: int, b: str = "(") -> dict[str, int]:'),
            ("export function g(\n  a: string,\n  b?: Opts,\n): Promise<void> {\n}", "TypeScript",
             "export function g(a: string, b?: Opts): Promise<void> {"),
            ("pub fn h<'a>(\n    x: &'a str,\n) -> u32 {\n    1\n}", "Rust", "pub fn h<'a>(x: &'a str) -> u32 {"),
            ("func New(\n\to int,\n) (int, error) {\n}", "Go", "func New(o int) (int, error) {"),
            ("class A(Base):  # one line\n    pass", "Python", "class A(Base):"),
            ("export const C = ({\n  a,\n  b,\n}: Props) => {\n  return a;\n};", "TypeScript",
             "export const C = ({ a, b }: Props) => {"),
            ("export function useThing<\n  T extends Base,\n  U,\n>(a: T): U {\n}", "TypeScript",
             "export function useThing<T extends Base, U>(a: T): U {"),
            ("export interface Opts {  // the options\n  a: string;\n}", "TypeScript", "export interface Opts {"),
        ],
        ids=["python-split", "typescript-split", "rust-lifetime", "go-split", "one-line", "destructured",
             "split-generic", "interface-body"],
    )
    def test_the_signature_joins_a_split_declaration(self, lines, language, signature) -> None:
        """A formatter that puts one parameter per line leaves `signature_line`
        holding only the opening line; `signature` is the declaration on one
        line, the form the provenance map records, so a diff never reads it
        as truncated."""
        start = 1 if lines.startswith("@") else 0
        raw = {"text": lines, "lines": lines, "file": "m", "ruleId": "r", "language": language,
               "range": {"start": {"line": 0}},
               "metaVariables": {"single": {"NAME": {"text": "f", "range": {"start": {"line": start}}}}}}
        match = mod._parse_match(raw)
        assert match["signature"] == signature
        assert match["signature_line"] == lines.split("\n")[start].strip()

    def test_an_unclosed_bracket_stops_at_the_line_cap(self) -> None:
        rows = ["def f("] + ["    a,"] * (mod.SIGNATURE_MAX_LINES + 5)
        assert mod._declaration_signature(rows, 0, "python") == "def f(" + ", ".join(["a"] * (mod.SIGNATURE_MAX_LINES - 1)) + ","


# --------------------------------------------------------------------------
# Full mode: the text readers entry points need
# --------------------------------------------------------------------------


def _p(name, type_=None, default=None, optional=False) -> dict:
    return {"name": name, "type": type_, "default": default, "optional": optional}


class TestSignatureParts:
    """A function's params and return_type come from the one-line
    signature its recipe matched, so step 3 reads a signature by eye only
    where the runner leaves params null (#605)."""

    @pytest.mark.parametrize(
        ("signature", "language", "name", "params", "return_type"),
        [
            ("def fetch(url: str, *, retries: int = 3) -> bytes:", "python", "fetch",
             [_p("url", "str"), _p("retries", "int", "3", True)], "bytes"),
            ("async def run(a, /, b: Opts = None, *args: int, k: str, **kw) -> list[str]:", "python", "run",
             [_p("a"), _p("b", "Opts", "None", True), _p("*args", "int", None, True), _p("k", "str"),
              _p("**kw", None, None, True)], "list[str]"),
            ("def plain():", "python", "plain", [], None),
            ('def tag(b: str = "x", mask: int = 0x10, *, sep: "Sep"=None) -> Dict[str,int]:', "python", "tag",
             [_p("b", "str", '"x"', True), _p("mask", "int", "0x10", True), _p("sep", '"Sep"', "None", True)],
             "Dict[str,int]"),
            ("export function connect(host: string, port?: number, ...rest: string[]): Promise<Client> {",
             "typescript", "connect",
             [_p("host", "string"), _p("port", "number", None, True), _p("...rest", "string[]", None, True)],
             "Promise<Client>"),
            ("export declare function on(this: Bus, cb: (x: number) => void, opts: { once: boolean } = {}): void;",
             "typescript", "on", [_p("cb", "(x: number) => void"), _p("opts", "{ once: boolean }", "{}", True)],
             "void"),
            ("export function useThing<T extends Base, U>(a: T): U {", "typescript", "useThing", [_p("a", "T")], "U"),
            ("export default function Button({ size, tone }: ButtonProps): JSX.Element {", "tsx", "Button",
             [_p("{ size, tone }", "ButtonProps")], "JSX.Element"),
            ("export const add = async <T,>(a: T, b = 1): Promise<T> => {", "tsx", "add",
             [_p("a", "T"), _p("b", None, "1", True)], "Promise<T>"),
            ("export const twice = x => x * 2", "javascript", "twice", [_p("x")], None),
            ("export async function $fetch(url: string): Promise<Response> {", "typescript", "$fetch",
             [_p("url", "string")], "Promise<Response>"),
            ("export const use$ = (a$: number) => a$", "typescript", "use$", [_p("a$", "number")], None),
            ("export function label(text, sep = ', ') {", "javascript", "label",
             [_p("text"), _p("sep", None, "', '", True)], None),
            ("pub fn parse<'a, F: Fn(u8) -> bool>(input: &'a str, keep: F) -> Result<Ast, Error> where F: Copy {",
             "rust", "parse", [_p("input", "&'a str"), _p("keep", "F")], "Result<Ast, Error>"),
            ("pub async fn close(&mut self, code: u16) {", "rust", "close", [_p("&mut self"), _p("code", "u16")],
             None),
            ("func New(a, b int, opts ...Option) (*Client, error) {", "go", "New",
             [_p("a", "int"), _p("b", "int"), _p("opts", "...Option", None, True)], "(*Client, error)"),
            ("func Map[T any, U any](xs []T, f func(T) U) []U {", "go", "Map",
             [_p("xs", "[]T"), _p("f", "func(T) U")], "[]U"),
            ("func Write(chan int, string) error {", "go", "Write", [_p(None, "chan int"), _p(None, "string")],
             "error"),
        ],
        ids=["python-keyword-only", "python-every-kind", "python-none", "python-source-text", "ts-optional-rest",
             "ts-this-and-callback", "ts-generic", "tsx-destructured", "tsx-async-arrow", "js-bare-arrow",
             "ts-dollar-name", "ts-dollar-suffix", "js-string-default",
             "rust-lifetime-and-where", "rust-self", "go-shared-type", "go-generic", "go-unnamed"],
    )
    def test_a_function_signature_gives_its_parameters(self, signature, language, name, params,
                                                        return_type) -> None:
        assert mod.signature_parts(signature, language, name) == (params, return_type)

    @pytest.mark.parametrize(
        ("signature", "language", "name"),
        [
            ("export function shape(): {", "typescript", "shape"),  # an object return type on the lines after
            ("def f(a: int,", "python", "f"),  # cut at the line cap
            ("export const handler = makeHandler(options)", "typescript", "handler"),
            ("pub fn open(", "rust", "open"),
            ("func Open(a int", "go", "Open"),
            ("defineProps<Props>()", "html", "Props"),
        ],
        ids=["ts-split-return", "python-cut", "ts-not-an-arrow", "rust-cut", "go-cut", "other-language"],
    )
    def test_a_form_it_cannot_read_gives_none(self, signature, language, name) -> None:
        assert mod.signature_parts(signature, language, name) == (None, None)

    def test_an_export_record_carries_them_for_a_function_only(self) -> None:
        match = {"name": "run", "file": "a.py", "line": 1, "signature_line": "def run(a: int) -> str:",
                 "signature": "def run(a: int) -> str:", "rule": "python-public-functions", "language": "python",
                 "source": None, "text": "def run(a: int) -> str:\n    return ''"}
        form = {"metadata": {"export_type": "function"}, "rule": {"kind": "function_definition"}}
        record = mod._export_record(match, form)
        assert (record["params"], record["return_type"]) == ([_p("a", "int")], "str")
        klass = dict(match, name="Run", signature="class Run(Base):", text="class Run(Base):\n    pass")
        record = mod._export_record(klass, {"metadata": {"export_type": "class"}, "rule": {"kind": "class_definition"}})
        assert (record["params"], record["return_type"]) == (None, None)

    def test_the_documented_export_fields_are_the_records(self) -> None:
        documented = mod.__doc__.split('"exports": [{', 1)[1].split("}, ...],", 1)[0]
        record = mod._export_record(
            {"name": "f", "file": "a.go", "line": 1, "signature_line": "func F() {", "signature": "func F() {",
             "rule": "go-exported-functions", "language": "go", "source": None, "text": "func F() {}"},
            {"metadata": {"export_type": "function"}, "rule": {"kind": "function_declaration"}})
        for field in ("params", "return_type", "signature"):
            assert f'"{field}"' in documented and field in record, field


class TestTextReaders:
    def test_blank_keeps_the_lines_and_the_code(self) -> None:
        js = "a // c\nb = '// x' /* y\nz */ c\n"
        assert mod._blank(js, "js") == "a     \nb = '    '     \n     c\n"
        # a regular expression's insides go, a division stays
        assert mod._blank("x = s.split(/\\/*'/) / 2;\n", "js") == "x = s.split(/    /) / 2;\n"
        go = "x := `\nfunc Hidden() {}\n` // c\nfunc Shown() {}\n"
        assert mod._blank(go, "go").splitlines()[1:] == [" " * 16, "`" + " " * 5, "func Shown() {}"]
        rust = "/* a /* b */ c */ pub fn f() { let q = '\"'; let s = r#\"pub fn g\"#; }\n"
        blanked = mod._blank(rust, "rust")
        assert "pub fn f()" in blanked and "pub fn g" not in blanked and len(blanked) == len(rust)

    def test_rust_use_trees(self) -> None:
        assert mod._rust_use_leaves("a::{b, c::D as E, f::*, self}") == [
            (["a", "b"], None, False), (["a", "c", "D"], "E", False), (["a", "f"], None, True),
            (["a", "self"], None, False)]
        assert mod._rust_use_leaves("crate::x::Y") == [(["crate", "x", "Y"], None, False)]

    def test_go_names(self) -> None:
        code = mod._blank(POLYGLOT["gopkg/api.go"], "go")
        assert mod._go_names(code) == [("A", 15), ("C", 17), ("D", 17), ("Default", 21), ("Exported", 8),
                                       ("New", 26), ("T", 12)]

    def test_js_text_names(self) -> None:
        text = ("export let a = 1;\nexport declare const b: number;\nexport declare namespace NS {}\n"
                "export default class Def {}\nexport import Q = R.S;\nexport default Foo;\n"
                "// export const commented = 1;\nexport type { T } from './t';\n")
        declared, defaults = mod._js_text_names(text)
        assert declared == [("a", 1, False), ("b", 2, False), ("NS", 3, False), ("Def", 4, True), ("Q", 5, False)]
        assert defaults == [("Foo", 6)]

    @pytest.mark.parametrize(
        ("spec", "wanted"),
        [("./x", "src/x.ts"), ("./x.js", "src/x.ts"), ("./dir", "src/dir/index.ts"), ("../top", "top.tsx"),
         ("../../out", None), ("pkg", None), ("./missing", None)],
    )
    def test_resolve_js_module(self, spec, wanted) -> None:
        tree = {"src/x.ts", "src/dir/index.ts", "top.tsx", "src/barrel.ts"}
        assert mod.resolve_js_module(spec, "src/barrel.ts", tree) == wanted

    def test_exports_maps(self) -> None:
        assert mod.exports_subpaths("./a.js") == {".": ["./a.js"]}
        assert mod.exports_subpaths({"import": "./a.mjs", "require": ["./a.cjs"]}) == {".": ["./a.mjs", "./a.cjs"]}
        assert mod.exports_subpaths({".": "./a.js", "./b": {"types": "./b.d.ts", "default": None}}) == {
            ".": ["./a.js"], "./b": ["./b.d.ts"]}
        assert mod.exports_subpaths(None) == {}
        tree = {"pkg/src/index.ts", "pkg/macro/index.d.mts", "pkg/lib/util.ts"}
        assert mod._package_target("pkg", "./macro/index.d.mts", tree) == ("pkg/macro/index.d.mts", "file")
        assert mod._package_target("pkg", "./dist/esm/index.js", tree) == ("pkg/src/index.ts", "source-guess")
        assert mod._package_target("pkg", "./build/lib/util.js", tree) == ("pkg/lib/util.ts", "source-guess")
        assert mod._package_target("pkg", "./dist/none.js", tree) == (None, "unresolved")
        assert mod._package_target("pkg", "../outside.js", tree) == (None, "unresolved")

    def test_subpath_patterns(self) -> None:
        tree = {"pkg/src/ui/a.ts", "pkg/src/ui/deep/b.tsx", "pkg/locale/en.js", "pkg/src/ui/a.css"}
        # a `*` spans folders, as in Node
        assert mod._package_pattern("pkg", "./dist/ui/*.js", tree) == (
            {"a": "pkg/src/ui/a.ts", "deep/b": "pkg/src/ui/deep/b.tsx"}, "source-guess")
        assert mod._package_pattern("pkg", "./locale/*.js", tree) == ({"en": "pkg/locale/en.js"}, "file")
        assert mod._package_pattern("pkg", "./dist/none/*.js", tree) == ({}, "unresolved")
        assert mod._package_pattern("pkg", "./*/*.js", tree) == ({}, "unresolved")
        excluded = ["./ui/internal/*", "./private"]
        assert mod._subpath_excluded("./ui/internal/x", excluded) and mod._subpath_excluded("./private", excluded)
        assert not mod._subpath_excluded("./ui/button", excluded)

    def test_rust_paths(self) -> None:
        tree = {"src/lib.rs", "src/client.rs", "src/client/builder/mod.rs"}
        assert mod._rust_file("src/lib.rs", [], tree) == "src/lib.rs"
        assert mod._rust_file("src/lib.rs", ["client", "builder"], tree) == "src/client/builder/mod.rs"
        assert mod._rust_file("src/lib.rs", ["client", "missing"], tree) is None
        here, mods = ["client"], {"builder"}
        assert mod._rust_use_path(["crate", "a", "B"], here, mods) == ["a", "B"]
        assert mod._rust_use_path(["self", "builder", "B"], here, mods) == ["client", "builder", "B"]
        assert mod._rust_use_path(["super", "x"], here, mods) == ["x"]
        assert mod._rust_use_path(["super", "super", "x"], here, mods) is None
        assert mod._rust_use_path(["builder", "r#B"], here, mods) == ["client", "builder", "B"]
        assert mod._rust_use_path(["serde", "Serialize"], here, mods) is None

    def test_python_bindings(self) -> None:
        text = ("__all__ = ['a'] + ['b']\n__all__ += ('c',)\n__all__.extend(['d'])\n__all__.append('e')\n"
                "from .x import y as z\nfrom . import sub\nimport os.path\n"
                "try:\n    from ._fast import speed\nexcept ImportError:\n    def speed():\n        pass\n"
                "from .star import *\nclass K:\n    def m(self): pass\n")
        all_names, bound, stars = mod._py_bindings(text)
        assert all_names == ["a", "b", "c", "d", "e"]
        assert bound["z"] == {"line": 5, "kind": "import", "module": "x", "level": 1, "imported": "y"}
        assert bound["sub"]["module"] is None and bound["os"]["kind"] == "module-import"
        assert bound["speed"]["kind"] == "import" and "m" not in bound and bound["K"]["line"] == 14
        assert stars == [{"module": "star", "level": 1, "line": 13}]

    def test_python_bindings_skip_type_checking_imports(self) -> None:
        text = ("import typing\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .a import A\n"
                "else:\n    from .b import B\nif typing.TYPE_CHECKING:\n    from .c import C\n"
                "if not TYPE_CHECKING:\n    from .d import D\n")
        _, bound, _ = mod._py_bindings(text)
        assert {"B", "D"} <= set(bound) and not {"A", "C"} & set(bound)

    def test_python_bindings_read_from_text(self) -> None:
        text = ('__all__ = ["a",\n  "b"]\ntype Alias = int\ndef f[T](x: T) -> T: ...\n'
                "from .m import (x,\n    y as w)\nfrom .n import *\n")
        all_names, bound, stars = mod._py_text_bindings(text)
        assert all_names == ["a", "b"]
        assert bound["f"]["kind"] == "definition" and bound["w"]["imported"] == "y"
        assert stars == [{"module": "n", "level": 1, "line": 7}]


class TestEntryPointDiff:
    def test_each_language_family_on_its_own(self) -> None:
        """A Go package's entry points never make TypeScript exports internal."""
        surfaces = {family: mod._Surface() for family in mod.FAMILIES}
        surfaces["go"].add("Exported", "api.go", "declaration", "api.go", 3)
        exports = [{"export_name": "helper", "language": "typescript", "source_file": "a.ts", "source_line": 1},
                   {"export_name": "Other", "language": "go", "source_file": "b.go", "source_line": 2}]
        entries = [{"language": "go", "file": ".", "package": ".", "subpath": None, "resolution": "package"}]
        statuses, public, internal, gaps, outside = mod.entry_point_diff(exports, surfaces, entries, {"api.go"})
        assert statuses == {"go": "barrel", "javascript": "no-entry-point"}
        assert sorted(public) == [("go", "Exported"), ("javascript", "helper")]
        assert [e["export_name"] for e in internal] == ["Other"]
        assert [(family, info["name"]) for family, info in gaps] == [("go", "Exported")]
        assert outside == []

    def test_reachable_files_and_names_outside_scope(self) -> None:
        """An export of a reachable file is not internal, and a declared
        name no recipe found is outside scope when a file out of scope
        defines it."""
        surfaces = {family: mod._Surface() for family in mod.FAMILIES}
        rust = surfaces["rust"]
        rust.add("client", "src/lib.rs", "namespace", "src/client/mod.rs", None)
        rust.add("LIMIT", "src/lib.rs", "declaration", "src/lib.rs", 3)
        rust.add("Gen", "src/lib.rs", "re-export", "gen/out.rs", 1, "gen", "Gen")
        rust.reachable_files.update({"src/lib.rs", "src/client/builder.rs"})
        exports = [{"export_name": name, "language": "rust", "source_file": file, "source_line": 1}
                   for name, file in (("build", "src/client/builder.rs"), ("helper", "src/private.rs"))]
        entries = [{"language": "rust", "file": "src/lib.rs", "package": ".", "subpath": None, "resolution": "file"}]
        _, _, internal, gaps, outside = mod.entry_point_diff(
            exports, surfaces, entries, {"src/lib.rs", "src/client/mod.rs", "src/client/builder.rs", "src/private.rs"})
        assert [e["export_name"] for e in internal] == ["helper"]
        assert [info["name"] for _, info in gaps] == ["LIMIT"]
        assert [info["name"] for _, info in outside] == ["Gen"]


# --------------------------------------------------------------------------
# Full mode: runs over source trees
# --------------------------------------------------------------------------


@needs_ast_grep
class TestFullRuns:
    def test_a_typescript_package(self, tmp_path, capsys) -> None:
        root = _tree(tmp_path, TS_PACKAGE)
        code, out = _full(capsys, root, "--include", "src/**", "--include", "macro/**")
        assert (code, out["status"], out["errors"], out["files_in_scope"]) == (0, "ok", [], 8)
        assert sorted((e["source_file"], e["source_line"], e["export_name"], e["ast_node_type"])
                      for e in out["exports"]) == [
            ("macro/index.d.mts", 1, "macro", "export_statement"),
            ("macro/index.d.mts", 2, "MacroOptions", "export_statement"),
            ("src/def.ts", 1, "def", "export_statement"),
            ("src/index.ts", 3, "format", "export_specifier"),
            ("src/index.ts", 3, "parseValue", "export_specifier"),
            ("src/index.ts", 5, "internals", "export_statement"),
            ("src/index.ts", 6, "H2", "export_specifier"),
            ("src/index.ts", 7, "VERSION", "export_statement"),
            ("src/internal/impl.ts", 1, "secret", "export_statement"),
            ("src/shapes.ts", 1, "Shape", "export_statement"),
            ("src/shapes.ts", 2, "Kind", "export_statement"),
            ("src/shapes.ts", 3, "makeShape", "export_statement"),
            ("src/utils/format.ts", 1, "format", "export_statement"),
            ("src/utils/format.ts", 2, "parse", "export_statement"),
            ("src/utils/format.ts", 3, "unused", "export_statement"),
            ("src/utils/helper.ts", 1, "Helper", "export_statement"),
            ("src/utils/index.ts", 1, "format", "export_specifier"),
        ]
        by_name = {(e["source_file"], e["export_name"]): e for e in out["exports"]}
        assert by_name[("src/index.ts", "parseValue")]["from_file"] == "src/utils/format.ts"
        assert by_name[("src/shapes.ts", "Kind")]["export_type"] == "type"
        assert out["aggregates"] == {"exports": 17, "by_type": {"class": 1, "const": 1, "function": 7,
                                                                "interface": 2, "re-export": 5, "type": 1},
                                     "t1": 17, "t1_low": 0}
        entry_points = out["entry_points"]
        assert [(e["file"], e["subpath"], e["resolution"]) for e in entry_points["files"]] == [
            ("src/index.ts", ".", "source-guess"), ("macro/index.d.mts", "./macro", "file"),
            ("src/utils/index.ts", "./utils", "source-guess")]
        assert entry_points["exports_maps"] == [{
            "package": ".", "subpaths": [".", "./features/*", "./macro", "./package.json", "./utils"],
            "non_root_subpaths": 2, "wildcard_subpaths": 1}]
        diff = out["entry_point_diff"]
        assert _names(diff["public"]) == ["H2", "Kind", "MacroOptions", "Shape", "VERSION", "declared", "default",
                                          "format", "internals", "macro", "makeShape", "mutable", "parseValue"]
        public = {p["name"]: p for p in diff["public"]}
        assert (public["H2"]["file"], public["H2"]["line"], public["H2"]["local"]) == ("src/utils/helper.ts", 1, "Helper")
        assert (public["default"]["file"], public["default"]["line"], public["default"]["local"]) == ("src/def.ts", 1, "def")
        assert (public["Kind"]["via"], public["internals"]["via"]) == ("star", "namespace")
        # `unused` is exported by no entry point; `secret` is reachable through
        # `internals`; `def` is the traced default export
        assert _names(diff["internal"]) == ["unused"]
        assert _names(diff["extraction_gaps"]) == ["declared", "mutable"]
        assert out["counts"] == {"exports_public_api": 13, "exports_internal": 1, "effective_denominator": 13,
                                 "effective_denominator_basis": "scope.include", "denominator_files": 8}
        assert out["arms"] == {"monorepo": False, "monorepo_kind": None, "specific_modules": False,
                               "multi_subpath_exports": True}
        _, narrowed = _full(capsys, root, "--include", "src/**", "--include", "macro/**",
                            "--tier-a-include", "src/utils/**")
        # H2, format and parseValue are defined under src/utils/
        assert narrowed["counts"]["effective_denominator"] == 3
        assert narrowed["counts"]["effective_denominator_basis"] == "tier_a_include"

    def test_a_split_signature_is_joined(self, tmp_path, capsys) -> None:
        """ast-grep's `lines` hold the whole declaration, so `signature` gives
        a formatter-split one on one line while `signature_line` keeps the
        line that names it."""
        root = _tree(tmp_path, {
            "pkg/api.py": "def fetch(\n    url: str,\n    *,\n    retries: int = 3,\n) -> bytes:\n    return b''\n",
            "src/client.ts": "export function connect(\n  host: string,\n  port: number,\n): Client {\n  return x;\n}\n",
        })
        list_file = _tree(tmp_path / "lists", {"files.json": json.dumps(["pkg/api.py", "src/client.ts"])})
        code, out = _full(capsys, root, "--files-from", str(list_file / "files.json"), "--head-cap", "0")
        assert (code, out["status"]) == (0, "ok")
        by_name = {e["export_name"]: e for e in out["exports"]}
        assert by_name["fetch"]["signature"] == "def fetch(url: str, *, retries: int = 3) -> bytes:"
        assert by_name["fetch"]["signature_line"] == "def fetch("
        assert by_name["connect"]["signature"] == "export function connect(host: string, port: number): Client {"

    def test_each_language_records_params_and_return_type(self, tmp_path, capsys) -> None:
        """Through ast-grep, each language's function export carries the
        parameters and return type its signature states, a split one
        included, and a class none."""
        root = _tree(tmp_path, {
            "pkg/api.py": ("def fetch(\n    url: str,\n    *,\n    retries: int = 3,\n) -> bytes:\n    return b''\n"
                           "\n\nclass Session:\n    pass\n"),
            "src/client.ts": ("export function connect(\n  host: string,\n  port?: number,\n): Promise<Client> {\n"
                              "  return x;\n}\n\nexport const close = async (code: number): Promise<void> => {};\n"),
            "web/util.js": "export function label(text, sep = '-') {\n  return text;\n}\n",
            "src/lib.rs": "pub fn parse(input: &str) -> Result<Ast, Error> {\n    todo!()\n}\n",
            "cmd/main.go": "package cmd\n\nfunc New(a, b int) (*Client, error) {\n\treturn nil, nil\n}\n",
        })
        list_file = _tree(tmp_path / "lists", {"files.json": json.dumps(
            ["pkg/api.py", "src/client.ts", "web/util.js", "src/lib.rs", "cmd/main.go"])})
        code, out = _full(capsys, root, "--files-from", str(list_file / "files.json"), "--head-cap", "0")
        assert (code, out["status"]) == (0, "ok")
        got = {e["export_name"]: (e["params"], e["return_type"]) for e in out["exports"]}
        assert got == {
            "fetch": ([_p("url", "str"), _p("retries", "int", "3", True)], "bytes"),
            "Session": (None, None),
            "connect": ([_p("host", "string"), _p("port", "number", None, True)], "Promise<Client>"),
            "close": ([_p("code", "number")], "Promise<void>"),
            "label": ([_p("text"), _p("sep", None, "'-'", True)], None),
            "parse": ([_p("input", "&str")], "Result<Ast, Error>"),
            "New": ([_p("a", "int"), _p("b", "int")], "(*Client, error)"),
        }

    def test_python_rust_and_go(self, tmp_path, capsys) -> None:
        root = _tree(tmp_path, POLYGLOT)
        code, out = _full(capsys, root, "--tier-a-include", "src/mypkg/**")
        assert (code, out["status"]) == (0, "ok")
        assert out["entry_points"]["by_language"] == {"go": "barrel", "python": "barrel", "rust": "barrel"}
        diff = out["entry_point_diff"]
        public = {(p["language"], p["name"]): p for p in diff["public"]}
        assert sorted(name for language, name in public if language == "python") == [
            "Alpha", "Engine", "VERSION", "beta", "configure", "helper_a", "missing_name", "start", "sub"]
        assert sorted(name for language, name in public if language == "rust") == [
            "Client", "DemoResult", "Error", "LIMIT", "Serialize", "client", "top_level", "util_fn"]
        assert sorted(name for language, name in public if language == "go") == [
            "A", "C", "D", "Default", "Exported", "New", "T"]
        assert public[("python", "start")]["local"] == "run" and public[("python", "start")]["line"] == 5
        assert public[("rust", "DemoResult")]["file"] == "crate/src/error.rs"
        assert public[("rust", "Client")]["file"] == "crate/src/client/mod.rs"
        # Hint's import sits under `if TYPE_CHECKING:`, so the package never exports it
        assert sorted(_names(diff["internal"])) == ["Hidden", "Hint", "TestX", "helper_b", "internal_helper"]
        assert sorted(_names(diff["extraction_gaps"])) == [
            "A", "C", "Client", "D", "Default", "DemoResult", "Error", "LIMIT", "Serialize", "T", "VERSION",
            "missing_name"]
        assert out["entry_points"]["unresolved"] == [
            {"entry": "crate/src/lib.rs", "name": "Serialize", "from": "serde::Serialize", "file": "crate/src/lib.rs"}]
        # the names defined under src/mypkg/: Engine, start, sub, helper_a, VERSION, configure
        assert out["counts"]["effective_denominator"] == 6
        assert out["counts"]["exports_public_api"] == 24

    def test_an_entry_point_outside_scope(self, tmp_path, capsys) -> None:
        """An exports subpath whose file is out of scope is flagged and
        warned about, and the names it exports are outside scope, not
        extraction gaps."""
        root = _tree(tmp_path, TS_PACKAGE)
        _, out = _full(capsys, root, "--include", "src/**")
        assert [(e["file"], e["in_scope"]) for e in out["entry_points"]["files"]] == [
            ("src/index.ts", True), ("macro/index.d.mts", False), ("src/utils/index.ts", True)]
        assert any(w.startswith("public entry point macro/index.d.mts (subpath './macro' of package .)")
                   for w in out["warnings"])
        diff = out["entry_point_diff"]
        assert _names(diff["outside_scope"]) == ["MacroOptions", "macro"]
        assert _names(diff["extraction_gaps"]) == ["declared", "mutable"]
        # the public API holds them; the denominator of the files in scope does not
        assert (out["counts"]["exports_public_api"], out["counts"]["effective_denominator"]) == (13, 11)

    def test_specific_modules_and_the_reexport_targets(self, tmp_path, capsys) -> None:
        """Arm (b) on a repository that is not a monorepo, and the resolved
        re-export targets brief-skill's Tier-A list reads."""
        root = _tree(tmp_path, TS_PACKAGE)
        _, out = _full(capsys, root, "--include", "src/**", "--include", "macro/**", "--scope-type", "specific-modules")
        assert out["arms"] == {"monorepo": False, "monorepo_kind": None, "specific_modules": True,
                               "multi_subpath_exports": True}
        targets = {t["name"]: t for t in out["reexport_targets"]}
        assert sorted(targets) == ["H2", "Kind", "Shape", "default", "format", "internals", "makeShape", "parseValue"]
        assert targets["parseValue"] == {"name": "parseValue", "language": "javascript", "local": "parse",
                                         "from": "./utils/format", "entry": "src/index.ts",
                                         "file": "src/utils/format.ts", "line": 2, "via": "re-export"}
        assert (targets["Kind"]["file"], targets["Kind"]["via"]) == ("src/shapes.ts", "star")
        assert (targets["internals"]["file"], targets["internals"]["line"]) == ("src/internal/impl.ts", None)

    def test_a_local_list_item_takes_its_binding_type(self, tmp_path, capsys) -> None:
        """A local list item is typed by the binding it names (#559), and
        cites the whole line of the list."""
        root = _tree(tmp_path, LOCAL_LISTS)
        _, out = _full(capsys, root)
        types = {e["export_name"]: e["export_type"] for e in out["exports"]}
        assert types == {"buttonVariants": "const", "Button": "const", "Icon": "function", "Card": "function",
                         "Store": "class", "picked": "const", "cva": "re-export", "Radix": "re-export",
                         "DialogProps": "interface", "Size": "type", "default": "enum"}
        (button,) = [e for e in out["exports"] if e["export_name"] == "Button"]
        assert button["signature_line"] == "export { buttonVariants, Button, Icon, Card, Store, picked, cva, Radix }"
        assert out["aggregates"]["by_type"] == {"class": 1, "const": 3, "enum": 1, "function": 2, "interface": 1,
                                                "re-export": 2, "type": 1}

    def test_a_rush_monorepo(self, tmp_path, capsys) -> None:
        root = _tree(tmp_path, RUSH_MONOREPO)
        _, out = _full(capsys, root, "--include", "libs/a/**", "--scope-type", "specific-modules")
        assert out["arms"] == {"monorepo": True, "monorepo_kind": "rush", "specific_modules": False,
                               "multi_subpath_exports": False}
        assert out["entry_points"]["exports_maps"][0]["non_root_subpaths"] == 2
        assert _names(out["entry_point_diff"]["public"]) == ["a", "x", "y"]

    def test_issues_the_cap_and_the_component_scope(self, tmp_path, capsys) -> None:
        root = _tree(tmp_path, {
            "bad.ts": "export function ok() {}\nexport const = ;\n",
            "many.ts": "".join(f"export const c{n} = {n};\n" for n in range(5)),
            "button.tsx": "const Button = () => null;\nexport { Button };\n",
        })
        _, out = _full(capsys, root, "--head-cap", "2")
        assert out["file_issues"] == [{"file": "bad.ts", "issue": "syntax-errors", "count": 1, "line": 2}]
        (constants,) = [r for r in out["recipes"] if r["id"] == "js-exported-constants"]
        assert (constants["matches"], constants["truncated"], out["truncated"]) == (5, True, True)
        assert [e["export_name"] for e in out["exports"] if e["ast_recipe"] == "js-exported-constants"] == ["c0", "c1"]
        brief = _tree(tmp_path / "b", {"brief.yaml": "scope:\n  type: component-library\n  include: []\n"})
        _, out = _full(capsys, root, "--brief", str(brief / "brief.yaml"), "--tier", "Deep")
        assert (out["recipe_set"], out["head_cap"]) == ("component-library", 300)
        assert "js-exported-constants" not in {r["id"] for r in out["recipes"]}

    def test_the_installed_layout(self, tmp_path) -> None:
        """Installed, the script finds its recipe file and its sibling helpers
        beside it under _bmad/skf/shared/, with no src/ tree."""
        shared = tmp_path / "_bmad" / "skf" / "shared"
        (shared / "scripts").mkdir(parents=True)
        (shared / "data").mkdir()
        for name in ("skf-extract-public-api.py", "skf-source-tree.py", "skf-resolve-authoritative-files.py",
                     "skf-detect-workspaces.py"):
            shutil.copy(SCRIPTS / name, shared / "scripts" / name)
        shutil.copy(DATA_FILE, shared / "data" / DATA_FILE.name)
        root = _tree(tmp_path / "source", {"a.py": "def run():\n    pass\n"})
        result = subprocess.run(
            [sys.executable, (shared / "scripts" / "skf-extract-public-api.py").as_posix(), "--mode", "full",
             "--source-root", root.as_posix()],
            capture_output=True, text=True, encoding="utf-8", check=False)
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)
        assert out["recipes_file"].endswith("_bmad/skf/shared/data/ast-grep-recipes.yaml")
        assert [e["export_name"] for e in out["exports"]] == ["run"]


@needs_ast_grep
class TestTracing:
    """Public names more than one hop from the entry point: `export *`
    chains, pattern subpaths, star imports of star imports and `pub mod`
    chains are followed to the end, and a chain the trace cannot follow is
    listed as unresolved."""

    def test_javascript_chains(self, tmp_path, capsys) -> None:
        _, out = _full(capsys, _tree(tmp_path, JS_CHAINS))
        diff = out["entry_point_diff"]
        public = {p["name"]: p for p in diff["public"]}
        assert sorted(public) == ["Button", "Tile", "buttonVariants", "icons", "top"]
        # two `export *` hops
        assert (public["Button"]["via"], public["Button"]["file"]) == ("star", "src/components/button/index.ts")
        # an aliased re-export of an aliased list item of an import, to its declaration
        assert (public["Tile"]["file"], public["Tile"]["line"], public["Tile"]["local"]) == (
            "src/components/inner.ts", 1, "Inner")
        assert (public["icons"]["via"], public["icons"]["file"]) == ("namespace", "src/icons/index.ts")
        # Card on Tile's way, and Star, which the namespace's module passes on, are not internal
        assert {"Card", "Inner", "Star"} <= {e["export_name"] for e in out["exports"]}
        assert (diff["internal"], diff["extraction_gaps"]) == ([], [])
        assert out["counts"]["exports_public_api"] == 5
        assert out["entry_points"]["unresolved"] == [
            {"entry": "src/index.ts", "name": "*", "from": "external-pkg", "file": "src/components/index.ts"}]

    def test_pattern_subpaths(self, tmp_path, capsys) -> None:
        _, out = _full(capsys, _tree(tmp_path, JS_WILDCARDS))
        assert [(e["file"], e["subpath"], e["resolution"]) for e in out["entry_points"]["files"]] == [
            ("src/index.ts", ".", "file"), ("src/components/button.ts", "./components/button", "source-guess"),
            ("locale/en.js", "./locale/en", "file")]
        diff = out["entry_point_diff"]
        assert _names(diff["public"]) == ["Button", "VERSION", "en"]
        # a `null` target takes ./components/internal/* out of the surface
        assert _names(diff["internal"]) == ["secret"]
        assert out["entry_points"]["unresolved"] == [
            {"package": ".", "subpath": "./gone/*", "targets": ["./dist/gone/*.js"]}]
        assert out["entry_points"]["exports_maps"][0]["wildcard_subpaths"] == 4
        assert out["arms"]["multi_subpath_exports"] is False

    def test_python_chains(self, tmp_path, capsys) -> None:
        _, out = _full(capsys, _tree(tmp_path, PY_CHAINS))
        diff = out["entry_point_diff"]
        public = {p["name"]: p for p in diff["public"]}
        # json and typing's Any are no names of the package, _hidden is private
        assert sorted(public) == ["configure", "run", "tools"]
        assert (public["run"]["via"], public["run"]["file"], public["run"]["line"]) == (
            "star", "mypkg/core/engine.py", 4)
        assert (public["tools"]["via"], public["tools"]["file"]) == ("namespace", "mypkg/core/tools.py")
        # tool is reachable through the tools submodule
        assert "tool" in {e["export_name"] for e in out["exports"]} and diff["internal"] == []
        assert out["entry_points"]["unresolved"] == [
            {"entry": "mypkg/__init__.py", "name": "*", "from": ".missing", "file": "mypkg/__init__.py"}]

    def test_rust_chains(self, tmp_path, capsys) -> None:
        _, out = _full(capsys, _tree(tmp_path, RUST_CHAINS))
        diff = out["entry_point_diff"]
        public = {p["name"]: p for p in diff["public"]}
        assert sorted(public) == ["client", "deep"]
        # a glob of a module that globs another
        assert (public["deep"]["via"], public["deep"]["file"]) == ("star", "src/util/more.rs")
        # build (two `pub mod` hops), helper (a `pub use` of a reachable module)
        # and nested (an inline `pub mod`) are reachable; the trace cannot find
        # the #[path] file of odd
        assert {"build", "helper", "nested"} <= {e["export_name"] for e in out["exports"]}
        assert sorted(_names(diff["internal"])) == ["odd_fn", "unexported"]
        assert out["entry_points"]["unresolved"] == [
            {"entry": "src/lib.rs", "name": "odd", "from": "crate::client::odd", "file": "src/client/mod.rs"}]


# --------------------------------------------------------------------------
# Full mode: CLI
# --------------------------------------------------------------------------


class TestFullCli:
    def test_quick_mode_refuses_full_mode_flags(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            mod.main(["--source-root", "."])
        assert exc.value.code == 2
        assert "full mode only" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("argv", "message"),
        [(["--mode", "full"], "needs --source-root"),
         (["--mode", "full", "--source-root", "no/such/folder"], "source root not found"),
         (["--mode", "full", "--source-root", ".", "--head-cap", "-1"], "--head-cap")],
        ids=["no-root", "missing-root", "negative-cap"],
    )
    def test_input_errors_exit_2(self, argv, message, capsys) -> None:
        assert mod.main(argv) == 2
        captured = capsys.readouterr()
        assert captured.out == "" and message in captured.err

    def test_no_ast_grep_exits_3_with_the_scope(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path, {"a.py": "def f(): pass\n"})
        code, out = _full(capsys, root)
        assert (code, out["status"], out["exports"], out["files_in_scope"]) == (3, "no-ast-grep", [], 1)
        assert any("ast-grep is not on PATH" in w for w in out["warnings"])

    def test_no_ast_grep_still_gives_the_arms(self, tmp_path, capsys, no_ast_grep) -> None:
        """The entry points' files, the exports maps and the arms need no
        ast-grep; the diff and the counts do."""
        root = _tree(tmp_path, TS_PACKAGE)
        code, out = _full(capsys, root, "--include", "src/**", "--include", "macro/**")
        assert (code, out["entry_point_diff"], out["counts"]) == (3, None, None)
        assert out["arms"] == {"monorepo": False, "monorepo_kind": None, "specific_modules": False,
                               "multi_subpath_exports": True}
        entry_points = out["entry_points"]
        assert (entry_points["status"], entry_points["exports_maps"][0]["non_root_subpaths"]) == (None, 2)
        assert [e["file"] for e in entry_points["files"]] == ["src/index.ts", "macro/index.d.mts", "src/utils/index.ts"]

    def test_output_file(self, tmp_path, capsys, no_ast_grep) -> None:
        root = _tree(tmp_path / "root", {"a.py": ""})
        target = tmp_path / "out.json"
        code = mod.main(["--mode", "full", "--source-root", str(root), "-o", str(target)])
        assert code == 3 and capsys.readouterr().out == ""
        assert json.loads(target.read_text(encoding="utf-8"))["files_in_scope"] == 1

    def test_a_failed_scan_is_incomplete(self, tmp_path, capsys, monkeypatch) -> None:
        monkeypatch.setattr(mod, "_ast_grep", lambda: ("ast-grep", "0.45.3", None))

        def timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 600)

        monkeypatch.setattr(mod.subprocess, "run", timeout)
        root = _tree(tmp_path, {"a.py": "def f(): pass\n"})
        code, out = _full(capsys, root)
        assert (code, out["status"]) == (1, "incomplete")
        assert [(e["reason"], e["files"], e["first_file"]) for e in out["errors"]] == [("ast-grep-timeout", 1, "a.py")]

    def test_a_scan_that_exits_non_zero_is_incomplete(self, tmp_path, capsys, monkeypatch) -> None:
        """ast-grep exits non-zero only when a scan fails (the rules carry no
        severity): a batch that printed some matches before a panic may have
        left files unread, so its matches are kept and the run is
        incomplete."""
        monkeypatch.setattr(mod, "_ast_grep", lambda: ("ast-grep", "0.45.3", None))
        line = json.dumps({"text": "def a(): pass", "lines": "def a(): pass", "file": "a.py", "language": "Python",
                           "ruleId": "python-public-functions", "range": {"start": {"line": 0}},
                           "metaVariables": {"single": {"NAME": {"text": "a", "range": {"start": {"line": 0}}}}}})

        def panic(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 101, (line + "\n").encode(), b"thread 'main' panicked\n")

        monkeypatch.setattr(mod.subprocess, "run", panic)
        root = _tree(tmp_path, {"a.py": "def a(): pass\n", "b.py": "def b(): pass\n"})
        code, out = _full(capsys, root)
        assert (code, out["status"]) == (1, "incomplete")
        assert [e["export_name"] for e in out["exports"]] == ["a"]
        assert [(e["reason"], e["files"], e["detail"]) for e in out["errors"]] == [
            ("ast-grep-error", 2, "exit 101: thread 'main' panicked")]

    def test_the_time_limit_still_writes_the_json(self, tmp_path, capsys, monkeypatch) -> None:
        """--timeout stops the ast-grep runs, not the run: the JSON is
        written, incomplete, and one `time-limit` item names every file
        left unread."""
        monkeypatch.setattr(mod, "_ast_grep", lambda: ("ast-grep", "0.45.3", None))
        monkeypatch.setattr(mod, "ARGV_BUDGET", 10)  # one file per ast-grep call
        ticks = iter([0.0, 5.0])  # the clock starts, the first call starts; then it has run out
        monkeypatch.setattr(mod.time, "monotonic", lambda: next(ticks, 50.0))
        calls: list = []

        def scan(cmd, **kwargs):
            calls.append((cmd[-1], kwargs["timeout"]))
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        monkeypatch.setattr(mod.subprocess, "run", scan)
        root = _tree(tmp_path / "root", {"a.py": "", "b.py": "", "c.py": ""})
        target = tmp_path / "out.json"
        code = mod.main(["--mode", "full", "--source-root", str(root), "--timeout", "20", "-o", str(target)])
        out = json.loads(target.read_text(encoding="utf-8"))
        assert (code, out["status"]) == (1, "incomplete")
        assert calls == [("a.py", 15.0)]
        (item,) = [e for e in out["errors"] if e["unread"] == ["b.py", "c.py"]]
        assert (item["reason"], item["files"], item["first_file"]) == ("time-limit", 2, "b.py")
        assert "--timeout of 20s" in item["detail"]

    def test_a_call_the_time_limit_stops_is_time_limit(self, tmp_path, capsys, monkeypatch) -> None:
        monkeypatch.setattr(mod, "_ast_grep", lambda: ("ast-grep", "0.45.3", None))
        ticks = iter([0.0, 5.0])  # the clock starts, the call starts with 25s left; it then runs out
        monkeypatch.setattr(mod.time, "monotonic", lambda: next(ticks, 40.0))

        def slow(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

        monkeypatch.setattr(mod.subprocess, "run", slow)
        root = _tree(tmp_path, {"a.py": "def f(): pass\n"})
        code, out = _full(capsys, root, "--timeout", "30")
        assert (code, out["status"]) == (1, "incomplete")
        assert [(e["reason"], e["unread"]) for e in out["errors"]] == [("time-limit", ["a.py"])]

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_a_timeout_not_above_zero_is_an_input_error(self, value, tmp_path, capsys) -> None:
        assert mod.main(["--mode", "full", "--source-root", str(tmp_path), "--timeout", value]) == 2
        captured = capsys.readouterr()
        assert captured.out == "" and "--timeout" in captured.err

    def test_quick_mode_refuses_the_timeout(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            mod.main(["--timeout", "5"])
        assert exc.value.code == 2 and "full mode only" in capsys.readouterr().err

    def test_an_unforeseen_failure_exits_2_with_one_line(self, tmp_path, capsys, monkeypatch) -> None:
        """A crash would exit 1, which callers read as `incomplete` and run
        again; it exits 2, an input error, with one stderr line instead."""
        def boom(root):
            raise KeyError("tree")

        monkeypatch.setattr(mod, "list_tree", boom)
        assert mod.main(["--mode", "full", "--source-root", str(tmp_path)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.splitlines() == ["error: the run failed: KeyError: 'tree'"]

    def test_an_npm_cmd_shim_is_never_run(self, tmp_path, capsys, monkeypatch) -> None:
        """On Windows an npm .cmd shim runs through cmd.exe, which reads a
        repository path's `&` as a command separator: the native binary the
        shim wraps runs instead, and with none there no recipe runs."""
        shim = _tree(tmp_path / "npm", {"ast-grep.cmd": "@echo off\n"}) / "ast-grep.cmd"
        tools = mod._sibling("skf-source-tree.py")
        resolve = tools._resolve_outside_cwd
        monkeypatch.setattr(tools, "_resolve_outside_cwd", lambda name: str(shim) if name == "ast-grep" else resolve(name))
        calls: list = []
        monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
        root = _tree(tmp_path / "repo", {"a&calc&.py": "def f(): pass\n"})
        code, out = _full(capsys, root)
        assert (code, out["status"], out["ast_grep"]) == (3, "no-ast-grep", {"path": None, "version": None})
        assert any(str(shim) in w and "cmd.exe" in w for w in out["warnings"])
        assert calls == []
        # the binary @ast-grep/cli's postinstall places beside a global install's shim
        _tree(tmp_path / "npm", {"node_modules/@ast-grep/cli/ast-grep.exe": b"MZ"})
        assert Path(mod._native_ast_grep(str(shim))).as_posix() == (
            tmp_path / "npm" / "node_modules" / "@ast-grep" / "cli" / "ast-grep.exe").as_posix()
        # from node_modules/.bin, a platform package's when the postinstall did not run
        bin_shim = _tree(tmp_path / "proj", {"node_modules/.bin/ast-grep.CMD": "",
                                             "node_modules/@ast-grep/cli-win32-x64-msvc/ast-grep.exe": b"MZ"})
        assert Path(mod._native_ast_grep(str(bin_shim / "node_modules" / ".bin" / "ast-grep.CMD"))).as_posix() == (
            bin_shim / "node_modules" / "@ast-grep" / "cli-win32-x64-msvc" / "ast-grep.exe").as_posix()
        assert mod._native_ast_grep("/usr/bin/ast-grep") == "/usr/bin/ast-grep"


# --------------------------------------------------------------------------
# Entries mode: quick mode's entry files, found in the listing (step 5b
# quick-skill determinism-1)
# --------------------------------------------------------------------------


def _listing(tmp_path: Path, paths: list[str]) -> Path:
    """A skf-github-probe.py tree listing of `paths`."""
    listing = tmp_path / "tree.json"
    listing.write_bytes(json.dumps({"status": "ok", "tree": paths, "truncated": False}).encode("utf-8"))
    return listing


def _entries(capsys, tmp_path: Path, language: str, paths: list[str], staged: dict[str, str],
             *extra: str) -> tuple[int, dict | None]:
    root = _stage(tmp_path / "src", staged) if staged else (tmp_path / "src")
    root.mkdir(parents=True, exist_ok=True)
    listing = _listing(tmp_path, paths)
    code = mod.main(["--mode", "entries", "--language", language, "--tree-file", str(listing),
                     "--source-root", str(root), *extra])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


class TestEntries:
    def test_a_python_import_name_that_is_not_the_distribution_name(self, tmp_path, capsys):
        """Pillow's package is src/PIL/: no folder is named pillow, so the package top is kept."""
        paths = ["pyproject.toml", "src/PIL/__init__.py", "src/PIL/Image.py", "Tests/test_image.py",
                 "Tests/__init__.py", "docs/conf.py", "docs/__init__.py", "setup.py"]
        code, out = _entries(capsys, tmp_path, "python", paths, {"pyproject.toml": '[project]\nname = "Pillow"\n'})
        assert code == 0
        assert (out["manifest"], out["entry_files"], out["unresolved"]) == ("pyproject.toml", ["src/PIL/__init__.py"], [])

    def test_the_package_named_after_the_manifest_is_preferred(self, tmp_path, capsys):
        paths = ["pyproject.toml", "acme_tools/__init__.py", "scripts/__init__.py", "examples/demo/__init__.py",
                 "benchmarks/__init__.py", "testing/__init__.py"]
        code, out = _entries(capsys, tmp_path, "python", paths, {"pyproject.toml": '[project]\nname = "acme-tools"\n'})
        assert (code, out["entry_files"]) == (0, ["acme_tools/__init__.py"])

    def test_a_single_module_package(self, tmp_path, capsys):
        """six ships six.py and no package folder: setup.py names it."""
        paths = ["setup.py", "six.py", "test_six.py", "documentation/index.rst", "README.rst"]
        code, out = _entries(capsys, tmp_path, "python", paths, {"setup.py": 'setup(name="six", version="1.16.0")\n'})
        assert (code, out["manifest"], out["entry_files"]) == (0, "setup.py", ["six.py"])

    def test_the_name_comes_from_the_first_manifest_that_gives_one(self, tmp_path, capsys):
        """A pyproject.toml with only [build-system] and [tool.*] names no package: setup.py does."""
        paths = ["pyproject.toml", "setup.py", "six.py", "test_six.py"]
        staged = {"pyproject.toml": '[build-system]\nrequires = ["setuptools"]\n\n[tool.black]\nline-length = 88\n',
                  "setup.py": 'from setuptools import setup\nsetup(name="six")\n'}
        code, out = _entries(capsys, tmp_path, "python", paths, staged)
        assert (code, out["manifest"], out["entry_files"], out["unresolved"]) == (0, "setup.py", ["six.py"], [])

    def test_a_setup_cfg_name_and_a_poetry_name(self, tmp_path, capsys):
        paths = ["pyproject.toml", "setup.cfg", "setup.py", "attrs_lite.py"]
        staged = {"pyproject.toml": '[build-system]\nrequires = ["setuptools"]\n',
                  "setup.py": "from setuptools import setup\nsetup()\n",
                  "setup.cfg": "[metadata]\nname = attrs-lite\nversion = 1.0\n\n[options]\ninstall_requires =\n    six>=1\n"}
        code, out = _entries(capsys, tmp_path, "python", paths, staged)
        assert (code, out["manifest"], out["entry_files"]) == (0, "setup.cfg", ["attrs_lite.py"])
        code, out = _entries(capsys, tmp_path / "poetry", "python", ["pyproject.toml", "src/tiny.py"],
                             {"pyproject.toml": '[tool.poetry]\nname = "tiny"\n'})
        assert (code, out["manifest"], out["entry_files"]) == (0, "pyproject.toml", ["src/tiny.py"])

    def test_a_source_root_not_made_yet_holds_no_manifest(self, tmp_path, capsys):
        """Nothing was fetched yet, so the fetch folder does not exist: the listing still gives the entry."""
        listing = _listing(tmp_path, ["six.py", "README.rst"])
        code = mod.main(["--mode", "entries", "--language", "python", "--tree-file", str(listing),
                         "--source-root", str(tmp_path / "not-made")])
        out = json.loads(capsys.readouterr().out)
        assert (code, out["manifest"], out["entry_files"]) == (0, None, [])
        (tmp_path / "a-file").write_bytes(b"x")
        code = mod.main(["--mode", "entries", "--language", "python", "--tree-file", str(listing),
                         "--source-root", str(tmp_path / "a-file")])
        assert code == 2 and "is not a folder" in capsys.readouterr().err

    def test_a_python_package_with_nothing_to_read_names_what_it_tried(self, tmp_path, capsys):
        code, out = _entries(capsys, tmp_path, "python", ["pyproject.toml", "README.md"],
                             {"pyproject.toml": '[project]\nname = "ghost"\n'})
        assert (code, out["entry_files"]) == (0, [])
        assert out["unresolved"] == [{"package": ".", "subpath": None, "targets": ["ghost.py", "src/ghost.py"]}]

    def test_a_main_that_names_the_build_output_maps_back_to_the_source(self, tmp_path, capsys):
        paths = ["package.json", "src/index.ts", "src/core.ts", "README.md"]
        code, out = _entries(capsys, tmp_path, "ts", paths,
                             {"package.json": '{"name": "acme", "main": "dist/index.js", "types": "dist/index.d.ts"}'},
                             "--fetch-list", str(tmp_path / "entries.txt"))
        assert (code, out["manifest"], out["entry_files"], out["unresolved"]) == (
            0, "package.json", ["src/index.ts"], [])
        assert (tmp_path / "entries.txt").read_bytes() == b"src/index.ts\n"

    def test_a_scoped_package_of_a_monorepo(self, tmp_path, capsys):
        paths = ["package.json", "packages/core/package.json", "packages/core/lib/main.js", "packages/web/index.js"]
        code, out = _entries(capsys, tmp_path, "js", paths,
                             {"packages/core/package.json": '{"name": "@acme/core", "exports": {".": "./lib/main.js"}}'},
                             "--scope", "./packages/core/")
        assert (code, out["scope"], out["manifest"], out["entry_files"]) == (
            0, "packages/core", "packages/core/package.json", ["packages/core/lib/main.js"])

    def test_a_cargo_lib_path(self, tmp_path, capsys):
        cargo = '[package]\nname = "demo"\n\n[lib]\npath = "src/demo.rs"\n'
        paths = ["Cargo.toml", "src/demo.rs", "src/main.rs", "crates/x/Cargo.toml", "crates/x/src/lib.rs"]
        code, out = _entries(capsys, tmp_path, "rust", paths, {"Cargo.toml": cargo})
        assert (code, out["entry_files"]) == (0, ["src/demo.rs"])
        code, out = _entries(capsys, tmp_path / "virtual", "rust", ["Cargo.toml", "crates/x/src/lib.rs",
                                                                     "crates/x/Cargo.toml"],
                             {"Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n'})
        assert (code, out["entry_files"], out["unresolved"][0]["targets"]) == (0, [], ["src/lib.rs"])

    def test_the_java_group_folder(self, tmp_path, capsys):
        pom = ("<project><parent><groupId>com.acme</groupId></parent><artifactId>core</artifactId>"
               "</project>")
        paths = ["pom.xml", "src/main/java/com/acme/A.java", "src/main/java/com/acme/B.java",
                 "src/main/java/com/acme/sub/C.java", "src/test/java/com/acme/ATest.java"]
        code, out = _entries(capsys, tmp_path, "java", paths, {"pom.xml": pom})
        assert (code, out["entry_files"]) == (0, ["src/main/java/com/acme/A.java", "src/main/java/com/acme/B.java"])

    def test_the_go_and_kotlin_globs_read_five_files(self, tmp_path, capsys):
        go = ["go.mod", *[f"f{i}.go" for i in range(7)], "a_test.go", "cmd/main.go"]
        code, out = _entries(capsys, tmp_path, "go", go, {"go.mod": "module example.com/acme\n"})
        assert (code, out["entry_files"]) == (0, [f"f{i}.go" for i in range(5)])
        kt = ["build.gradle.kts", "src/main/kotlin/a/A.kt", "src/main/kotlin/B.kt", "src/test/kotlin/T.kt"]
        code, out = _entries(capsys, tmp_path / "kt", "kotlin", kt, {})
        assert (code, out["manifest"], out["entry_files"]) == (
            0, "build.gradle.kts", ["src/main/kotlin/B.kt", "src/main/kotlin/a/A.kt"])
        assert any("not under --source-root" in w for w in out["warnings"])

    def test_a_language_with_no_rule_and_an_unknown_one(self, tmp_path, capsys):
        code, out = _entries(capsys, tmp_path, "swift", ["Package.swift", "Sources/A/a.swift"], {})
        assert (code, out["entry_files"]) == (0, []) and "no entry-point rule for swift" in out["warnings"][0]
        code, out = _entries(capsys, tmp_path / "f", "fortran", ["main.f90"], {})
        assert code == 1 and "unknown language" in out["_error"]

    @pytest.mark.parametrize(
        ("argv", "message"),
        [pytest.param(["--language", "python", "--source-root", "."], "needs --tree-file", id="no-listing"),
         pytest.param(["--language", "python", "--tree-file", "t.json"], "needs --tree-file and --source-root",
                      id="no-root"),
         pytest.param(["--tree-file", "t.json", "--source-root", "."], "takes one --language", id="no-language"),
         pytest.param(["--language", "python", "--tree-file", "t", "--source-root", ".", "--entry-file", "a.py"],
                      "quick mode only", id="quick-flag"),
         pytest.param(["--language", "python", "--tree-file", "t", "--source-root", ".", "--tier", "Quick"],
                      "full mode only", id="full-flag")],
    )
    def test_entries_mode_flags(self, argv, message, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "entries", *argv])
        assert exc.value.code == 2 and message in capsys.readouterr().err

    def test_a_listing_that_cannot_be_read_exits_2(self, tmp_path, capsys):
        code = mod.main(["--mode", "entries", "--language", "python", "--tree-file", str(tmp_path / "absent.json"),
                         "--source-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert (code, captured.out) == (2, "") and "cannot read --tree-file" in captured.err

    def test_the_listing_flags_belong_to_entries_and_quick_mode(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "full", "--source-root", ".", "--tree-file", "t.json"])
        assert exc.value.code == 2 and "entries or quick mode only" in capsys.readouterr().err
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "quick", "--language", "js", "--entry-file", "a.js", "--scope", "x"])
        assert exc.value.code == 2 and "entries mode only" in capsys.readouterr().err
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "quick", "--tree-file", "t.json"])
        assert exc.value.code == 2 and "only with --manifest-file or --entry-file" in capsys.readouterr().err


# --------------------------------------------------------------------------
# unlisted[]: the module each re-export statement names (step 5b quick-skill
# determinism-2)
# --------------------------------------------------------------------------


NODENEXT = {
    "package.json": '{"name": "acme", "type": "module"}',
    "src/index.ts": "export * from './core.js';\nexport { helper as h } from './util/index.js';\n",
    "src/core.ts": "export class Core {}\nexport * from './util/index.js';\n",
    "src/util/index.ts": "export function helper() {}\nexport const VERSION = '1';\n",
}


class TestUnlisted:
    def _extract(self, files: dict[str, str], entries: list[str], tree: list[str] | None, language: str = "ts"):
        payload = {"language": language, "manifest": {"path": "", "content": ""},
                   "entries": [{"path": p, "content": files[p]} for p in entries]}
        if tree is not None:
            payload["tree"] = tree
        return mod.extract(payload)

    def test_a_nodenext_specifier_names_its_typescript_source(self):
        out = self._extract(NODENEXT, ["src/index.ts"], list(NODENEXT))
        assert out["unlisted"] == [{"file": "src/index.ts", "line": 1, "statement": "export * from './core.js'",
                                    "specifier": "./core.js", "module_file": "src/core.ts"}]
        assert any("export * from './core.js'" in w for w in out["warnings"])

    def test_a_chain_is_followed_round_by_round_and_converges(self):
        """Each round passes the module files as entries: a statement whose module is
        already an entry drops out with its warning, so nothing is named twice."""
        entries = ["src/index.ts"]
        for _ in range(5):
            out = self._extract(NODENEXT, entries, list(NODENEXT))
            new = [r["module_file"] for r in out["unlisted"] if r["module_file"]]
            if not new:
                break
            entries += [f for f in new if f not in entries]
        assert entries == ["src/index.ts", "src/core.ts", "src/util/index.ts"]
        assert out["unlisted"] == [] and not any("passes on names" in w for w in out["warnings"])
        assert {e["name"] for e in out["exports"]} >= {"Core", "helper", "VERSION", "h"}

    def test_a_nested_index_barrel_and_a_folder_specifier(self):
        files = {"index.js": "export * from './lib';\nmodule.exports = require('./cjs');\n",
                 "lib/index.ts": "export const a = 1;\n", "cjs.js": "exports.b = 2;\n"}
        out = self._extract(files, ["index.js"], list(files), language="js")
        assert [(r["statement"], r["module_file"]) for r in out["unlisted"]] == [
            ("export * from './lib'", "lib/index.ts"), ("module.exports = require('./cjs')", "cjs.js")]

    def test_a_python_star_import_names_its_module(self):
        files = {"pkg/__init__.py": "from .core import *\nfrom pkg.extra import *\nfrom os import *\n",
                 "pkg/core.py": "def run(): pass\n", "pkg/extra/__init__.py": "X = 1\n"}
        out = self._extract(files, ["pkg/__init__.py"], list(files), language="python")
        assert [(r["specifier"], r["module_file"]) for r in out["unlisted"]] == [
            (".core", "pkg/core.py"), ("pkg.extra", "pkg/extra/__init__.py")]

    def test_a_rust_glob_and_a_package_import_have_no_module_file(self):
        out = self._extract({"src/lib.rs": "pub use crate::parser::*;\n"}, ["src/lib.rs"], ["src/lib.rs"],
                            language="rust")
        assert [(r["statement"], r["module_file"]) for r in out["unlisted"]] == [("pub use crate::parser::*", None)]
        out = self._extract({"index.js": "export * from 'lodash';\n"}, ["index.js"], ["index.js"], language="js")
        assert [(r["specifier"], r["module_file"]) for r in out["unlisted"]] == [("lodash", None)]

    def test_without_a_listing_only_the_entries_are_known(self):
        out = self._extract(NODENEXT, ["src/index.ts"], None)
        assert [r["module_file"] for r in out["unlisted"]] == [None]
        both = self._extract(NODENEXT, ["src/index.ts", "src/core.ts"], None)
        assert [r["file"] for r in both["unlisted"]] == ["src/core.ts"], "the read module drops out"
        assert not any("src/index.ts line 1" in w for w in both["warnings"])

    def test_a_followed_module_passes_on_no_default_export(self, tmp_path, capsys):
        """`export *` re-exports no default: `import { Hidden } from 'acme'` cannot import it."""
        files = {"package.json": '{"name": "acme"}', "src/index.ts": "export * from './core.js';\n",
                 "src/core.ts": "export default class Hidden {}\nexport class Core {}\n"
                                "export default function () {}\n"}
        root = _stage(tmp_path / "src", files)
        listing = _listing(tmp_path, list(files))
        code, out = _quick(capsys, "--language", "ts", "--source-root", str(root), "--tree-file", str(listing),
                           "--entry-file", "src/index.ts", "--follow-file", "src/core.ts")
        assert code == 0 and [e["name"] for e in out["exports"]] == ["Core"]
        assert out["unlisted"] == [] and not any("export default" in w for w in out["warnings"])
        code, out = _quick(capsys, "--language", "ts", "--source-root", str(root), "--entry-file", "src/core.ts")
        assert code == 0 and [e["name"] for e in out["exports"]] == ["Hidden", "Core"], "an entry keeps it"

    def test_the_module_folders_of_a_multi_module_build(self, tmp_path, capsys):
        pom = ("<project><groupId>com.acme</groupId><artifactId>parent</artifactId>"
               "<modules><module>core</module><module>../shared/api</module></modules></project>")
        out = mod.extract({"language": "java", "manifest": {"path": "lib/pom.xml", "content": pom}, "entries": []})
        assert (out["modules"], out["module_folders"]) == (["core", "../shared/api"], ["lib/core", "shared/api"])
        assert mod._module_folder("settings.gradle.kts", ":core:api") == "core/api"

    def test_the_cli_writes_the_modules_still_to_read(self, tmp_path, capsys):
        root = _stage(tmp_path / "src", NODENEXT)
        listing = _listing(tmp_path, list(NODENEXT))
        follow = tmp_path / "follow.txt"
        code, out = _quick(capsys, "--language", "ts", "--source-root", str(root), "--tree-file", str(listing),
                           "--entry-file", "src/index.ts", "--fetch-list", str(follow))
        assert code == 0 and follow.read_bytes() == b"src/core.ts\n"
        code, out = _quick(capsys, "--language", "ts", "--source-root", str(root), "--tree-file", str(listing),
                           "--entry-file", "src/index.ts", "--entry-file", "src/core.ts",
                           "--entry-file", "src/util/index.ts", "--fetch-list", str(follow))
        assert (code, out["unlisted"], follow.read_bytes()) == (0, [], b"")


# --------------------------------------------------------------------------
# --follow: quick mode reads the chains itself (step 5b gate run 2, brief-skill
# and quick-skill determinism-1: no caller loops over the modules)
# --------------------------------------------------------------------------


class TestFollow:
    def _follow(self, capsys, root: Path, listing: Path, *extra: str) -> tuple[int, dict | None]:
        return _quick(capsys, "--language", "ts", "--source-root", str(root), "--tree-file", str(listing),
                      "--manifest-file", "package.json", "--entry-file", "src/index.ts", "--follow", *extra)

    def test_a_local_chain_is_read_to_its_end(self, tmp_path, capsys):
        root = _stage(tmp_path / "src", NODENEXT)
        code, out = self._follow(capsys, root, _listing(tmp_path, list(NODENEXT)))
        assert code == 0 and out["followed"] == ["src/core.ts", "src/util/index.ts"]
        assert {e["name"] for e in out["exports"]} >= {"Core", "helper", "VERSION", "h"}
        assert out["unlisted"] == [] and not any("passes on names" in w for w in out["warnings"])

    def test_a_module_it_cannot_read_stays_unlisted_and_the_rest_is_kept(self, tmp_path, capsys):
        """A module the listing names but the folder lacks is a warning, never an exit: the names of
        the modules read before it, and after it, stay in the output."""
        files = {**NODENEXT, "src/core.ts": "export class Core {}\nexport * from './gone.js';\n"
                                            "export * from './util/index.js';\n"}
        root = _stage(tmp_path / "src", files)
        follow = tmp_path / "follow.txt"
        code, out = self._follow(capsys, root, _listing(tmp_path, [*files, "src/gone.ts"]),
                                 "--fetch-list", str(follow))
        assert code == 0 and out["followed"] == ["src/core.ts", "src/util/index.ts"]
        assert {e["name"] for e in out["exports"]} >= {"Core", "helper", "VERSION"}
        assert [r["module_file"] for r in out["unlisted"]] == ["src/gone.ts"]
        assert ("--follow could not read src/gone.ts (it is not under --source-root), so the names it passes on "
                "are missing") in out["warnings"]
        assert follow.read_bytes() == b"src/gone.ts\n", "the fetch list names what is left to read"

    def test_it_stops_after_the_last_round_and_says_what_is_left(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(mod, "FOLLOW_ROUNDS", 1)
        root = _stage(tmp_path / "src", NODENEXT)
        code, out = self._follow(capsys, root, _listing(tmp_path, list(NODENEXT)))
        assert code == 0 and out["followed"] == ["src/core.ts"]
        assert "--follow stopped after 1 rounds with modules left to read: src/util/index.ts" in out["warnings"]

    def test_a_github_source_is_fetched_round_by_round(self, tmp_path, capsys, monkeypatch):
        """With --repo each module is fetched into --source-root first, raw and without gh; a module the
        fetch cannot read is a warning naming why."""
        files = {**NODENEXT, "src/core.ts": "export class Core {}\nexport * from './util/index.js';\n"
                                            "export * from './private.js';\n"}
        served = {path: text.encode("utf-8") for path, text in files.items()}
        asked: list[tuple[str, str, str, str]] = []

        def raw(owner, repo, ref, path):
            asked.append((owner, repo, ref, path))
            return (served[path], "") if path in served else (None, "HTTP 404")

        fetch = mod._sibling("skf-github-fetch.py")
        monkeypatch.setattr(fetch, "_raw", raw)
        monkeypatch.setattr(fetch, "_gh_raw", lambda *a: (None, "gh is not installed"))
        root = _stage(tmp_path / "files", {path: files[path] for path in ("package.json", "src/index.ts")})
        listing = _listing(tmp_path, [*files, "src/private.ts"])
        code, out = self._follow(capsys, root, listing, "--repo", "https://github.com/acme/lib", "--ref", "v1.0.0")
        assert code == 0 and out["followed"] == ["src/core.ts", "src/util/index.ts"]
        assert asked == [("acme", "lib", "v1.0.0", "src/core.ts"), ("acme", "lib", "v1.0.0", "src/util/index.ts"),
                         ("acme", "lib", "v1.0.0", "src/private.ts")]
        assert (root / "src" / "util" / "index.ts").read_bytes() == served["src/util/index.ts"]
        assert {e["name"] for e in out["exports"]} >= {"Core", "helper", "VERSION"}
        [warning] = [w for w in out["warnings"] if w.startswith("--follow could not read src/private.ts")]
        assert "HTTP 404" in warning and "gh is not installed" in warning

    @pytest.mark.parametrize(("extra", "message"), [
        (["--repo", "acme/lib"], "--repo and --ref fetch the modules --follow reads, so pass --follow"),
        (["--follow", "--ref", "main"], "--ref is the ref of --repo, so pass --repo"),
    ], ids=["repo-without-follow", "ref-without-repo"])
    def test_a_flag_that_needs_another(self, tmp_path, capsys, extra, message):
        root = _stage(tmp_path / "src", NODENEXT)
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "quick", "--language", "ts", "--source-root", str(root), "--tree-file",
                      str(_listing(tmp_path, list(NODENEXT))), "--entry-file", "src/index.ts", *extra])
        assert exc.value.code == 2 and message in capsys.readouterr().err

    def test_follow_needs_the_listing_and_quick_mode_files(self, tmp_path, capsys):
        root = _stage(tmp_path / "src", NODENEXT)
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "quick", "--language", "ts", "--source-root", str(root),
                      "--entry-file", "src/index.ts", "--follow"])
        assert exc.value.code == 2 and "pass both" in capsys.readouterr().err
        with pytest.raises(SystemExit) as exc:
            mod.main(["--mode", "entries", "--language", "ts", "--source-root", str(root), "--tree-file",
                      str(_listing(tmp_path, list(NODENEXT))), "--follow"])
        assert exc.value.code == 2 and "--follow: quick mode only" in capsys.readouterr().err

    def test_a_repository_the_fetch_does_not_accept_is_an_input_error(self, tmp_path, capsys):
        root = _stage(tmp_path / "src", NODENEXT)
        code = mod.main(["--mode", "quick", "--language", "ts", "--source-root", str(root), "--tree-file",
                         str(_listing(tmp_path, list(NODENEXT))), "--entry-file", "src/index.ts", "--follow",
                         "--repo", "not a repo"])
        captured = capsys.readouterr()
        assert (code, captured.out) == (2, "")
        assert "not a repo is not a github.com repository" in captured.err
