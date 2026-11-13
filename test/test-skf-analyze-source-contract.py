#!/usr/bin/env python3
"""Analyze Source contract: the envelope on every exit (#585, #593), briefs
written through the brief writer (#592), a fresh start on a finished report
(#587), and the auto path reading the target's file list from a run file
(the wave-3 re-check's determinism-1 and determinism-2).

Step prose is not executed by any test, so these checks run the commands the
analyze-source steps document, filled in as an agent fills them, against
fixtures:

- skf-emit-result-envelope.py builds every SKF_ANALYZE_RESULT_JSON line from
  schemas/skf-analyze-result-envelope.v1.json: the halt, redirect, skip,
  success and zero-unit payloads the steps stage go through the documented
  commands, and each line validates under jsonschema. Every HARD HALT site
  names the exit code the schema maps its halt_reason to, and a phase; every
  step that halts states the emit command in its own opening.
- skf-write-skill-brief.py and skf-validate-brief-schema.py: the auto path's
  brief context, filled with the whole-language caveat (which holds an
  apostrophe), gives a valid brief; a brief the gate rejects never reaches
  the forge folder; the interactive path's context does the same.
- The auto path lists the target's files once into a run file, and shape
  and language detection read it: no grep pre-filter and no echo'd tree.
  A brief's include and exclude patterns come from that list too, never
  from a remote target's manifests-only checkout (gate run 6 determinism-2).
- The prose pins: a finished report is archived and the run starts fresh,
  continue.md keeps no unreachable "already complete" branch, the fallback
  to the interactive chain resets `mode`, the per-boundary brief rules are
  stated once, and every warning a step raises goes to the run sink.
- Step 5b gate run 2: an unfinished report resumes only when the re-run's
  ref and hint flags match it, an [auto] report carries the skill and brief
  inventory its fallback reads, and map-and-detect and [D] read the import
  graph through skf-count-imports.py summary, never the whole envelope.
- Step 5b gate run 7 determinism-1: both derive-name call sites pass
  --probe-git, and an address git reads as a repository, asks credentials
  for or leaves unanswered halts the [auto] path in section 0, before
  coexistence (and fails the scan root), with the helper's message; a
  missing git goes docs-only with a warning.
- #1123: a repository browser page whose repository git reads at the .git
  clone URL of a shorter part of its address (down to owner/repo), or at a
  Bitbucket Data Center /scm/ address, halts the same way and names that
  clone URL, and an http:// address is never
  told to drop https://. An [auto] call given several project paths (a
  documentation URL first or later among them), --target-ref or
  --target-refs halts in init section 2b with exit 2 before any analysis,
  and step 1a section 2 fetches its one target into clone-1.
- Step 5b gate run 7 architecture-1: an unfinished report whose `mode` is
  'auto' is archived like one an [auto] invocation finds, and continue.md
  never routes a resume back into auto-scope; the fallback report, marked
  interactive, still resumes.
- #1124: every report names its run folder in `run_dir`, and continue.md
  takes that folder over (this session's sink files appended, its own
  folder deleted), so the resumed run's envelope carries the decisions and
  warnings of both sessions; a report whose `run_dir` is missing, empty or
  names no folder of this workflow directly inside `.skf-run` deletes
  nothing and records `resumed-without-run-folder`. A clone into the folder
  taken over first deletes the copy a session cut short left there.
  continue.md reads two keys and announces its next step in one line.
- #1125: each unit's record is written by skf-check-unit-records.py
  from-extract from the extractor's output, a Java, Kotlin or Swift unit's
  from quick mode's parser over every source file (--all-sources), and the
  documented parser line and the record check run on a fixture. Step E
  counts the demo files and scores the registry candidates by
  skf-detect-registry.py, and the heuristics name those outputs.
- #1126: identify-units section 3's units call detects each unit's language
  with no workspace signal, as section 4 says, and map-and-detect and [D]
  build each project path's units JSON from the units file with
  skf-count-imports.py units-from, then print the summary and the
  cross-reference matrix: the documented blocks run on a fixture.
- #1127: generate-briefs section 3b is one skf-validate-brief-schema.py
  batch call, run here as documented on the contexts section 2's template
  gives; a version computed at build time comes from the schema asset's
  skf-extract-public-api.py --resolve-version call (run on a dynamic
  pyproject.toml), whose probe order both brief steps resolve; the asset
  keeps only the sections the steps read, recommend loads none of it, and
  the three brief templates leave out the keys the writer drops.
- #1128: the split's section 4a lists each workspace package's files and
  classifies the package with one skf-shape-detect.py --member call, run
  here as documented on a fixture monorepo: the script's scope_type gives
  each boundary's scope type and its source_file_count leaves out a package
  with no source file, and the model judges only the framework and parser
  signals, the two rows step-shape-detect.md keeps beside the ladder.
  SKILL.md and step-auto-scope.md stay under their token budgets, and
  step-auto-scope.md and generate-briefs.md state each rule once.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
AN = SRC / "skf-analyze-source"
REFS = AN / "references"
SCRIPTS = SRC / "shared" / "scripts"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
WRITER = SCRIPTS / "skf-write-skill-brief.py"
VALIDATOR = SCRIPTS / "skf-validate-brief-schema.py"
SHAPE = SCRIPTS / "skf-shape-detect.py"
LANGUAGE = SCRIPTS / "skf-detect-language.py"
WORKSPACES = SCRIPTS / "skf-detect-workspaces.py"
SCAN_MANIFESTS = SCRIPTS / "skf-scan-manifests.py"
EXTRACT = SCRIPTS / "skf-extract-public-api.py"
GATE = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-analyze-result-envelope.v1.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
SETTINGS = SCHEMA["$defs"]["skf-envelope"]["const"]
PREFIX = "SKF_ANALYZE_RESULT_JSON: "

SKILL = AN / "SKILL.md"
CONTRACT = REFS / "invocation-contract.md"
HEADLESS = REFS / "headless-contract.md"
INIT = REFS / "init.md"
CONTINUE = REFS / "continue.md"
AUTO = REFS / "step-auto-scope.md"
COEXIST = REFS / "step-auto-scope-coexistence.md"
SPLIT = REFS / "step-auto-scope-split.md"
CORPORA = REFS / "step-auto-scope-corpora.md"
DOCS = REFS / "auto-docs-only.md"
SHAPE_REF = REFS / "step-shape-detect.md"
IDENTIFY = REFS / "identify-units.md"
MAP = REFS / "map-and-detect.md"
GENERATE = REFS / "generate-briefs.md"
RECOMMEND = REFS / "recommend.md"
DISCOVER = REFS / "discover-additional-source.md"
BRIEF_SCHEMA_DOC = AN / "assets" / "skill-brief-schema.md"
TEMPLATE = AN / "templates" / "analysis-report-template.md"
STEP_FILES = sorted(p for p in REFS.glob("*.md") if p.name != "headless-contract.md")

# A HALT site: "HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `x`)".
HALT_SITE = re.compile(r'HARD HALT \(exit code (\d+), `halt_reason: "([a-z-]+)"`(, phase `([a-z0-9-]+:[a-z0-9-]+)`)?')
HALT_COMMAND = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" '
                '--target stderr < "{run_dir}/halt.json"')
JSON_RULE = ("Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / "
             "and each double quote with a backtick.")
CAVEAT_APOSTROPHE = "this skill's value"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` (which occurs once) up to marker `end`."""
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _fenced(text: str, lang: str) -> list[str]:
    """The ```<lang> blocks of `text`, each dedented to its fence's indentation."""
    blocks = []
    for m in re.finditer(r"^( *)```" + lang + r"\n(.*?)^\1```", text, flags=re.M | re.S):
        indent = len(m.group(1))
        blocks.append("\n".join(line[indent:] for line in m.group(2).split("\n")))
    return blocks


def _one_command(text: str, needle: str) -> str:
    lines = [line.strip() for block in _fenced(text, "bash") for line in block.split("\n") if needle in line]
    assert len(lines) == 1, f"expected one bash line holding {needle!r}, found {lines}"
    return lines[0]


def _argv(command: str, values: dict) -> list[str]:
    """Fill a documented `uv run {helper} ...` command in and split it, without a shell."""
    command = re.sub(r"\[(--[a-z-]+) [^\]]*\]", "", command)  # an optional flag the fixture leaves out
    words = []
    for word in shlex.split(re.sub(r"\{([\w-]+)\}", r"@@\1@@", command)):
        words.append(re.sub(r"@@([\w-]+)@@", lambda m: values[m.group(1)], word))
    assert words[:2] == ["uv", "run"], words
    return [sys.executable, *words[2:]]


def _run(command: str, values: dict, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a documented command; `< "<path>"` becomes the process's stdin."""
    command, _, source = command.partition(" < ")
    if source:
        path = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], source.strip().strip('"'))
        stdin = Path(path).read_bytes()
    return subprocess.run(_argv(command, values), input=stdin, capture_output=True, timeout=120)


def _fill(template: str, values: dict):
    """Fill a JSON template from the prose: `"{name ...}"` gets a JSON value, `<name ...>` too.

    Each placeholder is looked up by its whole text first, then by its first word.
    """
    def lookup(key: str):
        key = key.strip()
        return values[key] if key in values else values[key.split()[0]]

    text = re.sub(r'"\{([^{}"]+)\}"', lambda m: json.dumps(lookup(m.group(1))), template)
    text = re.sub(r'"<([^<>"]+)>"', lambda m: json.dumps(lookup(m.group(1))), text)
    text = re.sub(r"<([^<>]+)>", lambda m: json.dumps(lookup(m.group(1))), text)
    return json.loads(text)


def _envelope(stream: bytes) -> dict:
    [line] = stream.decode("utf-8").splitlines()
    assert line.startswith(PREFIX), line
    envelope = json.loads(line[len(PREFIX):])
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(envelope), key=str)
    assert not errors, [e.message for e in errors]
    return envelope


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-analyze-source-Ab3dE5gH"
    run_dir.mkdir(parents=True)
    return run_dir


# --------------------------------------------------------------------------
# The envelope: one schema, the emitter, and the halt reasons every site uses
# --------------------------------------------------------------------------


def test_the_schema_is_valid_and_its_settings_match_the_contract():
    Draft202012Validator.check_schema(SCHEMA)
    assert (SETTINGS["workflow"], SETTINGS["prefix"], SETTINGS["result_file"]) == (
        "skf-analyze-source", PREFIX.rstrip(": "), "analyze-source-result")
    assert (SETTINGS["halt_status"], SETTINGS["success_exit_code"], SETTINGS["wrapper"]) == ("error", 0, None)
    in_schema = {r for r in SCHEMA["properties"]["halt_reason"]["enum"] if r is not None}
    assert in_schema == set(SETTINGS["exit_codes"])
    rule = next(line for line in _read(HEADLESS).splitlines() if line.startswith("- `halt_reason`"))
    assert set(re.findall(r'"([a-z-]+)"', rule)) == in_schema
    assert set(SCHEMA["properties"]["exit_code"]["enum"]) == {0, *SETTINGS["exit_codes"].values()}
    # The fields the forger's AN circuit breaker reads stay required.
    assert {"unit_counts", "brief_paths", "status", "halt_reason"} <= set(SCHEMA["required"])
    # An optional warnings list, so the run's warnings (a resolver fallback) reach the line.
    assert "warnings" in SCHEMA["properties"] and "warnings" not in SCHEMA["required"]


def test_the_contract_template_has_the_required_fields_in_order():
    line = next(line for line in _read(HEADLESS).splitlines() if line.startswith(PREFIX))
    template = json.loads(line[len(PREFIX):].replace("…", "x").replace("N", "0"))
    assert list(template) == SCHEMA["required"]
    assert list(SCHEMA["properties"])[:len(SCHEMA["required"])] == SCHEMA["required"]


def test_the_exit_code_table_lists_the_schema_codes():
    table = _section(_read(HEADLESS), "## Exit Codes", None)
    rows = {int(m.group(1)) for m in re.finditer(r"^\| (\d+) +\|", table, flags=re.M)}
    assert rows == set(SCHEMA["properties"]["exit_code"]["enum"])


def _halt_sites():
    for path in [SKILL, *STEP_FILES]:
        for number, line in enumerate(_read(path).split("\n"), 1):
            for m in HALT_SITE.finditer(line):
                yield path.name, number, int(m.group(1)), m.group(2), m.group(4)


def test_every_halt_site_uses_the_schema_exit_code_and_names_its_phase():
    sites = list(_halt_sites())
    assert len(sites) > 30
    for name, number, code, reason, phase in sites:
        assert SETTINGS["exit_codes"].get(reason) == code, f"{name}:{number} {reason} exits {code}"
        assert phase, f"{name}:{number} names no phase"
    assert {reason for *_, reason, _ in sites} == set(SETTINGS["exit_codes"]), "a halt_reason no step raises"


@pytest.mark.parametrize("path", STEP_FILES, ids=[p.stem for p in STEP_FILES])
def test_every_step_that_halts_states_the_emit_command(path):
    """No HALT depends on a file that is not loaded: each step names the command itself."""
    text = _read(path)
    assert "shape in `references/headless-contract.md`" not in text
    assert "per `references/headless-contract.md`" not in text
    if HALT_SITE.search(text):
        opening = _section(text, "## MANDATORY SEQUENCE", "### ")
        assert _one_command(opening, "emit-halt") == HALT_COMMAND
        assert JSON_RULE in opening


def test_no_step_types_an_envelope_or_a_bare_halt():
    for path in [SKILL, *STEP_FILES]:
        text = _read(path)
        assert PREFIX + "{" not in text, f"{path.name} types an envelope"
        for bare in ("HALT if neither resolves", "HALT if no candidate exists", "HALT with a clear message",
                     "HALT with:", "Mark workflow complete and halt"):
            assert bare not in text, (path.name, bare)


@pytest.mark.parametrize("reason", sorted(SETTINGS["exit_codes"]))
def test_the_documented_halt_emits_a_valid_envelope_on_stderr(tmp_path, reason):
    run_dir = _run_dir(tmp_path)
    halt = {"phase": "step-auto-scope:8", "reason": f"{reason}: the brief for x was rejected",
            "halt_reason": reason, "mode": "auto", "path": "/fd/x/skill-brief.yaml"}
    (run_dir / "halt.json").write_bytes(json.dumps(halt).encode("utf-8"))
    proc = _run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"", "a HALT prints its envelope on stderr"
    envelope = _envelope(proc.stderr)
    assert (envelope["status"], envelope["halt_reason"]) == ("error", reason)
    assert envelope["exit_code"] == SETTINGS["exit_codes"][reason]
    assert (envelope["brief_paths"], envelope["result_path"], envelope["mode"]) == ([], None, "auto")
    assert envelope["error"] == {"phase": "step-auto-scope:8", "reason": halt["reason"],
                                 "path": "/fd/x/skill-brief.yaml"}
    assert not list(tmp_path.rglob("analyze-source-result-*.json")), "a HALT writes no result file"


def test_an_activation_halt_emits_without_a_run_folder():
    activation = _section(_read(SKILL), "## On Activation", None)
    assert 'HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `on-activation:config`)' in activation
    [block] = [b for b in _fenced(activation, "bash") if "<<'SKF_ANALYZE_HALT'" in b]
    lines = block.strip("\n").split("\n")
    start = next(i for i, line in enumerate(lines) if "<<'SKF_ANALYZE_HALT'" in line)
    head, body, end = lines[start:]
    assert end == "SKF_ANALYZE_HALT"
    command = head.partition(" <<")[0]
    assert "--run-dir" not in command
    payload = json.loads(body.replace("<the halt message>", "SKF cannot load its config"))
    proc = _run(command, {"emitEnvelopeHelper": str(EMITTER)}, stdin=json.dumps(payload).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    assert (envelope["halt_reason"], envelope["exit_code"], envelope["mode"]) == ("input-missing", 2, "interactive")
    # The same command, word for word, sits in the contract's Halt Envelope.
    assert head in _section(_read(HEADLESS), "## Halt Envelope", "## Exit Codes")


# --------------------------------------------------------------------------
# Every exit ends through the emitter: success, zero units, redirect, skip
# --------------------------------------------------------------------------

EMIT_COMMAND = ('uv run {emitEnvelopeHelper} emit --workflow skf-analyze-source --run-dir "{run_dir}" '
                '--result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"')


@pytest.mark.parametrize("path", [AUTO, DOCS, GENERATE, HEADLESS], ids=["auto", "docs-only", "interactive", "contract"])
def test_each_ending_runs_the_one_emit_command(path):
    assert _one_command(_read(path), "emit --workflow skf-analyze-source") == EMIT_COMMAND


def _emit(tmp_path: Path, payload: dict, latest_blocked: bool = False) -> tuple[dict, Path]:
    """Run the documented emit; `latest_blocked` puts a folder where the `-latest` copy goes, so that write fails."""
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge-data"
    forge.mkdir()
    if latest_blocked:
        (forge / "analyze-source-result-latest.json").mkdir()
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    proc = _run(EMIT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir),
                               "forge_data_folder": str(forge)})
    assert proc.returncode == 0, proc.stderr
    return _envelope(proc.stdout), forge


def _latest(forge: Path) -> dict:
    return json.loads((forge / "analyze-source-result-latest.json").read_text(encoding="utf-8"))


VALUES = {
    "matched_skill_name": "hono", "matched_active_path": "/skills/hono/4.0.0",
    "outputFile as an absolute path": "/fd/analyze-source-report-p.md",
    "the brief_path of each brief §8 wrote": "/fd/hono/skill-brief.yaml",
    "the brief_path of each brief §5 wrote": "/fd/auth/skill-brief.yaml",
    "the brief_path §4 printed": "/fd/docs-example-com/skill-brief.yaml",
    "each brief_path": "/fd/hono/skill-brief.yaml", "N": 1, "shape": "library-API",
    "each skill_name": "hono", "skill_name": "docs-example-com",
    "confirmed count from step 5": 0, "rejected count from step 5": 3, "briefs written": 0,
    "confirmed count": 0, "count": 0, "primary recommendation": "",
}


@pytest.mark.parametrize("marker, status", [("- **[M]erge:**", "redirect"), ("- **[S]kip:**", "skipped")],
                         ids=["redirect", "skip"])
def test_a_coexistence_redirect_or_skip_ends_with_a_valid_envelope_and_record(tmp_path, marker, status):
    branch = _section(_read(COEXIST), marker, None if status == "skipped" else "- **[S]kip:**")
    [template] = _fenced(branch, "json")
    assert "go to §9" in branch
    envelope, forge = _emit(tmp_path, _fill(template, VALUES))
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == (status, 0, None)
    assert envelope["result_path"] and envelope["mode"] == "auto"
    record = _latest(forge)
    assert (record["skill"], record["status"]) == ("skf-analyze-source", status)
    assert record["timestamp"] and record["run_id"] == "Ab3dE5gH"


@pytest.mark.parametrize("pin", [{"pinned_ref": "v4.0.0", "pinned_version": "4.0.0"}, {"pinned_ref": "main"}],
                         ids=["tag-pin", "branch-pin"])
def test_the_auto_run_ends_with_a_valid_envelope_and_record(tmp_path, pin):
    """skf-validate-pins.py gives a branch pin (and a release tag that is not a
    version) no version: the payload then carries no pinned_version, which the
    schema types as a string."""
    section = _section(_read(AUTO), "### 9. End the Run", None)
    assert '`"pinned_version": "{pinned_version}"` when `{pinned_version}` is non-null' in section
    [template] = _fenced(section, "json")
    payload = _fill(template.replace("<N>", "1"), VALUES)
    payload.update({"coexistence": "alongside", **pin})
    payload["result_contract"]["summary"].update(pin)
    envelope, forge = _emit(tmp_path, payload)
    assert (envelope["status"], envelope["brief_paths"], envelope["unit_counts"]["confirmed"]) == (
        "success", ["/fd/hono/skill-brief.yaml"], 1)
    assert (envelope["coexistence"], envelope["pinned_ref"]) == ("alongside", pin["pinned_ref"])
    assert envelope.get("pinned_version") == pin.get("pinned_version")
    assert _latest(forge)["outputs"][1] == {"type": "brief", "path": "/fd/hono/skill-brief.yaml"}


def test_the_docs_only_run_ends_with_a_valid_envelope(tmp_path):
    [template] = _fenced(_section(_read(DOCS), "### 5. End the run", "### 6."), "json")
    envelope, _ = _emit(tmp_path, _fill(template, VALUES))
    assert (envelope["source_type"], envelope["unit_counts"]["confirmed"]) == ("docs-only", 1)


def test_zero_confirmed_units_end_with_an_envelope_the_forger_reads(tmp_path):
    """#585: no confirmed unit still writes the record and prints the line, and the
    forger's AN gate reads it as no skillable unit instead of finding no line."""
    guard = _section(_read(GENERATE), "**No confirmed unit:**", "### 2.")
    for needle in ("continue at §7", "`generate-briefs` to `stepsCompleted`", "`brief_paths: []`",
                   "`unit_counts.confirmed: 0`", "§9b and §10"):
        assert needle in guard, needle
    [template] = _fenced(_section(_read(GENERATE), "### 9. End the Run", "### 9b."), "json")
    filled = template.replace('["{the brief_path of each brief §5 wrote}"]', "[]")
    filled = filled.replace(', {"type": "brief", "path": "{each brief_path}"}', "")
    envelope, forge = _emit(tmp_path, _fill(filled, VALUES))
    assert (envelope["status"], envelope["brief_paths"], envelope["unit_counts"]) == (
        "success", [], {"confirmed": 0, "skipped": 3, "maybe": 0})
    assert _latest(forge)["outputs"] == [{"type": "report", "path": "/fd/analyze-source-report-p.md"}]
    proc = subprocess.run([sys.executable, str(GATE), "--code", "AN"],
                          input=(PREFIX + json.dumps(envelope)).encode("utf-8"), capture_output=True, timeout=60)
    decision = json.loads(proc.stdout.decode("utf-8"))
    assert (decision["decision"], decision["reason"]) == ("halt", "no-skillable-units")


HOOK_SECTIONS = ((AUTO, "### 9. End the Run", None), (DOCS, "### 5. End the run", "### 6."),
                 (GENERATE, "### 9b.", "### 10."))
LATEST_SKIP = 'skip the hook and say so: "on_complete skipped: `analyze-source-result-latest.json` was not written."'


def test_the_hook_reads_the_latest_record_only_when_one_was_written():
    """#891: each ending runs the hook only when this run wrote the -latest copy (a non-null result_path and no
    write warning naming the copy), and says so when it skips; no file claims that every failed write nulls
    result_path, since a failed -latest copy leaves it set."""
    for path, start, end in HOOK_SECTIONS:
        text = _read(path)
        assert '--result-path="{forge_data_folder}/analyze-source-result-latest.json"' in text, path.name
        assert "`result_path` is not null" in text, path.name
        assert 'rm -rf "{run_dir}"' in text, path.name
        hook = _section(text, start, end)
        assert ("`result_path` is not null and its `warnings` hold no `result_file_write_failed` entry naming "
                "`analyze-source-result-latest.json`") in hook, path.name
        assert ("When `{onCompleteCommand}` is non-empty but `result_path` is null or a `result_file_write_failed` "
                "warning names `analyze-source-result-latest.json` (the copy alone failed), " + LATEST_SKIP) in hook, \
            path.name
        assert hook.index("hold no `result_file_write_failed` entry") < hook.index("{onCompleteCommand} --result-path=")
        assert "an earlier run's `-latest` copy" not in hook, path.name
    # §9b states the hook rule once, in step-auto-scope.md §9's two sentences (#1128 leanness-5)
    nine_b = _section(_read(GENERATE), "### 9b.", "### 10.")
    assert nine_b.count("never fails the run") == 1 and "**Never fail the workflow" not in nine_b
    assert "the §9 line's `result_path` is not null" in nine_b
    for path in (AUTO, DOCS, GENERATE, HEADLESS):
        text = _read(path)
        assert "A result file that could not be written" not in text, path.name
        assert "leaves the line's `result_path` null" not in text, path.name
        assert ("A per-run record that could not be written leaves `result_path` null, and a `-latest` copy that "
                "could not be written leaves it set; either adds a `result_file_write_failed` warning to the line, "
                "and the run still finishes.") in text, path.name
    contract = _read(HEADLESS)
    [rule] = [line for line in contract.splitlines() if line.startswith("- `result_path`:")]
    assert "when the write failed" not in rule
    assert ("`null` for a HALT, which writes no result file, when `--result-dir` names no folder (with no "
            "warning), and when the per-run record could not be written (a "
            "`result_file_write_failed` warning then says why); a `-latest` copy that could not be written leaves it "
            "set, and a `result_file_write_failed` warning names the copy.") in rule
    assert ("Then `{onCompleteCommand}` runs, when it is set, `result_path` is not null and no "
            "`result_file_write_failed` warning names `analyze-source-result-latest.json`, with "
            '`--result-path="{forge_data_folder}/analyze-source-result-latest.json"`, and a hook failure is displayed '
            "and never fails the run; otherwise a set hook is skipped with \"on_complete skipped: "
            '`analyze-source-result-latest.json` was not written."') in contract
    comments = _read(AN / "customize.toml")
    assert "result_path null in the\n# envelope" not in comments
    assert ("A HALT calls no hook, nor does a run whose result file or its -latest\n# copy could not be written "
            "(result_path null, or a result_file_write_failed\n# warning naming the copy, in the envelope)") in comments


def test_a_failed_latest_copy_leaves_result_path_and_names_the_copy(tmp_path):
    """#891: with a folder where the `-latest` copy goes, the documented emit still exits 0 and writes the per-run
    record: `result_path` stays set and one `result_file_write_failed` warning names the copy, the case each
    ending's hook condition skips on."""
    [template] = _fenced(_section(_read(GENERATE), "### 9. End the Run", "### 9b."), "json")
    envelope, forge = _emit(tmp_path, _fill(template, VALUES), latest_blocked=True)
    assert envelope["status"] == "success" and envelope["result_path"]
    assert Path(envelope["result_path"]).is_file() and Path(envelope["result_path"]).parent == forge
    failed = [w for w in envelope.get("warnings", []) if w.startswith("result_file_write_failed:")]
    assert len(failed) == 1 and "analyze-source-result-latest.json" in failed[0], envelope.get("warnings")
    assert (forge / "analyze-source-result-latest.json").is_dir(), "the copy was not written"
    for path, start, end in HOOK_SECTIONS:
        assert "warning names `analyze-source-result-latest.json`" in _section(_read(path), start, end), path.name


ENDINGS = ((GENERATE, "### 9. End the Run", "### 9b."), (AUTO, "### 9. End the Run", None),
           (DOCS, "### 5. End the run", "### 6."))
HEADLESS_BIND = ("When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here: "
                 "the shared health check displays it verbatim as the run's last line (the line the retry below "
                 "prints when the first run printed none, and empty when neither run printed one).")


def test_a_headless_run_hands_its_line_to_the_health_check():
    """#1113: each of the three endings binds `{result_envelope_line}` to the line it prints instead of displaying
    it, so the shared health check (step 7) displays it as the run's last line, the final message `claude -p`
    prints; the contract and the relay say so."""
    for path, start, end in ENDINGS:
        text = _read(path)
        ending = _section(text, start, end)
        assert HEADLESS_BIND in ending, path.name
        assert ending.index("prints the `SKF_ANALYZE_RESULT_JSON:` line on stdout") < ending.index(HEADLESS_BIND)
        # An emitter that fails twice still halts there, on its own line, and never reaches the health check.
        halt = 'if it fails again, HARD HALT (exit code 4, `halt_reason: "write-failed"`'
        assert ending.index(HEADLESS_BIND) < ending.index(halt), path.name
        assert "display the line verbatim" not in text, path.name
        assert "leave it empty" not in text, path.name
    contract = _section(_read(HEADLESS), "## Result Envelope", "```")
    assert "before chaining to step 7" not in contract
    assert ("prints the envelope on **stdout**; when `{headless_mode}` is true it binds `{result_envelope_line}` to it "
            "instead of displaying it, and the shared health check (step 7) displays it as the run's last line.") in (
        contract)
    relay = _read(REFS / "health-check.md")
    assert ("In a headless run the step that ended it (generate-briefs.md §9, step-auto-scope.md §9 or "
            "auto-docs-only.md §5) bound `{result_envelope_line}` to the `SKF_ANALYZE_RESULT_JSON` line without "
            "displaying it") in relay


@pytest.mark.parametrize("gate, marker", [("auto-scope.cohesion", "**Record the decision**"),
                                          ("auto-scope.shape", "**An app or a library on a framework.**"),
                                          ("auto-scope.language", "**Otherwise** (several languages")],
                         ids=["cohesion", "shape", "language"])
def test_the_auto_decisions_reach_the_envelope(tmp_path, gate, marker):
    """#593: the merge-or-split decision (and the app-or-library and language choices) land in the
    sink and the line."""
    end = {"auto-scope.language": "### 6. Build Scope", "auto-scope.shape": "### 5."}.get(gate, "### 4.")
    text = _section(_read(AUTO), marker, end)
    m = re.search(r'write `\{run_dir\}/decision\.json` as `(\{"gate": "' + re.escape(gate) + r'".*?\})` and run', text)
    assert m, gate
    values = {"merge or split": "merge", "the cohesion trigger that held, or why the members split": "umbrella facade",
              "package_count": 5, "the §2 member names": "a", "detected_languages[0]": "csharp",
              "the language you chose": "python", "the manifest or the source files that decided": "sources",
              "detected_languages": "csharp", "source_language": "python", "reference-app or library-API": "library-API",
              "the sentence of the description or README that decided": "Extra utilities for axum",
              "the §3 signals": "app_or_library:framework_dep"}
    decision = _fill(m.group(1), values)
    run_dir = _run_dir(tmp_path)
    (run_dir / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
    record = 'uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"'
    assert record in text
    proc = _run(record, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "step-auto-scope:8", "reason": "x", "halt_reason": "write-failed", "mode": "auto"}).encode("utf-8"))
    proc = _run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    envelope = _envelope(proc.stderr)
    assert [d["gate"] for d in envelope["headless_decisions"]] == [gate], "a halt reports the decision taken before it"


def test_a_parser_dependency_is_judged_as_the_shape_choice():
    """Gate run 6 determinism-1: a parser among the runtime dependencies asks rather than
    decides. Section 4 judges it from the description or README, makes the judged shape
    `{shape}` (the report and the result read it) and records it like the framework choice,
    whose decision.json the test above runs."""
    section = _section(_read(AUTO), "### 4. Map Shape to Scope", "### 5.")
    rule = next(line for line in section.splitlines() if line.startswith("**A language on a parser.**"))
    for needle in ("`language_or_user:parser_dep`", "description or README",
                   "from here on `{shape}` is the shape that case gives", "Record it the same way",
                   "`default_action` the shape you judged from", "`taken_action` the new `{shape}`"):
        assert needle in rule, needle
    row = next(line for line in _read(SHAPE_REF).splitlines() if "`language_or_user:parser_dep` signal |" in line)
    assert "step-auto-scope.md §4 judges which" in row


# --------------------------------------------------------------------------
# Briefs go through the writer and the schema gate (#592)
# --------------------------------------------------------------------------


def _caveat(seeds: int) -> str:
    text = _section(_read(CORPORA), "### 2.", "### 3.")
    rule = next(line for line in text.splitlines() if ("`{N}` ≥ 1:" if seeds else "`{N}` == 0:") in line)
    caveat = re.search(r'`"( LANGUAGE-REFERENCE CAVEAT: .*?)"`', rule).group(1)
    return (caveat.replace("{corpus_language}", "rust").replace("{N}", str(seeds))
            .replace("{corpus_labels}", "The Book, std"))


def _gate_and_write(tmp_path: Path, path: Path, context: dict, name: str):
    """Run the documented gate and write commands of `path` on `context`."""
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge-data"
    text = _read(path)
    stem = "unit-name" if path == GENERATE else "skill_name"
    (run_dir / f"brief-{name}.json").write_bytes(json.dumps(context).encode("utf-8"))
    values = {"writeSkillBriefHelper": str(WRITER), "validateBriefSchemaHelper": str(VALIDATOR),
              "run_dir": str(run_dir), "forge_data_folder": str(forge), stem: name}
    stage = _one_command(text, f'--target "{{run_dir}}/briefs/{{{stem}}}/skill-brief.yaml"')
    check = _one_command(text, 'uv run {validateBriefSchemaHelper} "{run_dir}/briefs/')
    final = _one_command(text, f'--target "{{forge_data_folder}}/{{{stem}}}/skill-brief.yaml"')
    staged = _run(stage, values)
    verdict = _run(check, values) if staged.returncode == 0 else None
    passed = staged.returncode == 0 and verdict.returncode == 0 and json.loads(verdict.stdout)["valid"]
    written = _run(final, values) if passed else None
    return staged, verdict, written, forge / name / "skill-brief.yaml"


def _auto_context(notes: str, **over) -> dict:
    [template] = _fenced(_section(_read(AUTO), "### 8. Write Skill Briefs", "**Gate every brief"), "json")
    values = {"skill_name": "rust-lang", "project_path": "https://github.com/rust-lang/rust",
              "detected_language": "rust", "forge_tier": "Forge", "current_date": "2026-10-01",
              "user_name": "armel", "scope_type": "full-library", "scope.notes": notes,
              "1-3 sentence description based on shape, language, and manifest name":
                  "The Rust language: its guide and standard library. Use when writing Rust.",
              "include_patterns": "compiler/**/*.rs", "exclude_patterns": "**/tests/**",
              "target_version from the pin table, or null": None,
              "target_ref from the pin table, or null": None, "detected_version, or null": None}
    context = _fill(template, values)
    context.update(over)
    return context


@pytest.mark.parametrize("seeds", [3, 0], ids=["corpora-seeded", "no-corpora"])
def test_the_auto_brief_with_the_language_caveat_is_written_valid(tmp_path, seeds):
    """#592: the caveat holds `this skill's`, which broke the old single-quoted
    template; through the writer the brief validates and keeps the text."""
    notes = "Auto-scoped from shape detection (shape: language-reference, confidence: 0.9)." + _caveat(seeds)
    doc_urls = [{"url": "https://doc.rust-lang.org/book/", "label": "The Book", "source": "language-registry"}]
    context = _auto_context(notes, doc_urls=doc_urls if seeds else None)
    staged, verdict, written, target = _gate_and_write(tmp_path, AUTO, context, "rust-lang")
    assert staged.returncode == 0, staged.stderr
    assert json.loads(verdict.stdout)["valid"] is True, verdict.stdout
    assert written.returncode == 0, written.stderr
    brief = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert brief["scope"]["notes"] == notes
    assert (CAVEAT_APOSTROPHE if seeds else "LOW-VALUE as code-only") in notes
    assert brief["version"] == "1.0.0"
    assert ("doc_urls" in brief) is bool(seeds)
    staged_bytes = (tmp_path / "_bmad-output" / ".skf-run" / "skf-analyze-source-Ab3dE5gH" / "briefs" / "rust-lang"
                    / "skill-brief.yaml").read_bytes()
    assert target.read_bytes() == staged_bytes, "the bytes written are the bytes that validated"


@pytest.mark.parametrize("over, rejected_by", [
    ({"scope_include": []}, "validator"),
    ({"name": "Rust_Lang"}, "writer"),
    ({"target_version": "main"}, "writer"),
], ids=["empty-include", "not-kebab", "branch-as-version"])
def test_a_rejected_brief_never_reaches_the_forge_folder(tmp_path, over, rejected_by):
    context = _auto_context("Auto-scoped from shape detection (shape: library-API, confidence: 0.8).", **over)
    staged, verdict, written, target = _gate_and_write(tmp_path, AUTO, context, "rust-lang")
    if rejected_by == "writer":
        assert staged.returncode != 0 and json.loads(staged.stderr)["status"] == "error"
    else:
        assert staged.returncode == 0 and verdict.returncode != 0
        assert json.loads(verdict.stdout)["valid"] is False
    assert written is None and not target.exists()
    halt = _section(_read(AUTO), "**Gate every brief", "**Then write each brief**")
    assert 'HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `step-auto-scope:8`' in halt


@pytest.mark.parametrize("pin, expected", [
    ({"target_version": "4.2.0", "target_ref": "v4.2.0"}, ("4.2.0", "v4.2.0")),
    ({"target_ref": "release/next", "detected_version": "4.3.0-rc.1"}, ("4.3.0-rc.1", "release/next")),
    ({}, ("1.0.0", None)),
], ids=["tag", "branch", "no-pin"])
def test_the_pin_table_reaches_the_brief_through_the_writer(tmp_path, pin, expected):
    """The writer applies the version precedence the prose no longer restates."""
    context = _auto_context("Auto-scoped from shape detection (shape: library-API, confidence: 0.8).", **pin)
    _, _, written, target = _gate_and_write(tmp_path, AUTO, context, "rust-lang")
    assert written is not None and written.returncode == 0
    brief = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert (brief["version"], brief.get("target_ref")) == expected
    section = _section(_read(AUTO), "### 8. Write Skill Briefs", "### 9.")
    assert "| `\"local\"` |" in section and "Version detection:" not in section


def test_the_interactive_brief_is_written_through_the_writer(tmp_path):
    """generate-briefs builds the same flat context; a composite spans its constituents."""
    text = _read(GENERATE)
    [template] = _fenced(_section(text, "### 2. Build Each Brief's Context", "### 3."), "json")
    values = {"unit-name": "animato", "version, or null": None, "source_repo": "/src/animato",
              "the unit's ref, or null": None,
              "language": "rust", "description": "Animation core. Use when animating.",
              "forge_tier": "Deep", "current_date": "2026-10-01", "user_name": "armel",
              "scope.type": "full-library", "scope.include": "crates/animato-core/**",
              "scope.exclude": "**/tests/**", "scope.notes": "Composite of the core's crates; the team's pick."}
    context = _fill(template, values)
    context["scope_include"].append("crates/animato-macros/**")
    staged, verdict, written, target = _gate_and_write(tmp_path, GENERATE, context, "animato")
    assert staged.returncode == 0 and json.loads(verdict.stdout)["valid"], (staged.stderr, verdict.stdout)
    brief = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert brief["scope"]["include"] == ["crates/animato-core/**", "crates/animato-macros/**"]
    assert "pipe the *exact* assembled YAML" not in text and "{assembled-brief-yaml}" not in text


def test_every_brief_context_is_a_file_never_an_echo():
    for path in (AUTO, DOCS, GENERATE):
        text = _read(path)
        assert "echo '<context-json>'" not in text and "echo '{" not in text, path.name
        assert '--from-flat < "{run_dir}/brief-' in text, path.name


@pytest.mark.parametrize("path", [AUTO, GENERATE], ids=["auto", "interactive"])
def test_the_manifest_version_reaches_the_writer_as_found(path):
    """step 5b determinism-2: the writer, not the prompt, decides whether a
    detected version is semver, so the step passes the manifest's version as
    found and never checks its shape by eye. The rule is stated once, in the
    schema's Version Detection, which both brief paths point at."""
    text = _read(path)
    rule = next(line for line in text.splitlines() if "`detected_version`" in line and "Version Detection" in line)
    assert "**Version Detection**" in rule and "manifests-" in rule, rule
    for gone in ("when it is full `X.Y.Z` semver (an optional", "since the writer rejects any other value",
                 "warns about a value that is not semver", "falls back to `1.0.0` otherwise"):
        assert gone not in text, gone


def test_the_version_detection_rule_starts_from_the_scan():
    """One statement of the version rule: the scan's `version` as found; the ladder
    only for a version computed at build time or a private workspace root."""
    rule = _section(_read(BRIEF_SCHEMA_DOC), "## Version Detection", "## Scope Object")
    assert "the `version` that `skf-scan-manifests.py` gives the unit's own manifest" in rule
    assert "passed to the brief writer as found, null when there is none" in rule
    assert 'falls back to `"1.0.0"` otherwise, with a warning' in rule
    assert "**A `version_dynamic` manifest**" in rule and "**A private workspace root that gives none**" in rule
    for gone in ("releases/latest", "If it fails or returns a non-semver value", "**Rust:**", "**Go:**"):
        assert gone not in rule, gone


def test_every_project_path_scan_is_one_file_the_brief_step_reads():
    """step 5b: a path [D] adds writes its scan where generate-briefs reads every
    project path's, and a resumed session writes it again before reading it."""
    discover = _read(DISCOVER)
    assert 'uv run {scanManifestsHelper} scan "{scan_root}" > "{run_dir}/manifests-{i}.json"' in discover
    assert '--deps "{run_dir}/manifests-{i}.json"' in discover
    assert "discover-{i}-manifests" not in discover
    row = next(line for line in _read(GENERATE).splitlines() if line.startswith("| version |"))
    assert "`{run_dir}/manifests-{i}.json`" in row and "When that file is missing" in row, row
    assert 'run `uv run {scanManifestsHelper} scan "{scan_root}" > "{run_dir}/manifests-{i}.json"` first' in row


@pytest.mark.parametrize("detected", ["0.1", "2.0.0rc1"], ids=["two-part-version", "pep440-version"])
def test_a_detected_version_that_is_not_semver_writes_the_default(tmp_path, detected):
    """A two-part or PEP 440 version no longer halts the run: the brief gets 1.0.0."""
    context = _auto_context("Auto-scoped from shape detection (shape: library-API, confidence: 0.8).",
                            detected_version=detected)
    staged, verdict, written, target = _gate_and_write(tmp_path, AUTO, context, "rust-lang")
    assert staged.returncode == 0, staged.stderr
    assert any("falling through to default 1.0.0" in w for w in json.loads(staged.stdout)["warnings"])
    assert written is not None and written.returncode == 0, written.stderr if written else verdict.stdout
    assert yaml.safe_load(target.read_text(encoding="utf-8"))["version"] == "1.0.0"


# --------------------------------------------------------------------------
# The brief checks and a dynamic version are helper calls (#1127)
# --------------------------------------------------------------------------

BATCH_CALL = "uv run {validateBriefSchemaHelper} batch"
ABSENT_KEY_LINE = "Leave out every other optional key: the writer reads an absent key as unset."
# The optional keys the brief writer drops when they are null (#1127 leanness-9).
DROPPED_KEYS = ("scope_rationale", "scope_tier_a_include", "scope_amendments", "scope_registry_path",
                "scope_ui_variants", "scope_demo_patterns", "scripts_intent", "assets_intent", "source_ref")


def _generate_context(name: str, source_repo: str) -> dict:
    """A context generate-briefs section 2's template gives."""
    [template] = _fenced(_section(_read(GENERATE), "### 2. Build Each Brief's Context", "### 3."), "json")
    values = {"unit-name": name, "version, or null": None, "source_repo": source_repo,
              "the unit's ref, or null": None, "language": "typescript",
              "description": "Helpers. Use when testing.", "forge_tier": "Forge", "current_date": "2026-11-13",
              "user_name": "armel", "scope.type": "full-library", "scope.include": "src/**",
              "scope.exclude": "**/tests/**", "scope.notes": "One package."}
    return _fill(template, values)


def _batch_call(run_dir: Path, existing: list[str], paths: list[str], roots: list[str]):
    """Section 3b's documented call, its lists filled in quoted, its glob left for the script."""
    command = _one_command(_section(_read(GENERATE), "**3b. Batch checks.**", "### 4."), BATCH_CALL)
    assert '--contexts "{run_dir}"/brief-*.json' in command
    for placeholder, words in (("<each existing_skills name>", existing),
                               ("<each project_paths entry, quoted>", paths),
                               ("<the scan_roots entry of each, quoted, in the same order>", roots)):
        assert placeholder in command, placeholder
        command = command.replace(placeholder, " ".join(shlex.quote(word) for word in words))
    return _run(command, {"validateBriefSchemaHelper": str(VALIDATOR), "run_dir": str(run_dir)})


def test_the_documented_batch_check_runs_on_the_brief_contexts(tmp_path):
    """#1127 determinism-8: section 3b's one call checks the contexts section 2 writes, its
    `brief-*.json` word as no shell expanded it: a clean batch passes, a remote unit through the scan
    root this run cloned, and a step 5 rename onto an existing skill's name fails on that brief."""
    run_dir = _run_dir(tmp_path)
    local = tmp_path / "mono"
    local.mkdir()
    remote = "https://github.com/acme/core"
    root = run_dir / "source-2"
    root.mkdir()
    for name, source in (("auth", str(local)), ("core", remote)):
        (run_dir / f"brief-{name}.json").write_bytes(json.dumps(_generate_context(name, source)).encode("utf-8"))
    lists = (["billing"], [str(local), remote], [str(local), str(root)])
    proc = _batch_call(run_dir, *lists)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert json.loads(proc.stdout) == {"valid": True, "errors": [], "warnings": []}
    (run_dir / "brief-core.json").write_bytes(json.dumps(_generate_context("billing", remote)).encode("utf-8"))
    proc = _batch_call(run_dir, *lists)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    [error] = json.loads(proc.stdout)["errors"]
    assert (Path(error["context"]).name, error["name"], error["field"]) == ("brief-core.json", "billing", "name")
    assert error["message"].startswith("Brief validation failed: ")


def test_the_documented_batch_check_passes_with_no_existing_skill(tmp_path):
    """A first run has an empty `existing_skills`: the filled call then holds a bare
    `--existing-skills` before `--project-paths`, and still passes a clean batch."""
    run_dir = _run_dir(tmp_path)
    local = tmp_path / "mono"
    local.mkdir()
    (run_dir / "brief-auth.json").write_bytes(json.dumps(_generate_context("auth", str(local))).encode("utf-8"))
    proc = _batch_call(run_dir, [], [str(local)], [str(local)])
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert json.loads(proc.stdout) == {"valid": True, "errors": [], "warnings": []}


def test_section_3b_runs_the_batch_once_every_brief_passed_the_gate():
    text = _read(GENERATE)
    checks = _section(text, "**3b. Batch checks.**", "### 4.")
    assert checks.startswith("**3b. Batch checks.** When every brief passed §3a, check them together")
    assert [line for block in _fenced(checks, "bash") for line in block.split("\n") if line.strip()] == [
        _one_command(checks, BATCH_CALL)]
    assert ("Its `errors[]` have §3a's shape and are 3b failures: each names its `context` file, and its brief "
            "`name`, `field` and `message` are the {unit-name}, {check} and reason below.") in checks
    assert ("a second exit 2 counts as a failed `batch` check of the first unit in `confirmed_units`, its reason "
            "the first stderr line") in checks
    assert "{unit-name}" in checks.split("**If any check fails:**")[1] and "{check}" in checks
    modify = _section(text, "**IF user modifies (M):**", "**IF user skips writing (N):**")
    assert "run §3a on it and §3b again" in modify, "an [M] rename is checked against the batch too"
    assert "`existing_skills`" in _section(text, "### 1. Load Context", "### 2.")
    opening = _section(text, "### 3. Validate Each Brief", "**3a.")
    assert "**batch check**" in opening and "semantic" not in opening
    row = next(line for line in _read(HEADLESS).splitlines() if line.startswith("| 4 "))
    assert "fails the batch check of step 6 §3 in headless mode" in row and "semantic" not in row


@pytest.mark.parametrize("path, phase", [(GENERATE, "generate-briefs:2"), (AUTO, "step-auto-scope:8")],
                         ids=["interactive", "auto"])
def test_both_brief_steps_resolve_the_extractor_or_halt(path, phase):
    """#1127 determinism-9: the version lookup's extractor is resolved with the brief writer and the
    validator, so a missing script halts there."""
    text = _read(path)
    assert ("extractPublicApiProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'\n") in text.split("\n---\n", 1)[0] + "\n"
    [line] = [line for line in text.splitlines()
              if "**`{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}`" in line]
    assert "**`{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`" in line
    assert f'HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `{phase}`)' in line


@pytest.mark.parametrize("files, expected", [
    ({"acme/__init__.py": '__version__ = "2.3.1"\n'}, ("2.3.1", "file:acme/__init__.py")),
    ({"acme/__init__.py": "from ._version import __version__\n", "acme/_version.py": '__version__ = "2.4.0"\n'},
     ("2.4.0", "file:acme/_version.py")),
    ({"acme.py": "x = 1\n", "setup.py": 'from setuptools import setup\nsetup(name="acme", version="3.1.0")\n'},
     ("3.1.0", "file:setup.py")),
], ids=["init", "version-file", "single-module"])
def test_a_dynamic_python_version_comes_from_the_extractor(tmp_path, files, expected):
    """#1127 determinism-9: the scan gives a `version_dynamic` manifest no version, and the schema
    asset's documented call finds it, with where it came from; for a package with no `__init__.py`
    the call leaves `--entry-file` out, as the rule says, so setup.py is still read."""
    root = tmp_path / "acme-src"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "acme"\ndynamic = ["version"]\n', encoding="utf-8")
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    scan = subprocess.run([sys.executable, str(SCAN_MANIFESTS), "scan", str(root)], capture_output=True, timeout=120)
    assert scan.returncode == 0, scan.stderr
    [manifest] = [m for m in json.loads(scan.stdout)["manifests"] if m["path"] == "pyproject.toml"]
    assert (manifest["version_dynamic"], manifest["version"]) == (True, None)
    rule = _section(_read(BRIEF_SCHEMA_DOC), "## Version Detection", "## Scope Object")
    command = _one_command(rule, "--resolve-version")
    assert command == ('uv run {extractPublicApiHelper} --mode quick --language python --source-root "{scan_root}" '
                       '--manifest-file "<the manifest>" --entry-file "<package>/__init__.py" --resolve-version')
    if not (root / "acme" / "__init__.py").is_file():
        assert "Leave `--entry-file` out when the scan root holds no `<package>/__init__.py`" in rule
        command = command.replace(' --entry-file "<package>/__init__.py"', "")
    command = command.replace("<the manifest>", manifest["path"]).replace("<package>", "acme")
    proc = _run(command, {"extractPublicApiHelper": str(EXTRACT), "scan_root": str(root)})
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert (result["version"], result["version_source"]) == expected


def test_the_schema_asset_keeps_only_what_the_brief_steps_read():
    """#1127 leanness-1, leanness-2 and determinism-9: Required Fields, Version Detection, Scope Object,
    Scope Types and the documented-language note stay; no tier or language list is checked; the
    version lookup is the extractor's, not a chain to walk."""
    text = _read(BRIEF_SCHEMA_DOC)
    assert re.findall(r"^#{2,3} (.+)$", text, flags=re.M) == [
        "Required Fields", "Version Detection", "Scope Object", "Scope Types"]
    assert text.count("> **Documented vs source language.**") == 1
    assert "forge-tier.yaml" not in text
    rows = {line.split("|")[1].strip(): line.split("|") for line in text.splitlines() if line.startswith("| ")}
    assert rows["language"][3].strip() == "Non-empty"
    assert "The analysis report's `forge_tier`" in rows["forge_tier"][4]
    rule = _section(text, "## Version Detection", "## Scope Object")
    assert "\u2192" not in rule, "no chain to walk by hand"
    assert "Look a version up only in two cases" in rule
    assert "`skf-extract-public-api.py --help` gives its order" in rule
    dynamic = _section(rule, "- **A `version_dynamic` manifest**", "- **A private workspace root")
    sparse = "sparse-checkout add '/<package>/__init__.py' '/<package>/_version.py' '/<the setup.py beside the manifest>'"
    assert dynamic.index(sparse) < dynamic.index("--resolve-version")
    assert "A non-zero exit or a null `version` leaves `detected_version` null." in dynamic
    assert "Read those files in the scan root" not in rule
    recommend = _read(RECOMMEND)
    assert "schemaFile" not in recommend and "skill-brief-schema" not in recommend
    generate = _read(GENERATE)
    assert "Load {schemaFile}" not in generate
    pointer = next(line for line in generate.splitlines() if line.startswith("Read {schemaFile}'s"))
    assert "**Version Detection** section only when" in pointer
    assert "no other part" not in pointer, "the language row still points to the documented-language note"
    assert "`version_dynamic`" in pointer and "a private workspace root without a `version`" in pointer
    preview = _section(generate, "### 4. Present Generation Preview", "### 5.")
    assert "`{version_source}`" in preview
    assert "found the `version` the brief shows" in preview, "a version the writer replaced names no source"


@pytest.mark.parametrize("path, start, end, kept", [
    (GENERATE, "### 2. Build Each Brief's Context", "### 3.", ()),
    (AUTO, "### 8. Write Skill Briefs", "**Gate every brief", ("doc_urls",)),
    (DOCS, "### 4. Write skill brief via canonical writer", "### 5.", ("doc_urls", "source_authority",
                                                                       "version_resolved")),
], ids=["interactive", "auto", "docs-only"])
def test_the_brief_templates_leave_out_the_keys_the_writer_drops(path, start, end, kept):
    """#1127 leanness-9: a null optional key is dropped by the writer, so no template pins one, and one
    line under each template says so; the version-precedence inputs stay."""
    section = _section(_read(path), start, end)
    [template] = _fenced(section, "json")
    keys = re.findall(r'^\s*"([a-z_]+)"\s*:', template, flags=re.M)
    for key in DROPPED_KEYS:
        assert key not in keys, key
    for key in ("target_version", "detected_version", *kept):
        assert key in keys, key
    if path != DOCS:
        assert "source_authority" not in keys and "version_resolved" not in keys
    assert f"```\n\n{ABSENT_KEY_LINE}\n" in section
    assert "scope.tier_a_include" not in _read(GENERATE)


def test_the_docs_only_brief_is_written_from_its_trimmed_context(tmp_path):
    """#1127 leanness-9: the docs-only context, without the keys the writer drops, still gives a valid
    brief through the documented write."""
    text = _read(DOCS)
    [template] = _fenced(_section(text, "### 4. Write skill brief via canonical writer", "### 5."), "json")
    url = "https://docs.example.com/guide"
    context = _fill(template, {"skill_name": "example-guide", "url": url, "forge_tier": "Quick",
                               "current_date": "2026-11-13", "user_name": "armel"})
    assert not set(DROPPED_KEYS) & set(context) and "target_ref" not in context, sorted(context)
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge-data"
    (run_dir / "brief-example-guide.json").write_bytes(json.dumps(context).encode("utf-8"))
    write = _one_command(text, '--target "{forge_data_folder}/{skill_name}/skill-brief.yaml"')
    proc = _run(write, {"writeSkillBriefHelper": str(WRITER), "forge_data_folder": str(forge),
                        "skill_name": "example-guide", "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    target = forge / "example-guide" / "skill-brief.yaml"
    brief = yaml.safe_load(target.read_text(encoding="utf-8"))
    # The writer leaves out the default `source_authority`, community.
    assert (brief["source_type"], brief.get("source_authority", "community"), brief["version"]) == (
        "docs-only", "community", "1.0.0")
    assert brief["doc_urls"][0]["url"] == url
    verdict = subprocess.run([sys.executable, str(VALIDATOR), str(target)], capture_output=True, timeout=60)
    assert verdict.returncode == 0, verdict.stdout


# --------------------------------------------------------------------------
# The auto path reads one file list (determinism-1 and determinism-2)
# --------------------------------------------------------------------------


def test_the_auto_path_has_no_grep_pre_filter_and_no_echoed_tree():
    text = _read(AUTO)
    for gone in ("grep -Ei", "grammar_matches", "--grammar-files", "--tree-paths", 'echo \'{"tree"', '"$tmp"'):
        assert gone not in text, gone
    assert '--tree-file "{run_dir}/tree.txt"' in _one_command(text, "uv run {shapeDetectHelper}")
    language = _one_command(_section(text, "### 5. Generate", "### 6. Build"), "uv run {detectLanguageHelper} --tree-file")
    assert language == 'uv run {detectLanguageHelper} --tree-file "{run_dir}/tree.txt" [--workspace-signal {workspace_kind}]'
    assert "detectWorkspacesProbeOrder:" in text.split("\n---\n", 1)[0]
    assert "{detectLanguageHelper}" not in _read(CORPORA), "6b reuses the language §5 detected"


def test_identify_units_passes_no_workspace_signal():
    """#1126: section 3's units call detects each unit's language from its own listing, with no workspace
    signal, as section 4 says."""
    text = _read(IDENTIFY)
    assert "{detectLanguageHelper}" not in text
    call = _one_command(_section(text, "### 3. Build Unit Classification Table", "### 4."),
                        "{disqualifyCandidatesHelper} units")
    assert "workspace" not in call
    language = _section(text, "### 4. Detect Primary Language Per Unit", "### 5.")
    assert ("It passes no workspace signal: a workspace root's language would answer for every unit of the "
            "workspace") in language
    assert "`.source_language`" in language


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=60)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_documented_listing_feeds_shape_and_language_detection(tmp_path):
    """The §2 listing of a local git repository, read by §3 and §5 as documented:
    a root pyproject.toml decides python over a docs site's package.json, and the
    grammar file nobody filtered reaches shape detection."""
    repo = tmp_path / "lang"
    files = {
        "pyproject.toml": b'[project]\nname = "lang"\nversion = "1.0.0"\n',
        "docs/package.json": b'{"name": "lang-docs", "private": true}\n',
        "docs/tsconfig.json": b"{}\n",
        "Grammar/lang.gram": b"start: expr\n",
        "Parser/lexer.c": b"int lex;\n", "Parser/parser.c": b"int parse;\n", "Parser/ast.c": b"int ast;\n",
        "Python/ceval.c": b"int eval;\n", "Lib/os.py": b"x = 1\n", "Lib/re.py": b"y = 2\n",
    }
    for rel, data in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(data)
    _git("init", "-q", cwd=repo)
    _git("add", "-A", cwd=repo)
    text = _read(AUTO)
    run_dir = _run_dir(tmp_path)
    [listing] = [line for line in _fenced(_section(text, "**List the target's files once.**", "### 3."), "bash")[0]
                 .split("\n") if "ls-files" in line]
    command, _, out = listing.partition(" > ")
    argv = shlex.split(command.replace("{scan_root}", repo.as_posix()))
    tree = subprocess.run(argv, capture_output=True, check=True, timeout=60).stdout
    (Path(out.strip('"').replace("{run_dir}", str(run_dir)))).write_bytes(tree)
    values = {"run_dir": str(run_dir), "shapeDetectHelper": str(SHAPE), "detectLanguageHelper": str(LANGUAGE),
              "project_path": repo.as_posix(), "scan_root": repo.as_posix(),
              "scanManifestsHelper": str(SCRIPTS / "skf-scan-manifests.py")}
    # The §2 scan of a local path writes the envelope shape detection reads.
    scan_cmd = _one_command(_section(text, "### 2. Manifest Scan", "### 3."), '<the path\'s scan root>')
    scan_cmd, _, scan_out = scan_cmd.replace("<the path's scan root>", "{scan_root}").partition(" > ")
    scanned = _run(scan_cmd, values)
    assert scanned.returncode == 0, scanned.stderr
    Path(scan_out.strip('"').replace("{run_dir}", str(run_dir))).write_bytes(scanned.stdout)
    shape = _run(_one_command(text, "uv run {shapeDetectHelper}"), values)
    assert shape.returncode == 0, shape.stderr
    assert any(s.startswith("grammar_file:") for s in json.loads(shape.stdout)["signals"])
    language = _run(_one_command(_section(text, "### 5. Generate", "### 6. Build"),
                                 "uv run {detectLanguageHelper} --tree-file"), values)
    out = json.loads(language.stdout)
    assert (out["language"], out["confidence"], out["detected_languages"]) == ("python", "high", ["python", "typescript"])


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_remote_target_takes_its_patterns_from_the_listing(tmp_path):
    """Step 5b gate run 6 determinism-2: §2 fetches a remote target as a manifests-only
    sparse checkout, where an Express-style lib/ does not exist on disk. §5 takes the
    patterns from the listing, so they root at lib/ and never fall back to src/."""
    origin = tmp_path / "express"
    for rel, data in {"package.json": b'{"name": "express", "version": "5.0.0", "main": "index.js"}\n',
                      "index.js": b"module.exports = require('./lib/express');\n",
                      "lib/express.js": b"exports.app = 1;\n", "lib/router/index.js": b"exports.route = 1;\n",
                      "test/app.js": b"require('..');\n", "examples/auth/index.js": b"require('../..');\n"}.items():
        (origin / rel).parent.mkdir(parents=True, exist_ok=True)
        (origin / rel).write_bytes(data)
    _git("init", "-q", cwd=origin)
    _git("add", "-A", cwd=origin)
    _git("-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
         "commit", "-q", "-m", "init", cwd=origin)
    _git("config", "uploadpack.allowFilter", "true", cwd=origin)
    text = _read(AUTO)
    run_dir = _run_dir(tmp_path)
    [fetch] = _fenced(_section(text, "- **`kind` is `remote`:**", "`{run_dir}/manifests-1.json` holds"), "bash")
    values = {"clone_url": origin.as_uri(), "run_dir": run_dir.as_posix(), "pinned_branch_flag": ""}
    for line in [line for line in fetch.strip().split("\n") if line.startswith("git ")]:
        argv = shlex.split(re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], line))
        subprocess.run(argv, check=True, capture_output=True, timeout=60)
    scan_root = run_dir / "clone-1"
    assert (scan_root / "package.json").is_file() and not (scan_root / "lib").exists(), "a manifests-only checkout"
    [listing] = [line for line in _fenced(_section(text, "**List the target's files once.**", "### 3."), "bash")[0]
                 .split("\n") if "ls-tree" in line]
    command, _, out = listing.partition(" > ")
    tree = subprocess.run(shlex.split(command.replace("{scan_root}", scan_root.as_posix())), capture_output=True,
                          check=True, timeout=60).stdout
    Path(out.strip('"').replace("{run_dir}", str(run_dir))).write_bytes(tree)
    section = _section(text, "### 5. Generate", "### 6. Build")
    values = {"run_dir": str(run_dir), "detectLanguageHelper": str(LANGUAGE)}
    language = _run(_one_command(section, "uv run {detectLanguageHelper} --tree-file"), values)
    values["detected_language"] = json.loads(language.stdout)["language"]
    patterns = _run(_one_command(section, "uv run {detectLanguageHelper} scope-patterns"), values)
    assert patterns.returncode == 0, patterns.stderr
    out = json.loads(patterns.stdout)
    assert (out["language"], out["source_folders"], out["include"]) == ("javascript", ["lib"], ["lib/**/*.js"])
    for gone in ("Check for the existence", "| Language | Default include |", "**Adjust for actual layout:**"):
        assert gone not in text, gone


def test_a_merged_monorepo_takes_patterns_over_every_member(tmp_path):
    """Section 3b prefers merge, and its facet guard never drops a member silently: the
    documented section 5 commands on an aws-sdk-js-v3-shaped listing, whose root lib/
    is one package beside clients/ and packages/, give patterns over every member."""
    run_dir = _run_dir(tmp_path)
    tree = ["package.json", "tsconfig.json", "lib/lib-storage/package.json", "lib/lib-storage/src/Upload.ts",
            "clients/client-s3/package.json", "clients/client-s3/src/S3Client.ts", "packages/core/package.json",
            "packages/core/src/index.ts", "scripts/build.ts"]
    (run_dir / "tree.txt").write_bytes("".join(f"{p}\n" for p in tree).encode("utf-8"))
    section = _section(_read(AUTO), "### 5. Generate", "### 6. Build")
    values = {"run_dir": str(run_dir), "detectLanguageHelper": str(LANGUAGE)}
    language = _run(_one_command(section, "uv run {detectLanguageHelper} --tree-file"), values)
    values["detected_language"] = json.loads(language.stdout)["language"]
    patterns = _run(_one_command(section, "uv run {detectLanguageHelper} scope-patterns"), values)
    assert patterns.returncode == 0, patterns.stderr
    out = json.loads(patterns.stdout)
    assert (out["language"], out["include"], out["exclude"][-1]) == ("typescript", ["**/*.ts"], "scripts/**")


def _split_block() -> tuple[str, str]:
    """The awk line and the shape detection call of the split's §4a block."""
    [block, *_] = _fenced(_section(_read(SPLIT), "### 4a.", "### 5a."), "bash")
    awk, call = block.strip().split("\n")
    return awk, call


def _list_boundary(awk: str, tree: list[str], boundary: str, run_dir: Path, c: int) -> None:
    """Run the documented awk line for candidate `c`, writing `{run_dir}/tree-{c}.txt`."""
    awk = awk.replace("<boundary path>", boundary).replace("{run_dir}", run_dir.as_posix())
    command, _, out = awk.partition(" > ")
    if shutil.which("awk"):
        listed = subprocess.run(shlex.split(command), capture_output=True, check=True, timeout=60).stdout
    else:  # the paths awk keeps: those that start with "<boundary path>/", every one for "."
        listed = "".join(f"{p}\n" for p in tree if boundary == "." or p.startswith(boundary + "/")).encode("utf-8")
    Path(out.strip('"').replace("{c}", str(c))).write_bytes(listed)


def test_each_boundary_takes_its_patterns_from_its_own_listing(tmp_path):
    """Split §4a lists a boundary's files; §5a detects its language from them and prints the
    patterns rooted at its source folder; §6a reuses that language."""
    split = _read(SPLIT)
    [block] = _fenced(_section(split, "### 5a.", "### 6a."), "bash")
    detect, patterns = block.strip().split("\n")
    assert detect == 'uv run {detectLanguageHelper} --tree-file "{run_dir}/tree-{c}.txt"', "no --workspace-signal"
    # A left-out candidate never shifts a listing onto another boundary: §5a reads its candidate's file.
    assert "from `tree-{c}.txt`, the file list §4a wrote for it as candidate `{c}`" in split
    assert "{detectLanguageHelper}" not in _section(split, "### 6a.", "### 7."), "6a reuses the language 5a detected"
    assert "default pattern table" not in split
    assert "list its files" not in _section(split, "### 5a.", "### 6a."), "§4a listed them"
    run_dir = _run_dir(tmp_path)
    tree = ["package.json", "packages/auth/package.json", "packages/auth/tsconfig.json", "packages/auth/lib/index.ts",
            "packages/auth/test/index.test.ts", "packages/auth-ui/package.json", "packages/auth-ui/src/a.ts"]
    (run_dir / "tree.txt").write_bytes("".join(f"{p}\n" for p in tree).encode("utf-8"))
    awk, _ = _split_block()
    _list_boundary(awk, tree, "packages/auth", run_dir, 1)
    values = {"run_dir": str(run_dir), "detectLanguageHelper": str(LANGUAGE), "c": "1"}
    language = json.loads(_run(detect, values).stdout)["language"]
    printed = _run(patterns.replace("<its language>", language), values)
    assert printed.returncode == 0, printed.stderr
    assert (language, json.loads(printed.stdout)["include"]) == ("typescript", ["packages/auth/lib/**/*.ts"])


SPLIT_WARNING = ("`uv run {emitEnvelopeHelper} record --run-dir \"{run_dir}\" --warning 'split: <boundary path> left "
                 "out: no source file in a language SKF detects'`")
SPLIT_CALL = ('uv run {shapeDetectHelper} --repo-url "{project_path}" --manifests-file "{run_dir}/manifests-1.json" '
              '--manifest-dir "{scan_root}" --member "<boundary path>" --tree-file "{run_dir}/tree-{c}.txt"')


def test_each_boundary_is_classified_by_one_documented_call(tmp_path):
    """#1128 determinism-4: §4a lists each workspace package's files and classifies it with one
    skf-shape-detect.py call, so its shape, its scope type and the trivial-member cut come from the
    script. Run on a monorepo of a CLI, a library, a package with no source file and a setup.py
    package: the CLI and the library take the printed scope type, the source-less package is left
    out by its count, the setup.py package (exit 1) takes full-library, and a package git does not
    track yet (its listing is empty, so the call exits 2) is left out without halting."""
    awk, call = _split_block()
    assert awk == ("awk -v p=\"<boundary path>/\" 'p == \"./\" || index($0, p) == 1' \"{run_dir}/tree.txt\" > "
                   "\"{run_dir}/tree-{c}.txt\"")
    assert call == SPLIT_CALL
    section = _section(_read(SPLIT), "### 4a.", "### 5a.")
    for needle in ("- **Exit 2:** when `tree-{c}.txt` is empty (git tracks none of the member's files: an untracked "
                   "or submodule folder), a trivial member; leave it out.",
                   'Otherwise HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase '
                   '`step-auto-scope-split:4a`): "Shape detection failed for <boundary path>: {the `error` its stderr '
                   'JSON names}."',
                   "sparse-checkout add '/<boundary path>/README*'",
                   "the case you choose sets this boundary's shape, never the run's `{shape}`",
                   "`shape`, `confidence`, `export_count`, `package_count` and `{scope_type}` feed §6a",
                   "- **`source_file_count` 0** (on exit 0 or 1): no file in a language `skf-detect-language.py` "
                   "reads: a trivial member, or one whose code is all `.vue`, `.svelte`, C or another language it "
                   "does not read; leave it out and record it as a warning, so it reaches the envelope: "
                   + SPLIT_WARNING,
                   "- **Exit 0:** `{scope_type}` ← its `scope_type`. When its `signals` hold "
                   "`app_or_library:framework_dep` or `language_or_user:parser_dep`, judge and record it as "
                   "step-auto-scope.md §4 does",
                   "- **Exit 1** (no shape, but source files): `{scope_type}` ← `full-library`, with shape `unknown`.",
                   "outside the folders `scope_hint` focuses on"):
        assert needle in section, needle
    for gone in ("no source files, no exports", "re-running the shape-to-scope ladder", "Per-boundary shape to scope"):
        assert gone not in _read(SPLIT), gone
    assert section.index(SPLIT_CALL) < section.index("derive-name"), "only the kept boundaries are named"
    assert "`scope.type` ← its §4a `{scope_type}`" in _section(_read(SPLIT), "### 6a.", "### 7.")
    # The contract names the split's halt beside step 1a §3's (#1128 lane review).
    [row3] = [line for line in _read(HEADLESS).splitlines() if line.startswith("| 3 ")]
    assert ("step 1a §3 (shape detection script error, exit code 2), and its split branch §4a (shape detection "
            "fails on a package whose files git tracks);") in row3
    front = _read(SPLIT).split("\n---\n", 1)[0]
    assert "shapeDetectProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-shape-detect.py'" in front
    assert "**`{shapeDetectHelper}`** from `{shapeDetectProbeOrder}`" in _read(SPLIT)

    repo = tmp_path / "mono"
    files = {
        "package.json": {"name": "mono", "private": True, "workspaces": ["packages/*"]},
        "packages/cli/package.json": {"name": "@mono/cli", "bin": {"mono": "bin/mono.js"},
                                      "dependencies": {"commander": "^12"}},
        "packages/cli/bin/mono.js": "require('commander');\n",
        "packages/core/package.json": {"name": "@mono/core", "main": "src/index.js"},
        "packages/core/src/index.ts": "export const core = 1;\n",
        "packages/types/package.json": {"name": "@mono/types", "exports": {".": "./schema.json"}},
        "packages/types/schema.json": "{}\n",
        "packages/legacy/setup.py": 'from setuptools import setup\nsetup(name="mono-legacy")\n',
        "packages/legacy/legacy/api.py": "def api():\n    return 1\n",
    }
    for rel, data in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes((json.dumps(data) if isinstance(data, dict) else data).encode("utf-8"))
    run_dir = _run_dir(tmp_path)
    tree = sorted(files)
    (run_dir / "tree.txt").write_bytes("".join(f"{p}\n" for p in tree).encode("utf-8"))
    # On disk, so the scan finds its manifest, but not in git's listing: an untracked package.
    (repo / "packages/fresh/src").mkdir(parents=True)
    (repo / "packages/fresh/package.json").write_bytes(b'{"name": "@mono/fresh", "main": "src/index.js"}')
    (repo / "packages/fresh/src/index.js").write_bytes(b"module.exports = 1;\n")
    scan = subprocess.run([sys.executable, str(SCAN_MANIFESTS), "scan", str(repo)], capture_output=True, timeout=60)
    assert scan.returncode == 0, scan.stderr
    (run_dir / "manifests-1.json").write_bytes(scan.stdout)
    values = {"shapeDetectHelper": str(SHAPE), "project_path": repo.as_posix(), "run_dir": str(run_dir),
              "scan_root": str(repo)}
    kept = {}
    for c, boundary in enumerate(("packages/cli", "packages/core", "packages/fresh", "packages/types",
                                  "packages/legacy"), 1):
        _list_boundary(awk, tree, boundary, run_dir, c)
        proc = _run(call.replace("<boundary path>", boundary), {**values, "c": str(c)})
        if not (run_dir / f"tree-{c}.txt").read_bytes().strip():
            assert proc.returncode == 2 and json.loads(proc.stderr)["code"] == "TREE_FILE_ERROR"
            continue
        assert proc.returncode in (0, 1), proc.stderr
        out = json.loads(proc.stdout)
        if out["source_file_count"] == 0:
            command = SPLIT_WARNING.strip("`").replace("<boundary path>", boundary)
            record = _run(command, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
            assert record.returncode == 0, record.stderr
            continue
        kept[boundary] = (proc.returncode, out["shape"], out["scope_type"] if proc.returncode == 0 else "full-library")
    assert kept == {"packages/cli": (0, "reference-app", "reference-app"),
                    "packages/core": (0, "library-API", "full-library"),
                    "packages/legacy": (1, "unknown", "full-library")}
    # The package left out by its count is named in the run's warnings, so it is not dropped unseen
    # (#1128 lane review: a package of .vue or C files counts no source file either).
    warnings = (run_dir / "warnings.jsonl").read_text(encoding="utf-8")
    assert "split: packages/types left out: no source file in a language SKF detects" in warnings
    assert "packages/fresh" not in warnings, "an untracked package is left out by its empty listing"
    proc = _run(call.replace("<boundary path>", "packages/nope"), {**values, "c": "9"})
    assert proc.returncode == 2 and json.loads(proc.stderr)["code"] == "MEMBER_NOT_FOUND", "§4a halts"


def test_a_root_package_is_listed_whole_and_kept_by_its_count(tmp_path):
    """#1128 lane review: a Cargo root `[package]` beside its `[workspace]` is a split boundary at the
    scan root (`.`), which the scan's `candidates[]` lists. Its listing is every file, so the script
    counts its source files instead of finding an empty `./` prefix listing, and its patterns leave
    the other boundaries out."""
    section = _section(_read(SPLIT), "### 4a.", "### 5a.")
    assert ("the scan root's own package (boundary path `.`) too when its manifest is not `private` and the scan's "
            "`candidates[]` lists `.`") in section
    assert "list its files (every file for the scan root's package)" in section
    assert ("the scan root's package, which lists every file, also excludes `<path>/**` for each other kept "
            "boundary") in _section(_read(SPLIT), "### 5a.", "### 6a.")
    repo = tmp_path / "ws"
    files = {
        "Cargo.toml": '[package]\nname = "root"\nversion = "0.1.0"\n\n[workspace]\nmembers = ["crates/a"]\n',
        "src/lib.rs": "pub fn r() {}\n",
        "src/z.rs": "pub fn z() {}\n",
        "crates/a/Cargo.toml": '[package]\nname = "a"\nversion = "0.1.0"\n',
        "crates/a/src/lib.rs": "pub fn a() {}\n",
    }
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(text.encode("utf-8"))
    run_dir = _run_dir(tmp_path)
    tree = sorted(files)
    (run_dir / "tree.txt").write_bytes("".join(f"{p}\n" for p in tree).encode("utf-8"))
    scan = subprocess.run([sys.executable, str(SCAN_MANIFESTS), "scan", str(repo)], capture_output=True, timeout=60)
    assert scan.returncode == 0, scan.stderr
    (run_dir / "manifests-1.json").write_bytes(scan.stdout)
    envelope = json.loads(scan.stdout)
    assert [c["path"] for c in envelope["candidates"]] == [".", "crates/a"]
    assert next(m for m in envelope["manifests"] if m["path"] == "Cargo.toml")["private"] is False
    awk, call = _split_block()
    values = {"shapeDetectHelper": str(SHAPE), "project_path": repo.as_posix(), "run_dir": str(run_dir),
              "scan_root": str(repo)}
    for c, boundary in enumerate((".", "crates/a"), 1):
        _list_boundary(awk, tree, boundary, run_dir, c)
        listed = (run_dir / f"tree-{c}.txt").read_text(encoding="utf-8").split()
        assert listed == (tree if boundary == "." else [p for p in tree if p.startswith("crates/a/")])
        proc = _run(call.replace("<boundary path>", boundary), {**values, "c": str(c)})
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert (out["shape"], out["package_count"]) == ("library-API", 1), "its own manifest alone"
        assert out["source_file_count"] > 0, boundary


def test_the_shape_reference_keeps_only_the_judged_rows_and_the_ladder():
    """#1128 leanness-3: step-auto-scope.md §3 owns the call, its output and its exit codes, and the
    script prints the scope type, so step-shape-detect.md keeps the two signals a model judges."""
    text = _read(SHAPE_REF)
    assert not text.startswith("---"), "no frontmatter: nothing resolves a helper from it"
    for gone in ("## Exit Codes", "--manifests-file", "## Output Schema", "## Invocation Contract",
                 "## Decomposition Thresholds", "| `library-API` | `full-library` |", "Corpora-dependent"):
        assert gone not in text, gone
    assert "## Judged Signals" in text and "## Heuristic Ladder" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and "signal |" in line]
    assert len(rows) == 2, rows
    framework = next(row for row in rows if "`app_or_library:framework_dep` signal |" in row)
    shape_detect = importlib.util.spec_from_file_location("skf_shape_detect", SHAPE)
    module = importlib.util.module_from_spec(shape_detect)
    shape_detect.loader.exec_module(module)
    assert f"`public-api` over {module._PUBLIC_API_EXPORTS} exports" in framework
    for row in rows:
        assert "step-auto-scope.md §4 judges which" in row and "the printed `scope_type`" in row
    auto = _read(AUTO)
    assert "Load `references/step-shape-detect.md`: it holds the two judgments §4 makes and the shape ladder." in auto
    assert "`{scope_type}` ← §3's `scope_type`." in auto
    assert "When a judgment changes `{shape}`, `{scope_type}` is the type that row gives the chosen case." in auto


def test_skill_md_and_the_auto_step_stay_under_their_token_budgets():
    """#1128 architecture-5 and leanness-4: 3,000 and 9,000 cl100k tokens, held in characters at 3.8
    a token (this prose measures 3.9 to 4.1), since no tokenizer is among the test dependencies."""
    assert len(_read(SKILL)) < 11_400
    assert len(_read(AUTO)) < 34_200


def test_the_auto_step_states_each_rule_once():
    """#1128 leanness-4: no rule restates a section, section 0c is one paragraph, and the narration of
    what each helper does inside is gone."""
    auto = _read(AUTO)
    rules = _section(auto, "## Rules", "## MANDATORY SEQUENCE")
    assert "exit code 1" not in rules and "exit code 2" not in rules and "Auto-proceed step" not in rules
    coexistence = _section(auto, "### 0c. Coexistence Detection", "### 1. Load Context")
    assert "do not re-match" not in coexistence and "```json" not in coexistence
    assert "**1. Load skill inventory:**" not in coexistence
    assert "On a non-zero exit or an empty top-level `matches[]`, go on to the route silently." in coexistence
    assert _section(auto, "### 7. Write Analysis Report", "### 8.").count("N = 1") == 1
    assert "Classify the repository from the §2 manifest scan and file list:" in auto
    assert "`{shape, signals, confidence, export_count, package_count, scope_type}`" in auto
    assert ("A *single* package with a large API surface is **not** a trigger: only a genuine multi-package "
            "monorepo is.") in auto
    for gone in ("so members are found without hand-listing", "**Decomposition Thresholds** ladder",
                 "Shape → Scope Type Mapping", "The helper owns the `tsconfig.json`",
                 "It keeps the manifest types it classifies"):
        assert gone not in auto, gone
    skill = _read(SKILL)
    for gone in ("Exports come from the ast-grep recipe runner", "`references/` holds prompt content",
                 "**Shape detection reference:**"):
        assert gone not in skill, gone
    generate = _read(GENERATE)
    assert "**Analyze-Source Summary**" not in generate
    summary = _section(generate, "### 8. Present Summary", "### 9.")
    for needle in ("each brief written (or that none was), with its path and its unit's §6 next workflow",
                   "create-stack-skill to run once their skills exist"):
        assert needle in summary, needle
    assert _section(generate, "### 10. Chain to Health Check", None).split("\n\n")[1].startswith(
        "Delete the run folder, whose payloads the emitter has read")


# --------------------------------------------------------------------------
# Run state: a finished report starts fresh (#587)
# --------------------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
def test_a_home_relative_target_is_listed(tmp_path):
    """§0 routes `~/...` as a local path, and the §2 commands quote every path,
    where bash does not expand `~`: the scan root writes the tilde as $HOME."""
    section = _section(_read(AUTO), "### 2. Manifest Scan", "### 3.")
    assert "with a leading `~` written as `$HOME`" in section
    home = tmp_path / "home"
    (home / "lib" / "src").mkdir(parents=True)
    (home / "lib" / "src" / "core.py").write_bytes(b"x = 1\n")
    [listing] = [line for line in _fenced(section, "bash")[-1].split("\n") if "find ." in line]
    run_dir = _run_dir(tmp_path)
    env = {**os.environ, "HOME": str(home)}

    def listed(scan_root: str) -> subprocess.CompletedProcess:
        command = listing.replace("{scan_root}", scan_root).replace("{run_dir}", run_dir.as_posix())
        return subprocess.run(["bash", "-c", command], capture_output=True, timeout=60, env=env)

    assert listed("~/lib").returncode != 0, "a quoted ~ does not expand"
    assert listed("~/lib".replace("~", "$HOME", 1)).returncode == 0
    assert (run_dir / "tree.txt").read_bytes().decode("utf-8").split() == ["src/core.py"]


def test_the_remote_target_is_fetched_into_the_run_folder():
    """[auto] takes one target (#1123), fetched into clone-1, the folder §3 and §5 read, and a
    failed fetch halts naming it."""
    section = _section(_read(AUTO), "### 2. Manifest Scan", "### 3.")
    clone = _one_command(section, "git clone")
    assert clone.endswith('"{run_dir}/clone-1"')
    assert '"{run_dir}/clone"' not in section
    assert ('HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:2`, '
            'path `{project_path}`): "{project_path} could not be fetched: {the first stderr line}."') in section
    assert all('"{scan_root}"' in line for line in _fenced(section, "bash")[-1].strip().split("\n"))


def test_a_finished_report_is_archived_and_the_run_starts_fresh():
    section = _section(_read(INIT), "### 1. Check for Existing Report", "### 2. Verify Prerequisites")
    for needle in ("`stepsCompleted` holds `generate-briefs` or `auto-scope`", "A finished report is never resumed",
                   "in headless mode either", "**Auto invocation or auto report:**",
                   "the report's `mode` is `'auto'`", "Headless runs resume it too",
                   "**Different target (stale collision):**"):
        assert needle in section, needle
    archive = _one_command(section, "mv -n")
    assert archive.startswith('archive="{forge_data_folder}/analyze-source-report-{project_name}-$(date -u +%Y%m%d-%H%M%S).md"')
    assert "overwrites the prior auto report" not in section
    # Read in order, a report is archived only once a rule says so: an
    # unfinished report of the same target resumes where it is.
    assert section.index("Apply the first rule that holds") < section.index("mv -n")
    assert "a report that resumes stays where it is" in section
    # Gate run 7 architecture-1: an [auto] run that ended at the coexistence
    # gate's [M]erge or [S]kip, or was interrupted, leaves a mode 'auto'
    # report. Rule 2 archives it before rule 3 can resume it, so a plain AN
    # of the same target starts the step-by-step analysis it asked for.
    assert section.index("the report's `mode` is `'auto'`") < section.index("3. **Unfinished:**")
    assert "mode-aware" not in section and "resumes through the auto path" not in section
    note = next(line for line in _read(REPO / "docs" / "workflows.md").splitlines()
                if line.startswith("**Note:** Run `@Ferris AN` again"))
    assert "an unfinished `AN[auto]` one (interrupted, or ended by a merge or skip choice)" in note
    # Rule 2 says why the run did not resume, as rules 1 and 3 do (fix round 7), and the stage table
    # names the report continue.md resumes by the same `mode` rule.
    assert ('announce "**An `[auto]` analysis never resumes: archived the unfinished report as <name>; '
            'starting a fresh analysis.**"') in section
    row = next(line for line in _read(SKILL).splitlines() if line.startswith("| 1b |"))
    assert "An unfinished step-by-step report (`mode` not `'auto'`)" in row and "without `[auto]`" in row


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
def test_the_archive_command_renames_and_never_overwrites(tmp_path):
    archive = _one_command(_section(_read(INIT), "### 1. Check for Existing Report", "### 2."), "mv -n")
    report = tmp_path / "analyze-source-report-p.md"
    report.write_bytes(b"---\nstepsCompleted: ['init', 'auto-scope']\n---\n")
    command = (archive.replace("{forge_data_folder}", str(tmp_path)).replace("{project_name}", "p")
               .replace("{outputFile}", str(report)))
    proc = subprocess.run(["bash", "-c", command], capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    moved = Path(proc.stdout.decode("utf-8").strip())
    assert not report.exists() and moved.read_bytes().startswith(b"---\nstepsCompleted")
    assert re.fullmatch(r"analyze-source-report-p-\d{8}-\d{6}\.md", moved.name)


def test_continue_resumes_only_unfinished_reports():
    text = _read(CONTINUE)
    for gone in ("already complete", "appears to be complete", "| generate-briefs | health-check |",
                 "Would you like to start a new analysis?", "Welcome back", "## Rules", "`existing_skills`",
                 "`confirmed_units`", "Present Progress Summary"):
        assert gone not in text, gone
    assert "only an unfinished report" in text
    assert "health-check.md" not in text.split("\n---\n", 1)[0], "nothing routes a resume to the health check"
    assert "step-auto-scope.md" not in text, "init archives an auto report: no resume re-enters auto-scope"
    assert "it archives a finished report and one whose `mode` is `'auto'`" in text, "the fallback report resumes"


def test_every_report_names_the_run_folder_it_was_made_in():
    """#1124: a resumed session finds the earlier session's run folder through the report's `run_dir`."""
    text = _read(INIT)
    for start, end in (("### 2b. Auto Mode Check", "### 3. Opening Question"),
                       ("### 6. Create Analysis Report", "### 7.")):
        [block] = _fenced(_section(text, start, end), "yaml")
        lines = [line.strip() for line in block.splitlines()]
        assert lines[lines.index("lastContinued: ''") + 1] == "run_dir: '{run_dir}'", start
    frontmatter = _read(TEMPLATE).split("\n---\n", 1)[0].splitlines()
    assert frontmatter[frontmatter.index("lastContinued: ''") + 1] == "run_dir: ''"


def test_a_resume_reads_two_keys_and_announces_its_next_step_in_one_line():
    """#1124 leanness-6: no greeting, progress template or Rules block; section 5 writes the folder the
    session kept, so a later resume finds it."""
    text = _read(CONTINUE)
    assert "### 1." not in text and "### 3." not in text
    assert "### 4. Determine Next Step" in text
    read = _section(text, "### 2. Read Progress State", "### 4. Determine Next Step")
    assert "Read {outputFile}'s frontmatter `stepsCompleted` and `run_dir`:" in read
    body = text.split("\n---\n", 1)[1]
    for key in ("project_paths", "project_name", "forge_tier"):
        assert key not in body, key
    route = _section(text, "### 5. Update and Route", None)
    [block] = _fenced(route, "yaml")
    assert block.strip().split("\n") == ["lastContinued: '{current_date}'", "run_dir: '{run_dir}'"]
    assert '"**Resuming from {next_step_name}** (last completed: {the last entry of `stepsCompleted`})."' in route
    assert route.index("Resuming from {next_step_name}") < route.index("{nextStepOptions}")


TAKE_OVER_NOTE = "A `run_dir` that holds a double quote, a backtick or a `$` names no run folder"


def _continue_shell() -> tuple[str, str, str]:
    """continue.md section 2, its run-folder check and its take-over line."""
    read = _section(_read(CONTINUE), "### 2. Read Progress State", "### 4. Determine Next Step")
    check, take_over = (block.strip() for block in _fenced(read, "bash"))
    assert TAKE_OVER_NOTE in read
    return read, check, take_over


def _bash(command: str, values: dict) -> subprocess.CompletedProcess:
    """Fill a documented shell line's `{placeholders}` and run it under bash."""
    filled = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], command)
    return subprocess.run(["bash", "-c", filled], capture_output=True, timeout=60)


def _zero_unit_payload() -> dict:
    """Step 6 section 9's result context for a run that confirmed no unit."""
    [template] = _fenced(_section(_read(GENERATE), "### 9. End the Run", "### 9b."), "json")
    filled = template.replace('["{the brief_path of each brief §5 wrote}"]', "[]")
    filled = filled.replace(', {"type": "brief", "path": "{each brief_path}"}', "")
    return _fill(filled, VALUES)


SCAN_DECISION = 'uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"'
WARNING_RECORD = "uv run {emitEnvelopeHelper} record --run-dir \"{run_dir}\" --warning '<the warning>'"


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
def test_a_resumed_session_takes_the_earlier_run_folder_over(tmp_path):
    """#1124: the decision and warning the earlier session recorded reach the resumed run's envelope with
    this session's warning, and this session's folder is gone, so step 6 section 10 deletes the one folder."""
    _, check, take_over = _continue_shell()
    earlier = _run_dir(tmp_path)
    fresh = earlier.parent / "skf-analyze-source-Fr3sh9Kq"
    fresh.mkdir()
    emitter = {"emitEnvelopeHelper": str(EMITTER)}
    assert SCAN_DECISION in _read(REFS / "scan-project.md")
    decision = {"gate": "scan-project.scan", "default_action": "C", "taken_action": "C",
                "reason": "headless: auto-continue past scan results",
                "evidence": {"project_paths": 1, "boundaries": 2}}
    (earlier / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
    proc = _run(SCAN_DECISION, {**emitter, "run_dir": str(earlier)})
    assert proc.returncode == 0, proc.stderr
    resolver = "customization_resolver_unavailable: no JSON"
    for folder, warning in ((earlier, "hono: missing key api_surface"), (fresh, resolver)):
        proc = _run(WARNING_RECORD.replace("<the warning>", warning), {**emitter, "run_dir": str(folder)})
        assert proc.returncode == 0, proc.stderr
    (fresh / "resolver-warning.txt").write_bytes(resolver.encode("utf-8"))
    values = {"project-root": str(tmp_path), "earlier_run_dir": str(earlier), "run_dir": str(fresh)}
    assert _bash(check, values).returncode == 0, "the earlier session's folder is taken over"
    proc = _bash(take_over, values)
    assert proc.returncode == 0, proc.stderr
    assert not fresh.exists(), "this session's own folder is deleted"
    assert (earlier / "resolver-warning.txt").read_bytes() == resolver.encode("utf-8")
    # {run_dir} is now the earlier folder: step 6 section 9 ends the run in it.
    forge = tmp_path / "forge-data"
    forge.mkdir()
    (earlier / "result-context.json").write_bytes(json.dumps(_zero_unit_payload()).encode("utf-8"))
    proc = _run(EMIT_COMMAND, {**emitter, "run_dir": str(earlier), "forge_data_folder": str(forge)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    assert [d["gate"] for d in envelope["headless_decisions"]] == ["scan-project.scan"]
    assert envelope["warnings"] == ["hono: missing key api_surface", resolver]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
@pytest.mark.parametrize("named", ["missing", "empty", "outside-skf-run", "subfolder", "parent", "other-workflow"])
def test_a_report_with_no_run_folder_to_take_keeps_the_fresh_one(tmp_path, named):
    """#1124: a gone, empty or unsafe `run_dir` deletes nothing, and the documented record line puts a
    `resumed-without-run-folder` warning in the envelope, so the reader knows the earlier entries are lost."""
    read, check, _ = _continue_shell()
    earlier = _run_dir(tmp_path)
    (earlier / "source-1").mkdir()
    elsewhere = tmp_path / "elsewhere" / "skf-analyze-source-Ab3dE5gH"
    elsewhere.mkdir(parents=True)
    other = earlier.parent / "skf-update-skill-Ab3dE5gH"
    other.mkdir()
    fresh = earlier.parent / "skf-analyze-source-Fr3sh9Kq"
    fresh.mkdir()
    value = {"missing": str(earlier.parent / "skf-analyze-source-G0neG0ne"), "empty": "",
             "outside-skf-run": str(elsewhere), "subfolder": str(earlier / "source-1"),
             "parent": f"{earlier}/..", "other-workflow": str(other)}[named]
    values = {"project-root": str(tmp_path), "earlier_run_dir": value, "run_dir": str(fresh)}
    assert _bash(check, values).returncode != 0, value
    for folder in (earlier, earlier / "source-1", elsewhere, other, fresh):
        assert folder.is_dir(), folder
    [record] = re.findall(r"`(uv run \{emitEnvelopeHelper\} record [^`]*)`", read)
    [placeholder] = re.findall(r"<[^<>]+>", record)
    named_dir = value or "none"
    proc = _run(record.replace(placeholder, named_dir), {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(fresh)})
    assert proc.returncode == 0, proc.stderr
    (fresh / "halt.json").write_bytes(json.dumps(
        {"phase": "scan-project:2", "reason": "x", "halt_reason": "resolution-failure"}).encode("utf-8"))
    envelope = _envelope(_run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(fresh)}).stderr)
    assert envelope["warnings"] == [f"resumed-without-run-folder: {named_dir}: the decisions and warnings "
                                    "recorded before this session are not in this result"]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None or shutil.which("git") is None,
                    reason="needs a POSIX shell and git")
def test_a_clone_into_a_taken_over_run_folder_replaces_the_copy_left_there(tmp_path):
    """#1124 review 1: a session cut short after scan-project section 2 (or [D] section 2) made `source-1` and
    before the step was recorded leaves the copy in its run folder, which the resume takes over. git clone
    refuses a folder that is not empty, so the resumed clone would halt on every try; it deletes the copy first."""
    _, check, take_over = _continue_shell()
    earlier = _run_dir(tmp_path)
    (earlier / "source-1").mkdir()
    (earlier / "source-1" / "stale.txt").write_bytes(b"left by the session before\n")
    fresh = earlier.parent / "skf-analyze-source-Fr3sh9Kq"
    fresh.mkdir()
    values = {"project-root": str(tmp_path), "earlier_run_dir": str(earlier), "run_dir": str(fresh)}
    assert _bash(check, values).returncode == 0, "the earlier session's folder is taken over"
    proc = _bash(take_over, values)
    assert proc.returncode == 0, proc.stderr
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "core.py").write_bytes(b"x = 1\n")
    _git("init", "-q", cwd=upstream)
    _git("add", "-A", cwd=upstream)
    _git("-c", "user.email=a@b.c", "-c", "user.name=a", "-c", "commit.gpgsign=false", "commit", "-qm", "one",
         cwd=upstream)
    clones = [line.strip() for block in _fenced(_read(SCAN_ROOT), "bash") for line in block.split("\n")
              if "git clone" in line]
    [remote] = [line for line in clones if "{clone_url}" in line]
    # {run_dir} is the earlier folder now: scan-project runs again and clones the path into it.
    proc = _bash(remote, {"run_dir": str(earlier), "i": "1", "ref_flag": "", "clone_url": upstream.as_uri()})
    assert proc.returncode == 0, proc.stderr
    assert not (earlier / "source-1" / "stale.txt").exists(), "the copy left there is gone"
    assert (earlier / "source-1" / "core.py").read_bytes() == b"x = 1\n"
    assert len(clones) == 2, clones
    for line in clones:
        assert line.startswith('rm -rf "{run_dir}/source-{i}" && git clone '), line


def test_the_fallback_to_the_interactive_chain_resets_the_mode():
    branch = _section(_read(AUTO), "- **Exit 1 (unknown shape):**", "- **Exit 2 (error):**")
    assert "Set `mode: 'interactive'`" in branch and "`{auto_mode}` to false" in branch
    # The fallback report still resumes: init archives a mode 'auto' report
    # only, and continue.md routes an unfinished report from its last step.
    assert "init archives an unfinished `'auto'` report" in branch
    routing = _section(_read(CONTINUE), "### 4. Determine Next Step", "### 5.")
    assert "| init | scan-project |" in routing and "`mode`" not in routing


def test_only_compiled_skills_count_as_already_skilled():
    """A re-run after an archived analysis keeps the units it only briefed."""
    init = _section(_read(INIT), "### 5. Check for Existing Skills", "### 6.")
    assert _one_command(init, "uv run {skillInventoryHelper}") == 'uv run {skillInventoryHelper} "{skills_output_folder}"'
    assert "`existing_briefs`" in init and "existing_briefs:" in _read(INIT)
    assert "whose `skf_skill` is true" in init, "update-skill cannot update a skill SKF did not generate"
    assert "status `briefed`" in _read(IDENTIFY)


def test_the_auto_report_carries_the_inventory_its_fallback_reads():
    """An [auto] run whose shape detection exits 1 goes on as a step-by-step analysis, which drops the
    already-skilled units and marks the briefed ones from these two keys (gate run 2 architecture-1)."""
    text = _read(INIT)
    auto = _section(text, "### 2b. Auto Mode Check", "### 3. Opening Question")
    fresh = _section(text, "### 6. Create Analysis Report", "### 7.")
    assert "existing_skills: []" not in auto
    assert "First build `existing_skills` and `existing_briefs` as section 5 does" in auto
    for key in ("existing_skills:", "existing_briefs:"):
        [line] = [line.strip() for line in auto.splitlines() if line.strip().startswith(key)]
        assert f"\n{line}\n" in "\n".join(row.strip() for row in fresh.splitlines()) + "\n", key
    for reader in (IDENTIFY, DISCOVER):
        assert "`existing_skills`" in _read(reader) and "`existing_briefs`" in _read(reader), reader.name


def test_an_unfinished_report_resumes_only_when_the_inputs_match(tmp_path):
    """A re-run with another ref or hint archives the unfinished report instead of resuming its old values
    (gate run 2 enhancement-1), and a headless run records why in its envelope's warnings."""
    section = _section(_read(INIT), "### 1. Check for Existing Report", "### 2. Verify Prerequisites")
    same = _section(section, "   - **Same target:**", "   - **Different target (stale collision):**")
    for flag in ("`--target-ref`", "`--target-refs`", "`--scope-hint`", "`--intent-hint`"):
        assert flag in same, flag
    assert "A flag the invocation does not pass changes nothing." in same
    assert same.index("**The inputs match:**") < same.index("{continueFile}") < same.index("**An input differs:**")
    assert '"**The inputs changed: archived as <name>; starting a fresh analysis.**"' in same
    assert "changed inputs" in section[section.index("**To archive a report**"):]
    [record] = re.findall(r"`(uv run \{emitEnvelopeHelper\} record [^`]*)`", same)
    run_dir = _run_dir(tmp_path)
    name = "/fd/analyze-source-report-p-20261003-101500.md"
    values = {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)}
    proc = _run(record.replace("<name>", name), values)
    assert proc.returncode == 0, proc.stderr
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "scan-project:2", "reason": "x", "halt_reason": "resolution-failure"}).encode("utf-8"))
    envelope = _envelope(_run(HALT_COMMAND, values).stderr)
    assert envelope["warnings"] == [f"inputs changed: the unfinished report was archived as {name}"]


def test_the_per_boundary_brief_rules_are_stated_once():
    text = _read(AUTO) + _read(SPLIT)
    assert text.count("Decomposed from {project_name}") == 1
    assert "This is the one statement of what each boundary's brief holds" in _read(SPLIT)
    assert "**When decomposition is active (N > 1 units):**" not in text
    assert "share the same `version`, `source_repo`, `language`" not in text


# --------------------------------------------------------------------------
# The import graph reaches the step as a summary (gate run 2 determinism-1)
# --------------------------------------------------------------------------

GRAPH_STEPS = (
    pytest.param(MAP, "{source_root}", "units-1.json", "imports-1.json", id="map-and-detect"),
    pytest.param(DISCOVER, "{scan_root}", "discover-1-units.json", "discover-1-imports.json",
                 id="discover-additional-source"),
)


def _graph_block(path: Path) -> str:
    [block] = [b for b in _fenced(_read(path), "bash") if "{countImportsHelper} summary" in b]
    return block


@pytest.mark.parametrize("path, root, units, imports", GRAPH_STEPS)
def test_the_import_graph_is_read_through_the_summary(path, root, units, imports):
    """The import envelope is kept in the run folder, never printed whole: the step reads the summary line."""
    block = _graph_block(path)
    for gone in ("mktemp", "trap ", "$work", "cat ", "SKF_UNITS"):
        assert gone not in block, gone
    imports = imports.replace("1", "{i}", 1)
    first = block.strip().split("\n")[0]
    assert first == ('uv run {countImportsHelper} units-from --units-file "{unitsFile}" --project-path '
                     f'"{{project_path}}" > "{{run_dir}}/{units.replace("1", "{i}", 1)}"')
    summaries = [line for line in block.split("\n") if "{countImportsHelper} summary" in line]
    assert summaries == [
        f'uv run {{countImportsHelper}} summary "{{run_dir}}/{imports}" --manifests "{{run_dir}}/manifests-{{i}}.json"',
        f'uv run {{countImportsHelper}} summary "{{run_dir}}/{imports}" --format markdown',
    ]
    for line in block.strip().split("\n"):
        if line.startswith("uv run {countImportsHelper} count"):
            assert f'count "{root}"' in line and " > " in line, line
    text = _read(path)
    assert "`external_dep_count`" in text and "`external_deps`" not in text
    assert "`umbrella_candidates[]`" in text


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
@pytest.mark.parametrize("path, root, units, imports", GRAPH_STEPS)
def test_the_documented_graph_block_prints_only_the_summary(tmp_path, path, root, units, imports):
    """The block, run as documented on two packages that import each other: the units JSON comes from the
    units file (its deferred unit left out), the summary line, the matrix, the cycle and the pairs reach the
    step, and the import envelope stays in its file."""
    source = tmp_path / "mono"
    files = {
        "package.json": b'{"name": "acme", "private": true, "workspaces": ["packages/*"]}\n',
        "packages/a/package.json": b'{"name": "@acme/a", "dependencies": {"@acme/b": "*", "zod": "3"}}\n',
        "packages/b/package.json": b'{"name": "@acme/b", "dependencies": {"@acme/a": "*"}}\n',
        "packages/a/src/index.ts": b"import { b } from '@acme/b';\nimport { z } from 'zod';\n",
        "packages/b/src/index.ts": b"import { a } from '@acme/a';\n",
    }
    for rel, data in files.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(data)
    run_dir = _run_dir(tmp_path)
    scan = subprocess.run([sys.executable, str(SCRIPTS / "skf-scan-manifests.py"), "scan", str(source)],
                          capture_output=True, timeout=60)
    assert scan.returncode == 0, scan.stderr
    (run_dir / "manifests-1.json").write_bytes(scan.stdout)
    units_file = tmp_path / "forge" / "analyze-source-units-mono.json"
    units_file.parent.mkdir(parents=True)
    units_file.write_bytes(json.dumps({"units": [
        {"name": name, "project_path": "https://github.com/acme/mono", "path": f"packages/{name}", "status": status,
         "manifest": {"path": f"packages/{name}/package.json", "ecosystem": "npm", "name": f"@acme/{name}",
                      "private": False}}
        for name, status in (("a", "new"), ("b", "briefed"), ("c", "deferred"))], "dropped": []}).encode("utf-8"))
    script = _graph_block(path).replace(root, source.as_posix())
    helpers = {"countImportsHelper": "skf-count-imports.py", "findCyclesHelper": "skf-find-cycles.py",
               "pairIntersectHelper": "skf-pair-intersect.py"}
    for placeholder, name in helpers.items():
        script = script.replace(f"uv run {{{placeholder}}}", f'"{sys.executable}" "{SCRIPTS / name}"')
    script = script.replace("{unitsFile}", units_file.as_posix()).replace("{project_path}", "https://github.com/acme/mono/")
    script = script.replace("{run_dir}", run_dir.as_posix()).replace("{i}", "1")
    assert not re.findall(r"\{[A-Za-z_]+\}", script), script
    proc = subprocess.run(["bash", "-c", script], capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.decode("utf-8")
    [line] = [row for row in out.splitlines() if row.startswith('{"units"')]
    summary = json.loads(line)
    assert [(u["name"], u["imports_from"], u["external_dep_count"]) for u in summary["units"]] == \
        [("a", ["b"], 1), ("b", ["a"], 0)]
    assert {m["name"]: m["internal_deps"] for m in summary["manifests"]}["@acme/a"] == ["@acme/b"]
    assert [u["name"] for u in json.loads((run_dir / units).read_text(encoding="utf-8"))["units"]] == ["a", "b"]
    lines = out.splitlines()
    matrix = lines[lines.index("**Cross-reference matrix:**"):]
    assert matrix[2:6] == ["| Unit | Imports From | Imported By | Import Sites | External Deps |",
                           "|---|---|---|---|---|", "| a | b | b | 1 | 1 |", "| b | a | a | 1 | -- |"]
    assert '"dependencies"' not in out and '"import_names"' not in out, "the envelope stays in its file"
    assert '"cycles"' in out and '"pairs"' in out
    assert "dependencies" in json.loads((run_dir / imports).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Warnings reach the envelope; the rules each live in one place
# --------------------------------------------------------------------------


def test_every_warning_a_step_raises_goes_to_the_run_sink(tmp_path):
    """A warning in a list that lives only in context never reaches the envelope:
    each step records it through the emitter, whose sink feeds `warnings`."""
    for path in [SKILL, *STEP_FILES]:
        assert "workflow_warnings" not in _read(path), path.name
    text = _read(REFS / "map-unit-exports.md")  # map-and-detect and [D] map units through it
    assert "returns only that file's path" in text and "pass it that path and the `to_read` list" in text
    assert "Save each subagent's reply as it came" not in text
    record = next(line.strip("` ") for line in re.findall(r"`uv run \{emitEnvelopeHelper\} record [^`]*`", text))
    assert record == "uv run {emitEnvelopeHelper} record --run-dir \"{run_dir}\" --warning '<the warning>'"
    for path in (CORPORA,):
        assert record in _read(path), path.name
    run_dir = _run_dir(tmp_path)
    warning = "hono: missing key api_surface"
    proc = _run(record.replace("<the warning>", warning), {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "map-and-detect:3", "reason": "x", "halt_reason": "resolution-failure"}).encode("utf-8"))
    envelope = _envelope(_run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)}).stderr)
    assert envelope["warnings"] == [warning]


UNIT_EXPORTS = REFS / "map-unit-exports.md"
HEURISTICS = REFS / "unit-detection-heuristics.md"


def _record_lines() -> tuple[str, str]:
    """map-unit-exports.md section 2's two lines: (the parser's, the recipe runner's)."""
    lines = [line for block in _fenced(_read(UNIT_EXPORTS), "bash") for line in block.split("\n")
             if "{checkUnitRecordsHelper} from-extract" in line]
    [parser_line] = [line for line in lines if "--mode quick" in line]
    [recipe_line] = [line for line in lines if "--mode full" in line]
    return parser_line, recipe_line


def test_each_record_is_written_from_the_extractors_output():
    """#1125 determinism-2 and -5: the parent runs the extraction and from-extract as one line per unit,
    a Java, Kotlin or Swift unit through the parser over every source file."""
    parser_line, recipe_line = _record_lines()
    # Each line makes the folder its extraction writes to, so the line runs as it stands.
    assert parser_line.startswith('mkdir -p "{run_dir}/extract" && uv run {extractPublicApiHelper} --mode quick '
                                  '--language {language} --source-root "{unit_root}" --all-sources '
                                  '> "{run_dir}/extract/{unit_name}.json"; ')
    assert recipe_line.startswith('mkdir -p "{run_dir}/extract" && uv run {extractPublicApiHelper} --mode full '
                                  '--source-root "{unit_root}" --scope-type {unit_scope_type} --tier {forge_tier} '
                                  '-o "{run_dir}/extract/{unit_name}.json"; ')
    for line in (parser_line, recipe_line):
        assert '--exit-code $? --unit-name "{unit_name}" --files-count {files_count} --language {language}' in line
    text = _read(UNIT_EXPORTS)
    assert "Java, Kotlin, Swift, C#" not in text


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
def test_the_documented_parser_line_and_check_give_a_java_unit_its_parser_record(tmp_path):
    """The parser line, run as documented on a Java unit, then the section 4 check: a parser record with
    the two main classes, nothing left to read and no problem; the test classes stay out."""
    unit_root = tmp_path / "mono" / "services" / "billing"
    for rel, data in {"pom.xml": b"<project><groupId>com.acme</groupId></project>\n",
                      "src/main/java/com/acme/Api.java": b"package com.acme;\npublic class Api {}\n",
                      "src/main/java/com/acme/Store.java": b"package com.acme;\npublic interface Store {}\n",
                      "src/test/java/com/acme/ApiTest.java": b"package com.acme;\npublic class ApiTest {}\n"}.items():
        (unit_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (unit_root / rel).write_bytes(data)
    run_dir = _run_dir(tmp_path)
    parser_line, _ = _record_lines()
    values = {"extractPublicApiHelper": SCRIPTS / "skf-extract-public-api.py",
              "checkUnitRecordsHelper": SCRIPTS / "skf-check-unit-records.py",
              "language": "java", "unit_root": unit_root.as_posix(), "run_dir": run_dir.as_posix(),
              "unit_name": "billing", "files_count": "4"}
    script = parser_line.replace("uv run ", f"{shlex.quote(sys.executable)} ")
    for key, value in values.items():
        script = script.replace(f"{{{key}}}", str(value))
    assert not re.findall(r"\{[A-Za-z_]+\}", script), script
    assert not (run_dir / "extract").exists(), "the line makes the folder itself"
    proc = subprocess.run(["bash", "-c", script], capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    line = json.loads(proc.stdout.decode("utf-8"))
    assert (line["strategy_used"], line["exports_count"], line["to_read"]) == ("parser", 2, [])
    check = _one_command(_read(UNIT_EXPORTS), "{checkUnitRecordsHelper} --dir")
    checked = _run(check, {"checkUnitRecordsHelper": str(SCRIPTS / "skf-check-unit-records.py"),
                           "run_dir": str(run_dir)})
    assert checked.returncode == 0, checked.stderr
    out = json.loads(checked.stdout)
    assert (out["problems"], out["unreadable"], out["warnings"]) == ([], [], [])
    [record] = out["records"]
    assert (record["unit_name"], record["files_count"], record["strategy_used"], record["confidence"]) == (
        "billing", 4, "parser", "T1")
    assert (record["api_surface"], record["export_pattern"]) == (["Api", "Store"], "parser: class 1, interface 1")


# A TypeScript unit whose entry point names two functions, passes on a module as a namespace and declares
# a name in a form no recipe matches (a destructuring export): an extraction gap.
TS_UNIT = {
    "package.json": b'{"name": "@acme/auth", "exports": {".": "./src/index.ts"}}\n',
    "src/index.ts": b'export { login, logout } from "./session";\nexport * as ns from "./ns";\n'
                    b'export const { refresh } = make();\n',
    "src/session.ts": b"export function login(): void {}\nexport function logout(): void {}\n",
    "src/ns.ts": b"export function a(): void {}\nexport function b(): void {}\n",
}


def _run_recipe_line(tmp_path: Path, env: dict | None = None) -> tuple[dict, dict]:
    """map-unit-exports.md section 2's recipe line, run as documented on TS_UNIT: (the printed line,
    the record written)."""
    unit_root = tmp_path / "mono" / "packages" / "auth"
    for rel, data in TS_UNIT.items():
        (unit_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (unit_root / rel).write_bytes(data)
    run_dir = _run_dir(tmp_path)
    _, recipe_line = _record_lines()
    values = {"extractPublicApiHelper": SCRIPTS / "skf-extract-public-api.py",
              "checkUnitRecordsHelper": SCRIPTS / "skf-check-unit-records.py",
              "language": "typescript", "unit_root": unit_root.as_posix(), "run_dir": run_dir.as_posix(),
              "unit_name": "auth", "files_count": "4", "unit_scope_type": "full-library", "forge_tier": "Forge"}
    script = recipe_line.replace("uv run ", f"{shlex.quote(sys.executable)} ")
    for key, value in values.items():
        script = script.replace(f"{{{key}}}", str(value))
    assert not re.findall(r"\{[A-Za-z_]+\}", script), script
    proc = subprocess.run(["bash", "-c", script], capture_output=True, timeout=300, env=env)
    assert proc.returncode == 0, proc.stderr
    line = json.loads(proc.stdout.decode("utf-8"))
    return line, json.loads(Path(line["record"]).read_text(encoding="utf-8"))


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_documented_recipe_line_gives_a_typescript_unit_its_record(tmp_path):
    """#1125: the recipe line on a real --mode full run, not a hand-written output: the namespace's members
    and the gap are in api_surface, and only the gap is left to read."""
    line, record = _run_recipe_line(tmp_path)
    assert (line["strategy_used"], line["exports_count"]) == ("ast-grep", 5)
    assert line["to_read"] == [{"why": "extraction-gap", "name": "refresh", "file": "src/index.ts", "line": 3}]
    assert (record["strategy_used"], record["confidence"]) == ("ast-grep", "T1")
    assert record["api_surface"] == ["login", "logout", "a", "b", "refresh"]
    assert record["export_pattern"].startswith("barrel: function 4")
    assert record["warnings"] == ["extraction gap: refresh at src/index.ts:3"]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
def test_the_documented_recipe_line_without_ast_grep_leaves_the_entry_point_to_read(tmp_path):
    """#1125: with no ast-grep on PATH the run exits 3 and still writes its output, so the record is
    source-read with the run's warning, and the entry point it listed is what is left to read."""
    path = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                           if d and not os.access(os.path.join(d, "ast-grep"), os.X_OK))
    line, record = _run_recipe_line(tmp_path, env={**os.environ, "PATH": path})
    assert (line["strategy_used"], line["exports_count"]) == ("source-read", 0)
    assert line["to_read"] == [{"why": "entry-point", "file": "src/index.ts"}]
    assert (record["confidence"], record["api_surface"]) == ("T1-low", [])
    assert any("ast-grep is not on PATH" in warning for warning in record["warnings"]), record["warnings"]


def test_step_e_counts_the_demo_files_and_scores_the_registry():
    """#1125 determinism-6: identify-units resolves skf-detect-registry.py and runs both subcommands per kept
    unit, and the heuristics name their outputs as the component-library tests."""
    text = _read(IDENTIFY)
    assert "detectRegistryProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'\n" \
        "  - '{project-root}/src/shared/scripts/skf-detect-registry.py'" in text.split("\n---\n", 1)[0]
    step_e = _section(text, "**Step E: Classify boundary type**", "### 3. Build Unit Classification Table")
    assert _one_command(step_e, "{detectRegistryHelper} demo") == \
        'uv run {detectRegistryHelper} demo --files-from "{the unit\'s tree_file}"'
    assert _one_command(step_e, "{detectRegistryHelper} registry") == \
        'uv run {detectRegistryHelper} registry --files-from "{the unit\'s tree_file}" --source-root "{scan_root}"'
    heuristics = _section(_read(HEURISTICS), "### Component Library Boundary", "### Composite Boundary")
    registry = next(line for line in heuristics.splitlines() if "registry or catalog file" in line)
    for needle in ("`skf-detect-registry.py registry`", "`qualifies`", "Judge only whether it is the registry",
                   "`selected` when `headless_accept` is true",
                   "no registry when it is false, as create-skill's registry gate does"):
        assert needle in registry, needle
    demo = next(line for line in heuristics.splitlines() if "demo/story/example" in line)
    assert "`skf-detect-registry.py demo`'s `excluded` over 30% of its `files_listed`" in demo


def test_the_language_rules_are_stated_once():
    text = _read(AUTO)
    assert text.count("detect once") == 1, "§8 states the language reuse once"
    for gone in ("do not restate the table in prose", "are not in the detector's extension map",
                 "**reuse `{detected_language}` from §5**", "No changes to that path."):
        assert gone not in text, gone


def test_one_mode_rule_and_one_brief_paths_rule():
    """The mode an [auto] run that fell back stages is the mode the contract and
    the schema describe; the docs-only branch runs the writer but not the gate."""
    contract = _read(HEADLESS)
    mode = next(line for line in contract.splitlines() if line.startswith("- `mode`"))
    assert "falls back to" in mode and "falls back to" in SCHEMA["properties"]["mode"]["description"]
    assert '"mode": "interactive"' in _read(REFS / "scan-project.md")
    for claim in (next(line for line in contract.splitlines() if line.startswith("- `brief_paths`")),
                  SCHEMA["properties"]["brief_paths"]["description"]):
        assert "outside the docs-only branch" in claim, claim


# --------------------------------------------------------------------------
# Step 5b gate run 7 determinism-1: a repository's web address on a host off
# GIT_HOSTS (no .git, no /_git/) stops for its clone URL, never a docs brief
# --------------------------------------------------------------------------

SCAN_ROOT = REFS / "scan-root.md"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
PAGE_ADDRESS = "https://codeberg.org/forgejo/forgejo"


def _inventory():
    spec = importlib.util.spec_from_file_location("skf_skill_inventory_for_contract", INVENTORY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REMEDY = "use its `.git` clone URL, its address without https:// or its SSH address"
CREDENTIALS = f"asks for credentials: SKF reads no documentation behind a login; if it is a private git repository, {REMEDY}"
UNANSWERED = f"gave git no answer in 20 s: if it is a git repository, {REMEDY}; if it is documentation, give a documentation URL that answers"
PROMPTS_OFF = b"fatal: could not read Username for 'https://codeberg.org': terminal prompts disabled\n"
# Each verdict that stops a run, with the message the helper gives for PAGE_ADDRESS.
HALTS = {"repository": f"{PAGE_ADDRESS} is a git repository: {REMEDY}.",
         "credentials": f"{PAGE_ADDRESS} {CREDENTIALS}.",
         "unanswered": f"{PAGE_ADDRESS} {UNANSWERED}."}
# A browser page of that repository, which git reads only at its `.git` clone URL (#1123).
BROWSER_PAGE = f"{PAGE_ADDRESS}/src/branch/forgejo"
PAGE_HALT = f"{BROWSER_PAGE} is a page of the git repository {PAGE_ADDRESS}.git: rerun with that clone URL."


@pytest.mark.parametrize("path", [AUTO, SCAN_ROOT], ids=["step-auto-scope", "scan-root"])
@pytest.mark.parametrize(("exit_code", "stderr", "raises", "verdict"),
                         [(0, b"", None, "repository"), (2, b"", None, "repository"), (128, b"", None, "docs"),
                          (128, PROMPTS_OFF, None, "credentials"),
                          (None, b"", subprocess.TimeoutExpired(["git"], 20), "unanswered"),
                          (None, b"", FileNotFoundError("git"), "no-git")],
                         ids=["repository", "no-branch", "docs", "credentials", "unanswered", "no-git"])
def test_both_call_sites_probe_the_page_address_with_git(path, exit_code, stderr, raises, verdict, monkeypatch,
                                                         capsys):
    """The documented call asks git whether the address serves a repository and gives the
    message a run stops with; git is stubbed, so no test reaches the network. The name stays the
    host's: naming never depends on the probe. A server that asks for credentials is not reported
    as a repository (fix round 7); git asks for the branches alone, and a probe git leaves
    unanswered stops the run instead of going docs-only (fix round 8)."""
    [call] = [line for block in _fenced(_read(path), "bash") for line in block.split("\n")
              if " derive-name --target " in line]
    assert call.endswith('derive-name --target "{project_path}" --probe-git' if path == AUTO
                         else 'derive-name --target "{path}" --probe-git'), call
    argv = _argv(call, {"skillInventoryHelper": INVENTORY.as_posix(), "project_path": PAGE_ADDRESS,
                        "path": PAGE_ADDRESS})
    assert argv[2] == "derive-name", argv
    inventory, calls = _inventory(), []

    def git(cmd, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        kwargs["stderr"].write(stderr)
        return subprocess.CompletedProcess(cmd, exit_code)

    monkeypatch.setattr(inventory.subprocess, "run", git)
    assert inventory._main_derive_name(argv[3:]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["kind"], out["name"], out["clone_url"], out["git_probe"], out["halt_message"]) == (
        "docs", "codeberg-org", None, verdict, HALTS.get(verdict))
    assert out["clone_hint"] is None
    assert calls == [["git", "ls-remote", "--exit-code", "--heads", PAGE_ADDRESS]]


@pytest.mark.parametrize("path", [AUTO, SCAN_ROOT], ids=["step-auto-scope", "scan-root"])
def test_both_call_sites_name_the_repository_behind_a_browser_page(path, monkeypatch, capsys):
    """#1123 determinism-1: a Codeberg branch page, which git cannot read at its address, gives
    the documented call the `.git` clone URL git reads at a shorter part of it, and the message a
    run stops with names it; before, the page went docs-only and an [auto] run reported success."""
    [call] = [line for block in _fenced(_read(path), "bash") for line in block.split("\n")
              if " derive-name --target " in line]
    argv = _argv(call, {"skillInventoryHelper": INVENTORY.as_posix(), "project_path": BROWSER_PAGE,
                        "path": BROWSER_PAGE})
    inventory, calls = _inventory(), []

    def git(cmd, **kwargs):
        calls.append(cmd[-1])
        if cmd[-1] == f"{PAGE_ADDRESS}.git":
            return subprocess.CompletedProcess(cmd, 0)
        kwargs["stderr"].write(b"fatal: repository not found\n")
        return subprocess.CompletedProcess(cmd, 128)

    monkeypatch.setattr(inventory.subprocess, "run", git)
    assert inventory._main_derive_name(argv[3:]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["kind"], out["name"], out["clone_url"], out["git_probe"], out["clone_hint"], out["halt_message"]) == (
        "docs", "codeberg-org", None, "repository-page", f"{PAGE_ADDRESS}.git", PAGE_HALT)
    assert calls == [BROWSER_PAGE, f"{PAGE_ADDRESS}/src/branch.git", f"{PAGE_ADDRESS}/src.git", f"{PAGE_ADDRESS}.git"]


@pytest.mark.parametrize("verdict", [*sorted(HALTS), "repository-page"])
def test_section_0_halts_with_the_helpers_message_before_any_docs_only_work(tmp_path, verdict):
    """The [auto] path halts in section 0 with the message the helper gives, before coexistence
    (section 0c) can offer a merge into an unrelated skill named after the same host, and before
    the docs-only branch can write a brief; a repository browser page halts the same way (#1123).
    [auto] takes one target, so section 2 probes no other path (#1123). The step-by-step chain's
    scan root fails with the same message."""
    auto = _read(AUTO)
    [row] = [line for line in auto.splitlines() if line.startswith("| `docs` | Documentation URL |")]
    assert row == ('| `docs` | Documentation URL | HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, '
                   'phase `step-auto-scope:0`, path `{project_path}`) with its `halt_message` when it gives one, '
                   'else `references/auto-docs-only.md`, via §0c |'), row
    assert auto.index(row) < auto.index("### 0b. Pin Resolution") < auto.index("### 0c. Coexistence Detection")
    # Every route out of section 0c is the one route it states (gate run 7 fix round 7).
    coexistence = _section(auto, "### 0c. Coexistence Detection", "### 1. Load Context")
    assert ("then goes on to its **route**: load, read fully, then execute `references/auto-docs-only.md` for a "
            "documentation URL, §1 for every other kind.") in coexistence
    assert coexistence.count("go on to the route") == 1 and coexistence.count("goes on to the route") == 1
    assert coexistence.count("auto-docs-only.md") == 1
    # [auto] takes one target (#1123): section 0 classifies it, and section 2 classifies no other path.
    assert ("The helper classifies `{project_path}`, the one entry of `project_paths[]` (init halts an `[auto]` "
            "run given several):") in auto
    assert "the first of `project_paths[]`" not in auto
    manifest_scan = _section(auto, "### 2. Manifest Scan", "### 3.")
    assert "how you point it at the target depends on the `{kind}` §0 gave:" in manifest_scan
    for gone in ("{i}", "derive-name", "For each path", "any other path", "as in §0"):
        assert gone not in manifest_scan, gone
    # The docs-only branch holds no halt of its own on git's verdict any more, and no step restates
    # the helper's messages.
    for path in (AUTO, DOCS, SCAN_ROOT):
        text = _read(path)
        for gone in ("git_repository", "git_credentials", "asks for credentials", "is a git repository",
                     "is a page of the git repository"):
            assert gone not in text, (path.name, gone)
    target, reason = (BROWSER_PAGE, PAGE_HALT) if verdict == "repository-page" else (PAGE_ADDRESS, HALTS[verdict])
    run_dir = _run_dir(tmp_path)
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "step-auto-scope:0", "reason": reason, "halt_reason": "resolution-failure", "mode": "auto",
         "path": target}).encode("utf-8"))
    proc = _run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    assert (envelope["halt_reason"], envelope["exit_code"]) == ("resolution-failure", 3)
    assert envelope["error"] == {"phase": "step-auto-scope:0", "reason": reason, "path": target}
    docs = _section(_read(SCAN_ROOT), "- **A documentation URL**", "When a command fails")
    assert ("Treat it as a command that failed with its `halt_message` as the first stderr line when it gives one "
            "(the message the [auto] path halts with), else with \"{path} is a documentation URL: run the analysis "
            "with [auto] for a docs-only brief\"." in docs), docs


def test_the_contract_and_the_guide_say_which_addresses_are_a_repository():
    """An address git reads as a repository stops the run; so does a repository browser page whose
    repository git reads at the `.git` clone URL of a shorter part of its address that keeps at
    least owner/repo, or at a Bitbucket Data Center /scm/ address, and the run names that clone URL
    (#1123). A page whose repository git finds neither way (a repository one folder below the host,
    or one git reads only without `.git`, among them), or does not reach in the 20 s the address and
    its shorter parts share, is still documentation, and the texts say to give its clone URL (gate
    run 7 fix round 8, #1123 reviews 1 and 2: no text promises a stop the helper never makes). An http:// address is never told to drop https://, which SKF puts back (#1123
    round8-2). A project wiki page is documentation, which the texts say too (#1123 lane review)."""
    [row3] = [line for line in _read(HEADLESS).splitlines() if line.startswith("| 3 ")]
    for site in ("step 1a §0 (a documentation URL that git reads as a repository, which on most hosts is the "
                 "repository's main page, one whose server asks for credentials, or one that gives git no answer "
                 "in 20 s: rerun with its `.git` clone URL, its address without https:// (an https address only) "
                 "or its SSH address, or a documentation URL that answers; a repository browser page whose "
                 "repository git reads at the `.git` clone URL of a shorter part of its address that keeps at "
                 "least `owner/repo`, such as a Codeberg `/src/branch/...` or GitLab `/-/tree/...` link or a link "
                 "to a file or folder inside a repository, or a Bitbucket Data Center `/projects/<p>/repos/<r>` "
                 "page, whose repository git reads at `/scm/<p>/<r>.git`: rerun with the clone URL the message "
                 "names; a page whose repository git finds neither way, such as a SourceForge or Launchpad code "
                 "page, a page of a repository one folder below the host or of one git reads only without `.git`, "
                 "is still read as documentation, and so is one whose repository git does not reach within the "
                 "20 s the address and its shorter parts share, so give its clone URL; a project wiki page "
                 "(`/wiki/...` or `/wikis/...` after `owner/repo`, or GitLab's `/-/wikis/...`) is read as "
                 "documentation)",
                 "step 1a §0a (docs-only URL unreachable);",
                 "step 1a §2 (the remote target cannot be fetched, or its files cannot be listed);"):
        assert site in row3, site
    assert "another path halts as in §0" not in row3
    guide = _read(REPO / "docs" / "forge-auto.md").splitlines()
    [repo_url] = [line for line in guide if line.startswith("- **Repo URL**")]
    assert "its address without `https://` (on a server that takes https) or its SSH address" in repo_url
    [doc_url] = [line for line in guide if line.startswith("- **Doc URL**")]
    for claim in ("stops in four cases", "which on most hosts", "the repository's main page", "asks for credentials",
                  "gets no answer from the address in 20 seconds", "a documentation URL that answers",
                  "(for an `http://` address, its `.git` clone URL with `http://`, or its SSH address)",
                  "When git cannot read the address but reads a repository at the `.git` clone URL of a shorter "
                  "part of it that keeps at least `owner/repo`, as for a Codeberg",
                  "SKF stops and names that clone URL.",
                  "A repository page whose repository git finds neither way, such as a SourceForge or Launchpad code "
                  "page, a page of a repository one folder below the host (`https://git.example.com/<repo>/tree/...`) "
                  "or of one git reads only without `.git` (a sourcehut page), is still read as documentation: give "
                  "its clone URL instead.",
                  # The address and every shorter part share one budget (#1123 review 2).
                  "The address and the shorter parts SKF tries share one 20-second limit, so a long link on a slow "
                  "server can run out of time before its repository is found and is then read as documentation too.",
                  # A wiki is documentation, though its repository answers git (#1123 lane review).
                  "A project wiki page (`/wiki/...` or `/wikis/...` after `owner/repo`, or a GitLab `/-/wikis/...` "
                  "page) is read as documentation too, so a wiki still makes a docs-only skill.",
                  "Without git installed, SKF reads the address as documentation and warns"):
        assert claim in doc_url, claim
    fragment = yaml.safe_load(_read(REPO / "changes" / "analyze-source-repository-page-clone-url.yaml"))
    assert (fragment["type"], fragment["scope"], fragment["issues"]) == ("breaking", "skf-analyze-source", [1123])
    assert fragment["migration"].strip() == "Rerun with the clone URL the message names."
    for claim in ("Codeberg `/src/branch/...`", "GitLab `/-/tree/...`", "a link to a file or folder inside a repository",
                  "Bitbucket Data Center `/projects/<p>/repos/<r>` page", "`/scm/<p>/<r>.git`",
                  "that keeps at least `owner/repo`", "SourceForge or Launchpad code page",
                  "a page of a repository one folder below the host", "of one git reads only without `.git`",
                  "is still read as documentation"):
        for text in (row3, doc_url, fragment["summary"]):
            assert claim in text, claim
    assert ("names the repository's `.git` clone URL when git reads the repository at a shorter part of the "
            "address that keeps at least `owner/repo` (given with `.git`) or, for Bitbucket Data Center, at its "
            "`/scm/<p>/<r>.git` address.") in fragment["summary"]
    assert ("So is a page whose repository git does not reach within the 20 seconds the address and the shorter "
            "parts tried share, and so is a project wiki page (a `/wiki/` or `/wikis/` page after `owner/repo`, or "
            "a GitLab `/-/wikis/` page), which git is not asked about past its own address, so a wiki still makes a "
            "docs-only brief.") in fragment["summary"]
    for text in (row3, doc_url, fragment["summary"]):
        assert "reads a repository at a shorter part" not in text and "at a shorter part of its address," not in text
    assert "`.git` clone URL with `http://`" in fragment["summary"] and "exit `3`" in fragment["summary"]


# The flags of an [auto] call init section 2b halts on, and the halt each gets (#1123).
AUTO_CALLS = [
    pytest.param({"--project-path": "https://docs.example.com/guide,https://github.com/acme/mono"}, "paths",
                 id="docs-first"),
    pytest.param({"--project-path": "https://github.com/acme/mono,https://docs.example.com/guide"}, "paths",
                 id="docs-later"),
    pytest.param({"--project-path": "acme/mono", "--target-ref": "v1.2.0"}, "refs", id="target-ref"),
    pytest.param({"--project-path": "acme/mono", "--target-refs": "acme/mono:v1"}, "refs", id="target-refs"),
    pytest.param({"--project-path": "acme/mono,"}, None, id="trailing-comma"),
]


@pytest.mark.parametrize(("flags", "halt"), AUTO_CALLS)
def test_an_auto_call_given_several_paths_or_a_ref_flag_halts_in_init(tmp_path, flags, halt):
    """#1123 architecture-2 and round8-1: [auto] analyzes one target and pins it with --pin, so a
    call naming several project paths, a documentation URL first or later among them, or passing
    --target-ref or --target-refs halts in init section 2b with exit 2, before the report is
    created and step 1a loads. Before, it analyzed the first path alone, dropped the others and
    the ref, and reported success. An empty entry a trailing comma leaves is not a path."""
    init = _read(INIT)
    section = _section(init, "### 2b. Auto Mode Check", "### 3.")
    [item] = [line for line in section.splitlines() if line.startswith("1. **Resolve project path:**")]
    sites = [(m.group(1), m.group(2), m.group(4), re.match(r'\): "([^"]+)"', item[m.end():]).group(1))
             for m in HALT_SITE.finditer(item)]
    assert [site[:3] for site in sites] == [("2", "input-missing", "init:2b")] * 3, sites
    no_path, several, refs = (site[3] for site in sites)
    assert no_path == "**Auto mode requires `--project-path`: no project path available.**"
    assert several == ("**Auto mode analyzes one target, and `--project-path` names {N}.** Run `[auto]` once "
                       "for each, or analyze them together without `[auto]`.")
    # --pin takes a GitHub repository's tag or branch only (skf-validate-pins.py), so every other
    # target is sent to the step-by-step chain, which reads it at --target-ref (#1123 review 1).
    assert refs == ("**Auto mode pins with `--pin`, not `--target-ref` or `--target-refs`.** Pass a GitHub "
                    "repository's tag or branch as `--pin <ref>`; to read another repository or a local path at a "
                    "ref, analyze it without `[auto]`, with `--target-ref`.")
    # The count halt reads project_paths[], so it holds whether init split --project-path or took
    # the list a continuation left, and a value of empty entries alone is no path (#1123 review 1).
    assert ("set `project_paths[]` from it (comma-split if multiple; an empty entry, as a trailing comma leaves, "
            "is dropped). If `project_paths[]` is still empty, HARD HALT") in item
    assert "When `project_paths[]` holds more than one path, `{N}` of them, HARD HALT" in item
    assert "the split gives" not in item and "If neither is available" not in item
    assert "When `--target-ref` or `--target-refs` was passed" in item
    # Both halts come before the report is created and before the route to step 1a.
    assert (section.index(item) < section.index("**Create the analysis report**")
            < section.index("execute `references/step-auto-scope.md`"))
    # The split, as the prose says: comma-separated, an empty entry dropped.
    paths = [entry.strip() for entry in flags["--project-path"].split(",") if entry.strip()]
    if halt is None:
        assert paths == ["acme/mono"], "one target: the run goes on"
        return
    message = {"paths": several.replace("{N}", str(len(paths))), "refs": refs}[halt]
    assert (len(paths) > 1) == (halt == "paths")
    assert ("--target-ref" in flags or "--target-refs" in flags) == (halt == "refs")
    [template] = re.findall(r"stage `\{run_dir\}/halt\.json` as `(\{[^`]*\})`",
                            _section(init, "## MANDATORY SEQUENCE", "### "))
    # The message goes in once the template is filled: `<ref>` in it is no placeholder.
    payload = _fill(template, {"phase": "init:2b", "the halt message": "", "halt_reason": "input-missing",
                               "auto": "auto"})
    assert payload == {"phase": "init:2b", "reason": "", "halt_reason": "input-missing", "mode": "auto"}
    payload["reason"] = message
    run_dir = _run_dir(tmp_path)
    (run_dir / "halt.json").write_bytes(json.dumps(payload).encode("utf-8"))
    proc = _run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"", "the only envelope is the halt on stderr"
    envelope = _envelope(proc.stderr)
    assert (envelope["exit_code"], envelope["halt_reason"], envelope["mode"]) == (2, "input-missing", "auto")
    assert envelope["error"] == {"phase": "init:2b", "reason": message}
    assert envelope["brief_paths"] == [] and not list(tmp_path.rglob("analyze-source-result-*.json"))
    # The contract and the Invocation Contract say the same.
    [row2] = [line for line in _read(HEADLESS).splitlines() if line.startswith("| 2 ")]
    assert ("step 1 §2b (auto mode without `--project-path`, with more than one project path, or with "
            "`--target-ref` or `--target-refs`)") in row2
    contract = _read(CONTRACT).splitlines()
    [auto_flag] = [line for line in contract if line.startswith("| **Auto flag** |")]
    assert "Requires `--project-path` naming one target." in auto_flag
    [inputs] = [line for line in contract if line.startswith("| **Headless inputs** |")]
    assert "`--project-path <path>` (comma-separated for several; one for `[auto]`)" in inputs
    # The user guide and step 1a's own context list say one target too (#1123 lane review).
    assert ("Analyze Source takes `--project-path` (one path for an `AN[auto]` run, which exits 2 when given "
            "several), `--scope-hint` and `--intent-hint`.") in _read(REPO / "docs" / "workflows.md")
    load = _section(_read(AUTO), "### 1. Load Context", "### 2.")
    assert "- `project_paths[]`: its one entry, `{project_path}`, the target to analyze" in load
    assert "root(s)" not in _read(AUTO)
    fragment = yaml.safe_load(_read(REPO / "changes" / "analyze-source-auto-one-target.yaml"))
    assert (fragment["type"], fragment["scope"], fragment["issues"]) == ("breaking", "skf-analyze-source", [1123])
    assert "now exits `2` (`input-missing`, `error.phase` `init:2b`)" in fragment["summary"]
    # Without a ref flag, [auto] read a GitHub repository at its latest release tag, any other
    # remote at its latest commit and a local path as it stood, so the summary names no ref the
    # ignored flags gave way to (#1123 review 2).
    assert fragment["summary"].rstrip().endswith("and it ignored the ref flags.")
    assert "latest release" not in fragment["summary"]
    assert fragment["migration"].strip() == (
        "Run `AN[auto]` once for each path, or analyze several paths together without `[auto]`. Pin an `[auto]` "
        "run on a GitHub repository with `--pin <tag-or-branch>` in place of `--target-ref` or `--target-refs`; "
        "to read another repository or a local path at a ref, analyze it without `[auto]`, where `--target-ref` "
        "and `--target-refs` still work.")


def test_a_missing_git_goes_docs_only_with_a_warning_naming_it(tmp_path):
    """With no git to ask, a documentation URL needs none: the docs-only branch goes on and
    leaves a warning that names git as missing (gate run 7 fix round 8)."""
    check = _section(_read(DOCS), "### 1. Validate URL reachability", "```bash")
    assert check.startswith("### 1. Validate URL reachability\n\nWhen §0's `derive-name` call gave `git_probe` "
                            "`no-git` (git is missing, so nothing asked whether `{url}` is a repository), run "), check
    [record] = re.findall(r"`(uv run \{emitEnvelopeHelper\} record [^`]*)`", check)
    assert "HARD HALT" not in check
    run_dir = _run_dir(tmp_path)
    url = "https://docs.example.com/guide/"
    proc = _run(record.replace("{url}", url), {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stderr
    reason = f"Documentation URL unreachable: {url}: 404"
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "auto-docs-only:1", "reason": reason, "halt_reason": "resolution-failure", "mode": "auto",
         "source_type": "docs-only", "path": url}).encode("utf-8"))
    envelope = _envelope(_run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)}).stderr)
    assert envelope["warnings"] == [f"git_probe_unanswered: {url} was not checked for a repository: git is missing"]
