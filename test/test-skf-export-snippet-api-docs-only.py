#!/usr/bin/env python3
"""The api ranking of a docs-only skill and of a reference app.

- #1251: Export Skill's api ranking (generate-snippet.md §3b item 2) took a
  name only when metadata.json `exports` listed it, and took `exports` as its
  third source. A docs-only skill's `exports` names its documented items,
  often by an id such as `page#concept-0`, and a reference app's is empty by
  design, so the ranking dropped every prior `|api:` name and every table row
  name, then filled the line with those ids or left it out. §3b item 1 now
  reads metadata.json `scope_type`, and for a `docs-only` or `reference-app`
  skill item 2 ranks only the `prior_api` names and the rows, with no
  `exports` check and no name from `exports`. Both scope types are the brief
  schema's, which create-skill copies into metadata.json `scope_type`. Update
  Skill's headline-exports trigger, which reuses the ranking, says no name of
  such a skill leaves `exports`.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
FRAGMENT = REPO / "changes" / "export-snippet-api-docs-only.yaml"
SNIPPET = SRC / "skf-export-skill" / "references" / "generate-snippet.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
BRIEF_SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skill-brief.v1.json"

ITEM_1 = "1. Read metadata.json for `version`, `scope_type` and the `exports` array"
SCOPED = ("A skill whose metadata.json `scope_type` is `docs-only` or `reference-app` ranks only the `prior_api` names "
          "and the rows, since its `exports` is not a list of API names: a docs-only skill's `exports` names its "
          "documented items, often by an id such as `page#concept-0`, and a reference app's is empty by design. Such a "
          "skill reads a row's name as the next sentence says, but matches none to `exports`.")
TAKE = ("Take each name once, only when metadata.json `exports` lists it (any name, for a `docs-only` or "
        "`reference-app` skill), and never one the current SKILL.md marks deprecated or removed")
TRIGGER = ("No name of a `docs-only` or `reference-app` skill leaves `exports`, since `generate-snippet.md` §3b does not "
           "check such a skill's names against it.")


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


def _single() -> str:
    return _section(SNIPPET.read_text(encoding="utf-8"), "#### 3b. Single Skills", "#### 3c. ")


def test_item_1_reads_the_scope_type():
    """#1251: §3b reads metadata.json `scope_type` beside `version` and `exports`."""
    assert _line(_single(), "1. ") == ITEM_1


def test_a_docs_only_or_reference_app_skill_ranks_without_exports():
    """#1251: such a skill ranks only the prior names and the rows, reads a row's name as any skill does, and keeps
    any name of them. With neither, nothing is ranked and the `|api:` line is omitted, never filled from `exports`."""
    single = _single()
    rank = _line(single, "2. ")
    parts = ("then the metadata.json `exports`, in order.", SCOPED, "Match a row's name to `exports`", TAKE)
    assert all(rank.count(part) == 1 for part in parts)
    assert [rank.index(part) for part in parts] == sorted(rank.index(part) for part in parts)
    assert "filling `api` from the names ranked above (all of them when fewer than the limit; omit the line when " \
           "there are none)" in single


def test_both_scope_types_are_the_briefs():
    """#1251: the two scope types §3b names are values of the brief's `scope.type`."""
    schema = json.loads(BRIEF_SCHEMA.read_text(encoding="utf-8"))
    types = schema["properties"]["scope"]["properties"]["type"]["enum"]
    assert "docs-only" in types and "reference-app" in types


def test_update_skill_reads_no_such_name_as_gone_from_exports():
    """#1251: the headline-exports trigger never fires because a name of such a skill left `exports`."""
    five = _section(UPDATE_WRITE.read_text(encoding="utf-8"), "### 5. Regenerate context-snippet.md", None)
    headline = _line(five, "- **Headline exports changed**")
    assert headline.endswith("waits for the next export. " + TRIGGER)


def test_the_fragment_says_to_delete_a_line_an_earlier_export_filled_with_ids():
    """#1251: ids an earlier export wrote into the `|api:` line stay as prior names, so the fragment says to
    delete the line and export again, as the create-skill fragment for #1268 says."""
    fragment = yaml.safe_load(FRAGMENT.read_text(encoding="utf-8"))
    assert (fragment["type"], fragment["scope"], fragment["issues"]) == \
        ("fixed", "skf-export-skill, skf-update-skill", [1251])
    summary = fragment["summary"]
    for claim in ("For a skill whose metadata.json `scope_type` is `docs-only` or `reference-app`, the ranking now "
                  "takes the prior line's names, then the table's rows, and never checks them against `exports` or "
                  "takes a name from it.",
                  "It still leaves out a name SKILL.md marks deprecated or removed.",
                  "A line an earlier export already filled with item ids keeps them: delete the `|api:` line from the "
                  "`context-snippet.md` of the skill's active version, then export the skill again, which takes the "
                  "line's names from the table."):
        assert claim in summary, claim
    assert "\u2014" not in summary and "\u00a7" not in summary
