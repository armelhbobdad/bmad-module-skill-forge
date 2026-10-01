#!/usr/bin/env python3
"""Tests for skf-report-delta.py (skf-verify-stack synthesize.md §3).

Covers improved/regressed/unchanged/new/dropped classification across the
coverage and integration verdict rankings, unordered integration-pair matching,
Replaced bucketing, evidence-tier downgrade detection on the one T-code scale
(any other tier token is rejected as UNKNOWN_TIER), validation, reading the
two reports (--previous-report, --current-report) from the template the
producer fills, the reports it does not read (INVALID_REPORT), this run's tiers
from the enumerate inventory (--inventory), the installed layout that finds the
shared reader, the subprocess CLI contract, and the call synthesize.md makes.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "src" / "skf-verify-stack"
SCRIPT_PATH = SKILL / "scripts" / "skf-report-delta.py"
SYNTHESIZE = SKILL / "references" / "synthesize.md"
COVERAGE = SKILL / "references" / "coverage.md"
TEMPLATE = SKILL / "assets" / "feasibility-report-template.md"
READER_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-validate-feasibility-report.py"

spec = importlib.util.spec_from_file_location("skf_report_delta", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
compute = mod.compute


def test_coverage_improved_and_regressed():
    out = compute(
        {
            "previous": {
                "coverage": [
                    {"technology": "react", "verdict": "Missing"},
                    {"technology": "express", "verdict": "Covered"},
                ]
            },
            "current": {
                "coverage": [
                    {"technology": "react", "verdict": "Covered"},   # improved
                    {"technology": "express", "verdict": "Missing"},  # regressed
                ]
            },
        }
    )
    assert out["improvedCount"] == 1
    assert out["regressedCount"] == 1
    assert out["unchangedCount"] == 0
    assert "react" in out["improved"]
    assert "express" in out["regressed"]


def test_integration_ranking():
    out = compute(
        {
            "previous": {
                "integration": [
                    {"libA": "a", "libB": "b", "verdict": "Risky"},
                    {"libA": "c", "libB": "d", "verdict": "Verified"},
                ]
            },
            "current": {
                "integration": [
                    {"libA": "a", "libB": "b", "verdict": "Verified"},  # Risky->Verified improved
                    {"libA": "c", "libB": "d", "verdict": "Blocked"},   # Verified->Blocked regressed
                ]
            },
        }
    )
    assert out["improvedCount"] == 1
    assert out["regressedCount"] == 1


def test_integration_pair_order_independent():
    out = compute(
        {
            "previous": {"integration": [{"libA": "react", "libB": "express", "verdict": "Plausible"}]},
            "current": {"integration": [{"libA": "express", "libB": "react", "verdict": "Verified"}]},
        }
    )
    # Same unordered pair -> matched -> improved, not new+dropped.
    assert out["improvedCount"] == 1
    assert out["newCount"] == 0
    assert out["droppedCount"] == 0


def test_new_and_dropped():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "old", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "shiny", "verdict": "Covered"}]},
        }
    )
    assert out["newCount"] == 1 and "shiny" in out["new"]
    assert out["droppedCount"] == 1 and "old" in out["dropped"]


def test_unchanged():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
        }
    )
    assert out["unchangedCount"] == 1


def test_replaced_bucketed_not_regressed():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "orm", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "orm", "verdict": "Replaced"}]},
        }
    )
    # Covered -> Replaced is intentional removal, not a regression.
    assert out["regressedCount"] == 0
    assert out["replacedCount"] == 1


def test_tier_downgrade():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"react": "T1", "express": "T1-low", "vue": "T2"},
            "currentTiers": {"react": "T2", "express": "T1-low", "vue": "T2"},
        }
    )
    assert out["tierDowngradeCount"] == 1
    assert out["tierDowngrades"][0]["skill"] == "react"
    assert out["tierDowngrades"][0]["from"] == "T1"
    assert out["tierDowngrades"][0]["to"] == "T2"


def test_tier_t1_to_t1low_is_downgrade():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"x": "T1"},
            "currentTiers": {"x": "T1-low"},
        }
    )
    assert out["tierDowngradeCount"] == 1


def test_no_tiers_no_downgrades():
    out = compute({"previous": {}, "current": {}})
    assert out["tierDowngradeCount"] == 0


def test_every_drop_along_the_scale_is_a_downgrade():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"a": "T1", "b": "T1-low", "c": "T2", "d": "T3", "e": "T3"},
            "currentTiers": {"a": "T1-low", "b": "T2", "c": "T3", "d": "T2", "e": "T3"},
        }
    )
    # T3 ranks lowest: d rose from T3 to T2, e stayed.
    assert [(d["skill"], d["from"], d["to"]) for d in out["tierDowngrades"]] == [
        ("a", "T1", "T1-low"),
        ("b", "T1-low", "T2"),
        ("c", "T2", "T3"),
    ]


def test_a_skill_in_one_run_only_is_not_compared():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"gone": "T1"},
            "currentTiers": {"new": "T3"},
        }
    )
    assert out["tierDowngradeCount"] == 0


def test_forge_tier_input_is_rejected_not_skipped():
    # The #590 reproduction: previous {react: Deep, vite: Forge+, zod: T1}
    # against current {react: Quick, vite: Forge, zod: T2} used to report only
    # the zod downgrade and exit 0, dropping two regressions without a word.
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"react": "Deep", "vite": "Forge+", "zod": "T1"},
            "currentTiers": {"react": "Quick", "vite": "Forge", "zod": "T2"},
        }
    )
    assert out["code"] == "UNKNOWN_TIER"
    assert "`previousTiers.react` tier 'Deep'" in out["error"]
    assert "T1, T1-low, T2, T3" in out["error"]


def test_tier_tokens_are_case_sensitive():
    for token in ("t1", "T1-LOW", "t1-low", "T1low", "", None, 1):
        out = compute({"previous": {}, "current": {}, "currentTiers": {"x": token}})
        assert out.get("code") == "UNKNOWN_TIER", token


def test_a_tier_map_that_is_no_object_is_invalid_input():
    out = compute({"previous": {}, "current": {}, "currentTiers": ["T1"]})
    assert out.get("code") == "INVALID_INPUT"


def test_tiers_compared_only_with_both_maps():
    assert compute({"previous": {}, "current": {}})["tiersCompared"] is False
    assert compute({"previous": {}, "current": {}, "currentTiers": {"x": "T1"}})["tiersCompared"] is False
    both = {"previous": {}, "current": {}, "previousTiers": {}, "currentTiers": {"x": "T1"}}
    assert compute(both)["tiersCompared"] is True


def test_invalid_missing_sides():
    assert compute({"previous": {}}).get("code") == "INVALID_INPUT"
    assert compute("nope").get("code") == "INVALID_INPUT"


def test_invalid_verdict_token():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "x", "verdict": "covered"}]},
            "current": {"coverage": []},
        }
    )
    assert out.get("code") == "INVALID_INPUT"


# --- CLI / subprocess contract ---------------------------------------------


def _run(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_success():
    payload = json.dumps(
        {
            "previous": {"coverage": [{"technology": "react", "verdict": "Missing"}]},
            "current": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
        }
    )
    proc = _run(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["improvedCount"] == 1


def test_cli_no_input_exit_1():
    assert _run([]).returncode == 1


def test_cli_bad_json_exit_1():
    proc = _run(["{bad"])
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit_2():
    proc = _run([json.dumps({"previous": {}})])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_unknown_tier_exit_2():
    payload = {"previous": {}, "current": {}, "previousTiers": {"react": "Deep"}, "currentTiers": {"react": "Quick"}}
    proc = _run(["--stdin"], stdin=json.dumps(payload))
    assert proc.returncode == 2
    out = json.loads(proc.stdout)
    assert out["code"] == "UNKNOWN_TIER"
    assert "`previousTiers.react` tier 'Deep'" in out["error"]
    # --no-tiers compares no tier, so the same input goes through.
    proc = _run(["--stdin", "--no-tiers"], stdin=json.dumps(payload))
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["tiersCompared"] is False


def test_cli_help_prints_the_rankings_synthesize_points_to():
    proc = _run(["--help"])
    assert proc.returncode == 0
    for needle in ("Blocked(0) < Risky(1) < Plausible(2) < Verified(3)", "T3(0) < T2(1) < T1-low(2) < T1(3)"):
        assert needle in proc.stdout, needle


# --- Reading the two reports -------------------------------------------------

COVERAGE_HEADER = "| Technology | Source Section | Skill Match | Verdict |"
VERDICT_HEADER = "| lib_a | lib_b | verdict | rationale |"
TIER_HEADER = "| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |"

PREVIOUS = {
    "coverage": [("react", "Missing"), ("vite", "Covered"), ("zod", "Covered")],
    "pairs": [("react", "vite", "Plausible"), ("vite", "zod", "Verified")],
    "tiers": [("react", "T1"), ("vite", "T1"), ("zod", "T2")],
}
CURRENT = {
    "coverage": [("react", "Covered"), ("vite", "Covered"), ("zod", "Covered")],
    "pairs": [("vite", "react", "Verified"), ("vite", "zod", "Risky")],
    "tiers": [],
}
CURRENT_TIERS = {"react": "T1-low", "vite": "T1", "zod": "T2"}

READER = mod.load_reader()


def _coverage_table(rows, header=COVERAGE_HEADER):
    names = [cell.strip() for cell in header.strip().strip("|").split("|")]
    lines = [header, "|" + "---|" * len(names)]
    for tech, verdict in rows:
        cells = {"Technology": tech, "Verdict": verdict}
        lines.append("| " + " | ".join(cells.get(name, "x") for name in names) + " |")
    return lines


def _report_text(coverage=(), pairs=(), tiers=(), coverage_lines=None):
    """A report built from the template the producer fills, each table filled in place.

    coverage_lines replaces the coverage table (an empty list writes none).
    """
    lines = TEMPLATE.read_text(encoding="utf-8").split("\n")
    at = lines.index("## Coverage Analysis") + 1
    lines[at:at] = [""] + (_coverage_table(coverage) if coverage_lines is None else coverage_lines)
    at = lines.index(VERDICT_HEADER) + 2
    lines[at:at] = [f"| {a} | {b} | {v} | from the skills |" for a, b, v in pairs]
    at = lines.index(TIER_HEADER) + 2
    lines[at:at] = [f"| {skill} | {tier} | none | 1.3 | skills/{skill}/SKILL.md |" for skill, tier in tiers]
    return "\n".join(lines)


def _without_table(text, header):
    """Drop the table whose header row is `header` (header and delimiter rows)."""
    lines = text.split("\n")
    at = lines.index(header)
    return "\n".join(lines[:at] + lines[at + 2:])


def _with_second_verdict_table(text):
    lines = text.split("\n")
    at = lines.index("## Recommendations")
    lines[at:at] = [VERDICT_HEADER, "|---|---|---|---|", "| react | zod | Verified | appended |", ""]
    return "\n".join(lines)


def _reports(folder, previous=None, current=None):
    prev = folder / "feasibility-report-my-app-20260101-080000.md"
    curr = folder / "feasibility-report-my-app-20260930-120000.md"
    prev.write_bytes((_report_text(**PREVIOUS) if previous is None else previous).encode("utf-8"))
    curr.write_bytes((_report_text(**CURRENT) if current is None else current).encode("utf-8"))
    return prev, curr


def _run_reports(prev, curr, data=None, no_tiers=False):
    data = {"currentTiers": CURRENT_TIERS} if data is None else data
    return mod.run(data, str(prev), str(curr), no_tiers, READER)


def _findings(spec):
    return {
        "coverage": [{"technology": tech, "verdict": verdict} for tech, verdict in spec["coverage"]],
        "integration": [{"libA": a, "libB": b, "verdict": v} for a, b, v in spec["pairs"]],
    }


def test_the_shared_reader_is_found_beside_the_skill():
    assert READER is not None
    assert mod.SHARED_READER == READER_PATH.resolve()


def test_reads_both_reports_from_the_template_it_fills(tmp_path):
    prev, curr = _reports(tmp_path)
    out = _run_reports(prev, curr)
    assert out["improved"] == ["react", "vite ↔ react"]
    assert out["regressed"] == ["vite ↔ zod"]
    assert out["unchanged"] == ["vite", "zod"]
    assert out["tierDowngrades"] == [{"skill": "react", "from": "T1", "to": "T1-low"}]
    assert out["tiersCompared"] is True
    assert out["previousTiersRecorded"] is True


def test_reading_a_report_equals_passing_its_findings(tmp_path):
    prev, curr = _reports(tmp_path)
    from_reports = _run_reports(prev, curr)
    passed = compute(
        {
            "previous": _findings(PREVIOUS),
            "current": _findings(CURRENT),
            "previousTiers": dict(PREVIOUS["tiers"]),
            "currentTiers": CURRENT_TIERS,
        }
    )
    assert from_reports.pop("previousTiersRecorded") is True
    assert from_reports == passed


@pytest.mark.parametrize("no_table", [False, True], ids=["empty-tier-table", "no-tier-table"])
def test_a_previous_report_that_records_no_tier(tmp_path, no_table):
    # A report written before tiers were recorded: the delta still runs.
    text = _report_text(**{**PREVIOUS, "tiers": ()})
    if no_table:
        text = _without_table(text, TIER_HEADER)
    prev, curr = _reports(tmp_path, previous=text)
    out = _run_reports(prev, curr)
    assert "code" not in out, out
    assert out["previousTiersRecorded"] is False
    assert out["tiersCompared"] is False
    assert out["tierDowngrades"] == []
    assert out["improvedCount"] == 2


def test_an_unknown_tier_in_the_previous_report(tmp_path):
    prev, curr = _reports(tmp_path, previous=_report_text(**{**PREVIOUS, "tiers": [("react", "Deep")]}))
    out = _run_reports(prev, curr)
    assert out["code"] == "UNKNOWN_TIER"
    assert out["report"] == "previous" and out["path"] == str(prev)
    assert "skill `react` has evidence_tier 'Deep'" in out["error"]
    # The retry synthesize.md asks for: the same reports, no tier compared.
    again = _run_reports(prev, curr, no_tiers=True)
    assert "code" not in again, again
    assert again["tiersCompared"] is False
    assert again["previousTiersRecorded"] is None
    assert again["improvedCount"] == 2


def _with_schema_version(text, line):
    return text.replace('schemaVersion: "1.0"\n', line, 1)


INVALID_PREVIOUS = [
    pytest.param(lambda t: _with_schema_version(t, 'schemaVersion: "2.0"\n'), "schemaVersion '2.0'", id="schema-2.0"),
    pytest.param(lambda t: _with_schema_version(t, ""), "no schemaVersion", id="no-schema-version"),
    pytest.param(
        lambda t: _report_text(**{**PREVIOUS, "coverage_lines": []}),
        "no table with Technology and Verdict columns",
        id="no-coverage-table",
    ),
    pytest.param(
        lambda t: _report_text(**{**PREVIOUS, "coverage": [("react", "covered")]}),
        "coverage verdict 'covered' for `react`",
        id="coverage-token-case",
    ),
    pytest.param(
        lambda t: _report_text(**{**PREVIOUS, "coverage": [("", "Covered")]}),
        "a coverage row names no technology",
        id="coverage-row-without-technology",
    ),
    pytest.param(lambda t: _without_table(t, VERDICT_HEADER), "has no `| lib_a | lib_b", id="no-verdict-table"),
    pytest.param(_with_second_verdict_table, "table twice (again at line", id="verdict-table-twice"),
    pytest.param(
        lambda t: _report_text(**{**PREVIOUS, "pairs": [("react", "vite", "VERIFIED")]}),
        "verdict 'VERIFIED' for `react` and `vite`",
        id="pair-token-case",
    ),
]


@pytest.mark.parametrize(("mutate", "needle"), INVALID_PREVIOUS)
def test_a_report_it_does_not_read(tmp_path, mutate, needle):
    prev, curr = _reports(tmp_path, previous=mutate(_report_text(**PREVIOUS)))
    out = _run_reports(prev, curr)
    assert out["code"] == "INVALID_REPORT", out
    assert out["report"] == "previous" and out["path"] == str(prev)
    assert needle in out["error"]


def test_a_missing_report_file_is_not_read(tmp_path):
    prev, curr = _reports(tmp_path)
    out = _run_reports(tmp_path / "nope.md", curr)
    assert out["code"] == "INVALID_REPORT" and "cannot be read" in out["error"]


def test_this_runs_report_is_read_the_same_way(tmp_path):
    prev, curr = _reports(tmp_path, current=_with_second_verdict_table(_report_text(**CURRENT)))
    out = _run_reports(prev, curr)
    assert out["code"] == "INVALID_REPORT"
    assert out["report"] == "current" and out["path"] == str(curr)


def test_example_tables_in_fences_and_comments_are_not_read(tmp_path):
    fenced = ["```markdown", *_coverage_table([("fenced", "Bogus")]), "```"]
    commented = ["<!--", *_coverage_table([("commented", "Bogus")]), "-->"]
    real = _coverage_table(PREVIOUS["coverage"])
    text = _report_text(**{**PREVIOUS, "coverage_lines": fenced + [""] + commented + [""] + real})
    prev, curr = _reports(tmp_path, previous=text)
    out = _run_reports(prev, curr)
    assert "code" not in out, out
    assert out["improvedCount"] == 2


def test_a_coverage_table_is_found_by_its_two_columns(tmp_path):
    # An earlier run's table with fewer columns still reads by column name.
    lines = _coverage_table(PREVIOUS["coverage"], header="| Verdict | Technology |")
    prev, curr = _reports(tmp_path, previous=_report_text(**{**PREVIOUS, "coverage_lines": lines}))
    out = _run_reports(prev, curr)
    assert "code" not in out, out
    assert out["improved"] == ["react", "vite ↔ react"]


def test_a_report_side_is_left_out_of_the_json(tmp_path):
    prev, curr = _reports(tmp_path)
    for data, flag in (({"previous": {}}, "previous"), ({"previousTiers": {}}, "previous"), ({"current": {}}, "current")):
        out = _run_reports(prev, curr, data=data)
        assert out["code"] == "INVALID_INPUT"
        assert f"--{flag}-report" in out["error"]


def test_cli_reads_two_reports_with_no_json(tmp_path):
    prev, curr = _reports(tmp_path)
    proc = _run(["--previous-report", str(prev), "--current-report", str(curr)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["improvedCount"] == 2
    # No currentTiers given: the previous report's tiers are read, none compared.
    assert out["previousTiersRecorded"] is True and out["tiersCompared"] is False


def test_cli_reads_the_reports_with_tiers_on_stdin(tmp_path):
    prev, curr = _reports(tmp_path)
    args = ["--previous-report", str(prev), "--current-report", str(curr), "--stdin"]
    proc = _run(args, stdin=json.dumps({"currentTiers": CURRENT_TIERS}))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["tierDowngradeCount"] == 1


def _inventory(folder, tiers=CURRENT_TIERS):
    """An skf-enumerate-stack-skills.py inventory whose skills carry these evidence tiers."""
    skills = [{"name": name, "path": name, "evidence_tier": tier, "confidence_tier": "Deep"}
              for name, tier in tiers.items()]
    path = folder / "skill-inventory.json"
    path.write_bytes(json.dumps({"skills": skills, "warnings": []}).encode("utf-8"))
    return path


def test_the_inventory_gives_the_current_tiers(tmp_path):
    prev, curr = _reports(tmp_path)
    from_inventory = mod.run({}, str(prev), str(curr), False, READER, str(_inventory(tmp_path)))
    # The evidence_tier of each skill, never its confidence_tier (a forge tier).
    assert from_inventory == _run_reports(prev, curr)
    assert from_inventory["tierDowngrades"] == [{"skill": "react", "from": "T1", "to": "T1-low"}]


def test_cli_reads_the_reports_and_the_inventory_with_no_json(tmp_path):
    prev, curr = _reports(tmp_path)
    proc = _run(["--previous-report", str(prev), "--current-report", str(curr),
                 "--inventory", str(_inventory(tmp_path))])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["tiersCompared"], out["tierDowngradeCount"], out["improvedCount"]) == (True, 1, 2)


@pytest.mark.parametrize(
    "content, needle",
    [
        pytest.param(None, "cannot be read", id="missing-file"),
        pytest.param(b"{not json", "is not JSON", id="not-json"),
        pytest.param(b'{"skills": {}}', "holds no `skills` list", id="no-skills-list"),
        pytest.param(b'{"skills": [{"path": "x"}]}', "skills[0] has no `name`", id="unnamed-skill"),
    ],
)
def test_an_inventory_it_cannot_read_is_invalid_input(tmp_path, content, needle):
    prev, curr = _reports(tmp_path)
    inventory = tmp_path / "inventory.json"
    if content is not None:
        inventory.write_bytes(content)
    out = mod.run({}, str(prev), str(curr), False, READER, str(inventory))
    assert out["code"] == "INVALID_INPUT" and needle in out["error"]
    assert out["path"] == str(inventory) and "report" not in out
    # The retry synthesize.md asks for compares no tier, so it reads no inventory.
    again = mod.run({}, str(prev), str(curr), True, READER, str(inventory))
    assert "code" not in again and again["tiersCompared"] is False


def test_an_inventory_tier_off_the_scale_is_unknown_tier(tmp_path):
    prev, curr = _reports(tmp_path)
    out = mod.run({}, str(prev), str(curr), False, READER, str(_inventory(tmp_path, {"react": "Deep"})))
    assert out["code"] == "UNKNOWN_TIER"


def test_current_tiers_come_from_one_source(tmp_path):
    prev, curr = _reports(tmp_path)
    out = mod.run({"currentTiers": CURRENT_TIERS}, str(prev), str(curr), False, READER, str(_inventory(tmp_path)))
    assert out["code"] == "INVALID_INPUT" and "--inventory" in out["error"]


def test_cli_one_report_flag_still_needs_json(tmp_path):
    prev, _curr = _reports(tmp_path)
    assert _run(["--previous-report", str(prev)]).returncode == 1


def test_cli_a_report_it_does_not_read_exits_2(tmp_path):
    prev, curr = _reports(tmp_path, previous=_without_table(_report_text(**PREVIOUS), VERDICT_HEADER))
    proc = _run(["--previous-report", str(prev), "--current-report", str(curr)])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_REPORT"


def _install(root, with_reader):
    """Copy the script, and the shared reader if asked, into an installed layout."""
    scripts = root / "_bmad" / "skf" / "skf-verify-stack" / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / SCRIPT_PATH.name
    script.write_bytes(SCRIPT_PATH.read_bytes())
    if with_reader:
        shared = root / "_bmad" / "skf" / "shared" / "scripts"
        shared.mkdir(parents=True)
        (shared / READER_PATH.name).write_bytes(READER_PATH.read_bytes())
    return script


def test_installed_layout_finds_the_shared_reader(tmp_path):
    script = _install(tmp_path / "project", with_reader=True)
    prev, curr = _reports(tmp_path)
    proc = subprocess.run(
        [sys.executable, script.as_posix(), "--previous-report", str(prev), "--current-report", str(curr)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["improvedCount"] == 2


def test_a_missing_shared_reader_exits_1(tmp_path):
    script = _install(tmp_path / "project", with_reader=False)
    prev, curr = _reports(tmp_path)
    proc = subprocess.run(
        [sys.executable, script.as_posix(), "--previous-report", str(prev), "--current-report", str(curr)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "HELPER_MISSING"
    # Findings passed as JSON need no reader.
    proc = subprocess.run(
        [sys.executable, script.as_posix(), json.dumps({"previous": {}, "current": {}})],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout


# --- The call and tier inputs synthesize.md builds ---------------------------


def _section(heading, end, path=SYNTHESIZE):
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    return text[start:text.index(end, start)]


def test_synthesize_runs_the_delta_on_both_reports():
    delta = _section("### 3. Check for Previous Report", "### 4.")
    [call] = [line for line in delta.splitlines() if line.startswith("uv run {reportDeltaScript} ")]
    words = shlex.split(call.split("uv run {reportDeltaScript}", 1)[1])
    parser = mod._build_parser()
    args = parser.parse_args(words)
    assert (args.previous_report, args.current_report, args.inventory, args.stdin) == (
        "{previousReport}", "{outputFile}", "{inventoryFile}", False)
    # The retry the UNKNOWN_TIER branch asks for fits the parser too.
    assert parser.parse_args([*words, "--no-tiers"]).no_tiers
    assert "`--no-tiers`" in delta
    for code in ("UNKNOWN_TIER", "INVALID_REPORT", "INVALID_INPUT", "HELPER_MISSING"):
        assert f"`{code}`" in delta, code
        assert code in mod.__doc__, code
    assert "`previousTiersRecorded`" in delta
    # Reading the pinned tables is the script's work, not the prompt's.
    for stale in ("Reading the tables is judgment", "Extract the coverage findings", "`previousTiers`",
                  "When the error names a tier", "manual backup"):
        assert stale not in delta, stale


def test_synthesize_passes_evidence_tiers_on_the_scripts_scale():
    delta = _section("### 3. Check for Previous Report", "### 4.")
    # The script reads each skill's evidence_tier from the inventory, never
    # metadata's confidence_tier (a forge tier for a single skill), so the
    # prose builds no tier map.
    assert '--inventory "{inventoryFile}"' in delta and "`evidence_tier`" in delta
    assert "`currentTiers`" not in delta and "<tiers JSON>" not in delta
    assert "--inventory fills\n  `currentTiers`" in mod.__doc__
    for tier in mod.TIERS:
        assert f"`{tier}`" in delta, tier
    assert "Tier 1 → Tier 2" not in delta, "the old gloss fits neither vocabulary"
    # An exit 2 on a tier is reported, never swallowed.
    assert "Tier changes were not compared" in delta


def test_the_report_persists_the_tier_the_next_run_reads():
    append = _section("### 5. Append to Report", "### 6.")
    assert f"`{TIER_HEADER}`" in append
    assert "Fill it in place" in append
    delta = _section("### 3. Check for Previous Report", "### 4.")
    assert "`evidence_tier` column" in delta
    # The template seeds that table once, and the script reads its columns.
    template = TEMPLATE.read_text(encoding="utf-8")
    assert [line.strip() for line in template.splitlines()].count(TIER_HEADER) == 1
    cells = [cell.strip() for cell in TIER_HEADER.strip("|").split("|")]
    assert all(column in cells for column in mod.TIER_COLUMNS)


def test_coverage_writes_the_table_the_next_run_reads():
    write = _section("### 6. Append to Report", "### 7.", path=COVERAGE)
    assert f"`{COVERAGE_HEADER}`" in write
    cells = [cell.strip() for cell in COVERAGE_HEADER.strip("|").split("|")]
    assert all(column in cells for column in mod.COVERAGE_COLUMNS)
    for verdict in mod.COVERAGE_VERDICTS:
        assert f"`{verdict}`" in write, verdict


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
