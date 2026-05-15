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
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-scan-manifests.py"

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
