#!/usr/bin/env python3
"""Tests for skf-detect-scripts-assets.py.

Covers detection rules from src/skf-create-skill/references/extraction-patterns-tracing.md:
  - Script directory convention (scripts/, bin/, tools/, cli/), and a Python
    package's folder of that name, whose .py modules are code (#683)
  - Shebang signals (#!/bin/bash, #!/usr/bin/env python|node|...)
  - Entry point declarations (package.json `bin`)
  - Asset directory convention + filename patterns (*.schema.json, *.template.*, ...)
  - Binary exclusion + generated-path pruning
  - Size flagging + scope filtering (--brief: the brief's scope, by
    skf-classify-changed-files.py load_scope, never fnmatch; #697)
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
    # binary write so newline-translation on Windows doesn't change
    # size_bytes / SHA-256 (shebang detection reads bytes) vs the content
    # the test passed in
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
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


class TestIsPackageModule:
    """The package rule, one function: is_script and skf-compare-file-hashes.py (#696) both call it."""

    def test_the_rule(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg" / "tools"
        files = {"__init__.py": "", "helper.py": "X = 1\n", "__main__.py": "run()\n",
                 "runme.py": "if __name__ == '__main__':\n    pass\n", "run2.py": "#!/usr/bin/env python3\n",
                 "setup.sh": "echo\n"}
        for name, text in files.items():
            write_file(pkg / name, text)
        write_file(tmp_path / "scripts" / "loose.py", "X = 1\n")  # no __init__.py: a script folder
        modules = {name for name in files if mod.is_package_module(pkg / name, tmp_path)}
        assert modules == {"__init__.py", "helper.py"}
        assert not mod.is_package_module(tmp_path / "scripts" / "loose.py", tmp_path)
        assert _sources(mod.detect(tmp_path)) == ["pkg/tools/__main__.py", "pkg/tools/run2.py", "pkg/tools/runme.py",
                                                  "pkg/tools/setup.sh", "scripts/loose.py"]


class TestPythonPackageScriptDirs:
    """#683: a Python package's folder named tools/, cli/, bin/ or scripts/ (it holds __init__.py) is code: a .py
    module in it is a script only with a shebang or a __main__ block."""

    @pytest.mark.parametrize("folder", ["tools", "cli", "bin", "scripts"])
    def test_a_package_module_is_not_a_script(self, tmp_path: Path, folder: str) -> None:
        write_file(tmp_path / "cognee" / "api" / "v1" / folder / "__init__.py", "from .tools import TOOLS\n")
        write_file(tmp_path / "cognee" / "api" / "v1" / folder / "tools.py", "TOOLS = []\n")
        assert mod.detect(tmp_path)["scripts_inventory"] == []

    def test_a_package_module_that_runs_on_its_own_is_a_script(self, tmp_path: Path) -> None:
        write_file(tmp_path / "pkg" / "cli" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "cli" / "main.py", "def main():\n    pass\n\n\nif __name__ == '__main__':\n"
                                                        "    main()\n")
        write_file(tmp_path / "pkg" / "cli" / "run.py", "#!/usr/bin/env python3\nprint('run')\n")
        write_file(tmp_path / "pkg" / "cli" / "lib.py", "def helper():\n    if __name__ == '__main__':\n"
                                                       "        pass\n")  # not a top-level block
        result = mod.detect(tmp_path)
        assert [r["source_file"] for r in result["scripts_inventory"]] == ["pkg/cli/main.py", "pkg/cli/run.py"]
        assert result["scripts_inventory"][1]["language"] == "python"

    @pytest.mark.parametrize("text", [
        'if __name__ == "__main__":\n    main()\n',
        'if "__main__" == __name__:\n    main()\n',
        'if (__name__ == "__main__"):\n    main()\n',
        "if __name__=='__main__':\n    main()\n",
    ], ids=["plain", "reversed", "parenthesized", "single-quotes"])
    def test_every_form_of_the_main_block_counts(self, tmp_path: Path, text: str) -> None:
        write_file(tmp_path / "pkg" / "cli" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "cli" / "main.py", "def main():\n    pass\n\n\n" + text)
        assert [r["source_file"] for r in mod.detect(tmp_path)["scripts_inventory"]] == ["pkg/cli/main.py"]

    def test_a_main_block_inside_a_string_does_not_count(self, tmp_path: Path) -> None:
        write_file(tmp_path / "pkg" / "cli" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "cli" / "doc.py", '"""Usage:\n\nif __name__ == "__main__":\n    run()\n"""\n'
                                                        "X = 1\n")
        assert mod.detect(tmp_path)["scripts_inventory"] == []

    def test_a_file_that_does_not_parse_is_matched_line_by_line(self, tmp_path: Path) -> None:
        write_file(tmp_path / "pkg" / "cli" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "cli" / "old.py", 'print "py2"\n\nif __name__ == "__main__":\n    pass\n')
        assert [r["source_file"] for r in mod.detect(tmp_path)["scripts_inventory"]] == ["pkg/cli/old.py"]

    def test_a_package_s_main_module_is_its_entry_point(self, tmp_path: Path) -> None:
        # `python -m pkg.cli` runs pkg/cli/__main__.py, which often has no main block
        write_file(tmp_path / "pkg" / "cli" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "cli" / "__main__.py", "from .app import run\n\nrun()\n")
        write_file(tmp_path / "pkg" / "cli" / "app.py", "def run():\n    pass\n")
        assert [r["source_file"] for r in mod.detect(tmp_path)["scripts_inventory"]] == ["pkg/cli/__main__.py"]

    def test_a_package_folder_s_other_files_still_count(self, tmp_path: Path) -> None:
        # only a .py module is code: a shell script in the package folder is still a script by directory
        write_file(tmp_path / "pkg" / "tools" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "tools" / "setup.sh", "echo setup\n")
        assert [r["source_file"] for r in mod.detect(tmp_path)["scripts_inventory"]] == ["pkg/tools/setup.sh"]

    def test_a_module_below_a_package_script_folder_is_code(self, tmp_path: Path) -> None:
        write_file(tmp_path / "pkg" / "tools" / "__init__.py", "")
        write_file(tmp_path / "pkg" / "tools" / "sub" / "x.py", "X = 1\n")
        write_file(tmp_path / "scripts" / "tools" / "__init__.py", "")
        write_file(tmp_path / "scripts" / "tools" / "y.py", "Y = 1\n")
        assert mod.detect(tmp_path)["scripts_inventory"] == []

    def test_a_folder_without_init_keeps_the_directory_convention(self, tmp_path: Path) -> None:
        write_file(tmp_path / "tools" / "lint.py", "import sys\n")
        write_file(tmp_path / "pkg" / "__init__.py", "")  # a package above the script folder changes nothing
        write_file(tmp_path / "pkg" / "scripts" / "gen.py", "print('gen')\n")
        assert [r["source_file"] for r in mod.detect(tmp_path)["scripts_inventory"]] == ["pkg/scripts/gen.py",
                                                                                          "tools/lint.py"]


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


def write_brief(path: Path, include=None, exclude=None, language: str = "Python") -> Path:
    lines = ["name: demo", f"language: {language}", "scope:", "  type: public-api"]
    for key, patterns in (("include", include), ("exclude", exclude)):
        if patterns is None:
            continue
        lines.append(f"  {key}:" + ("" if patterns else " []"))
        lines += [f"  - {json.dumps(pattern)}" for pattern in patterns]  # a YAML double-quoted string
    return write_file(path, "\n".join(lines) + "\n")


def _sources(result: dict, key: str = "scripts_inventory") -> list[str]:
    return [r["source_file"] for r in result[key]]


class TestScope:
    """#697: --brief scopes the detector by the brief's glob rules (`**` spans folders, `*` never crosses a `/`,
    `scope.exclude` honoured), the in-scope test update-skill's Category A and D use, never fnmatch."""

    def _scope(self, tmp_path: Path, **brief):
        return mod.load_brief_scope(str(write_brief(tmp_path / "brief" / "skill-brief.yaml", **brief)))

    def test_double_star_spans_folders_and_an_exclude_wins(self, tmp_path: Path) -> None:
        for rel in ("install.sh", "scripts/build.sh", "scripts/dev/release.sh", "tools/sub/x.sh"):
            write_file(tmp_path / "src" / rel, "#!/bin/sh\n")
        result = mod.detect(tmp_path / "src", scope=self._scope(tmp_path, include=["**/*.sh"],
                                                                exclude=["scripts/dev/**"]))
        # fnmatch read `**/*.sh` as needing a folder (root install.sh lost) and ignored scope.exclude
        assert _sources(result) == ["install.sh", "scripts/build.sh", "tools/sub/x.sh"]

    def test_star_never_crosses_a_folder(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "src" / "run.sh", "#!/bin/sh\n")
        write_file(tmp_path / "src" / "src" / "cli" / "sub" / "run.sh", "#!/bin/sh\n")
        result = mod.detect(tmp_path / "src", scope=self._scope(tmp_path, include=["src/*"]))
        assert _sources(result) == ["src/run.sh"]  # fnmatch's `*` took src/cli/sub/run.sh too

    def test_the_scope_test_runs_before_the_asset_rules(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "pkg" / "schemas" / "a.schema.json", "{}")
        write_file(tmp_path / "src" / "examples" / "demo.json", "{}")
        result = mod.detect(tmp_path / "src", scope=self._scope(tmp_path, include=["pkg/**"]))
        assert _sources(result, "assets_inventory") == ["pkg/schemas/a.schema.json"]
        assert result["stats"]["files_scanned"] == 2  # every file is walked; the scope drops one

    def test_an_empty_include_takes_the_language_files_no_exclude_matches(self, tmp_path: Path) -> None:
        for rel in ("scripts/gen.py", "scripts/run.sh", "bin/tool.py"):
            write_file(tmp_path / "src" / rel, "")
        result = mod.detect(tmp_path / "src", scope=self._scope(tmp_path, include=[], exclude=["bin/**"]))
        assert _sources(result) == ["scripts/gen.py"]

    def test_without_a_brief_every_file_is_in_scope(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "a.sh", "")
        write_file(tmp_path / "tools" / "b.sh", "")
        assert {r["name"] for r in mod.detect(tmp_path)["scripts_inventory"]} == {"a.sh", "b.sh"}
        assert {r["name"] for r in mod.detect(tmp_path, scope=None)["scripts_inventory"]} == {"a.sh", "b.sh"}

    def test_the_fnmatch_matcher_is_gone(self) -> None:
        assert not hasattr(mod, "matches_scope")


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


class TestScriptPEP723:
    """--brief loads skf-classify-changed-files.py, whose resolver reads the brief with PyYAML: under `uv run`
    the header must declare it."""

    def test_pyyaml_dependency(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        header = text[: text.index("# ///", text.index("# /// script") + 1)]
        assert '# requires-python = ">=3.11"' in header and 'dependencies = ["pyyaml"]' in header

    def test_the_scope_test_loads_only_with_brief(self, tmp_path: Path, monkeypatch) -> None:
        # the import surface stays flat without --brief: the classifier is a lazy sibling
        monkeypatch.setattr(mod, "_SIBLINGS", {})
        write_file(tmp_path / "scripts" / "a.sh", "echo\n")
        assert mod.detect(tmp_path)["stats"]["scripts_found"] == 1
        assert mod._SIBLINGS == {}

    @pytest.mark.parametrize("siblings", [
        {},
        {"skf-classify-changed-files.py": None},
        {"skf-classify-changed-files.py": "X = 1\n"},
    ], ids=["no-classifier", "no-resolver", "classifier-without-load-scope"])
    def test_a_scope_test_it_cannot_load_is_one_error_line(self, tmp_path: Path, siblings: dict) -> None:
        alone = tmp_path / "alone"
        alone.mkdir()
        (alone / SCRIPT_PATH.name).write_bytes(SCRIPT_PATH.read_bytes())
        for name, text in siblings.items():
            data = (SCRIPT_PATH.parent / name).read_bytes() if text is None else text.encode("utf-8")
            (alone / name).write_bytes(data)
        write_file(tmp_path / "src" / "scripts" / "a.sh", "")
        brief = write_brief(tmp_path / "skill-brief.yaml", include=["**"])
        result = subprocess.run([sys.executable, str(alone / SCRIPT_PATH.name), "detect", str(tmp_path / "src"),
                                 "--brief", str(brief)], capture_output=True, text=True, check=False)
        assert result.returncode == 1 and result.stdout == ""
        lines = result.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith("error: cannot load"), result.stderr
        assert "re-install SKF" in lines[0] and "Traceback" not in result.stderr


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

    def test_brief_passes_through(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "scripts" / "a.sh", "")
        write_file(tmp_path / "src" / "tools" / "b.sh", "")
        brief = write_brief(tmp_path / "skill-brief.yaml", include=["scripts/*"])
        result = _run_cli("detect", str(tmp_path / "src"), "--brief", str(brief))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert {r["name"] for r in payload["scripts_inventory"]} == {"a.sh"}

    def test_scope_include_is_gone(self, tmp_path: Path) -> None:
        result = _run_cli("detect", str(tmp_path), "--scope-include", "scripts/*")
        assert result.returncode == 2 and "unrecognized arguments: --scope-include" in result.stderr

    @pytest.mark.parametrize("case", ["missing", "empty", "blank", "not-yaml", "not-a-mapping"])
    def test_a_brief_it_cannot_use_exits_1_with_one_error_line(self, tmp_path: Path, case: str) -> None:
        write_file(tmp_path / "src" / "scripts" / "a.sh", "")
        brief = tmp_path / "skill-brief.yaml"
        value = {"missing": str(tmp_path / "nope.yaml"), "empty": "", "blank": "  "}.get(case, str(brief))
        if case == "not-yaml":
            write_file(brief, "scope: [unclosed\n")
        elif case == "not-a-mapping":
            write_file(brief, "- a\n- b\n")
        result = _run_cli("detect", str(tmp_path / "src"), "--brief", value)
        assert result.returncode == 1 and result.stdout == ""
        lines = result.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith("error: "), result.stderr
        needle = {"missing": "brief not found", "empty": "--brief is empty", "blank": "--brief is empty",
                  "not-yaml": "not valid YAML", "not-a-mapping": "must be a YAML mapping"}[case]
        assert needle in lines[0]

    def test_max_lines_passes_through(self, tmp_path: Path) -> None:
        write_file(tmp_path / "scripts" / "x.sh", "echo\n" * 50)
        result = _run_cli(
            "detect", str(tmp_path), "--max-lines", "10"
        )
        payload = json.loads(result.stdout)
        assert payload["scripts_inventory"][0]["size_flag"] == "oversized"
