"""Tests for campaign-report.py: campaign report generation from state + template.

With --context-file the script also writes the payload of the campaign's
SKF_CAMPAIGN_RESULT_JSON line, which the shared emitter turns into an
envelope that validates against skf-campaign-result-envelope.v1.json: the
success payload, and on a failed report the degraded one.
"""

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


class TestExportGate:
    """The report and its result JSON say which completed skills the gate kept from export."""

    def test_verdicts_and_exclusions_in_the_result(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state["skills"][1]["quality_score"] = 70
        output_file = tmp_path / "report.md"
        rc = mod.run(str(_write_state(tmp_path, state)), str(_write_template(tmp_path)), str(output_file))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["export_verdicts"] == {"skill-alpha": "pass", "skill-beta": "fail"}
        assert result["skills_excluded"] == ["skill-beta"]
        report = output_file.read_text(encoding="utf-8")
        assert "| skill-alpha | 92 | pass |" in report
        assert "**Not exported (below the quality gate):** skill-beta (70: below soft_fallback 80)" in report

    def test_directive_overrides_apply(self, tmp_path: Path, capsys):
        directive = tmp_path / "_campaign-directive.md"
        directive.write_bytes(b"## Quality Overrides\n- soft_target: 95\n")
        state = _minimal_state()
        state["campaign"]["directive_path"] = str(directive)
        rc = mod.run(str(_write_state(tmp_path, state)), str(_write_template(tmp_path)), str(tmp_path / "r.md"))
        assert rc == 0
        verdicts = json.loads(capsys.readouterr().out)["export_verdicts"]
        assert verdicts == {"skill-alpha": "fallback", "skill-beta": "fallback"}

    def test_gate_that_cannot_be_applied_is_null(self, tmp_path: Path, capsys):
        state = _minimal_state()
        state["campaign"]["quality_gate"]["hard"] = "lenient"
        output_file = tmp_path / "report.md"
        rc = mod.run(str(_write_state(tmp_path, state)), str(_write_template(tmp_path)), str(output_file))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["export_verdicts"] is None
        assert result["skills_excluded"] is None
        assert "could not be applied" in output_file.read_text(encoding="utf-8")

    def test_no_completed_skill(self):
        state = _minimal_state()
        for skill in state["skills"]:
            skill["status"] = "failed"
        assert mod._compute_aggregates(state)["export_gate_section"] == "No completed skills."


EMITTER = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
ENVELOPE_SCHEMA = (Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts" / "schemas"
                   / "skf-campaign-result-envelope.v1.json")


def _envelope(context: Path) -> dict:
    """The envelope the shared emitter builds from a context file, checked against the schema."""
    import subprocess

    from jsonschema import Draft202012Validator

    proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-campaign"],
                          input=context.read_text(encoding="utf-8"), capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.splitlines()
    prefix = "SKF_CAMPAIGN_RESULT_JSON: "
    assert line.startswith(prefix)
    envelope = json.loads(line[len(prefix):])
    schema = json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(envelope))
    return envelope


class TestContextFile:
    def test_success_payload_becomes_the_success_envelope(self, tmp_path: Path, capsys):
        context = tmp_path / "_result-context.json"
        output_file = tmp_path / "campaign-report.md"
        rc = mod.run(str(_write_state(tmp_path, _minimal_state())), str(_write_template(tmp_path)),
                     str(output_file), str(context), "ws/_campaign-decision-log.md")
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        envelope = _envelope(context)
        assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("success", 0, None)
        assert envelope["campaign_report_path"] == output_file.as_posix() == result["report_path"]
        assert envelope["decision_log"] == "ws/_campaign-decision-log.md"
        for key in ("skills_completed", "skills_failed", "quality_scores", "export_verdicts", "skills_excluded",
                    "duration"):
            assert envelope[key] == result[key], key

    def test_a_failed_report_writes_the_degraded_payload(self, tmp_path: Path, capsys):
        context = tmp_path / "_result-context.json"
        state = _minimal_state()
        state["skills"][1]["status"] = "failed"
        rc = mod.run(str(_write_state(tmp_path, state)), str(tmp_path / "missing-template.md"),
                     str(tmp_path / "r.md"), str(context), "ws/log.md")
        assert rc == 2
        assert json.loads(capsys.readouterr().err)["code"] == "TEMPLATE_NOT_FOUND"
        envelope = _envelope(context)
        assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("error", 10,
                                                                                      "report-failure")
        assert envelope["campaign_report_path"] is None
        assert (envelope["skills_completed"], envelope["skills_failed"]) == (1, 1)
        assert envelope["quality_scores"] == {"skill-alpha": 92}
        assert envelope["decision_log"] == "ws/log.md"

    def test_a_state_it_cannot_read_still_gives_a_degraded_payload(self, tmp_path: Path, capsys):
        context = tmp_path / "_result-context.json"
        bad = tmp_path / "_campaign-state.yaml"
        bad.write_text("campaign: [half", encoding="utf-8")
        rc = mod.run(str(bad), str(_write_template(tmp_path)), str(tmp_path / "r.md"), str(context))
        assert rc == 2
        envelope = _envelope(context)
        assert (envelope["halt_reason"], envelope["skills_completed"], envelope["decision_log"]) == (
            "report-failure", 0, None)

    def test_a_payload_it_cannot_write_leaves_no_earlier_one(self, tmp_path: Path, capsys, monkeypatch):
        # Step 11 falls back only when the file is missing: an earlier run's payload must not stand in.
        context = tmp_path / "_result-context.json"
        context.write_text('{"status": "success", "skills_completed": 99}', encoding="utf-8")
        real_write = Path.write_text

        def refuse_context(self, *args, **kwargs):
            if self.name == context.name:
                raise OSError("disk full")
            return real_write(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", refuse_context)
        rc = mod.run(str(_write_state(tmp_path, _minimal_state())), str(_write_template(tmp_path)),
                     str(tmp_path / "r.md"), str(context), "ws/log.md")
        assert rc == 0
        assert not context.exists()
        assert json.loads(capsys.readouterr().err)["code"] == "CONTEXT_WRITE_ERROR"

    def test_no_context_file_writes_none(self, tmp_path: Path, capsys):
        rc = mod.run(str(_write_state(tmp_path, _minimal_state())), str(_write_template(tmp_path)),
                     str(tmp_path / "r.md"))
        assert rc == 0
        assert sorted(p.name for p in tmp_path.iterdir()) == ["_campaign-state.yaml", "r.md", "template.md"]
