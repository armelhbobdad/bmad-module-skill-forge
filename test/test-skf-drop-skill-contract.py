#!/usr/bin/env python3
"""Drop Skill contract: the halt on a failed manifest write (#585), the envelope
the shared emitter builds (#593), the version input and the helpers resolved
before the first prompt (#594), the version counts from the inventory
helper (#597), the customization surface without `default_mode` and with a
fail-closed purge guard (#596), the headless contract in one file outside
SKILL.md (#600), a whole-skill deprecate that keeps the manifest entry, and
the w3 re-check findings (#591, #600): the roster from one helper call, no
roster for a named target, the degraded outcomes as warnings, an interactive
HALT that leaves no run folder and the lean stage files.

Step prose is not executed by any test, so these checks run the commands the
drop steps document, filled in as an agent fills them, against fixtures:

- skf-emit-result-envelope.py builds every SKF_DROP_SKILL_RESULT_JSON line from
  schemas/skf-drop-skill-result-envelope.v1.json. The halt, dry-run and
  success payloads the steps stage go through the documented commands, and
  each line validates against the schema under jsonschema. Every HALT site's
  exit code is the one the schema maps its halt_reason to, every emitting HALT
  names its phase, and the contract lists the schema's halt reasons. The
  headless auto-decisions select.md records reach the result record.
- drop-roster.py, the roster select.md reads in one call, gives the counts the
  active-version guard and the blast-radius line read, and the version the
  guard's refusal names to keep (`keep_candidate`); skf-update-active-symlink.py
  repair-after-drop, execute.md's documented call, points `active` at the
  version the same rule picks after a version purge, and only when the link
  names the purged version (#1158). test-skf-drop-roster.py tests the roster
  helper itself.
- The active-version guard's refusal names a recovery that works (step 5b
  gate run 3, enhancement-3, #1172): Export Skill with `--version` and the
  version to keep, so the commands its load and manifest steps document run
  over the fixture with that version: the export points `active` at it,
  publishes it and archives the refused version, and the roster then lets the
  drop through.
- The prose pins: a failed manifest write halts in every mode and never reaches
  the report; `skill_name` and `version` answer their gates in both modes; the
  helpers resolve before the first prompt, each stage declares the probe
  order of every helper it runs for a binding a compaction dropped (#1116),
  and no step keeps an in-prompt fallback for them; no stage reads
  version-paths.md, types an envelope or makes up a timestamp; the mode comes
  only from the `mode` argument or the prompt.
- skf-manifest-ops.py runs the skill-level manifest calls execute.md documents:
  a whole-skill deprecate marks every version deprecated and keeps the entry,
  and only a purge removes it.
- A repair the helper cannot make (#732) is recorded as `active_link_dangling`
  with the helper's `manual_fix`, or, when it prints no JSON, with the one
  fix execute.md states, which runs `skf-atomic-write.py flip-link` and also
  works on native Windows without symlink rights (#735); the guard refusal's
  recovery, Export Skill's `--version`, runs the same command.
- No step decides in the prompt what a helper computes (#1158): execute.md
  rebuilds the context files with one `rebuild` call (each file with its own
  skill root), checks the final state with `drop-roster.py verify`, and
  report.md lists the remaining versions from the roster; SKILL.md binds the
  headless-purge guard from `drop-roster.py activation`.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
DROP = SRC / "skf-drop-skill"
SKILL = "src/skf-drop-skill/SKILL.md"
SELECT = "src/skf-drop-skill/references/select.md"
EXECUTE = "src/skf-drop-skill/references/execute.md"
REPORT = "src/skf-drop-skill/references/report.md"
CUSTOMIZE = "src/skf-drop-skill/customize.toml"
# The one contract file: the Invocation Contract, Exit Codes, Result Contract
# and Halt Envelope lifted out of SKILL.md (the old headless-contract.md).
CONTRACT = "src/skf-drop-skill/references/invocation-contract.md"
CONTRACTS = (CONTRACT,)
SCRIPTS = SRC / "shared" / "scripts"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
ROSTER = DROP / "scripts" / "drop-roster.py"
MANIFEST_OPS = SCRIPTS / "skf-manifest-ops.py"
# Export Skill's steps, which the active-version guard's recovery runs.
EXPORT_LOAD = "src/skf-export-skill/references/load-skill.md"
EXPORT_UPDATE = "src/skf-export-skill/references/update-context.md"
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-drop-skill-result-envelope.v1.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
SETTINGS = SCHEMA["$defs"]["skf-envelope"]["const"]
PREFIX = "SKF_DROP_SKILL_RESULT_JSON: "
# A HALT site: "exit code 2, `halt_reason: ...`", "exit code 6 and `halt_reason: ...`"
# or "exit code 6 (`halt_reason: ...`".
HALT_SITE = re.compile(r'exit code (\d+)(?:,| and| \() ?`halt_reason: "([a-z-]+)"`')
PER_RUN_NAME = re.compile(r"drop-skill-result-\d{8}-\d{6}(-\d+)?\.json")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` (which occurs once) up to marker `end`."""
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _contract_text(*, with_skill: bool) -> str:
    """The contract file, SKILL.md first when `with_skill`."""
    rels = ((SKILL,) if with_skill else ()) + CONTRACTS
    return "\n".join(_read(rel) for rel in rels)


def _exit_codes_table() -> str:
    """The Exit Codes table of the invocation contract."""
    text = _read(CONTRACT)
    m = re.search(r"^#+ Exit Codes\n(.*?)(?=^#+ |\Z)", text, flags=re.M | re.S)
    assert m, "no Exit Codes section"
    return m.group(1)


def _fenced(text: str, lang: str) -> list[str]:
    """The ```<lang> blocks of `text`, each dedented to its fence's indentation."""
    blocks = []
    for m in re.finditer(r"^( *)```" + lang + r"\n(.*?)^\1```", text, flags=re.M | re.S):
        indent = len(m.group(1))
        blocks.append("\n".join(line[indent:] for line in m.group(2).split("\n")))
    return blocks


def _one_command(text: str, needle: str) -> str:
    """The one fenced bash command line of `text` that holds `needle`."""
    lines = [line.strip() for block in _fenced(text, "bash") for line in block.split("\n")
             if needle in line]
    assert len(lines) == 1, f"expected one bash line holding {needle!r}, found {lines}"
    return lines[0]


def _argv(command: str, values: dict) -> list[str]:
    """Fill a documented `uv run {helper} ...` or `python3 {helper} ...` command in and split it, without a shell.

    Placeholders become sentinels before the words are split, so a Windows path
    keeps its backslashes; `uv run` or `python3` becomes this interpreter.
    """
    words = []
    for word in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", command)):
        words.append(re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], word))
    prefix = 1 if words[0] == "python3" else 2
    assert words[:prefix] in (["python3"], ["uv", "run"]), words
    return [sys.executable, *words[prefix:]]


def _run(command: str, values: dict, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a documented command; `< "<path>"` becomes the process's stdin."""
    command, _, source = command.partition(" < ")
    if source:
        path = re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], source.strip().strip('"'))
        stdin = Path(path).read_bytes()
    return subprocess.run(_argv(command, values), input=stdin, capture_output=True, timeout=60)


def _fill_json(template: str, values: dict):
    """Fill a JSON template from the prose: `"{name ...}"` gets a string, `{name ...}` any JSON value.

    Each placeholder is looked up by its first word, so `{affected_directories
    when drop_mode is purge, else []}` reads `values["affected_directories"]`.
    """
    def value(m):
        return json.dumps(values[m.group(1).split()[0]])

    text = re.sub(r'"\{([^{}"]+)\}"', value, template)
    return json.loads(re.sub(r"\{([^{}\"]+)\}", value, text))


def _envelope(stream: bytes) -> dict:
    [line] = stream.decode("utf-8").splitlines()
    assert line.startswith(PREFIX), line
    envelope = json.loads(line[len(PREFIX):])
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(envelope), key=str)
    assert not errors, [e.message for e in errors]
    return envelope


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-drop-skill-Ab3dE5gH"
    run_dir.mkdir(parents=True)
    return run_dir


# --------------------------------------------------------------------------
# The envelope: one schema, the emitter, and the halt reasons every site uses
# --------------------------------------------------------------------------

def test_contract_lists_the_schema_halt_reasons():
    contract = _contract_text(with_skill=False)
    rule = next(line for line in contract.splitlines() if line.startswith("- `halt_reason`"))
    listed = set(re.findall(r'"([a-z-]+)"', rule))
    in_schema = {r for r in SCHEMA["properties"]["halt_reason"]["enum"] if r is not None}
    assert listed == in_schema == set(SETTINGS["exit_codes"])


def test_contract_template_has_the_schema_fields_in_order():
    contract = _contract_text(with_skill=False)
    line = next(line for line in contract.splitlines() if line.startswith(PREFIX))
    template = json.loads(line[len(PREFIX):])
    assert list(template) == SCHEMA["required"]
    assert list(SCHEMA["properties"])[:len(SCHEMA["required"])] == SCHEMA["required"]


def test_schema_settings_match_the_exit_codes_table():
    table = _exit_codes_table()
    rows = {int(m.group(1)): m.group(2) for m in re.finditer(r"^\| (\d+) +\| ([^|]+)\|", table, flags=re.M)}
    assert set(rows) == set(SCHEMA["properties"]["exit_code"]["enum"])
    classes = {2: "input-missing / input-invalid", 3: "resolution-failure", 4: "write-failure",
               5: "state-conflict", 6: "user-cancelled"}
    for reason, code in SETTINGS["exit_codes"].items():
        assert rows[code].strip() == classes[code], (reason, code)
    assert SETTINGS["result_file"] == "drop-skill-result"
    assert SETTINGS["halt_status"] == "error" and SETTINGS["success_exit_code"] == 0


def _halt_sites():
    for rel in (SKILL, SELECT, EXECUTE, REPORT):
        for number, line in enumerate(_read(rel).split("\n"), 1):
            for m in HALT_SITE.finditer(line):
                yield rel, number, int(m.group(1)), m.group(2), line


def test_every_halt_site_uses_the_schema_exit_code():
    sites = list(_halt_sites())
    for rel, number, code, reason, _ in sites:
        assert SETTINGS["exit_codes"].get(reason) == code, f"{rel}:{number} {reason} exits {code}"
    assert {reason for *_, reason, _ in sites} == set(SETTINGS["exit_codes"]), "a halt_reason no step raises"


@pytest.mark.parametrize("rel, start", [
    (SKILL, "## On Activation"),
    (SELECT, "## MANDATORY SEQUENCE"),
    (EXECUTE, "## MANDATORY SEQUENCE"),
], ids=["activation", "select", "execute"])
def test_every_emitting_halt_names_its_phase(rel, start):
    """Each HALT that prints an envelope names the phase its error object carries."""
    body = _section(_read(rel), start, None)
    sites = [line for line in body.split("\n") if HALT_SITE.search(line)]
    assert sites
    for line in sites:
        assert re.search(r"phase `(on-activation|select|execute):[a-z-]+`", line), line[:160]
    assert "emit the error envelope per" not in body, "every halt emits through the shared emitter"


def test_every_stage_runs_the_same_halt_command():
    """The contract's Halt Envelope (for the activation HALTs), and the Halts sections of select.md and
    execute.md, state the halt rule each; the command and the JSON rule never drift."""
    halt = _section(_read(CONTRACT), "## Halt Envelope", None)
    rules = {CONTRACT: halt,
             SELECT: _section(_read(SELECT), "## Halts", "## MANDATORY SEQUENCE"),
             EXECUTE: _section(_read(EXECUTE), "## Halts", "## MANDATORY SEQUENCE")}
    commands = {rel: _one_command(rule, "emit-halt --workflow skf-drop-skill --run-dir")
                for rel, rule in rules.items()}
    assert len(set(commands.values())) == 1, commands
    assert commands[SELECT] == ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill '
                                '--run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"')
    for rel, rule in rules.items():
        # A Windows path or a quoted stderr line written as is breaks the JSON, and the HALT prints nothing.
        assert ("Write the payload as valid JSON: in the halt message and `path`, replace each backslash "
                "with / and each double quote with a backtick.") in rule, rel
    activation = _section(_read(SKILL), "## On Activation", None)
    assert "the Halt Envelope section of `references/invocation-contract.md`" in activation
    assert "emit-halt" not in activation and "halt.json" not in activation, "SKILL.md names the section, once"


def test_the_json_rule_keeps_a_windows_halt_printable():
    """A raw Windows path makes the payload invalid JSON; the rule's rewrite emits."""
    [block] = [b for b in _fenced(_section(_read(CONTRACT), "## Halt Envelope", None), "bash")
               if "<<'SKF_DROP_HALT'" in b]
    command = next(line for line in block.split("\n") if "<<'SKF_DROP_HALT'" in line).partition(" <<")[0]
    raw = ('{"phase": "on-activation:run-folder", "reason": "SKF cannot create its run folder under '
           'C:\\Users\\dev\\_bmad-output: "Access is denied"", "halt_reason": "write-failed", "exit_code": 4}')
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER)}, stdin=raw.encode("utf-8"))
    assert proc.returncode != 0 and PREFIX.encode("utf-8") not in proc.stdout + proc.stderr, "no envelope"
    fixed = raw.replace("\\", "/").replace('"Access is denied"', "`Access is denied`")
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER)}, stdin=fixed.encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    assert envelope["error"]["reason"].endswith("C:/Users/dev/_bmad-output: `Access is denied`")


def test_documented_halt_emits_a_schema_valid_envelope_on_stderr(tmp_path):
    run_dir = _run_dir(tmp_path)
    halt = {"phase": "select:scope", "reason": "headless mode requires a `version` argument for `cognee`",
            "halt_reason": "input-missing", "exit_code": 2, "skill": "cognee"}
    (run_dir / "halt.json").write_bytes(json.dumps(halt).encode("utf-8"))
    command = _one_command(_read(SELECT), "emit-halt --workflow skf-drop-skill --run-dir")
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"", "a HALT prints its envelope on stderr"
    envelope = _envelope(proc.stderr)
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("error", 2, "input-missing")
    assert envelope["error"] == {"phase": "select:scope", "reason": halt["reason"]}
    assert (envelope["skill"], envelope["drop_mode"], envelope["versions_affected"]) == ("cognee", None, [])
    assert (envelope["files_deleted"], envelope["would_delete"], envelope["result_path"]) == ([], [], None)
    assert not list(tmp_path.rglob("drop-skill-result-*.json")), "a HALT writes no result file"


def test_failed_manifest_write_envelope(tmp_path):
    """#585: the step 2 halt reports exit 4 and a manifest that did not change."""
    run_dir = _run_dir(tmp_path)
    halt = {"phase": "execute:manifest-write", "reason": "Manifest update failed: disk full",
            "halt_reason": "manifest-write-failed", "exit_code": 4, "path": "/p/skills/.export-manifest.json",
            "skill": "cognee", "drop_mode": "purge", "versions_affected": "all", "manifest_updated": False}
    (run_dir / "halt.json").write_bytes(json.dumps(halt).encode("utf-8"))
    command = _one_command(_read(EXECUTE), "emit-halt --workflow skf-drop-skill --run-dir")
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    assert (envelope["status"], envelope["exit_code"], envelope["manifest_updated"]) == ("error", 4, False)
    assert envelope["error"]["path"] == "/p/skills/.export-manifest.json"
    assert envelope["versions_affected"] == "all"


def test_a_halt_whose_exit_code_disagrees_is_refused(tmp_path):
    """The emitter checks a typed exit code against the schema's mapping."""
    run_dir = _run_dir(tmp_path)
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "execute:manifest-write", "reason": "x", "halt_reason": "manifest-write-failed",
         "exit_code": 0}).encode("utf-8"))
    command = _one_command(_read(EXECUTE), "emit-halt --workflow skf-drop-skill --run-dir")
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode != 0 and b"exit_code" in proc.stderr


def test_run_folder_halt_emits_without_a_run_folder():
    """The one activation halt with no run folder passes its payload inline."""
    activation = _section(_read(SKILL), "## On Activation", None)
    assert 'HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:run-folder`)' in activation
    [block] = [b for b in _fenced(_section(_read(CONTRACT), "## Halt Envelope", None), "bash")
               if "<<'SKF_DROP_HALT'" in b]
    lines = block.strip("\n").split("\n")
    start = next(i for i, line in enumerate(lines) if "<<'SKF_DROP_HALT'" in line)
    head, body, end = lines[start:]
    assert end == "SKF_DROP_HALT"
    command = head.partition(" <<")[0]
    assert "--run-dir" not in command
    payload = json.loads(body.replace("<the halt message>", "SKF cannot create its run folder"))
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER)}, stdin=json.dumps(payload).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    assert (envelope["halt_reason"], envelope["exit_code"]) == ("write-failed", 4)
    assert envelope["error"]["phase"] == "on-activation:run-folder"


def test_dry_run_envelope_lists_the_planned_deletions(tmp_path):
    """#593: a headless --dry-run of a purge names the folders it would delete, and writes no result file."""
    confirm = _section(_read(SELECT), "### 10. Confirmation Gate", "### 12. ")
    [template] = _fenced(confirm, "json")
    run_dir = _run_dir(tmp_path)
    skills = tmp_path / "skills"
    would = [str(skills / "cognee"), str(tmp_path / "forge" / "cognee")]
    payload = _fill_json(template, {"target_skill": "cognee", "drop_mode": "purge", "target_versions": "all",
                                    "affected_directories": would, "forge_left_in_place": None})
    assert set(payload) == {"status", "skill", "drop_mode", "versions_affected", "would_delete",
                            "forge_left_in_place"}
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    command = _one_command(confirm, "emit --workflow skf-drop-skill")
    assert "--result-dir" not in command, "a dry run writes no result file"
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("dry-run", 0, None)
    assert envelope["would_delete"] == would and envelope["files_deleted"] == []
    assert (envelope["manifest_updated"], envelope["result_path"], envelope["error"]) == (False, None, None)
    assert not list(tmp_path.rglob("drop-skill-result-*.json"))
    assert 'delete the run folder (`rm -rf "{run_dir}"`) and HALT (exit code 0)' in confirm


REPORT_VALUES = {
    "target_skill": "cognee", "drop_mode": "purge", "target_versions": ["0.5.0"], "manifest_updated": True,
    "forge_left_in_place": None, "keep_version": None,
}


@pytest.mark.parametrize("record_status", ["success", "partial"])
def test_report_emit_writes_the_result_files(tmp_path, record_status):
    """#593: the emitter names the per-run file from the clock and writes its -latest copy. #1161: the headless
    mode and confirm decisions reach the record once, in `headless_decisions`, and the summary no longer repeats
    them."""
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [template] = _fenced(contract, "json")
    skills = tmp_path / "skills"
    skills.mkdir()
    deleted = str(skills / "cognee" / "0.5.0")
    run_dir = _run_dir(tmp_path)
    select = _read(SELECT)
    mode = _section(select, "### 8. Ask Mode", "### 8b. ")
    confirm = _section(select, "### 10. Confirmation Gate", "### 12. ")
    decisions = [_decision(mode, "select.mode", {"drop_mode": "purge", "mode_source": "--mode argument"}),
                 _decision(confirm, "select.confirm", {})]
    record_command = _one_command(mode, "record --run-dir")
    for decision in decisions:
        (run_dir / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
        proc = _run(record_command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
        assert proc.returncode == 0, proc.stderr
    payload = _fill_json(template, {**REPORT_VALUES, "files_deleted": [deleted], "each": deleted,
                                    "record_status": record_status})
    assert set(payload) == {"status", "skill", "drop_mode", "versions_affected", "files_deleted",
                            "forge_left_in_place", "manifest_updated", "result_contract"}
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    command = _one_command(contract, "emit --workflow skf-drop-skill")
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir),
                          "skills_output_folder": str(skills)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    # The envelope has no partial status: the record carries it.
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("success", 0, None)
    assert envelope["files_deleted"] == [deleted] and envelope["versions_affected"] == ["0.5.0"]
    per_run = Path(envelope["result_path"])
    assert PER_RUN_NAME.fullmatch(per_run.name), per_run.name
    assert (skills / per_run.name).is_file()
    latest = skills / "drop-skill-result-latest.json"
    assert latest.read_bytes() == (skills / per_run.name).read_bytes()
    record = json.loads(latest.read_text(encoding="utf-8"))
    assert (record["skill"], record["status"]) == ("skf-drop-skill", record_status)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", record["timestamp"])
    assert record["run_id"] == "Ab3dE5gH"
    assert record["outputs"] == [{"type": "skill", "path": deleted}]
    assert record["headless_decisions"] == decisions
    assert [(d["gate"], d["reason"]) for d in decisions] == [("select.mode", "--mode argument"),
                                                            ("select.confirm", "headless auto-confirm")]
    assert set(record["summary"]) == {"target_skill", "drop_mode", "versions_affected", "forge_left_in_place",
                                      "keep_version"}
    # #1160: a drop that kept no version says so in the summary, never in the envelope.
    assert record["summary"]["keep_version"] is None and "keep_version" not in envelope


def _decision(text: str, gate: str, values: dict) -> dict:
    """The decision object a gate stages, its `<name>` placeholders filled in."""
    m = re.search(r'`(\{"gate": "' + re.escape(gate) + r'"[^`]*\})`', text)
    assert m, f"no staged {gate} decision"
    return json.loads(re.sub(r"<(\w+)>", lambda v: values[v.group(1)], m.group(1)))


def test_headless_decisions_reach_the_result_record(tmp_path):
    """#593: the mode and the confirmation a headless run decides land in the record's headless_decisions. #1160:
    so does the version a `keep` argument made active, and the summary names it."""
    select = _read(SELECT)
    guard = _section(select, "### 7. Active Version Guard", "### 8. ")
    mode = _section(select, "### 8. Ask Mode", "### 8b. ")
    confirm = _section(select, "### 10. Confirmation Gate", "### 12. ")
    command = _one_command(mode, "record --run-dir")
    assert "--workflow" not in command, "the drop schema has no headless_decisions to check a decision against"
    assert "run the §8 `record` command" in confirm
    assert ("When `{headless_mode}` is true and `keep_version` is bound, record the keep as an auto-decision: stage "
            "`{run_dir}/decision.json` as") in guard and "run the §8 `record` command" in guard
    run_dir = _run_dir(tmp_path)
    decisions = [_decision(guard, "select.active-guard", {"keep_version": "0.5.0"}),
                 _decision(mode, "select.mode", {"drop_mode": "purge", "mode_source": "--mode argument"}),
                 _decision(confirm, "select.confirm", {})]
    assert decisions[0] == {"gate": "select.active-guard", "default_action": "use args", "taken_action": "keep 0.5.0",
                            "reason": "keep argument"}
    for decision in decisions:
        (run_dir / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
        proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
        assert proc.returncode == 0, proc.stderr
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [template] = _fenced(contract, "json")
    skills = tmp_path / "skills"
    skills.mkdir()
    deleted = str(skills / "cognee" / "0.6.0")
    payload = _fill_json(template, {**REPORT_VALUES, "target_versions": ["0.6.0"], "keep_version": "0.5.0",
                                    "files_deleted": [deleted], "each": deleted, "record_status": "success"})
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    proc = _run(_one_command(contract, "emit --workflow skf-drop-skill"),
                {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir), "skills_output_folder": str(skills)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    assert "headless_decisions" not in envelope and "keep_version" not in envelope, "the envelope has no such field"
    record = json.loads((skills / "drop-skill-result-latest.json").read_text(encoding="utf-8"))
    assert record["headless_decisions"] == decisions
    assert decisions[1]["taken_action"] == "purge" and decisions[2]["gate"] == "select.confirm"
    assert (record["summary"]["keep_version"], record["summary"]["versions_affected"]) == ("0.5.0", ["0.6.0"])


# --------------------------------------------------------------------------
# #585: a failed manifest write halts in every mode, before the report
# --------------------------------------------------------------------------

def test_failed_manifest_write_halts_in_every_mode():
    manifest = _section(_read(EXECUTE), "### 2. Update Export Manifest", "### 3. ")
    on_error = _section(manifest, "**On error (the helper exits non-zero):**", None)
    assert 'HALT (exit code 4, `halt_reason: "manifest-write-failed"`' in on_error
    assert "in every mode, before section 3" in on_error
    for stale in ("jump to section 6", "Store `manifest_updated = false`", "{captured stderr}"):
        assert stale not in manifest, stale
    assert "When the helper exits 0 (`status: \"ok\"`), set context flag `manifest_updated = true`." in manifest
    rules = _section(_read(REPORT), "## Rules", "## MANDATORY SEQUENCE")
    assert "HALTs in step 2" not in rules, "leanness-8: execute.md states the halt once"
    table = _exit_codes_table()
    exit_4 = next(line for line in table.splitlines() if line.startswith("| 4 "))
    assert "step 2 manifest write, in every mode (`manifest-write-failed`)" in exit_4


# --------------------------------------------------------------------------
# #593: no stage types an envelope, a timestamp or a result file name
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [SKILL, SELECT, EXECUTE, REPORT])
def test_no_stage_types_an_envelope(rel):
    text = _read(rel)
    assert PREFIX + "{" not in text, "the emitter prints the line"
    assert "{headlessContract}" not in text and "headlessContract:" not in text


def test_the_emitter_stamps_the_time_and_writes_the_result_files():
    assert "Generate and store `timestamp`" not in _read(SKILL)
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    assert "Write the result contract per" not in contract
    assert _one_command(contract, "emit --workflow skf-drop-skill") == (
        'uv run {emitEnvelopeHelper} emit --workflow skf-drop-skill --run-dir "{run_dir}" '
        '--result-dir "{skills_output_folder}" < "{run_dir}/result-context.json"')
    assert ("Bind `{result_json_path}` ← the `result_path` of the `SKF_DROP_SKILL_RESULT_JSON:` line it prints on "
            "stdout") in contract
    hook = _section(_read(REPORT), "### Post-drop hook", "### 3. ")
    assert "`{result_json_path}` is not null" in hook
    assert 'rm -rf "{run_dir}"' in hook


# --------------------------------------------------------------------------
# #594: helpers before the first prompt; arguments answer their gates
# --------------------------------------------------------------------------

# #1116: the helpers SKILL.md On-Activation §4 resolves, by probe-order stem, with the script each one runs.
ACTIVATION_HELPERS = {"emitEnvelope": "skf-emit-result-envelope.py", "manifestOps": "skf-manifest-ops.py",
                      "rebuildManagedSections": "skf-rebuild-managed-sections.py"}
# The ones each stage runs, and so declares a probe order for.
STAGE_HELPERS = {SELECT: ("emitEnvelope", "rebuildManagedSections"),
                 EXECUTE: ("emitEnvelope", "manifestOps", "rebuildManagedSections"),
                 REPORT: ("emitEnvelope",)}
LOST_BINDING_RULE = "- When a helper is not bound, it resolves to the first existing path in its probe order: "


def _probe_order(script: str) -> list[str]:
    """The installed path, then the development tree's, as On Activation probes them."""
    return [f"{{project-root}}/_bmad/skf/shared/scripts/{script}", f"{{project-root}}/src/shared/scripts/{script}"]


def test_required_helpers_resolve_before_the_first_prompt():
    """#594: On Activation resolves the helpers and halts on a missing one before the first prompt. #1116: each
    stage still declares the probe order of every helper it runs, and its Rules resolve one from it when the
    binding is lost, so a stage a context compaction reached finds its helpers again from its own file."""
    activation = _section(_read(SKILL), "## On Activation", None)
    preflight = _section(activation, "**Pre-flight: helpers", "and then execute `references/select.md`")
    resolve = next(line for line in preflight.splitlines() if line.startswith("   First, resolve "))
    for helper, script in (("emitEnvelopeHelper", "skf-emit-result-envelope.py"),
                           ("manifestOpsHelper", "skf-manifest-ops.py"),
                           ("rebuildManagedSectionsHelper", "skf-rebuild-managed-sections.py")):
        assert f"`{{{helper}}}`" in resolve and f"`{script}`" in resolve, helper
        installed = REPO / "src" / "shared" / "scripts" / script  # where _bmad/skf/shared/scripts/ comes from
        assert installed.is_file(), script
    assert ("the first that exists of `{project-root}/_bmad/skf/shared/scripts/<script>` (installed) and "
            "`{project-root}/src/shared/scripts/<script>` (development tree)") in resolve
    missing = next(line for line in preflight.splitlines() if "resolved to no path" in line)
    assert 'HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:helpers`)' in missing
    assert preflight.index("resolved to no path") < preflight.index("check that `{skills_output_folder}` is writable")
    # A step finds a lost helper again from its own probe order, but never halts on a missing one after the
    # manifest changed or keeps an in-prompt fallback that no run can reach.
    execute = _read(EXECUTE)
    assert "If no candidate exists, HALT" not in execute
    assert "HALT (exit code 4, `halt_reason: \"manifest-write-failed\"`) if no candidate exists" not in execute
    for rel, stems in STAGE_HELPERS.items():
        text = _read(rel)
        front, body = text.removeprefix("---\n").split("\n---\n", 1)
        bindings = yaml.safe_load(front)
        [rule] = [line for line in _section(text, "## Rules", "## MANDATORY SEQUENCE").splitlines()
                  if line.startswith(LOST_BINDING_RULE)]
        assert re.findall(r"`\{(\w+)Helper\}` in `\{\1ProbeOrder\}`", rule) == list(stems), rel
        for stem, script in ACTIVATION_HELPERS.items():
            # A stage declares the probe order of exactly the helpers its body runs.
            assert (f"{{{stem}Helper}}" in body.replace(rule, "")) == (stem in stems), (rel, stem)
            assert bindings.get(f"{stem}ProbeOrder") == (_probe_order(script) if stem in stems else None), (rel, stem)
        for gone in ("On-Activation §4 resolved", "SKILL.md On Activation §3", "come from SKILL.md On-Activation",
                     "manifest file in-prompt", "the in-prompt computation", "manifest in-prompt",
                     "by comparing version components numerically"):
            assert gone not in text, f"{rel}: {gone}"
    roster = _section(_read(SELECT), "### 3. List Available Skills", "### 4. ")
    assert ("When `{roster}.inventory` is false (the inventory helper could not run), the roster holds the manifest "
            "skills alone") in roster, "the inventory fallback stays: it changes what is offered"
    for start, end in (("### 2. Update Export Manifest", "### 3. "), ("### 3. Rebuild Context Files", "### 4. ")):
        assert "halts before the first prompt" not in _section(execute, start, end), start
    rule = next(line for line in _read(SKILL).splitlines() if line.startswith("- Never do by hand what a helper does"))
    assert "A missing On-Activation §4 helper halts the run before the first prompt" in rule


def test_a_stage_that_lost_a_helper_runs_the_one_its_probe_order_finds(tmp_path):
    """#1116, restated as code: a stage resolves a helper whose binding a compaction dropped to the first path of its
    probe order that exists, the installed copy when SKF is installed and the development tree's otherwise, and to
    none when neither exists (the helper's command then fails, and the step's own branch for that applies). The
    copy execute.md's order finds runs §2's documented skill-level purge."""
    installed, dev = tmp_path / "installed", tmp_path / "dev"
    for root, folders in ((installed, ("_bmad/skf/shared/scripts", "src/shared/scripts")),
                          (dev, ("src/shared/scripts",))):
        for folder in folders:
            (root / folder).mkdir(parents=True)
            for script in ACTIVATION_HELPERS.values():
                shutil.copyfile(SCRIPTS / script, root / folder / script)

    def first(probe: list[str], root: Path) -> Path | None:
        paths = [Path(entry.replace("{project-root}", root.as_posix())) for entry in probe]
        return next((path for path in paths if path.is_file()), None)

    for rel, stems in STAGE_HELPERS.items():
        bindings = yaml.safe_load(_read(rel).removeprefix("---\n").split("\n---\n", 1)[0])
        for stem in stems:
            script, probe = ACTIVATION_HELPERS[stem], bindings[f"{stem}ProbeOrder"]
            assert first(probe, installed) == installed / "_bmad" / "skf" / "shared" / "scripts" / script, (rel, stem)
            assert first(probe, dev) == dev / "src" / "shared" / "scripts" / script, (rel, stem)
            assert first(probe, tmp_path / "neither") is None, (rel, stem)
    execute = _read(EXECUTE)
    helper = first(yaml.safe_load(execute.removeprefix("---\n").split("\n---\n", 1)[0])["manifestOpsProbeOrder"], dev)
    skills = tmp_path / "skills"
    skills.mkdir()
    _write_manifest(skills, "cognee", "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"})
    proc = _run(_skill_level_calls()["purge"], {"manifestOpsHelper": str(helper), "skills_output_folder": str(skills),
                                                "target_skill": "cognee"})
    assert proc.returncode == 0, proc.stderr
    assert "cognee" not in json.loads((skills / ".export-manifest.json").read_text(encoding="utf-8"))["exports"]


def test_activation_runs_the_resolver_through_uv_and_records_its_failure():
    """#595 option (a): the resolver runs under uv with --project-root, so a
    dropped `forbid_purge_in_headless` override is never silent: a failure
    prints one warning, and step 4 records the reason in the run sink once the
    run folder and the emitter exist, through a file, so every envelope from
    there on carries it. #1107: Drop ships no project-context default, and
    its comment shows the two-line override that loads those files anyway."""
    activation = _section(_read(SKILL), "## On Activation", None)
    resolve = " ".join(_section(activation, "3. **Resolve workflow customization.**", "4. **Pre-flight").split())
    assert ("uv run {resolveCustomizationHelper} --skill {skill-root} "
            "--project-root {project-root} --key workflow") in resolve
    assert "{project-root}/_bmad/scripts/resolve_customization.py" not in activation
    for token in ("It merges the bundled `{skill-root}/customize.toml` with "
                  "`{project-root}/_bmad/custom/skf-drop-skill.toml` (team overrides, committed) and `.user.toml` "
                  "(personal overrides, gitignored).",
                  "When it exits non-zero, prints no JSON or is missing, print one line, "
                  "`[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr "
                  "line, `SKF helper skf-resolve-customization.py not found` when the "
                  "script is missing, `no JSON` when it printed none).",
                  "If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled "
                  "defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run.",
                  "Keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran)",
                  "keep `workflow.persistent_facts` as standing context (if the resolver ran, `--facts` has "
                  "applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a "
                  "`file:` entry names one file)"):
        assert token in resolve, token
    # Drop ships no default, so the step names none.
    assert "the bundled default loads" not in resolve
    # #601: no bare `_bmad/` path is left for the path-standards scan to flag.
    assert re.search(r"(?<!\{project-root\}/)_bmad/", resolve) is None
    preflight = " ".join(_section(activation, "**Pre-flight: helpers", "5. Load").split())
    record = ('write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a file '
              'write (a resolver error can hold quotes or `$( )`, so never echo it or type it into an argument), then '
              'run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '
              '"$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`')
    assert record in preflight
    # After the helper check (the emitter exists), before the write probe and the purge guard can halt.
    assert (preflight.index("resolved to no path") < preflight.index(record)
            < preflight.index("check that `{skills_output_folder}` is writable")
            < preflight.index("Last, the headless-purge guard."))
    warnings = next(line for line in _read(CONTRACT).splitlines() if line.startswith("- `warnings`:"))
    assert "`customization_resolver_unavailable: <reason>` when On Activation records" in warnings
    # The activation halts keep the run folder; the stages that delete it say so where they do.
    assert "bind `{run_dir}` ← the path it prints (an activation HALT keeps it):" in preflight
    toml = _read(CUSTOMIZE)
    # #1107: no Drop Skill stage reads the project context, so the list ships empty and the comment shows the opt-in.
    assert tomllib.loads(toml)["workflow"]["persistent_facts"] == []
    comment = _comment(toml, "# Persistent facts the workflow keeps", "persistent_facts = []\n")
    assert ("Ships empty: no Drop Skill stage reads the project context. To load every project-context.md under "
            "{project-root} anyway, set in {project-root}/_bmad/custom/skf-drop-skill.toml: "
            '[workflow] persistent_facts = ["file:{project-root}/**/project-context.md"]') in comment
    assert "!file:" not in comment and "The default below" not in comment
    # The example is an override file as written: under the table, where the resolver's `--key workflow` reads it.
    example = _section(toml, "skf-drop-skill.toml:\n", "\n\n")
    override = tomllib.loads("\n".join(line.lstrip("#").strip() for line in example.splitlines()[1:]))
    assert override == {"workflow": {"persistent_facts": ["file:{project-root}/**/project-context.md"]}}
    assert "Each entry is either:" not in comment
    assert ("Each entry is one of: - a literal sentence" in comment
            and "- an entry prefixed with `!`, which loads nothing and drops each earlier entry it names." in comment)


def test_conventions_say_how_module_and_sibling_paths_resolve():
    """#601: drop reads `shared/` scripts and export-skill's managed-section
    format, so its Conventions say where both resolve from. #1112: a stage's
    `nextStepFile: 'execute.md'` sits beside `dropRosterHelper:
    'scripts/drop-roster.py'`, so the bare-path rule says which of the two
    names a file beside the stage."""
    conventions = _section(_read(SKILL), "## Conventions", "## Role")
    assert ("- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: "
            "only a stage's frontmatter `nextStepFile` names a file beside it.") in conventions
    assert ("- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the "
            "SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.") in conventions
    assert ("- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the "
            "SKF module root, and that skill must be installed with this one.") in conventions
    assert "`skf-export-skill/assets/managed-section-format.md`" in conventions
    # Drop has scripts/ and no assets/: the Conventions name the helpers it holds.
    assert not (DROP / "assets").exists() and "`assets/`" not in conventions
    helpers = sorted(p.name for p in (DROP / "scripts").glob("*.py"))
    assert helpers == ["dir-sizes.py", "drop-roster.py"]
    assert "`scripts/` holds its helpers (`dir-sizes.py`, `drop-roster.py`)." in conventions
    assert "`headless_mode: true` in `{sidecar_path}/preferences.yaml`" in _read(SKILL)


def test_a_supplied_skill_name_answers_the_skill_gate_in_both_modes():
    ask = _section(_read(SELECT), "### 4. Ask Which Skill", "### 5. ")
    gate = next(line for line in ask.splitlines() if line.startswith("**GATE [default: use args]:**"))
    assert "take it as the answer below in either mode, without showing the prompt" in gate
    assert 'headless mode HALTs (exit code 2, `halt_reason: "input-missing"`' in gate
    assert "If `{headless_mode}` and skill name was provided" not in ask


def test_the_version_argument_answers_the_scope_gate():
    scope = _section(_read(SELECT), "### 6. Ask Scope", "### 7. ")
    assert "**GATE [default: use args]:** the `version` argument answers this section in either mode" in scope
    draft = _section(scope, "**If `target_in_manifest = false`:**", "**If `target_in_manifest = true`:**")
    assert 'HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:scope`) in either mode' in draft
    assert "Re-run with `version=all`." in draft
    assert "the drop never widens it to every version" in draft
    exported = _section(scope, "**If `target_in_manifest = true`:**", "**If [N] Specific version:**")
    assert ("a `version` argument of `all` takes **[A]** below, `older` takes **[O]**, and any other value takes "
            "**[N]**") in exported
    assert 'headless mode HALTs (exit code 2, `halt_reason: "input-missing"`, phase `select:scope`)' in exported
    # #1160 enhancement-3: [O] drops every version but the active one, from the roster's list.
    assert "- **[O]** Older versions: every manifest version except the active one\n" in exported
    assert "`{target_skill}`: `all`, `older`, or one of its versions" in exported
    older = _section(scope, "**If [O] Older versions:**", "**If [A] All versions:**")
    assert ("set `target_versions` ← the `older_versions` of `{target_skill}`'s roster entry (its manifest versions "
            "that are neither active nor deprecated, newest first) and `is_skill_level = false`.") in older
    empty = "`{target_skill}` has no older version to drop: every version but the active one is already deprecated."
    assert f'- **Interactive:** display "{empty}" and ask again.' in older
    assert ('- **Headless (`{headless_mode}` is true):** HALT (exit code 2, `halt_reason: "input-invalid"`, phase '
            '`select:scope`), with `skill: "{target_skill}"` in the halt envelope: "headless mode: ' + empty + '"'
            ) in older
    assert "draft skills can only be dropped as a whole" not in scope, "a draft no longer ignores the argument"
    # The versions are named and checked from §5's ordered rows, never from the manifest map by eye.
    assert "one of its versions ({each `{version_rows}` entry with `in_manifest` true})" in exported
    assert "Validate that the version is a `{version_rows}` entry with `in_manifest` true." in scope
    assert "{its manifest versions, newest first}" not in scope and "`versions` map" not in scope
    versions = _section(_read(SELECT), "### 5. Display Version Details", "### 6. ")
    assert "Bind `{version_rows}` ← the `versions` of `{target_skill}`'s roster entry" in versions
    assert "affected-versions" not in _read(SELECT), "the roster orders the versions"
    gates = next(line for line in _contract_text(with_skill=True).splitlines() if line.startswith("| **Gates** |"))
    assert "Scope Gate [use args] (§6 version), Keep Gate [use args] (§7 keep)" in gates
    inputs = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Inputs** |"))
    assert "version (`all`, `older` or one version) [required for a skill in the manifest" in inputs
    # Lane review: a `keep` makes its version active whichever version the drop removes, and the docs say so.
    assert ("keep (the version to make active before the drop, whichever version it drops, so dropping the active "
            "version keeps another) [optional]") in inputs
    safety = _section(_read("docs/workflows.md"), "### Drop Skill (DS)", "**Preview first:**")
    assert ("A `keep` makes that version active whichever version the drop removes, so pass it only to change the "
            "active version.") in safety
    assert "needs `version=all` or the one version to drop (or `version=older` for the older versions)" in safety
    [ds] = [line for line in _read("docs/workflows.md").splitlines() if line.startswith("- **`/skf-drop-skill` (DS)**")]
    assert "a `keep` that names no version the drop can keep, and `version=older` with no older version left" in ds
    paths = _read("src/knowledge/version-paths.md")
    assert "Drops a specific version, every version but the active one (Older versions), or the entire skill" in paths
    assert "a version-level purge (one version, or Older versions) whose every version is marked" in paths


def test_the_mode_argument_answers_the_mode_gate():
    gates = next(line for line in _contract_text(with_skill=True).splitlines() if line.startswith("| **Gates** |"))
    assert "Mode Gate [use args] (§8 mode)" in gates
    mode = _section(_read(SELECT), "### 8. Ask Mode", "### 8b. ")
    gate = ("**GATE [default: use args]:** a `mode` argument answers this section in either mode, "
            "and an interactive run with none asks")
    assert gate in mode and mode.index(gate) < mode.index("**If `target_in_manifest = false`:**")
    # #596: no setting picks the mode, so a headless run without `mode` halts on both branches.
    exported = _section(mode, "**If `target_in_manifest = true`:**", None)
    assert ('If `{headless_mode}` is true (no `mode` arg), there is no input to prompt for: HALT (exit code 2, '
            '`halt_reason: "input-missing"`, phase `select:mode`)') in exported
    assert '"headless mode requires `--mode deprecate|purge` to set the drop mode."' in exported
    draft = _section(mode, "**If `target_in_manifest = false`:**", "**If `target_in_manifest = true`:**")
    assert ('2. `{headless_mode}` is true and no `mode` argument was passed: HALT (exit code 2, '
            '`halt_reason: "input-missing"`') in draft


# --------------------------------------------------------------------------
# #596: the customization surface: no default mode, a fail-closed purge
# guard, and hook comments that match when the hooks run
# --------------------------------------------------------------------------

def _drop_files():
    return [path for path in sorted(DROP.rglob("*")) if path.suffix in (".md", ".toml")]


def _comment(toml: str, start: str, end: str) -> str:
    """A customize.toml comment block as one line of prose, its `#` markers dropped."""
    return " ".join(line.lstrip("#").strip() for line in _section(toml, start, end).splitlines()).strip()


def test_no_drop_file_reads_a_default_mode():
    """`default_mode` is gone: the mode is the `mode` argument or the interactive answer."""
    for path in _drop_files():
        text = path.read_text(encoding="utf-8")
        for gone in ("default_mode", "{defaultMode}", "effective drop mode",
                     "customize.toml.workflow.default_mode"):
            assert gone not in text, f"{path.name}: {gone}"
    assert not re.search(r"^\s*default_mode\s*=", _read(CUSTOMIZE), flags=re.M)
    # #1161: the record keeps the headless decisions in `headless_decisions` alone, so nothing stages them twice.
    assert "headless_provenance" not in _read(REPORT)
    for path in _drop_files():
        assert "confirm_source" not in path.read_text(encoding="utf-8"), path.name
    mode = _section(_read(SELECT), "### 8. Ask Mode", "### 8b. ")
    for source in ('`mode_source = "--mode argument"`', '`mode_source = "draft-skill-forced-purge"`'):
        assert source in mode, source
    # Only a headless run records the select.mode decision, and it never reaches the prompt.
    assert "interactive-prompt" not in mode
    stored = _section(_read(SELECT), "### 12. Load Next Step", None)
    assert "`mode_source`" not in stored


def test_any_non_empty_forbid_value_turns_the_purge_guard_on():
    """A mistyped forbid_purge_in_headless that still parses blocks the purge instead of allowing it.

    An override file that fails to parse (an unquoted True, yes or on, or a
    bad line elsewhere in it) stops the resolver, so the run reads the bundled
    empty value and the guard is off: the comment, the Headless row and the
    settings list say so and ask for a quoted value.
    """
    activation = _section(_read(SKILL), "## On Activation", None)
    binding = next(line for line in activation.splitlines() if "`{forbidPurgeInHeadless}` ←" in line)
    # #1158: the helper reads the value; the agent never decides by hand whether a JSON `false` is on.
    assert ("the `purge_forbidden` that step 4's `activation` call reads from `workflow.forbid_purge_in_headless`"
            in binding)
    assert "holds any value other than the empty string" not in binding and 'non-`"true"`' not in binding
    guard = _section(activation, "Last, the headless-purge guard.", "5. Load")
    assert ('When `{headless_mode}` is true, the `mode` arg is `"purge"` and the §3 resolver ran, write the JSON it '
            'printed, as printed, to `{run_dir}/customization.json` with a file write') in guard
    assert _one_command(guard, "{dropRosterHelper}") == (
        'uv run {dropRosterHelper} activation < "{run_dir}/customization.json"')
    assert ("Bind `{forbidPurgeInHeadless}` ← its `purge_forbidden`, which is on for any value other than the empty "
            'string (a TOML `true`, `false` or `"false"` included); a non-zero exit, or no JSON, counts as on.') in guard
    assert guard.index("activation <") < guard.index(
        'If `{headless_mode}` is true, `{forbidPurgeInHeadless}` is on and the `mode` arg is `"purge"`, '
        'HALT (exit code 6, `halt_reason: "headless-purge-forbidden"`')
    # The §3 resolver stays one call: the guard reads what it printed.
    assert activation.count("{resolveCustomizationHelper} --skill") == 1
    assert "empty the setting in the team or personal override that sets it" in guard, "never the base file"
    comment = _comment(_read(CUSTOMIZE), "# --- Optional safety scalar ---", 'forbid_purge_in_headless = ""')
    assert "Any value other than the empty string turns the guard on" in comment
    for token in ("so a mistyped value that still parses blocks the purge rather than allowing it",
                  "An override file that fails to parse (an unquoted True, yes or on, or a bad line elsewhere in "
                  "it) stops the resolver", "customization_resolver_unavailable and uses this file alone, so the "
                  "guard is off", 'Quote the value, as in "true".'):
        assert token in comment, token
    assert re.search(r'^forbid_purge_in_headless = ""$', _read(CUSTOMIZE), flags=re.M)
    headless = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Headless** |"))
    assert "Any non-empty `forbid_purge_in_headless`" in headless
    assert "never in the bundled `customize.toml`" in headless, "an edit to the DO-NOT-EDIT base file is lost on update"
    assert ('(exit code 6, `halt_reason: "headless-purge-forbidden"`) when the customization resolver runs. When it '
            "cannot, including an override file that fails to parse, the run warns "
            "`customization_resolver_unavailable` and the bundled empty value leaves the guard off.") in headless


def test_the_guard_is_set_under_the_workflow_table():
    """Step 5b run 2 customization-1: the resolver reads `--key workflow`, so a key written above the
    `[workflow]` line lands at the file's root, never reaches the guard and warns nothing. The comment and
    the Headless row give the two-line form and say what a header-less key does, and TOML bears both out."""
    comment = _comment(_read(CUSTOMIZE), "# --- Optional safety scalar ---", 'forbid_purge_in_headless = ""')
    for token in ("In {project-root}/_bmad/custom/skf-drop-skill.toml (or .user.toml) write it under the table, "
                  'as two lines: `[workflow]` then `forbid_purge_in_headless = "true"`.',
                  "A key above the `[workflow]` line is ignored without a warning, which leaves the guard off."):
        assert token in comment, token
    headless = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Headless** |"))
    assert "set under `[workflow]` in a team or personal override" in headless
    assert ("A key written without the `[workflow]` line is ignored with no warning, and the guard stays off."
            in headless)
    # The comment's two lines, written as an override file, set the key the guard reads.
    lines = re.search(r"as two lines: `(\[workflow\])` then `([^`]+)`", comment).groups()
    assert tomllib.loads("\n".join(lines))["workflow"] == {"forbid_purge_in_headless": "true"}
    # The same key without the table line parses, but `workflow` holds no guard: the warning stays true.
    bare = tomllib.loads(lines[1])
    assert bare == {"forbid_purge_in_headless": "true"}
    assert "forbid_purge_in_headless" not in bare.get("workflow", {})


def _unquoted_examples() -> list[str]:
    """The unquoted values the forbid_purge_in_headless comment names, read from the shipped comment."""
    comment = _comment(_read(CUSTOMIZE), "# --- Optional safety scalar ---", 'forbid_purge_in_headless = ""')
    found = re.search(r"an unquoted (\w+), (\w+) or (\w+)", comment)
    assert found, "the comment names the unquoted values that fail to parse"
    return list(found.groups())


@pytest.mark.parametrize("value", _unquoted_examples())
def test_an_unquoted_forbid_value_is_an_override_that_fails_to_parse(value):
    """The comment's examples: TOML refuses each one, so the resolver stops and the guard is off; quoted, it parses."""
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(f"[workflow]\nforbid_purge_in_headless = {value}\n")
    quoted = tomllib.loads(f'[workflow]\nforbid_purge_in_headless = "{value}"\n')
    assert quoted["workflow"]["forbid_purge_in_headless"] == value


def test_hook_comments_match_when_the_hooks_run():
    toml = _read(CUSTOMIZE)
    prepend = _comment(toml, "# Steps to run once On Activation", "activation_steps_prepend = []")
    assert "uv probe" not in prepend and "before its pre-flight" in prepend
    append = _comment(toml, "# Steps to run right after the prepend steps", "activation_steps_append = []")
    assert "still before the pre-flight" in append and "once activation completes" not in append
    # SKILL.md runs both in On Activation section 3, before the section 4 pre-flight.
    activation = _section(_read(SKILL), "## On Activation", None)
    assert (activation.index("run `workflow.activation_steps_prepend` now")
            < activation.index("then run `workflow.activation_steps_append` after")
            < activation.index("**Pre-flight: helpers"))
    on_complete = _comment(toml, "# Optional post-drop hook", 'on_complete = ""')
    assert '`<command> --result-path="<path>"`' in on_complete
    assert "a dry run, a HALT or a failed record write never calls it" in on_complete
    hook = _section(_read(REPORT), "### Post-drop hook", "### 3. ")
    assert "`{result_json_path}` is not null" in hook
    assert 'display "on_complete hook failed (exit {code}): {its first stderr line}"' in hook
    for text in (toml, hook):
        assert "workflow_warnings" not in text, "nothing reads that list"


# --------------------------------------------------------------------------
# #600: the headless contract lives in references/invocation-contract.md
# --------------------------------------------------------------------------

def test_skill_md_points_at_the_one_contract_file():
    skill = _read(SKILL)
    assert not (DROP / "references" / "headless-contract.md").exists()
    for gone in ("| **Inputs** |", "| **Flags** |", "| **Gates** |", "## Exit Codes", "| Code | Meaning"):
        assert gone not in skill, gone
    pointer = _section(skill, "## Invocation Contract", "## On Activation")
    assert "live in `references/invocation-contract.md`. Interactive runs do not need it." in pointer
    contract = _read(CONTRACT)
    headings = re.findall(r"^## (.+)$", contract, flags=re.M)
    assert headings == ["Invocation Contract", "Exit Codes", "Result Contract (Headless)", "Halt Envelope"]
    assert "per the Exit Codes table above" in contract
    for path in [*_drop_files(), SCHEMA_PATH]:
        text = path.read_text(encoding="utf-8")
        assert "headless-contract.md" not in text and "SKILL.md Exit Codes" not in text, path.name


def test_the_description_triggers_name_their_object():
    """A bare "drop" would also match dropping a table, a column or a commit."""
    front = _read(SKILL).split("\n---\n", 1)[0]
    description = next(line for line in front.splitlines() if line.startswith("description: "))
    triggers = re.findall(r'"([^"]+)"', description)
    assert triggers == ["drop a skill", "remove a skill"]


# --------------------------------------------------------------------------
# A whole-skill deprecate keeps the manifest entry, so it stays reversible
# --------------------------------------------------------------------------

def _skill_level_calls() -> dict:
    """execute.md section 2's skill-level manifest command for each drop mode."""
    manifest = _section(_read(EXECUTE), "### 2. Update Export Manifest", "### 3. ")
    level = _section(manifest, "**If `is_skill_level == true` (skill-level drop):**", "When the helper exits 0")
    return {"deprecate": _one_command(_section(level, "- **Deprecate (`drop_mode == \"deprecate\"`):**",
                                               "- **Purge:**"), "{manifestOpsHelper}"),
            "purge": _one_command(_section(level, "- **Purge:**", None), "{manifestOpsHelper}")}


@pytest.mark.parametrize("drop_mode", ["deprecate", "purge"])
def test_the_skill_level_manifest_call_follows_the_drop_mode(tmp_path, drop_mode):
    skills = tmp_path / "skills"
    skills.mkdir()
    _write_manifest(skills, "cognee", "0.6.0", {"0.6.0": "active", "0.5.0": "archived", "0.1.0": "deprecated"})
    manifest = json.loads((skills / ".export-manifest.json").read_text(encoding="utf-8"))
    manifest["exports"]["other"] = {"active_version": "1.0.0",
                                    "versions": {"1.0.0": {"ides": [], "last_exported": "2026-01-01",
                                                           "status": "active"}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    command = _skill_level_calls()[drop_mode]
    proc = subprocess.run(_argv(command, {"manifestOpsHelper": str(MANIFEST_OPS),
                                          "skills_output_folder": str(skills), "target_skill": "cognee"}),
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    exports = json.loads((skills / ".export-manifest.json").read_text(encoding="utf-8"))["exports"]
    assert exports["other"]["versions"]["1.0.0"]["status"] == "active", "other entries are untouched"
    if drop_mode == "deprecate":
        entry = exports["cognee"]
        assert {v["status"] for v in entry["versions"].values()} == {"deprecated"}
        assert entry["active_version"] == "0.6.0"
    else:
        assert "cognee" not in exports


def test_the_whole_skill_deprecate_is_checked_and_reported_as_kept():
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 7. ")
    # drop-roster.py verify expects every version deprecated for a whole-skill deprecate, and no entry for a purge.
    assert "--mode {drop_mode} [--version {version}]" in _one_command(verify, "{dropRosterHelper} verify")
    assert "Pass `--version` once per `target_versions` entry for a version-level drop." in verify
    remaining = _section(_read(REPORT), "### 1. Determine Remaining Versions", "### 2. ")
    assert '**If `is_skill_level == true` and `drop_mode == "purge"`:**' in remaining
    assert "a whole-skill deprecate, which keeps every version in the manifest" in remaining
    # The refusals that offer --mode deprecate no longer say it removes the entry.
    assert "to remove the manifest entry only" not in _read(SELECT)
    assert "Use `--mode deprecate` to mark it deprecated in the manifest only" in _read(SELECT)


def test_the_purge_option_names_the_folders_the_purge_check_bound():
    """The [P] option and §9 read the §8b purge check, never path templates no step defines."""
    select = _read(SELECT)
    for template in ("{skill_package}", "{skill_group}", "{forge_version}", "{forge_group}"):
        assert template not in select, template
    option = next(line for line in select.splitlines() if line.startswith("- **[P]** Purge (hard)"))
    assert "delete {affected_directories} from disk" in option
    mode = _section(select, "### 8. Ask Mode", "### 8b. ")
    assert mode.index("run the §8b purge check at the current scope") < mode.index("- **[P]** Purge (hard)")


def test_the_confirm_gate_cancel_is_interactive_only():
    """A headless run auto-confirms [Y], so the [N] HALT and the cancel rule print no envelope."""
    select = _read(SELECT)
    confirm = _section(select, "### 10. Confirmation Gate", "### 12. ")
    cancel = next(line for line in confirm.splitlines() if line.startswith("- **If `N`**"))
    assert 'HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `select:confirm`).' in cancel
    assert "halt envelope" not in cancel
    rules = _section(select, "## Rules", "## MANDATORY SEQUENCE")
    assert "headless envelope" not in rules and "the §10 commit gate adds its own tip on top of this" in rules


# --------------------------------------------------------------------------
# #597: the counts come from the roster, the new active version from resolve
# --------------------------------------------------------------------------

def test_no_drop_file_reads_the_version_paths_knowledge():
    for path in sorted(DROP.rglob("*")):
        if path.suffix in (".md", ".toml"):
            text = path.read_text(encoding="utf-8")
            assert "versionPathsKnowledge" not in text and "knowledge/version-paths.md" not in text, path.name


def test_the_guard_and_the_blast_radius_read_the_roster_counts():
    select = _read(SELECT)
    versions = _section(select, "### 5. Display Version Details", "### 6. ")
    assert "Bind `{version_rows}` ← the `versions` of `{target_skill}`'s roster entry" in versions
    assert "`{version_counts}` ← its `counts`" in versions
    assert "{skillInventoryHelper} resolve" not in versions, "the roster already holds the rows"
    guard = _section(select, "### 7. Active Version Guard", "### 8. ")
    assert "`{version_counts}.non_deprecated` (§5) is above `1`" in guard
    assert "The guard never counts by hand" not in guard, "§5 defines the count"
    assert "Count the number of OTHER versions" not in guard
    assert "without `{version_counts}`" not in guard, "the roster always gives the counts"
    blast = _section(select, "#### 9b.", "### 10. ")
    assert "`{version_counts}.non_deprecated` (§5)" in blast and "`{version_counts}.on_disk` for a draft" in blast
    assert "count of non-deprecated versions in" not in blast and "Without `{version_counts}`" not in blast
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    # #1158: the repair helper picks the version, never the prompt from `resolve`'s fields.
    for gone in ("{skillInventoryHelper} resolve", "resolve.newest_non_deprecated", "resolve.counts.non_deprecated",
                 "{new_active_version}", "the newest non-deprecated version in its `versions` map"):
        assert gone not in delete, gone


def _write_skill(skills: Path, name: str, version: str) -> None:
    package = skills / name / version / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_bytes(f"# {name} {version}\n".encode("utf-8"))
    (package / "metadata.json").write_bytes(json.dumps(
        {"name": name, "version": version, "generated_by": "create-skill"}).encode("utf-8"))


def _write_manifest(skills: Path, name: str, active: str, statuses: dict) -> None:
    versions = {v: {"ides": ["claude-code"], "last_exported": "2026-01-01", "status": s}
                for v, s in statuses.items()}
    manifest = {"schema_version": "2", "exports": {name: {"active_version": active, "versions": versions}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))


def _roster_entry(skills: Path, forge: Path, name: str) -> dict:
    """The roster entry of `name`, from select.md §2's documented call with its `--skill` group kept."""
    command = _one_command(_section(_read(SELECT), "### 2. Read the Roster", "### 3. "), "{dropRosterHelper} skills")
    command = command.replace('[--skill "{skill_name}"]', '--skill "{skill_name}"')
    proc = _run(command, {"dropRosterHelper": str(ROSTER), "skills_output_folder": str(skills),
                          "forge_data_folder": str(forge), "skill_name": name})
    result = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and result["status"] == "ok", result
    [entry] = result["skills"]
    return entry


def _resolve(rel: str, start: str, end: str, skills: Path, forge: Path, name: str) -> dict:
    command = _one_command(_section(_read(rel), start, end), "{skillInventoryHelper} resolve")
    proc = _run(command, {"skillInventoryHelper": str(INVENTORY), "skills_output_folder": str(skills),
                          "forge_data_folder": str(forge), "target_skill": name})
    result = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and result["status"] == "ok", result
    return result["resolve"]


@pytest.mark.parametrize("statuses, refused", [
    ({"0.6.0": "active", "0.5.0": "archived", "0.1.0": "deprecated"}, True),
    ({"0.6.0": "active", "0.5.0": "deprecated", "0.1.0": "deprecated"}, False),
], ids=["another-version-kept", "only-non-deprecated"])
def test_roster_counts_drive_the_active_version_guard(tmp_path, statuses, refused):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in statuses:
        _write_skill(skills, "cognee", version)
    _write_manifest(skills, "cognee", "0.6.0", statuses)
    forge.mkdir()
    entry = _roster_entry(skills, forge, "cognee")
    assert [row["version"] for row in entry["versions"]] == ["0.6.0", "0.5.0", "0.1.0"]
    # §7: dropping the active 0.6.0 is refused when the count is above 1.
    assert (entry["counts"]["non_deprecated"] > 1) is refused


@pytest.mark.parametrize("recovery", ["out-of-run", "keep"])
def test_the_guard_refusal_names_a_recovery_that_works(recovery):
    """enhancement-3 (gate run 3), #1172: the refusal names Export Skill's `--version`, which points the
    `active` link at the version to keep, so no step asks for a flip by hand. #1160 enhancement-1: the guard first
    offers [K] Keep, which makes the roster's `keep_candidate` active and drops the old version in the same run
    (headless: `keep=<version>`); the refusal and its out-of-run recipe stay for a run with nothing to keep, and a
    headless refusal names the `keep=` value to re-run with."""
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    safety = _section(_read("docs/workflows.md"), "### Drop Skill (DS)", "**Preview first:**")
    drop = _section(_read("src/knowledge/version-paths.md"), "### Drop (DS - Drop Skill)", "**Skill-level drop:**")
    for text in (guard, safety, drop):
        assert "ln -s" not in text, "Git Bash without symlink rights turns `ln -s` into a copy of the folder"
        assert "flip-link" not in text, "Export Skill moves the link: no recovery asks for a flip by hand"
    if recovery == "out-of-run":
        assert "with a different version selected" not in guard, "the refusal names the command to run"
        assert ("run `[EX] Export Skill {target_skill} --version <version to keep>`, which points the `active` link at "
                "that version, exports it and archives `{version}`, then return here to drop `{version}`") in guard
        assert ("In (a), `<version to keep>` is the `keep_candidate` of `{target_skill}`'s roster entry; when it is "
                "null, show `<version to keep>` as written.") in guard
        assert "first `{version_rows}` entry other than" not in guard, "the roster helper picks it (#1158)"
        # The recovery runs no command of select.md's own, so it binds no helper for it.
        assert "atomicWrite" not in _read(SELECT)
        assert ("- **Otherwise** (a headless run, or no such `keep_candidate`): refuse the drop with the message below "
                "and HALT (exit code 5, `halt_reason: \"active-version-guard-refused\"`") in guard
        # The docs keep Export Skill's `--version` for a drop that does not keep another version.
        assert ("`@Ferris EX <name> --version <version to keep>`, which points the skill's `active` link at it, "
                "exports it and archives the old one") in safety
        assert ("`[EX] Export Skill <skill> --version <version to keep>` points the `active` link at it, exports it, "
                "and its manifest update archives the old one") in drop
        assert "switch active to another version first" not in drop
        assert "Otherwise, the user must either make the version they keep active first" in drop
        return
    # The keep path: one run, offered with the roster's pick, taken headless only through `keep`.
    assert "**GATE [default: use args]:** a `keep` argument answers this section in either mode" in guard
    assert ("- **Interactive, when `{target_skill}`'s roster entry has a `keep_candidate` other than `{version}`:** "
            "ask") in guard
    assert "  - **[K]** Keep `{keep_candidate}`: make it active, then drop `{version}`\n" in guard
    assert "  - **[A]** All versions: drop every version of `{target_skill}` at once\n" in guard
    assert ("On [K], bind `keep_version` ← `{keep_candidate}`. On [A], set `target_versions = \"all\"` and "
            "`is_skill_level = true`.") in guard
    # [A] widens the scope §6 chose, so the purge check runs at the whole skill.
    assert "**The purge check.** Run it at the scope §6 or §7 chose," in _section(_read(SELECT), "### 8b. ", "### 9. ")
    # A keep_candidate equal to the dropped version (a manifest with two `active` rows) is no keep §7 accepts.
    assert ("A headless refusal whose `keep_candidate` is neither null nor `{version}` ends with: \"Or re-run with "
            "`keep={keep_candidate}` to make `{keep_candidate}` active and drop `{version}` in one run.\"") in guard
    level = _section(_section(_read(EXECUTE), "### 2. Update Export Manifest", "### 3. "),
                     "**If `is_skill_level == false` (version-level drop):**", "**If `is_skill_level == true`")
    assert level.index("{updateActiveSymlinkHelper} update") < level.index(" set ") < level.index(" deprecate ")
    rendered = _section(_read(REPORT), "### 2. Render the Report", "### Result Contract")
    assert "when `keep_version` is bound, that `{keep_version}` is now the active version" in rendered
    # The user docs describe Keep and the headless argument.
    for token in ("Drop offers Keep, which makes another version on disk active",
                  "drops the old one in the same run", "A headless drop of the active version then needs "
                  "`keep=<version>`", "exit `5` (`active-version-guard-refused`)",
                  "choose Older versions (`version=older`)"):
        assert token in safety, token
    assert ("its Keep option (`keep=<version>` in a headless run) points `active` at that version and records it as "
            "the manifest's active version, then drops the old one in the same run") in drop
    # Lane review: the Manifest-lag guard names Keep, a backward flip that records `active_version` in the same run.
    [lag] = [line for line in _read("src/knowledge/version-paths.md").splitlines() if "**Manifest-lag guard.**" in line]
    assert "only changes when `export-skill` runs or `drop-skill` keeps another version" in lag
    assert ("and `drop-skill`'s Keep, which halts in that case too, and whose re-run with the same arguments reconciles "
            "them") in lag
    assert "the one workflow that flips" not in lag and "it never leaves them diverged" not in lag


def _link_active(group: Path, version: str) -> None:
    """Point `active` at a version, as `ln -sfn` does: a symlink, or a junction on Windows without the privilege."""
    active = group / "active"
    if os.path.lexists(active):
        try:
            active.unlink()
        except OSError:
            os.rmdir(active)  # a directory link on Windows
    try:
        active.symlink_to(version, target_is_directory=True)
    except OSError as e:
        if os.name != "nt":
            pytest.skip(f"symlinks are not available: {e}")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(active), str((group / version).resolve())],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            pytest.skip("neither a symlink nor a junction can be created")


def _export_resolve(skills: Path, forge: Path, name: str, version: str | None = None) -> dict:
    """The version Export Skill exports: its load step's documented `resolve` call, with `--version` when given."""
    load = _section(_read(EXPORT_LOAD), "### 2. Load and Validate Skill Artifacts", "### 3. ")
    command = _one_command(load, "{skillInventoryHelper} resolve")
    group = " [--version {requested_version}]"
    assert command.endswith(group), "§2 passes `--version` only when step 1 bound it"
    command = command[:-len(group)] + (" --version {requested_version}" if version is not None else "")
    proc = _run(command.replace("{skill-name}", "{skill_name}"),
                {"skillInventoryHelper": str(INVENTORY), "skills_output_folder": str(skills),
                 "forge_data_folder": str(forge), "skill_name": name, "requested_version": version})
    result = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and result["status"] == "ok", result
    return result["resolve"]


def test_the_guard_recovery_lets_the_drop_through(tmp_path):
    """Roll back a bad latest version: drop the active 0.6.0 and keep 0.5.0."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    statuses = {"0.6.0": "active", "0.5.0": "archived", "0.1.0": "deprecated"}
    for version in statuses:
        _write_skill(skills, "cognee", version)
    _write_manifest(skills, "cognee", "0.6.0", statuses)
    forge.mkdir()
    _link_active(skills / "cognee", "0.6.0")
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["counts"]["non_deprecated"] > 1, "§7 refuses to drop the active 0.6.0"
    # Re-running Export Skill alone exports 0.6.0 again, and §7 would refuse again.
    assert _export_resolve(skills, forge, "cognee")["chosen_version"] == "0.6.0"
    keep = entry["keep_candidate"]  # select.md §7 (a): the roster names the version to keep (#1158)
    assert keep == "0.5.0"
    # The recovery the refusal names, as the agent fills it in: Export Skill with `--version 0.5.0`.
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    assert re.search(r"run `\[EX\] Export Skill \{target_skill\} --version <version to keep>`", guard)
    resolved = _export_resolve(skills, forge, "cognee", keep)
    assert (resolved["chosen_version"], resolved["reason"], resolved["skill_package_exists"]) == (
        "0.5.0", "requested", True)
    # Export's manifest step points `active` at it, then records the version in the exported package's metadata.json.
    update = _section(_read(EXPORT_UPDATE), "### 9b. Update Export Manifest", "### 9c. ")
    flip = _one_command(update, "{atomicWriteHelper} flip-link")
    proc = _run(flip.replace("{skill-name}", "{skill_name}"),
                {"atomicWriteHelper": str(SCRIPTS / "skf-atomic-write.py"), "skills_output_folder": str(skills),
                 "skill_name": "cognee", "requested_version": keep})
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["points_to"] == "0.5.0"
    metadata = json.loads((Path(resolved["skill_package"]) / "metadata.json").read_text(encoding="utf-8"))
    command = _one_command(update, "{manifestOpsHelper}").replace(" [--ides {ides_written}]", "")
    proc = _run(command.replace("{skill-name}", "{skill_name}"),
                {"manifestOpsHelper": str(MANIFEST_OPS), "skills_output_folder": str(skills),
                 "skill_name": "cognee", "version": metadata["version"]})
    assert proc.returncode == 0, proc.stderr
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["active_version"] == "0.5.0"
    assert {row["version"]: row["status"] for row in entry["versions"]} == {
        "0.6.0": "archived", "0.5.0": "active", "0.1.0": "deprecated"}, "§7 step 2: 0.6.0 is no longer active"
    # The manifest and the link agree, so a later plain export keeps 0.5.0.
    assert (_export_resolve(skills, forge, "cognee")["reason"], entry["active_version"]) == (
        "manifest-and-link", "0.5.0")


def test_roster_lists_a_draft_skill_by_its_folders(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("0.2.0", "0.10.0"):
        _write_skill(skills, "draft", version)
    forge.mkdir()
    entry = _roster_entry(skills, forge, "draft")
    rows = [(row["version"], row["on_disk"], row["in_manifest"]) for row in entry["versions"]]
    assert rows == [("0.10.0", True, False), ("0.2.0", True, False)], "newest first, 0.10.0 above 0.2.0"
    assert (entry["counts"]["on_disk"], entry["counts"]["non_deprecated"]) == (2, 0)
    assert entry["purge_only"] is True


def _repair(values: dict) -> subprocess.CompletedProcess:
    """§4's documented `repair-after-drop` call, filled in and run."""
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    return _run(_one_command(delete, "repair-after-drop"), values)


def _purged(tmp_path: Path, active: str | None, statuses: dict, dropped: str, link: str) -> Path:
    """The skills folder step 2 leaves after purging `dropped`: deprecated in the manifest, its folder deleted."""
    skills = tmp_path / "skills"
    for version in {*statuses, link}:
        _write_skill(skills, "cognee", version)
    _write_manifest(skills, "cognee", active, {**statuses, dropped: "deprecated"})
    _link_active(skills / "cognee", link)
    shutil.rmtree(skills / "cognee" / dropped)
    return skills


def test_the_repair_is_one_helper_call_with_one_fallback_fix():
    """#1158 determinism-1 and leanness-5: the helper reads the link and picks the version; execute.md states the
    one flip-link fix, for a helper that prints no JSON."""
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    assert _one_command(delete, "repair-after-drop") == (
        'uv run {updateActiveSymlinkHelper} repair-after-drop --skill-group "{skills_output_folder}/{target_skill}" '
        "--dropped {version}")
    assert ("A non-null `manual_fix` is the manual repair: record it in `verification_errors`, record the warning "
            "`active_link_dangling: {skills_output_folder}/{target_skill}/active: {the manual repair}`, and continue."
            ) in delete
    assert ('When no candidate exists, or the helper prints no JSON, record the same way the manual repair "if `active` '
            'still names `{version}`, run `uv run {atomicWriteHelper} flip-link --link '
            '"{skills_output_folder}/{target_skill}/active" --target <the version the manifest lists as active, else the '
            'newest one it does not list as deprecated>`, or remove the link when there is none", followed by its last '
            'stderr line in parentheses, or '
            "by `(exit <code>)` when it prints nothing on stderr.") in delete
    assert ("`{atomicWriteHelper}` is the first existing path in `{atomicWriteProbeOrder}`, or its first entry when "
            "neither exists.") in delete
    assert _read(EXECUTE).count("flip-link") == 1, "the flip-link fix is stated once"
    assert "ln -sfn" not in delete and "rm {skills_output_folder}" not in delete
    for gone in ("{updateActiveSymlinkHelper} update", "Record a `busy` exit", "mismatch`/`missing-target`"):
        assert gone not in delete, gone


@pytest.mark.parametrize("active, statuses, dropped, link, expected", [
    ("0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.5.0", "0.5.0", "0.6.0"),
    ("0.5.0", {"0.5.0": "active", "0.4.0": "archived", "0.3.0": "archived"}, "0.5.0", "0.5.0", "0.4.0"),
    ("0.5.0", {"0.5.0": "active"}, "0.5.0", "0.5.0", None),
    (None, {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived"}, "0.6.0", "0.6.0", "0.5.0"),
    ("../0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.6.0", "0.6.0", "0.5.0"),
    ("0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.5.0", "0.7.0", "0.7.0"),
], ids=["manifest-active-kept", "newest-non-deprecated", "none-left", "no-active-version",
        "active-version-not-a-folder-name", "newer-unexported-link-kept"])
def test_the_repair_points_active_at_the_version_the_rule_picks(tmp_path, active, statuses, dropped, link, expected):
    """The documented call over the state step 2 leaves: `active` named the purged version, or a newer one a writing
    workflow flipped to and never exported, which the purge leaves alone."""
    skills = _purged(tmp_path, active, statuses, dropped, link)
    proc = _repair({"updateActiveSymlinkHelper": str(SCRIPTS / "skf-update-active-symlink.py"),
                    "skills_output_folder": str(skills), "target_skill": "cognee", "version": dropped})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["manual_fix"] is None
    active_link = skills / "cognee" / "active"
    if expected is None:
        assert result["action"] == "unlinked" and not os.path.lexists(active_link)
    else:
        assert result["action"] == ("flipped" if link == dropped else "none")
        assert active_link.resolve() == (skills / "cognee" / expected).resolve()


@pytest.mark.parametrize("deprecated, expected", [((), "0.5.0"), (("0.5.0",), "0.4.0")],
                         ids=["next-kept", "deprecated-skipped"])
def test_the_version_to_keep_is_the_one_the_purge_repair_picks(tmp_path, deprecated, expected):
    """One rule: the version select.md §7 names to keep is where §4 points `active` once the active one is purged."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    statuses = {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived"}
    statuses.update({version: "deprecated" for version in deprecated})
    for version in statuses:
        _write_skill(skills, "cognee", version)
    _write_manifest(skills, "cognee", "0.6.0", statuses)
    forge.mkdir()
    _link_active(skills / "cognee", "0.6.0")
    keep = _roster_entry(skills, forge, "cognee")["keep_candidate"]
    _write_manifest(skills, "cognee", "0.6.0", {**statuses, "0.6.0": "deprecated"})
    shutil.rmtree(skills / "cognee" / "0.6.0")
    proc = _repair({"updateActiveSymlinkHelper": str(SCRIPTS / "skf-update-active-symlink.py"),
                    "skills_output_folder": str(skills), "target_skill": "cognee", "version": "0.6.0"})
    assert proc.returncode == 0, proc.stderr
    assert keep == json.loads(proc.stdout)["new_active"] == expected


def _manual_fix_argv(fix: str) -> list[str]:
    """The `uv run "<helper>" flip-link ...` command of a manual fix, run with this interpreter."""
    command = re.search(r"run `(uv run [^`]+)`", fix).group(1)
    words = shlex.split(command)
    assert words[:2] == ["uv", "run"], words
    return [sys.executable, *words[2:]]


@pytest.mark.skipif(os.name == "nt", reason="Windows refuses to open a folder with errno 13, not EISDIR; "
                    "test-skf-update-active-symlink.py runs the helper on Windows")
@pytest.mark.parametrize("broken", ["no-siblings", "lock-path-is-a-folder"])
def test_a_repair_that_fails_leaves_a_fix_that_works(tmp_path, broken):
    """#732, #1158: a copy of the helper with no skf-skill-inventory.py or skf-atomic-write.py beside it (a partial
    install) exits 1 with nothing on stdout, and execute.md's one fallback fix repairs the link; a folder at the lock
    path, after the helper picked the version, exits 2 with a `manual_fix` that repairs it once that folder is gone.
    Either way `active` still names the purged version until then."""
    helper = SCRIPTS / "skf-update-active-symlink.py"
    if broken == "no-siblings":
        (tmp_path / "scripts").mkdir()
        helper = shutil.copyfile(helper, tmp_path / "scripts" / helper.name)
    skills = _purged(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.5.0", "0.5.0")
    group = skills / "cognee"
    if broken == "lock-path-is-a-folder":
        (group / "active.skf-lock").mkdir()
    proc = _repair({"updateActiveSymlinkHelper": str(helper), "skills_output_folder": str(skills),
                    "target_skill": "cognee", "version": "0.5.0"})
    assert os.readlink(group / "active") == "0.5.0" and not (group / "active").exists(), "the link still dangles"
    if broken == "no-siblings":
        assert (proc.returncode, proc.stdout) == (1, b""), proc.stderr
        [line] = proc.stderr.decode("utf-8").splitlines()
        assert line.startswith("error: cannot load the inventory helper "), line
        delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
        fix = re.search(r"run `(uv run \{atomicWriteHelper\} flip-link [^`]+)`", delete).group(1)
        # The manifest lists 0.6.0 as active: the version the helper would have picked.
        fix = fix.replace("<the version the manifest lists as active, else the newest one it does not list as "
                          "deprecated>", "0.6.0")
        proc = _run(fix, {"atomicWriteHelper": str(SCRIPTS / "skf-atomic-write.py"),
                          "skills_output_folder": str(skills), "target_skill": "cognee"})
    else:
        assert proc.returncode == 2, proc.stderr
        result = json.loads(proc.stdout)
        assert (result["action"], result["new_active"]) == ("failed", "0.6.0")
        assert f"[Errno {errno.EISDIR}]" in result["error"] and result["manual_fix"].endswith(f"({result['error']})")
        assert result["manual_fix"].startswith("if `active` still names 0.5.0, run `uv run ")
        (group / "active.skf-lock").rmdir()  # the folder the error names goes first
        proc = subprocess.run(_manual_fix_argv(result["manual_fix"]), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert os.readlink(group / "active") == "0.6.0" and (group / "active").is_dir()


# --------------------------------------------------------------------------
# The w3 re-check findings (#591, #600): one roster call, a named target,
# warnings for the degraded outcomes, the run folder and lean stage files
# --------------------------------------------------------------------------

def test_the_roster_comes_from_one_helper_call():
    """determinism-1: no hand join of the manifest, the scan and one version call per skill."""
    select = _read(SELECT)
    roster = _section(select, "### 2. Read the Roster", "### 3. ")
    assert _one_command(roster, "{dropRosterHelper} skills") == (
        'uv run {dropRosterHelper} skills "{skills_output_folder}" --forge-data-folder "{forge_data_folder}" '
        '[--skill "{skill_name}"]')
    assert "dropRosterHelper: 'scripts/drop-roster.py'" in select.split("\n---\n", 1)[0]
    for stale in ("{manifestOpsHelper}", "affected-versions", "{skillInventoryHelper} {skills_output_folder}",
                  "manifest.exports", "result.skills[]", "result.not_skf_output"):
        assert stale not in select, stale
    assert 'HALT (exit code 3, `halt_reason: "manifest-corrupt"`, phase `select:manifest-read`' in roster
    assert 'HALT (exit code 4, `halt_reason: "write-failed"`, phase `select:roster`)' in roster
    exit_4 = next(line for line in _exit_codes_table().splitlines() if line.startswith("| 4 "))
    assert "step 1 §2 when the roster helper cannot run (`write-failed`)" in exit_4


def test_a_named_skill_builds_no_roster_list():
    """enhancement-4: a supplied skill_name reads one roster entry and shows no list."""
    select = _read(SELECT)
    roster = _section(select, "### 2. Read the Roster", "### 3. ")
    assert "Pass `--skill` when a `skill_name` argument was supplied: the roster then holds that skill only." in roster
    listing = _section(select, "### 3. List Available Skills", "### 4. ")
    assert "When a `skill_name` argument was supplied, show no list: §4 takes the name." in listing
    gate = next(line for line in _section(select, "### 4. Ask Which Skill", "### 5. ").splitlines()
                if line.startswith("**GATE [default: use args]:**"))
    assert "runs §2's call again without `--skill` and shows §3's list before it asks" in gate


def test_the_skill_name_convention_has_no_second_meaning():
    """leanness-3: SKILL.md's {skill-name} is the skill's own folder name, never a listed skill."""
    for rel in (SKILL, SELECT, EXECUTE, REPORT):
        assert "{skill-name}" not in _read(rel), rel


@pytest.mark.parametrize("rel", [SELECT, EXECUTE, REPORT])
def test_the_frontmatter_names_each_helper_in_one_line(rel):
    """leanness-4: the body wires each helper where it runs; the frontmatter only binds it."""
    front = _read(rel).split("\n---\n", 1)[0]
    comments = [line for line in front.splitlines() if line.startswith("#")]
    bindings = re.findall(r"^(\w+)(?:ProbeOrder)?:", front, flags=re.M)
    assert len(comments) == len(bindings) - 1, "one comment per helper, none for nextStepFile"
    for comment in comments:
        assert re.fullmatch(r"# \{\w+\}: the §\d+b? .+\.", comment), comment
    for internal in ("semver", "os.replace", "temp-symlink", "Matches skf-update-skill", "first hit wins"):
        assert internal not in front, internal


def test_select_cuts_the_dead_state_and_the_helper_narration():
    """leanness-1, -6, -7 and -8."""
    select = _read(SELECT)
    for dead in ("manifest_exists", "bytes_total_raw", "blast_radius ="):
        assert dead not in select, dead
    guard = _section(select, "### 8b. Purge Guard", "### 9. ")
    for narration in ("`0.1.0-rc/` is not version `0.1.0`", "with or without a trailing `/`",
                      "SKF's own `improvement-queue`", "unless both settings name one folder"):
        assert narration not in guard, narration
    assert "The helper alone decides what a purge may delete" in guard
    affected = _section(select, "### 9. Compute Affected Directories", "#### 9b.")
    assert "The helper writes each path" not in affected
    blast = _section(select, "#### 9b.", "### 10. ")
    assert "execute.md §4 measures" not in blast and "so the user sees the scale" not in blast
    confirm = _section(select, "### 10. Confirmation Gate", "### 12. ")
    assert confirm.count("so the user sees the scale before scanning paths") == 1
    assert "The wording stays the same" not in confirm
    assert confirm.count("takes precedence over the headless auto-confirm") == 1
    assert "(the envelope has no such field)" not in select
    stored = _section(select, "### 12. Load Next Step", None)
    assert len([line for line in stored.splitlines() if line.strip()]) == 2, "one paragraph naming the handoff"
    roster = _section(select, "### 2. Read the Roster", "### 3. ")
    assert "Read every skill this drop can offer in one call:\n" in roster
    for narration in ("the shared manifest helper", "never joins them by hand"):
        assert narration not in roster, narration
    listing = _section(select, "### 3. List Available Skills", "### 4. ")
    assert "§8b allows no purge" not in listing, "§8b states its own rule for a roster without the inventory helper"


def test_execute_cuts_the_helper_narration():
    """leanness-5 and -6: the helpers' internals live in their docstrings."""
    execute = _read(EXECUTE)
    for internal in ("temp file + rename", "temp-symlink", "os.replace", "the helper has no removal action",
                     "Step-01 forced", "no link or junction leads to", "has no `\"partial\"` value"):
        assert internal not in execute, internal
    delete = _section(execute, "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    assert "**Skill-level purge:**" not in delete
    stored = _section(execute, "### 7. Load Next Step", None)
    assert len([line for line in stored.splitlines() if line.strip()]) == 2, "one paragraph naming the handoff"


def test_an_interactive_halt_deletes_the_run_folder():
    """enhancement-5: an interactive cancel never leaves an empty run folder behind."""
    rule = ('An interactive HALT displays its message, emits nothing and then deletes the run folder '
            '(`rm -rf "{run_dir}"`), which nothing reads after it.')
    for rel in (SELECT, EXECUTE):
        assert rule in _section(_read(rel), "## Halts", "## MANDATORY SEQUENCE"), rel
    outputs = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Outputs** |"))
    assert "kept only after a HALT, except an interactive HALT in step 1 or 2, which deletes it" in outputs
    # The contract's Halt Envelope states the rule the step files repeat in their Halts sections.
    envelope = _section(_read(CONTRACT), "## Halt Envelope", None)
    assert ("An interactive HALT displays its message and emits nothing; in step 1 or 2 it then deletes the run "
            "folder.") in envelope
    assert "in their section 1" not in envelope


WARNINGS = {
    "context_rebuild_failed": ("### 3. Rebuild Context Files", "`context_rebuild_failed: {file}: {error}`"),
    "active_link_dangling": ("### 4. Delete Files (Purge Mode Only)",
                             "`active_link_dangling: {skills_output_folder}/{target_skill}/active: {the manual repair}`"),
    "delete_failed": ("### 4. Delete Files (Purge Mode Only)", "`delete_failed: {path}: {error}`"),
    "verification_failed": ("### 5. Verify Final State", "`verification_failed: {what failed}: {its manual fix}`"),
}


def test_each_degraded_outcome_is_recorded_as_a_warning():
    """enhancement-2: a run that reads `success` still names what needs a manual fix."""
    execute = _read(EXECUTE)
    rules = _section(execute, "## Rules", "## MANDATORY SEQUENCE")
    assert "`uv run {emitEnvelopeHelper} record --run-dir \"{run_dir}\" --warning '<the warning>'`" in rules
    sections = ["### 2. ", "### 3. ", "### 4. ", "### 5. ", "### 7. "]
    for name, (start, text) in WARNINGS.items():
        end = sections[sections.index(start[:7]) + 1]
        assert text in _section(execute, start, end), name
    field = next(line for line in _read(CONTRACT).splitlines() if line.startswith("- `warnings`:"))
    for name in (*WARNINGS, "result_file_write_failed", "customization_resolver_unavailable"):
        assert f"`{name}: " in field, name
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    assert "The payload carries no `warnings`: the emitter adds the ones step 2 recorded" in contract
    for name in WARNINGS:
        assert name not in contract, f"{name}: invocation-contract.md lists the warnings, the report never again"


def test_the_recorded_warnings_reach_the_envelope_and_the_record(tmp_path):
    """The warnings step 2 records go through the documented record command into both outputs."""
    rules = _section(_read(EXECUTE), "## Rules", "## MANDATORY SEQUENCE")
    command = re.search(r"`(uv run \{emitEnvelopeHelper\} record [^`]+)`", rules).group(1)
    run_dir = _run_dir(tmp_path)
    recorded = ["context_rebuild_failed: CLAUDE.md: CLAUDE.md is not UTF-8 text",
                "active_link_dangling: /p/skills/cognee/active: ln -sfn 0.6.0 /p/skills/cognee/active"]
    for warning in recorded:
        proc = _run(command.replace("<the warning>", warning), {"emitEnvelopeHelper": str(EMITTER),
                                                                 "run_dir": str(run_dir)})
        assert proc.returncode == 0, proc.stderr
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [template] = _fenced(contract, "json")
    skills = tmp_path / "skills"
    skills.mkdir()
    payload = _fill_json(template, {**REPORT_VALUES, "files_deleted": [], "each": "", "record_status": "success"})
    payload["result_contract"]["outputs"] = []
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    proc = _run(_one_command(contract, "emit --workflow skf-drop-skill"),
                {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir), "skills_output_folder": str(skills)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    assert envelope["status"] == "success" and envelope["warnings"] == recorded
    record = json.loads((skills / "drop-skill-result-latest.json").read_text(encoding="utf-8"))
    assert record["warnings"] == recorded


def test_each_verification_failure_names_its_manual_fix():
    """architecture-3: the report points at the fixes step 2 recorded, not at a missing section."""
    report = _read(REPORT)
    assert "error-handling guidance in step 2" not in report
    assert "and each `verification_errors` entry with its manual fix." in report
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 7. ")
    # #1158: the helper names each failure's fix; the prose names only the fix for a call that fails.
    assert "Each `failures` entry is one failed check: its `detail` is what failed and its `manual_fix` the fix." in verify
    assert ("the fix is to check the `{target_skill}` entry of `{skills_output_folder}/.export-manifest.json` by hand "
            "and re-run `[EX] Export Skill`") in verify
    assert "record it in `verification_errors` with its manual fix" in verify
    assert ("If any verification fails, record it in `verification_errors` with its manual fix, record the warning "
            "`verification_failed: {what failed}: {its manual fix}`") in verify
    rendered = _section(report, "### 2. Render the Report", "### Result Contract")
    assert "each `delete_failures` path with its error and its fix `rm -rf {path}`" in rendered


def test_the_context_check_reads_no_snippet_text():
    """determinism-3: §5 asks the roster helper for the dropped skill's rows, never every row's text. #1158
    determinism-4: the manifest check is the same call, never `get` JSON read by hand."""
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 7. ")
    assert _one_command(verify, "{dropRosterHelper} verify") == (
        'uv run {dropRosterHelper} verify "{skills_output_folder}" --skill {target_skill} --mode {drop_mode} '
        "[--version {version}] {each file in context_files_updated, quoted}")
    for gone in ("orphan-detect", "orphan_managed_rows", "{manifestOpsHelper}", "entry.versions", '"not_found"'):
        assert gone not in verify, gone


@pytest.mark.parametrize("drop_mode, versions, statuses, failed", [
    ("purge", ["0.5.0"], {"0.6.0": "active", "0.5.0": "deprecated"}, []),
    ("deprecate", [], {"0.6.0": "deprecated", "0.5.0": "deprecated"}, []),
    ("deprecate", [], {"0.6.0": "active", "0.5.0": "deprecated"}, ["manifest"]),
    ("purge", [], None, []),
    ("purge", [], {"0.6.0": "deprecated"}, ["manifest"]),
], ids=["version-purge", "skill-deprecate", "skill-deprecate-unmet", "skill-purge", "skill-purge-unmet"])
def test_execute_runs_the_final_state_check_it_documents(tmp_path, drop_mode, versions, statuses, failed):
    """§5's call, filled in as an agent fills it, over the manifest and the context file step 2 left."""
    skills = tmp_path / "skills"
    skills.mkdir()
    if statuses is not None:
        _write_manifest(skills, "cognee", "0.6.0", statuses)
    claude = tmp_path / "CLAUDE.md"
    claude.write_bytes(b"# Project\n")
    command = _one_command(_section(_read(EXECUTE), "### 5. Verify Final State", "### 7. "), "{dropRosterHelper} verify")
    command = command.replace("[--version {version}]", "--version {version}" if versions else "")
    command = command.replace("{each file in context_files_updated, quoted}", "{context_file}")
    proc = _run(command, {"dropRosterHelper": str(ROSTER), "skills_output_folder": str(skills),
                          "target_skill": "cognee", "drop_mode": drop_mode, "version": "0.5.0",
                          "context_file": str(claude)})
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert [f["check"] for f in result["failures"]] == failed
    for failure in result["failures"]:
        assert failure["manual_fix"] == f"correct the `cognee` entry of `{skills / '.export-manifest.json'}` by hand"


def test_no_step_decides_what_a_helper_computes():
    """#1158: the acceptance grep. execute.md and report.md keep no assemble call, no bare `{skill_root}`, no
    `affected-versions` and no hand rule over `resolve`; SKILL.md binds the guard from `activation`."""
    for rel in (EXECUTE, REPORT):
        text = _read(rel)
        for gone in ("{skill_root}", "assemble", "affected-versions", "{skillInventoryHelper} resolve",
                     "resolve.newest_non_deprecated"):
            assert gone not in text, f"{rel}: {gone}"
    rebuild = _section(_read(EXECUTE), "### 3. Rebuild Context Files", "### 4. ")
    assert _one_command(rebuild, "{rebuildManagedSectionsHelper}") == (
        'python3 {rebuildManagedSectionsHelper} rebuild --project-root "{project-root}" --ides "{ides}" '
        '--skills-folder "{skills_output_folder}" --dropped {target_skill} '
        '[--skill-root-override "{snippet_skill_root_override}"]')
    assert ("`rebuild` resolves `target_context_files` again from the same `{ides}` (the comma-joined `ides` list of "
            "`config.yaml`, as select.md §9b passed it), so it rebuilds the files §10 counted") in rebuild
    assert ("Bind `context_files_updated` ← `updated` and `context_files_failed` ← the `file` of each `failed` entry, "
            "show each `warnings[]` line") in rebuild
    for gone in ("{context_path}", ".skf-content", "skipped_deprecated", "`case`"):
        assert gone not in rebuild, gone
    remaining = _section(_read(REPORT), "### 1. Determine Remaining Versions", "### 2. ")
    assert _one_command(remaining, "{dropRosterHelper}") == (
        'uv run {dropRosterHelper} skills "{skills_output_folder}" --forge-data-folder "{forge_data_folder}" '
        '--skill "{target_skill}"')
    assert "whose `in_manifest` is true, in the roster's order" in remaining
    assert "dropRosterHelper: 'scripts/drop-roster.py'" in _read(REPORT).split("\n---\n", 1)[0]


# --------------------------------------------------------------------------
# #1159: no rule, display template or narration that changes no move
# --------------------------------------------------------------------------

def test_the_workflow_rules_name_no_hand_fallback():
    """leanness-1: every call site names what happens without its helper, so the Rules never send the work to the
    main thread; leanness-3: the Rules select.md owns, and the facts only step 2 reads, leave SKILL.md."""
    rules = _section(_read(SKILL), "## Workflow Rules", "## Stages")
    assert "achieve the outcome in your main context thread" not in rules
    assert ("- Never do by hand what a helper does: an envelope, a manifest or context-file write, or whether SKF "
            "generated a folder. A missing On-Activation §4 helper halts the run before the first prompt, and every "
            "other call site says what happens without its helper\n") in rules
    for owned in ("enforce the active version guard", "exit cleanly with exit code 6"):
        assert owned not in rules, f"select.md states it: {owned}"
    skill = _read(SKILL)
    for gone in ("nothing is deleted silently", "Shared context-file rebuild", "the three skills that write the section",
                 "every row's `root:` takes it", "A draft skill cannot be deprecated"):
        assert gone not in skill, gone
    assert "   - `snippet_skill_root_override`\n" in skill, "the key alone: execute.md §3 says how it is passed"
    assert ("- `skf-export-skill/assets/managed-section-format.md` documents the managed section step 2 rebuilds, "
            "`snippet_skill_root_override` included.") in _section(skill, "## Conventions", "## Role")


def test_skill_md_stays_under_its_token_budget():
    """architecture-4: SKILL.md loads on every run; #1159 brought it from 2,737 cl100k tokens (11,318 characters)
    to about 2,390 (9,713). 10,100 characters holds it under the 2,500-token budget without a tokenizer."""
    assert len(_read(SKILL)) < 10_100, len(_read(SKILL))


def test_a_purge_whose_sizing_helper_fails_shows_disk_freed_as_unknown():
    """leanness-1: §4 item 3 names its own fallback, and the documented call can take it."""
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    item = _section(delete, "3. Format the size of the deleted folders", "**Classify the deletion outcome")
    assert 'When the helper exits non-zero or prints no JSON, store `disk_freed` as `"unknown"`.' in item
    proc = _run(_one_command(item, "humanize"), {"dirSizesHelper": str(DROP / "scripts" / "dir-sizes.py"),
                                                 "bytes_freed": "not-a-number"})
    assert proc.returncode != 0
    with pytest.raises(ValueError):
        json.loads(proc.stdout)


@pytest.mark.parametrize("rel", [SELECT, EXECUTE, REPORT])
def test_the_named_shouted_lines_and_the_report_template_are_gone(rel):
    """leanness-2 and -6: the report is one sentence naming what it shows, and the shouted lines #1159 names read
    plain. The select.md §10 confirmation and the execute.md §3 progress line keep their templates: #1159 names
    neither."""
    text = _read(rel)
    for gone in ("ONLY WHEN", "must NOT", "§1 halt envelope", "### 1. Halt Envelope"):
        assert gone not in text, f"{rel}: {gone}"
    if rel == REPORT:
        assert "{if " not in text


@pytest.mark.parametrize("rel, kept", [
    (SELECT, ["2", "3", "4", "5", "6", "7", "8", "8b", "9", "9b", "10", "12"]),
    (EXECUTE, ["2", "3", "4", "5", "7"]),
])
def test_the_halt_rule_is_a_preamble_and_the_sections_keep_their_numbers(rel, kept):
    """leanness-6: the halt rule is no step, the stored-decision sections fold into Load Next Step, and no kept
    section is renumbered, so a "§n" elsewhere still names the same section."""
    text = _read(rel)
    assert text.index("\n## Rules\n") < text.index("\n## Halts\n") < text.index("\n## MANDATORY SEQUENCE\n")
    sequence = _section(text, "## MANDATORY SEQUENCE", None)
    assert re.findall(r"^#{3,4} (\d+b?)\. ", sequence, flags=re.M) == kept
    load = _section(text, f"### {kept[-1]}. Load Next Step", None)
    assert "Store" not in "".join(re.findall(r"^#+ .*$", text, flags=re.M)), "no section only stores context"
    assert "(the sequence above enforces this ordering)" not in load


def test_select_numbers_only_true_sequences():
    """leanness-6: the guard is one condition and 9b three independent values."""
    select = _read(SELECT)
    guard = _section(select, "### 7. Active Version Guard", "### 8. ")
    assert re.search(r"^\s*(\d+|[a-c])\. ", guard, flags=re.M) is None
    assert ("When `target_in_manifest` is true, one version was selected (§6 [N]), its `{version_rows}` entry's "
            "`status` is `\"active\"`, `{version_counts}.non_deprecated` (§5) is above `1` and no `keep_version` is "
            "bound, the drop would leave `{target_skill}` without an active version:") in guard
    assert ("refuse the drop with the message below and HALT (exit code 5, "
            "`halt_reason: \"active-version-guard-refused\"`, phase `select:active-version-guard`), with "
            "`skill: \"{target_skill}\"` and `versions_affected: [\"{version}\"]` in the halt envelope.") in guard
    assert guard.rstrip().endswith("When the guard does not apply, or [K] or [A] answered it, continue to §8.")
    blast = _section(select, "#### 9b.", "### 10. ")
    for value in ("versions_count", "bytes_total", "context_files_count"):
        assert f"\n- **`{value}`**" in blast, value
    assert re.search(r"^\d\. ", blast, flags=re.M) is None


def test_the_displays_name_what_they_show():
    """leanness-4 and -2: the §3 list, the §5 version details and the report are each a sentence naming the facts
    shown, not a fill-in block; the draft note and the remaining-versions example are gone. The variant eval of
    #1159 checked each display against HEAD's template."""
    select = _read(SELECT)
    listing = _section(select, "### 3. List Available Skills", "### 4. ")
    versions = _section(select, "### 5. Display Version Details", "### 6. ")
    for display in (listing, versions):
        assert "```" not in display, "no display template"
    for fact in ('("on disk only" when its `in_manifest` is false)', "a trailing `*` on the one whose `active` is true",
                 'a `purge_only` skill shows "(not in manifest: purge only)" in place of its versions',
                 '"Not offered (not SKF output): {not_offered}"'):
        assert fact in listing, fact
    assert "the skills numbered from 1" in listing and "its number from the list above" in select, "§4 takes a number"
    assert ("**If `target_in_manifest = true`**, display every `{version_rows}` entry with `in_manifest` true: its "
            "version, its `status` with a trailing `*` on the row whose `active` is true, its `last_exported` and its "
            "`ides`.") in versions
    assert ("**If `target_in_manifest = false`**, display each `{version_rows}` entry whose `on_disk` is true, newest "
            "first, or \"(flat layout)\" when the roster entry's `layout` is \"flat\".") in versions
    assert "soft-deprecate is not available" not in select, "§8 case 3 says a draft is purged"
    report = _read(REPORT)
    remaining = _section(report, "### 1. Determine Remaining Versions", "### 2. ")
    assert len(_fenced(remaining, "")) == 0 and len(_fenced(remaining, "bash")) == 1
    assert "with a trailing `*`; that list is `remaining_versions_display`." in remaining
    rendered = _section(report, "### 2. Render the Report", "### Result Contract")
    assert "```" not in rendered
    for fact in ("the operation (Deprecate or Purge)", "whether the manifest was updated (`manifest_updated`)",
                 'the context files rebuilt (`context_files_updated`, or "(none)")',
                 "each one in `context_files_failed`", "`disk_freed`",
                 'the folders deleted (`files_deleted`, or "(none: nothing on disk)")',
                 "each `delete_failures` path with its error and its fix `rm -rf {path}`",
                 '`forge_left_in_place` as "Left in place (not SKF output)" when it is set',
                 "`remaining_versions_display`",
                 "setting the version's `status` back to `\"active\"` or `\"archived\"` in "
                 "`{skills_output_folder}/.export-manifest.json`, then running `[EX] Export Skill`, reverses the drop",
                 "each `verification_errors` entry with its manual fix"):
        assert fact in rendered, fact


def test_the_stages_cut_the_narration_of_helper_internals():
    """leanness-7: what a helper does inside, and lines that restate their neighbours, leave the stages."""
    narration = {
        SELECT: ("The emitter folds each recorded decision", "A headless run reaches this case only with",
                 "A purge deletes only what SKF generated, and the inventory helper decides what that is"),
        EXECUTE: ("other entries are untouched", "The run ends here", "removes any trailing",
                  "output-contract-schema.md"),
        REPORT: ("The emitter stamps the UTC time", "The health-check step is the true terminal step"),
        CONTRACT: ("in their section 1",),
    }
    for rel, gone in narration.items():
        text = _read(rel)
        for line in gone:
            assert line not in text, f"{rel}: {line}"
    assert "If the command fails, go on: only that entry is lost." in _section(_read(SELECT), "### 8. Ask Mode",
                                                                              "### 8b. ")
    assert "SKF never deletes through a link." in _read(EXECUTE)
    chain = _section(_read(REPORT), "### 3. Chain to Health Check", None)
    assert ("Once the report is shown and the record emitted, load, read the full file, and execute "
            "`{nextStepFile}`: the health check is the terminal step, and in a headless run it prints the envelope as "
            "the last line, so stopping at the report loses it. Do not re-run an earlier step after it "
            "completes.") in chain


# --------------------------------------------------------------------------
# #1160: keep another version active, and drop every older version, in one run
# --------------------------------------------------------------------------

UPDATE_ACTIVE = SCRIPTS / "skf-update-active-symlink.py"
EACH_VERSION = "{each version in target_versions, space-separated}"
# select.md §7's check of a `keep` argument, which _keep_is_valid restates over the roster's rows.
KEEP_CHECK = ("When a `keep` argument was supplied, check it first, in either mode: it names a `{version_rows}` entry "
              "that is not in `target_versions`, with `in_manifest` and `on_disk` true and a `status` other than "
              "`\"deprecated\"`, and `target_versions` is not `\"all\"`.")
# select.md §8b's merge of the purge checks over several versions, which _merge_purge_checks restates.
PURGE_MERGE = ("Over two or more versions, merge the results in `target_versions` order: the first whose `verdict` is "
               "not `\"ok\"` (else the first) gives `{purge_verdict}`, `{purge_reason}`, `{purge_detail}`, "
               "`{purge_entries}` and the `{version}` the guard's message names, `{affected_directories}` and "
               "`{forge_errors}` join every result's lists in order, and `{forge_left_in_place}` is the list of their "
               "non-null values, or null when every one is null.")


def _version_level_calls() -> dict:
    """execute.md §2's version-level commands: the keep's link and manifest calls, then the one deprecate."""
    manifest = _section(_read(EXECUTE), "### 2. Update Export Manifest", "### 3. ")
    level = _section(manifest, "**If `is_skill_level == false` (version-level drop):**",
                     "**If `is_skill_level == true`")
    return {"update": _one_command(level, "{updateActiveSymlinkHelper} update"),
            "set": _one_command(level, "{manifestOpsHelper} {skills_output_folder} set "),
            "deprecate": _one_command(level, "{manifestOpsHelper} {skills_output_folder} deprecate ")}


def _values(skills: Path, **extra) -> dict:
    return {"updateActiveSymlinkHelper": str(UPDATE_ACTIVE), "manifestOpsHelper": str(MANIFEST_OPS),
            "dropRosterHelper": str(ROSTER), "skillInventoryHelper": str(INVENTORY),
            "skills_output_folder": str(skills), "target_skill": "cognee", **extra}


def _set_exported(skills: Path, version: str, date: str) -> None:
    path = skills / ".export-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["exports"]["cognee"]["versions"][version]["last_exported"] = date
    path.write_bytes(json.dumps(manifest).encode("utf-8"))


def _keep_is_valid(rows: dict, keep: str, target_versions) -> bool:
    """KEEP_CHECK over the roster's rows, keyed by version."""
    row = rows.get(keep)
    return (target_versions != "all" and row is not None and keep not in target_versions
            and row["in_manifest"] and row["on_disk"] and row["status"] != "deprecated")


def _final_state(skills: Path, versions: list[str]) -> dict:
    """execute.md §5's documented check of a version-level deprecate, one `--version` per dropped version."""
    verify = _one_command(_section(_read(EXECUTE), "### 5. Verify Final State", "### 7. "), "{dropRosterHelper} verify")
    command = (verify.replace("[--version {version}]", " ".join(f"--version {v}" for v in versions))
               .replace(" {each file in context_files_updated, quoted}", ""))
    proc = _run(command, _values(skills, drop_mode="deprecate"))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _emit_halt(tmp_path: Path, halt: dict) -> dict:
    run_dir = _run_dir(tmp_path)
    (run_dir / "halt.json").write_bytes(json.dumps(halt).encode("utf-8"))
    proc = _run(_one_command(_read(SELECT), "emit-halt --workflow skf-drop-skill --run-dir"),
                {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    return _envelope(proc.stderr)


def _cognee(tmp_path: Path, statuses: dict, active: str, on_disk=None) -> tuple[Path, Path]:
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in statuses if on_disk is None else on_disk:
        _write_skill(skills, "cognee", version)
    _write_manifest(skills, "cognee", active, statuses)
    forge.mkdir()
    return skills, forge


@pytest.mark.parametrize("rerun", [False, True], ids=["one-run", "re-run-after-a-halt"])
def test_the_keep_path_makes_the_kept_version_active_then_drops(tmp_path, rerun):
    """enhancement-1: [K] Keep, or a headless `keep=0.5.0`, run as execute.md §2 documents it. `active` points at the
    kept version, the manifest lists it active with the export date it had (a drop exports nothing), and one call
    deprecates the dropped one. A run whose deprecate halted after `set` takes the same arguments again: §7 accepts
    the keep, its guard no longer applies, `update` is a no-op and `set` changes nothing."""
    skills, forge = _cognee(tmp_path, {"0.6.0": "active", "0.5.0": "archived", "0.1.0": "deprecated"}, "0.6.0")
    _set_exported(skills, "0.5.0", "2025-03-04")
    _link_active(skills / "cognee", "0.6.0")
    entry = _roster_entry(skills, forge, "cognee")
    keep = entry["keep_candidate"]
    assert keep == "0.5.0", "[K] offers the roster's pick"
    assert _keep_is_valid({row["version"]: row for row in entry["versions"]}, keep, ["0.6.0"])
    calls = _version_level_calls()
    values = _values(skills, keep_version=keep)
    if rerun:
        for name in ("update", "set"):  # the first run got this far, then its deprecate halted
            assert _run(calls[name], values).returncode == 0
        rows = {row["version"]: row for row in _roster_entry(skills, forge, "cognee")["versions"]}
        assert _keep_is_valid(rows, keep, ["0.6.0"]), "§7 accepts the same keep again"
        assert rows["0.6.0"]["status"] == "archived", "the guard applies to an active version only"
    proc = _run(calls["update"], values)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["action_taken"] == ("no-op" if rerun else "flipped")
    proc = _run(calls["set"], values)
    assert proc.returncode == 0, proc.stderr
    proc = _run(calls["deprecate"].replace(EACH_VERSION, "0.6.0"), values)
    assert proc.returncode == 0, proc.stderr
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["active_version"] == "0.5.0"
    assert {row["version"]: (row["status"], row["last_exported"]) for row in entry["versions"]} == {
        "0.6.0": ("deprecated", "2026-01-01"), "0.5.0": ("active", "2025-03-04"), "0.1.0": ("deprecated", "2026-01-01")}
    assert (skills / "cognee" / "active").resolve() == (skills / "cognee" / "0.5.0").resolve()
    assert _final_state(skills, ["0.6.0"])["failures"] == []


@pytest.mark.parametrize("skill, keep, target_versions, valid", [
    ("cognee", "0.5.0", ["0.6.0"], True),
    ("cognee", "0.1.0", ["0.6.0"], False),
    ("cognee", "0.4.0", ["0.6.0"], False),
    ("cognee", "0.6.0", ["0.6.0"], False),
    ("cognee", "0.5.0", "all", False),
    ("cognee", "9.9.9", ["0.6.0"], False),
    ("draft", "0.2.0", "all", False),
], ids=["kept", "deprecated", "not-on-disk", "in-scope", "version-all", "unknown", "draft"])
def test_a_keep_argument_names_a_version_this_drop_can_keep(tmp_path, skill, keep, target_versions, valid):
    """enhancement-1: §7 checks a `keep` argument in either mode against the roster's rows, and one this drop cannot
    keep halts with exit 2 before any change, the guard or no guard."""
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    assert KEEP_CHECK in guard
    assert ('When it does not, HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:active-version-guard`), '
            'with `skill: "{target_skill}"` in the halt envelope') in guard
    assert "When it does, bind `keep_version` ← it." in guard
    skills, forge = _cognee(tmp_path, {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived",
                                       "0.1.0": "deprecated"}, "0.6.0", on_disk=("0.6.0", "0.5.0", "0.1.0"))
    _write_skill(skills, "draft", "0.2.0")
    rows = {row["version"]: row for row in _roster_entry(skills, forge, skill)["versions"]}
    assert _keep_is_valid(rows, keep, target_versions) is valid
    if not valid:
        envelope = _emit_halt(tmp_path, {"phase": "select:active-version-guard", "halt_reason": "input-invalid",
                                         "exit_code": 2, "skill": skill,
                                         "reason": f"`keep` argument `{keep}` is not a version of `{skill}` this drop "
                                                   "can keep"})
        assert (envelope["exit_code"], envelope["error"]["phase"]) == (2, "select:active-version-guard")


def _atomic_write():
    spec = importlib.util.spec_from_file_location("skf_atomic_write", SCRIPTS / "skf-atomic-write.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("broken", ["missing-target", "busy", "active-is-a-folder"])
def test_a_keep_whose_link_cannot_move_halts_before_any_change(tmp_path, broken):
    """enhancement-1: `update` refuses (exit 2 with its JSON: no folder for the kept version, or another flip held
    the link's lock for its whole wait) or fails (exit 1, stderr only); §2 then halts with exit 4 before `set` runs,
    so the manifest and the link are as they were."""
    level = _section(_read(EXECUTE), "**If `is_skill_level == false` (version-level drop):**",
                     "**If `is_skill_level == true`")
    assert ('When no candidate exists, or `update` exits non-zero or prints no JSON, HALT (exit code 4, '
            '`halt_reason: "write-failed"`, phase `execute:keep-active`) in every mode, before `set` runs, with the '
            'resolved `skill`, `drop_mode` and `versions_affected` in the halt envelope') in level
    assert "Nothing was changed. Re-run the drop once the cause is fixed." in level
    skills, _ = _cognee(tmp_path, {"0.6.0": "active", "0.5.0": "archived"}, "0.6.0")
    group = skills / "cognee"
    _link_active(group, "0.6.0")
    if broken == "missing-target":
        shutil.rmtree(group / "0.5.0")
    elif broken == "active-is-a-folder":
        try:
            (group / "active").unlink()
        except OSError:
            os.rmdir(group / "active")  # a directory link on Windows
        (group / "active").mkdir()
    before = (skills / ".export-manifest.json").read_bytes()
    lock = None
    if broken == "busy":
        atomic_write = _atomic_write()
        lock = atomic_write.take_flip_lock(group / "active")
    try:
        proc = _run(_version_level_calls()["update"], _values(skills, keep_version="0.5.0"))
    finally:
        if lock is not None:
            atomic_write.release_flip_lock(group / "active", lock)
    if broken in ("missing-target", "busy"):
        assert proc.returncode == 2, proc.stderr
        result = json.loads(proc.stdout)
        assert result["status"] == broken
        cause = result["halt_message"]
        assert (group / "active").resolve() == (group / "0.6.0").resolve(), "the link is unchanged"
    else:
        assert (proc.returncode, proc.stdout) == (1, b""), proc.stderr
        cause = proc.stderr.decode("utf-8").splitlines()[0]
        assert (group / "active").is_dir() and not os.path.islink(group / "active")
    envelope = _emit_halt(tmp_path, {"phase": "execute:keep-active", "halt_reason": "write-failed", "exit_code": 4,
                                     "reason": f"SKF cannot make `0.5.0` the active version: {cause}. Nothing was "
                                               "changed. Re-run the drop once the cause is fixed.",
                                     "skill": "cognee", "drop_mode": "deprecate", "versions_affected": ["0.6.0"]})
    assert (envelope["exit_code"], envelope["halt_reason"], envelope["manifest_updated"]) == (4, "write-failed", False)
    assert envelope["error"]["phase"] == "execute:keep-active"
    assert (skills / ".export-manifest.json").read_bytes() == before, "`set` never ran"


def test_a_headless_refusal_names_the_keep_to_re_run_with(tmp_path):
    """enhancement-1: with no `keep` argument a headless drop of the active version still exits 5, and its message
    names the version the roster would keep."""
    skills, forge = _cognee(tmp_path, {"0.6.0": "active", "0.5.0": "archived", "0.1.0": "deprecated"}, "0.6.0")
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["counts"]["non_deprecated"] > 1, "the guard applies to 0.6.0"
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    [ending] = re.findall(r'ends with: "(Or re-run with [^"]+)"', guard)
    ending = ending.replace("{keep_candidate}", entry["keep_candidate"]).replace("{version}", "0.6.0")
    assert ending == "Or re-run with `keep=0.5.0` to make `0.5.0` active and drop `0.6.0` in one run."
    envelope = _emit_halt(tmp_path, {"phase": "select:active-version-guard", "halt_reason": "active-version-guard-refused",
                                     "exit_code": 5, "skill": "cognee", "versions_affected": ["0.6.0"],
                                     "reason": "Cannot drop the active version `0.6.0`. " + ending})
    assert (envelope["exit_code"], envelope["versions_affected"]) == (5, ["0.6.0"])
    assert envelope["error"]["reason"].endswith("`keep=0.5.0` to make `0.5.0` active and drop `0.6.0` in one run.")


@pytest.mark.parametrize("link, keep", [("0.7.0", None), ("0.4.0", "0.4.0")],
                         ids=["unexported-version", "older-version-made-active-by-hand"])
def test_a_keep_leaves_a_link_that_names_another_version_where_it_is(tmp_path, link, keep):
    """Lane review: `active` names 0.7.0, forged after the last export, while the manifest still lists 0.6.0 as
    active, or 0.4.0, made active by hand. Dropping 0.6.0 never offers a [K] that points the link back at 0.5.0: with
    no manifest version to keep the refusal stands, and otherwise [K] keeps the link's own version, so §2's `update`
    leaves the link where it is."""
    statuses = {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived"}
    skills, forge = _cognee(tmp_path, statuses, "0.6.0", on_disk=("0.7.0", *statuses))
    group = skills / "cognee"
    _link_active(group, link)
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["counts"]["non_deprecated"] > 1, "the guard applies to 0.6.0"
    assert entry["keep_candidate"] == keep
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    assert ("- **Interactive, when `{target_skill}`'s roster entry has a `keep_candidate` other than `{version}`:** "
            "ask") in guard
    if keep is None:
        assert "- **Otherwise** (a headless run, or no such `keep_candidate`): refuse the drop" in guard
        assert (group / "active").resolve() == (group / "0.7.0").resolve()
        return
    calls = _version_level_calls()
    values = _values(skills, keep_version=keep)
    proc = _run(calls["update"], values)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["action_taken"] == "no-op"
    for name, command in (("set", calls["set"]), ("deprecate", calls["deprecate"].replace(EACH_VERSION, "0.6.0"))):
        proc = _run(command, values)
        assert proc.returncode == 0, (name, proc.stderr)
    assert _roster_entry(skills, forge, "cognee")["active_version"] == "0.4.0"
    assert (group / "active").resolve() == (group / "0.4.0").resolve()


def _purge_check(skills: Path, forge: Path, version: str) -> dict:
    """select.md §8b's documented purge check of one version, as an agent fills it."""
    guard = _section(_read(SELECT), "### 8b. Purge Guard", "### 9. ")
    command = _one_command(guard, "--purge-check").replace("[--purge-version {version}]", "--purge-version {version}")
    proc = _run(command, _values(skills, forge_data_folder=str(forge), version=version))
    result = json.loads(proc.stdout)
    assert proc.returncode == 0 and result["status"] == "ok", result
    return result["purge_check"]


def _merge_purge_checks(results: list[dict]) -> dict:
    """PURGE_MERGE over the checks of `target_versions`, in order."""
    first = next((r for r in results if r["verdict"] != "ok"), results[0])
    left = [r["forge_left_in_place"] for r in results if r["forge_left_in_place"] is not None]
    return {"verdict": first["verdict"], "reason": first["reason"], "offending_entries": first["offending_entries"],
            "version": first["version"],
            "affected_directories": [path for r in results for path in r["affected_directories"]],
            "forge_errors": [e for r in results for e in r["forge_errors"]], "forge_left_in_place": left or None}


@pytest.mark.parametrize("link", ["0.7.0", "0.6.0"], ids=["link-on-the-active", "link-on-an-older-version"])
def test_older_versions_drop_every_version_but_the_active_one_in_one_run(tmp_path, link):
    """enhancement-3: [O] (headless `version=older`) binds the roster's `older_versions`, newest first. §8b checks
    each version and merges, §2 deprecates them in one call, §4 deletes and repairs `active` once per version and
    §5 passes one `--version` per version. The repair runs for each version, not only the active one: a link a
    writing workflow left on an older version the purge deletes points back at the active one."""
    statuses = {"0.7.0": "active", "0.6.0": "archived", "0.5.0": "archived", "0.1.0": "deprecated"}
    skills, forge = _cognee(tmp_path, statuses, "0.7.0")
    group = skills / "cognee"
    _link_active(group, link)
    target_versions = _roster_entry(skills, forge, "cognee")["older_versions"]
    assert target_versions == ["0.6.0", "0.5.0"]
    select = _read(SELECT)
    assert "  - Version-level drop: the number of `target_versions` entries\n" in _section(select, "#### 9b.", "### 10. ")
    assert PURGE_MERGE in _section(select, "### 8b. Purge Guard", "### 9. ")
    merged = _merge_purge_checks([_purge_check(skills, forge, v) for v in target_versions])
    assert (merged["verdict"], merged["forge_left_in_place"]) == ("ok", None)
    assert merged["affected_directories"] == [str(group / "0.6.0"), str(group / "0.5.0")]
    proc = _run(_version_level_calls()["deprecate"].replace(EACH_VERSION, " ".join(target_versions)), _values(skills))
    assert proc.returncode == 0, proc.stderr
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    assert "Run the call below once per `target_versions` entry, with `{version}` that entry." in delete
    paths = {f"path{i}": path for i, path in enumerate(merged["affected_directories"])}
    command = _one_command(delete, "guarded-delete").replace(
        "{each path in affected_directories, quoted, space-separated}", " ".join(f'"{{{k}}}"' for k in paths))
    proc = _run(command, _values(skills, forge_data_folder=str(forge), **paths))
    assert proc.returncode == 0, proc.stderr
    deleted = json.loads(proc.stdout)
    assert (deleted["files_deleted"], deleted["purge_status"]) == (merged["affected_directories"], "success")
    for version in target_versions:
        proc = _repair(_values(skills, version=version))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["action"] == ("flipped" if version == link else "none")
    assert (group / "active").resolve() == (group / "0.7.0").resolve()
    assert _final_state(skills, target_versions)["failures"] == []
    entry = _roster_entry(skills, forge, "cognee")
    assert {row["version"]: row["status"] for row in entry["versions"]} == {
        "0.7.0": "active", "0.6.0": "deprecated", "0.5.0": "deprecated", "0.1.0": "deprecated"}
    assert entry["older_versions"] == [], "a second [O] has nothing left to drop"


def test_an_older_versions_purge_names_the_version_that_holds_foreign_entries(tmp_path):
    """enhancement-3: the merged check refuses the purge with the first version that fails, and the guard's message
    names that version; nothing runs after the halt, so nothing is deleted."""
    skills, forge = _cognee(tmp_path, {"0.7.0": "active", "0.6.0": "archived", "0.5.0": "archived"}, "0.7.0")
    (skills / "cognee" / "0.5.0" / "NOTES.md").write_bytes(b"mine\n")
    target_versions = _roster_entry(skills, forge, "cognee")["older_versions"]
    merged = _merge_purge_checks([_purge_check(skills, forge, v) for v in target_versions])
    assert (merged["verdict"], merged["reason"], merged["version"]) == ("not-skf-output", "skill-version-mixed", "0.5.0")
    assert merged["offending_entries"] == ["0.5.0/NOTES.md"]
    guard = _section(_read(SELECT), "### 8b. Purge Guard", "### 9. ")
    [message] = re.findall(r'^- `skill-version-mixed`: "(.+)"$', guard, flags=re.M)
    message = (message.replace("{skills_output_folder}", skills.as_posix()).replace("{target_skill}", "cognee")
               .replace("{version}", merged["version"]).replace("{purge_entries}", ", ".join(merged["offending_entries"])))
    assert f"`{skills.as_posix()}/cognee/0.5.0` also holds entries SKF did not generate" in message
    envelope = _emit_halt(tmp_path, {"phase": "select:purge-guard", "halt_reason": "not-skf-output", "exit_code": 5,
                                     "skill": "cognee", "drop_mode": "purge", "reason": message})
    assert (envelope["exit_code"], envelope["error"]["phase"]) == (5, "select:purge-guard")
    assert all((skills / "cognee" / v).is_dir() for v in target_versions)


def test_an_older_versions_purge_lists_each_forge_folder_it_leaves(tmp_path):
    """enhancement-3: two forge version folders SKF did not generate are both left in place, and the dry-run,
    success and halt envelopes carry `forge_left_in_place` as a list the schema accepts."""
    skills, forge = _cognee(tmp_path, {"0.7.0": "active", "0.6.0": "archived", "0.5.0": "archived"}, "0.7.0")
    (forge / "cognee").mkdir()
    (forge / "cognee" / "skill-brief.yaml").write_bytes(b"name: cognee\n")
    for version in ("0.6.0", "0.5.0"):
        (forge / "cognee" / version).mkdir()
        (forge / "cognee" / version / "data.csv").write_bytes(b"a,b\n")
    target_versions = _roster_entry(skills, forge, "cognee")["older_versions"]
    merged = _merge_purge_checks([_purge_check(skills, forge, v) for v in target_versions])
    left = [str(forge / "cognee" / "0.6.0"), str(forge / "cognee" / "0.5.0")]
    assert (merged["verdict"], merged["forge_left_in_place"]) == ("ok", left)
    assert merged["affected_directories"] == [str(skills / "cognee" / v) for v in target_versions]
    values = {"target_skill": "cognee", "drop_mode": "purge", "target_versions": target_versions,
              "affected_directories": merged["affected_directories"], "forge_left_in_place": left}
    [dry] = _fenced(_section(_read(SELECT), "### 10. Confirmation Gate", "### 12. "), "json")
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [success] = _fenced(contract, "json")
    payloads = {"dry-run": _fill_json(dry, values),
                "success": _fill_json(success, {**REPORT_VALUES, **values, "files_deleted": values["affected_directories"],
                                                "each": values["affected_directories"][0], "record_status": "success"})}
    for status, payload in payloads.items():
        run_dir = tmp_path / status / "_bmad-output" / ".skf-run" / "skf-drop-skill-Ab3dE5gH"
        run_dir.mkdir(parents=True)
        (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
        command = _one_command(_read(SELECT) if status == "dry-run" else contract, "emit --workflow skf-drop-skill")
        proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir),
                              "skills_output_folder": str(skills)})
        assert proc.returncode == 0, proc.stderr
        envelope = _envelope(proc.stdout)
        assert (envelope["status"], envelope["forge_left_in_place"]) == (status, left)
        assert envelope["versions_affected"] == ["0.6.0", "0.5.0"]
    record = json.loads((skills / "drop-skill-result-latest.json").read_text(encoding="utf-8"))
    assert record["summary"]["forge_left_in_place"] == left
    halt = _emit_halt(tmp_path, {"phase": "execute:delete", "halt_reason": "delete-failed", "exit_code": 4,
                                 "reason": "Purge failed", "skill": "cognee", "drop_mode": "purge",
                                 "versions_affected": target_versions, "forge_left_in_place": left})
    assert (halt["exit_code"], halt["forge_left_in_place"]) == (4, left)
    schema = SCHEMA["properties"]["forge_left_in_place"]
    assert schema["type"] == ["string", "array", "null"] and schema["items"] == {"type": "string", "minLength": 1}
