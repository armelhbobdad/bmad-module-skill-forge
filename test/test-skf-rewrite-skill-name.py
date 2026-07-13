#!/usr/bin/env python3
"""Tests for skf-rewrite-skill-name.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-rewrite-skill-name.py"

spec = importlib.util.spec_from_file_location("skf_rewrite_skill_name", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run_cli(*args):
    """Invoke the script as a subprocess; return (returncode, parsed_stdout_or_None, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None
    return proc.returncode, parsed, proc.stderr


OLD = "rename"
NEW = "rename-skill"


# --- Frontmatter transform ----------------------------------------------------


class TestFrontmatter:
    def test_replaces_name_in_frontmatter_only(self):
        content = (
            "---\n"
            "name: rename\n"
            "description: A skill about the rename operation\n"
            "---\n"
            "# rename\n"
            "This body legitimately mentions rename and renamed things.\n"
        )
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert matched is True
        assert old == "rename"
        assert "name: rename-skill\n" in new
        # Body mentions preserved verbatim (not substituted).
        assert "This body legitimately mentions rename and renamed things." in new
        # description field untouched even though it contains "rename".
        assert "description: A skill about the rename operation" in new

    def test_substring_key_not_matched(self):
        # `renamed:` and a nested `  name:` must not be mistaken for the top-level name.
        content = (
            "---\n"
            "name: rename\n"
            "metadata:\n"
            "  name: nested-should-not-change\n"
            "renamed: 2020\n"
            "---\n"
            "body\n"
        )
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert old == "rename"
        assert "name: rename-skill\n" in new
        assert "  name: nested-should-not-change" in new
        assert "renamed: 2020" in new

    def test_preserves_quotes(self):
        content = "---\nname: 'rename'\ndescription: x\n---\nbody\n"
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert old == "rename"
        assert "name: 'rename-skill'\n" in new

    def test_missing_name_field(self):
        content = "---\ndescription: x\n---\nbody\n"
        new, old, matched = mod.rewrite_frontmatter_name(content, NEW)
        assert matched is False
        assert new == content

    def test_no_frontmatter_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_frontmatter_name("# just a body\n", NEW)

    def test_no_closing_delimiter_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_frontmatter_name("---\nname: rename\nno closing\n", NEW)


# --- JSON transforms ----------------------------------------------------------


class TestJsonField:
    def test_metadata_name_roundtrip_preserves_key_order(self):
        content = json.dumps(
            {"name": "rename", "version": "1.0.0", "language": "python"}, indent=2
        )
        new, old, matched = mod.rewrite_json_field(content, "name", NEW)
        assert old == "rename"
        assert matched is True
        data = json.loads(new)
        assert data["name"] == NEW
        assert list(data.keys()) == ["name", "version", "language"]
        assert new.endswith("\n")

    def test_provenance_skill_name(self):
        content = json.dumps({"skill_name": "rename", "entries": []}, indent=2)
        new, old, matched = mod.rewrite_json_field(content, "skill_name", NEW)
        assert old == "rename"
        assert json.loads(new)["skill_name"] == NEW

    def test_absent_field_is_set(self):
        content = json.dumps({"version": "1.0.0"}, indent=2)
        new, old, matched = mod.rewrite_json_field(content, "name", NEW)
        assert matched is False
        assert old is None
        assert json.loads(new)["name"] == NEW

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            mod.rewrite_json_field("{not valid", "name", NEW)


# --- Context-snippet transform ------------------------------------------------


class TestContextSnippet:
    def test_header_and_ide_root(self):
        content = "[rename v1.2.0]|root: .windsurf/skills/rename/\n|IMPORTANT: read me\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert details["header_rewritten"] is True
        assert "[rename-skill v1.2.0]" in new
        assert "root: .windsurf/skills/rename-skill/" in new
        assert details["roots"] == [
            {"old": ".windsurf/skills/rename/", "new": ".windsurf/skills/rename-skill/"}
        ]

    def test_draft_skills_prefix(self):
        content = "[rename v0.1.0]|root: skills/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: skills/rename-skill/" in new

    def test_legacy_nested_form_flattens(self):
        content = "[rename v0.1.0]|root: skills/rename/active/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: skills/rename-skill/" in new
        assert "active" not in new

    def test_prefix_containing_old_name_preserved(self):
        # A prefix segment that merely contains the old name must survive.
        content = "[rename v1.0.0]|root: .claude/rename-tools/rename/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert "root: .claude/rename-tools/rename-skill/" in new

    def test_header_substring_not_matched(self):
        # old_name is a substring of the actual header name -> no change.
        content = "[renamer v1.0.0]|root: .claude/skills/renamer/\n"
        new, details = mod.rewrite_context_snippet(content, OLD, NEW)
        assert new == content
        assert details["header_rewritten"] is False
        assert details["roots"] == []


# --- CLI: atomic write + exit codes -------------------------------------------


class TestCli:
    def test_frontmatter_writes_atomically(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: rename\ndescription: x\n---\n# rename\nrename body\n")
        rc, out, err = run_cli(f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert out["changed"] is True
        assert out["wrote"] == str(f)
        text = f.read_text()
        assert "name: rename-skill\n" in text
        assert "rename body" in text  # body preserved

    def test_metadata_cli(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": "rename", "version": "1.0.0"}, indent=2) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert json.loads(f.read_text())["name"] == NEW

    def test_no_change_no_write(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": NEW}, indent=2) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 0, err
        assert out["changed"] is False
        assert out["wrote"] is None

    def test_dry_run_does_not_write(self, tmp_path):
        f = tmp_path / "SKILL.md"
        original = "---\nname: rename\ndescription: x\n---\nbody\n"
        f.write_text(original)
        rc, out, err = run_cli(
            f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW, "--dry-run"
        )
        assert rc == 0, err
        assert out["dry_run"] is True
        assert "name: rename-skill" in out["new_content"]
        assert f.read_text() == original  # unchanged on disk

    def test_invalid_new_name_exit_1(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text(json.dumps({"name": "rename"}) + "\n")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", "Bad Name")
        assert rc == 1

    def test_missing_target_exit_1(self, tmp_path):
        rc, out, err = run_cli(
            tmp_path / "nope.json", "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW
        )
        assert rc == 1

    def test_malformed_skill_md_exit_2(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("# no frontmatter here\n")
        rc, out, err = run_cli(f, "--kind", "skill-frontmatter", "--old-name", OLD, "--new-name", NEW)
        assert rc == 2

    def test_invalid_json_exit_2(self, tmp_path):
        f = tmp_path / "metadata.json"
        f.write_text("{not valid json")
        rc, out, err = run_cli(f, "--kind", "metadata-json", "--old-name", OLD, "--new-name", NEW)
        assert rc == 2
