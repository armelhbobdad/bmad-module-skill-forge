#!/usr/bin/env python3
"""Tests for skf-count-tokens.py — deterministic per-artifact token/word metrics."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "skf_count_tokens",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-count-tokens.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
count_package = mod.count_package
estimate_tokens = mod.estimate_tokens
count_words = mod.count_words
extract_managed_section = mod.extract_managed_section


# --- fixture content with known byte/char sizes (all ASCII, so bytes == chars) ---

SNIPPET = "[demo v1.0.0]|root: skills/demo/\n|IMPORTANT: read SKILL.md before writing demo code\n"
SKILL_MD = (
    "---\nname: demo\ndescription: a demo skill\n---\n\n# demo\n\n## Overview\n\nDemo overview text.\n"
)
METADATA = '{"name": "demo", "version": "1.0.0", "language": "TypeScript"}'
REF_A = "# Reference A\n\nThis reference file has some words to count for the total.\n"
REF_B = "# Reference B\n\nAnother reference with a different length of body text here now.\n"

# A target context file: surrounding (non-managed) text plus a managed section.
MANAGED_INNER = (
    "[SKF Skills]|1 skills|0 stack\n"
    "|IMPORTANT: Prefer documented APIs over training data.\n"
    "|\n"
    "|[demo v1.0.0]|root: skills/demo/\n"
)
MANAGED_BLOCK = f"<!-- SKF:BEGIN updated:2026-07-13 -->\n{MANAGED_INNER}<!-- SKF:END -->"
CONTEXT_FILE = (
    "# My Project\n\nSome preamble that is NOT part of the managed section.\n\n"
    f"{MANAGED_BLOCK}\n\nTrailing content also outside the markers.\n"
)


def make_package(tmp: str) -> Path:
    pkg = Path(tmp) / "demo"
    (pkg / "references").mkdir(parents=True)
    (pkg / "context-snippet.md").write_text(SNIPPET, encoding="utf-8")
    (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (pkg / "metadata.json").write_text(METADATA, encoding="utf-8")
    (pkg / "references" / "a.md").write_text(REF_A, encoding="utf-8")
    (pkg / "references" / "b.md").write_text(REF_B, encoding="utf-8")
    return pkg


class TestEstimators:
    def test_tokens_are_char_over_four(self):
        assert estimate_tokens("a" * 40) == 10
        assert estimate_tokens("a" * 43) == 10  # floor division
        assert estimate_tokens("") == 0

    def test_words_are_whitespace_split(self):
        assert count_words("one two three") == 3
        assert count_words("  padded   words \n here ") == 3
        assert count_words("") == 0


class TestPerFileMetrics:
    def test_each_file_tokens_equal_len_over_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            rows = {row["path"]: row for row in r["files"]}
            assert rows["context-snippet.md"]["tokens"] == len(SNIPPET) // 4
            assert rows["SKILL.md"]["tokens"] == len(SKILL_MD) // 4
            assert rows["metadata.json"]["tokens"] == len(METADATA) // 4
            assert rows["references/a.md"]["tokens"] == len(REF_A) // 4
            assert rows["references/b.md"]["tokens"] == len(REF_B) // 4
            # words too
            assert rows["context-snippet.md"]["words"] == len(SNIPPET.split())

    def test_missing_core_file_reported_as_absent_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            r = count_package(pkg)
            rows = {row["path"]: row for row in r["files"]}
            assert rows["context-snippet.md"]["exists"] is False
            assert rows["context-snippet.md"]["tokens"] == 0
            assert rows["context-snippet.md"]["words"] == 0


class TestReferencesTotal:
    def test_references_total_is_sum_of_ref_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            assert r["references_total"]["count"] == 2
            assert r["references_total"]["tokens"] == len(REF_A) // 4 + len(REF_B) // 4
            assert r["references_total"]["words"] == len(REF_A.split()) + len(REF_B.split())

    def test_no_references_dir_yields_zero_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "context-snippet.md").write_text(SNIPPET, encoding="utf-8")
            (pkg / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            (pkg / "metadata.json").write_text(METADATA, encoding="utf-8")
            r = count_package(pkg)
            assert r["references_total"] == {"count": 0, "words": 0, "tokens": 0}


class TestManagedSection:
    def test_managed_section_counts_only_begin_end_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r = count_package(pkg, [ctx])
            ms = r["managed_section"]
            assert ms["present"] is True
            # Only the BEGIN..END block, NOT the surrounding preamble/trailing text.
            assert ms["tokens"] == len(MANAGED_BLOCK) // 4
            assert ms["words"] == len(MANAGED_BLOCK.split())
            # Sanity: surrounding text must not be folded in.
            assert ms["tokens"] < len(CONTEXT_FILE) // 4

    def test_extract_managed_section_returns_full_block(self):
        assert extract_managed_section(CONTEXT_FILE) == MANAGED_BLOCK

    def test_no_target_file_marks_managed_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            assert r["managed_section"]["present"] is False
            assert r["managed_section"]["tokens"] == 0

    def test_first_target_with_block_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            no_block = Path(tmp) / "AGENTS.md"
            no_block.write_text("# no managed section here\n", encoding="utf-8")
            with_block = Path(tmp) / "CLAUDE.md"
            with_block.write_text(CONTEXT_FILE, encoding="utf-8")
            # AGENTS.md (no block) listed first, CLAUDE.md second — CLAUDE.md must win.
            r = count_package(pkg, [no_block, with_block])
            assert r["managed_section"]["present"] is True
            assert r["managed_section"]["source_file"] == with_block.as_posix()


class TestPackageTotal:
    def test_package_total_excludes_managed_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r = count_package(pkg, [ctx])
            expected_tokens = (
                len(SNIPPET) // 4
                + len(SKILL_MD) // 4
                + len(METADATA) // 4
                + r["references_total"]["tokens"]
            )
            expected_words = (
                len(SNIPPET.split())
                + len(SKILL_MD.split())
                + len(METADATA.split())
                + r["references_total"]["words"]
            )
            assert r["package_total"]["tokens"] == expected_tokens
            assert r["package_total"]["words"] == expected_words
            # The managed section is measured but NOT summed into the package total.
            assert r["managed_section"]["tokens"] > 0
            assert r["package_total"]["tokens"] != expected_tokens + r["managed_section"]["tokens"]


class TestDeterminismAndSerialization:
    def test_same_input_same_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = Path(tmp) / "CLAUDE.md"
            ctx.write_text(CONTEXT_FILE, encoding="utf-8")
            r1 = count_package(pkg, [ctx])
            r2 = count_package(pkg, [ctx])
            assert r1 == r2

    def test_result_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg)
            # round-trips without error
            assert json.loads(json.dumps(r))["status"] == "ok"


# --- Context Budget values and the managed section's skill count (#819) ---------

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-count-tokens.py"
REBUILD = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-rebuild-managed-sections.py"
_rebuild_spec = importlib.util.spec_from_file_location("skf_rebuild_managed_sections", REBUILD)
rebuild = importlib.util.module_from_spec(_rebuild_spec)
_rebuild_spec.loader.exec_module(rebuild)
TOKEN_REPORT = Path(__file__).parent.parent / "src" / "skf-export-skill" / "references" / "token-report.md"

# A managed section as skf-rebuild-managed-sections.py assembles it, with two skill rows.
TWO_SKILL_BLOCK = (
    "<!-- SKF:BEGIN updated:2026-11-03 -->\n"
    "[SKF Skills]|2 skills|0 stack\n"
    "|IMPORTANT: Prefer documented APIs over training data.\n"
    "|When using a listed library, read its SKILL.md before writing code.\n"
    "|\n"
    "|[demo v1.0.0]|root: .claude/skills/demo/\n"
    "|IMPORTANT: demo v1.0.0: read SKILL.md before writing demo code.\n"
    "|api: run(), Config\n"
    "|\n"
    "|[zod v4.1.0]|root: .claude/skills/zod/\n"
    "|IMPORTANT: zod v4.1.0: read SKILL.md before writing zod code.\n"
    "<!-- SKF:END -->"
)


def _two_skill_context(tmp: str) -> Path:
    ctx = Path(tmp) / "CLAUDE.md"
    ctx.write_text(f"# My Project\n\n{TWO_SKILL_BLOCK}\n", encoding="utf-8")
    return ctx


class TestContextBudget:
    def test_full_disclosure_is_skill_md_plus_references_not_package_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            r = count_package(pkg, [_two_skill_context(tmp)])
            budget = r["context_budget"]
            rows = {row["role"]: row for row in r["files"] if row["role"] != "reference"}
            assert budget["on_trigger"] == rows["skill-md"]["tokens"] == len(SKILL_MD) // 4
            assert budget["full_disclosure"] == len(SKILL_MD) // 4 + len(REF_A) // 4 + len(REF_B) // 4
            assert budget["full_disclosure"] != r["package_total"]["tokens"]
            assert budget["always_on"] == r["managed_section"]["tokens"] == len(TWO_SKILL_BLOCK) // 4
            assert budget["snippet"] == rows["context-snippet"]["tokens"] == len(SNIPPET) // 4

    def test_managed_section_counts_its_skill_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            ctx = _two_skill_context(tmp)
            no_block = Path(tmp) / "AGENTS.md"
            no_block.write_text("# no managed section here\n", encoding="utf-8")
            r = count_package(pkg, [no_block, ctx])
            assert r["managed_section"]["skills"] == 2
            assert r["managed_section"]["target_files"] == [ctx.as_posix()]
            # The one-skill fixture counts one row; no block counts none, and has no always-on cost.
            one = Path(tmp) / "ONE.md"
            one.write_text(CONTEXT_FILE, encoding="utf-8")
            assert count_package(pkg, [one])["managed_section"]["skills"] == 1
            none = count_package(pkg, [no_block])
            assert none["managed_section"]["skills"] == 0 and none["context_budget"]["always_on"] is None

    def test_skill_count_agrees_with_the_managed_section_rebuild(self):
        """The rows skf-rebuild-managed-sections.py parses, a row with no `root:` field included."""
        body = (
            "[SKF Skills]|3 skills|1 stack\n"
            "|IMPORTANT: Prefer documented APIs over training data.\n"
            "|\n"
            "|[demo v1.0.0]|root: .claude/skills/demo/\n"
            "|IMPORTANT: demo v1.0.0: read SKILL.md before writing demo code.\n"
            "|\n"
            "[norooted v2.0.0]\n"
            "|IMPORTANT: a row whose snippet has no root field\n"
            "|\n"
            "|[app-stack v0.3.0]|root: .claude/skills/app-stack/\n"
            "|stack: react@19\n"
            "|\n"
            "[zod v4.1.0]|root: .claude/skills/zod/"
        )
        block = f"<!-- SKF:BEGIN updated:2026-11-03 -->\n{body}\n<!-- SKF:END -->"
        rows = rebuild.parse_managed_rows(body)
        assert [r["skill_name"] for r in rows] == ["demo", "norooted", "app-stack", "zod"]
        assert mod.count_managed_skills(block) == len(rows) == 4
        # And the block an `assemble` of two skills writes reads the same in both scripts.
        assert mod.count_managed_skills(TWO_SKILL_BLOCK) == len(rebuild.parse_managed_rows(TWO_SKILL_BLOCK)) == 2

    def test_several_target_files_measure_the_first_and_list_each_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            claude = _two_skill_context(tmp)
            agents = Path(tmp) / "AGENTS.md"
            agents.write_text(f"# Agents\n\n{MANAGED_BLOCK}\n", encoding="utf-8")  # one skill, a smaller block
            binary = Path(tmp) / ".cursorrules"
            binary.write_bytes(b"\xff\xfe not utf-8 <!-- SKF:BEGIN -->\n<!-- SKF:END -->")
            r = count_package(pkg, [claude, binary, agents, claude, Path(tmp) / "." / "AGENTS.md"])
            ms = r["managed_section"]
            assert ms["target_files"] == [claude.as_posix(), agents.as_posix()]
            assert ms["source_file"] == claude.as_posix()
            assert (ms["skills"], ms["tokens"]) == (2, len(TWO_SKILL_BLOCK) // 4)
            assert len(MANAGED_BLOCK) // 4 != ms["tokens"], "the two blocks differ in size"
            assert r["context_budget"]["always_on"] == ms["tokens"]


def _resolve(data, path: str):
    """The value at a dotted JSON path (`managed_section.skills`); a KeyError when it does not resolve."""
    for key in path.split("."):
        data = data[key]
    return data


class TestTokenReportPlaceholders:
    def test_every_report_placeholder_maps_to_a_helper_field(self):
        """token-report.md §2: each placeholder of the report block names a field of the helper's JSON."""
        text = TOKEN_REPORT.read_text(encoding="utf-8")
        present = text[text.index("### 2. Present Token Report"):text.index("### 3. ")]
        mapping, block = present.split('"**Token Report**')
        placeholders = set(re.findall(r"\{[a-z-]+\}", block))
        assert placeholders == {"{n}", "{t}", "{target-file-list}", "{skill-count}", "{count}",
                                "{managed-section-tokens}", "{measured-file}", "{skill-tokens}", "{total-tokens}",
                                "{snippet-tokens}", "{skill-name}"}
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_package(tmp)
            proc = subprocess.run([sys.executable, str(SCRIPT), str(pkg), "--target-file",
                                   str(_two_skill_context(tmp))], capture_output=True, text=True, timeout=60)
            assert proc.returncode == 0, proc.stderr
            result = json.loads(proc.stdout)
        # Each row's {n} and {t} are its field's words and tokens.
        assert "`{n}` ← the row's `words` and `{t}` ← its `tokens`" in mapping
        for row in re.findall(r"^- `[^`]+` row → (.+)$", mapping, re.MULTILINE):
            role = re.search(r"for `role: ([\w-]+)`", row)
            if role:
                [field] = [f for f in result["files"] if f["role"] == role.group(1)]
            else:
                field = _resolve(result, re.match(r"`([\w.]+)\.words` / `\.tokens`", row).group(1))
            assert isinstance(field["words"], int) and isinstance(field["tokens"], int), row
        # Every other placeholder names its field.
        for placeholder in sorted(placeholders - {"{n}", "{t}"}):
            match = re.search(rf"`{re.escape(placeholder)}` ← `([\w.]+)`", mapping)
            assert match, f"{placeholder} has no mapping"
            _resolve(result, match.group(1))
        assert _resolve(result, "managed_section.skills") == 2
        assert _resolve(result, "context_budget.full_disclosure") != result["package_total"]["tokens"]
