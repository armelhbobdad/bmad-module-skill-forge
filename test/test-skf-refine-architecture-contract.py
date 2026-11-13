#!/usr/bin/env python3
"""Contract of skf-refine-architecture's envelope, halts, draft and terminal sequence (#585, #587, #593).

No test runs a stage file, so these run the commands the stage files document
and pin the prose around them:

- skf-refine-architecture-result-envelope.v1.json is a valid JSON Schema whose
  emitter settings map each halt_reason to the exit code the Exit Codes table
  of references/exit-codes.md gives (SKILL.md points there and stays lean),
  and declares headless_decisions and warnings;
- every HALT the skill's Markdown names uses a halt_reason of the schema with
  its mapped exit code and names its phase; every stage that halts binds the
  emitter itself and shows the emit-halt command, and no file types an
  envelope or defers it to SKILL.md (the bare "HALT with error" is gone);
- On Activation reads the run's timestamp from the clock, and the stages
  read the run's bindings back from the RA state file: init writes its
  `[RA-RUN]` block one `key=value` per line, so a path holding spaces, `=`
  or quotes reads back whole, and each binding compile, report and init's
  resume offer read back is a key that block maps (#1178); the block saves
  no `on_complete` hook, which a personal `.user.toml` can set, and report.md
  binds a lost one from the customization resolver;
- an interactive run offers to resume a review that stopped before its [C]
  or [X] (#1178): init asks between its first section and the one that
  sets an earlier pass aside, only for the same document, unchanged since
  that run hashed it, whose run folder still holds the plan and the apply
  record, with the draft still in place, and never in a headless run; an
  edited document gets one line and a new run; [R] binds the stopped run,
  checks the rules again and hands compile the kept plan, whose `apply`
  rebuilds the draft before the review, and the halts a resumed review can
  reach point at [N]; the documented `hash` call gives one hash for one
  document and another once it is edited, apply and promote leave the
  files the conditions read, and SKILL.md declares no single-pass run;
- On Activation keeps only the emitter and the heredoc a halt uses before
  the run folder exists; init.md section 0 runs the config check, the write
  probe and the run folder in that order, under their on-activation phases,
  records the resolver warning once the folder exists and then runs the
  `activation_steps_append` entries, all before its first prompt (#1179);
- every halt_reason, emitted through the documented command (and On
  Activation's heredoc, before the run folder exists), prints a line that
  validates, whose run_id is the run's timestamp;
- every decision a gate documents is one the schema accepts, and every
  warning a step records is a fixed code the schema names; a document that
  names no inventory skill shows the scope confirmation with every skill in
  scope in an interactive run, and a headless run records that gate's
  decision (#1179);
- the documented pipeline runs on a fixture: init's rules check passes the
  bundled rules, init's inspect sets an earlier pass aside, compile's apply
  builds the draft from compile's summary, whose Changes Made rows (the VS
  Coverage row included, naming the report by file name only) the script
  writes (#1176), promote renames the earlier output, and the result payload
  report.md stages from their records writes the result files with the
  gates' decisions;
- compile writes {outputFile} only through promote, after the preservation
  check, keeps the draft beside the RA state file and deletes it on [X],
  halts a not-preserved build without a retry, shows the summary the script
  filled, and claims preservation only when the script passed and set no
  unmarked block aside; Steps 02 to 04 read the analysis copy, and an issue's
  claim is recorded as the exact line compile anchors on;
- report.md stages its payload with the script's context command, writes the
  result contract, runs on_complete with the emitter's result_path and shows
  its failure on a report line, takes every count and name from the build
  record, and finishes the run with no menu (the walkthrough of each
  refinement is [R] at step 5's review, where feedback can still act);
- init's documented `rules` call and issue detection's `verdicts` and
  `exports` calls run as written on a fixture, with the bindings the steps
  give them;
- init's `enumerate` and `terms` calls and gap analysis's `scope` call run
  as written on skill folders (#1177): the terms are the source basenames
  the hand rule took, deduped, and `pair_count` is
  `{skill_count}*({skill_count}-1)/2`; an empty scope reruns with every
  skill, and a `verdicts` call that lost its terms runs again once issue
  detection writes them again.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SKILL = SRC / "skf-refine-architecture"
REFERENCES = SKILL / "references"
SCHEMA_PATH = SRC / "shared" / "scripts" / "schemas" / "skf-refine-architecture-result-envelope.v1.json"
EMITTER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
PRESERVATION = SKILL / "scripts" / "skf-check-preservation.py"
ENUMERATE = SRC / "shared" / "scripts" / "skf-enumerate-stack-skills.py"
HASH_CONTENT = SRC / "shared" / "scripts" / "skf-hash-content.py"
SKILL_MD = SKILL / "SKILL.md"
EXIT_CODES = REFERENCES / "exit-codes.md"
INIT = REFERENCES / "init.md"
GAP = REFERENCES / "gap-analysis.md"
ISSUES = REFERENCES / "issue-detection.md"
IMPROVEMENTS = REFERENCES / "improvements.md"
COMPILE = REFERENCES / "compile.md"
REPORT = REFERENCES / "report.md"

WORKFLOW = "skf-refine-architecture"
PREFIX = "SKF_REFINE_ARCHITECTURE_RESULT_JSON: "
RUN_STAMP = "20261001-101500"
EMIT_HALT = (
    'uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" '
    '--target stderr < "{run_dir}/halt.json"'
)
EMIT_PROBES = (
    "emitEnvelopeProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'\n"
    "  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'\n"
)
PHASE_PREFIX = {
    "SKILL.md": "on-activation",
    "init.md": "init",
    "gap-analysis.md": "gap-analysis",
    "issue-detection.md": "issue-detection",
    "compile.md": "compile",
    "report.md": "report",
}
# Two halts can share a line, so the phase is matched, not the rest of the line.
HALT_RE = re.compile(r'HALT \(exit code (\d+), `halt_reason: "([^"]+)"`\)((?: at phase `[^`]*`)?)')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _schema() -> dict:
    return json.loads(_read(SCHEMA_PATH))


def _settings() -> dict:
    return _schema()["$defs"]["skf-envelope"]["const"]


def _markdown() -> list[Path]:
    return [SKILL_MD, *sorted(REFERENCES.glob("*.md"))]


def _section(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"marker not found exactly once: {start!r}"
    at = text.index(start)
    stop = text.find(end, at + len(start))
    assert stop != -1, f"end marker {end!r} not found after {start!r}"
    return text[at:stop]


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


def _run(args, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, *[str(a) for a in args]],
        input=stdin, capture_output=True, text=True, encoding="utf-8", check=False,
    )


def _envelope(text: str) -> dict:
    [line] = [line for line in text.splitlines() if line.startswith(PREFIX)]
    return json.loads(line[len(PREFIX):])


def _validate(envelope: dict) -> None:
    jsonschema.Draft202012Validator(_schema()).validate(envelope)


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"{WORKFLOW}-{RUN_STAMP}"
    run_dir.mkdir(parents=True)
    return run_dir


# --- The schema and exit-codes.md agree ------------------------------------------------


def test_the_schema_is_valid_and_names_the_workflow():
    jsonschema.Draft202012Validator.check_schema(_schema())
    settings = _settings()
    assert settings["workflow"] == WORKFLOW
    assert settings["prefix"] == PREFIX.rstrip(": ")
    assert settings["wrapper"] is None and settings["halt_status"] == "error"
    assert settings["result_file"] == "refine-architecture-result"
    # Declared, so the emitter keeps what the run sink holds.
    assert {"headless_decisions", "warnings", "error", "run_id", "result_path"} <= set(_schema()["properties"])


def _exit_code_rows() -> dict[int, str]:
    rows = {}
    for line in _section(_read(EXIT_CODES), "| Code |", "## Result Envelope").splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|(.*)$", line)
        if m:
            rows[int(m.group(1))] = m.group(2)
    return rows


def test_each_halt_reason_sits_in_its_exit_code_row():
    rows = _exit_code_rows()
    assert sorted(rows) == [0, 2, 3, 4, 5, 6, 7, 8]
    for reason, code in _settings()["exit_codes"].items():
        assert reason in rows[code], (reason, code)
    halt_enum = [r for r in _schema()["properties"]["halt_reason"]["enum"] if r is not None]
    assert sorted(halt_enum) == sorted(_settings()["exit_codes"])
    assert sorted(_schema()["properties"]["exit_code"]["enum"]) == [0, *sorted(set(_settings()["exit_codes"].values()))]
    listed = _section(_read(EXIT_CODES), "`halt_reason` is one of:", "\n")
    assert sorted(re.findall(r'`"([a-z-]+)"`', listed)) == sorted(halt_enum)


def test_exit_codes_names_the_fields_and_leaves_their_meaning_to_the_schema():
    text = _read(EXIT_CODES)
    contract = _section(text, "## Result Envelope", "## Emitting a Halt")
    assert "skf-refine-architecture-result-envelope.v1.json" in contract
    assert set(_schema()["properties"]) <= set(re.findall(r"`([a-z_]+)`", contract))
    assert PREFIX + '{"' not in text, "the line is the emitter's, never typed"
    assert EMIT_HALT in _section(text, "## Emitting a Halt", "A HALT before the run folder exists")
    assert not HALT_RE.search(text), "exit-codes.md describes halts, it raises none"


def test_skill_md_points_at_the_exit_codes_and_keeps_no_copy():
    # The table, the envelope and the halt command live in one reference file,
    # so SKILL.md stays within its budget and no copy of them drifts. The
    # Result Contract section is the one pointer (w3 leanness-4).
    skill = _read(SKILL_MD)
    assert "## Exit Codes" not in skill and "**Emitting a halt.**" not in skill
    assert "| **Exit codes** |" not in skill
    contract = _section(skill, "## Result Contract (Headless)", "## On Activation")
    assert "`references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command" in contract
    for path in sorted(REFERENCES.glob("*.md")):
        if HALT_RE.search(_read(path)):
            assert "(`references/exit-codes.md` describes the envelope)" in _read(path), _rel(path)


def test_the_description_names_what_it_refines():
    """#600 architecture-4: both triggers name what RA refines, an architecture document checked against the
    generated skills and a Verify Stack report, so a generic "improve architecture doc" no longer picks it."""
    front = _read(SKILL_MD).split("\n---\n", 1)[0]
    [description] = [line for line in front.splitlines() if line.startswith("description: ")]
    assert "an architecture document against generated skills and a Verify Stack report" in description
    triggers = re.findall(r'"([^"]+)"', description.split("Use when", 1)[1])
    assert triggers == ["refine the architecture against generated skills",
                        "refine an architecture doc with a VS report."]
    for gone in ("improve architecture doc", "refine skill architecture"):
        assert gone not in description, gone


def test_skill_md_stays_under_its_token_budget():
    """#600 leanness-4 held SKILL.md under the 2,500-token prepass guideline; it measured 2,503 cl100k tokens at
    10,083 characters before the 6.0.0 release gate. The maintainer's decision for that gate adds two sentences on
    purpose, past the guideline: the foreground rule every SKILL.md carries word for word and the reading rule in
    the Headless row, to about 2,650 tokens. 10,740 characters holds it there without a tokenizer, so nothing else
    grows it. #965 grows the resolver sentence every SKILL.md carries word for word by 40 characters, to name the
    missing SKF helper, so the ceiling was 10,761. #1037 grows the foreground rule by 108 characters, to have every
    Agent call pass `run_in_background: false`, so the ceiling was 10,869. #1112 adds 286 characters: the bare-path
    rule names the `nextStepFile` exception and a `references/` line names the files the stages load, so the
    ceiling was 11,155. #1179 moved section 5's config, write-probe and run-folder halts, the resolver-warning
    record and the `activation_steps_append` run into init.md §0, which brings SKILL.md back under the 2,500-token
    guideline (2,331 cl100k tokens at 9,564 characters), so the ceiling is 9,600."""
    assert len(_read(SKILL_MD)) < 9_600, len(_read(SKILL_MD))

# --- Every HALT names a known reason, its code and its phase ------------------------------


def _halts():
    for path in _markdown():
        for m in HALT_RE.finditer(_read(path)):
            yield path, int(m.group(1)), m.group(2), m.group(3)


def test_every_halt_uses_a_schema_reason_and_its_exit_code():
    mapping = _settings()["exit_codes"]
    found = list(_halts())
    assert len(found) >= 25, len(found)
    for path, code, reason, _ in found:
        assert reason in mapping, f"{_rel(path)}: unknown halt_reason {reason}"
        assert mapping[reason] == code, f"{_rel(path)}: {reason} exits {mapping[reason]}, not {code}"
    assert {reason for _, _, reason, _ in found} == set(mapping), "every halt_reason is raised somewhere"


def _init_pre_flight() -> str:
    """init.md §0, the On Activation halts #1179 moved out of SKILL.md."""
    return _section(_read(INIT), "### 0. Pre-flight: Config, Write Probe and Run Folder", "### 1. ")


def test_every_halt_names_its_phase():
    pre_flight = _init_pre_flight()
    for path, _, reason, phase in _halts():
        m = re.fullmatch(r" at phase `([a-z-]+):([a-z0-9-]+)`", phase)
        assert m, f"{_rel(path)}: a {reason} HALT names no phase"
        allowed = {PHASE_PREFIX[path.name]} | ({"on-activation"} if path.name == "init.md" else set())
        assert m.group(1) in allowed, (_rel(path), m.group(0))
    # #1179: init.md §0 keeps the On Activation phases it took from SKILL.md, and no other part of init.md uses one.
    init = _read(INIT)
    at = init.index(pre_flight)
    for m in HALT_RE.finditer(init):
        inside = at <= m.start() < at + len(pre_flight)
        assert m.group(3).startswith(" at phase `on-activation:") is inside, m.group(0)
    phases = [m.group(3) for m in HALT_RE.finditer(pre_flight)]
    assert phases == [" at phase `on-activation:config`", " at phase `on-activation:config`",
                      " at phase `on-activation:write-probe`", " at phase `on-activation:run-folder`"], phases
    assert [m.group(3) for m in HALT_RE.finditer(_read(SKILL_MD))] == [" at phase `on-activation:emitter`"]


def test_each_halting_stage_binds_the_emitter_and_shows_the_command():
    stages = [path for path in sorted(REFERENCES.glob("*.md")) if HALT_RE.search(_read(path))]
    assert {path.name for path in stages} == {"init.md", "gap-analysis.md", "issue-detection.md", "compile.md",
                                               "report.md"}
    for path in stages:
        text = _read(path)
        assert EMIT_PROBES in _frontmatter(text) + "\n", _rel(path)
        assert "**Halt envelope.**" in text and EMIT_HALT in text, _rel(path)
        assert "resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound" in text
    # SKILL.md resolves it before init.md §0, whose halts run before the first prompt (#1179).
    activation = _section(_read(SKILL_MD), "5. **Pre-flight", "6. Load")
    assert activation.startswith("5. **Pre-flight: the emitter.** Resolve `{emitEnvelopeHelper}`")
    assert ("Resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, "
            "else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`") in activation
    pre = _init_pre_flight()
    order = ["**Config-completeness (exit 3).**", "**Write probe (exit 4).**", "**Run folder (exit 4).**"]
    assert [pre.index(block) for block in order] == sorted(pre.index(block) for block in order)
    for block in order:
        assert block not in _read(SKILL_MD), block


def test_no_file_types_an_envelope_or_defers_it_to_skill_md():
    for path in [*_markdown(), SKILL / "customize.toml"]:
        text = _read(path)
        for stale in ("emit the error envelope", 'per SKILL.md "Result Contract (Headless)"',
                      "per **Result Contract (Headless)**", "SKILL.md's **Result Contract (Headless)**",
                      PREFIX + '{"', "HALT with error", "workflow_warnings"):
            assert stale not in text, f"{_rel(path)}: {stale!r}"


# --- The emitter builds each documented line ---------------------------------------------


def _halt_payload(reason: str) -> dict:
    """The halt.json the stage files document, filled in."""
    shape = re.search(r'`(\{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"\})`',
                      _read(COMPILE)).group(1)
    return json.loads(shape.replace("<phase>", "compile:draft").replace("<the halt message>", "Cannot build")
                      .replace("<halt_reason>", reason))


@pytest.mark.parametrize("reason", sorted(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
                                          ["$defs"]["skf-envelope"]["const"]["exit_codes"]))
def test_each_halt_reason_emits_a_valid_line(tmp_path, reason):
    run_dir = _run_dir(tmp_path)
    proc = _run([EMITTER, "emit-halt", "--workflow", WORKFLOW, "--run-dir", run_dir, "--target", "stderr"],
                stdin=json.dumps(_halt_payload(reason)))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert envelope["status"] == "error" and envelope["halt_reason"] == reason
    assert envelope["exit_code"] == _settings()["exit_codes"][reason]
    assert envelope["run_id"] == RUN_STAMP
    assert (envelope["refined_path"], envelope["result_path"], envelope["previous_pass"]) == (None, None, False)
    assert envelope["error"]["phase"] == "compile:draft"


def test_a_halt_after_the_promotion_names_the_refined_document(tmp_path):
    run_dir = _run_dir(tmp_path)
    shape = re.search(r'`(\{"phase": "<phase>", [^`]*"refined_path": "\{outputFile\}"\})`', _read(REPORT)).group(1)
    payload = (shape.replace("<phase>", "report:result-contract").replace("<the halt message>", "No contract")
               .replace("<halt_reason>", "write-failed").replace("{outputFile}", "/docs/refined-architecture-app.md"))
    proc = _run([EMITTER, "emit-halt", "--workflow", WORKFLOW, "--run-dir", run_dir, "--target", "stderr"],
                stdin=payload)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert (envelope["refined_path"], envelope["exit_code"]) == ("/docs/refined-architecture-app.md", 4)


def test_the_activation_halts_emit_before_the_run_folder_exists():
    activation = _read(SKILL_MD)
    m = re.search(r"<<'SKF_RA_HALT'\n\s*(\{.*\})\n\s*SKF_RA_HALT", activation)
    assert m, "SKILL.md shows the heredoc halt"
    payload = (m.group(1).replace("<phase>", "on-activation:run-folder")
               .replace("<the halt message>", "Cannot create the run folder").replace("<halt_reason>", "write-failed"))
    proc = _run([EMITTER, "emit-halt", "--workflow", WORKFLOW, "--target", "stderr"], stdin=payload)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert (envelope["exit_code"], envelope["run_id"]) == (4, None)
    # The run folder comes last in init.md §0's pre-flight, after every halt that cannot use it, and those halts
    # pass their payload with SKILL.md's block, not through the folder they have not made (#1179).
    pre = _init_pre_flight()
    assert pre.index("**Write probe") < pre.index("**Run folder (exit 4).**")
    assert 'mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"' in pre
    assert ("Until the run folder exists, a headless halt here passes its payload on stdin with the `emit-halt` "
            "block SKILL.md On Activation §5 shows, not through `{run_dir}/halt.json`.") in pre
    shown = _section(activation, "5. **Pre-flight", "6. Load")
    assert ("The halts of init.md §0 (the config, the write probe and the run folder) come before the run "
            "folder") in shown
    assert ("`run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-refine-architecture-{timestamp}`"
            in _section(activation, "2. **Compute run-scoped variables:**", "3. **Resolve"))


def test_init_runs_the_pre_flight_and_the_append_steps_before_its_first_prompt():
    """#1179: init.md §0 runs what On Activation §5 ran, in the order it ran it: the config, the write probe and the
    run folder, then the resolver warning once the folder exists, then the `activation_steps_append` entries, all
    before §1 asks for anything. SKILL.md only points there, and runs no append entry itself (#1111's rule, that
    the entries run once every halting pre-flight check has passed, now holds inside init.md)."""
    init = _read(INIT)
    pre = _init_pre_flight()
    assert init.index("**Recording a decision or a warning.**") < init.index(pre) < init.index("### 1. Accept Input")
    record = ('uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" '
              '--warning "$(cat "{run_dir}/resolver-warning.txt")"')
    steps = ["**Config-completeness (exit 3).**", "**Write probe (exit 4).**", "**Run folder (exit 4).**",
             'mkdir "{run_dir}"', "`{run_dir}/resolver-warning.txt` with a file write, never `echo`", record,
             "run each entry in `workflow.activation_steps_append` in order, then go on to §1."]
    at = [pre.index(step) for step in steps]
    assert at == sorted(at), steps
    assert "Every halting pre-flight check has now passed: run each entry" in pre
    assert pre.index(steps[-1]) > max(m.start() for m in HALT_RE.finditer(pre))
    assert init.count("activation_steps_append") == 1
    skill = _read(SKILL_MD)
    assert skill.count("activation_steps_append") == 1
    assert "init.md §0 runs `workflow.activation_steps_append` once its pre-flight has passed." in skill
    assert "then run `workflow.activation_steps_append`" not in skill
    assert ("keep the reason as `{customization_resolver_unavailable}` for init.md §0 to record once it has created "
            "`{run_dir}`") in skill
    assert "record --run-dir" not in skill and "mkdir" not in skill
    # The resume offer adds the reason to the stopped run's folder the way §0 records it.
    assert "with the file write and the `record` call §0 uses" in _section(init, "### 1a.", "### 1b.")
    assert "On Activation §5 uses" not in init
    # The exit-code rows name the stage that now raises those halts.
    rows = _exit_code_rows()
    assert "step 1 §0 (`output_folder` or `forge_data_folder` unconfigured" in rows[3]
    assert "On Activation §5 (the result emitter is not installed → `resolution-failure`)" in rows[3]
    assert "step 1 §0 (the write probe, the run folder)" in rows[4]
    assert "(SKILL.md On Activation §5, step 1 §0) passes the payload on stdin" in _read(EXIT_CODES)
    # The rows name step 1 §0, so the file says why its halts report on-activation phases.
    assert ("Step 1 §0's halts report the phases `on-activation:config`, `on-activation:write-probe` and "
            "`on-activation:run-folder`: they finish the activation's pre-flight, before the first prompt."
            ) in _read(EXIT_CODES)


# --- Decisions and warnings --------------------------------------------------------------

DECISION_RE = re.compile(r'`(\{"gate": "[a-z.-]+", [^`]+\})`')


def _fill(shape: str) -> str:
    """A documented decision with its placeholders filled in."""
    shape = re.sub(r"\[<[^<>]*>\]", '["oms-cognee"]', shape)
    return re.sub(r"<[^<>]*>", "value", shape)


def _decisions() -> list[dict]:
    found = []
    for path in (INIT, GAP, COMPILE):
        found += [json.loads(_fill(shape)) for shape in DECISION_RE.findall(_read(path))]
    return found


def test_each_documented_decision_is_one_the_schema_accepts(tmp_path):
    decisions = _decisions()
    gates = _schema()["properties"]["headless_decisions"]["items"]["properties"]["gate"]["enum"]
    assert sorted({d["gate"] for d in decisions}) == sorted(gates)
    run_dir = _run_dir(tmp_path)
    for decision in decisions:
        proc = _run([EMITTER, "record", "--workflow", WORKFLOW, "--run-dir", run_dir, "--decision"],
                    stdin=json.dumps(decision))
        assert proc.returncode == 0, (decision, proc.stderr)


def test_each_gate_records_its_decision_where_it_decides():
    record = 'uv run {emitEnvelopeHelper} record --workflow skf-refine-architecture --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"'
    assert record in _read(INIT) and record in _read(GAP) and record in _read(COMPILE)
    gate = [line for line in _read(GAP).splitlines() if line.startswith("**GATE [default: C]**")][0]
    assert "Record that decision in the run sink the moment it is taken" in gate
    assert '"gate": "gap-analysis.scope"' in gate
    review = _section(_read(COMPILE), "#### GATE [default: C]", "#### Menu Handling Logic:")
    assert '"gate": "compile.review"' in review


WARNING_RE = re.compile(r"[Rr]ecord the warning `([a-z_]+): [^`]+`")


def test_each_documented_warning_is_a_fixed_code_the_schema_names():
    codes = []
    for path in (INIT, GAP, REPORT):
        text = _read(path)
        codes += WARNING_RE.findall(text)
        codes += re.findall(r"--warning '([a-z_]+): [^']+'", text)
    assert sorted(set(codes)) == ["legacy_blocks_set_aside", "malformed_ra_markers", "out_of_scope_skills",
                                  "scope_fallback_all_skills", "unknown_scope_skills"]
    described = _schema()["properties"]["warnings"]["description"]
    for code in [*codes, "result_file_write_failed"]:
        assert code in described, code
    # Both ways to every skill in scope leave a trace in the envelope.
    safe_default = _section(_read(GAP), "**Safe default:**", "\n\n")
    assert "record the warning `scope_fallback_all_skills: the document names no inventory skill" in safe_default


def test_the_safe_default_asks_to_check_the_document_and_records_its_decision(tmp_path):
    """#1179: a document that names no inventory skill no longer skips the scope confirmation. An interactive run
    shows every skill in scope under one line asking whether the document is the one meant, with the same menu and
    edits; a headless run keeps every skill, records the gate's decision naming each one, and the fallback warning
    is recorded only when every skill leaves the gate in scope."""
    gap = _read(GAP)
    safe_default = _section(gap, "**Safe default:**", "\n\n")
    assert "leave `{in_scope_skills}` empty: §3 then puts every skill in scope" in safe_default
    assert "The confirmation below then asks the user to check the document." in safe_default
    assert ("When the confirmation ends with every skill still in scope, as a headless run's does at once, record "
            "the warning `scope_fallback_all_skills: the document names no inventory skill") in safe_default
    assert ("an edit that takes a skill out records none, since §3's `out_of_scope_skills` warning names those "
            "skills") in safe_default
    gate = _section(gap, "**Confirm a derived scope.**", "**Technologies with no skill.**")
    condition = gate.splitlines()[0]
    assert "or the safe default applies, show the split once" in condition
    assert "the safe default leaves no skill out, so neither shows this gate" not in gate
    shown = _section(gate, "**Under the safe default**", "\n\n")
    assert ('show "Check that `{architecture_doc}` is the document you meant: it names none of these skills." in '
            "place of the title line") in shown
    assert ("one row `| {skill} | In scope | the document names no inventory skill |` for each skill of "
            "`{doc_mentions}.skills[]`") in shown
    assert "with the rest of the message and the same menu" in shown
    assert ("An edit starts from every one of those skills in `{in_scope_skills}`, and §3's `[RA-SCOPE]` block then "
            "says the scope was derived then edited at the §2b confirmation; unedited, `{in_scope_skills}` stays "
            "empty, as §3 expects.") in shown
    # The check line names the document after a context loss too.
    assert ("When `{architecture_doc}` is no longer bound, read it from the `<!-- [RA-RUN] ... -->` block of the RA "
            "state file.") in shown
    assert gate.index("**Under the safe default**") < gate.index("Display: **Select:**")
    [gate_line] = [line for line in gate.splitlines() if line.startswith("**GATE [default: C]**")]
    assert ("Under the safe default, keep every skill in scope: the log and `in_scope` name each skill of "
            "`{doc_mentions}.skills[]`, and `out_of_scope` is `[]`.") in gate_line
    assert gate_line.index("Under the safe default") < gate_line.index("Record that decision in the run sink")
    # [X] at this confirmation cancels as it does for a derived scope.
    [cancel] = [line for line in gate.splitlines() if line.startswith("- IF cancel / exit / [X] / q / :q:")]
    assert 'HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `gap-analysis:scope`' in cancel
    # The headless decision, every skill in scope and none out, is one the emitter records.
    [shape] = [d for d in DECISION_RE.findall(gate_line) if '"gate": "gap-analysis.scope"' in d]
    decision = json.loads(re.sub(r"<[^<>]*>", "value", shape.replace("[<the in-scope skills>]", '["a", "b"]')
                                 .replace("[<the out-of-scope skills>]", "[]")))
    assert decision["evidence"] == {"in_scope": ["a", "b"], "out_of_scope": []}
    run_dir = _run_dir(tmp_path)
    proc = _run([EMITTER, "record", "--workflow", WORKFLOW, "--run-dir", run_dir, "--decision"],
                stdin=json.dumps(decision))
    assert proc.returncode == 0, proc.stderr
    proc = _run([EMITTER, "record", "--run-dir", run_dir, "--warning",
                 "scope_fallback_all_skills: the document names no inventory skill, so every skill is in scope"])
    assert proc.returncode == 0, proc.stderr
    # The scope block names how the scope was set either way.
    split = _section(gap, "### 3. Split the Library Pairs by Scope", "### 4.")
    assert "derived then edited at the §2b confirmation, or every skill by the safe default" in split


# --- The documented pipeline ---------------------------------------------------------------

ARCH = """---
project_name: app
---
# App Architecture

## Data Layer

Loro stores documents.

## API Layer

The API uses FastAPI.
"""


def _call(text: str, command: str) -> list[str]:
    """The documented preservation-script call, as argv for the script."""
    [line] = [line.strip() for line in text.splitlines()
              if line.strip().startswith(f"uv run {{preservationScript}} {command} ")]
    rest = line.split("{preservationScript} ", 1)[1]
    return [quoted or bare for quoted, bare in re.findall(r'"([^"]*)"|(\S+)', rest)]


def _helper_call(text: str, helper: str, command: str) -> list[str]:
    """The documented call of a resolved helper, as argv for its script, up to an output redirect."""
    prefix = f"uv run {{{helper}}} {command} "
    [line] = [line.strip() for line in text.splitlines() if line.strip().startswith(prefix)]
    rest = line.split(f"{{{helper}}} ", 1)[1].split(" > ", 1)[0]
    return [quoted or bare for quoted, bare in re.findall(r'"([^"]*)"|(\S+)', rest)]


def _bind(argv: list[str], values: dict) -> list[str]:
    out = []
    for word in argv:
        for key, value in values.items():
            word = word.replace("{" + key + "}", value)
        assert "{" not in word, word
        out.append(word)
    return out


def test_the_documented_pipeline_runs_end_to_end(tmp_path):
    run_dir = _run_dir(tmp_path)
    forge, docs = tmp_path / "forge", tmp_path / "docs"
    forge.mkdir()
    docs.mkdir()
    output = docs / "refined-architecture-app.md"
    output.write_bytes(b"# my earlier curated refinement\n")
    arch = tmp_path / "architecture.md"
    arch.write_bytes(ARCH.encode("utf-8"))
    values = {"architecture_doc": arch.as_posix(), "run_dir": run_dir.as_posix(), "timestamp": RUN_STAMP,
              "draftFile": (forge / ".skf-ra-draft-app.md").as_posix(), "outputFile": output.as_posix(),
              "planFile": (run_dir / "insertion-plan.json").as_posix(),
              "applyResult": (run_dir / "apply.json").as_posix(),
              "promoteResult": (run_dir / "promote.json").as_posix(),
              "inspectResult": (run_dir / "inspect.json").as_posix()}

    rules = _run([PRESERVATION, *_bind(_call(_read(INIT), "rules"),
                                       {"refinementRulesData": (REFERENCES / "refinement-rules.md").as_posix()})])
    assert rules.returncode == 0, rules.stdout
    inspect = _run([PRESERVATION, *_bind(_call(_read(INIT), "inspect"), values)])
    assert inspect.returncode == 0, inspect.stdout
    assert (run_dir / "analysis-doc.md").read_bytes() == ARCH.encode("utf-8")

    # Compile §5's summary: the Changes Made header row, its separator and {changes_rows}, then the
    # Evidence Sources header row, its separator and {evidence_rows}.
    table = _section(_read(COMPILE), "| Category | Count | Breakdown |", "\n\n")
    assert table.splitlines()[-1] == "{changes_rows}"
    summary = f"## Refinement Summary\n\n{table}\n\n| Skill | Refinements |\n|---|---|\n{{evidence_rows}}\n"
    report = forge / "feasibility-report-app-latest.md"
    plan = {"entries": [
        {"id": "gap-1", "kind": "gap", "anchor": "## Data Layer", "skills": ["loro", "fastapi"],
         "block": "#### RA: Loro <-> FastAPI Integration Path\n\n> [!NOTE] **Gap Identified by Refine Architecture**"},
        {"id": "issue-1", "kind": "issue", "tier": "Major", "anchor": "The API uses FastAPI.", "skills": ["fastapi"],
         "block": "> [!WARNING] **Issue Detected by Refine Architecture** (Major)"},
    ], "summary": summary, "unverified_technologies": [], "skill_count": 2,
        "tiers": json.loads(rules.stdout)["tiers"],
        # §6 passes the cached report JSON's path and coverage keys as they are.
        "vs_report": {"path": report.as_posix(), "coveragePercentage": 80, "coverageMeasured": True}}
    (run_dir / "insertion-plan.json").write_bytes(json.dumps(plan).encode("utf-8"))
    apply = _run([PRESERVATION, *_bind(_call(_read(COMPILE), "apply"), values)])
    assert apply.returncode == 0, apply.stdout
    promote = _run([PRESERVATION, *_bind(_call(_read(COMPILE), "promote"), values)])
    assert promote.returncode == 0, promote.stdout
    previous = docs / f"refined-architecture-app-{RUN_STAMP}.md"
    assert previous.read_bytes() == b"# my earlier curated refinement\n"
    refined = output.read_text(encoding="utf-8").splitlines()
    start = refined.index("| Category | Count | Breakdown |")
    assert refined[start + 2:start + 9] == [
        "| Gaps Filled | 1 | - |",
        "| Issues Flagged | 1 | Critical: 0, Major: 1, Minor: 0 |",
        "| Improvements Suggested | 0 | High: 0, Medium: 0, Low: 0 |",
        "| Skills Used as Evidence | 2 | - |",
        "| Not verified (no skill) | 0 | none |",
        "| VS Coverage | 80% | technologies with a skill when [VS] ran, from `feasibility-report-app-latest.md` |",
        "",
    ]
    assert forge.as_posix() not in output.read_text(encoding="utf-8"), "the refined document names no local folder"

    # The gates that auto-resolved on the way, then report.md's payload from the records.
    for decision in _decisions():
        assert _run([EMITTER, "record", "--workflow", WORKFLOW, "--run-dir", run_dir, "--decision"],
                    stdin=json.dumps(decision)).returncode == 0
    context = _run([PRESERVATION, *_bind(_call(_read(REPORT), "context"), values)])
    assert context.returncode == 0, context.stdout
    payload = (run_dir / "result-context.json").read_text(encoding="utf-8")
    proc = _run([EMITTER, "emit", "--workflow", WORKFLOW, "--run-dir", run_dir, "--result-dir", docs],
                stdin=payload)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    _validate(envelope)
    assert envelope["status"] == "success" and envelope["exit_code"] == 0
    assert (envelope["gap_count"], envelope["issue_count"], envelope["improvement_count"]) == (1, 1, 0)
    assert Path(envelope["previous_refined_path"]).as_posix() == previous.as_posix()
    assert envelope["run_id"] == RUN_STAMP
    assert {d["gate"] for d in envelope["headless_decisions"]} == {d["gate"] for d in _decisions()}
    per_run = [p for p in docs.glob("refine-architecture-result-*.json") if not p.name.endswith("-latest.json")]
    assert len(per_run) == 1 and Path(envelope["result_path"]).as_posix() == per_run[0].as_posix()
    latest = json.loads((docs / "refine-architecture-result-latest.json").read_text(encoding="utf-8"))
    assert latest["skill"] == WORKFLOW and latest["summary"]["gap_count"] == 1
    assert latest["outputs"] == [{"type": "report", "path": output.as_posix()}]


# --- Draft then promote --------------------------------------------------------------------


def test_compile_writes_the_output_only_through_promote():
    text = _read(COMPILE)
    frontmatter = _frontmatter(text)
    assert "draftFile: '{forge_data_folder}/.skf-ra-draft-{project_name}.md'" in frontmatter
    assert "preservationScript: 'scripts/skf-check-preservation.py'" in frontmatter
    assert "Write the complete refined architecture to `{outputFile}`" not in text
    build = _section(text, "### 6. Build the Draft", "### 7.")
    assert ('uv run {preservationScript} apply --original "{architecture_doc}" --plan "{planFile}" '
            '--draft "{draftFile}" -o "{applyResult}"') in build
    assert "`{outputFile}` is not touched here" in build
    menu = _section(text, "### 8. Present MENU OPTIONS", "[Redisplay Menu Options]")
    assert ('uv run {preservationScript} promote --original "{architecture_doc}" --draft "{draftFile}" '
            '--output "{outputFile}" --timestamp "{timestamp}" -o "{promoteResult}"') in menu
    assert "refined-architecture-{arch_project_name}-{timestamp}.md" in menu
    cancel = [line for line in menu.splitlines() if line.startswith("- IF cancel")][0]
    assert 'rm -f "{draftFile}"' in cancel and "`{outputFile}` is unchanged" in cancel
    feedback = [line for line in menu.splitlines() if line.startswith("- IF Any other")][0]
    assert "in `{planFile}`" in feedback and "feedback never edits the draft" in feedback


def test_a_failed_check_never_promotes():
    # apply is deterministic: the same plan on the same document fails the same
    # way, so a failed build halts (headless) or waits for feedback, never retries.
    build = _section(_read(COMPILE), "### 6. Build the Draft", "### 7.")
    failed = [line for line in build.splitlines() if line.startswith('- **1 with `status: "not-preserved"`')][0]
    assert "`missing[]`" in failed and "`altered[]`" in failed and "rebuild" not in failed
    assert "running the same plan again gives the same result" in failed
    assert ('In headless, HALT (exit code 4, `halt_reason: "preservation-failed"`) at phase `compile:draft` '
            "without a retry") in failed
    assert "offer no [C] until a feedback round's `apply` passes" in failed
    feedback = [line for line in _read(COMPILE).splitlines() if line.startswith("- IF Any other")][0]
    assert "rebuilt once" not in feedback and "[C] waits for a round whose `apply` passes" in feedback
    # A draft edited during the review is what a rebuild fixes, so promote keeps one.
    promote = _section(_read(COMPILE), "  - **1** (`not-preserved`)", "\n")
    assert "rebuild once" in promote and '`halt_reason: "preservation-failed"`' in promote
    unreadable = _section(_read(COMPILE), "  - **2** with a JSON (`error` names the file it could not read)", "\n")
    assert ('if it still cannot be read, HALT (exit code 4, `halt_reason: "write-failed"`) at phase '
            '`compile:promote`, with `"path": "{draftFile}"`') in unreadable
    rollback = _section(_read(COMPILE), "  - **3:** HALT", "\n")
    assert "unless the `error` names a file the script could not put back" in rollback


def test_preservation_is_claimed_only_after_the_check_passed():
    review = _section(_read(COMPILE), "### 7. Present the Draft for Review", "### 8.")
    # One template line: a failed check, then lines set aside unchecked, rule out the claim.
    [claim] = [line for line in review.splitlines() if "Original architecture content preserved in full" in line]
    assert claim.startswith("- {IF the last `apply` failed the check:}")
    assert "{ELSE IF its `set_aside` holds a `legacy` entry:}Every original line is preserved except" in claim
    assert claim.endswith("{ELSE:}Original architecture content preserved in full: the preservation script found "
                          "every line unchanged{END IF}")
    shown = _section(_read(REPORT), "### 2. Display Summary", "### 3.")
    assert "The original architecture content is fully preserved." not in shown
    assert ("{IF `{ranges}` is empty:}The original architecture content is preserved in full: the preservation "
            "script found every line unchanged before step 5 promoted the draft.") in shown
    assert "{IF previous_refined_path:}" in shown


def test_an_unmarked_block_set_aside_is_shown_not_claimed(tmp_path):
    # An older pass's RA: section runs to the next heading, so a paragraph of
    # the user's after it is set aside with it: every step names those lines.
    first = _section(_read(INIT), "### 1b. Set Aside an Earlier Refinement Pass", "### 2.")
    assert "when `set_aside` holds a `legacy` entry, list each one's `start`-`end` lines and `first_line`" in first
    assert "record the warning `legacy_blocks_set_aside: lines <each start-end, comma-separated>`" in first
    review = _section(_read(COMPILE), "### 7. Present the Draft for Review", "### 8.")
    assert "Every original line is preserved except lines {ranges} of `{architecture_doc}`" in review
    assert "{ranges} of `{architecture_doc}` (each `legacy` entry's `start`-`end`)" in review
    shown = _section(_read(REPORT), "### 2. Display Summary", "### 3.")
    assert "{ELSE:}Every original line is preserved except lines {ranges}" in shown
    assert "`{ranges}` from the `legacy` entries of `set_aside`" in _section(_read(REPORT), "### 1.", "### 2.")
    # The record the prose reads names the user's paragraph's lines.
    doc = tmp_path / "architecture.md"
    doc.write_bytes(b"# A\n\n## Data\n\n#### RA: X <-> Y Integration Path\n\nWe also cache in Redis.\n\n"
                    b"## API\n\n## Refinement Summary\n\nold\n")
    inspect = json.loads(_run([PRESERVATION, *_bind(_call(_read(INIT), "inspect"), {
        "architecture_doc": doc.as_posix(), "run_dir": tmp_path.as_posix()})]).stdout)
    assert inspect["set_aside"][0] == {"start": 5, "end": 8, "kind": "legacy",
                                       "first_line": "#### RA: X <-> Y Integration Path"}


def test_the_review_shows_the_summary_the_script_filled():
    review = _section(_read(COMPILE), "### 7. Present the Draft for Review", "### 8.")
    assert "{Display the `summary` of `{applyResult}`: the Refinement Summary as the draft holds it}" in review
    assert "Display the Refinement Summary section of `{draftFile}`" not in review
    summary = _section(_read(COMPILE), "### 5. Add Refinement Summary Section", "### 6.")
    assert ("the script writes the Changes Made rows as `{changes_rows}` and the Evidence Sources rows as "
            "`{evidence_rows}` from the plan's entries, `tiers`, `unverified_technologies`, `skill_count` and "
            "`vs_report`") in summary
    assert "refuses a summary that lacks `{changes_rows}` or `{evidence_rows}`" in summary
    # #1177: the run reads the in-scope skills only, so the summary counts those as its evidence.
    build = _section(_read(COMPILE), "### 6. Build the Draft", "### 7.")
    assert "`skill_count` (the number of skills in `{in_scope_skills}`, Step 02 §3" in build
    assert "the inventory's `{skill_count}`" not in build


def test_an_issue_claim_is_recorded_as_the_line_compile_anchors_on():
    claims = _section(_read(ISSUES), "### 2. Extract Integration Claims from Architecture", "### 3.")
    assert "The exact text or paraphrase from the architecture" not in claims
    assert "The claim's exact text as one line of `{analysis_doc}` holds it" in claims
    cited = _section(_read(ISSUES), "### 5. Document Each Issue", "### 6.")
    assert 'Architecture states: "{the claim\'s exact text from §2}"' in cited
    issue_anchor = _section(_read(COMPILE), "### 3. Plan the Issue Annotations", "### 4.")
    assert "exactly as Step 03 recorded it from its line of `{analysis_doc}`" in issue_anchor


def test_the_run_reads_its_clock_and_its_bindings_back():
    variables = _section(_read(SKILL_MD), "2. **Compute run-scoped variables:**", "3. **Resolve")
    assert "`timestamp` ← the output of `date -u +%Y%m%d-%H%M%S`, run once now" in variables
    assert "captured at activation time" not in variables
    reset = _section(_read(INIT), "### 3c. Reset RA State File", "### 4.")
    assert "<!-- [RA-RUN] run_dir={run_dir}" not in reset, "#1178: one binding per line, not one line"
    assert "Steps 02 to 06 read these bindings back from the block when context degrades" in reset
    for path in (COMPILE, REPORT):
        assert "the `<!-- [RA-RUN] -->` block of `{forge_data_folder}/ra-state-{project_name}.md`" in _read(path), path
        assert "as Step 01 §3c maps its keys" in _read(path), path


RUN_KEYS = ["run_dir", "timestamp", "architecture_doc", "architecture_doc_hash", "arch_project_name", "headless_mode",
            "output_folder_path", "refinement_rules_path", "previous_pass"]


def _run_block() -> str:
    """The `[RA-RUN]` block init §3c appends, as its fenced template shows it."""
    reset = _section(_read(INIT), "### 3c. Reset RA State File", "### 4.")
    m = re.search(r"```markdown\n(<!-- \[RA-RUN\]\n.*?\n-->)\n```", reset, re.DOTALL)
    assert m, "init §3c shows the [RA-RUN] block in a fence"
    return m.group(1)


def _run_block_keys() -> dict[str, str]:
    """{key: binding} for each `key={binding}` line of the block."""
    keys = {}
    for line in _run_block().splitlines()[1:-1]:
        key, sep, value = line.partition("=")
        binding = re.fullmatch(r"\{([A-Za-z_]+)\}", value)
        assert sep and binding and re.fullmatch(r"[a-z_]+", key), line
        keys[key] = binding.group(1)
    return keys


def test_the_run_block_gives_each_binding_back_whole(tmp_path):
    """#1178 architecture-1: one `key=value` per line, the value everything after the first `=`, so a path holding
    spaces, `=` or quotes reads back whole, and a document §1b could not hash reads back an empty hash."""
    keys = _run_block_keys()
    assert list(keys) == RUN_KEYS
    reset = _section(_read(INIT), "### 3c. Reset RA State File", "### 4.")
    assert "A key's value is everything after the first `=` of its line, empty when the line ends there" in reset
    for key, binding in keys.items():
        if key != binding:
            assert f"`{key}` as `{{{binding}}}`" in reset, key
    assert "every other key as the binding of its own name" in reset
    values = {
        "run_dir": f"/home/a user/app/_bmad-output/.skf-run/{WORKFLOW}-{RUN_STAMP}",
        "timestamp": RUN_STAMP,
        "architecture_doc": '/home/a user/app/docs/arch = v2 "draft".md',
        "architecture_doc_hash": "sha256:" + "0f" * 32,
        "arch_project_name": "my app",
        "headless_mode": "false",
        "outputFolderPath": "/home/a user/app/docs/refined out",
        "refinementRulesPath": "/home/a user/app/_bmad/custom/rules=house.md",
        "previous_pass": "true",
    }
    assert set(values) == set(keys.values())
    for doc_hash in (values["architecture_doc_hash"], ""):
        bound = {**values, "architecture_doc_hash": doc_hash}
        block = _run_block()
        for binding, value in bound.items():
            block = block.replace("{" + binding + "}", value)
        state = tmp_path / "ra-state-app.md"
        state.write_bytes(f"<!-- RA state for app -->\n<!-- [RA-VS] none -->\n{block}\n".encode("utf-8"))
        text = state.read_text(encoding="utf-8")
        lines = text[text.index("<!-- [RA-RUN]"):].splitlines()
        read_back = dict(line.split("=", 1) for line in lines[1:lines.index("-->")])
        assert read_back == {key: bound[binding] for key, binding in keys.items()}


def test_every_binding_read_back_is_a_key_the_run_block_maps():
    """#1178 architecture-1: compile reads back every binding but the document's hash, report the four it uses, and
    init's resume offer the block's own keys, so none names a binding the block does not hold."""
    keys = _run_block_keys()
    bindings = set(keys.values())
    recovery = _section(_read(COMPILE), "**Context recovery check:**", "\n\n")
    compiled = re.findall(r"`\{([A-Za-z_]+)\}`", _section(
        recovery, "read what is no longer in context from the RA state file: ", " from the `<!-- [RA-RUN] -->` block"))
    # Only init's resume offer compares the document's hash.
    assert set(compiled) == bindings - {"architecture_doc_hash"}, compiled
    numbers = _section(_read(REPORT), "### 1. Load the Run's Numbers", "### 2.")
    reported = re.findall(r"`\{([A-Za-z_]+)\}`", _section(numbers, "**Run recovery:** if ", " is no longer bound"))
    assert reported == ["run_dir", "arch_project_name", "headless_mode", "outputFolderPath"]
    assert set(reported) <= bindings
    resume = _section(_read(INIT), "### 1a. Resume a Stopped Review", "### 1b.")
    conditions = _section(resume, "Only an interactive run looks for a stopped review", "Show:")
    read = set(re.findall(r"(?:its|block's) `([a-z_]+)`", conditions))
    assert read == {"headless_mode", "architecture_doc", "architecture_doc_hash", "run_dir", "timestamp"}, read
    assert read <= set(keys)
    assert "bind each key of the block as §3c maps it" in resume


def test_the_run_block_saves_no_hook_and_the_report_resolves_it_again():
    """#1178: the state file sits in the forge data folder, which a project may commit, and a personal `.user.toml`
    can set an `on_complete` hook holding a token, so the block saves no hook; report.md binds a lost
    `{onCompleteCommand}` from the customization resolver, as the other report steps do (#1116)."""
    block = _run_block()
    assert "on_complete" not in block and "onCompleteCommand" not in block, block
    reset = _section(_read(INIT), "### 3c. Reset RA State File", "### 4.")
    assert "`on_complete` as `{onCompleteCommand}`" not in reset
    assert "so Step 06 binds a lost `{onCompleteCommand}` from the customization resolver instead" in reset
    assert ("resolveCustomizationProbeOrder:\n"
            "  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-resolve-customization.py'") in _frontmatter(_read(REPORT))
    hook = _section(_read(REPORT), "### 5. Post-Completion Hook", "### 6.")
    assert hook.split("\n\n")[1] == (
        "When `{onCompleteCommand}` is not bound, bind it to the `workflow.on_complete` value this prints, or to the "
        "one in `{skill-root}/customize.toml` when the resolver cannot run (resolve `{resolveCustomizationHelper}` "
        "from `{resolveCustomizationProbeOrder}` when it is not bound, first existing path wins):")
    assert hook.split("\n\n")[2] == ("```bash\nuv run {resolveCustomizationHelper} --skill {skill-root} "
                                     "--project-root {project-root} --key workflow.on_complete\n```")
    assert "[RA-RUN]" not in hook and "RA state file" not in hook
    assert "onCompleteCommand" not in _section(_read(REPORT), "### 1. Load the Run's Numbers", "### 2.")


def test_an_interactive_run_offers_to_resume_a_stopped_review():
    """#1178 enhancement-5: the issue's first option, a resume offer, not a single-pass line in SKILL.md. Only an
    interactive run asks, between §1 and §1b, and only for a review of the same, unchanged document whose plan,
    apply record and draft are still there; [R] binds the stopped run, checks the rules and hands compile the kept
    plan, and a halt it can reach points at [N]."""
    init = _read(INIT)
    assert (init.index("### 1. Accept Input Documents") < init.index("### 1a. Resume a Stopped Review")
            < init.index("### 1b. Set Aside an Earlier Refinement Pass") < init.index("### 3c. Reset RA State File"))
    assert "draftFile: '{forge_data_folder}/.skf-ra-draft-{project_name}.md'" in _frontmatter(init)
    resume = _section(init, "### 1a. Resume a Stopped Review", "### 1b.")
    assert resume.split("\n\n")[1] == ("Only an interactive run looks for a stopped review: a headless run skips this "
                                       "section and always starts a new run.")
    conditions = [line for line in resume.splitlines() if line.startswith("- ") and not line.startswith("- IF ")]
    leads = ("- the state file holds that block with every key §3c writes, and its `headless_mode` is `false`",
             "- its `architecture_doc` names the same file as `{architecture_doc}`",
             "- the folder its `run_dir` names holds `insertion-plan.json` and `apply.json`",
             "- `{draftFile}` exists: step 5's [X] deletes the draft and its [C] moves it into place",
             "- the document is as that run read it")
    assert len(conditions) == len(leads) and all(c.startswith(lead) for c, lead in zip(conditions, leads)), conditions
    assert "a block an older version wrote on one line lacks keys" in conditions[0]
    for needle in ("Otherwise say nothing and go on to §1b.", "`{stopped_timestamp}` is the block's `timestamp`"):
        assert needle in resume, needle
    offer = _section(resume, '"**A review of this document stopped before it finished.**', "\n\n")
    for needle in ("Resuming rebuilds that draft from the plan and shows the review again with that run's settings: "
                   "its scope, its [VS] report, its output folder and its refinement rules, so the report you chose",
                   "so the report you chose above and `--scope-skills` do not apply to it",
                   "A new run reads the skills again and builds a new draft, and leaves that run's folder as it is."):
        assert needle in offer, needle
    assert "replaces both" not in offer, "[N] leaves the stopped plan in its folder"
    [menu] = [line for line in resume.splitlines() if "**Select:**" in line]
    assert menu == ("Display: **Select:** [R] Resume the review of the draft from {stopped_timestamp} | "
                    "[N] Start a new run")
    branches = [line for line in resume.splitlines() if line.startswith("- IF ")]
    leads = ("- IF R:", "- IF N:", "- IF cancel / exit / [X] / q / :q:", "- IF anything else:")
    assert len(branches) == len(leads) and all(b.startswith(lead) for b, lead in zip(branches, leads)), branches
    steps = ('rm -rf "{run_dir}"', "bind each key of the block as §3c maps it",
             "add it to that folder's run sink", "run §4's `rules` check", "set `{resumed_review}` to true",
             "execute `references/compile.md`")
    at = [branches[0].lower().index(step.lower()) for step in steps]
    assert at == sorted(at), steps
    assert "§1's report answer and `--scope-skills` do not apply" in branches[0]
    # The rules the review binds are the stopped run's, so the halt names [N], not removing the override.
    assert ('its message ends "Fix that copy, or run [RA] again and choose [N] to start a new run." in place of its '
            "last sentence") in branches[0]
    rules = _section(init, "### 4. Check the Refinement Rules", "### 5.")
    assert rules.count("or remove that override.") == 1, "the last sentence a resumed review replaces"
    assert "leave the stopped run folder as it is and go on to §1b" in branches[1]
    assert "Once §3c replaces the state file, that review can no longer be resumed." in branches[1]
    assert 'HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `init:resume`' in branches[2]
    assert "GATE [default:" not in resume, "headless never reaches it (test-skf-headless-gates INTERACTIVE_ONLY)"
    [gates] = [line for line in _read(SKILL_MD).splitlines() if line.startswith("| **Gates** |")]
    assert "| step 1: Input Gate [use args], Resume Gate [R]/[N] (interactive) | step 2:" in gates
    # Compile rebuilds the draft from the kept plan, after reading every binding back, then shows the review.
    base = _section(_read(COMPILE), "### 1. Prepare the Original as Base", "### 2.")
    resumed = _section(base, "**A resumed review.**", "\n\n")
    assert base.index("**Context recovery check:**") < base.index("**A resumed review.**")
    assert "When `{resumed_review}` is true (Step 01 §1a resumed a stopped review)" in resumed
    assert (resumed.index("run §6's `apply` on the kept `{planFile}` without writing the plan again")
            < resumed.index("handle its exit code as §6 says") < resumed.index("go to §7"))
    assert ("On an exit 2 whose `error` names `{planFile}`, write the plan again through §2 to §5, from the findings "
            "the recovery check read back") in resumed
    recovery = _section(base, "**Context recovery check:**", "\n\n")
    assert ('In a resumed review (Step 01 §1a), the message ends instead with "Re-run [RA] and choose [N] when it '
            'offers to resume this review: [R] would read the same state file again."') in recovery
    assert "single-pass" not in _read(SKILL_MD).lower()


def test_a_review_resumes_only_on_the_document_its_run_read(tmp_path):
    """#1178 review loop 1: the kept plan's anchors come from the stopped run's copy of the document, so init hashes
    the document, records the hash, and offers a resume only while the document hashes the same; an edited one
    gets one line and a new run. The documented call gives one document one hash and an edit another."""
    init = _read(INIT)
    probes = ("hashContentProbeOrder:\n"
              "  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'\n"
              "  - '{project-root}/src/shared/scripts/skf-hash-content.py'\n")
    assert probes in _frontmatter(init) + "\n" and HASH_CONTENT.is_file()
    first = _section(init, "### 1b. Set Aside an Earlier Refinement Pass", "### 2.")
    hashed = first[first.index("**Hash the document.**"):]
    assert "Bind `{architecture_doc_hash}` ← the `content_hash` it prints" in hashed
    assert "bind it empty and go on" in hashed
    keys = _run_block_keys()
    assert list(keys).index("architecture_doc_hash") == list(keys).index("architecture_doc") + 1
    resume = _section(init, "### 1a. Resume a Stopped Review", "### 1b.")
    [condition] = [line for line in resume.splitlines() if line.startswith("- the document is as that run read it")]
    assert "run §1b's call, `uv run {hashContentHelper} hash \"{architecture_doc}\"`" in condition
    assert "a `content_hash` that is not empty and equals the block's `architecture_doc_hash`" in condition
    notice = _section(resume, "Otherwise say nothing and go on to §1b.", "\n\n")
    assert "when the first four hold and only the last does not (the hashes differ, or either is empty)" in notice
    assert ('say "A review of this document stopped before it finished, but the document changed after that run '
            'read it, or cannot be compared with it, so this run starts over." and go on to §1b') in notice
    call = _helper_call(init, "hashContentHelper", "hash")
    arch = tmp_path / "my docs" / "architecture.md"
    arch.parent.mkdir()
    arch.write_bytes(ARCH.encode("utf-8"))

    def content_hash() -> str:
        proc = _run([HASH_CONTENT, *_bind(call, {"architecture_doc": arch.as_posix()})])
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)["content_hash"]

    stopped = content_hash()
    assert stopped.startswith("sha256:") and content_hash() == stopped, "an unchanged document is offered"
    arch.write_bytes(ARCH.replace("Loro stores documents.", "Loro stores and syncs documents.").encode("utf-8"))
    assert content_hash() != stopped, "an edited document is not"


def test_the_resume_conditions_follow_what_apply_and_promote_leave(tmp_path):
    """#1178: init's offer reads files the documented calls leave. A plan apply refuses writes no apply.json and no
    draft, the kept plan rebuilds the same draft, the promotion moves the draft away and [X] deletes it, so a review
    that ended either way is never offered again, while a promotion the check refuses keeps the draft (review loop 2)."""
    resume = _section(_read(INIT), "### 1a. Resume a Stopped Review", "### 1b.")
    assert "holds `insertion-plan.json` and `apply.json`" in resume and "`{draftFile}` exists" in resume
    assert "while a [C] whose `promote` halted keeps it for the resumed review to approve again" in resume
    compile_text = _read(COMPILE)
    compile_files = _frontmatter(compile_text)
    for name in ("planFile: '{run_dir}/insertion-plan.json'", "applyResult: '{run_dir}/apply.json'",
                 "draftFile: '{forge_data_folder}/.skf-ra-draft-{project_name}.md'"):
        assert name in compile_files, name
    cancel = [line for line in compile_text.splitlines() if line.startswith("- IF cancel / exit / [X] / q / :q:")]
    assert len(cancel) == 1 and 'delete the draft (`rm -f "{draftFile}"`)' in cancel[0]
    run_dir = _run_dir(tmp_path)
    forge, docs = tmp_path / "forge", tmp_path / "docs"
    forge.mkdir()
    docs.mkdir()
    arch = tmp_path / "architecture.md"
    arch.write_bytes(ARCH.encode("utf-8"))
    draft = forge / ".skf-ra-draft-app.md"
    values = {"architecture_doc": arch.as_posix(), "run_dir": run_dir.as_posix(), "timestamp": RUN_STAMP,
              "draftFile": draft.as_posix(), "outputFile": (docs / "refined-architecture-app.md").as_posix(),
              "planFile": (run_dir / "insertion-plan.json").as_posix(),
              "applyResult": (run_dir / "apply.json").as_posix(),
              "promoteResult": (run_dir / "promote.json").as_posix()}
    rules = json.loads(_run([PRESERVATION, *_bind(_call(_read(INIT), "rules"), {
        "refinementRulesData": (REFERENCES / "refinement-rules.md").as_posix()})]).stdout)
    summary = "## Refinement Summary\n\n{changes_rows}\n\n{evidence_rows}\n"
    plan = {"entries": [{"id": "gap-1", "kind": "gap", "anchor": "## No Such Section", "skills": ["loro", "fastapi"],
                         "block": "#### RA: Loro <-> FastAPI Integration Path"}],
            "summary": summary, "unverified_technologies": [], "skill_count": 2, "tiers": rules["tiers"]}
    (run_dir / "insertion-plan.json").write_bytes(json.dumps(plan).encode("utf-8"))
    refused = _run([PRESERVATION, *_bind(_call(compile_text, "apply"), values)])
    assert refused.returncode == 1 and json.loads(refused.stdout)["status"] == "problems", refused.stdout
    assert not (run_dir / "apply.json").exists() and not draft.exists(), "no offer for a plan that built nothing"
    plan["entries"][0]["anchor"] = "## Data Layer"
    (run_dir / "insertion-plan.json").write_bytes(json.dumps(plan).encode("utf-8"))
    built = _run([PRESERVATION, *_bind(_call(compile_text, "apply"), values)])
    assert built.returncode == 0, built.stdout
    assert (run_dir / "apply.json").is_file() and draft.is_file(), "the offer's files are there"
    first = draft.read_bytes()
    draft.unlink()
    # [R]: compile runs apply on the kept plan, which writes the same draft again.
    again = _run([PRESERVATION, *_bind(_call(compile_text, "apply"), values)])
    assert again.returncode == 0, again.stdout
    assert draft.read_bytes() == first
    # A [C] whose promote halts keeps the draft, so that review is offered again.
    draft.write_bytes(first.replace(b"Loro stores documents.", b""))
    kept = _run([PRESERVATION, *_bind(_call(compile_text, "promote"), values)])
    assert kept.returncode == 1 and draft.is_file(), kept.stdout
    draft.write_bytes(first)
    promoted = _run([PRESERVATION, *_bind(_call(compile_text, "promote"), values)])
    assert promoted.returncode == 0, promoted.stdout
    assert not draft.exists(), "a review that ended with [C] leaves no draft to resume"


def test_the_stages_table_marks_every_gate():
    stages = _section(_read(SKILL_MD), "## Stages", "## Invocation Contract")
    assert "| 1 | Initialize & Load Inputs | references/init.md | No (input gate) |" in stages
    assert "| 5 | Compile Refined Architecture | references/compile.md | No (review) |" in stages
    assert "| 6 | Report | references/report.md | Yes |" in stages


def test_the_rules_file_leaves_preservation_to_the_script():
    rules = _read(REFERENCES / "refinement-rules.md")
    assert "## Preservation Rules" not in rules and 'prefix added subsections with "RA:"' not in rules
    assert "compile.md and `scripts/skf-check-preservation.py` own them" in rules


def test_steps_2_to_4_read_the_analysis_copy():
    first = _section(_read(INIT), "### 1b. Set Aside an Earlier Refinement Pass", "### 2.")
    assert ('uv run {preservationScript} inspect --doc "{architecture_doc}" --stripped "{run_dir}/analysis-doc.md" '
            '-o "{run_dir}/inspect.json"') in first
    assert "Bind `{analysis_doc}` ← `{run_dir}/analysis-doc.md`" in first
    init = _read(INIT)
    assert init.index("### 1b.") < init.index("### 3c. Reset RA State File")
    assert 'mentions --doc "{analysis_doc}"' in _read(GAP)
    assert "no inventory skill covers, read in `{analysis_doc}`" in _read(GAP)
    for path in (ISSUES, IMPROVEMENTS):
        assert "`{analysis_doc}`, the copy Step 01 §1b wrote" in _read(path), _rel(path)


def test_the_next_steps_state_the_accept_convention():
    # A refinement is kept by moving it into the user's prose; anything left
    # between RA markers is replaced on the next pass, and deleting a block
    # does not keep a later run from finding the same thing again.
    steps = _section(_read(REPORT), "### 3. Present Next Steps", "### 4.")
    assert "to accept a refinement, move what you keep into your own prose" in steps
    assert "Anything still between RA markers is replaced the next time you run [RA] on this document" in steps
    assert "a later [RA] run that finds the same thing again adds it back" in steps


# --- The terminal sequence -------------------------------------------------------------------


def test_report_writes_the_contract_then_the_hook_then_finishes():
    text = _read(REPORT)
    contract = text.index("### 4. Result Contract")
    hook = text.index("### 5. Post-Completion Hook")
    finish = text.index("### 6. Hand Off to the Health Check")
    assert contract < hook < finish
    emit = ('uv run {emitEnvelopeHelper} emit --workflow skf-refine-architecture --run-dir "{run_dir}" '
            '--result-dir "{outputFolderPath}" < "{run_dir}/result-context.json"')
    assert emit in text
    contract = _section(text, "### 4. Result Contract", "### 5.")
    assert "{timestamp}" not in contract, "the emitter names the files"
    assert "mkdir" not in contract, "promote already put the refined document in that folder"
    # The payload comes from the script's records, never typed.
    numbers = _section(text, "### 1. Load the Run's Numbers", "### 2.")
    assert ('uv run {preservationScript} context --inspect "{inspectResult}" --apply "{applyResult}" '
            '--promote "{promoteResult}" --out "{run_dir}/result-context.json"') in numbers
    assert "```json" not in text


def test_the_hook_gets_the_emitters_result_path_and_its_failure_is_shown():
    hook = _section(_read(REPORT), "### 5. Post-Completion Hook", "### 6.")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook
    assert "When `{result_path}` is null, skip it too" in hook
    assert '"**Warning:** on_complete failed: {reason}"' in hook and "on its own line of this report" in hook
    assert "Bind `{result_path}` ← the line's `result_path`" in _read(REPORT)


def test_a_headless_run_hands_its_line_to_the_health_check():
    """#1113: §4 binds `{result_envelope_line}` to the emitter's line instead of displaying it, so the shared health
    check displays it as the run's last line, and still binds `{result_path}` from the same line for the hook."""
    report = _read(REPORT)
    contract = _section(report, "### 4. Result Contract", "### 5.")
    bind = ("When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here: the "
            "shared health check displays it verbatim as the run's last line (the line the retry below prints when the "
            "first run printed none).")
    assert bind in contract
    assert (contract.index("prints the `SKF_REFINE_ARCHITECTURE_RESULT_JSON:` line on stdout") < contract.index(bind)
            < contract.index("Bind `{result_path}` ← the line's `result_path`"))
    # An emitter that fails twice still halts here, on its own line, and never reaches the health check.
    assert contract.index(bind) < contract.index(
        'if it fails again, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:result-contract`')
    assert "display the line verbatim" not in report
    relay = _read(REFERENCES / "health-check.md")
    assert ("In a headless run report.md §4 bound `{result_envelope_line}` to the "
            "`SKF_REFINE_ARCHITECTURE_RESULT_JSON` line without displaying it: the shared health check displays that "
            "line verbatim as the run's last line") in relay
    result = _section(_read(SKILL_MD), "## Result Contract (Headless)", "## On Activation")
    # Said at no cost to the SKILL.md budget: "a run ends on one" replaces "step 6 prints one".
    assert ("When `{headless_mode}` is true, a run ends on one `SKF_REFINE_ARCHITECTURE_RESULT_JSON: {...}` line on "
            "**stdout**, and every HARD HALT one on **stderr**") in result
    envelope = _section(_read(REFERENCES / "exit-codes.md"), "## Result Envelope", "## Emitting a Halt")
    assert ("line on **stdout** when it writes the result contract, which the shared health check (step 7) displays "
            "as the run's last line, and every HARD HALT prints one on **stderr**") in envelope


def test_the_report_finishes_the_run_without_a_menu():
    # A menu after the approval could not act on the document, so step 6
    # asks nothing: the walkthrough is [R] at step 5's review gate.
    finish = _section(_read(REPORT), "### 6. Hand Off to the Health Check", "the true terminal step")
    assert "**Select:**" not in finish and "[X]" not in finish and "GATE" not in finish
    assert 'rm -rf "{run_dir}"' in finish
    assert "Headless auto-selects" not in _read(REPORT)
    rule = [line for line in _read(SKILL_MD).splitlines() if line.startswith("- At any interactive prompt")][0]
    assert "final menu" not in rule and rule.rstrip().endswith('(`halt_reason: "user-cancelled"`)')
    exit_6 = _exit_code_rows()[6]
    assert "final menu" not in exit_6 and "step 5 review gate `[X]`" in exit_6


def test_report_takes_every_count_from_the_build_record():
    numbers = _section(_read(REPORT), "### 1. Load the Run's Numbers", "### 2.")
    assert "the Evidence Sources from `evidence` of `{applyResult}`" in numbers
    assert "`unverified_count` from `counts.unverified`" in numbers
    assert "`previous_refined_path` from the `previous` of `{promoteResult}`" in numbers
    assert "`unverified_technologies` from its `unverified_technologies`" in numbers
    # The headless counts reach the result line through the `context` payload, never typed.
    assert "every count from `{applyResult}`" in _section(_read(REPORT), "### 4. Result Contract", "### 5.")
    assert "[RA-SCOPE]" not in numbers, "the names come from the list the count was taken from"
    assert "Extract metrics from the Refinement Summary" not in _read(REPORT)
    frontmatter = _frontmatter(_read(REPORT))
    for key, path in (("applyResult", "{run_dir}/apply.json"), ("promoteResult", "{run_dir}/promote.json"),
                      ("inspectResult", "{run_dir}/inspect.json")):
        assert f"{key}: '{path}'" in frontmatter, key


# --- The rules check and the verdict join, as documented --------------------------------------

VS_REPORT = """---
schemaVersion: "1.0"
reportType: feasibility
overallVerdict: "CONDITIONALLY_FEASIBLE"
generatedAt: "2026-10-01T09:00:00Z"
---

# Feasibility Report

## Executive Summary

Summary.

## Coverage Analysis

Coverage.

## Integration Verdicts

| lib_a | lib_b | verdict | rationale |
|-------|-------|---------|-----------|
| loro | yjs | Blocked | no bridge |
| cycle | loro \u2192 yjs \u2192 loro | Risky | circular integration dependency detected |
| loro | fastapi | Risky | fastapi is out of scope |

## Recommendations

Recommendations.

## Evidence Sources

Sources.
"""


def test_the_documented_rules_and_verdicts_calls_run(tmp_path):
    run_dir = _run_dir(tmp_path)
    rules = (REFERENCES / "refinement-rules.md").as_posix()
    checked = _run([PRESERVATION, *_bind(_call(_read(INIT), "rules"), {"refinementRulesData": rules})])
    assert checked.returncode == 0, checked.stdout
    tiers = json.loads(checked.stdout)["tiers"]
    assert tiers == {"issue": ["Critical", "Major", "Minor"], "improvement": ["High", "Medium", "Low"]}
    report = tmp_path / "feasibility-report-app-latest.md"
    report.write_bytes(VS_REPORT.encode("utf-8"))
    # Step 01 section 2 writes the terms both helpers read, with the enumerate helper's `terms` (#1177).
    (run_dir / "skill-inventory.json").write_bytes(json.dumps({"skills": [
        {"name": "loro", "source_repo_basename": "loro", "source_root_basename": None},
        {"name": "yjs", "source_repo_basename": None, "source_root_basename": None},
        {"name": "fastapi", "source_repo_basename": "fastapi", "source_root_basename": "fastapi"},
    ]}).encode("utf-8"))
    terms_argv = _bind(_helper_call(_read(INIT), "enumerateStackSkillsHelper", "terms"),
                       {"run_dir": run_dir.as_posix()})
    written = _run([ENUMERATE, *terms_argv])
    assert written.returncode == 0, written.stderr
    assert json.loads((run_dir / "skill-terms.json").read_bytes().decode("utf-8")) == [
        {"name": "loro", "aliases": []}, {"name": "yjs", "aliases": []}, {"name": "fastapi", "aliases": []}]
    values = {"vs_report_path": report.as_posix(), "vs_generated_at": "2026-10-01T09:00:00Z",
              "run_dir": run_dir.as_posix(), "in_scope_names": "loro,yjs", "refinementRulesData": rules}
    joined = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert joined.returncode == 0, joined.stdout
    result = json.loads(joined.stdout)
    assert [(r["skill_a"], r["skill_b"], r["raises"]) for r in result["in_scope"]] == [("loro", "yjs", "Critical")]
    assert [(r["lib_a"], r["reason"]) for r in result["out_of_scope"]] == [("cycle", "no-inventory-skill"),
                                                                          ("loro", "out-of-scope")]
    # Terms that are gone exit 2 naming the file: issue detection writes them again with the same call, then reruns.
    (run_dir / "skill-terms.json").unlink()
    lost = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert lost.returncode == 2 and "skill-terms.json" in json.loads(lost.stdout)["error"]
    rerun_argv = _bind(_helper_call(_read(ISSUES), "enumerateStackSkillsHelper", "terms"),
                       {"run_dir": run_dir.as_posix()})
    assert rerun_argv == terms_argv
    assert _run([ENUMERATE, *rerun_argv]).returncode == 0
    again = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert again.returncode == 0 and json.loads(again.stdout)["in_scope"] == result["in_scope"]
    # A report [VS] rewrote during the run is stale: exit 1, which the step turns into exit 8.
    values["vs_generated_at"] = "2026-09-30T09:00:00Z"
    stale = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert stale.returncode == 1 and json.loads(stale.stdout)["status"] == "stale"


# Ten skills SKF generated, with the source each was built from (None: no source recorded).
SKILL_SOURCES = {
    "oms-cognee": ("https://github.com/topoteretes/cognee.git", "cognee"),
    "react": ("facebook/react", None),
    "zod": (None, None),
    "loro": ("loro-dev/loro", "crates/loro-internal"),
    "yjs": ("https://github.com/yjs/yjs", None),
    "automerge": ("automerge/automerge", "rust/automerge"),
    "fastapi": ("tiangolo/fastapi", "FastAPI"),
    "vite": ("vitejs/vite", "packages/vite"),
    "tauri": ("tauri-apps/tauri", None),
    "surrealdb": ("surrealdb/surrealdb", "lib"),
}


def _skf_skills(root: Path) -> None:
    for name, (repo, source_root) in SKILL_SOURCES.items():
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_bytes(f"# {name}\n".encode("utf-8"))
        metadata = {"generated_by": "create-skill", "exports": [f"{name}Export"]}
        if repo is not None:
            metadata["source_repo"] = repo
        if source_root is not None:
            metadata["source_root"] = source_root
        (folder / "metadata.json").write_bytes(json.dumps(metadata).encode("utf-8"))


def _hand_terms(inventory: dict) -> list[dict]:
    """The array gap analysis staged by hand before #1177: each entry's source basenames that are not null, with
    the repeats the helper now drops (an alias equal to the name or to an earlier alias, ignoring case)."""
    terms = []
    for entry in inventory["skills"]:
        aliases: list[str] = []
        for alias in (entry["source_repo_basename"], entry["source_root_basename"]):
            if alias is not None and alias.casefold() not in {entry["name"].casefold(), *map(str.casefold, aliases)}:
                aliases.append(alias)
        terms.append({"name": entry["name"], "aliases": aliases})
    return terms


def test_the_documented_terms_and_scope_calls_run(tmp_path):
    # #1177 determinism-2 and architecture-5: init writes the terms with the helper, and gap analysis splits every
    # unique pair of the saved inventory, so `pair_count` is the identity of `{skill_count}`.
    run_dir = _run_dir(tmp_path)
    skills = tmp_path / "skills"
    _skf_skills(skills)
    enumerate_argv = _bind(_helper_call(_read(INIT), "enumerateStackSkillsHelper", "enumerate"),
                           {"skills_output_folder": skills.as_posix()})
    assert "--pairs" not in enumerate_argv
    enumerated = _run([ENUMERATE, *enumerate_argv])
    assert enumerated.returncode == 0, enumerated.stderr
    (run_dir / "skill-inventory.json").write_bytes(enumerated.stdout.encode("utf-8"))
    inventory = json.loads(enumerated.stdout)
    skill_count = inventory["skill_count"]
    assert skill_count == len(SKILL_SOURCES) and "pairs" not in inventory

    terms = _run([ENUMERATE, *_bind(_helper_call(_read(INIT), "enumerateStackSkillsHelper", "terms"),
                                    {"run_dir": run_dir.as_posix()})])
    assert terms.returncode == 0, terms.stderr
    written = json.loads((run_dir / "skill-terms.json").read_bytes().decode("utf-8"))
    assert written == json.loads(terms.stdout) == _hand_terms(inventory)
    by_name = {entry["name"]: entry["aliases"] for entry in written}
    assert by_name["oms-cognee"] == ["cognee"] and by_name["react"] == [] and by_name["zod"] == []
    assert by_name["loro"] == ["loro-internal"] and by_name["fastapi"] == []

    scope = _helper_call(_read(GAP), "enumerateStackSkillsHelper", "scope")

    def split(in_scope_names: str) -> dict:
        proc = _run([ENUMERATE, *_bind(scope, {"run_dir": run_dir.as_posix(), "in_scope_names": in_scope_names})])
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    # Ten skills, three in scope: section 4 reads three surfaces and section 5 judges three pairs.
    result = split("loro,yjs,automerge")
    assert result["pair_count"] == skill_count * (skill_count - 1) // 2 == 45
    assert result["in_scope"] == ["automerge", "loro", "yjs"] and len(result["out_of_scope"]) == 7
    assert result["in_scope_pair_count"] == 3 and result["out_of_scope_pair_count"] == 42
    # The safe default passes no name, then runs the call again with the first result's out_of_scope names.
    first = split("")
    assert first["in_scope"] == [] and first["in_scope_pairs"] == []
    # A name the rerun's hand-copied list drops comes back in out_of_scope, which section 3 then runs again for.
    dropped = split(",".join(first["out_of_scope"][1:]))
    assert dropped["out_of_scope"] == first["out_of_scope"][:1]
    every = split(",".join(first["out_of_scope"]))
    assert every["out_of_scope"] == [] and every["out_of_scope_pairs"] == []
    assert every["in_scope_pair_count"] == every["pair_count"] == skill_count * (skill_count - 1) // 2


def test_the_documented_exports_call_runs(tmp_path):
    # #1176: issue detection §3 looks each claim §2 staged up with one call, never by hand.
    run_dir = _run_dir(tmp_path)
    inventory = {"skills": [
        {"name": "loro", "exports": ["LoroDoc", "LoroText"], "exports_source": "metadata",
         "source_repo_basename": "loro-crdt", "source_root_basename": None},
        {"name": "stack-app", "exports": [], "exports_source": "metadata", "source_repo_basename": None,
         "source_root_basename": None},
    ], "warnings": []}
    (run_dir / "skill-inventory.json").write_bytes(json.dumps(inventory).encode("utf-8"))
    claims = [{"skill": "loro", "claimed": "`LoroDoc.import(bytes)`"}, {"skill": "loro-crdt", "claimed": "LoroText"},
              {"skill": "loro", "claimed": "LoroTree::create()"}, {"skill": "stack-app", "claimed": "mount"},
              {"skill": "automerge", "claimed": "merge"}]
    (run_dir / "claimed-names.json").write_bytes(json.dumps(claims).encode("utf-8"))
    argv = _bind(_call(_read(ISSUES), "exports"), {"run_dir": run_dir.as_posix()})
    proc = _run([PRESERVATION, *argv])
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    assert [(r["name"], r["status"]) for r in result["results"]] == [
        ("import", "member-unlisted"), ("LoroText", "present"), ("create", "absent"), ("mount", "list-empty"),
        ("merge", "unknown-skill")]
    # An inventory that is no longer one exits 2 naming it, which the step turns into exit 8.
    (run_dir / "skill-inventory.json").write_bytes(b"{}")
    proc = _run([PRESERVATION, *argv])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["error"].startswith((run_dir / "skill-inventory.json").as_posix())


def _customize_comment(key: str) -> str:
    """The comment above `key = ...` in customize.toml, `#` markers dropped, as one line."""
    text = _read(SKILL / "customize.toml")
    block = text[: text.index(f"\n{key} =")].rsplit("\n\n", 1)[-1]
    return " ".join(line.lstrip("#").strip() for line in block.splitlines())


def test_the_path_settings_are_named_from_the_project_root():
    """#1108: a bare path resolves from the installed skill's folder, which every update replaces, so both path
    comments and the docs name a copy or a folder from {project-root} and show one."""
    rules = _customize_comment("refinement_rules_path")
    assert ("Keep the copy outside the skill folder, which every update overwrites, and name it as "
            "{project-root}/<path to the copy>, e.g. {project-root}/_bmad/custom/refinement-rules.md.") in rules
    folder = _customize_comment("output_folder_path")
    assert ("Name it as {project-root}/<folder>, e.g. {project-root}/docs/architecture; a bare path resolves from "
            "the skill folder, which every update deletes.") in folder
    docs = _read(REPO / "docs" / "workflows.md").splitlines()
    [output] = [line for line in docs if line.startswith("- Refine Architecture `output_folder_path`:")]
    assert ("Name it as `{project-root}/<folder>`, such as `{project-root}/docs/architecture`: a bare path "
            "resolves from the installed skill's folder, which every update deletes.") in output
    [copy] = [line for line in docs if line.startswith("- Refine Architecture `refinement_rules_path`:")]
    assert ("Keep it outside the skill folder, which every update overwrites, and name it as "
            "`{project-root}/<path to the copy>`, such as `{project-root}/_bmad/custom/refinement-rules.md`.") in copy
