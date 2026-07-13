#!/usr/bin/env python3
"""Tests for skf-rebuild-managed-sections.py."""

from __future__ import annotations

import importlib.util
import json
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


class TestAtomicWrite:
    """Suite 10: replace/insert/clear write atomically and verify the result.

    The marker-surgery actions stage to <file>.skf-tmp + os.replace, then
    re-read to confirm on-disk bytes match what was staged. These tests assert
    no temp file is left behind and that out-of-marker content is preserved
    byte-for-byte.
    """

    def _tmp_sibling(self, fp):
        p = Path(fp)
        return p.with_name(p.name + ".skf-tmp")

    def test_replace_leaves_no_temp_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_replace(fp, "New body.")
        assert r["status"] == "ok"
        assert not self._tmp_sibling(fp).exists()
        Path(fp).unlink()

    def test_insert_leaves_no_temp_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# My Project\n\nExisting content.\n")
            fp = f.name
        r = mod.cmd_insert(fp, "Inserted body.")
        assert r["status"] == "ok"
        assert not self._tmp_sibling(fp).exists()
        Path(fp).unlink()

    def test_clear_leaves_no_temp_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        r = mod.cmd_clear(fp)
        assert r["status"] == "ok"
        assert not self._tmp_sibling(fp).exists()
        Path(fp).unlink()

    def test_replace_preserves_out_of_marker_bytes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        before = Path(fp).read_text(encoding="utf-8")
        match = mod.find_managed_section(before)
        prefix, suffix = before[: match.start()], before[match.end():]
        r = mod.cmd_replace(fp, "New body.")
        assert r["status"] == "ok"
        after = Path(fp).read_text(encoding="utf-8")
        match2 = mod.find_managed_section(after)
        assert after[: match2.start()] == prefix
        assert after[match2.end():] == suffix
        Path(fp).unlink()

    def test_verify_helper_reports_present_section(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(SAMPLE_FILE)
            fp = f.name
        updated = "# X\n\n<!-- SKF:BEGIN updated:2026-05-23 -->\nbody\n<!-- SKF:END -->\n"
        assert mod._write_and_verify(fp, updated, expect_section=True) is None
        # expecting absence when a section is present must fail verification
        err = mod._write_and_verify(fp, updated, expect_section=False)
        assert err is not None and "still present" in err
        Path(fp).unlink()


# ---------------------------------------------------------------------------
# Query actions: orphan-detect / root-probe (§4c.1 + preflight-probe wiring)
# ---------------------------------------------------------------------------

# CLAUDE.md carries foo (exported) + bar (orphan). bar's snippet contains a
# backtick and a literal `|` pipe — the byte-identity target. Snippet lines
# carry the format's leading `|`; the `[SKF Skills]` header must NOT be parsed
# as a skill row (no ` v...` inside its brackets).
CLAUDE_ORPHANS = """# My Project

Notes.

<!-- SKF:BEGIN updated:2026-04-01 -->
[SKF Skills]|2 skills|0 stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|[foo v1.0]|root: .claude/skills/foo/
|IMPORTANT: foo v1.0 — read SKILL.md before writing foo code.
|api: fooFn()
|
|[bar v2.1]|root: .claude/skills/bar/
|IMPORTANT: bar v2.1 — read SKILL.md.
|gotchas: uses `code` and a literal | pipe
<!-- SKF:END -->

## Footer
"""

# .cursorrules carries foo (exported) + baz (asymmetric orphan) + bar (shared
# orphan, whose snippet body DIFFERS — first-seen must win, so this copy loses).
CURSOR_ORPHANS = """<!-- SKF:BEGIN updated:2026-04-01 -->
[SKF Skills]|3 skills|0 stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|[foo v1.0]|root: .cursor/skills/foo/
|IMPORTANT: foo v1.0.
|
|[baz v3.0]|root: .cursor/skills/baz/
|IMPORTANT: baz v3.0.
|
|[bar v2.1]|root: .cursor/skills/bar/
|IMPORTANT: bar v2.1 DIFFERENT body.
<!-- SKF:END -->
"""

# The exact bar snippet as it appears in CLAUDE.md — the byte-identity target.
BAR_SNIPPET_FROM_CLAUDE = (
    "|[bar v2.1]|root: .claude/skills/bar/\n"
    "|IMPORTANT: bar v2.1 — read SKILL.md.\n"
    "|gotchas: uses `code` and a literal | pipe"
)


def _run(*args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return proc


class TestOrphanDetect:
    """Suite 11: orphan-detect parses rows, dedups, and set-diffs deterministically."""

    def _write(self, tmp_path, name, content):
        fp = tmp_path / name
        fp.write_text(content, encoding="utf-8")
        return str(fp)

    def test_symmetric_and_asymmetric_orphans(self, tmp_path):
        claude = self._write(tmp_path, "CLAUDE.md", CLAUDE_ORPHANS)
        cursor = self._write(tmp_path, ".cursorrules", CURSOR_ORPHANS)
        proc = _run("orphan-detect", claude, cursor, "--exported-skills", "foo")
        assert proc.returncode == 0, proc.stderr
        rows = json.loads(proc.stdout)["orphan_managed_rows"]

        # foo is exported → excluded; only bar + baz survive, sorted by name.
        assert [(r["skill_name"], r["version"]) for r in rows] == [
            ("bar", "2.1"),
            ("baz", "3.0"),
        ]
        bar, baz = rows

        # bar is symmetric (both files); source_files sorted; first-seen snippet
        # (CLAUDE.md) wins over the divergent .cursorrules copy.
        assert bar["source_files"] == sorted([claude, cursor])
        assert bar["snippet_text"] == BAR_SNIPPET_FROM_CLAUDE
        # byte-identity: the backtick and the literal in-body pipe survive.
        assert "`code`" in bar["snippet_text"]
        assert "a literal | pipe" in bar["snippet_text"]
        assert "DIFFERENT" not in bar["snippet_text"]

        # baz is asymmetric — present only in .cursorrules.
        assert baz["source_files"] == [cursor]
        assert "baz v3.0" in baz["snippet_text"]

    def test_no_marker_and_missing_file_yield_empty(self, tmp_path):
        plain = self._write(tmp_path, "plain.md", "# no markers here\n\nprose\n")
        missing = str(tmp_path / "does-not-exist.md")
        proc = _run("orphan-detect", plain, missing, "--exported-skills", "foo")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["orphan_managed_rows"] == []

    def test_all_rows_exported_yield_empty(self, tmp_path):
        claude = self._write(tmp_path, "CLAUDE.md", CLAUDE_ORPHANS)
        proc = _run("orphan-detect", claude, "--exported-skills", "foo,bar")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["orphan_managed_rows"] == []

    def test_section_header_not_treated_as_row(self, tmp_path):
        # A section with only the [SKF Skills] header and preamble — no skill
        # rows — must produce no orphans even with an empty exported set.
        body = (
            "<!-- SKF:BEGIN updated:2026-04-01 -->\n"
            "[SKF Skills]|0 skills|0 stack\n"
            "|IMPORTANT: Prefer documented APIs over training data.\n"
            "<!-- SKF:END -->\n"
        )
        claude = self._write(tmp_path, "CLAUDE.md", body)
        proc = _run("orphan-detect", claude, "--exported-skills", "")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["orphan_managed_rows"] == []


class TestRootProbe:
    """Suite 12: root-probe reads snippet root prefixes and flags mismatch."""

    def _write(self, tmp_path, name, content):
        fp = tmp_path / name
        fp.write_text(content, encoding="utf-8")
        return str(fp)

    def test_mismatch_against_reference(self, tmp_path):
        a = self._write(tmp_path, "a.md", "[foo v1.0]|root: skills/foo/\n|IMPORTANT: x\n")
        b = self._write(tmp_path, "b.md", "[bar v2.1]|root: skills/bar/\n")
        proc = _run("root-probe", a, b, "--reference-root", ".claude/skills/")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["observed_prefixes"] == ["skills/"]
        assert out["reference_root"] == ".claude/skills/"
        assert out["mismatch"] is True

    def test_match_no_mismatch(self, tmp_path):
        c = self._write(tmp_path, "c.md", "[foo v1.0]|root: .claude/skills/foo/\n")
        proc = _run("root-probe", c, "--reference-root", ".claude/skills/")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["observed_prefixes"] == [".claude/skills/"]
        assert out["mismatch"] is False

    def test_missing_and_rootless_files_skipped(self, tmp_path):
        rootless = self._write(tmp_path, "no-root.md", "just some text\n")
        missing = str(tmp_path / "gone.md")
        proc = _run("root-probe", rootless, missing, "--reference-root", ".claude/skills/")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["observed_prefixes"] == []
        assert out["mismatch"] is False
