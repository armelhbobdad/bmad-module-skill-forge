"""Tests for campaign-quality-gate.py: the campaign quality gate, enforced.

Pins the four subcommands the step files call: `check` (step-01 settles
the gate, a brief's values over customize.toml's, and validates it before it
writes state), `resolve` (step-05 skips a Skip List skill, hands brief-skill
its inputs and test-skill its threshold), `record` (step-05 settles a Tier A
skill from its test verdict, never from envelope status) and `classify`
(step-07 composes and step-10 exports only pass and fallback skills). Also
pins the step prose that calls them, so a step cannot drift back to deciding
by hand.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAMPAIGN_DIR = REPO_ROOT / "src" / "skf-campaign"
SCRIPT = CAMPAIGN_DIR / "scripts" / "campaign-quality-gate.py"
REFERENCES = CAMPAIGN_DIR / "references"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_quality_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

GATE = {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80}


def _state(skills, gate=None):
    return {
        "campaign": {
            "name": "demo",
            "started_at": "2026-01-01T00:00:00Z",
            "last_updated": "2026-01-01T00:00:00Z",
            "current_stage": 4,
            "quality_gate": dict(gate or GATE),
        },
        "skills": skills,
        "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
    }


def _skill(name, status="completed", tier="A", score=None, skill_path=None):
    return {"name": name, "status": status, "tier": tier, "quality_score": score, "skill_path": skill_path}


def _envelope(**fields):
    base = {
        "status": "success",
        "skill_name": "core",
        "verdict": "PASS",
        "score": 93,
        "threshold": 90,
        "report_path": "/r.md",
        "next_workflow": "export-skill",
        "exit_code": 0,
        "halt_reason": None,
    }
    base.update(fields)
    return "SKF_TEST_RESULT_JSON: " + json.dumps(base)


def _write_state(tmp_path, state):
    path = tmp_path / "_campaign-state.yaml"
    path.write_text(yaml.safe_dump(state), encoding="utf-8")
    return path


def _write_brief(tmp_path, brief):
    path = tmp_path / "campaign-brief.yaml"
    path.write_text(yaml.safe_dump(brief, sort_keys=False), encoding="utf-8")
    return path


def _write_directive(tmp_path, text):
    path = tmp_path / "_campaign-directive.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(argv, capsys, stdin=None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8"))))
    rc = mod.main(argv)
    out = capsys.readouterr()
    return rc, (json.loads(out.out) if out.out.strip() else None), (json.loads(out.err) if out.err.strip() else None)


# --------------------------------------------------------------------------
# check: the gate step-01 writes
# --------------------------------------------------------------------------


class TestCheck:
    def test_default_gate_passes(self):
        assert mod.check("zero-critical-high", "90", "80") == GATE

    def test_whole_float_prints_as_int(self):
        assert mod.check("zero-critical-high", "90.0", "80")["soft_target"] == 90

    @pytest.mark.parametrize(
        "hard, target, fallback, fragment",
        [
            ("lenient", "90", "80", "hard gate `lenient` is not supported"),
            ("zero-critical-high", "ninety", "80", "`soft_target` must be a number"),
            ("zero-critical-high", "101", "80", "`soft_target` must be a number from 0 to 100"),
            ("zero-critical-high", "90", "-1", "`soft_fallback` must be a number from 0 to 100"),
            ("zero-critical-high", "80", "90", "`soft_fallback` 90 is above `soft_target` 80"),
        ],
        ids=["unknown-hard", "word", "above-100", "negative", "fallback-above-target"],
    )
    def test_bad_gate_is_rejected(self, hard, target, fallback, fragment):
        with pytest.raises(mod.GateError) as exc:
            mod.check(hard, target, fallback)
        assert exc.value.code == "INVALID_GATE"
        assert any(fragment in e for e in exc.value.extra["errors"])

    def test_cli_exit_2_with_json_error(self, capsys):
        rc, out, err = _run(["check", "--hard", "zero-critical", "--soft-target", "90", "--soft-fallback", "80"], capsys)
        assert rc == 2
        assert out is None
        assert err["code"] == "INVALID_GATE"

    def test_cli_prints_the_gate(self, capsys):
        rc, out, _ = _run(["check", "--hard", "zero-critical-high", "--soft-target", "95", "--soft-fallback", "85"], capsys)
        assert rc == 0
        assert out == {"hard": "zero-critical-high", "soft_target": 95, "soft_fallback": 85}

    def test_brief_wins_field_by_field(self):
        brief = {"quality_gate": {"soft_target": 95, "soft_fallback": None}}
        assert mod.check("zero-critical-high", "90", "80", brief) == {
            "hard": "zero-critical-high", "soft_target": 95, "soft_fallback": 80,
        }

    def test_brief_without_a_gate_keeps_the_base(self):
        assert mod.check("zero-critical-high", "90", "80", {"targets": []}) == GATE

    def test_brief_value_that_breaks_the_gate_names_the_brief(self):
        with pytest.raises(mod.GateError) as exc:
            mod.check("zero-critical-high", "90", "80", {"quality_gate": {"soft_fallback": 95}})
        assert exc.value.code == "INVALID_GATE"
        assert "campaign brief: soft_fallback 95" in str(exc.value)

    def test_brief_hard_gate_is_checked(self):
        with pytest.raises(mod.GateError) as exc:
            mod.check("zero-critical-high", "90", "80", {"quality_gate": {"hard": "lenient"}})
        assert any("hard gate `lenient`" in e for e in exc.value.extra["errors"])

    def test_cli_brief_file(self, tmp_path, capsys):
        brief = _write_brief(tmp_path, {"quality_gate": {"hard": "zero-critical-high", "soft_target": 92, "soft_fallback": 85}})
        rc, out, _ = _run(["check", "--hard", "zero-critical-high", "--soft-target", "90", "--soft-fallback", "80",
                           "--brief-file", str(brief)], capsys)
        assert rc == 0
        assert out == {"hard": "zero-critical-high", "soft_target": 92, "soft_fallback": 85}

    @pytest.mark.parametrize("content, code", [(None, "BRIEF_NOT_FOUND"), (b"- a\n", "BRIEF_UNREADABLE"),
                                               (b"quality_gate: 90\n", "INVALID_GATE")],
                             ids=["missing", "not-a-mapping", "gate-not-a-mapping"])
    def test_cli_bad_brief_exit_2(self, tmp_path, capsys, content, code):
        brief = tmp_path / "campaign-brief.yaml"
        if content is not None:
            brief.write_bytes(content)
        rc, _, err = _run(["check", "--hard", "zero-critical-high", "--soft-target", "90", "--soft-fallback", "80",
                           "--brief-file", str(brief)], capsys)
        assert rc == 2
        assert err["code"] == code


# --------------------------------------------------------------------------
# The directive's Skip List and Quality Overrides
# --------------------------------------------------------------------------

DIRECTIVE = """# Campaign directive

## Quality Overrides

- soft_target: 85
- `web`: soft_target 95, soft_fallback 92
- cli: soft_fallback: 70%
- hard: lenient

### Why
- these numbers came from the last review

## Skip List

- `legacy`: upstream is mid-rewrite
- old-sdk (deprecated)
- ghost - not in this campaign
- bare

## Notes

- soft_target: 10
"""


class TestDirective:
    def test_overrides(self):
        d = mod.parse_directive(DIRECTIVE)
        assert d["campaign"] == {"soft_target": 85}
        assert d["skills"] == {"web": {"soft_target": 95, "soft_fallback": 92}, "cli": {"soft_fallback": 70}}

    def test_skip_list_with_and_without_reasons(self):
        d = mod.parse_directive(DIRECTIVE)
        assert d["skip"] == {
            "legacy": "upstream is mid-rewrite",
            "old-sdk": "deprecated",
            "ghost": "not in this campaign",
            "bare": None,
        }

    def test_unreadable_item_is_reported_not_applied(self):
        d = mod.parse_directive(DIRECTIVE)
        # A `###` heading does not end the section, so its prose item is reported too.
        assert d["unparsed"] == [
            {"section": "Quality Overrides", "line": 8, "text": "hard: lenient"},
            {"section": "Quality Overrides", "line": 11, "text": "these numbers came from the last review"},
        ]
        assert "hard" not in d["skills"]

    @pytest.mark.parametrize(
        "item",
        [
            "react: soft_target 80 (was soft_target 90)",
            "soft_target: 85, but react: soft_target 70",
            "react: soft_target 70 only if the docs stay thin, otherwise soft_target 90",
            "soft_target: 85, soft_target: 90",
            "react: soft_fallback 70, soft_target 90, SOFT_FALLBACK 60",
            "react: soft_target 85, soft_fallback75",
            "react: soft_target85, soft_fallback 70",
            "soft_target: 85, soft_fallback75",
        ],
        ids=["parenthesised-old-value", "second-skill-in-prose", "conditional-prose", "campaign-repeated-key",
             "skill-repeated-key", "key-glued-to-number", "first-key-glued-to-number",
             "campaign-key-glued-to-number"],
    )
    def test_item_beyond_the_grammar_applies_no_number(self, item):
        # Other text or a repeated key leaves the item unparsed: no last number wins.
        d = mod.parse_directive(f"## Quality Overrides\n- {item}\n")
        assert d["unparsed"] == [{"section": "Quality Overrides", "line": 2, "text": item}]
        assert d["campaign"] == {}
        assert d["skills"] == {}

    def test_other_sections_are_ignored(self):
        # `## Notes` holds `soft_target: 10`, which is no override.
        assert mod.parse_directive(DIRECTIVE)["campaign"]["soft_target"] == 85

    def test_level_one_heading_ends_a_section(self):
        d = mod.parse_directive("## Skip List\n- a\n# Appendix\n- b\n")
        assert d["skip"] == {"a": None}

    def test_numbered_items(self):
        assert mod.parse_directive("## Skip List\n1. a\n2) b: why\n")["skip"] == {"a": None, "b": "why"}

    def test_missing_file_is_no_directive(self, tmp_path):
        d = mod.read_directive(str(tmp_path / "nope.md"))
        assert d == {"skip": {}, "campaign": {}, "skills": {}, "unparsed": []}

    def test_no_path_is_no_directive(self):
        assert mod.read_directive(None)["skip"] == {}

    def test_bom_and_crlf(self, tmp_path):
        path = tmp_path / "d.md"
        path.write_bytes(b"\xef\xbb\xbf## Skip List\r\n- core: flaky\r\n")
        assert mod.read_directive(str(path))["skip"] == {"core": "flaky"}


# --------------------------------------------------------------------------
# resolve: step-05's per-skill gate
# --------------------------------------------------------------------------


class TestResolve:
    STATE = _state([_skill("core", "pending"), _skill("web", "pending"), _skill("legacy", "pending")])

    def test_no_directive_takes_the_state_gate(self):
        r = mod.resolve(self.STATE, mod.parse_directive(""), "core")
        assert r["skip"] is False
        assert r["threshold"] == 90
        assert (r["soft_target"], r["soft_fallback"]) == (90, 80)
        assert r["overrides"] == []

    def test_campaign_override_sets_the_threshold(self):
        r = mod.resolve(self.STATE, mod.parse_directive("## Quality Overrides\n- soft_target: 85\n"), "core")
        assert r["threshold"] == 85
        assert r["overrides"] == ["directive Quality Overrides: soft_target 85"]

    def test_skill_override_beats_campaign_override(self):
        text = "## Quality Overrides\n- soft_target: 85\n- web: soft_target 95\n"
        assert mod.resolve(self.STATE, mod.parse_directive(text), "web")["threshold"] == 95
        assert mod.resolve(self.STATE, mod.parse_directive(text), "core")["threshold"] == 85

    def test_skip_list(self):
        r = mod.resolve(self.STATE, mod.parse_directive("## Skip List\n- legacy: abandoned\n"), "legacy")
        assert r["skip"] is True
        assert r["skip_reason"] == "abandoned"

    def test_unknown_names_warn(self):
        r = mod.resolve(self.STATE, mod.parse_directive("## Skip List\n- ghost\n"), "core")
        assert r["warnings"] == ["Skip List names `ghost`, which is no skill in this campaign"]

    def test_override_that_breaks_the_gate_halts(self):
        with pytest.raises(mod.GateError) as exc:
            mod.resolve(self.STATE, mod.parse_directive("## Quality Overrides\n- soft_fallback: 95\n"), "core")
        assert exc.value.code == "INVALID_GATE"
        assert "directive Quality Overrides: soft_fallback 95" in str(exc.value)

    def test_unknown_skill(self):
        with pytest.raises(mod.GateError) as exc:
            mod.resolve(self.STATE, mod.parse_directive(""), "nope")
        assert exc.value.code == "SKILL_NOT_FOUND"

    def test_cli(self, tmp_path, capsys):
        state = _write_state(tmp_path, self.STATE)
        directive = _write_directive(tmp_path, "## Skip List\n- legacy\n")
        rc, out, _ = _run(
            ["resolve", "--state-file", str(state), "--skill", "legacy", "--directive-file", str(directive)], capsys
        )
        assert rc == 0
        assert out["skip"] is True

    def test_cli_missing_state(self, tmp_path, capsys):
        rc, _, err = _run(["resolve", "--state-file", str(tmp_path / "x.yaml"), "--skill", "a"], capsys)
        assert rc == 2
        assert err["code"] == "STATE_NOT_FOUND"

    def test_no_brief_no_inputs(self):
        assert "brief_skill" not in mod.resolve(self.STATE, mod.parse_directive(""), "core")


class TestBriefSkillInputs:
    STATE = _state([dict(_skill("core", "pending"), pin="1.2.0"), dict(_skill("web", "pending"), pin=None)])
    BRIEF = {"targets": [
        {"name": "core", "repo_url": "https://github.com/o/core", "language": "python", "scope_hint": " public api "},
        {"name": "web", "repo_url": "https://github.com/o/web", "language_hint": "", "scope": ["not", "text"]},
    ]}

    def test_inputs_come_from_brief_and_state(self):
        r = mod.resolve(self.STATE, mod.parse_directive(""), "core", self.BRIEF)
        assert r["brief_skill"] == {
            "target_repo": "https://github.com/o/core",
            "skill_name": "core",
            "target_version": "1.2.0",
            "language_hint": "python",
            "scope_hint": "public api",
        }

    def test_absent_pin_and_hints_are_null(self):
        r = mod.resolve(self.STATE, mod.parse_directive(""), "web", self.BRIEF)
        assert r["brief_skill"] == {
            "target_repo": "https://github.com/o/web",
            "skill_name": "web",
            "target_version": None,
            "language_hint": None,
            "scope_hint": None,
        }

    def test_skill_with_no_brief_target(self):
        with pytest.raises(mod.GateError) as exc:
            mod.resolve(self.STATE, mod.parse_directive(""), "web", {"targets": [{"name": "core", "repo_url": "o/core"}]})
        assert exc.value.code == "TARGET_NOT_FOUND"

    def test_cli(self, tmp_path, capsys):
        state = _write_state(tmp_path, self.STATE)
        brief = _write_brief(tmp_path, self.BRIEF)
        rc, out, _ = _run(["resolve", "--state-file", str(state), "--skill", "core", "--brief-file", str(brief)], capsys)
        assert rc == 0
        assert out["brief_skill"]["target_version"] == "1.2.0"
        assert out["threshold"] == 90

    def test_cli_missing_brief(self, tmp_path, capsys):
        state = _write_state(tmp_path, self.STATE)
        rc, _, err = _run(["resolve", "--state-file", str(state), "--skill", "core",
                           "--brief-file", str(tmp_path / "none.yaml")], capsys)
        assert rc == 2
        assert err["code"] == "BRIEF_NOT_FOUND"


# --------------------------------------------------------------------------
# record: a Tier A skill's result is its test verdict
# --------------------------------------------------------------------------


class TestRecord:
    def test_pass_completes(self):
        r = mod.record("core", _envelope())
        assert r["status"] == "completed"
        assert r["verdict"] == "PASS"
        assert r["quality_score"] == 93
        assert r["reason"] is None

    def test_threshold_fallback_pass_completes(self):
        r = mod.record("core", _envelope(score=84, threshold=90, threshold_fallback=True, original_threshold=90))
        assert r["status"] == "completed"
        assert r["threshold_fallback"] is True

    @pytest.mark.parametrize(
        "verdict, route", [("FAIL", "update-skill"), ("INCONCLUSIVE", None), ("pass-with-drift", "update-skill")],
        ids=["fail", "inconclusive", "pass-with-drift"],
    )
    def test_any_other_verdict_fails_although_status_is_success(self, verdict, route):
        r = mod.record("core", _envelope(verdict=verdict, next_workflow=route, score=91))
        assert r["status"] == "failed"
        assert r["reason"] == verdict
        assert r["quality_score"] == 91

    def test_record_spelling_of_drift(self):
        assert mod.record("core", _envelope(verdict="PASS_WITH_DRIFT"))["reason"] == "pass-with-drift"

    def test_hard_gate_block_fails_with_its_halt_reason(self):
        r = mod.record("core", _envelope(status="error", verdict="FAIL", score=None, halt_reason="hard-gate-blocked"))
        assert r["status"] == "failed"
        assert r["reason"] == "hard-gate-blocked"

    def test_pass_routed_elsewhere_fails(self):
        assert mod.record("core", _envelope(next_workflow="update-skill"))["status"] == "failed"

    def test_last_envelope_wins(self):
        text = _envelope(verdict="FAIL") + "\nlog line\n" + _envelope()
        assert mod.record("core", text)["status"] == "completed"

    def test_no_result(self):
        assert mod.record("core", "  \n")["reason"] == "no-result"

    def test_unreadable_result(self):
        assert mod.record("core", "SKF_TEST_RESULT_JSON: {nope")["reason"] == "result-unreadable"

    def test_another_workflows_envelope(self):
        r = mod.record("core", 'SKF_CREATE_SKILL_RESULT_JSON: {"status":"failed"}')
        assert r["reason"] == "not-a-test-result"

    def test_result_for_another_skill(self):
        r = mod.record("core", _envelope(skill_name="web"))
        assert r["status"] == "failed"
        assert r["reason"] == "result-for-another-skill: web"

    def test_unknown_verdict(self):
        assert mod.record("core", _envelope(verdict="MAYBE"))["reason"] == "unknown-verdict: MAYBE"

    def test_cli_reads_stdin(self, capsys, monkeypatch):
        rc, out, _ = _run(["record", "--skill", "core"], capsys, stdin=_envelope(), monkeypatch=monkeypatch)
        assert rc == 0
        assert out["status"] == "completed"

    def test_cli_result_file(self, tmp_path, capsys):
        path = tmp_path / "ts.txt"
        path.write_bytes(_envelope(verdict="INCONCLUSIVE").encode("utf-8"))
        rc, out, _ = _run(["record", "--skill", "core", "--result", str(path)], capsys)
        assert rc == 0
        assert out["status"] == "failed"

    def test_cli_missing_result_file(self, tmp_path, capsys):
        rc, _, err = _run(["record", "--skill", "core", "--result", str(tmp_path / "x")], capsys)
        assert rc == 2
        assert err["code"] == "RESULT_NOT_FOUND"


# --------------------------------------------------------------------------
# classify: only pass and fallback skills export
# --------------------------------------------------------------------------


class TestClassify:
    STATE = _state([
        _skill("core", score=95, skill_path="/s/core"),
        _skill("web", score=84),
        _skill("cli", tier="B", score=70),
        _skill("nos", tier="B", score=None),
        _skill("bad", status="failed", score=40),
        _skill("todo", status="pending"),
    ])

    def test_verdicts_and_export_list(self):
        r = mod.classify(self.STATE, mod.parse_directive(""))
        verdicts = {row["name"]: row["verdict"] for row in r["skills"]}
        assert verdicts == {"core": "pass", "web": "fallback", "cli": "fail", "nos": "fail"}
        assert r["export"] == ["core", "web"]
        assert [e["name"] for e in r["excluded"]] == ["cli", "nos"]
        assert r["counts"] == {"pass": 1, "fallback": 1, "fail": 2}
        assert r["skills"][0]["skill_path"] == "/s/core"

    def test_reasons(self):
        r = mod.classify(self.STATE, mod.parse_directive(""))
        reasons = {e["name"]: e["reason"] for e in r["excluded"]}
        assert reasons == {"cli": "below soft_fallback 80", "nos": "no quality score to check against the gate"}

    def test_failed_and_pending_skills_are_not_candidates(self):
        names = [row["name"] for row in mod.classify(self.STATE, mod.parse_directive(""))["skills"]]
        assert "bad" not in names and "todo" not in names

    @pytest.mark.parametrize(
        "target, expected",
        [
            (95, {"core": "pass", "web": "fallback"}),
            (84, {"core": "pass", "web": "pass"}),
            (99, {"core": "fallback", "web": "fallback"}),
        ],
        ids=["target-95", "target-84", "target-99"],
    )
    def test_changing_the_target_changes_the_verdicts(self, target, expected):
        gate = {"hard": "zero-critical-high", "soft_target": target, "soft_fallback": 84}
        state = _state([_skill("core", score=95), _skill("web", score=84)], gate=gate)
        r = mod.classify(state, mod.parse_directive(""))
        assert {row["name"]: row["verdict"] for row in r["skills"]} == expected

    def test_raising_the_fallback_excludes(self):
        gate = {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 85}
        r = mod.classify(_state([_skill("web", score=84)], gate=gate), mod.parse_directive(""))
        assert r["export"] == []
        assert r["excluded"][0]["reason"] == "below soft_fallback 85"

    def test_directive_overrides_apply(self):
        text = "## Quality Overrides\n- soft_fallback: 60\n- web: soft_target 80\n"
        r = mod.classify(self.STATE, mod.parse_directive(text))
        verdicts = {row["name"]: row["verdict"] for row in r["skills"]}
        assert verdicts == {"core": "pass", "web": "pass", "cli": "fallback", "nos": "fail"}
        assert r["gate"] == {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 60}

    def test_export_name_is_the_folder_the_build_wrote(self):
        # quick-skill names a Tier B package after the library, not the campaign target:
        # skf-export-skill resolves that folder, so a target `api` exports as `mono-api`.
        state = _state([
            _skill("api", tier="B", score=95, skill_path="/skills/mono-api/1.0.0/mono-api"),
            _skill("core", score=95),
            _skill("blank", score=95, skill_path="  "),
            _skill("win", tier="B", score=95, skill_path="C:\\skills\\win-lib\\2.0.0\\win-lib\\"),
        ])
        r = mod.classify(state, mod.parse_directive(""))
        assert {row["name"]: row["export_name"] for row in r["skills"]} == {
            "api": "mono-api", "core": "core", "blank": "blank", "win": "win-lib"}
        assert r["export"] == ["api", "core", "blank", "win"]

    def test_cli(self, tmp_path, capsys):
        state = _write_state(tmp_path, self.STATE)
        rc, out, _ = _run(["classify", "--state-file", str(state)], capsys)
        assert rc == 0
        assert out["export"] == ["core", "web"]
        assert [row["export_name"] for row in out["skills"]] == ["core", "web", "cli", "nos"]

    def test_cli_bad_state_gate(self, tmp_path, capsys):
        state = _write_state(tmp_path, _state([_skill("a", score=90)], gate={"hard": "x", "soft_target": 90, "soft_fallback": 80}))
        rc, _, err = _run(["classify", "--state-file", str(state)], capsys)
        assert rc == 2
        assert err["code"] == "INVALID_GATE"


# --------------------------------------------------------------------------
# The step prose calls the script instead of deciding by hand
# --------------------------------------------------------------------------


def _text(name: str) -> str:
    return (REFERENCES / name).read_text(encoding="utf-8")


def _frontmatter(name: str) -> dict:
    return yaml.safe_load(_text(name).split("---", 2)[1])


@pytest.mark.parametrize("name", ["step-05-skill-loop.md", "step-07-capstone.md", "step-10-export.md"])
def test_steps_bind_the_gate_script(name):
    assert _frontmatter(name)["gateScript"] == "scripts/campaign-quality-gate.py"


def test_setup_settles_the_gate_with_the_script(tmp_path, capsys):
    # Setup's init (campaign-state.py) runs this script's check before it writes the state.
    text = _text("step-01-setup.md")
    assert ("init --state-file {stateFile} --targets-file - --name \"<campaign_name>\" --hard \"{qualityGateHard}\" "
            "--soft-target {qualityGateSoftTarget} --soft-fallback {qualityGateSoftFallback} [--brief-file <brief-file>]"
            ) in text
    assert "settles and checks the gate with `campaign-quality-gate.py check`" in text
    assert "field by field" not in text
    spec = importlib.util.spec_from_file_location("campaign_state_gate_test", SCRIPT.parent / "campaign-state.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"targets": [{"name": "core", "tier": "A", "pin": None, "depends_on": []}],
                                   "errors": []}), encoding="utf-8")
    state = tmp_path / "_campaign-state.yaml"
    # A fallback above the target: the gate script refuses it, so init writes nothing.
    rc = helper.main(["init", "--state-file", str(state), "--targets-file", str(targets), "--name", "demo",
                      "--hard", "zero-critical-high", "--soft-target", "80", "--soft-fallback", "90"])
    assert rc == 2
    assert not state.exists()
    with pytest.raises(mod.GateError) as refused:
        mod.check("zero-critical-high", "80", "90")
    err = json.loads(capsys.readouterr().err)
    assert (err["code"], err["errors"]) == (refused.value.code, refused.value.extra["errors"])


class TestSkillLoopProse:
    TEXT = _text("step-05-skill-loop.md")

    def test_every_sub_skill_runs_headless(self):
        for code, skill in (("BS", "skf-brief-skill"), ("CS", "skf-create-skill"), ("TS", "skf-test-skill")):
            line = next(line for line in self.TEXT.splitlines() if f"**{code}** (`{skill}`)" in line)
            assert "--headless" in line, code

    def test_no_analyze_pass_whose_briefs_nobody_reads(self):
        assert "skf-analyze-source" not in self.TEXT
        assert "--target-ref" not in self.TEXT
        assert "Campaign runs no analyze-source pass" in self.TEXT

    def test_brief_skill_inputs_are_copied_from_the_script(self):
        assert "uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name} --brief-file {briefFile}" in self.TEXT
        bs = next(line for line in self.TEXT.splitlines() if "**BS** (`skf-brief-skill`)" in line)
        assert "each non-null field of §4's `brief_skill`" in bs
        assert "never read them out of the kickoff" in bs
        assert "from the kickoff" not in self.TEXT

    def test_threshold_is_resolved_again_right_before_the_test(self):
        ts = next(line for line in self.TEXT.splitlines() if "**TS** (`skf-test-skill`)" in line)
        resolve = ts.index("uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name}")
        assert resolve < ts.index("--threshold={threshold}")
        assert "keep its `threshold`" not in self.TEXT

    def test_completed_skill_records_its_path(self):
        assert "--status completed --quality-score <quality_score> --skill-path <skill_package>`, with its `quality_score` and the `{skill_package}` CS named" in self.TEXT

    def test_directive_problems_are_logged_once_per_stage(self):
        assert "once per stage, from the first resolve call" in self.TEXT

    def test_test_skill_gets_the_threshold_and_alias(self):
        assert "`{skill_name} --headless --threshold={threshold}`" in self.TEXT
        assert "`pipeline_alias` set to `campaign`" in self.TEXT

    def test_result_comes_from_the_verdict(self):
        assert "uv run {gateScript} record --skill {skill_name}" in self.TEXT
        assert "never from an envelope's `status`" in self.TEXT
        assert "On success:" not in self.TEXT

    def test_skip_list_and_gate_resolved_per_skill(self):
        assert "uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name}" in self.TEXT

    def test_blocked_dependency_has_an_exit_code_and_headless_skip(self):
        assert "exit code 13 (`dependency-blocked`)" in self.TEXT
        assert "take `default_action`" in self.TEXT
        assert "Dependency gate blocks default to HALT" not in self.TEXT


def test_capstone_composes_only_skills_that_clear_the_gate():
    text = _text("step-07-capstone.md")
    assert "uv run {gateScript} classify --state-file {stateFile}" in text
    assert "The capstone composes the skills in its `export[]`" in text
    # The script names each skill (classify's export_name); the step no longer derives it.
    assert "Name each composed skill by the `export_name` of its row in `skills[]`" in text
    assert "- `skills`: the §2 `export_name` values" in text
    assert "its `skill_path` when the row has one" not in text
    assert "uv run {manifestScript} --stack-name {stateFile}" in text
    assert "lower-cased" not in text


def test_export_takes_only_the_classified_candidates():
    text = _text("step-10-export.md")
    assert "uv run {gateScript} classify --state-file {stateFile}" in text
    assert "For each `skills[]` row of §3 whose `name` is in `export[]`" in text
    assert "| Gate | Export Name |" in text
    assert "For each completed skill (from §3)" not in text


def test_export_runs_under_the_export_name_and_records_each_outcome():
    text = _text("step-10-export.md")
    assert "skf-export-skill {export_name} --headless" in text
    assert "skf-export-skill {skill_name}" not in text
    assert "--skill {name} --export exported" in text
    assert "--skill {name} --export failed --export-exit-code <exit_code> [--export-halt-reason <halt_reason>]" in text
    assert _frontmatter("step-10-export.md")["stateScript"] == "scripts/campaign-state.py"


def test_exit_13_is_a_contract_code():
    contracts = (REFERENCES / "campaign-contracts.md").read_text(encoding="utf-8")
    row = next(line for line in contracts.splitlines() if re.match(r"^\| 13 ", line))
    assert "dependency-blocked" in row
    assert re.search(r"^\| 7 +\| dependency-deadlock", contracts, re.M)


def test_customize_states_the_precedence_and_the_only_hard_gate():
    text = (CAMPAIGN_DIR / "customize.toml").read_text(encoding="utf-8")
    block = text.split("# --- Quality gate ---", 1)[1].split("quality_gate_hard =", 1)[0]
    comment = " ".join(line.lstrip("#").strip() for line in block.splitlines() if line.strip())
    assert "the directive's `## Quality Overrides` (while the campaign runs), then the `quality_gate` of the campaign-brief.yaml Setup reads" in comment
    assert "`zero-critical-high` is the only accepted value" in comment
    assert mod.HARD_GATES == ("zero-critical-high",)
