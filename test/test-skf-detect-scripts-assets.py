#!/usr/bin/env python3
"""Tests for skf-detect-scripts-assets.py.

Covers detection rules from src/skf-create-skill/references/extraction-patterns-tracing.md:
  - Script directory convention (scripts/, bin/, tools/, cli/)
  - Shebang signals (#!/bin/bash, #!/usr/bin/env python|node|...)
  - Entry point declarations (package.json `bin`)
  - Asset directory convention + filename patterns (*.schema.json, *.template.*, ...)
  - Binary exclusion + generated-path pruning
  - Size flagging + scope filtering
  - Intent gates (scripts_intent=none, assets_intent=none)
  - Purpose extraction (header comment, schema title, filename fallback)
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-detect-scripts-assets.py"

spec = importlib.util.spec_from_file_location("skf_detect_scripts_assets", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def write_file(path: Path, content: str = "", *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


# --------------------------------------------------------------------------
# Script directory convention
# --------------------------------------------------------------------------


class TestScriptDirectoryConvention:
    def test_file_in_scripts_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "deploy.sh", "echo hello\n")
        result = mod.detect(tmp_path)
        assert len(result["scripts_inventory"]) == 1
        rec = result["scripts_inventory"][0]
        assert rec["source_file"] == "scripts/deploy.sh"
        assert rec["language"] == "shell"
        assert rec["confidence"] == "T1-low"
        assert rec["content_hash"].startswith("sha256:")

    def test_file_in_bin_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "bin" / "tool.py", "import sys\n")
        result = mod.detect(tmp_path)
        assert any(r["name"] == "tool.py" for r in result["scripts_inventory"])

    def test_file_in_tools_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "tools" / "lint.js", "console.log('x')\n")
        result = mod.detect(tmp_path)
        assert any(r["name"] == "lint.js" for r in result["scripts_inventory"])

    def test_nested_script_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "pkg" / "scripts" / "build.sh", "")
        result = mod.detect(tmp_path)
        assert any(r["name"] == "build.sh" for r in result["scripts_inventory"])


# --------------------------------------------------------------------------
# Shebang signals
# --------------------------------------------------------------------------


class TestShebangSignals:
    def test_bash_shebang(self, tmp_path: Path) -> None:
        write_file(tmp_path / "deploy", "#!/bin/bash\necho hi\n")
        result = mod.detect(tmp_path)
        rec = result["scripts_inventory"][0]
        assert rec["language"] == "bash"

    def test_env_python_shebang(self, tmp_path: Path) -> None:
        write_file(tmp_path / "tool", "#!/usr/bin/env python3\nimport sys\n")
        result = mod.detect(tmp_path)
        rec = result["scripts_inventory"][0]
        assert rec["language"] == "python"

    def test_env_node_shebang(self, tmp_path: Path) -> None:
        write_file(tmp_path / "cli", "#!/usr/bin/env node\nconsole.log()\n")
        result = mod.detect(tmp_path)
        rec = result["scripts_inventory"][0]
        assert rec["language"] == "javascript"

    def test_no_shebang_no_dir_not_detected(self, tmp_path: Path) -> None:
        write_file(tmp_path / "lib.py", "def foo(): pass\n")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []


# --------------------------------------------------------------------------
# Entry-point declarations (package.json bin)
# --------------------------------------------------------------------------


class TestPackageJsonBin:
    def test_bin_string(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "package.json",
            '{"name": "mytool", "bin": "src/cli.js"}',
        )
        write_file(tmp_path / "src" / "cli.js", "// cli entry\n")
        result = mod.detect(tmp_path)
        # cli.js is in src/, not scripts/, so it's detected via entry-point only
        assert any(r["source_file"] == "src/cli.js" for r in result["scripts_inventory"])

    def test_bin_object(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "package.json",
            '{"name": "x", "bin": {"foo": "lib/foo.js", "bar": "lib/bar.js"}}',
        )
        write_file(tmp_path / "lib" / "foo.js", "")
        write_file(tmp_path / "lib" / "bar.js", "")
        result = mod.detect(tmp_path)
        names = {r["name"] for r in result["scripts_inventory"]}
        assert names == {"foo.js", "bar.js"}

    def test_bin_missing_file_ignored(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "package.json",
            '{"name": "x", "bin": "missing.js"}',
        )
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []

    def test_malformed_package_json_no_crash(self, tmp_path: Path) -> None:
        write_file(tmp_path / "package.json", "{not json")
        write_file(tmp_path / "scripts" / "ok.sh", "")
        result = mod.detect(tmp_path)
        # malformed package.json doesn't kill scanning
        assert any(r["name"] == "ok.sh" for r in result["scripts_inventory"])


# --------------------------------------------------------------------------
# Asset detection
# --------------------------------------------------------------------------


class TestAssetDetection:
    def test_schema_json_in_schemas_dir(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "schemas" / "config.schema.json",
            '{"$schema": "http://json-schema.org/draft-07/schema#", "title": "Config"}',
        )
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "schema"
        assert rec["purpose"] == "Config"

    def test_schema_json_outside_schemas_dir(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "pkg" / "user.schema.json",
            '{"$schema": "x"}',
        )
        result = mod.detect(tmp_path)
        # pattern-based detection catches *.schema.json anywhere
        assert len(result["assets_inventory"]) == 1
        assert result["assets_inventory"][0]["type"] == "schema"

    def test_template_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "templates" / "report.md.template", "# {{title}}\n")
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "template"

    def test_configs_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "configs" / "production.yaml", "key: value\n")
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "config"

    def test_examples_dir(self, tmp_path: Path) -> None:
        write_file(tmp_path / "examples" / "basic.md", "# Example\n")
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "example"

    def test_openapi_json(self, tmp_path: Path) -> None:
        write_file(tmp_path / "openapi.json", '{"openapi": "3.0.0"}')
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "schema"

    def test_graphql_file(self, tmp_path: Path) -> None:
        write_file(tmp_path / "api.graphql", "type Query { hello: String }\n")
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "schema"

    def test_sample_extension(self, tmp_path: Path) -> None:
        write_file(tmp_path / "config.sample", "# sample\n")
        result = mod.detect(tmp_path)
        rec = result["assets_inventory"][0]
        assert rec["type"] == "example"


# --------------------------------------------------------------------------
# Exclusions
# --------------------------------------------------------------------------


class TestExclusions:
    def test_binary_extension_excluded(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "tool.exe", "")
        write_file(tmp_path / "lib" / "blob.so", "")
        write_file(tmp_path / "assets" / "icon.png", "")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []
        assert result["assets_inventory"] == []

    def test_node_modules_pruned(self, tmp_path: Path) -> None:
        write_file(tmp_path / "node_modules" / "lib" / "scripts" / "x.sh", "")
        write_file(tmp_path / "scripts" / "deploy.sh", "")
        result = mod.detect(tmp_path)
        names = [r["name"] for r in result["scripts_inventory"]]
        assert names == ["deploy.sh"]

    def test_dist_pruned(self, tmp_path: Path) -> None:
        write_file(tmp_path / "dist" / "scripts" / "bundle.js", "")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []

    def test_pycache_pruned(self, tmp_path: Path) -> None:
        write_file(tmp_path / "__pycache__" / "x.cpython-310.pyc", "")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []

    def test_git_pruned(self, tmp_path: Path) -> None:
        write_file(tmp_path / ".git" / "hooks" / "pre-commit", "#!/bin/sh\n")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"] == []


# --------------------------------------------------------------------------
# Size flagging
# --------------------------------------------------------------------------


class TestSizeFlag:
    def test_under_threshold_no_flag(self, tmp_path: Path) -> None:
        content = "echo line\n" * 100
        write_file(tmp_path / "scripts" / "small.sh", content)
        result = mod.detect(tmp_path)
        rec = result["scripts_inventory"][0]
        assert rec["lines"] == 100
        assert rec["size_flag"] is None

    def test_over_threshold_flagged(self, tmp_path: Path) -> None:
        content = "echo line\n" * 600
        write_file(tmp_path / "scripts" / "big.sh", content)
        result = mod.detect(tmp_path, max_lines=500)
        rec = result["scripts_inventory"][0]
        assert rec["lines"] == 600
        assert rec["size_flag"] == "oversized"


# --------------------------------------------------------------------------
# Scope filtering
# --------------------------------------------------------------------------


class TestScope:
    def test_scope_include_filter(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "include-me.sh", "")
        write_file(tmp_path / "tools" / "exclude-me.sh", "")
        result = mod.detect(tmp_path, scope_patterns=["scripts/*"])
        names = {r["name"] for r in result["scripts_inventory"]}
        assert names == {"include-me.sh"}

    def test_empty_scope_includes_everything(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "a.sh", "")
        write_file(tmp_path / "tools" / "b.sh", "")
        result = mod.detect(tmp_path, scope_patterns=[])
        names = {r["name"] for r in result["scripts_inventory"]}
        assert names == {"a.sh", "b.sh"}


# --------------------------------------------------------------------------
# Intent gates
# --------------------------------------------------------------------------


class TestIntentGates:
    def test_scripts_intent_none(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "")
        write_file(tmp_path / "assets" / "y.yaml", "")
        result = mod.detect(tmp_path, scripts_intent="none")
        assert result["scripts_skipped"] is True
        assert result["scripts_inventory"] == []
        # assets still detected
        assert len(result["assets_inventory"]) == 1

    def test_assets_intent_none(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "")
        write_file(tmp_path / "assets" / "y.yaml", "")
        result = mod.detect(tmp_path, assets_intent="none")
        assert result["assets_skipped"] is True
        assert result["assets_inventory"] == []
        assert len(result["scripts_inventory"]) == 1

    def test_both_none_no_walk(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "")
        result = mod.detect(tmp_path, scripts_intent="none", assets_intent="none")
        assert result["stats"]["files_scanned"] == 0
        assert result["scripts_skipped"] is True
        assert result["assets_skipped"] is True


# --------------------------------------------------------------------------
# Purpose extraction
# --------------------------------------------------------------------------


class TestPurpose:
    def test_purpose_from_header_comment_bash(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "scripts" / "deploy.sh",
            "#!/bin/bash\n# Deploy the app to staging\nset -e\n",
        )
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"][0]["purpose"] == "Deploy the app to staging"

    def test_purpose_from_header_comment_python(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "scripts" / "tool.py",
            "#!/usr/bin/env python\n# Tool that processes things\nimport sys\n",
        )
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"][0]["purpose"] == "Tool that processes things"

    def test_purpose_from_header_comment_js(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "scripts" / "build.js",
            "// Build the project\nconst x = 1\n",
        )
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"][0]["purpose"] == "Build the project"

    def test_purpose_from_schema_title(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "user.schema.json",
            '{"$schema": "x", "title": "User Profile", "description": "ignored"}',
        )
        result = mod.detect(tmp_path)
        assert result["assets_inventory"][0]["purpose"] == "User Profile"

    def test_purpose_from_schema_description_fallback(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / "x.schema.json",
            '{"$schema": "x", "description": "A schema with no title"}',
        )
        result = mod.detect(tmp_path)
        assert result["assets_inventory"][0]["purpose"] == "A schema with no title"

    def test_purpose_falls_back_to_filename(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "no-comments.sh", "echo x\n")
        result = mod.detect(tmp_path)
        assert result["scripts_inventory"][0]["purpose"] == "no-comments.sh"


# --------------------------------------------------------------------------
# Determinism & ordering
# --------------------------------------------------------------------------


class TestOrdering:
    def test_scripts_sorted_by_source_file(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "zzz.sh", "")
        write_file(tmp_path / "scripts" / "aaa.sh", "")
        write_file(tmp_path / "bin" / "mmm.sh", "")
        result = mod.detect(tmp_path)
        paths = [r["source_file"] for r in result["scripts_inventory"]]
        assert paths == sorted(paths)

    def test_hash_stable_across_runs(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "echo hi\n")
        r1 = mod.detect(tmp_path)
        r2 = mod.detect(tmp_path)
        assert r1 == r2


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
    def test_detect_emits_json(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "")
        result = _run_cli("detect", str(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert "scripts_inventory" in payload
        assert "assets_inventory" in payload
        assert "stats" in payload

    def test_bad_source_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("detect", str(tmp_path / "missing"))
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_bad_intent_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "detect", str(tmp_path), "--scripts-intent", "bogus"
        )
        assert result.returncode == 1

    def test_scope_include_passes_through(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "a.sh", "")
        write_file(tmp_path / "tools" / "b.sh", "")
        result = _run_cli(
            "detect", str(tmp_path), "--scope-include", "scripts/*"
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        names = {r["name"] for r in payload["scripts_inventory"]}
        assert names == {"a.sh"}

    def test_max_lines_passes_through(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "echo\n" * 50)
        result = _run_cli(
            "detect", str(tmp_path), "--max-lines", "10"
        )
        payload = json.loads(result.stdout)
        assert payload["scripts_inventory"][0]["size_flag"] == "oversized"
