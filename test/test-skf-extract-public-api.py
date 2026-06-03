#!/usr/bin/env python3
"""Tests for skf-extract-public-api.py.

The helper does no I/O — it parses content passed in via JSON. Tests
build payloads inline, call extract() directly, and assert on the
shape of the returned envelope. Per-language manifest parsers and
export scanners are also exercised individually.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_extract_public_api",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-extract-public-api.py",
)
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
        def boom(content, source_file):
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
