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
  coexistence, for every project path (and fails the scan root) with the
  helper's message; a missing git goes docs-only with a warning.
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
GATE = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-analyze-result-envelope.v1.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
SETTINGS = SCHEMA["$defs"]["skf-envelope"]["const"]
PREFIX = "SKF_ANALYZE_RESULT_JSON: "

SKILL = AN / "SKILL.md"
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
DISCOVER = REFS / "discover-additional-source.md"
BRIEF_SCHEMA_DOC = AN / "assets" / "skill-brief-schema.md"
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


def _emit(tmp_path: Path, payload: dict) -> tuple[dict, Path]:
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge-data"
    forge.mkdir()
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


def test_the_hook_reads_the_latest_record_only_when_one_was_written():
    for path in (AUTO, DOCS, GENERATE):
        text = _read(path)
        assert "--result-path={forge_data_folder}/analyze-source-result-latest.json" in text, path.name
        assert "`result_path` is not null" in text, path.name
        assert 'rm -rf "{run_dir}"' in text, path.name


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
    check = _one_command(text, "uv run {validateBriefSchemaHelper}")
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
    text = _read(IDENTIFY)
    calls = [line for block in _fenced(text, "bash") for line in block.split("\n") if "{detectLanguageHelper}" in line]
    assert calls and not any("--workspace-signal" in line for line in calls)
    assert "Pass no `--workspace-signal` here" in text
    assert "`.source_language`" in text


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
              "project_path": repo.as_posix(), "scan_root": repo.as_posix(), "i": "1",
              "scanManifestsHelper": str(SCRIPTS / "skf-scan-manifests.py")}
    # The §2 scan of a local path writes the envelope shape detection reads.
    scan_cmd = _one_command(_section(text, "### 2. Manifest Scan", "### 3."), '<the path\'s scan root>')
    scan_cmd, _, scan_out = scan_cmd.replace("<the path's scan root>", "{scan_root}").partition(" > ")
    scanned = _run(scan_cmd, values)
    assert scanned.returncode == 0, scanned.stderr
    Path(scan_out.strip('"').replace("{run_dir}", str(run_dir)).replace("{i}", "1")).write_bytes(scanned.stdout)
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
    [fetch] = _fenced(_section(text, "- **`kind` is `remote`:**", "Each `{run_dir}/manifests-{i}.json`"), "bash")
    values = {"clone_url": origin.as_uri(), "run_dir": run_dir.as_posix(), "i": "1", "pinned_branch_flag": ""}
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


def test_each_boundary_takes_its_patterns_from_its_own_listing(tmp_path):
    """Split §5a lists a boundary's files, detects its language from them and prints the
    patterns rooted at its source folder; §6a reuses that language."""
    split = _read(SPLIT)
    [block] = _fenced(_section(split, "### 5a.", "### 6a."), "bash")
    awk, detect, patterns = block.strip().split("\n")
    assert detect == 'uv run {detectLanguageHelper} --tree-file "{run_dir}/tree-{i}.txt"', "no --workspace-signal"
    assert "{detectLanguageHelper}" not in _section(split, "### 6a.", "### 7."), "6a reuses the language 5a detected"
    assert "default pattern table" not in split
    run_dir = _run_dir(tmp_path)
    tree = ["package.json", "packages/auth/package.json", "packages/auth/tsconfig.json", "packages/auth/lib/index.ts",
            "packages/auth/test/index.test.ts", "packages/auth-ui/package.json", "packages/auth-ui/src/a.ts"]
    (run_dir / "tree.txt").write_bytes("".join(f"{p}\n" for p in tree).encode("utf-8"))
    awk = awk.replace("<boundary path>", "packages/auth").replace("{run_dir}", run_dir.as_posix())
    command, _, out = awk.partition(" > ")
    if shutil.which("awk"):
        listed = subprocess.run(shlex.split(command), capture_output=True, check=True, timeout=60).stdout
    else:  # the paths awk keeps: those that start with "<boundary path>/"
        listed = "".join(f"{p}\n" for p in tree if p.startswith("packages/auth/")).encode("utf-8")
    Path(out.strip('"').replace("{i}", "1")).write_bytes(listed)
    values = {"run_dir": str(run_dir), "detectLanguageHelper": str(LANGUAGE), "i": "1"}
    language = json.loads(_run(detect, values).stdout)["language"]
    printed = _run(patterns.replace("<its language>", language), values)
    assert printed.returncode == 0, printed.stderr
    assert (language, json.loads(printed.stdout)["include"]) == ("typescript", ["packages/auth/lib/**/*.ts"])


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


def test_each_remote_path_is_fetched_into_its_own_folder():
    """Two remote project paths never clone into one folder, and a failed fetch halts."""
    section = _section(_read(AUTO), "### 2. Manifest Scan", "### 3.")
    clone = _one_command(section, "git clone")
    assert clone.endswith('"{run_dir}/clone-{i}"')
    assert '"{run_dir}/clone"' not in section
    assert 'HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `step-auto-scope:2`, path `{path}`)' in section
    assert all('"{scan_root}"' in line for line in _fenced(section, "bash")[-1].strip().split("\n"))


def test_a_finished_report_is_archived_and_the_run_starts_fresh():
    section = _section(_read(INIT), "### 1. Check for Existing Report", "### 2. Verify Prerequisites")
    for needle in ("`stepsCompleted` holds `generate-briefs` or `auto-scope`", "A finished report is never resumed",
                   "in headless mode either", "**Auto invocation:**", "Headless runs resume it too",
                   "**Different target (stale collision):**"):
        assert needle in section, needle
    archive = _one_command(section, "mv -n")
    assert archive.startswith('archive="{forge_data_folder}/analyze-source-report-{project_name}-$(date -u +%Y%m%d-%H%M%S).md"')
    assert "overwrites the prior auto report" not in section
    # Read in order, a report is archived only once a rule says so: an
    # unfinished report of the same target resumes where it is.
    assert section.index("Apply the first rule that holds") < section.index("mv -n")
    assert "a report that resumes stays where it is" in section


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
                 "Would you like to start a new analysis?"):
        assert gone not in text, gone
    assert "only an unfinished report" in text
    assert "health-check.md" not in text.split("\n---\n", 1)[0], "nothing routes a resume to the health check"


def test_the_fallback_to_the_interactive_chain_resets_the_mode():
    branch = _section(_read(AUTO), "- **Exit 1 (unknown shape):**", "- **Exit 2 (error):**")
    assert "Set `mode: 'interactive'`" in branch and "`{auto_mode}` to false" in branch
    assert "set the report's `mode: 'interactive'` first" in _read(SHAPE_REF)


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
    pytest.param(MAP, "{source_root}", "<one entry per qualifying unit under {source_root}>", "imports-1.json",
                 id="map-and-detect"),
    pytest.param(DISCOVER, "{scan_root}", "<one entry per new unit that is not deferred>", "discover-1-imports.json",
                 id="discover-additional-source"),
)


def _graph_block(path: Path) -> str:
    [block] = [b for b in _fenced(_read(path), "bash") if "{countImportsHelper} summary" in b]
    return block


@pytest.mark.parametrize("path, root, units, imports", GRAPH_STEPS)
def test_the_import_graph_is_read_through_the_summary(path, root, units, imports):
    """The import envelope is kept in the run folder, never printed whole: the step reads the summary line."""
    block = _graph_block(path)
    for gone in ("mktemp", "trap ", "$work", "cat \""):
        assert gone not in block, gone
    [summary] = [line for line in block.split("\n") if "{countImportsHelper} summary" in line]
    assert summary == (f'uv run {{countImportsHelper}} summary "{{run_dir}}/{imports.replace("1", "{i}", 1)}" '
                       '--manifests "{run_dir}/manifests-{i}.json"')
    for line in block.strip().split("\n"):
        if line.startswith("uv run {countImportsHelper} count"):
            assert f'count "{root}"' in line and " > " in line, line
    text = _read(path)
    assert "`external_dep_count`" in text and "`external_deps`" not in text
    assert "`umbrella_candidates[]`" in text


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX shell")
@pytest.mark.parametrize("path, root, units, imports", GRAPH_STEPS)
def test_the_documented_graph_block_prints_only_the_summary(tmp_path, path, root, units, imports):
    """The block, run as documented on two packages that import each other: the summary line, the cycle and
    the pairs reach the step, and the import envelope stays in its file."""
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
    entries = [{"name": name, "path": f"packages/{name}", "manifest_name": f"@acme/{name}", "ecosystem": "npm"}
               for name in ("a", "b")]
    script = _graph_block(path).replace(f"[{units}]", json.dumps(entries)).replace(root, source.as_posix())
    helpers = {"countImportsHelper": "skf-count-imports.py", "findCyclesHelper": "skf-find-cycles.py",
               "pairIntersectHelper": "skf-pair-intersect.py"}
    for placeholder, name in helpers.items():
        script = script.replace(f"uv run {{{placeholder}}}", f'"{sys.executable}" "{SCRIPTS / name}"')
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
    assert "returns that path" in text and "pass it `{run_dir}`" in text
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
    assert calls == [["git", "ls-remote", "--exit-code", "--heads", PAGE_ADDRESS]]


@pytest.mark.parametrize("verdict", sorted(HALTS))
def test_section_0_halts_with_the_helpers_message_before_any_docs_only_work(tmp_path, verdict):
    """The [auto] path halts in section 0 with the message the helper gives, before coexistence
    (section 0c) can offer a merge into an unrelated skill named after the same host, and before
    the docs-only branch can write a brief; section 2 halts the same way for every other path
    (gate run 7 fix round 8). The step-by-step chain's scan root fails with the same message."""
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
    assert coexistence.count("go on to the route") == 2 and coexistence.count("goes on to the route") == 1
    assert coexistence.count("auto-docs-only.md") == 1
    # Every other project path halts the same way, under section 2's phase and with its own address.
    manifest_scan = _section(auto, "### 2. Manifest Scan", "**For each path in `project_paths[]`:**")
    assert ("§0's `derive-name --target` call gives them for any other path, and its `halt_message` halts the run "
            "as in §0, with phase `step-auto-scope:2` and that path as `{project_path}`.") in manifest_scan
    # The docs-only branch holds no halt of its own on git's verdict any more.
    for path in (AUTO, DOCS, SCAN_ROOT):
        text = _read(path)
        for gone in ("git_repository", "git_credentials", "asks for credentials", "is a git repository"):
            assert gone not in text, (path.name, gone)
    for phase in ("step-auto-scope:0", "step-auto-scope:2"):
        run_dir = _run_dir(tmp_path / phase.replace(":", "-"))
        (run_dir / "halt.json").write_bytes(json.dumps(
            {"phase": phase, "reason": HALTS[verdict], "halt_reason": "resolution-failure", "mode": "auto",
             "path": PAGE_ADDRESS}).encode("utf-8"))
        proc = _run(HALT_COMMAND, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
        assert proc.returncode == 0, proc.stderr
        envelope = _envelope(proc.stderr)
        assert (envelope["halt_reason"], envelope["exit_code"]) == ("resolution-failure", 3)
        assert envelope["error"] == {"phase": phase, "reason": HALTS[verdict], "path": PAGE_ADDRESS}
    docs = _section(_read(SCAN_ROOT), "- **A documentation URL**", "When a command fails")
    assert ("Treat it as a command that failed with its `halt_message` as the first stderr line when it gives one "
            "(the message the [auto] path halts with), else with \"{path} is a documentation URL: run the analysis "
            "with [auto] for a docs-only brief\"." in docs), docs


def test_the_contract_and_the_guide_say_which_addresses_are_a_repository():
    """An address git reads as a repository stops the run; a repository browser page git cannot
    read at its address is still documentation, and both texts say to give its clone URL (gate
    run 7 fix round 8: SKF reads no browser page for the clone URL it advertises)."""
    [row3] = [line for line in _read(HEADLESS).splitlines() if line.startswith("| 3 ")]
    for site in ("step 1a §0 (a documentation URL that git reads as a repository, which on most hosts is the "
                 "repository's main page, one whose server asks for credentials, or one that gives git no answer "
                 "in 20 s: rerun with its `.git` clone URL, its address without https:// or its SSH address, or a "
                 "documentation URL that answers; a repository browser page git cannot read at that address, such "
                 "as a Bitbucket Data Center `/projects/<p>/repos/<r>` page, a SourceForge or Launchpad code page "
                 "or a link to a file or folder inside a repository, is still read as documentation, so give its "
                 "clone URL)",
                 "step 1a §0a (docs-only URL unreachable);",
                 "another path halts as in §0"):
        assert site in row3, site
    [doc_url] = [line for line in _read(REPO / "docs" / "forge-auto.md").splitlines()
                 if line.startswith("- **Doc URL**")]
    fragment = yaml.safe_load(_read(REPO / "changes" / "analyze-source-git-url-any-host.yaml"))["summary"]
    for text in (doc_url, fragment):
        for claim in ("which on most hosts", "the repository's main page", "asks for credentials",
                      "gets no answer from the address in 20 seconds", "a documentation URL that answers",
                      "Bitbucket Data Center `/projects/<p>/repos/<r>` page", "SourceForge or Launchpad code page",
                      "a link to a file or folder inside a repository"):
            assert claim in text, claim
    assert ("A repository browser page that git cannot read at its address is still read as documentation: "
            "a Bitbucket Data Center") in doc_url and "inside a repository. Give its clone URL instead." in doc_url
    assert "is still read as documentation: give its clone URL." in fragment
    assert "Without git installed, SKF reads the address as documentation and warns" in doc_url


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
