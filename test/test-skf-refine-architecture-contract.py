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
  read the run's bindings back from the RA state file;
- every halt_reason, emitted through the documented command (and On
  Activation's heredoc, before the run folder exists), prints a line that
  validates, whose run_id is the run's timestamp;
- every decision a gate documents is one the schema accepts, and every
  warning a step records is a fixed code the schema names;
- the documented pipeline runs on a fixture: init's inspect sets an earlier
  pass aside, compile's apply builds the draft and promote renames the earlier
  output, and the result payload report.md stages from their records writes
  the result files with the gates' decisions;
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
- init's documented `rules` call and issue detection's `verdicts` call run
  as written on a fixture, with the bindings the steps give them.
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
    # so SKILL.md stays within its budget and no copy of them drifts.
    skill = _read(SKILL_MD)
    assert "## Exit Codes" not in skill and "**Emitting a halt.**" not in skill
    assert "| **Exit codes** | See `references/exit-codes.md` |" in skill
    contract = _section(skill, "## Result Contract (Headless)", "## On Activation")
    assert "`references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command" in contract
    for path in sorted(REFERENCES.glob("*.md")):
        if HALT_RE.search(_read(path)):
            assert "(`references/exit-codes.md` describes the envelope)" in _read(path), _rel(path)


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


def test_every_halt_names_its_phase():
    for path, _, reason, phase in _halts():
        m = re.fullmatch(r" at phase `([a-z-]+):([a-z0-9-]+)`", phase)
        assert m, f"{_rel(path)}: a {reason} HALT names no phase"
        assert m.group(1) == PHASE_PREFIX[path.name], (_rel(path), m.group(0))


def test_each_halting_stage_binds_the_emitter_and_shows_the_command():
    stages = [path for path in sorted(REFERENCES.glob("*.md")) if HALT_RE.search(_read(path))]
    assert {path.name for path in stages} == {"init.md", "gap-analysis.md", "issue-detection.md", "compile.md",
                                               "report.md"}
    for path in stages:
        text = _read(path)
        assert EMIT_PROBES in _frontmatter(text) + "\n", _rel(path)
        assert "**Halt envelope.**" in text and EMIT_HALT in text, _rel(path)
        assert "resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound" in text
    # SKILL.md resolves it before the first prompt, where its own halts run.
    activation = _section(_read(SKILL_MD), "5. **Pre-flight", "6. Load")
    assert ("Resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, "
            "else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`") in activation
    assert activation.index("**The emitter.**") < activation.index("**Config-completeness")


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
    # The run folder comes last in the pre-flight, after every halt that cannot use it.
    pre = _section(activation, "5. **Pre-flight", "6. Load")
    assert pre.index("**Write probe") < pre.index("**Run folder (exit 4).**")
    assert 'mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"' in pre
    assert ("`run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-refine-architecture-{timestamp}`"
            in _section(activation, "2. **Compute run-scoped variables:**", "3. **Resolve"))


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

    inspect = _run([PRESERVATION, *_bind(_call(_read(INIT), "inspect"), values)])
    assert inspect.returncode == 0, inspect.stdout
    assert (run_dir / "analysis-doc.md").read_bytes() == ARCH.encode("utf-8")

    summary = "\n".join(line for line in _section(_read(COMPILE), "| Category | Count | Breakdown |", "\n\n")
                        .splitlines()[:5])
    summary = "## Refinement Summary\n\n" + summary
    plan = {"entries": [
        {"id": "gap-1", "kind": "gap", "anchor": "## Data Layer", "skills": ["loro", "fastapi"],
         "block": "#### RA: Loro <-> FastAPI Integration Path\n\n> [!NOTE] **Gap Identified by Refine Architecture**"},
        {"id": "issue-1", "kind": "issue", "tier": "Major", "anchor": "The API uses FastAPI.", "skills": ["fastapi"],
         "block": "> [!WARNING] **Issue Detected by Refine Architecture** (Major)"},
    ], "summary": summary, "unverified_technologies": [], "skill_count": 2}
    (run_dir / "insertion-plan.json").write_bytes(json.dumps(plan).encode("utf-8"))
    apply = _run([PRESERVATION, *_bind(_call(_read(COMPILE), "apply"), values)])
    assert apply.returncode == 0, apply.stdout
    promote = _run([PRESERVATION, *_bind(_call(_read(COMPILE), "promote"), values)])
    assert promote.returncode == 0, promote.stdout
    previous = docs / f"refined-architecture-app-{RUN_STAMP}.md"
    assert previous.read_bytes() == b"# my earlier curated refinement\n"
    assert "| Gaps Filled | 1 |" in output.read_text(encoding="utf-8")

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
    assert "`{unverified_count}` and `{unverified_technologies}` from its `unverified_technologies`" in summary


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
    assert ("<!-- [RA-RUN] run_dir={run_dir} timestamp={timestamp} architecture_doc={architecture_doc} "
            "arch_project_name={arch_project_name} -->") in reset
    for path in (COMPILE, REPORT):
        assert "the `<!-- [RA-RUN] -->` block of `{forge_data_folder}/ra-state-{project_name}.md`" in _read(path), path


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
    finish = text.index("### 6. Finish the Run")
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


def test_the_report_finishes_the_run_without_a_menu():
    # A menu after the approval could not act on the document, so step 6
    # asks nothing: the walkthrough is [R] at step 5's review gate.
    finish = _section(_read(REPORT), "### 6. Finish the Run", "the true terminal step")
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
    # Step 02 section 2 stages the terms both helpers read.
    (run_dir / "skill-terms.json").write_bytes(json.dumps(
        [{"name": "loro", "aliases": []}, {"name": "yjs", "aliases": []}, {"name": "fastapi", "aliases": []}]
    ).encode("utf-8"))
    values = {"vs_report_path": report.as_posix(), "vs_generated_at": "2026-10-01T09:00:00Z",
              "run_dir": run_dir.as_posix(), "in_scope_names": "loro,yjs", "refinementRulesData": rules}
    joined = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert joined.returncode == 0, joined.stdout
    result = json.loads(joined.stdout)
    assert [(r["skill_a"], r["skill_b"], r["raises"]) for r in result["in_scope"]] == [("loro", "yjs", "Critical")]
    assert [(r["lib_a"], r["reason"]) for r in result["out_of_scope"]] == [("cycle", "no-inventory-skill"),
                                                                          ("loro", "out-of-scope")]
    # A report [VS] rewrote during the run is stale: exit 1, which the step turns into exit 8.
    values["vs_generated_at"] = "2026-09-30T09:00:00Z"
    stale = _run([PRESERVATION, *_bind(_call(_read(ISSUES), "verdicts"), values)])
    assert stale.returncode == 1 and json.loads(stale.stdout)["status"] == "stale"
