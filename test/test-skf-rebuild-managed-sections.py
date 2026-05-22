#!/usr/bin/env python3
"""Tests for skf-rebuild-managed-sections.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile

import pytest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-rebuild-managed-sections.py"

spec = importlib.util.spec_from_file_location("skf_rms", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


SAMPLE_FILE = """# My Project

Some user content here.

<!-- SKF:BEGIN updated:2026-04-01 -->
Old skill snippets here.
<!-- SKF:END -->

## More user content

This should be preserved.
"""

SAMPLE_FILE_BARE = """# My Project

Some user content here.

<!-- SKF:BEGIN -->
Old skill snippets here.
<!-- SKF:END -->

## More user content

This should be preserved.
"""


class TestCheck:
    """Suite 1: Check existing section."""

    def test_section_found(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_check(fp)
        assert r["has_managed_section"] is True
        assert r["markers_valid"] is True
        Path(fp).unlink()


class TestCheckNoSection:
    """Suite 2: Check file without section."""

    def test_no_section(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# No markers\n\nJust content.\n")
            fp = f.name
        r = mod.cmd_check(fp)
        assert r["has_managed_section"] is False
        assert r["markers_valid"] is True


class TestReadSection:
    """Suite 3: Read section content."""

    def test_read_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_read(fp)
        assert r["has_managed_section"] is True
        assert "Old skill snippets" in r["content"]
        Path(fp).unlink()


class TestReplaceSection:
    """Suite 4: Replace section."""

    def test_replace(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_replace(fp, "New snippet content here.")
        assert r["status"] == "ok"
        updated = Path(fp).read_text(encoding="utf-8")
        assert "New snippet content here." in updated
        assert "Old skill snippets" not in updated
        assert "Some user content here." in updated
        assert "More user content" in updated
        assert "<!-- SKF:BEGIN updated:" in updated
        assert "<!-- SKF:END -->" in updated
        Path(fp).unlink()

    def test_replace_bare_marker(self):
        """Replace also works with bare (legacy) markers."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE_BARE)
            fp = f.name
        r = mod.cmd_replace(fp, "New snippet content here.")
        assert r["status"] == "ok"
        updated = Path(fp).read_text(encoding="utf-8")
        assert "New snippet content here." in updated
        assert "<!-- SKF:BEGIN updated:" in updated
        Path(fp).unlink()


class TestClearSection:
    """Suite 5: Clear section."""

    def test_clear(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_clear(fp)
        assert r["status"] == "ok"
        cleared = Path(fp).read_text(encoding="utf-8")
        assert "<!-- SKF:BEGIN" not in cleared
        assert "Some user content here." in cleared
        assert "More user content" in cleared
        Path(fp).unlink()


class TestInsertSection:
    """Suite 6: Insert into file without section."""

    def test_insert(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# My Project\n\nExisting content.\n")
            fp = f.name
        r = mod.cmd_insert(fp, "Inserted skill snippets.")
        assert r["status"] == "ok"
        inserted = Path(fp).read_text(encoding="utf-8")
        assert "<!-- SKF:BEGIN updated:" in inserted
        assert "Inserted skill snippets." in inserted
        assert "Existing content." in inserted
        Path(fp).unlink()


class TestInsertCollision:
    """Suite 7: Insert fails if section exists."""

    def test_error_on_existing_section(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_insert(fp, "Should fail")
        assert r["status"] == "error"
        assert "already exists" in r["error"]
        Path(fp).unlink()


class TestMalformedMarkers:
    """Suite 8: Malformed markers (begin without end)."""

    def test_markers_invalid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test\n\n<!-- SKF:BEGIN -->\nOrphan begin.\n")
            fp = f.name
        r = mod.cmd_check(fp)
        assert r["markers_valid"] is False
        assert "no matching" in r.get("error_detail", "").lower()
        Path(fp).unlink()


class TestEmptyContentGuard:
    """Suite 9: replace/insert must reject empty content instead of silently wiping the section.

    Exercises main() via subprocess because the guard lives in the CLI layer. The empty-stdin
    path (no --content, non-tty stdin) previously read "" and wiped the managed section.
    """

    @pytest.mark.parametrize("action", ["replace", "insert"])
    def test_missing_content_with_empty_stdin_preserves_file(self, action):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), fp, action],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "non-empty" in proc.stdout
        assert Path(fp).read_text(encoding="utf-8") == SAMPLE_FILE
        Path(fp).unlink()

    @pytest.mark.parametrize("action", ["replace", "insert"])
    def test_whitespace_only_content_preserves_file(self, action):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), fp, action, "--content", "   \n  "],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "non-empty" in proc.stdout
        assert Path(fp).read_text(encoding="utf-8") == SAMPLE_FILE
        Path(fp).unlink()

    def test_real_replace_still_succeeds(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), fp, "replace", "--content", "Fresh body."],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        updated = Path(fp).read_text(encoding="utf-8")
        assert "Fresh body." in updated
        assert "Old skill snippets" not in updated
        Path(fp).unlink()
