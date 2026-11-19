#!/usr/bin/env python3
"""The first `|api:` line of a docs-only skill.

- #1268: Create Skill's compile.md §3 took the `|api:` names from the top 10
  exports of the extraction inventory. A docs-only inventory holds no export
  and no `top_exports`; its only names are the `t3_items` names, which
  metadata.json `exports` also lists and which are often ids such as
  `page#concept-0`. Since #1259 Export Skill keeps a docs-only skill's prior
  `|api:` names first on every export and Update Skill never reads one as
  stale, so ids written here stayed ahead of the table's real API names. For
  a `docs-only` brief §3 now takes the first 10 names of the
  `## Key API Summary` rows §2 assembled, read with the words Export Skill
  §3b item 2 uses, marks a name `()` only when the provenance map gives it a
  function kind, never takes a `t3_items` name the table does not give, and
  omits the line when the table gives no name. A source brief's line is
  unchanged.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
FRAGMENT = REPO / "changes" / "create-snippet-api-docs-only.yaml"
COMPILE = SRC / "skf-create-skill" / "references" / "compile.md"
SNIPPET = SRC / "skf-export-skill" / "references" / "generate-snippet.md"

CODE = "- **api**: Top 10 exports from extraction inventory, append `()` to function names. "
DOCS_ONLY = ("For a `docs-only` brief (`source_type: \"docs-only\"`), take instead the first 10 names of the rows of the "
             "`## Key API Summary` table §2 assembled, in row order, each once: read a row's name ")
READING = ("without backticks, `()`, a module qualifier (`cognee.add` is `add`) or generic parameters "
           "(`Meta<T = Args>` is `Meta`), and split a cell that names several on `/`")
KIND = ("Such a name takes `()` when its `export_type` in the provenance map §1c staged is a function, and is written "
        "bare for any other kind or when the map gives no kind for it.")
NEVER = ("Never take a `t3_items` name the table does not give (an item id such as `page#concept-0`), and omit the "
         "line when the table gives no name.")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` up to marker `end` (or the end of the text)."""
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _line(text: str, start: str) -> str:
    """The one line of `text` that starts with `start`."""
    [line] = [line for line in text.split("\n") if line.startswith(start)]
    return line


def _api_line() -> str:
    snippet = _section(COMPILE.read_text(encoding="utf-8"), "### 3. Build context-snippet.md Content", "### 4. ")
    return _line(snippet, "- **api**:")


def test_a_docs_only_brief_takes_the_key_api_summary_rows():
    """#1268: the code-skill clause stays word for word; a docs-only brief takes the table's row names, each once,
    with `()` only for a function kind the provenance map gives, and never a `t3_items` name the table does not."""
    assert _api_line() == CODE + DOCS_ONLY + READING + ". " + KIND + " " + NEVER


def test_the_row_name_reading_is_export_skills():
    """#1268: Create Skill reads a row's name with the words Export Skill §3b item 2 uses, so the first export
    finds the names the first line wrote and adds no second spelling of one."""
    single = _section(SNIPPET.read_text(encoding="utf-8"), "#### 3b. Single Skills", "#### 3c. ")
    rank = _line(single, "2. ")
    assert rank.count(READING) == 1
    assert _api_line().count(READING) == 1


def test_the_fragment_says_to_edit_a_line_an_earlier_run_filled_with_ids():
    """#1268: ids an earlier run wrote into the `|api:` line stay as prior names on every export, so the fragment
    says to delete the line by hand and export again."""
    fragment = yaml.safe_load(FRAGMENT.read_text(encoding="utf-8"))
    assert (fragment["type"], fragment["scope"], fragment["issues"]) == ("fixed", "skf-create-skill", [1268])
    summary = fragment["summary"]
    for claim in ("Create Skill now writes the first `|api:` line of a docs-only skill from the names of its "
                  "`## Key API Summary` table, in row order.",
                  "A line an earlier run already filled with item ids keeps them: delete the `|api:` line from the "
                  "`context-snippet.md` of the skill's active version, then export the skill again, which takes "
                  "the line's names from the table."):
        assert claim in summary, claim
    assert "\u2014" not in summary and "\u00a7" not in summary
