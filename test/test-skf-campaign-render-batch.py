"""Tests for campaign-render-batch.py: build the QS --batch input file and join its results.

Confirms the script selects Tier B skills that are pending or left active by an
interrupted batch, leaves out the directive's Skip List, joins each to its
brief `repo_url`, and emits the consumer's single-target line shape verbatim
(`{repo_url}` with `@{pin}` appended only when the state pin is non-null), with
no skill-name field and no bare pin token, while excluding Tier A and
already-handled skills, and HALTing (exit 8) on a missing brief or an unmatched
target. The line-to-skill map and --record join QS batch results back to skills
by batch number, never by matching lines by hand; a hint QS could not read as
one word is left off its line, so every line parses as the map says (checked
against QS's own parser, skf-quick-batch.py).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-render-batch.py"
QUICK_BATCH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-quick-batch.py"


def _load(path=SCRIPT, name="campaign_render_batch"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
qb = _load(QUICK_BATCH, "skf_quick_batch")

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
            "skills": ["a", "b"],
            "skipped_by_directive": [],
            "dropped_hints": [],
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


# --------------------------------------------------------------------------
# Selection: interrupted (active) skills and the directive's Skip List
# --------------------------------------------------------------------------


class TestSelection:
    def test_active_tier_b_skill_is_batched_again(self):
        state = {"skills": [
            {"name": "a", "tier": "B", "status": "active", "pin": None},
            {"name": "b", "tier": "B", "status": "pending", "pin": None},
        ]}
        lines, summary = mod.build_batch(state, BRIEF)
        assert lines == ["https://github.com/x/a", "https://github.com/x/b"]
        assert summary["skills"] == ["a", "b"]

    def test_skip_list_leaves_a_skill_out(self):
        lines, summary = mod.build_batch(STATE, BRIEF, {"a": "abandoned"})
        assert lines == ["https://github.com/x/b"]
        assert summary["skills"] == ["b"]
        assert summary["skipped_by_directive"] == [{"name": "a", "reason": "abandoned"}]

    def test_skip_list_names_only_selected_skills(self):
        # d is completed and c is Tier A: the Skip List changes nothing for them.
        _, summary = mod.build_batch(STATE, BRIEF, {"c": None, "d": None})
        assert summary["skipped_by_directive"] == []

    def test_directive_file_is_read_by_the_gate_parser(self, tmp_path, capsys):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        df = tmp_path / "_campaign-directive.md"
        sf.write_text(yaml.dump(STATE), encoding="utf-8")
        bf.write_text(yaml.dump(BRIEF), encoding="utf-8")
        df.write_bytes(b"## Skip List\n- `b`: flaky upstream\n")
        out = tmp_path / "_batch-input.txt"
        rc = mod.run(str(sf), str(bf), str(out), None, str(df))
        assert rc == 0
        assert out.read_text(encoding="utf-8") == "https://github.com/x/a@1.2.0\n"
        summary = json.loads(capsys.readouterr().err.strip())
        assert summary["skipped_by_directive"] == [{"name": "b", "reason": "flaky upstream"}]

    def test_missing_directive_file_is_no_directive(self, tmp_path, capsys):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        sf.write_text(yaml.dump(STATE), encoding="utf-8")
        bf.write_text(yaml.dump(BRIEF), encoding="utf-8")
        rc = mod.run(str(sf), str(bf), None, None, str(tmp_path / "none.md"))
        assert rc == 0
        assert capsys.readouterr().out.count("\n") == 2


# --------------------------------------------------------------------------
# The line-to-skill map and --record
# --------------------------------------------------------------------------

# Two Tier B skills from one repository and pin: their lines read the same.
TWIN_STATE = {"skills": [
    {"name": "api", "tier": "B", "status": "pending", "pin": "1.0.0"},
    {"name": "cli", "tier": "B", "status": "pending", "pin": "1.0.0"},
]}
TWIN_BRIEF = {"targets": [
    {"name": "api", "repo_url": "https://github.com/x/mono", "scope_hint": "api/"},
    {"name": "cli", "repo_url": "https://github.com/x/mono"},
]}


def _summary(*results):
    return {"skill": "skf-quick-skill", "mode": "batch", "status": "partial", "results": list(results)}


def _result(batch, target, status="success", **extra):
    base = {"batch": batch, "target": target, "status": status, "exit_code": 0 if status == "success" else 3,
            "skill_package": None, "error_code": None, "quality_score": None}
    base.update(extra)
    return base


class TestMapAndRecord:
    def _render(self, tmp_path, capsys, state=TWIN_STATE, brief=TWIN_BRIEF):
        sf = tmp_path / "state.yaml"
        bf = tmp_path / "brief.yaml"
        sf.write_text(yaml.dump(state), encoding="utf-8")
        bf.write_text(yaml.dump(brief), encoding="utf-8")
        out = tmp_path / "_batch-input.txt"
        map_file = tmp_path / "_batch-map.json"
        assert mod.run(str(sf), str(bf), str(out), str(map_file)) == 0
        capsys.readouterr()
        return out, map_file

    def test_map_numbers_lines_like_qs(self, tmp_path, capsys):
        out, map_file = self._render(tmp_path, capsys)
        batch_map = json.loads(map_file.read_text(encoding="utf-8"))
        assert out.read_text(encoding="utf-8").splitlines() == [
            "https://github.com/x/mono@1.0.0 scope=api/",
            "https://github.com/x/mono@1.0.0",
        ]
        assert batch_map["lines"] == [
            {"batch": 1, "skill": "api", "target": "https://github.com/x/mono@1.0.0",
             "line": "https://github.com/x/mono@1.0.0 scope=api/"},
            {"batch": 2, "skill": "cli", "target": "https://github.com/x/mono@1.0.0",
             "line": "https://github.com/x/mono@1.0.0"},
        ]
        assert batch_map["batch_file"] == str(out)

    def test_record_joins_by_batch_number(self, tmp_path, capsys):
        _, map_file = self._render(tmp_path, capsys)
        summary = tmp_path / "quick-skill-batch-latest.json"
        summary.write_text(json.dumps(_summary(
            _result(2, "https://github.com/x/mono@1.0.0", "error", error_code="no-exports"),
            _result(1, "https://github.com/x/mono@1.0.0", skill_package="/skills/mono-api/1.0.0/mono-api",
                    quality_score=88),
        )), encoding="utf-8")
        rc = mod.main(["--record", str(summary), "--map", str(map_file)])
        assert rc == 0
        joined = json.loads(capsys.readouterr().out)
        assert joined["results"] == [
            {"skill": "api", "batch": 1, "status": "completed", "quality_score": 88,
             "skill_path": "/skills/mono-api/1.0.0/mono-api", "exit_code": 0, "error_code": None},
            {"skill": "cli", "batch": 2, "status": "failed", "quality_score": None,
             "skill_path": None, "exit_code": 3, "error_code": "no-exports"},
        ]
        assert joined["counts"] == {"completed": 1, "failed": 1}

    def test_a_line_with_no_result_fails(self, tmp_path, capsys):
        _, map_file = self._render(tmp_path, capsys)
        summary = tmp_path / "s.json"
        summary.write_text(json.dumps(_summary(_result(1, "https://github.com/x/mono@1.0.0"))), encoding="utf-8")
        assert mod.main(["--record", str(summary), "--map", str(map_file)]) == 0
        results = json.loads(capsys.readouterr().out)["results"]
        assert results[1]["status"] == "failed"
        assert results[1]["error_code"] == "no-batch-result"

    def test_summary_of_another_batch_is_refused(self, tmp_path, capsys):
        _, map_file = self._render(tmp_path, capsys)
        summary = tmp_path / "s.json"
        summary.write_text(json.dumps(_summary(_result(1, "https://github.com/x/other"))), encoding="utf-8")
        assert mod.main(["--record", str(summary), "--map", str(map_file)]) == 2
        err = json.loads(capsys.readouterr().err)
        assert err["code"] == "SUMMARY_MISMATCH"

    @pytest.mark.parametrize("missing", ["map", "summary"], ids=["no-map", "no-summary"])
    def test_missing_file_exit_2(self, tmp_path, capsys, missing):
        _, map_file = self._render(tmp_path, capsys)
        summary = tmp_path / "s.json"
        summary.write_text(json.dumps(_summary()), encoding="utf-8")
        args = {"map": str(map_file), "summary": str(summary)}
        args[missing] = str(tmp_path / "gone.json")
        assert mod.main(["--record", args["summary"], "--map", args["map"]]) == 2
        assert json.loads(capsys.readouterr().err)["code"] == f"{missing.upper()}_NOT_FOUND"

    def test_spaced_hint_is_left_out_and_the_join_still_completes(self, tmp_path, capsys):
        state = {"skills": [
            {"name": "aa", "tier": "B", "status": "pending", "pin": None},
            {"name": "bb", "tier": "B", "status": "pending", "pin": "2.0.0"},
        ]}
        brief = {"targets": [
            {"name": "aa", "repo_url": "https://github.com/o/aa", "language": "go"},
            {"name": "bb", "repo_url": "https://github.com/o/bb", "scope": "public api", "language_hint": "ts"},
        ]}
        sf, bf = tmp_path / "state.yaml", tmp_path / "brief.yaml"
        sf.write_text(yaml.dump(state), encoding="utf-8")
        bf.write_text(yaml.dump(brief), encoding="utf-8")
        out, map_file = tmp_path / "_batch-input.txt", tmp_path / "_batch-map.json"
        assert mod.run(str(sf), str(bf), str(out), str(map_file)) == 0
        assert json.loads(capsys.readouterr().err)["dropped_hints"] == [
            {"skill": "bb", "hint": "scope", "value": "public api"},
        ]
        # QS reads the file as the map says: one target per line, the hints as modifiers.
        parsed = qb.parse_text(out.read_text(encoding="utf-8"))
        batch_map = json.loads(map_file.read_text(encoding="utf-8"))
        assert [(t["batch"], t["target"]) for t in parsed] == [(e["batch"], e["target"]) for e in batch_map["lines"]]
        assert parsed[1]["language_hint"] == "ts"
        summary = tmp_path / "s.json"
        summary.write_text(json.dumps(_summary(*(
            _result(t["batch"], t["target"], skill_package=f"/skills/{t['batch']}", quality_score=90) for t in parsed
        ))), encoding="utf-8")
        assert mod.main(["--record", str(summary), "--map", str(map_file)]) == 0
        joined = json.loads(capsys.readouterr().out)
        assert joined["counts"] == {"completed": 2, "failed": 0}

    @pytest.mark.parametrize(
        "hints",
        [
            {"scope_hint": "pkg/api/"},
            {"language": "c++", "scope": "src/core"},
            {"scope": "a=b"},
            {"language_hint": " python "},
            {"scope_hint": "two words", "language_hint": "go"},
            {"language": "\tpython\n3"},
            {"scope": ""},
        ],
        ids=["scope", "both", "equals-in-value", "padded", "spaced-scope", "tab-newline", "empty"],
    )
    def test_every_line_parses_as_its_map_entry(self, hints):
        state = {"skills": [{"name": "x", "tier": "B", "status": "pending", "pin": "1.0.0"}]}
        brief = {"targets": [{"name": "x", "repo_url": "https://github.com/o/x", **hints}]}
        lines, summary = mod.build_batch(state, brief)
        entry = mod.build_map(lines, summary, "f")["lines"][0]
        assert qb.parse_line(lines[0])["target"] == entry["target"] == "https://github.com/o/x@1.0.0"

    def test_record_needs_a_map(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--record", "s.json"])
        assert exc.value.code == 2

    def test_render_needs_state_and_brief(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.main(["-o", "x.txt"])
        assert exc.value.code == 2
