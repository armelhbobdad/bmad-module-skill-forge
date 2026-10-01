#!/usr/bin/env python3
"""Tests for skf-quick-batch.py, the on-disk state of a skf-quick-skill --batch run.

The batch file grammar is tested against the Input format example of
skf-quick-skill's references/batch-mode.md, and the summary file and the
event lines against its schema block and event formats, so the helper and
the page the agent reads cannot drift apart. Each subcommand runs in-process on a
temporary run folder; the outcome of a halted target is checked against
the exit code the shared emitter gives the same staged halt.json, and a
whole batch runs once through the script as a program.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-quick-batch.py"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
SCHEMA = SCRIPTS / "schemas" / "skf-quick-skill-result-envelope.v1.json"
BATCH_MODE = REPO / "src" / "skf-quick-skill" / "references" / "batch-mode.md"

spec = importlib.util.spec_from_file_location("skf_quick_batch", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _exit_codes() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]["exit_codes"]


def _run(capsys, *argv) -> tuple[int, dict | None, str]:
    """main() in-process: (exit code, stdout JSON or None, stderr)."""
    code = mod.main(list(argv))
    out, err = capsys.readouterr()
    return code, (json.loads(out) if out.strip() else None), err


def _stage(folder: Path, name: str, payload: dict) -> None:
    (folder / name).write_text(json.dumps(payload), encoding="utf-8")


def _halt(folder: Path, reason: str = "resolution-failure", package=None) -> None:
    _stage(folder, "halt.json", {"phase": "resolve-target", "halt_reason": reason, "reason": "it halted",
                                 "skill_package": package})


def _success(folder: Path, score=90, package="/skills/x/1.0.0/x") -> None:
    _stage(folder, "result-context.json", {"status": "success", "skill_package": package,
                                           "summary": {"quality_score": score}})


@pytest.fixture()
def batch(tmp_path):
    """A batch file of three targets and an empty batch run folder."""
    file = tmp_path / "targets.txt"
    file.write_text("lodash\ncognee@0.5.0 language=python\nhttps://github.com/foo/bar\n", encoding="utf-8")
    run_dir = tmp_path / ".skf-run" / "skf-quick-skill-ab12cd34"
    run_dir.mkdir(parents=True)
    return file, run_dir


# --------------------------------------------------------------------------
# The batch file grammar
# --------------------------------------------------------------------------


def _documented_example() -> str:
    """The example batch file batch-mode.md's Input format section shows."""
    section = BATCH_MODE.read_text(encoding="utf-8").split("## Input format", 1)[1].split("## Execution", 1)[0]
    [block] = re.findall(r"^```\n(.*?)^```$", section, flags=re.M | re.S)
    return block


def test_the_documented_example_parses_as_batch_mode_says():
    targets = mod.parse_text(_documented_example())
    assert [(t["batch"], t["target"], t["language_hint"], t["scope_hint"]) for t in targets] == [
        (1, "lodash", None, None),
        (2, "@vercel/og", None, None),
        (3, "cognee@0.5.0", None, None),
        (4, "https://github.com/foo/bar", None, None),
        (5, "https://github.com/foo/bar@2.1.0-beta", None, None),
        (6, "lodash", "javascript", "src/"),
        (7, "cognee@0.5.0", "python", "cognee/api/"),
    ]


def test_the_documented_modifiers_are_the_helpers():
    section = BATCH_MODE.read_text(encoding="utf-8").split("Recognised per-line modifiers:", 1)[1]
    rows = re.findall(r"^\| `([a-z]+)=<[a-z]+>` \| Sets `([a-z_]+)`", section, flags=re.M)
    assert dict(rows) == mod.MODIFIERS


@pytest.mark.parametrize("line, expected", [
    ("  lodash  ", ("lodash", None, None)),
    ("requests==2.31.0", ("requests==2.31.0", None, None)),  # the version stays: parse-target splits it
    ("next@canary scope=packages/next", ("next@canary", None, "packages/next")),
    ("lodash LANGUAGE=javascript Scope=src/", ("lodash", "javascript", "src/")),
    ("lodash scope=src/a=b", ("lodash", None, "src/a=b")),
    ("lodash language=", ("lodash language=", None, None)),
    ("lodash language=js language=ts", ("lodash language=js language=ts", None, None)),
    ("lodash langauge=js", ("lodash langauge=js", None, None)),
    ("I want a skill for onboarding", ("I want a skill for onboarding", None, None)),
    ("lodash # a comment", ("lodash # a comment", None, None)),
], ids=["spaces", "pypi-pin", "dist-tag-scope", "key-case", "value-with-equals", "empty-value",
        "repeated-modifier", "misspelled-modifier", "prose", "trailing-comment"])
def test_a_line_is_a_target_and_its_modifiers(line, expected):
    [entry] = mod.parse_text(line)
    assert (entry["target"], entry["language_hint"], entry["scope_hint"]) == expected


@pytest.mark.parametrize("line", ["", "   ", "# comment", "   # indented comment", "\t#tab"],
                         ids=["empty", "blank", "comment", "indented-comment", "tab-comment"])
def test_blank_and_comment_lines_are_skipped(line):
    assert mod.parse_text(line) == []


def test_crlf_and_a_byte_order_mark_are_read(tmp_path, capsys):
    file = tmp_path / "targets.txt"
    file.write_bytes(b"\xef\xbb\xbflodash\r\n# c\r\nnumpy language=python\r\n")
    code, out, _ = _run(capsys, "parse", str(file))
    assert code == 0
    assert [(t["batch"], t["target"], t["language_hint"]) for t in out["targets"]] == [
        (1, "lodash", None), (2, "numpy", "python")]


def test_an_unreadable_batch_file_is_refused(tmp_path, capsys):
    code, out, err = _run(capsys, "parse", str(tmp_path / "missing.txt"))
    assert (code, out) == (1, None)
    assert "cannot be read" in json.loads(err)["message"]
    bad = tmp_path / "latin1.txt"
    bad.write_bytes(b"caf\xe9\n")
    code, out, err = _run(capsys, "parse", str(bad))
    assert (code, out) == (1, None)
    assert "not UTF-8" in json.loads(err)["message"]


# --------------------------------------------------------------------------
# start and next
# --------------------------------------------------------------------------


def test_start_writes_every_target_pending(batch, capsys):
    file, run_dir = batch
    code, out, _ = _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    assert code == 0
    assert out == {"status": "running", "input_file": str(file), "fail_fast": False, "targets_total": 3,
                   "recorded": 0, "resumed": False}
    lines = [json.loads(line) for line in (run_dir / "batch.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["event"] == "start" and lines[0]["status"] == "running"
    assert [(e["event"], e["batch"], e["status"]) for e in lines[1:]] == [
        ("target", 1, "pending"), ("target", 2, "pending"), ("target", 3, "pending")]


def test_start_again_on_the_same_file_changes_nothing(batch, capsys, monkeypatch):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _run(capsys, "next", "--run-dir", str(run_dir))
    _halt(run_dir / f"{run_dir.name}-1")
    _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    before = (run_dir / "batch.jsonl").read_text(encoding="utf-8")
    monkeypatch.chdir(file.parent)  # the same file, named relative to the working folder
    code, out, _ = _run(capsys, "start", file.name, "--run-dir", str(run_dir))
    assert code == 0 and (out["resumed"], out["recorded"], out["targets_total"]) == (True, 1, 3)
    assert (run_dir / "batch.jsonl").read_text(encoding="utf-8") == before


def test_start_refuses_a_run_folder_that_holds_another_batch(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    other = tmp_path / "other.txt"
    other.write_text("numpy\n", encoding="utf-8")
    code, out, err = _run(capsys, "start", str(other), "--run-dir", str(run_dir))
    assert (code, out) == (1, None)
    refusal = json.loads(err)
    assert "a run folder of its own" in refusal["message"] and refusal["halt_reason"] == "input-invalid"


def test_a_refused_start_names_the_halt_the_batch_stops_with(tmp_path, capsys):
    """batch-mode.md §1 halts with the halt_reason start names: 4 for a folder it cannot write, else 2."""
    code, out, err = _run(capsys, "start", str(tmp_path / "missing.txt"), "--run-dir", str(tmp_path / "run"))
    assert (code, out) == (1, None)
    unreadable = json.loads(err)
    assert unreadable["halt_reason"] == "input-invalid" and "cannot be read" in unreadable["message"]
    file = tmp_path / "targets.txt"
    file.write_text("lodash\n", encoding="utf-8")
    blocker = tmp_path / "a-file"
    blocker.write_text("", encoding="utf-8")
    code, out, err = _run(capsys, "start", str(file), "--run-dir", str(blocker / "skf-quick-skill-x"))
    assert (code, out) == (1, None)
    unwritable = json.loads(err)
    assert unwritable["halt_reason"] == "write-failure" and "cannot be written" in unwritable["message"]
    codes = _exit_codes()
    assert (codes[unreadable["halt_reason"]], codes[unwritable["halt_reason"]]) == (2, 4)


def test_start_keeps_the_absolute_path_so_another_working_folder_resumes(tmp_path, capsys, monkeypatch):
    first, second = tmp_path / "a", tmp_path / "b"
    (first / "lists").mkdir(parents=True)
    second.mkdir()
    file = first / "lists" / "targets.txt"
    file.write_text("lodash\n", encoding="utf-8")
    run_dir = tmp_path / "skf-quick-skill-rel"
    monkeypatch.chdir(first)
    code, out, _ = _run(capsys, "start", "lists/targets.txt", "--run-dir", str(run_dir))
    assert code == 0 and out["input_file"] == str(file)
    monkeypatch.chdir(second)
    code, out, _ = _run(capsys, "start", "../a/lists/targets.txt", "--run-dir", str(run_dir))
    assert code == 0 and out["resumed"] is True and out["input_file"] == str(file)
    _finish(run_dir, capsys, ["success"])
    _, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert json.loads(Path(event["summary_path"]).read_text(encoding="utf-8"))["input_file"] == str(file)


def test_next_hands_out_each_pending_target_with_its_own_run_folder(batch, capsys):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    code, out, err = _run(capsys, "next", "--run-dir", str(run_dir))
    assert code == 0
    folder = run_dir / "skf-quick-skill-ab12cd34-1"
    assert out == {"status": "next", "batch": 1, "target": "lodash", "language_hint": None, "scope_hint": None,
                   "run_dir": folder.as_posix()}
    assert err == '{"batch":1,"target":"lodash","status":"start"}\n', "next prints the target's start event"
    assert folder.is_dir() and not any(folder.iterdir())
    # Until it is recorded, the same target comes back, its folder emptied (a restart).
    (folder / "decision.json").write_text("{}", encoding="utf-8")
    code, again, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert again == out and not any(folder.iterdir())
    _success(folder)
    _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    _, second, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert (second["batch"], second["target"], second["language_hint"]) == (2, "cognee@0.5.0", "python")


@pytest.mark.parametrize("staged", ["halt.json", "result-context.json"])
def test_next_sends_an_ended_target_to_record_instead_of_running_it_again(batch, capsys, staged):
    """A compaction between a target's envelope and record: next never empties a staged payload."""
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _, out, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    folder = Path(out["run_dir"])
    (_halt if staged == "halt.json" else _success)(folder)
    code, again, err = _run(capsys, "next", "--run-dir", str(run_dir))
    assert (code, again, err) == (0, {"status": "record", "batch": 1}, "")
    assert (folder / staged).is_file(), "the staged payload stays for record"
    _, event, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    assert event["status"] == ("fail" if staged == "halt.json" else "done")
    _, second, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert (second["status"], second["batch"]) == ("next", 2)


def test_next_is_done_when_no_target_is_pending(tmp_path, capsys):
    file = tmp_path / "empty.txt"
    file.write_text("# nothing to do\n", encoding="utf-8")
    run_dir = tmp_path / "skf-quick-skill-empty"
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    code, out, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert (code, out) == (0, {"status": "done", "fail_fast_triggered": False})


def test_next_without_a_started_batch_is_refused(tmp_path, capsys):
    code, out, err = _run(capsys, "next", "--run-dir", str(tmp_path))
    assert (code, out) == (1, None) and "run start first" in json.loads(err)["message"]


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def _started(batch, capsys, *extra) -> tuple[Path, Path]:
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir), *extra)
    _run(capsys, "next", "--run-dir", str(run_dir))
    return run_dir, run_dir / f"{run_dir.name}-1"


@pytest.mark.parametrize("reason", sorted(_exit_codes()))
def test_a_halt_is_recorded_with_the_exit_code_its_reason_maps_to(batch, capsys, reason):
    run_dir, folder = _started(batch, capsys)
    _halt(folder, reason, package="/skills/lodash/1.0.0/lodash" if reason == "write-failure" else None)
    code, event, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    expected = _exit_codes()[reason]
    assert code == 0
    assert event == {"batch": 1, "target": "lodash", "status": "fail", "exit": expected, "error_code": reason}
    state = mod.load(run_dir)
    assert state["results"][1]["exit_code"] == expected
    assert folder.is_dir(), "a halted target keeps its run folder"


def test_a_success_is_recorded_with_its_score_and_its_folder_removed(batch, capsys):
    run_dir, folder = _started(batch, capsys)
    _success(folder, score=87.5, package="/skills/lodash/4.17.21/lodash")
    code, event, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    assert (code, event) == (0, {"batch": 1, "target": "lodash", "status": "done", "exit": 0})
    result = mod.load(run_dir)["results"][1]
    assert (result["status"], result["quality_score"], result["skill_package"]) == (
        "success", 87.5, "/skills/lodash/4.17.21/lodash")
    assert not folder.exists()


def test_recording_twice_prints_the_same_event(batch, capsys):
    run_dir, folder = _started(batch, capsys)
    _halt(folder)
    first = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    lines = (run_dir / "batch.jsonl").read_text(encoding="utf-8")
    assert _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1") == first
    assert (run_dir / "batch.jsonl").read_text(encoding="utf-8") == lines


@pytest.mark.parametrize("setup, needle", [
    (lambda folder: None, "staged neither halt.json nor result-context.json"),
    (lambda folder: (folder / "halt.json").write_text("{not json", encoding="utf-8"), "holds no JSON object"),
    (lambda folder: _halt(folder, "no-such-reason"), "maps to no exit code"),
], ids=["nothing-staged", "broken-json", "unknown-reason"])
def test_record_refuses_what_it_cannot_read(batch, capsys, setup, needle):
    run_dir, folder = _started(batch, capsys)
    setup(folder)
    code, out, err = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    assert (code, out) == (1, None) and needle in json.loads(err)["message"]


def test_record_refuses_a_number_the_batch_does_not_hold(batch, capsys):
    run_dir, _ = _started(batch, capsys)
    code, out, err = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "9")
    assert (code, out) == (1, None) and "has no target 9" in json.loads(err)["message"]


def test_the_recorded_exit_code_is_the_emitters(batch, capsys):
    """record and the shared emitter read one halt.json into one exit code."""
    run_dir, folder = _started(batch, capsys)
    _halt(folder, "not-skf-output")
    proc = subprocess.run([sys.executable, str(EMITTER), "emit-halt", "--workflow", "skf-quick-skill",
                           "--run-dir", str(folder)], input=(folder / "halt.json").read_bytes(),
                          capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout.decode("utf-8").split("SKF_QUICK_SKILL_RESULT_JSON: ", 1)[1])
    _, event, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    assert event["exit"] == envelope["exit_code"] == 9
    assert event["error_code"] == envelope["halt_reason"] == envelope["error"]["code"]


def test_a_torn_last_line_is_skipped_and_the_next_outcome_kept(batch, capsys):
    run_dir, folder = _started(batch, capsys)
    with open(run_dir / "batch.jsonl", "ab") as fh:
        fh.write(b'{"event":"result","batch":1,"tar')  # a write cut short, no newline
    assert 1 not in mod.load(run_dir)["results"]
    _halt(folder)
    code, event, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    assert code == 0 and event["status"] == "fail"
    # The outcome starts a line of its own, so it is saved: next never hands target 1 out again.
    assert mod.load(run_dir)["results"][1]["status"] == "error"
    _, nxt, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert (nxt["status"], nxt["batch"]) == ("next", 2)
    assert (folder / "halt.json").is_file(), "the halted target's run folder is kept"


# --------------------------------------------------------------------------
# summarize
# --------------------------------------------------------------------------


def _finish(run_dir: Path, capsys, outcomes) -> None:
    """Run each pending target to the outcome given for it, in order."""
    for outcome in outcomes:
        _, nxt, _ = _run(capsys, "next", "--run-dir", str(run_dir))
        if nxt["status"] == "done":
            return
        folder = Path(nxt["run_dir"])
        if outcome == "success":
            _success(folder)
        else:
            _halt(folder, outcome)
        _run(capsys, "record", "--run-dir", str(run_dir), "--batch", str(nxt["batch"]))


@pytest.mark.parametrize("outcomes, status, exit_code", [
    (["success", "success", "success"], "success", 0),
    (["resolution-failure", "success", "not-skf-output"], "partial", 9),
    (["write-failure", "resolution-failure", "user-cancelled"], "failed", 6),
], ids=["all-succeed", "some-fail", "all-fail"])
def test_summarize_counts_and_takes_the_highest_failed_code(batch, capsys, tmp_path, outcomes, status, exit_code):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, outcomes)
    out_dir = tmp_path / "skills" / "_batch"
    code, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(out_dir))
    failed = sum(o != "success" for o in outcomes)
    assert code == 0
    assert {k: event[k] for k in ("batch_summary", "targets_total", "succeeded", "failed", "status",
                                  "fail_fast_triggered", "exit_code")} == {
        "batch_summary": True, "targets_total": 3, "succeeded": 3 - failed, "failed": failed,
        "status": status, "fail_fast_triggered": False, "exit_code": exit_code}
    summary = json.loads(Path(event["summary_path"]).read_text(encoding="utf-8"))
    assert summary == json.loads((out_dir / "quick-skill-batch-latest.json").read_text(encoding="utf-8"))
    assert (summary["skill"], summary["mode"], summary["status"], summary["exit_code"]) == (
        "skf-quick-skill", "batch", status, exit_code)
    assert summary["input_file"] == str(file)
    assert [r["batch"] for r in summary["results"]] == [1, 2, 3]
    assert set(summary["results"][0]) == {"batch", "target", "status", "exit_code", "skill_package",
                                          "error_code", "quality_score"}
    for result, outcome in zip(summary["results"], outcomes):
        if outcome == "success":
            assert (result["status"], result["quality_score"], result["error_code"]) == ("success", 90, None)
        else:
            assert (result["status"], result["error_code"], result["exit_code"]) == (
                "error", outcome, _exit_codes()[outcome])
    assert run_dir.exists() == (failed > 0), "the batch run folder is kept only when a target halted"


def test_a_batch_with_no_target_ends_at_once_as_a_success(tmp_path, capsys):
    """batch-mode.md: an empty batch file is a success, targets_total 0 and exit code 0."""
    file = tmp_path / "empty.txt"
    file.write_text("# nothing to do\n\n", encoding="utf-8")
    run_dir = tmp_path / "skf-quick-skill-empty"
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    assert _run(capsys, "next", "--run-dir", str(run_dir))[1] == {"status": "done", "fail_fast_triggered": False}
    code, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert code == 0
    assert (event["status"], event["targets_total"], event["succeeded"], event["failed"], event["exit_code"]) == (
        "success", 0, 0, 0, 0)
    assert json.loads(Path(event["summary_path"]).read_text(encoding="utf-8"))["results"] == []
    rule = BATCH_MODE.read_text(encoding="utf-8").split("`status` resolves as:", 1)[1].split("\n", 1)[0]
    assert "a batch file with no target included (it ends at once, `targets_total` 0 and exit code `0`)" in rule


def _documented_summary() -> dict:
    """The JSON block batch-mode.md's Batch summary contract shows as the schema."""
    section = BATCH_MODE.read_text(encoding="utf-8").split("## Batch summary contract", 1)[1]
    [block] = re.findall(r"^```json\n(.*?)^```$", section.split("## Headless events", 1)[0], flags=re.M | re.S)
    return json.loads(block)


def _documented_status(failed: int, succeeded: int) -> list[str]:
    """The statuses batch-mode.md's rule gives these counts, read from its `"<status>"` when `<test>` clauses."""
    rule = BATCH_MODE.read_text(encoding="utf-8").split("`status` resolves as:", 1)[1].split("\n", 1)[0]
    counts, ops = {"failed": failed, "succeeded": succeeded}, {"==": int.__eq__, ">": int.__gt__}
    matched = []
    for status, test in re.findall(r'`"([a-z]+)"` when `([^`]+)`', rule):
        terms = [re.fullmatch(r"(failed|succeeded) (==|>) (\d+)", term) for term in test.split(" && ")]
        assert all(terms), test
        if all(ops[op](counts[name], int(n)) for name, op, n in (t.groups() for t in terms)):
            matched.append(status)
    return matched


@pytest.mark.parametrize("outcomes", [[], ["success"], ["success", "write-failure"], ["user-cancelled"]],
                         ids=["empty", "all-succeed", "some-fail", "all-fail"])
def test_the_status_is_the_one_the_documented_rule_gives(tmp_path, capsys, outcomes):
    file = tmp_path / "targets.txt"
    file.write_text("".join(f"target-{n}\n" for n in range(len(outcomes))), encoding="utf-8")
    run_dir = tmp_path / "skf-quick-skill-rule"
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, outcomes)
    _, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert _documented_status(event["failed"], event["succeeded"]) == [event["status"]]


def test_the_summary_file_has_the_documented_keys(batch, capsys, tmp_path):
    """The schema block of batch-mode.md and the record summarize writes keep one shape."""
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, ["success", "resolution-failure", "success"])
    _, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    written = json.loads(Path(event["summary_path"]).read_text(encoding="utf-8"))
    documented = _documented_summary()
    assert list(written) == list(documented)
    assert [list(r) for r in written["results"]] == [list(documented["results"][0])] * 3
    assert {r["status"] for r in written["results"]} <= set(documented["results"][0]["status"].split(" | "))
    assert written["status"] in documented["status"].split(" | ")


def test_fail_fast_stops_at_the_first_failure(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir), "--fail-fast")
    _finish(run_dir, capsys, ["success", "write-failure", "success"])
    code, nxt, _ = _run(capsys, "next", "--run-dir", str(run_dir))
    assert nxt == {"status": "done", "fail_fast_triggered": True}
    code, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "out"))
    assert (event["targets_total"], event["succeeded"], event["failed"], event["status"],
            event["fail_fast_triggered"], event["exit_code"]) == (2, 1, 1, "partial", True, 4)


def test_fail_fast_on_the_last_target_triggers_nothing(tmp_path, capsys):
    file = tmp_path / "one.txt"
    file.write_text("lodash\n", encoding="utf-8")
    run_dir = tmp_path / "skf-quick-skill-one"
    _run(capsys, "start", str(file), "--run-dir", str(run_dir), "--fail-fast")
    _finish(run_dir, capsys, ["resolution-failure"])
    _, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "out"))
    assert (event["status"], event["fail_fast_triggered"], event["exit_code"]) == ("failed", False, 3)


def test_summarize_refuses_while_targets_are_pending(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, ["success"])
    code, out, err = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert (code, out) == (1, None) and "2 target(s) of the batch are still pending" in json.loads(err)["message"]


def test_summarize_twice_prints_the_same_event(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, ["resolution-failure", "success", "success"])
    first = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o")) == first
    assert len(list((tmp_path / "o").glob("quick-skill-batch-2*.json"))) == 1


def test_a_removed_batch_folder_names_its_summary(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, ["success", "success", "success"])
    _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    code, out, err = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    assert (code, out) == (1, None)
    assert (tmp_path / "o" / "quick-skill-batch-latest.json").as_posix() in json.loads(err)["message"]


def test_two_batches_that_end_in_one_second_keep_both_summaries(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(mod.time, "time", lambda: 1_790_000_000.0)
    paths = []
    for name in ("a", "b"):
        file = tmp_path / f"{name}.txt"
        file.write_text("lodash\n", encoding="utf-8")
        run_dir = tmp_path / f"skf-quick-skill-{name}"
        _run(capsys, "start", str(file), "--run-dir", str(run_dir))
        _finish(run_dir, capsys, ["success"])
        _, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
        paths.append(Path(event["summary_path"]).name)
    stamp = mod._utc(1_790_000_000.0)[1]
    assert paths == [f"quick-skill-batch-{stamp}.json", f"quick-skill-batch-{stamp}-2.json"]


def test_a_summary_that_cannot_be_written_keeps_the_batch_file(batch, capsys, tmp_path):
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _finish(run_dir, capsys, ["success", "success", "success"])
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("", encoding="utf-8")
    code, event, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(blocker))
    assert code == 0 and event["summary_path"] is None
    assert event["warnings"][0].startswith("summary_write_failed:")
    assert (run_dir / "batch.jsonl").is_file(), "with no summary file, the batch file is the only record"


# --------------------------------------------------------------------------
# The events and the CLI
# --------------------------------------------------------------------------


def _documented_events() -> list[str]:
    section = BATCH_MODE.read_text(encoding="utf-8").split("## Headless events", 1)[1].split("## Exit code", 1)[0]
    return [line for block in re.findall(r"^```\n(.*?)^```$", section, flags=re.M | re.S)
            for line in block.splitlines()]


def _keys(line: str) -> list[str]:
    return re.findall(r'"([a-z_]+)":', line)


def test_the_printed_events_have_the_documented_keys(batch, capsys, tmp_path):
    documented = {tuple(_keys(line)) for line in _documented_events()}
    file, run_dir = batch
    _run(capsys, "start", str(file), "--run-dir", str(run_dir))
    _, nxt, start_line = _run(capsys, "next", "--run-dir", str(run_dir))
    start = json.loads(start_line)
    _halt(Path(nxt["run_dir"]))
    _, fail, _ = _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
    _finish(run_dir, capsys, ["success", "success"])
    _, summary, _ = _run(capsys, "summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"))
    code = mod.main(["record", "--run-dir", str(run_dir), "--batch", "2"])
    done = json.loads(capsys.readouterr().out)
    assert code == 0
    for event in (start, fail, done, summary):
        assert tuple(event) in documented, event


@pytest.mark.parametrize("cmd", ["record", "summarize"])
def test_target_stderr_prints_the_event_on_stderr(batch, capsys, tmp_path, cmd):
    """batch-mode.md §3 and §4 pass --target stderr: the helper prints the event, the agent types none."""
    run_dir, folder = _started(batch, capsys)
    _halt(folder)
    if cmd == "summarize":
        _run(capsys, "record", "--run-dir", str(run_dir), "--batch", "1")
        _finish(run_dir, capsys, ["success", "success"])
        argv = ["summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o")]
    else:
        argv = ["record", "--run-dir", str(run_dir), "--batch", "1"]
    code = mod.main([*argv, "--target", "stderr"])
    out, err = capsys.readouterr()
    assert (code, out) == (0, "")
    assert json.loads(err) == _run(capsys, *argv)[1], "the same line the default prints on stdout"
    assert err.count("\n") == 1


def test_the_script_runs_a_batch_as_a_program(batch, tmp_path):
    """The calls batch-mode.md makes, in order: each result and event is one compact ASCII line."""
    file, run_dir = batch

    def line(raw: bytes) -> dict:
        text = raw.decode("ascii")
        value = json.loads(text)
        assert text.rstrip("\r\n") == json.dumps(value, separators=(",", ":")), "one compact ASCII line"
        return value

    def run(*argv) -> tuple[dict | None, dict | None]:
        proc = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr
        return (line(proc.stdout) if proc.stdout else None), (line(proc.stderr) if proc.stderr else None)

    run("start", str(file), "--run-dir", str(run_dir))
    for n in (1, 2, 3):
        nxt, start = run("next", "--run-dir", str(run_dir))
        assert nxt["batch"] == n and start == {"batch": n, "target": nxt["target"], "status": "start"}
        _success(Path(nxt["run_dir"]))
        out, done = run("record", "--run-dir", str(run_dir), "--batch", str(n), "--target", "stderr")
        assert out is None and done["status"] == "done"
    out, summary = run("summarize", "--run-dir", str(run_dir), "--output-dir", str(tmp_path / "o"),
                       "--target", "stderr")
    assert out is None and (summary["status"], summary["exit_code"]) == ("success", 0)


def test_a_bad_argument_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        mod.main(["record", "--run-dir", "x", "--batch", "one"])
    assert exc.value.code == 2
