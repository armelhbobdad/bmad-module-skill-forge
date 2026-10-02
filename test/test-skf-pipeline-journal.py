#!/usr/bin/env python3
"""Tests for src/skf-forger/scripts/pipeline-journal.py.

The forger keeps each chain's state in a journal on disk (#587), so a
killed session or a compacted context loses nothing:
  - start parses the invocation with parse-pipeline.py and records the plan
    with its bracket values, the alias and the first workflow's args
  - step records each step in plan order: a gated step takes the decision
    the gate printed (a skip also records the step it passes over), any
    other step its status; a halt needs its reason, and a completed step
    the value it hands the next
  - finish writes pipeline-result-<UTC>.json and its -latest copy in
    output-contract-schema.md's shape, with one fixed per-step shape
    (#593), prints the next action the stop leaves, deletes only the
    journal's own run folder when nothing is left to resume, and records
    the stop even when the journal cannot be saved or read
  - resume: a chain killed after its second workflow offers to resume at the
    third with the original alias, brackets and args; a quality halt offers
    its repair route, keyed on the gate's reason; no offer once a later
    chain recorded a result (behind a parse halt's record too), or the skill
    was tested or exported since
  - reopen applies the offer: US --from-test-report joins the plan before a
    failed TS, an AS CRITICAL review picks the chain up after AS with the
    skill as US's target; discard drops a stopped chain
  - the calls SKILL.md and pipeline-mode.md document run as written, a
    reason with shell characters included, and the contract tables in
    pipeline-contracts.md match the script
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "skf-forger" / "scripts" / "pipeline-journal.py"
GATE = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"
CONTRACTS = SRC / "shared" / "references" / "pipeline-contracts.md"
OUTPUT_CONTRACT = SRC / "shared" / "references" / "output-contract-schema.md"
# test-skill's halt reasons live in its envelope schema (#593, #600).
TEST_SKILL_SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-test-result-envelope.v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("skf_pipeline_journal", SCRIPT)

HONO = "https://github.com/honojs/hono"
FORGE_AUTO = f"forge-auto {HONO} --pin v4.6.0"
T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
STEP_KEYS = ["code", "min", "mode", "target", "flags", "status", "reason"]
GATED = ("AN", "TS", "AS", "VS")
# The value each code hands the next workflow, as a completed step records it.
HANDOFF = {"AN": "brief_path=/fd/hono/skill-brief.yaml", "BS": "brief_path=/fd/hono/skill-brief.yaml",
           "CS": "skill_name=hono", "QS": "skill_name=cognee", "US": "skill_name=hono"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def gate_json(code: str, decision: str = "continue", reason: str | None = None, skip: str | None = None) -> str:
    """What pipeline-gate.py prints for a decision."""
    return json.dumps({"code": code, "decision": decision, "reason": reason, "skip": skip,
                       "message": f"{code}: {decision}"}, indent=2)


# --------------------------------------------------------------------------
# Fixtures: an in-process CLI on a controlled clock, and a chain's folders
# --------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = T0

    def tick(self, seconds: int = 60) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(mod, "_now", lambda: c.now)
    return c


@pytest.fixture
def cli(capsys, monkeypatch, clock):
    """Run the script's main() in-process; returns the JSON it printed."""

    def invoke(*argv, stdin: str = "", code: int = 0) -> dict:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        rc = mod.main([str(a) for a in argv])
        out = capsys.readouterr().out
        assert rc == code, out
        return json.loads(out)

    return invoke


class Chain:
    """The folders a chain reads and writes, and shortcuts for its calls."""

    def __init__(self, root: Path, cli, clock):
        self.root = root
        self.run_root = root / "_bmad-output" / ".skf-run"
        self.sidecar = root / "_bmad" / "_memory" / "forger-sidecar"
        self.forge = root / "forge-data"
        self.skills = root / "skills"
        self.cli = cli
        self.clock = clock
        self.journal: Path | None = None

    def start(self, invocation: str) -> dict:
        out = self.cli("start", "--run-root", self.run_root, stdin=invocation + "\n")
        self.journal = Path(out["journal"])
        return out

    def step(self, code: str, status: str = "completed", *extra, reason: str | None = None, rc: int = 0) -> dict:
        """A step with no gate decision: --status."""
        self.clock.tick()
        argv = ["step", "--journal", self.journal, "--code", code, "--status", status, *extra]
        if reason is not None:
            argv += ["--reason", reason]
        return self.cli(*argv, code=rc)

    def gate(self, code: str, decision: str = "continue", *extra, reason: str | None = None,
             skip: str | None = None, rc: int = 0) -> dict:
        """A gated step: the decision the gate printed, on stdin."""
        self.clock.tick()
        return self.cli("step", "--journal", self.journal, "--code", code, "--gate", *extra,
                        stdin=gate_json(code, decision, reason, skip), code=rc)

    def ran(self, code: str, *extra) -> dict:
        """A step that went on: its gate continued, or it completed, handing its value on."""
        handoff = HANDOFF.get(code)
        if handoff and not any(str(a).startswith(handoff.split("=")[0] + "=") for a in extra):
            extra = (*extra, "--set", handoff)
        return self.gate(code, "continue", *extra) if code in GATED else self.step(code, "completed", *extra)

    def halt(self, code: str, reason: str) -> dict:
        """A step that halted: the gate's halt, or the workflow's own."""
        return self.gate(code, "halt", reason=reason) if code in GATED else self.step(code, "halted", reason=reason)

    def finish(self, *extra, code: int = 0) -> dict:
        self.clock.tick()
        return self.cli("finish", "--journal", self.journal, "--result-dir", self.sidecar, *extra, code=code)

    def resume(self) -> dict:
        return self.cli("resume", "--run-root", self.run_root, "--result-dir", self.sidecar,
                        "--forge-data-folder", self.forge, "--skills-output-folder", self.skills)

    def reopen(self, code: int = 0) -> dict:
        self.clock.tick()
        return self.cli("reopen", "--journal", self.journal, code=code)

    def data(self) -> dict:
        return json.loads(_read(self.journal))


@pytest.fixture
def chain(tmp_path, cli, clock):
    return Chain(tmp_path, cli, clock)


def _halt_forge_auto_at_ts(chain: Chain, reason: str) -> None:
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    chain.ran("BS")
    chain.ran("CS")
    chain.halt("TS", reason)  # recorded at 12:04:00


def _succeed_forge_quick(chain: Chain) -> None:
    chain.start("forge-quick cognee")
    chain.ran("QS")
    chain.ran("TS")
    chain.step("EX")


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------


def test_start_records_the_plan_alias_and_args(chain):
    out = chain.start(FORGE_AUTO)
    assert out["status"] == "ok"
    assert RUN_ID_RE.match(out["run_id"]), out["run_id"]
    assert Path(out["run_dir"]).name == f"skf-forger-{out['run_id']}"
    assert Path(out["run_dir"]).parent == chain.run_root
    journal = chain.data()
    assert journal["journal_version"] == 1
    assert journal["status"] == "running"
    assert journal["invocation"] == FORGE_AUTO
    assert journal["alias"] == "forge-auto"
    assert journal["args"] == {"project_path": HONO, "pin": "v4.6.0"}
    assert [s["code"] for s in journal["steps"]] == ["AN", "BS", "CS", "TS", "EX"]
    assert [s["mode"] for s in journal["steps"]] == ["auto", "auto", None, None, None]
    assert [s["min"] for s in journal["steps"]] == [None, None, None, 90, None]
    assert all(list(s) == STEP_KEYS and s["status"] == "pending" for s in journal["steps"])
    assert journal["started_at"] == journal["updated_at"] == "2026-10-01T12:00:00Z"
    assert journal["run_id"].startswith("20261001T120000Z-")
    assert (journal["data"], journal["outputs"], journal["history"]) == ({}, [], [])


def test_start_keeps_a_target_bracket_and_an_ad_hoc_chain_has_no_alias(chain):
    chain.start("QS[cognee] TS[min:85] EX")
    journal = chain.data()
    assert journal["alias"] is None
    assert journal["args"] == {}
    assert [(s["code"], s["target"], s["min"]) for s in journal["steps"]] == [
        ("QS", "cognee", None), ("TS", None, 85), ("EX", None, None)]


@pytest.mark.parametrize("invocation", ["BS CS TX EX", f"onboard {HONO}", "forge-quick", "TS[min:80%] EX"],
                         ids=["unknown-code", "removed-alias", "missing-arg", "malformed-bracket"])
def test_start_refuses_an_invocation_step_1_halts_on(chain, invocation):
    out = chain.cli("start", "--run-root", chain.run_root, stdin=invocation, code=1)
    assert (out["status"], out["error"], out["retry"]) == ("error", "not-runnable", False)
    assert not chain.run_root.exists()


def test_start_needs_an_invocation(chain):
    out = chain.cli("start", "--run-root", chain.run_root, stdin="  \n", code=1)
    assert out["error"] == "no-invocation"


# --------------------------------------------------------------------------
# step
# --------------------------------------------------------------------------


def test_steps_record_in_order_and_hand_their_values_on(chain):
    chain.start(FORGE_AUTO)
    out = chain.gate("AN", "continue", "--set", "brief_path=/fd/hono/skill-brief.yaml",
                     "--output", "/fd/hono/analyze-source-result-latest.json")
    assert out["recorded"]["index"] == 0 and out["recorded"]["status"] == "completed"
    assert out["skipped"] is None
    assert out["next"]["code"] == "BS" and out["next"]["mode"] == "auto"
    assert out["data"] == {"brief_path": "/fd/hono/skill-brief.yaml"}
    journal = chain.data()
    assert journal["outputs"] == [{"code": "AN", "path": "/fd/hono/analyze-source-result-latest.json"}]
    assert journal["updated_at"] == "2026-10-01T12:01:00Z"
    wrong = chain.step("CS", "completed", "--set", "skill_name=hono", rc=1)
    assert (wrong["error"], wrong["retry"]) == ("out-of-order", False)
    assert "BS" in wrong["message"]


def test_the_code_matches_in_any_case(chain):
    chain.start("QS TS EX")
    assert chain.step("qs", "completed", "--set", "skill_name=cognee")["recorded"]["code"] == "QS"


def test_a_gate_skip_records_the_step_it_passes_over(chain):
    """maintain with a CLEAN audit: one call records AS and the skipped US,
    so the next step, TS, goes in without an out-of-order error."""
    chain.start("maintain cocoindex")
    out = chain.gate("AS", "skip", reason="CLEAN", skip="US")
    assert (out["recorded"]["code"], out["recorded"]["status"], out["recorded"]["reason"]) == ("AS", "completed", None)
    assert (out["skipped"]["code"], out["skipped"]["status"], out["skipped"]["reason"]) == ("US", "skipped", "CLEAN")
    assert out["next"]["code"] == "TS"
    assert chain.ran("TS")["next"]["code"] == "EX"


def test_a_gate_halt_records_its_reason_and_stops_the_journal(chain):
    chain.start("forge-quick cognee")
    chain.ran("QS")
    out = chain.gate("TS", "halt", reason="FAIL")
    assert (out["recorded"]["status"], out["recorded"]["reason"], out["next"]) == ("halted", "FAIL", None)
    assert chain.data()["status"] == "halted"


def test_a_skip_passes_over_only_the_step_after_the_gated_one(chain):
    chain.start("AS[cocoindex] TS EX")
    out = chain.gate("AS", "skip", reason="CLEAN", skip="US", rc=1)
    assert (out["error"], out["retry"]) == ("skip-mismatch", False)
    assert [s["status"] for s in chain.data()["steps"]] == ["pending"] * 3


def test_a_gated_step_records_the_gates_decision_not_a_status(chain):
    chain.start("forge-quick cognee")
    chain.ran("QS")
    out = chain.step("TS", "completed", rc=1)
    assert (out["error"], out["retry"]) == ("gate-required", True)
    # A gate that printed no JSON: the halt goes in with what it printed.
    out = chain.step("TS", "halted", reason="Traceback: the gate crashed")
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "Traceback: the gate crashed")


@pytest.mark.parametrize(("stdin", "error"), [
    pytest.param("", "gate-unreadable", id="empty"),
    pytest.param("not json", "gate-unreadable", id="not-json"),
    pytest.param(json.dumps({"code": "TS", "decision": "maybe"}), "gate-unreadable", id="unknown-decision"),
    pytest.param(json.dumps({"code": "TS", "decision": "halt", "reason": None}), "gate-unreadable",
                 id="halt-without-reason"),
    pytest.param(json.dumps({"code": "AS", "decision": "continue"}), "gate-mismatch", id="another-codes-decision"),
])
def test_a_decision_that_does_not_fit_is_refused(chain, stdin, error):
    chain.start("forge-quick cognee")
    chain.ran("QS")
    out = chain.cli("step", "--journal", chain.journal, "--code", "TS", "--gate", stdin=stdin, code=1)
    assert (out["error"], out["retry"]) == (error, True)
    assert chain.data()["steps"][1]["status"] == "pending"


def test_a_decision_with_text_around_it_still_reads(chain):
    chain.start("forge-quick cognee")
    chain.ran("QS")
    out = chain.cli("step", "--journal", chain.journal, "--code", "TS", "--gate",
                    stdin="```json\n" + gate_json("TS") + "\n```\n")
    assert out["recorded"]["status"] == "completed"


@pytest.mark.parametrize(("invocation", "code", "name"), [
    pytest.param("CS TS EX", "CS", "skill_name", id="cs"),
    pytest.param("forge-quick cognee", "QS", "skill_name", id="qs"),
    pytest.param("US[hono] TS EX", "US", "skill_name", id="us"),
    pytest.param(FORGE_AUTO, "AN", "brief_path", id="an"),
    pytest.param(f"forge {HONO} hono", "BS", "brief_path", id="bs"),
])
def test_a_completed_step_hands_its_value_on(chain, invocation, code, name):
    """The resumed chain, a repair's target and the later-test and
    later-export checks all need it."""
    chain.start(invocation)
    out = chain.gate(code, "continue", rc=1) if code in GATED else chain.step(code, "completed", rc=1)
    assert (out["error"], out["retry"]) == ("handoff-missing", True)
    assert f'--set "{name}=<value>"' in out["message"]
    assert chain.data()["steps"][0]["status"] == "pending"
    # A step that halted hands nothing on.
    assert chain.halt(code, "helper-missing")["recorded"]["status"] == "halted"


def test_a_halt_needs_its_reason(chain):
    chain.start("QS TS EX")
    out = chain.step("QS", "halted", rc=1)
    assert (out["error"], out["retry"]) == ("reason-missing", True)
    assert chain.data()["steps"][0]["status"] == "pending"


def test_a_halted_journal_takes_no_step_until_it_is_reopened(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    journal = chain.data()
    assert journal["status"] == "halted"
    assert journal["steps"][3]["reason"] == "FAIL"
    out = chain.step("EX", rc=1)
    assert out["error"] == "not-running"


def test_a_name_set_twice_holds_a_list(chain):
    chain.start(FORGE_AUTO)
    out = chain.gate("AN", "continue", "--set", "brief_path=/a.yaml", "--set", "brief_path=/b.yaml",
                     "--set", "skill_name=hono")
    assert out["data"] == {"brief_path": ["/a.yaml", "/b.yaml"], "skill_name": "hono"}


@pytest.mark.parametrize("pair", ["Skill=x", "skill_name=", "novalue", "=x"])
def test_set_takes_a_lower_case_name_and_a_value(chain, pair):
    chain.start("QS TS EX")
    out = chain.step("QS", "completed", "--set", pair, rc=1)
    assert (out["error"], out["retry"]) == ("bad-value", True)


def test_a_journal_that_is_not_one_is_refused(chain, tmp_path):
    bad = tmp_path / "pipeline-journal.json"
    bad.write_bytes(b'{"steps": "no"}')
    out = chain.cli("step", "--journal", bad, "--code", "QS", "--status", "completed", code=1)
    assert out["error"] == "journal-unreadable"


# --------------------------------------------------------------------------
# finish: the pipeline result and the next action
# --------------------------------------------------------------------------


def _records(sidecar: Path) -> list[Path]:
    return sorted(p for p in sidecar.glob("pipeline-result-*.json") if p.name != "pipeline-result-latest.json")


def _latest(chain: Chain) -> dict:
    return json.loads(_read(chain.sidecar / "pipeline-result-latest.json"))


def _schema_keys() -> list[str]:
    """The top-level keys output-contract-schema.md's Schema block lists, in order."""
    block = re.search(r"## Schema\s*```json\n(.*?)\n```", _read(OUTPUT_CONTRACT), re.S)
    assert block, "output-contract-schema.md has no Schema block"
    return re.findall(r'^  "(\w+)":', block.group(1), re.M)


def test_a_chain_that_succeeds_leaves_two_records_and_no_run_folder(chain):
    chain.start("forge-quick cognee")
    chain.ran("QS", "--output", "/skills/cognee/0.3.0/cognee/quick-skill-result-latest.json")
    chain.ran("TS")
    chain.step("EX")
    out = chain.finish()
    assert (out["pipeline_status"], out["halt_reason"], out["run_dir_kept"]) == ("success", None, False)
    assert all(out[key] is None for key in mod.NEXT_ACTION_KEYS)
    assert not chain.journal.parent.exists()
    [per_run] = _records(chain.sidecar)
    assert per_run.name == "pipeline-result-20261001-120400.json"
    assert Path(out["result_path"]) == per_run
    latest = chain.sidecar / "pipeline-result-latest.json"
    assert Path(out["latest_path"]) == latest
    assert per_run.read_bytes() == latest.read_bytes()
    assert b"\r\n" not in latest.read_bytes()
    record = _latest(chain)
    assert list(record) == _schema_keys()
    assert record["skill"] == "skf-forger"
    assert record["status"] == record["summary"]["status"] == "success"
    assert record["timestamp"] == "2026-10-01T12:04:00Z"
    assert RUN_ID_RE.match(record["run_id"])
    assert record["outputs"] == [{"type": "report", "path": "/skills/cognee/0.3.0/cognee/quick-skill-result-latest.json"}]
    assert list(record["summary"]) == ["status", "halt_reason", "alias", "steps"]
    assert record["summary"]["alias"] == "forge-quick"
    assert [(s["code"], s["status"]) for s in record["summary"]["steps"]] == [
        ("QS", "completed"), ("TS", "completed"), ("EX", "completed")]
    assert all(list(s) == STEP_KEYS for s in record["summary"]["steps"])
    assert (record["headless_decisions"], record["warnings"]) == ([], [])


def test_a_quality_halt_leaves_a_partial_result_and_names_its_repair(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    out = chain.finish()
    assert (out["pipeline_status"], out["halt_reason"], out["run_dir_kept"]) == ("partial", "FAIL", True)
    assert (out["offer"], out["kind"], out["repair"], out["user_action"]) == (
        "repair", "quality", "update-from-test-report", None)
    assert out["route"] == "US hono --from-test-report, then TS EX at the recorded threshold of 90"
    assert (out["halted_on"], out["resume_at"], out["threshold"]) == (
        {"index": 3, "code": "TS", "reason": "FAIL"}, {"index": 3, "code": "TS"}, 90)
    assert chain.journal.is_file()
    record = _latest(chain)
    assert record["run_id"] == chain.data()["run_id"]
    assert [(s["code"], s["status"], s["reason"]) for s in record["summary"]["steps"]] == [
        ("AN", "completed", None), ("BS", "completed", None), ("CS", "completed", None),
        ("TS", "halted", "FAIL"), ("EX", "pending", None)]


def test_a_halt_before_any_step_completed_is_failed(chain):
    chain.start("forge-quick cognee")
    chain.halt("QS", "target-inaccessible")
    out = chain.finish()
    assert (out["pipeline_status"], out["run_dir_kept"]) == ("failed", True)
    assert (out["offer"], out["kind"], out["route"]) == ("resume", "error", "resume at QS: QS TS EX")


def test_a_halt_no_resume_fixes_leaves_no_run_folder(chain):
    chain.start(FORGE_AUTO)
    chain.halt("AN", "no-skillable-units")
    out = chain.finish()
    assert (out["pipeline_status"], out["run_dir_kept"], out["offer"]) == ("failed", False, None)
    assert (out["repair"], out["route"]) == ("new-target", f"no resume: {mod.USER_ACTIONS['new-target']}")
    assert not chain.journal.parent.exists()


def test_a_parse_halt_records_no_step(chain):
    out = chain.cli("finish", "--result-dir", chain.sidecar, "--halt-reason", "unknown code TX")
    assert (out["pipeline_status"], out["halt_reason"], out["run_dir_kept"]) == ("failed", "unknown code TX", False)
    assert all(out[key] is None for key in mod.NEXT_ACTION_KEYS)
    record = _latest(chain)
    assert record["summary"] == {"status": "failed", "halt_reason": "unknown code TX", "alias": None, "steps": []}
    assert (record["headless_decisions"], record["warnings"]) == ([], [])
    assert RUN_ID_RE.match(record["run_id"])
    out = chain.cli("finish", "--result-dir", chain.sidecar, code=1)
    assert (out["error"], out["retry"]) == ("reason-missing", True)


def test_finish_halts_the_pending_step_only_with_a_reason(chain):
    chain.start("QS TS EX")
    chain.ran("QS")
    out = chain.finish(code=1)
    assert (out["error"], out["retry"]) == ("unfinished", True)
    out = chain.finish("--halt-reason", "stopped: the workflow printed no envelope")
    assert (out["pipeline_status"], out["halt_reason"]) == ("partial", "stopped: the workflow printed no envelope")
    assert (out["offer"], out["kind"], out["route"]) == ("resume", "error", "resume at TS: TS EX")
    assert chain.data()["steps"][1]["status"] == "halted"


def test_finish_writes_the_result_when_the_journal_cannot_be_saved(chain, monkeypatch):
    chain.start("QS TS EX")
    chain.ran("QS")

    def refuse(path, journal):
        raise mod.JournalError("write-failed", f"The journal {path} cannot be written: disk full")

    monkeypatch.setattr(mod, "_save", refuse)
    out = chain.finish("--halt-reason", "context exhausted")
    assert (out["status"], out["pipeline_status"]) == ("ok", "partial")
    assert out["warnings"] == [f"journal_not_saved: The journal {chain.journal} cannot be written: disk full"]
    record = _latest(chain)
    assert record["run_id"] == chain.data()["run_id"]
    assert record["warnings"] == out["warnings"]


def test_finish_still_records_a_run_whose_journal_is_lost(chain):
    chain.start("QS TS EX")
    chain.ran("QS")
    run_id = chain.data()["run_id"]
    chain.journal.write_bytes(b"{not json")
    out = chain.finish("--halt-reason", "context exhausted")
    assert (out["pipeline_status"], out["halt_reason"], out["run_dir_kept"]) == ("failed", "context exhausted", True)
    assert out["warnings"] == [f"journal_unreadable: {chain.journal.as_posix()}"]
    record = _latest(chain)
    assert (record["run_id"], record["summary"]["steps"], record["warnings"]) == (run_id, [], out["warnings"])


def test_a_finished_run_is_not_recorded_twice(chain):
    _succeed_forge_quick(chain)
    chain.finish()
    out = chain.finish(code=1)
    assert (out["error"], out["retry"]) == ("already-finished", False)
    assert len(_records(chain.sidecar)) == 1
    assert _latest(chain)["status"] == "success"


def test_finish_deletes_only_the_journals_own_run_folder(chain, tmp_path, monkeypatch):
    _succeed_forge_quick(chain)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_bytes(b"kept")
    moved = elsewhere / "pipeline-journal.json"
    moved.write_bytes(chain.journal.read_bytes())
    chain.journal = moved
    out = chain.finish()
    warning = f"run_dir_not_deleted: {elsewhere.as_posix()}: not the journal's run folder"
    assert (out["pipeline_status"], out["run_dir_kept"], out["warnings"]) == ("success", True, [warning])
    assert (elsewhere / "keep.txt").is_file()
    assert _latest(chain)["warnings"] == [warning]
    # A relative journal path names no run folder either.
    monkeypatch.chdir(elsewhere)
    out = chain.cli("finish", "--journal", "pipeline-journal.json", "--result-dir", chain.sidecar)
    assert out["run_dir_kept"] is True
    assert (elsewhere / "keep.txt").is_file()


def test_two_records_in_one_second_do_not_collide(tmp_path):
    record = {"skill": "skf-forger"}
    first, _ = mod._write_result(tmp_path, record, T0)
    second, latest = mod._write_result(tmp_path, record, T0)
    assert (first.name, second.name) == ("pipeline-result-20261001-120000.json", "pipeline-result-20261001-120000-2.json")
    assert json.loads(_read(latest)) == record


# --------------------------------------------------------------------------
# resume: the offer a new activation makes
# --------------------------------------------------------------------------


def test_no_journal_no_offer(chain):
    out = chain.resume()
    assert (out["status"], out["why"]) == ("none", "no-journal")


def test_a_chain_killed_after_its_second_workflow_resumes_at_the_third(chain):
    """#587's acceptance: the original alias, bracket values and args come back."""
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    chain.ran("BS")
    out = chain.resume()
    assert (out["status"], out["offer"], out["kind"], out["repair"]) == ("offer", "resume", "interrupted", None)
    assert out["halted_on"] == {"index": 2, "code": "CS", "reason": None}
    assert out["resume_at"] == {"index": 2, "code": "CS"}
    assert out["alias"] == "forge-auto"
    assert out["args"] == {"project_path": HONO, "pin": "v4.6.0"}
    assert out["data"] == {"brief_path": "/fd/hono/skill-brief.yaml"}
    assert [(s["code"], s["min"]) for s in out["remaining"]] == [("CS", None), ("TS", 90), ("EX", None)]
    assert out["threshold"] == 90
    assert (out["route"], out["user_action"]) == ("resume at CS: CS TS EX at the recorded threshold of 90", None)
    assert Path(out["journal"]) == chain.journal


def _repair_route(repair: str, run: str) -> str:
    return f"{mod.USER_ACTIONS[repair]}, then {run}"


@pytest.mark.parametrize(
    ("invocation", "steps", "halted", "reason", "repair", "resume_at", "route"),
    [
        pytest.param(FORGE_AUTO, ["AN", "BS", "CS"], "TS", "FAIL", "update-from-test-report", ("TS", 3),
                     "US hono --from-test-report, then TS EX at the recorded threshold of 90", id="ts-fail"),
        pytest.param(FORGE_AUTO, ["AN", "BS", "CS"], "TS", "INCONCLUSIVE", "add-evidence", ("TS", 3),
                     _repair_route("add-evidence", "TS EX at the recorded threshold of 90"), id="ts-inconclusive"),
        pytest.param(FORGE_AUTO, ["AN", "BS", "CS"], "TS", "pass-with-drift", "retest-at-pinned-commit", ("TS", 3),
                     _repair_route("retest-at-pinned-commit", "TS EX at the recorded threshold of 90"),
                     id="ts-pass-with-drift"),
        pytest.param(FORGE_AUTO, ["AN", "BS", "CS"], "TS", "workspace-drift", "retest-at-pinned-commit", ("TS", 3),
                     _repair_route("retest-at-pinned-commit", "TS EX at the recorded threshold of 90"),
                     id="ts-workspace-drift"),
        pytest.param("maintain cocoindex", [], "AS", "CRITICAL", "review-drift-report", ("US", 1),
                     _repair_route("review-drift-report", "US TS EX"), id="as-critical"),
        pytest.param("VS RA", [], "VS", "zero-coverage", "create-missing-skills", ("VS", 0),
                     _repair_route("create-missing-skills", "VS RA"), id="vs-zero-coverage"),
    ],
)
def test_a_quality_halt_offers_its_repair_route(chain, invocation, steps, halted, reason, repair, resume_at, route):
    chain.start(invocation)
    for code in steps:
        chain.ran(code)
    chain.halt(halted, reason)
    finished = chain.finish()
    assert finished["run_dir_kept"] is True
    out = chain.resume()
    assert (out["status"], out["offer"], out["kind"], out["repair"]) == ("offer", "repair", "quality", repair)
    assert out["halted_on"]["code"] == halted and out["halted_on"]["reason"] == reason
    assert (out["resume_at"]["code"], out["resume_at"]["index"]) == resume_at
    assert (out["route"], out["user_action"]) == (route, mod.USER_ACTIONS[repair])
    # The summary at the halt names the same next action the activation offers.
    assert {key: finished[key] for key in mod.NEXT_ACTION_KEYS} == {key: out[key] for key in mod.NEXT_ACTION_KEYS}


def test_a_pass_with_drift_verdict_spelled_as_the_record_does_is_the_same_halt(chain):
    _halt_forge_auto_at_ts(chain, "PASS_WITH_DRIFT")
    assert chain.resume()["repair"] == "retest-at-pinned-commit"


def test_an_error_halt_offers_a_resume_at_the_halted_step(chain):
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    chain.ran("BS")
    chain.halt("CS", "helper-missing")
    out = chain.resume()
    assert (out["offer"], out["kind"], out["repair"]) == ("resume", "error", None)
    assert out["resume_at"] == {"index": 2, "code": "CS"}
    assert out["route"] == "resume at CS: CS TS EX at the recorded threshold of 90"


@pytest.mark.parametrize(("invocation", "halted", "reason"), [
    pytest.param(FORGE_AUTO, "AN", "no-skillable-units", id="an-no-units"),
    pytest.param(FORGE_AUTO, "AN", "redirect", id="an-redirect"),
    pytest.param("AS[cocoindex]", "AS", "CRITICAL", id="as-critical-last-step"),
])
def test_a_halt_with_nothing_to_resume_offers_nothing(chain, invocation, halted, reason):
    chain.start(invocation)
    chain.halt(halted, reason)
    out = chain.resume()
    assert (out["status"], out["why"]) == ("none", "nothing-to-resume")
    assert chain.reopen(code=1)["error"] == "nothing-to-resume"


def _later_run_id(run_id: str, seconds: int) -> str:
    stamp = datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ") + timedelta(seconds=seconds)
    return f"{stamp.strftime('%Y%m%dT%H%M%SZ')}-0000beef"


def test_a_later_chain_with_a_step_in_its_result_drops_the_offer(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    chain.finish()
    latest = chain.sidecar / "pipeline-result-latest.json"
    record = json.loads(_read(latest))
    record["run_id"] = _later_run_id(record["run_id"], 3600)
    latest.write_bytes(json.dumps(record).encode("utf-8"))
    out = chain.resume()
    assert (out["status"], out["why"]) == ("none", "later-pipeline")


def test_a_parse_halt_after_the_chain_keeps_the_offer(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    chain.finish()
    chain.clock.tick(3600)
    chain.cli("finish", "--result-dir", chain.sidecar, "--halt-reason", "unknown code TX")
    assert chain.resume()["offer"] == "repair"


def test_a_parse_halt_does_not_bring_back_an_offer_a_later_chain_dropped(chain):
    """A forge-auto halted at TS, a forge-quick then succeeded, and a parse
    halt replaced the latest record: the forge-quick per-run record still
    supersedes the forge-auto journal."""
    _halt_forge_auto_at_ts(chain, "FAIL")
    chain.finish()
    chain.clock.tick(3600)
    _succeed_forge_quick(chain)
    chain.finish()
    assert chain.resume()["why"] == "later-pipeline"
    chain.clock.tick(3600)
    chain.cli("finish", "--result-dir", chain.sidecar, "--halt-reason", "unknown code TX")
    out = chain.resume()
    assert (out["status"], out["why"]) == ("none", "later-pipeline")


def test_the_newest_journal_is_the_one_offered(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    older = chain.journal
    chain.clock.tick(3600)
    chain.start("forge-quick cognee")
    out = chain.resume()
    assert Path(out["journal"]) == chain.journal != older
    assert (out["offer"], out["resume_at"]["code"]) == ("resume", "QS")


def test_an_unreadable_newer_journal_is_named_in_warnings(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    broken = chain.run_root / "skf-forger-29991231T235959Z-00000000"
    broken.mkdir()
    (broken / "pipeline-journal.json").write_bytes(b"{not json")
    out = chain.resume()
    assert out["offer"] == "repair"
    assert out["warnings"] == [f"journal_unreadable: {(broken / 'pipeline-journal.json').as_posix()}"]


def _test_record(forge: Path, skill: str, version: str | None, **fields) -> None:
    folder = forge / skill / version if version else forge / skill
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skf-test-skill-result-latest.json").write_bytes(json.dumps(fields).encode("utf-8"))


@pytest.mark.parametrize(("version", "fields", "offered"), [
    pytest.param("1.0.0", {"runId": "20261001T121000Z-1a2b3c4d"}, False, id="run-id-after"),
    pytest.param(None, {"runId": "20261001T121000Z-1a2b3c4d"}, False, id="flat-layout-after"),
    pytest.param("1.0.0", {"timestamp": "2026-10-01T12:10:00Z"}, False, id="timestamp-without-run-id"),
    # The run id comes from the clock; a typed timestamp can be wrong.
    pytest.param("1.0.0", {"timestamp": "2026-10-01T12:10:00Z", "runId": "20261001T120330Z-1a2b3c4d"}, True,
                 id="run-id-wins"),
    pytest.param("1.0.0", {"runId": "20261001T120330Z-1a2b3c4d"}, True, id="the-chains-own-test"),
    pytest.param("1.0.0", {"summary": {"result": "PASS"}}, True, id="no-time"),
])
def test_a_test_after_the_journal_drops_the_offer(chain, version, fields, offered):
    _halt_forge_auto_at_ts(chain, "FAIL")  # the halt is recorded at 12:04:00
    _test_record(chain.forge, "hono", version, **fields)
    out = chain.resume()
    assert (out["status"] == "offer") is offered, out
    if not offered:
        assert out["why"] == "tested-after"


def _export_manifest(skills: Path, *, day: str, updated_at: str, v1: bool = False, others=()) -> None:
    skills.mkdir(parents=True, exist_ok=True)

    def entry(last_exported: str) -> dict:
        if v1:
            return {"active_version": "1.0.0", "versions": ["1.0.0"]}
        return {"active_version": "1.0.0",
                "versions": {"1.0.0": {"ides": [], "last_exported": last_exported, "status": "active"}}}

    exports = {"hono": entry(day), **{name: entry(when) for name, when in others}}
    manifest = {"schema_version": "1" if v1 else "2", "exports": exports, "updated_at": updated_at}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))


@pytest.mark.parametrize(("day", "updated_at", "v1", "others", "offered"), [
    pytest.param("2026-10-02", "2026-10-02T08:00:00+00:00", False, (), False, id="next-day"),
    pytest.param("2026-10-01", "2026-10-01T12:30:00+00:00", False, (), False, id="same-day-later-write"),
    pytest.param("2026-10-01", "2026-10-01T09:00:00+00:00", False, (), True, id="same-day-earlier-write"),
    pytest.param("2026-09-15", "2026-10-01T12:30:00+00:00", False, (), True, id="an-earlier-export"),
    pytest.param("", "2026-10-01T12:30:00+00:00", True, (), False, id="v1-manifest-later"),
    # The manifest dates an export by its day only, and any skill's export
    # moves its updated_at: the contracts document this limit.
    pytest.param("2026-10-01", "2026-10-01T12:30:00+00:00", False, (("cognee", "2026-10-01"),), False,
                 id="same-day-another-skills-export-counts-too"),
])
def test_an_export_after_the_journal_drops_the_offer(chain, day, updated_at, v1, others, offered):
    _halt_forge_auto_at_ts(chain, "FAIL")
    _export_manifest(chain.skills, day=day, updated_at=updated_at, v1=v1, others=others)
    out = chain.resume()
    assert (out["status"] == "offer") is offered, out
    if not offered:
        assert out["why"] == "exported-after"


def test_a_skill_no_step_handed_on_comes_from_the_alias_argument(chain):
    """maintain names its skill as an argument: a halt at AS, before any
    step handed a skill_name on, still knows which skill was tested since."""
    chain.start("maintain cocoindex")
    chain.halt("AS", "helper-missing")
    out = chain.resume()
    assert (out["offer"], out["skill_name"]) == ("resume", "cocoindex")
    _test_record(chain.forge, "cocoindex", "0.4.0", runId="20261001T121000Z-1a2b3c4d")
    assert chain.resume()["why"] == "tested-after"


def test_a_repair_takes_a_bracket_skill_name_when_no_step_handed_one_on(chain):
    chain.start("TS[cocoindex] EX")
    chain.halt("TS", "FAIL")
    out = chain.reopen()
    assert [(r["code"], r["target"], r["flags"]) for r in out["run"]] == [
        ("US", "cocoindex", ["--from-test-report"]), ("TS", "cocoindex", []), ("EX", None, [])]


def test_a_quick_skill_names_its_skill_by_the_value_it_hands_on(chain):
    """QS takes a package or a URL: the skill is the name it hands on."""
    chain.start("forge-quick cognee")
    chain.ran("QS", "--set", "skill_name=cognee-sdk")
    chain.halt("TS", "FAIL")
    out = chain.resume()
    assert out["skill_name"] == "cognee-sdk"
    assert out["route"] == "US cognee-sdk --from-test-report, then TS EX"


def test_resume_reads_no_later_activity_without_the_folders(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    _test_record(chain.forge, "hono", "1.0.0", runId="20261001T121000Z-1a2b3c4d")
    out = chain.cli("resume", "--run-root", chain.run_root, "--result-dir", chain.sidecar)
    assert out["status"] == "offer"


# --------------------------------------------------------------------------
# reopen and discard: the accepted or the dropped offer
# --------------------------------------------------------------------------


def test_a_repaired_fail_updates_then_tests_at_the_recorded_threshold(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    chain.finish()
    out = chain.reopen()
    assert (out["status"], out["offer"], out["repair"], out["alias"], out["skill_name"]) == (
        "ok", "repair", "update-from-test-report", "forge-auto", "hono")
    assert [(r["index"], r["code"], r["target"], r["flags"], r["min"]) for r in out["run"]] == [
        (3, "US", "hono", ["--from-test-report"], None), (4, "TS", None, [], 90), (5, "EX", None, [], None)]
    journal = chain.data()
    assert journal["status"] == "running"
    assert journal["history"] == [{"code": "TS", "reason": "FAIL", "repair": "update-from-test-report",
                                   "at": "2026-10-01T12:06:00Z"}]
    chain.ran("US")
    chain.ran("TS")
    chain.step("EX")
    assert chain.finish()["pipeline_status"] == "success"
    assert not chain.journal.parent.exists()
    assert chain.resume()["status"] == "none"


def test_a_reviewed_critical_audit_picks_the_chain_up_after_it(chain):
    """US runs first and no step of this run hands it the skill: it takes
    the journal's skill as its target."""
    chain.start("maintain cocoindex")
    chain.halt("AS", "CRITICAL")
    out = chain.reopen()
    assert [(r["code"], r["target"]) for r in out["run"]] == [("US", "cocoindex"), ("TS", None), ("EX", None)]
    assert (out["args"], out["skill_name"]) == ({"skill_name": "cocoindex"}, "cocoindex")
    assert chain.data()["steps"][0] == {**mod._step_entry("AS"), "status": "completed", "reason": "CRITICAL"}


def test_the_first_step_to_run_takes_the_skill(chain):
    chain.start("forge-quick cognee")
    chain.ran("QS")
    chain.halt("TS", "no-result")
    out = chain.reopen()
    assert [(r["code"], r["target"]) for r in out["run"]] == [("TS", "cognee"), ("EX", None)]


def test_an_interrupted_chain_runs_from_its_first_pending_step(chain):
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    chain.ran("BS")
    out = chain.reopen()
    assert [(r["code"], r["target"]) for r in out["run"]] == [("CS", None), ("TS", None), ("EX", None)]
    assert chain.data()["history"] == []


def test_an_error_halt_reruns_the_step(chain):
    chain.start("forge-quick cognee")
    chain.halt("QS", "target-inaccessible")
    out = chain.reopen()
    assert out["run"][0] == {"index": 0, **mod._step_entry("QS")}
    assert out["args"] == {"target": "cognee"}
    assert chain.data()["history"][0]["repair"] is None


def test_discard_drops_a_stopped_chain(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    out = chain.cli("discard", "--journal", chain.journal)
    assert (out["status"], out["deleted"], Path(out["run_dir"])) == ("ok", True, chain.journal.parent)
    assert not chain.journal.parent.exists()
    assert chain.resume()["why"] == "no-journal"


def test_discard_removes_a_journal_that_no_longer_loads(chain):
    chain.start("QS TS EX")
    chain.journal.write_bytes(b"{not json")
    assert chain.cli("discard", "--journal", chain.journal)["deleted"] is True
    assert not chain.journal.parent.exists()


def test_discard_leaves_any_other_folder_alone(chain, tmp_path):
    chain.start("QS TS EX")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    moved = elsewhere / "pipeline-journal.json"
    moved.write_bytes(chain.journal.read_bytes())
    out = chain.cli("discard", "--journal", moved, code=1)
    assert out["error"] == "not-deleted"
    assert moved.is_file()


# --------------------------------------------------------------------------
# The script matches the contracts it keeps
# --------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^#{{2,3}} |\Z)", text, re.M | re.S)
    assert m, f"section {heading!r} not found"
    return m.group(1)


def _table(section: str) -> list[list[str]]:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("| ")]
    return [r for r in rows[1:] if not set("".join(r)) <= set("-: ")]


def test_every_quality_reason_is_one_a_halt_gives():
    gate = _read(GATE)
    gate_mod = _load("skf_pipeline_gate", GATE)
    ts = {v.lower() for v in gate_mod.TS_VERDICTS.values()} | {"workspace-drift"}
    for code, reason in mod.REPAIRS:
        if code == "TS":
            assert reason in ts, reason
        elif code == "AS":
            assert reason.upper() in gate_mod.AS_SEVERITIES
        else:
            assert f'"{reason}"' in gate, (code, reason)
    assert "workspace-drift" in json.loads(_read(TEST_SKILL_SCHEMA))["properties"]["halt_reason"]["enum"]


def test_the_gated_codes_and_decisions_are_the_gates():
    gate_mod = _load("skf_pipeline_gate", GATE)
    assert mod.GATED == set(gate_mod.GATED_CODES)
    for decision in mod.DECISIONS:
        assert f'"{decision}"' in _read(GATE), decision


def test_the_repair_routes_table_is_the_scripts():
    rows = _table(_section(_read(CONTRACTS), "### Repair Routes"))
    table, actions = {}, {}
    for code, reasons, repair, user_action, pickup in rows:
        where = None if pickup == "no resume" else "next" if pickup.startswith("the step after") else "same"
        if where == "same":
            assert pickup.startswith(code), pickup
        repair = repair.strip("`")
        for reason in re.findall(r"`([^`]+)`", reasons):
            table[(code, reason.lower().replace("_", "-"))] = (repair, where)
        actions[repair] = None if user_action.startswith("none:") else user_action.replace("`", "")
    assert table == mod.REPAIRS
    assert actions == mod.USER_ACTIONS
    fail = next(r for r in rows if r[1] == "`FAIL`")
    assert "`US <skill> --from-test-report`" in fail[3]
    assert mod.REPAIR_STEPS == {"update-from-test-report": ("US", ("--from-test-report",))}


def test_the_handoffs_are_data_flow_values_step_4e_names():
    rows = _table(_section(_read(CONTRACTS), "## Data Flow"))
    record = _read(PIPELINE_MODE).split("   - e. **Record the step**", 1)[1].split("   - f. **", 1)[0]
    rule = next(sentence for sentence in record.split(". ") if "hands on" in sentence)
    for code, name in mod.HANDOFFS.items():
        assert any(row[0] == code for row in rows), code
        assert re.search(rf"\b{code}\b", rule) and f"`{name}=<" in rule, (code, name)


def test_the_pipeline_state_table_names_every_journal_field(chain):
    chain.start("QS TS EX")
    rows = _table(_section(_read(CONTRACTS), "## Pipeline State"))
    fields = [name for row in rows for name in re.findall(r"`([a-z_]+)`", row[0])]
    assert fields == list(chain.data())


def test_the_step_shape_is_the_one_the_contracts_show():
    state = _section(_read(CONTRACTS), "## Pipeline State")
    example = json.loads(re.search(r"```json\n(.+?)\n```", state, re.S).group(1))
    assert list(example) == list(mod._step_entry("TS")) == STEP_KEYS
    for status in mod.STEP_STATUSES:
        assert f"`{status}`" in state, status


def test_the_pipeline_result_example_has_the_shape_finish_writes(chain):
    chain.start("QS TS EX")
    chain.halt("QS", "target-inaccessible")
    chain.finish()
    written = _latest(chain)
    section = _section(_read(CONTRACTS), "## Pipeline Result")
    example = json.loads(re.search(r"```json\n(.+?)\n```", section, re.S).group(1))
    assert list(example) == list(written) == _schema_keys()
    assert list(example["summary"]) == list(written["summary"])
    assert all(list(s) == STEP_KEYS for s in example["summary"]["steps"])
    for status in ("success", "partial", "failed"):
        assert f"`{status}`" in section, status


def test_the_run_id_and_the_record_names_are_the_shared_helpers(tmp_path):
    """pipeline-journal.py loads no shared script and keeps its own copy of
    skf-run-lock.py's run id and the emitter's per-run record name."""
    lock = _load("skf_run_lock", SRC / "shared" / "scripts" / "skf-run-lock.py")
    emitter = _load("skf_emit_result_envelope", SRC / "shared" / "scripts" / "skf-emit-result-envelope.py")
    assert mod._RUN_ID_RE.pattern == lock.RUN_ID_RE.pattern
    assert mod.new_run_id(T0)[:17] == lock.new_run_id(T0)[:17] == "20261001T120000Z-"
    _, stamp = emitter._stamps(int(T0.timestamp()))
    assert stamp == T0.strftime(mod.FILE_STAMP_FORMAT) == mod._file_stamp(mod.new_run_id(T0))
    ours, theirs = tmp_path / "ours", tmp_path / "theirs"
    ours.mkdir()
    theirs.mkdir()
    names = [(mod._claim_result_path(ours, stamp).name,
              emitter._claim_result_path(theirs, mod.RESULT_STEM, stamp).name) for _ in range(3)]
    assert [a for a, _ in names] == [b for _, b in names] == [
        "pipeline-result-20261001-120000.json", "pipeline-result-20261001-120000-2.json",
        "pipeline-result-20261001-120000-3.json"]


# --------------------------------------------------------------------------
# The prose calls run as written
# --------------------------------------------------------------------------


def _run(*argv: str, stdin: str = "", rc: int = 0) -> dict:
    p = subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    assert p.returncode == rc, p.stdout + p.stderr
    return json.loads(p.stdout)


def _argv(call: str, values: dict[str, str]) -> list[str]:
    """A documented call's words after the script, placeholders filled in."""
    words = shlex.split(call)
    assert words[:3] == ["uv", "run", "scripts/pipeline-journal.py"], words
    out = []
    for word in words[3:]:
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        assert not re.search(r"[{<][a-z_ |-]+[}>]", word), word
        out.append(word)
    return out


def _required(call: str) -> str:
    return re.sub(r"\s*\[--[^\]]+\]", "", call)


def _every_option(call: str) -> str:
    return re.sub(r"\[(--[^\]]+)\]", r"\1", call)


def _step_4_of_activation() -> str:
    text = _read(FORGER_SKILL)
    return text[text.index("4. **Read the pipeline journal**"):text.index("5. **Greet, then dispatch or wait.**")]


def _pipeline_mode_calls() -> dict[str, str]:
    """pipeline-mode.md's documented journal calls, by name."""
    text = _read(PIPELINE_MODE)
    calls = {}
    for name, pattern in (("start", r"start .+?"), ("gate", r"step .+?--gate.*?")):
        m = re.search(rf"```bash\n\s*(uv run scripts/pipeline-journal\.py {pattern}) <<'(\w+)'\n\s*(<[^>\n]+>)\n\s*\2\n",
                      text)
        assert m, f"pipeline-mode.md shows no {name} call over a quoted heredoc"
        calls[name], calls[f"{name}-stdin"] = m.group(1), m.group(3)
    [calls["status"]] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py step .+--status .+)$", text, re.M)
    [calls["finish"]] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py finish --journal .+)$", text, re.M)
    [calls["reopen"]] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py reopen .+)$", text, re.M)
    [calls["parse-halt"]] = re.findall(r"`(uv run scripts/pipeline-journal\.py finish --result-dir [^`]+)`", text)
    return calls


def test_the_activation_call_runs_as_written(tmp_path):
    [call] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py resume .+)$", _step_4_of_activation(), re.M)
    values = {"{project-root}": str(tmp_path), "{sidecar_path}": str(tmp_path / "sidecar"),
              "{forge_data_folder}": str(tmp_path / "forge-data"), "{skills_output_folder}": str(tmp_path / "skills")}
    run_root = tmp_path / "_bmad-output" / ".skf-run"
    assert _run(*_argv(call, values))["status"] == "none"
    _run("start", "--run-root", str(run_root), stdin="QS TS EX\n")
    out = _run(*_argv(call, values))
    assert (out["status"], out["offer"], out["resume_at"]["code"]) == ("offer", "resume", "QS")


def test_the_pipeline_mode_calls_run_as_written(tmp_path):
    calls = _pipeline_mode_calls()
    assert (calls["start-stdin"], calls["gate-stdin"]) == ("<the whole invocation>", "<the JSON the gate printed>")
    values = {"{project-root}": str(tmp_path), "{sidecar_path}": str(tmp_path / "sidecar")}
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    values["<journal>"] = started["journal"]
    assert Path(started["run_dir"]).parent == tmp_path / "_bmad-output" / ".skf-run"
    # AS: the gate skipped US, required arguments only.
    out = _run(*_argv(_required(calls["gate"]), {**values, "<code>": "AS"}), stdin=gate_json("AS", "skip", "CLEAN", "US"))
    assert (out["skipped"]["code"], out["next"]["code"]) == ("US", "TS")
    # TS: the gate halted, every option given.
    options = {"<name>=<value>": "skill_name=cocoindex", "<path>": "/fd/r.json"}
    out = _run(*_argv(_every_option(calls["gate"]), {**values, **options, "<code>": "TS"}),
               stdin=gate_json("TS", "halt", "FAIL"))
    assert (out["recorded"]["reason"], out["next"]) == ("FAIL", None)
    finished = _run(*_argv(_required(calls["finish"]), values))
    assert (finished["run_dir_kept"], finished["route"]) == (True, "US cocoindex --from-test-report, then TS EX")
    assert [r["code"] for r in _run(*_argv(calls["reopen"], values))["run"]] == ["US", "TS", "EX"]
    # US, TS and EX run the repaired chain to its end.
    status = {**values, **options, "<reason>": "unused when completed"}
    out = _run(*_argv(_every_option(calls["status"]), {**status, "<code>": "US", "<completed|halted>": "completed"}))
    assert out["next"]["code"] == "TS"
    _run(*_argv(_required(calls["gate"]), {**values, "<code>": "TS"}), stdin=gate_json("TS"))
    out = _run(*_argv(_required(calls["status"]), {**values, "<code>": "EX", "<completed|halted>": "completed"}))
    assert out["next"] is None
    assert _run(*_argv(_required(calls["finish"]), values))["pipeline_status"] == "success"
    out = _run(*_argv(calls["parse-halt"], {**values, "<the halt reason>": "unknown code TX"}))
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", "unknown code TX")


def test_a_failed_step_call_still_leaves_this_runs_result(tmp_path):
    """A step call that fails stops the chain, and step 5's call, given the
    failure as the halt reason, writes this run's result: the latest record
    is never the previous run's."""
    calls = _pipeline_mode_calls()
    values = {"{project-root}": str(tmp_path), "{sidecar_path}": str(tmp_path / "sidecar")}
    (tmp_path / "sidecar").mkdir()
    earlier = {"skill": "skf-forger", "status": "success", "run_id": "20260930T080000Z-0000beef",
               "summary": {"status": "success", "steps": [{"code": "QS"}]}}
    (tmp_path / "sidecar" / "pipeline-result-latest.json").write_bytes(json.dumps(earlier).encode("utf-8"))
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    values["<journal>"] = started["journal"]
    _run(*_argv(_required(calls["gate"]), {**values, "<code>": "AS"}), stdin=gate_json("AS", "continue"))
    failed = _run(*_argv(_required(calls["gate"]), {**values, "<code>": "TS"}), stdin=gate_json("TS"), rc=1)
    assert (failed["error"], failed["retry"]) == ("out-of-order", False)
    finish = _every_option(calls["finish"])
    reason = failed["message"].replace("'", "`")  # as pipeline-mode.md quotes a reason
    out = _run(*_argv(finish, {**values, "<reason>": reason}))
    assert (out["pipeline_status"], out["halt_reason"]) == ("partial", reason)
    latest = json.loads(_read(tmp_path / "sidecar" / "pipeline-result-latest.json"))
    assert latest["run_id"] == started["run_id"]
    assert [(s["code"], s["status"]) for s in latest["summary"]["steps"]] == [
        ("AS", "completed"), ("US", "halted"), ("TS", "pending"), ("EX", "pending")]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="runs the documented call through bash")
def test_a_reason_with_shell_characters_survives_the_documented_quoting(tmp_path):
    text = _read(PIPELINE_MODE)
    assert "goes in single quotes, with each `'` in it replaced by a backtick" in text
    started = _run("start", "--run-root", str(tmp_path / "runs"), stdin="QS TS EX\n")
    reason = "the run folder could not be created: can't write `$HOME/x` $(touch pwned)".replace("'", "`")
    command = _pipeline_mode_calls()["status"].replace(
        "uv run scripts/pipeline-journal.py", f"{shlex.quote(sys.executable)} {shlex.quote(str(SCRIPT))}", 1)
    command = re.sub(r"\s*\[--(set|output) [^\]]+\]", "", command).replace("[--reason '<reason>']", "--reason '<reason>'")
    for placeholder, value in {"<journal>": started["journal"], "<code>": "QS", "<completed|halted>": "halted",
                               "<reason>": reason}.items():
        command = command.replace(placeholder, value)
    p = subprocess.run(["bash", "-c", command], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["recorded"]["reason"] == reason
    assert not (tmp_path / "pwned").exists()


def test_the_discard_call_runs_as_written(tmp_path):
    [call] = re.findall(r"`(uv run scripts/pipeline-journal\.py discard [^`]+)`", _read(FORGER_SKILL))
    started = _run("start", "--run-root", str(tmp_path / "runs"), stdin="QS TS EX\n")
    out = _run(*_argv(call, {"<journal>": started["journal"]}))
    assert out["deleted"] is True and not Path(started["run_dir"]).exists()


# --------------------------------------------------------------------------
# What the prose says about the journal, the offers and the dispatch
# --------------------------------------------------------------------------


def test_activation_presents_the_route_the_script_prints():
    step = _step_4_of_activation()
    assert "re-enters Pipeline Mode with the pending codes" not in _read(FORGER_SKILL)
    for token in ("`status` `offer`", "`halted_on`", "`route`", "Resume procedure", "`warnings`"):
        assert token in step, token
    # The script prints the route: the greeting reads no second file for it.
    assert "pipeline-contracts.md" not in step


def test_ws_gives_one_next_action_per_skill():
    ws = _read(FORGER_SKILL).split("- **WS**:", 1)[1].split("## Pipeline Mode", 1)[0]
    assert "`pipeline-journal.py resume` call, run again" in ws
    assert "one next action per skill" in ws
    assert "the resume offer first" not in ws
    assert "gets that offer's `route` instead" in ws


def test_a_pick_at_invocation_runs_and_only_the_headless_flag_halts_without_one():
    """A start headless only through preferences.yaml greets and ends at the
    menu as before: the menu is a choice point, not a gate."""
    greeting = _read(FORGER_SKILL).split("5. **Greet, then dispatch or wait.**", 1)[1].split("\n", 1)[0]
    assert "dispatch the pick at once" in greeting
    halt = greeting.split("When the invocation carries `--headless` or `-H` and no pick, HARD HALT", 1)[1]
    halt = halt.split("Otherwise", 1)[0]
    assert "`/skf-forger forge-auto <repo-url> --headless`" in halt
    assert "preferences.yaml" not in halt
    assert "HARD HALT naming both forms when the invocation carries `--headless` or `-H`" in greeting
    assert "When `{headless_mode}` is true" not in greeting
    assert "`@Ferris TS cocoindex`" in _section(_read(FORGER_SKILL), "## Overview")


def test_step_5_and_the_overview_say_a_pick_dispatches():
    text = _read(FORGER_SKILL)
    assert "5. **Greet, then dispatch or wait.**" in text
    assert "otherwise Ferris greets and waits for a pick" in _section(text, "## Overview")


def test_the_persona_rule_is_stated_once():
    text = _read(FORGER_SKILL)
    assert text.count("Maintain this persona across all skill invocations") == 1
    assert "applying your persona" not in text and "holding one persona" not in text


def test_pipeline_mode_leaves_the_contracts_to_the_contracts_file():
    text = _read(PIPELINE_MODE)
    for gone in ("This file covers the run procedure", "It tokenizes", "**`AN` with `CS`:**",
                 "**`TS` followed by `EX`:**", "{YYYYMMDD-HHmmss}", "UTC timestamp", "in a second call",
                 "the Repair Routes entry", "For a repair only the user can make"):
        assert gone not in text, gone
    assert "tracks pipeline state in memory" not in _read(CONTRACTS)
    assert "Only the alias names need recognizing here" not in _read(FORGER_SKILL)
