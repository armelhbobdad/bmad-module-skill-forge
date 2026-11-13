#!/usr/bin/env python3
"""Tests for src/skf-forger/scripts/pipeline-journal.py.

The forger keeps each chain's state in a journal on disk (#587), so a
killed session or a compacted context loses nothing:
  - start parses the invocation with parse-pipeline.py and records the plan
    with its bracket values, the alias and the first workflow's args
  - step records each step in plan order: a gated step takes the decision
    the gate printed (a skip also records the step it passes over), any
    other step its status; a halt needs its reason, and a completed step
    the value it hands the next; an AS that found upstream moved hands US the
    new ref through the gate's `handoff`, with no --set
  - a skip of several codes (#1170) is matched to the steps from the one
    right after the gated step, in its order, each code once, so the first
    step that is not its next code, or works on another skill than the
    gated step's, ends the pass, and `skipped` lists the steps it passed
    over; AS's
    gate gets the folders `step` is given and the journal's skill, so
    `maintain` on a current skill, run through the documented calls, passes
    over US, TS and EX and finishes `success`; `SF <alias>` hands the
    alias's arguments to the workflow after SF
  - step --envelope records a step from the envelope line its workflow
    printed (#1168): the gate's rules for AN, TS, AS and VS, run in process,
    and the envelope's `status` for every other code (CS `partial` and EX
    `dry-run` halt), with the value the step hands on and its output paths;
    SS and RA hand theirs on too, and a reason goes on stdin
  - finish writes pipeline-result-<UTC>.json and its -latest copy in
    output-contract-schema.md's shape, with one fixed per-step shape
    (#593), prints the next action the stop leaves, deletes only the
    journal's own run folder when nothing is left to resume, and records
    the stop even when the journal cannot be saved or read
  - resume: a chain killed after its second workflow offers to resume at the
    third with the original alias, brackets and args; a quality halt offers
    its repair route, keyed on the gate's reason; no offer once a later
    chain recorded a result (behind a parse halt's record too), or the skill
    was tested or exported since; an offer names the journal's `started_at`
    and `updated_at` (#1169), and a headless `resume` that halts (no offer,
    an offer the user acts on first, or a `reopen` that fails) writes a
    record with no step, which leaves the offer
  - reopen applies the offer: US --from-test-report joins the plan before a
    failed TS, an AS CRITICAL review picks the chain up after AS with the
    skill as US's target; discard drops a stopped chain
  - the calls SKILL.md and pipeline-mode.md document run as written, a
    reason with shell characters in a heredoc included, and the contract
    tables in pipeline-contracts.md match the script
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
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "skf-forger" / "scripts" / "pipeline-journal.py"
GATE = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"
CONTRACTS = SRC / "shared" / "references" / "pipeline-contracts.md"
OUTPUT_CONTRACT = SRC / "shared" / "references" / "output-contract-schema.md"
SCHEMAS = SRC / "shared" / "scripts" / "schemas"
# test-skill's halt reasons live in its envelope schema (#593, #600).
TEST_SKILL_SCHEMA = SCHEMAS / "skf-test-result-envelope.v1.json"
# Each code's envelope schema, by its file stem's middle (skf-<stem>-result-envelope.v1.json).
SCHEMA_STEMS = {"SF": "setup", "AN": "analyze", "BS": "brief", "CS": "create-skill", "QS": "quick-skill",
                "SS": "stack", "US": "update", "AS": "audit", "VS": "verify-stack", "RA": "refine-architecture",
                "TS": "test", "EX": "export", "RS": "rename-skill", "DS": "drop-skill"}


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
           "CS": "skill_name=hono", "QS": "skill_name=cognee", "US": "skill_name=hono",
           "SS": "skill_name=acme-stack", "RA": "architecture_doc_path=/out/refined-architecture-acme.md"}


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

    def envelope(self, code: str, line: str, *extra, rc: int = 0) -> dict:
        """A step recorded from the envelope line its workflow printed, on stdin: --envelope."""
        self.clock.tick()
        return self.cli("step", "--journal", self.journal, "--code", code, "--envelope", *extra, stdin=line, code=rc)

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
    assert out["skipped"] == []
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
    assert [(s["index"], s["code"], s["status"], s["reason"]) for s in out["skipped"]] == [
        (1, "US", "skipped", "CLEAN")]
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


@pytest.mark.parametrize(("invocation", "skipped", "following"), [
    ("AS[cocoindex] US TS EX", ["US", "TS", "EX"], None),
    ("AS[cocoindex] US TS", ["US", "TS"], None),
    ("AS[cocoindex] US SS", ["US"], ("SS", None)),
    ("AS[cocoindex] US TS EX TS[other] EX[other]", ["US", "TS", "EX"], ("TS", "other")),
    ("AS[cocoindex] US TS[other] EX[other]", ["US"], ("TS", "other")),
    ("AS[cocoindex] US TS[cocoindex] EX", ["US", "TS", "EX"], None),
    ("AS[cocoindex] US[other] TS EX", [], ("US", "other")),
    ("AS[cocoindex] US EX TS", ["US"], ("EX", None)),
    ("AS[cocoindex] US US TS EX", ["US"], ("US", None)),
    ("maintain cocoindex", ["US", "TS", "EX"], None),
])
def test_a_skip_of_several_codes_passes_over_each_step_it_names_in_its_order(chain, invocation, skipped, following):
    """#1170: a current skill's CLEAN audit skips `US TS EX`: from the step after the audit, each step is matched to
    the skip's next code, each code once, while it works on the audited skill (an empty bracket, or that skill's
    name), and the first that is not ends the pass, so another skill's US, TS and EX, or steps out of that order,
    run."""
    chain.start(invocation)
    out = chain.gate("AS", "skip", reason="current", skip="US TS EX")
    assert [(s["index"], s["code"], s["status"], s["reason"]) for s in out["skipped"]] == [
        (i + 1, code, "skipped", "current") for i, code in enumerate(skipped)]
    assert (None if out["next"] is None else (out["next"]["code"], out["next"]["target"])) == following
    steps = chain.data()["steps"]
    assert [s["status"] for s in steps] == ["completed", *["skipped"] * len(skipped),
                                            *["pending"] * (len(steps) - 1 - len(skipped))]
    if following is None:
        assert chain.finish()["pipeline_status"] == "success"


@pytest.mark.parametrize("skip", ["US", "US TS EX"])
def test_a_skip_passes_over_no_step_of_another_skill(chain, skip):
    """#1170: after `AS[x]`, a CLEAN skip (`US`) or a current one (`US TS EX`) records nothing skipped when the step
    after the audit works on another skill, whose update then runs."""
    reason = "CLEAN" if skip == "US" else "current"
    chain.start("AS[cocoindex] US[other] TS EX")
    out = chain.gate("AS", "skip", reason=reason, skip=skip)
    assert (out["recorded"]["status"], out["skipped"]) == ("completed", [])
    assert (out["next"]["code"], out["next"]["target"]) == ("US", "other")
    assert [s["status"] for s in chain.data()["steps"]] == ["completed", "pending", "pending", "pending"]


def test_a_skip_of_several_codes_must_start_at_the_step_after_the_gated_one(chain):
    """`US TS EX` after `AS[x] TS EX` records nothing; after `AS[x] US TS EX` it records the three."""
    chain.start("AS[cocoindex] TS EX")
    out = chain.gate("AS", "skip", reason="current", skip="US TS EX", rc=1)
    assert (out["error"], out["retry"]) == ("skip-mismatch", False)
    assert out["message"] == "The gate passes over US TS EX, but the step after AS is TS."
    assert [s["status"] for s in chain.data()["steps"]] == ["pending"] * 3
    assert chain.data()["updated_at"] == chain.data()["started_at"]
    chain.start("AS[cocoindex] US TS EX")
    out = chain.gate("AS", "skip", reason="current", skip="US TS EX")
    assert [s["code"] for s in out["skipped"]] == ["US", "TS", "EX"]


def test_sf_before_an_alias_gives_the_alias_arguments_to_the_workflow_after_sf(chain):
    """#1170: a first run's `SF forge-auto <url>` runs SF, then AN with the URL and its auto mode."""
    out = chain.start(f"SF forge-auto {HONO}")
    assert (out["alias"], out["args"]) == ("forge-auto", {"project_path": HONO})
    assert [s["code"] for s in out["steps"]] == ["SF", "AN", "BS", "CS", "TS", "EX"]
    assert (out["next"]["code"], out["next"]["inputs"]) == ("SF", {})
    out = chain.step("SF")
    assert (out["next"]["code"], out["next"]["inputs"]) == ("AN", {"project_path": HONO, "auto": True})
    assert [s["min"] for s in chain.data()["steps"]] == [None, None, None, None, 90, None]


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
    pytest.param("SS TS EX", "SS", "skill_name", id="ss"),
    pytest.param("RA[docs/arch.md] SS", "RA", "architecture_doc_path", id="ra"),
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


def _as_gate_json(severity: str, **fields) -> str:
    """What pipeline-gate.py itself prints for an AS envelope before a US."""
    gate_mod = _load("skf_pipeline_gate", GATE)
    envelope = {"status": "success", "skill_name": "cocoindex", "drift_score": severity,
                "report_path": "/fd/cocoindex/drift-report.md", "next_workflow": "update-skill", "exit_code": 0,
                "halt_reason": None, **fields}
    text = f"{gate_mod.ENVELOPES['AS']}: {json.dumps(envelope)}"
    return json.dumps(gate_mod.gate("AS", text, next_code="US"), indent=2)


def _gate_as(chain: Chain, stdin: str, *extra) -> dict:
    chain.clock.tick()
    return chain.cli("step", "--journal", chain.journal, "--code", "AS", "--gate", *extra, stdin=stdin)


def test_the_gate_hands_an_audits_new_ref_to_the_update(chain):
    """determinism-1: `maintain` after an upstream release. The gate's handoff,
    not a --set typed by hand, puts `target_ref` in the journal's data, which
    step 4b passes to US as --target-ref."""
    chain.start("maintain cocoindex")
    out = _gate_as(chain, _as_gate_json("CLEAN", upstream_moved=True, upstream_ref="v1.3.0"))
    assert (out["recorded"]["status"], out["next"]["code"]) == ("completed", "US")
    assert out["data"] == {"target_ref": "v1.3.0"}
    assert chain.data()["data"] == {"target_ref": "v1.3.0"}


def test_a_critical_audit_keeps_the_new_ref_for_the_repaired_update(chain):
    """The review-drift-report repair picks the chain up at US, which still needs the ref."""
    chain.start("maintain cocoindex")
    out = _gate_as(chain, _as_gate_json("CRITICAL", upstream_moved=True, upstream_ref="v1.3.0"))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "CRITICAL")
    assert out["data"] == {"target_ref": "v1.3.0"}
    reopened = chain.reopen()
    assert reopened["run"][0]["code"] == "US" and reopened["data"] == {"target_ref": "v1.3.0"}
    assert reopened["next"]["inputs"] == {"target": "cocoindex", "target_ref": "v1.3.0"}


def test_an_audit_that_found_no_move_hands_on_no_ref(chain):
    chain.start("maintain cocoindex")
    out = _gate_as(chain, _as_gate_json("MINOR", upstream_moved=False, upstream_ref=None))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {})


def test_the_gates_ref_wins_over_one_typed_with_set(chain):
    chain.start("maintain cocoindex")
    out = _gate_as(chain, _as_gate_json("CLEAN", upstream_moved=True, upstream_ref="v1.3.0"),
                   "--set", "target_ref=v1.2.0")
    assert out["data"] == {"target_ref": "v1.3.0"}


@pytest.mark.parametrize("handoff", [
    pytest.param("v1.3.0", id="not-an-object"),
    pytest.param(["target_ref"], id="a-list"),
    pytest.param({"Target_Ref": "v1.3.0"}, id="upper-case-name"),
    pytest.param({"target_ref": "  "}, id="blank-value"),
    pytest.param({"target_ref": 3}, id="not-a-string"),
])
def test_a_handoff_that_is_not_names_and_values_records_nothing(chain, handoff):
    chain.start("maintain cocoindex")
    gate = {"code": "AS", "decision": "continue", "reason": None, "skip": None, "message": "AS: continue",
            "handoff": handoff}
    out = _gate_as(chain, json.dumps(gate))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {})


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
# The entry to run next: its skill, description and inputs (#1167)
# --------------------------------------------------------------------------

PARSER = _load("skf_parse_pipeline_for_journal", SCRIPT.parent / "parse-pipeline.py")


def _named(code: str) -> dict:
    skill, description = PARSER.SKILLS[code]
    return {"skill": skill, "description": description}


def _kept_the_step_shape(chain: Chain) -> None:
    """Only the printed entries carry `skill`, `description` and `inputs`: the journal keeps its shape."""
    journal = chain.data()
    assert journal["journal_version"] == 1
    assert all(list(s) == STEP_KEYS for s in journal["steps"]), journal["steps"]


def test_start_prints_the_first_entry_with_its_inputs(chain):
    out = chain.start(FORGE_AUTO)
    assert out["next"] == {"index": 0, **mod._step_entry("AN", mode="auto"), **_named("AN"),
                           "inputs": {"project_path": HONO, "pin": "v4.6.0", "auto": True}}
    assert out["next"]["skill"] == "skf-analyze-source"
    assert [list(s) for s in out["steps"]] == [[*STEP_KEYS, "skill", "description"]] * 5
    assert [(s["code"], s["skill"], s["description"]) for s in out["steps"]] == [
        (code, *PARSER.SKILLS[code]) for code in ("AN", "BS", "CS", "TS", "EX")]
    _kept_the_step_shape(chain)


def test_each_step_hands_the_next_entry_its_inputs(chain):
    """forge-auto: BS takes AN's brief as `data` holds it, CS takes BS's one brief as its `brief_path`,
    and TS takes CS's skill with the recorded threshold."""
    chain.start(FORGE_AUTO)
    out = chain.gate("AN", "continue", "--set", "brief_path=/fd/hono/skill-brief.yaml")
    assert (out["next"]["code"], out["next"]["inputs"]) == (
        "BS", {"brief_path": "/fd/hono/skill-brief.yaml", "auto": True})
    out = chain.step("BS", "completed", "--set", "brief_path=/fd/hono/skill-brief.yaml")
    assert out["next"] == {"index": 2, **mod._step_entry("CS"), **_named("CS"),
                           "inputs": {"brief_path": "/fd/hono/skill-brief.yaml"}}
    out = chain.step("CS", "completed", "--set", "skill_name=hono")
    assert out["next"] == {
        "index": 3, "code": "TS", "min": 90, "mode": None, "target": None, "flags": [], "status": "pending",
        "reason": None, "skill": "skf-test-skill",
        "description": "Cognitive completeness verification: quality gate before export",
        "inputs": {"skill_name": "hono", "threshold": 90}}
    assert chain.ran("TS")["next"]["inputs"] == {"skill_name": "hono"}
    assert chain.step("EX")["next"] is None
    _kept_the_step_shape(chain)


def test_the_briefs_an_hands_straight_to_cs_go_as_one_batch(chain):
    """AN[<repo>] CS TS EX: the several briefs AN wrote reach CS as one `batch`."""
    chain.start(f"AN[{HONO}] CS TS EX")
    out = chain.gate("AN", "continue", "--set", "brief_path=/fd/core/skill-brief.yaml",
                     "--set", "brief_path=/fd/cli/skill-brief.yaml")
    assert out["next"] == {"index": 1, **mod._step_entry("CS"), **_named("CS"),
                           "inputs": {"batch": ["/fd/core/skill-brief.yaml", "/fd/cli/skill-brief.yaml"]}}
    _kept_the_step_shape(chain)


def test_a_brief_list_reaching_bs_passes_as_data_holds_it(chain):
    chain.start(FORGE_AUTO)
    out = chain.gate("AN", "continue", "--set", "brief_path=/fd/a.yaml", "--set", "brief_path=/fd/b.yaml")
    assert out["next"]["inputs"] == {"brief_path": ["/fd/a.yaml", "/fd/b.yaml"], "auto": True}


def test_us_after_an_audit_takes_the_skill_and_the_new_ref(chain):
    """maintain: no step of the run named the skill, so US takes the alias argument, and the gate's
    `target_ref` beside it."""
    chain.start("maintain cocoindex")
    assert chain.data()["args"] == {"skill_name": "cocoindex"}
    out = _gate_as(chain, _as_gate_json("CLEAN", upstream_moved=True, upstream_ref="v2.0.0"))
    assert (out["next"]["code"], out["next"]["skill"]) == ("US", "skf-update-skill")
    assert out["next"]["inputs"] == {"skill_name": "cocoindex", "target_ref": "v2.0.0"}
    _kept_the_step_shape(chain)


def test_a_repaired_fail_runs_the_update_with_its_flag(chain):
    _halt_forge_auto_at_ts(chain, "FAIL")
    out = chain.reopen()
    assert out["next"] == {"index": 3, **mod._step_entry("US", target="hono", flags=("--from-test-report",)),
                           **_named("US"), "inputs": {"target": "hono", "flags": ["--from-test-report"]}}
    assert [list(r) for r in out["run"]] == [["index", *STEP_KEYS, "skill", "description"]] * 3
    assert [(r["code"], r["skill"]) for r in out["run"]] == [
        ("US", "skf-update-skill"), ("TS", "skf-test-skill"), ("EX", "skf-export-skill")]
    _kept_the_step_shape(chain)


def test_a_bracket_target_is_the_first_entrys_input(chain):
    out = chain.start("QS[cocoindex] TS EX")
    assert (out["next"]["code"], out["next"]["inputs"]) == ("QS", {"target": "cocoindex"})
    assert chain.step("QS", "completed", "--set", "skill_name=cocoindex")["next"]["inputs"] == {
        "skill_name": "cocoindex"}


def test_ra_takes_the_document_vs_was_given(chain):
    out = chain.start("VS[docs/arch.md] RA")
    assert out["next"]["inputs"] == {"target": "docs/arch.md"}
    out = chain.gate("VS", "continue")
    assert (out["next"]["code"], out["next"]["skill"]) == ("RA", "skf-refine-architecture")
    assert out["next"]["inputs"] == {"architecture_doc_path": "docs/arch.md"}


def test_a_leading_sf_leaves_the_args_to_the_first_workflow(chain):
    out = chain.start("SF QS[x] TS EX --pin 1.2")
    assert (out["next"]["code"], out["next"]["skill"], out["next"]["inputs"]) == ("SF", "skf-setup", {})
    out = chain.step("SF")
    assert (out["next"]["code"], out["next"]["inputs"]) == ("QS", {"target": "x", "pin": "1.2"})


def test_a_halt_prints_no_next_entry(chain):
    chain.start("forge-quick cognee")
    out = chain.halt("QS", "target-inaccessible")
    assert out["next"] is None
    reopened = chain.reopen()
    assert reopened["next"]["inputs"] == {"target": "cognee"}  # the first workflow takes the alias argument


def test_a_step_saved_before_the_parser_went_missing_is_kept(chain, monkeypatch, tmp_path):
    chain.start("QS TS EX")
    monkeypatch.setattr(mod, "PARSER", tmp_path / "parse-pipeline.py")
    out = chain.step("QS", "completed", "--set", "skill_name=cognee", rc=1)
    assert (out["status"], out["error"], out["retry"]) == ("error", "parser-missing", False)
    journal = chain.data()
    assert journal["steps"][0]["status"] == "completed" and journal["data"] == {"skill_name": "cognee"}
    _kept_the_step_shape(chain)


def test_a_reopen_with_no_parser_changes_nothing(chain, monkeypatch, tmp_path):
    _halt_forge_auto_at_ts(chain, "FAIL")
    before = chain.journal.read_bytes()
    monkeypatch.setattr(mod, "PARSER", tmp_path / "parse-pipeline.py")
    out = chain.reopen(code=1)
    assert (out["status"], out["error"]) == ("error", "parser-missing")
    assert chain.journal.read_bytes() == before


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


def test_resume_prints_when_the_journal_started_and_was_last_written(chain):
    """#1169: an `interrupted` chain may still run in another session, so the offer carries the journal file's own
    `started_at` and `updated_at`, which each `step` moves; `finish` prints the same next action without them."""
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    first = chain.resume()
    written = chain.data()
    assert first["kind"] == "interrupted"
    assert (first["started_at"], first["updated_at"]) == (written["started_at"], written["updated_at"])
    chain.ran("BS")
    later = chain.resume()  # forge-auto stopped after AN and BS
    assert (later["kind"], later["started_at"]) == ("interrupted", first["started_at"])
    assert later["updated_at"] == chain.data()["updated_at"] and later["updated_at"] > first["updated_at"]
    chain.halt("CS", "helper-missing")
    finished = chain.finish()
    error = chain.resume()
    written = chain.data()
    assert error["kind"] == "error"
    assert (error["started_at"], error["updated_at"]) == (written["started_at"], written["updated_at"])
    assert {key: finished[key] for key in mod.NEXT_ACTION_KEYS} == {key: error[key] for key in mod.NEXT_ACTION_KEYS}
    assert "started_at" not in finished and "updated_at" not in finished


def test_resume_prints_null_for_a_time_the_journal_lacks(chain):
    chain.start("QS[cognee] TS EX")
    journal = chain.data()
    del journal["started_at"], journal["updated_at"]
    chain.journal.write_bytes(json.dumps(journal).encode("utf-8"))
    out = chain.resume()
    assert (out["status"], out["started_at"], out["updated_at"]) == ("offer", None, None)


def _resume_section() -> str:
    return _read(PIPELINE_MODE).split("## Resume", 1)[1].split("\n## ", 1)[0]


def test_a_headless_resume_the_user_must_act_on_first_leaves_the_offer(chain):
    """#1169: `/skf-forger resume --headless` on an offer with a `user_action` writes the failed pipeline result
    as step 1 does, with no journal and no step, so the offer stands for the next start."""
    assert "the halt reason `user-action-required: <user_action>`" in _resume_section()
    _halt_forge_auto_at_ts(chain, "INCONCLUSIVE")
    chain.finish()
    offer = chain.resume()
    assert offer["user_action"] == mod.USER_ACTIONS["add-evidence"]
    chain.clock.tick(3600)
    reason = f"user-action-required: {offer['user_action']}"
    out = chain.cli(*_argv(_pipeline_mode_calls()["parse-halt"], {"{sidecar_path}": str(chain.sidecar)}),
                    stdin=reason + "\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", reason)
    assert json.loads(_read(chain.sidecar / "pipeline-result-latest.json"))["summary"]["steps"] == []
    again = chain.resume()
    assert (again["status"], again["journal"], again["route"]) == ("offer", offer["journal"], offer["route"])


def test_a_headless_resume_with_no_offer_writes_its_failed_result(chain):
    """#1169: `resume` with no offer halts **Nothing to resume.**; headless, it first writes the failed result."""
    assert "the halt reason `nothing-to-resume: <message>`" in _resume_section()
    none = chain.resume()
    assert none["status"] == "none"
    reason = f"nothing-to-resume: {none['message']}"
    out = chain.cli(*_argv(_pipeline_mode_calls()["parse-halt"], {"{sidecar_path}": str(chain.sidecar)}),
                    stdin=reason + "\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", reason)


def test_a_headless_resume_whose_reopen_fails_writes_its_failed_result(chain):
    """#1169: a `reopen` that fails (here the run folder went between the offer and the pick) halts; headless, it
    first writes the failed pipeline result as step 1 does, with its `message`, so a `claude -p` caller does not
    read an earlier chain's result."""
    reopen = _resume_section().split("`<journal>` is the path the offer named", 1)[1]
    assert ("in `{headless_mode}`, first write the failed pipeline result as step 1 does, with its `message` (or what "
            "it printed, when that is no JSON object) as the halt reason") in reopen
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    offer = chain.resume()
    chain.cli("discard", "--journal", offer["journal"])
    failed = chain.cli(*_argv(_pipeline_mode_calls()["reopen"], {"<journal>": offer["journal"]}), code=1)
    assert failed["status"] == "error" and failed["message"]
    out = chain.cli(*_argv(_pipeline_mode_calls()["parse-halt"], {"{sidecar_path}": str(chain.sidecar)}),
                    stdin=failed["message"] + "\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", failed["message"])
    written = json.loads(_read(chain.sidecar / "pipeline-result-latest.json"))
    assert (written["summary"]["halt_reason"], written["summary"]["steps"]) == (failed["message"], [])


def test_a_headless_resume_with_no_user_action_reopens_the_chain(chain):
    """#1169: an offer whose `user_action` is null goes on to the documented `reopen` call."""
    assert "A headless offer whose `user_action` is null goes on" in _resume_section()
    chain.start(FORGE_AUTO)
    chain.ran("AN")
    chain.ran("BS")
    offer = chain.resume()
    assert (offer["kind"], offer["user_action"]) == ("interrupted", None)
    out = chain.cli(*_argv(_pipeline_mode_calls()["reopen"], {"<journal>": offer["journal"]}))
    assert [entry["code"] for entry in out["run"]] == ["CS", "TS", "EX"]


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
    assert out["run"][0] == {"index": 0, **mod._step_entry("QS"), **_named("QS")}
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
# step --envelope: the step from the envelope line its workflow printed (#1168)
# --------------------------------------------------------------------------

GATE_MOD = _load("skf_pipeline_gate_for_journal", GATE)

# What each code's run prints on success, over a value for every field its schema requires.
SUCCESS = {
    "SF": {"skf_setup": {"status": "success"}},
    "AN": {"status": "success", "mode": "auto", "brief_paths": ["/fd/hono/skill-brief.yaml"],
           "unit_counts": {"confirmed": 1, "skipped": 0, "maybe": 0}, "report_path": "/fd/hono/analysis-report.md",
           "result_path": "/fd/analyze-source-result-20261001-120100.json"},
    "BS": {"status": "success", "brief_path": "/fd/hono/skill-brief.yaml", "skill_name": "hono"},
    "CS": {"status": "success", "summary": {"skill_name": "hono"},
           "result_path": "/fd/hono/1.0.0/create-skill-result-20261001-120300.json"},
    "QS": {"status": "success", "summary": {"skill_name": "cognee"},
           "result_path": "/skills/cognee/0.3.0/cognee/quick-skill-result-20261001-120100.json"},
    "SS": {"status": "success", "skill_name": "acme-stack", "mode": "compose"},
    "US": {"skf_update": {"status": "success", "skill_name": "hono"}},
    "AS": {"status": "success", "skill_name": "cocoindex", "drift_score": "MINOR", "next_workflow": None,
           "upstream_moved": False, "report_path": "/fd/cocoindex/0.4.0/drift-report-20261001-120100.md"},
    "VS": {"status": "success", "overall_verdict": "FEASIBLE", "coverage_percentage": 80,
           "report_path": "/fd/feasibility-report-acme-20261001-120100.md"},
    "RA": {"status": "success", "refined_path": "/out/refined-architecture-acme.md"},
    "TS": {"status": "success", "skill_name": "hono", "verdict": "PASS", "score": 92, "threshold": 90,
           "next_workflow": "export-skill", "report_path": "/fd/hono/1.0.0/test-report-hono-x.md"},
    "EX": {"status": "success"},
    "RS": {"status": "success"},
    "DS": {"status": "success"},
}
# The value each success above hands on.
HANDED = {"AN": {"brief_path": "/fd/hono/skill-brief.yaml"}, "BS": {"brief_path": "/fd/hono/skill-brief.yaml"},
          "CS": {"skill_name": "hono"}, "QS": {"skill_name": "cognee"}, "US": {"skill_name": "hono"},
          "SS": {"skill_name": "acme-stack"}, "RA": {"architecture_doc_path": "/out/refined-architecture-acme.md"}}
# A reason with what a shell would run or unquote: a quote, backticks, `$( )`, double quotes and a backslash.
SHELL_REASON = "the run folder could not be created: can't write `$HOME/x` $(touch pwned) \"quoted\" \\n"


def _schema(code: str) -> dict:
    return json.loads(_read(SCHEMAS / f"skf-{SCHEMA_STEMS[code]}-result-envelope.v1.json"))


def _settings(code: str) -> dict:
    """The emitter's settings in the schema: its envelope `prefix` and `wrapper`."""
    return _schema(code)["$defs"]["skf-envelope"]["const"]


def _status_enum(code: str) -> list:
    schema, wrapper = _schema(code), _settings(code)["wrapper"]
    fields = schema["properties"][wrapper] if wrapper else schema
    return fields["properties"]["status"]["enum"]


def _synthetic(node: dict):
    """A value the schema node accepts: each required key of an object, null wherever null is allowed."""
    if "const" in node:
        return node["const"]
    for key in ("oneOf", "anyOf"):
        if key in node:
            branches = node[key]
            return None if any(b.get("type") == "null" for b in branches) else _synthetic(branches[0])
    if "enum" in node:
        return None if None in node["enum"] else node["enum"][0]
    kind = node.get("type")
    if isinstance(kind, list):
        if "null" in kind:
            return None
        kind = kind[0]
    if kind == "object":
        return {key: _synthetic(node["properties"][key]) for key in node.get("required", [])}
    return {"string": "x", "integer": node.get("minimum", 0), "number": 0, "boolean": False, "array": []}[kind]


def _merged(base, extra):
    if isinstance(base, dict) and isinstance(extra, dict):
        return {**base, **{key: _merged(base.get(key), value) for key, value in extra.items()}}
    return extra


def _line(code: str, payload: dict) -> str:
    """The envelope line a workflow prints for `payload`, which its schema must accept."""
    errors = sorted(Draft202012Validator(_schema(code)).iter_errors(payload), key=str)
    assert not errors, (code, [e.message for e in errors])
    return f"{mod.ENVELOPES[code]}: {json.dumps(payload)}"


def envelope_payload(code: str, **fields) -> dict:
    """A run's envelope for `code`: SUCCESS, with `fields` over it (an object's keys merged one by one)."""
    return _merged(_merged(_synthetic(_schema(code)), SUCCESS[code]), fields)


def envelope(code: str, **fields) -> str:
    return _line(code, envelope_payload(code, **fields))


def test_the_envelopes_are_each_schemas_and_the_gates():
    assert set(mod.ENVELOPES) == set(PARSER.KNOWN_CODES) == set(SCHEMA_STEMS)
    for code, name in mod.ENVELOPES.items():
        assert _schema(code)["title"].split()[0] == _settings(code)["prefix"] == name, code
    assert {code: mod.ENVELOPES[code] for code in GATE_MOD.GATED_CODES} == GATE_MOD.ENVELOPES
    assert mod._ENVELOPE_RE.pattern == GATE_MOD._ENVELOPE_RE.pattern
    # Campaign is a workflow of its own, not a chain code.
    assert "campaign" not in SCHEMA_STEMS.values() and (SCHEMAS / "skf-campaign-result-envelope.v1.json").is_file()


def test_the_status_table_is_each_schemas():
    assert set(mod.COMPLETED_STATUSES) == set(PARSER.KNOWN_CODES) - set(GATED)
    for code, statuses in mod.COMPLETED_STATUSES.items():
        assert "success" in statuses and set(statuses) <= set(_status_enum(code)), code
    assert mod.COMPLETED_STATUSES["US"] == ("success", "no-changes", "detect-only", "dry-run")
    assert all(statuses == ("success",) for code, statuses in mod.COMPLETED_STATUSES.items() if code != "US")
    assert mod.HALT_REASONS == {("CS", "partial"): "zero-exports", ("EX", "dry-run"): "dry-run"}
    for code, status in mod.HALT_REASONS:
        assert status in _status_enum(code) and status not in mod.COMPLETED_STATUSES[code]
    assert mod.PAYLOADS == {code: _settings(code)["wrapper"] for code in SCHEMA_STEMS if _settings(code)["wrapper"]}


def test_the_handoff_fields_are_the_handoffs_and_each_schemas():
    assert set(mod.HANDOFF_FIELDS) == set(mod.HANDOFFS)
    for code, keys in mod.HANDOFF_FIELDS.items():
        node = _schema(code)
        for key in keys:
            node = node["properties"][key]
        assert node, (code, keys)
    assert mod.OUTPUT_FIELDS == ("result_path", "report_path")
    for name in mod.OUTPUT_FIELDS:
        assert [code for code in SCHEMA_STEMS if name in _schema(code)["properties"]], name


@pytest.mark.parametrize("code", sorted(PARSER.KNOWN_CODES))
def test_each_codes_envelope_completes_its_step(chain, code):
    """One success per code, from a line its schema accepts: the step completes, hands its value on and
    records the line's result and report paths."""
    chain.start(f"{code}[cognee]")
    payload = envelope_payload(code)
    out = chain.envelope(code, _line(code, payload) + "\n")
    assert (out["recorded"]["code"], out["recorded"]["status"], out["recorded"]["reason"]) == (code, "completed", None)
    assert (out["skipped"], out["next"]) == ([], None)
    assert out["data"] == HANDED.get(code, {})
    if code in GATED:
        assert out["gate"] == GATE_MOD.gate(code, _line(code, payload))
    else:
        assert out["gate"] is None
    paths = [payload[name] for name in mod.OUTPUT_FIELDS if payload.get(name)]
    assert chain.data()["outputs"] == [{"code": code, "path": p} for p in paths]
    _kept_the_step_shape(chain)


def test_a_chain_recorded_from_its_envelopes_keeps_the_journal_shape(chain):
    """#1168's acceptance: every step through --envelope, and the journal is still version 1 with the
    seven step keys."""
    chain.start(FORGE_AUTO)
    for code in ("AN", "BS", "CS", "TS"):
        assert chain.envelope(code, envelope(code))["recorded"]["status"] == "completed", code
    assert chain.envelope("EX", envelope("EX"))["next"] is None
    _kept_the_step_shape(chain)
    assert [s["status"] for s in chain.data()["steps"]] == ["completed"] * 5
    assert chain.finish()["pipeline_status"] == "success"


def test_create_skill_hands_its_skill_to_test_skill(chain):
    chain.start("CS[cognee] TS EX")
    payload = envelope_payload("CS", summary={"skill_name": "cognee"})
    out = chain.envelope("CS", _line("CS", payload))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"skill_name": "cognee"})
    assert chain.data()["outputs"] == [{"code": "CS", "path": payload["result_path"]}]
    assert (out["next"]["code"], out["next"]["inputs"]) == ("TS", {"skill_name": "cognee"})


def test_a_skill_compiled_with_no_exports_halts_zero_exports(chain):
    """CS reports a zero-export run as `partial`: the chain stops before TS, with the skill recorded, and
    offers to run CS again once the brief is fixed."""
    chain.start("CS[cognee] TS EX")
    out = chain.envelope("CS", envelope("CS", status="partial", summary={"skill_name": "cognee",
                                                                         "warning": "zero-exports"}))
    assert (out["recorded"]["status"], out["recorded"]["reason"], out["next"]) == ("halted", "zero-exports", None)
    assert out["data"] == {"skill_name": "cognee"}
    done = chain.finish()
    assert (done["offer"], done["kind"], done["resume_at"]) == ("resume", "error", {"index": 0, "code": "CS"})


@pytest.mark.parametrize("code", ["EX", "DS", "RS"])
def test_a_dry_run_halts_dry_run(chain, code):
    """A chain takes no --dry-run, so a dry-run line means nothing was written."""
    chain.start(f"{code}[cognee]")
    out = chain.envelope(code, envelope(code, status="dry-run"))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "dry-run")
    done = chain.finish()
    assert (done["offer"], done["resume_at"]) == ("resume", {"index": 0, "code": code})


@pytest.mark.parametrize("status", ["success", "no-changes", "detect-only", "dry-run"])
def test_an_update_completes_on_each_successful_exit(chain, status):
    chain.start("US[hono] TS EX")
    out = chain.envelope("US", envelope("US", skf_update={"status": status}))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"skill_name": "hono"})
    assert (out["next"]["code"], out["next"]["inputs"]) == ("TS", {"skill_name": "hono"})


@pytest.mark.parametrize(("code", "fields", "reason"), [
    pytest.param("US", {"skf_update": {"status": "halted-for-workspace-drift",
                                       "error": {"phase": "gap-driven:3", "reason": "the tree moved"}}},
                 "halted-for-workspace-drift: the tree moved", id="us-halted-for"),
    pytest.param("US", {"skf_update": {"status": "blocked"}}, "blocked", id="us-blocked-no-reason"),
    pytest.param("SF", {"skf_setup": {"status": "tier_failure",
                                      "error": {"phase": "step 3:require-tier", "path": "<n/a>",
                                                "reason": "Deep required, Forge detected"}}},
                 "tier_failure: Deep required, Forge detected", id="sf-tier-failure"),
    pytest.param("BS", {"status": "error", "halt_reason": "target-inaccessible", "exit_code": 3,
                        "brief_path": None}, "target-inaccessible", id="bs-halt-reason"),
    pytest.param("CS", {"status": "failed", "halt_reason": "brief-missing", "exit_code": 2},
                 "brief-missing", id="cs-failed"),
    pytest.param("RA", {"status": "error", "halt_reason": "preservation-failed", "exit_code": 5,
                        "refined_path": None, "error": {"phase": "compile:promote", "reason": "a section was lost"}},
                 "preservation-failed", id="ra-halt-reason-wins"),
])
def test_any_other_status_halts_with_the_envelopes_reason(chain, code, fields, reason):
    chain.start("SF QS[x]" if code == "SF" else f"{code}[cognee]")
    out = chain.envelope(code, envelope(code, **fields))
    assert (out["recorded"]["status"], out["recorded"]["reason"], out["next"]) == ("halted", reason, None)
    assert chain.data()["status"] == "halted"


def test_a_line_with_no_status_halts_no_status(chain):
    chain.start("CS[cognee] TS EX")
    out = chain.envelope("CS", f"{mod.ENVELOPES['CS']}: " + json.dumps({"summary": {"skill_name": "cognee"}}))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "no-status")


def test_analyze_hands_on_every_brief_it_wrote(chain):
    chain.start(FORGE_AUTO)
    briefs = ["/fd/core/skill-brief.yaml", "/fd/cli/skill-brief.yaml"]
    payload = envelope_payload("AN", brief_paths=briefs, unit_counts={"confirmed": 2})
    out = chain.envelope("AN", _line("AN", payload))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"brief_path": briefs})
    assert chain.data()["outputs"] == [{"code": "AN", "path": payload["result_path"]},
                                       {"code": "AN", "path": payload["report_path"]}]
    assert (out["gate"]["decision"], out["next"]["inputs"]) == ("continue", {"brief_path": briefs, "auto": True})


def test_analyze_below_its_plan_min_halts(chain):
    """The journal hands the gate AN's plan `min`."""
    chain.start("AN[min:2] CS TS EX")
    out = chain.envelope("AN", envelope("AN"))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "units-below-min")
    assert "at least 2" in out["gate"]["message"]
    assert out["data"] == {"brief_path": "/fd/hono/skill-brief.yaml"}


def test_a_clean_audit_skips_the_update_and_prints_the_gate(chain):
    """The journal hands the gate the next plan code, so a CLEAN audit passes over US."""
    chain.start("maintain cocoindex")
    line = envelope("AS", drift_score="CLEAN")
    out = chain.envelope("AS", line)
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("completed", None)
    assert [(s["code"], s["status"], s["reason"]) for s in out["skipped"]] == [("US", "skipped", "CLEAN")]
    assert out["gate"] == GATE_MOD.gate("AS", line, next_code="US") and out["gate"]["message"]
    assert out["next"]["code"] == "TS"


def test_an_audit_that_found_upstream_moved_hands_the_update_its_ref(chain):
    chain.start("maintain cocoindex")
    out = chain.envelope("AS", envelope("AS", upstream_moved=True, upstream_ref="v2", next_workflow="update-skill"))
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"target_ref": "v2"})
    assert out["next"]["inputs"] == {"skill_name": "cocoindex", "target_ref": "v2"}


def test_a_stack_chain_hands_the_refined_document_to_ss_and_its_skill_to_ts(chain):
    """SS composes from the document RA refined, TS tests the stack skill SS wrote, and a FAIL routes the
    repair to that skill."""
    chain.start("VS[docs/arch.md] RA SS TS EX")
    out = chain.envelope("VS", envelope("VS"))
    assert (out["next"]["code"], out["next"]["inputs"]) == ("RA", {"architecture_doc_path": "docs/arch.md"})
    refined = "/out/refined-architecture-acme.md"
    out = chain.envelope("RA", envelope("RA", refined_path=refined))
    assert out["data"] == {"architecture_doc_path": refined}
    assert (out["next"]["code"], out["next"]["inputs"]) == ("SS", {"architecture_doc_path": refined})
    out = chain.envelope("SS", envelope("SS", skill_name="acme-stack"))
    assert (out["next"]["code"], out["next"]["inputs"]) == ("TS", {"skill_name": "acme-stack"})
    out = chain.envelope("TS", envelope("TS", skill_name="acme-stack", verdict="FAIL",
                                        next_workflow="update-skill", exit_code=2))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "FAIL")
    assert chain.finish()["route"] == "US acme-stack --from-test-report, then TS EX"
    _kept_the_step_shape(chain)


def test_ra_still_takes_the_document_vs_was_given_when_ss_follows(chain):
    chain.start("VS[docs/arch.md] RA SS")
    chain.envelope("VS", envelope("VS"))
    assert chain.data()["data"] == {}
    assert mod.resolve_inputs(chain.data(), 1) == {"architecture_doc_path": "docs/arch.md"}
    assert mod.resolve_inputs(chain.data(), 2) == {}  # SS has nothing until RA hands it the refined document


@pytest.mark.parametrize(("code", "line"), [
    pytest.param("CS", lambda: envelope("TS"), id="ungated"),
    pytest.param("TS", lambda: envelope("CS"), id="gated"),
])
def test_another_workflows_line_halts_wrong_result(chain, code, line):
    chain.start(f"{code}[cognee]")
    out = chain.envelope(code, line())
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "wrong-result")
    assert out["data"] == {} and chain.data()["outputs"] == []


def test_the_last_line_of_the_codes_own_envelope_wins(chain):
    chain.start("QS[cognee] TS EX")
    text = "\n".join(["Pipeline log", envelope("TS"), envelope("QS", status="error", halt_reason="input-invalid",
                                                           exit_code=2, summary={}),
                      envelope("QS", summary={"skill_name": "cognee-sdk"}), "done"])
    out = chain.envelope("QS", text)
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"skill_name": "cognee-sdk"})


@pytest.mark.parametrize("text", ["not an envelope", "SKF_QUICK_SKILL_RESULT_JSON: {not json}", "[1, 2]"],
                         ids=["prose", "broken-json", "not-an-object"])
def test_text_that_is_no_envelope_halts_result_unreadable(chain, text):
    chain.start("QS[cognee] TS EX")
    out = chain.envelope("QS", text)
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "result-unreadable")


def test_a_byte_order_mark_is_dropped(chain):
    chain.start("QS[cognee] TS EX")
    assert chain.envelope("QS", "\ufeff" + envelope("QS"))["recorded"]["status"] == "completed"


@pytest.mark.parametrize("code", ["QS", "AN"])
def test_a_completed_step_whose_line_names_no_handoff_halts_handoff_missing(chain, code):
    """The next workflow would start without its input, and a retry would send the model back to reading
    the envelope by hand. A gated AN halts so too when its gate continues: the AN schema allows a line that
    counts units but lists no brief."""
    if code == "QS":
        chain.start("QS[cognee] TS EX")
        payload = envelope_payload("QS")
        del payload["summary"]["skill_name"]
    else:
        chain.start("AN[min:1] CS TS EX")
        payload = envelope_payload("AN", brief_paths=[])
    out = chain.envelope(code, _line(code, payload))
    assert (out["recorded"]["status"], out["recorded"]["reason"], out["next"]) == ("halted", "handoff-missing", None)
    assert (out["gate"] or {}).get("decision") == (None if code == "QS" else "continue")
    assert chain.data()["status"] == "halted"


def test_the_envelopes_value_wins_over_a_typed_one(chain):
    chain.start("QS[cognee] TS EX")
    out = chain.envelope("QS", envelope("QS", summary={"skill_name": "cognee-sdk"}), "--set", "skill_name=typed")
    assert out["data"] == {"skill_name": "cognee-sdk"}
    # A value the line does not name still comes from --set.
    chain.start("QS[cognee] TS EX")
    payload = envelope_payload("QS")
    del payload["summary"]["skill_name"]
    out = chain.envelope("QS", _line("QS", payload), "--set", "skill_name=typed", "--output", "/r/report.md")
    assert (out["recorded"]["status"], out["data"]) == ("completed", {"skill_name": "typed"})
    assert chain.data()["outputs"] == [{"code": "QS", "path": payload["result_path"]},
                                       {"code": "QS", "path": "/r/report.md"}]


def test_a_gate_that_cannot_load_records_nothing(chain, monkeypatch, tmp_path):
    chain.start("forge-quick cognee")
    chain.envelope("QS", envelope("QS"))
    before = chain.journal.read_bytes()
    monkeypatch.setattr(mod, "GATE", tmp_path / "pipeline-gate.py")
    out = chain.envelope("TS", envelope("TS", skill_name="cognee"), rc=1)
    assert (out["status"], out["error"], out["retry"]) == ("error", "gate-missing", False)
    assert "pipeline-gate.py" in out["message"]
    assert chain.journal.read_bytes() == before
    # The chain stops, and step 5 records the stop with the error's message.
    done = chain.cli("finish", "--journal", chain.journal, "--result-dir", chain.sidecar, "--halt-reason", "-",
                     stdin=out["message"] + "\n")
    assert (done["pipeline_status"], done["halt_reason"], done["halted_on"]["code"]) == (
        "partial", out["message"], "TS")
    # A code with no gate does not need it.
    chain.start("forge-quick cognee")
    assert chain.envelope("QS", envelope("QS"))["recorded"]["status"] == "completed"


def test_the_journal_loads_the_gate_only_when_a_step_needs_it():
    """forge-status.py imports the journal: the gate loads in `step --envelope` for a gated code, never at
    import (a gate gone missing breaks no import and no other step, above)."""
    source = _read(SCRIPT)
    calls = [m.start() for m in re.finditer(r"(?<!def )_load_gate\(\)", source)]
    assert len(calls) == 1 and source.index("def cmd_step") < calls[0] < source.index("def _claim_result_path")


def test_step_prints_the_decision_it_recorded(chain):
    chain.start("forge-quick cognee")
    assert chain.step("QS", "completed", "--set", "skill_name=cognee")["gate"] is None
    out = chain.gate("TS", "halt", reason="FAIL")
    assert (out["gate"]["code"], out["gate"]["decision"], out["gate"]["reason"]) == ("TS", "halt", "FAIL")


def test_a_reason_on_stdin_is_recorded_as_given(chain):
    chain.start("SF QS[cognee] TS EX")
    out = chain.cli("step", "--journal", chain.journal, "--code", "SF", "--status", "halted", "--reason", "-",
                    stdin=SHELL_REASON + "\n")
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", SHELL_REASON)
    chain.start("SF QS[cognee] TS EX")
    out = chain.cli("step", "--journal", chain.journal, "--code", "SF", "--status", "halted", "--reason", "-",
                    stdin="\n", code=1)
    assert (out["error"], out["retry"]) == ("reason-missing", True)


@pytest.mark.parametrize("how", ["--gate", "--envelope"])
def test_a_reason_on_stdin_goes_only_with_status(chain, capsys, monkeypatch, how):
    """--gate and --envelope read stdin themselves: `--reason -` with them is a usage error, and nothing
    is recorded."""
    chain.start("forge-quick cognee")
    chain.envelope("QS", envelope("QS"))
    before = chain.journal.read_bytes()
    monkeypatch.setattr(sys, "stdin", io.StringIO(envelope("TS", skill_name="cognee")))
    with pytest.raises(SystemExit) as stopped:
        mod.main(["step", "--journal", str(chain.journal), "--code", "TS", how, "--reason", "-"])
    assert stopped.value.code == 2
    printed = capsys.readouterr()
    assert printed.out == "" and "--reason" in printed.err
    assert chain.journal.read_bytes() == before


def test_finish_reads_the_halt_reason_on_stdin(chain):
    chain.start("QS TS EX")
    chain.ran("QS")
    finish = ("finish", "--journal", chain.journal, "--result-dir", chain.sidecar, "--halt-reason", "-")
    out = chain.cli(*finish, stdin="\n", code=1)  # an empty heredoc is no reason
    assert (out["error"], out["retry"]) == ("unfinished", True)
    out = chain.cli(*finish, stdin=SHELL_REASON + "\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("partial", SHELL_REASON)
    assert chain.data()["steps"][1] == {**mod._step_entry("TS"), "status": "halted", "reason": SHELL_REASON}


def test_finish_with_an_empty_reason_heredoc_records_the_stop_a_step_recorded(chain):
    chain.start("forge-quick cognee")
    chain.envelope("QS", envelope("QS"))
    chain.envelope("TS", envelope("TS", skill_name="cognee", verdict="FAIL", next_workflow="update-skill",
                                  exit_code=2))
    out = chain.cli("finish", "--journal", chain.journal, "--result-dir", chain.sidecar, "--halt-reason", "-",
                    stdin="")
    assert (out["pipeline_status"], out["halt_reason"]) == ("partial", "FAIL")
    out = chain.cli("finish", "--result-dir", chain.sidecar, "--halt-reason", "-", stdin="unknown code TX\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", "unknown code TX")
    out = chain.cli("finish", "--result-dir", chain.sidecar, "--halt-reason", "-", stdin="", code=1)
    assert (out["error"], out["retry"]) == ("reason-missing", True)


def _run_bytes(*argv: str, stdin: bytes) -> dict:
    p = subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout.decode("utf-8"))


@pytest.mark.parametrize("code", ["QS", "TS"])
def test_a_line_read_from_a_real_stdin_drops_a_bom_and_refuses_bytes_that_are_not_utf8(tmp_path, code):
    started = _run("start", "--run-root", str(tmp_path / "runs"), stdin=f"{code}[cognee]\n")
    step = ("step", "--journal", started["journal"], "--code", code, "--envelope")
    line = envelope(code, **({"skill_name": "cognee"} if code == "TS" else {}))
    out = _run_bytes(*step, stdin=b"\xef\xbb\xbf" + line.encode("utf-8") + b"\n")
    assert out["recorded"]["status"] == "completed"
    started = _run("start", "--run-root", str(tmp_path / "runs"), stdin=f"{code}[cognee]\n")
    step = ("step", "--journal", started["journal"], "--code", code, "--envelope")
    out = _run_bytes(*step, stdin=line.encode("utf-8").replace(b"cognee", b"cogn\xe9e"))
    assert (out["recorded"]["status"], out["recorded"]["reason"]) == ("halted", "result-unreadable")


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


def _step_d() -> str:
    """pipeline-mode.md step 4d, which records each step (#1168: the circuit breaker and the record in one)."""
    return _read(PIPELINE_MODE).split("   - d. **Record the step**", 1)[1].split("   - e. **", 1)[0]


def test_the_handoffs_are_data_flow_values_step_d_names():
    rows = _table(_section(_read(CONTRACTS), "## Data Flow"))
    rule = next(sentence for sentence in _step_d().split(". ") if "hands on" in sentence)
    for code, name in mod.HANDOFFS.items():
        assert any(row[0] == code for row in rows), code
        assert re.search(rf"\b{code}\b", rule) and f"`{name}=<" in rule, (code, name)


def test_the_data_flow_map_is_the_data_flow_table():
    """#1167: DATA_FLOW has one key per Data Flow row, each value an input the row names, and every
    handoff a code records reaches each code its rows hand it to. #1168: RA hands SS the refined
    document, and SS hands TS and EX its skill."""
    rows = _table(_section(_read(CONTRACTS), "## Data Flow"))
    pairs = [(row[0], row[1]) for row in rows]
    assert list(mod.DATA_FLOW) == pairs and len(pairs) == 14
    assert pairs[-4:] == [("VS", "RA"), ("RA", "SS"), ("SS", "TS"), ("SS", "EX")]
    assert {"SS", "RA"} <= set(mod.HANDOFFS) and {"SS", "RA"} <= {source for source, _ in pairs}
    for row in rows:
        text = " ".join(row[2:])
        for name in mod.DATA_FLOW[(row[0], row[1])]:
            assert name in text or name.replace("_", " ") in text, (row[:2], name)
    for code, name in mod.HANDOFFS.items():
        taken = [names for (source, _), names in mod.DATA_FLOW.items() if source == code]
        assert taken and all(name in names for names in taken), (code, name)


def test_the_contracts_name_the_status_rules_and_the_stack_handoffs():
    """#1168: the Circuit Breakers intro and the CS and EX rows state the statuses the journal reads, and
    the Data Flow rows the values RA and SS hand on, as the script keeps them."""
    contracts = _read(CONTRACTS)
    section = _section(contracts, "## Circuit Breakers")
    rows = {row[0]: " ".join(row[1:]) for row in _table(section)}
    for (code, status), reason in mod.HALT_REASONS.items():
        assert f"`{status}` halts with `{reason}`" in rows[code], code
    intro = section.split("| Workflow |", 1)[0]
    for token in ("`pipeline-journal.py step --envelope`", "`pipeline-gate.py`", "`skf_setup.status` for SF",
                  "`skf_update.status` for US", "followed by `: <error.reason>`",
                  *(f"`{status}`" for status in mod.COMPLETED_STATUSES["US"])):
        assert token in intro, token
    flow = {(row[0], row[1]): " ".join(row[2:]) for row in _table(_section(contracts, "## Data Flow"))}
    assert ("`refined_path` from `SKF_REFINE_ARCHITECTURE_RESULT_JSON` as SS's `architecture_doc_path`, which runs "
            "SS in compose mode") in flow[("RA", "SS")]
    for to in ("TS", "EX"):
        assert "the `skill_name` from `SKF_STACK_RESULT_JSON`" in flow[("SS", to)], to
    assert "`pipeline-journal.py step --envelope` records it" in flow[("AS", "US")]
    [bullet] = [line for line in _read(REPO / "docs" / "workflows.md").splitlines()
                if line.startswith("- **Circuit breakers**")]
    assert "CS hits a hard error or compiles a skill with no exports" in bullet


def test_step_d_leaves_the_audits_ref_to_the_gate():
    """No --set copies AS's upstream_ref by hand: `step --envelope` records the gate's handoff."""
    text = _read(PIPELINE_MODE)
    record = _step_d()
    assert "target_ref=<upstream_ref>" not in record and "upstream_ref" not in record
    assert ("AS's `target_ref` is the gate's: when upstream moved, the gate names it in its `handoff`, and "
            "`step --envelope` records it.") in record
    resolve = text.split("   - b. **Resolve inputs**", 1)[1].split("   - c. **", 1)[0]
    assert "a `target_ref` (AS hands it on when upstream moved) goes to US as `--target-ref <target_ref>`" in resolve


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


def test_a_chain_cut_off_before_finish_leaves_the_earlier_result(chain):
    """Only `finish` writes the pipeline result, so a chain cut off mid-step (an agent that ended its turn
    under `claude -p`) leaves the previous chain's copy in place, as pipeline-contracts.md says: a caller reads
    the envelope lines the chain's workflows print, never this file in their place."""
    chain.start("QS[cognee] TS")
    chain.ran("QS")
    chain.ran("TS")
    chain.finish()
    earlier = _latest(chain)
    chain.clock.tick(3600)
    chain.start("QS[cognee] TS")
    chain.ran("QS")
    assert _latest(chain) == earlier
    section = _section(_read(CONTRACTS), "## Pipeline Result")
    for token in ("which holds the last chain, or attempt, that reached `finish`",
                  "A chain cut off before `finish` writes none, so the file may describe an earlier chain or an "
                  "earlier attempt of this one: a caller reads the envelope lines the chain's workflows print, never "
                  "this file in their place."):
        assert token in section, token
    assert "the file consumers read" not in section and "`run_id` is its own chain's" not in section


@pytest.mark.parametrize("code", sorted(PARSER.KNOWN_CODES))
def test_a_workflow_with_no_result_line_halts_no_result(chain, code):
    """pipeline-mode.md step d leaves the heredoc empty for a workflow that printed no envelope line: the
    journal records it `halted` with `no-result`, gated or not, and offers to run that step again."""
    chain.start(f"{code}[cognee]")
    out = chain.envelope(code, "")
    assert (out["recorded"]["status"], out["recorded"]["reason"], out["next"]) == ("halted", "no-result", None)
    if code in GATED:
        assert (out["gate"]["decision"], out["gate"]["reason"]) == ("halt", "no-result")
    else:
        assert out["gate"] is None
    done = chain.finish()
    assert (done["pipeline_status"], done["halt_reason"], done["offer"], done["kind"]) == (
        "failed", "no-result", "resume", "error")
    flow = " ".join(_step_d().split())
    assert ("A workflow that printed no envelope line has no result to read, whatever the process exit code: it "
            "was cut off, or could not write its result, so leave the heredoc empty: the step is recorded "
            "`halted` with `no-result`.") in flow


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


def _heredoc_call(text: str, pattern: str) -> tuple[str, str, str]:
    """A documented journal call over a quoted heredoc: (the call, its delimiter, its one placeholder line)."""
    m = re.search(rf"```bash\n\s*(uv run scripts/pipeline-journal\.py {pattern}) <<'(\w+)'\n\s*(<[^>\n]+>)\n\s*\2\n",
                  text)
    assert m, f"pipeline-mode.md shows no {pattern!r} call over a quoted heredoc"
    return m.group(1), m.group(2), m.group(3)


def _journal_step_of_activation() -> str:
    text = _read(FORGER_SKILL)
    return text[text.index("5. **Read the pipeline journal**"):text.index("6. **Greet, then dispatch or wait.**")]


def _pipeline_mode_calls() -> dict[str, str]:
    """pipeline-mode.md's documented journal calls, by name, and each heredoc's placeholder as `<name>-stdin`."""
    text = _read(PIPELINE_MODE)
    calls = {}
    for name, pattern in (("start", r"start .+?"), ("envelope", r"step .+?--envelope"),
                          ("status", r"step .+?--status halted --reason -"),
                          ("finish", r"finish --journal .+?--halt-reason -"),
                          ("parse-halt", r"finish --result-dir .+?--halt-reason -")):
        calls[name], _, calls[f"{name}-stdin"] = _heredoc_call(text, pattern)
    [calls["reopen"]] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py reopen .+)$", text, re.M)
    assert len(re.findall(r"uv run scripts/pipeline-journal\.py step ", text)) == 2
    assert len(re.findall(r"uv run scripts/pipeline-journal\.py finish ", text)) == 2
    return calls


def _documented_values(root: Path) -> dict[str, str]:
    """The placeholders pipeline-mode.md's calls take, filled with the folders a project under `root` keeps."""
    return {"{project-root}": str(root), "{sidecar_path}": str(root / "sidecar"),
            "{forge_data_folder}": str(root / "forge-data"), "{skills_output_folder}": str(root / "skills")}


def test_the_activation_call_runs_as_written(tmp_path):
    [call] = re.findall(r"^\s*(uv run scripts/pipeline-journal\.py resume .+)$", _journal_step_of_activation(), re.M)
    values = {"{project-root}": str(tmp_path), "{sidecar_path}": str(tmp_path / "sidecar"),
              "{forge_data_folder}": str(tmp_path / "forge-data"), "{skills_output_folder}": str(tmp_path / "skills")}
    run_root = tmp_path / "_bmad-output" / ".skf-run"
    assert _run(*_argv(call, values))["status"] == "none"
    _run("start", "--run-root", str(run_root), stdin="QS TS EX\n")
    out = _run(*_argv(call, values))
    assert (out["status"], out["offer"], out["resume_at"]["code"]) == ("offer", "resume", "QS")


def test_the_pipeline_mode_calls_run_as_written(tmp_path):
    """#1168: `maintain` from start to finish, every step recorded by the one call step d documents, each
    reason given on stdin."""
    calls = _pipeline_mode_calls()
    assert (calls["start-stdin"], calls["envelope-stdin"], calls["status-stdin"]) == (
        "<the whole invocation>", "<the envelope line the workflow printed>", "<the line SF displayed>")
    assert (calls["finish-stdin"], calls["parse-halt-stdin"]) == ("<the reason the chain stopped with>",
                                                                  "<the halt reason>")
    values = _documented_values(tmp_path)
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    values["<journal>"] = started["journal"]
    assert Path(started["run_dir"]).parent == tmp_path / "_bmad-output" / ".skf-run"

    def record(code: str, line: str) -> dict:
        return _run(*_argv(calls["envelope"], {**values, "<code>": code}), stdin=line + "\n")

    # AS: a CLEAN audit with no move skips US (the skill is not in the skills folder, so it is not current).
    out = record("AS", envelope("AS", drift_score="CLEAN", next_workflow=None))
    assert ([s["code"] for s in out["skipped"]], out["gate"]["decision"], out["next"]["code"]) == (
        ["US"], "skip", "TS")
    # TS: FAIL halts.
    out = record("TS", envelope("TS", verdict="FAIL", next_workflow="update-skill", exit_code=2))
    assert (out["recorded"]["reason"], out["next"]) == ("FAIL", None)
    finished = _run(*_argv(calls["finish"], values), stdin="")  # a step call recorded the stop: an empty heredoc
    assert (finished["run_dir_kept"], finished["route"]) == (True, "US cocoindex --from-test-report, then TS EX")
    assert [r["code"] for r in _run(*_argv(calls["reopen"], values))["run"]] == ["US", "TS", "EX"]
    # US, TS and EX run the repaired chain to its end.
    assert record("US", envelope("US", skf_update={"skill_name": "cocoindex"}))["next"]["code"] == "TS"
    assert record("TS", envelope("TS", skill_name="cocoindex"))["next"]["code"] == "EX"
    assert record("EX", envelope("EX"))["next"] is None
    assert _run(*_argv(calls["finish"], values), stdin="")["pipeline_status"] == "success"
    out = _run(*_argv(calls["parse-halt"], values), stdin="unknown code TX\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("failed", "unknown code TX")
    # SF displayed a line that is no envelope line: that line is the halt reason.
    started = _run(*_argv(calls["start"], values), stdin="SF QS[cognee] TS EX\n")
    out = _run(*_argv(calls["status"], {**values, "<journal>": started["journal"]}), stdin="uv: command not found\n")
    assert (out["recorded"]["code"], out["recorded"]["status"], out["recorded"]["reason"]) == (
        "SF", "halted", "uv: command not found")


def _link_active(active_link: Path, version: str) -> None:
    """active -> version, with the Windows junction fallback test-skf-skill-inventory.py uses."""
    try:
        active_link.symlink_to(version)
        return
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
    abs_target = (active_link.parent / version).resolve()
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(active_link), str(abs_target)],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr or done.stdout


def current_skill(forge: Path, skills: Path, sidecar: Path, name: str) -> None:
    """A skill forge-status.py calls current: version 1.0.0 is active, PASSed its test and is the exported one,
    with no drift on record, and forge-tier.yaml was last written an hour before that test."""
    package = skills / name / "1.0.0" / name
    package.mkdir(parents=True)
    package.joinpath("SKILL.md").write_bytes(f"---\nname: {name}\n---\n# {name}\n".encode("utf-8"))
    (package / "metadata.json").write_bytes(json.dumps({"name": name, "generated_by": "create-skill"}).encode())
    _link_active(skills / name / "active", "1.0.0")
    manifest = {"schema_version": "2", "updated_at": "2026-03-01T13:00:00Z", "exports": {name: {
        "active_version": "1.0.0", "versions": {"1.0.0": {"last_exported": "2026-03-01", "status": "active"}}}}}
    (skills / mod.EXPORT_MANIFEST).write_bytes(json.dumps(manifest).encode("utf-8"))
    (forge / name / "1.0.0").mkdir(parents=True)
    record = {"runId": "20260301T120000Z-0000beef", "timestamp": "2026-03-01T12:00:00Z",
              "summary": {"result": "PASS"}}
    (forge / name / "1.0.0" / mod.TEST_RESULT).write_bytes(json.dumps(record).encode("utf-8"))
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / "forge-tier.yaml").write_bytes(b"tier: Forge\n")
    hour_before = datetime(2026, 3, 1, 11, 0, 0, tzinfo=timezone.utc).timestamp()
    os.utime(sidecar / "forge-tier.yaml", (hour_before, hour_before))


def _step_1_parse_call(values: dict[str, str]) -> list[str]:
    """pipeline-mode.md step 1's parse call: its words after the script, placeholders filled."""
    m = re.search(r"```bash\n\s*uv run scripts/parse-pipeline\.py (.+?) <<'(\w+)'\n\s*<the whole invocation>\n\s*\2\n",
                  _read(PIPELINE_MODE))
    assert m, "step 1 shows no parse call over a quoted heredoc"
    words = []
    for word in shlex.split(m.group(1)):
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        assert not re.search(r"[{<][a-z_ |-]+[}>]", word), word
        words.append(word)
    return words


def test_maintain_on_a_current_skill_passes_over_us_ts_and_ex_as_documented(tmp_path):
    """#1170's acceptance: step 1 and step 4d run as written, every placeholder filled, on `maintain` of a skill
    that is current: the parse warns about nothing, AS's step records US, TS and EX skipped, and the chain
    finishes `success` with nothing left to resume."""
    calls = _pipeline_mode_calls()
    values = _documented_values(tmp_path)
    current_skill(Path(values["{forge_data_folder}"]), Path(values["{skills_output_folder}"]),
                  Path(values["{sidecar_path}"]), "cocoindex")
    parse = subprocess.run([sys.executable, str(SRC / "skf-forger" / "scripts" / "parse-pipeline.py"),
                            *_step_1_parse_call(values)], input="maintain cocoindex\n", capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
    assert parse.returncode == 0, parse.stdout + parse.stderr
    assert json.loads(parse.stdout)["anti_patterns"] == []
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    values["<journal>"] = started["journal"]
    out = _run(*_argv(calls["envelope"], {**values, "<code>": "AS"}),
               stdin=envelope("AS", drift_score="CLEAN", next_workflow=None) + "\n")
    assert (out["gate"]["decision"], out["gate"]["skip"], out["gate"]["reason"]) == ("skip", "US TS EX", "current")
    assert "cocoindex is current" in out["gate"]["message"] and "Run TS cocoindex" in out["gate"]["message"]
    assert [(s["code"], s["status"], s["reason"]) for s in out["skipped"]] == [
        ("US", "skipped", "current"), ("TS", "skipped", "current"), ("EX", "skipped", "current")]
    assert out["next"] is None
    finished = _run(*_argv(calls["finish"], values), stdin="")
    assert (finished["pipeline_status"], finished["halt_reason"], finished["run_dir_kept"]) == ("success", None,
                                                                                                False)
    # A tier set after that test (SF ran since) keeps TS and EX.
    os.utime(Path(values["{sidecar_path}"]) / "forge-tier.yaml", None)
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    out = _run(*_argv(calls["envelope"], {**values, "<journal>": started["journal"], "<code>": "AS"}),
               stdin=envelope("AS", drift_score="CLEAN", next_workflow=None) + "\n")
    assert ([s["code"] for s in out["skipped"]], out["gate"]["reason"], out["next"]["code"]) == (["US"], "CLEAN", "TS")


def test_the_as_gate_reads_the_journals_skill_and_the_folders_step_is_given(chain):
    """A shorter plan passes over what it holds; without the folders the skip stays at US."""
    current_skill(chain.forge, chain.skills, chain.sidecar, "cocoindex")
    folders = ("--forge-data-folder", chain.forge, "--skills-output-folder", chain.skills, "--sidecar", chain.sidecar)
    line = envelope("AS", drift_score="CLEAN", next_workflow=None)
    chain.start("AS[cocoindex] US TS")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["next"]) == (["US", "TS"], None)
    chain.start("AS[cocoindex] US SS")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["next"]["code"]) == (["US"], "SS")
    chain.start("maintain cocoindex")
    out = chain.envelope("AS", line)
    assert ([s["code"] for s in out["skipped"]], out["next"]["code"]) == (["US"], "TS")
    chain.start("maintain other")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["gate"]["reason"]) == (["US"], "CLEAN")
    # Another skill's TS and EX after them run, and so do they right after US.
    chain.start("AS[cocoindex] US TS EX TS[other] EX[other]")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["next"]["code"], out["next"]["target"]) == (
        ["US", "TS", "EX"], "TS", "other")
    chain.start("AS[cocoindex] US TS[other] EX[other]")
    out = chain.envelope("AS", line, *folders)
    assert (out["gate"]["skip"], out["gate"]["reason"]) == ("US TS EX", "current")
    assert ([s["code"] for s in out["skipped"]], out["next"]["code"], out["next"]["target"]) == (
        ["US"], "TS", "other")
    chain.start("AS[cocoindex] US[other] TS EX")
    out = chain.envelope("AS", line, *folders)
    assert (out["skipped"], out["next"]["code"], out["next"]["target"]) == ([], "US", "other")


def test_the_as_gate_reads_the_skill_as_audited_not_an_earlier_steps(chain):
    """In `TS[x] AS[y] US TS EX` AS audited y: x being current skips nothing of y's, and y being current does."""
    current_skill(chain.forge, chain.skills, chain.sidecar, "cocoindex")
    folders = ("--forge-data-folder", chain.forge, "--skills-output-folder", chain.skills, "--sidecar", chain.sidecar)
    line = envelope("AS", drift_score="CLEAN", next_workflow=None)
    chain.start("TS[cocoindex] AS[other] US TS EX")
    chain.ran("TS")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["gate"]["reason"]) == (["US"], "CLEAN")
    chain.start("TS[other] AS[cocoindex] US TS EX")
    chain.ran("TS")
    out = chain.envelope("AS", line, *folders)
    assert ([s["code"] for s in out["skipped"]], out["gate"]["reason"], out["next"]) == (
        ["US", "TS", "EX"], "current", None)


def test_pipeline_mode_documents_no_hand_copied_value_and_no_quoting_rule():
    """#1168's acceptance: step d hands the journal the envelope line, so no documented call runs the gate,
    copies a value with --set or --output, or quotes a reason by hand."""
    text = _read(PIPELINE_MODE)
    calls = re.findall(r"^\s*(uv run scripts/\S+ .+)$", text, re.M)
    assert calls and not [c for c in calls if "pipeline-gate.py" in c]
    assert not [c for c in calls if "--set" in c or "--output" in c or "'<" in c]
    assert "--reason '" not in text and "--halt-reason '" not in text
    assert "replaced by a backtick" not in text and "single quotes" not in text
    assert "pipeline-gate.py" not in text


def test_a_failed_step_call_still_leaves_this_runs_result(tmp_path):
    """A step call that fails stops the chain, and step 5's call, given the failure as the halt reason in
    its heredoc, writes this run's result: the latest record is never the previous run's."""
    calls = _pipeline_mode_calls()
    values = _documented_values(tmp_path)
    (tmp_path / "sidecar").mkdir()
    earlier = {"skill": "skf-forger", "status": "success", "run_id": "20260930T080000Z-0000beef",
               "summary": {"status": "success", "steps": [{"code": "QS"}]}}
    (tmp_path / "sidecar" / "pipeline-result-latest.json").write_bytes(json.dumps(earlier).encode("utf-8"))
    started = _run(*_argv(calls["start"], values), stdin="maintain cocoindex\n")
    values["<journal>"] = started["journal"]
    _run(*_argv(calls["envelope"], {**values, "<code>": "AS"}), stdin=envelope("AS"))
    failed = _run(*_argv(calls["envelope"], {**values, "<code>": "TS"}), stdin=envelope("TS"), rc=1)
    assert (failed["error"], failed["retry"]) == ("out-of-order", False)
    out = _run(*_argv(calls["finish"], values), stdin=failed["message"] + "\n")
    assert (out["pipeline_status"], out["halt_reason"]) == ("partial", failed["message"])
    latest = json.loads(_read(tmp_path / "sidecar" / "pipeline-result-latest.json"))
    assert latest["run_id"] == started["run_id"]
    assert [(s["code"], s["status"]) for s in latest["summary"]["steps"]] == [
        ("AS", "completed"), ("US", "halted"), ("TS", "pending"), ("EX", "pending")]


def _bash_heredoc(name: str, values: dict[str, str], body: str) -> str:
    """The documented call `name` and its heredoc as a bash script, `body` in the heredoc's place."""
    call, delimiter, _ = _heredoc_call(_read(PIPELINE_MODE), {
        "status": r"step .+?--status halted --reason -", "finish": r"finish --journal .+?--halt-reason -"}[name])
    call = call.replace("uv run scripts/pipeline-journal.py",
                        f"{shlex.quote(sys.executable)} {shlex.quote(str(SCRIPT))}", 1)
    for placeholder, value in values.items():
        call = call.replace(placeholder, value)
    return f"{call} <<'{delimiter}'\n{body}\n{delimiter}\n"


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="runs the documented call through bash")
def test_a_reason_with_shell_characters_survives_the_documented_heredoc(tmp_path):
    """#1168: the reason goes in a quoted heredoc, as given: a quote, backticks, `$( )` and a backslash
    reach the journal unchanged, and the shell runs nothing in them."""
    started = _run("start", "--run-root", str(tmp_path / "runs"), stdin="SF QS[cognee] TS EX\n")
    script = _bash_heredoc("status", {"<journal>": started["journal"]}, SHELL_REASON)
    p = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["recorded"]["reason"] == SHELL_REASON
    # The finish heredoc: empty after a step call recorded the stop, the reason itself when none did.
    for invocation, body in (("SF QS[cognee] TS EX", ""), ("QS[cognee] TS EX", SHELL_REASON)):
        journal = started["journal"] if not body else _run("start", "--run-root", str(tmp_path / "runs"),
                                                           stdin=invocation + "\n")["journal"]
        script = _bash_heredoc("finish", {"<journal>": journal, "{sidecar_path}": str(tmp_path / "sidecar")}, body)
        p = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
                           timeout=60)
        assert p.returncode == 0, p.stdout + p.stderr
        assert json.loads(p.stdout)["halt_reason"] == SHELL_REASON, invocation
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
    step = _journal_step_of_activation()
    assert "re-enters Pipeline Mode with the pending codes" not in _read(FORGER_SKILL)
    for token in ("`status` `offer`", "`halted_on`", "`route`", "Resume procedure", "`warnings`"):
        assert token in step, token
    # The script prints the route: the greeting reads no second file for it.
    assert "pipeline-contracts.md" not in step


def test_ws_gives_one_next_action_per_skill():
    """WS reads the offer through forge-status.py, which puts its route in place of the named skill's code."""
    ws = _read(FORGER_SKILL).split("- **WS**:", 1)[1].split("## Pipeline Mode", 1)[0]
    assert "a stopped pipeline's offer (the On Activation step 5 call)" in ws
    assert "one next action per skill" in ws
    assert "the resume offer first" not in ws
    assert "where a stopped pipeline's offer stands as its `route`" in ws
    status = _read(SRC / "skf-forger" / "scripts" / "forge-status.py")
    assert 'JOURNAL_SCRIPT = Path(__file__).resolve().parent / "pipeline-journal.py"' in status
    assert "journal.cmd_resume(" in status


def test_a_pick_at_invocation_runs_and_only_the_headless_flag_halts_without_one():
    """A start headless only through preferences.yaml greets and ends at the
    menu as before: the menu is a choice point, not a gate."""
    greeting = _read(FORGER_SKILL).split("6. **Greet, then dispatch or wait.**", 1)[1].split("\n", 1)[0]
    assert "dispatch the pick at once" in greeting
    halt = greeting.split("When the invocation carries `--headless` or `-H` and no pick, HARD HALT", 1)[1]
    halt = halt.split("Otherwise", 1)[0]
    assert "`/skf-forger forge-auto <repo-url> --headless`" in halt
    assert "preferences.yaml" not in halt
    assert "HARD HALT naming both forms when the invocation carries `--headless` or `-H`" in greeting
    assert "When `{headless_mode}` is true" not in greeting
    assert "`@Ferris TS cocoindex`" in _section(_read(FORGER_SKILL), "## Overview")


def test_step_6_and_the_overview_say_a_pick_dispatches():
    text = _read(FORGER_SKILL)
    assert "6. **Greet, then dispatch or wait.**" in text
    assert "otherwise Ferris greets and waits for a pick" in _section(text, "## Overview")


def test_the_persona_rule_is_stated_once():
    text = _read(FORGER_SKILL)
    assert text.count("Maintain this persona across all skill invocations") == 1
    assert "applying your persona" not in text and "holding one persona" not in text


def test_a_chain_loads_the_run_procedure_alone():
    """#1167: the journal prints each entry's skill and inputs, so neither SKILL.md nor the run
    procedure sends a chain into pipeline-contracts.md."""
    text = _read(PIPELINE_MODE)
    assert "pipeline-contracts" not in text and "Data Flow" not in text
    skill = _read(FORGER_SKILL)
    section = _section(skill, "## Pipeline Mode")
    assert "load `references/pipeline-mode.md` (the run procedure), then follow it" in section
    assert "pipeline-contracts.md" not in section
    conventions = _section(skill, "## Conventions")
    assert skill.count("pipeline-contracts.md") == conventions.count("pipeline-contracts.md") == 1


def test_pipeline_mode_leaves_the_contracts_to_the_contracts_file():
    text = _read(PIPELINE_MODE)
    for gone in ("This file covers the run procedure", "It tokenizes", "**`AN` with `CS`:**",
                 "**`TS` followed by `EX`:**", "{YYYYMMDD-HHmmss}", "UTC timestamp", "in a second call",
                 "the Repair Routes entry", "For a repair only the user can make"):
        assert gone not in text, gone
    assert "tracks pipeline state in memory" not in _read(CONTRACTS)
    assert "Only the alias names need recognizing here" not in _read(FORGER_SKILL)
