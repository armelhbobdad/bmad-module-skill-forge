#!/usr/bin/env python3
"""Tests for skf-description-guard.py.

Covers:
  - capture: happy path, missing file, no frontmatter, missing description
  - classify_divergence: identical, whitespace-only, replaced, truncated, deleted
  - restore_description: inline/quoted/block-scalar shapes; key order preserved
  - CLI integration via subprocess for capture and verify-restore
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _parse_frontmatter(text: str) -> dict:
    """Extract the frontmatter mapping from a SKILL.md text blob."""
    assert text.startswith("---\n"), "expected leading frontmatter fence"
    rest = text[4:]
    close = rest.find("\n---\n")
    assert close != -1, "expected closing frontmatter fence"
    return yaml.safe_load(rest[:close])


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-description-guard.py"

spec = importlib.util.spec_from_file_location("skf_description_guard", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


SAMPLE_DESC = "Compiles a verified agent skill from a brief and source code."


def _write_skill(tmp_path: Path, description: str, *, shape: str = "inline") -> Path:
    """Write a SKILL.md with given description in one of three frontmatter shapes."""
    if shape == "inline":
        fm = f"""---
name: my-skill
description: {description}
---

# My Skill

Body content.
"""
    elif shape == "quoted":
        fm = f'''---
name: my-skill
description: "{description}"
---

# My Skill

Body content.
'''
    elif shape == "block":
        fm = f"""---
name: my-skill
description: |
  {description}
---

# My Skill

Body content.
"""
    else:
        raise ValueError(shape)
    path = tmp_path / "SKILL.md"
    path.write_text(fm, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# read_description / capture
# --------------------------------------------------------------------------


class TestReadDescription:
    def test_inline_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        desc, hash_ = mod.read_description(skill)
        assert desc == SAMPLE_DESC
        assert hash_.startswith("sha256:")
        assert len(hash_) == len("sha256:") + 64

    def test_quoted_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="quoted")
        desc, _ = mod.read_description(skill)
        assert desc == SAMPLE_DESC

    def test_block_description(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="block")
        desc, _ = mod.read_description(skill)
        # block scalar preserves a trailing newline by default
        assert desc.strip() == SAMPLE_DESC

    def test_no_frontmatter_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("# My Skill\n\nNo frontmatter here.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no frontmatter"):
            mod.read_description(skill)

    def test_missing_description_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: foo\n---\n\nBody\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no `description`"):
            mod.read_description(skill)

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: : :\n---\nBody\n", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid YAML"):
            mod.read_description(skill)


# --------------------------------------------------------------------------
# classify_divergence
# --------------------------------------------------------------------------


class TestClassifyDivergence:
    def test_byte_identical(self) -> None:
        assert mod.classify_divergence("hello world", "hello world") == "none"

    def test_whitespace_only_trailing_newline(self) -> None:
        assert mod.classify_divergence("hello world", "hello world\n") == "whitespace-only"

    def test_whitespace_only_collapsed_runs(self) -> None:
        assert mod.classify_divergence("hello  world", "hello world") == "whitespace-only"

    def test_whitespace_only_trim(self) -> None:
        assert mod.classify_divergence("hello world", "  hello world  ") == "whitespace-only"

    def test_replaced(self) -> None:
        assert mod.classify_divergence("hello world", "goodbye world") == "replaced"

    def test_truncated(self) -> None:
        assert mod.classify_divergence("hello world today", "hello world") == "truncated"

    def test_truncated_single_word(self) -> None:
        assert mod.classify_divergence("hello world", "hello") == "truncated"

    def test_deleted(self) -> None:
        assert mod.classify_divergence("hello world", "") == "deleted"
        assert mod.classify_divergence("hello world", "   \t  ") == "deleted"

    def test_angle_bracket_reintroduction_is_replaced(self) -> None:
        # post-tool description re-introduces an angle-bracket token —
        # token-stream comparison sees a different word
        captured = "Use when running tests"
        current = "Use when running tests <component>"
        assert mod.classify_divergence(captured, current) == "replaced"

    def test_is_diverged_true_for_real_changes(self) -> None:
        assert mod.is_diverged("replaced") is True
        assert mod.is_diverged("truncated") is True
        assert mod.is_diverged("deleted") is True

    def test_is_diverged_false_for_non_changes(self) -> None:
        assert mod.is_diverged("none") is False
        assert mod.is_diverged("whitespace-only") is False


# --------------------------------------------------------------------------
# restore_description
# --------------------------------------------------------------------------


class TestRestoreDescription:
    def test_restore_inline_preserves_other_keys(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
description: tool-rewritten short version
version: 1.2.3
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "the authoritative original description")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        # frontmatter parses as valid YAML with all expected keys
        assert fm["name"] == "my-skill"
        assert fm["description"] == "the authoritative original description"
        assert fm["version"] == "1.2.3"
        # key order preserved (name → description → version)
        assert list(fm.keys()) == ["name", "description", "version"]
        # body untouched
        assert "# Body" in text

    def test_restore_quoted(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="quoted")
        mod.restore_description(skill, "original")
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        assert fm["description"] == "original"

    def test_restore_block_scalar_collapses_to_inline(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="block")
        mod.restore_description(skill, "original")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert fm["description"] == "original"
        # the prior block-scalar shape (`description: |` with continuation lines)
        # MUST NOT survive — its leftover continuation block was the original
        # failure mode this fix targets
        assert "description: |" not in text
        assert "description: >" not in text

    def test_restore_escapes_embedded_quotes(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "x", shape="inline")
        mod.restore_description(skill, 'has "double" quotes and \\ backslash')
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        # round-trip through YAML emit/parse preserves the value verbatim,
        # regardless of which quoting style safe_dump chose
        assert fm["description"] == 'has "double" quotes and \\ backslash'

    def test_restore_atomic_no_partial_file(self, tmp_path: Path) -> None:
        # after restore, no .skf-guard.tmp files remain in the directory
        skill = _write_skill(tmp_path, "tool wrote this", shape="inline")
        mod.restore_description(skill, "original")
        leftover = [p for p in tmp_path.iterdir() if ".skf-guard.tmp" in p.name]
        assert leftover == []

    def test_restore_roundtrip_via_read(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, "tool wrote this", shape="inline")
        mod.restore_description(skill, "the original")
        desc, _ = mod.read_description(skill)
        assert desc == "the original"

    def test_restore_block_scalar_with_keys_after(self, tmp_path: Path) -> None:
        """Regression: folded `>` description followed by sibling keys.

        The previous line-rewrite implementation could leave continuation
        lines on disk in certain layouts, producing invalid YAML where the
        new inline `description:` was followed by orphan indented text.
        With YAML round-trip, the output is always parseable.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
description: >
  Tool-rewritten short
  version on multiple
  lines.
license: MIT
metadata:
  version: 1.2.3
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "the authoritative original")
        text = skill.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert fm["description"] == "the authoritative original"
        assert fm["name"] == "my-skill"
        assert fm["license"] == "MIT"
        assert fm["metadata"] == {"version": "1.2.3"}

    def test_restore_does_not_touch_nested_description_key(self, tmp_path: Path) -> None:
        """Regression: a `description:` inside a nested mapping must not
        be mistaken for the top-level field, and must be left untouched.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
metadata:
  description: nested — must not be touched
name: my-skill
description: top-level tool-rewritten
---

# Body
""",
            encoding="utf-8",
        )
        mod.restore_description(skill, "top-level original")
        fm = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        assert fm["description"] == "top-level original"
        assert fm["metadata"]["description"] == "nested — must not be touched"

    def test_restore_when_only_nested_description_exists_raises(
        self, tmp_path: Path
    ) -> None:
        """Regression: if the top-level frontmatter has no `description`
        field (only a nested one), restore must fail loudly rather than
        silently rewriting the nested key.
        """
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            """---
name: my-skill
related:
  description: nested only
---

# Body
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="no `description`"):
            mod.restore_description(skill, "should not be written anywhere")


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
    def test_capture_emits_json(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli("capture", str(skill))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["description"] == SAMPLE_DESC
        assert payload["schema_hash"].startswith("sha256:")

    def test_capture_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("capture", str(tmp_path / "missing.md"))
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_verify_restore_no_divergence(self, tmp_path: Path) -> None:
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is False
        assert payload["restored"] is False
        assert payload["diff_kind"] == "none"

    def test_verify_restore_whitespace_only_no_restore(self, tmp_path: Path) -> None:
        # disk has trailing whitespace, captured doesn't — token streams match
        skill = _write_skill(tmp_path, SAMPLE_DESC + "  ", shape="quoted")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is False
        assert payload["diff_kind"] == "whitespace-only"

    def test_verify_restore_replaced_restores(self, tmp_path: Path) -> None:
        # disk has tool-rewritten short version; captured is the real one
        skill = _write_skill(tmp_path, "tool short version", shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diverged"] is True
        assert payload["restored"] is True
        assert payload["diff_kind"] == "replaced"
        # file now has the captured description
        text = skill.read_text(encoding="utf-8")
        assert SAMPLE_DESC in text

    def test_verify_restore_truncated_restores(self, tmp_path: Path) -> None:
        # disk has a truncated version of the captured description
        skill = _write_skill(tmp_path, "Compiles a verified agent skill", shape="inline")
        result = _run_cli(
            "verify-restore", str(skill), "--captured-description", SAMPLE_DESC
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["diff_kind"] == "truncated"
        assert payload["restored"] is True

    def test_verify_restore_missing_arg_exits_2(self, tmp_path: Path) -> None:
        # argparse missing-required-arg exits 2 by convention
        skill = _write_skill(tmp_path, SAMPLE_DESC, shape="inline")
        result = _run_cli("verify-restore", str(skill))
        assert result.returncode == 2
        assert "captured-description" in result.stderr
