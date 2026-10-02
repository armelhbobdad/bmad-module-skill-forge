#!/usr/bin/env python3
"""Tests for skf-validate-feasibility-report.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-validate-feasibility-report.py"
)

spec = importlib.util.spec_from_file_location(
    "skf_validate_feasibility_report", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_report = mod.validate_report
split_frontmatter = mod.split_frontmatter
scan_headings = mod.scan_headings
slugify = mod.slugify
locate_report = mod.locate_report
read_verdict_table = mod.read_verdict_table
frontmatter_list = mod.frontmatter_list


def _report(schema_version='"1.0"', sections=None):
    """Build a feasibility-report string.

    `sections` is the ordered list of body headings to emit; defaults to the
    canonical order. Each section gets a line of filler body, and the
    Integration Verdicts section also gets the canonical table, empty.
    """
    if sections is None:
        sections = [
            "Executive Summary",
            "Coverage Analysis",
            "Integration Verdicts",
            "Recommendations",
            "Evidence Sources",
        ]
    fm_lines = ["---"]
    if schema_version is not None:
        fm_lines.append(f"schemaVersion: {schema_version}")
    fm_lines.append("reportType: feasibility")
    fm_lines.append('overallVerdict: "FEASIBLE"')
    fm_lines.append("---")
    body_lines = ["", "# Feasibility Report", ""]
    for s in sections:
        body_lines.append(f"## {s}")
        body_lines.append("")
        body_lines.append(f"Body text for {s}.")
        body_lines.append("")
        if s == "Integration Verdicts":
            body_lines.append("| lib_a | lib_b | verdict | rationale |")
            body_lines.append("|-------|-------|---------|-----------|")
            body_lines.append("")
    return "\n".join(fm_lines + body_lines) + "\n"


def _write(tmp_path, content, name="report.md"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- (1) valid report -------------------------------------------------------


def test_valid_report_passes(tmp_path):
    p = _write(tmp_path, _report())
    result, code = validate_report(str(p))
    assert code == 0
    assert result["status"] == "ok"
    assert result["headingsOk"] is True
    assert result["schemaVersionOk"] is True
    assert result["schemaVersionFound"] == "1.0"
    assert result["missingHeadings"] == []
    assert result["orderViolations"] == []
    assert result["violation"] is None


# --- (2) out-of-order sections ---------------------------------------------


def test_out_of_order_sections_fail(tmp_path):
    # Recommendations placed before Integration Verdicts.
    p = _write(
        tmp_path,
        _report(
            sections=[
                "Executive Summary",
                "Coverage Analysis",
                "Recommendations",
                "Integration Verdicts",
                "Evidence Sources",
            ]
        ),
    )
    result, code = validate_report(str(p))
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["headingsOk"] is False
    assert result["missingHeadings"] == []
    assert result["orderViolations"], "expected a non-empty orderViolations list"
    # schemaVersion itself is fine here.
    assert result["schemaVersionOk"] is True


# --- (3) missing section ----------------------------------------------------


def test_missing_section_fail(tmp_path):
    p = _write(
        tmp_path,
        _report(
            sections=[
                "Executive Summary",
                "Coverage Analysis",
                "Integration Verdicts",
                "Recommendations",
                # Evidence Sources omitted
            ]
        ),
    )
    result, code = validate_report(str(p))
    assert code == 1
    assert result["violation"] == "schema-violation"
    assert "Evidence Sources" in result["missingHeadings"]
    assert result["headingsOk"] is False


# --- (4) schemaVersion mismatch --------------------------------------------


def test_schema_version_mismatch_fail(tmp_path):
    p = _write(tmp_path, _report(schema_version='"2.0"'))
    result, code = validate_report(str(p))
    assert code == 1
    assert result["schemaVersionOk"] is False
    assert result["schemaVersionFound"] == "2.0"
    assert result["violation"] == "schema-violation"
    # Headings are correct — only the version is wrong.
    assert result["headingsOk"] is True


# --- (5) schemaVersion absent ----------------------------------------------


def test_schema_version_absent_fail(tmp_path):
    p = _write(tmp_path, _report(schema_version=None))
    result, code = validate_report(str(p))
    assert code == 1
    assert result["schemaVersionOk"] is False
    assert result["schemaVersionFound"] is None
    assert result["violation"] == "schema-violation"


# --- IO error ---------------------------------------------------------------


def test_missing_file_io_error(tmp_path):
    result, code = validate_report(str(tmp_path / "does-not-exist.md"))
    assert code == 2
    assert result["status"] == "error"
    assert result["violation"] == "io-error"
    # The values earlier callers read stay; the read keys say nothing was read.
    assert result["schemaVersionOk"] is False
    assert result["headingsOk"] is False
    assert result["schemaVersion"] is None
    assert result["overallVerdict"] is None
    assert result["coverageMeasured"] is None
    assert result["pairVerdicts"] == []
    assert set(result) == VALIDATE_KEYS | {"error"}


# --- helper-level unit checks ----------------------------------------------


def test_split_frontmatter_quotes_stripped(tmp_path):
    fm, body = split_frontmatter(_report())
    assert fm["schemaVersion"] == "1.0"
    assert "## Executive Summary" in body


def test_split_frontmatter_no_frontmatter():
    content = "# Just a body\n\n## Executive Summary\n"
    fm, body = split_frontmatter(content)
    assert fm == {}
    assert body == content


def test_scan_headings_ignores_level_three():
    # A '### Executive Summary' must NOT satisfy the level-2 requirement.
    body = "### Executive Summary\n## Coverage Analysis\n"
    missing, _ = scan_headings(body)
    assert "Executive Summary" in missing


def test_scan_headings_first_occurrence_used():
    body = "\n".join(
        [
            "## Executive Summary",
            "## Coverage Analysis",
            "## Integration Verdicts",
            "## Recommendations",
            "## Evidence Sources",
        ]
    )
    missing, violations = scan_headings(body)
    assert missing == []
    assert violations == []


# --- CLI exit-code smoke test ----------------------------------------------


def test_cli_exit_codes(tmp_path):
    valid = _write(tmp_path, _report(), name="valid.md")
    bad = _write(tmp_path, _report(schema_version='"9.9"'), name="bad.md")

    ok = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(valid)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0
    payload = json.loads(ok.stdout)
    assert payload["status"] == "ok"

    fail = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(bad)],
        capture_output=True,
        text=True,
    )
    assert fail.returncode == 1
    payload = json.loads(fail.stdout)
    assert payload["schemaVersionFound"] == "9.9"

    err = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(tmp_path / "nope.md")],
        capture_output=True,
        text=True,
    )
    assert err.returncode == 2


# The keys both modes check and read the same way (read_report()): an explicit
# report path gets the JSON a located report gets.
READ_KEYS = {
    "status",
    "path",
    "schemaVersion",
    "schemaVersionOk",
    "headingsOk",
    "missingHeadings",
    "orderViolations",
    "generatedAt",
    "overallVerdict",
    "coveragePercentage",
    "coverageMeasured",
    "verdictTableFound",
    "duplicateVerdictTableLine",
    "pairVerdicts",
    "unknownTokens",
    "violation",
}

# Validate mode also keeps schemaVersionFound, the name earlier callers read.
VALIDATE_KEYS = READ_KEYS | {"schemaVersionFound"}


def test_validate_mode_keys(tmp_path):
    result, _ = validate_report(str(_write(tmp_path, _report())))
    assert set(result) == VALIDATE_KEYS
    assert result["schemaVersionFound"] == result["schemaVersion"] == "1.0"


# --- slug rule (--locate) --------------------------------------------------


@pytest.mark.parametrize(
    "name,slug",
    [
        ("My Project", "my-project"),
        # NFKD: an accented Latin letter keeps its base letter.
        ("Café Déjà Vu", "cafe-deja-vu"),
        # Punctuation to hyphen, repeats collapsed, both ends trimmed.
        ("Acme__Platform!!v2", "acme-platform-v2"),
        ("  --Trim me--  ", "trim-me"),
        ("C++ & Rust", "c-rust"),
        # Compatibility forms fold to ASCII: full-width letters, ligature, superscript.
        ("Ｆｕｌｌ ﬁle x²", "full-file-x2"),
        # Punctuation of any script becomes a hyphen too (en dash, middle dot).
        ("Acme–Platform·API", "acme-platform-api"),
        # A letter with no ASCII form is dropped.
        ("Straße", "strae"),
        ("Проект Alpha", "alpha"),
        # Nothing left: the fallback slug, an empty name included.
        ("日本語", "project"),
        ("", "project"),
        ("already-a-slug", "already-a-slug"),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug
    assert slugify(slug) == slug  # idempotent


# --- locate mode -------------------------------------------------------------

PAIR_ROWS = [
    ("react", "vite", "Verified", '"see also: vite" in react SKILL.md line 12'),
    ("vite", "zod", "Plausible", "no literal cross-reference"),
    ("zod", "tauri", "Blocked", "TypeScript to Rust with no bridge"),
]


def _verdict_table(rows, header="| lib_a | lib_b | verdict | rationale |"):
    lines = [header, "|-------|-------|---------|-----------|"]
    lines += [f"| {a} | {b} | {v} | {r} |" for a, b, v, r in rows]
    return "\n".join(lines)


def _full_report(
    overall='"NOT_FEASIBLE"', schema_version='"1.0"', verdicts=None, extra_frontmatter=()
):
    """A report shaped like skf-verify-stack's feasibility-report-template.md.

    `verdicts` is the Integration Verdicts section body; defaults to the
    canonical table over PAIR_ROWS followed by the producer's display table.
    `extra_frontmatter` lines are appended to the frontmatter as written.
    """
    if verdicts is None:
        verdicts = "\n".join(
            [
                _verdict_table(PAIR_ROWS),
                "",
                "| Library A | Library B | Context | Verdict | Evidence |",
                "|---|---|---|---|---|",
                "| react | vite | bundles the app | Risky | none |",
            ]
        )
    fm = ["---"]
    if schema_version is not None:
        fm.append(f"schemaVersion: {schema_version}")
    fm += ["reportType: feasibility", 'projectName: "My Project"', 'projectSlug: "my-project"']
    if overall is not None:
        fm.append(f"overallVerdict: {overall}")
    fm += ["pairsVerified: 1", "pairsPlausible: 1", "pairsRisky: 0", "pairsBlocked: 1"]
    fm += [*extra_frontmatter, "---"]
    body = [
        "",
        "# Stack Feasibility Report: My Project",
        "",
        "## Executive Summary",
        "",
        "**Overall Verdict:** NOT_FEASIBLE",
        "",
        "## Coverage Analysis",
        "",
        "| Technology | Verdict |",
        "|---|---|",
        "| react | Covered |",
        "",
        "## Integration Verdicts",
        "",
        verdicts,
        "",
        "## Recommendations",
        "",
        "Replace tauri.",
        "",
        "## Evidence Sources",
        "",
    ]
    return "\n".join(fm + body)


def _write_latest(folder, content, slug="my-project"):
    folder.mkdir(parents=True, exist_ok=True)
    return _write(folder, content, name=f"feasibility-report-{slug}-latest.md")


def _pairs(rows):
    return [{"lib_a": a, "lib_b": b, "verdict": v, "rationale": r} for a, b, v, r in rows]


def test_locate_reads_latest_report(tmp_path):
    latest = _write_latest(tmp_path, _full_report())
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["status"] == "ok"
    assert result["projectSlug"] == "my-project"
    assert result["path"] == str(latest)
    assert result["latestPath"] == str(latest)
    assert result["schemaVersion"] == "1.0"
    assert result["schemaVersionOk"] is True
    assert result["overallVerdict"] == "NOT_FEASIBLE"
    assert result["verdictTableFound"] is True
    assert result["duplicateVerdictTableLine"] is None
    # The canonical table only: the display table's Risky row is not read.
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)
    assert result["unknownTokens"] == []
    assert result["violation"] is None


LOCATE_KEYS = READ_KEYS | {"projectName", "projectSlug", "latestPath"}


def test_locate_result_keys(tmp_path):
    # One shape whatever the status; `error` is added on an io-error only.
    missing, _ = locate_report(str(tmp_path), "My Project")
    assert set(missing) == LOCATE_KEYS
    _write_latest(tmp_path, _full_report())
    found, _ = locate_report(str(tmp_path), "My Project")
    assert set(found) == LOCATE_KEYS
    _write_latest(tmp_path, _full_report(schema_version='"2.0"'))
    mismatch, _ = locate_report(str(tmp_path), "My Project")
    assert set(mismatch) == LOCATE_KEYS
    tmp_path.joinpath("feasibility-report-my-project-latest.md").write_bytes(b"\xff\xfe")
    unreadable, _ = locate_report(str(tmp_path), "My Project")
    assert set(unreadable) == LOCATE_KEYS | {"error"}


def test_locate_applies_the_slug_rule(tmp_path):
    latest = _write_latest(tmp_path, _full_report(), slug="cafe-deja-vu")
    result, code = locate_report(str(tmp_path), "Café Déjà Vu")
    assert code == 0
    assert result["projectName"] == "Café Déjà Vu"
    assert result["projectSlug"] == "cafe-deja-vu"
    assert result["path"] == str(latest)


@pytest.mark.parametrize("name", ["", "  ", "日本語"])
def test_locate_name_that_leaves_no_slug(tmp_path, name):
    # The slug rule holds for every name: nothing left gives `project`.
    latest = _write_latest(tmp_path, _full_report(), slug="project")
    result, code = locate_report(str(tmp_path), name)
    assert code == 0
    assert result["projectSlug"] == "project"
    assert result["path"] == str(latest)


def test_locate_picks_latest_over_newer_timestamped_report(tmp_path):
    _write_latest(tmp_path, _full_report(overall='"NOT_FEASIBLE"'))
    # A later timestamped report (a halted run's partial one, say) is ignored.
    _write(
        tmp_path,
        _full_report(overall='"FEASIBLE"'),
        name="feasibility-report-my-project-20991231-235959.md",
    )
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["overallVerdict"] == "NOT_FEASIBLE"
    assert result["path"].endswith("feasibility-report-my-project-latest.md")


def test_locate_ignores_other_projects_reports(tmp_path):
    _write_latest(tmp_path, _full_report(overall='"NOT_FEASIBLE"'))
    _write_latest(tmp_path, _full_report(overall='"FEASIBLE"'), slug="my-project-api")
    mine, _ = locate_report(str(tmp_path), "My Project")
    other, _ = locate_report(str(tmp_path), "My Project API")
    assert mine["overallVerdict"] == "NOT_FEASIBLE"
    assert other["overallVerdict"] == "FEASIBLE"
    assert other["projectSlug"] == "my-project-api"


def test_locate_not_found_with_only_timestamped_reports(tmp_path):
    _write(tmp_path, _full_report(), name="feasibility-report-my-project-20260930-101010.md")
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["status"] == "not-found"
    assert result["path"] is None
    assert result["latestPath"] == str(tmp_path / "feasibility-report-my-project-latest.md")
    # Nothing was read, so nothing reads as a schema mismatch either.
    assert result["schemaVersionOk"] is None
    assert result["verdictTableFound"] is None
    assert result["duplicateVerdictTableLine"] is None
    assert result["pairVerdicts"] == []
    assert result["violation"] is None


def test_locate_not_found_when_folder_is_missing(tmp_path):
    result, code = locate_report(str(tmp_path / "no-such-folder"), "My Project")
    assert code == 0
    assert result["status"] == "not-found"
    assert result["projectSlug"] == "my-project"


def test_locate_zero_pairs(tmp_path):
    _write_latest(tmp_path, _full_report(overall='"CONDITIONALLY_FEASIBLE"', verdicts=_verdict_table([])))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["status"] == "ok"
    assert result["verdictTableFound"] is True
    assert result["pairVerdicts"] == []


def test_locate_reads_only_the_table_in_its_section(tmp_path):
    # A canonical-looking table under another heading is not the verdict table.
    content = _full_report(verdicts="No table here.").replace(
        "Replace tauri.", _verdict_table([("a", "b", "Verified", "elsewhere")])
    )
    _write_latest(tmp_path, content)
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["verdictTableFound"] is False
    assert result["pairVerdicts"] == []


def test_locate_skips_fenced_code(tmp_path):
    verdicts = "\n".join(
        [
            "```markdown",
            _verdict_table([("fenced", "example", "Verified", "not a finding")]),
            "## Not a heading",
            "```",
            "",
            _verdict_table(PAIR_ROWS[:1]),
        ]
    )
    _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS[:1])


def test_locate_skips_html_comments(tmp_path):
    verdicts = "\n".join(
        [
            # A canonical example table in a comment is not the verdict table,
            # and a heading in a comment does not end the section.
            "<!-- The header is fixed, for example:",
            _verdict_table([("commented", "example", "Verified", "not a finding")]),
            "## Not a heading",
            "-->",
            # A comment that closes on its own line hides nothing after it.
            "<!-- one line -->",
            # `<!--` in fenced code opens no comment.
            "```html",
            "<!-- not a comment",
            "```",
            _verdict_table(PAIR_ROWS),
        ]
    )
    _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)
    assert result["duplicateVerdictTableLine"] is None


# The Integration Verdicts section of skf-verify-stack's
# feasibility-report-template.md: a comment, then the empty canonical table.
TEMPLATE_VERDICTS = "\n".join(
    [
        "<!-- Appended by integrations.",
        "Consumers grep for the `## Integration Verdicts` heading to locate the pair table.",
        "The table header is fixed and MUST be emitted exactly as shown below: -->",
        "",
        "| lib_a | lib_b | verdict | rationale |",
        "|-------|-------|---------|-----------|",
    ]
)


def test_locate_reads_the_template_table_filled_in_place(tmp_path):
    rows = [f"| {a} | {b} | {v} | {r} |" for a, b, v, r in PAIR_ROWS]
    _write_latest(tmp_path, _full_report(verdicts="\n".join([TEMPLATE_VERDICTS, *rows])))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)


def _header_lines(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    return [n for n, text in enumerate(lines, 1) if text == "| lib_a | lib_b | verdict | rationale |"]


def test_locate_rejects_a_table_appended_below_the_templates(tmp_path):
    # The template's empty table left in place and the filled one appended
    # below it: reading the first alone would drop the Blocked pair.
    verdicts = "\n".join([TEMPLATE_VERDICTS, "", _verdict_table(PAIR_ROWS)])
    latest = _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["verdictTableFound"] is True
    assert result["duplicateVerdictTableLine"] == _header_lines(latest)[1]
    assert result["unknownTokens"] == []


def test_locate_rejects_a_table_in_a_repeated_verdicts_section(tmp_path):
    content = _full_report(verdicts=_verdict_table([]))
    content += "\n## Integration Verdicts\n\n" + _verdict_table(PAIR_ROWS) + "\n"
    latest = _write_latest(tmp_path, content)
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["violation"] == "schema-violation"
    assert result["duplicateVerdictTableLine"] == _header_lines(latest)[1]


@pytest.mark.parametrize(
    "after",
    [
        "```markdown\n" + _verdict_table([("fenced", "example", "Verified", "x")]) + "\n```",
        "<!--\n" + _verdict_table([("commented", "example", "Verified", "x")]) + "\n-->",
        # A header row with no delimiter row is not a table.
        "| lib_a | lib_b | verdict | rationale |\n\nSee above.",
        # A table under another heading is not in the section.
        "## Appendix\n\n" + _verdict_table([("elsewhere", "example", "Verified", "x")]),
    ],
    ids=["fenced", "comment", "no-delimiter", "other-section"],
)
def test_locate_second_table_look_alikes(tmp_path, after):
    verdicts = "\n".join([_verdict_table(PAIR_ROWS), "", after])
    _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["duplicateVerdictTableLine"] is None
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)


def test_locate_reads_a_report_with_a_byte_order_mark(tmp_path):
    # An editor that saves with a BOM must not hide the frontmatter.
    latest = tmp_path / "feasibility-report-my-project-latest.md"
    latest.write_text("\ufeff" + _full_report(), encoding="utf-8")
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["schemaVersion"] == "1.0"
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)


def test_validate_reads_a_report_with_a_byte_order_mark(tmp_path):
    p = tmp_path / "report.md"
    p.write_text("\ufeff" + _report(), encoding="utf-8")
    result, code = validate_report(str(p))
    assert code == 0
    assert result["schemaVersionFound"] == "1.0"


def test_locate_unknown_pair_tokens(tmp_path):
    rows = [
        ("react", "vite", "Verified", "fine"),
        ("vite", "zod", "verified", "lower case"),
        ("zod", "tauri", "Plausible (capped)", "annotated"),
    ]
    latest = _write_latest(tmp_path, _full_report(verdicts=_verdict_table(rows)))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    # Never dropped or mapped: every row stays as written.
    assert result["pairVerdicts"] == _pairs(rows)
    tokens = result["unknownTokens"]
    assert [(t["field"], t["lib_a"], t["lib_b"], t["token"]) for t in tokens] == [
        ("verdict", "vite", "zod", "verified"),
        ("verdict", "zod", "tauri", "Plausible (capped)"),
    ]
    # `line` is the row's 1-based line in the report file.
    file_lines = latest.read_text(encoding="utf-8").split("\n")
    for token in tokens:
        assert f"| {token['token']} |" in file_lines[token["line"] - 1]


def test_locate_unknown_overall_token(tmp_path):
    _write_latest(tmp_path, _full_report(overall='"Feasible"'))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["overallVerdict"] == "Feasible"
    assert result["unknownTokens"] == [{"field": "overallVerdict", "token": "Feasible"}]


def test_locate_missing_overall_verdict(tmp_path):
    _write_latest(tmp_path, _full_report(overall=None))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["unknownTokens"] == [{"field": "overallVerdict", "token": None}]


@pytest.mark.parametrize("schema_version,found", [('"2.0"', "2.0"), (None, None)])
def test_locate_schema_version_mismatch_is_not_interpreted(tmp_path, schema_version, found):
    _write_latest(tmp_path, _full_report(schema_version=schema_version))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["schemaVersion"] == found
    assert result["schemaVersionOk"] is False
    # An unknown version is never interpreted: no verdict is read from it.
    assert result["overallVerdict"] is None
    assert result["verdictTableFound"] is None
    assert result["duplicateVerdictTableLine"] is None
    assert result["pairVerdicts"] == []
    assert result["unknownTokens"] == []


def test_locate_requires_the_canonical_header(tmp_path):
    verdicts = _verdict_table(PAIR_ROWS, header="| Library A | Library B | Verdict | Rationale |")
    _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["verdictTableFound"] is False
    assert result["violation"] == "schema-violation"


def test_locate_requires_a_delimiter_row(tmp_path):
    verdicts = "| lib_a | lib_b | verdict | rationale |\n| react | vite | Verified | x |"
    _write_latest(tmp_path, _full_report(verdicts=verdicts))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["verdictTableFound"] is False


def test_read_verdict_table_cells():
    body = "\n".join(
        [
            "## Integration Verdicts",
            "",
            "| lib_a | lib_b | verdict | rationale |",
            "|:------|:-----:|--------:|-----------|",
            r"| react | vite | Verified | uses `a \| b` |",
            "| vite | zod | Risky | split | by a pipe |",
            "| zod | tauri |",
            "",
            "| after | the | Verified | blank line |",
        ]
    )
    found, rows, duplicate_line = read_verdict_table(body, first_line=10)
    assert found is True
    assert rows == [
        (14, ["react", "vite", "Verified", "uses `a | b`"]),
        (15, ["vite", "zod", "Risky", "split | by a pipe"]),
        (16, ["zod", "tauri", "", ""]),
    ]
    assert duplicate_line is None


def test_read_verdict_table_duplicate_line():
    body = "\n".join(
        [
            "## Integration Verdicts",
            "| lib_a | lib_b | verdict | rationale |",
            "|---|---|---|---|",
            "",
            "### Detail",
            "| lib_a | lib_b | verdict | rationale |",
            "|---|---|---|---|",
            "| react | vite | Blocked | a subheading keeps the section |",
        ]
    )
    found, rows, duplicate_line = read_verdict_table(body, first_line=10)
    assert found is True
    assert rows == []  # the first table's rows
    assert duplicate_line == 15


def test_locate_unreadable_report_is_io_error(tmp_path):
    tmp_path.joinpath("feasibility-report-my-project-latest.md").write_bytes(b"---\n\xff\xfe\n---\n")
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 2
    assert result["status"] == "error"
    assert result["violation"] == "io-error"
    assert result["path"].endswith("feasibility-report-my-project-latest.md")
    assert "could not read report file" in result["error"]


# --- locate mode CLI ----------------------------------------------------------


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
    )


def test_cli_locate_exit_codes(tmp_path):
    forge = tmp_path / "forge"
    _write_latest(forge, _full_report())

    ok = _run("--locate", str(forge), "--project-name", "My Project")
    assert ok.returncode == 0
    payload = json.loads(ok.stdout)
    assert payload["status"] == "ok"
    assert payload["pairVerdicts"] == _pairs(PAIR_ROWS)

    missing = _run("--locate", str(forge), "--project-name", "Another Project")
    assert missing.returncode == 0
    assert json.loads(missing.stdout)["status"] == "not-found"

    _write_latest(forge, _full_report(overall='"Feasible"'), slug="bad-tokens")
    bad = _run("--locate", str(forge), "--project-name", "Bad Tokens")
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["unknownTokens"]

    # An empty name is not a usage error: it gets the fallback slug.
    empty = _run("--locate", str(forge), "--project-name", "")
    assert empty.returncode == 0
    assert json.loads(empty.stdout)["projectSlug"] == "project"


def test_cli_locate_writes_output_file(tmp_path):
    _write_latest(tmp_path, _full_report())
    out = tmp_path / "result.json"
    run = _run("--locate", str(tmp_path), "--project-name", "My Project", "-o", str(out))
    assert run.returncode == 0
    assert run.stdout == ""
    assert json.loads(out.read_text(encoding="utf-8"))["overallVerdict"] == "NOT_FEASIBLE"


@pytest.mark.parametrize(
    "argv",
    [
        ["--locate", "forge"],  # --project-name missing
        ["--locate", "", "--project-name", "My Project"],  # empty folder
        ["--locate", "  ", "--project-name", "My Project"],  # blank folder
        ["report.md", "--project-name", "My Project"],  # name without --locate
        ["report.md", "--locate", "forge", "--project-name", "My Project"],  # both modes
        [],  # neither mode
        # An unquoted path that holds a space splits in two: a caller's
        # malformed call, never a finding about the report.
        ["--locate", "/data/First", "Last/forge", "--project-name", "My Project"],
        ["/data/First", "Last/report.md"],
    ],
)
def test_cli_usage_errors(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        mod.main(argv)
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""  # no JSON verdict on a usage error
    # The parser itself refuses them, so a caller that only parses (the
    # helper-call contract test) sees the same errors as main().
    with pytest.raises(SystemExit) as excinfo:
        mod._build_parser().parse_args(argv)
    assert excinfo.value.code == 2


# --- validate mode reads a report path as --locate reads -latest ------------


def _write_report_and_latest(tmp_path, content):
    """The same text as an explicit report and as the project's -latest copy."""
    report = _write(tmp_path, content, name="feasibility-report-my-project-20260930-101010.md")
    _write_latest(tmp_path, content)
    return report


# The template's empty canonical table with a filled one appended below it.
DUPLICATE_VERDICTS = "\n".join([TEMPLATE_VERDICTS, "", _verdict_table(PAIR_ROWS)])

# Reports that exercise every outcome of read_report().
SAME_JSON_REPORTS = {
    "ok": _full_report(),
    "schema-mismatch": _full_report(schema_version='"2.0"'),
    "duplicate-table": _full_report(verdicts=DUPLICATE_VERDICTS),
    "unknown-tokens": _full_report(
        overall='"Feasible"', verdicts=_verdict_table([("react", "vite", "risky", "lower case")])
    ),
    "no-table": _full_report(verdicts="No table here."),
    "missing-section": _full_report().replace("## Recommendations", "## Advice"),
    "coverage-measured": _full_report(
        extra_frontmatter=['generatedAt: "2026-09-30T10:00:00Z"', "coveragePercentage: 80",
                           "stepsCompleted: ['init', 'coverage', 'integrations']"]
    ),
}


@pytest.mark.parametrize("name", sorted(SAME_JSON_REPORTS))
def test_report_path_gives_the_located_json(tmp_path, name):
    # An explicit report path (validate mode) and the located -latest copy get
    # the same checks, the same keys and the same exit code.
    report = _write_report_and_latest(tmp_path, SAME_JSON_REPORTS[name])
    validated, validate_code = validate_report(str(report))
    located, locate_code = locate_report(str(tmp_path), "My Project")
    assert validate_code == locate_code
    for key in READ_KEYS - {"path"}:
        assert validated[key] == located[key], key
    assert validated["path"] == str(report)
    assert located["path"] == str(tmp_path / "feasibility-report-my-project-latest.md")


def test_validate_reads_verdicts_and_coverage(tmp_path):
    frontmatter = ['generatedAt: "2026-09-30T10:00:00Z"', "coveragePercentage: 80",
                   "stepsCompleted: ['init', 'coverage']"]
    report = _write(tmp_path, _full_report(extra_frontmatter=frontmatter))
    result, code = validate_report(str(report))
    assert code == 0
    assert result["status"] == "ok"
    assert result["overallVerdict"] == "NOT_FEASIBLE"
    assert result["generatedAt"] == "2026-09-30T10:00:00Z"
    assert result["coveragePercentage"] == 80
    assert result["coverageMeasured"] is True
    assert result["verdictTableFound"] is True
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)
    assert result["unknownTokens"] == []


@pytest.mark.parametrize(
    "verdicts,overall,check",
    [
        ("No table here.", '"NOT_FEASIBLE"', "no-table"),
        (DUPLICATE_VERDICTS, '"NOT_FEASIBLE"', "duplicate"),
        (_verdict_table([("react", "vite", "Verified (capped)", "x")]), '"NOT_FEASIBLE"',
         "pair-token"),
        (_verdict_table(PAIR_ROWS), '"feasible"', "overall-token"),
    ],
    ids=["no-table", "duplicate-table", "unknown-pair-token", "unknown-overall-token"],
)
def test_validate_fails_on_the_verdict_table_and_tokens(tmp_path, verdicts, overall, check):
    # The sections and schemaVersion are fine: the verdict table or a token
    # alone makes the report a schema violation, as it does for --locate.
    report = _write(tmp_path, _full_report(overall=overall, verdicts=verdicts))
    result, code = validate_report(str(report))
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["headingsOk"] is True
    assert result["schemaVersionOk"] is True
    if check == "no-table":
        assert result["verdictTableFound"] is False
    elif check == "duplicate":
        assert result["duplicateVerdictTableLine"] is not None
    else:
        assert result["unknownTokens"]


def test_validate_cli_emits_the_read_keys(tmp_path):
    frontmatter = ["coveragePercentage: 64", "stepsCompleted: [init, coverage]"]
    report = _write(tmp_path, _full_report(extra_frontmatter=frontmatter))
    run = _run(str(report))
    assert run.returncode == 0, run.stderr
    payload = json.loads(run.stdout)
    assert set(payload) == VALIDATE_KEYS
    assert payload["coveragePercentage"] == 64
    assert payload["coverageMeasured"] is True
    assert payload["pairVerdicts"] == _pairs(PAIR_ROWS)


def test_locate_checks_the_sections(tmp_path):
    _write_latest(tmp_path, _full_report().replace("## Evidence Sources", "## Sources"))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["headingsOk"] is False
    assert result["missingHeadings"] == ["Evidence Sources"]
    # The rest of the report is still read.
    assert result["pairVerdicts"] == _pairs(PAIR_ROWS)


def test_locate_not_found_reads_nothing(tmp_path):
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0
    assert result["headingsOk"] is None
    assert result["missingHeadings"] == [] and result["orderViolations"] == []
    assert result["generatedAt"] is None
    assert result["coveragePercentage"] is None
    assert result["coverageMeasured"] is None


# --- coveragePercentage, coverageMeasured and generatedAt --------------------


@pytest.mark.parametrize(
    "frontmatter,percentage,measured",
    [
        (["coveragePercentage: 80", "stepsCompleted: ['init', 'coverage']"], 80, True),
        (["coveragePercentage: 0", 'stepsCompleted: ["init", "coverage", "integrations"]'],
         0, True),
        (["coveragePercentage: 100", "stepsCompleted: [init, coverage]"], 100, True),
        (["coveragePercentage: '75'", "stepsCompleted:", "  - init", "  - 'coverage'"], 75, True),
        (["coveragePercentage: 75", "stepsCompleted:", "- init", "- coverage  # measured"],
         75, True),
        (["coveragePercentage: 75", "stepsCompleted: ['init',", "  'coverage']"], 75, True),
        # A run that stopped before its coverage step holds the 0 it started with.
        (["coveragePercentage: 0", "stepsCompleted: ['init']"], 0, False),
        (["coveragePercentage: 0", "stepsCompleted: []"], 0, False),
        (["coveragePercentage: 0"], 0, False),
        (["coveragePercentage: 90", "stepsCompleted: coverage"], 90, False),
        (["coveragePercentage: 90", "stepsCompleted: ['coverage-draft']"], 90, False),
        # A value that is no whole percentage is not recorded, measured or not.
        (["coveragePercentage: 87.5", "stepsCompleted: ['init', 'coverage']"], None, False),
        (["coveragePercentage: 101", "stepsCompleted: ['init', 'coverage']"], None, False),
        (["coveragePercentage: -3", "stepsCompleted: ['init', 'coverage']"], None, False),
        (["coveragePercentage: ''", "stepsCompleted: ['init', 'coverage']"], None, False),
        (["stepsCompleted: ['init', 'coverage']"], None, False),
        (["coveragePercentage: 64  # from the tally", "stepsCompleted: ['coverage']"], 64, True),
    ],
    ids=[
        "flow-single-quotes", "zero-measured", "flow-bare", "block-indented", "block-flush",
        "flow-two-lines", "init-only", "empty-list", "no-list", "scalar-not-list", "other-step",
        "fraction", "above-100", "negative", "empty-value", "no-percentage", "trailing-comment",
    ],
)
def test_coverage_fields(tmp_path, frontmatter, percentage, measured):
    _write_latest(tmp_path, _full_report(extra_frontmatter=frontmatter))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0, result
    assert result["coveragePercentage"] == percentage
    assert result["coverageMeasured"] is measured


def test_coverage_fields_of_the_verify_stack_template(tmp_path):
    # The producer's template, as [VS] writes it when a run starts: the 0 is
    # read, but it was never measured.
    assets = Path(__file__).parent.parent / "src" / "skf-verify-stack" / "assets"
    template = (assets / "feasibility-report-template.md").read_text(encoding="utf-8")
    _write_latest(tmp_path, template)
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 0, result
    assert result["coveragePercentage"] == 0
    assert result["coverageMeasured"] is False
    assert result["generatedAt"] is None  # the template leaves it empty
    assert result["verdictTableFound"] is True and result["pairVerdicts"] == []


def test_generated_at(tmp_path):
    _write_latest(tmp_path, _full_report(extra_frontmatter=['generatedAt: "2026-09-30T10:00:00Z"']))
    result, _ = locate_report(str(tmp_path), "My Project")
    assert result["generatedAt"] == "2026-09-30T10:00:00Z"


def test_an_uninterpreted_report_gives_no_coverage(tmp_path):
    frontmatter = ['generatedAt: "2026-09-30T10:00:00Z"', "coveragePercentage: 80",
                   "stepsCompleted: ['coverage']"]
    _write_latest(tmp_path, _full_report(schema_version='"2.0"', extra_frontmatter=frontmatter))
    result, code = locate_report(str(tmp_path), "My Project")
    assert code == 1
    assert result["generatedAt"] is None
    assert result["coveragePercentage"] is None
    assert result["coverageMeasured"] is None


# --- frontmatter_list ------------------------------------------------------------


@pytest.mark.parametrize(
    "lines,items",
    [
        (["steps: ['a', \"b\", c]"], ["a", "b", "c"]),
        (["steps: []"], []),
        (["steps:", "  - a", "", "  # a comment", "  - 'b'  # trailing", "other: 1", "  - c"],
         ["a", "b"]),
        (["steps: [a,", "   b]"], ["a", "b"]),
        (["steps: a"], None),
        (["steps:"], None),
        (["other: [a]"], None),
        (["nested:", "  steps: [a]"], None),
        (["steps: [a]", "steps: [b]"], ["b"]),
    ],
    ids=["flow", "flow-empty", "block", "flow-two-lines", "scalar", "no-items", "absent",
         "indented", "last-wins"],
)
def test_frontmatter_list(lines, items):
    content = "\n".join(["---", *lines, "---", "", "# Body"])
    assert frontmatter_list(content, "steps") == items


def test_frontmatter_list_needs_a_frontmatter_block():
    assert frontmatter_list("steps: [a]\n", "steps") is None
    assert frontmatter_list("---\nsteps: [a]\n", "steps") is None  # never closed
