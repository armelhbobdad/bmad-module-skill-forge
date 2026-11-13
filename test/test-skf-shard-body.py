#!/usr/bin/env python3
"""Tests for skf-shard-body.py.

Covers the deterministic auto-shard mechanic that replaces the in-prompt
line-counting / boundary-detection / size-sort / file-write / blockquote
surgery in skf-create-skill's step-auto-shard.md §1–§5 and validate.md §4:

  - largest-first extraction stops the moment the body fits under budget,
    reference files carry kebab names + preserved headings, SKILL.md gains
    blockquote xrefs, and the JSON reports correct before/after counts with
    tier1_preserved / xref_ok true
  - a body already under budget -> action:"skip", zero files written
  - a body whose Tier-2 sections cannot fit under budget -> under_budget:false
  - --dry-run reports the same plan with no filesystem mutation
  - the Tier-1 preservation guard flags a pulled Tier-1 heading
  - frontmatter is never modified; writes route through skf-atomic-write.py
  - --word-budget splits on body words as well (update-skill's measure for
    skill-check's body.max_tokens), counted as JavaScript's /\s+/ splits;
    whichever budget is exceeded picks the next section; a body with no
    section left to move reports under_word_budget:false
  - --skip-manual keeps every section a [MANUAL] block reaches into, a block
    spanning sections and a marker split across lines included
  - a reference file is never overwritten: a `-2`, `-3` suffix, in document
    order, and the pointer names it; a failed write names what was written
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-shard-body.py"

spec = importlib.util.spec_from_file_location("skf_shard_body", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


FRONTMATTER = "---\nname: demo-skill\ndescription: A demo skill for tests.\n---\n"


def _section(heading: str, body_lines: int) -> str:
    """A markdown section: `## <heading>` plus `body_lines` filler lines."""
    filler = "\n".join(f"line {i} of {heading}" for i in range(body_lines))
    return f"## {heading}\n{filler}\n"


def _tier1(heading: str, body_lines: int = 3) -> str:
    return _section(heading, body_lines)


def _run(skill_md: Path, *extra: str) -> dict:
    """Invoke the script as a subprocess, return parsed JSON."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(skill_md), *extra],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# (1) Largest-first extraction stops the moment the body fits
# --------------------------------------------------------------------------


class TestSelectiveExtraction:
    def _build(self, tmp_path: Path) -> Path:
        # Tier-1 sections (small, must stay inline) + three Tier-2 `## Full`
        # sections of known, distinct sizes. Total body ~450 lines > 400.
        body = (
            _tier1("Overview", 4)
            + _tier1("Quick Start", 4)
            + _tier1("Key API Summary", 4)
            + _section("Full API Reference", 200)  # largest
            + _section("Full Type Definitions", 120)  # middle
            + _section("Full Integration Patterns", 90)  # smallest
        )
        return _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

    def test_extracts_largest_first_until_under_budget(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "shard"
        assert result["body_lines_before"] > 400
        assert result["body_lines_after"] <= 400
        assert result["under_budget"] is True
        assert result["tier1_preserved"] is True
        assert result["tier1_missing"] == []
        assert result["xref_ok"] is True

        headings = [s["heading"] for s in result["sections_extracted"]]
        # Largest first, and it should stop before pulling every section:
        # 450 - 200 = 250-ish after just the first extraction is already < 400.
        assert headings[0] == "Full API Reference"
        assert "Full Integration Patterns" not in headings

    def test_reference_files_written_with_kebab_names(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        for entry in result["sections_extracted"]:
            ref = skill_md.parent / entry["file"]
            assert ref.is_file(), f"{entry['file']} should exist"
            content = ref.read_text(encoding="utf-8")
            assert content.startswith(f"## {entry['heading']}\n")
        # Full API Reference -> references/full-api-reference.md
        assert (skill_md.parent / "references" / "full-api-reference.md").is_file()

    def test_skill_md_carries_blockquote_xrefs(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        rewritten = skill_md.read_text(encoding="utf-8")
        for entry in result["sections_extracted"]:
            assert (
                f"> See [{entry['heading']}]({entry['file']})" in rewritten
            ), f"blockquote for {entry['heading']} missing"
        # The extracted section body must no longer be inline.
        assert "line 199 of Full API Reference" not in rewritten

    def test_frontmatter_unmodified(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        _run(skill_md, "--budget", "400")
        rewritten = skill_md.read_text(encoding="utf-8")
        assert rewritten.startswith(FRONTMATTER)

    def test_tier1_sections_remain_inline(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        _run(skill_md, "--budget", "400")
        rewritten = skill_md.read_text(encoding="utf-8")
        for name in ("Overview", "Quick Start", "Key API Summary"):
            assert f"## {name}\n" in rewritten


# --------------------------------------------------------------------------
# (2) Already under budget -> skip, zero files written
# --------------------------------------------------------------------------


class TestSkipUnderBudget:
    def test_skip_writes_nothing(self, tmp_path: Path) -> None:
        body = _tier1("Overview", 20) + _section("Full API Reference", 40)
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "skip"
        assert result["sections_extracted"] == []
        assert result["body_lines_before"] == result["body_lines_after"]
        assert result["under_budget"] is True
        assert result["tier1_preserved"] is True
        assert result["xref_ok"] is True
        # No mutation, no references/ directory created.
        assert skill_md.read_text(encoding="utf-8") == before
        assert not (skill_md.parent / "references").exists()


# --------------------------------------------------------------------------
# (3) Tier-2 sections cannot fit the body under budget -> under_budget:false
# --------------------------------------------------------------------------


class TestCannotFit:
    def test_under_budget_false_when_tier1_too_large(self, tmp_path: Path) -> None:
        # Tier-1 alone is ~430 lines; extracting every Tier-2 section still
        # leaves the body over budget -> under_budget:false signals the caller
        # to fall to the editing-judgment trim.
        body = (
            _tier1("Overview", 210)
            + _tier1("Architecture at a Glance", 210)
            + _section("Full API Reference", 60)
            + _section("Full Type Definitions", 60)
        )
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )

        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "shard"
        assert result["under_budget"] is False
        # Every Tier-2 section was extracted (maximum possible reduction).
        headings = {s["heading"] for s in result["sections_extracted"]}
        assert headings == {"Full API Reference", "Full Type Definitions"}
        assert result["body_lines_after"] > 400
        # Tier-1 was never pulled despite the overflow.
        assert result["tier1_preserved"] is True


# --------------------------------------------------------------------------
# (4a) --dry-run reports the same plan with no filesystem mutation
# --------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_mutation(self, tmp_path: Path) -> None:
        body = (
            _tier1("Overview", 4)
            + _section("Full API Reference", 300)
            + _section("Full Type Definitions", 150)
        )
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, "--budget", "400", "--dry-run")

        assert result["action"] == "shard"
        assert result["dry_run"] is True
        assert result["body_lines_after"] <= 400
        assert result["sections_extracted"][0]["heading"] == "Full API Reference"
        assert result["tier1_preserved"] is True
        assert result["xref_ok"] is True
        # Nothing on disk changed.
        assert skill_md.read_text(encoding="utf-8") == before
        assert not (skill_md.parent / "references").exists()

    def test_dry_run_matches_write_plan(self, tmp_path: Path) -> None:
        body = (
            _tier1("Overview", 4)
            + _section("Full API Reference", 300)
            + _section("Full Type Definitions", 150)
        )
        dry = _write(tmp_path / "a" / "SKILL.md", FRONTMATTER + "\n" + body)
        wet = _write(tmp_path / "b" / "SKILL.md", FRONTMATTER + "\n" + body)

        dry_res = _run(dry, "--budget", "400", "--dry-run")
        wet_res = _run(wet, "--budget", "400")

        # The plan (counts + sections) is identical; only dry_run differs.
        for key in (
            "action",
            "body_lines_before",
            "body_lines_after",
            "sections_extracted",
            "tier1_preserved",
            "under_budget",
        ):
            assert dry_res[key] == wet_res[key], key


# --------------------------------------------------------------------------
# (4b) Tier-1 preservation guard flags a pulled heading
# --------------------------------------------------------------------------


class TestTier1Guard:
    def test_guard_flags_missing_tier1(self) -> None:
        # Direct unit test of the guard: a Tier-1 heading present before but
        # absent after (a hypothetical bad extraction) must be reported.
        before = ["## Overview", "text", "## Full API Reference", "x"]
        after = ["## Full API Reference", "x"]
        tier1_before = mod.present_tier1(before)
        tier1_after = mod.present_tier1(after)
        missing = [
            h
            for h in mod.TIER1_HEADINGS
            if h in tier1_before and h not in tier1_after
        ]
        assert missing == ["Overview"]
        assert bool(missing) is True  # tier1_preserved would be False

    def test_guard_passes_when_only_full_sections_pulled(self) -> None:
        before = ["## Overview", "t", "## Full API Reference", "x"]
        after = ["## Overview", "t", "> See [Full API Reference](references/x.md)"]
        tier1_before = mod.present_tier1(before)
        tier1_after = mod.present_tier1(after)
        missing = [
            h
            for h in mod.TIER1_HEADINGS
            if h in tier1_before and h not in tier1_after
        ]
        assert missing == []


# --------------------------------------------------------------------------
# (5) The word budget and the [MANUAL] guard (update-skill verify-publish.md
#     §7 runs the split on skill-check's body.max_tokens warning as well, #797)
# --------------------------------------------------------------------------


def _wordy(heading: str, lines: int, words: int) -> str:
    """`## <heading>` plus `lines` filler lines of `words` words each."""
    filler = "\n".join(" ".join(f"w{i}x{j}" for j in range(words)) for i in range(lines))
    return f"## {heading}\n{filler}\n"


def _manual(heading: str, lines: int, words: int) -> str:
    """A `## <heading>` section whose filler sits inside a [MANUAL] block."""
    head, filler = _wordy(heading, lines, words).split("\n", 1)
    return f"{head}\n<!-- [MANUAL:notes] -->\n{filler}<!-- [/MANUAL:notes] -->\n"


WORD_FLAGS = ("--budget", "500", "--word-budget", "5000", "--skip-manual")


class TestWordBudget:
    def _build(self, tmp_path: Path) -> Path:
        # About 320 lines (under the 500-line budget) and about 5,600 words.
        # The [MANUAL] section is the largest, so without the guard it would
        # move first and the API reference would stay.
        body = (
            _wordy("Overview", 20, 10)
            + _wordy("Quick Start", 20, 10)
            + _wordy("Key API Summary", 20, 10)
            + _wordy("Full API Reference", 100, 12)
            + _manual("Full Integration Notes", 150, 25)
        )
        return _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

    def test_only_the_section_without_manual_moves(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        body = skill_md.read_text(encoding="utf-8").split("---\n", 2)[2]
        assert len(body.splitlines()) < 500

        result = _run(skill_md, *WORD_FLAGS)

        assert result["action"] == "shard"
        # words as skill-check counts them: whitespace-split
        assert result["body_words_before"] == len(body.split()) > 5000
        assert result["body_words_after"] <= 5000
        assert result["under_word_budget"] is True
        assert result["under_budget"] is True
        assert [s["heading"] for s in result["sections_extracted"]] == ["Full API Reference"]
        assert result["tier1_preserved"] is True and result["xref_ok"] is True
        rewritten = skill_md.read_text(encoding="utf-8")
        assert "> See [Full API Reference](references/full-api-reference.md)" in rewritten
        # the [MANUAL] block stays inline, whole
        assert "## Full Integration Notes\n<!-- [MANUAL:notes] -->\n" in rewritten
        assert "<!-- [/MANUAL:notes] -->" in rewritten
        assert not (skill_md.parent / "references" / "full-integration-notes.md").exists()
        assert result["body_words_after"] == len(rewritten.split("---\n", 2)[2].split())

    def test_without_the_guard_the_manual_section_would_move(self, tmp_path: Path) -> None:
        # the fixture above is a real test of --skip-manual: largest-first
        # alone takes the [MANUAL] section and stops
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "500", "--word-budget", "5000", "--dry-run")
        assert [s["heading"] for s in result["sections_extracted"]] == ["Full Integration Notes"]

    def test_nothing_to_move_reports_over_the_word_budget(self, tmp_path: Path) -> None:
        # Tier 1 alone runs past 5,000 words and there is no `## Full` section
        body = _wordy("Overview", 100, 30) + _wordy("Quick Start", 100, 30)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, *WORD_FLAGS)

        assert result["action"] == "shard"
        assert result["sections_extracted"] == []
        assert result["under_word_budget"] is False
        assert result["body_words_after"] == result["body_words_before"] > 5000
        assert skill_md.read_text(encoding="utf-8") == before
        assert not (skill_md.parent / "references").exists()

    def test_only_manual_sections_left_reports_over_the_word_budget(self, tmp_path: Path) -> None:
        body = _wordy("Overview", 10, 10) + _manual("Full API Reference", 200, 30)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, *WORD_FLAGS)

        assert result["sections_extracted"] == []
        assert result["under_word_budget"] is False
        assert skill_md.read_text(encoding="utf-8") == before

    def test_within_both_budgets_skips(self, tmp_path: Path) -> None:
        body = _wordy("Overview", 10, 10) + _wordy("Full API Reference", 40, 10)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, *WORD_FLAGS)

        assert result["action"] == "skip"
        assert result["under_word_budget"] is True
        assert result["body_words_before"] == result["body_words_after"]

    def test_word_budget_off_by_default(self, tmp_path: Path) -> None:
        # without --word-budget only lines count: create-skill's calls are unchanged
        body = _wordy("Overview", 10, 10) + _wordy("Full API Reference", 40, 200)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "skip"
        assert result["body_words_before"] > 5000
        assert result["under_word_budget"] is True

    def test_holds_manual_reads_open_and_close_markers(self) -> None:
        body = ["## Full A", "x", "## Full B", "<!--  [MANUAL:n] -->", "## Full C", "<!-- [/MANUAL:n] -->"]
        secs = mod.find_full_sections(body)
        assert [mod.holds_manual(body, s) for s in secs] == [False, True, True]

    def test_new_keys_reach_the_output_file(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        out = tmp_path / "report.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(skill_md), "--budget", "400", "--word-budget", "4500",
             "--skip-manual", "-o", str(out)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0 and proc.stdout == "", proc.stderr
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["word_budget"] == 4500 and report["budget"] == 400
        assert report["body_words_before"] > 4500 >= report["body_words_after"]
        assert report["under_word_budget"] is True
        # off by default, and echoed as 0 on the skip path too
        small = _write(tmp_path / "small" / "SKILL.md", FRONTMATTER + "\n" + _wordy("Overview", 3, 3))
        assert _run(small)["word_budget"] == 0


# --------------------------------------------------------------------------
# (6) The [MANUAL] guard reads whole blocks over the whole body
# --------------------------------------------------------------------------


HASH_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-hash-content.py"


def _hash_blocks(text: str) -> list[dict]:
    hspec = importlib.util.spec_from_file_location("skf_hash_content", HASH_PATH)
    hmod = importlib.util.module_from_spec(hspec)
    assert hspec.loader is not None
    hspec.loader.exec_module(hmod)
    return hmod.find_manual_blocks(text.encode("utf-8"))


class TestManualGuard:
    def test_a_block_spanning_sections_stays(self, tmp_path: Path) -> None:
        # the block opens in Overview and closes inside the second `## Full`
        # section: the first `## Full` section holds no marker but sits
        # inside the block, so neither moves; the third is free
        body = (
            _wordy("Overview", 5, 5).rstrip("\n") + "\n<!-- [MANUAL:span] -->\n"
            + _wordy("Full API Reference", 300, 3)
            + "## Full Integration Notes\n<!-- [/MANUAL:span] -->\n" + _wordy("x", 150, 3).split("\n", 1)[1]
            + _wordy("Full Extra", 100, 3)
        )
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)
        assert len(_hash_blocks(body)) == 1

        result = _run(skill_md, "--budget", "400", "--skip-manual")

        assert [s["heading"] for s in result["sections_extracted"]] == ["Full Extra"]
        assert result["under_budget"] is False
        rewritten = skill_md.read_text(encoding="utf-8")
        assert len(_hash_blocks(rewritten)) == 1
        assert _hash_blocks(rewritten)[0]["content_hash"] == _hash_blocks(body)[0]["content_hash"]

    def test_a_marker_split_across_lines_is_found(self, tmp_path: Path) -> None:
        # skf-hash-content.py reads `<!--` / `[MANUAL:notes]` / `-->` on three
        # lines as one marker, so the largest section must stay
        manual = (
            "## Full API Reference\n<!--\n[MANUAL:notes]\n-->\n" + _wordy("x", 300, 3).split("\n", 1)[1]
            + "<!-- [/MANUAL:notes]\n-->\n"
        )
        body = _wordy("Overview", 5, 5) + manual + _wordy("Full Type Definitions", 150, 3)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)
        assert [b["name"] for b in _hash_blocks(body)] == ["notes"]

        result = _run(skill_md, "--budget", "400", "--skip-manual")

        assert [s["heading"] for s in result["sections_extracted"]] == ["Full Type Definitions"]
        assert "<!--\n[MANUAL:notes]\n-->" in skill_md.read_text(encoding="utf-8")

    def test_skip_manual_with_the_line_budget_alone(self, tmp_path: Path) -> None:
        body = (
            _wordy("Overview", 5, 5)
            + _manual("Full Integration Notes", 300, 2)
            + _wordy("Full API Reference", 150, 2)
        )
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, "--budget", "400", "--skip-manual")

        assert [s["heading"] for s in result["sections_extracted"]] == ["Full API Reference"]
        assert result["under_budget"] is True
        assert result["under_word_budget"] is True and result["word_budget"] == 0
        assert "<!-- [MANUAL:notes] -->" in skill_md.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# (7) Reference files are never overwritten
# --------------------------------------------------------------------------


class TestNeverOverwrite:
    def _body(self) -> str:
        return _wordy("Overview", 5, 5) + _wordy("Full API Reference", 450, 3)

    def test_an_existing_reference_file_gets_a_suffix(self, tmp_path: Path) -> None:
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + self._body())
        existing = _write(skill_md.parent / "references" / "full-api-reference.md", "## Full API Reference\nkept\n")

        result = _run(skill_md, "--budget", "400")

        assert result["sections_extracted"][0]["file"] == "references/full-api-reference-2.md"
        assert result["xref_ok"] is True
        assert existing.read_text(encoding="utf-8") == "## Full API Reference\nkept\n"
        rewritten = skill_md.read_text(encoding="utf-8")
        assert "> See [Full API Reference](references/full-api-reference-2.md)" in rewritten
        assert "w449x0" not in rewritten
        moved = (skill_md.parent / "references" / "full-api-reference-2.md").read_text(encoding="utf-8")
        assert moved.startswith("## Full API Reference\n")

    def test_a_file_with_the_same_content_is_reused(self, tmp_path: Path) -> None:
        first = _write(tmp_path / "a" / "SKILL.md", FRONTMATTER + "\n" + self._body())
        _run(first, "--budget", "400")
        second = _write(tmp_path / "b" / "SKILL.md", FRONTMATTER + "\n" + self._body())
        same = (first.parent / "references" / "full-api-reference.md").read_text(encoding="utf-8")
        _write(second.parent / "references" / "full-api-reference.md", same)

        result = _run(second, "--budget", "400")

        assert result["sections_extracted"][0]["file"] == "references/full-api-reference.md"
        assert sorted(p.name for p in (second.parent / "references").iterdir()) == ["full-api-reference.md"]

    def test_a_failed_write_names_the_references_already_written(self, tmp_path: Path) -> None:
        # a folder where the atomic writer puts SKILL.md's temporary file makes
        # the last write fail after the reference file was written
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + self._body())
        before = skill_md.read_text(encoding="utf-8")
        (skill_md.parent / "SKILL.md.skf-tmp").mkdir()

        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), str(skill_md), "--budget", "400"],
                              capture_output=True, text=True)

        assert proc.returncode == 2 and proc.stdout == ""
        [line] = proc.stderr.strip().splitlines()
        assert line.startswith("error: atomic write failed for ") and "SKILL.md" in line
        assert line.endswith("; already written: references/full-api-reference.md")
        assert skill_md.read_text(encoding="utf-8") == before

    def test_two_headings_with_one_kebab_name(self, tmp_path: Path) -> None:
        body = _wordy("Overview", 5, 5) + _wordy("Full API Reference", 250, 3) + _wordy("Full API: Reference", 300, 3)
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, "--budget", "100")

        files = {s["heading"]: s["file"] for s in result["sections_extracted"]}
        # names go in document order, whatever order the sections moved in
        assert files == {"Full API Reference": "references/full-api-reference.md",
                         "Full API: Reference": "references/full-api-reference-2.md"}
        assert result["xref_ok"] is True
        rewritten = skill_md.read_text(encoding="utf-8")
        assert "> See [Full API Reference](references/full-api-reference.md)" in rewritten
        assert "> See [Full API: Reference](references/full-api-reference-2.md)" in rewritten
        refs = skill_md.parent / "references"
        assert (refs / "full-api-reference.md").read_text(encoding="utf-8").startswith("## Full API Reference\n")
        assert (refs / "full-api-reference-2.md").read_text(encoding="utf-8").startswith("## Full API: Reference\n")


# --------------------------------------------------------------------------
# (8) Which budget is exceeded picks the next section
# --------------------------------------------------------------------------


UPDATE_FLAGS = ("--budget", "400", "--word-budget", "4500", "--skip-manual")


class TestSelectionOrder:
    def test_the_loop_goes_on_for_words_after_the_lines_fit(self, tmp_path: Path) -> None:
        # the largest section by lines holds few words; once it moves the lines
        # fit, the words do not, and the wordy section moves too
        body = (
            _wordy("Overview", 10, 5)
            + _wordy("Full Type Definitions", 400, 1)
            + _wordy("Full API Reference", 50, 100)
        )
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, *UPDATE_FLAGS)

        assert [s["heading"] for s in result["sections_extracted"]] == ["Full Type Definitions", "Full API Reference"]
        assert result["under_budget"] is True and result["under_word_budget"] is True

    def test_words_pick_first_when_the_lines_fit(self, tmp_path: Path) -> None:
        # by lines the first section is larger; only words are over, so the
        # wordy one moves alone
        body = (
            _wordy("Overview", 10, 5)
            + _wordy("Full Type Definitions", 200, 2)
            + _wordy("Full API Reference", 50, 100)
        )
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, *UPDATE_FLAGS)

        assert result["body_lines_before"] < 400 and result["body_words_before"] > 4500
        assert [s["heading"] for s in result["sections_extracted"]] == ["Full API Reference"]
        assert result["under_word_budget"] is True

    def test_update_flags_on_a_long_body_of_few_words(self, tmp_path: Path) -> None:
        body = (
            _wordy("Overview", 10, 5)
            + _wordy("Full API Reference", 450, 2)
            + _wordy("Full Type Definitions", 100, 2)
        )
        skill_md = _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

        result = _run(skill_md, *UPDATE_FLAGS)

        assert result["body_lines_before"] > 400 and result["body_words_before"] < 4500
        assert [s["heading"] for s in result["sections_extracted"]] == ["Full API Reference"]
        assert result["under_budget"] is True and result["under_word_budget"] is True
        assert result["word_budget"] == 4500


# --------------------------------------------------------------------------
# (9) Words are counted as JavaScript's /\s+/ splits them
# --------------------------------------------------------------------------


class TestWordCount:
    def test_js_whitespace(self) -> None:
        assert mod.count_words("") == 0
        assert mod.count_words("  a \t\n b  ") == 2
        # JavaScript's \s holds NBSP, the ideographic space and the BOM ...
        assert mod.count_words("a b　c﻿d") == 4
        assert mod.count_words("a b c d e f g h") == 8
        # ... and not U+0085 or the U+001C-U+001F separators, where str.split() differs
        for sep in ("\x85", "\x1c", "\x1d", "\x1e", "\x1f"):
            assert mod.count_words(f"a{sep}b") == 1, repr(sep)
            assert len(f"a{sep}b".split()) == 2, repr(sep)
        assert len("a﻿b".split()) == 1

    def test_body_words_use_the_js_count(self) -> None:
        assert mod.count_body_words(["a b", "c\x85d"]) == 3


# --------------------------------------------------------------------------
# Unit-level helpers: kebab, section boundaries, counting
# --------------------------------------------------------------------------


class TestHelpers:
    def test_kebab_case(self) -> None:
        assert mod.kebab_case("Full API Reference") == "full-api-reference"
        assert mod.kebab_case("Full Type Definitions") == "full-type-definitions"
        assert (
            mod.kebab_case("Full Integration & Patterns")
            == "full-integration-patterns"
        )

    def test_count_body_excludes_trailing_blanks(self) -> None:
        assert mod.count_body_lines(["a", "b", "", "  ", ""]) == 2
        assert mod.count_body_lines([]) == 0
        assert mod.count_body_lines(["", ""]) == 0

    def test_full_section_boundary_stops_at_next_h2(self) -> None:
        body = [
            "## Full API Reference",
            "a",
            "### nested",
            "b",
            "## Overview",
            "c",
        ]
        secs = mod.find_full_sections(body)
        assert len(secs) == 1
        assert secs[0].heading == "Full API Reference"
        assert secs[0].start == 0
        assert secs[0].end == 4  # nested ### stays inside; stops at ## Overview
        assert secs[0].kebab == "full-api-reference"

    def test_non_full_h2_not_extracted(self) -> None:
        body = ["## Overview", "x", "## Fully Loaded", "y"]
        # "Fully Loaded" does not start with the "Full " token boundary word.
        secs = mod.find_full_sections(body)
        assert secs == []

    def test_split_frontmatter(self) -> None:
        fm, body = mod.split_frontmatter(FRONTMATTER + "\nbody line\n")
        assert fm[0] == "---"
        assert fm[-1] == "---"
        assert "body line" in body
