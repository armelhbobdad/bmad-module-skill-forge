#!/usr/bin/env python3
"""Tests for skf-comention-pairs.py.

Covers:
  - analyze: two-paragraph gate, section exclusion, substring trap, single-
    paragraph silence, evidence excerpts, deterministic ordering
  - parse_body_paragraphs / normalize_header: markdown parsing edges
  - parse_skills: structural validation
  - CLI: file input, stdin (-) piping, both-stdin guard, exit codes,
    byte-identical reproducibility
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-comention-pairs.py"

spec = importlib.util.spec_from_file_location("skf_comention_pairs", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# The canonical fixture from the implementation brief's test_idea.
# --------------------------------------------------------------------------

# (a) X and Y co-mentioned in TWO distinct body paragraphs under a normal
#     "## Data Flow" header  → pair (X, Y) qualifies with paragraph_count=2.
# (b) X and Y also co-mentioned ONCE under "## Overview"  → excluded, and
#     must not push any pair over the >=2 gate.
# (c) "react" and "reactive" both appear  → substring must not create a pair.
# (d) X and Z co-mentioned in only ONE body paragraph  → below gate, absent.
FIXTURE_DOC = """\
# Architecture

## Overview

This system uses XLib and YLib together with reactive streams.

## Data Flow

XLib produces events that YLib consumes over the bus.

Later, XLib hands its parsed output to YLib for rendering.

## Storage

XLib persists via ZLib on shutdown.

## Reactive Notes

The react library is unrelated to the reactive scheduler mentioned above.
"""

FIXTURE_SKILLS = ["XLib", "YLib", "ZLib", "react"]


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------


class TestAnalyzeCanonicalFixture:
    def _run(self) -> dict:
        return mod.analyze(FIXTURE_DOC, FIXTURE_SKILLS)

    def test_only_xy_pair_qualifies(self) -> None:
        result = self._run()
        pair_names = {(p["a"], p["b"]) for p in result["pairs"]}
        assert pair_names == {("XLib", "YLib")}

    def test_xy_paragraph_count_is_two(self) -> None:
        result = self._run()
        xy = next(
            p for p in result["pairs"] if p["a"] == "XLib" and p["b"] == "YLib"
        )
        assert xy["paragraph_count"] == 2
        assert len(xy["evidence"]) == 2

    def test_overview_comention_excluded_not_counted(self) -> None:
        # The Overview paragraph co-mentions X and Y too — but it is section-
        # excluded, so it must NOT contribute to the pair count (still 2, not 3)
        # and it must not by itself create any qualifying pair.
        result = self._run()
        xy = next(p for p in result["pairs"] if p["a"] == "XLib")
        assert xy["paragraph_count"] == 2
        # every evidence header is the Data Flow section, never Overview
        for ev in xy["evidence"]:
            assert ev["header"] == "Data Flow"

    def test_excluded_section_count(self) -> None:
        # Exactly one excluded section ("Overview") governed a body paragraph.
        result = self._run()
        assert result["excluded_section_count"] == 1

    def test_substring_trap_no_false_pair(self) -> None:
        # "react" must not match inside "reactive"; there is no other real
        # co-mention involving react, so no react pair may appear.
        result = self._run()
        for p in result["pairs"]:
            assert "react" not in (p["a"], p["b"])

    def test_single_paragraph_pair_absent(self) -> None:
        # X and Z co-mention only once (Storage) → below the >=2 gate.
        result = self._run()
        pair_names = {(p["a"], p["b"]) for p in result["pairs"]}
        assert ("XLib", "ZLib") not in pair_names
        assert ("ZLib", "XLib") not in pair_names

    def test_evidence_excerpts_present(self) -> None:
        result = self._run()
        xy = next(p for p in result["pairs"] if p["a"] == "XLib")
        excerpts = [ev["excerpt"] for ev in xy["evidence"]]
        assert any("produces events" in e for e in excerpts)
        assert any("parsed output" in e for e in excerpts)

    def test_deterministic_same_input(self) -> None:
        # Byte-identical across runs, and independent of skills input order.
        r1 = mod.analyze(FIXTURE_DOC, FIXTURE_SKILLS)
        r2 = mod.analyze(FIXTURE_DOC, list(reversed(FIXTURE_SKILLS)))
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


class TestAnalyzeOrdering:
    def test_sorted_by_count_desc_then_pair_asc(self) -> None:
        doc = """\
## Section A

alpha and beta collaborate here.

alpha and beta again in a second paragraph.

alpha and beta a third time for good measure.

## Section B

gamma and delta work together.

gamma and delta once more.
"""
        result = mod.analyze(doc, ["alpha", "beta", "gamma", "delta"])
        ordered = [(p["a"], p["b"], p["paragraph_count"]) for p in result["pairs"]]
        # (alpha,beta)=3 first, then (delta,gamma)=2
        assert ordered == [("alpha", "beta", 3), ("delta", "gamma", 2)]

    def test_pair_names_are_lexicographic(self) -> None:
        doc = "zeta talks to alpha.\n\nzeta talks to alpha again.\n"
        result = mod.analyze(doc, ["zeta", "alpha"])
        assert result["pairs"][0]["a"] == "alpha"
        assert result["pairs"][0]["b"] == "zeta"

    def test_empty_skills_yields_no_pairs(self) -> None:
        result = mod.analyze(FIXTURE_DOC, [])
        assert result["pairs"] == []

    def test_empty_doc_yields_no_pairs(self) -> None:
        result = mod.analyze("", ["a", "b"])
        assert result == {"pairs": [], "excluded_section_count": 0}


class TestSectionExclusion:
    def test_all_exclusion_headers(self) -> None:
        for header in [
            "Introduction",
            "Overview",
            "Glossary",
            "Table of Contents",
            "References",
            "Appendix",
            "Index",
        ]:
            doc = f"## {header}\n\nlibA and libB.\n\nlibA and libB again.\n"
            result = mod.analyze(doc, ["libA", "libB"])
            assert result["pairs"] == [], f"{header} should be excluded"
            assert result["excluded_section_count"] == 1

    def test_exclusion_header_normalised(self) -> None:
        # trailing punctuation + mixed case + closing hashes all normalise
        doc = "## OVERVIEW:  ##\n\nlibA and libB.\n\nlibA and libB again.\n"
        result = mod.analyze(doc, ["libA", "libB"])
        assert result["pairs"] == []
        assert result["excluded_section_count"] == 1

    def test_h1_governs_exclusion(self) -> None:
        # An H1 "Overview" governs following paragraphs until the next H1/H2.
        doc = "# Overview\n\nlibA and libB.\n\nlibA and libB again.\n"
        result = mod.analyze(doc, ["libA", "libB"])
        assert result["pairs"] == []

    def test_h3_does_not_change_governing_header(self) -> None:
        # H3 under an excluded H2 does not lift the exclusion.
        doc = (
            "## Overview\n\n### Details\n\n"
            "libA and libB.\n\nlibA and libB again.\n"
        )
        result = mod.analyze(doc, ["libA", "libB"])
        assert result["pairs"] == []

    def test_heading_text_is_not_a_comention_source(self) -> None:
        # Both names appear only in the heading, never in a body paragraph.
        doc = "## libA and libB\n\nSome unrelated prose here.\n"
        result = mod.analyze(doc, ["libA", "libB"])
        assert result["pairs"] == []

    def test_paragraph_before_any_header_is_included(self) -> None:
        doc = "libA and libB.\n\nlibA and libB again.\n\n# Title\n"
        result = mod.analyze(doc, ["libA", "libB"])
        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["evidence"][0]["header"] is None


class TestWordBoundary:
    def test_substring_not_matched(self) -> None:
        doc = "reactive scheduler and redux store.\n\nreactive and redux.\n"
        # "react" must not match "reactive"
        result = mod.analyze(doc, ["react", "redux"])
        assert result["pairs"] == []

    def test_case_insensitive(self) -> None:
        doc = "REACT and Redux.\n\nreact and redux.\n"
        result = mod.analyze(doc, ["react", "redux"])
        assert len(result["pairs"]) == 1


# --------------------------------------------------------------------------
# parse_body_paragraphs / normalize_header
# --------------------------------------------------------------------------


class TestParsing:
    def test_multiline_paragraph_joined(self) -> None:
        doc = "line one\nline two\n\nnext para\n"
        paras = mod.parse_body_paragraphs(doc)
        assert paras == [(None, "line one\nline two"), (None, "next para")]

    def test_header_terminates_paragraph(self) -> None:
        doc = "para under none\n## H\nbody\n"
        paras = mod.parse_body_paragraphs(doc)
        assert paras == [(None, "para under none"), ("H", "body")]

    def test_hash_without_space_is_body(self) -> None:
        # `#foo` is not an ATX header (no space) → treated as body text.
        paras = mod.parse_body_paragraphs("#foo bar\n")
        assert paras == [(None, "#foo bar")]

    def test_normalize_header(self) -> None:
        assert mod.normalize_header("Table  of   Contents") == "table of contents"
        assert mod.normalize_header("Overview:") == "overview"
        assert mod.normalize_header("  APPENDIX  ") == "appendix"


# --------------------------------------------------------------------------
# parse_skills
# --------------------------------------------------------------------------


class TestParseSkills:
    def test_valid(self) -> None:
        assert mod.parse_skills('["a", "b"]') == ["a", "b"]

    def test_malformed_json_raises(self) -> None:
        import pytest

        with pytest.raises(mod.UserError, match="malformed JSON"):
            mod.parse_skills("{not json")

    def test_not_array_raises(self) -> None:
        import pytest

        with pytest.raises(mod.UserError, match="must be a JSON array"):
            mod.parse_skills('{"a": 1}')

    def test_non_string_entry_raises(self) -> None:
        import pytest

        with pytest.raises(mod.UserError, match="non-empty string"):
            mod.parse_skills('["a", 42]')

    def test_empty_string_entry_raises(self) -> None:
        import pytest

        with pytest.raises(mod.UserError, match="non-empty string"):
            mod.parse_skills('["a", ""]')


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(
    *args: str, stdin_text: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        input=stdin_text,
        check=False,
    )


class TestCli:
    def test_comention_from_files(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(FIXTURE_DOC, encoding="utf-8")
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps(FIXTURE_SKILLS), encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", str(skills)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [(p["a"], p["b"]) for p in payload["pairs"]] == [("XLib", "YLib")]
        assert payload["pairs"][0]["paragraph_count"] == 2

    def test_comention_skills_from_stdin(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(FIXTURE_DOC, encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", "-",
            stdin_text=json.dumps(FIXTURE_SKILLS),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [(p["a"], p["b"]) for p in payload["pairs"]] == [("XLib", "YLib")]

    def test_comention_doc_from_stdin(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps(FIXTURE_SKILLS), encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", "-", "--skills", str(skills),
            stdin_text=FIXTURE_DOC,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [(p["a"], p["b"]) for p in payload["pairs"]] == [("XLib", "YLib")]

    def test_both_stdin_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "comention", "--doc", "-", "--skills", "-", stdin_text="x"
        )
        assert result.returncode == 1
        assert "both read from stdin" in result.stderr

    def test_missing_doc_exits_1(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills.json"
        skills.write_text("[]", encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(tmp_path / "nope.md"),
            "--skills", str(skills),
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_malformed_skills_exits_1(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text("body\n", encoding="utf-8")
        skills = tmp_path / "skills.json"
        skills.write_text("{not json", encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", str(skills)
        )
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_reproducible_output(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(FIXTURE_DOC, encoding="utf-8")
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps(FIXTURE_SKILLS), encoding="utf-8")
        r1 = _run_cli("comention", "--doc", str(doc), "--skills", str(skills))
        r2 = _run_cli("comention", "--doc", str(doc), "--skills", str(skills))
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout

    def test_empty_skills_array(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(FIXTURE_DOC, encoding="utf-8")
        skills = tmp_path / "skills.json"
        skills.write_text("[]", encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", str(skills)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["pairs"] == []
