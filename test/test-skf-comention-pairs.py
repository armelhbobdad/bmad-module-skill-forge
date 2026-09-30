#!/usr/bin/env python3
"""Tests for skf-comention-pairs.py.

Covers:
  - analyze: two-paragraph gate, section exclusion, substring trap, single-
    paragraph silence, evidence excerpts, deterministic ordering
  - evidence kinds (#582): co-mention, lead-in and list-only for prose,
    list items (blockquoted ones too), table rows and code lines;
    comention_count and lead_in_count; line numbers; a Tech Stack table
    plus a Components list gives list-only candidates
  - unit quotes: unit_line and unit_excerpt show the co-mention or the
    lead-in past the paragraph excerpt, within 240 characters, keeping both
    names when they are far apart
  - aliases: alias and multi-word matching, merging, non-word term edges
  - mentions (#598): mentioned, fenced_only and unmentioned sets, fenced
    blocks skipped and listed with their info strings, headings, per-skill
    paragraphs, candidates, each occurrence naming the longest term
  - infer (#582 no-document path): docs mentions with self-masking, shared
    keywords, a language (or a stack's list of them) never pairing on its
    own, the Top-K cap
  - parse_body_paragraphs / normalize_header / read_markdown: markdown
    parsing edges, linear time on long runs of spaces
  - parse_skills: structural validation, inventory entries as they are
  - CLI: file input, stdin (-) piping, both-stdin guard, exit codes,
    non-UTF-8 input, byte-identical reproducibility, for each subcommand
"""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest


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


def _pair(result: dict, a: str, b: str, key: str = "pairs") -> dict:
    return next(p for p in result[key] if (p["a"], p["b"]) == (a, b))


def _kinds(result: dict, a: str, b: str, key: str = "pairs") -> list[str]:
    return [e["kind"] for e in _pair(result, a, b, key)["evidence"]]


def _skills(*entries: object) -> list:
    """Skills as the CLI parses them from a --skills JSON array."""
    return mod.parse_skills(json.dumps(list(entries)))


def _twice(paragraph: str) -> str:
    """The paragraph twice, as two paragraphs, to meet the >=2 gate."""
    return paragraph + "\n" + paragraph


# --------------------------------------------------------------------------
# Evidence kinds (#582): co-mention, lead-in and list-only
# --------------------------------------------------------------------------

# The #582 case: a Tech Stack table and a Components list name every
# library, which gives every pair the two paragraphs the gate asks for.
# Only the Data Flow paragraph describes two libraries together.
STACK_DOC = """\
# Shop

## Tech Stack

| Layer | Library |
| --- | --- |
| UI | react |
| API | express |
| Auth | passport |

## Components

- react renders the storefront
- express serves the REST API
- passport authenticates sessions

## Data Flow

The react client calls express over fetch for every page.
"""

STACK_SKILLS = ["react", "express", "passport"]


class TestEvidenceKinds:
    def test_listed_pairs_stay_candidates_with_list_only_evidence(self) -> None:
        result = mod.analyze(STACK_DOC, STACK_SKILLS)
        # Every pair still meets the two-paragraph gate: the pairs are
        # candidates, and the calling step reads their evidence.
        assert [(p["a"], p["b"]) for p in result["pairs"]] == [
            ("express", "react"), ("express", "passport"), ("passport", "react"),
        ]
        for a, b in [("express", "passport"), ("passport", "react")]:
            pair = _pair(result, a, b)
            assert pair["paragraph_count"] == 2
            assert (pair["comention_count"], pair["lead_in_count"]) == (0, 0)
            assert _kinds(result, a, b) == ["list-only", "list-only"]

    def test_prose_paragraph_is_a_co_mention(self) -> None:
        pair = _pair(mod.analyze(STACK_DOC, STACK_SKILLS), "express", "react")
        assert pair["paragraph_count"] == 3
        assert pair["comention_count"] == 1
        assert [(e["header"], e["kind"]) for e in pair["evidence"]] == [
            ("Tech Stack", "list-only"),
            ("Components", "list-only"),
            ("Data Flow", "co-mention"),
        ]

    def test_evidence_line_is_the_paragraph_first_line(self) -> None:
        pair = _pair(mod.analyze(STACK_DOC, STACK_SKILLS), "express", "react")
        assert [e["line"] for e in pair["evidence"]] == [5, 13, 19]

    def test_line_numbers_with_crlf(self) -> None:
        doc = (
            "## Flow\r\n\r\nreact and express.\r\n\r\n"
            "react and express again.\r\n"
        )
        pair = _pair(mod.analyze(doc, ["react", "express"]), "express", "react")
        assert [e["line"] for e in pair["evidence"]] == [3, 5]
        assert [e["unit_line"] for e in pair["evidence"]] == [3, 5]

    def test_canonical_fixture_is_all_co_mention(self) -> None:
        xy = _pair(mod.analyze(FIXTURE_DOC, FIXTURE_SKILLS), "XLib", "YLib")
        assert xy["comention_count"] == 2
        assert [e["kind"] for e in xy["evidence"]] == ["co-mention", "co-mention"]

    def test_new_fields_follow_the_existing_ones(self) -> None:
        xy = _pair(mod.analyze(FIXTURE_DOC, FIXTURE_SKILLS), "XLib", "YLib")
        assert list(xy) == [
            "a", "b", "paragraph_count", "comention_count", "lead_in_count",
            "evidence",
        ]
        assert list(xy["evidence"][0]) == [
            "header", "excerpt", "line", "kind", "unit_line", "unit_excerpt",
        ]

    def test_list_item_naming_both_is_a_co_mention(self) -> None:
        doc = _twice("- react calls express\n- passport\n")
        result = mod.analyze(doc, ["react", "express", "passport"])
        assert _pair(result, "express", "react")["comention_count"] == 2
        assert _pair(result, "passport", "react")["comention_count"] == 0

    def test_list_item_continuation_lines_join_the_item(self) -> None:
        doc = (
            "- react renders the view and\n  talks to express\n- passport\n\n"
            "- react renders the view and\ntalks to express\n- passport\n"
        )
        result = mod.analyze(doc, ["react", "express"])
        assert _kinds(result, "express", "react") == ["co-mention", "co-mention"]

    def test_nested_items_are_units_of_their_own(self) -> None:
        doc = _twice("- Backend\n  - express\n  - passport\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["list-only", "list-only"]

    def test_lead_in_line_and_item_are_a_lead_in(self) -> None:
        doc = _twice("The express layer uses:\n- passport\n- helmet\n")
        result = mod.analyze(doc, ["express", "passport", "helmet"])
        pair = _pair(result, "express", "passport")
        assert (pair["comention_count"], pair["lead_in_count"]) == (0, 2)
        assert _kinds(result, "express", "passport") == ["lead-in", "lead-in"]
        # The items under one lead-in are still only listed together.
        assert _kinds(result, "helmet", "passport") == ["list-only", "list-only"]

    def test_lead_in_that_names_nothing_leaves_items_list_only(self) -> None:
        doc = _twice("Our stack:\n- express\n- passport\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["list-only", "list-only"]

    def test_lead_in_reaches_table_rows_and_code_lines(self) -> None:
        doc = _twice(
            "express mounts these:\n| Middleware |\n| --- |\n| passport |\n"
        ) + "\n" + _twice("express mounts it so:\n```js\nuse(passport)\n```\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["lead-in"] * 4

    def test_a_lead_in_covers_the_units_up_to_the_next_run_of_prose(self) -> None:
        # comention reads fenced code as body text: after the code line, a
        # new run of prose leads the item that follows it.
        doc = _twice(
            "express serves:\n```\nroutes\n```\nprisma stores rows.\n- redis\n"
        )
        result = mod.analyze(doc, ["express", "prisma", "redis"])
        assert _kinds(result, "prisma", "redis") == ["lead-in", "lead-in"]
        assert _kinds(result, "express", "redis") == ["list-only", "list-only"]
        assert _kinds(result, "express", "prisma") == ["list-only", "list-only"]

    def test_a_co_mention_wins_over_a_lead_in(self) -> None:
        doc = _twice("express mounts passport:\n- passport sessions\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["co-mention"] * 2

    def test_blockquoted_list_items_are_units(self) -> None:
        doc = _twice("> The express layer uses:\n> - passport\n> - helmet\n")
        result = mod.analyze(doc, ["express", "passport", "helmet"])
        assert _kinds(result, "express", "passport") == ["lead-in", "lead-in"]
        assert _kinds(result, "helmet", "passport") == ["list-only", "list-only"]

    def test_blockquoted_table_rows_are_units(self) -> None:
        doc = _twice(
            "> Layer | Library\n> --- | ---\n> API | express\n> Auth | passport\n"
        )
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["list-only", "list-only"]

    def test_table_row_naming_both_is_a_co_mention(self) -> None:
        doc = _twice(
            "| Layer | Libraries |\n| --- | --- |\n"
            "| API | express with passport |\n| DB | prisma |\n"
        )
        result = mod.analyze(doc, ["express", "passport", "prisma"])
        assert _pair(result, "express", "passport")["comention_count"] == 2
        assert _kinds(result, "express", "prisma") == ["list-only", "list-only"]

    def test_table_without_leading_pipes(self) -> None:
        doc = _twice(
            "Layer | Library\n----- | -------\nAPI | express\nAuth | passport\n"
        )
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["list-only", "list-only"]

    def test_prose_then_table_without_a_blank_line(self) -> None:
        doc = _twice("express and passport meet here.\n| a |\n| - |\n| prisma |\n")
        result = mod.analyze(doc, ["express", "passport", "prisma"])
        assert _pair(result, "express", "passport")["comention_count"] == 2
        assert _kinds(result, "express", "prisma") == ["lead-in", "lead-in"]

    def test_ordered_marker_other_than_one_does_not_interrupt_prose(self) -> None:
        # CommonMark: only `1.` starts a list inside running prose, so the
        # second line continues the sentence.
        doc = _twice("express was chosen in\n2024. passport came later.\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _pair(result, "express", "passport")["comention_count"] == 2

    def test_ordered_item_one_interrupts_prose(self) -> None:
        doc = _twice("express was chosen, then:\n1. passport\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["lead-in", "lead-in"]

    def test_ordered_items_after_an_item_are_units(self) -> None:
        doc = _twice("1. express\n2. passport\n")
        result = mod.analyze(doc, ["express", "passport"])
        assert _kinds(result, "express", "passport") == ["list-only", "list-only"]

    def test_code_lines_are_units(self) -> None:
        # comention reads fenced code as body text, as it always has; each
        # code line is a unit, so a diagram edge names both of its ends.
        doc = _twice(
            "```mermaid\ngraph LR\n  react --> express\n  express --> prisma\n"
            "  prisma\n```\n"
        )
        result = mod.analyze(doc, ["react", "express", "prisma"])
        assert _pair(result, "express", "react")["comention_count"] == 2
        assert _pair(result, "express", "prisma")["comention_count"] == 2
        assert _kinds(result, "prisma", "react") == ["list-only", "list-only"]


# --------------------------------------------------------------------------
# Where a paragraph names a pair: unit_line and unit_excerpt
# --------------------------------------------------------------------------

# A first sentence longer than the 240-character paragraph excerpt.
LONG_OPENING = " ".join(["The storefront keeps every page fast and small."] * 6)


class TestUnitQuotes:
    def test_a_co_mention_past_the_excerpt_limit_is_quoted(self) -> None:
        para = LONG_OPENING + "\nThe react client calls express over fetch.\n"
        doc = "## Flow\n\n" + para + "\n" + para
        pair = _pair(mod.analyze(doc, ["react", "express"]), "express", "react")
        entry = pair["evidence"][0]
        assert "express" not in entry["excerpt"]
        assert (entry["kind"], entry["line"], entry["unit_line"]) == (
            "co-mention", 3, 4,
        )
        quote = entry["unit_excerpt"]
        assert quote.startswith("...")
        assert quote.endswith(" The react client calls express over fetch.")
        assert len(quote) <= 240

    def test_a_table_row_further_down_is_quoted(self) -> None:
        doc = _twice(
            "| Layer | Libraries |\n| --- | --- |\n| UI | react |\n"
            "| API | express with passport |\n"
        )
        result = mod.analyze(doc, ["react", "express", "passport"])
        entry = _pair(result, "express", "passport")["evidence"][1]
        assert (entry["line"], entry["unit_line"]) == (6, 9)
        assert entry["unit_excerpt"] == "| API | express with passport |"

    def test_list_only_entries_have_no_quote(self) -> None:
        doc = _twice("- react\n- express\n")
        pair = _pair(mod.analyze(doc, ["react", "express"]), "express", "react")
        entry = pair["evidence"][0]
        assert (entry["kind"], entry["unit_line"], entry["unit_excerpt"]) == (
            "list-only", None, None,
        )

    def test_unit_line_is_the_line_of_the_first_name(self) -> None:
        doc = _twice("- the view layer and\n  react talks to express\n- passport\n")
        result = mod.analyze(doc, ["react", "express", "passport"])
        entry = _pair(result, "express", "react")["evidence"][1]
        assert (entry["line"], entry["unit_line"]) == (5, 6)
        assert entry["unit_excerpt"] == (
            "- the view layer and react talks to express"
        )

    def test_a_lead_in_quotes_the_lead_in_and_the_item(self) -> None:
        doc = _twice(
            "The express server mounts:\n- passport for sessions\n"
            "- helmet for headers\n"
        )
        result = mod.analyze(doc, ["express", "passport", "helmet"])
        near = _pair(result, "express", "passport")["evidence"][0]
        far = _pair(result, "express", "helmet")["evidence"][0]
        assert (near["kind"], near["unit_line"], near["unit_excerpt"]) == (
            "lead-in", 1, "The express server mounts: - passport for sessions",
        )
        # `...` stands for the items between the lead-in and this one.
        assert (far["unit_line"], far["unit_excerpt"]) == (
            1, "The express server mounts: ... - helmet for headers",
        )

    def test_names_too_far_apart_keep_both_and_cut_the_middle(self) -> None:
        filler = " ".join(["and then some more words"] * 20)
        doc = _twice(f"react starts here {filler} until express ends it.\n")
        pair = _pair(mod.analyze(doc, ["react", "express"]), "express", "react")
        entry = pair["evidence"][0]
        quote = entry["unit_excerpt"]
        assert quote.startswith("react starts here and then")
        assert quote.endswith("until express ends it.")
        assert quote.count(" ... ") == 1
        assert len(quote) <= 240

    def test_the_nearest_occurrences_are_quoted(self) -> None:
        filler = " ".join(["words"] * 60)
        doc = _twice(f"react first. {filler}\nLater react calls express.\n")
        pair = _pair(mod.analyze(doc, ["react", "express"]), "express", "react")
        entry = pair["evidence"][0]
        assert entry["unit_line"] == 2
        assert entry["unit_excerpt"].startswith("...")
        assert entry["unit_excerpt"].endswith("Later react calls express.")

    def test_mentions_candidates_carry_the_quote(self) -> None:
        result = mod.mentions(MENTIONS_DOC, MENTIONS_SKILLS)
        pair = _pair(result, "express", "passport", key="candidates")
        (entry,) = pair["evidence"]
        assert (entry["unit_line"], entry["unit_excerpt"]) == (
            16,
            "The react client calls express over fetch; express checks "
            "passport first.",
        )

    def test_quotes_name_both_skills_within_the_limit(self) -> None:
        rng = random.Random(582)
        words = ["react", "express", "the", "client", "calls", "x" * 40, "and"]
        for _ in range(300):
            lines = [
                rng.choice(["", "- ", "| ", "1. ", "> - "])
                + " ".join(rng.choice(words) for _ in range(rng.randint(1, 60)))
                for _ in range(rng.randint(1, 6))
            ]
            doc = _twice("\n".join(lines) + "\n")
            doc_lines = doc.splitlines()
            for pair in mod.analyze(doc, ["react", "express"])["pairs"]:
                for entry in pair["evidence"]:
                    if entry["kind"] == "list-only":
                        continue
                    quote = entry["unit_excerpt"]
                    assert len(quote) <= 240
                    assert "react" in quote and "express" in quote
                    first = doc_lines[entry["unit_line"] - 1]
                    assert "react" in first or "express" in first


class TestAliases:
    def test_alias_names_the_skill(self) -> None:
        doc = (
            "The API mounts Passport on express.\n\n"
            "express runs Passport again.\n"
        )
        skills = _skills(
            {"name": "oms-passport", "aliases": ["Passport"]}, "express"
        )
        result = mod.analyze(doc, skills)
        assert [(p["a"], p["b"]) for p in result["pairs"]] == [
            ("express", "oms-passport"),
        ]

    def test_multi_word_alias_spans_a_line_break(self) -> None:
        doc = (
            "express routes to React\nRouter views.\n\n"
            "express and React Router again.\n"
        )
        skills = _skills(
            {"name": "react-router", "aliases": ["React Router"]}, "express"
        )
        pair = _pair(mod.analyze(doc, skills), "express", "react-router")
        assert pair["paragraph_count"] == 2
        assert pair["evidence"][0]["unit_excerpt"] == (
            "express routes to React Router views."
        )

    def test_alias_with_non_word_edges(self) -> None:
        doc = "C++ core with a .NET shell.\n\nThe .NET shell calls C++ code.\n"
        skills = _skills(
            {"name": "cpp-core", "aliases": ["C++"]},
            {"name": "dotnet-shell", "aliases": [".NET"]},
        )
        pair = _pair(mod.analyze(doc, skills), "cpp-core", "dotnet-shell")
        assert pair["paragraph_count"] == 2

    def test_alias_keeps_the_word_boundary(self) -> None:
        doc = "reactive streams and express.\n\nreactive again with express.\n"
        skills = _skills({"name": "oms-react", "aliases": ["React"]}, "express")
        assert mod.analyze(doc, skills)["pairs"] == []

    def test_entries_with_one_name_merge(self) -> None:
        skills = _skills(
            "oms-passport", {"name": "oms-passport", "aliases": ["Passport"]}
        )
        doc = "Passport guards express.\n\nPassport and express again.\n"
        result = mod.analyze(doc, [*skills, "express"])
        assert [(p["a"], p["b"]) for p in result["pairs"]] == [
            ("express", "oms-passport"),
        ]

    def test_inventory_keys_are_ignored(self) -> None:
        (skill,) = _skills({
            "name": "express", "path": "express/active/express",
            "exports": ["Router"], "confidence": "T1",
        })
        assert skill == mod.Skill("express", ("express",))


# --------------------------------------------------------------------------
# mentions (#598)
# --------------------------------------------------------------------------

MENTIONS_DOC = """\
# Shop Architecture

## Overview

The shop runs react in the browser.

## Tech Stack

| Layer | Library |
| --- | --- |
| UI | react |
| API | express |

## Request Flow

The react client calls express over fetch; express checks passport first.

```mermaid
graph LR
  express --> redis
```

### Vite build

```python
# Overview
store = prisma.session
```
"""

MENTIONS_SKILLS = [
    "react", "express", "passport", "redis", "prisma", "vite", "lodash",
]


class TestMentions:
    def _run(self) -> dict:
        return mod.mentions(MENTIONS_DOC, MENTIONS_SKILLS)

    def _skill(self, name: str) -> dict:
        return next(s for s in self._run()["skills"] if s["name"] == name)

    def test_scope_sets_partition_the_skills(self) -> None:
        result = self._run()
        assert result["mentioned"] == ["express", "passport", "react", "vite"]
        assert result["fenced_only"] == ["prisma", "redis"]
        assert result["unmentioned"] == ["lodash"]

    def test_per_skill_counts(self) -> None:
        counts = {
            s["name"]: (s["paragraph_count"], s["heading_count"], s["fenced_count"])
            for s in self._run()["skills"]
        }
        assert counts == {
            "express": (2, 0, 1),
            "lodash": (0, 0, 0),
            "passport": (1, 0, 0),
            "prisma": (0, 0, 1),
            "react": (3, 0, 0),
            "redis": (0, 0, 1),
            "vite": (0, 1, 0),
        }

    def test_skills_sorted_by_name(self) -> None:
        names = [s["name"] for s in self._run()["skills"]]
        assert names == sorted(MENTIONS_SKILLS)

    def test_paragraphs_in_document_order_with_no_section_excluded(self) -> None:
        react = self._skill("react")
        # The Overview paragraph counts here, unlike in comention.
        assert [(p["header"], p["line"]) for p in react["paragraphs"]] == [
            ("Overview", 5), ("Tech Stack", 9), ("Request Flow", 16),
        ]
        assert react["paragraphs"][0] == {
            "header": "Overview",
            "excerpt": "The shop runs react in the browser.",
            "line": 5,
        }

    def test_candidates(self) -> None:
        result = self._run()
        got = [
            (c["a"], c["b"], c["comention_count"], c["paragraph_count"])
            for c in result["candidates"]
        ]
        assert got == [
            ("express", "react", 1, 2),
            ("express", "passport", 1, 1),
            ("passport", "react", 1, 1),
        ]
        assert result["list_only_pair_count"] == 0
        assert result["fenced_block_count"] == 2

    def test_fenced_blocks_give_their_line_and_info_string(self) -> None:
        assert self._run()["fenced_blocks"] == [
            {"line": 18, "info": "mermaid"}, {"line": 25, "info": "python"},
        ]
        doc = "~~~\nx\n~~~\n\n```` Mermaid  title=Flow \nx\n````\n"
        assert mod.mentions(doc, [])["fenced_blocks"] == [
            {"line": 1, "info": ""}, {"line": 5, "info": "Mermaid  title=Flow"},
        ]

    def test_candidate_evidence_kinds(self) -> None:
        cand = _pair(self._run(), "express", "react", key="candidates")
        assert [(e["line"], e["kind"]) for e in cand["evidence"]] == [
            (9, "list-only"), (16, "co-mention"),
        ]

    def test_one_paragraph_is_enough(self) -> None:
        result = mod.mentions("express mounts passport.\n", ["express", "passport"])
        assert [(c["a"], c["b"]) for c in result["candidates"]] == [
            ("express", "passport"),
        ]

    def test_pairs_only_listed_together_are_counted_not_emitted(self) -> None:
        doc = "- express\n- passport\n- prisma\n\nexpress mounts passport.\n"
        result = mod.mentions(doc, ["express", "passport", "prisma"])
        assert [(c["a"], c["b"]) for c in result["candidates"]] == [
            ("express", "passport"),
        ]
        assert result["list_only_pair_count"] == 2

    def test_a_lead_in_pair_is_a_candidate(self) -> None:
        doc = "The express server mounts:\n- passport\n- helmet\n"
        result = mod.mentions(doc, ["express", "passport", "helmet"])
        got = [
            (c["a"], c["b"], c["comention_count"], c["lead_in_count"])
            for c in result["candidates"]
        ]
        assert got == [("express", "helmet", 0, 1), ("express", "passport", 0, 1)]
        assert result["list_only_pair_count"] == 1

    def test_candidates_sorted_by_co_mentions_then_lead_ins(self) -> None:
        doc = (
            "- alpha\n- beta\n\n- alpha\n- beta\n\nalpha and beta.\n\n"
            "gamma and delta.\n\ngamma and delta.\n\n"
            "epsilon uses:\n- zeta\n\nepsilon uses:\n- zeta\n\nepsilon uses:\n"
            "- zeta\n"
        )
        result = mod.mentions(
            doc, ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        )
        got = [
            (c["a"], c["b"], c["comention_count"], c["lead_in_count"],
             c["paragraph_count"])
            for c in result["candidates"]
        ]
        assert got == [
            ("delta", "gamma", 2, 0, 2),
            ("alpha", "beta", 1, 0, 3),
            ("epsilon", "zeta", 0, 3, 3),
        ]

    def test_each_occurrence_names_the_longest_term(self) -> None:
        # #598: `react` must not count where the text says `react-dom`.
        doc = "react-dom renders what express serves.\n\n## react-dom setup\n"
        result = mod.mentions(doc, ["react", "react-dom", "express"])
        assert result["mentioned"] == ["express", "react-dom"]
        assert result["unmentioned"] == ["react"]
        assert [(c["a"], c["b"]) for c in result["candidates"]] == [
            ("express", "react-dom"),
        ]
        react_dom = next(s for s in result["skills"] if s["name"] == "react-dom")
        assert react_dom["heading_count"] == 1

    def test_a_name_inside_a_term_no_skill_owns_still_counts(self) -> None:
        result = mod.mentions("react-dom renders it.\n", ["react"])
        assert result["mentioned"] == ["react"]

    def test_fenced_code_is_never_a_candidate_source(self) -> None:
        result = mod.mentions(
            "```\nexpress --> passport\n```\n", ["express", "passport"]
        )
        assert result["candidates"] == []
        assert result["fenced_only"] == ["express", "passport"]

    def test_unclosed_fence_runs_to_the_end(self) -> None:
        doc = "express\n\n```\nnever closed\npassport and express\n"
        result = mod.mentions(doc, ["express", "passport"])
        assert result["mentioned"] == ["express"]
        assert result["fenced_only"] == ["passport"]
        assert result["fenced_block_count"] == 1

    def test_tilde_fence_and_a_longer_closing_fence(self) -> None:
        doc = "~~~\npassport\n~~~~\n\n````\nprisma\n```\n````\nexpress\n"
        result = mod.mentions(doc, ["express", "passport", "prisma"])
        assert result["mentioned"] == ["express"]
        assert result["fenced_only"] == ["passport", "prisma"]
        assert result["fenced_block_count"] == 2

    def test_backtick_info_string_with_a_backtick_is_not_a_fence(self) -> None:
        result = mod.mentions(
            "``` not `a fence`\nexpress and passport\n", ["express", "passport"]
        )
        assert result["mentioned"] == ["express", "passport"]
        assert result["fenced_block_count"] == 0

    def test_word_boundary(self) -> None:
        result = mod.mentions("reactive streams only.\n", ["react"])
        assert result["unmentioned"] == ["react"]

    def test_aliases(self) -> None:
        skills = _skills({"name": "oms-cognee", "aliases": ["Cognee"]}, "qdrant")
        result = mod.mentions("Cognee stores vectors in Qdrant.\n", skills)
        assert result["mentioned"] == ["oms-cognee", "qdrant"]
        assert [(c["a"], c["b"]) for c in result["candidates"]] == [
            ("oms-cognee", "qdrant"),
        ]

    def test_empty_inputs(self) -> None:
        assert mod.mentions("", []) == {
            "skills": [],
            "mentioned": [],
            "fenced_only": [],
            "unmentioned": [],
            "candidates": [],
            "list_only_pair_count": 0,
            "fenced_block_count": 0,
            "fenced_blocks": [],
        }
        assert mod.mentions("", ["react"])["unmentioned"] == ["react"]

    def test_deterministic_and_order_independent(self) -> None:
        r1 = mod.mentions(MENTIONS_DOC, MENTIONS_SKILLS)
        r2 = mod.mentions(MENTIONS_DOC, list(reversed(MENTIONS_SKILLS)))
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# --------------------------------------------------------------------------
# infer (#582, no architecture document)
# --------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _shared(n: int) -> list:
    """n skills that all share one keyword: n*(n-1)/2 candidate pairs."""
    return _skills(*[{"name": f"s{i}", "keywords": ["shared"]} for i in range(n)])


class TestInfer:
    def test_docs_mention(self, tmp_path: Path) -> None:
        doc = _write(
            tmp_path, "passport.md",
            "---\nname: passport\n---\n# Passport\n"
            "Mount it in an Express app.\n\nExpress sessions keep the login.\n",
        )
        result = mod.infer(_skills({"name": "passport", "docs": [doc]}, "express"))
        assert (result["total_pairs"], result["truncated"]) == (1, False)
        pair = result["pairs"][0]
        assert (pair["a"], pair["b"]) == ("express", "passport")
        assert (pair["docs_mention_count"], pair["shared_keyword_count"]) == (1, 0)
        assert pair["evidence"] == [{
            "kind": "docs-mention",
            "documented_by": "passport",
            "doc": doc.replace("\\", "/"),
            "line": 5,
            "line_count": 2,
            "excerpt": "Mount it in an Express app.",
        }]

    def test_both_directions(self, tmp_path: Path) -> None:
        on_express = _write(tmp_path, "passport.md", "Works inside express.\n")
        on_passport = _write(tmp_path, "express.md", "Mount passport here.\n")
        skills = _skills(
            {"name": "passport", "docs": [on_express]},
            {"name": "express", "docs": [on_passport]},
        )
        pair = mod.infer(skills)["pairs"][0]
        assert pair["docs_mention_count"] == 2
        assert [e["documented_by"] for e in pair["evidence"]] == [
            "express", "passport",
        ]

    def test_own_name_is_masked(self, tmp_path: Path) -> None:
        doc = _write(
            tmp_path, "react-dom.md",
            "# react-dom\nreact-dom renders into the DOM.\n"
            "Import react-dom/client.\n",
        )
        skills = _skills({"name": "react-dom", "docs": [doc]}, "react")
        assert mod.infer(skills)["pairs"] == []

    def test_other_name_outside_the_own_name_counts(self, tmp_path: Path) -> None:
        doc = _write(
            tmp_path, "react-dom.md", "react-dom renders what react describes.\n"
        )
        skills = _skills({"name": "react-dom", "docs": [doc]}, "react")
        (evidence,) = mod.infer(skills)["pairs"][0]["evidence"]
        assert (evidence["documented_by"], evidence["line_count"]) == (
            "react-dom", 1,
        )

    def test_each_occurrence_names_the_longest_term(self, tmp_path: Path) -> None:
        doc = _write(
            tmp_path, "vite-plugin.md",
            "Renders with react-dom.\nThen react-dom again.\nreact hooks too.\n",
        )
        skills = _skills(
            {"name": "vite-plugin", "docs": [doc]}, "react", "react-dom"
        )
        pairs = {(p["a"], p["b"]): p for p in mod.infer(skills)["pairs"]}
        # `react-dom` names react-dom only; the standalone `react` names react.
        assert pairs["react-dom", "vite-plugin"]["evidence"][0]["line_count"] == 2
        assert pairs["react", "vite-plugin"]["evidence"][0]["line"] == 3
        assert pairs["react", "vite-plugin"]["evidence"][0]["line_count"] == 1

    def test_case_fold_that_lowercasing_misses(self, tmp_path: Path) -> None:
        # The long s matches `s` case-insensitively but lowercases to itself.
        doc = _write(tmp_path, "express.md", "Mount paſſport first.\n")
        skills = _skills({"name": "express", "docs": [doc]}, "passport")
        (evidence,) = mod.infer(skills)["pairs"][0]["evidence"]
        assert (evidence["documented_by"], evidence["line"]) == ("express", 1)

    def test_aliases_mask_and_name(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "cognee.md", "Cognee stores vectors in Qdrant.\n")
        skills = _skills(
            {"name": "oms-cognee", "aliases": ["Cognee"], "docs": [doc]},
            {"name": "oms-qdrant", "aliases": ["Qdrant"]},
        )
        pair = mod.infer(skills)["pairs"][0]
        assert (pair["a"], pair["b"], pair["docs_mention_count"]) == (
            "oms-cognee", "oms-qdrant", 1,
        )

    def test_first_hit_follows_the_docs_order(self, tmp_path: Path) -> None:
        first = _write(tmp_path, "SKILL.md", "no mention here\n")
        second = _write(tmp_path, "ref.md", "intro\nuses express\nexpress again\n")
        skills = _skills({"name": "passport", "docs": [first, second]}, "express")
        (evidence,) = mod.infer(skills)["pairs"][0]["evidence"]
        assert (evidence["doc"], evidence["line"], evidence["line_count"]) == (
            second.replace("\\", "/"), 2, 2,
        )

    def test_a_doc_listed_twice_counts_once(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "passport.md", "Mount it in an Express app.\n")
        skills = _skills({"name": "passport", "docs": [doc, doc]}, "express")
        (evidence,) = mod.infer(skills)["pairs"][0]["evidence"]
        assert evidence["line_count"] == 1

    def test_shared_keywords(self) -> None:
        skills = _skills(
            {"name": "express", "keywords": ["HTTP", "Middleware", "routing"]},
            {"name": "passport", "keywords": ["auth", " middleware ", "http"]},
        )
        pair = mod.infer(skills)["pairs"][0]
        assert pair["shared_keyword_count"] == 2
        assert pair["evidence"] == [
            {"kind": "shared-keywords", "keywords": ["http", "middleware"]},
        ]

    def test_a_language_keyword_does_not_count(self) -> None:
        skills = _skills(
            {"name": "a", "language": "TypeScript",
             "keywords": ["typescript", "state"]},
            {"name": "b", "language": "typescript", "keywords": ["TypeScript"]},
            {"name": "c", "language": "typescript", "keywords": ["state"]},
        )
        result = mod.infer(skills)
        assert [(p["a"], p["b"]) for p in result["pairs"]] == [("a", "c")]
        assert result["pairs"][0]["evidence"][0]["keywords"] == ["state"]
        assert result["language_only_pair_count"] == 2

    def test_a_listed_language_sets_its_keyword_aside(self) -> None:
        skills = _skills(
            {"name": "stack", "language": ["TypeScript", "Python"],
             "keywords": ["python", "etl"]},
            {"name": "loader", "keywords": ["python", "etl"]},
        )
        (pair,) = mod.infer(skills)["pairs"]
        assert pair["evidence"] == [
            {"kind": "shared-keywords", "keywords": ["etl"]},
        ]

    def test_a_shared_language_alone_never_makes_a_pair(self) -> None:
        # #582: with no architecture document, 12 TypeScript skills gave 66
        # pairs from the shared language alone.
        skills = _skills(
            *[{"name": f"lib-{i:02d}", "language": "typescript"} for i in range(12)]
        )
        result = mod.infer(skills)
        assert (result["pairs"], result["total_pairs"]) == ([], 0)
        assert result["language_only_pair_count"] == 66

    def test_language_only_pairs_share_any_listed_language(self) -> None:
        skills = _skills(
            {"name": "stack", "language": ["javascript", "python"]},
            {"name": "py-lib", "language": "python"},
            {"name": "go-lib", "language": "go"},
            {"name": "bare"},
        )
        result = mod.infer(skills)
        assert (result["pairs"], result["language_only_pair_count"]) == ([], 1)

    def test_different_languages_are_not_language_only(self) -> None:
        skills = _skills(
            {"name": "a", "language": "python"}, {"name": "b", "language": "rust"}
        )
        assert mod.infer(skills)["language_only_pair_count"] == 0

    def test_entries_with_one_name_join_their_languages(self) -> None:
        skills = _skills(
            {"name": "x", "language": "go"}, {"name": "x", "language": ["rust"]},
            {"name": "y", "language": "rust"}, {"name": "z", "language": "go"},
        )
        result = mod.infer(skills)
        assert result["language_only_pair_count"] == 2

    def test_ordering(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "delta.md", "uses zeta\n")
        skills = _skills(
            {"name": "alpha", "keywords": ["k1"]},
            {"name": "beta", "keywords": ["k1", "k2"]},
            {"name": "gamma", "keywords": ["k1", "k2"]},
            {"name": "delta", "docs": [doc]},
            "zeta",
        )
        got = [(p["a"], p["b"]) for p in mod.infer(skills)["pairs"]]
        assert got == [
            ("delta", "zeta"), ("beta", "gamma"), ("alpha", "beta"),
            ("alpha", "gamma"),
        ]

    def test_default_top_k_is_20(self) -> None:
        result = mod.infer(_shared(8))
        assert (len(result["pairs"]), result["truncated"]) == (20, True)
        assert result["total_pairs"] == 28

    def test_top_k(self) -> None:
        result = mod.infer(_shared(8), top_k=5)
        assert [(p["a"], p["b"]) for p in result["pairs"]] == [
            ("s0", "s1"), ("s0", "s2"), ("s0", "s3"), ("s0", "s4"), ("s0", "s5"),
        ]
        assert (result["truncated"], result["total_pairs"]) == (True, 28)
        assert mod.infer(_shared(8), top_k=28)["truncated"] is False
        assert mod.infer(_shared(8), top_k=0)["pairs"] == []

    def test_empty_input(self) -> None:
        assert mod.infer([]) == {
            "pairs": [],
            "truncated": False,
            "total_pairs": 0,
            "language_only_pair_count": 0,
        }

    def test_missing_docs_file_raises(self, tmp_path: Path) -> None:
        skills = _skills({"name": "a", "docs": [str(tmp_path / "nope.md")]}, "b")
        with pytest.raises(mod.UserError, match="docs file of skill 'a' not found"):
            mod.infer(skills)

    def test_undecodable_docs_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "binary.md"
        path.write_bytes(b"\xff\xfe\x00 not utf-8")
        skills = _skills({"name": "a", "docs": [str(path)]}, "b")
        with pytest.raises(
            mod.UserError, match="failed to read docs file of skill 'a'"
        ):
            mod.infer(skills)

    def test_only_infer_reads_docs(self, tmp_path: Path) -> None:
        skills = _skills({"name": "a", "docs": [str(tmp_path / "nope.md")]}, "b")
        assert mod.analyze("a and b.\n\na and b.\n", skills)["pairs"][0]["b"] == "b"
        assert mod.mentions("a and b.\n", skills)["mentioned"] == ["a", "b"]

    def test_deterministic_and_order_independent(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "delta.md", "uses zeta and alpha\n")
        entries = [
            {"name": "alpha", "keywords": ["k1"], "language": "go"},
            {"name": "beta", "keywords": ["k1", "k2"], "language": ["go", "c"]},
            {"name": "delta", "docs": [doc], "language": "go"},
            {"name": "zeta", "language": "go"},
        ]
        r1 = mod.infer(_skills(*entries))
        r2 = mod.infer(_skills(*reversed(entries)))
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


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


class TestReadMarkdown:
    def test_units(self) -> None:
        doc = (
            "# T\n\nLead-in line\n- item one\n  continued\n- item two\n"
            "| row |\n```\ncode\n```\n> - quoted item\n"
        )
        (para,) = mod.read_markdown(doc, skip_fenced=False).paragraphs
        assert [(u.line, u.text, u.prose) for u in para.units] == [
            (3, "Lead-in line", True),
            (4, "- item one\n  continued", False),
            (6, "- item two", False),
            (7, "| row |", False),
            (8, "```", False),
            (9, "code", False),
            (10, "```", False),
            (11, "> - quoted item", False),
        ]

    def test_paragraph_first_line(self) -> None:
        doc = "# T\n\nfirst\nsecond\n\n\nthird\n"
        paras = mod.read_markdown(doc, skip_fenced=False).paragraphs
        assert [(p.line, p.text) for p in paras] == [
            (3, "first\nsecond"), (7, "third"),
        ]

    def test_skip_fenced_sets_blocks_apart(self) -> None:
        doc = "before\n```\n# not a heading\n\ninside\n```\nafter\n"
        md = mod.read_markdown(doc, skip_fenced=True)
        assert [(p.line, p.text) for p in md.paragraphs] == [
            (1, "before"), (7, "after"),
        ]
        assert md.headings == []
        assert md.fenced == [mod.Fence(2, "", "# not a heading\n\ninside")]

    def test_without_skip_fenced_a_hash_line_in_a_fence_is_a_header(self) -> None:
        # comention keeps this reading so that its pairs stay the ones
        # earlier releases emitted.
        doc = "before\n```\n# Overview\ninside\n```\n"
        md = mod.read_markdown(doc, skip_fenced=False)
        assert md.headings == ["Overview"]
        assert [(p.header, p.text) for p in md.paragraphs] == [
            (None, "before\n```"), ("Overview", "inside\n```"),
        ]
        assert md.fenced == []

    def test_headings_of_every_level_are_recorded(self) -> None:
        md = mod.read_markdown(
            "# One\n### Three ###\n###### Six\n#no\n", skip_fenced=True
        )
        assert md.headings == ["One", "Three", "Six"]
        assert [p.text for p in md.paragraphs] == ["#no"]

    @pytest.mark.parametrize(
        ("row", "table"),
        [
            ("--- | ---", True),
            ("| :-: | --- |", True),
            (":--|--:", True),
            ("  | --- |  ", True),
            ("--- | x", False),
            ("-- - | ---", False),
            ("x | ---", False),
        ],
    )
    def test_gfm_delimiter_row(self, row: str, table: bool) -> None:
        (para,) = mod.read_markdown(
            f"a | b\n{row}\nc d\n", skip_fenced=False
        ).paragraphs
        # A delimiter row makes a table of the lines around it.
        assert [u.prose for u in para.units] == (
            [False, False, False] if table else [True]
        )

    def test_long_runs_of_spaces_read_in_linear_time(self) -> None:
        # The table delimiter and closing-hash patterns once backtracked
        # quadratically: 64,000 spaces took over a minute.
        spaces = " " * 64_000
        doc = f"# a{spaces}b ##\n\na | b\n{spaces}|x\n"
        start = time.perf_counter()
        md = mod.read_markdown(doc, skip_fenced=False)
        assert time.perf_counter() - start < 5
        assert md.headings == [f"a{spaces}b"]
        (para,) = md.paragraphs
        assert [(u.line, u.prose) for u in para.units] == [(3, True), (4, False)]

    @pytest.mark.parametrize(
        ("header", "text"),
        [
            ("Overview ##", "Overview"),
            ("Data Flow #\t", "Data Flow"),
            ("Tech  Stack", "Tech  Stack"),
            ("##", ""),
        ],
    )
    def test_closing_hashes(self, header: str, text: str) -> None:
        md = mod.read_markdown(f"## {header}\n", skip_fenced=True)
        assert md.headings == [text]


# --------------------------------------------------------------------------
# parse_skills
# --------------------------------------------------------------------------


class TestParseSkills:
    def test_valid(self) -> None:
        skills = mod.parse_skills('["a", "b"]')
        assert [s.name for s in skills] == ["a", "b"]
        assert [s.terms for s in skills] == [("a",), ("b",)]

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(mod.UserError, match="malformed JSON"):
            mod.parse_skills("{not json")

    def test_not_array_raises(self) -> None:
        with pytest.raises(mod.UserError, match="must be a JSON array"):
            mod.parse_skills('{"a": 1}')

    def test_non_string_entry_raises(self) -> None:
        with pytest.raises(mod.UserError, match="non-empty string"):
            mod.parse_skills('["a", 42]')

    def test_empty_string_entry_raises(self) -> None:
        with pytest.raises(mod.UserError, match="non-empty string"):
            mod.parse_skills('["a", ""]')


class TestParseSkillObjects:
    def test_object_with_aliases(self) -> None:
        (skill,) = _skills(
            {"name": "oms-cognee", "aliases": ["Cognee", " cognee "]}
        )
        # Aliases are trimmed, and a repeat that differs only in case goes.
        assert skill == mod.Skill("oms-cognee", ("oms-cognee", "Cognee"))

    def test_infer_fields_are_normalised(self) -> None:
        (skill,) = _skills({
            "name": "x",
            "keywords": ["HTTP  Server", "http server", "Auth"],
            "language": " TypeScript ",
            "docs": ["docs/x.md", "docs/y.md", "docs/x.md"],
        })
        assert skill.keywords == ("auth", "http server")
        assert skill.languages == ("typescript",)
        assert skill.docs == ("docs/x.md", "docs/y.md")

    def test_a_language_array(self) -> None:
        (skill,) = _skills(
            {"name": "x", "language": ["TypeScript", " python ", "typescript"]}
        )
        assert skill.languages == ("python", "typescript")

    @pytest.mark.parametrize("language", [None, []])
    def test_null_or_empty_language_is_no_language(self, language: object) -> None:
        (skill,) = _skills({"name": "x", "language": language})
        assert skill.languages == ()

    def test_whitespace_only_name_raises(self) -> None:
        with pytest.raises(mod.UserError, match="non-empty string"):
            mod.parse_skills('["   "]')

    def test_missing_name_raises(self) -> None:
        with pytest.raises(
            mod.UserError, match=r"--skills\[0\]\.name must be a non-empty string"
        ):
            _skills({"aliases": ["x"]})

    def test_aliases_not_an_array_raises(self) -> None:
        with pytest.raises(
            mod.UserError, match=r"--skills\[0\]\.aliases must be an array"
        ):
            _skills({"name": "x", "aliases": "X"})

    def test_blank_alias_raises(self) -> None:
        with pytest.raises(
            mod.UserError,
            match=r"--skills\[1\]\.aliases\[1\] must be a non-empty string",
        ):
            _skills("y", {"name": "x", "aliases": ["X", " "]})

    def test_keyword_not_a_string_raises(self) -> None:
        with pytest.raises(mod.UserError, match=r"--skills\[0\]\.keywords\[0\]"):
            _skills({"name": "x", "keywords": [3]})

    def test_docs_not_an_array_raises(self) -> None:
        with pytest.raises(
            mod.UserError, match=r"--skills\[0\]\.docs must be an array"
        ):
            _skills({"name": "x", "docs": "x.md"})

    @pytest.mark.parametrize("language", [3, "  ", ["go", ""], ["go", 3], {}])
    def test_malformed_language_raises(self, language: object) -> None:
        with pytest.raises(
            mod.UserError,
            match=r"--skills\[0\]\.language must be a non-empty string or an "
            r"array of non-empty strings",
        ):
            _skills({"name": "x", "language": language})


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

    def test_comention_kinds_and_alias_objects(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(STACK_DOC.replace("passport", "Passport"), encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", "-",
            stdin_text=json.dumps([
                "react", "express",
                {"name": "oms-passport", "aliases": ["Passport"]},
            ]),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        got = [(p["a"], p["b"], p["comention_count"]) for p in payload["pairs"]]
        assert got == [
            ("express", "react", 1), ("express", "oms-passport", 0),
            ("oms-passport", "react", 0),
        ]

    def test_comention_verbose_summary(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_text(FIXTURE_DOC, encoding="utf-8")
        result = _run_cli(
            "comention", "--doc", str(doc), "--skills", "-", "--verbose",
            stdin_text=json.dumps(FIXTURE_SKILLS),
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr.strip() == (
            "analyzed 4 distinct skill names; 1 qualifying pairs; "
            "1 excluded sections"
        )


class TestMentionsCli:
    def _files(self, tmp_path: Path) -> tuple[Path, Path]:
        doc = tmp_path / "arch.md"
        doc.write_text(MENTIONS_DOC, encoding="utf-8")
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps(MENTIONS_SKILLS), encoding="utf-8")
        return doc, skills

    def test_from_files(self, tmp_path: Path) -> None:
        doc, skills = self._files(tmp_path)
        result = _run_cli("mentions", "--doc", str(doc), "--skills", str(skills))
        assert result.returncode == 0, result.stderr
        expected = mod.mentions(MENTIONS_DOC, MENTIONS_SKILLS)
        assert json.loads(result.stdout) == expected

    def test_skills_from_stdin(self, tmp_path: Path) -> None:
        doc, _ = self._files(tmp_path)
        result = _run_cli(
            "mentions", "--doc", str(doc), "--skills", "-",
            stdin_text=json.dumps(MENTIONS_SKILLS),
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["unmentioned"] == ["lodash"]

    def test_doc_from_stdin(self, tmp_path: Path) -> None:
        _, skills = self._files(tmp_path)
        result = _run_cli(
            "mentions", "--doc", "-", "--skills", str(skills),
            stdin_text=MENTIONS_DOC,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["fenced_only"] == ["prisma", "redis"]

    def test_both_stdin_exits_1(self) -> None:
        result = _run_cli("mentions", "--doc", "-", "--skills", "-", stdin_text="x")
        assert result.returncode == 1
        assert "both read from stdin" in result.stderr

    def test_malformed_skills_exits_1(self, tmp_path: Path) -> None:
        doc, _ = self._files(tmp_path)
        result = _run_cli(
            "mentions", "--doc", str(doc), "--skills", "-",
            stdin_text='[{"aliases": ["x"]}]',
        )
        assert result.returncode == 1
        assert "--skills[0].name must be a non-empty string" in result.stderr

    def test_non_utf8_doc_exits_1(self, tmp_path: Path) -> None:
        doc = tmp_path / "arch.md"
        doc.write_bytes(b"\xffnot utf-8\n")
        result = _run_cli(
            "mentions", "--doc", str(doc), "--skills", "-",
            stdin_text='["react"]',
        )
        assert result.returncode == 1
        assert "failed to read --doc file" in result.stderr

    def test_non_utf8_skills_file_exits_1(self, tmp_path: Path) -> None:
        doc, _ = self._files(tmp_path)
        skills = tmp_path / "skills.json"
        skills.write_bytes(b'\xff["react"]')
        result = _run_cli("mentions", "--doc", str(doc), "--skills", str(skills))
        assert result.returncode == 1
        assert "failed to read --skills file" in result.stderr

    def test_verbose_summary(self, tmp_path: Path) -> None:
        doc, skills = self._files(tmp_path)
        result = _run_cli(
            "mentions", "--doc", str(doc), "--skills", str(skills), "--verbose"
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr.strip() == (
            "analyzed 7 distinct skill names; 4 mentioned, "
            "2 only in fenced code, 1 unmentioned; 3 candidate pairs; "
            "0 list-only pairs"
        )

    def test_reproducible_output(self, tmp_path: Path) -> None:
        doc, skills = self._files(tmp_path)
        r1 = _run_cli("mentions", "--doc", str(doc), "--skills", str(skills))
        r2 = _run_cli("mentions", "--doc", str(doc), "--skills", str(skills))
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout


class TestInferCli:
    def _skills_file(self, tmp_path: Path) -> Path:
        doc = _write(tmp_path, "passport.md", "Mount it in an Express app.\n")
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps([
            {"name": "passport", "language": "javascript", "docs": [doc]},
            {"name": "express", "language": "javascript"},
            {"name": "lodash", "language": "javascript"},
        ]), encoding="utf-8")
        return skills

    def test_from_file(self, tmp_path: Path) -> None:
        result = _run_cli("infer", "--skills", str(self._skills_file(tmp_path)))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [(p["a"], p["b"]) for p in payload["pairs"]] == [
            ("express", "passport"),
        ]
        assert payload["language_only_pair_count"] == 2
        assert payload["truncated"] is False

    def test_from_stdin(self, tmp_path: Path) -> None:
        skills = self._skills_file(tmp_path)
        result = _run_cli(
            "infer", "--skills", "-", stdin_text=skills.read_text(encoding="utf-8")
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["total_pairs"] == 1

    def test_top_k_flag(self) -> None:
        entries = [{"name": f"s{i}", "keywords": ["shared"]} for i in range(4)]
        result = _run_cli(
            "infer", "--skills", "-", "--top-k", "2",
            stdin_text=json.dumps(entries),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (len(payload["pairs"]), payload["truncated"]) == (2, True)
        assert payload["total_pairs"] == 6

    def test_negative_top_k_exits_1(self) -> None:
        result = _run_cli(
            "infer", "--skills", "-", "--top-k", "-1", stdin_text="[]"
        )
        assert result.returncode == 1
        assert "--top-k must be >= 0" in result.stderr

    def test_missing_docs_file_exits_1(self, tmp_path: Path) -> None:
        entries = [{"name": "a", "docs": [str(tmp_path / "nope.md")]}, "b"]
        result = _run_cli("infer", "--skills", "-", stdin_text=json.dumps(entries))
        assert result.returncode == 1
        assert "docs file of skill 'a' not found" in result.stderr

    def test_missing_skills_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("infer", "--skills", str(tmp_path / "nope.json"))
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_verbose_summary(self, tmp_path: Path) -> None:
        result = _run_cli(
            "infer", "--skills", str(self._skills_file(tmp_path)), "--verbose"
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr.strip() == (
            "analyzed 3 distinct skill names; 1 candidate pairs, 1 emitted; "
            "2 language-only pairs"
        )

    def test_reproducible_output(self, tmp_path: Path) -> None:
        skills = self._skills_file(tmp_path)
        r1 = _run_cli("infer", "--skills", str(skills))
        r2 = _run_cli("infer", "--skills", str(skills))
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout


def _enumerated(name: str, language: object, **fields: object) -> dict:
    """A skills[] entry shaped as skf-enumerate-stack-skills.py emits it."""
    return {
        "name": name, "path": f"{name}/active/{name}", "exports": ["main"],
        "exports_source": "metadata", "confidence": "T1",
        "evidence_tier": "T1", "metadata_hash": "sha256:" + "0" * 64,
        "skill_type": "single", "language": language,
        "confidence_tier": "Forge", "exports_documented": 1,
        "metadata_schema_version": "1.3", "source_repo": None,
        "source_repo_basename": None, "source_root": None,
        "source_root_basename": None, **fields,
    }


# An enumerate roster: a stack lists its libraries' languages, and a skill
# whose metadata.json has no language carries null.
ENUMERATED_SKILLS = [
    _enumerated("express", "javascript"),
    _enumerated("react", "javascript"),
    _enumerated(
        "web-stack", ["javascript", "python"],
        skill_type="stack", confidence_tier="T1",
    ),
    _enumerated("lodash", None),
]

ENUMERATED_DOC = "## Flow\n\nreact calls express.\n\nreact and express again.\n"


class TestInventoryEntriesCli:
    """--skills takes skf-enumerate-stack-skills.py `skills[]` entries as
    they are, in every subcommand."""

    def _skills_file(self, tmp_path: Path) -> str:
        path = tmp_path / "skills.json"
        path.write_text(json.dumps(ENUMERATED_SKILLS), encoding="utf-8")
        return str(path)

    def test_comention(self, tmp_path: Path) -> None:
        result = _run_cli(
            "comention", "--doc", "-", "--skills", self._skills_file(tmp_path),
            stdin_text=ENUMERATED_DOC,
        )
        assert result.returncode == 0, result.stderr
        pairs = json.loads(result.stdout)["pairs"]
        assert [(p["a"], p["b"], p["comention_count"]) for p in pairs] == [
            ("express", "react", 2),
        ]

    def test_mentions(self, tmp_path: Path) -> None:
        result = _run_cli(
            "mentions", "--doc", "-", "--skills", self._skills_file(tmp_path),
            stdin_text=ENUMERATED_DOC,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["mentioned"] == ["express", "react"]
        assert payload["unmentioned"] == ["lodash", "web-stack"]

    def test_infer(self, tmp_path: Path) -> None:
        result = _run_cli("infer", "--skills", self._skills_file(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        # express, react and web-stack share javascript; lodash has none.
        assert (payload["pairs"], payload["language_only_pair_count"]) == ([], 3)
