#!/usr/bin/env python3
"""Tests for combine-external-scores.py (skf-test-skill external-validators.md §4).

Covers the three §4 branches (both tools -> mean, one tool -> passthrough,
neither -> null), JS-compatible rounding of odd-sum averages, the toolsUsed /
available fields, schema validation, and the subprocess CLI contract.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "combine-external-scores.py"
)

spec = importlib.util.spec_from_file_location("combine_external_scores", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
combine = mod.combine


# --------------------------------------------------------------------------
# Both tools ran -> mean
# --------------------------------------------------------------------------


def test_both_even_sum_mean():
    out = combine({"skillCheckScore": 73, "tesslReviewScore": 45})
    assert out["externalScore"] == 59.0
    assert out["toolsUsed"] == ["skill-check", "tessl"]
    assert out["available"] is True


def test_both_odd_sum_half_up():
    """(80 + 73) / 2 = 76.5 — the odd-sum case an in-prompt round would swing."""
    out = combine({"skillCheckScore": 80, "tesslReviewScore": 73})
    assert out["externalScore"] == 76.5


# --------------------------------------------------------------------------
# One tool ran -> passthrough
# --------------------------------------------------------------------------


def test_only_skill_check():
    out = combine({"skillCheckScore": 90, "tesslReviewScore": None})
    assert out["externalScore"] == 90.0
    assert out["toolsUsed"] == ["skill-check"]
    assert out["available"] is True


def test_only_tessl_omitted_field():
    out = combine({"tesslReviewScore": 62})
    assert out["externalScore"] == 62.0
    assert out["toolsUsed"] == ["tessl"]


# --------------------------------------------------------------------------
# Neither ran -> null
# --------------------------------------------------------------------------


def test_neither_null():
    out = combine({"skillCheckScore": None, "tesslReviewScore": None})
    assert out["externalScore"] is None
    assert out["toolsUsed"] == []
    assert out["available"] is False


def test_empty_object_null():
    out = combine({})
    assert out["externalScore"] is None
    assert out["available"] is False


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"skillCheckScore": 101},
        {"tesslReviewScore": -1},
        {"skillCheckScore": "80"},
        {"skillCheckScore": True},
        None,
    ],
)
def test_invalid_input(bad):
    out = combine(bad)
    assert out["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------
# CLI contract (subprocess)
# --------------------------------------------------------------------------


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_ok():
    res = _run_cli(["--stdin"], stdin=json.dumps({"skillCheckScore": 80, "tesslReviewScore": 73}))
    assert res.returncode == 0
    assert json.loads(res.stdout)["externalScore"] == 76.5


def test_cli_positional_ok():
    res = _run_cli([json.dumps({"skillCheckScore": 90})])
    assert res.returncode == 0
    assert json.loads(res.stdout)["externalScore"] == 90.0


def test_cli_no_input_exit_1():
    res = _run_cli(["--stdin"], stdin="")
    assert res.returncode == 1


def test_cli_invalid_schema_exit_2():
    res = _run_cli(["--stdin"], stdin=json.dumps({"skillCheckScore": 200}))
    assert res.returncode == 2
    assert json.loads(res.stdout)["code"] == "INVALID_INPUT"


def test_cli_malformed_json_exit_1():
    res = _run_cli(["--stdin"], stdin="{bad")
    assert res.returncode == 1


def test_cli_output_writes_the_score_file(tmp_path):
    """external-validators §4 writes `{run_dir}/external.json`, which compute-score.py --external reads,
    also when neither tool scored (externalScore null)."""
    out_path = tmp_path / "run" / "external.json"
    res = _run_cli(["--stdin", "--output", str(out_path)], stdin=json.dumps({}))
    assert res.returncode == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written == json.loads(_run_cli(["--stdin"], stdin=json.dumps({})).stdout)
    assert written["externalScore"] is None and json.loads(res.stdout)["output"] == str(out_path)  # #1063


def test_cli_output_prints_only_a_summary(tmp_path):
    """#1063: with --output stdout gives the two fields external-validators §4 binds, `toolsUsed` still a list, and
    the path; the file keeps `available` and equals the stdout of the same run without --output. A refused input
    prints its error object as before."""
    out_path = tmp_path / "run" / "external.json"
    res = _run_cli(["--stdin", "--output", str(out_path)], stdin=json.dumps({}))
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == {"externalScore": None, "toolsUsed": [], "output": str(out_path)}
    assert json.loads(out_path.read_text(encoding="utf-8")) == {"externalScore": None, "toolsUsed": [],
                                                                 "available": False}
    both = json.dumps({"skillCheckScore": 80, "tesslReviewScore": 73})
    res = _run_cli(["--stdin", "--output", str(out_path)], stdin=both)
    assert json.loads(res.stdout) == {"externalScore": 76.5, "toolsUsed": ["skill-check", "tessl"],
                                      "output": str(out_path)}
    assert json.loads(out_path.read_text(encoding="utf-8")) == json.loads(_run_cli(["--stdin"], stdin=both).stdout)

    bad = json.dumps({"skillCheckScore": 200})
    refused = _run_cli(["--stdin", "--output", str(out_path)], stdin=bad)
    assert refused.returncode == 2 and not out_path.exists()
    assert json.loads(refused.stdout) == json.loads(_run_cli(["--stdin"], stdin=bad).stdout)
    assert json.loads(refused.stdout)["code"] == "INVALID_INPUT"


def test_cli_refused_input_removes_a_stale_score_file(tmp_path):
    out_path = tmp_path / "external.json"
    out_path.write_bytes(b'{"externalScore": 100}')
    res = _run_cli(["--stdin", "--output", str(out_path)], stdin=json.dumps({"skillCheckScore": 200}))
    assert res.returncode == 2 and not out_path.exists()


# --------------------------------------------------------------------------
# File mode: the saved skill-check and Tessl Review JSON (#1120)
# --------------------------------------------------------------------------

SUMMARY_KEYS = ["externalScore", "toolsUsed", "skillCheckScore", "skillCheckErrorCount", "skillCheckWarningCount",
                "descriptionIssues", "output"]
LIST_KEYS = ("skillCheckDiagnostics", "tesslValidationFindings", "tesslDescriptionSuggestions",
             "tesslContentSuggestions")


def _diagnostic(rule, file="skills/demo/SKILL.md", line=1, severity="warn", **extra):
    return {"ruleId": rule, "severity": severity, "message": f"{rule} reported", "file": file, "line": line,
            "column": 1, **extra}


def _skill_check(path, diagnostics, scores=None, tail="", **extra):
    data = {"summary": {"skillCount": 1, "errorCount": sum(d["severity"] == "error" for d in diagnostics),
                        "warningCount": sum(d["severity"] == "warn" for d in diagnostics)},
            "diagnostics": diagnostics, "metadata": {"roots": ["skills"], "format": "json"}, **extra}
    if scores is not None:
        data["scores"] = scores
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2) + "\n" + tail).encode("utf-8"))
    return path


def _tessl(path, status="reviewed", review=73, description=85, **extra):
    data = {"status": status, "summary": "x", "detail": None, "workspace": "w", "tessl_version": "0.80.0",
            "exit_code": 0, "run_id": "r1",
            "review_score": review if status == "reviewed" else None,
            "description_score": description if status == "reviewed" else None,
            "content_score": 60 if status == "reviewed" else None,
            "validation": {"passed": False, "errors": 0, "warnings": 1,
                           "findings": [{"name": "frontmatter_unknown_keys", "status": "warning",
                                         "message": "unknown key"}]} if status == "reviewed" else None,
            "description_suggestions": ["Name the triggers."] if status == "reviewed" else [],
            "content_suggestions": ["Add examples.", "Drop the citations."] if status == "reviewed" else [],
            "warnings": [], **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


def _files(tmp_path, *extra, cwd=None):
    run = tmp_path / "run"
    args = ["--skill-check", str(run / "skill-check.json"), "--tessl", str(run / "tessl.json"),
            "--skill-dir", str(tmp_path / "skills" / "demo"), *extra]
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], capture_output=True, text=True,
                          cwd=cwd or tmp_path)


@pytest.fixture
def skill(tmp_path):
    folder = tmp_path / "skills" / "demo"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_bytes(b"---\nname: demo\ndescription: Demo.\n---\n# Demo\n")
    return folder


def test_files_both_tools(tmp_path, skill):
    """TS both tools: skill-check's score for this skill with a description warning, and a reviewed Tessl result."""
    run = tmp_path / "run"
    _skill_check(run / "skill-check.json", [_diagnostic("description.use_when_phrase", suggestion="Say Use when.")],
                 [{"skillId": "x/other", "relativePath": "skills/other/SKILL.md", "score": 20},
                  {"skillId": "x/demo", "relativePath": "skills/demo/SKILL.md", "score": 80}], tail="Wrote r.json\n")
    _tessl(run / "tessl.json")
    res = _files(tmp_path, "--output", str(run / "external.json"))
    assert res.returncode == 0, res.stdout + res.stderr
    summary = json.loads(res.stdout)
    assert list(summary) == SUMMARY_KEYS
    assert summary == {"externalScore": 76.5, "toolsUsed": ["skill-check", "tessl"], "skillCheckScore": 80,
                       "skillCheckErrorCount": 0, "skillCheckWarningCount": 1, "descriptionIssues": True,
                       "output": str(run / "external.json")}
    written = json.loads((run / "external.json").read_text(encoding="utf-8"))
    assert (written["available"], written["tesslReviewScore"], written["tesslDescriptionScore"]) == (True, 73, 85)
    assert written["skillCheckDiagnostics"] == [
        {"ruleId": "description.use_when_phrase", "severity": "warn", "message": "description.use_when_phrase reported",
         "file": "SKILL.md", "line": 1, "suggestion": "Say Use when."}]
    assert written["tesslValidationFindings"] == [{"name": "frontmatter_unknown_keys", "status": "warning",
                                                   "message": "unknown key"}]
    assert (written["tesslDescriptionSuggestions"], written["tesslContentSuggestions"]) == (
        ["Name the triggers."], ["Add examples.", "Drop the citations."])


def test_files_nothing_ran(tmp_path, skill):
    """TS nothing ran: no skill-check (the probe found none) and no Tessl helper."""
    res = _files(tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    out = json.loads(res.stdout)
    assert (out["externalScore"], out["toolsUsed"], out["available"]) == (None, [], False)
    assert (out["skillCheckScore"], out["skillCheckErrorCount"], out["skillCheckWarningCount"]) == (None, None, None)
    assert out["descriptionIssues"] is False and out["tesslDescriptionScore"] is None
    assert all(out[key] == [] for key in LIST_KEYS)


def test_files_a_stopped_tessl_call(tmp_path, skill):
    """TS stopped Tessl call: the redirect left tessl.json empty, so skill-check's score stands alone."""
    run = tmp_path / "run"
    _skill_check(run / "skill-check.json", [], qualityScore=90)
    (run / "tessl.json").write_bytes(b"")
    out = json.loads(_files(tmp_path).stdout)
    assert (out["externalScore"], out["toolsUsed"], out["tesslReviewScore"], out["tesslDescriptionScore"]) == (
        90.0, ["skill-check"], None, None)


@pytest.mark.parametrize("status", ["pending", "off", "timeout", "failed"])
def test_files_a_review_that_did_not_finish_gives_no_tessl_score(tmp_path, skill, status):
    run = tmp_path / "run"
    _tessl(run / "tessl.json", status=status)
    out = json.loads(_files(tmp_path).stdout)
    assert (out["externalScore"], out["toolsUsed"], out["tesslContentSuggestions"]) == (None, [], [])


def test_files_the_skill_id_matches_from_another_folder(tmp_path, skill):
    """relativePath names the folder skill-check ran in; from another folder the skillId rule finds the entry."""
    run = tmp_path / "run"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _skill_check(run / "skill-check.json", [], [{"skillId": f"{tmp_path.name}/demo",
                                                 "relativePath": "skills/demo/SKILL.md", "score": 64}])
    out = json.loads(_files(tmp_path, cwd=elsewhere).stdout)
    assert out["skillCheckScore"] == 64


def test_files_a_diagnostic_outside_the_skill_keeps_its_path(tmp_path, skill):
    run = tmp_path / "run"
    _skill_check(run / "skill-check.json", [_diagnostic("links.local_markdown_resolves", line=7),
                                            _diagnostic("file.trailing_newline_single", file="other/SKILL.md")])
    out = json.loads(_files(tmp_path).stdout)
    assert [(d["file"], d["line"]) for d in out["skillCheckDiagnostics"]] == [("SKILL.md", 7),
                                                                             ("other/SKILL.md", 1)]
    assert out["descriptionIssues"] is False


@pytest.mark.parametrize("rule, flagged", [("description.max_length", True),
                                           ("frontmatter.description_required", True),
                                           ("frontmatter.name_required", False), ("body.max_lines", False)])
def test_files_the_description_rules(tmp_path, skill, rule, flagged):
    run = tmp_path / "run"
    _skill_check(run / "skill-check.json", [_diagnostic(rule, severity="error")])
    out = json.loads(_files(tmp_path).stdout)
    assert out["descriptionIssues"] is flagged and out["skillCheckErrorCount"] == 1


def test_files_an_out_of_range_tessl_score_is_refused(tmp_path, skill):
    run = tmp_path / "run"
    _tessl(run / "tessl.json", review=140)
    (run / "external.json").write_bytes(b'{"externalScore": 100}')
    res = _files(tmp_path, "--output", str(run / "external.json"))
    assert res.returncode == 2 and json.loads(res.stdout)["code"] == "INVALID_INPUT"
    assert not (run / "external.json").exists()


@pytest.mark.parametrize("args, message", [
    (["--stdin", "--skill-check", "s.json", "--skill-dir", "d"], "in place of a JSON input"),
    (['{"skillCheckScore": 80}', "--tessl", "t.json", "--skill-dir", "d"], "in place of a JSON input"),
    (["--json-input", "{}", "--skill-dir", "d"], "in place of a JSON input"),
    (["--skill-check", "s.json"], "need --skill-dir"),
    (["--skill-dir", "d"], "goes with --skill-check or --tessl"),
], ids=["stdin", "positional", "json-input", "no-skill-dir", "skill-dir-alone"])
def test_files_refuses_a_mixed_or_partial_call(tmp_path, args, message):
    """The file flags beside a JSON input, or --skill-dir without a file, are refused, and a stale file goes."""
    stale = tmp_path / "external.json"
    stale.write_bytes(b'{"externalScore": 100}')
    res = _run_cli([*args, "--output", str(stale)], stdin="{}")
    assert res.returncode == 2, res.stdout
    out = json.loads(res.stdout)
    assert out["code"] == "INVALID_INPUT" and message in out["error"]
    assert not stale.exists()


def test_files_without_the_shared_reader(tmp_path):
    """HELPER_MISSING: the script loads skf-summarize-validation.py from <its folder>/../../shared/scripts/."""
    copy = tmp_path / "module" / "skf-test-skill" / "scripts" / SCRIPT_PATH.name
    copy.parent.mkdir(parents=True)
    copy.write_bytes(SCRIPT_PATH.read_bytes())
    stale = tmp_path / "external.json"
    stale.write_bytes(b"{}")
    res = subprocess.run([sys.executable, str(copy), "--skill-check", "s.json", "--skill-dir", "d",
                          "--output", str(stale)], capture_output=True, text=True)
    assert res.returncode == 1
    out = json.loads(res.stdout)
    assert out["code"] == "HELPER_MISSING" and "skf-summarize-validation.py" in out["error"]
    assert not stale.exists()
    # With the shared folder beside it, as an installed module lays it out, the same copy runs.
    shared = tmp_path / "module" / "shared" / "scripts"
    shared.mkdir(parents=True)
    reader = REPO_ROOT / "src" / "shared" / "scripts" / "skf-summarize-validation.py"
    (shared / reader.name).write_bytes(reader.read_bytes())
    res = subprocess.run([sys.executable, str(copy), "--skill-check", "s.json", "--skill-dir", "d"],
                         capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 0 and json.loads(res.stdout)["externalScore"] is None


def test_the_json_modes_are_unchanged_beside_file_mode(tmp_path):
    """The JSON-input output keeps its three keys, and its --output summary its two fields and the path."""
    res = _run_cli(["--stdin"], stdin=json.dumps({"skillCheckScore": 80}))
    assert json.loads(res.stdout) == {"externalScore": 80.0, "toolsUsed": ["skill-check"], "available": True}
    out_path = tmp_path / "external.json"
    res = _run_cli(["--stdin", "--output", str(out_path)], stdin=json.dumps({"skillCheckScore": 80}))
    assert json.loads(res.stdout) == {"externalScore": 80.0, "toolsUsed": ["skill-check"], "output": str(out_path)}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
