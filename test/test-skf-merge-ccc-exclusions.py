#!/usr/bin/env python3
"""Tests for skf-merge-ccc-exclusions.py.

Highest-value tests:
- Validation rules from PR #248 reject the exact failure modes the prior
  prose-driven version couldn't detect (empty, absolute, glob-meta).
- Set-union merge is idempotent — re-running against a settings.yml that
  already has the SKF patterns is a no-op (mtime unchanged).
- User-customized exclude_patterns entries are preserved (not overwritten).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-merge-ccc-exclusions.py"
)

spec = importlib.util.spec_from_file_location("skf_merge_ccc_exclusions", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def tmp_project():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def _settings_path(project: Path) -> Path:
    return project / ".cocoindex_code" / "settings.yml"


def _read_settings(project: Path) -> dict:
    path = _settings_path(project)
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


# ─── validate_config_value: PR #248 rules ───────────────────────────────────


@pytest.mark.parametrize("value,is_valid", [
    # Valid — relative paths with no glob meta
    ("skills",                       True),
    ("_bmad-output/forge-data",      True),
    ("nested/path/value",            True),
    ("path-with.dots_and-dashes",    True),
    # Invalid — empty / whitespace
    ("",                             False),
    ("   ",                          False),
    ("\t",                           False),
    # Invalid — absolute / anchored
    ("/abs/path",                    False),
    ("~/home",                       False),
    ("./rel",                        False),
    # Invalid — glob meta
    ("path/*",                       False),
    ("?ile",                         False),
    ("dir[abc]",                     False),
    ("**/wildcard",                  False),
])
def test_validate_config_value(value, is_valid):
    cleaned, warning = mod.validate_config_value("skills_output_folder", value)
    if is_valid:
        assert cleaned is not None
        assert warning is None
    else:
        assert cleaned is None
        assert warning is not None
        assert "skills_output_folder" in warning  # Warning names the offending key


def test_validate_warning_messages_are_actionable():
    """Each rejection reason should name (a) the key, (b) the failure mode, (c) where to fix it."""
    _, w = mod.validate_config_value("skills_output_folder", "")
    assert "skills_output_folder" in w
    assert "empty" in w.lower() or "whitespace" in w.lower()
    assert "_bmad/skf/config.yaml" in w  # config file location

    _, w = mod.validate_config_value("forge_data_folder", "/abs")
    assert "forge_data_folder" in w
    assert "absolute" in w.lower() or "anchored" in w.lower()

    _, w = mod.validate_config_value("forge_data_folder", "x*")
    assert "glob meta" in w.lower()


def test_validate_strips_surrounding_whitespace():
    """A value like '  skills  ' should be treated as 'skills', not rejected."""
    cleaned, warning = mod.validate_config_value("skills_output_folder", "  skills  ")
    assert cleaned == "skills"
    assert warning is None


# ─── assemble_patterns ─────────────────────────────────────────────────────


def test_assemble_patterns_always_includes_four_hardcoded():
    patterns, warnings = mod.assemble_patterns("skills", "_bmad-output/forge-data")
    assert "**/_bmad" in patterns
    assert "**/_bmad-output" in patterns
    assert "**/.claude" in patterns
    assert "**/_skf-learn" in patterns
    assert "**/skills" in patterns
    assert "**/_bmad-output/forge-data" in patterns
    assert warnings == []


def test_assemble_patterns_skips_rejected_config_values():
    """Config-value rejection MUST NOT disable the 4 always-include patterns."""
    patterns, warnings = mod.assemble_patterns("", "/abs/path")
    # Always-include patterns survive
    for p in mod.ALWAYS_INCLUDE:
        assert p in patterns
    # Bad values DON'T appear as malformed globs
    assert "**/" not in patterns
    assert "**//abs/path" not in patterns
    # Both produce warnings
    assert len(warnings) == 2


def test_assemble_patterns_empty_skills_keeps_forge_data():
    """One bad value doesn't poison the other."""
    patterns, warnings = mod.assemble_patterns("", "_bmad-output/forge-data")
    assert "**/_bmad-output/forge-data" in patterns
    assert "**/" not in patterns
    assert len(warnings) == 1
    assert "skills_output_folder" in warnings[0]


# ─── merge_patterns ────────────────────────────────────────────────────────


def test_merge_patterns_appends_new():
    merged, added = mod.merge_patterns(["**/node_modules"], ["**/_bmad", "**/_bmad-output"])
    assert merged == ["**/node_modules", "**/_bmad", "**/_bmad-output"]
    assert added == ["**/_bmad", "**/_bmad-output"]


def test_merge_patterns_skips_already_present():
    merged, added = mod.merge_patterns(
        ["**/node_modules", "**/_bmad"],
        ["**/_bmad", "**/_bmad-output"],
    )
    assert merged == ["**/node_modules", "**/_bmad", "**/_bmad-output"]
    assert added == ["**/_bmad-output"]


def test_merge_patterns_preserves_existing_order():
    merged, _ = mod.merge_patterns(
        ["**/dist", "**/build", "**/node_modules"],
        ["**/_bmad"],
    )
    # Existing order preserved, new entry appended
    assert merged == ["**/dist", "**/build", "**/node_modules", "**/_bmad"]


def test_merge_patterns_idempotent_on_full_overlap():
    """Re-running with all-already-present yields no changes."""
    existing = list(mod.ALWAYS_INCLUDE) + ["**/skills"]
    to_add   = list(mod.ALWAYS_INCLUDE) + ["**/skills"]
    merged, added = mod.merge_patterns(existing, to_add)
    assert merged == existing
    assert added == []


# ─── End-to-end CLI: first run (no settings.yml) ────────────────────────────


def _run(project: Path, skills="skills", forge_data="_bmad-output/forge-data") -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--project-root", str(project),
         "--skills-output-folder", skills,
         "--forge-data-folder", forge_data],
        capture_output=True, text=True, timeout=10,
    )
    payload = json.loads(result.stdout) if result.stdout else None
    return result.returncode, payload, result.stderr


def test_cli_first_run_creates_settings_yml(tmp_project):
    rc, payload, stderr = _run(tmp_project)
    assert rc == 0, f"stderr: {stderr}"
    assert payload["status"] == "ok"
    assert payload["settings_yml_existed"] is False
    assert payload["written"] is True
    assert payload["patterns_added"] == 6  # 4 always + 2 config
    assert payload["warnings"] == []
    # File created with all 6 patterns
    settings = _read_settings(tmp_project)
    excludes = settings["exclude_patterns"]
    for p in mod.ALWAYS_INCLUDE:
        assert p in excludes
    assert "**/skills" in excludes
    assert "**/_bmad-output/forge-data" in excludes


def test_cli_re_run_is_no_op_after_first_write(tmp_project):
    # First run creates the file
    _run(tmp_project)
    settings_path = _settings_path(tmp_project)
    mtime_before = settings_path.stat().st_mtime_ns

    # Second run with identical inputs should be a no-op (no write, no mtime change)
    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert payload["written"] is False
    assert payload["patterns_added"] == 0
    assert payload["patterns_already_present"] == 6
    assert settings_path.stat().st_mtime_ns == mtime_before


def test_cli_existing_settings_with_user_customizations_preserved(tmp_project):
    """A pre-existing settings.yml with user excludes must keep them."""
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        "exclude_patterns:\n"
        "  - '**/node_modules'\n"
        "  - '**/dist'\n"
        "other_user_setting: keep_me\n",
        encoding="utf-8",
    )

    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert payload["settings_yml_existed"] is True
    assert payload["written"] is True
    assert payload["patterns_added"] == 6  # All 6 SKF patterns are new

    settings = _read_settings(tmp_project)
    # User customizations preserved
    assert "**/node_modules" in settings["exclude_patterns"]
    assert "**/dist" in settings["exclude_patterns"]
    assert settings["other_user_setting"] == "keep_me"
    # Plus all SKF patterns appended
    for p in mod.ALWAYS_INCLUDE:
        assert p in settings["exclude_patterns"]


def test_cli_partial_overlap_only_adds_missing(tmp_project):
    """Some SKF patterns already present — only the missing ones are added."""
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    # User has manually added two of the four always-include patterns.
    settings_path.write_text(
        "exclude_patterns:\n"
        "  - '**/_bmad'\n"
        "  - '**/.claude'\n",
        encoding="utf-8",
    )

    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert payload["written"] is True
    # 6 SKF patterns total, 2 already present, 4 newly added
    assert payload["patterns_added"] == 4
    assert payload["patterns_already_present"] == 2
    assert "**/_bmad" not in payload["patterns_added_list"]
    assert "**/.claude" not in payload["patterns_added_list"]


# ─── PR #248 incident reproductions ─────────────────────────────────────────


def test_cli_pr248_empty_skills_folder(tmp_project):
    """User has skills_output_folder='' in config — refuse, warn, but still write hardcoded patterns."""
    rc, payload, _ = _run(tmp_project, skills="", forge_data="_bmad-output/forge-data")
    assert rc == 0
    settings = _read_settings(tmp_project)
    assert "**/" not in settings["exclude_patterns"]  # The would-be-malformed glob is NOT present
    # Always-include patterns still applied
    for p in mod.ALWAYS_INCLUDE:
        assert p in settings["exclude_patterns"]
    # forge_data_folder still applied (one bad value doesn't poison the other)
    assert "**/_bmad-output/forge-data" in settings["exclude_patterns"]
    # Warning is surfaced
    assert any("skills_output_folder" in w for w in payload["warnings"])


def test_cli_pr248_absolute_skills_folder(tmp_project):
    rc, payload, _ = _run(tmp_project, skills="/home/u/skills", forge_data="_bmad-output/forge-data")
    assert rc == 0
    settings = _read_settings(tmp_project)
    # Malformed `**//home/u/skills` glob NOT present
    assert "**//home/u/skills" not in settings["exclude_patterns"]
    assert any("skills_output_folder" in w and ("absolute" in w.lower() or "anchored" in w.lower())
               for w in payload["warnings"])


def test_cli_pr248_glob_meta_in_forge_data_folder(tmp_project):
    rc, payload, _ = _run(tmp_project, skills="skills", forge_data="forge-*")
    assert rc == 0
    settings = _read_settings(tmp_project)
    assert "**/forge-*" not in settings["exclude_patterns"]
    assert any("forge_data_folder" in w and "glob meta" in w.lower() for w in payload["warnings"])


# ─── Error paths ────────────────────────────────────────────────────────────


def test_cli_missing_required_arg():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--skills-output-folder", "skills"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


def test_cli_malformed_existing_settings(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("exclude_patterns: [unclosed\n", encoding="utf-8")
    rc, _, stderr = _run(tmp_project)
    assert rc == 1
    err = json.loads(stderr)
    assert "failed to parse" in err["message"]


def test_cli_non_list_exclude_patterns_dies(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("exclude_patterns: 42\n", encoding="utf-8")
    rc, _, stderr = _run(tmp_project)
    assert rc == 1


def test_cli_non_mapping_top_level_dies(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    rc, _, stderr = _run(tmp_project)
    assert rc == 1
