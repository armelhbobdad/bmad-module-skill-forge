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
  active-version guard and the blast-radius line read; skf-skill-inventory.py
  resolve gives the version execute.md points `active` at after a version
  purge (that rule is prose the agent applies, so it is restated here as code
  and run over the helper's output). test-skf-drop-roster.py tests the roster
  helper itself.
- The active-version guard's refusal names a recovery that works (step 5b
  gate run 3, enhancement-3): Export Skill takes no version, so the commands
  its load and manifest steps document run over a fixture where `active`
  points at the version to keep; that export publishes it and archives the
  refused version, and the roster then lets the drop through.
- The prose pins: a failed manifest write halts in every mode and never reaches
  the report; `skill_name` and `version` answer their gates in both modes; the
  helpers resolve before the first prompt and no step keeps a fallback for
  them; no stage reads version-paths.md, types an envelope or makes up a
  timestamp; the mode comes only from the `mode` argument or the prompt.
- skf-manifest-ops.py runs the skill-level manifest calls execute.md documents:
  a whole-skill deprecate marks every version deprecated and keeps the entry,
  and only a purge removes it.
"""

from __future__ import annotations

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
    """The contract's Halt Envelope (for the activation HALTs), select.md and execute.md
    state the halt rule each; the command and the JSON rule never drift."""
    halt = _section(_read(CONTRACT), "## Halt Envelope", None)
    rules = {CONTRACT: halt,
             SELECT: _section(_read(SELECT), "### 1. Halt Envelope", "### 2. "),
             EXECUTE: _section(_read(EXECUTE), "### 1. Halt Envelope", "### 2. ")}
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
    confirm = _section(_read(SELECT), "### 10. Confirmation Gate", "### 11. ")
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
    "forge_left_in_place": None, "headless_mode": True, "mode_source": "--mode argument",
    "confirm_source": "headless-auto",
}


@pytest.mark.parametrize("record_status", ["success", "partial"])
def test_report_emit_writes_the_result_files(tmp_path, record_status):
    """#593: the emitter names the per-run file from the clock and writes its -latest copy."""
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [template] = _fenced(contract, "json")
    skills = tmp_path / "skills"
    skills.mkdir()
    deleted = str(skills / "cognee" / "0.5.0")
    run_dir = _run_dir(tmp_path)
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
    assert record["summary"]["headless_provenance"] == {"headless": True, "mode_source": "--mode argument",
                                                        "confirm": "headless-auto"}


def _decision(text: str, gate: str, values: dict) -> dict:
    """The decision object a gate stages, its `<name>` placeholders filled in."""
    m = re.search(r'`(\{"gate": "' + re.escape(gate) + r'"[^`]*\})`', text)
    assert m, f"no staged {gate} decision"
    return json.loads(re.sub(r"<(\w+)>", lambda v: values[v.group(1)], m.group(1)))


def test_headless_decisions_reach_the_result_record(tmp_path):
    """#593: the mode and the confirmation a headless run decides land in the record's headless_decisions."""
    select = _read(SELECT)
    mode = _section(select, "### 8. Ask Mode", "### 8b. ")
    confirm = _section(select, "### 10. Confirmation Gate", "### 11. ")
    command = _one_command(mode, "record --run-dir")
    assert "--workflow" not in command, "the drop schema has no headless_decisions to check a decision against"
    assert "run the §8 `record` command" in confirm
    run_dir = _run_dir(tmp_path)
    decisions = [_decision(mode, "select.mode", {"drop_mode": "purge", "mode_source": "--mode argument"}),
                 _decision(confirm, "select.confirm", {})]
    for decision in decisions:
        (run_dir / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
        proc = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
        assert proc.returncode == 0, proc.stderr
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    [template] = _fenced(contract, "json")
    skills = tmp_path / "skills"
    skills.mkdir()
    deleted = str(skills / "cognee" / "0.5.0")
    payload = _fill_json(template, {**REPORT_VALUES, "files_deleted": [deleted], "each": deleted,
                                    "record_status": "success"})
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    proc = _run(_one_command(contract, "emit --workflow skf-drop-skill"),
                {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir), "skills_output_folder": str(skills)})
    assert proc.returncode == 0, proc.stderr
    assert "headless_decisions" not in _envelope(proc.stdout), "the envelope has no such field"
    record = json.loads((skills / "drop-skill-result-latest.json").read_text(encoding="utf-8"))
    assert record["headless_decisions"] == decisions
    assert decisions[0]["taken_action"] == "purge" and decisions[1]["gate"] == "select.confirm"
    assert "`headless_decisions`" in contract


# --------------------------------------------------------------------------
# #585: a failed manifest write halts in every mode, before the report
# --------------------------------------------------------------------------

def test_failed_manifest_write_halts_in_every_mode():
    manifest = _section(_read(EXECUTE), "### 2. Update Export Manifest", "### 3. ")
    on_error = _section(manifest, "**On error (the helper exits non-zero):**", None)
    assert 'HALT (exit code 4, `halt_reason: "manifest-write-failed"`' in on_error
    assert "in every mode, before section 3" in on_error
    assert "step 3 never runs, so no success report is shown and no result file is written" in on_error
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
    assert "Bind `{result_json_path}` ← that line's `result_path`" in contract
    hook = _section(_read(REPORT), "### Post-drop hook", "### 3. ")
    assert "`{result_json_path}` is not null" in hook
    assert 'rm -rf "{run_dir}"' in hook


# --------------------------------------------------------------------------
# #594: helpers before the first prompt; arguments answer their gates
# --------------------------------------------------------------------------

def test_required_helpers_resolve_before_the_first_prompt():
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
    # The steps use the resolved helpers: no step resolves one again, halts on a missing one after
    # the manifest changed, or keeps an in-prompt fallback that no run can reach.
    execute = _read(EXECUTE)
    assert "If no candidate exists, HALT" not in execute
    assert "HALT (exit code 4, `halt_reason: \"manifest-write-failed\"`) if no candidate exists" not in execute
    for rel in (SELECT, EXECUTE, REPORT):
        text = _read(rel)
        for gone in ("manifestOpsProbeOrder", "rebuildManagedSectionsProbeOrder", "emitEnvelopeProbeOrder",
                     "manifest file in-prompt", "the in-prompt computation", "manifest in-prompt",
                     "by comparing version components numerically"):
            assert gone not in text, f"{rel}: {gone}"
    assert "the `{manifestOpsHelper}` On-Activation §4 resolved" in _read(REPORT)
    roster = _section(_read(SELECT), "### 3. List Available Skills", "### 4. ")
    assert ("When `{roster}.inventory` is false (the inventory helper could not run), the roster holds the manifest "
            "skills alone") in roster, "the inventory fallback stays: it changes what is offered"
    for start, end in (("### 2. Update Export Manifest", "### 3. "), ("### 3. Rebuild Context Files", "### 4. ")):
        assert "halts before the first prompt" not in _section(execute, start, end), start
    rule = next(line for line in _read(SKILL).splitlines()
                if line.startswith("- If any instruction references a subprocess"))
    assert "never type an envelope or edit the manifest or a context file yourself" in rule


def test_activation_runs_the_resolver_through_uv_and_records_its_failure():
    """#595 option (a): the resolver runs under uv with --project-root, so a
    dropped `forbid_purge_in_headless` override is never silent: a failure
    prints one warning, and step 4 records the reason in the run sink once the
    run folder and the emitter exist, through a file, so every envelope from
    there on carries it. #596: a `!` entry drops the project-context default."""
    activation = _section(_read(SKILL), "## On Activation", None)
    resolve = " ".join(_section(activation, "3. **Resolve workflow customization.**", "4. **Pre-flight").split())
    assert ("uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} "
            "--project-root {project-root} --key workflow") in resolve
    assert "python3 {project-root}/_bmad/scripts/resolve_customization.py" not in activation
    for token in ("It merges the bundled `{skill-root}/customize.toml` with "
                  "`{project-root}/_bmad/custom/skf-drop-skill.toml` (team overrides, committed) and `.user.toml` "
                  "(personal overrides, gitignored).",
                  "When it exits non-zero, prints no JSON or is missing, print one line, "
                  "`[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr "
                  "line, `not found` when the script is missing, `no JSON` when it printed none).",
                  "If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled "
                  "defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run.",
                  "Keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran)",
                  "the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed "
                  "`!` drops each earlier entry it names and loads nothing itself, so an override's "
                  '`"!file:{project-root}/**/project-context.md"` turns that default off'):
        assert token in resolve, token
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
    # An interactive HALT in step 1 or 2 deletes the run folder; the activation halts keep it.
    assert ("(step 3, a `--dry-run` at the confirmation gate, or an interactive HALT in step 1 or 2 deletes it; "
            "any other HALT keeps it)") in preflight
    toml = _read(CUSTOMIZE)
    comment = _comment(toml, "# Persistent facts the workflow keeps", "persistent_facts = [\n")
    assert ('to stop loading those files, set in {project-root}/_bmad/custom/skf-drop-skill.toml: '
            '[workflow] persistent_facts = ["!file:{project-root}/**/project-context.md"]') in comment
    # The example is an override file as written: under the table, where the resolver's `--key workflow` reads it.
    example = _section(toml, "skf-drop-skill.toml:\n", "\n\n")
    override = tomllib.loads("\n".join(line.lstrip("#").strip() for line in example.splitlines()[1:]))
    assert override == {"workflow": {"persistent_facts": ["!file:{project-root}/**/project-context.md"]}}
    assert "Each entry is either:" not in comment
    assert ("Each entry is one of: - a literal sentence" in comment
            and "- an entry prefixed with `!`, which loads nothing and drops each earlier entry it names." in comment)


def test_conventions_say_how_module_and_sibling_paths_resolve():
    """#601: drop reads `shared/` scripts and export-skill's managed-section
    format, so its Conventions say where both resolve from."""
    conventions = _section(_read(SKILL), "## Conventions", "## Role")
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
    assert "a `version` argument of `all` takes **[A]** below, and any other value takes **[N]**" in exported
    assert 'headless mode HALTs (exit code 2, `halt_reason: "input-missing"`, phase `select:scope`)' in exported
    assert "draft skills can only be dropped as a whole" not in scope, "a draft no longer ignores the argument"
    # The versions are named and checked from §5's ordered rows, never from the manifest map by eye.
    assert "one of its versions ({each `{version_rows}` entry with `in_manifest` true})" in exported
    assert "Validate that the version is a `{version_rows}` entry with `in_manifest` true." in scope
    assert "{its manifest versions, newest first}" not in scope and "`versions` map" not in scope
    versions = _section(_read(SELECT), "### 5. Display Version Details", "### 6. ")
    assert "Bind `{version_rows}` ← the `versions` of `{target_skill}`'s roster entry" in versions
    assert "affected-versions" not in _read(SELECT), "the roster orders the versions"
    gates = next(line for line in _contract_text(with_skill=True).splitlines() if line.startswith("| **Gates** |"))
    assert "Scope Gate [use args] (§6 version)" in gates


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
    sources = _section(_read(REPORT), "- `headless_provenance` persists", "\n")
    assert "`{mode_source}` and `{confirm_source}` the values step 1 set" in sources
    mode = _section(_read(SELECT), "### 8. Ask Mode", "### 8b. ")
    for source in ('`mode_source = "--mode argument"`', '`mode_source = "interactive-prompt"`',
                   '`mode_source = "draft-skill-forced-purge"`'):
        assert source in mode, source
    stored = _section(_read(SELECT), "### 11. Store Decisions in Context", "### 12. ")
    assert "`mode_source`" in stored and "`confirm_source`" in stored


def test_any_non_empty_forbid_value_turns_the_purge_guard_on():
    """A mistyped forbid_purge_in_headless that still parses blocks the purge instead of allowing it.

    An override file that fails to parse (an unquoted True, yes or on, or a
    bad line elsewhere in it) stops the resolver, so the run reads the bundled
    empty value and the guard is off: the comment, the Headless row and the
    settings list say so and ask for a quoted value.
    """
    activation = _section(_read(SKILL), "## On Activation", None)
    binding = next(line for line in activation.splitlines() if "`{forbidPurgeInHeadless}` ←" in line)
    assert "on when `workflow.forbid_purge_in_headless` holds any value other than the empty string" in binding
    assert 'non-`"true"`' not in binding
    guard = _section(activation, "Last, the headless-purge guard.", "5. Load")
    assert ('If `{headless_mode}` is true, `{forbidPurgeInHeadless}` is on and the `mode` arg is `"purge"`, '
            'HALT (exit code 6, `halt_reason: "headless-purge-forbidden"`') in guard
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
    assert "`<command> --result-path=<path>`" in on_complete
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
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 6. ")
    assert ('Skill-level deprecate: every version in `entry.versions` has `status` `"deprecated"`. '
            'Skill-level purge: `status` is `"not_found"`.') in verify
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
    confirm = _section(select, "### 10. Confirmation Gate", "### 11. ")
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
    assert "Read `{version_counts}.non_deprecated` (§5)" in guard and "above `1`" in guard
    assert "The guard never counts by hand" in guard
    assert "Count the number of OTHER versions" not in guard
    assert "without `{version_counts}`" not in guard, "the roster always gives the counts"
    blast = _section(select, "#### 9b.", "### 10. ")
    assert "`{version_counts}.non_deprecated` (§5)" in blast and "`{version_counts}.on_disk` for a draft" in blast
    assert "count of non-deprecated versions in" not in blast and "Without `{version_counts}`" not in blast
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    assert "`resolve.newest_non_deprecated`" in delete and "`resolve.counts.non_deprecated`" in delete
    assert "the newest non-deprecated version in its `versions` map" not in delete


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


def test_the_guard_refusal_names_a_recovery_that_works():
    """enhancement-3 (gate run 3): Export Skill has no version choice, so the refusal names the `active` link."""
    guard = _section(_read(SELECT), "### 7. Active Version Guard", "### 8. ")
    assert "with a different version selected" not in guard, "Export Skill takes no version"
    assert ("point the `active` link at it (`ln -sfn <version to keep> {skills_output_folder}/{target_skill}/active`), "
            "run `[EX] Export Skill` for `{target_skill}`, which exports that version and archives `{version}`, "
            "then return here to drop `{version}`") in guard
    assert ("`<version to keep>` is the first `{version_rows}` entry other than `{version}` whose `in_manifest` "
            "and `on_disk` are true and whose `status` is not `\"deprecated\"`") in guard
    safety = _section(_read("docs/workflows.md"), "### Drop Skill (DS)", "**Preview first:**")
    assert "`ln -sfn <version to keep> <skills_output_folder>/<name>/active`" in safety and "`@Ferris EX`" in safety
    drop = _section(_read("src/knowledge/version-paths.md"), "### Drop (DS - Drop Skill)", "**Skill-level drop:**")
    assert "`ln -sfn <version to keep> {skill_group}/active`" in drop
    assert "switch active to another version first" not in drop


def _version_to_keep(entry: dict, version: str) -> str | None:
    """select.md §7 (a): the `<version to keep>` the refusal names (prose the agent applies, restated as code)."""
    return next((row["version"] for row in entry["versions"] if row["version"] != version and row["in_manifest"]
                 and row["on_disk"] and row["status"] != "deprecated"), None)


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


def _export_resolve(skills: Path, forge: Path, name: str) -> dict:
    """The version Export Skill exports: its load step's documented `resolve` call."""
    load = _section(_read(EXPORT_LOAD), "### 2. Load and Validate Skill Artifacts", "### 3. ")
    command = _one_command(load, "{skillInventoryHelper} resolve")
    assert "--version" not in command, "Export Skill exports the version `resolve` chooses"
    proc = _run(command.replace("{skill-name}", "{skill_name}"),
                {"skillInventoryHelper": str(INVENTORY), "skills_output_folder": str(skills),
                 "forge_data_folder": str(forge), "skill_name": name})
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
    keep = _version_to_keep(entry, "0.6.0")
    assert keep == "0.5.0"
    _link_active(skills / "cognee", keep)
    resolved = _export_resolve(skills, forge, "cognee")
    assert (resolved["chosen_version"], resolved["reason"]) == ("0.5.0", "manifest-lags-link")
    # Export's manifest step records the version in the exported package's metadata.json.
    metadata = json.loads((Path(resolved["skill_package"]) / "metadata.json").read_text(encoding="utf-8"))
    update = _section(_read(EXPORT_UPDATE), "### 9b. Update Export Manifest", "### 9c. ")
    command = _one_command(update, "{manifestOpsHelper}").replace(" [--ides {ides_written}]", "")
    proc = _run(command.replace("{skill-name}", "{skill_name}"),
                {"manifestOpsHelper": str(MANIFEST_OPS), "skills_output_folder": str(skills),
                 "skill_name": "cognee", "version": metadata["version"]})
    assert proc.returncode == 0, proc.stderr
    entry = _roster_entry(skills, forge, "cognee")
    assert entry["active_version"] == "0.5.0"
    assert {row["version"]: row["status"] for row in entry["versions"]} == {
        "0.6.0": "archived", "0.5.0": "active", "0.1.0": "deprecated"}, "§7 step 2: 0.6.0 is no longer active"


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


def _new_active(resolved: dict) -> str | None:
    """execute.md §4: the version `active` points at after a version purge, or None to remove it."""
    if resolved["counts"]["non_deprecated"] == 0:
        return None
    status = {row["version"]: row["status"] for row in resolved["versions"]}
    active = resolved["active_version"]
    if active is None or status.get(active) == "deprecated":
        return resolved["newest_non_deprecated"]
    return active


def test_the_new_active_rule_covers_a_null_active_version():
    delete = _section(_read(EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. ")
    assert ("`{new_active_version}` ← `resolve.active_version`, the version the manifest lists as active, "
            "unless it is null or its `resolve.versions` entry has `status` `\"deprecated\"`; "
            "then `resolve.newest_non_deprecated`") in delete


@pytest.mark.parametrize("active, statuses, dropped, expected", [
    ("0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.5.0", "0.6.0"),
    ("0.5.0", {"0.5.0": "active", "0.4.0": "archived", "0.3.0": "archived"}, "0.5.0", "0.4.0"),
    ("0.5.0", {"0.5.0": "active"}, "0.5.0", None),
    (None, {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived"}, "0.6.0", "0.5.0"),
    ("../0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, "0.6.0", "0.5.0"),
], ids=["manifest-active-kept", "newest-non-deprecated", "none-left", "no-active-version",
        "active-version-not-a-folder-name"])
def test_resolve_gives_the_version_active_points_at_after_a_purge(tmp_path, active, statuses, dropped, expected):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in statuses:
        _write_skill(skills, "cognee", version)
    forge.mkdir()
    # The state step 2 leaves: the version deprecated in the manifest and its folder deleted.
    _write_manifest(skills, "cognee", active, {**statuses, dropped: "deprecated"})
    shutil.rmtree(skills / "cognee" / dropped)
    resolved = _resolve(EXECUTE, "### 4. Delete Files (Purge Mode Only)", "### 5. ", skills, forge, "cognee")
    assert _new_active(resolved) == expected


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
    for rel in (SELECT, EXECUTE, REPORT):
        assert "{skill-name}" not in _read(rel), rel


@pytest.mark.parametrize("rel", [SELECT, EXECUTE])
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
    confirm = _section(select, "### 10. Confirmation Gate", "### 11. ")
    assert confirm.count("so the user sees the scale before scanning paths") == 1
    assert "The wording stays the same" not in confirm
    assert confirm.count("takes precedence over the headless auto-confirm") == 1
    assert "(the envelope has no such field)" not in select
    stored = _section(select, "### 11. Store Decisions in Context", "### 12. ")
    assert len([line for line in stored.splitlines() if line.strip()]) == 2, "one sentence naming the handoff"
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
    stored = _section(execute, "### 6. Store Results in Context", "### 7. ")
    assert len([line for line in stored.splitlines() if line.strip()]) == 2, "one sentence naming the handoff"


def test_an_interactive_halt_deletes_the_run_folder():
    """enhancement-5: an interactive cancel never leaves an empty run folder behind."""
    rule = ('An interactive HALT displays its message, emits nothing and then deletes the run folder '
            '(`rm -rf "{run_dir}"`), which nothing reads after it.')
    for rel in (SELECT, EXECUTE):
        assert rule in _section(_read(rel), "### 1. Halt Envelope", "### 2. "), rel
    outputs = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Outputs** |"))
    assert "kept only after a HALT, except an interactive HALT in step 1 or 2, which deletes it" in outputs
    # The contract's Halt Envelope states the rule the step files repeat in their section 1.
    envelope = _section(_read(CONTRACT), "## Halt Envelope", None)
    assert ("An interactive HALT displays its message and emits nothing; in step 1 or 2 it then deletes the run "
            "folder.") in envelope
    assert "select.md and execute.md state the same rule in their section 1" in envelope


WARNINGS = {
    "context_rebuild_failed": ("### 3. Rebuild Context Files", "`context_rebuild_failed: {context_file}: {context_error}`"),
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
    sections = ["### 2. ", "### 3. ", "### 4. ", "### 5. ", "### 6. "]
    for name, (start, text) in WARNINGS.items():
        end = sections[sections.index(start[:7]) + 1]
        assert text in _section(execute, start, end), name
    field = next(line for line in _read(CONTRACT).splitlines() if line.startswith("- `warnings`:"))
    for name in (*WARNINGS, "result_file_write_failed", "customization_resolver_unavailable"):
        assert f"`{name}: " in field, name
    contract = _section(_read(REPORT), "### Result Contract", "### Post-drop hook")
    assert "The payload carries no `warnings`" in contract and "the run's warnings" in contract
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
    assert "Each item above names its manual fix." in report
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 6. ")
    assert "A failure's manual fix: correct the `{target_skill}` entry" in verify
    assert "the manual fix for both is to re-run `[EX] Export Skill`" in verify
    assert "record it in `verification_errors` with its manual fix" in verify
    rendered = _section(report, "### 2. Render the Report", "### Result Contract")
    assert "{if delete_failures is non-empty:}- Not deleted:" in rendered


def test_the_context_check_reads_no_snippet_text():
    """determinism-3: §5 asks the roster helper for the dropped skill's rows, never every row's text."""
    verify = _section(_read(EXECUTE), "### 5. Verify Final State", "### 6. ")
    assert _one_command(verify, "{dropRosterHelper} rows") == (
        "uv run {dropRosterHelper} rows --skill {target_skill} [--version {version}] "
        "{each file in context_files_updated, quoted}")
    assert "orphan-detect" not in verify and "orphan_managed_rows" not in verify
