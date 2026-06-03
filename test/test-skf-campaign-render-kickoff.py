"""Tests for campaign-render-kickoff.py — mechanical kickoff placeholder fill.

Confirms the script substitutes the 10 state/brief-derived placeholders and
leaves the three judgment slots ({{brief_summary}}, {{persistent_facts}},
{{directive_content}}) untouched for the LLM.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
TEMPLATE = REPO_ROOT / "src" / "skf-campaign" / "templates" / "kickoff-template.md"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_render_kickoff", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

STATE = {
    "campaign": {
        "name": "demo",
        "current_stage": 4,
        "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80},
    },
    "skills": [
        {"name": "auth", "tier": "A", "pin": "v1.2.3", "commit_sha": "abc123", "status": "active",
         "depends_on": ["core"], "workarounds_applied": ["[doc-rot] fixed import"]},
        {"name": "core", "tier": "A", "pin": None, "commit_sha": None, "status": "completed",
         "depends_on": [], "workarounds_applied": []},
    ],
}
BRIEF = {"targets": [
    {"name": "auth", "repo_url": "https://github.com/o/auth"},
    {"name": "core", "repo_url": "https://github.com/o/core"},
]}
TEMPLATE_TEXT = TEMPLATE.read_text(encoding="utf-8")


class TestRenderKickoff:
    def test_mechanical_fields_filled(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT)
        assert "demo" in out
        assert "v1.2.3" in out
        assert "abc123" in out
        assert "https://github.com/o/auth" in out
        assert "Hard: zero-critical-high | Soft: 90 (fallback: 80)" in out
        # dependency status table for core (completed)
        assert "| core | completed |" in out
        # workaround list
        assert "[doc-rot] fixed import" in out

    def test_judgment_slots_preserved(self):
        out = mod.render_kickoff(STATE, BRIEF, "auth", TEMPLATE_TEXT)
        for slot in mod.JUDGMENT_SLOTS:
            assert slot in out, f"{slot} must be left for the LLM to fill"

    def test_null_pin_becomes_latest(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "latest" in out
        assert "{{pin}}" not in out

    def test_null_commit_becomes_unknown(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "unknown" in out
        assert "{{commit_sha}}" not in out

    def test_no_deps_message(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT)
        assert "No dependencies." in out

    def test_explicit_workarounds_override(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT, workarounds=["wa-1", "wa-2"])
        assert "- wa-1" in out and "- wa-2" in out

    def test_empty_workarounds_none(self):
        out = mod.render_kickoff(STATE, BRIEF, "core", TEMPLATE_TEXT, workarounds=[])
        # core's workarounds slot should render "None"
        assert "None" in out

    def test_unknown_skill_raises(self):
        with pytest.raises(KeyError):
            mod.render_kickoff(STATE, BRIEF, "ghost", TEMPLATE_TEXT)


class TestRun:
    def _files(self, tmp_path):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        tf = tmp_path / "kickoff.md"
        sf.write_text(yaml.dump(STATE), encoding="utf-8")
        bf.write_text(yaml.dump(BRIEF), encoding="utf-8")
        tf.write_text(TEMPLATE_TEXT, encoding="utf-8")
        return sf, bf, tf

    def test_success(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "demo" in out and "{{brief_summary}}" in out

    def test_missing_state_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(tmp_path / "no.yaml"), str(bf), "auth", str(tf), None)
        assert rc == 2

    def test_unknown_skill_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "ghost", str(tf), None)
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "SKILL_NOT_FOUND"

    def test_bad_workarounds_exit_2(self, tmp_path, capsys):
        sf, bf, tf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), "auth", str(tf), '{"not":"a list"}')
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "BAD_WORKAROUNDS"
