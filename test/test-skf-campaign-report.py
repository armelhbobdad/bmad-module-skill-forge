"""Tests for campaign-report.py — campaign report generation from state + template."""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "src" / "skf-campaign" / "scripts" / "campaign-report.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("campaign_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


def _write_state(tmp_path: Path, state: dict[str, Any]) -> Path:
    p = tmp_path / "_campaign-state.yaml"
    p.write_text(yaml.dump(state, default_flow_style=False), encoding="utf-8")
    return p


def _write_template(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "template.md"
    if content is None:
        content = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "skf-campaign"
            / "templates"
            / "campaign-report-template.md"
        ).read_text(encoding="utf-8")
    p.write_text(content, encoding="utf-8")
    return p


def _minimal_state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "campaign": {
            "name": "test-campaign",
            "started_at": "2026-01-01T00:00:00+00:00",
            "last_updated": "2026-01-01T02:30:00+00:00",
            "current_stage": 10,
            "quality_gate": {
                "hard": "zero-critical-high",
                "soft_target": 90,
                "soft_fallback": 80,
            },
            "health_findings_queue": "local",
        },
        "skills": [
            {
                "name": "skill-alpha",
                "status": "completed",
                "tier": "A",
                "pin": "v1.0.0",
                "brief_path": None,
                "skill_path": "skills/skill-alpha",
                "quality_score": 92,
                "workarounds_applied": ["fp-abc1234"],
                "depends_on": [],
                "started_at": "2026-01-01T00:10:00+00:00",
                "completed_at": "2026-01-01T01:00:00+00:00",
                "commit_sha": None,
            },
            {
                "name": "skill-beta",
                "status": "completed",
                "tier": "B",
                "pin": None,
                "brief_path": None,
                "skill_path": "skills/skill-beta",
                "quality_score": 88,
                "workarounds_applied": [],
                "depends_on": ["skill-alpha"],
                "started_at": "2026-01-01T01:00:00+00:00",
                "completed_at": "2026-01-01T02:00:00+00:00",
                "commit_sha": None,
            },
        ],
        "dependency_graph": {
            "execution_order": ["skill-alpha", "skill-beta"],
            "circular_deps_detected": False,
        },
    }
    base.update(overrides)
    return base


class TestComputeAggregates:
    def test_basic_aggregates(self):
        state = _minimal_state()
        agg = mod._compute_aggregates(state)

        assert agg["campaign_name"] == "test-campaign"
        assert agg["skills_completed"] == "2"
        assert agg["skills_failed"] == "0"
        assert agg["skills_skipped"] == "0"
        assert agg["quality_min"] == "88"
        assert agg["quality_max"] == "92"
        assert agg["quality_avg"] == "90.0"
        assert agg["total_workarounds"] == "1"
        assert agg["skills_with_workarounds"] == "1"

    def test_duration_format(self):
        state = _minimal_state()
        agg = mod._compute_aggregates(state)
        assert agg["duration"] == "2h 30m 0s"

    def test_no_completed_skills(self):
        state = _minimal_state(
            skills=[
                {
                    "name": "skill-x",
                    "status": "failed",
                    "tier": "A",
                    "pin": None,
                    "brief_path": None,
                    "skill_path": None,
                    "quality_score": None,
                    "workarounds_applied": [],
                    "depends_on": [],
                    "started_at": None,
                    "completed_at": None,
                    "commit_sha": None,
                }
            ]
        )
        agg = mod._compute_aggregates(state)
        assert agg["skills_completed"] == "0"
        assert agg["skills_failed"] == "1"
        assert agg["quality_min"] == "0"
        assert agg["quality_max"] == "0"
        assert agg["quality_avg"] == "0"
        assert "Failed Skills" in agg["failed_skipped_section"]

    def test_skipped_skills(self):
        state = _minimal_state()
        state["skills"].append(
            {
                "name": "skill-gamma",
                "status": "skipped",
                "tier": "B",
                "pin": None,
                "brief_path": None,
                "skill_path": None,
                "quality_score": None,
                "workarounds_applied": [],
                "depends_on": [],
                "started_at": None,
                "completed_at": None,
                "commit_sha": None,
            }
        )
        agg = mod._compute_aggregates(state)
        assert agg["skills_skipped"] == "1"
        assert "Skipped Skills" in agg["failed_skipped_section"]

    def test_all_successful_no_failed_section(self):
        state = _minimal_state()
        agg = mod._compute_aggregates(state)
        assert "All skills completed successfully" in agg["failed_skipped_section"]

    def test_empty_skills(self):
        state = _minimal_state(skills=[])
        agg = mod._compute_aggregates(state)
        assert agg["skills_completed"] == "0"
        assert agg["skills_failed"] == "0"
        assert agg["skills_skipped"] == "0"
        assert agg["quality_min"] == "0"
        assert agg["quality_max"] == "0"
        assert agg["quality_avg"] == "0"
        assert agg["total_workarounds"] == "0"
        assert "No skills in campaign" in agg["failed_skipped_section"]


class TestFormatDuration:
    def test_hours(self):
        assert mod._format_duration(
            mod._parse_iso("2026-01-01T00:00:00+00:00"),
            mod._parse_iso("2026-01-01T03:15:30+00:00"),
        ) == "3h 15m 30s"

    def test_minutes_only(self):
        assert mod._format_duration(
            mod._parse_iso("2026-01-01T00:00:00+00:00"),
            mod._parse_iso("2026-01-01T00:45:10+00:00"),
        ) == "45m 10s"

    def test_seconds_only(self):
        assert mod._format_duration(
            mod._parse_iso("2026-01-01T00:00:00+00:00"),
            mod._parse_iso("2026-01-01T00:00:42+00:00"),
        ) == "42s"

    def test_none_values(self):
        assert mod._format_duration(None, None) == "N/A"
        assert mod._format_duration(mod._parse_iso("2026-01-01T00:00:00+00:00"), None) == "N/A"


class TestRun:
    def test_success(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state_file = _write_state(tmp_path, state)
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 0

        assert output_file.exists()
        report = output_file.read_text(encoding="utf-8")
        assert "test-campaign" in report
        assert "skill-alpha" in report
        assert "skill-beta" in report

        stdout = capsys.readouterr().out
        result = json.loads(stdout.strip())
        assert result["status"] == "success"
        assert result["skills_completed"] == 2
        assert result["skills_failed"] == 0
        assert result["report_path"] == output_file.as_posix()

    def test_missing_state_file(self, tmp_path: Path, capsys):
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(tmp_path / "missing.yaml"), str(template_file), str(output_file))
        assert rc == 2

        stderr = capsys.readouterr().err
        err = json.loads(stderr.strip())
        assert err["code"] == "STATE_NOT_FOUND"

    def test_missing_template_file(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state_file = _write_state(tmp_path, state)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(tmp_path / "missing.md"), str(output_file))
        assert rc == 2

        stderr = capsys.readouterr().err
        err = json.loads(stderr.strip())
        assert err["code"] == "TEMPLATE_NOT_FOUND"

    def test_bad_yaml(self, tmp_path: Path, capsys):
        state_file = tmp_path / "bad.yaml"
        state_file.write_text(": : : invalid yaml [[[", encoding="utf-8")
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 2

        stderr = capsys.readouterr().err
        err = json.loads(stderr.strip())
        assert err["code"] == "STATE_PARSE_ERROR"

    def test_non_dict_state(self, tmp_path: Path, capsys):
        state_file = tmp_path / "state.yaml"
        state_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 2

        stderr = capsys.readouterr().err
        err = json.loads(stderr.strip())
        assert err["code"] == "INVALID_STATE"

    def test_output_dir_created(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state_file = _write_state(tmp_path, state)
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "nested" / "dir" / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 0
        assert output_file.exists()

    def test_custom_template(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state_file = _write_state(tmp_path, state)
        template_file = _write_template(
            tmp_path, content="Campaign: {{campaign_name}} | Completed: {{skills_completed}}"
        )
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 0

        report = output_file.read_text(encoding="utf-8")
        assert report == "Campaign: test-campaign | Completed: 2"

    def test_report_path_posix(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state_file = _write_state(tmp_path, state)
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 0

        stdout = capsys.readouterr().out
        result = json.loads(stdout.strip())
        assert "\\" not in result["report_path"]

    def test_malformed_state_aggregate_error(self, tmp_path: Path, capsys):
        state_file = tmp_path / "state.yaml"
        state_file.write_text("campaign: null\nskills: null\n", encoding="utf-8")
        template_file = _write_template(tmp_path)
        output_file = tmp_path / "report.md"

        rc = mod.run(str(state_file), str(template_file), str(output_file))
        assert rc == 2

        stderr = capsys.readouterr().err
        err = json.loads(stderr.strip())
        assert err["code"] == "AGGREGATE_ERROR"
