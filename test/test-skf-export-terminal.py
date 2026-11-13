#!/usr/bin/env python3
"""export-skill's result envelope, terminal sequence, snippet timing and test-report lookup.

Step prose is not executed by any test, so these checks pin it and run the
commands it documents:

- #593: every SKF_EXPORT_RESULT_JSON line comes from the shared emitter under
  skf-export-result-envelope.v1.json. No export file types the envelope or a
  timestamp, the five headless gates record their decisions with the emitter's
  `record` (the gate ids are the schema's) in commands bash can close, and the
  documented `emit`, `emit-halt` and `record` calls produce envelopes and
  result files that pass the schema, with `headless_decisions` and a clock
  timestamp in the result file. The exit-code table lives beside the halt
  command in references/result-envelope.md, not in SKILL.md.
- #585: a --dry-run writes no result file and fires no on_complete hook, and
  manifest_path stays null until step 3 §9b wrote the manifest. The §8 dry-run
  branch shows the manifest line, and On Activation checks the skills folder
  without writing under --dry-run.
- #587: step 2 only stages the snippet; step 3 §9c copies it into the package
  after the §8 gate, the context files and the manifest, so a cancel, a dry run
  or a halt before §9c never spends a carried gotchas line's `[CARRIED]` cycle.
- #583 and determinism-2: step 1 §2 binds the version, its package and its
  evidence report from `skf-skill-inventory.py resolve`, and §4b reads the test
  report of that version through `skf-find-test-report.py find`.
- leanness-3: one gotchas resolution, first export included, serves single
  and stack skills.
- #810, #811, #818: the current SKILL.md is a gotchas source, so `[CARRIED]`
  marks only a prior pitfall no current source backs; the api line has one
  ranking (the prior `|api:` names, then `## Key API Summary`, then
  metadata.json `exports`); an anchor SKILL.md holds stays on SKILL.md.
  Update-skill's regeneration says the same.
- #1091: `; ` is reserved for the gotchas separator. The rebuild helper's
  `gotchas` action splits a prior line and writes a new one (its tests hold
  the read matrix and the round trips), so no step file states the split or
  the escaping.
- #1092: a prior pitfall stays derived, without `[CARRIED]`, while a T2-future
  annotation states it or the current SKILL.md still states its main claim
  anywhere, its frontmatter description and whole body included, and no place
  in it contradicts that claim with another version or name. New gotchas
  still come only from a T2-future annotation and source 2's SKILL.md places,
  and one left without a slot is named in a warning that says how to free a
  slot. A prior pitfall that joins several stays stated while one T2-future
  annotation or one of source 2's bullets, rows or Quick Start calls states it
  whole, and is written once; one SKILL.md states only apart or only in other
  prose, a pitfall `gotchas prior` reads whole among them, stays unbacked, so it
  is carried at most once, then dropped. These judgments are modelled here and
  handed to the helper's `resolve_gotchas`, which places them as §3a's
  `resolve` call does.
- #1093: §3b writes each name the prior `|api:` line lists with the mark that
  line gave it, `()` or bare, whatever its provenance `export_type`, and the
  map's kind sets `()` only for a name new to the line, so a re-export of an
  unchanged surface writes the same line. The snippet format's single-skill
  `|api:` placeholder sends the marks to step 2's ranking instead of giving
  functions `()`, and update-skill's headline-exports trigger no longer counts
  a listed name's kind change; its regeneration takes no `()` rule from
  create-skill's skill-sections.md placeholder, which still gives functions
  `()`.
- #1164: §2.5 is one `gotchas prior` call and the binding of its output, and
  §3a keeps its three sources, the judgments file, the `resolve` call and its
  three warnings; update-skill's write.md §5 runs the same two calls. The
  snippet format holds only its title, the parse-critical note and the two
  templates, so each snippet rule lives in generate-snippet.md alone. The
  documented calls run here on a fixture skill.
"""

from __future__ import annotations

import calendar
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
EXPORT = SRC / "skf-export-skill"
SCRIPTS = SRC / "shared" / "scripts"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
FIND_REPORT = SCRIPTS / "skf-find-test-report.py"
REBUILD = SCRIPTS / "skf-rebuild-managed-sections.py"
_RMS_SPEC = importlib.util.spec_from_file_location("skf_rms_export_terminal", REBUILD)
rms = importlib.util.module_from_spec(_RMS_SPEC)
_RMS_SPEC.loader.exec_module(rms)
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-export-result-envelope.v1.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
META = SCHEMA["$defs"]["skf-envelope"]["const"]
PREFIX = "SKF_EXPORT_RESULT_JSON: "

SKILL_MD = "SKILL.md"
LOAD = "references/load-skill.md"
SNIPPET = "references/generate-snippet.md"
UPDATE = "references/update-context.md"
SUMMARY = "references/summary.md"
ENVELOPE = "references/result-envelope.md"
CONTRACT = "references/invocation-contract.md"
PROBE = "references/preflight-snippet-root-probe.md"
ORPHAN_CONTEXT = "references/orphan-context-detection.md"
ORPHAN_ROWS = "references/orphan-row-detection.md"

# The file each headless gate lives in, by the gate id it records.
GATE_FILES = {
    "load-skill.snippet-root-layout": PROBE,
    "load-skill.snippet-root-probe": PROBE,
    "load-skill.confirmation": LOAD,
    "update-context.orphan-context-files": ORPHAN_CONTEXT,
    "update-context.orphan-rows": ORPHAN_ROWS,
    "update-context.write-confirmation": UPDATE,
}
HEREDOC_RE = re.compile(r"<<'(\w+)'\s*$")
FENCE_RE = re.compile(r"^\s*```")


def _read(rel: str) -> str:
    return (EXPORT / rel).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` up to marker `end` (or the end of the text)."""
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _fenced_blocks(text: str) -> list[list[str]]:
    """Each fenced code block's lines, the indentation of a list item's fence removed."""
    blocks, current, indent = [], None, 0
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            if current is None:
                current, indent = [], len(line) - len(line.lstrip())
            else:
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line[indent:] if line[:indent].strip() == "" else line)
    return blocks


def _heredoc_calls(text: str) -> list[tuple[str, str]]:
    """(command, body) of every fenced command that reads a quoted heredoc."""
    calls = []
    for block in _fenced_blocks(text):
        for i, line in enumerate(block):
            m = HEREDOC_RE.search(line)
            if m:
                end = block.index(m.group(1), i + 1)
                calls.append((line[:m.start()].strip(), "\n".join(block[i + 1:end])))
    return calls


def _argv(command: str, values: dict[str, str], *, keep: tuple[str, ...] = ()) -> list[str]:
    """The argv of a documented `uv run {helper} ...` call, run with this Python.

    A `[--flag ...]` synopsis group is kept when its flag is in `keep` and
    dropped otherwise; every `{name}` placeholder takes its value from `values`.
    """
    def group(m: re.Match) -> str:
        return " " + m.group(1) + " " if m.group(1).split()[0] in keep else " "

    command = re.sub(r"\[(--[^\[\]]+)\]", group, command)
    command = re.sub(r"\{([A-Za-z_][\w-]*)\}", lambda m: values[m.group(1)], command)
    words = shlex.split(command)
    assert words[:2] == ["uv", "run"], command
    return [sys.executable, *words[2:]]


def _run(argv: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=60)


def _envelope(proc: subprocess.CompletedProcess, stream: str = "stdout") -> dict:
    lines = [line for line in getattr(proc, stream).splitlines() if line.startswith(PREFIX)]
    assert len(lines) == 1, proc.stdout + proc.stderr
    envelope = json.loads(lines[0][len(PREFIX):])
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(envelope), key=str)
    assert not errors, [e.message for e in errors]
    return envelope


def _call(rel: str, verb: str) -> tuple[str, str]:
    """The one documented emitter call of `rel` whose subcommand is `verb`."""
    found = [(c, b) for c, b in _heredoc_calls(_read(rel)) if c.split()[3:4] == [verb]]
    assert len(found) == 1, f"{rel}: {len(found)} documented `{verb}` calls"
    return found[0]


def _record(run_dir: Path, gate: str, action: str = "C") -> None:
    decision = {"gate": gate, "default_action": action, "taken_action": action,
                "reason": f"headless: {gate}"}
    proc = _run([sys.executable, str(EMITTER), "record", "--workflow", META["workflow"],
                 "--run-dir", run_dir.as_posix(), "--decision"], json.dumps(decision))
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# #593: the envelope comes from the emitter
# --------------------------------------------------------------------------


def test_no_export_file_types_the_envelope_or_a_timestamp():
    for path in sorted(EXPORT.rglob("*")):
        if path.suffix not in (".md", ".toml"):
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        assert 'SKF_EXPORT_RESULT_JSON: {"' not in text, f"{rel}: the emitter prints the line"
        assert "{timestamp}" not in text, f"{rel}: the emitter names the result file from the clock"
        assert "workflow_warnings" not in text, f"{rel}: nothing reads workflow_warnings[]"
    skill = _read(SKILL_MD)
    assert "captured at activation time" not in skill
    activation = _section(skill, "## On Activation", None)
    assert ("`{emitEnvelopeHelper}` ← the first existing path of "
            "`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and "
            "`{project-root}/src/shared/scripts/skf-emit-result-envelope.py`") in activation
    assert 'mktemp -d "{project-root}/_bmad-output/.skf-run/skf-export-skill-XXXXXXXX"' in activation
    envelope = _read(ENVELOPE)
    assert "`shared/scripts/schemas/skf-export-result-envelope.v1.json` describes each field" in envelope
    for stale in ("stands alone", "back-references no other file", "## Fields"):
        assert stale not in envelope, stale
    # Every payload travels as JSON text: a raw Windows backslash is an invalid escape.
    assert "Each value is a JSON string: write a path with `/` in place of `\\`" in envelope
    assert "with each path written with `/` in place of `\\` so every value stays a JSON string" in _read(SUMMARY)


def test_the_schema_names_the_workflow_and_its_exit_codes():
    assert META["workflow"] == "skf-export-skill" and META["prefix"] + ": " == PREFIX
    assert META["result_file"] == "export-skill-result" and META["halt_status"] == "error"
    exit_codes = _section(_read(ENVELOPE), "## Exit Codes", None)
    rows = {line.split("|")[1].strip(): line for line in exit_codes.splitlines() if re.match(r"\| \d ", line)}
    for reason, code in META["exit_codes"].items():
        assert f"`{reason}`" in rows[str(code)], (reason, code)
    assert "step 3 §9c (a snippet write fails) → `write-failed`" in rows["4"]
    # The table sits beside the halt command, and the headless contract in its own
    # reference, so the always-loaded SKILL.md keeps a pointer only.
    skill = _read(SKILL_MD)
    assert "## Exit Codes" not in skill and "## Result Contract" not in skill
    assert "| **Exit codes** |" not in skill
    row = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Exit codes** |"))
    assert "`not-skf-output`" in row and "`references/result-envelope.md` maps every halt site to its code" in row
    halt_reasons = {r for r in SCHEMA["properties"]["halt_reason"]["enum"] if r is not None}
    assert halt_reasons == set(META["exit_codes"])
    named = set()
    for path in sorted(EXPORT.rglob("*.md")):
        named |= set(re.findall(r'halt_reason: "([a-z-]+)"', path.read_text(encoding="utf-8")))
    assert named <= halt_reasons, named - halt_reasons


def test_every_headless_gate_records_its_decision_where_it_decides():
    gates = SCHEMA["properties"]["headless_decisions"]["items"]["properties"]["gate"]["enum"]
    assert set(gates) == set(GATE_FILES)
    found = {}
    for rel in sorted({*GATE_FILES.values()}):
        for command, body in _heredoc_calls(_read(rel)):
            if " record " in f" {command} ":
                assert command == ('uv run {emitEnvelopeHelper} record --workflow skf-export-skill '
                                   '--run-dir "{run_dir}" --decision'), command
                found[json.loads(re.sub(r"\{[^{}\"]*\}", "[]", body))["gate"]] = rel
    assert found == GATE_FILES
    for rel in sorted({*GATE_FILES.values()}):
        assert "If `record` exits non-zero, display its error line and go on" in _read(rel), (
            f"{rel}: a decision that fails to record must show, not vanish from headless_decisions")


def test_every_heredoc_command_starts_and_ends_at_column_0():
    """bash ends a heredoc only at a line that is its delimiter alone, so an indented one never closes."""
    for path in sorted(EXPORT.rglob("*.md")):
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text(encoding="utf-8").split("\n")
        for number, line in enumerate(lines, start=1):
            m = HEREDOC_RE.search(line)
            if m:
                assert line == line.lstrip(), f"{rel}:{number}: the command is indented"
                assert m.group(1) in lines[number:], f"{rel}:{number}: no `{m.group(1)}` line at column 0 ends it"


def _decision_values(body: str) -> str:
    """A documented decision body with its placeholders filled in."""
    return (body.replace("{observed_prefixes}", '["my-skills/"]')
                .replace("{reference_root}", ".claude/skills/")
                .replace("{choice}", "d").replace("{disk_root}", "my-skills/")
                .replace("{file_path}", "/project/CLAUDE.md")
                .replace("{skill_name} v{version}", "zod v1.4.0"))


@pytest.mark.parametrize("gate", sorted(GATE_FILES), ids=sorted(GATE_FILES))
def test_the_documented_decision_passes_the_schema(tmp_path, gate):
    rel = GATE_FILES[gate]
    [(command, body)] = [(c, b) for c, b in _heredoc_calls(_read(rel)) if f'"gate":"{gate}"' in b]
    run_dir = tmp_path / ".skf-run" / "skf-export-skill-abcd1234"
    proc = _run(_argv(command, {"emitEnvelopeHelper": EMITTER.as_posix(), "run_dir": run_dir.as_posix()}),
                _decision_values(body))
    assert proc.returncode == 0, proc.stderr
    [line] = (run_dir / "headless-decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["gate"] == gate


def test_record_refuses_a_gate_the_schema_does_not_list(tmp_path):
    decision = {"gate": "summary.hook", "default_action": "C", "taken_action": "C", "reason": "x"}
    proc = _run([sys.executable, str(EMITTER), "record", "--workflow", "skf-export-skill",
                 "--run-dir", tmp_path.as_posix(), "--decision"], json.dumps(decision))
    assert proc.returncode == 1 and "fails skf-export-result-envelope.v1.json" in proc.stderr


HALT_REASONS = sorted(META["exit_codes"])


@pytest.mark.parametrize("halt_reason", HALT_REASONS, ids=HALT_REASONS)
def test_the_documented_halt_emits_the_decisions_taken_before_it(tmp_path, halt_reason):
    command, body = _call(ENVELOPE, "emit-halt")
    run_dir = tmp_path / ".skf-run" / "skf-export-skill-abcd1234"
    _record(run_dir, "load-skill.confirmation")
    payload = (body.replace("<phase>", "update-context §9")
                   .replace("<the halt message>", "CLAUDE.md: the write failed its check")
                   .replace("<halt_reason>", halt_reason).replace("<name>", "zod"))
    values = {"emitEnvelopeHelper": EMITTER.as_posix(), "run_dir": run_dir.as_posix()}
    proc = _run(_argv(command, values, keep=("--run-dir",)), payload)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "", "a halt prints its line on stderr"
    envelope = _envelope(proc, "stderr")
    assert (envelope["status"], envelope["halt_reason"]) == ("error", halt_reason)
    assert envelope["exit_code"] == META["exit_codes"][halt_reason]
    assert envelope["skills"] == ["zod"] and envelope["manifest_path"] is None
    assert envelope["result_path"] is None, "a halt writes no result file"
    assert envelope["error"] == {"phase": "update-context §9", "reason": "CLAUDE.md: the write failed its check"}
    assert [d["gate"] for d in envelope["headless_decisions"]] == ["load-skill.confirmation"]
    assert list(tmp_path.glob("**/export-skill-result*.json")) == []


def _success_payload(skills: Path, manifest: str) -> str:
    """The payload summary.md §6 describes for a finished run, built from its own template."""
    _, body = _call(SUMMARY, "emit")
    template = json.loads(re.sub(r"\{result_contract\}", "null", body.replace('"{', '"<').replace('}"', '>"')))
    assert set(template) == {"status", "skills", "context_files_updated", "manifest_path", "result_contract"}
    contract = {"skill": "skf-export-skill", "status": "success",
                "outputs": [{"type": "skill", "path": f"{skills}/zod/1.4.0/zod/context-snippet.md"},
                            {"type": "config", "path": "CLAUDE.md"},
                            {"type": "manifest", "path": manifest}],
                "summary": {"skills": ["zod"], "always_on_tokens": 120, "on_trigger_tokens": {"zod": 900}}}
    return json.dumps({"status": "success", "skills": ["zod"], "context_files_updated": ["CLAUDE.md"],
                       "manifest_path": manifest, "result_contract": contract})


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "interactive"])
def test_the_documented_success_emit_writes_both_result_files(tmp_path, headless):
    command, _ = _call(SUMMARY, "emit")
    skills = tmp_path / "skills"
    skills.mkdir()
    run_dir = tmp_path / ".skf-run" / "skf-export-skill-abcd1234"
    keep = ("--result-dir",)
    if headless:
        _record(run_dir, "update-context.write-confirmation")
        keep += ("--run-dir",)
    manifest = (skills / ".export-manifest.json").as_posix()
    values = {"emitEnvelopeHelper": EMITTER.as_posix(), "run_dir": run_dir.as_posix(),
              "skills_output_folder": skills.as_posix()}
    before = int(time.time())
    proc = _run(_argv(command, values, keep=keep), _success_payload(skills, manifest))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc)
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("success", 0, None)
    assert envelope["manifest_path"] == manifest and envelope["context_files_updated"] == ["CLAUDE.md"]
    assert "timestamp" not in envelope and "run_id" not in envelope, "the line gets result_path, the file the rest"
    [per_run] = [p for p in skills.glob("export-skill-result-*.json") if p.name != "export-skill-result-latest.json"]
    assert re.fullmatch(r"export-skill-result-\d{8}-\d{6}\.json", per_run.name), per_run.name
    assert Path(envelope["result_path"]).as_posix() == per_run.as_posix()
    latest = skills / "export-skill-result-latest.json"
    assert latest.read_bytes() == per_run.read_bytes(), "-latest is a copy of the per-run record"
    record = json.loads(per_run.read_text(encoding="utf-8"))
    if headless:
        assert record["run_id"] == "abcd1234"
        assert [d["gate"] for d in record["headless_decisions"]] == ["update-context.write-confirmation"]
    else:
        assert "run_id" not in record, "an interactive run has no run folder, so its record names no run"
        assert record["headless_decisions"] == []
    stamped = calendar.timegm(time.strptime(record["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
    assert before - 5 <= stamped <= time.time() + 5, "the timestamp is the clock's"
    assert record["outputs"][2] == {"type": "manifest", "path": manifest}
    result = _section(_read(SUMMARY), "### 6. Result Contract and Envelope", "### 6b. ")
    assert "The emitter derives `exit_code` (0) and `halt_reason` (null) and sets `result_path`" in result
    assert "the emitter adds `timestamp`, `headless_decisions` and `warnings` to the record it writes, " \
        "and `run_id` in a headless run" in result


def test_the_documented_dry_run_emit_writes_no_result_file(tmp_path):
    command, _ = _call(SUMMARY, "emit")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "export-skill-result-latest.json").write_bytes(b'{"status": "success"}\n')
    run_dir = tmp_path / ".skf-run" / "skf-export-skill-abcd1234"
    _record(run_dir, "load-skill.confirmation")
    payload = json.dumps({"status": "dry-run", "skills": ["zod"], "context_files_updated": [],
                          "manifest_path": None})
    values = {"emitEnvelopeHelper": EMITTER.as_posix(), "run_dir": run_dir.as_posix(),
              "skills_output_folder": skills.as_posix()}
    proc = _run(_argv(command, values, keep=("--run-dir",)), payload)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc)
    assert (envelope["status"], envelope["manifest_path"], envelope["result_path"]) == ("dry-run", None, None)
    assert [p.name for p in skills.iterdir()] == ["export-skill-result-latest.json"]
    assert (skills / "export-skill-result-latest.json").read_bytes() == b'{"status": "success"}\n'


# --------------------------------------------------------------------------
# #585: dry-run writes nothing, and manifest_path follows the manifest write
# --------------------------------------------------------------------------


def test_a_dry_run_writes_no_result_file_and_fires_no_hook():
    summary = _read(SUMMARY)
    result = _section(summary, "### 6. Result Contract and Envelope", "### 6b. ")
    dry = next(line for line in result.splitlines() if line.startswith("- **With `--dry-run`:**"))
    assert "leave out `--result-dir` and `result_contract`" in dry and "`manifest_path: null`" in dry
    real = next(line for line in result.splitlines() if line.startswith("- **Without `--dry-run`:**"))
    assert "pass `--result-dir`" in real and "the `{manifest_path}` step 3 §9b bound" in real
    hook = _section(summary, "### 6b. Post-Export Hook (Optional)", "### 7. ")
    assert hook.startswith("### 6b. Post-Export Hook (Optional)\n\nSkip this section on a dry run")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook, "a path with a space stays one argument"
    assert "when `{result_path}` is null" in hook
    flags = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Flags** |"))
    assert "no result file is written and no `on_complete` hook runs" in flags
    assert "write nothing other than a headless run's scratch run folder" in flags, (
        "a headless dry run still creates and deletes its run folder")
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    hook_comment = toml[toml.index("# Optional post-export hook"):toml.index("\non_complete = ")]
    assert "a --dry-run writes none and never invokes it" in " ".join(
        line.lstrip("#").strip() for line in hook_comment.splitlines())


def test_manifest_path_is_bound_only_once_the_manifest_is_written():
    update = _read(UPDATE)
    manifest = _section(update, "### 9b. Update Export Manifest", "### 9c. ")
    bind = "Once every `set` has exited 0, bind `{manifest_path}` ← `{skills_output_folder}/.export-manifest.json`"
    assert bind in manifest
    assert manifest.index("[--ides {ides_written}]") < manifest.index(bind)
    meaning = SCHEMA["properties"]["manifest_path"]["description"]
    assert "Null when no manifest write completed: every dry run, and every halt before the manifest write" in meaning


def test_a_step_4_halt_reports_the_batch_and_what_it_wrote():
    """A field a halt leaves out reads as empty, so every halt passes the batch it resolved,
    and the fields step 3 writes follow the run's state, stated once (leanness-4)."""
    halt = _section(_read(ENVELOPE), "## Emitting a Halt", "## Exit Codes")
    assert "Always pass `skills`, the resolved batch (`[]` only before step 1 bound `skill_batch`" in halt
    assert ("Add `context_files_updated`, the context files step 3 §9 wrote before the halt, once it has "
            "written one, and `manifest_path`, the `{manifest_path}` step 3 §9b bound, once the manifest is "
            "written") in halt
    assert "the emitter gives `context_files_updated` `[]` and `manifest_path` `null`" in halt
    update = _read(UPDATE)
    manifest = _section(update, "### 9b. Update Export Manifest", "### 9c. ")
    assert 'HALT (exit code 4, `halt_reason: "manifest-write-failed"`, phase `update-context §9b`)' in manifest
    snippets = _section(update, "### 9c. Write the Snippets", None)
    assert 'On a failed copy, HALT (exit code 4, `halt_reason: "write-failed"`, phase `update-context §9c`)' in snippets


# The step files whose HALTs leave their envelope to result-envelope.md, by the name their phases use.
HALT_FILES = {LOAD: "load-skill", SNIPPET: "generate-snippet", UPDATE: "update-context"}
SECTION_RE = re.compile(r"^###+ (\d+(?:\.\d+)?[a-z]?)\.", re.M)


@pytest.mark.parametrize("rel", sorted(HALT_FILES), ids=sorted(HALT_FILES))
def test_every_halt_names_its_phase_and_states_no_envelope_of_its_own(rel):
    """leanness-4: the envelope and its defaults live in result-envelope.md; a halt
    site names its exit code, halt_reason and the phase of the section it is in."""
    text = _read(rel)
    assert "envelope per" not in text and "context_files_updated: []" not in text, rel
    assert "`manifest_path: null`" not in text and "`skills: []`" not in text, rel
    rules = _section(text, "## Rules", "## MANDATORY SEQUENCE")
    assert ("Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its "
            "envelope as `references/result-envelope.md` states") in rules
    sites = 0
    for line in _section(text, "## MANDATORY SEQUENCE", None).split("\n"):
        if "HALT" not in line or "halt_reason" not in line:
            continue
        sites += 1
        before = text[:text.index(line)]
        section = SECTION_RE.findall(before)[-1]
        assert f"phase `{HALT_FILES[rel]} §{section}`" in line, (rel, section, line[:120])
    assert sites, rel


def test_activation_halts_name_their_phase_and_leave_the_envelope_to_the_contract():
    """leanness-4: result-envelope.md states the headless HALT envelope once, so
    each On Activation halt names its exit code, halt_reason and phase, and a
    Workflow Rule points every HALT at the contract."""
    skill = _read(SKILL_MD)
    rules = _section(skill, "## Workflow Rules", "## Stages")
    assert ("- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its "
            "envelope as `references/result-envelope.md` states") in rules
    activation = _section(skill, "## On Activation", None)
    assert "envelope per" not in activation and "`skills: []`" not in activation
    assert "context_files_updated: []" not in activation and "manifest_path: null" not in activation
    sites = re.findall(r'HALT \(exit code (\d), `halt_reason: "([a-z-]+)"`\) at phase `([^`]+)`', activation)
    assert sites == [("4", "context-rebuild-failed", "on-activation §4"), ("4", "write-failed", "on-activation §4"),
                     ("4", "write-failed", "on-activation §5")]
    for code, reason, _ in sites:
        assert META["exit_codes"][reason] == int(code), reason
    # The contract covers what the cut sites stated: no --run-dir and `skills: []` before step 1.
    envelope = _read(ENVELOPE)
    assert "`[]` only before step 1 bound `skill_batch`, as at every On Activation halt" in envelope
    assert "Pass `--run-dir` once On Activation bound `{run_dir}`" in envelope


def test_activation_runs_the_resolver_through_uv_and_records_its_failure():
    """#595 option (a): the resolver runs under uv with --project-root; a failure
    prints one warning, and a headless run records the reason in its run sink,
    through a file, once step 4 created the folder, so the envelope carries it.
    #596: a `!` entry drops the project-context default, and customize.toml
    says how; the prepend comment says when SKILL.md runs it (customization-2)."""
    activation = " ".join(_section(_read(SKILL_MD), "## On Activation", None).split())
    assert ("uv run {resolveCustomizationHelper} --skill {skill-root} "
            "--project-root {project-root} --key workflow") in activation
    assert "{project-root}/_bmad/scripts/resolve_customization.py" not in activation
    for token in ("It merges the bundled `{skill-root}/customize.toml` with "
                  "`{project-root}/_bmad/custom/skf-export-skill.toml` (team overrides, committed) and `.user.toml` "
                  "(personal overrides, gitignored).",
                  "When it exits non-zero, prints no JSON or is missing, print one line, "
                  "`[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr "
                  "line, `SKF helper skf-resolve-customization.py not found` when the "
                  "script is missing, `no JSON` when it printed none).",
                  "If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled "
                  "defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run.",
                  "Keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran): a "
                  "headless run records it once step 4 creates its run folder, and an interactive run only "
                  "prints it.",
                  'write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a '
                  'file write', 'run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '
                  '"$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`',
                  "(the bundled default loads every `project-context.md` under `{project-root}`, none in "
                  "`{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` "
                  "entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names "
                  "one file)",
                  "`headless_mode: true` in `{sidecar_path}/preferences.yaml`"):
        assert token in activation, token
    assert "\u2014" not in _section(_read(SKILL_MD), "3. **Resolve workflow customization.**", "4. **Resolve")
    # #601: no bare `_bmad/` path is left for the path-standards scan to flag.
    assert re.search(r"(?<!\{project-root\}/)_bmad/", activation) is None
    toml = " ".join(re.sub(r"(?m)^# ?", "", _read("customize.toml")).split())
    assert "Steps to run before the standard activation (uv probe, config load)" not in toml
    assert ("Steps SKILL.md On Activation step 3 runs once this file resolves: after the config load (step 1) and "
            "the headless flag (step 2), before step 4 resolves the helpers and creates the run folder") in toml
    assert ('to stop loading those files, set in {project-root}/_bmad/custom/skf-export-skill.toml: '
            '[workflow] persistent_facts = ["!file:{project-root}/**/project-context.md"]') in toml
    assert "Team overrides: {project-root}/_bmad/custom/skf-export-skill.toml" in toml
    assert "Each entry is either:" not in toml
    assert ("Each entry is one of: - a literal sentence" in toml
            and "- an entry prefixed with `!`, which loads nothing and drops each earlier entry it names." in toml)


def test_conventions_route_every_reference_file():
    """#601 (export architecture-8): the Conventions name the stage that loads
    each reference outside the Stages table, and how module-level and
    sibling-skill paths resolve."""
    skill = _read(SKILL_MD)
    conventions = _section(skill, "## Conventions", "## Role")
    assert ("- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the "
            "SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root") in conventions
    assert ("- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the "
            "SKF module root, and that skill must be installed with this one.") in conventions
    # Export holds no scripts/ folder: the Conventions name only the folders it has.
    assert not (EXPORT / "scripts").exists() and "`scripts/`" not in conventions
    assert "`assets/` holds the snippet and managed-section templates." in conventions
    assert sorted(p.name for p in (EXPORT / "assets").iterdir()) == ["managed-section-format.md", "snippet-format.md"]
    routes = {"load-skill.md": ("preflight-snippet-root-probe.md",),
              "update-context.md": ("orphan-context-detection.md", "orphan-row-detection.md", "manifest-rebuild.md")}
    for loader, files in routes.items():
        for name in files:
            assert f"`{name}`" in conventions, name
            assert name in _read(f"references/{loader}"), (loader, name)
    stages = set(re.findall(r"\| (references/[a-z-]+\.md) \|", _section(skill, "## Stages", "## Invocation")))
    named = {f"references/{n}" for files in routes.values() for n in files}
    named |= {"references/invocation-contract.md", "references/result-envelope.md"}
    for path in sorted((EXPORT / "references").glob("*.md")):
        rel = f"references/{path.name}"
        assert rel in stages or rel in named, f"{rel}: no Stages row and no Conventions route"
        if rel in named:
            assert f"`{path.name}`" in conventions, rel


def test_the_dry_run_shows_the_manifest_line_where_it_runs():
    """architecture-2: a dry run with passive context on leaves step 3 at §8, so §8 shows the line too."""
    update = _read(UPDATE)
    line = "**[DRY RUN] Export manifest would be updated for {skill-name-list}: ides: {ides_written}.**"
    menu = _section(update, "### 8. Present MENU OPTIONS", "**If NOT dry-run:**")
    assert line in menu and "§9 to §9c do not run" in menu
    assert "give `{ides_written}` as §9b defines it, over the targets above, or `none` when it is empty" in menu
    assert "deduplicated" not in menu, "§9b alone defines ides_written"
    assert line in _section(update, "### 9b. Update Export Manifest", "### 9c. ")


def test_activation_checks_the_skills_folder_without_writing_under_dry_run():
    probe = _section(_read(SKILL_MD), "5. **Pre-flight write check.**", "6. Execute each entry")
    assert "Without `--dry-run`, probe it with a write:" in probe
    dry = next(line for line in probe.splitlines() if "With `--dry-run`, check without writing" in line)
    assert '`test -w "{skills_output_folder}"`' in dry
    assert probe.index("Without `--dry-run`") < probe.index('printf \'probe\' > "{skills_output_folder}/.skf-write-probe"')


# --------------------------------------------------------------------------
# #587: the snippet is written after the step-3 gate, as the run's last write
# --------------------------------------------------------------------------

SNIPPET_COPY = 'cp "{export_stage_dir}/drafts/{skill-name}/context-snippet.md" "{resolved_skill_package}/context-snippet.md"'


def _writes_into_the_package(text: str) -> list[str]:
    """Fenced command lines that write into `{resolved_skill_package}`."""
    hits = []
    for block in _fenced_blocks(text):
        for line in block:
            if "{resolved_skill_package}" in line and re.search(r"(^|\s)(cp|mv|tee|rm)\s|>", line):
                hits.append(line.strip())
    return hits


def test_step_2_stages_the_snippet_and_writes_nothing_into_the_package():
    text = _read(SNIPPET)
    assert _writes_into_the_package(text) == []
    preview = _section(text, "### 5. Preview the Snippet", "### 6. ")
    assert "Nothing is written to a skill package in this step" in preview
    assert "step 3 copies each measured draft into its package after its [C] gate (§9c)" in preview


def test_step_3_writes_the_snippets_last_after_the_gate():
    update = _read(UPDATE)
    assert _writes_into_the_package(update) == [SNIPPET_COPY]
    order = [update.index(marker) for marker in ("### 8. Present MENU OPTIONS", "### 9. Write and Verify",
                                                  "### 9b. Update Export Manifest", "### 9c. Write the Snippets",
                                                  SNIPPET_COPY)]
    assert order == sorted(order), "the copy runs after the gate, the context files and the manifest"
    gate = _section(update, "#### Gate handling", "### 9. ")
    assert "write the targets (§9), record the export (§9b) and write the snippets (§9c)" in gate
    cancel = next(line for line in gate.splitlines() if line.startswith("- **[X]**"))
    assert "delete the `{export_stage_dir}` folder" in cancel and "§9c" not in cancel
    last = _section(update, "### 9c. Write the Snippets", None)
    assert last.rstrip().endswith("Once every snippet is written, delete the `{export_stage_dir}` folder.")
    assert "the end of §9c" in _section(update, "### 2. Stage Folder", "### 3. ")
    rules = _section(_read(SKILL_MD), "## Workflow Rules", "## Stages")
    decision = next(line for line in rules.splitlines() if line.startswith("- **Snippet timing:**"))
    assert "after its [C] gate, as step 3's last write" in decision and "`[CARRIED]`" in decision
    assert "A cancel, a dry run or a halt before §9c leaves every snippet" in decision, (
        "a §9c halt keeps the snippets copied before it")
    for path in sorted(EXPORT.rglob("*.md")):
        assert "the run's last write" not in path.read_text(encoding="utf-8"), (
            f"{path.name}: step 5 writes the result files after §9c")


# Every step file and protocol a run reads before step 3 §9c, in run order.
BEFORE_9C = ("references/load-skill.md", PROBE, SNIPPET, ORPHAN_CONTEXT, ORPHAN_ROWS)


def test_nothing_before_9c_writes_into_a_package():
    """#587: a cancel, a dry run or a halt before §9c leaves every package's snippet as it was."""
    for rel in BEFORE_9C:
        assert _writes_into_the_package(_read(rel)) == [], rel
    update = _read(UPDATE)
    assert _writes_into_the_package(update[:update.index("### 9c. Write the Snippets")]) == []


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_the_9c_copy_publishes_the_carried_draft_byte_for_byte(tmp_path):
    """The #587 fixture: a re-export whose draft carries its gotchas forward.

    After [C], §9 and §9b, the documented §9c copy replaces the package's
    snippet with the staged draft, byte for byte, `[CARRIED]` marker included.
    """
    package = tmp_path / "skills" / "zod" / "1.4.0" / "zod"
    package.mkdir(parents=True)
    prior = "[zod v1.4.0]|root: .claude/skills/zod/\n|gotchas: z.string().email() is deprecated\n"
    (package / "context-snippet.md").write_bytes(prior.encode("utf-8"))
    stage = tmp_path / "stage"
    (stage / "drafts" / "zod").mkdir(parents=True)
    draft = prior.replace("|gotchas: ", "|gotchas: [CARRIED] ")
    (stage / "drafts" / "zod" / "context-snippet.md").write_bytes(draft.encode("utf-8"))
    command = SNIPPET_COPY.replace("{export_stage_dir}", stage.as_posix()).replace("{skill-name}", "zod") \
        .replace("{resolved_skill_package}", package.as_posix())
    proc = subprocess.run(["bash", "-c", command], capture_output=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert (package / "context-snippet.md").read_bytes() == draft.encode("utf-8")


# --------------------------------------------------------------------------
# #583 and determinism-2: the version and the test report come from helpers
# --------------------------------------------------------------------------


def test_load_skill_resolves_the_version_through_the_inventory_helper():
    load = _read(LOAD)
    step = _section(load, "### 2. Load and Validate Skill Artifacts", "**Validation (the export gate):**")
    resolve = ('uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill-name} '
               '--forge-data-folder "{forge_data_folder}"')
    assert [line for block in _fenced_blocks(step) for line in block] == [resolve]
    for binding in ("`{resolved_version}` ← `chosen_version`", "`{resolved_skill_package}` ← `skill_package`",
                    "`{forge_version}` ← `forge_version`",
                    "`{forge_evidence_report}` ← `paths.evidence_report.path`"):
        assert binding in step, binding
    assert "emit the helper's `detail` as an Info note" in step
    assert "`uv run {skillInventoryHelper} {skills_output_folder} --skill {skill-name}`" in step, (
        "the flat_skf ownership gate keeps its --skill call: resolve does not decide ownership")
    for stale in ("get {skill-name}", "read the `active` symlink target", "prefer the **symlink target**",
                  "Store the resolved path", "If neither", "step 3's Otherwise"):
        assert stale not in step, stale
    # Every rung opens with the `reason` values it handles, so `missing` never reads as "neither".
    for rung in ("1. `manifest-and-link`, `manifest` or `link`:", "2. `manifest-lags-link`",
                 "3. `flat-layout`: fall back to the flat path", "4. `missing`, `newest-on-disk`,"):
        assert rung in step, rung
    # On Activation resolves the helper, so no rung handles it missing.
    assert "no helper candidate" not in step and "`skf-skill-inventory.py` is missing" not in step


def test_the_test_report_comes_from_the_shared_helper_for_the_resolved_version():
    load = _read(LOAD)
    frontmatter = load.split("\n---\n", 1)[0]
    assert ("findTestReportProbeOrder:\n"
            "  - '{project-root}/_bmad/skf/shared/scripts/skf-find-test-report.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-find-test-report.py'") in frontmatter
    report = _section(load, "### 4b. Check Test Report (Quality Gate)", "### 5. ")
    assert [line for block in _fenced_blocks(report) for line in block] == [
        'uv run {findTestReportHelper} find --forge-data-folder "{forge_data_folder}" --skill-name {skill-name} '
        "[--version {resolved_version}]"]
    assert "never the manifest's `active_version`" in report
    # The lookup order is the helper's to state: its docstring, not a copy here.
    assert "The shared helper finds the newest finished test report of the version §2 chose." in report
    for stale in ("{active_version}", "{forge_version}", "Glob ", "sort -r", "Read frontmatter", "-latest.json"):
        assert stale not in report, stale
    for verdict in ("`pass`", "`fail`", "`pass-with-drift`", "`inconclusive`", '`status: "not-found"`'):
        assert verdict in report, verdict


def _link_active(group: Path, version: str) -> None:
    """Point `active` at a version: a symlink, or a junction on Windows without the privilege."""
    active = group / "active"
    try:
        active.symlink_to(version, target_is_directory=True)
    except OSError as e:
        if os.name != "nt":
            pytest.skip(f"symlinks are not available: {e}")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(active), str((group / version).resolve())],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            pytest.skip("neither a symlink nor a junction can be created")


def _package(skills: Path, name: str, version: str) -> None:
    package = skills / name / version / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    (package / "metadata.json").write_text(json.dumps({"name": name, "version": version,
                                                       "generated_by": "create-skill"}), encoding="utf-8")


def _test_report(forge: Path, name: str, version: str, run_id: str, result: str) -> None:
    folder = forge / name / version
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"test-report-{name}-{run_id}.md").write_text(
        f"---\nskillName: '{name}'\ntestResult: '{result}'\nscore: 70\n---\n# Test Report\n", encoding="utf-8")


def test_the_documented_calls_read_the_report_of_the_version_being_exported(tmp_path):
    """The SS->TS->EX case: the manifest names 1.0.0, `active` the just-forged 1.1.0, which failed its test."""
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    _package(skills, "zod", "1.0.0")
    _package(skills, "zod", "1.1.0")
    _link_active(skills / "zod", "1.1.0")
    (skills / ".export-manifest.json").write_text(json.dumps({"schema_version": "2", "exports": {"zod": {
        "active_version": "1.0.0",
        "versions": {"1.0.0": {"ides": ["claude-code"], "last_exported": "2026-09-01", "status": "active"}}}}}),
        encoding="utf-8")
    _test_report(forge, "zod", "1.0.0", "20260901T100000Z-aa", "pass")
    _test_report(forge, "zod", "1.1.0", "20260930T100000Z-bb", "fail")
    _test_report(forge, "zod", "1.1.0", "20260930T120000Z-cc", "")  # a run that stopped before its verdict
    (forge / "zod" / "1.1.0" / "evidence-report.md").write_text("# Evidence\n", encoding="utf-8")
    load = _read(LOAD)
    values = {"skillInventoryHelper": INVENTORY.as_posix(), "findTestReportHelper": FIND_REPORT.as_posix(),
              "skills_output_folder": skills.as_posix(), "skill-name": "zod",
              "forge_data_folder": forge.as_posix()}
    step = _section(load, "### 2. Load and Validate Skill Artifacts", "**Validation (the export gate):**")
    [[resolve_call]] = _fenced_blocks(step)
    proc = _run(_argv(resolve_call, values))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    resolved = json.loads(proc.stdout)["resolve"]
    assert (resolved["reason"], resolved["chosen_version"]) == ("manifest-lags-link", "1.1.0")
    assert "the manifest names 1.0.0" in resolved["detail"]
    # Each binding §2 documents reads a field the helper returns.
    bound = {}
    for name, field in re.findall(r"`\{(\w+)\}` ← `([\w.]+)`", step):
        value = resolved
        for key in field.split("."):
            value = value[key]
        bound[name] = value
    assert set(bound) == {"resolved_version", "resolved_skill_package", "forge_version", "forge_evidence_report",
                          "forge_provenance_map"}
    assert bound["forge_provenance_map"] is None, "no provenance map on disk: the api line keeps the prior `()`"
    assert bound["resolved_version"] == "1.1.0"
    assert Path(bound["resolved_skill_package"]).parts[-3:] == ("zod", "1.1.0", "zod")
    assert Path(bound["forge_evidence_report"]).parts[-3:] == ("zod", "1.1.0", "evidence-report.md")
    values["resolved_version"] = resolved["chosen_version"]
    [[find_call]] = _fenced_blocks(_section(load, "### 4b. Check Test Report (Quality Gate)", "### 5. "))
    proc = _run(_argv(find_call, values, keep=("--version",)))
    assert proc.returncode == 0, proc.stderr
    found = json.loads(proc.stdout)
    assert (found["status"], found["source"], found["testResult"]) == ("found", "versioned-glob", "fail")
    assert Path(found["path"]).name == "test-report-zod-20260930T100000Z-bb.md"
    assert [Path(s["path"]).name for s in found["skipped"]] == ["test-report-zod-20260930T120000Z-cc.md"]


# --------------------------------------------------------------------------
# leanness-3: one gotchas resolution for both skill types
# --------------------------------------------------------------------------

# #1164: the two documented calls of the rebuild helper's `gotchas` action.
PRIOR_CALL = ('python3 {rebuildManagedSectionsHelper} gotchas prior "{resolved_skill_package}/context-snippet.md" '
              '--skills-folder "{skills_output_folder}" --skill {skill-name}')
RESOLVE_CALL = ('python3 {rebuildManagedSectionsHelper} gotchas resolve "{resolved_skill_package}/context-snippet.md" '
                '--skills-folder "{skills_output_folder}" --skill {skill-name} '
                '--judgments "{export_stage_dir}/gotchas/{skill-name}.json"')
FILL_GOTCHAS = "`gotchas` from `{gotchas_line}` (omit the line when it is null)"


def test_both_skill_types_use_one_gotchas_resolution():
    text = _read(SNIPPET)
    generate = _section(text, "### 3. Generate Snippet Content", "### 4. Verify Token Count")
    shared = _section(generate, "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    single = _section(generate, "#### 3b. Single Skills", "#### 3c. ")
    stack = _section(generate, "#### 3c. Stack Skills", None)
    assert "{manifestOpsHelper}" not in text and " get {skill-name}" not in text, "#1164: the helper reads the manifest"
    assert "the evidence report at `{forge_evidence_report}`" in shared, "the report step 1 §2 bound, never a guess"
    assert [RESOLVE_CALL] in _fenced_blocks(shared)
    assert "- **If " not in shared and "decision tree" not in text and "first-export branch" not in text
    assert "is_first_export" not in single and "is_first_export" not in stack
    assert FILL_GOTCHAS in _line(single, "Emit the single-skill template") and FILL_GOTCHAS in stack
    assert "Same one-cycle expiry logic" not in text and "See the single-skill steps" not in text


# --------------------------------------------------------------------------
# #810, #811, #818: the snippet's gotchas sources, api ranking and anchors
# --------------------------------------------------------------------------

SNIPPET_FORMAT = "assets/snippet-format.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
# #1093: §3b item 2's `()` sentences and the snippet format's pointer, which
# the api ranking pin and `_api_marks` (below) follow.
PRIOR_MARK_CLAUSE = ("Write each `prior_api` name as the prior `|api:` line wrote it, with `()` or bare, whatever "
                     "its `export_type`")
NEW_NAME_CLAUSE = ("A name new to the line (one `prior_api` does not hold, every name when there is no prior "
                   "snippet) takes `()` when its `export_type` in the provenance map at `{forge_provenance_map}` is "
                   "a function, and is written bare for any other kind, or when that map is null or gives no kind "
                   "for the name.")
# The rule the snippet format's api line rule held before #1164 moved every rule to generate-snippet.md.
FORMAT_MARK_CLAUSE = "Step 2's single-skill api ranking alone sets which names take `()`."
# #1164: what the snippet format keeps, and the rule bullets it no longer has.
FORMAT_HEADINGS = ["# Context Snippet Format (Vercel-Aligned Indexed Format)", "## Single Skill Snippet Template",
                   "## Stack Skill Snippet Template"]
FORMAT_RULE_STARTS = ("- **gotchas line**", "- **api line**", "- **key-types line**", "- **stack line**",
                      "- **integrations line**", "- Section anchors must be verified", "- **Line ")
GOTCHAS_PLACEHOLDER = "|gotchas: {at most 3 pitfalls, separated by `; `}"


def _generate() -> str:
    return _section(_read(SNIPPET), "### 3. Generate Snippet Content", "### 4. Verify Token Count")


def _line(text: str, start: str) -> str:
    """The one line of `text` that starts with `start`."""
    [line] = [line for line in text.split("\n") if line.startswith(start)]
    return line


def _in_order(text: str, *parts: str) -> bool:
    return all(part in text for part in parts) and [text.index(p) for p in parts] == sorted(text.index(p) for p in parts)


def _regeneration() -> str:
    return _section(UPDATE_WRITE.read_text(encoding="utf-8"), "### 5. Regenerate context-snippet.md", "### 6. ")


def _sources(shared: str) -> str:
    """§3a's three sources and the sentences that close them, before the judgments file."""
    return _section(shared, "A gotcha is **derived** when a current source states it:", "Write your judgments to ")


def test_the_snippet_format_holds_only_its_templates():
    """#1164 (leanness-1): the asset keeps its title, the parse-critical note and the two templates; the gotchas,
    api, anchor and token rules live in generate-snippet.md alone, which the asset no longer restates."""
    fmt = _read(SNIPPET_FORMAT)
    assert [line for line in fmt.split("\n") if line.startswith("#")] == FORMAT_HEADINGS
    blocks = _fenced_blocks(fmt)
    assert len(blocks) == 2
    prose = [line for line in fmt.split("\n") if line and not line.startswith("#")
             and not any(line in block for block in blocks) and not line.startswith("```")]
    assert len(prose) == 1 and prose[0].startswith("**A house-style copy** of this file"), prose
    assert fmt.index("**A house-style copy**") < fmt.index("## Single Skill Snippet Template")
    for start in FORMAT_RULE_STARTS:
        assert not any(line.startswith(start) for line in fmt.split("\n")), start
    for gone in ("## Skill Root Path", "## Format Rules", "## Rules", "80-120", "300 tokens", "up from ~50-80",
                 "brief default", "Top exports"):
        assert gone not in fmt, gone
    for block in blocks:
        assert block[-1] == GOTCHAS_PLACEHOLDER
    note = prose[0]
    assert _in_order(note, "line 1 with its `root:` field", "line 2's `|IMPORTANT:` start and skill name",
                     "the `|api:` label", "the `|gotchas:` label with its `; ` separator and its `[CARRIED]` marker",
                     "the rebuild helper's `gotchas` action", "no bare `|` line")


def test_a_gotcha_the_current_skill_md_states_is_derived_not_carried():
    """#810: a deprecation SKILL.md states and the evidence report lacks is kept without `[CARRIED]`."""
    text = _read(SNIPPET)
    shared = _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    sources = _sources(shared)
    assert "a T2-future annotation in the evidence report at `{forge_evidence_report}`, when step 1 §2 bound" in sources
    skill_md = _line(sources, "2. **The current SKILL.md**")
    assert "a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or " \
           "import corrections" in skill_md
    assert "a `## Key API Summary` row whose purpose says deprecated or removed" in skill_md
    assert "an async requirement its Quick Start shows (an API it calls with `await`)" in skill_md
    assert "Key API Summary` rows give" not in text, "the summary table has no kind column"
    assert "kept in its prior wording without the `[CARRIED]` marker" in \
        _line(sources, "3. **A prior pitfall still stated:**")
    assert "`[CARRIED]` applies only to a prior pitfall no current source backs." in sources
    assert "cannot be derived from the current evidence report" not in text
    drop = _line(shared, "- **When `dropped` is not empty**")
    assert "no longer appear in the current SKILL.md or evidence report" in drop
    assert "re-forge the skill with update-skill" in drop and "the evidence report's T2-future section" in drop
    assert "- **gotchas line**" not in _read(SNIPPET_FORMAT), "#1164: the rule lives in §3a alone"
    five = _regeneration()
    assert "new gotchas" not in five and "derive the gotchas as its §3a states" in five
    assert "this run's evidence report (`{forge_version}/evidence-report.md`) and the provenance map §3 wrote" in five


def test_the_gotchas_line_has_one_selection():
    """#810, #1164 (leanness-8): §2.5 is the `prior` call and one binding sentence that names the already-carried
    flag and the null cases; §3a hands its judgments to `resolve`, which applies the slot order, the marker and
    the separator, and shows each warning its result calls for."""
    text = _read(SNIPPET)
    prior = _section(text, "### 2.5. Check Existing Snippet", "### 2.7. ")
    assert [PRIOR_CALL] in _fenced_blocks(prior)
    binding = _line(prior, "Bind `prior_gotchas` ← its `prior_gotchas`")
    assert _in_order(binding, "`{text, already_carried, read_whole}`", "`already_carried` when the line marked it "
                     "`[CARRIED]`", "null for no prior snippet, no `|gotchas:` line or an empty one",
                     "`prior_api` ← its `prior_api`", "`{name, parens}`", "`is_first_export` ← its `is_first_export`")
    assert not re.search(r"^\d\. ", prior, re.M), "one call, not six numbered steps"
    for gone in ("prior_gotchas_content", "prior_gotchas_already_carried", "hard one-cycle expiry",
                 "Distinguish empty from absent", "split `prior_gotchas_content`"):
        assert gone not in text, gone
    shared = _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    assert "The line holds at most 3 pitfalls" not in shared and "{pitfall-1}" not in shared
    applies = _line(shared, "The helper reads `prior_gotchas` and `is_first_export` again")
    assert _in_order(applies, "the slot order", "the `[CARRIED]` marker with its one-cycle expiry",
                     "the `; ` separator", "on a first export it writes an unbacked prior pitfall unmarked",
                     "since the workflow that built or updated the skill",
                     "Bind `{gotchas_line}` ← its `line` (null when it writes no pitfall)")
    carry = _line(shared, "- **When `carried` is not empty**")
    assert "Gotchas preserved from prior export" in carry
    drop = _line(shared, "- **When `dropped` is not empty**")
    assert "(`already-carried`: it was already carried forward once; `no-slot`: the line's 3 slots went to " \
           "current gotchas)" in drop
    fmt = _read(SNIPPET_FORMAT)
    assert fmt.count(GOTCHAS_PLACEHOLDER) == 2 and "- **Line 6 (gotchas):**" not in fmt
    trigger = _line(_regeneration(), "- **Gotchas changed**")
    assert "(at most 3 pitfalls, in its order) differs from the prior snippet's `|gotchas:` line, " \
           "`[CARRIED]` markers aside" in trigger


def test_the_api_line_has_one_ranking():
    """#811: the prior `|api:` names, then the `## Key API Summary` rows, then metadata.json `exports`."""
    text = _read(SNIPPET)
    prior = _section(text, "### 2.5. Check Existing Snippet", "### 2.7. ")
    assert "`prior_api` ← its `prior_api` (each name, in line order, as `{name, parens}`: `parens` when the line " \
           "wrote it with `()`; `[]` with no `|api:` line)" in prior
    rank = _line(_section(_generate(), "#### 3b. Single Skills", "#### 3c. "), "2. ")
    assert _in_order(rank, "the prior snippet's `|api:` line", "SKILL.md's `## Key API Summary` table, in row order",
                     "the metadata.json `exports`, in order")
    assert "the Key Components of its `## Component Catalog` rows" in rank
    assert "the surfaces of its `## Pattern Surface` rows" in rank
    for normalized in ("without backticks, `()`, a module qualifier (`cognee.add` is `add`) or generic parameters "
                       "(`Meta<T = Args>` is `Meta`)", "split a cell that names several on `/`"):
        assert normalized in rank
    assert "Take each name once, only when metadata.json `exports` lists it" in rank
    assert "never one the current SKILL.md marks deprecated or removed: a bullet of a section whose heading names " \
           "deprecations, migration or breaking changes gives it as the deprecated, removed or renamed name (not as " \
           "its replacement), or its `## Key API Summary` row's purpose says deprecated or removed" in rank
    assert "the first 10 for the Deep tier, 5 for the other tiers" in rank
    assert _in_order(rank, "the first 10 for the Deep tier", PRIOR_MARK_CLAUSE, NEW_NAME_CLAUSE)
    assert "when that map is null or gives no kind for the name, keep the `()` the prior `|api:` line gave it" \
        not in rank and "Append `()` to a name whose" not in rank, "#1093: a kind never overrules the prior line"
    assert "Key API Summary kind" not in text and "{forge_version}/provenance-map.json" not in text
    assert "`{forge_provenance_map}` ← `paths.provenance_map.path`" in _read(LOAD)
    trim = _line(_section(text, "### 4. Verify Token Count", "### 5. "), "- If `{count}` is above 300")
    assert "drop api names from the end of the §3b ranking, one at a time" in trim
    assert "Select top exports" not in text
    fmt = _read(SNIPPET_FORMAT)
    assert "Top exports from metadata.json" not in fmt
    assert "- **api line**" not in fmt and FORMAT_MARK_CLAUSE not in fmt, "#1164: the ranking lives in §3b item 2 alone"
    five = _regeneration()
    assert "top exports" not in five and "top-K" not in five
    assert "Rank the api names and verify the section anchors as " \
           "`skf-export-skill/references/generate-snippet.md` §3b states" in five
    assert "`skf-create-skill/assets/skill-sections.md` gives only its line format (pipe-delimited indexed format), " \
           "not the `()` its `|api:` placeholder gives functions: §3b item 2 sets each api name's `()`." in five, \
        "#1093: Update Skill takes no `()` rule from create-skill's first-snippet placeholder"
    exports = _line(five, "- **Headline exports changed**")
    assert "In gap-driven mode it fires only when a name of the prior line left `exports` or SKILL.md now marks it " \
           "deprecated or removed: a line that differs by the ranking alone" in exports


def test_an_anchor_skill_md_holds_stays_on_skill_md():
    """#818: only a heading SKILL.md lacks moves to `references/`, and only for a split-body skill."""
    anchor = _line(_section(_generate(), "#### 3b. Single Skills", "#### 3c. "), "4. ")
    assert _in_order(anchor, "when SKILL.md has the heading, keep `SKILL.md#{slug}`",
                     "Only when SKILL.md lacks the heading and the skill is split-body",
                     "point the anchor at the `references/{file}.md#{slug}` that holds the heading",
                     "When neither holds it, omit that anchor line")
    assert "rewrite the anchor to point to the reference file path" not in anchor
    assert "- Section anchors must be verified" not in _read(SNIPPET_FORMAT), "#1164: the rule lives in §3b item 4"
    # update-skill regenerates a snippet whose anchors §3b item 4 would place elsewhere.
    trigger = _line(_regeneration(), "- **Anchors changed**")
    assert "differs from the one `generate-snippet.md` §3b item 4 gives for the merged SKILL.md" in trigger
    assert "Record it as `anchors` in `Triggers fired`." in trigger


# --------------------------------------------------------------------------
# #1091: `; ` is reserved for the gotchas separator
# --------------------------------------------------------------------------

# The rule §2.5 step 3, §3a and the snippet format stated before #1164 moved the split and the escaping into
# the rebuild helper's `gotchas` action. test-skf-rebuild-managed-sections.py runs the issue's lines through it.
SEPARATOR_CLAUSE = ("A `; ` is a separator only when an even number of backticks precede it (it is outside a code "
                    "span) and every `(` before it outside a code span is closed before it (a `)` outside a code "
                    "span closes the last `(` still open, and one with no `(` open closes nothing); any other `; ` "
                    "stays inside its pitfall.")
WHOLE_VALUE_CLAUSE = ("A split that gives more than 3 pieces comes from a line §3a never writes, such as an older or "
                      "hand-written one: the whole value is then one pitfall, already carried when it starts with "
                      "`[CARRIED]`.")
WHOLE_VALUE_UNBACKED_CLAUSE = ("§3a counts such a value as unbacked, even when the current SKILL.md states each of "
                               "its pitfalls, unless one T2-future annotation, or one bullet, row or Quick Start "
                               "call of §3a's source 2, states it whole")
WRITE_CLAUSE = "A pitfall never holds the separator: in every pitfall the line writes"
GONE_GOTCHAS_RULES = (SEPARATOR_CLAUSE, WHOLE_VALUE_CLAUSE, WHOLE_VALUE_UNBACKED_CLAUSE, WRITE_CLAUSE,
                      "write a `; ` outside a code span as `, `", "is written as `, ` (a code span keeps its `; `)",
                      "split `prior_gotchas_content`", "The line holds at most 3 pitfalls",
                      "{skills_output_folder} get {skill-name}")


def _gotchas_step_files() -> list[Path]:
    """Every file of export-skill, and update-skill's write.md, which runs the same two calls."""
    return sorted(EXPORT.rglob("*.md")) + [EXPORT / "customize.toml", UPDATE_WRITE]


def test_a_pitfall_never_holds_the_gotchas_separator():
    """#1091, #1164 (determinism-4): the split and the escaping belong to the helper, so no step file states the
    separator clause, the whole-value clause or the write clause, and §3a hands the line to `resolve`."""
    for path in _gotchas_step_files():
        text = path.read_text(encoding="utf-8")
        for clause in GONE_GOTCHAS_RULES:
            assert clause not in text, (path.relative_to(REPO).as_posix(), clause[:60])
    shared = _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    assert [RESOLVE_CALL] in _fenced_blocks(shared)
    assert "reads the line back as the same pitfalls" not in shared, \
        "an unclosed `(` or an odd backtick count still joins a pitfall with the ones after it"
    # The helper's split keeps a `; ` inside parentheses or a code span, and reads more than 3 pieces as one.
    assert [p["text"] for p in rms.read_gotchas("x (a; b); y; `f(); g()`")] == ["x (a; b)", "y", "`f(); g()`"]
    assert rms.write_gotchas([("x (a; b)", False), ("`f(); g()`", True)]) == "x (a, b); [CARRIED] `f(); g()`"


# oh-my-skills a02403f, skills/oms-uitripled/0.1.0/oms-uitripled/context-snippet.md
# line 6, its em dash written as a colon: the line that split into four pieces.
UITRIPLED_A02403F = (
    'Copy-paste distribution: NEVER barrel-import from @uitripled/react-shadcn (src/index.ts empty by design); '
    'render entries from client components (170 of the 171 files start with `"use client"`; every entry declares '
    'framer-motion); React 19 / Next.js 16 peer deps are required.'
)
# --------------------------------------------------------------------------
# #1092: a prior pitfall the current SKILL.md still says anywhere stays derived
# --------------------------------------------------------------------------

# §3a source 3, sentence by sentence.
PRIOR_STATED_CLAUSE = ("3. **A prior pitfall still stated:** a pitfall of `prior_gotchas` (§2.5), already carried "
                       "or not, that source 1 states or that the current SKILL.md still says anywhere (its "
                       "frontmatter `description` and its whole body, not only source 2's places), kept in its "
                       "prior wording without the `[CARRIED]` marker.")
MAIN_CLAIM_CLAUSE = ("SKILL.md still says a pitfall when it states the pitfall's main claim (what to do or avoid, "
                     "with any version or name the pitfall gives) in SKILL.md's own words: a detail the pitfall "
                     "adds need not appear, and a pitfall whose main claim SKILL.md no longer states, or now "
                     "contradicts with another version or name in any place (even while another place still "
                     "states it), stays unbacked.")
NEW_GOTCHAS_CLAUSE = ("New gotchas come only from source 1 and source 2's places: a pitfall SKILL.md states only "
                      "elsewhere is kept when the prior line holds it, never added as a new one.")
ONE_PITFALL_CLAUSE = ("SKILL.md prose outside source 2's places backs only a prior pitfall that is one pitfall (a "
                      "parenthesis that adds detail to it does not make it several): one that joins several pitfalls "
                      "that each warn on their own is still stated only when one T2-future annotation, or one "
                      "bullet, row or Quick Start call of source 2, states it whole, every pitfall it joins "
                      "included, so it stays unbacked when SKILL.md states its pitfalls only apart or only in other "
                      "prose, such as a pitfall `gotchas prior` marks `read_whole`, the one pitfall it reads back "
                      "as once §3a has written it (its `; ` written as `, `), or an older export's line that "
                      "joined its pitfalls with `, `.")
WRITTEN_ONCE_CLAUSE = ("A prior pitfall that source 1 or source 2 states, one that joins several included, is "
                       "written once, as that prior pitfall in its prior wording, never also as a new gotcha.")
# §3a's warnings, each shown when the `resolve` result it names is not empty.
NO_SLOT_WARNING = ("- **When `left_off` is not empty**, emit warning: \"**New gotchas left off the line:** {each one, "
                   "with where it is stated: the evidence report's T2-future section, or the SKILL.md section, "
                   "`## Key API Summary` row or Quick Start call}. The line's 3 slots went first to the prior "
                   "pitfalls a T2-future annotation or the current SKILL.md still states, in their prior order, "
                   "then to new gotchas in source order.")
NO_SLOT_REMEDY = ("to give a left-off gotcha a slot, remove from the `|gotchas:` line of "
                  "`{resolved_skill_package}/context-snippet.md` a prior pitfall that SKILL.md states only in other "
                  "prose, then re-run export. A pitfall a T2-future annotation or one of those SKILL.md places "
                  "states comes back as a new gotcha, in source order, so removing it frees a slot only for a "
                  "left-off gotcha stated before it.\"")
CARRY_PROMISE = ("They will be DROPPED on the next export unless a T2-future annotation in the evidence report "
                 "states them, or the current SKILL.md states them and no place in it contradicts them with another "
                 "version or name, except one that joins several pitfalls, such as a whole older "
                 "line, which is dropped unless one T2-future annotation, one bullet of a section whose heading "
                 "names gotchas, deprecations, migration, breaking changes or import corrections, one "
                 "`## Key API Summary` row whose purpose says deprecated or removed, or one Quick Start `await` "
                 "call states it whole.")
DROP_REASONS = ("\"**Stale gotchas dropped:** {each pitfall, with why it was dropped: it was already carried "
                "forward once, or the line's 3 slots went to current gotchas, and, for one that joins several "
                "pitfalls, that no single place states it whole}. The pitfalls that do not join several no longer "
                "appear in the current SKILL.md or evidence report, or a place in SKILL.md now contradicts them "
                "with another version or name.")
DROP_COMES_BACK = ("A dropped pitfall comes back only as a new gotcha: if one is still relevant, re-forge the skill "
                   "with update-skill so its SKILL.md states it in a bullet of a section whose heading names "
                   "gotchas, deprecations, migration, breaking changes or import corrections, in a "
                   "`## Key API Summary` row whose purpose says deprecated or removed, or as an async requirement "
                   "its Quick Start shows (other SKILL.md prose that says it does not add it back), or add it to "
                   "the evidence report's T2-future section, then re-run export.")
DROP_JOINED_ADVICE = ("For one that joins several pitfalls, state it whole in one such place, or each of its "
                      "pitfalls in its own.\"")
# The snippet format's gotchas rule before #1164, which left the rule in §3a alone.
FORMAT_PRIOR_STATED_CLAUSE = ("and a prior pitfall, already carried or not, that a T2-future annotation states or "
                              "that the current SKILL.md still says anywhere (its frontmatter description and its "
                              "whole body), kept in its prior wording without the `[CARRIED]` marker.")
FORMAT_MAIN_CLAIM_CLAUSE = ("SKILL.md says a pitfall when it states the pitfall's main claim (what to do or avoid, "
                            "with any version or name the pitfall gives) in SKILL.md's own words and no place in it "
                            "contradicts that claim with another version or name.")
FORMAT_NEW_GOTCHAS_CLAUSE = ("New gotchas come only from the evidence report's T2-future annotations and those "
                             "SKILL.md places: a gotchas-type section's bullets, a deprecated or removed "
                             "`## Key API Summary` row and an async requirement the Quick Start shows.")
FORMAT_JOINED_CLAUSE = ("A pitfall that joins several pitfalls, such as a value step 2 reads whole, is still stated "
                        "only when one T2-future annotation or one of those bullets, rows or Quick Start calls "
                        "states it whole, not when SKILL.md states its pitfalls only apart or only in other prose, "
                        "and a prior pitfall one of those states is written once, never also as a new gotcha.")

# The SKILL.md places source 2 reads. Source 3 reads every place, these included.
SOURCE_2_PLACES = {"gotchas bullet", "deprecated Key API Summary row", "Quick Start await"}


def _resolve_gotchas(prior_value: str, skill_md: list[tuple[str, str]], is_first_export: bool,
                     report: tuple[str, ...] = (), several: tuple[str, ...] = ()
                     ) -> tuple[str, list[str], list[str], list[str]]:
    """The `|gotchas:` value §3a writes, then the pitfalls its carry, drop and no-slot warnings name.

    This models §3a's judgments, as the judgments file states them, and hands them to the rebuild helper's
    `resolve_gotchas`, which places them as the `resolve` call does. `skill_md` lists (place, pitfall) in
    SKILL.md order, one entry per place, a pitfall standing for the one whose main claim that place states,
    whole, in SKILL.md's own words (source 3 checks meaning, not text, so a test names the pitfall meant); a
    place that states only part of a joined pitfall names that part. `report` holds source 1's T2-future
    annotations, one entry per annotation. `several` names the prior pitfalls that join several pitfalls, a
    judgment of meaning too; a pitfall `gotchas prior` marks `read_whole` is one without being named."""
    prior = rms.read_gotchas(prior_value) if prior_value else []
    backed, new = _judgments(prior, skill_md, report, several)
    placed = rms.resolve_gotchas(prior or None, backed, new, is_first_export)
    return (placed["line"] or "", placed["carried"], [dropped["text"] for dropped in placed["dropped"]],
            placed["left_off"])


def _judgments(prior: list[dict], skill_md: list[tuple[str, str]], report: tuple[str, ...] = (),
               several: tuple[str, ...] = ()) -> tuple[list[bool], list[str]]:
    """§3a's judgments file for `prior` (the `prior_gotchas` entries): `backed` and `new_gotchas`."""
    joined = set(several) | {pitfall["text"] for pitfall in prior if pitfall["read_whole"]}
    said = set(report) | {pitfall for _, pitfall in skill_md}
    sourced = list(report) + [pitfall for place, pitfall in skill_md if place in SOURCE_2_PLACES]
    prior_texts = [pitfall["text"] for pitfall in prior]
    # Prose backs a prior pitfall that is one pitfall; one that joins several needs one annotation or one
    # source-2 place stating it whole. Either way a prior pitfall a source states is never also new.
    backed = [text in (sourced if text in joined else said) for text in prior_texts]
    return backed, [text for text in sourced if text not in prior_texts]


# oh-my-skills a02403f, skills/oms-uitripled/0.1.0/oms-uitripled/SKILL.md, which has no gotchas-type section,
# so source 2 gives none. The sentences that state each prior pitfall's main claim, in SKILL.md's own words:
# - REACT_19, its description: "Installs React 19 and Next.js 16 UI components", and its Overview: "All
#   components are built with React 19, Next.js 16, TypeScript, Tailwind CSS 4, and Framer Motion." ("peer
#   deps" is a detail the pitfall adds.)
# - BARREL, its description: "do NOT generate barrel imports from the react-shadcn package", and its Overview:
#   "it is not an installable npm package for direct imports".
# - USE_CLIENT, its Quick Start prose: "Render the copied components from client code: 170 of the 171 shadcn
#   entries ship a file that starts with `"use client"`".
BARREL, USE_CLIENT, REACT_19 = (pitfall["text"] for pitfall in rms.read_gotchas(UITRIPLED_A02403F))
UITRIPLED_A02403F_SKILL_MD = [("description", REACT_19), ("description", BARREL), ("Overview", BARREL),
                              ("Overview", REACT_19), ("Quick Start prose", USE_CLIENT)]
# The same SKILL.md with React 20 and Next.js 17 in place of React 19 and Next.js 16: another version.
REACT_20 = "React 20 / Next.js 17 peer deps are required."
UITRIPLED_REACT_20_SKILL_MD = [(place, REACT_20 if pitfall == REACT_19 else pitfall)
                               for place, pitfall in UITRIPLED_A02403F_SKILL_MD]
# oh-my-skills b732108, skills/oms-cognee/1.6.2/oms-cognee/SKILL.md:230, a `## Deprecations & Gotchas` bullet
# whose lead joins two warnings that each stand on their own: a pitfall that joins several, stated whole.
START_UI = "`cognee.start_ui` is sync (not async) and requires a `pid_callback` positional argument"


def test_a_prior_pitfall_the_current_skill_md_still_says_anywhere_is_derived():
    """#1092: source 3 keeps a prior pitfall, carried or not, that source 1 states or whose main claim the
    current SKILL.md still states anywhere; new gotchas come only from source 1 and source 2's places, and one
    left without a slot is named with the way to free a slot; a pitfall that joins several needs one
    annotation or one source-2 place stating it whole, and a prior pitfall a source states is written once.
    The judgments file and the carry and drop warnings say the same; the snippet format no longer restates it."""
    text, fmt = _read(SNIPPET), _read(SNIPPET_FORMAT)
    shared = _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    three = _line(_sources(shared), "3. **A prior pitfall still stated:**")
    assert _in_order(three, PRIOR_STATED_CLAUSE, MAIN_CLAIM_CLAUSE, NEW_GOTCHAS_CLAUSE, ONE_PITFALL_CLAUSE,
                     WRITTEN_ONCE_CLAUSE)
    assert "in its own wording" not in three, "SKILL.md's own words: a check of meaning, never of text"
    for clause in (FORMAT_PRIOR_STATED_CLAUSE, FORMAT_MAIN_CLAIM_CLAUSE, FORMAT_NEW_GOTCHAS_CLAUSE,
                   FORMAT_JOINED_CLAUSE):
        assert clause not in fmt, "#1164: the gotchas rule lives in §3a alone"
    for gone in ("source 1 or 2 still states", "either of them still states", "dropped either way",
                 "Source 3 backs only a prior pitfall that is one pitfall", "only a pitfall that is one pitfall counts",
                 "a value §2.5 reads whole"):
        assert gone not in text and gone not in fmt
    judgments = _line(shared, "Write your judgments to ")
    assert _in_order(judgments, "`{export_stage_dir}/gotchas/{skill-name}.json` with your file-write tool",
                     "`backed` holds one `true` or `false` per `prior_gotchas` entry, in its order",
                     "(`[]` when `prior_gotchas` is null)", "true when source 3 keeps that pitfall and false when no "
                     "current source backs it", "`new_gotchas` holds the other gotchas source 1 and source 2's places "
                     "state, in source order")
    assert _in_order(_line(shared, "- **When `left_off` is not empty**"), NO_SLOT_WARNING, NO_SLOT_REMEDY)
    carry = _line(shared, "- **When `carried` is not empty**")
    assert CARRY_PROMISE in carry and "unless the current SKILL.md or evidence report states them" not in carry
    drop = _line(shared, "- **When `dropped` is not empty**")
    assert _in_order(drop, DROP_REASONS, DROP_COMES_BACK, DROP_JOINED_ADVICE)
    assert "re-forge the skill with update-skill so its SKILL.md states it, or" not in drop
    # The user docs no longer say the current export needs a gotchas-type section to keep a prior pitfall.
    page = (REPO / "docs" / "verifying-a-skill.md").read_text(encoding="utf-8")
    assert "which Skill Forge 10.0.0's export needed to keep the snippet's pitfalls" in page
    assert "export needs to keep the snippet's pitfalls" not in page


@pytest.mark.parametrize("prior_value, skill_md, report, is_first_export, several, expected", [
    pytest.param(UITRIPLED_A02403F, UITRIPLED_A02403F_SKILL_MD, (), False, (),
                 (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False), (REACT_19, False)]), [], [], []),
                 id="issue-1092-uitripled"),
    pytest.param(UITRIPLED_A02403F, UITRIPLED_REACT_20_SKILL_MD, (), False, (),
                 (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False), (REACT_19, True)]), [REACT_19], [], []),
                 id="another-version-is-unbacked"),
    pytest.param("[CARRIED] a; [CARRIED] b; c", [("Overview", "a")], (), False, (),
                 ("a; [CARRIED] c", ["c"], ["b"], []), id="carried-still-said"),
    pytest.param("[CARRIED] a; b", [], ("a",), False, (), ("a; [CARRIED] b", ["b"], [], []),
                 id="carried-only-the-report-states"),
    pytest.param("a; b", [("description", "z"), ("Overview", "b"), ("gotchas bullet", "n")], (), False, (),
                 ("b; n; [CARRIED] a", ["a"], [], []), id="prose-never-adds"),
    pytest.param("a; b", [("gotchas bullet", "a"), ("gotchas bullet", "n")], (), False, (),
                 ("a; n; [CARRIED] b", ["b"], [], []), id="a-source-2-place-states-a-prior-one"),
    pytest.param("", UITRIPLED_A02403F_SKILL_MD, (), False, (), ("", [], [], []),
                 id="issue-1092-uitripled-no-prior-line"),
    pytest.param("a; b", [("Overview", "b")], ("r", "a"), False, (), ("a; b; r", [], [], []),
                 id="report-states-and-adds"),
    pytest.param("a; [CARRIED] b; c", [("Overview", "a")], (), True, (), ("a; b; c", [], [], []), id="first-export"),
    pytest.param("a; b; c", [("Overview", "a"), ("Overview", "b"), ("Overview", "c"), ("gotchas bullet", "n")], (),
                 False, (), ("a; b; c", [], [], ["n"]), id="no-slot-for-a-new-gotcha"),
    pytest.param("a; b", [("Overview", "a"), ("Overview", "b"), ("gotchas bullet", "n"), ("Quick Start await", "m")],
                 ("r",), False, (), ("a; b; r", [], [], ["n", "m"]), id="more-than-3-derived"),
    pytest.param(START_UI, [("gotchas bullet", START_UI)], (), False, (START_UI,),
                 (rms.write_gotchas([(START_UI, False)]), [], [], []), id="a-gotchas-bullet-states-a-joined-one-whole"),
    pytest.param(START_UI, [], (START_UI,), False, (START_UI,), (rms.write_gotchas([(START_UI, False)]), [], [], []),
                 id="an-annotation-states-a-joined-one-whole"),
    pytest.param("a, b", [("Overview", "a"), ("description", "b")], (), False, ("a, b",),
                 ("[CARRIED] a, b", ["a, b"], [], []), id="prose-states-a-joined-ones-parts-apart"),
])
def test_a_prior_pitfall_skill_md_still_says_is_kept_unmarked(prior_value, skill_md, report, is_first_export,
                                                               several, expected):
    """#1092: re-exports and a first export, through §3a as written."""
    text = _read(SNIPPET)
    for clause in (PRIOR_STATED_CLAUSE, MAIN_CLAIM_CLAUSE, NEW_GOTCHAS_CLAUSE, ONE_PITFALL_CLAUSE,
                   WRITTEN_ONCE_CLAUSE, NO_SLOT_WARNING):
        assert clause in text
    assert _resolve_gotchas(prior_value, skill_md, is_first_export, report, several) == expected


def test_a_prior_pitfall_skill_md_no_longer_says_is_carried_once_then_dropped():
    """#1092: reading SKILL.md whole changes nothing for a pitfall it says nowhere."""
    assert PRIOR_STATED_CLAUSE in _read(SNIPPET)
    first = _resolve_gotchas("a; b", [("Overview", "a")], is_first_export=False)
    assert first == ("a; [CARRIED] b", ["b"], [], [])
    assert _resolve_gotchas(first[0], [("Overview", "a")], is_first_export=False) == ("a", [], ["b"], [])


def test_a_prior_value_that_joins_several_pitfalls_is_carried_once_then_dropped():
    """#1092: a value `gotchas prior` reads whole, then the one pitfall it reads back as once written, stays unbacked
    although SKILL.md states each of its pitfalls, so it gets one `[CARRIED]` cycle and is dropped; only its
    pitfall source 2 states comes back, as a new gotcha. An older `, `-joined line whose pitfalls SKILL.md
    states only in prose, or only apart, rides the same one cycle."""
    text = _read(SNIPPET)
    assert ONE_PITFALL_CLAUSE in text and CARRY_PROMISE in text
    whole = "a; b; c; d"
    assert rms.read_gotchas(whole) == [{"text": whole, "already_carried": False, "read_whole": True}]
    joined = rms.write_gotchas([(whole, False)])
    assert rms.split_gotchas(whole) == ["a", "b", "c", "d"] and rms.read_gotchas(joined) == [
        {"text": joined, "already_carried": False, "read_whole": False}], \
        "once written, the value is one piece the more-than-3 test no longer catches"
    # The Overview states each of a, b, c and d, so a check of meaning alone would find the value said, as
    # read and as read back; a gotchas bullet states d.
    skill_md = [("Overview", whole), ("Overview", joined)] + [("Overview", part) for part in "abcd"] + \
        [("gotchas bullet", "d")]
    carried = _resolve_gotchas(whole, skill_md, is_first_export=False)
    assert carried == ("d; [CARRIED] " + joined, [whole], [], [])
    dropped = _resolve_gotchas(carried[0], skill_md, is_first_export=False, several=(joined,))
    assert dropped == ("d", [], [joined], [])
    assert _resolve_gotchas(dropped[0], skill_md, is_first_export=False) == ("d", [], [], [])
    # Written unmarked by a first export, the value still gets one carry only.
    fresh = _resolve_gotchas(whole, skill_md, is_first_export=True)
    assert fresh == ("d; " + joined, [], [], [])
    carried = _resolve_gotchas(fresh[0], skill_md, is_first_export=False, several=(joined,))
    assert carried == ("d; [CARRIED] " + joined, [joined], [], [])
    assert _resolve_gotchas(carried[0], skill_md, is_first_export=False, several=(joined,)) == \
        ("d", [], [joined], [])
    # One T2-future annotation that states the whole value keeps it unmarked, read whole and read back.
    stated = _resolve_gotchas(whole, [], is_first_export=False, report=(whole,))
    assert stated == (joined, [], [], [])
    assert _resolve_gotchas(stated[0], [], is_first_export=False, report=(joined,), several=(joined,)) == stated
    # An older export's line that joined its pitfalls with `, ` is one pitfall that joins several.
    older = _resolve_gotchas("a, b", [("Overview", "a, b")], is_first_export=False, several=("a, b",))
    assert older == ("[CARRIED] a, b", ["a, b"], [], [])
    assert _resolve_gotchas(older[0], [("Overview", "a, b")], is_first_export=False, several=("a, b",)) == \
        ("", [], ["a, b"], [])
    # The same line with each pitfall in a gotchas bullet of its own: they come back as new gotchas while the
    # joined one rides its one carry, and the line then stays the same.
    apart = [("gotchas bullet", "a"), ("gotchas bullet", "b")]
    older = _resolve_gotchas("a, b", apart, is_first_export=False, several=("a, b",))
    assert older == ("a; b; [CARRIED] a, b", ["a, b"], [], [])
    settled = _resolve_gotchas(older[0], apart, is_first_export=False, several=("a, b",))
    assert settled == ("a; b", [], ["a, b"], [])
    assert _resolve_gotchas(settled[0], apart, is_first_export=False) == ("a; b", [], [], [])


@pytest.mark.parametrize("skill_md, report", [
    pytest.param([("Overview", START_UI), ("gotchas bullet", START_UI)], (), id="oms-cognee-gotchas-bullet"),
    pytest.param([("Overview", START_UI)], (START_UI,), id="t2-future-annotation"),
])
@pytest.mark.parametrize("is_first_export", [False, True])
def test_a_joined_prior_pitfall_one_place_states_whole_stays_on_the_line(skill_md, report, is_first_export):
    """#1092: a prior pitfall that joins several, which one gotchas-type bullet or one T2-future annotation
    states whole, is kept unmarked, written once, on every export, never carried, dropped and added back."""
    text = _read(SNIPPET)
    assert ONE_PITFALL_CLAUSE in text and WRITTEN_ONCE_CLAUSE in text
    line = rms.write_gotchas([(START_UI, False)])
    for export in range(3):
        result = _resolve_gotchas(line, skill_md, is_first_export and export == 0, report, several=(START_UI,))
        assert result == (line, [], [], []), f"export {export + 1}"
        line = result[0]


def test_removing_a_prior_pitfall_gives_a_left_off_gotcha_its_slot():
    """#1092: the no-slot warning's way out, through §3a as written."""
    assert NO_SLOT_WARNING in _read(SNIPPET) and NO_SLOT_REMEDY in _read(SNIPPET)
    skill_md = [("Overview", "a"), ("Overview", "b"), ("Overview", "c"), ("gotchas bullet", "n")]
    assert _resolve_gotchas("a; b; c", skill_md, is_first_export=False) == ("a; b; c", [], [], ["n"])
    freed = _resolve_gotchas("a; b", skill_md, is_first_export=False)
    assert freed == ("a; b; n", [], [], [])
    assert _resolve_gotchas(freed[0], skill_md, is_first_export=False) == freed
    # A pitfall a source-2 place states comes back as a new gotcha, in source order, so removing it frees a
    # slot only for a left-off gotcha stated before it. With no prior line, new gotchas alone fill the line.
    bullets = [("gotchas bullet", pitfall) for pitfall in "abne"]
    assert _resolve_gotchas("", bullets, is_first_export=False) == ("a; b; n", [], [], ["e"])
    assert _resolve_gotchas("a; b; e", bullets, is_first_export=False) == ("a; b; e", [], [], ["n"])
    assert _resolve_gotchas("b; e", bullets, is_first_export=False) == ("b; e; a", [], [], ["n"])
    assert _resolve_gotchas("a; b", bullets, is_first_export=False) == ("a; b; n", [], [], ["e"])


# --------------------------------------------------------------------------
# #1093: a name the prior `|api:` line lists keeps the mark that line gave it
# --------------------------------------------------------------------------

# The reason item 2 gives, for both halves of the #1093 dry run: the three const
# arrow functions that lost `()` and the two components that gained it.
KIND_REASON = ("a kind does not say how the line marks a name (an AST recipe labels a const arrow function "
               "`function` where a by-eye read can label it `const`, and a component declared with `function` is "
               "labeled `function` though the line can write it bare), so a kind never changes the mark of a name "
               "the line lists.")
# The single-skill template §3b fills from the snippet format.
TEMPLATE_API = "|api: {ranked exports, each with () or bare as step 2's api ranking gives it, comma-separated}"

# oh-my-skills forge-data/oms-uitripled/0.1.0/provenance-map.json: each name's
# `export_type`. `ThemeProvider` and `UILibraryProvider` come from ast-grep, the
# others from by-eye `source-read` entries, which label three const arrow
# functions `const`.
UITRIPLED_KINDS = {"ThemeProvider": "function", "useTheme": "const", "UILibraryProvider": "function",
                   "useUILibrary": "function", "cn": "function", "sanitizeSlug": "const",
                   "generateUniqueSlug": "function", "generateGridCode": "const",
                   "mergeComponentImports": "function", "add": "function"}
# oh-my-skills skills/oms-uitripled/0.1.0/oms-uitripled/context-snippet.md line 4,
# at a02403f (the prior line of the #1093 dry run) and at 7a14e80 (the line the
# SKF 10.0.0 re-export published, its marks set by the kinds above).
UITRIPLED_API_A02403F = ("ThemeProvider, useTheme(), UILibraryProvider, useUILibrary(), cn(), sanitizeSlug(), "
                         "generateUniqueSlug(), generateGridCode(), mergeComponentImports(), add()")
UITRIPLED_API_7A14E80 = ("ThemeProvider(), useTheme, UILibraryProvider(), useUILibrary(), cn(), sanitizeSlug, "
                         "generateUniqueSlug(), generateGridCode, mergeComponentImports(), add()")


def _prior_marks(value: str) -> dict[str, bool]:
    """The helper's `read_api` of an `|api:` value as {name: parens}, in order: `prior_api` as §3b ranks it."""
    return {name["name"]: name["parens"] for name in rms.read_api(value)}


def _api_marks(prior_line: str, ranked_names: list[str], kinds: dict[str, str] | None) -> str:
    """The `|api:` value §3b item 2 writes for the ranked names: a `prior_api` name with the mark the prior line
    gave it, whatever its kind, and a name new to the line with `()` only when the provenance map (`kinds`, None
    when there is no map) labels it `function`. The oracle reads no other kind as a function."""
    prior = _prior_marks(prior_line)

    def parens(name: str) -> bool:
        if name in prior:
            return prior[name]
        return kinds is not None and kinds.get(name) == "function"

    return ", ".join(name + ("()" if parens(name) else "") for name in ranked_names)


def test_the_prior_api_line_sets_the_mark_of_each_name_it_lists():
    """#1093: §3b item 2 keeps a listed name's prior mark and lets `export_type` mark only a new name; the snippet
    format, load-skill's binding and update-skill's trigger say the same."""
    rank = _line(_section(_generate(), "#### 3b. Single Skills", "#### 3c. "), "2. ")
    assert _in_order(rank, "so the `|api:` line stays the same from export to export while the surface does",
                     "first the `prior_api` names", PRIOR_MARK_CLAUSE + ": " + KIND_REASON, NEW_NAME_CLAUSE)
    assert _line(_read(SNIPPET_FORMAT), "|api: ") == TEMPLATE_API
    assert "`{forge_provenance_map}` ← `paths.provenance_map.path` (that folder's `provenance-map.json`, else the " \
           "flat copy, else null), whose `export_type` gives step 2 the `()` of an api name new to the line." \
           in _read(LOAD)
    exports = _line(_regeneration(), "- **Headline exports changed**")
    assert "differ from the prior snippet's `|api:` line (a listed name left `exports` or is now deprecated, or a " \
           "`NEW_EXPORT` took a free slot)." in exports
    assert "MODIFIED_EXPORT" not in exports and "changed the kind" not in exports


def test_the_single_skill_template_gives_no_mark_rule_of_its_own():
    """#1093, #1164: §3b fills the single-skill template from the snippet format, so its `|api:` placeholder sends
    each name's mark to step 2's ranking and gives a function no `()` on its own; it has no Line 4 bullet."""
    assert "from {snippetFormatData}" in _line(_generate(), "Emit the single-skill template")
    fmt = _read(SNIPPET_FORMAT)
    template = _section(fmt, "## Single Skill Snippet Template", "## Stack Skill Snippet Template")
    assert _line(template, "|api: ") == TEMPLATE_API
    assert "- **Line 4 (api):**" not in fmt and "- **api line**" not in fmt
    assert "for functions" not in fmt and "export_type" not in fmt, "#1093: only step 2 says which api names take `()`"


@pytest.mark.parametrize("prior_line", [UITRIPLED_API_A02403F, UITRIPLED_API_7A14E80], ids=["a02403f", "7a14e80"])
@pytest.mark.parametrize("kinds", [UITRIPLED_KINDS, None], ids=["0.1.0-map", "no-map"])
def test_an_unchanged_surface_writes_the_same_api_line(prior_line, kinds):
    """#1093: re-ranked on the same surface, each oms-uitripled line comes back as it was, each of its 10 names
    with its prior mark, whichever marks the line holds and with or without a provenance map."""
    assert PRIOR_MARK_CLAUSE in _read(SNIPPET) and NEW_NAME_CLAUSE in _read(SNIPPET)
    ranked = list(_prior_marks(prior_line))
    assert ranked == list(UITRIPLED_KINDS), "the prior names rank first, and the surface lists all 10"
    assert _api_marks(prior_line, ranked, kinds) == prior_line


def test_the_kinds_alone_set_every_mark_only_when_there_is_no_prior_line():
    """#1093: with no prior snippet every name is new to the line, so the 0.1.0 kinds give the 7a14e80 line,
    which differs from the a02403f line in the 5 marks the issue names."""
    assert NEW_NAME_CLAUSE in _read(SNIPPET)
    assert _api_marks("", list(UITRIPLED_KINDS), UITRIPLED_KINDS) == UITRIPLED_API_7A14E80
    before, after = _prior_marks(UITRIPLED_API_A02403F), _prior_marks(UITRIPLED_API_7A14E80)
    assert {name for name in before if before[name] != after[name]} == \
        {"ThemeProvider", "useTheme", "UILibraryProvider", "sanitizeSlug", "generateGridCode"}


LISTED_KINDS = {"useTheme": "const", "ThemeProvider": "function"}


@pytest.mark.parametrize("kinds, expected", [
    pytest.param({**LISTED_KINDS, "createTheme": "function"}, "useTheme(), ThemeProvider, createTheme()",
                 id="function"),
    pytest.param({**LISTED_KINDS, "createTheme": "const"}, "useTheme(), ThemeProvider, createTheme", id="const"),
    pytest.param({**LISTED_KINDS, "createTheme": "class"}, "useTheme(), ThemeProvider, createTheme", id="class"),
    pytest.param(LISTED_KINDS, "useTheme(), ThemeProvider, createTheme", id="no-kind"),
    pytest.param(None, "useTheme(), ThemeProvider, createTheme", id="no-map"),
])
def test_only_a_name_new_to_the_api_line_takes_its_mark_from_its_kind(kinds, expected):
    """#1093: a new name takes `()` for a function kind and is bare for any other kind, for no kind and with no
    map, while the listed names keep their prior marks against their kinds."""
    assert PRIOR_MARK_CLAUSE in _read(SNIPPET) and NEW_NAME_CLAUSE in _read(SNIPPET)
    assert _api_marks("useTheme(), ThemeProvider", ["useTheme", "ThemeProvider", "createTheme"], kinds) == expected


# --------------------------------------------------------------------------
# #1164: the documented `gotchas prior` and `resolve` calls, run
# --------------------------------------------------------------------------

GOTCHAS_CALL_RE = re.compile(r"(?:python3|uv run) \{rebuildManagedSectionsHelper\} gotchas (?:prior|resolve) [^`\n]+")


def _gotchas_calls(text: str) -> dict[str, str]:
    """The documented `gotchas prior` and `gotchas resolve` calls of `text`, fenced or inline, by mode."""
    calls: dict[str, str] = {}
    for call in GOTCHAS_CALL_RE.findall(text):
        mode = call.split("} gotchas ", 1)[1].split()[0]
        assert mode not in calls, f"two documented `gotchas {mode}` calls"
        calls[mode] = call
    assert set(calls) == {"prior", "resolve"}, calls
    return calls


def _helper_argv(call: str, values: dict[str, str]) -> list[str]:
    """The argv of a documented `python3 {helper} ...` or `uv run {helper} ...` call, run with this Python."""
    words = shlex.split(re.sub(r"\{([A-Za-z_][\w-]*)\}", lambda m: values[m.group(1)], call))
    runner = 2 if words[:2] == ["uv", "run"] else 1
    assert words[:runner] in (["uv", "run"], ["python3"]), call
    return [sys.executable, *words[runner:]]


def _documented_gotchas(workflow: str) -> tuple[dict[str, str], str]:
    """The two calls and the prose that binds their output: export's §2.5 and §3a, or update-skill's §5."""
    if workflow == "update":
        five = _regeneration()
        return _gotchas_calls(five), five
    text = _read(SNIPPET)
    steps = _section(text, "### 2.5. Check Existing Snippet", "### 2.7. ") + \
        _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    return _gotchas_calls(steps), steps


@pytest.mark.parametrize("workflow", ["export", "update"])
@pytest.mark.parametrize("skill_md, exports", [
    pytest.param(UITRIPLED_A02403F_SKILL_MD, [
        (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False), (REACT_19, False)]), [], [], []),
        (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False), (REACT_19, False)]), [], [], []),
    ], id="unchanged-surface"),
    pytest.param(UITRIPLED_REACT_20_SKILL_MD, [
        (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False), (REACT_19, True)]), [], [REACT_19], []),
        (rms.write_gotchas([(BARREL, False), (USE_CLIENT, False)]), [], [], [{"text": REACT_19,
                                                                          "reason": "already-carried"}]),
    ], id="another-version"),
])
def test_the_documented_gotchas_calls_rerun_an_oms_uitripled_export(tmp_path, workflow, skill_md, exports):
    """#1164: generate-snippet.md's and write.md §5's documented calls, run on the oms-uitripled package with the
    #1092 judgments, re-export it twice and give the line and warnings the old §3a tree gave."""
    calls, prose = _documented_gotchas(workflow)
    skills = tmp_path / "skills"
    package = skills / "oms-uitripled" / "0.1.0" / "oms-uitripled"
    package.mkdir(parents=True)
    snippet = package / "context-snippet.md"
    manifest = {"schema_version": "2", "exports": {"oms-uitripled": {"active_version": "0.1.0", "versions": {
        "0.1.0": {"ides": ["claude-code"], "last_exported": "2026-09-01", "status": "active"}}}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    values = {"rebuildManagedSectionsHelper": REBUILD.as_posix(), "skills_output_folder": skills.as_posix(),
              "resolved_skill_package": package.as_posix(), "skill_package": package.as_posix(),
              "skill-name": "oms-uitripled", "skill_name": "oms-uitripled",
              "export_stage_dir": (tmp_path / "stage").as_posix(), "run_dir": (tmp_path / "run").as_posix()}
    line = UITRIPLED_A02403F
    for export, (expected_line, left_off, carried, dropped) in enumerate(exports, start=1):
        snippet.write_bytes(("[oms-uitripled v0.1.0]|root: .claude/skills/oms-uitripled/\n"
                             f"|api: {UITRIPLED_API_A02403F}\n|gotchas: {line}\n").encode("utf-8"))
        proc = _run(_helper_argv(calls["prior"], values))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        prior = json.loads(proc.stdout)
        assert set(prior) == {"status", "prior_gotchas", "prior_api", "is_first_export"}
        for name in ("prior_gotchas", "prior_api", "is_first_export"):
            assert f"`{name}`" in prose, name
        assert prior["is_first_export"] is False and len(prior["prior_api"]) == 10
        # A place states the same claim whichever way the line wrote the pitfall's `; `, so the pitfall it
        # names is the one the prior line now holds.
        forms = {rms.write_gotchas([(p["text"], False)]): p["text"] for p in prior["prior_gotchas"]}
        meant = [(place, forms.get(rms.write_gotchas([(pitfall, False)]), pitfall)) for place, pitfall in skill_md]
        backed, new = _judgments(prior["prior_gotchas"], meant)
        argv = _helper_argv(calls["resolve"], values)
        judgments = Path(argv[argv.index("--judgments") + 1])
        judgments.parent.mkdir(parents=True, exist_ok=True)
        judgments.write_bytes(json.dumps({"backed": backed, "new_gotchas": new}).encode("utf-8"))
        proc = _run(argv)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        placed = json.loads(proc.stdout)
        assert (placed["line"], placed["left_off"], placed["carried"], placed["dropped"]) == \
            (expected_line, left_off, carried, dropped), f"export {export}"
        line = placed["line"]
    assert workflow == "update" or "Bind `{gotchas_line}` ← its `line`" in prose


@pytest.mark.parametrize("workflow", ["export", "update"])
def test_a_failed_gotchas_call_halts(workflow):
    """#1164: a `prior` that cannot read the snippet or the manifest, and a `resolve` that still fails after one
    corrected retry, halt without a new halt reason."""
    if workflow == "export":
        text = _read(SNIPPET)
        prior = _section(text, "### 2.5. Check Existing Snippet", "### 2.7. ")
        assert ("When it exits non-zero, delete the `{export_stage_dir}` folder when it is bound and HALT (exit code 4, "
                '`halt_reason: "context-rebuild-failed"`, phase `generate-snippet §2.5`)') in prior
        shared = _section(_generate(), "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
        assert _in_order(shared, "When it exits non-zero, correct the judgments file as its `error` says and run it "
                         "once more.", "When it fails again, delete the `{export_stage_dir}` folder and HALT (exit "
                         'code 4, `halt_reason: "context-rebuild-failed"`, phase `generate-snippet §3a`)')
        exit_4 = next(line for line in _read(ENVELOPE).splitlines() if line.startswith("| 4 "))
        assert "step 2 §2.5 (the prior snippet or the export manifest cannot be read), §3a (the gotchas cannot be " \
               "placed, after one corrected retry) or §4 (the token counter fails)" in exit_4
    else:
        five = _regeneration()
        assert "When `resolve` exits non-zero, correct the judgments file as its `error` says and run it once more." \
            in five
        assert ("When `prior` fails, or `resolve` fails again, HALT with status `halted-for-write-failure` (halt "
                'procedure: `phase: "write:context-snippet"`, `path: "{skill_package}/context-snippet.md"`') in five
        write = UPDATE_WRITE.read_text(encoding="utf-8")
        frontmatter = write.split("\n---\n", 1)[0]
        assert ("rebuildManagedSectionsProbeOrder:\n"
                "  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'\n"
                "  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'\n") in frontmatter
        assert "resolve `{rebuildManagedSectionsHelper}` ← first existing path in " \
               "`{rebuildManagedSectionsProbeOrder}`" in five
