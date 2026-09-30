#!/usr/bin/env python3
"""Tests for skf-scan-manifests.py.

Covers:
  - single-ecosystem repo: one package.json with 5 deps
  - multi-ecosystem repo: package.json + pyproject.toml side-by-side
  - monorepo: multiple package.json at sibling depths → monorepo=true
  - empty repo: zero manifests → graceful empty result
  - malformed manifests: emits warning, doesn't crash
  - excluded directories: node_modules / .venv / .git / dist are skipped
  - per-parser unit tests: each parser surfaces the canonical fields
  - CLI invocation: subprocess returns JSON with expected shape
  - package identity: each manifest's own name and private flag
  - internal_deps and umbrella_candidates across workspace members
  - --include-dev: development dependencies tagged scope: dev
  - searched_filenames, and manifest-patterns.md in skf-create-stack-skill
    kept equal to MANIFEST_ECOSYSTEMS and EXCLUDED_DIRS
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
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-scan-manifests.py"
MANIFEST_PATTERNS = (
    REPO_ROOT / "src" / "skf-create-stack-skill" / "references" / "manifest-patterns.md"
)

spec = importlib.util.spec_from_file_location("skf_scan_manifests", SCRIPT_PATH)
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


def _names(deps: list[dict]) -> list[str]:
    return [d["name"] for d in deps]


# --------------------------------------------------------------------------
# find_manifests
# --------------------------------------------------------------------------


class TestFindManifests:
    def test_finds_package_json(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", '{"name": "x"}')
        result = mod.find_manifests(tmp_path)
        assert len(result) == 1
        assert result[0].name == "package.json"

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", '{"name": "x"}')
        # nested manifest inside node_modules — must be ignored
        _write(tmp_path / "node_modules" / "foo" / "package.json", '{"name": "foo"}')
        result = mod.find_manifests(tmp_path)
        assert len(result) == 1
        assert result[0] == tmp_path / "package.json"

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / ".git" / "package.json", '{"name": "hidden"}')
        _write(tmp_path / ".github" / "package.json", '{"name": "ci"}')
        _write(tmp_path / "package.json", '{"name": "real"}')
        result = mod.find_manifests(tmp_path)
        assert len(result) == 1

    def test_skips_dist_and_target(self, tmp_path: Path) -> None:
        _write(tmp_path / "dist" / "package.json", '{"name": "built"}')
        _write(tmp_path / "target" / "Cargo.toml", "[package]\nname='built'\n")
        _write(tmp_path / "package.json", '{"name": "real"}')
        result = mod.find_manifests(tmp_path)
        assert len(result) == 1
        assert result[0].name == "package.json"

    def test_finds_nested_monorepo_manifests(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", '{"name": "root"}')
        _write(tmp_path / "packages" / "a" / "package.json", '{"name": "a"}')
        _write(tmp_path / "packages" / "b" / "package.json", '{"name": "b"}')
        result = mod.find_manifests(tmp_path)
        assert len(result) == 3

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert mod.find_manifests(tmp_path) == []


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


class TestPackageJsonParser:
    def test_extracts_dependencies(self) -> None:
        text = json.dumps(
            {
                "name": "x",
                "dependencies": {"react": "^18.0.0", "lodash": "4.17.21"},
                "devDependencies": {"jest": "^29.0.0"},
            }
        )
        deps, warnings = mod.parse_package_json(text)
        assert warnings == []
        assert sorted(_names(deps)) == ["lodash", "react"]
        assert {"name": "react", "version": "^18.0.0"} in deps

    def test_no_dependencies_key(self) -> None:
        deps, warnings = mod.parse_package_json('{"name": "x"}')
        assert deps == []
        assert warnings == []

    def test_malformed_json_emits_warning(self) -> None:
        deps, warnings = mod.parse_package_json("{not json")
        assert deps == []
        assert any("JSON parse failed" in w for w in warnings)

    def test_top_level_array_warns(self) -> None:
        deps, warnings = mod.parse_package_json("[1,2,3]")
        assert deps == []
        assert any("top-level is not an object" in w for w in warnings)


class TestPyprojectParser:
    def test_pep_621_dependencies(self) -> None:
        text = """
[project]
name = "x"
dependencies = [
    "requests>=2.0",
    "click==8.1.0",
]
"""
        deps, warnings = mod.parse_pyproject_toml(text)
        assert warnings == []
        assert {"name": "requests", "version": ">=2.0"} in deps
        assert {"name": "click", "version": "==8.1.0"} in deps

    def test_poetry_dependencies_skips_python(self) -> None:
        text = """
[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.28.0"
click = { version = "^8.0", extras = ["foo"] }
"""
        deps, warnings = mod.parse_pyproject_toml(text)
        assert warnings == []
        names = _names(deps)
        assert "python" not in names
        assert "requests" in names
        assert "click" in names
        # click is a dict-form spec → version extracted from `version` key
        click = next(d for d in deps if d["name"] == "click")
        assert click["version"] == "^8.0"

    def test_malformed_toml_emits_warning(self) -> None:
        deps, warnings = mod.parse_pyproject_toml("[broken")
        assert deps == []
        assert any("TOML parse failed" in w for w in warnings)


class TestRequirementsTxtParser:
    def test_basic_deps(self) -> None:
        text = "requests==2.28.0\nclick>=8.0\n# comment\n\n-r other.txt\n"
        deps, warnings = mod.parse_requirements_txt(text)
        assert warnings == []
        names = _names(deps)
        assert "requests" in names
        assert "click" in names

    def test_extras_and_markers(self) -> None:
        text = 'requests[security]==2.28.0 ; python_version >= "3.8"\n'
        deps, warnings = mod.parse_requirements_txt(text)
        assert len(deps) == 1
        assert deps[0]["name"] == "requests"


class TestSetupPyParser:
    def test_install_requires(self) -> None:
        text = """
from setuptools import setup
setup(
    name="x",
    install_requires=[
        "requests>=2.0",
        'click==8.1.0',
    ],
)
"""
        deps, _ = mod.parse_setup_py(text)
        assert sorted(_names(deps)) == ["click", "requests"]

    def test_no_install_requires(self) -> None:
        deps, warnings = mod.parse_setup_py("setup(name='x')")
        assert deps == []
        assert warnings == []


class TestSetupCfgParser:
    def test_install_requires_block(self) -> None:
        text = """
[options]
install_requires =
    requests>=2.0
    click==8.1.0
"""
        deps, _ = mod.parse_setup_cfg(text)
        assert sorted(_names(deps)) == ["click", "requests"]


class TestPipfileParser:
    def test_packages_section(self) -> None:
        text = """
[packages]
requests = "*"
click = "==8.1.0"
foo = { version = "^1.0", extras = ["bar"] }

[dev-packages]
pytest = "*"
"""
        deps, _ = mod.parse_pipfile(text)
        names = _names(deps)
        assert "requests" in names
        assert "click" in names
        assert "foo" in names
        assert "pytest" not in names
        requests = next(d for d in deps if d["name"] == "requests")
        assert requests["version"] is None  # "*" normalised to None


class TestCargoTomlParser:
    def test_basic_deps(self) -> None:
        text = """
[package]
name = "x"

[dependencies]
serde = "1.0"
tokio = { version = "1.30", features = ["full"] }

[dev-dependencies]
mock_instant = "0.3"
"""
        deps, _ = mod.parse_cargo_toml(text)
        names = _names(deps)
        assert "serde" in names
        assert "tokio" in names
        assert "mock_instant" not in names


class TestGoModParser:
    def test_require_block_and_single_line(self) -> None:
        text = """
module example.com/foo

go 1.20

require github.com/gin-gonic/gin v1.9.0

require (
    github.com/stretchr/testify v1.8.0
    github.com/spf13/cobra v1.7.0 // indirect
)
"""
        deps, _ = mod.parse_go_mod(text)
        names = _names(deps)
        assert "github.com/gin-gonic/gin" in names
        assert "github.com/stretchr/testify" in names
        assert "github.com/spf13/cobra" in names


class TestPomXmlParser:
    def test_dependency_blocks(self) -> None:
        text = """
<project>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
      <version>31.0-jre</version>
    </dependency>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
"""
        deps, _ = mod.parse_pom_xml(text)
        names = _names(deps)
        assert "com.google.guava:guava" in names
        assert "junit:junit" not in names  # test scope excluded


class TestGradleParser:
    def test_implementation_and_api(self) -> None:
        text = """
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter:2.7.0'
    api "com.google.guava:guava:31.0-jre"
    testImplementation 'junit:junit:4.13.2'
}
"""
        deps, _ = mod.parse_gradle(text)
        names = _names(deps)
        assert "org.springframework.boot:spring-boot-starter" in names
        assert "com.google.guava:guava" in names
        # testImplementation is NOT in the captured scopes
        assert "junit:junit" not in names


class TestGemfileParser:
    def test_gem_entries_skip_dev_group(self) -> None:
        text = """
source 'https://rubygems.org'

gem 'rails', '7.0.0'
gem 'pg'

group :development, :test do
  gem 'rspec'
end
"""
        deps, _ = mod.parse_gemfile(text)
        names = _names(deps)
        assert "rails" in names
        assert "pg" in names
        assert "rspec" not in names


class TestComposerJsonParser:
    def test_require_only(self) -> None:
        text = json.dumps(
            {
                "require": {
                    "php": ">=8.0",
                    "ext-json": "*",
                    "symfony/console": "^6.0",
                    "monolog/monolog": "^3.0",
                },
                "require-dev": {"phpunit/phpunit": "^10.0"},
            }
        )
        deps, _ = mod.parse_composer_json(text)
        names = _names(deps)
        assert "symfony/console" in names
        assert "monolog/monolog" in names
        assert "php" not in names
        assert "ext-json" not in names
        assert "phpunit/phpunit" not in names


class TestPackageSwiftParser:
    def test_package_url_with_from(self) -> None:
        text = """
let package = Package(
    name: "Foo",
    dependencies: [
        .package(url: "https://github.com/apple/swift-nio.git", from: "2.0.0"),
        .package(url: "https://github.com/vapor/vapor", from: "4.0.0"),
    ]
)
"""
        deps, _ = mod.parse_package_swift(text)
        names = _names(deps)
        assert "swift-nio" in names
        assert "vapor" in names
        nio = next(d for d in deps if d["name"] == "swift-nio")
        assert nio["version"] == "2.0.0"


# --------------------------------------------------------------------------
# scan (integration)
# --------------------------------------------------------------------------


class TestScan:
    def test_single_ecosystem_five_deps(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps(
                {
                    "name": "x",
                    "dependencies": {
                        "react": "^18",
                        "react-dom": "^18",
                        "lodash": "4.17.21",
                        "axios": "^1.0",
                        "zod": "^3.0",
                    },
                }
            ),
        )
        result = mod.scan(tmp_path)
        assert len(result["manifests"]) == 1
        assert result["manifests"][0]["ecosystem"] == "npm"
        assert result["manifests"][0]["path"] == "package.json"
        assert len(result["manifests"][0]["deps"]) == 5
        assert result["total_unique"] == 5
        assert result["monorepo"] is False
        assert "warnings" not in result

    def test_multi_ecosystem(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"react": "^18"}}),
        )
        _write(
            tmp_path / "pyproject.toml",
            """
[project]
dependencies = ["requests>=2.0", "click==8.0"]
""",
        )
        result = mod.scan(tmp_path)
        ecos = sorted(m["ecosystem"] for m in result["manifests"])
        assert ecos == ["npm", "python"]
        # 1 npm dep + 2 python deps, all distinct names
        assert result["total_unique"] == 3
        assert result["monorepo"] is False

    def test_monorepo_detection(self, tmp_path: Path) -> None:
        # root package.json + two sibling package.json's under packages/*
        _write(tmp_path / "package.json", json.dumps({"name": "root"}))
        _write(
            tmp_path / "packages" / "a" / "package.json",
            json.dumps({"name": "a", "dependencies": {"lodash": "*"}}),
        )
        _write(
            tmp_path / "packages" / "b" / "package.json",
            json.dumps({"name": "b", "dependencies": {"axios": "*"}}),
        )
        result = mod.scan(tmp_path)
        assert len(result["manifests"]) == 3
        assert result["monorepo"] is True
        # ensure forward-slash paths regardless of platform
        paths = [m["path"] for m in result["manifests"]]
        assert "package.json" in paths
        assert "packages/a/package.json" in paths
        assert "packages/b/package.json" in paths

    def test_non_monorepo_nested_does_not_flag(self, tmp_path: Path) -> None:
        # parent + single child manifest of same ecosystem at overlapping depth
        # → NOT a monorepo (still only one "branch")
        _write(tmp_path / "package.json", json.dumps({"name": "root"}))
        _write(
            tmp_path / "packages" / "a" / "package.json",
            json.dumps({"name": "a"}),
        )
        result = mod.scan(tmp_path)
        assert result["monorepo"] is False

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = mod.scan(tmp_path)
        assert result == {
            "manifests": [],
            "total_unique": 0,
            "monorepo": False,
            "umbrella_candidates": [],
            "searched_filenames": list(mod.MANIFEST_ECOSYSTEMS),
        }

    def test_malformed_manifest_emits_warning(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", "{not json")
        result = mod.scan(tmp_path)
        # manifest record exists with empty deps
        assert len(result["manifests"]) == 1
        assert result["manifests"][0]["deps"] == []
        # warning recorded at top level
        assert "warnings" in result
        assert any("JSON parse failed" in w for w in result["warnings"])

    def test_unparsable_name_excluded_from_unique_count(self, tmp_path: Path) -> None:
        # `requirements.txt` line that can't be parsed should not inflate uniques
        _write(tmp_path / "requirements.txt", "===invalid\nrequests==2.0\n")
        result = mod.scan(tmp_path)
        # only "requests" counted; "<unparsable>" excluded
        assert result["total_unique"] == 1

    def test_dedup_across_manifests(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"react": "^18"}}),
        )
        _write(
            tmp_path / "packages" / "a" / "package.json",
            json.dumps({"dependencies": {"react": "^18", "lodash": "*"}}),
        )
        result = mod.scan(tmp_path)
        # react appears in both manifests but counts once
        assert result["total_unique"] == 2

    def test_paths_use_forward_slashes(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "deep" / "nest" / "package.json",
            json.dumps({"name": "x"}),
        )
        result = mod.scan(tmp_path)
        # On Windows this is the critical assertion — no backslashes leaked
        assert result["manifests"][0]["path"] == "packages/deep/nest/package.json"


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_scan_emits_json(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"react": "^18"}}),
        )
        result = _run_cli("scan", str(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["total_unique"] == 1
        assert payload["monorepo"] is False
        assert len(payload["manifests"]) == 1
        assert payload["manifests"][0]["ecosystem"] == "npm"

    def test_scan_empty_directory_exits_0(self, tmp_path: Path) -> None:
        result = _run_cli("scan", str(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {
            "manifests": [],
            "total_unique": 0,
            "monorepo": False,
            "umbrella_candidates": [],
            "searched_filenames": list(mod.MANIFEST_ECOSYSTEMS),
        }

    def test_scan_bad_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("scan", str(tmp_path / "missing"))
        assert result.returncode == 1
        assert "root not a directory" in result.stderr

    def test_scan_rejects_unknown_ecosystem_flag(self, tmp_path: Path) -> None:
        result = _run_cli("scan", str(tmp_path), "--ecosystems", "npm")
        assert result.returncode == 1
        assert "supports only 'auto'" in result.stderr

    def test_scan_accepts_auto_ecosystem_flag(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", '{"name": "x"}')
        result = _run_cli("scan", str(tmp_path), "--ecosystems", "auto")
        assert result.returncode == 0, result.stderr

    def test_subcommand_required(self) -> None:
        result = _run_cli()
        assert result.returncode != 0

    def test_scan_include_dev_flag(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"react": "^18"}, "devDependencies": {"vitest": "^1"}}),
        )
        plain = json.loads(_run_cli("scan", str(tmp_path)).stdout)
        assert _names(plain["manifests"][0]["deps"]) == ["react"]
        result = _run_cli("scan", str(tmp_path), "--include-dev")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["manifests"][0]["deps"] == [
            {"name": "react", "version": "^18"},
            {"name": "vitest", "version": "^1", "scope": "dev"},
        ]
        assert payload["total_unique"] == 1
        assert payload["total_unique_dev"] == 1


# --------------------------------------------------------------------------
# Package identity: name and private flag
# --------------------------------------------------------------------------


class TestIdentity:
    @pytest.mark.parametrize(
        ("filename", "text", "expected"),
        [
            ("package.json", '{"name": "@acme/core"}', ("@acme/core", False)),
            ("package.json", '{"name": "root", "private": true}', ("root", True)),
            ("package.json", '{"private": true}', (None, True)),
            ("package.json", "{not json", (None, None)),
            ("pyproject.toml", '[project]\nname = "acme-core"\n', ("acme-core", False)),
            (
                "pyproject.toml",
                '[project]\nname = "internal"\n'
                'classifiers = ["Private :: Do Not Upload"]\n',
                ("internal", True),
            ),
            ("pyproject.toml", '[tool.poetry]\nname = "poetic"\n', ("poetic", False)),
            (
                "pyproject.toml",
                '[tool.poetry]\nname = "app"\npackage-mode = false\n',
                ("app", True),
            ),
            ("pyproject.toml", "[tool.black]\nline-length = 100\n", (None, None)),
            ("setup.py", 'from setuptools import setup\nsetup(\n    name="legacy",\n)\n', ("legacy", False)),
            ("setup.cfg", "[metadata]\nname = cfgpkg\nversion = 1.0\n", ("cfgpkg", False)),
            ("Cargo.toml", '[package]\nname = "animato"\n', ("animato", False)),
            ("Cargo.toml", '[package]\nname = "bench"\npublish = false\n', ("bench", True)),
            ("Cargo.toml", '[package]\nname = "nope"\npublish = []\n', ("nope", True)),
            ("Cargo.toml", '[package]\nname = "m"\npublish.workspace = true\n', ("m", None)),
            ("Cargo.toml", '[workspace]\nmembers = ["crates/*"]\n', (None, None)),
            ("go.mod", "module github.com/acme/kit\n\ngo 1.22\n", ("github.com/acme/kit", None)),
            ("composer.json", '{"name": "acme/widgets"}', ("acme/widgets", None)),
            ("Package.swift", 'let package = Package(\n    name: "Kit",\n)\n', ("Kit", None)),
        ],
    )
    def test_readers(self, filename: str, text: str, expected: tuple) -> None:
        assert mod.IDENTITY_READERS[filename](text) == expected

    def test_pom_own_coordinates_not_parent_or_dependency(self) -> None:
        text = """
<project>
  <!-- <artifactId>commented</artifactId> -->
  <parent>
    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
  </parent>
  <artifactId>acme-core</artifactId>
  <properties>
    <maven.deploy.skip>true</maven.deploy.skip>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
    </dependency>
  </dependencies>
</project>
"""
        assert mod.identity_pom_xml(text) == ("com.acme:acme-core", True)

    def test_formats_without_a_package_name(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "requests\n")
        _write(tmp_path / "a" / "Gemfile", "gem 'rails'\n")
        _write(tmp_path / "b" / "build.gradle", "dependencies { implementation 'a:b:1' }\n")
        _write(tmp_path / "c" / "Pipfile", '[packages]\nrequests = "*"\n')
        result = mod.scan(tmp_path)
        assert [(m["name"], m["private"]) for m in result["manifests"]] == [(None, None)] * 4

    def test_scan_reports_identity(self, tmp_path: Path) -> None:
        _write(tmp_path / "package.json", json.dumps({"name": "root", "private": True}))
        result = mod.scan(tmp_path)
        manifest = result["manifests"][0]
        assert list(manifest) == ["path", "ecosystem", "name", "private", "deps", "internal_deps"]
        assert (manifest["name"], manifest["private"]) == ("root", True)


# --------------------------------------------------------------------------
# internal_deps and umbrella_candidates
# --------------------------------------------------------------------------


def _npm(root: Path, rel: str, name: str, deps: dict | None = None, **extra) -> None:
    _write(root / rel / "package.json", json.dumps({"name": name, "dependencies": deps or {}, **extra}))


class TestWorkspaceMembers:
    def test_npm_internal_deps(self, tmp_path: Path) -> None:
        _npm(tmp_path, ".", "root", private=True)
        _npm(tmp_path, "packages/core", "@acme/core", {"zod": "^3"})
        _npm(tmp_path, "packages/client", "@acme/client", {"@acme/core": "workspace:*", "zod": "^3"})
        result = mod.scan(tmp_path)
        by_path = {m["path"]: m for m in result["manifests"]}
        assert by_path["packages/client/package.json"]["internal_deps"] == ["@acme/core"]
        assert by_path["packages/core/package.json"]["internal_deps"] == []
        assert by_path["package.json"]["internal_deps"] == []

    def test_python_names_compare_as_pep_503(self, tmp_path: Path) -> None:
        _write(tmp_path / "libs" / "core" / "pyproject.toml", '[project]\nname = "Acme_Core"\n')
        _write(
            tmp_path / "libs" / "app" / "pyproject.toml",
            '[project]\nname = "acme-app"\ndependencies = ["acme.core>=1", "requests"]\n',
        )
        result = mod.scan(tmp_path)
        app = next(m for m in result["manifests"] if m["name"] == "acme-app")
        assert app["internal_deps"] == ["Acme_Core"]

    def test_rust_dash_and_underscore_alike(self, tmp_path: Path) -> None:
        _write(tmp_path / "crates" / "a" / "Cargo.toml", '[package]\nname = "anim-core"\n')
        _write(
            tmp_path / "crates" / "b" / "Cargo.toml",
            '[package]\nname = "anim"\n\n[dependencies]\nanim_core = { path = "../a" }\n',
        )
        result = mod.scan(tmp_path)
        anim = next(m for m in result["manifests"] if m["name"] == "anim")
        assert anim["internal_deps"] == ["anim-core"]

    def test_maven_project_group_id_resolves(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "core" / "pom.xml",
            "<project><groupId>com.acme</groupId><artifactId>core</artifactId></project>",
        )
        _write(
            tmp_path / "app" / "pom.xml",
            "<project><groupId>com.acme</groupId><artifactId>app</artifactId>"
            "<dependencies><dependency><groupId>${project.groupId}</groupId>"
            "<artifactId>core</artifactId></dependency></dependencies></project>",
        )
        result = mod.scan(tmp_path)
        app = next(m for m in result["manifests"] if m["name"] == "com.acme:app")
        assert app["internal_deps"] == ["com.acme:core"]

    def test_dev_dependencies_are_not_internal_deps(self, tmp_path: Path) -> None:
        _npm(tmp_path, "packages/core", "@acme/core")
        _npm(tmp_path, "packages/tests", "@acme/tests", devDependencies={"@acme/core": "*"})
        result = mod.scan(tmp_path, include_dev=True)
        tests = next(m for m in result["manifests"] if m["name"] == "@acme/tests")
        assert tests["internal_deps"] == []

    def test_umbrella_candidate(self, tmp_path: Path) -> None:
        _npm(tmp_path, ".", "root", private=True)
        for member in ("core", "client", "server"):
            _npm(tmp_path, f"packages/{member}", f"@acme/{member}")
        _npm(
            tmp_path,
            "packages/acme",
            "acme",
            {"@acme/core": "*", "@acme/client": "*", "@acme/server": "*"},
        )
        # a private example depends on the facade and is not a member
        _npm(tmp_path, "examples/demo", "demo", {"acme": "*", "@acme/core": "*"}, private=True)
        result = mod.scan(tmp_path)
        assert result["umbrella_candidates"] == [
            {
                "path": "packages/acme/package.json",
                "name": "acme",
                "ecosystem": "npm",
                "internal_dep_count": 3,
                "member_count": 3,
            }
        ]

    def test_below_half_is_not_an_umbrella(self, tmp_path: Path) -> None:
        for member in ("a", "b", "c", "d", "e", "f"):
            _npm(tmp_path, f"packages/{member}", member)
        _npm(tmp_path, "packages/adapter", "adapter", {"a": "*", "b": "*"})
        assert mod.scan(tmp_path)["umbrella_candidates"] == []

    def test_one_internal_dep_is_not_an_umbrella(self, tmp_path: Path) -> None:
        _npm(tmp_path, "packages/a", "a")
        _npm(tmp_path, "packages/b", "b", {"a": "*"})
        assert mod.scan(tmp_path)["umbrella_candidates"] == []


# --------------------------------------------------------------------------
# --include-dev
# --------------------------------------------------------------------------


class TestDevDependencies:
    @pytest.mark.parametrize(
        ("filename", "text", "dev_names"),
        [
            (
                "package.json",
                json.dumps({"dependencies": {"react": "1"}, "devDependencies": {"jest": "29"}}),
                ["jest"],
            ),
            (
                "pyproject.toml",
                "[project]\n"
                'dependencies = ["requests"]\n'
                "[project.optional-dependencies]\n"
                'dev = ["black"]\n'
                'aws = ["boto3"]\n'
                "[dependency-groups]\n"
                'test = ["pytest>=8", {include-group = "lint"}]\n'
                "[tool.poetry.dev-dependencies]\n"
                'mypy = "^1"\n'
                "[tool.poetry.group.docs.dependencies]\n"
                'sphinx = "^7"\n'
                "[tool.pdm.dev-dependencies]\n"
                'lint = ["ruff"]\n'
                "[tool.uv]\n"
                'dev-dependencies = ["coverage"]\n',
                ["pytest", "black", "mypy", "sphinx", "ruff", "coverage"],
            ),
            (
                "setup.py",
                "setup(install_requires=['requests'], tests_require=['pytest'],\n"
                "      extras_require={'docs': ['sphinx'], 'aws': ['boto3']})\n",
                ["pytest", "sphinx"],
            ),
            (
                "setup.cfg",
                "[options]\ninstall_requires =\n    requests\ntests_require =\n    pytest\n\n"
                "[options.extras_require]\ndev =\n    black\n    mypy\naws = boto3\n",
                ["pytest", "black", "mypy"],
            ),
            ("Pipfile", '[packages]\nflask = "*"\n\n[dev-packages]\npytest = "*"\n', ["pytest"]),
            (
                "Cargo.toml",
                '[package]\nname = "x"\n\n[dependencies]\nserde = "1"\n\n'
                '[dev-dependencies]\ncriterion = "0.5"\n',
                ["criterion"],
            ),
            (
                "pom.xml",
                "<project><dependencies>"
                "<dependency><groupId>junit</groupId><artifactId>junit</artifactId>"
                "<scope>test</scope></dependency>"
                "<dependency><groupId>javax</groupId><artifactId>api</artifactId>"
                "<scope>provided</scope></dependency>"
                "</dependencies></project>",
                ["junit:junit"],
            ),
            (
                "build.gradle",
                "dependencies {\n  implementation 'a:b:1'\n  testImplementation 'junit:junit:4.13'\n"
                "  androidTestImplementation(\"x:espresso:3\")\n}\n",
                ["junit:junit", "x:espresso"],
            ),
            (
                "build.gradle.kts",
                "dependencies {\n  implementation(\"a:b:1\")\n"
                "  testImplementation(kotlin(\"test\"))\n"
                "  testImplementation(\"io.mockk:mockk:1.13.8\")\n"
                "  testImplementation(\"org.junit.jupiter:junit-jupiter:5.10.0\")\n}\n",
                ["io.mockk:mockk", "org.junit.jupiter:junit-jupiter"],
            ),
            (
                "Gemfile",
                "gem 'rails'\ngroup :development, :test do\n  gem 'rspec'\nend\n",
                ["rspec"],
            ),
            (
                "composer.json",
                json.dumps({"require": {"monolog/monolog": "^3"},
                            "require-dev": {"phpunit/phpunit": "^10", "ext-xdebug": "*"}}),
                ["phpunit/phpunit"],
            ),
        ],
    )
    def test_dev_sections(self, tmp_path: Path, filename: str, text: str, dev_names: list) -> None:
        _write(tmp_path / filename, text)
        manifest = mod.scan(tmp_path, include_dev=True)["manifests"][0]
        dev = [d for d in manifest["deps"] if d.get("scope") == "dev"]
        assert _names(dev) == dev_names
        runtime = [d for d in manifest["deps"] if "scope" not in d]
        assert runtime == mod.PARSERS[filename](text)[0]

    def test_formats_without_dev_sections(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "requests\n")
        _write(tmp_path / "a" / "go.mod", "module x\n\nrequire github.com/a/b v1.0.0\n")
        _write(tmp_path / "b" / "Package.swift", '.package(url: "https://github.com/a/b.git", from: "1.0.0")')
        result = mod.scan(tmp_path, include_dev=True)
        assert all("scope" not in d for m in result["manifests"] for d in m["deps"])
        assert result["total_unique_dev"] == 0

    def test_runtime_name_not_repeated_and_dev_only_total(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "package.json",
            json.dumps({"dependencies": {"zod": "3"}, "devDependencies": {"zod": "3", "vitest": "1"}}),
        )
        _write(
            tmp_path / "packages" / "a" / "package.json",
            json.dumps({"dependencies": {"vitest": "1"}, "devDependencies": {"tsx": "4"}}),
        )
        result = mod.scan(tmp_path, include_dev=True)
        root = next(m for m in result["manifests"] if m["path"] == "package.json")
        assert root["deps"] == [
            {"name": "zod", "version": "3"},
            {"name": "vitest", "version": "1", "scope": "dev"},
        ]
        # vitest is a runtime dependency of packages/a, so only tsx is dev-only
        assert result["total_unique"] == 2
        assert result["total_unique_dev"] == 1

    def test_default_scan_reads_runtime_only(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "Cargo.toml",
            '[package]\nname = "x"\n\n[dependencies]\nserde = "1"\n\n[dev-dependencies]\nmockall = "0.12"\n',
        )
        result = mod.scan(tmp_path)
        assert _names(result["manifests"][0]["deps"]) == ["serde"]
        assert "total_unique_dev" not in result


# --------------------------------------------------------------------------
# searched_filenames and manifest-patterns.md
# --------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    return text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _documented_manifests() -> dict[str, str]:
    """Manifest file -> ecosystem, from the Supported Ecosystems table."""
    section = _section(MANIFEST_PATTERNS.read_text(encoding="utf-8"), "Supported Ecosystems")
    table: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        ecosystem = cells[0].strip("`")
        for filename in re.findall(r"`([^`]+)`", cells[2]):
            assert filename not in table, f"{filename} listed twice"
            table[filename] = ecosystem
    return table


class TestManifestPatternsDoc:
    def test_searched_filenames_are_the_ecosystem_table(self, tmp_path: Path) -> None:
        _write(tmp_path / "go.mod", "module x\n")
        assert mod.scan(tmp_path)["searched_filenames"] == list(mod.MANIFEST_ECOSYSTEMS)

    def test_table_matches_the_script(self) -> None:
        assert _documented_manifests() == mod.MANIFEST_ECOSYSTEMS

    def test_table_names_the_formerly_missing_manifests(self) -> None:
        documented = _documented_manifests()
        for filename in ("setup.cfg", "build.gradle.kts", "Package.swift"):
            assert filename in documented
        assert not any("csproj" in name for name in documented)
        assert "csproj" not in MANIFEST_PATTERNS.read_text(encoding="utf-8")

    def test_scan_exclusions_match_the_script(self) -> None:
        section = _section(MANIFEST_PATTERNS.read_text(encoding="utf-8"), "Scan Exclusion Patterns")
        documented = {d.rstrip("/") for d in re.findall(r"`([^`]+/)`", section)}
        assert documented == set(mod.EXCLUDED_DIRS)
