#!/usr/bin/env python3
"""Unit tests for src/skf-create-skill/scripts/scan-doc-rot.py (step-doc-rot.md §2).

Covers the case-insensitive substring scan against the 13-row keyword table,
the per-(line, pattern) candidate record shape (`candidate_category`, never a
verdict), the `## Migration & Deprecation Warnings` and frontmatter positional
exclusions, duplicate collapse and the candidate cap the feeders share (the
compiled SKILL.md's own lines last), missing/empty-feeder skipping, and the
subprocess CLI (exit codes + JSON-on-stdout).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-create-skill"
    / "scripts"
    / "scan-doc-rot.py"
)

spec = importlib.util.spec_from_file_location("scan_doc_rot", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

scan_text = mod.scan_text
migration_section_range = mod.migration_section_range
apply_migration_exclusion = mod.apply_migration_exclusion
frontmatter_range = mod.frontmatter_range
apply_frontmatter_exclusion = mod.apply_frontmatter_exclusion
collapse_duplicates = mod.collapse_duplicates
apply_cap = mod.apply_cap
scan_files = mod.scan_files
PATTERN_TABLE = mod.PATTERN_TABLE
DEFAULT_MAX_CANDIDATES = mod.DEFAULT_MAX_CANDIDATES


# --------------------------------------------------------------------------
# Pattern table contract
# --------------------------------------------------------------------------


def test_pattern_table_has_13_rows():
    assert len(PATTERN_TABLE) == 13


def test_step_doc_does_not_restate_the_pattern_table():
    """The keyword table lives only in the script: step-doc-rot.md §2 judges the
    candidates the script returns and never needs the rows, so it keeps no copy
    to hold in lockstep."""
    step = (SCRIPT_PATH.parent.parent / "references" / "step-doc-rot.md").read_text(
        encoding="utf-8"
    )
    assert "| Pattern |" not in step
    assert "PATTERN_TABLE" not in step


# --------------------------------------------------------------------------
# scan_text — case-insensitive substring, per-(line, pattern) records
# --------------------------------------------------------------------------


def test_case_insensitive_match():
    matches = scan_text("This API was DEPRECATED last year.", "f.md")
    patterns = {m["pattern"] for m in matches}
    assert "deprecated" in patterns


def test_records_full_field_shape():
    matches = scan_text("foo removed in v2", "f.md")
    m = next(x for x in matches if x["pattern"] == "removed in")
    assert m == {
        "source": "f.md",
        "pattern": "removed in",
        "candidate_category": "Removal",
        "context_line": "foo removed in v2",
        "line_number": 1,
    }


@pytest.mark.parametrize(
    "line,candidate_category",
    [
        ("- No breaking changes in this release.", "Breaking change"),
        ("- Non-breaking: `parse()` accepts a Path.", "Breaking change"),
        ("- Fixed a bug where the deprecated-warning banner was shown twice.", "Deprecation"),
        ("- Support for Python 2 was removed in 0.3.", "Removal"),
        ("- [x] Bug fix (non-breaking change which fixes an issue)", "Breaking change"),
    ],
    ids=["negation", "non-breaking", "bug-fix", "old-history", "pr-template-checkbox"],
)
def test_keyword_lines_are_candidates_not_corrections(line, candidate_category):
    """#582: a negated, passing, bug-fix, historical or checkbox line holds a
    keyword, so the scan proposes it, labelled only as a candidate. Deciding
    that it is no correction is step 5c's judgment pass, not the script's."""
    matches = scan_text(line, "changelog.md")
    assert matches
    assert {m["candidate_category"] for m in matches} == {candidate_category}
    assert all("category" not in m for m in matches)


def test_line_numbers_are_1_indexed():
    text = "clean\nclean\nrenamed to bar\n"
    m = next(x for x in scan_text(text, "f.md") if x["pattern"] == "renamed to")
    assert m["line_number"] == 3


def test_at_deprecated_and_deprecated_both_fire_on_same_line():
    """Overlapping table patterns each record their own hit (13-row contract)."""
    matches = scan_text("`@deprecated` marks it", "f.md")
    patterns = [m["pattern"] for m in matches]
    assert "deprecated" in patterns
    assert "@deprecated" in patterns


def test_no_false_positive_on_clean_text():
    assert scan_text("A perfectly current stable API.\nNothing to see.", "f.md") == []


def test_context_line_is_stripped():
    m = scan_text("   breaking change ahead   ", "f.md")[0]
    assert m["context_line"] == "breaking change ahead"


# --------------------------------------------------------------------------
# Migration & Deprecation Warnings exclusion (§4b guard)
# --------------------------------------------------------------------------


SKILL_MD = (
    "# Skill\n"
    "\n"
    "## API\n"
    "foo was removed in v2\n"  # line 4 — OUTSIDE migration section → kept
    "\n"
    "## Migration & Deprecation Warnings\n"  # line 6 — heading
    "- bar deprecated since v3\n"  # line 7 — INSIDE → excluded
    "- baz superseded by qux\n"  # line 8 — INSIDE → excluded
    "\n"
    "## Footer\n"  # line 10 — closes the section
    "old note renamed to new\n"  # line 11 — OUTSIDE → kept
)


def test_migration_section_range():
    assert migration_section_range(SKILL_MD) == (6, 10)


def test_migration_range_none_when_absent():
    assert migration_section_range("# Skill\n## API\nfoo deprecated\n") is None


def test_exclusion_drops_only_in_section_matches():
    matches = scan_text(SKILL_MD, "SKILL.md")
    kept, dropped = apply_migration_exclusion(matches, "SKILL.md", SKILL_MD)
    kept_lines = {m["line_number"] for m in kept}
    assert 4 in kept_lines  # "removed in" before the section
    assert 11 in kept_lines  # "renamed to" after the section
    assert 7 not in kept_lines  # "deprecated" inside → dropped
    assert 8 not in kept_lines  # "superseded by" inside → dropped
    assert dropped == 2


def test_exclusion_only_applies_to_skill_md_source():
    """An identical line from a NON-skill-md feeder is never excluded."""
    other = scan_text("bar deprecated since v3", "evidence-report.md")
    kept, dropped = apply_migration_exclusion(other, "SKILL.md", SKILL_MD)
    assert dropped == 0
    assert len(kept) == len(other)


def test_subsection_does_not_close_migration_window():
    text = (
        "## Migration & Deprecation Warnings\n"  # 1
        "### Details\n"  # 2 — ### must NOT close the section
        "old renamed to new\n"  # 3 — still inside
        "## Next\n"  # 4 — closes
    )
    assert migration_section_range(text) == (1, 4)


def test_exclusion_is_keyed_to_the_canonical_heading():
    """A retitled §4b section is deliberately NOT recognized.

    The exact heading is a module-wide structural key (skf-shard-body.py's
    TIER1_HEADINGS, step-auto-shard.md §3, validate.md's Tier-1 preservation
    check, skf-test-skill's migration-section-rules.md), so broadening only this
    matcher would desync it from the gates that share the vocabulary. Retitling
    is drift to fix at the producer, not a variant to absorb here. Widening this
    is a reviewed, module-wide change — not a local tweak.
    """
    retitled = (
        "# Skill\n"
        "\n"
        "## Deprecations & pre-1.0 hazards\n"
        "- bar deprecated since v3\n"
    )
    assert migration_section_range(retitled) is None


# --------------------------------------------------------------------------
# Frontmatter exclusion (self-authored description guard)
# --------------------------------------------------------------------------


FM_SKILL_MD = (
    "---\n"  # 1
    "name: katex\n"  # 2
    "description: KaTeX 0.17.0 — its only breaking change is internal.\n"  # 3 → excluded
    "---\n"  # 4
    "\n"
    "## API\n"
    "foo was removed in v2\n"  # 7 — body → kept
)


def test_frontmatter_range_covers_both_fences():
    assert frontmatter_range(FM_SKILL_MD) == (1, 4)


def test_frontmatter_range_none_when_absent():
    assert frontmatter_range("# Skill\n\n## API\nfoo deprecated\n") is None


def test_frontmatter_range_none_when_unterminated():
    """An unterminated opening fence must not swallow the whole file."""
    assert frontmatter_range("---\nname: x\n\n## API\nfoo deprecated\n") is None


def test_body_horizontal_rule_does_not_open_frontmatter():
    """`---` further down the body is a horizontal rule, not a fence."""
    text = "# Skill\n\n---\n\n## API\nfoo deprecated\n"
    assert frontmatter_range(text) is None


def test_frontmatter_exclusion_drops_description_keeps_body():
    matches = scan_text(FM_SKILL_MD, "SKILL.md")
    kept, dropped = apply_frontmatter_exclusion(matches, "SKILL.md", FM_SKILL_MD)
    kept_lines = {m["line_number"] for m in kept}
    # The description line hits both "breaking change" and "BREAKING" — the
    # overlapping-pattern contract records each separately, so both drop.
    assert dropped == 2
    assert 3 not in kept_lines  # description → dropped
    assert 7 in kept_lines  # body "removed in" → kept


def test_frontmatter_exclusion_only_applies_to_skill_md_source():
    other = scan_text(FM_SKILL_MD, "evidence-report.md")
    kept, dropped = apply_frontmatter_exclusion(other, "SKILL.md", FM_SKILL_MD)
    assert dropped == 0
    assert len(kept) == len(other)


def test_migration_search_starts_after_frontmatter():
    """An indented heading restated in a folded description must not anchor the
    window — otherwise the real body section goes unexcluded."""
    text = (
        "---\n"  # 1
        "description: >\n"  # 2
        "  ## Migration & Deprecation Warnings are covered inline.\n"  # 3 — decoy
        "---\n"  # 4
        "\n"
        "## Migration & Deprecation Warnings\n"  # 6 — the real section
        "- bar deprecated since v3\n"  # 7
        "\n"
        "## Footer\n"  # 9
    )
    assert migration_section_range(text) == (6, 9)


# --------------------------------------------------------------------------
# Bounding — duplicate collapse + cap
# --------------------------------------------------------------------------


def test_collapse_merges_same_category_and_normalized_text():
    matches = [
        {"source": "a.md", "pattern": "deprecated", "candidate_category": "Deprecation",
         "context_line": "foo is deprecated", "line_number": 1},
        {"source": "b.md", "pattern": "deprecated", "candidate_category": "Deprecation",
         "context_line": "  foo   is    deprecated  ", "line_number": 42},
    ]
    kept, collapsed = collapse_duplicates(matches)
    assert collapsed == 1
    assert len(kept) == 1
    assert kept[0]["occurrences"] == 2
    assert kept[0]["duplicate_of"] == [{"source": "b.md", "line_number": 42}]
    assert kept[0]["line_number"] == 1  # first occurrence survives


def test_collapse_merges_overlapping_patterns_on_one_line():
    """`breaking change` and `BREAKING` share a candidate category, so one line
    yields one candidate rather than two saying the same thing. `scan_text` still
    records both (the 13-row overlapping-pattern contract is unchanged): only
    the emitted candidate set is collapsed. `occurrences` counts keyword hits,
    so the second hit counts and points back at the same line."""
    raw = scan_text("v2: this is a breaking change", "changelog.md")
    assert len(raw) == 2
    kept, collapsed = collapse_duplicates(raw)
    assert collapsed == 1
    assert len(kept) == 1
    assert kept[0]["occurrences"] == 2
    assert kept[0]["duplicate_of"] == [{"source": "changelog.md", "line_number": 1}]


def test_collapse_keeps_distinct_categories_apart():
    matches = [
        {"source": "a.md", "pattern": "deprecated", "candidate_category": "Deprecation",
         "context_line": "same text", "line_number": 1},
        {"source": "a.md", "pattern": "BREAKING", "candidate_category": "Breaking change",
         "context_line": "same text", "line_number": 1},
    ]
    kept, collapsed = collapse_duplicates(matches)
    assert collapsed == 0
    assert len(kept) == 2


def test_collapse_does_not_mutate_input():
    matches = scan_text("foo removed in v2", "f.md")
    before = json.dumps(matches, sort_keys=True)
    collapse_duplicates(matches)
    assert json.dumps(matches, sort_keys=True) == before


def _candidate(source, line_number, pattern="deprecated", candidate_category="Deprecation"):
    return {"source": source, "pattern": pattern, "candidate_category": candidate_category,
            "context_line": f"{source} line {line_number} {pattern}", "line_number": line_number}


def _cap_fixture():
    """Scan order: a long changelog, a short release feed, then the compiled SKILL.md."""
    return (
        [_candidate("changelog.md", i) for i in range(1, 7)]
        + [_candidate("releases.md", i, "renamed to", "Rename") for i in range(1, 3)]
        + [_candidate("SKILL.md", i, "replaced by", "Supersession") for i in (40, 41)]
    )


def _kept(kept):
    return [(m["source"], m["line_number"]) for m in kept]


def test_cap_zero_means_unlimited():
    matches = _cap_fixture()
    kept, dropped = apply_cap(matches, 0, "SKILL.md")
    assert dropped == 0
    assert kept == matches


def test_cap_gives_every_feeder_its_turn():
    """A long feeder cannot crowd out a short one: each turn takes the next
    candidate of every feeder, and the survivors come back in scan order."""
    kept, dropped = apply_cap(_cap_fixture(), 4, "SKILL.md")
    assert dropped == 6
    assert _kept(kept) == [
        ("changelog.md", 1), ("changelog.md", 2), ("releases.md", 1), ("releases.md", 2),
    ]


def test_cap_puts_the_skill_md_lines_last():
    """#582: the compiled SKILL.md's own lines never outrank an upstream line,
    although the old cap kept them first."""
    matches = _cap_fixture()
    kept, dropped = apply_cap(matches, 8, "SKILL.md")
    assert dropped == 2
    assert {m["source"] for m in kept} == {"changelog.md", "releases.md"}


def test_cap_gives_the_skill_md_lines_the_places_left():
    kept, dropped = apply_cap(_cap_fixture(), 9, "SKILL.md")
    assert dropped == 1
    assert _kept(kept)[-1] == ("SKILL.md", 40)


def test_cap_without_a_skill_md_feeder_shares_by_turns():
    matches = [m for m in _cap_fixture() if m["source"] != "SKILL.md"]
    kept, dropped = apply_cap(matches, 3, None)
    assert dropped == 5
    assert _kept(kept) == [("changelog.md", 1), ("changelog.md", 2), ("releases.md", 1)]


def test_cap_at_or_above_total_is_a_no_op():
    matches = _cap_fixture()
    kept, dropped = apply_cap(matches, len(matches), "SKILL.md")
    assert dropped == 0
    assert kept == matches


# --------------------------------------------------------------------------
# scan_files — missing/empty skip + scanned list
# --------------------------------------------------------------------------


def test_scan_files_skips_missing_and_empty(tmp_path):
    good = tmp_path / "evidence-report.md"
    good.write_text("thing removed in v9\n", encoding="utf-8")
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    missing = tmp_path / "nope.md"
    out = scan_files([str(good), str(empty), str(missing)], None)
    assert out["scanned"] == [str(good)]
    assert out["match_count"] == 1
    assert out["matches"][0]["pattern"] == "removed in"


def test_scan_files_applies_exclusion_end_to_end(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL_MD, encoding="utf-8")
    out = scan_files([], str(skill))
    lines = {m["line_number"] for m in out["matches"]}
    assert out["excluded_count"] == 2
    assert 4 in lines and 11 in lines
    assert 7 not in lines and 8 not in lines
    assert out["scanned"] == [str(skill)]


def test_scan_files_counts_both_exclusion_windows(tmp_path):
    """excluded_count is the combined frontmatter + §4b total."""
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"  # 1
        "description: the only breaking change is internal\n"  # 2 → frontmatter
        "---\n"  # 3
        "\n"
        "## Migration & Deprecation Warnings\n"  # 5
        "- bar deprecated since v3\n"  # 6 → §4b
        "\n"
        "## API\n"  # 8
        "foo was removed in v2\n",  # 9 → kept
        encoding="utf-8",
    )
    out = scan_files([], str(skill))
    # 2 from the description line ("breaking change" + "BREAKING"), 1 from §4b.
    assert out["excluded_count"] == 3
    assert [m["line_number"] for m in out["matches"]] == [9]


def test_scan_files_collapses_and_caps(tmp_path):
    changelog = tmp_path / "changelog.md"
    # 80 distinct deprecations + 40 verbatim restatements of one of them.
    lines = [f"v{i}: api_{i} deprecated" for i in range(80)]
    lines += ["v0: api_0 deprecated"] * 40
    changelog.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = scan_files([str(changelog)], None)
    assert out["cap"] == DEFAULT_MAX_CANDIDATES
    assert out["deduped_count"] == 40  # the restatements collapse away
    assert out["capped_count"] == 80 - DEFAULT_MAX_CANDIDATES
    assert out["match_count"] == DEFAULT_MAX_CANDIDATES
    assert len(out["matches"]) == DEFAULT_MAX_CANDIDATES
    assert out["matches"][0]["occurrences"] == 41  # 1 original + 40 restatements

    unlimited = scan_files([str(changelog)], None, max_candidates=0)
    assert unlimited["capped_count"] == 0
    assert unlimited["match_count"] == 80


def test_scan_files_hands_over_more_candidates_than_blocks(tmp_path):
    """The judgment pass keeps at most 10 corrections, so the pool it reviews
    must be larger: a feeder with 30 distinct keyword lines hands over all 30."""
    changelog = tmp_path / "changelog.md"
    changelog.write_text("".join(f"- api_{i} deprecated\n" for i in range(30)), encoding="utf-8")
    out = scan_files([str(changelog)], None)
    assert DEFAULT_MAX_CANDIDATES > 10
    assert (out["match_count"], out["capped_count"]) == (30, 0)


def test_scan_files_caps_the_skill_md_lines_before_upstream_lines(tmp_path):
    """End to end: when the pool overflows, the compiled SKILL.md's body lines
    (scanned last) are the ones left out, and every upstream feeder keeps a share."""
    changelog = tmp_path / "changelog.md"
    changelog.write_text("".join(f"- api_{i} deprecated\n" for i in range(6)), encoding="utf-8")
    releases = tmp_path / "releases.md"
    releases.write_text("## v2.0.0\n- old_a renamed to new_a\n", encoding="utf-8")
    skill = tmp_path / "SKILL.md"
    skill.write_text("# Skill\n\n## API\n- `foo()` is replaced by `bar()`\n", encoding="utf-8")

    out = scan_files([str(changelog), str(releases)], str(skill), max_candidates=4)
    assert out["capped_count"] == 4
    assert [Path(m["source"]).name for m in out["matches"]] == [
        "changelog.md", "changelog.md", "changelog.md", "releases.md",
    ]


def test_scan_files_unique_matches_report_single_occurrence(tmp_path):
    feeder = tmp_path / "evidence-report.md"
    feeder.write_text("thing removed in v9\n", encoding="utf-8")
    out = scan_files([str(feeder)], None)
    assert out["deduped_count"] == 0
    assert out["capped_count"] == 0
    assert out["matches"][0]["occurrences"] == 1
    assert out["matches"][0]["duplicate_of"] == []


# --------------------------------------------------------------------------
# CLI (subprocess) — exit codes + JSON on stdout
# --------------------------------------------------------------------------


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
    )


def test_cli_emits_json(tmp_path):
    feeder = tmp_path / "provenance-map.json"
    feeder.write_text('{"note": "api migration required now"}\n', encoding="utf-8")
    proc = _run([str(feeder)])
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["match_count"] == 1
    assert data["matches"][0]["candidate_category"] == "Migration"


def test_cli_hands_over_the_reproduced_lines_as_candidates(tmp_path):
    """The #582 reproduction: both lines hold a keyword and come back as
    `Breaking change` candidates, for step 5c's judgment pass to drop. No
    record carries the old `category` field, which read as a verdict."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "- No breaking changes in this release.\n- Non-breaking: `parse()` accepts a Path.\n",
        encoding="utf-8",
    )
    proc = _run([str(changelog)])
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert sorted(m["line_number"] for m in data["matches"]) == [1, 2]
    assert {m["candidate_category"] for m in data["matches"]} == {"Breaking change"}
    assert all("category" not in m for m in data["matches"])


def test_cli_zero_matches_is_success(tmp_path):
    feeder = tmp_path / "clean.md"
    feeder.write_text("all current, nothing to correct\n", encoding="utf-8")
    proc = _run([str(feeder)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["match_count"] == 0


def test_cli_no_args_exits_1():
    proc = _run([])
    assert proc.returncode == 1


def test_cli_max_candidates_flag(tmp_path):
    feeder = tmp_path / "changelog.md"
    feeder.write_text(
        "".join(f"v{i}: api_{i} deprecated\n" for i in range(5)), encoding="utf-8"
    )
    proc = _run(["--max-candidates", "2", str(feeder)])
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["cap"] == 2
    assert data["match_count"] == 2
    assert data["capped_count"] == 3


def test_cli_default_cap_is_the_candidate_pool(tmp_path):
    feeder = tmp_path / "changelog.md"
    feeder.write_text("api_0 deprecated\n", encoding="utf-8")
    proc = _run([str(feeder)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["cap"] == DEFAULT_MAX_CANDIDATES == 50


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
