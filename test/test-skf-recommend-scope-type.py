#!/usr/bin/env python3
"""Tests for skf-recommend-scope-type.py.

The script is pure — it walks a fixed 5-rule ladder against a payload of
intent text + analysis signals and returns a recommendation. Tests build
payloads inline and call recommend() directly, plus a few subprocess
cases for CLI wiring.
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
    / "skf-recommend-scope-type.py"
)

spec = importlib.util.spec_from_file_location("skf_recommend_scope_type", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VALID_SCOPE_TYPES = {
    "full-library",
    "specific-modules",
    "public-api",
    "component-library",
    "reference-app",
    "docs-only",
}

VALID_HEURISTICS = {
    "component-registry",
    "reference-app-keywords",
    "specific-modules-naming",
    "specific-modules-count",
    "narrow-public-api",
    "default-full-library",
    "docs-only-shortcircuit",
}


def assert_result_shape(result: dict) -> None:
    assert set(result.keys()) >= {"scope_type", "matched_heuristic", "signals", "rationale"}
    assert result["scope_type"] in VALID_SCOPE_TYPES
    assert result["matched_heuristic"] in VALID_HEURISTICS
    assert isinstance(result["signals"], dict)
    assert isinstance(result["rationale"], str) and result["rationale"]


# --------------------------------------------------------------------------
# Short-circuit: docs-only
# --------------------------------------------------------------------------


def test_docs_only_short_circuits_before_any_other_rule():
    result = mod.recommend(
        {
            "intent": "starter wiring with 47-entry registry.ts",  # would otherwise match multiple rules
            "module_count": 99,
            "export_count": 3,
            "tree": ["src/components/registry.ts"],
            "source_type": "docs-only",
            "mode": "interactive",
        }
    )
    assert_result_shape(result)
    assert result["scope_type"] == "docs-only"
    assert result["matched_heuristic"] == "docs-only-shortcircuit"


# --------------------------------------------------------------------------
# Rule 1: component-registry
# --------------------------------------------------------------------------


def test_interactive_registry_with_10_plus_entries():
    content = "export const registry: Component[] = [" + ",".join(["{ id: 'x' }"] * 12) + "];"
    result = mod.recommend(
        {
            "intent": "build a UI library skill",
            "tree": ["src/components/registry.ts"],
            "entry_files": [{"path": "src/components/registry.ts", "content": content}],
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "component-library"
    assert result["matched_heuristic"] == "component-registry"
    assert result["signals"]["registry_path"] == "src/components/registry.ts"
    assert result["signals"]["contents_inspected"] is True


def test_interactive_registry_with_component_array_annotation_passes_even_with_few_entries():
    content = "const registry: Component[] = [{id:'a'},{id:'b'}];"
    result = mod.recommend(
        {
            "intent": "skill the design system",
            "tree": ["src/components/registry.tsx"],
            "entry_files": [{"path": "src/components/registry.tsx", "content": content}],
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "component-library"
    assert result["signals"]["component_array_annotation"] is True


def test_interactive_registry_with_few_entries_and_no_annotation_does_not_match():
    content = "const x = [{a:1},{b:2}];"
    result = mod.recommend(
        {
            "intent": "library skill",
            "tree": ["src/components/registry.ts"],
            "entry_files": [{"path": "src/components/registry.ts", "content": content}],
            "mode": "interactive",
            "module_count": 0,
            "export_count": 5,
        }
    )
    assert result["scope_type"] == "full-library"


def test_headless_falls_back_to_presence_only_when_no_contents():
    result = mod.recommend(
        {
            "intent": "library skill",
            "tree": ["src/components/registry.ts"],
            "entry_files": None,
            "mode": "headless",
        }
    )
    assert result["scope_type"] == "component-library"
    assert result["signals"]["contents_inspected"] is False


def test_interactive_without_contents_does_not_match_component_library():
    result = mod.recommend(
        {
            "intent": "library skill",
            "tree": ["src/components/registry.ts"],
            "entry_files": None,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "full-library"


# --------------------------------------------------------------------------
# Rule 2: reference-app-keywords
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent",
    [
        "I want to skill the IPC wiring of this Electron starter",
        "It's a build config example that shows lifecycle hooks",
        "The repo is a reference app for Tauri integration example",
    ],
)
def test_reference_app_keywords_match(intent):
    result = mod.recommend({"intent": intent, "tree": [], "mode": "interactive"})
    assert result["scope_type"] == "reference-app"
    assert result["matched_heuristic"] == "reference-app-keywords"
    assert result["signals"]["keywords"]


# --------------------------------------------------------------------------
# Rule 3: specific-modules-naming and -count
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent",
    [
        "I just want the auth module",
        "We only need the streaming part",
        "Specifically the parser, nothing else",
        "just auth module please",
    ],
)
def test_specific_modules_naming_phrases(intent):
    result = mod.recommend({"intent": intent, "tree": [], "module_count": 0, "mode": "interactive"})
    assert result["scope_type"] == "specific-modules"
    assert result["matched_heuristic"] == "specific-modules-naming"


def test_specific_modules_count_when_no_naming_phrase():
    result = mod.recommend(
        {
            "intent": "skill this whole library",  # no narrow phrase
            "tree": [],
            "module_count": 8,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "specific-modules"
    assert result["matched_heuristic"] == "specific-modules-count"
    assert result["signals"]["module_count"] == 8


def test_module_count_below_threshold_does_not_trigger():
    result = mod.recommend(
        {
            "intent": "skill this library",
            "tree": [],
            "module_count": 5,
            "export_count": 50,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "full-library"


# --------------------------------------------------------------------------
# Rule 4: narrow-public-api
# --------------------------------------------------------------------------


def test_narrow_public_api_match_with_keyword_and_small_export_count():
    result = mod.recommend(
        {
            "intent": "I need the SDK only",
            "tree": [],
            "export_count": 6,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "public-api"
    assert result["matched_heuristic"] == "narrow-public-api"


def test_narrow_public_api_keyword_without_small_exports_does_not_trigger():
    result = mod.recommend(
        {
            "intent": "I need the SDK",
            "tree": [],
            "export_count": 47,  # above threshold
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "full-library"


def test_small_exports_without_keyword_does_not_trigger():
    result = mod.recommend(
        {
            "intent": "general use",
            "tree": [],
            "export_count": 4,  # below threshold but no keyword
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "full-library"


# --------------------------------------------------------------------------
# Rule 5: default-full-library
# --------------------------------------------------------------------------


def test_default_full_library_when_no_signal_matches():
    result = mod.recommend(
        {
            "intent": "skill this library",
            "tree": [],
            "module_count": 2,
            "export_count": 30,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "full-library"
    assert result["matched_heuristic"] == "default-full-library"


# --------------------------------------------------------------------------
# Rule precedence
# --------------------------------------------------------------------------


def test_component_registry_takes_precedence_over_reference_app_keywords():
    """When both fire, component-registry wins (rule 1 before rule 2)."""
    content = "const r: Component[] = [];"
    result = mod.recommend(
        {
            "intent": "starter wiring example",  # would match reference-app
            "tree": ["src/components/registry.ts"],
            "entry_files": [{"path": "src/components/registry.ts", "content": content}],
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "component-library"


def test_reference_app_takes_precedence_over_specific_modules():
    """When both fire, reference-app wins (rule 2 before rule 3)."""
    result = mod.recommend(
        {
            "intent": "starter wiring with just the auth module",
            "tree": [],
            "module_count": 99,
            "mode": "interactive",
        }
    )
    assert result["scope_type"] == "reference-app"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_invalid_source_type_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend({"source_type": "weird", "tree": [], "mode": "interactive"})
    assert exc_info.value.code == 2


def test_invalid_mode_dies():
    with pytest.raises(SystemExit) as exc_info:
        mod.recommend({"tree": [], "mode": "background"})
    assert exc_info.value.code == 2


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_cli_stdin_payload_round_trip():
    payload = {
        "intent": "starter integration example",
        "tree": [],
        "mode": "headless",
    }
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "reference-app"


def test_cli_json_arg():
    payload = {"source_type": "docs-only", "tree": [], "mode": "headless"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["scope_type"] == "docs-only"


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
