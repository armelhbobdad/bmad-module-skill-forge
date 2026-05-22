#!/usr/bin/env python3
"""Tests for skf-detect-language.py.

Pure-function rule-walk tests against an inline file tree, plus a few
subprocess cases to verify CLI wiring (stdin/argparse/exit-code).
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
    / "skf-detect-language.py"
)

spec = importlib.util.spec_from_file_location("skf_detect_language", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def assert_result_shape(out: dict) -> None:
    assert set(out.keys()) >= {
        "language",
        "confidence",
        "detection_source",
        "fallback_to_extension_frequency",
    }, out
    assert out["confidence"] in {"high", "medium", "low"}
    assert isinstance(out["detection_source"], str) and out["detection_source"]
    assert isinstance(out["fallback_to_extension_frequency"], bool)


# --------------------------------------------------------------------------
# Rule 1 — package.json + tsconfig.json disambiguation
# --------------------------------------------------------------------------


def test_package_json_only_returns_javascript_high():
    result = mod.detect({"tree": ["package.json", "src/index.js"]})
    assert_result_shape(result)
    assert result["language"] == "javascript"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


def test_package_json_with_tsconfig_returns_typescript_high():
    result = mod.detect({"tree": ["package.json", "tsconfig.json", "src/index.ts"]})
    assert result["language"] == "typescript"
    assert result["confidence"] == "high"
    assert "tsconfig.json" in result["detection_source"]


def test_package_json_in_subdir_still_matches():
    result = mod.detect({"tree": ["packages/foo/package.json", "packages/foo/src/index.js"]})
    assert result["language"] == "javascript"


# --------------------------------------------------------------------------
# Rule 0 — workspace_signal precedence
# --------------------------------------------------------------------------


def test_cargo_workspace_signal_wins_over_nested_package_json_tsconfig():
    """The reported bug: a Rust cargo-workspace root with a docs/ TS site must detect rust, not typescript."""
    tree = [
        "Cargo.toml",
        "crates/core/src/lib.rs",
        "docs/package.json",
        "docs/tsconfig.json",
        "docs/pages/index.tsx",
    ]
    result = mod.detect({"tree": tree, "workspace_signal": "cargo-workspace"})
    assert_result_shape(result)
    assert result["language"] == "rust"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False
    assert "cargo-workspace" in result["detection_source"]


def test_python_multi_package_signal_returns_python():
    tree = ["packages/a/pyproject.toml", "docs/package.json", "docs/tsconfig.json"]
    result = mod.detect({"tree": tree, "workspace_signal": "python-multi-package"})
    assert result["language"] == "python"
    assert result["confidence"] == "high"


def test_npm_workspace_signal_falls_through_to_package_json_rule():
    """JS-family workspace kinds carry no override; a root package.json+tsconfig still resolves typescript."""
    tree = ["package.json", "tsconfig.json", "packages/a/src/index.ts"]
    result = mod.detect({"tree": tree, "workspace_signal": "npm-workspaces"})
    assert result["language"] == "typescript"
    assert result["confidence"] == "high"


def test_unknown_or_null_workspace_signal_is_ignored():
    """generic-folders / unexpected values fall through to the normal rule walk."""
    tree = ["package.json", "src/index.js"]
    assert mod.detect({"tree": tree, "workspace_signal": "generic-folders"})["language"] == "javascript"
    assert mod.detect({"tree": tree, "workspace_signal": None})["language"] == "javascript"


def test_no_workspace_signal_preserves_legacy_behavior():
    """Absent workspace_signal: a nested package.json still matches rule 1 (unchanged)."""
    result = mod.detect({"tree": ["docs/package.json", "Cargo.toml", "src/lib.rs"]})
    assert result["language"] == "javascript"


# --------------------------------------------------------------------------
# Rules 2-6 — single-basename manifests
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "manifest,expected_lang",
    [
        ("Cargo.toml", "rust"),
        ("pyproject.toml", "python"),
        ("setup.py", "python"),
        ("setup.cfg", "python"),
        ("go.mod", "go"),
        ("pom.xml", "java"),
        ("build.gradle.kts", "kotlin"),
        ("Gemfile", "ruby"),
    ],
)
def test_manifest_rules_high_confidence(manifest, expected_lang):
    tree = [manifest, "src/main.unknown"]
    result = mod.detect({"tree": tree})
    assert result["language"] == expected_lang
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False
    assert manifest in result["detection_source"]


# --------------------------------------------------------------------------
# Rule 7 — build.gradle (Groovy) Java/Kotlin disambiguation
# --------------------------------------------------------------------------


def test_build_gradle_with_kotlin_path_returns_kotlin_medium():
    result = mod.detect(
        {"tree": ["build.gradle", "src/main/kotlin/com/example/App.kt"]}
    )
    assert result["language"] == "kotlin"
    assert result["confidence"] == "medium"
    assert "src/main/kotlin/" in result["detection_source"]


def test_build_gradle_without_kotlin_path_defaults_to_java_medium():
    result = mod.detect(
        {"tree": ["build.gradle", "src/main/java/com/example/App.java"]}
    )
    assert result["language"] == "java"
    assert result["confidence"] == "medium"
    assert "defaulting to java" in result["detection_source"]


def test_build_gradle_kts_takes_precedence_over_groovy_when_both_present():
    """Kotlin .kts manifest hits the basename loop first — even with a sibling Groovy build.gradle."""
    result = mod.detect(
        {"tree": ["build.gradle", "build.gradle.kts", "src/main/kotlin/A.kt"]}
    )
    assert result["language"] == "kotlin"
    assert result["confidence"] == "high"


# --------------------------------------------------------------------------
# Rule 8 — csproj / sln
# --------------------------------------------------------------------------


def test_csproj_returns_csharp():
    result = mod.detect({"tree": ["MyApp.csproj", "Program.cs"]})
    assert result["language"] == "csharp"
    assert result["confidence"] == "high"


def test_sln_returns_csharp():
    result = mod.detect({"tree": ["MyApp.sln", "src/Program.cs"]})
    assert result["language"] == "csharp"


# --------------------------------------------------------------------------
# Rule 10 — extension-frequency fallback
# --------------------------------------------------------------------------


def test_dominant_extension_returns_medium_confidence():
    tree = ["a.swift", "b.swift", "c.swift", "README.md", "LICENSE"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "swift"
    assert result["confidence"] == "medium"
    assert result["fallback_to_extension_frequency"] is True
    assert "extension frequency" in result["detection_source"]


def test_no_clear_winner_returns_low_confidence():
    tree = ["a.py", "b.py", "c.js", "d.js", "e.rb"]  # 2/2/1, top is 40% (below 50%)
    result = mod.detect({"tree": tree})
    assert result["confidence"] == "low"
    assert result["fallback_to_extension_frequency"] is True


def test_no_recognized_source_extensions_returns_unknown():
    tree = ["README.md", "LICENSE", "Dockerfile", "data.json"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "unknown"
    assert result["confidence"] == "low"
    assert result["fallback_to_extension_frequency"] is True


def test_php_via_extension_frequency():
    tree = ["index.php", "lib.php", "config.php", "README.md"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "php"


# --------------------------------------------------------------------------
# Rule precedence
# --------------------------------------------------------------------------


def test_package_json_takes_precedence_over_dominant_python_extensions():
    """Manifest rule 1 fires before extension fallback."""
    tree = ["package.json", "main.py", "lib.py", "test.py"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "javascript"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


def test_cargo_toml_takes_precedence_over_python_files():
    tree = ["Cargo.toml", "scripts/build.py", "scripts/release.py"]
    result = mod.detect({"tree": tree})
    assert result["language"] == "rust"


def test_pom_xml_takes_precedence_over_build_gradle():
    """pom.xml fires in the manifest loop (java, high); build.gradle is post-loop and never reached."""
    result = mod.detect(
        {"tree": ["pom.xml", "build.gradle", "src/main/java/com/example/App.java"]}
    )
    assert result["language"] == "java"
    assert result["confidence"] == "high"
    assert result["fallback_to_extension_frequency"] is False


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_missing_tree_dies_with_2():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({})
    assert exc_info.value.code == 2


def test_empty_tree_dies_with_2():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({"tree": []})
    assert exc_info.value.code == 2


def test_tree_not_a_list_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.detect({"tree": "package.json"})
    assert exc_info.value.code == 2


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_cli_stdin_payload_round_trip():
    payload = {"tree": ["Cargo.toml", "src/lib.rs"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["language"] == "rust"


def test_cli_json_arg():
    payload = {"tree": ["pyproject.toml"]}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["language"] == "python"


def test_cli_empty_stdin_dies_with_2():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "empty input" in proc.stderr


def test_cli_invalid_json_dies_with_2():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input="{not valid",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "invalid JSON" in proc.stderr
