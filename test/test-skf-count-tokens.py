#!/usr/bin/env python3
"""Tests for skf-count-tokens.py — deterministic per-artifact token/word metrics."""

from __future__ import annotations

import importlib.util
import json
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
