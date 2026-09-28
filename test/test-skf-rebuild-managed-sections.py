#!/usr/bin/env python3
"""Tests for skf-rebuild-managed-sections.py."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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


# ---------------------------------------------------------------------------
# replace/insert take the body only: they write both markers themselves
# ---------------------------------------------------------------------------

MANAGED_FORMAT = REPO / "src" / "skf-export-skill" / "assets" / "managed-section-format.md"
SNIPPET_FORMAT = REPO / "src" / "skf-export-skill" / "assets" / "snippet-format.md"


def _fenced_after(path: Path, heading: str) -> str:
    """The first fenced block after `heading` in `path`, without its fences."""
    text = path.read_text(encoding="utf-8")
    assert text.count(heading) == 1, f"{heading!r} must occur once in {path.name}"
    m = re.search(r"^```[a-z]*\n(.*?)^```", text[text.index(heading):], re.S | re.M)
    assert m, f"no fenced block after {heading!r}"
    return m.group(1)


def _render_snippet(name: str, gotchas: str) -> str:
    snippet = _fenced_after(SNIPPET_FORMAT, "## Single Skill Snippet Template")
    snippet = snippet.replace("{skill_root}", ".claude/skills/").replace("{skill-name}", name)
    snippet = snippet.replace("{version}", "1.4.0")
    snippet = re.sub(r"\|gotchas: \{[^{}\n]*\}", lambda _m: "|gotchas: " + gotchas, snippet)
    return re.sub(r"\{[^{}\n]*\}", "details", snippet).rstrip("\n")


def _real_managed_section() -> str:
    """A managed section as export-skill writes it: SKF's marker format with two
    snippets rendered from its snippet template. The gotchas carry the shell
    metacharacters real snippets do (backticks, `$`, a literal `|`)."""
    section = _fenced_after(MANAGED_FORMAT, "## Marker Format").rstrip("\n")
    section = section.replace("{YYYY-MM-DD}", "2026-04-25").replace("{n}", "2").replace("{m}", "0")
    section = section.replace("{skill-snippet-1}", _render_snippet(
        "cognee", 'all entries require `"use client"`; read $COGNEE_HOME'))
    return section.replace("{skill-snippet-2}", _render_snippet("zod", "use `z.infer<typeof S>` | not `any`"))


REAL_SECTION = _real_managed_section()
BEFORE = "# My Project\n\nUser notes stay.\n\n"
AFTER = "\n\n## Team rules\n\nKeep me byte-for-byte.\n"
REAL_CLAUDE_MD = BEFORE + REAL_SECTION + AFTER
# What rename §7 / drop §3 now pass: the section without its two marker lines.
REAL_BODY = "\n".join(REAL_SECTION.split("\n")[1:-1])


def _run_content(path, action, content, via="flag"):
    args = [sys.executable, str(SCRIPT), str(path), action]
    if via == "flag":
        return subprocess.run(args + ["--content", content], stdin=subprocess.DEVNULL,
                              capture_output=True, encoding="utf-8")
    return subprocess.run(args, input=content, capture_output=True, encoding="utf-8")


class TestBodyOnlyContent:
    """Suite 13: a body carrying its own marker would nest a second pair; refuse it."""

    def test_fixture_is_a_real_section(self):
        assert REAL_SECTION.startswith("<!-- SKF:BEGIN updated:2026-04-25 -->\n[SKF Skills]|2 skills|0 stack\n")
        assert REAL_SECTION.endswith("\n<!-- SKF:END -->")
        rows = mod.parse_managed_rows(REAL_BODY)
        assert [(r["skill_name"], r["version"]) for r in rows] == [("cognee", "1.4.0"), ("zod", "1.4.0")]

    @pytest.mark.parametrize("via", ["flag", "stdin"])
    def test_replace_refuses_the_whole_section(self, tmp_path, via):
        """The call rename §7 and drop §3 made before: the section with its markers."""
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(REAL_CLAUDE_MD.encode("utf-8"))
        fresh = REAL_SECTION.replace("updated:2026-04-25", "updated:2026-09-28")
        proc = _run_content(f, "replace", fresh, via)
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and "SKF marker" in out["error"] and "body" in out["error"]
        assert f.read_bytes() == REAL_CLAUDE_MD.encode("utf-8")

    def test_insert_refuses_the_whole_section(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_bytes(b"# Agents\n")
        proc = _run_content(f, "insert", REAL_SECTION)
        assert proc.returncode == 1 and "SKF marker" in json.loads(proc.stdout)["error"]
        assert f.read_bytes() == b"# Agents\n"

    @pytest.mark.parametrize("content", [
        "[SKF Skills]|0 skills|0 stack\n<!-- SKF:END -->",
        "<!-- SKF:BEGIN -->\n[SKF Skills]|0 skills|0 stack",
        "[SKF Skills]|0 skills|0 stack\n<!--SKF:END-->",
        "  <!--  SKF:BEGIN updated:2026-01-01 -->\n|row",
    ])
    @pytest.mark.parametrize("action", ["replace", "insert"])
    def test_any_marker_in_the_body_is_refused(self, tmp_path, action, content):
        f = tmp_path / "CLAUDE.md"
        original = REAL_CLAUDE_MD if action == "replace" else "# No section yet\n"
        f.write_bytes(original.encode("utf-8"))
        result = getattr(mod, f"cmd_{action}")(str(f), content)
        assert result["status"] == "error" and "SKF marker" in result["error"]
        assert f.read_bytes() == original.encode("utf-8")

    def test_body_replace_keeps_one_marker_pair(self, tmp_path):
        """The call rename §7 and drop §3 make now."""
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(REAL_CLAUDE_MD.replace("|IMPORTANT: zod", "|IMPORTANT: old-zod").encode("utf-8"))
        proc = _run_content(f, "replace", REAL_BODY)
        assert proc.returncode == 0, proc.stdout
        after = f.read_text(encoding="utf-8")
        assert after.count("<!-- SKF:BEGIN") == 1 and after.count("<!-- SKF:END") == 1
        match = mod.find_managed_section(after)
        assert after[: match.start()] == BEFORE and after[match.end():] == AFTER
        assert match.group(2) == "\n" + REAL_BODY + "\n"
        assert re.fullmatch(r"<!-- SKF:BEGIN updated:\d{4}-\d{2}-\d{2} -->", match.group(1))

    def test_body_insert_keeps_one_marker_pair(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_bytes(b"# Agents\n")
        proc = _run_content(f, "insert", REAL_BODY, via="stdin")
        assert proc.returncode == 0, proc.stdout
        after = f.read_text(encoding="utf-8")
        assert after.count("<!-- SKF:BEGIN") == 1 and after.count("<!-- SKF:END") == 1
        assert mod.find_managed_section(after).group(2) == "\n" + REAL_BODY + "\n"

    @pytest.mark.parametrize("action", ["replace", "insert"])
    def test_stdin_is_utf8_under_a_cp1252_console(self, tmp_path, action):
        """A Windows pipe or redirect decodes stdin with cp1252; the IMPORTANT line's em dash must survive.

        PYTHONIOENCODING=cp1252 simulates that console on any platform. The body
        goes in as raw UTF-8 bytes, as a staging file redirected to stdin does.
        """
        assert "\u2014" in REAL_BODY
        f = tmp_path / "CLAUDE.md"
        original = REAL_CLAUDE_MD if action == "replace" else "# No section yet\n"
        f.write_bytes(original.encode("utf-8"))
        proc = subprocess.run([sys.executable, str(SCRIPT), str(f), action], input=REAL_BODY.encode("utf-8"),
                              capture_output=True, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
        assert mod.find_managed_section(f.read_text(encoding="utf-8")).group(2) == "\n" + REAL_BODY + "\n"

    def test_stdin_that_is_not_utf8_is_refused(self, tmp_path):
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(REAL_CLAUDE_MD.encode("utf-8"))
        proc = subprocess.run([sys.executable, str(SCRIPT), str(f), "replace"],
                              input=REAL_BODY.encode("cp1252", "replace"), capture_output=True)
        assert proc.returncode == 1
        assert "not UTF-8" in json.loads(proc.stdout)["error"]
        assert f.read_bytes() == REAL_CLAUDE_MD.encode("utf-8")

    def test_a_prose_mention_of_the_marker_names_is_not_a_marker(self, tmp_path):
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(REAL_CLAUDE_MD.encode("utf-8"))
        body = REAL_BODY + "\n|gotchas: SKF rewrites only between its SKF:BEGIN and SKF:END markers"
        assert mod.cmd_replace(str(f), body)["status"] == "ok"
        assert f.read_text(encoding="utf-8").count("<!-- SKF:BEGIN") == 1


# ---------------------------------------------------------------------------
# Every replace/insert caller in src/ passes the body only
# ---------------------------------------------------------------------------

RENAME_EXECUTE = "src/skf-rename-skill/references/execute.md"
DROP_EXECUTE = "src/skf-drop-skill/references/execute.md"
EXPORT_UPDATE = "src/skf-export-skill/references/update-context.md"
REBUILD_STEPS = [
    (RENAME_EXECUTE, "### 7. Rebuild Context Files", "### 8. ", "7"),
    (DROP_EXECUTE, "### 3. Rebuild Context Files", "### 4. ", "8"),
]
BODY_CALL_RE = re.compile(r"\{rebuildManagedSectionsHelper\}\s+\S+\s+(replace|insert)\b")
MARKER_LINE_RE = re.compile(r"^\s*<!--\s*SKF:(?:BEGIN|END)")


def _md(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _part(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    assert end in body, f"marker {end!r} missing after {start!r}"
    return body[:body.index(end)]


def _fenced_blocks(text: str) -> list[list[str]]:
    blocks, current = [], None
    for line in text.split("\n"):
        if re.match(r"^\s*```", line):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line)
    return blocks


class TestCallersPassTheBody:
    """Suite 14: the step files build only the body for replace and insert."""

    def test_callers_are_exactly_these(self):
        sites = {}
        for path in sorted((REPO / "src").rglob("*.md")):
            for line in path.read_text(encoding="utf-8").split("\n"):
                m = BODY_CALL_RE.search(line)
                if m:
                    rel = path.relative_to(REPO).as_posix()
                    sites.setdefault(rel, []).append(m.group(1))
        assert sites == {RENAME_EXECUTE: ["replace"], DROP_EXECUTE: ["replace"],
                         EXPORT_UPDATE: ["insert", "replace"]}

    @pytest.mark.parametrize("rel, start, end, item", REBUILD_STEPS)
    def test_rebuild_builds_the_body_and_binds_the_error(self, rel, start, end, item):
        section = _part(_md(rel), start, end)
        blocks = _fenced_blocks(section)
        assert blocks, "the section shows the body it builds"
        for block in blocks:
            assert not any(MARKER_LINE_RE.match(line) for line in block), block
        assert any(line.strip() == "[SKF Skills]|{n} skills|{m} stack" for block in blocks for line in block)
        assert "{new_managed_section_text}" not in section
        assert f"without its two marker lines. The helper in item {item} writes" in section
        assert "It refuses a body that holds a marker of its own" in section
        assert "bind `{context_error}` ← `error`" in section
        assert "record `{context_error}` against that context file" in section
        assert "clear `stderr` reason" not in section, "the helper reports on stdout as JSON"

    @pytest.mark.parametrize("rel, start, end, item", REBUILD_STEPS)
    def test_rebuild_stages_the_body_for_stdin(self, rel, start, end, item):
        """As export-skill §9 does: a staging file and a redirect, never the body inline."""
        section = _part(_md(rel), start, end)
        calls = [line.strip() for block in _fenced_blocks(section) for line in block
                 if "{rebuildManagedSectionsHelper}" in line]
        assert calls == ['python3 {rebuildManagedSectionsHelper} "{context_file}" replace < "{context_file}.skf-content"']
        assert "Write `{managed_section_inner}` to `{context_file}.skf-content` with your file-write tool, " \
               "with **no trailing newline**" in section
        assert "Never pass the body inline as `--content \"…\"` or through `echo`" in section
        assert "Delete `{context_file}.skf-content` once the helper returns, whatever its exit code." in section

    @pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
    @pytest.mark.parametrize("rel, start, end, item", REBUILD_STEPS)
    def test_the_documented_call_keeps_the_body_through_the_shell(self, tmp_path, rel, start, end, item):
        """Run the step's command line through bash as an agent would: backticks and `$` stay text."""
        section = _part(_md(rel), start, end)
        [call] = [line.strip() for block in _fenced_blocks(section) for line in block
                  if "{rebuildManagedSectionsHelper}" in line]
        context_file = tmp_path / "CLAUDE.md"
        context_file.write_bytes(REAL_CLAUDE_MD.encode("utf-8"))
        staging = Path(str(context_file) + ".skf-content")
        if "{context_file}.skf-content" in call:
            staging.write_bytes(REAL_BODY.encode("utf-8"))  # the file-write tool, no trailing newline
        command = re.sub(r"^python3 ", shlex.quote(sys.executable) + " ", call)
        command = (command.replace("{rebuildManagedSectionsHelper}", shlex.quote(str(SCRIPT)))
                   .replace("{context_file}", str(context_file))
                   .replace("{managed_section_inner}", REAL_BODY))
        proc = subprocess.run(["bash", "-c", command], capture_output=True, encoding="utf-8",
                              cwd=tmp_path, env={**os.environ, "COGNEE_HOME": "/expanded"})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        body = mod.find_managed_section(context_file.read_text(encoding="utf-8")).group(2)
        assert body == "\n" + REAL_BODY + "\n", proc.stderr
        assert proc.stderr == ""

    def test_export_stages_the_body_for_insert_and_replace(self):
        text = _md(EXPORT_UPDATE)
        assert "For **Cases 2 and 3**, write `{managed_section_inner}`" in text
        assert "double-wraps" not in text
        assert "refuses (exit 1) marker-bearing text" in _part(text, "**Case 2 (Append", "**Case 3 (Regenerate")
        assert "refuses marker-bearing text" in _part(text, "**Case 3 (Regenerate", "**Case 4 (malformed")
