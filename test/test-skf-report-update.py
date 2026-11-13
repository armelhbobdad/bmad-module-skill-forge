#!/usr/bin/env python3
"""Tests for skf-report-update.py (skf-verify-stack, #1198).

The coverage, integrations, requirements and synthesize stages write their
frontmatter counts, table rows and sections through this helper, which edits
only the part a call names and writes through the shared atomic writer:

- set-counts maps each helper's JSON onto its frontmatter keys, adds the
  stage to stepsCompleted once as one flow list, adds a key the frontmatter
  lacks, and refuses input of the wrong shape or a helper's saved error;
- fill-table replaces the data rows of the first table under a heading,
  refusing a line that is not a row of that table;
- replace-section replaces a section's body, keeping its closing break, or
  one `###` subsection of it, appending it when absent, and refuses content
  with a heading that would end the section;
- every other byte stays (CRLF, a byte order mark, an open last line), the
  installed layout finds the shared reader and writer, a missing one exits 1
  and a failing writer exits 3 with the report as it was;
- the calls the four stage files document, run on a report made from the
  template, leave a report the feasibility-report check passes, the verdict
  rollup reads and the next run's delta reads back.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "skf-verify-stack"
REFERENCES = SKILL / "references"
SCRIPT = SKILL / "scripts" / "skf-report-update.py"
TALLY = SKILL / "scripts" / "skf-coverage-tally.py"
ROLLUP = SKILL / "scripts" / "skf-verdict-rollup.py"
DELTA = SKILL / "scripts" / "skf-report-delta.py"
TEMPLATE = SKILL / "assets" / "feasibility-report-template.md"
SHARED = REPO / "src" / "shared" / "scripts"
READER_PATH = SHARED / "skf-validate-feasibility-report.py"
WRITER_PATH = SHARED / "skf-atomic-write.py"
VERDICT_HEADER = "| lib_a | lib_b | verdict | rationale |"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load("skf_report_update", SCRIPT)
reader = _load("skf_validate_feasibility_report_update", READER_PATH)


def _report(tmp_path, steps="['init']", newline="\n", name="feasibility-report-my-app-20261001-101500.md"):
    """The report init.md creates from the template, with its stepsCompleted."""
    text = TEMPLATE.read_text(encoding="utf-8").replace("stepsCompleted: []", f"stepsCompleted: {steps}")
    path = tmp_path / name
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def _call(args, stdin=b"", script=SCRIPT):
    """(exit code, parsed stdout JSON or None, the process) of one CLI call."""
    proc = subprocess.run([sys.executable, str(script), *[str(arg) for arg in args]], input=stdin,
                          capture_output=True, check=False)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc


def _run(args, stdin=b""):
    """(result, exit code) of mod.run() for these arguments."""
    return mod.run(mod._build_parser().parse_args([str(arg) for arg in args]), stdin, reader)


def _frontmatter(path):
    text = path.read_text(encoding="utf-8-sig")
    fields, _ = reader.split_frontmatter(text)
    return fields, reader.frontmatter_list(text, "stepsCompleted")


def _changed_lines(before, after):
    """The indexes of the lines that differ, for two texts with the same line count."""
    old, new = before.split(b"\n"), after.split(b"\n")
    assert len(old) == len(new), (len(old), len(new))
    return [i for i, (a, b) in enumerate(zip(old, new)) if a != b]


def _json(data):
    return json.dumps(data).encode("utf-8")


COVERAGE_TALLY = {"covered_count": 3, "missing_count": 1, "replaced_count": 2, "live_count": 4,
                  "total_referenced": 6, "coverage_percentage": 75}


# --- set-counts ------------------------------------------------------------------------


def test_set_counts_writes_the_coverage_keys_and_the_stage(tmp_path):
    path = _report(tmp_path)
    before = path.read_bytes()
    result, code = _run(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY))
    assert code == 0, result
    assert result["changed"] is True and result["stepsCompleted"] == ["init", "coverage"]
    assert result["set"] == {"coveragePercentage": 75, "coverageCovered": 3, "coverageMissing": 1,
                             "coverageReplaced": 2}
    after = path.read_bytes()
    lines = after.split(b"\n")
    changed = {lines[i].decode("utf-8") for i in _changed_lines(before, after)}
    assert changed == {"coveragePercentage: 75", "coverageCovered: 3", "coverageMissing: 1",
                       "coverageReplaced: 2", "stepsCompleted: ['init', 'coverage']"}
    fields, steps = _frontmatter(path)
    assert steps == ["init", "coverage"] and fields["coverageCovered"] == "3"


def test_set_counts_twice_changes_nothing(tmp_path):
    path = _report(tmp_path)
    args = ["set-counts", "--report", path, "--kind", "coverage"]
    assert _run(args, _json(COVERAGE_TALLY))[1] == 0
    once = path.read_bytes()
    result, code = _run(args, _json(COVERAGE_TALLY))
    assert (code, result["changed"]) == (0, False)
    assert path.read_bytes() == once
    assert _frontmatter(path)[1].count("coverage") == 1


def test_a_block_list_becomes_one_flow_line_and_a_missing_key_is_added(tmp_path):
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8").replace("stepsCompleted: ['init']", "stepsCompleted:\n  - init")
    text = text.replace("coverageReplaced: null\n", "")
    path.write_bytes(text.encode("utf-8"))
    assert _run(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY))[1] == 0
    after = path.read_text(encoding="utf-8")
    frontmatter = after.split("\n---\n", 1)[0].split("\n")
    assert "stepsCompleted: ['init', 'coverage']" in frontmatter and "  - init" not in frontmatter
    # The key the frontmatter lacked goes in just before its closing `---`.
    assert frontmatter[-1] == "coverageReplaced: 2"
    assert _frontmatter(path) == (reader.split_frontmatter(after)[0], ["init", "coverage"])


@pytest.mark.parametrize("kind, data, needle", [
    pytest.param("coverage", {k: v for k, v in COVERAGE_TALLY.items() if k != "missing_count"},
                 "has no missing_count", id="missing-key"),
    pytest.param("coverage", {**COVERAGE_TALLY, "covered_count": True}, "covered_count is True", id="bool"),
    pytest.param("coverage", {**COVERAGE_TALLY, "replaced_count": -1}, "replaced_count is -1", id="negative"),
    pytest.param("coverage", {**COVERAGE_TALLY, "coverage_percentage": 101}, "coverage_percentage is 101",
                 id="percentage-above-100"),
    pytest.param("coverage", {**COVERAGE_TALLY, "covered_count": "3"}, "covered_count is '3'", id="string"),
    pytest.param("synthesize", {"overallVerdict": "Feasible", "recommendationCount": 0}, "overallVerdict is 'Feasible'",
                 id="unknown-verdict"),
    pytest.param("integrations", {"error": "duplicate pair 'a' / 'b'", "code": "INVALID_INPUT"},
                 "carries an error: duplicate pair", id="error-input"),
    pytest.param("delta", [1, 2], "must be a JSON object", id="not-an-object"),
])
def test_bad_counts_write_nothing(tmp_path, kind, data, needle):
    path = _report(tmp_path)
    before = path.read_bytes()
    code, out, _ = _call(["set-counts", "--report", path, "--kind", kind], _json(data))
    assert (code, out["code"]) == (2, "INVALID_INPUT"), out
    assert needle in out["error"], out["error"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("stdin, needle", [(b"", "holds no coverage JSON"), (b"{not json", "not JSON")])
def test_set_counts_needs_json_on_stdin(tmp_path, stdin, needle):
    path = _report(tmp_path)
    code, out, _ = _call(["set-counts", "--report", path, "--kind", "coverage"], stdin)
    assert (code, out["code"]) == (2, "INVALID_INPUT") and needle in out["error"]


@pytest.mark.parametrize("kind, data, expected, stage", [
    ("integrations", {"pairs_verified": 1, "pairs_plausible": 2, "pairs_risky": 3, "pairs_blocked": 0,
                      "pair_count": 5, "cycle_count": 1, "row_count": 6},
     {"pairsVerified": "1", "pairsPlausible": "2", "pairsRisky": "3", "pairsBlocked": "0"}, "integrations"),
    ("requirements", {"requirements_fulfilled": 2, "requirements_partial": 1, "requirements_not_addressed": 0,
                      "requirement_count": 3},
     {"requirementsFulfilled": "2", "requirementsPartial": "1", "requirementsNotAddressed": "0",
      "requirementsPass": "completed"}, "requirements"),
    ("requirements-skipped", None, {"requirementsPass": "skipped", "requirementsFulfilled": "null"}, "requirements"),
    ("synthesize", {"overallVerdict": "NOT_FEASIBLE", "recommendationCount": 4, "matchedConditions": []},
     {"overallVerdict": "NOT_FEASIBLE", "recommendationCount": "4"}, "synthesize"),
    ("delta", {"improvedCount": 1, "regressedCount": 0, "newCount": 2, "unchangedCount": 5, "improved": ["x"]},
     {"deltaImproved": "1", "deltaRegressed": "0", "deltaNew": "2", "deltaUnchanged": "5"}, None),
])
def test_each_kind_sets_its_keys(tmp_path, kind, data, expected, stage):
    path = _report(tmp_path)
    # requirements-skipped reads no stdin: whatever is there is never read.
    stdin = b"not read" if data is None else _json(data)
    code, out, _ = _call(["set-counts", "--report", path, "--kind", kind], stdin)
    assert code == 0, out
    fields, steps = _frontmatter(path)
    for key, value in expected.items():
        assert fields[key] == value, key
    assert steps == (["init"] if stage is None else ["init", stage])
    # Tokens are double-quoted, counts bare.
    text = path.read_text(encoding="utf-8")
    for key, value in expected.items():
        if value.isdigit():
            assert f"\n{key}: {value}\n" in text, key
        elif value != "null":
            assert f'\n{key}: "{value}"\n' in text, key


def test_a_scalar_steps_completed_is_refused(tmp_path):
    path = _report(tmp_path, steps="init")
    before = path.read_bytes()
    code, out, _ = _call(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY))
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "not a list" in out["error"]
    assert path.read_bytes() == before


def test_a_report_with_no_frontmatter_or_no_file_is_invalid(tmp_path):
    bare = tmp_path / "bare.md"
    bare.write_bytes(b"# A report\n\n## Coverage Analysis\n")
    code, out, _ = _call(["set-counts", "--report", bare, "--kind", "coverage"], _json(COVERAGE_TALLY))
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "no frontmatter" in out["error"]
    code, out, _ = _call(["set-counts", "--report", tmp_path / "missing.md", "--kind", "coverage"],
                         _json(COVERAGE_TALLY))
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "cannot read the report" in out["error"]
    latin = tmp_path / "latin1.md"
    latin.write_bytes(b"---\nnote: caf\xe9\n---\n")
    code, out, _ = _call(["set-counts", "--report", latin, "--kind", "coverage"], _json(COVERAGE_TALLY))
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "not UTF-8" in out["error"]


# --- fill-table --------------------------------------------------------------------------


VERDICT_ROWS = ["| react | zod | Verified | zod cites react |",
                "| next | prisma | Plausible | neither cites the other |",
                "| cycle | a → b → c → a | Risky | circular integration dependency detected: `a → b`|"]


def _rows(rows, newline="\n"):
    return "".join(row + newline for row in rows).encode("utf-8")


def test_fill_table_puts_the_rows_under_the_header(tmp_path):
    path = _report(tmp_path)
    before = path.read_text(encoding="utf-8")
    args = ["fill-table", "--report", path, "--heading", "Integration Verdicts"]
    result, code = _run(args, _rows(VERDICT_ROWS, "\r\n"))
    assert (code, result["rows"]) == (0, 3), result
    after = path.read_text(encoding="utf-8")
    lines = after.split("\n")
    at = lines.index(VERDICT_HEADER)
    assert lines[at + 1] == "|-------|-------|---------|-----------|"
    assert lines[at + 2:at + 5] == VERDICT_ROWS and lines[at + 5] == ""
    # Only the rows went in: the comment, the header and every later line are as they were.
    assert after.replace("".join(row + "\n" for row in VERDICT_ROWS), "") == before
    found, rows, duplicate = reader.read_verdict_table(reader.split_frontmatter(after)[1])
    assert found and duplicate is None and [cells[2] for _, cells in rows] == ["Verified", "Plausible", "Risky"]
    # A second call replaces the rows.
    assert _run(args, _rows(VERDICT_ROWS[:1]))[1] == 0
    assert path.read_text(encoding="utf-8") == before.replace(
        "|-------|-------|---------|-----------|\n", "|-------|-------|---------|-----------|\n" + VERDICT_ROWS[0] + "\n")


@pytest.mark.parametrize("stdin", [b"", b"\n\r\n  \n"], ids=["empty", "blank-lines"])
def test_fill_table_with_no_row_leaves_the_header_and_delimiter(tmp_path, stdin):
    path = _report(tmp_path)
    template = path.read_bytes()
    args = ["fill-table", "--report", path, "--heading", "Integration Verdicts"]
    assert _run(args, _rows(VERDICT_ROWS))[1] == 0
    result, code = _run(args, stdin)
    assert (code, result["rows"], result["changed"]) == (0, 0, True)
    assert path.read_bytes() == template


@pytest.mark.parametrize("case, stdin, code, needle", [
    pytest.param("json-error", b'{\n  "error": "rows[0] requires a non-empty string `rationale`",\n}\n',
                 "INVALID_INPUT", "stdin line 1 is not a table row", id="json-error"),
    pytest.param("three-cells", b"| react | zod | Verified |\n", "INVALID_INPUT",
                 "stdin line 1 has 3 cells but the `## Integration Verdicts` table has 4", id="three-cells"),
    pytest.param("five-cells", b"| a | b | Verified | x | y |\n", "INVALID_INPUT", "has 5 cells", id="unescaped-pipe"),
    pytest.param("no-heading", b"", "INVALID_REPORT", "no `## Integration Verdicts` heading", id="heading-absent"),
    pytest.param("two-headings", b"", "INVALID_REPORT", "holds `## Integration Verdicts` twice", id="heading-twice"),
    pytest.param("no-table", b"", "INVALID_REPORT", "no table under `## Integration Verdicts`", id="no-table"),
])
def test_fill_table_refusals_write_nothing(tmp_path, case, stdin, code, needle):
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8")
    if case == "no-heading":
        text = text.replace("## Integration Verdicts", "## Integration Results")
    elif case == "two-headings":
        text = text.replace("## Recommendations", "## Integration Verdicts\n\n## Recommendations")
    elif case == "no-table":
        text = text.replace(VERDICT_HEADER + "\n|-------|-------|---------|-----------|\n", "")
    path.write_bytes(text.encode("utf-8"))
    before = path.read_bytes()
    exit_code, out, _ = _call(["fill-table", "--report", path, "--heading", "Integration Verdicts"], stdin)
    assert (exit_code, out["code"]) == (2, code), out
    assert needle in out["error"], out["error"]
    if case == "two-headings":
        # The refusal names the file line of each copy of the heading.
        at = [str(i + 1) for i, line in enumerate(text.split("\n")) if line == "## Integration Verdicts"]
        assert f"(lines {' and '.join(at)})" in out["error"], out["error"]
    assert path.read_bytes() == before


def test_a_table_in_fenced_code_or_a_comment_is_not_filled(tmp_path):
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "## Coverage Analysis\n",
        "## Coverage Analysis\n\n```markdown\n| a | b |\n|---|---|\n```\n\n<!--\n| c | d |\n|---|---|\n-->\n")
    path.write_bytes(text.encode("utf-8"))
    code, out, _ = _call(["fill-table", "--report", path, "--heading", "Coverage Analysis"], b"| x | y |\n")
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "no table under" in out["error"]


# --- replace-section ---------------------------------------------------------------------


def _body(text, heading):
    """The lines of `## heading` up to the next `##` heading."""
    lines = text.split("\n")
    at = lines.index(f"## {heading}")
    end = next((i for i in range(at + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[at + 1:end]


def test_replace_section_replaces_the_body_and_keeps_the_break(tmp_path):
    path = _report(tmp_path)
    before = path.read_text(encoding="utf-8")
    content = b"\n\n| Technology | Source Section | Skill Match | Verdict |\n|---|---|---|---|\n\n**Coverage: 3/4**\n\n"
    args = ["replace-section", "--report", path, "--heading", "Coverage Analysis"]
    result, code = _run(args, content)
    assert (code, result["lines"], result["subsection"]) == (0, 4, None), result
    after = path.read_text(encoding="utf-8")
    assert _body(after, "Coverage Analysis") == [
        "", "| Technology | Source Section | Skill Match | Verdict |", "|---|---|---|---|", "", "**Coverage: 3/4**",
        "", "---", ""]
    assert "<!-- Appended by coverage -->" not in after
    # Every other section is as it was.
    for heading in ("Executive Summary", "Integration Verdicts", "Recommendations", "Evidence Sources"):
        assert _body(after, heading) == _body(before, heading), heading
    # The same call again changes nothing.
    assert _run(args, content)[0]["changed"] is False


def test_replace_section_of_the_last_section_ends_the_file(tmp_path):
    path = _report(tmp_path)
    args = ["replace-section", "--report", path, "--heading", "Evidence Sources"]
    assert _run(args, b"rows go here\n")[1] == 0
    assert path.read_text(encoding="utf-8").endswith("## Evidence Sources\n\nrows go here\n")


def test_subsections_append_then_replace_in_place(tmp_path):
    path = _report(tmp_path)
    base = ["replace-section", "--report", path, "--heading", "Recommendations", "--subsection"]
    assert _run([*base, "Requirements Coverage"], b"| ID | Requirement |\n|---|---|\n| R1 | sync |\n")[1] == 0
    requirements = path.read_text(encoding="utf-8")
    assert _run([*base, "Prioritized Recommendations"], b"1. Do this.\n\n#### Delta\n\nnone\n\nNext: [VS]\n")[1] == 0
    after = path.read_text(encoding="utf-8")
    assert _body(after, "Recommendations") == [
        "", "<!-- Appended by synthesize -->", "", "### Requirements Coverage", "", "| ID | Requirement |", "|---|---|",
        "| R1 | sync |", "", "### Prioritized Recommendations", "", "1. Do this.", "", "#### Delta", "", "none", "",
        "Next: [VS]", "", "---", ""]
    # The requirements block is as the first call left it.
    assert _body(requirements, "Recommendations")[:9] == _body(after, "Recommendations")[:9]
    # The same call again replaces the block in place.
    result, code = _run([*base, "Prioritized Recommendations"], b"1. Do that instead.\n")
    assert code == 0 and result["changed"] is True
    body = _body(path.read_text(encoding="utf-8"), "Recommendations")
    assert body[9:] == ["### Prioritized Recommendations", "", "1. Do that instead.", "", "---", ""]
    assert body.count("### Prioritized Recommendations") == 1
    assert _run([*base, "Prioritized Recommendations"], b"1. Do that instead.\n")[0]["changed"] is False
    # A block before another one is replaced up to that one's heading.
    assert _run([*base, "Requirements Coverage"], b"| R1 | done |\n")[1] == 0
    body = _body(path.read_text(encoding="utf-8"), "Recommendations")
    assert body[3:8] == ["### Requirements Coverage", "", "| R1 | done |", "", "### Prioritized Recommendations"]


def test_a_subsection_appended_at_the_end_of_the_file(tmp_path):
    path = _report(tmp_path)
    base = ["replace-section", "--report", path, "--heading", "Evidence Sources", "--subsection", "Input Documents"]
    assert _run(base, b"- architecture: docs/arch.md\n")[1] == 0
    text = path.read_text(encoding="utf-8")
    assert text.endswith("|----------|\n\n### Input Documents\n\n- architecture: docs/arch.md\n")
    # The table above it still takes its rows.
    rows = _rows(["| react | T1 | none | 1.3 | /s/react/SKILL.md |"])
    assert _run(["fill-table", "--report", path, "--heading", "Evidence Sources"], rows)[1] == 0
    assert path.read_text(encoding="utf-8").endswith(
        "|----------|\n| react | T1 | none | 1.3 | /s/react/SKILL.md |\n\n### Input Documents\n\n"
        "- architecture: docs/arch.md\n")
    assert _run(base, b"- architecture: docs/arch.md\n")[0]["changed"] is False


@pytest.mark.parametrize("subsection, content, needle", [
    pytest.param(None, b"text\n## Integration Verdicts\n", "content line 2 is a `#` or `##` heading", id="h2"),
    pytest.param(None, b"# Title\n", "content line 1 is a `#` or `##` heading", id="h1"),
    pytest.param("Input Documents", b"text\n\n### Other\n", "content line 3 is a `#`, `##` or `###` heading",
                 id="h3-in-subsection"),
    pytest.param(None, b"```\nopen fence\n", "leaves a fenced code block", id="open-fence"),
    pytest.param(None, b"<!-- open\n", "an HTML comment open", id="open-comment"),
    pytest.param(None, b"\n  \n", "holds no content", id="empty"),
])
def test_content_that_would_end_the_section_is_refused(tmp_path, subsection, content, needle):
    path = _report(tmp_path)
    before = path.read_bytes()
    args = ["replace-section", "--report", path, "--heading", "Coverage Analysis"]
    if subsection:
        args += ["--subsection", subsection]
    code, out, _ = _call(args, content)
    assert (code, out["code"]) == (2, "INVALID_INPUT"), out
    assert needle in out["error"], out["error"]
    assert path.read_bytes() == before


def test_headings_in_fenced_code_and_h3_without_subsection_are_content(tmp_path):
    path = _report(tmp_path)
    content = b"```markdown\n## Not a heading\n```\n\n### A subheading\n"
    assert _run(["replace-section", "--report", path, "--heading", "Coverage Analysis"], content)[1] == 0
    text = path.read_text(encoding="utf-8")
    assert ("## Coverage Analysis\n\n```markdown\n## Not a heading\n```\n\n### A subheading\n\n---\n\n"
            "## Integration Verdicts\n") in text
    assert subprocess.run([sys.executable, str(READER_PATH), str(path)], capture_output=True,
                          check=False).returncode == 0


def test_a_subsection_twice_is_refused(tmp_path):
    path = _report(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "<!-- Appended by synthesize -->", "### Input Documents\n\na\n\n### Input Documents\n\nb")
    path.write_bytes(text.encode("utf-8"))
    code, out, _ = _call(["replace-section", "--report", path, "--heading", "Recommendations", "--subsection",
                          "Input Documents"], b"c\n")
    assert (code, out["code"]) == (2, "INVALID_REPORT") and "`### Input Documents` twice" in out["error"]
    # The refusal names the file line of each copy of the subsection.
    at = [str(i + 1) for i, line in enumerate(text.split("\n")) if line == "### Input Documents"]
    assert len(at) == 2 and f"(lines {at[0]} and {at[1]})" in out["error"], out["error"]


def test_each_stage_states_the_headings_its_content_files_hold_none_of():
    # replace-section refuses content with a `#` or `##` heading, and with --subsection a
    # `###` one too: each stage says so where it writes the file the call reads.
    rules = {
        "coverage.md": ["The report keeps its `## Coverage Analysis` line, so the file holds no `#` or `##` heading."],
        "integrations.md": ["The helper writes that `###` line, so the file holds no `#`, `##` or `###` heading."],
        "requirements.md": ["The helper writes the `### Requirements Coverage` line, so the file holds no `#`, `##` "
                            "or `###` heading."],
        "synthesize.md": ["The report keeps its `##` headings and the helper writes each `###` line, so no file holds "
                          "a `#` or `##` heading, and the last two hold no `###` heading either."],
    }
    for name, sentences in rules.items():
        text = (REFERENCES / name).read_text(encoding="utf-8")
        for sentence in sentences:
            assert text.count(sentence) == 1, (name, sentence)


# --- Bytes the call does not name stay ---------------------------------------------------


def test_a_crlf_report_keeps_crlf(tmp_path):
    path = _report(tmp_path, newline="\r\n")
    assert _run(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY))[1] == 0
    assert _run(["fill-table", "--report", path, "--heading", "Integration Verdicts"], _rows(VERDICT_ROWS))[1] == 0
    assert _run(["replace-section", "--report", path, "--heading", "Coverage Analysis"], b"text\n")[1] == 0
    assert _run(["replace-section", "--report", path, "--heading", "Evidence Sources", "--subsection",
                 "Input Documents"], b"paths\n")[1] == 0
    data = path.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n") and data.endswith(b"paths\r\n")
    assert b"\r\nstepsCompleted: ['init', 'coverage']\r\n" in data
    assert b"\r\n" + VERDICT_ROWS[0].encode("utf-8") + b"\r\n" in data
    assert _frontmatter(path)[1] == ["init", "coverage"]


def test_a_byte_order_mark_and_an_open_last_line_stay(tmp_path):
    path = _report(tmp_path)
    data = b"\xef\xbb\xbf" + path.read_bytes().rstrip(b"\n")
    path.write_bytes(data)
    assert _run(["fill-table", "--report", path, "--heading", "Evidence Sources"],
                _rows(["| react | T1 | none | 1.3 | /s/react/SKILL.md |"]))[1] == 0
    after = path.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf---\n")
    assert after.endswith(b"|----------|\n| react | T1 | none | 1.3 | /s/react/SKILL.md |")
    assert _run(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY))[1] == 0
    assert path.read_bytes().startswith(b"\xef\xbb\xbf---\n") and _frontmatter(path)[1] == ["init", "coverage"]


# --- The installed layout and the shared scripts ------------------------------------------


def _install(root, reader_file=True, writer_file=True, writer_text=None):
    """The installed layout: _bmad/skf/<skill>/scripts/ beside _bmad/skf/shared/scripts/."""
    script = root / "_bmad" / "skf" / "skf-verify-stack" / "scripts" / SCRIPT.name
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    shared = root / "_bmad" / "skf" / "shared" / "scripts"
    shared.mkdir(parents=True)
    if reader_file:
        (shared / READER_PATH.name).write_bytes(READER_PATH.read_bytes())
    if writer_file:
        data = WRITER_PATH.read_bytes() if writer_text is None else writer_text.encode("utf-8")
        (shared / WRITER_PATH.name).write_bytes(data)
    return script


def test_the_installed_layout_finds_the_shared_scripts(tmp_path):
    script = _install(tmp_path / "project")
    path = _report(tmp_path)
    code, out, _ = _call(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY), script)
    assert code == 0, out
    assert _frontmatter(path)[1] == ["init", "coverage"]
    assert mod.SHARED_READER == READER_PATH.resolve() and mod.ATOMIC_WRITER == WRITER_PATH.resolve()


@pytest.mark.parametrize("missing", ["reader", "writer"])
def test_a_missing_shared_script_exits_1(tmp_path, missing):
    script = _install(tmp_path / "project", reader_file=missing != "reader", writer_file=missing != "writer")
    path = _report(tmp_path)
    before = path.read_bytes()
    code, out, _ = _call(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY), script)
    assert (code, out["code"]) == (1, "HELPER_MISSING"), out
    name = READER_PATH.name if missing == "reader" else WRITER_PATH.name
    assert name in out["error"]
    assert path.read_bytes() == before


def test_a_failing_writer_leaves_the_report(tmp_path):
    failing = "import sys\nsys.stdin.buffer.read()\nsys.stderr.write('disk full')\nsys.exit(2)\n"
    script = _install(tmp_path / "project", writer_text=failing)
    path = _report(tmp_path)
    before = path.read_bytes()
    code, out, _ = _call(["set-counts", "--report", path, "--kind", "coverage"], _json(COVERAGE_TALLY), script)
    assert (code, out["code"]) == (3, "WRITE_FAILED"), out
    assert "disk full" in out["error"]
    assert path.read_bytes() == before
    # A call that changes nothing writes nothing, so the writer never runs.
    code, out, _ = _call(["fill-table", "--report", path, "--heading", "Integration Verdicts"], b"", script)
    assert (code, out["changed"]) == (0, False), out


def test_help_states_the_contract():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    for needle in ("set-counts", "fill-table", "replace-section", "requirements-skipped", "coverageReplaced",
                   "deltaUnchanged", "HELPER_MISSING", "WRITE_FAILED", "CRLF"):
        assert needle in proc.stdout, needle


def test_usage_errors_print_no_json(tmp_path):
    for args in (["set-counts", "--report", "r.md"], ["set-counts", "--report", "r.md", "--kind", "pairs"],
                 ["fill-table", "--report", "r.md"], ["replace-section", "--heading", "H"], []):
        code, out, proc = _call(args)
        assert code == 2 and out is None, args
        assert b"usage:" in proc.stderr, args


# --- The calls the stage files document ---------------------------------------------------


SCRIPTS = {"{coverageTallyScript}": TALLY, "{reportUpdateScript}": SCRIPT, "{verdictRollupScript}": ROLLUP}
BASH_BLOCK = re.compile(r"^```bash\n(.*?)^```\n", re.M | re.S)
# Where each stage's calls start: requirements.md §1 is the no-PRD path.
STAGES = (("coverage.md", "### 3."), ("integrations.md", "### 4."), ("requirements.md", "### 3."),
          ("synthesize.md", "### 1."))


def _documented_calls(name, start):
    """The tally, report-update and rollup calls of one stage file from `start`, in order."""
    text = (REFERENCES / name).read_text(encoding="utf-8")
    text = text[text.index(start):]
    calls = []
    for block in BASH_BLOCK.finditer(text):
        for line in block.group(1).splitlines():
            words = line.strip().split(" ", 3)
            if words[:2] == ["uv", "run"] and words[2] in SCRIPTS:
                calls.append(line.strip())
    return calls


def _run_documented(line, values):
    """Run one documented call as its shell line would: `< in` on stdin, `> out` saving stdout."""
    for key, value in values.items():
        line = line.replace(key, value)
    command, _, saved = line.partition(" > ")
    command, _, source = command.partition(" < ")
    words = shlex.split(command)
    stdin = Path(shlex.split(source)[0]).read_bytes() if source else b""
    proc = subprocess.run([sys.executable, str(SCRIPTS[words[2]]), *words[3:]], input=stdin, capture_output=True,
                          check=False)
    if saved:
        Path(shlex.split(saved)[0]).write_bytes(proc.stdout)
    return proc


def _fixture(tmp_path):
    """A run folder holding what the model writes: rows files, prose files and the inventory."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    files = {
        "coverage-rows.json": {"rows": [
            {"technology": "react", "section": "Stack", "skill": "react", "verdict": "Covered"},
            {"technology": "zod", "section": "Stack", "skill": "zod", "verdict": "Covered"},
            {"technology": "next", "section": "Stack", "skill": "next", "verdict": "Covered"},
            {"technology": "postgres", "section": "Data", "skill": None, "verdict": "Missing"},
            {"technology": "old-orm", "section": "Legacy", "skill": None, "verdict": "Replaced"}]},
        "integration-pairs.json": {"pairs": [["react", "zod"], ["next", "react"]]},
        "verdict-rows.json": {"rows": [
            {"lib_a": "react", "lib_b": "zod", "verdict": "Verified", "rationale": "zod cites react | line 4"},
            {"lib_a": "next", "lib_b": "react", "verdict": "Plausible", "rationale": "neither cites the other"}]},
        "cycles.json": {"cycles": [["next", "react", "zod", "next"]], "cycle_count": 1},
        "requirement-rows.json": {"rows": [{"requirement_id": "R1", "verdict": "Fulfilled"},
                                           {"requirement_id": "R2", "verdict": "Not Addressed"}]},
        "skill-inventory.json": {"skills": [
            {"name": "react", "path": "react/active/react", "evidence_tier": "T1", "confidence_tier": None,
             "metadata_schema_version": "1.3"},
            {"name": "zod", "path": "zod/active/zod", "evidence_tier": "T1-low", "confidence_tier": "Forge",
             "metadata_schema_version": "1.3"},
            {"name": "next", "path": "next", "evidence_tier": "T2", "confidence_tier": None,
             "metadata_schema_version": None}], "warnings": []},
        "delta.json": {"improvedCount": 1, "regressedCount": 0, "newCount": 2, "unchangedCount": 3},
    }
    for name, data in files.items():
        (run_dir / name).write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    prose = {
        "coverage-section.md": "| Technology | Source Section | Skill Match | Verdict |\n|---|---|---|---|\n\n"
                               "**Coverage: 3/4 (75%)**\n\n**Missing Skills:**\n- `postgres`\n",
        "integration-details.md": "| Library A | Library B | Context | Verdict | Evidence |\n|---|---|---|---|---|\n"
                                  "| react | zod | forms | Verified | line 4 |\n\n**Risky Integrations:**\n- cycle\n",
        "requirements-section.md": "| ID | Requirement | Category | Verdict | Contributing Skills |\n"
                                   "|---|---|---|---|---|\n| R1 | sync | feature | Fulfilled | react |\n",
        "executive-summary.md": "**Overall Verdict:** NOT_FEASIBLE\n\nA Missing technology and a cycle.\n",
        "recommendations.md": "1. Run [CS] for `postgres`.\n\n#### Delta from Previous Run\n\n- Improved: 1\n\n"
                              "**Suggested next workflow:** Apply the recommendations above and re-run **[VS]**.\n",
        "input-documents.md": "- Architecture: docs/architecture.md\n- PRD: docs/prd.md\n",
    }
    for name, text in prose.items():
        (run_dir / name).write_bytes(text.encode("utf-8"))
    return run_dir


def test_each_stage_documents_its_calls():
    calls = {name: _documented_calls(name, start) for name, start in STAGES}
    assert [len(calls[name]) for name, _ in STAGES] == [5, 5, 3, 8]
    # Synthesize records the verdict last, after the delta counts.
    assert calls["synthesize.md"][-2].startswith('uv run {reportUpdateScript} set-counts --report "{outputFile}" '
                                                 "--kind delta ")
    assert calls["synthesize.md"][-1] == ('uv run {reportUpdateScript} set-counts --report "{outputFile}" '
                                          '--kind synthesize < "{run_dir}/rollup.json"')


def test_the_documented_calls_write_a_report_the_consumers_read(tmp_path):
    run_dir = _fixture(tmp_path)
    report = _report(tmp_path)
    values = {"{run_dir}": run_dir.as_posix(), "{outputFile}": report.as_posix(),
              "{inventoryFile}": (run_dir / "skill-inventory.json").as_posix(),
              "{skills_output_folder}": (tmp_path / "skills").as_posix()}
    for name, start in STAGES:
        for line in _documented_calls(name, start):
            proc = _run_documented(line, values)
            assert proc.returncode == 0, (name, line, proc.stdout, proc.stderr)
        if name == "requirements.md":
            requirements = _body(report.read_text(encoding="utf-8"), "Recommendations")

    check = subprocess.run([sys.executable, str(READER_PATH), str(report)], capture_output=True, check=False)
    assert check.returncode == 0, check.stdout
    fields, steps = _frontmatter(report)
    assert steps == ["init", "coverage", "integrations", "requirements", "synthesize"]
    # The rollup reads the counts the helpers wrote, and its verdict and count are recorded verbatim.
    rollup = _load("skf_verdict_rollup_update", ROLLUP)
    proc = subprocess.run([sys.executable, str(ROLLUP), "--report", str(report)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert out == rollup.rollup({"coveragePercentage": 75, "coveredCount": 3, "missingCount": 1, "replacedCount": 1,
                                 "pairsVerified": 1, "pairsPlausible": 1, "pairsRisky": 1, "pairsBlocked": 0,
                                 "requirementsEvaluated": True, "requirementsNotAddressed": 1,
                                 "requirementsPartial": 0})
    assert (fields["overallVerdict"], fields["recommendationCount"]) == (out["overallVerdict"],
                                                                         str(out["recommendationCount"]))
    assert (fields["deltaImproved"], fields["deltaNew"], fields["requirementsPass"]) == ("1", "2", "completed")
    # The next run's delta reads the coverage, verdict and tier findings back.
    delta = _load("skf_report_delta_update", DELTA)
    side, tiers = delta.read_report(str(report), delta.load_reader(), with_tiers=True)
    assert side["coverage"] == [{"technology": t, "verdict": v} for t, v in (
        ("react", "Covered"), ("zod", "Covered"), ("next", "Covered"), ("postgres", "Missing"),
        ("old-orm", "Replaced"))]
    assert side["integration"] == [{"libA": "react", "libB": "zod", "verdict": "Verified"},
                                   {"libA": "next", "libB": "react", "verdict": "Plausible"},
                                   {"libA": "cycle", "libB": "next → react → zod → next",
                                    "verdict": "Risky"}]
    assert tiers == {"react": "T1", "zod": "T1-low", "next": "T2"}
    # The requirements subsection is as its stage wrote it, and the prioritized list
    # follows it, ending with the suggested next workflow.
    text = report.read_text(encoding="utf-8")
    body = _body(text, "Recommendations")
    assert body[:len(requirements) - 2] == requirements[:-2]
    prioritized = body.index("### Prioritized Recommendations")
    assert body.index("### Requirements Coverage") < prioritized
    assert [line for line in body if line.strip()][-2].startswith("**Suggested next workflow:**")
    assert "{1-2 sentence summary}" not in text and "A Missing technology and a cycle." in text
    details = _body(text, "Integration Verdicts")
    assert details.index("### Integration Details") > details.index(VERDICT_HEADER)
    assert text.endswith("### Input Documents\n\n- Architecture: docs/architecture.md\n- PRD: docs/prd.md\n")


def test_the_skipped_requirements_pass_reaches_the_rollup(tmp_path):
    text = (REFERENCES / "requirements.md").read_text(encoding="utf-8")
    skipped = text[text.index("### 1."):text.index("### 2.")]
    [line] = [line for block in BASH_BLOCK.finditer(skipped) for line in block.group(1).splitlines()]
    report = _report(tmp_path, steps="['init', 'coverage', 'integrations']")
    proc = _run_documented(line, {"{outputFile}": report.as_posix()})
    assert proc.returncode == 0, proc.stdout
    fields, steps = _frontmatter(report)
    assert fields["requirementsPass"] == "skipped" and steps[-1] == "requirements"
    assert mod.counts_to_set("requirements-skipped", None) == {"requirementsPass": '"skipped"'}
