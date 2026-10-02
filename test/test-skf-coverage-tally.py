#!/usr/bin/env python3
"""Tests for skf-coverage-tally.py (skf-verify-stack coverage.md §3,
integrations.md §4 and requirements.md §3, each persisted in its stage's
report section).

Covers Covered/Missing/Replaced counting, the Replaced-excluded denominator,
half-up percentage rounding, validation (bad tokens, duplicates), the
integrations tally (pair rows by verdict, each cycle the --cycles file lists
counted as one more Risky row, the pair checks), the requirements tally, the
--render mode (the coverage rows with their section and skill, the canonical
verdict rows with their rationale and one row per cycle, each cell on one line
with its pipes escaped, the same checks as the counts), the subprocess CLI
contract (exit codes + JSON-on-stdout, a UTF-8 row file read under a cp1252
console), and the stage calls that persist the counts and render the rows.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "src" / "skf-verify-stack"
SCRIPT_PATH = SKILL / "scripts" / "skf-coverage-tally.py"
FIND_CYCLES = REPO_ROOT / "src" / "shared" / "scripts" / "skf-find-cycles.py"

spec = importlib.util.spec_from_file_location("skf_coverage_tally", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
tally = mod.tally


def test_basic_counts_and_percentage():
    out = tally(
        {
            "rows": [
                {"technology": "react", "verdict": "Covered"},
                {"technology": "express", "verdict": "Covered"},
                {"technology": "postgres", "verdict": "Missing"},
            ]
        }
    )
    assert out["covered_count"] == 2
    assert out["missing_count"] == 1
    assert out["replaced_count"] == 0
    assert out["live_count"] == 3
    assert out["total_referenced"] == 3
    assert out["coverage_percentage"] == 67  # round-half-up(2/3*100)=66.66..->67


def test_replaced_excluded_from_denominator():
    out = tally(
        {
            "rows": [
                {"technology": "react", "verdict": "Covered"},
                {"technology": "old-orm", "verdict": "Replaced"},
                {"technology": "legacy-ui", "verdict": "Replaced"},
            ]
        }
    )
    # live_count = Covered + Missing only; Replaced never dilutes the percentage.
    assert out["live_count"] == 1
    assert out["replaced_count"] == 2
    assert out["total_referenced"] == 3
    assert out["coverage_percentage"] == 100


def test_all_replaced_is_zero_not_divide_by_zero():
    out = tally({"rows": [{"technology": "x", "verdict": "Replaced"}]})
    assert out["live_count"] == 0
    assert out["coverage_percentage"] == 0


def test_full_coverage():
    out = tally(
        {
            "rows": [
                {"technology": "a", "verdict": "Covered"},
                {"technology": "b", "verdict": "Covered"},
            ]
        }
    )
    assert out["coverage_percentage"] == 100


def test_half_up_rounding():
    # 1/8 covered -> 12.5% -> half-up -> 13
    rows = [{"technology": f"cov{i}", "verdict": "Covered"} for i in range(1)]
    rows += [{"technology": f"miss{i}", "verdict": "Missing"} for i in range(7)]
    out = tally({"rows": rows})
    assert out["live_count"] == 8
    assert out["coverage_percentage"] == 13


def test_empty_rows():
    out = tally({"rows": []})
    assert out["coverage_percentage"] == 0
    assert out["total_referenced"] == 0


def test_invalid_verdict_token():
    out = tally({"rows": [{"technology": "x", "verdict": "covered"}]})  # lowercase
    assert out.get("code") == "INVALID_INPUT"


def test_duplicate_technology_rejected():
    out = tally(
        {
            "rows": [
                {"technology": "React", "verdict": "Covered"},
                {"technology": "react", "verdict": "Missing"},
            ]
        }
    )
    assert out.get("code") == "INVALID_INPUT"


def test_missing_rows_field():
    assert tally({}).get("code") == "INVALID_INPUT"
    assert tally("nope").get("code") == "INVALID_INPUT"


# --- CLI / subprocess contract ---------------------------------------------


def _run(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_success():
    payload = json.dumps({"rows": [{"technology": "react", "verdict": "Covered"}]})
    proc = _run(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["coverage_percentage"] == 100


def test_cli_positional_success():
    payload = json.dumps({"rows": [{"technology": "react", "verdict": "Missing"}]})
    proc = _run([payload])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["coverage_percentage"] == 0


def test_cli_no_input_exit_1():
    proc = _run([])
    assert proc.returncode == 1


def test_cli_bad_json_exit_1():
    proc = _run(["{not json"])
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit_2():
    payload = json.dumps({"rows": [{"technology": "x", "verdict": "Bogus"}]})
    proc = _run([payload])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


# --- integrations: the canonical verdict table's rows --------------------------


def _pairs(*verdicts):
    return {"rows": [{"lib_a": f"a{i}", "lib_b": f"b{i}", "verdict": v} for i, v in enumerate(verdicts)]}


def test_integrations_counts_each_verdict():
    out = mod.tally_integrations(_pairs("Verified", "Verified", "Plausible", "Risky", "Blocked"))
    assert out == {
        "pairs_verified": 2,
        "pairs_plausible": 1,
        "pairs_risky": 1,
        "pairs_blocked": 1,
        "pair_count": 5,
        "cycle_count": 0,
        "row_count": 5,
    }


def test_each_cycle_is_one_more_risky_row():
    # Every pair Verified, but the citations run in a circle: the table gains a
    # Risky row per cycle, and the frontmatter's pairsRisky counts it, so the
    # rollup cannot read the run as FEASIBLE on one run and not on the next.
    cycles = {"cycles": [["a", "b", "a"], ["a", "b", "c", "a"]], "cycle_count": 2}
    out = mod.tally_integrations(_pairs("Verified", "Verified", "Risky"), cycles)
    assert out["pairs_verified"] == 2
    assert out["pairs_risky"] == 3
    assert (out["pair_count"], out["cycle_count"], out["row_count"]) == (3, 2, 5)


def test_no_pairs_and_no_cycles():
    assert mod.tally_integrations({"rows": []}, {"cycles": [], "cycle_count": 0})["row_count"] == 0


def test_the_cycle_finder_output_feeds_the_tally():
    edges = json.dumps({"edges": [["react", "zod"], ["zod", "react"]]})
    found = subprocess.run(
        [sys.executable, str(FIND_CYCLES), "find", "--edges", "-"],
        input=edges,
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode == 0, found.stderr
    out = mod.tally_integrations(_pairs("Verified"), json.loads(found.stdout))
    assert (out["cycle_count"], out["pairs_risky"]) == (1, 1)


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param([{"lib_a": "a", "lib_b": "b", "verdict": "verified"}], id="lowercase-token"),
        pytest.param([{"lib_a": "a", "lib_b": "b", "verdict": "Feasible"}], id="overall-token"),
        pytest.param([{"lib_a": "", "lib_b": "b", "verdict": "Risky"}], id="empty-lib-a"),
        pytest.param([{"lib_a": "a", "verdict": "Risky"}], id="no-lib-b"),
        pytest.param([{"lib_a": "React", "lib_b": "react", "verdict": "Risky"}], id="paired-with-itself"),
        pytest.param(
            [{"lib_a": "a", "lib_b": "b", "verdict": "Verified"}, {"lib_a": "B", "lib_b": "A", "verdict": "Risky"}],
            id="pair-twice-reversed",
        ),
        pytest.param(["a|b|Verified"], id="row-not-object"),
    ],
)
def test_integrations_rejects_bad_rows(rows):
    assert mod.tally_integrations({"rows": rows}).get("code") == "INVALID_INPUT"


@pytest.mark.parametrize(
    "cycles",
    [
        pytest.param([["a", "b", "a"]], id="bare-list"),
        pytest.param({"cycle_count": 1}, id="no-cycles-key"),
        pytest.param({"cycles": [["a", "b"]]}, id="open-path"),
        pytest.param({"cycles": [["a"]]}, id="one-node"),
        pytest.param({"cycles": [["a", "", "a"]]}, id="empty-node"),
    ],
)
def test_integrations_rejects_a_malformed_cycles_file(cycles):
    out = mod.tally_integrations(_pairs("Verified"), cycles)
    assert out.get("code") == "INVALID_INPUT"
    assert "--cycles" in out["error"]


def test_a_self_loop_is_a_cycle():
    assert mod.tally_integrations(_pairs("Verified"), {"cycles": [["a", "a"]]})["pairs_risky"] == 1


# --- requirements ------------------------------------------------------------------


def test_requirements_counts_each_verdict():
    rows = [
        {"requirement_id": "R1", "verdict": "Fulfilled"},
        {"requirement_id": "R2", "verdict": "Partially Fulfilled"},
        {"requirement_id": "R3", "verdict": "Not Addressed"},
        {"requirement_id": "R4", "verdict": "Not Addressed"},
    ]
    assert mod.tally_requirements({"rows": rows}) == {
        "requirements_fulfilled": 1,
        "requirements_partial": 1,
        "requirements_not_addressed": 2,
        "requirement_count": 4,
    }


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param([{"requirement_id": "R1", "verdict": "Partial"}], id="bad-token"),
        pytest.param([{"requirement_id": " ", "verdict": "Fulfilled"}], id="blank-id"),
        pytest.param(
            [{"requirement_id": "R1", "verdict": "Fulfilled"}, {"requirement_id": "r1", "verdict": "Not Addressed"}],
            id="id-twice",
        ),
    ],
)
def test_requirements_rejects_bad_rows(rows):
    assert mod.tally_requirements({"rows": rows}).get("code") == "INVALID_INPUT"


# --- CLI kinds -----------------------------------------------------------------------


def test_cli_integrations_with_a_cycles_file(tmp_path):
    cycles = tmp_path / "cycles.json"
    cycles.write_bytes(json.dumps({"cycles": [["a0", "b0", "a0"]], "cycle_count": 1}).encode("utf-8"))
    proc = _run(["--kind", "integrations", "--cycles", str(cycles), "--stdin"], stdin=json.dumps(_pairs("Verified")))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["pairs_verified"], out["pairs_risky"], out["row_count"]) == (1, 1, 2)


def test_cli_integrations_without_cycles_counts_the_rows():
    proc = _run(["--kind", "integrations", "--stdin"], stdin=json.dumps(_pairs("Blocked")))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["pairs_blocked"] == 1


def test_cli_requirements():
    rows = {"rows": [{"requirement_id": "R1", "verdict": "Not Addressed"}]}
    proc = _run(["--kind", "requirements", json.dumps(rows)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["requirements_not_addressed"] == 1


def test_cli_a_cycles_file_that_cannot_be_read_exits_1(tmp_path):
    proc = _run(["--kind", "integrations", "--cycles", str(tmp_path / "missing.json"), "--stdin"],
                stdin=json.dumps(_pairs("Verified")))
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    proc = _run(["--kind", "integrations", "--cycles", str(bad), "--stdin"], stdin=json.dumps(_pairs("Verified")))
    assert proc.returncode == 1


def test_cli_a_malformed_cycles_file_exits_2(tmp_path):
    cycles = tmp_path / "cycles.json"
    cycles.write_bytes(b'{"cycles": [["a", "b"]]}')
    proc = _run(["--kind", "integrations", "--cycles", str(cycles), "--stdin"], stdin=json.dumps(_pairs("Verified")))
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_cycles_only_with_integrations(tmp_path):
    proc = _run(["--kind", "requirements", "--cycles", str(tmp_path / "c.json"), '{"rows": []}'])
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_cli_reads_a_utf8_row_file_under_a_cp1252_console():
    # The stages redirect UTF-8 row files into --stdin, which a Windows
    # console decodes as cp1252: the second byte of `\u00c1` is undefined there.
    rows = {"rows": [{"requirement_id": "R\u00c1", "verdict": "Fulfilled"},
                     {"requirement_id": "R2", "verdict": "Not Addressed"}]}
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    args = [sys.executable, str(SCRIPT_PATH), "--kind", "requirements", "--stdin"]
    proc = subprocess.run(args, input=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
                          capture_output=True, env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["requirements_fulfilled"], out["requirements_not_addressed"]) == (1, 1)
    # An error naming the row keeps its name.
    rows["rows"][1]["requirement_id"] = "r\u00e1"
    proc = subprocess.run(args, input=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
                          capture_output=True, env=env, check=False)
    assert proc.returncode == 2, proc.stderr
    assert "r\u00e1" in json.loads(proc.stdout)["error"]


def test_cli_unknown_kind_is_a_usage_error():
    proc = _run(["--kind", "pairs", '{"rows": []}'])
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_cli_the_default_kind_is_coverage():
    payload = json.dumps({"rows": [{"technology": "react", "verdict": "Covered"}]})
    assert json.loads(_run([payload]).stdout) == json.loads(_run(["--kind", "coverage", payload]).stdout)


# --- --render: the report rows ----------------------------------------------------


def _coverage(*rows):
    return {"rows": [dict(zip(("technology", "verdict", "section", "skill"), row)) for row in rows]}


def test_render_coverage_gives_each_technology_its_row():
    lines = mod.render_coverage(_coverage(("React", "Covered", "Tech Stack", "react"),
                                          ("postgres", "Missing", "Data", None),
                                          ("old-orm", "Replaced", None, None)))
    assert lines == ["| React | Tech Stack | react | Covered |",
                     "| postgres | Data | none | Missing |",
                     "| old-orm | none | none | Replaced |"]


@pytest.mark.parametrize("rows, needle", [
    pytest.param([("react", "Covered", "Tech Stack", None)], "names no skill", id="covered-without-skill"),
    pytest.param([("pg", "Missing", "Data", "postgres")], "names a skill", id="missing-with-skill"),
    pytest.param([("pg", "Replaced", None, "postgres")], "names a skill", id="replaced-with-skill"),
    pytest.param([("react", "Covered", 3, "react")], "`section`", id="section-not-text"),
    pytest.param([("react", "covered", None, "react")], "verdict", id="bad-token"),
    pytest.param([("React", "Covered", None, "react"), ("react", "Missing", None, None)], "duplicate",
                 id="duplicate"),
])
def test_render_coverage_checks_the_rows(rows, needle):
    out = mod.render_coverage(_coverage(*rows))
    assert out["code"] == "INVALID_INPUT" and needle in out["error"], out


@pytest.mark.parametrize("rows, needle", [
    pytest.param([("react", "Covered", "Tech Stack", None)], "names no skill", id="covered-without-skill"),
    pytest.param([("pg", "Missing", "Data", "postgres")], "names a skill", id="missing-with-skill"),
    pytest.param([("react", "Covered", None, 7)], "`skill`", id="skill-not-text"),
])
def test_the_tally_refuses_a_row_render_would_refuse(rows, needle):
    """The section 3 tally checks the rows file as --render will, before it counts."""
    out = mod.tally(_coverage(*rows))
    assert out["code"] == "INVALID_INPUT" and needle in out["error"], out
    proc = _run(["--stdin"], stdin=json.dumps(_coverage(*rows)))
    assert proc.returncode == 2 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_the_tally_still_counts_rows_without_a_skill_key():
    """A direct caller's rows carry only technology and verdict: no pairing to check."""
    out = mod.tally({"rows": [{"technology": "react", "verdict": "Covered"}]})
    assert out["covered_count"] == 1 and out["coverage_percentage"] == 100


def _verdicts(*rows):
    return {"rows": [dict(zip(("lib_a", "lib_b", "verdict", "rationale"), row)) for row in rows]}


def test_render_integrations_gives_each_pair_then_each_cycle_its_row():
    cycles = {"cycles": [["oms-cognee", "zod", "react-query", "oms-cognee"]], "cycle_count": 1}
    lines = mod.render_integrations(_verdicts(("react-query", "zod", "Verified", "zod cites react-query, line 3"),
                                              ("oms-cognee", "zod", "Risky", "skill modified mid-run: re-run [VS]")),
                                    cycles)
    assert lines == [
        "| react-query | zod | Verified | zod cites react-query, line 3 |",
        "| oms-cognee | zod | Risky | skill modified mid-run: re-run [VS] |",
        "| cycle | oms-cognee \u2192 zod \u2192 react-query \u2192 oms-cognee | Risky | circular integration "
        "dependency detected: `oms-cognee \u2192 zod \u2192 react-query \u2192 oms-cognee` |",
    ]
    # The rows the table holds are the ones the tally counts.
    counted = mod.tally_integrations(_verdicts(("a", "b", "Verified", "x"), ("c", "d", "Risky", "y")), cycles)
    assert counted["row_count"] == len(mod.render_integrations(
        _verdicts(("a", "b", "Verified", "x"), ("c", "d", "Risky", "y")), cycles))


def test_a_cell_stays_on_one_line_with_its_pipes_escaped():
    [line] = mod.render_integrations(_verdicts(("a", "b", "Plausible", "a | b, neither cites\nthe other")))
    assert line == "| a | b | Plausible | a \\| b, neither cites the other |"


@pytest.mark.parametrize("rows, needle", [
    pytest.param([("a", "b", "Verified", None)], "`rationale`", id="no-rationale"),
    pytest.param([("a", "b", "Verified", " ")], "`rationale`", id="blank-rationale"),
    pytest.param([("a", "b", "verified", "x")], "verdict", id="bad-token"),
    pytest.param([("a", "a", "Verified", "x")], "with itself", id="self-pair"),
])
def test_render_integrations_checks_the_rows(rows, needle):
    out = mod.render_integrations(_verdicts(*rows))
    assert out["code"] == "INVALID_INPUT" and needle in out["error"], out


def test_render_integrations_checks_the_cycles():
    out = mod.render_integrations(_verdicts(("a", "b", "Verified", "x")), {"cycles": [["a", "b"]]})
    assert out["code"] == "INVALID_INPUT" and "closed node path" in out["error"]


def test_cli_render_prints_the_rows_only(tmp_path):
    cycles = tmp_path / "cycles.json"
    cycles.write_bytes(json.dumps({"cycles": [["a0", "b0", "c0", "a0"]], "cycle_count": 1}).encode("utf-8"))
    rows = json.dumps(_verdicts(("a0", "b0", "Verified", "b0 cites a0")), ensure_ascii=False).encode("utf-8")
    args = [sys.executable, str(SCRIPT_PATH), "--kind", "integrations", "--render", "--cycles", str(cycles), "--stdin"]
    # A Windows console's cp1252 has no arrow: the rows print as UTF-8 all the same.
    proc = subprocess.run(args, input=rows, capture_output=True, check=False,
                          env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.decode("utf-8").splitlines() == [
        "| a0 | b0 | Verified | b0 cites a0 |",
        "| cycle | a0 \u2192 b0 \u2192 c0 \u2192 a0 | Risky | circular integration dependency detected: "
        "`a0 \u2192 b0 \u2192 c0 \u2192 a0` |"]
    empty = _run(["--render", "--stdin"], stdin='{"rows": []}')
    assert (empty.returncode, empty.stdout) == (0, "")
    refused = _run(["--render", "--stdin"], stdin=json.dumps(_coverage(("react", "Covered", None, None))))
    assert refused.returncode == 2 and json.loads(refused.stdout)["code"] == "INVALID_INPUT"


def test_cli_render_has_no_requirements_table():
    proc = _run(["--kind", "requirements", "--render", '{"rows": []}'])
    assert proc.returncode == 2 and proc.stdout == ""


# --- The stages that persist the counts -------------------------------------------


def _between(path, start, end):
    text = path.read_text(encoding="utf-8")
    at = text.index(start)
    return text[at:text.index(end, at)]


def test_integrations_shows_and_persists_the_pair_counts_from_the_tally():
    path = SKILL / "references" / "integrations.md"
    # The tally runs once every pair and cycle row exists, before anything shows a count.
    rate = _between(path, "### 4. Cross-Reference Each Integration Pair", "### 5.")
    call = 'uv run {coverageTallyScript} --kind integrations --cycles "{run_dir}/cycles.json" --stdin'
    assert call in rate
    assert rate.index("**For each cycle**") < rate.index(call)
    display = _between(path, "### 5. Display Integration Results", "### 6.")
    assert "{pairs_verified} Verified, {pairs_plausible} Plausible, {pairs_risky} Risky, {pairs_blocked} Blocked" in display
    assert "{verified_count}" not in display
    write = _between(path, "### 6. Append to Report", "### 7.")
    assert call not in write
    # The canonical rows come from the same rows file, rendered, never typed again.
    render = 'uv run {coverageTallyScript} --kind integrations --render --cycles "{run_dir}/cycles.json" --stdin'
    assert render + ' < "{run_dir}/verdict-rows.json"' in write
    assert '"rationale":' in rate and "Add one row per pair" not in write
    for key, field in (("pairsVerified", "pairs_verified"), ("pairsPlausible", "pairs_plausible"),
                       ("pairsRisky", "pairs_risky"), ("pairsBlocked", "pairs_blocked")):
        assert f"`{key}` \u2190 `{field}`" in write, key
    # The all-Blocked warning reads the same tally.
    proceed = _between(path, "### 7. Auto-Proceed", "Load, read the full file")
    assert "`pairs_blocked` equals `pair_count`" in proceed
    assert "coverageTallyScript: 'scripts/skf-coverage-tally.py'" in path.read_text(encoding="utf-8")


def test_requirements_shows_and_persists_its_counts_from_the_tally():
    path = SKILL / "references" / "requirements.md"
    assess = _between(path, "### 3. Assess Stack Coverage", "### 4.")
    call = 'uv run {coverageTallyScript} --kind requirements --stdin < "{run_dir}/requirement-rows.json"'
    assert call in assess
    display = _between(path, "### 4. Display Requirements Results", "### 5.")
    assert ("{requirements_fulfilled} Fulfilled, {requirements_partial} Partially Fulfilled, "
            "{requirements_not_addressed} Not Addressed") in display
    write = _between(path, "### 5. Append to Report", "### 6.")
    assert call not in write
    for key, field in (("requirementsFulfilled", "requirements_fulfilled"),
                       ("requirementsPartial", "requirements_partial"),
                       ("requirementsNotAddressed", "requirements_not_addressed")):
        assert f"`{key}` \u2190 `{field}`" in write, key
    assert "coverageTallyScript: 'scripts/skf-coverage-tally.py'" in path.read_text(encoding="utf-8")


def test_coverage_tallies_and_renders_one_rows_file():
    path = SKILL / "references" / "coverage.md"
    tally_section = _between(path, "### 3. Cross-Reference Against Skills", "### 4.")
    assert 'uv run {coverageTallyScript} --stdin < "{run_dir}/coverage-rows.json"' in tally_section
    assert '"section":' in tally_section and '"skill":' in tally_section and "echo '<rows JSON>'" not in tally_section
    display = _between(path, "### 5. Display Coverage Results", "### 6.")
    assert 'uv run {coverageTallyScript} --render --stdin < "{run_dir}/coverage-rows.json"' in display
    assert "{the rendered rows, as printed}" in display and "{tech_name} | {section_heading}" not in display
    write = _between(path, "### 6. Append to Report", "### 7.")
    assert "the rows §5 rendered, as printed" in write


def test_the_stage_calls_fit_the_parser():
    parser = mod._build_parser()
    for words in (
        ["--kind", "integrations", "--cycles", "c.json", "--stdin"],
        ["--kind", "integrations", "--render", "--cycles", "c.json", "--stdin"],
        ["--kind", "requirements", "--stdin"],
        ["--render", "--stdin"],
        ["--stdin"],
    ):
        parser.parse_args(words)


def test_a_stage_that_runs_the_tally_names_it_in_its_frontmatter():
    for name in ("coverage.md", "integrations.md", "requirements.md"):
        text = (SKILL / "references" / name).read_text(encoding="utf-8")
        frontmatter = text.split("\n---\n", 1)[0]
        assert "uv run {coverageTallyScript}" in text, name
        assert "coverageTallyScript: 'scripts/skf-coverage-tally.py'" in frontmatter, name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
