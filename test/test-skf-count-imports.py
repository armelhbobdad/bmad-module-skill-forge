#!/usr/bin/env python3
"""Tests for skf-count-imports.py.

Covers:
  - boundary-anchored matching: react against react-dom and react-router,
    scoped npm packages, Python, Rust and Go module prefixes, longest prefix
  - distribution-to-import names: PyYAML as yaml, Pillow as PIL,
    beautifulsoup4 as bs4, typeshed and DefinitelyTyped stubs, namespace
    families, Symfony naming, installed Composer metadata, explicit modules
  - unresolved[]: unmatched guesses (names built by a rule included), no
    import name, unsupported ecosystem
  - the exclusion globs: defaults, --exclude, glob semantics, anchoring, and
    the list documented in skf-create-stack-skill's manifest-patterns.md
  - output: files[{path, line}], file_count, above_threshold, sort order and
    ties, scope pass-through
  - per-language import extraction (JS/TS, Python, Rust, Go, JVM, Ruby, PHP,
    Swift), Python through ast and line by line when a file does not parse
  - units: relative imports, edges, the importing files of each edge,
    imported_by / imports_from, external deps (a dependency that is a unit
    left out), import names from manifest_name or what a JVM, Composer or
    Swift unit declares, and the edges and libraries outputs piped into
    skf-find-cycles.py and skf-pair-intersect.py
  - input shapes and errors; CLI exit codes; skf-scan-manifests.py output
    piped in as it is
  - --relative-to: the files of one package written relative to the project
    that holds it
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
SCRIPT_PATH = SCRIPTS / "skf-count-imports.py"
MANIFEST_PATTERNS = (
    REPO_ROOT / "src" / "skf-create-stack-skill" / "references" / "manifest-patterns.md"
)

spec = importlib.util.spec_from_file_location("skf_count_imports", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _count(root: Path, deps: list, units: list | None = None, **kwargs) -> dict:
    parsed_units = mod.parse_units(units) if units is not None else None
    return mod.count_imports(root, mod.parse_dependencies(deps), units=parsed_units, **kwargs)


def _dep(result: dict, name: str) -> dict:
    return next(d for d in result["dependencies"] if d["name"] == name)


def _paths(entry: dict) -> list[str]:
    return [f["path"] for f in entry["files"]]


def _unresolved_names(result: dict) -> list[str]:
    return [u["name"] for u in result["unresolved"]]


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        input=stdin,
        check=False,
    )


def _run_helper(name: str, *args: str, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        input=stdin,
        check=False,
    )


# --------------------------------------------------------------------------
# Boundary-anchored matching
# --------------------------------------------------------------------------


class TestBoundaryMatching:
    def test_react_does_not_count_react_dom_or_react_router(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "src" / "App.tsx",
            "import React from 'react';\n"
            "import { createRoot } from 'react-dom/client';\n"
            "import { Link } from \"react-router\";\n",
        )
        _write(tmp_path / "src" / "main.tsx", "import { createRoot } from 'react-dom/client';\n")
        _write(tmp_path / "src" / "jsx.ts", "import { jsx } from 'react/jsx-runtime';\n")
        result = _count(
            tmp_path,
            [
                {"name": "react", "ecosystem": "npm"},
                {"name": "react-dom", "ecosystem": "npm"},
                {"name": "react-router", "ecosystem": "npm"},
            ],
        )
        assert _paths(_dep(result, "react")) == ["src/App.tsx", "src/jsx.ts"]
        assert _paths(_dep(result, "react-dom")) == ["src/App.tsx", "src/main.tsx"]
        assert _paths(_dep(result, "react-router")) == ["src/App.tsx"]
        assert _dep(result, "react")["resolution"] == "exact"

    def test_scoped_package_boundary(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "import x from '@tanstack/query-core/build';\n")
        _write(tmp_path / "b.ts", "import y from '@tanstack/query-core-extra';\n")
        result = _count(tmp_path, [{"name": "@tanstack/query-core", "ecosystem": "npm"}])
        assert _paths(_dep(result, "@tanstack/query-core")) == ["a.ts"]

    def test_python_module_boundary(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "import yaml\n")
        _write(tmp_path / "b.py", "from yaml.loader import SafeLoader\n")
        _write(tmp_path / "c.py", "import yamlordereddictloader\n")
        result = _count(tmp_path, [{"name": "PyYAML", "ecosystem": "python"}])
        assert _paths(_dep(result, "PyYAML")) == ["a.py", "b.py"]

    def test_rust_crate_boundary(self, tmp_path: Path) -> None:
        _write(tmp_path / "src" / "a.rs", "use serde::Deserialize;\n")
        _write(tmp_path / "src" / "b.rs", "use serde_json::Value;\n")
        _write(tmp_path / "src" / "c.rs", "fn f() { let v = serde_json::to_string(&x); }\n")
        result = _count(
            tmp_path,
            [{"name": "serde", "ecosystem": "rust"}, {"name": "serde_json", "ecosystem": "rust"}],
        )
        assert _paths(_dep(result, "serde")) == ["src/a.rs"]
        assert _paths(_dep(result, "serde_json")) == ["src/b.rs", "src/c.rs"]

    def test_go_module_prefix_boundary(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.go", 'package a\n\nimport "github.com/acme/kit/log"\n')
        _write(tmp_path / "b.go", 'package b\n\nimport "github.com/acme/kitchen"\n')
        result = _count(tmp_path, [{"name": "github.com/acme/kit", "ecosystem": "go"}])
        assert _paths(_dep(result, "github.com/acme/kit")) == ["a.go"]

    def test_longest_import_name_wins(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "from opentelemetry import trace\n")
        _write(tmp_path / "b.py", "from opentelemetry.sdk.trace import TracerProvider\n")
        result = _count(
            tmp_path,
            [
                {"name": "opentelemetry-api", "ecosystem": "python"},
                {"name": "opentelemetry-sdk", "ecosystem": "python"},
            ],
        )
        assert _paths(_dep(result, "opentelemetry-api")) == ["a.py"]
        assert _paths(_dep(result, "opentelemetry-sdk")) == ["b.py"]

    def test_ecosystem_limits_the_languages_read(self, tmp_path: Path) -> None:
        # a Python module named like an npm package does not count for it
        _write(tmp_path / "a.py", "import lodash\n")
        result = _count(tmp_path, [{"name": "lodash", "ecosystem": "npm"}])
        assert _dep(result, "lodash")["file_count"] == 0


# --------------------------------------------------------------------------
# Distribution-to-import names
# --------------------------------------------------------------------------


class TestImportNames:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("PyYAML", ["yaml"]),
            ("pyyaml", ["yaml"]),
            ("Pillow", ["PIL"]),
            ("beautifulsoup4", ["bs4"]),
            ("scikit-learn", ["sklearn"]),
            ("python-dateutil", ["dateutil"]),
            ("types-PyYAML", ["yaml"]),
        ],
    )
    def test_python_mapped(self, name: str, expected: list[str], tmp_path: Path) -> None:
        assert mod.import_names(name, "python", tmp_path) == (expected, "mapped")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("google-cloud-storage", ["google.cloud.storage"]),
            ("google-cloud-bigquery-storage", ["google.cloud.bigquery_storage"]),
            ("azure-storage-blob", ["azure.storage.blob"]),
            ("opentelemetry-sdk", ["opentelemetry.sdk"]),
            ("zope.interface", ["zope.interface"]),
        ],
    )
    def test_python_namespace_families_are_guesses(
        self, name: str, expected: list[str], tmp_path: Path
    ) -> None:
        # a rule, not a table entry: google-cloud-pubsub is imported as pubsub_v1
        assert mod.import_names(name, "python", tmp_path) == (expected, "guessed")

    def test_python_guess_keeps_case_and_tries_lower(self, tmp_path: Path) -> None:
        assert mod.import_names("Flask-SQLAlchemy", "python", tmp_path) == (
            ["Flask_SQLAlchemy", "flask_sqlalchemy"],
            "guessed",
        )
        assert mod.import_names("requests", "python", tmp_path) == (["requests"], "guessed")

    def test_npm_types_packages(self, tmp_path: Path) -> None:
        assert mod.import_names("@types/react", "npm", tmp_path) == (["react"], "guessed")
        assert mod.import_names("@types/babel__core", "npm", tmp_path) == (
            ["@babel/core"],
            "guessed",
        )
        assert mod.import_names("lodash", "npm", tmp_path) == (["lodash"], "exact")

    def test_rust_dash_becomes_underscore(self, tmp_path: Path) -> None:
        assert mod.import_names("tokio-util", "rust", tmp_path) == (["tokio_util"], "exact")

    def test_jvm_map_and_group_guess(self, tmp_path: Path) -> None:
        assert mod.import_names("com.google.guava:guava", "maven", tmp_path) == (
            ["com.google.common"],
            "mapped",
        )
        assert mod.import_names("io.ktor:ktor-server-core", "gradle", tmp_path) == (
            ["io.ktor"],
            "guessed",
        )
        assert mod.import_names("${project.groupId}:core", "maven", tmp_path) == ([], "guessed")

    def test_ruby_map_and_guess(self, tmp_path: Path) -> None:
        assert mod.import_names("activesupport", "ruby", tmp_path) == (
            ["active_support"],
            "mapped",
        )
        assert mod.import_names("net-http", "ruby", tmp_path) == (
            ["net-http", "net/http"],
            "guessed",
        )

    def test_composer_installed_metadata_wins(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "vendor" / "acme" / "widgets" / "composer.json",
            json.dumps({"autoload": {"psr-4": {"Acme\\Widgets\\": "src/"}}}),
        )
        assert mod.import_names("acme/widgets", "composer", tmp_path) == (
            ["Acme\\Widgets"],
            "exact",
        )
        assert mod.import_names("symfony/http-foundation", "composer", tmp_path) == (
            ["Symfony\\Component\\HttpFoundation"],
            "guessed",
        )
        assert mod.import_names("other/thing", "composer", tmp_path) == (
            ["Other\\Thing", "Other"],
            "guessed",
        )

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("symfony/console", "Symfony\\Component\\Console"),
            ("symfony/framework-bundle", "Symfony\\Bundle\\FrameworkBundle"),
            ("symfony/security-bundle", "Symfony\\Bundle\\SecurityBundle"),
            ("symfony/twig-bridge", "Symfony\\Bridge\\Twig"),
            ("symfony/security-core", "Symfony\\Component\\Security\\Core"),
            ("symfony/http-client-contracts", "Symfony\\Contracts\\HttpClient"),
            ("symfony/ux-turbo", "Symfony\\UX\\Turbo"),
            ("symfony/polyfill-mbstring", "Symfony\\Polyfill\\Mbstring"),
        ],
    )
    def test_symfony_naming_rules(self, name: str, expected: str, tmp_path: Path) -> None:
        assert mod.import_names(name, "composer", tmp_path) == ([expected], "guessed")

    def test_swift_map_and_guess(self, tmp_path: Path) -> None:
        assert mod.import_names("swift-log", "swift", tmp_path) == (["Logging"], "mapped")
        assert mod.import_names("swift-argument-parser", "swift", tmp_path)[0] == [
            "ArgumentParser"
        ]

    def test_pyyaml_counted_as_yaml(self, tmp_path: Path) -> None:
        _write(tmp_path / "app" / "config.py", "import yaml\n")
        _write(tmp_path / "app" / "load.py", "from yaml import safe_load\n")
        result = _count(tmp_path, [{"name": "PyYAML", "ecosystem": "python"}])
        entry = _dep(result, "PyYAML")
        assert entry["import_names"] == ["yaml"]
        assert entry["resolution"] == "mapped"
        assert entry["file_count"] == 2
        assert entry["above_threshold"] is True
        assert result["unresolved"] == []

    def test_from_package_import_submodule(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "from google.cloud import storage, bigquery\n")
        result = _count(tmp_path, [{"name": "google-cloud-storage", "ecosystem": "python"}])
        assert _paths(_dep(result, "google-cloud-storage")) == ["a.py"]

    def test_explicit_modules_skip_the_rules(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "import internal_sdk.client\n")
        result = _count(
            tmp_path,
            [{"name": "acme-sdk", "ecosystem": "python", "modules": ["internal_sdk"]}],
        )
        entry = _dep(result, "acme-sdk")
        assert entry["resolution"] == "explicit"
        assert entry["import_names"] == ["internal_sdk"]
        assert _paths(entry) == ["a.py"]


# --------------------------------------------------------------------------
# unresolved[]
# --------------------------------------------------------------------------


class TestUnresolved:
    def test_unmatched_guess_is_unresolved_not_zero(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "import requests\n")
        result = _count(
            tmp_path,
            [
                {"name": "requests", "ecosystem": "python"},
                {"name": "gunicorn", "ecosystem": "python"},
            ],
        )
        assert _dep(result, "requests")["resolution"] == "guessed"
        assert result["unresolved"] == [
            {
                "name": "gunicorn",
                "ecosystem": "python",
                "import_names": ["gunicorn"],
                "reason": "guess-unmatched",
            }
        ]
        assert "gunicorn" not in [d["name"] for d in result["dependencies"]]

    def test_rule_built_names_that_match_nothing_are_unresolved(self, tmp_path: Path) -> None:
        # each rule builds a name no file imports, so none of them counts 0
        _write(tmp_path / "app" / "publish.py", "from google.cloud import pubsub_v1\n")
        _write(tmp_path / "web" / "read.ts", "import { readFile } from 'node:fs';\n")
        _write(
            tmp_path / "src" / "Kernel.php",
            "<?php\nuse Symfony\\Component\\HttpKernel\\Kernel as BaseKernel;\n",
        )
        _write(
            tmp_path / "src" / "Twig" / "Ui.php",
            "<?php\nuse Symfony\\UX\\StimulusBundle\\Helper\\StimulusHelper;\n",
        )
        result = _count(
            tmp_path,
            [
                {"name": "google-cloud-pubsub", "ecosystem": "python"},
                {"name": "@types/node", "ecosystem": "npm"},
                {"name": "symfony/framework-bundle", "ecosystem": "composer"},
                {"name": "symfony/stimulus-bundle", "ecosystem": "composer"},
            ],
        )
        assert result["dependencies"] == []
        assert [(u["name"], u["import_names"], u["reason"]) for u in result["unresolved"]] == [
            ("@types/node", ["node"], "guess-unmatched"),
            ("google-cloud-pubsub", ["google.cloud.pubsub"], "guess-unmatched"),
            (
                "symfony/framework-bundle",
                ["Symfony\\Bundle\\FrameworkBundle"],
                "guess-unmatched",
            ),
            (
                "symfony/stimulus-bundle",
                ["Symfony\\Bundle\\StimulusBundle"],
                "guess-unmatched",
            ),
        ]

    def test_symfony_bundle_counted_without_vendor(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "src" / "Controller" / "HomeController.php",
            "<?php\n"
            "use Symfony\\Bundle\\FrameworkBundle\\Controller\\AbstractController;\n"
            "use Symfony\\Component\\Security\\Core\\User\\UserInterface;\n",
        )
        result = _count(
            tmp_path,
            [
                {"name": "symfony/framework-bundle", "ecosystem": "composer"},
                {"name": "symfony/security-core", "ecosystem": "composer"},
            ],
        )
        bundle = _dep(result, "symfony/framework-bundle")
        assert bundle["resolution"] == "guessed"
        assert bundle["files"] == [{"path": "src/Controller/HomeController.php", "line": 2}]
        security = _dep(result, "symfony/security-core")
        assert security["files"] == [{"path": "src/Controller/HomeController.php", "line": 3}]
        assert result["unresolved"] == []

    def test_exact_name_with_no_import_counts_zero(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "export const x = 1;\n")
        result = _count(tmp_path, [{"name": "typescript", "ecosystem": "npm"}])
        entry = _dep(result, "typescript")
        assert entry["file_count"] == 0
        assert entry["files"] == []
        assert entry["above_threshold"] is False
        assert result["unresolved"] == []

    def test_no_import_name(self, tmp_path: Path) -> None:
        result = _count(tmp_path, [{"name": "${project.groupId}:core", "ecosystem": "maven"}])
        assert result["unresolved"][0]["reason"] == "no-import-name"

    def test_unsupported_ecosystem(self, tmp_path: Path) -> None:
        result = _count(tmp_path, [{"name": "Newtonsoft.Json", "ecosystem": "nuget"}])
        assert result["unresolved"] == [
            {
                "name": "Newtonsoft.Json",
                "ecosystem": "nuget",
                "import_names": [],
                "reason": "unsupported-ecosystem",
            }
        ]

    def test_unresolved_sorted_by_name(self, tmp_path: Path) -> None:
        result = _count(
            tmp_path,
            [{"name": "zzz-tool", "ecosystem": "python"}, {"name": "aaa-tool", "ecosystem": "python"}],
        )
        assert _unresolved_names(result) == ["aaa-tool", "zzz-tool"]


# --------------------------------------------------------------------------
# Exclusion globs
# --------------------------------------------------------------------------


class TestExcludes:
    def test_default_exclusions(self, tmp_path: Path) -> None:
        counted = ["src/a.ts", "src/b.ts"]
        excluded = [
            "src/a.test.ts",
            "src/a.spec.ts",
            "src/__tests__/c.ts",
            "test/d.ts",
            "tests/e.ts",
            "spec/f.ts",
            "vite.config.ts",
            ".eslintrc.js",
            ".storybook/main.ts",
            "node_modules/react/index.js",
            "dist/bundle.js",
            "build/out.js",
            "out/x.js",
            "vendor/lib.js",
        ]
        for rel in counted + excluded:
            _write(tmp_path / rel, "import React from 'react';\n")
        result = _count(tmp_path, [{"name": "react", "ecosystem": "npm"}])
        assert _paths(_dep(result, "react")) == counted
        assert result["files_scanned"] == len(counted)

    def test_python_test_and_build_files_excluded(self, tmp_path: Path) -> None:
        for rel in ("pkg/core.py", "pkg/test_core.py", "pkg/core_test.py", "conftest.py",
                    "setup.py", "noxfile.py", "pkg/__pycache__/x.py", "venv/lib/y.py"):
            _write(tmp_path / rel, "import yaml\n")
        result = _count(tmp_path, [{"name": "PyYAML", "ecosystem": "python"}])
        assert _paths(_dep(result, "PyYAML")) == ["pkg/core.py"]

    @pytest.mark.parametrize("examples", ["examples/", "./examples/", "./examples/**"])
    def test_extra_excludes(self, tmp_path: Path, examples: str) -> None:
        for rel in ("src/a.ts", "examples/b.ts", "src/legacy/old/c.ts", "src/d.stories.tsx"):
            _write(tmp_path / rel, "import React from 'react';\n")
        result = _count(
            tmp_path,
            [{"name": "react", "ecosystem": "npm"}],
            extra_excludes=[examples, "src/legacy/**", "*.stories.tsx"],
        )
        assert _paths(_dep(result, "react")) == ["src/a.ts"]

    def test_leading_slash_or_dot_slash_anchors_to_the_root(self) -> None:
        excludes = mod.Excludes(["./gen/", "/tmp/", "./*.min.js", "./"])
        assert excludes.skip_dir("gen", "gen")
        assert not excludes.skip_dir("gen", "src/gen")
        assert excludes.skip_dir("tmp", "tmp")
        assert not excludes.skip_dir("tmp", "a/tmp")
        assert excludes.skip_file("a.min.js", "a.min.js")
        assert not excludes.skip_file("a.min.js", "lib/a.min.js")
        # `./` alone names the root itself, which is never skipped
        assert not excludes.skip_dir("src", "src")

    def test_glob_semantics(self) -> None:
        excludes = mod.Excludes(["build/", "src/gen/", "*.min.js", "src/*.tmp.ts", "docs/**/x.ts"])
        assert excludes.skip_dir("build", "a/b/build")
        assert excludes.skip_dir("gen", "src/gen")
        assert not excludes.skip_dir("gen", "lib/gen")
        assert excludes.skip_file("app.min.js", "deep/app.min.js")
        assert excludes.skip_file("a.tmp.ts", "src/a.tmp.ts")
        # `*` stays inside one directory
        assert not excludes.skip_file("a.tmp.ts", "src/sub/a.tmp.ts")
        # `**/` spans zero or more directories
        assert excludes.skip_file("x.ts", "docs/x.ts")
        assert excludes.skip_file("x.ts", "docs/a/b/x.ts")

    def test_symlinks_not_followed(self, tmp_path: Path) -> None:
        _write(tmp_path / "src" / "a.ts", "import React from 'react';\n")
        try:
            (tmp_path / "linked").symlink_to(tmp_path / "src", target_is_directory=True)
            (tmp_path / "b.ts").symlink_to(tmp_path / "src" / "a.ts")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        result = _count(tmp_path, [{"name": "react", "ecosystem": "npm"}])
        assert _paths(_dep(result, "react")) == ["src/a.ts"]

    def test_documented_exclusions_match_the_script(self) -> None:
        text = MANIFEST_PATTERNS.read_text(encoding="utf-8")
        section = text.split("## Import Counting", 1)[1].split("\n## ", 1)[0]
        listed = section.split("Excluded paths", 1)[1]
        documented = [
            glob
            for line in listed.splitlines()
            if line.startswith("- ")
            for glob in re.findall(r"`([^`]+)`", line)
        ]
        assert sorted(documented) == sorted(mod.DEFAULT_EXCLUDES)
        assert len(documented) == len(set(documented))


# --------------------------------------------------------------------------
# Output shape
# --------------------------------------------------------------------------


class TestOutput:
    def test_sorted_by_file_count(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "import 'zod';\nimport 'axios';\nimport 'lodash';\n")
        _write(tmp_path / "b.ts", "import 'zod';\nimport 'axios';\n")
        _write(tmp_path / "c.ts", "import 'zod';\n")
        result = _count(
            tmp_path,
            [{"name": n, "ecosystem": "npm"} for n in ("lodash", "zod", "axios", "express")],
        )
        assert [(d["name"], d["file_count"], d["above_threshold"]) for d in result["dependencies"]] == [
            ("zod", 3, True),
            ("axios", 2, True),
            ("lodash", 1, False),
            ("express", 0, False),
        ]

    def test_tie_breaks_on_name(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "import 'beta';\nimport 'alpha';\n")
        _write(tmp_path / "b.ts", "import 'alpha';\nimport 'beta';\n")
        result = _count(
            tmp_path,
            [{"name": "beta", "ecosystem": "npm"}, {"name": "alpha", "ecosystem": "npm"}],
        )
        assert [(d["name"], d["file_count"]) for d in result["dependencies"]] == [
            ("alpha", 2),
            ("beta", 2),
        ]

    def test_files_once_each_with_first_line(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "src" / "b.ts",
            "// header\nimport React from 'react';\nimport { useState } from 'react';\n",
        )
        _write(tmp_path / "src" / "a.ts", "const x = 1;\nconst r = require('react');\n")
        result = _count(tmp_path, [{"name": "react", "ecosystem": "npm"}])
        assert _dep(result, "react")["files"] == [
            {"path": "src/a.ts", "line": 2},
            {"path": "src/b.ts", "line": 2},
        ]

    def test_threshold(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "import 'zod';\n")
        _write(tmp_path / "b.ts", "import 'zod';\n")
        deps = [{"name": "zod", "ecosystem": "npm"}]
        assert _dep(_count(tmp_path, deps), "zod")["above_threshold"] is True
        assert _dep(_count(tmp_path, deps, threshold=3), "zod")["above_threshold"] is False
        result = _count(tmp_path, deps, threshold=3)
        assert result["threshold"] == 3

    def test_scope_dev_passes_through_and_runtime_wins(self, tmp_path: Path) -> None:
        envelope = {
            "manifests": [
                {"path": "package.json", "ecosystem": "npm",
                 "deps": [{"name": "vitest", "version": "1", "scope": "dev"},
                          {"name": "zod", "version": "3", "scope": "dev"}]},
                {"path": "packages/a/package.json", "ecosystem": "npm",
                 "deps": [{"name": "zod", "version": "3"}]},
            ]
        }
        result = _count(tmp_path, envelope)
        assert _dep(result, "vitest")["scope"] == "dev"
        assert "scope" not in _dep(result, "zod")

    def test_empty_tree(self, tmp_path: Path) -> None:
        result = _count(tmp_path, [{"name": "react", "ecosystem": "npm"}])
        assert result == {
            "threshold": 2,
            "files_scanned": 0,
            "dependencies": [
                {
                    "name": "react",
                    "ecosystem": "npm",
                    "import_names": ["react"],
                    "resolution": "exact",
                    "files": [],
                    "file_count": 0,
                    "above_threshold": False,
                }
            ],
            "unresolved": [],
        }


# --------------------------------------------------------------------------
# Import extraction per language
# --------------------------------------------------------------------------


# A Python 2 print statement: `ast` rejects the file, so it is read line by line.
PY2_TAIL = 'print "done"\n'


def _modules(language: str, text: str, rel: str = "src/file") -> list[tuple[int, str]]:
    return [(n, v) for n, kind, v in mod.extract_records(language, text, rel) if kind == "module"]


def _rel_paths(language: str, text: str, rel: str) -> list[tuple[int, str]]:
    return [(n, v) for n, kind, v in mod.extract_records(language, text, rel) if kind == "path"]


class TestExtraction:
    def test_js_forms(self) -> None:
        text = (
            "import React, { useState } from 'react';\n"
            "import 'side-effect';\n"
            "export * from \"re-export\";\n"
            "const lazy = () => import('dynamic');\n"
            "const cjs = require(`required`);\n"
            "import type { T } from 'types-only';\n"
            "// import commented from 'commented';\n"
            " * import doc from 'jsdoc';\n"
            "const s = Array.from('not-an-import');\n"
            "const t = import(`./locale/${lang}`);\n"
            "import abs from '/absolute';\n"
        )
        assert _modules("js", text) == [
            (1, "react"),
            (2, "side-effect"),
            (3, "re-export"),
            (4, "dynamic"),
            (5, "required"),
            (6, "types-only"),
        ]

    def test_js_relative_imports_resolve(self) -> None:
        text = "import a from './a';\nimport b from '../lib/b';\nimport c from '../../../out';\n"
        assert _rel_paths("js", text, "src/app/x.ts") == [(1, "src/app/a"), (2, "src/lib/b")]

    @pytest.mark.parametrize("tail", ["", PY2_TAIL])
    def test_python_forms(self, tail: str) -> None:
        text = (
            '"""Module docstring\n'
            "import not_real\n"
            '"""\n'
            "import os, yaml as y\n"
            "import a.b.c\n"
            "from pkg import (\n"
            "    one,\n"
            "    two as deux,\n"
            ")\n"
            "# import commented\n"
            "mod = importlib.import_module('dyn.mod')\n"
            "if TYPE_CHECKING:\n"
            "    from typing_extensions import Self\n"
        ) + tail
        assert _modules("python", text) == [
            (4, "os"),
            (4, "yaml"),
            (5, "a.b.c"),
            (6, "pkg"),
            (6, "pkg.one"),
            (6, "pkg.two"),
            (11, "dyn.mod"),
            (13, "typing_extensions"),
            (13, "typing_extensions.Self"),
        ]

    def test_python_relative_imports_resolve(self) -> None:
        text = "from . import sibling\nfrom ..core import engine\nfrom ... import too_far\n"
        assert _rel_paths("python", text, "pkg/sub/mod.py") == [
            (1, "pkg/sub"),
            (1, "pkg/sub/sibling"),
            (2, "pkg/core"),
            (2, "pkg/core/engine"),
            (3, ""),
            (3, "too_far"),
        ]
        assert _rel_paths("python", "from .... import x\n", "pkg/sub/mod.py") == []

    @pytest.mark.parametrize("tail", ["", PY2_TAIL])
    def test_python_hash_inside_a_string_is_not_a_comment(self, tail: str) -> None:
        text = '"""Fix #12."""\nimport yaml\nfrom . import sibling\n' + tail
        assert _modules("python", text) == [(2, "yaml")]
        assert _rel_paths("python", text, "pkg/mod.py") == [(3, "pkg"), (3, "pkg/sibling")]
        text = (
            'punctuation = r"""!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~"""\n'
            "from x import y\n"
            "s = '# not a comment'; import z  # import commented\n"
        ) + tail
        assert _modules("python", text) == [(2, "x"), (2, "x.y"), (3, "z")]

    def test_python_parser_reads_what_lines_split(self) -> None:
        text = (
            "import a, \\\n"
            "    b\n"
            "def f():\n"
            "    import c\n"
            "x = 'import not_real'\n"
        )
        assert _modules("python", text) == [(1, "a"), (1, "b"), (4, "c")]

    def test_python_file_over_the_ast_limit_is_read_line_by_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = "import yaml\n"
        monkeypatch.setattr(mod, "_python_line_records", lambda text, base: [(1, "module", "line")])
        assert _modules("python", text) == [(1, "yaml")]
        monkeypatch.setattr(mod, "PYTHON_AST_MAX_CHARS", len(text) - 1)
        assert _modules("python", text) == [(1, "line")]

    def test_line_numbers_count_newlines_only(self) -> None:
        # str.splitlines would also break at the form feed and at U+2028
        assert _modules("python", "import a\n\x0cimport b\n") == [(1, "a"), (2, "b")]
        assert _modules("js", "// a\x0c b\u2028 c\nimport d from 'd';\n") == [(2, "d")]

    def test_rust_forms(self) -> None:
        text = (
            "use serde::{Deserialize, Serialize};\n"
            "pub(crate) use tokio::sync;\n"
            "extern crate log;\n"
            "// use commented::x;\n"
            "fn f() { anyhow::bail!(\"x\") }\n"
        )
        modules = _modules("rust", text)
        assert (1, "serde") in modules
        assert (2, "tokio::sync") in modules
        assert (3, "log") in modules
        assert (5, "anyhow::bail") in modules
        assert not any(v.startswith("commented") for _, v in modules)

    def test_go_forms(self) -> None:
        text = (
            "package main\n\n"
            'import "fmt"\n'
            "import (\n"
            '    "net/http"\n'
            '    gin "github.com/gin-gonic/gin"\n'
            '    _ "github.com/lib/pq"\n'
            "    // \"commented/out\"\n"
            ")\n"
            'var s = "not/an/import"\n'
        )
        assert _modules("go", text) == [
            (3, "fmt"),
            (5, "net/http"),
            (6, "github.com/gin-gonic/gin"),
            (7, "github.com/lib/pq"),
        ]

    def test_jvm_forms(self) -> None:
        text = (
            "import com.google.common.collect.ImmutableList;\n"
            "import static org.junit.Assert.*;\n"
            "import kotlinx.coroutines.flow.Flow as F\n"
        )
        assert _modules("jvm", text) == [
            (1, "com.google.common.collect.ImmutableList"),
            (2, "org.junit.Assert"),
            (3, "kotlinx.coroutines.flow.Flow"),
        ]

    def test_ruby_forms(self) -> None:
        text = "require 'active_support/core_ext'\nrequire_relative '../lib/helper'\n"
        assert _modules("ruby", text, "app/models/user.rb") == [(1, "active_support/core_ext")]
        assert _rel_paths("ruby", text, "app/models/user.rb") == [(2, "app/lib/helper")]

    def test_php_forms_and_case_insensitive_match(self, tmp_path: Path) -> None:
        text = (
            "<?php\n"
            "use GuzzleHttp\\Client;\n"
            "use Symfony\\Component\\Console\\{Command, Input};\n"
            "use function Monolog\\log_it;\n"
        )
        assert _modules("php", text) == [
            (2, "GuzzleHttp\\Client"),
            (3, "Symfony\\Component\\Console"),
            (4, "Monolog\\log_it"),
        ]
        _write(tmp_path / "src" / "a.php", "<?php\nuse guzzlehttp\\Client;\n")
        result = _count(tmp_path, [{"name": "guzzlehttp/guzzle", "ecosystem": "composer"}])
        assert _paths(_dep(result, "guzzlehttp/guzzle")) == ["src/a.php"]

    def test_swift_forms(self) -> None:
        text = "import Foundation\n@testable import MyLib\nimport struct NIOCore.ByteBuffer\n"
        assert _modules("swift", text) == [(1, "Foundation"), (2, "MyLib"), (3, "NIOCore")]


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------


def _monorepo(root: Path) -> list[dict]:
    _write(
        root / "packages" / "core" / "src" / "index.ts",
        "import { c } from '@acme/client';\nimport { h } from './helper';\n",
    )
    _write(
        root / "packages" / "client" / "src" / "index.ts",
        "import { core } from '@acme/core';\nimport { z } from 'zod';\n",
    )
    _write(
        root / "packages" / "server" / "src" / "index.ts",
        "import { core } from '@acme/core/sub';\n"
        "import { client } from '../../client/src/index';\n"
        "import { z } from 'zod';\n",
    )
    _write(
        root / "app" / "main.ts",
        "import { core } from '@acme/core';\n"
        "import { client } from '@acme/client';\n"
        "import { server } from '../packages/server/src';\n",
    )
    return [
        {"name": "core", "path": "packages/core", "modules": ["@acme/core"], "ecosystem": "npm"},
        {"name": "client", "path": "packages/client", "modules": ["@acme/client"]},
        {"name": "server", "path": "./packages/server/"},
    ]


class TestUnits:
    def test_graph(self, tmp_path: Path) -> None:
        units = _monorepo(tmp_path)
        result = _count(tmp_path, [{"name": "zod", "ecosystem": "npm"}], units=units)
        assert result["edges"] == [
            ["client", "core"],
            ["core", "client"],
            ["server", "client"],
            ["server", "core"],
        ]
        by_name = {u["name"]: u for u in result["units"]}
        assert by_name["core"]["imported_by"] == ["client", "server"]
        assert by_name["core"]["imports_from"] == ["client"]
        assert by_name["server"]["path"] == "packages/server"
        assert by_name["server"]["imported_by"] == []
        assert by_name["server"]["imports_from"] == ["client", "core"]
        assert by_name["server"]["external_deps"] == ["zod"]
        # a unit's own files never import it; files outside every unit count
        assert _paths(by_name["core"]) == [
            "app/main.ts",
            "packages/client/src/index.ts",
            "packages/server/src/index.ts",
        ]
        assert by_name["server"]["files"] == [{"path": "app/main.ts", "line": 3}]
        assert [u["name"] for u in result["units"]] == ["client", "core", "server"]

    def test_edge_files_name_the_importing_files(self, tmp_path: Path) -> None:
        result = _count(tmp_path, [], units=_monorepo(tmp_path))
        edge_files = {(e["from"], e["to"]): e["files"] for e in result["edge_files"]}
        assert list(edge_files) == [tuple(edge) for edge in result["edges"]]
        assert edge_files[("server", "client")] == [
            {"path": "packages/server/src/index.ts", "line": 2}]
        assert edge_files[("client", "core")] == [
            {"path": "packages/client/src/index.ts", "line": 1}]
        # app/main.ts belongs to no unit: it imports units but is no edge
        assert all(f["path"] != "app/main.ts" for files in edge_files.values() for f in files)

    def test_nested_unit_files_are_their_own(self, tmp_path: Path) -> None:
        """A file of a unit nested in another is the inner unit's edge only."""
        _write(tmp_path / "lib" / "core" / "a.ts", "export const a = 1;\n")
        _write(tmp_path / "lib" / "inner" / "b.ts", "import { a } from '../core/a';\n")
        _write(tmp_path / "lib" / "c.ts", "import { a } from './core/a';\n")
        units = [{"name": "lib", "path": "lib"}, {"name": "inner", "path": "lib/inner"},
                 {"name": "core", "path": "lib/core"}]
        result = _count(tmp_path, [], units=units)
        edge_files = {(e["from"], e["to"]): _paths(e) for e in result["edge_files"]}
        assert edge_files == {("inner", "core"): ["lib/inner/b.ts"],
                              ("lib", "core"): ["lib/c.ts"]}

    def test_manifest_name_gives_the_import_names(self, tmp_path: Path) -> None:
        _write(tmp_path / "crates" / "core-lib" / "src" / "lib.rs", "pub fn f() {}\n")
        _write(tmp_path / "crates" / "app" / "src" / "main.rs", "use core_lib::f;\n")
        _write(tmp_path / "web" / "index.ts", "import { x } from '@acme/ui/button';\n")
        _write(tmp_path / "ui" / "index.ts", "export const x = 1;\n")
        _write(tmp_path / "svc" / "main.go", 'import "example.com/acme/pkg/util"\n')
        _write(tmp_path / "pkg" / "util.go", "package util\n")
        units = [
            {"name": "core-lib", "path": "crates/core-lib", "manifest_name": "core-lib",
             "ecosystem": "rust"},
            {"name": "app", "path": "crates/app", "manifest_name": "app", "ecosystem": "rust"},
            {"name": "ui", "path": "ui", "manifest_name": "@acme/ui", "ecosystem": "npm"},
            {"name": "web", "path": "web", "manifest_name": "@acme/web", "ecosystem": "npm"},
            {"name": "pkg", "path": "pkg", "manifest_name": "example.com/acme/pkg",
             "ecosystem": "go"},
            {"name": "svc", "path": "svc", "manifest_name": "example.com/acme/svc",
             "ecosystem": "go"},
        ]
        result = _count(tmp_path, [], units=units)
        assert result["edges"] == [["app", "core-lib"], ["svc", "pkg"], ["web", "ui"]]
        by_name = {u["name"]: u for u in result["units"]}
        assert by_name["core-lib"]["import_names"] == ["core_lib"]
        # explicit modules win, and an explicit [] reaches by relative imports only
        units[2]["modules"] = []
        assert ["web", "ui"] not in _count(tmp_path, [], units=units)["edges"]

    def test_jvm_units_are_imported_by_the_packages_they_declare(self, tmp_path: Path) -> None:
        """Two modules of one Maven group: the group alone would bind both."""
        java = "src/main/java/com/acme"
        _write(tmp_path / "core" / java / "core" / "Graph.java", "package com.acme.core;\n")
        _write(tmp_path / "core" / java / "core" / "util" / "Ids.java",
               "// ids\npackage com.acme.core.util;\n")
        _write(tmp_path / "api" / java / "api" / "Server.kt",
               "package com.acme.api\n\nimport com.acme.core.util.Ids\n")
        _write(tmp_path / "core" / "src" / "test" / "java" / "GraphTest.java",
               "package com.acme.coretest;\n")
        units = [
            {"name": "core", "path": "core", "manifest_name": "com.acme:core", "ecosystem": "maven"},
            {"name": "api", "path": "api", "ecosystem": "gradle"},
        ]
        result = _count(tmp_path, [], units=units)
        by_name = {u["name"]: u for u in result["units"]}
        assert by_name["core"]["import_names"] == ["com.acme.core", "com.acme.core.util"]
        assert by_name["api"]["import_names"] == ["com.acme.api"]
        assert result["edges"] == [["api", "core"]]

    def test_composer_and_swift_units_declare_their_names(self, tmp_path: Path) -> None:
        _write(tmp_path / "auth" / "composer.json",
               json.dumps({"name": "acme/auth", "autoload": {"psr-4": {"Acme\\Auth\\": "src/"}}}))
        _write(tmp_path / "auth" / "src" / "Guard.php", "<?php\nnamespace Acme\\Auth;\n")
        _write(tmp_path / "web" / "index.php", "<?php\nuse Acme\\Auth\\Guard;\n")
        _write(tmp_path / "kit" / "Package.swift",
               'let package = Package(name: "Kit", targets: [\n'
               '  .target(name: "KitCore"),\n  .testTarget(name: "KitTests")])\n')
        _write(tmp_path / "kit" / "Sources" / "KitCore" / "A.swift", "public struct A {}\n")
        _write(tmp_path / "app" / "main.swift", "import KitCore\n")
        units = [
            {"name": "auth", "path": "auth", "manifest_name": "acme/auth", "ecosystem": "composer"},
            {"name": "web", "path": "web"},
            {"name": "kit", "path": "kit", "manifest_name": "Kit", "ecosystem": "swift"},
            {"name": "app", "path": "app"},
        ]
        result = _count(tmp_path, [], units=units)
        by_name = {u["name"]: u for u in result["units"]}
        assert by_name["auth"]["import_names"] == ["Acme\\Auth"]
        assert by_name["kit"]["import_names"] == ["KitCore"]
        assert result["edges"] == [["app", "kit"], ["web", "auth"]]

    def test_a_dependency_that_is_a_unit_is_not_external(self, tmp_path: Path) -> None:
        envelope = {"manifests": [
            {"path": "packages/core/package.json", "ecosystem": "npm",
             "name": "@acme/core", "deps": [{"name": "zod", "version": "3"}]},
            {"path": "packages/client/package.json", "ecosystem": "npm",
             "name": "@acme/client",
             "deps": [{"name": "@acme/core", "version": "*"}, {"name": "zod", "version": "3"}]},
        ]}
        _write(tmp_path / "packages" / "core" / "index.ts", "import { z } from 'zod';\n")
        _write(tmp_path / "packages" / "client" / "index.ts",
               "import { core } from '@acme/core';\nimport { z } from 'zod';\n")
        units = [
            {"name": "core", "path": "packages/core", "manifest_name": "@acme/core",
             "ecosystem": "npm"},
            {"name": "client", "path": "packages/client", "manifest_name": "@acme/client",
             "ecosystem": "npm"},
        ]
        result = _count(tmp_path, envelope, units=units)
        assert [d["name"] for d in result["dependencies"]] == ["zod"]
        by_name = {u["name"]: u for u in result["units"]}
        assert by_name["client"]["external_deps"] == ["zod"]
        assert by_name["client"]["imports_from"] == ["core"]

    def test_python_relative_unit_imports(self, tmp_path: Path) -> None:
        _write(tmp_path / "app" / "api" / "views.py", "from ..db import models\n")
        _write(tmp_path / "app" / "db" / "models.py", "from . import base\n")
        result = _count(
            tmp_path,
            [],
            units=[{"name": "api", "path": "app/api"}, {"name": "db", "path": "app/db"}],
        )
        assert result["edges"] == [["api", "db"]]

    def test_edges_pipe_into_find_cycles(self, tmp_path: Path) -> None:
        units = _monorepo(tmp_path)
        result = _count(tmp_path, [], units=units)
        proc = _run_helper("skf-find-cycles.py", "find", "--edges", "-", stdin=json.dumps(result))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["cycles"] == [["client", "core", "client"]]

    def test_libraries_pipe_into_pair_intersect(self, tmp_path: Path) -> None:
        units = _monorepo(tmp_path)
        units_file = _write(tmp_path / "units.json", json.dumps(units))
        proc = _run_cli("count", str(tmp_path), "--units", str(units_file), "--format", "libraries")
        assert proc.returncode == 0, proc.stderr
        libraries = json.loads(proc.stdout)
        assert [row["name"] for row in libraries] == ["client", "core", "server"]
        pairs = _run_helper("skf-pair-intersect.py", "intersect", "--libraries", "-", stdin=proc.stdout)
        assert pairs.returncode == 0, pairs.stderr
        first = json.loads(pairs.stdout)["pairs"][0]
        assert (first["a"], first["b"], first["intersection_count"]) == ("client", "core", 2)

    @pytest.mark.parametrize(
        ("units", "message"),
        [
            ([{"name": "a", "path": "x"}, {"name": "a", "path": "y"}], "repeats unit name"),
            ([{"name": "a", "path": "x"}, {"name": "b", "path": "./x/"}], "repeats unit path"),
            ([{"name": "a", "path": "../outside"}], "leaves the root"),
            ([{"name": "a"}], "needs a `path`"),
            ([{"name": "a", "path": "x", "modules": "nope"}], "list of non-empty strings"),
        ],
    )
    def test_invalid_units(self, units: list, message: str) -> None:
        with pytest.raises(mod.InputError, match=re.escape(message)):
            mod.parse_units(units)


# --------------------------------------------------------------------------
# Input parsing
# --------------------------------------------------------------------------


class TestParseDependencies:
    def test_manifests_envelope(self) -> None:
        envelope = {
            "manifests": [
                {"path": "requirements.txt", "ecosystem": "python",
                 "deps": [{"name": "PyYAML", "version": None},
                          {"name": "<unparsable>", "version": None}]},
                {"path": "pyproject.toml", "ecosystem": "python",
                 "deps": [{"name": "pyyaml", "version": ">=6"}]},
            ]
        }
        assert mod.parse_dependencies(envelope) == [
            {"name": "PyYAML", "ecosystem": "python", "scope": "runtime"}
        ]

    def test_names_and_objects(self) -> None:
        deps = mod.parse_dependencies({"dependencies": ["react", {"name": "zod", "ecosystem": "npm"}]})
        assert deps == [
            {"name": "react", "ecosystem": None, "scope": "runtime"},
            {"name": "zod", "ecosystem": "npm", "scope": "runtime"},
        ]

    def test_no_ecosystem_matches_every_language(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.ts", "import React from 'react';\n")
        _write(tmp_path / "b.py", "import react\n")
        result = _count(tmp_path, ["react"])
        entry = _dep(result, "react")
        assert entry["ecosystem"] is None
        assert entry["resolution"] == "guessed"
        assert _paths(entry) == ["a.ts", "b.py"]

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"other": []}, "JSON array"),
            ([{"version": "1"}], "non-empty `name`"),
            ([42], "name string or an object"),
            ([{"name": "x", "scope": "test"}], "`scope` must be"),
            ([{"name": "x", "ecosystem": ""}], "`ecosystem` must be"),
            ({"manifests": {}}, "`manifests` must be a list"),
        ],
    )
    def test_invalid(self, payload: object, message: str) -> None:
        with pytest.raises(mod.InputError, match=re.escape(message)):
            mod.parse_dependencies(payload)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    def test_deps_file(self, tmp_path: Path) -> None:
        _write(tmp_path / "src" / "a.ts", "import 'zod';\n")
        deps = _write(tmp_path / "deps.json", json.dumps(["zod"]))
        proc = _run_cli("count", str(tmp_path), "--deps", str(deps))
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["dependencies"][0]["files"] == [{"path": "src/a.ts", "line": 1}]

    def test_deps_stdin(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "import yaml\n")
        proc = _run_cli(
            "count", str(tmp_path), "--deps", "-",
            stdin=json.dumps([{"name": "PyYAML", "ecosystem": "python"}]),
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["dependencies"][0]["file_count"] == 1

    def test_scan_manifests_output_pipes_in(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"react": "^18", "react-dom": "^18"}}),
        )
        _write(tmp_path / "src" / "a.tsx", "import React from 'react';\n")
        _write(tmp_path / "src" / "b.tsx", "import React from 'react';\n")
        scan = _run_helper("skf-scan-manifests.py", "scan", str(tmp_path), stdin="")
        assert scan.returncode == 0, scan.stderr
        proc = _run_cli("count", str(tmp_path), "--deps", "-", stdin=scan.stdout)
        assert proc.returncode == 0, proc.stderr
        counts = {d["name"]: d["file_count"] for d in json.loads(proc.stdout)["dependencies"]}
        assert counts == {"react": 2, "react-dom": 0}

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--deps", "-", "--units", "-"], "only one of --deps and --units"),
            ([], "pass --deps, --units or both"),
            (["--deps", "missing.json"], "file not found"),
            (["--deps", "-", "--threshold", "-1"], "--threshold must be >= 0"),
        ],
    )
    def test_user_errors_exit_1(self, tmp_path: Path, args: list[str], message: str) -> None:
        proc = _run_cli("count", str(tmp_path), *args, stdin="[]")
        assert proc.returncode == 1
        assert message in proc.stderr

    def test_python_parse_warnings_stay_off_stderr(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", 'PATTERN = "\\d+"\nimport yaml\n')
        proc = _run_cli(
            "count", str(tmp_path), "--deps", "-",
            stdin=json.dumps([{"name": "PyYAML", "ecosystem": "python"}]),
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == ""
        assert json.loads(proc.stdout)["dependencies"][0]["file_count"] == 1

    def test_malformed_json_exits_1(self, tmp_path: Path) -> None:
        proc = _run_cli("count", str(tmp_path), "--deps", "-", stdin="{not json")
        assert proc.returncode == 1
        assert "malformed JSON" in proc.stderr

    def test_bad_root_exits_1(self, tmp_path: Path) -> None:
        proc = _run_cli("count", str(tmp_path / "missing"), "--deps", "-", stdin="[]")
        assert proc.returncode == 1
        assert "root not a directory" in proc.stderr

    def test_subcommand_required(self) -> None:
        assert _run_cli().returncode != 0


# --------------------------------------------------------------------------
# --relative-to: one package scanned, project-relative paths written
# --------------------------------------------------------------------------


class TestRelativeTo:
    def _project(self, tmp_path: Path) -> Path:
        _write(tmp_path / "apps" / "web" / "src" / "a.tsx", "import React from 'react';\n")
        _write(tmp_path / "apps" / "web" / "src" / "b.tsx", "import 'react';\nimport './a';\n")
        return tmp_path

    def test_package_files_carry_the_project_path(self, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        web = project / "apps" / "web"
        units = json.dumps([{"name": "web", "path": "src"}])
        proc = _run_cli("count", str(web), "--deps", "-", "--units", str(_write(tmp_path / "u.json", units)),
                        "--relative-to", str(project), stdin=json.dumps([{"name": "react", "ecosystem": "npm"}]))
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert _paths(_dep(result, "react")) == ["apps/web/src/a.tsx", "apps/web/src/b.tsx"]
        (unit,) = result["units"]
        assert unit["path"] == "src", "a unit's path stays relative to the root"
        libraries = _run_cli("count", str(web), "--deps", "-", "--format", "libraries",
                             "--relative-to", str(project), stdin='["react"]')
        assert json.loads(libraries.stdout) == [
            {"name": "react", "files": ["apps/web/src/a.tsx", "apps/web/src/b.tsx"]}]

    def test_the_same_folder_changes_nothing(self, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        same = _run_cli("count", str(project), "--deps", "-", "--relative-to", str(project), stdin='["react"]')
        plain = _run_cli("count", str(project), "--deps", "-", stdin='["react"]')
        assert same.returncode == 0, same.stderr
        assert same.stdout == plain.stdout

    @pytest.mark.parametrize(
        ("base", "message"),
        [("apps/web/src", "is not inside --relative-to"), ("missing", "--relative-to not a directory")],
    )
    def test_a_folder_that_does_not_hold_the_root_exits_1(self, tmp_path: Path, base: str, message: str) -> None:
        project = self._project(tmp_path)
        proc = _run_cli("count", str(project / "apps" / "web"), "--deps", "-",
                        "--relative-to", str(project / base), stdin='["react"]')
        assert proc.returncode == 1
        assert message in proc.stderr

    def test_edge_files_move_too(self, tmp_path: Path) -> None:
        web = tmp_path / "apps" / "web"
        _write(web / "core" / "x.ts", "export const x = 1;\n")
        _write(web / "ui" / "y.ts", "import { x } from '../core/x';\n")
        units = [{"name": "core", "path": "core"}, {"name": "ui", "path": "ui"}]
        result = mod.prefix_paths(_count(web, [], units), "apps/web")
        assert result["edge_files"] == [
            {"from": "ui", "to": "core", "files": [{"path": "apps/web/ui/y.ts", "line": 1}]}]
        assert [_paths(u) for u in result["units"]] == [["apps/web/ui/y.ts"], []]
