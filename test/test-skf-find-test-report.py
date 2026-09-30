#!/usr/bin/env python3
"""Tests for src/shared/scripts/skf-find-test-report.py.

The one test-report lookup export-skill and update-skill share:
  - versioned glob: newest run id first, another skill's reports with the
    same name prefix ignored, an unfinished report skipped
  - flat glob when the version folder has none, or no --version is given
  - skf-test-skill-result-latest.json (versioned, then flat): the report its
    outputs[] names, or its summary when that report is gone
  - not-found, verdict and score normalization, CLI argument checks
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts" / "skf-find-test-report.py"

spec = importlib.util.spec_from_file_location("skf_find_test_report", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

SKILL = "demo"
VERSION = "1.2.0"


def write_report(folder: Path, run_id: str, *, result: str = "fail", score: str = "'72'", skill: str = SKILL) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"test-report-{skill}-{run_id}.md"
    path.write_text(
        "---\n"
        "workflowType: 'test-skill'\n"
        f"skillName: '{skill}'\n"
        f"runId: '{run_id}'\n"
        f"testResult: '{result}'\n"
        f"score: {score}\n"
        "testDate: '2026-09-30T10:10:10Z'\n"
        "stepsCompleted: ['init', 'report']\n"
        "---\n\n# Test Report\n",
        encoding="utf-8",
    )
    return path


def write_latest(folder: Path, outputs: list, summary: dict | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "skf-test-skill-result-latest.json"
    path.write_text(
        json.dumps(
            {
                "skill": "skf-test-skill",
                "status": "success",
                "timestamp": "2026-09-30T10:10:10Z",
                "runId": "20260930T101010Z-1-aaaa",
                "outputs": outputs,
                "summary": summary or {},
            }
        ),
        encoding="utf-8",
    )
    return path


def find(forge: Path, version: str | None = VERSION) -> dict:
    return mod.find_test_report(forge, SKILL, version)


@pytest.fixture
def forge(tmp_path: Path) -> Path:
    return tmp_path / "forge-data"


def test_embedded_doctests_pass():
    results = doctest.testmod(mod, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed"


class TestGlobs:
    def test_versioned_newest_wins(self, forge: Path):
        folder = forge / SKILL / VERSION
        write_report(folder, "20260901T080000Z-11-aaaa", result="pass", score="'95'")
        newest = write_report(folder, "20260930T101010Z-22-bbbb", result="fail", score="'71.5'")
        write_report(folder, "20260915T000000Z-33-cccc", result="pass")
        out = find(forge)
        assert out["status"] == "found"
        assert out["source"] == "versioned-glob"
        assert out["path"] == str(newest)
        assert out["testResult"] == "fail"
        assert out["score"] == 71.5
        assert out["run_id"] == "20260930T101010Z-22-bbbb"
        assert out["test_date"] == "2026-09-30T10:10:10Z"
        assert out["result_path"] is None

    def test_other_skill_with_same_prefix_is_ignored(self, forge: Path):
        folder = forge / SKILL / VERSION
        mine = write_report(folder, "20260901T080000Z-11-aaaa")
        write_report(folder, "20260930T101010Z-22-bbbb", skill=f"{SKILL}-extra")
        assert find(forge)["path"] == str(mine)

    def test_unfinished_report_is_skipped(self, forge: Path):
        folder = forge / SKILL / VERSION
        finished = write_report(folder, "20260901T080000Z-11-aaaa", result="fail")
        unfinished = write_report(folder, "20260930T101010Z-22-bbbb", result="", score="''")
        out = find(forge)
        assert out["path"] == str(finished)
        assert out["skipped"] == [{"path": str(unfinished), "reason": "unfinished"}]

    def test_flat_when_versioned_folder_has_none(self, forge: Path):
        (forge / SKILL / VERSION).mkdir(parents=True)
        flat = write_report(forge / SKILL, "20260901T080000Z-11-aaaa", result="pass", score="88")
        out = find(forge)
        assert out["source"] == "flat-glob"
        assert out["path"] == str(flat)
        assert out["testResult"] == "pass"
        assert out["score"] == 88

    def test_flat_without_a_version(self, forge: Path):
        flat = write_report(forge / SKILL, "20260901T080000Z-11-aaaa")
        out = find(forge, version=None)
        assert out["source"] == "flat-glob"
        assert out["path"] == str(flat)
        assert out["version"] is None

    def test_versioned_wins_over_a_newer_flat_report(self, forge: Path):
        versioned = write_report(forge / SKILL / VERSION, "20260901T080000Z-11-aaaa")
        write_report(forge / SKILL, "20260930T101010Z-22-bbbb")
        assert find(forge)["path"] == str(versioned)

    def test_run_id_from_file_name_when_frontmatter_has_none(self, forge: Path):
        folder = forge / SKILL / VERSION
        folder.mkdir(parents=True)
        path = folder / f"test-report-{SKILL}-20260930T101010Z-22-bbbb.md"
        path.write_text("---\ntestResult: \"PASS_WITH_DRIFT\"\nscore: 91\n---\n", encoding="utf-8")
        out = find(forge)
        assert out["run_id"] == "20260930T101010Z-22-bbbb"
        assert out["testResult"] == "pass-with-drift"
        assert out["score"] == 91


class TestLatestJson:
    def test_versioned_result_file_names_the_report(self, forge: Path):
        folder = forge / SKILL / VERSION
        report = folder / "archive" / f"test-report-{SKILL}-20260930T101010Z-22-bbbb.md"
        write_report(report.parent, "20260930T101010Z-22-bbbb", result="inconclusive", score="''")
        latest = write_latest(
            folder,
            [{"type": "report", "path": str(report)}],
            {"result": "INCONCLUSIVE", "score": 64},
        )
        out = find(forge)
        assert out["source"] == "latest-json"
        assert out["path"] == str(report)
        assert out["result_path"] == str(latest)
        assert out["testResult"] == "inconclusive"
        assert out["score"] == 64  # frontmatter score empty: taken from the summary

    def test_relative_output_path_resolves_beside_the_result_file(self, forge: Path):
        folder = forge / SKILL / VERSION
        write_report(folder / "kept", "20260930T101010Z-22-bbbb", result="pass", score="'93'")
        write_latest(folder, [{"type": "report", "path": f"kept/test-report-{SKILL}-20260930T101010Z-22-bbbb.md"}])
        out = find(forge)
        assert out["source"] == "latest-json"
        assert out["testResult"] == "pass"
        assert out["score"] == 93

    def test_flat_result_file_after_versioned(self, forge: Path):
        (forge / SKILL / VERSION).mkdir(parents=True)
        report = write_report(forge / SKILL / "old", "20260101T000000Z-1-aaaa", result="fail")
        latest = write_latest(forge / SKILL, [{"type": "report", "path": str(report)}])
        out = find(forge)
        assert out["source"] == "latest-json"
        assert out["result_path"] == str(latest)

    def test_missing_report_falls_back_to_the_summary(self, forge: Path):
        folder = forge / SKILL / VERSION
        write_latest(
            folder,
            [{"type": "report", "path": "gone/test-report-demo-20260930T101010Z-22-bbbb.md"}],
            {"result": "FAIL", "score": "70"},
        )
        out = find(forge)
        assert out["status"] == "found"
        assert out["path"] == "gone/test-report-demo-20260930T101010Z-22-bbbb.md"
        assert out["testResult"] == "fail"
        assert out["score"] == 70
        assert out["run_id"] == "20260930T101010Z-1-aaaa"
        assert any("missing" in w for w in out["warnings"])

    def test_report_found_by_name_without_a_type(self, forge: Path):
        folder = forge / SKILL / VERSION
        report = write_report(folder / "x", "20260930T101010Z-22-bbbb")
        write_latest(folder, [{"type": "manifest", "path": "m.json"}, {"path": str(report)}])
        assert find(forge)["path"] == str(report)

    def test_result_file_without_a_report_is_not_a_match(self, forge: Path):
        write_latest(forge / SKILL / VERSION, [{"type": "manifest", "path": "m.json"}])
        out = find(forge)
        assert out["status"] == "not-found"
        assert any("names no report" in w for w in out["warnings"])

    def test_unreadable_result_file(self, forge: Path):
        folder = forge / SKILL / VERSION
        folder.mkdir(parents=True)
        (folder / "skf-test-skill-result-latest.json").write_text("{", encoding="utf-8")
        out = find(forge)
        assert out["status"] == "not-found"
        assert out["warnings"]


def test_not_found(forge: Path):
    out = find(forge)
    assert out == {
        "status": "not-found",
        "skill_name": SKILL,
        "version": VERSION,
        "path": None,
        "source": None,
        "testResult": None,
        "score": None,
        "run_id": None,
        "test_date": None,
        "result_path": None,
        "skipped": [],
        "warnings": [],
    }


def test_cli_prints_the_result(forge: Path):
    report = write_report(forge / SKILL / VERSION, "20260930T101010Z-22-bbbb")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "find", "--forge-data-folder", str(forge), "--skill-name", SKILL, "--version", VERSION],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["path"] == str(report)
    assert out["source"] == "versioned-glob"


@pytest.mark.parametrize(("flag", "value"), [("--skill-name", "../demo"), ("--version", "..")])
def test_cli_refuses_a_path_as_a_name(forge: Path, flag: str, value: str):
    args = {"--skill-name": SKILL, "--version": VERSION, flag: value}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "find", "--forge-data-folder", str(forge), *[x for kv in args.items() for x in kv]],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 1
    assert "single folder name" in proc.stderr


def test_cli_usage_error_exits_2(forge: Path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "find", "--forge-data-folder", str(forge)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "--skill-name" in proc.stderr
