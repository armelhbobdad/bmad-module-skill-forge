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


REAL_GOTCHAS = {
    "cognee": 'all entries require `"use client"`; read $COGNEE_HOME',
    "zod": "use `z.infer<typeof S>` | not `any`",
}


def _real_managed_section() -> str:
    """A managed section as export-skill writes it: SKF's marker format with two
    snippets rendered from its snippet template. The gotchas carry the shell
    metacharacters real snippets do (backticks, `$`, a literal `|`)."""
    section = _fenced_after(MANAGED_FORMAT, "## Marker Format").rstrip("\n")
    section = section.replace("{YYYY-MM-DD}", "2026-04-25").replace("{n}", "2").replace("{m}", "0")
    section = section.replace("{skill-snippet-1}", _render_snippet("cognee", REAL_GOTCHAS["cognee"]))
    return section.replace("{skill-snippet-2}", _render_snippet("zod", REAL_GOTCHAS["zod"]))


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


# ---------------------------------------------------------------------------
# A BEGIN marker no END closes: check reports it, insert/replace/clear refuse it
# ---------------------------------------------------------------------------

# The reproduction from issue #591: a BEGIN whose END is gone, then user text.
DANGLING = "# Project\n<!-- SKF:BEGIN updated:2026-01-01 -->\nold row\nUSER NOTES THAT MATTER\nmore user text\n"
EMPTY_BODY = "[SKF Skills]|0 skills|0 stack"
# Each file and the line of the BEGIN marker that no END closes.
UNCLOSED = {
    "dangling": (DANGLING, 2),
    "bare-legacy-begin": ("# P\n\n<!-- SKF:BEGIN -->\nnotes\n", 3),
    # What insert used to write into the reproduction: a second section after the dangling marker.
    "second-section-after-it": (DANGLING + "<!-- SKF:BEGIN updated:2026-02-01 -->\nnew\n<!-- SKF:END -->\n", 2),
    "end-before-begin": ("<!-- SKF:END -->\nnotes\n<!-- SKF:BEGIN updated:2026-01-01 -->\nmore\n", 3),
    "text-between-nested-begins": (
        "<!-- SKF:BEGIN updated:2026-01-01 -->\nnotes\n<!-- SKF:BEGIN updated:2026-01-02 -->\nrow\n<!-- SKF:END -->\n<!-- SKF:END -->\n",
        1,
    ),
    "begin-not-closed-on-its-line": ("# P\n<!-- SKF:BEGIN updated:2026-01-01\nnotes\n<!-- SKF:END -->\n", 2),
}
# The BEGIN and END marker counts of the sections released versions left: drop or rename
# wrapped a second pair inside (2, 2), each later drop or rename left one more END (2, 3),
# and an export replace kept the outer END (1, 2).
LEFT_BY_OLD_REBUILDS = [(2, 2), (2, 3), (1, 2), (3, 3)]


def _double_wrapped(begins: int, ends: int) -> str:
    """A context file whose section has `begins` BEGIN markers in a row and `ends` END markers in a row."""
    opening = "".join(f"<!-- SKF:BEGIN updated:2026-06-0{i} -->\n" for i in range(1, begins + 1))
    closing = "<!-- SKF:END -->\n" * ends
    return f"# P\n\nnotes\n\n{opening}[SKF Skills]|1 skills|0 stack\n|\n|[foo v1.0]|root: x/foo/\n{closing}\ntail\n"


class TestUnclosedBegin:
    """Suite 15: a BEGIN marker with no END is the Case 4 halt, enforced in code."""

    @pytest.mark.parametrize("name", sorted(UNCLOSED))
    def test_check_reports_it_malformed(self, tmp_path, name):
        content, line = UNCLOSED[name]
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(content.encode("utf-8"))
        proc = _run(str(f), "check")
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and out["case"] == "malformed" and out["begin_line"] == line
        assert out["exists"] is True and out["has_managed_section"] is False and out["markers_valid"] is False
        assert f"<!-- SKF:BEGIN on line {line} " in out["error"] and out["error_detail"] in out["error"]

    @pytest.mark.parametrize("name", sorted(UNCLOSED))
    @pytest.mark.parametrize("action", ["insert", "replace", "clear"])
    def test_the_writers_refuse_it_and_leave_the_file(self, tmp_path, name, action):
        content, line = UNCLOSED[name]
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(content.encode("utf-8"))
        proc = _run(str(f), action, *(["--content", EMPTY_BODY] if action != "clear" else []))
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["case"] == "malformed" and out["begin_line"] == line
        assert out["error"].endswith("then re-run. The file was not changed.")
        assert f.read_bytes() == content.encode("utf-8")
        assert not (tmp_path / "CLAUDE.md.skf-tmp").exists()

    def test_the_issue_reproduction_keeps_the_user_lines(self, tmp_path):
        """check said markers_valid false, insert then appended a section and replace deleted the notes."""
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(DANGLING.encode("utf-8"))
        assert mod.cmd_check(str(f))["case"] == "malformed"
        assert mod.cmd_insert(str(f), EMPTY_BODY)["status"] == "error"
        assert mod.cmd_replace(str(f), EMPTY_BODY)["status"] == "error"
        assert f.read_bytes() == DANGLING.encode("utf-8")

    def test_text_between_two_begins_names_both_lines(self):
        content, _ = UNCLOSED["text-between-nested-begins"]
        assert mod.find_unclosed_begin(content) == (
            1,
            "<!-- SKF:BEGIN on line 1 has no matching <!-- SKF:END --> before the next <!-- SKF:BEGIN on line 3",
        )

    @pytest.mark.parametrize("begins, ends", LEFT_BY_OLD_REBUILDS)
    def test_a_double_wrapped_section_is_rebuilt(self, tmp_path, begins, ends):
        """drop and rename once wrote a second pair inside the section: no text sits between its BEGIN markers."""
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(_double_wrapped(begins, ends).encode("utf-8"))
        assert mod.cmd_check(str(f))["case"] == "regenerate"
        assert mod.cmd_replace(str(f), EMPTY_BODY)["status"] == "ok"
        after = f.read_text(encoding="utf-8")
        assert after.startswith("# P\n\nnotes\n\n<!-- SKF:BEGIN updated:")
        assert after.endswith(f"\n{EMPTY_BODY}\n<!-- SKF:END -->\n\ntail\n")
        assert after.count("<!-- SKF:BEGIN") == 1 and after.count("<!-- SKF:END") == 1
        assert mod.find_unclosed_begin(after) is None

    @pytest.mark.parametrize("begins, ends", LEFT_BY_OLD_REBUILDS)
    def test_a_double_wrapped_section_is_cleared_whole(self, tmp_path, begins, ends):
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(_double_wrapped(begins, ends).encode("utf-8"))
        assert mod.cmd_clear(str(f))["status"] == "ok"
        assert f.read_bytes() == b"# P\n\nnotes\n\ntail\n"

    @pytest.mark.parametrize("action, ends_left", [("replace", 2), ("clear", 1)])
    def test_an_end_after_the_users_text_stays(self, tmp_path, action, ends_left):
        """Only an END with nothing but blank space before it joins the section."""
        content = _double_wrapped(2, 2).replace("-->\n<!-- SKF:END -->\n\ntail", "-->\nmy note\n<!-- SKF:END -->\n\ntail")
        assert "my note" in content
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(content.encode("utf-8"))
        result = mod.cmd_replace(str(f), EMPTY_BODY) if action == "replace" else mod.cmd_clear(str(f))
        assert result["status"] == "ok"
        after = f.read_text(encoding="utf-8")
        assert after.endswith("\nmy note\n<!-- SKF:END -->\n\ntail\n") and after.count("<!-- SKF:END") == ends_left

    @pytest.mark.parametrize(
        "content, case, valid",
        [
            ("# P\n\nnotes\n", "append", True),
            ("# P\n<!-- SKF:END -->\nnotes\n", "append", False),
            ("<!-- SKF:END -->\n" + SAMPLE_FILE, "regenerate", True),
            (SAMPLE_FILE + "<!-- SKF:END -->\n", "regenerate", True),
            (SAMPLE_FILE + SAMPLE_FILE, "regenerate", True),
            (SAMPLE_FILE_BARE, "regenerate", True),
        ],
    )
    def test_closed_markers_and_a_stray_end_are_not_malformed(self, tmp_path, content, case, valid):
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(content.encode("utf-8"))
        r = mod.cmd_check(str(f))
        assert (r["status"], r["exists"], r["case"], r["markers_valid"]) == ("ok", True, case, valid)
        assert r["has_managed_section"] is (case == "regenerate")

    def test_check_on_a_missing_file_is_the_create_case(self, tmp_path):
        proc = _run(str(tmp_path / "AGENTS.md"), "check")
        assert proc.returncode == 0
        assert json.loads(proc.stdout) == {
            "status": "ok",
            "exists": False,
            "case": "create",
            "has_managed_section": False,
            "markers_valid": True,
        }

    def test_insert_after_a_stray_end_keeps_the_user_text(self, tmp_path):
        content = "# P\n<!-- SKF:END -->\nnotes\n"
        f = tmp_path / "CLAUDE.md"
        f.write_bytes(content.encode("utf-8"))
        assert mod.cmd_insert(str(f), EMPTY_BODY)["status"] == "ok"
        after = f.read_text(encoding="utf-8")
        assert after.startswith(content) and mod.find_managed_section(after).group(2) == "\n" + EMPTY_BODY + "\n"
        assert mod.cmd_check(str(f))["case"] == "regenerate"


class TestOrphanDetectSkipsMalformedFiles:
    """Suite 16: a file whose markers are malformed is not read for rows."""

    def test_its_rows_are_not_reported(self, tmp_path):
        good = tmp_path / "CLAUDE.md"
        good.write_bytes(CLAUDE_ORPHANS.encode("utf-8"))
        bad = tmp_path / ".cursorrules"
        bad.write_bytes(b"<!-- SKF:BEGIN updated:2026-01-01 -->\n|[ghost v1.0]|root: x/ghost/\nUSER TEXT\n")
        proc = _run("orphan-detect", str(good), str(bad), "--exported-skills", "foo")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert [r["skill_name"] for r in out["orphan_managed_rows"]] == ["bar"]
        assert out["malformed_files"] == [str(bad)]


# ---------------------------------------------------------------------------
# One IDE mapping: src/shared/data/ide-context-files.json and resolve-targets
# ---------------------------------------------------------------------------

IDE_DATA = REPO / "src" / "shared" / "data" / "ide-context-files.json"
PLATFORM_CODES = REPO / "tools" / "cli" / "lib" / "platform-codes.yaml"
# A row of the mapping tables in managed-section-format.md: IDE, context file, skill root.
TABLE_ROW_RE = re.compile(r"^\|\s*(?:`([^`]+)`|(_\(any unknown value\)_))\s*\|\s*([^|\s]+)\s*\|\s*`([^`]+)`\s*\|\s*$")


def _ide_data() -> dict:
    return json.loads(IDE_DATA.read_text(encoding="utf-8"))


class TestIdeMappingData:
    """Suite 17: the mapping file, pinned to the table readers see and to the installer's folders."""

    def test_the_helper_reads_the_shared_file(self):
        assert mod.IDE_DATA_FILE == IDE_DATA.resolve()
        assert mod.load_ide_mapping() == (_ide_data()["ides"], _ide_data()["unknown_ide"])

    def test_the_managed_section_format_table_is_the_same_mapping(self):
        rows, unknown_rows = {}, []
        for line in MANAGED_FORMAT.read_text(encoding="utf-8").split("\n"):
            m = TABLE_ROW_RE.match(line)
            if not m:
                continue
            entry = {"context_file": m.group(3), "skill_root": m.group(4)}
            if m.group(2):
                unknown_rows.append(entry)
            else:
                assert m.group(1) not in rows, f"{m.group(1)} is listed twice"
                rows[m.group(1)] = entry
        assert rows == _ide_data()["ides"]
        assert unknown_rows == [_ide_data()["unknown_ide"]]

    def test_each_skill_root_is_the_installer_target_dir(self):
        yaml = pytest.importorskip("yaml")
        platforms = yaml.safe_load(PLATFORM_CODES.read_text(encoding="utf-8"))["platforms"]
        data = _ide_data()
        assert {ide: e["skill_root"] for ide, e in data["ides"].items() if ide != "other"} == {
            code: p["installer"]["target_dir"] + "/" for code, p in platforms.items()
        }
        assert data["ides"]["other"] == data["unknown_ide"]

    def test_every_entry_names_a_known_context_file_and_a_relative_folder(self):
        data = _ide_data()
        for entry in [*data["ides"].values(), data["unknown_ide"]]:
            assert set(entry) == {"context_file", "skill_root"}
            assert entry["context_file"] in ("CLAUDE.md", ".cursorrules", "AGENTS.md")
            assert entry["skill_root"].endswith("/") and not entry["skill_root"].startswith("/")


class TestResolveTargets:
    """Suite 18: resolve-targets maps config.yaml's IDEs to one target per context file."""

    def _resolve(self, ides, context_file=None):
        result = mod.cmd_resolve_targets(ides, context_file)
        assert result["status"] == "ok", result
        return result

    def test_each_ide_gets_its_context_file_and_skill_root(self):
        r = self._resolve("claude-code,cursor")
        assert r["targets"] == [
            {"context_file": "CLAUDE.md", "skill_root": ".claude/skills/", "ides": ["claude-code"]},
            {"context_file": ".cursorrules", "skill_root": ".cursor/skills/", "ides": ["cursor"]},
        ]
        assert r["ide_map"] == {"claude-code": "CLAUDE.md", "cursor": ".cursorrules"}
        assert r["other_context_files"] == ["AGENTS.md"]
        assert (r["unknown_ides"], r["warnings"], r["notes"]) == ([], [], [])

    def test_ides_sharing_a_file_take_the_first_ides_skill_root(self):
        r = self._resolve("windsurf, github-copilot ,windsurf")
        assert r["targets"] == [
            {"context_file": "AGENTS.md", "skill_root": ".windsurf/skills/", "ides": ["windsurf", "github-copilot"]}
        ]
        assert r["notes"] == [
            "Multiple IDEs target AGENTS.md: using windsurf's skill root (`.windsurf/skills/`). "
            "Each IDE's skills are installed to its own directory."
        ]

    def test_an_unknown_ide_resolves_to_agents_md_with_a_warning(self):
        r = self._resolve("zed")
        assert r["targets"] == [{"context_file": "AGENTS.md", "skill_root": ".agents/skills/", "ides": ["zed"]}]
        assert r["unknown_ides"] == ["zed"] and r["ide_map"] == {"zed": "AGENTS.md"}
        assert r["warnings"] == ["Unknown IDE 'zed' in config.yaml: defaulting to AGENTS.md with `.agents/skills/`"]

    @pytest.mark.parametrize("ides", ["", " , ", None])
    def test_no_ide_resolves_to_agents_md(self, ides):
        r = self._resolve(ides)
        assert r["targets"] == [{"context_file": "AGENTS.md", "skill_root": ".agents/skills/", "ides": []}]
        assert r["notes"] == ["No IDEs configured in config.yaml: defaulting to AGENTS.md with `.agents/skills/`."]
        assert r["other_context_files"] == ["CLAUDE.md", ".cursorrules"]

    def test_ides_written_is_the_union_of_the_written_targets_ides(self):
        r = self._resolve("claude-code,github-copilot,zed,cursor")
        written = {"CLAUDE.md", "AGENTS.md"}  # .cursorrules failed to write
        ides_written = sorted(ide for t in r["targets"] if t["context_file"] in written for ide in t["ides"])
        assert ides_written == ["claude-code", "github-copilot", "zed"]

    @pytest.mark.parametrize(
        "ides, context_file, skill_root, target_ides, others",
        [
            ("cursor", "CLAUDE.md", ".claude/skills/", [], ["cursor"]),
            ("claude-code,kiro,codex", "AGENTS.md", ".kiro/skills/", ["kiro", "codex"], ["claude-code"]),
            ("", "AGENTS.md", ".agents/skills/", [], []),
            ("", ".cursorrules", ".cursor/skills/", [], []),
        ],
    )
    def test_context_file_keeps_that_one_file(self, ides, context_file, skill_root, target_ides, others):
        r = self._resolve(ides, context_file)
        assert r["targets"] == [{"context_file": context_file, "skill_root": skill_root, "ides": target_ides}]
        assert r["notes"] == (
            [
                f"Exporting to {context_file} only. config.yaml also lists: {', '.join(others)}. "
                "Run without `--context-file` to export to all configured IDEs."
            ]
            if others
            else []
        )

    def test_the_command_line(self):
        proc = _run("resolve-targets", "--ides", "claude-code")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["targets"][0]["context_file"] == "CLAUDE.md"
        proc = _run("resolve-targets", "--ides", "claude-code", "--context-file", "GEMINI.md")
        assert proc.returncode == 1
        assert "expected one of CLAUDE.md, .cursorrules, AGENTS.md" in json.loads(proc.stdout)["error"]

    def test_a_broken_mapping_file_is_an_error(self, tmp_path, monkeypatch):
        broken = tmp_path / "ide-context-files.json"
        broken.write_text('{"ides": {"x": {"context_file": "X.md"}}}', encoding="utf-8")
        monkeypatch.setattr(mod, "IDE_DATA_FILE", broken)
        result = mod.cmd_resolve_targets("x")
        assert result["status"] == "error" and "ide-context-files.json" in result["error"]


# ---------------------------------------------------------------------------
# assemble: the body export, drop and rename write, built by the helper
# ---------------------------------------------------------------------------


def _put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _snippet(name: str, version: str, root: str = ".claude/skills/", *lines: str) -> str:
    """A context-snippet.md in the template's shape: header line with root, then `|key:` lines."""
    body = lines or (f"|IMPORTANT: {name} v{version}: read SKILL.md before writing {name} code.",)
    return "\n".join([f"[{name} v{version}]|root: {root}{name}/", *body]) + "\n"


def _rows(body: str) -> list[tuple[str, str]]:
    return [(r["skill_name"], r["version"]) for r in mod.parse_managed_rows(body)]


class Forge:
    """A skills folder with its export manifest and packages, and context files beside it."""

    def __init__(self, root: Path):
        self.root = root
        self.skills = root / "skills"
        self.skills.mkdir()
        self.exports: dict = {}

    def export(self, name, version, status="active", **kw):
        """A manifest entry whose active_version is `version`, and its package on disk."""
        self.exports[name] = {
            "active_version": version,
            "versions": {version: {"ides": [], "last_exported": "2026-01-01", "status": status}},
        }
        self.save()
        return self.package(name, version, **kw)

    def package(self, name, version, *, skill_type="single", snippet=None, layout="versioned"):
        folder = self.skills / name / version / name if layout == "versioned" else self.skills / name
        _put(folder / "context-snippet.md", _snippet(name, version) if snippet is None else snippet)
        if skill_type is not None:
            _put(folder / "metadata.json", json.dumps({"name": name, "version": version, "skill_type": skill_type}))
        return folder

    def save(self):
        _put(self.skills / ".export-manifest.json", json.dumps({"schema_version": "2", "exports": self.exports}))

    def context(self, name, *rows):
        """A context file whose managed section holds `rows`, each a row's text."""
        body = "\n".join(["[SKF Skills]|0 skills|0 stack", *mod.SECTION_PREAMBLE, *[x for row in rows for x in ("|", row)]])
        return _put(self.root / name, f"# Project\n\n<!-- SKF:BEGIN updated:2026-01-01 -->\n{body}\n<!-- SKF:END -->\n\nTail.\n")

    def assemble(self, context_file, skill_root=".claude/skills/", **kw):
        result = mod.cmd_assemble(str(context_file), str(self.skills), skill_root, **kw)
        staged = Path(result["content_file"]) if result["status"] == "ok" else None
        return result, staged.read_bytes().decode("utf-8") if staged else None


@pytest.fixture
def forge(tmp_path):
    return Forge(tmp_path)


class TestAssemble:
    """Suite 19: assemble builds the body from the manifest and the snippets."""

    def test_the_body_is_the_documented_format(self, forge):
        """Two snippets rendered from snippet-format.md give managed-section-format.md's section body."""
        for name in ("zod", "cognee"):
            forge.export(name, "1.4.0", snippet=_render_snippet(name, REAL_GOTCHAS[name]) + "\n")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert r["status"] == "ok" and body == REAL_BODY
        assert r["content_file"] == str(forge.root / "CLAUDE.md") + ".skf-content"

    def test_versioned_and_flat_snippets_and_a_missing_one(self, forge):
        forge.export("alpha", "1.0.0")
        forge.export("beta", "0.9.0", layout="flat")
        forge.exports["gamma"] = {"active_version": "2.0.0", "versions": {"2.0.0": {"status": "active"}}}
        forge.save()
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert [(i["skill_name"], i["snippet_source"]) for i in r["included"]] == [("alpha", "versioned"), ("beta", "flat")]
        gamma = forge.skills / "gamma"
        assert r["skipped_missing_snippet"] == [
            {
                "skill_name": "gamma",
                "version": "2.0.0",
                "tried": [str(p / "context-snippet.md") for p in (gamma / "2.0.0" / "gamma", gamma / "active" / "gamma", gamma)],
            }
        ]
        assert _rows(body) == [("alpha", "1.0.0"), ("beta", "0.9.0")]

    def test_the_active_link_when_the_versioned_package_is_gone(self, forge):
        forge.export("alpha", "1.0.0")
        shutil.rmtree(forge.skills / "alpha" / "1.0.0")
        forge.package("alpha", "1.1.0")
        try:
            os.symlink("1.1.0", forge.skills / "alpha" / "active", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        [item] = r["included"]
        assert (item["snippet_source"], item["version"], item["active_version"]) == ("active", "1.1.0", "1.0.0")
        assert _rows(body) == [("alpha", "1.1.0")]

    def test_deprecated_and_broken_entries_are_skipped(self, forge):
        forge.export("keep", "1.0.0")
        forge.export("old", "1.0.0", status="deprecated")
        forge.export("broken", "2.0.0")
        forge.exports["broken"]["active_version"] = "3.0.0"
        forge.exports["bare"] = {"versions": {}}
        forge.exports["../escape"] = {"active_version": "1.0.0", "versions": {"1.0.0": {"status": "active"}}}
        forge.save()
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert _rows(body) == [("keep", "1.0.0")]
        assert r["skipped_deprecated"] == [{"skill_name": "old", "version": "1.0.0"}]
        assert {s["skill_name"]: s["reason"] for s in r["skipped_integrity"]} == {
            "../escape": "the skill name or its active_version is not a plain folder name",
            "bare": "the manifest entry has no active_version",
            "broken": "active_version 3.0.0 has no entry under versions",
        }

    def test_every_root_takes_the_target_skill_root(self, forge):
        for name, root in (("a", ".claude/skills/"), ("b", "skills/"), ("c", ".windsurf/skills/")):
            forge.export(name, "1.0.0", snippet=_snippet(name, "1.0.0", root))
        r, body = forge.assemble(forge.root / "AGENTS.md", ".windsurf/skills/")
        assert r["effective_root"] == ".windsurf/skills/"
        assert [line for line in body.split("\n") if "root:" in line] == [
            f"|[{name} v1.0.0]|root: .windsurf/skills/{name}/" for name in "abc"
        ]
        assert [i["root_rewritten"] for i in r["included"]] == [True, True, False]

    @pytest.mark.parametrize("override", ["skills/", "skills", " skills/ "])
    def test_the_override_is_every_rows_root(self, forge, override):
        forge.export("a", "1.0.0", snippet=_snippet("a", "1.0.0", "skills/"))
        forge.export("b", "1.0.0", snippet=_snippet("b", "1.0.0", ".claude/skills/"))
        r, body = forge.assemble(forge.root / "CLAUDE.md", ".claude/skills/", override=override)
        assert r["effective_root"] == "skills/"
        assert [line for line in body.split("\n") if "root:" in line] == [
            "|[a v1.0.0]|root: skills/a/",
            "|[b v1.0.0]|root: skills/b/",
        ]
        assert [i["root_rewritten"] for i in r["included"]] == [False, True]

    def test_the_counts_come_from_metadata_skill_type(self, forge):
        """`individual` is a single skill, as skf-skill-inventory.py reads it."""
        forge.export("one", "1.0.0")
        forge.export("two", "1.0.0", skill_type="individual")
        forge.export("app-stack", "0.1.0", skill_type="stack")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert (r["n_single"], r["n_stack"], r["warnings"]) == (2, 1, [])
        assert body.split("\n")[0] == "[SKF Skills]|2 skills|1 stack"
        assert {i["skill_name"]: i["skill_type"] for i in r["included"]} == {"app-stack": "stack", "one": "single", "two": "single"}

    def test_without_skill_type_the_row_decides(self, forge):
        forge.export("app-stack", "0.1.0", skill_type=None, snippet=_snippet("app-stack", "0.1.0", ".claude/skills/", "|stack: a@1"))
        forge.export("lib", "1.0.0", skill_type=None)
        r, _ = forge.assemble(forge.root / "CLAUDE.md")
        assert (r["n_single"], r["n_stack"]) == (1, 1)
        assert len(r["warnings"]) == 2 and all("counted as" in w for w in r["warnings"])

    def test_rows_are_sorted_by_name(self, forge):
        for name in ("zeta", "alpha", "mid"):
            forge.export(name, "1.0.0")
        _, body = forge.assemble(forge.root / "CLAUDE.md")
        assert [name for name, _ in _rows(body)] == ["alpha", "mid", "zeta"]

    def test_orphans_are_kept_verbatim_from_every_target(self, forge):
        forge.export("foo", "1.0.0")
        ext1 = "|[ext1 v1.0]|root: .claude/skills/ext1/\n|IMPORTANT: ext1 with `code` and a literal | pipe"
        ext1_elsewhere = "|[ext1 v1.0]|root: .cursor/skills/ext1/\n|IMPORTANT: another copy"
        ext2 = "|[ext2 v2.0]|root: .cursor/skills/ext2/\n|stack: a@1"
        claude = forge.context("CLAUDE.md", "|" + _snippet("foo", "0.9.0").rstrip("\n"), ext1)
        cursor = forge.context(".cursorrules", ext2, ext1_elsewhere)
        sources = [str(claude), str(cursor)]
        r1, body1 = forge.assemble(claude, ".claude/skills/", orphan_sources=sources)
        r2, body2 = forge.assemble(cursor, ".cursor/skills/", orphan_sources=sources)
        assert _rows(body1) == [("ext1", "1.0"), ("ext2", "2.0"), ("foo", "1.0.0")]
        assert ext1 in body1 and ext2 in body1 and ext1_elsewhere not in body1
        # The first file wins for both targets, so every file gets the same orphan rows.
        assert body2 == body1.replace("root: .claude/skills/foo/", "root: .cursor/skills/foo/")
        assert (r1["n_single"], r1["n_stack"]) == (2, 1)
        assert [(o["skill_name"], o["source_files"], o["skill_type"]) for o in r1["orphan_rows"]] == [
            ("ext1", sorted(sources), "single"),
            ("ext2", [str(cursor)], "stack"),
        ]
        assert r2["orphan_rows"] == r1["orphan_rows"]

    def test_the_context_file_is_always_scanned(self, forge):
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/")
        agents = forge.context("AGENTS.md")
        r, body = forge.assemble(claude, orphan_sources=[str(agents)])
        assert _rows(body) == [("ext", "1.0")] and r["orphan_rows"][0]["source_files"] == [str(claude)]

    def test_orphans_drop_leaves_them_out(self, forge):
        forge.export("foo", "1.0.0")
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/")
        r, body = forge.assemble(claude, orphans="drop")
        assert _rows(body) == [("foo", "1.0.0")] and r["orphans"] == "drop"
        assert [o["skill_name"] for o in r["orphan_rows"]] == ["ext"]
        assert (r["n_single"], r["n_stack"]) == (1, 0)

    def test_a_renamed_skills_old_rows_are_not_orphans(self, forge):
        forge.export("new-name", "1.0.0")  # the manifest after the re-key
        claude = forge.context("CLAUDE.md", "|[old-name v1.0.0]|root: .claude/skills/old-name/", "|[ext v1.0]|root: x/ext/")
        r, body = forge.assemble(claude, renamed=("old-name", "new-name"))
        assert _rows(body) == [("ext", "1.0"), ("new-name", "1.0.0")] and r["warnings"] == []
        _, body = forge.assemble(claude)  # without --renamed the old row would stay
        assert _rows(body) == [("ext", "1.0"), ("new-name", "1.0.0"), ("old-name", "1.0.0")]
        r, _ = forge.assemble(claude, renamed=("old-name", "elsewhere"))
        assert r["warnings"] == ["--renamed: elsewhere is not in the manifest, so the section has no row for it"]

    def test_a_dropped_skills_rows_are_not_orphans(self, forge):
        forge.export("stay", "1.0.0")
        claude = forge.context("CLAUDE.md", "|[gone v1.0.0]|root: .claude/skills/gone/", "|[stay v1.0.0]|root: .claude/skills/stay/")
        _, body = forge.assemble(claude, dropped=["gone"])
        assert _rows(body) == [("stay", "1.0.0")]

    def test_rows_of_skills_the_manifest_knows_are_never_orphans(self, forge):
        forge.export("old", "1.0.0", status="deprecated")
        forge.export("broken", "2.0.0")
        forge.exports["broken"]["active_version"] = "9.9.9"
        forge.exports["lost"] = {"active_version": "1.0.0", "versions": {"1.0.0": {"status": "active"}}}
        forge.save()
        claude = forge.context("CLAUDE.md", "|[broken v2.0.0]|root: x/", "|[lost v1.0.0]|root: x/", "|[old v1.0.0]|root: x/")
        r, body = forge.assemble(claude)
        assert _rows(body) == [] and r["orphan_rows"] == []

    def test_include_adds_the_skills_being_exported(self, forge):
        forge.export("foo", "1.0.0")
        forge.package("foo", "2.0.0")  # re-exported at a new version
        forge.package("fresh", "0.1.0")  # first export: not in the manifest yet
        forge.export("revived", "1.0.0", status="deprecated")
        r, body = forge.assemble(forge.root / "CLAUDE.md", includes=[("foo", "2.0.0"), ("fresh", "0.1.0"), ("revived", "1.0.0")])
        assert _rows(body) == [("foo", "2.0.0"), ("fresh", "0.1.0"), ("revived", "1.0.0")]
        assert r["skipped_deprecated"] == []

    def test_a_given_snippet_replaces_the_package_one(self, forge, tmp_path):
        forge.export("foo", "1.0.0", skill_type="stack")
        draft = _put(tmp_path / "drafts" / "foo.md", _snippet("foo", "1.0.0", "anything/", "|IMPORTANT: the draft"))
        r, body = forge.assemble(forge.root / "CLAUDE.md", snippets={"foo": str(draft), "ghost": str(draft)})
        assert body.endswith("|\n|[foo v1.0.0]|root: .claude/skills/foo/\n|IMPORTANT: the draft")
        [item] = r["included"]
        assert (item["snippet_source"], item["snippet_path"], item["skill_type"]) == ("given", str(draft), "stack")
        assert r["warnings"] == ["--snippet ghost: not one of the section's skills, so its file was not read"]
        missing = str(tmp_path / "nope.md")
        r, body = forge.assemble(forge.root / "CLAUDE.md", snippets={"foo": missing})
        assert _rows(body) == [] and r["skipped_missing_snippet"][0]["tried"] == [missing]

    @pytest.mark.parametrize(
        "snippet, reason",
        [
            (_snippet("other", "1.0.0"), "its header names other, not foo"),
            ("just prose\n", "its first line is not a [skill-name vX.Y.Z] row header"),
            ("\n\n", "the snippet is empty"),
            (_snippet("foo", "1.0.0") + "<!-- SKF:END -->\n", "the snippet holds an SKF marker (<!-- SKF:BEGIN or <!-- SKF:END)"),
        ],
    )
    def test_a_snippet_the_section_cannot_hold_is_skipped(self, forge, snippet, reason):
        forge.export("foo", "1.0.0", snippet=snippet)
        forge.export("bar", "1.0.0")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert _rows(body) == [("bar", "1.0.0")]
        assert [(s["skill_name"], s["reason"]) for s in r["skipped_malformed_snippet"]] == [("foo", reason)]

    def test_a_snippet_without_root_keeps_its_row(self, forge):
        forge.export("foo", "1.0.0", snippet="[foo v1.0.0]\n|IMPORTANT: no root\n")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert body.endswith("|\n|[foo v1.0.0]\n|IMPORTANT: no root")
        assert len(r["warnings"]) == 1 and "has no root: field" in r["warnings"][0]

    def test_a_snippet_with_its_own_pipe_and_blank_edges_keeps_one_pipe(self, forge):
        forge.export("foo", "1.0.0", snippet="\n|[foo v1.0.0]|root: x/foo/\n|IMPORTANT: y\n\n")
        _, body = forge.assemble(forge.root / "CLAUDE.md")
        assert body.endswith("|\n|[foo v1.0.0]|root: .claude/skills/foo/\n|IMPORTANT: y")

    def test_no_skills_writes_the_header_alone(self, forge):
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert body == "\n".join(["[SKF Skills]|0 skills|0 stack", *mod.SECTION_PREAMBLE])
        assert (r["n_single"], r["n_stack"], r["included"]) == (0, 0, [])

    def test_a_v1_manifest_reads_as_skf_manifest_ops_reads_it(self, forge):
        forge.package("live", "1.0.0")
        forge.package("dead", "1.0.0")
        manifest = {
            "exports": {
                "live": {"active_version": "1.0.0", "versions": ["0.9.0", "1.0.0"]},
                "dead": {"active_version": "1.0.0", "versions": ["1.0.0"], "deprecated": True},
            }
        }
        _put(forge.skills / ".export-manifest.json", json.dumps(manifest))
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert _rows(body) == [("live", "1.0.0")]
        assert r["skipped_deprecated"] == [{"skill_name": "dead", "version": "1.0.0"}]

    def test_an_unreadable_manifest_writes_nothing(self, forge):
        _put(forge.skills / ".export-manifest.json", "{not json")
        r, body = forge.assemble(forge.root / "CLAUDE.md")
        assert r["status"] == "error" and "parse error" in r["error"] and r["error"].endswith("Nothing was written.")
        assert body is None and not (forge.root / "CLAUDE.md.skf-content").exists()

    def test_out_writes_the_same_body_and_nothing_beside_the_context_file(self, forge, tmp_path_factory):
        """A dry run, or a preview before the user confirms, stages the body outside the project."""
        forge.export("foo", "1.0.0")
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/")
        _, default_body = forge.assemble(claude)
        (forge.root / "CLAUDE.md.skf-content").unlink()
        project = sorted(p.name for p in forge.root.iterdir())
        out = tmp_path_factory.mktemp("dry-run") / "preview" / "CLAUDE.md.skf-content"
        r, body = forge.assemble(claude, out=str(out))
        assert r["status"] == "ok" and r["content_file"] == str(out)
        assert out.read_bytes() == default_body.encode("utf-8") and body == default_body
        assert sorted(p.name for p in forge.root.iterdir()) == project

    @pytest.mark.parametrize("target", ["context-file", "orphan-source"])
    def test_out_never_names_a_file_the_call_reads(self, forge, target):
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/")
        agents = forge.context("AGENTS.md")
        before = {p: p.read_bytes() for p in (claude, agents)}
        out = os.path.join(str(forge.root), ".", "CLAUDE.md") if target == "context-file" else str(agents)
        r, body = forge.assemble(claude, orphan_sources=[str(agents)], out=out)
        assert r["status"] == "error" and body is None
        assert r["error"] == f"--out {out} is a context file this call reads: pass a path of its own. Nothing was written."
        assert {p: p.read_bytes() for p in before} == before
        assert sorted(p.name for p in forge.root.iterdir()) == ["AGENTS.md", "CLAUDE.md", "skills"]

    def test_a_missing_skills_folder_writes_nothing(self, tmp_path):
        r = mod.cmd_assemble(str(tmp_path / "CLAUDE.md"), str(tmp_path / "nope"), ".claude/skills/")
        assert r["status"] == "error" and "does not exist" in r["error"]
        assert not (tmp_path / "CLAUDE.md.skf-content").exists()

    def test_a_malformed_target_is_not_read_for_orphans(self, forge):
        forge.export("foo", "1.0.0")
        bad = _put(forge.root / "AGENTS.md", "<!-- SKF:BEGIN updated:2026-01-01 -->\n|[ghost v1.0]|root: x/\nUSER NOTES\n")
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/")
        r, body = forge.assemble(claude, orphan_sources=[str(claude), str(bad)])
        assert _rows(body) == [("ext", "1.0"), ("foo", "1.0.0")]
        assert r["malformed_context_files"] == [str(bad)]

    def test_an_orphan_holding_a_marker_variant_is_refused(self, forge):
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/\n|note: <!--SKF:END-->")
        r, body = forge.assemble(claude)
        assert r["status"] == "error" and f"ext v1.0 in {claude}" in r["error"] and body is None
        assert not (forge.root / "CLAUDE.md.skf-content").exists()
        r, body = forge.assemble(claude, orphans="drop")
        assert r["status"] == "ok" and _rows(body) == []

    @pytest.mark.parametrize("action", ["replace", "insert"])
    def test_the_staged_body_goes_through_replace_and_insert(self, forge, action):
        forge.export("foo", "1.0.0")
        if action == "replace":
            f = forge.context("CLAUDE.md", "|[foo v0.9.0]|root: x/foo/")
        else:
            f = _put(forge.root / "CLAUDE.md", "# Project\n")
        r, body = forge.assemble(f)
        staged = Path(r["content_file"])
        assert not staged.read_bytes().endswith(b"\n")
        with staged.open("rb") as stdin:
            proc = subprocess.run([sys.executable, str(SCRIPT), str(f), action], stdin=stdin, capture_output=True)
        assert proc.returncode == 0, proc.stdout
        text = f.read_text(encoding="utf-8")
        assert text.count("<!-- SKF:BEGIN") == 1 and mod.find_managed_section(text).group(2) == "\n" + body + "\n"

    def test_export_drop_and_rename_calls_build_the_same_body(self, forge):
        """The same manifest, snippets and sections give the same bytes, whichever skill asks."""
        forge.export("foo", "1.0.0")
        forge.export("new-name", "2.0.0")
        claude = forge.context("CLAUDE.md", "|[ext v1.0]|root: x/ext/\n|IMPORTANT: external")
        agents = forge.context("AGENTS.md", "|[foo v1.0.0]|root: .agents/skills/foo/")
        sources = [str(claude), str(agents)]
        calls = {
            "export": {"includes": [("foo", "1.0.0")]},
            "drop": {"dropped": ["gone"]},
            "rename": {"renamed": ("old-name", "new-name")},
        }
        bodies = {who: forge.assemble(claude, orphan_sources=sources, **kw)[1] for who, kw in calls.items()}
        assert bodies["export"] == bodies["drop"] == bodies["rename"]
        assert _rows(bodies["export"]) == [("ext", "1.0"), ("foo", "1.0.0"), ("new-name", "2.0.0")]


class TestAssembleCommandLine:
    """Suite 20: assemble's flags reach the action, and bad ones exit 2 before anything is written."""

    def test_the_flags_reach_the_action(self, tmp_path):
        forge = Forge(tmp_path)
        forge.export("foo", "1.0.0")
        forge.package("bar", "0.1.0")
        claude = forge.context("CLAUDE.md", "|[gone v1.0]|root: x/", "|[old v1.0]|root: x/", "|[ext v1.0]|root: x/ext/")
        proc = _run(
            "assemble", str(claude), "--skills-folder", str(forge.skills), "--skill-root", ".cursor/skills/",
            "--skill-root-override", "skills", "--include", "bar@0.1.0,", "--dropped", "gone",
            "--renamed", "old:foo", "--orphan-sources", str(claude), "--orphans", "keep",
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        out = json.loads(proc.stdout)
        assert out["effective_root"] == "skills/"
        staged = Path(out["content_file"]).read_bytes().decode("utf-8")
        assert _rows(staged) == [("bar", "0.1.0"), ("ext", "1.0"), ("foo", "1.0.0")]
        assert "|[foo v1.0.0]|root: skills/foo/" in staged

    @pytest.mark.parametrize(
        "bad",
        [
            ["--include", "foo"],
            ["--include", "foo@"],
            ["--include", "../x@1.0.0"],
            ["--include", "foo@1,foo@2"],
            ["--renamed", "a"],
            ["--renamed", "a:a"],
            ["--renamed", ":b"],
            ["--snippet", "foo"],
            ["--snippet", "foo=a", "--snippet", "foo=b"],
            ["--dropped", "a/b"],
            ["--orphans", "maybe"],
        ],
    )
    def test_a_bad_flag_exits_2(self, tmp_path, bad):
        proc = _run("assemble", str(tmp_path / "CLAUDE.md"), "--skills-folder", str(tmp_path), "--skill-root", ".claude/skills/", *bad)
        assert proc.returncode == 2
        assert not (tmp_path / "CLAUDE.md.skf-content").exists()

    def test_out_reaches_the_action(self, tmp_path, tmp_path_factory):
        forge = Forge(tmp_path)
        forge.export("foo", "1.0.0")
        claude = forge.context("CLAUDE.md")
        out = tmp_path_factory.mktemp("dry-run") / "CLAUDE.md.skf-content"
        proc = _run(
            "assemble", str(claude), "--skills-folder", str(forge.skills), "--skill-root", ".claude/skills/", "--out", str(out),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["content_file"] == str(out)
        assert _rows(out.read_bytes().decode("utf-8")) == [("foo", "1.0.0")]
        assert not (tmp_path / "CLAUDE.md.skf-content").exists()

    def test_an_error_exits_1(self, tmp_path):
        proc = _run("assemble", str(tmp_path / "CLAUDE.md"), "--skills-folder", str(tmp_path / "missing"), "--skill-root", ".claude/skills/")
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and "does not exist" in out["error"]


# ---------------------------------------------------------------------------
# A context file that cannot be read: a JSON error, never a traceback
# ---------------------------------------------------------------------------

# A CLAUDE.md saved as cp1252 on Windows: its accented letter is not UTF-8.
CP1252_CLAUDE_MD = "# Café notes\n\n<!-- SKF:BEGIN updated:2026-01-01 -->\n|[ext v1.0]|root: x/ext/\n<!-- SKF:END -->\n".encode("cp1252")


def _unreadable(folder: Path, kind: str) -> tuple[Path, str]:
    """A context file that cannot be read as text, and what its error says."""
    if kind == "cp1252":
        path = folder / "CLAUDE.md"
        path.write_bytes(CP1252_CLAUDE_MD)
        return path, f"{path} is not UTF-8 text"
    path = folder / "AGENTS.md"
    path.mkdir()
    return path, f"Cannot read {path}"


def _untouched(path: Path) -> bool:
    return path.read_bytes() == CP1252_CLAUDE_MD if path.is_file() else path.is_dir() and not any(path.iterdir())


class TestUnreadableContextFile:
    """Suite 21: a context file that is a folder or not UTF-8 text is a JSON error, and stays as it is."""

    @pytest.mark.parametrize("kind", ["cp1252", "folder"])
    def test_check_reports_it_unreadable(self, tmp_path, kind):
        f, says = _unreadable(tmp_path, kind)
        proc = _run(str(f), "check")
        assert proc.returncode == 1 and proc.stderr == ""
        out = json.loads(proc.stdout)
        assert (out["status"], out["case"], out["exists"], out["has_managed_section"]) == ("error", "unreadable", True, False)
        assert out["error"].startswith(says)

    @pytest.mark.parametrize("kind", ["cp1252", "folder"])
    @pytest.mark.parametrize("action", ["read", "insert", "replace", "clear"])
    def test_the_other_actions_refuse_it(self, tmp_path, kind, action):
        f, says = _unreadable(tmp_path, kind)
        proc = _run(str(f), action, *(["--content", EMPTY_BODY] if action in ("insert", "replace") else []))
        assert proc.returncode == 1 and proc.stderr == ""
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and out["error"].startswith(says)
        assert _untouched(f) and sorted(p.name for p in tmp_path.iterdir()) == [f.name]

    def test_orphan_detect_stops_on_it(self, tmp_path):
        good = _put(tmp_path / ".cursorrules", CURSOR_ORPHANS)
        bad, says = _unreadable(tmp_path, "cp1252")
        proc = _run("orphan-detect", str(good), str(bad), "--exported-skills", "foo")
        assert proc.returncode == 1 and proc.stderr == ""
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and out["error"].startswith(says)

    @pytest.mark.parametrize("kind", ["cp1252", "folder"])
    @pytest.mark.parametrize("where", ["context-file", "orphan-source"])
    def test_assemble_stops_on_it_and_writes_nothing(self, tmp_path, kind, where):
        forge = Forge(tmp_path)
        forge.export("foo", "1.0.0")
        good = forge.context("CURSOR.md", "|[ext v1.0]|root: x/ext/")
        bad, says = _unreadable(tmp_path, kind)
        target, sources = (bad, [good]) if where == "context-file" else (good, [bad, good])
        proc = _run(
            "assemble", str(target), "--skills-folder", str(forge.skills), "--skill-root", ".claude/skills/",
            "--orphan-sources", *map(str, sources),
        )
        assert proc.returncode == 1 and proc.stderr == ""
        out = json.loads(proc.stdout)
        assert out["status"] == "error" and out["error"].startswith(says) and out["error"].endswith("Nothing was written.")
        assert _untouched(bad) and sorted(p.name for p in tmp_path.iterdir()) == sorted(["CURSOR.md", bad.name, "skills"])

    def test_root_probe_skips_it(self, tmp_path):
        snippet = tmp_path / "context-snippet.md"
        snippet.write_bytes("[café v1.0]|root: skills/café/\n".encode("cp1252"))
        proc = _run("root-probe", str(snippet), "--reference-root", ".claude/skills/")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["observed_prefixes"] == []
