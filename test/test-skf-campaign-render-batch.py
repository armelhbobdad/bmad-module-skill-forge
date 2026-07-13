"""Tests for campaign-render-batch.py — build the QS --batch input file.

Confirms the script filters `skills[]` for Tier B pending, joins each to its
brief `repo_url`, and emits the consumer's single-target line shape verbatim
(`{repo_url}` with `@{pin}` appended only when the state pin is non-null) — no
skill-name field, no bare pin token — while excluding Tier A and already-handled
skills, and HALTing (exit 8) on a missing brief or an unmatched target.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-render-batch.py"


def _load():
    spec = importlib.util.spec_from_file_location("campaign_render_batch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

# Two Tier-B pending (one pinned, one latest), one Tier-A pending, one Tier-B done.
STATE = {
    "campaign": {"name": "demo", "current_stage": 4},
    "skills": [
        {"name": "a", "tier": "B", "status": "pending", "pin": "1.2.0"},
        {"name": "b", "tier": "B", "status": "pending", "pin": None},
        {"name": "c", "tier": "A", "status": "pending", "pin": "9.9.9"},
        {"name": "d", "tier": "B", "status": "completed", "pin": "2.0.0"},
    ],
}
BRIEF = {
    "targets": [
        {"name": "a", "repo_url": "https://github.com/x/a"},
        {"name": "b", "repo_url": "https://github.com/x/b"},
        {"name": "c", "repo_url": "https://github.com/x/c"},
        {"name": "d", "repo_url": "https://github.com/x/d"},
    ]
}


class TestBuildBatch:
    def test_only_tier_b_pending_emitted(self):
        lines, summary = mod.build_batch(STATE, BRIEF)
        # EXACTLY two lines, in skills[] order, consumer shape verbatim.
        assert lines == [
            "https://github.com/x/a@1.2.0",
            "https://github.com/x/b",
        ]
        assert summary["count"] == 2

    def test_no_skill_name_or_bare_pin(self):
        lines, _ = mod.build_batch(STATE, BRIEF)
        joined = "\n".join(lines)
        # skill names must not leak into the batch line for URL targets.
        assert "a," not in joined and "b," not in joined
        # the latest target carries no `@` pin token at all.
        assert "https://github.com/x/b\n" not in joined  # no trailing token
        assert lines[1] == "https://github.com/x/b"

    def test_tier_a_and_completed_excluded(self):
        lines, summary = mod.build_batch(STATE, BRIEF)
        joined = "\n".join(lines)
        assert "https://github.com/x/c" not in joined  # Tier A
        assert "https://github.com/x/d" not in joined  # completed
        assert summary["skipped_non_tierB"] == 1  # skill c
        assert summary["skipped_non_pending"] == 1  # skill d

    def test_deterministic(self):
        first = mod.build_batch(STATE, BRIEF)
        second = mod.build_batch(STATE, BRIEF)
        assert first == second

    def test_unmatched_target_recorded(self):
        brief_missing_b = {"targets": [{"name": "a", "repo_url": "https://github.com/x/a"}]}
        lines, summary = mod.build_batch(STATE, brief_missing_b)
        assert lines == ["https://github.com/x/a@1.2.0"]
        assert summary["unmatched"] == ["b"]

    def test_empty_repo_url_is_unmatched(self):
        brief_empty = {"targets": [
            {"name": "a", "repo_url": "https://github.com/x/a"},
            {"name": "b", "repo_url": ""},
        ]}
        _, summary = mod.build_batch(STATE, brief_empty)
        assert summary["unmatched"] == ["b"]

    def test_language_and_scope_hints_appended(self):
        brief_hints = {"targets": [
            {"name": "a", "repo_url": "https://github.com/x/a",
             "language_hint": "python", "scope_hint": "pkg/api/"},
            {"name": "b", "repo_url": "https://github.com/x/b"},
        ]}
        lines, _ = mod.build_batch(STATE, brief_hints)
        assert lines[0] == "https://github.com/x/a@1.2.0 language=python scope=pkg/api/"
        assert lines[1] == "https://github.com/x/b"

    def test_no_tier_b_pending_empty(self):
        state = {"skills": [{"name": "c", "tier": "A", "status": "pending", "pin": None}]}
        lines, summary = mod.build_batch(state, BRIEF)
        assert lines == []
        assert summary["count"] == 0


class TestRun:
    def _files(self, tmp_path, state=STATE, brief=BRIEF):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        sf.write_text(yaml.dump(state), encoding="utf-8")
        bf.write_text(yaml.dump(brief), encoding="utf-8")
        return sf, bf

    def test_writes_exactly_two_lines(self, tmp_path, capsys):
        sf, bf = self._files(tmp_path)
        out = tmp_path / "_batch-input.txt"
        rc = mod.run(str(sf), str(bf), str(out))
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        # EXACTLY two lines, trailing newline, verbatim consumer shape.
        assert content == "https://github.com/x/a@1.2.0\nhttps://github.com/x/b\n"
        # summary on stderr, not stdout.
        summary = json.loads(capsys.readouterr().err.strip())
        assert summary == {
            "written": str(out),
            "count": 2,
            "skipped_non_tierB": 1,
            "skipped_non_pending": 1,
        }

    def test_default_stdout(self, tmp_path, capsys):
        sf, bf = self._files(tmp_path)
        rc = mod.run(str(sf), str(bf), None)
        assert rc == 0
        cap = capsys.readouterr()
        assert cap.out == "https://github.com/x/a@1.2.0\nhttps://github.com/x/b\n"
        assert json.loads(cap.err.strip())["written"] == "<stdout>"

    def test_unmatched_target_exit_8(self, tmp_path, capsys):
        brief_missing_b = {"targets": [{"name": "a", "repo_url": "https://github.com/x/a"}]}
        sf, bf = self._files(tmp_path, brief=brief_missing_b)
        out = tmp_path / "_batch-input.txt"
        rc = mod.run(str(sf), str(bf), str(out))
        assert rc == 8
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "unmatched-target"
        assert "b" in err["skills"]
        assert not out.exists()  # no partial batch file written

    def test_missing_brief_exit_8(self, tmp_path, capsys):
        sf, bf = self._files(tmp_path)
        rc = mod.run(str(sf), str(tmp_path / "no-brief.yaml"), None)
        assert rc == 8
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "missing-brief"

    def test_corrupt_brief_exit_8(self, tmp_path, capsys):
        sf, _ = self._files(tmp_path)
        bad_brief = tmp_path / "bad-brief.yaml"
        bad_brief.write_text("targets: [oops\n", encoding="utf-8")
        rc = mod.run(str(sf), str(bad_brief), None)
        assert rc == 8
        assert json.loads(capsys.readouterr().err.strip())["code"] == "missing-brief"

    def test_missing_state_exit_2(self, tmp_path, capsys):
        _, bf = self._files(tmp_path)
        rc = mod.run(str(tmp_path / "no-state.yaml"), str(bf), None)
        assert rc == 2
        assert json.loads(capsys.readouterr().err.strip())["code"] == "STATE_NOT_FOUND"

    def test_corrupt_state_exit_2(self, tmp_path, capsys):
        bad_state = tmp_path / "bad-state.yaml"
        bad_state.write_text("skills: [oops\n", encoding="utf-8")
        _, bf = self._files(tmp_path)
        rc = mod.run(str(bad_state), str(bf), None)
        assert rc == 2
        assert json.loads(capsys.readouterr().err.strip())["code"] == "STATE_PARSE_ERROR"

    def test_no_tier_b_writes_empty_file(self, tmp_path, capsys):
        state = {"skills": [{"name": "c", "tier": "A", "status": "pending", "pin": None}]}
        sf, bf = self._files(tmp_path, state=state)
        out = tmp_path / "_batch-input.txt"
        rc = mod.run(str(sf), str(bf), str(out))
        assert rc == 0
        assert out.read_text(encoding="utf-8") == ""
        assert json.loads(capsys.readouterr().err.strip())["count"] == 0
