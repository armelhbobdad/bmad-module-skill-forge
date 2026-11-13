"""Tests for campaign-status.py: the state summary.

`campaign status` and step-resume's summary read their counts from this
script. These tests pin the per-status counts, the absence of any backup
comparison (step-resume recovers a damaged state through
`campaign-state.py recover`), and the exit codes for a missing or unreadable
state.

#1141: --export-names gives step-09 Refine Architecture's scope, the skill
folder of every completed skill, so a Tier B skill whose folder differs from
its campaign name stays in scope.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-status.py"
REFINE = REPO_ROOT / "src" / "skf-campaign" / "references" / "step-09-refine.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("campaign_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _state(stage: int = 4, last_updated: str = "2026-10-01T12:00:00+00:00", statuses=None) -> dict:
    statuses = statuses if statuses is not None else ["completed", "completed", "active", "pending", "failed",
                                                      "skipped"]
    return {
        "campaign": {"name": "demo", "started_at": "2026-10-01T10:00:00+00:00", "last_updated": last_updated,
                     "current_stage": stage,
                     "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80}},
        "skills": [{"name": f"s{i}", "status": status, "tier": "A"} for i, status in enumerate(statuses)],
        "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
    }


def _write(tmp_path: pathlib.Path, name: str, state) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(state), encoding="utf-8")
    return path


def _run(capsys, *argv: str) -> tuple[int, dict]:
    rc = mod.main(list(argv))
    captured = capsys.readouterr()
    return rc, json.loads((captured.out if rc == 0 else captured.err).strip())


class TestSummary:
    def test_counts_every_status(self, tmp_path, capsys):
        rc, out = _run(capsys, "--state-file", str(_write(tmp_path, "s.yaml", _state())))
        assert rc == 0
        assert {k: out[k] for k in ("total", "completed", "pending", "active", "failed", "skipped")} == {
            "total": 6, "completed": 2, "pending": 1, "active": 1, "failed": 1, "skipped": 1}
        assert (out["campaign_name"], out["current_stage"]) == ("demo", 4)
        assert out["last_updated"] == "2026-10-01T12:00:00+00:00"
        assert "backup_comparison" not in out

    def test_no_skills(self, tmp_path, capsys):
        rc, out = _run(capsys, "--state-file", str(_write(tmp_path, "s.yaml", _state(statuses=[]))))
        assert rc == 0
        assert out["total"] == 0 and out["completed"] == 0

    def test_an_unknown_status_counts_toward_the_total_only(self, tmp_path, capsys):
        rc, out = _run(capsys, "--state-file", str(_write(tmp_path, "s.yaml", _state(statuses=["done", "pending"]))))
        assert rc == 0
        assert (out["total"], out["pending"], out["completed"]) == (2, 1, 0)


class TestErrors:
    def test_missing_state_exit_2(self, tmp_path, capsys):
        rc, err = _run(capsys, "--state-file", str(tmp_path / "none.yaml"))
        assert (rc, err["code"]) == (2, "STATE_UNREADABLE")

    @pytest.mark.parametrize("text", ["campaign: [half", "- a\n- b\n"], ids=["bad-yaml", "not-a-mapping"])
    def test_unreadable_state_exit_2(self, tmp_path, capsys, text):
        path = tmp_path / "s.yaml"
        path.write_text(text, encoding="utf-8")
        rc, err = _run(capsys, "--state-file", str(path))
        assert (rc, err["code"]) == (2, "STATE_UNREADABLE")

    def test_the_backup_file_option_is_gone(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--state-file", str(_write(tmp_path, "s.yaml", _state())), "--backup-file", "x.bak"])
        assert exc.value.code == 2

    def test_state_file_is_required(self):
        with pytest.raises(SystemExit) as exc:
            mod.main([])
        assert exc.value.code == 2


def test_cli_prints_one_json_line(tmp_path):
    state = _write(tmp_path, "s.yaml", _state())
    proc = subprocess.run([sys.executable, str(SCRIPT), "--state-file", str(state)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.splitlines()
    assert json.loads(line)["total"] == 6


def test_step_resume_reads_the_fields_this_script_prints():
    resume = (REPO_ROOT / "src" / "skf-campaign" / "references" / "step-resume.md").read_text(encoding="utf-8")
    assert "uv run {statusScript} --state-file {stateFile}" in resume
    for field in ("completed", "total", "pending", "active", "failed", "skipped"):
        assert f"`{field}`" in resume, field


def _scope_state(*skills: dict) -> dict:
    state = _state(statuses=[])
    state["skills"] = [{"tier": "A", "skill_path": None, **skill} for skill in skills]
    return state


SCOPE = _scope_state(
    {"name": "cognee-lib", "status": "completed", "tier": "B", "skill_path": "skills/cognee/0.3.1/cognee"},
    {"name": "core", "status": "completed"},
    {"name": "web", "status": "failed", "skill_path": "skills/web/1.0.0/web"},
)


class TestExportNames:
    """step-09's --scope-skills: each completed skill's folder, the name Refine Architecture's inventory knows."""

    def _names(self, capsys, tmp_path, state) -> tuple[int, str]:
        rc = mod.main(["--state-file", str(_write(tmp_path, "s.yaml", state)), "--export-names"])
        return rc, capsys.readouterr().out

    def test_completed_skills_by_folder_in_skills_order(self, tmp_path, capsys):
        assert self._names(capsys, tmp_path, SCOPE) == (0, "cognee,core\n")

    def test_no_completed_skill_prints_an_empty_line(self, tmp_path, capsys):
        state = _scope_state({"name": "web", "status": "failed"}, {"name": "cli", "status": "pending", "tier": "B"})
        assert self._names(capsys, tmp_path, state) == (0, "\n")

    def test_a_folder_two_skills_share_is_named_once(self, tmp_path, capsys):
        state = _scope_state({"name": "a", "status": "completed", "skill_path": "skills/lib/1.0.0/lib"},
                             {"name": "b", "status": "completed", "skill_path": "skills/lib/2.0.0/lib"})
        assert self._names(capsys, tmp_path, state) == (0, "lib\n")

    def test_an_unreadable_state_is_exit_2(self, tmp_path, capsys):
        rc = mod.main(["--state-file", str(tmp_path / "none.yaml"), "--export-names"])
        captured = capsys.readouterr()
        assert (rc, captured.out) == (2, "")
        assert json.loads(captured.err)["code"] == "STATE_UNREADABLE"

    @pytest.mark.parametrize("state, line", [(SCOPE, "cognee,core"), (_scope_state(), "")], ids=["scope", "none"])
    def test_cli_prints_one_line(self, tmp_path, state, line):
        path = _write(tmp_path, "s.yaml", state)
        proc = subprocess.run([sys.executable, str(SCRIPT), "--state-file", str(path), "--export-names"],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.splitlines() == [line]


def test_refine_scopes_by_the_folder_names_this_script_prints():
    text = REFINE.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter["statusScript"] == "scripts/campaign-status.py"
    [scope] = [line for line in text.splitlines() if line.startswith("- `--scope-skills`:")]
    assert "the line `uv run {statusScript} --state-file {stateFile} --export-names` prints, unchanged" in scope
    assert "Leave the flag out when that line is empty or the call exits non-zero." in scope
    assert 'status == "completed"' not in text
