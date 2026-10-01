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
  manifest_path stays null until step 4 §9b wrote the manifest. The §8 dry-run
  branch shows the manifest line, and On Activation checks the skills folder
  without writing under --dry-run.
- #587: step 3 only stages the snippet; step 4 §9c copies it into the package
  after the §8 gate, the context files and the manifest, so a cancel, a dry run
  or a halt before §9c never spends a carried gotchas line's `[CARRIED]` cycle.
- #583 and determinism-2: step 1 §2 binds the version, its package and its
  evidence report from `skf-skill-inventory.py resolve`, and §4b reads the test
  report of that version through `skf-find-test-report.py find`.
- leanness-3: one gotchas decision tree, first-export branch included, serves
  single and stack skills.
"""

from __future__ import annotations

import calendar
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
PROBE = "references/preflight-snippet-root-probe.md"
ORPHAN_CONTEXT = "references/orphan-context-detection.md"
ORPHAN_ROWS = "references/orphan-row-detection.md"

# The file each headless gate lives in, by the gate id it records.
GATE_FILES = {
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
    assert "step 4 §9c (a snippet write fails) → `write-failed`" in rows["4"]
    # The table sits beside the halt command, so the always-loaded SKILL.md keeps a pointer only.
    skill = _read(SKILL_MD)
    assert "## Exit Codes" not in skill and "## Result Contract" not in skill
    row = next(line for line in skill.splitlines() if line.startswith("| **Exit codes** |"))
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
    return (body.replace("{observed_prefixes}", '["skills/"]')
                .replace("{target_context_files[0].skill_root}", ".claude/skills/")
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
    payload = (body.replace("<step file> §<section>", "update-context §9")
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
    assert "pass `--result-dir`" in real and "the `{manifest_path}` step 4 §9b bound" in real
    hook = _section(summary, "### 6b. Post-Export Hook (Optional)", "### 7. ")
    assert hook.startswith("### 6b. Post-Export Hook (Optional)\n\nSkip this section on a dry run")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook, "a path with a space stays one argument"
    assert "when `{result_path}` is null" in hook
    flags = next(line for line in _read(SKILL_MD).splitlines() if line.startswith("| **Flags** |"))
    assert "no result file is written and no `on_complete` hook runs" in flags
    assert "write nothing other than a headless run's scratch run folder" in flags, (
        "a headless dry run still creates and deletes its run folder")
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    assert "a --dry-run writes none and\n# never invokes it" in toml


def test_manifest_path_is_bound_only_once_the_manifest_is_written():
    update = _read(UPDATE)
    manifest = _section(update, "### 9b. Update Export Manifest", "### 9c. ")
    bind = "Once every `set` has exited 0, bind `{manifest_path}` ← `{skills_output_folder}/.export-manifest.json`"
    assert bind in manifest
    assert manifest.index("[--ides {ides_written}]") < manifest.index(bind)
    meaning = SCHEMA["properties"]["manifest_path"]["description"]
    assert "Null when no manifest write completed: every dry run, and every halt before the manifest write" in meaning


def test_a_step_4_halt_reports_the_batch_and_what_it_wrote():
    """A field a halt leaves out reads as empty, so every halt passes the batch it resolved."""
    halt = _section(_read(ENVELOPE), "## Emitting a Halt", "## Exit Codes")
    assert "Always pass `skills`, the resolved batch (`[]` only before step 1 bound `skill_batch`)" in halt
    update = _read(UPDATE)
    manifest = _section(update, "### 9b. Update Export Manifest", "### 9c. ")
    helper = next(line for line in manifest.splitlines() if line.startswith("Resolve `{manifestOpsHelper}`"))
    assert 'when no candidate exists, HALT (exit code 4, `halt_reason: "manifest-write-failed"`)' in helper
    assert ("emit the error envelope per `references/result-envelope.md` with the resolved `skills`, "
            "the `context_files_updated` list and `manifest_path: null`") in helper
    snippets = _section(update, "### 9c. Write the Snippets", None)
    assert 'On a failed copy, HALT (exit code 4, `halt_reason: "write-failed"`)' in snippets
    assert ("with the resolved `skills`, the `context_files_updated` list and `manifest_path` as §9b bound it"
            in snippets)


def test_the_dry_run_shows_the_manifest_line_where_it_runs():
    """architecture-2: a dry run with passive context on leaves step 4 at §8, so §8 shows the line too."""
    update = _read(UPDATE)
    line = "**[DRY RUN] Export manifest would be updated for {skill-name-list}: ides: {ides_written}.**"
    menu = _section(update, "### 8. Present MENU OPTIONS", "**If NOT dry-run:**")
    assert line in menu and "§9 to §9c do not run" in menu
    assert "give `{ides_written}` as §9b defines it, over the targets above, or `none` when it is empty" in menu
    assert "deduplicated" not in menu, "§9b alone defines ides_written"
    assert line in _section(update, "### 9b. Update Export Manifest", "### 9c. ")


def test_activation_checks_the_skills_folder_without_writing_under_dry_run():
    probe = _section(_read(SKILL_MD), "5. **Pre-flight write check.**", "6. Load, read the full file")
    assert "Without `--dry-run`, probe it with a write:" in probe
    dry = next(line for line in probe.splitlines() if "With `--dry-run`, check without writing" in line)
    assert '`test -w "{skills_output_folder}"`' in dry
    assert probe.index("Without `--dry-run`") < probe.index('printf \'probe\' > "{skills_output_folder}/.skf-write-probe"')


# --------------------------------------------------------------------------
# #587: the snippet is written after the step-4 gate, as the run's last write
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


def test_step_3_stages_the_snippet_and_writes_nothing_into_the_package():
    text = _read(SNIPPET)
    assert _writes_into_the_package(text) == []
    preview = _section(text, "### 5. Preview the Snippet", "### 6. ")
    assert "Nothing is written to a skill package in this step" in preview
    assert "step 4 copies each measured draft into its package after its [C] gate (§9c)" in preview


def test_step_4_writes_the_snippets_last_after_the_gate():
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
    assert "the end of §9c" in _section(update, "### 2. Resolve the Helpers", "### 3. ")
    rules = _section(_read(SKILL_MD), "## Workflow Rules", "## Stages")
    decision = next(line for line in rules.splitlines() if line.startswith("- **Snippet timing:**"))
    assert "after its [C] gate, as step 4's last write" in decision and "`[CARRIED]`" in decision
    assert "A cancel, a dry run or a halt before §9c leaves every snippet" in decision, (
        "a §9c halt keeps the snippets copied before it")
    for path in sorted(EXPORT.rglob("*.md")):
        assert "the run's last write" not in path.read_text(encoding="utf-8"), (
            f"{path.name}: step 6 writes the result files after §9c")


# Every step file and protocol a run reads before step 4 §9c, in run order.
BEFORE_9C = ("references/load-skill.md", PROBE, "references/multi-skill-mode.md", "references/package.md",
             SNIPPET, ORPHAN_CONTEXT, ORPHAN_ROWS)


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
    step = _section(load, "### 2. Load and Validate Skill Artifacts", "Load all files from `{resolved_skill_package}`:")
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
    assert "take item 3's **Otherwise** branch (the `not-skf-output` HALT)" in step


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
    step = _section(load, "### 2. Load and Validate Skill Artifacts", "Load all files")
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
    assert set(bound) == {"resolved_version", "resolved_skill_package", "forge_version", "forge_evidence_report"}
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
# leanness-3: one gotchas decision tree for both skill types
# --------------------------------------------------------------------------


def test_both_skill_types_use_one_gotchas_decision_tree():
    text = _read(SNIPPET)
    generate = _section(text, "### 3. Generate Snippet Content", "### 4. Verify Token Count")
    shared = _section(generate, "#### 3a. Gotchas (Both Skill Types)", "#### 3b. ")
    single = _section(generate, "#### 3b. Single Skills", "#### 3c. ")
    stack = _section(generate, "#### 3c. Stack Skills", None)
    assert "`python3 {manifestOpsHelper} {skills_output_folder} get {skill-name}`" in shared
    assert "the evidence report at `{forge_evidence_report}`" in shared, "the report step 1 §2 bound, never a guess"
    assert "set `is_first_export = true`" in shared
    assert shared.count("- **If ") == 5 and "`is_first_export == true`" in shared
    assert "- **If " not in single and "is_first_export" not in single
    assert "`gotchas` per the §3a decision tree" in single
    assert "Stack skills: apply the gotchas decision tree above unchanged, including the first-export branch." in stack
    assert "Same one-cycle expiry logic" not in text and "See the single-skill steps" not in text
