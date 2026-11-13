#!/usr/bin/env python3
"""skf-brief-skill's result envelope, halt contract and on_complete hook.

#593 (brief part): references/invocation-contract.md is the one statement
of the SKF_BRIEF_RESULT_JSON envelope. SKILL.md resolves the emitter at
activation and states the one halt command, so a halt in step 1 or 2 no
longer depends on write-brief.md, a step file the no-preload rule keeps
unloaded, and each halt site these checks cover calls the emitter where it
stops. The envelope carries the run's warnings (`workflow_warnings[]`),
and write-brief.md builds it after the QMD registration, the last step
that can raise one. The emitter takes only strings, so a helper warning
that is a {field, message} object goes in as one `field: message` line.

#585 (brief part): on_complete runs right after the envelope on the [auto]
path (step-auto-validate.md section 3), as it does in write-brief.md
section 6b; the local health-check relay stays a pure relay, and
customize.toml names both places.

#599 (brief part): a pipeline always runs BS[auto] headless, so the [auto]
validation step asks nothing: its approve, edit and reject menu is gone.
#594 and #600 (brief part): the headless input gate (headless-args.md) and
the ratify route (gather-intent-ratify.md) left gather-intent.md, so their
halts and the validators' warnings are pinned where they now live.

Step 5b round 1 (enhancement-1): a headless or [auto] run binds the success
line to `{result_envelope_line}` instead of displaying it, and the shared
health check displays it as the run's last line, so a `claude -p` caller
reads the envelope as the final message.

Step 5b gate run 3: [auto] stays a separate route by design (enhancement-1,
a written exception), and at Deep tier it runs write-brief.md section 3b's
QMD registration before its envelope; a ratified brief is written from the
file it ratified, so no step pins its version by hand (determinism-3);
the module pick stays step 2's judgment, and the prose says why
(determinism-1, a written exception).

#1112 (brief part): no brief prose names the dev-only `src/shared/` outside
a probe order, which writes it as `{project-root}/src/shared/...`.

#1118: step 1 reads the forge tier, the tool flags and `tier_override`
with one `skf-forge-tier-rw.py effective` call, resolved from the probe
order step 5 uses, never by eye: a forge-tier.yaml it finds binds `tier`,
`detected_tier`, `tier_source` and `tools`, an ignored override or an
unreadable preferences.yaml is a warning, a missing file halts
`forge-tier-missing`, and one it cannot use, a truncated one included,
takes the Quick fallback. The steps that read `tools.qmd` or `tools.ccc`
read the `tools` step 1 bound.

#1134: SKILL.md binds `{emitEnvelopeHelper}` to the shared emitter
(skf-emit-brief-result-envelope.py stays as its alias) and its Halt
Contract is a pointer. Each warning is recorded in the run sink as it is
raised, a helper's saved JSON with `--warnings-file`, text that quotes a
helper or the user through `{run_dir}/warning.txt`, so no stage keeps a
`workflow_warnings[]` list or flattens a `{field, message}` warning: the
emitter does. Each of the twenty halt sites is one `emit-halt --halt-reason`
command that reads no stdin and takes the mode and the skill name from
`{run_dir}/halt-state.json`, which step 1 §1 writes and the steps that
resolve the name rewrite; the success sites run `emit --run-dir`. SKILL.md
stays under its 2,500-token budget.

#1135: every run starts in stage 0, references/preflight.md, which holds
the old gather-intent.md §1 (run folder, halt state, forge tier) and §1b
(route by mode), so a headless or [auto] run never loads the interactive
stage and gather-intent.md starts at §2. qmd-collection-registration.md
resolves `skf-forge-tier-rw.py` itself and handles a missing one, so
write-brief.md §3b and step-auto-validate.md §3 both load it directly and
the [auto] route never loads write-brief.md; `{skill-name}` is the brief's
name. The copies other files own are cut: the tier glosses are one set,
version-resolution.md keeps its Detection Algorithm and one precedence
line, and the [auto] files say `## Goal` and `## Sequence` and state each
rule as the failure it prevents.

No test runs the step prose, so these checks pin it, and they run the
commands it documents against the emitter and validate what it prints
against the schema.
"""

from __future__ import annotations

import json
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
SKILL_DIR = REPO / "src" / "skf-brief-skill"
REFERENCES = SKILL_DIR / "references"
SKILL_MD = SKILL_DIR / "SKILL.md"
CONTRACT = REFERENCES / "invocation-contract.md"
WRITE_BRIEF = REFERENCES / "write-brief.md"
AUTO_BRIEF = REFERENCES / "step-auto-brief.md"
AUTO_VALIDATE = REFERENCES / "step-auto-validate.md"
ANALYZE_TARGET = REFERENCES / "analyze-target.md"
PREFLIGHT = REFERENCES / "preflight.md"
GATHER_INTENT = REFERENCES / "gather-intent.md"
HEADLESS_ARGS = REFERENCES / "headless-args.md"
RATIFY = REFERENCES / "gather-intent-ratify.md"
SCOPE_DEFINITION = REFERENCES / "scope-definition.md"
HEALTH_CHECK = REFERENCES / "health-check.md"
QMD_REGISTRATION = REFERENCES / "qmd-collection-registration.md"
PORTFOLIO_CHECK = REFERENCES / "portfolio-similarity-check.md"
CUSTOMIZE = SKILL_DIR / "customize.toml"
EMITTER = REPO / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
VALIDATE_BRIEF = REPO / "src" / "shared" / "scripts" / "skf-validate-brief-schema.py"
FORGE_TIER_RW = REPO / "src" / "shared" / "scripts" / "skf-forge-tier-rw.py"
SCHEMA_PATH = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-brief-result-envelope.v1.json"
PREFIX = "SKF_BRIEF_RESULT_JSON: "
BASH = shutil.which("bash")
# The documented block is POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"

HEREDOC_RE = re.compile(r"<<'(?P<tag>[A-Z_]+)'\n(?P<body>.*?)\n(?P=tag)\n", re.DOTALL)
# The halt command each halt site writes, its halt_reason in it; step 0 §1's write probe runs before the run
# folder exists, so it alone leaves `--run-dir` out.
HALT_CALL = ('`uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --run-dir "{run_dir}" --target stderr '
             '--halt-reason <halt_reason>`')
HALT_CALL_RE = re.compile(r'`uv run \{emitEnvelopeHelper\} emit-halt --workflow skf-brief-skill '
                          r'(?P<run_dir>--run-dir "\{run_dir\}" )?--target stderr '
                          r'--halt-reason (?P<reason><halt_reason>|[a-z]+(?:-[a-z]+)*)`')
# The step files whose halts call the emitter where they stop.
HALT_SITE_FILES = (PREFLIGHT, GATHER_INTENT, HEADLESS_ARGS, RATIFY, ANALYZE_TARGET, SCOPE_DEFINITION, AUTO_BRIEF,
                   AUTO_VALIDATE, WRITE_BRIEF)
# The [auto] success path: the envelope, the hook, the run folder's removal, the chain.
AUTO_SUCCESS = "### 3. Envelope, Hook and Chain"
HALT_LINE_RE = re.compile(HALT_CALL_RE.pattern + r".*?\bthen (?:HARD )?HALT\b \(exit code (?P<code>\d+)\)")
# The two record commands a step writes: fixed text, and text that quotes a helper or the user, from a file.
RECORD = 'uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" '
RECORD_FILE = f'`{RECORD}--warning "$(cat "{{run_dir}}/warning.txt")"`'
# The success command of both success sites.
SUCCESS_CALL = 'uv run {emitEnvelopeHelper} emit --workflow skf-brief-skill --run-dir "{run_dir}" ' "<<'SKF_BRIEF_RESULT'"
HOOK_CALL = '{onCompleteCommand} --result-path="{brief_path}"'
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"
# The two success sites, each with the section that builds the line.
SUCCESS_SITES = ((WRITE_BRIEF, "### 4b. Result Envelope (Headless)"), (AUTO_VALIDATE, AUTO_SUCCESS))
# Wording that has a success site print the envelope it now binds for the health check to display last.
PRINTED_ENVELOPE = ("printed its envelope", "already printed", "envelope printed", "envelope is printed",
                    "print the result envelope", "prints the envelope", "prints the result envelope",
                    "printed before the hook")
# A warning with a single quote, which would end an `echo '...'` payload.
QUOTED_WARNING = "warn: skill name 'demo' collides with existing brief at /tmp/forge/demo/skill-brief.yaml"
# The one line a helper warning that is a {field, message} object becomes.
OBJECT_WARNING = "<field>: <message>"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
SETTINGS = SCHEMA["$defs"]["skf-envelope"]["const"]
VALIDATOR = Draft202012Validator(SCHEMA)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The text under `heading`, up to the next heading of the same or a higher level."""
    start = text.index(f"\n{heading}\n")
    level = len(heading) - len(heading.lstrip("#"))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, start + len(heading) + 2)
    return text[start:end.start() if end else len(text)]


def _heredoc(text: str, tag: str) -> tuple[str, str]:
    """(the command line that opens the one heredoc named `tag`, up to its delimiter, and its payload)."""
    found = [m for m in HEREDOC_RE.finditer(text) if m.group("tag") == tag]
    assert len(found) == 1, f"one <<'{tag}' heredoc expected, found {len(found)}"
    match = found[0]
    line_start = text.rfind("\n", 0, match.start()) + 1
    return text[line_start:match.end("tag") + 1].strip(), match.group("body")


def _fill(body: str) -> str:
    """The documented success payload with its placeholders filled in, still as text."""
    body = body.replace('"<scope.type>"', '"public-api"').replace('"{scope_type}"', '"public-api"')
    body = re.sub(r'"<[^"<>]*>"', '"demo"', body)  # "<name>", "<brief_path from §3>" ...
    return re.sub(r'"\{[a-z_]+\}"', '"demo"', body)  # "{skill_name}", "{brief_path}" ...


def _argv(command: str, run_dir: Path | None = None) -> list[str]:
    """A documented `uv run {emitEnvelopeHelper} ...` command, up to any heredoc, as the argv that runs it here."""
    command = command.strip().strip("`").split(" <<", 1)[0]
    assert command.startswith("uv run {emitEnvelopeHelper} "), command
    if run_dir is not None:
        command = command.replace("{run_dir}", run_dir.as_posix())
    rest = command[len("uv run {emitEnvelopeHelper} "):]
    assert "{" not in rest, command
    return [sys.executable, str(EMITTER), *shlex.split(rest)]


def _run(argv: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=30,
                          check=False)


def _envelope(line: str) -> dict:
    assert line.startswith(PREFIX), line
    envelope = json.loads(line[len(PREFIX):])
    errors = [error.message for error in VALIDATOR.iter_errors(envelope)]
    assert not errors, errors
    return envelope


def _run_folder(tmp_path: Path, state: dict | None, warnings=()) -> Path:
    """A run folder as step 0 §1 creates it, holding a halt state and the warnings the run recorded."""
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-brief-skill-abc12345"
    run_dir.mkdir(parents=True)
    if state is not None:
        (run_dir / "halt-state.json").write_bytes(json.dumps(state).encode("utf-8"))
    for warning in warnings:
        done = _run([sys.executable, str(EMITTER), "record", "--run-dir", str(run_dir), "--warning", warning])
        assert done.returncode == 0, done.stderr
    return run_dir


def _halt_command(reason: str) -> str:
    """The Halt Contract's command for one halt_reason."""
    [command] = [m.group(0) for m in HALT_CALL_RE.finditer(_section(_read(SKILL_MD), "## Halt Contract"))]
    return command.replace("<halt_reason>", reason)


def _halt(reason: str, run_dir: Path | None) -> dict:
    """Run the documented halt command with stdin left holding junk, and return the line it printed on stderr."""
    proc = _run(_argv(_halt_command(reason), run_dir), stdin="{not read")
    assert proc.returncode == 0 and proc.stdout == "", proc.stderr
    [line] = proc.stderr.splitlines()
    return _envelope(line)


@pytest.fixture(scope="module")
def validator_output(tmp_path_factory) -> tuple[bytes, dict]:
    """skf-validate-brief-schema.py's stdout for a docs-only brief with source_authority official, and its one
    {field, message} warning."""
    brief = {
        "name": "demo", "version": "1.0.0", "source_type": "docs-only", "source_authority": "official",
        "source_repo": "https://example.com/docs", "doc_urls": [{"url": "https://example.com/docs"}],
        "language": "python", "description": "Demo docs.", "forge_tier": "Forge", "created": "2026-05-15",
        "created_by": "demo", "scope": {"type": "docs-only", "include": [], "exclude": [], "notes": ""},
    }
    path = tmp_path_factory.mktemp("brief") / "skill-brief.yaml"
    path.write_bytes(json.dumps(brief).encode("utf-8"))  # JSON is YAML
    proc = subprocess.run([sys.executable, str(VALIDATE_BRIEF), str(path)], capture_output=True, timeout=60,
                          check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["valid"] is True
    [warning] = result["warnings"]
    assert sorted(warning) == ["field", "message"]
    return proc.stdout, warning


# --------------------------------------------------------------------------
# The envelope is stated once
# --------------------------------------------------------------------------


def test_invocation_contract_is_the_one_statement_of_the_envelope():
    literal = f"{PREFIX}{{"
    holders = [path.relative_to(SKILL_DIR).as_posix() for path in sorted(SKILL_DIR.rglob("*.md"))
               if literal in _read(path)]
    assert holders == ["references/invocation-contract.md"], holders
    contract = _section(_read(CONTRACT), "## Result Contract (Headless)")
    [line] = [line for line in contract.splitlines() if line.startswith(PREFIX)]
    fields = json.loads(line[len(PREFIX):])
    assert list(fields) == list(SCHEMA["properties"]), "the documented line lists every field, in schema order"


def test_documented_halt_reasons_and_exit_codes_match_the_schema():
    contract = _read(CONTRACT)
    listed = contract.split("`halt_reason` is one of:", 1)[1].split(". `exit_code`", 1)[0]
    reasons = [None if value == "null" else json.loads(value) for value in re.findall(r"`([^`]+)`", listed)]
    assert reasons == SCHEMA["properties"]["halt_reason"]["enum"]
    table = _section(contract, "## Exit Codes")
    codes = {int(code) for code in re.findall(r"^\| (\d+) +\|", table, re.M)}
    assert codes == {SETTINGS["success_exit_code"], *SETTINGS["exit_codes"].values()}


# --------------------------------------------------------------------------
# SKILL.md resolves the emitter at activation and points at the halt command
# --------------------------------------------------------------------------


def _activation_steps() -> dict[int, str]:
    activation = _section(_read(SKILL_MD), "## On Activation")
    parts = re.split(r"^(\d+)\. ", activation, flags=re.M)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


def test_activation_resolves_the_emitter_before_the_first_stage_loads():
    steps = _activation_steps()
    [resolve] = [n for n, body in steps.items() if "`{emitEnvelopeHelper}` ←" in body]
    [first_stage] = [n for n, body in steps.items() if "`references/preflight.md`" in body]
    assert resolve < first_stage
    for path in ("_bmad/skf/shared/scripts/", "src/shared/scripts/"):
        assert f"`{{project-root}}/{path}{EMITTER.name}`" in steps[resolve]
    [auto] = [n for n, body in steps.items() if "**Resolve `{auto_mode}`**" in body]
    assert auto < first_stage
    # activation_steps_append runs once activation is done, before that stage.
    assert f"before step {first_stage} loads the first stage" in "".join(steps.values())


def test_no_step_file_resolves_the_emitter_again():
    for path in HALT_SITE_FILES:
        text = _read(path)
        assert "emitBriefEnvelopeProbeOrder" not in text and "emitEnvelopeProbeOrder" not in text, path.name
        assert "Error Envelope (Canonical)" not in text, path.name
        assert "**Resolve `{emitEnvelopeHelper}`**" not in text, path.name


def test_the_halt_contract_is_a_pointer():
    """#1134 (architecture-6): SKILL.md states the one command a halt runs and points at the Result Contract,
    which says what the emitter fills in; it holds no payload, no warning list and no fallback rules."""
    skill = _read(SKILL_MD)
    contract = " ".join(_section(skill, "## Halt Contract").split())
    assert HALT_CALL in contract and "except an interactive `[X]` cancel" in contract
    assert "`references/invocation-contract.md` (Result Contract) says what the emitter fills in" in contract
    assert "<<" not in contract and "```" not in contract and "unknown" not in contract
    for gone in ("{emitBriefEnvelopeHelper}", "workflow_warnings", OBJECT_WARNING, "SKF_BRIEF_HALT"):
        assert gone not in skill, gone
    result = " ".join(_section(_read(CONTRACT), "## Result Contract (Headless)").split())
    for needle in ("the halt runs the `emit-halt --halt-reason` command written at it", "The emitter reads no stdin",
                   "`skill_name` from `{run_dir}/halt-state.json`", 'gives `skill_name` `"unknown"` before then',
                   "folds in the warnings the run recorded", "prints nothing for an interactive run",
                   "it displays its message alone", "runs the command without `--run-dir`, in a headless or `[auto]` "
                   "run only", "`skf-emit-result-envelope.py`; `skf-emit-brief-result-envelope.py` stays as its "
                   "alias"):
        assert needle in result, needle
    assert OBJECT_WARNING not in result and "recorded in its run sink" in result


def test_skill_md_stays_under_its_token_budget():
    """#1134 (leanness-9): the prepass budget for SKILL.md, 2,500 tokens, on its chars/4 fallback."""
    assert len(_read(SKILL_MD)) // 4 < 2500


@pytest.mark.parametrize("mode", [pytest.param("auto", id="auto"), pytest.param(None, id="not-auto")])
@pytest.mark.parametrize("reason", [pytest.param(r, id=r) for r in SETTINGS["exit_codes"]])
def test_the_halt_command_emits_every_halt_reason_from_the_run_folder(tmp_path, reason, mode):
    """The command alone gives the whole line: the mode and the name from the halt state, the warnings from the
    sink, the exit code from the reason; stdin is never read."""
    run_dir = _run_folder(tmp_path, {"interactive": False, "mode": mode, "skill_name": "demo"}, [QUOTED_WARNING])
    envelope = _halt(reason, run_dir)
    assert (envelope["status"], envelope["halt_reason"]) == ("error", reason)
    assert envelope["exit_code"] == SETTINGS["exit_codes"][reason]
    assert envelope["mode"] == mode and envelope["skill_name"] == "demo"
    assert envelope["warnings"] == [QUOTED_WARNING]


def test_a_halt_before_the_name_says_unknown_and_lists_no_warning(tmp_path):
    run_dir = _run_folder(tmp_path, {"interactive": False, "mode": "auto"})
    envelope = _halt("forge-tier-missing", run_dir)
    assert (envelope["skill_name"], envelope["mode"], envelope["exit_code"]) == ("unknown", "auto", 3)
    assert "warnings" not in envelope


def test_an_interactive_halt_prints_no_line(tmp_path):
    run_dir = _run_folder(tmp_path, {"interactive": True, "mode": None}, [QUOTED_WARNING])
    proc = _run(_argv(_halt_command("write-failed"), run_dir))
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented record command in a POSIX bash")
def test_a_recorded_warning_reaches_the_halt_line_as_written(tmp_path, validator_output):
    """The file route keeps a single quote, backticks and `$( )` as text, and the line keeps the recorded order."""
    _, warning = validator_output
    hostile = f"{warning['field']}: {warning['message']} $(touch pwned) it's"
    assert "`" in hostile, "an unquoted argument would run the backticked words as commands"
    run_dir = _run_folder(tmp_path, {"interactive": False, "mode": None, "skill_name": "demo"})
    command = RECORD_FILE.strip("`").replace("uv run {emitEnvelopeHelper}", f'"{sys.executable}" "{EMITTER}"')
    for text in (QUOTED_WARNING, hostile):
        (run_dir / "warning.txt").write_bytes(text.encode("utf-8"))
        proc = subprocess.run([BASH, "-c", command.replace("{run_dir}", run_dir.as_posix())], capture_output=True,
                              text=True, encoding="utf-8", timeout=30, check=False, cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "pwned").exists()
    envelope = _halt("target-inaccessible", run_dir)
    assert envelope["warnings"] == [QUOTED_WARNING, hostile] and envelope["exit_code"] == 3


# --------------------------------------------------------------------------
# Each halt site calls the emitter where it stops
# --------------------------------------------------------------------------


def test_every_halt_site_emits_its_envelope_before_it_stops():
    sites = 0
    for path in HALT_SITE_FILES:
        text = _read(path)
        assert "error envelope per" not in text, f"{path.name} points its halt envelope elsewhere"
        assert "Halt Contract" not in text, f"{path.name} still sends its halts to SKILL.md"
        for line in text.splitlines():
            if "`uv run {emitEnvelopeHelper} emit-halt" not in line:
                continue
            match = HALT_LINE_RE.search(line)
            where = f"{path.name}: {line[:80]}"
            # The envelope first, then the halt, with the code the schema maps the reason to.
            assert match, where
            sites += 1
            reason, code = match.group("reason"), int(match.group("code"))
            reasons = ("input-missing", "input-invalid") if reason == "<halt_reason>" else (reason,)
            assert {SETTINGS["exit_codes"][r] for r in reasons} == {code}, where
            # Only step 0 §1's write probe runs before the run folder exists.
            probe = "**On any non-zero exit:**" in line and path == PREFLIGHT
            assert (match.group("run_dir") is None) is probe, where
    # preflight 3, headless-args 1, gather-intent-ratify 2, analyze-target 4, scope-definition 1,
    # step-auto-brief 4, step-auto-validate 2, write-brief 3
    assert sites == 20, sites


def test_write_brief_leaves_each_halt_to_its_own_command():
    """A halt in steps 1 to 5 runs the command written where it stops, which reads the halt state."""
    section = " ".join(_section(_read(WRITE_BRIEF), "### 4b. Result Envelope (Headless)").split())
    assert ("A HALT in this step, or in steps 1 to 3, does not use this section: it runs the `emit-halt` command "
            "written where it stops, which reads the run's halt state for the mode and the skill name") in section
    assert "Halt Contract" not in section


def test_step_one_halts_emit_in_headless_and_auto_mode_alike():
    """The halt state says whether the run prints an envelope, so no step 1 halt narrows the command to headless,
    points at write-brief.md section 4b, or types the mode; only the write probe, with no run folder, says when."""
    step_one = (PREFLIGHT, GATHER_INTENT, HEADLESS_ARGS, RATIFY)
    for path in step_one:
        text = _read(path)
        assert "In headless mode, emit" not in text, path.name
        assert "§4b" not in text and "step 5 section 4b" not in text and "placeholder convention" not in text
    [auto] = [line for line in _read(PREFLIGHT).splitlines() if "brief_path` is not available" in line]
    match = HALT_CALL_RE.search(auto)
    assert match and match.group("reason") == "input-missing" and match.group("run_dir"), auto
    assert '`"auto"`' not in auto and "`mode`" not in auto
    [probe] = [line for line in _read(PREFLIGHT).splitlines() if "**On any non-zero exit:**" in line]
    for needle in ("in a headless or `[auto]` run, emit the halt envelope first",
                   "(no `--run-dir`: the run folder does not exist; add `--mode auto` in an `[auto]` run)"):
        assert needle in probe, needle
    # The validators' {field, message} warnings go to the sink from the file the call saved.
    for path, saved in ((HEADLESS_ARGS, "inputs-validation.json"), (RATIFY, "ratify-validation.json")):
        valid = [line for line in _read(path).splitlines() if line.lstrip().startswith("- **`valid: true`**")]
        assert len(valid) == 1, (path.name, valid)
        assert f'`{RECORD}--warnings-file "{{run_dir}}/{saved}"`' in valid[0], path.name
    assert "- **`valid: true`**" not in _read(GATHER_INTENT)


def test_no_brief_prose_names_a_dev_only_shared_path():
    """#1112 (brief-skill architecture-5): `src/shared/` exists only in dev. A probe order names it after the
    installed path, always as `{project-root}/src/shared/...` (the frontmatter `*ProbeOrder` lists and SKILL.md's
    resolver and emitter bindings); every other pointer, such as a schema's, is `shared/...`, which resolves
    from the SKF module root installed and in dev."""
    stray = [f"{path.relative_to(SKILL_DIR).as_posix()}:{number}" for path in sorted(SKILL_DIR.rglob("*.md"))
             for number, line in enumerate(_read(path).splitlines(), 1)
             if re.search(r"(?<!\{project-root\}/)src/shared/", line)]
    assert not stray, f"brief prose names the dev-only src/shared/ outside a probe order: {stray}"


# --------------------------------------------------------------------------
# #1134: the halt state, written where the run learns what it holds
# --------------------------------------------------------------------------


HALT_STATE_RE = re.compile(r"""^cat > "\{run_dir\}/halt-state\.json" <<'SKF_JSON'\n(?P<body>.*?)\nSKF_JSON$""",
                           re.M | re.S)
# Each file that writes the halt state, the keys it writes and the values it gives in a run that reaches it.
HALT_STATES = (
    (PREFLIGHT, {"interactive": False, "mode": "auto"}),
    (HEADLESS_ARGS, {"interactive": False, "mode": None, "skill_name": "demo"}),
    (RATIFY, {"interactive": False, "mode": None, "skill_name": "demo"}),
    (AUTO_BRIEF, {"interactive": False, "mode": "auto", "skill_name": "demo"}),
)


def _halt_state(path: Path, values: dict) -> dict:
    """The one halt state the file writes, each placeholder filled from `values`."""
    [body] = [m.group("body") for m in HALT_STATE_RE.finditer(_read(path))]
    filled = re.sub(r'"(\w+)": "?<[^<>]*>"?', lambda m: f'"{m.group(1)}": {json.dumps(values[m.group(1)])}', body)
    return json.loads(filled)


@pytest.mark.parametrize("path,values", [pytest.param(path, values, id=path.stem) for path, values in HALT_STATES])
def test_each_halt_state_is_written_whole_with_the_keys_the_run_knows(tmp_path, path, values):
    state = _halt_state(path, values)
    assert state == values, state
    envelope = _halt("write-failed", _run_folder(tmp_path, state))
    assert envelope["mode"] == values["mode"]
    assert envelope["skill_name"] == values.get("skill_name", "unknown")


def test_step_zero_writes_the_halt_state_before_its_first_halt_that_can_read_it():
    section = _forge_tier_section()
    bind = section.index("Bind `{run_dir}` ← the path the last command prints.")
    state = section.index('cat > "{run_dir}/halt-state.json"')
    assert bind < state < section.index("--halt-reason forge-tier-missing")
    body = HALT_STATE_RE.search(section).group("body")
    assert ('"interactive": <true when neither {headless_mode} nor {auto_mode} is true, else false>' in body
            and '"mode": <"auto" when {auto_mode} is true, else null>' in body)
    interactive = _halt_state(PREFLIGHT, {"interactive": True, "mode": None})
    assert interactive == {"interactive": True, "mode": None}
    # The name is written where it resolves: the input gate on the derive route, the ratify route in a headless
    # run, and the upstream brief on the [auto] route.
    args = _read(HEADLESS_ARGS)
    assert args.index("- **`valid: true`**") < args.index('cat > "{run_dir}/halt-state.json"') < args.index("### 3. ")
    assert "On `valid: true` with no `normalized.from_brief`, the skill name is resolved" in args
    assert "In a headless run, `valid: true` resolves the skill name" in _read(RATIFY)
    auto = _read(AUTO_BRIEF)
    assert auto.index("- **`valid: true`**") < auto.index('cat > "{run_dir}/halt-state.json"') < auto.index("### 2. ")


# --------------------------------------------------------------------------
# The success envelope carries the warnings the run recorded
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,heading,mode",
    [
        pytest.param(WRITE_BRIEF, "### 4b. Result Envelope (Headless)", None, id="write-brief"),
        pytest.param(AUTO_VALIDATE, AUTO_SUCCESS, "auto", id="auto"),
    ],
)
def test_success_envelope_carries_the_run_warnings(tmp_path, path, heading, mode):
    command, body = _heredoc(_section(_read(path), heading), "SKF_BRIEF_RESULT")
    assert command == SUCCESS_CALL
    assert '"warnings"' not in body, "the sink holds the warnings; no stage types the list"
    recorded = [QUOTED_WARNING, "Doc detection failed: proceeding without doc enrichment."]
    run_dir = _run_folder(tmp_path, {"interactive": False, "mode": mode, "skill_name": "demo"}, recorded)
    proc = _run(_argv(command, run_dir), stdin=_fill(body))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout.strip())
    assert envelope["status"] == "success" and envelope["exit_code"] == SETTINGS["success_exit_code"]
    assert envelope["mode"] == mode and envelope["skill_name"] == "demo"
    assert envelope["warnings"] == recorded


# Each helper whose own `warnings[]` a stage records: the file its call saves its stdout in, and how many calls do.
SAVED_HELPER_OUTPUTS = (
    (HEADLESS_ARGS, "{validateBriefInputsHelper}", "inputs-validation.json", 1),
    (RATIFY, "{validateBriefSchemaHelper}", "ratify-validation.json", 1),
    (AUTO_BRIEF, "{validateBriefSchemaHelper}", "upstream-validation.json", 1),
    (AUTO_VALIDATE, "{validateBriefSchemaHelper}", "auto-validation.json", 1),
    (WRITE_BRIEF, "{writeSkillBriefHelper}", "brief-write.json", 2),
    (AUTO_BRIEF, "{writeSkillBriefHelper}", "brief-write.json", 1),
    (ANALYZE_TARGET, "{detectWorkspacesHelper} --tree-file \"{run_dir}/tree.json\" --manifest-dir", "workspaces.json",
     1),
    (ANALYZE_TARGET, "{extractPublicApiHelper} --mode entries", "entries.json", 1),
    (ANALYZE_TARGET, "{extractPublicApiHelper} --mode quick", "extract.json", 1),
)


@pytest.mark.parametrize("path,helper,saved,calls",
                         [pytest.param(*row, id=f"{row[0].stem}:{row[2]}") for row in SAVED_HELPER_OUTPUTS])
def test_a_helpers_warnings_are_recorded_from_the_stdout_its_call_saved(path, helper, saved, calls):
    text = _read(path)
    # A call inside a numbered step is indented with its fenced block.
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith(f"uv run {helper}")]
    lines = [line for line in lines if "--snapshot" not in line]
    assert len(lines) == calls and all(line.endswith(f' > "{{run_dir}}/{saved}"') for line in lines), lines
    assert f'`{RECORD}--warnings-file "{{run_dir}}/{saved}"`' in text, path.name


def test_no_stage_keeps_a_warning_list_or_flattens_an_object():
    """#1134 (architecture-6, determinism-2): the sink is the run's one list, and the emitter turns a {field,
    message} warning into its line, so no brief file keeps `workflow_warnings[]` or spells out the conversion."""
    rules = " ".join(_section(_read(SKILL_MD), "## Workflow Rules").split())
    for needle in ("Record each warning the moment it is raised, each `warn:` line a step logs included",
                   f'`{RECORD}--warning "<text>"`', "or `--warnings-file` on a helper's saved JSON",
                   "write it to `{run_dir}/warning.txt`, then pass `--warning \"$(cat \"{run_dir}/warning.txt\")\"`"):
        assert needle in rules, needle
    for path in sorted(SKILL_DIR.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for gone in ("workflow_warnings", OBJECT_WARNING, "{emitBriefEnvelopeHelper}"):
                assert gone not in text, (path.relative_to(SKILL_DIR).as_posix(), gone)


# Placeholders a fixed --warning may hold: a count, an enum value, a kebab-case name.
SAFE_PLACEHOLDERS = {"{count}", "{manifest_kind}", "{skill-name}"}
# A `warn:` line no record command follows: the draft checkpoint is written in interactive runs only, which print
# no envelope, so SKILL.md's rule alone covers it.
UNRECORDED_WARN = {"draft-checkpoint.md"}


def test_every_warning_is_recorded_where_it_is_raised():
    """Each site writes the whole record command: fixed text as `--warning "<text>"` with safe placeholders only,
    text that quotes a helper or the user from `{run_dir}/warning.txt`, written with a file write."""
    fixed = file_route = 0
    for path in sorted(REFERENCES.glob("*.md")):
        for line in _read(path).splitlines():
            where = f"{path.name}: {line[:90]}"
            if re.search(r"[`\"]warn: ", line) and path.name not in UNRECORDED_WARN:
                assert RECORD in line or "the GATE above records" in line, where
            if RECORD_FILE in line:
                file_route += line.count(RECORD_FILE)
                assert "`{run_dir}/warning.txt` with a file write, never `echo`" in line, where
            for text in re.findall(re.escape(RECORD) + r'--warning "([^"$]*)"`', line):
                fixed += 1
                assert not set(re.findall(r"\{[^}]+\}", text)) - SAFE_PLACEHOLDERS, where
                assert "'" not in text and "`" not in text, where
    assert fixed >= 8 and file_route >= 14, (fixed, file_route)


def test_a_validator_warning_reaches_every_envelope_as_one_line(tmp_path, validator_output):
    """A real {field, message} warning, recorded with the documented --warnings-file command from the stdout the
    validator call saved, reaches the halt and both success envelopes as one `field: message` line."""
    stdout, warning = validator_output
    line = f"{warning['field']}: {warning['message']}"
    run_dir = _run_folder(tmp_path, {"interactive": False, "mode": None, "skill_name": "demo"})
    (run_dir / "ratify-validation.json").write_bytes(stdout)
    [valid] = [text for text in _read(RATIFY).splitlines() if text.startswith("- **`valid: true`**")]
    [record] = re.findall(r"`(" + re.escape(RECORD) + r"--warnings-file [^`]+)`", valid)
    proc = _run(_argv(record, run_dir))
    assert proc.returncode == 0, proc.stderr
    assert _halt("input-invalid", run_dir)["warnings"] == [line]
    for path, heading in SUCCESS_SITES:
        command, body = _heredoc(_section(_read(path), heading), "SKF_BRIEF_RESULT")
        proc = _run(_argv(command, run_dir), stdin=_fill(body))
        assert proc.returncode == 0, f"{path.name}: {proc.stderr}"
        assert _envelope(proc.stdout.strip())["warnings"] == [line], path.name


def test_write_brief_builds_the_envelope_after_the_qmd_registration():
    text = _read(WRITE_BRIEF)
    order = ["### 3. Write the Brief", "### 3b. QMD Collection Registration (Deep Tier Only)",
             "### 4b. Result Envelope (Headless)", "### 6. Display Success Summary",
             "### 6b. On-Complete Hook (pipeline integration)", "### 7. Chain to Health Check"]
    positions = [text.index(f"\n{heading}\n") for heading in order]
    assert positions == sorted(positions)
    assert "### 5. " not in text
    # Every pointer at the registration names its new place.
    assert "Loaded by step 5 §3b " in _read(QMD_REGISTRATION)
    assert ("one `<name>-brief` collection per existing brief, registered by step 5 §3b (step-auto-validate.md §3 "
            "on an `[auto]` run) ") in _read(PORTFOLIO_CHECK)
    assert "Used by skf-brief-skill step 5 §3b" in FORGE_TIER_RW.read_text(encoding="utf-8")
    stale = [path.name for path in sorted(SKILL_DIR.rglob("*.md")) if "step 5 §5" in _read(path)]
    assert not stale, stale


def test_qmd_registration_never_halts_after_the_write():
    """A missing skf-forge-tier-rw.py costs the registry update, not the envelope of a brief already written.
    #1135 (architecture-2): the registration file resolves the helper and handles a missing one itself, so either
    route that loads it gets the same fallback."""
    section = _section(_read(WRITE_BRIEF), "### 3b. QMD Collection Registration (Deep Tier Only)")
    assert "HALT if no candidate exists" not in section and "{forgeTierRwHelper}" not in section
    qmd = _read(QMD_REGISTRATION)
    assert "HALT if no candidate exists" not in qmd
    registry = _flow(_section(qmd, "## Registry Update (Delegated to Script)"))
    assert registry.startswith("## Registry Update (Delegated to Script) Resolve `{forgeTierRwHelper}` from "
                               "`{forgeTierRwProbeOrder}` (first existing path wins; with no path, see Error "
                               "Handling).")
    [missing] = [line for line in _section(qmd, "## Error Handling").splitlines()
                 if line.startswith("- If `{forgeTierRwHelper}` has no path")]
    for needle in ("the brief is already written, so do not HALT", "Skip the Registry Update",
                   f'record the warning: `{RECORD}--warning "QMD registry not updated: skf-forge-tier-rw.py '
                   'not found"`'):
        assert needle in missing, needle
    # The brief is indexed before the registry update, so a missing helper still leaves it searchable.
    assert qmd.index("## Collection Creation") < qmd.index("## Registry Update")


# --------------------------------------------------------------------------
# The success envelope is the run's last line (step 5b enhancement-1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path,heading", [pytest.param(*site, id=site[0].stem) for site in SUCCESS_SITES])
def test_the_success_line_is_bound_for_the_health_check(path, heading):
    section = " ".join(_section(_read(path), heading).split())
    assert ("Bind `{result_envelope_line}` to the line it prints, and do not display it here: the shared health "
            "check displays it verbatim as the run's last line") in section
    assert "leave `{result_envelope_line}` empty and display its error" in section
    assert "display the line it prints verbatim" not in section.lower()


def test_the_health_check_displays_the_bound_line_last():
    shared = " ".join(_read(SHARED_HEALTH_CHECK).split())
    assert "may bind `{result_envelope_line}`" in shared and "as its very last line" in shared
    relay = " ".join(_read(HEALTH_CHECK).split())
    assert ("the shared health check displays the `{result_envelope_line}` that write-brief.md §4b or "
            "step-auto-validate.md §3 bound as the run's last line") in relay
    contract = " ".join(_section(_read(CONTRACT), "## Result Contract (Headless)").split())
    assert ("It is the run's last line: the step binds `{result_envelope_line}` to it instead of displaying it"
            in contract)
    # A headless run ends on the envelope, not on the interactive success summary.
    summary = _section(_read(WRITE_BRIEF), "### 6. Display Success Summary")
    assert "When `{headless_mode}` is true, skip this section" in summary
    # No line says the success envelope is printed where it is built: a step that read so would display it early.
    for path in (*sorted(REFERENCES.glob("*.md")), SKILL_MD, CUSTOMIZE):
        text = " ".join(_read(path).split())
        for stale in PRINTED_ENVELOPE:
            assert stale not in text, (path.name, stale)
    final = next(line for line in _read(REPO / "docs" / "workflows.md").splitlines()
                 if line.startswith("Setup is not the only workflow whose result line is the run's final message"))
    assert "Brief Skill" in final and "`SKF_BRIEF_RESULT_JSON`" in final


# --------------------------------------------------------------------------
# on_complete fires on every success path, after the envelope
# --------------------------------------------------------------------------


def test_auto_path_runs_on_complete_right_after_the_envelope():
    approve = _section(_read(AUTO_VALIDATE), AUTO_SUCCESS)
    envelope = approve.index("<<'SKF_BRIEF_RESULT'")
    hook = approve.index(HOOK_CALL)
    chain = approve.index("Chain to {nextStepFile}")
    assert envelope < hook < chain


def test_hook_runs_in_write_brief_and_auto_approve_only():
    callers = sorted(path.name for path in REFERENCES.glob("*.md") if HOOK_CALL in _read(path))
    assert callers == ["step-auto-validate.md", "write-brief.md"]
    relay = _read(HEALTH_CHECK)
    assert "on_complete" not in relay and "{onCompleteCommand}" not in relay
    assert re.search(r"^nextStepFile: 'shared/health-check\.md'$", relay, re.M)


def test_hook_failure_is_displayed_after_the_envelope():
    for path, heading in ((WRITE_BRIEF, "### 6b. On-Complete Hook (pipeline integration)"),
                          (AUTO_VALIDATE, AUTO_SUCCESS)):
        section = _section(_read(path), heading)
        assert "`on_complete hook failed (exit {code}): {first line of its stderr}`" in section, path.name
        assert "does not carry this line" in section, path.name
        assert "workflow_warnings" not in section.split("**On-complete hook.**")[-1], path.name


def test_customize_toml_names_both_hook_sites():
    text = _read(CUSTOMIZE)
    comment = text[:text.index('on_complete = ""')].rstrip().rsplit("\n\n", 1)[-1]
    flat = " ".join(line.lstrip("#").strip() for line in comment.splitlines())
    for needle in ("write-brief.md §6b", "step-auto-validate.md §3", "[auto]", "a shell command",
                   "on_complete hook failed",
                   # An interactive run outside [auto] prints no envelope.
                   "once the brief is written (and, in a headless or [auto] run, the result envelope is built)"):
        assert needle in flat, needle
    assert "step 5)" not in comment and "workflow_warnings" not in comment
    [line] = [line for line in _read(SKILL_MD).splitlines() if "`{onCompleteCommand}` ←" in line]
    assert "write-brief.md §6b" in line and "step-auto-validate.md §3" in line


def test_the_auto_validation_step_asks_nothing():
    """#599: the forger runs every pipeline stage headless, so BS[auto] never reached the approve, edit and
    reject menu. The step checks, summarizes and goes on, and no file promises the menu any more."""
    text = _read(AUTO_VALIDATE)
    for gone in ("[E]dit", "[R]eject", "rejectTargetFile", "writeSkillBriefProbeOrder", "Validation Gate"):
        assert gone not in text, gone
    headings = re.findall(r"^### (\d+)\. ", text, re.M)
    assert headings == ["1", "2", "3"], headings
    for path in (SKILL_MD, CONTRACT, CUSTOMIZE, AUTO_BRIEF, WRITE_BRIEF):
        body = _read(path)
        assert "[R]eject" not in body and "step-auto-validate.md §4" not in body, path.name
    [row] = [line for line in _read(SKILL_MD).splitlines() if "references/step-auto-validate.md" in line]
    assert row.rstrip().endswith("| Yes |"), row


def test_ratify_version_line_names_the_r_pass():
    """Handoff from W2-brief-scope-signals: an [R] pass runs step 2 on a ratify run. Step 5b gate run 3
    (determinism-3): step 5 writes a ratified brief from the file it ratified (--base-brief), which keeps its
    version, so no step pins the version through a typed version_resolved key any more."""
    section = _section(_read(WRITE_BRIEF), "### 3. Write the Brief")
    [line] = [line for line in section.splitlines() if line.startswith("**Ratify run (`ratify_mode: true`):**")]
    assert ("such as its version, which step 2 never re-derives on a ratify run (an [R] pass analyzes the "
            "brief's ref but keeps the hydrated version)") in line
    assert "this path never ran step 2" not in line
    [call] = [line for line in section.splitlines() if "--base-brief" in line]
    assert call == ('uv run {writeSkillBriefHelper} write --target {resolved-target-path} '
                    '--base-brief "{ratify_source_path}" --patch-file "{run_dir}/ratify-patch.json" '
                    '> "{run_dir}/brief-write.json"')
    confirm = _read(REFERENCES / "confirm-brief.md")
    assert "rely on the hydrated `version` (step 5 writes from the ratified file, which keeps it)" in confirm
    for path in sorted(SKILL_DIR.rglob("*.md")):
        assert "version_resolved" not in _read(path), path.name


def test_auto_stays_a_separate_route_by_design():
    """Step 5b gate run 3 (enhancement-1), a written exception the maintainer accepted on 2026-10-03: [auto]
    keeps its own stages, because the forge-auto contract gives it doc enrichment the other routes lack. #1135
    (architecture-3): every run starts in stage 0, so [auto] runs in place of stages 1 to 5."""
    [line] = [line for line in _read(SKILL_MD).splitlines() if line.startswith("Every run starts in preflight.md")]
    assert line.startswith("Every run starts in preflight.md (run folder, forge tier), which routes by mode.")
    assert ("It stays a separate route by design: the forge-auto pipeline contract gives it doc enrichment "
            "(step-auto-brief.md §2-§3), which the ratify and derive routes do not run") in line
    assert ("in place of stages 1-5; at Deep tier step-auto-validate.md loads stage 5's QMD registration file."
            in line)
    assert "Interactive: gather-intent.md." in line and "the rest of gather-intent.md" not in line
    assert "skf-detect-docs.py" in _read(AUTO_BRIEF)
    for path in (WRITE_BRIEF, RATIFY):
        assert "skf-detect-docs.py" not in _read(path), path.name


def test_the_auto_path_registers_the_brief_in_qmd_before_its_envelope():
    """Step 5b gate run 3 (enhancement-1, drift 1): an [auto] run at Deep tier runs the one QMD registration
    procedure before it builds its envelope, so a warning the registration raises reaches it. #1135
    (architecture-2): it loads qmd-collection-registration.md directly, as write-brief.md §3b does, and never
    loads write-brief.md, a stage whose overwrite gate, envelope and hook must not run on this route."""
    text = _read(AUTO_VALIDATE)
    assert re.search(r"^qmdRegistrationFile: 'references/qmd-collection-registration\.md'$", text, re.M)
    assert _frontmatter(AUTO_VALIDATE)["qmdRegistrationFile"] == _frontmatter(WRITE_BRIEF)["qmdRegistrationFile"]
    assert "writeBriefFile" not in text and "write-brief.md" not in text
    approve = _section(text, AUTO_SUCCESS)
    [qmd] = [line for line in approve.splitlines() if line.startswith("**QMD registration.**")]
    for needle in ("When the run's forge tier (step 0 §1) is Deep and QMD is available, load "
                   "`{qmdRegistrationFile}` and follow it", "is recorded in the run sink before the envelope below is "
                   "built", "Otherwise skip this."):
        assert needle in qmd, needle
    # SKILL.md defines {skill-name} as the brief's name, so this route binds it once, where the name resolves.
    assert "{skill-name}` ←" not in text and "`{skill_name}`" not in qmd
    assert approve.index("**QMD registration.**") < approve.index("<<'SKF_BRIEF_RESULT'")
    assert "register it in QMD at Deep tier" in _section(text, "## Goal")
    # Both routes load the one copy of the procedure, and no stage holds a copy of its steps.
    write = _read(WRITE_BRIEF)
    assert "\n### 3b. QMD Collection Registration (Deep Tier Only)\n" in write
    loaders = sorted(path.name for path in REFERENCES.glob("*.md") if "{qmdRegistrationFile}" in _read(path))
    assert loaders == ["step-auto-validate.md", "write-brief.md"], loaders
    assert "qmd collection add" not in text and "qmd collection add" not in write
    # No file still says an [auto] run loads part of write-brief.md, and the procedure names both callers.
    assert "An `[auto]` run never loads this file" not in write
    assert "An `[auto]` run runs only §3b of this file" not in write
    assert ("Loaded by step 5 §3b and, for an `[auto]` brief, step-auto-validate.md §3, only when forge tier is "
            "Deep AND QMD is available") in _read(QMD_REGISTRATION)


def test_skill_name_is_the_briefs_name_bound_once_on_the_auto_route():
    """#1135 (leanness-2): `{skill-name}` names the brief, never this skill's folder, and the [auto] route binds it
    with `skill_name` where the upstream brief resolves the name."""
    [rule] = [line for line in _read(SKILL_MD).splitlines() if line.startswith("- `{skill-name}`")]
    assert rule == "- `{skill-name}` is the brief's approved `name`, never this skill's folder name."
    auto = _read(AUTO_BRIEF)
    binds = [line for line in auto.splitlines() if "`{skill-name}`" in line]
    assert len(binds) == 1 and "`skill_name` ← `brief.name` (bind `{skill-name}` to it too)" in binds[0], binds
    assert auto.index("- **`valid: true`**") < auto.index(binds[0]) < auto.index("### 2. ")


def test_the_module_pick_stays_step_2s_judgment():
    """Step 5b gate run 3 (determinism-1), a written exception the maintainer accepted on 2026-10-03: which folders
    are modules is step 2 §4.3's judgment, so the recommender carries `module_count` and the snapshot names no
    module. The prose says so, so the old "never a count" contradiction cannot return and later audits see why."""
    scope = _section(_read(SCOPE_DEFINITION), "### 2c. Offer Scope Templates")
    [line] = [line for line in scope.splitlines() if line.startswith("**Run the recommender in one Bash call**")]
    assert ("never the file list, a registry file or the exports typed into the payload; `module_count` is the one "
            "count it carries, because which folders are modules is step 2 §4.3's judgment") in line
    assert "never a list, a count" not in line
    output = _section(_read(ANALYZE_TARGET), "#### 4.3 Output format (both paths)")
    assert ("The snapshot lists candidates and names no module on purpose: a folder-name rule misreads `LICENSES`, "
            "`ci`, `web` or lodash's `lib/`.") in output


# --------------------------------------------------------------------------
# #1118: step 1 reads the forge tier through skf-forge-tier-rw.py effective (#1135: in stage 0, preflight.md)
# --------------------------------------------------------------------------


EFFECTIVE_CALL = "uv run {forgeTierRwHelper} effective "
# The step files that read a tool flag, and the binding each one names.
TOOL_READERS = ((GATHER_INTENT, "`tools.qmd` is true in the `tools` step 0 §1 bound"),
                (PORTFOLIO_CHECK, "`tools.qmd` is true in the `tools` step 0 §1 bound"),
                (ANALYZE_TARGET, "`tools.ccc` is true in the `tools` step 0 §1 bound"))


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space."""
    return re.sub(r"\s+", " ", text).strip()


def _frontmatter(path: Path) -> dict:
    match = re.match(r"\A---\n(.*?)\n---\n", _read(path), re.S)
    assert match, f"{path.name} has no frontmatter"
    return yaml.safe_load(match.group(1))


def _forge_tier_section() -> str:
    return _section(_read(PREFLIGHT), "### 1. Discover Forge Tier")


def _branch(label: str) -> str:
    """The paragraph, or the list it introduces, of one outcome of the effective call."""
    section = _forge_tier_section()
    start = section.index(f"\n{label} (")
    end = section.find("\n\n", start + 1)
    return section[start:end if end != -1 else len(section)]


def _run_documented_effective(sidecar: Path) -> subprocess.CompletedProcess:
    """§1's documented call, its paths filled in, run against the real helper."""
    blocks = [m.group(1).strip() for m in re.finditer(r"```bash\n(.*?)```", _forge_tier_section(), re.S)
              if EFFECTIVE_CALL in m.group(1)]
    assert len(blocks) == 1, blocks
    command = blocks[0].replace("{forgeTierFile}", _frontmatter(PREFLIGHT)["forgeTierFile"])
    command = command.replace("{sidecar_path}", sidecar.as_posix())
    assert command.startswith(EFFECTIVE_CALL) and "{" not in command[len(EFFECTIVE_CALL):], command
    argv = shlex.split(command[len("uv run {forgeTierRwHelper} "):])
    return subprocess.run([sys.executable, str(FORGE_TIER_RW), *argv], capture_output=True, text=True,
                          encoding="utf-8", timeout=30, check=False)


def test_step_zero_resolves_the_forge_tier_helper_as_the_qmd_registration_does():
    """#1135 (architecture-2): the two files that run skf-forge-tier-rw.py hold the same probe order and target, and
    the stages that loaded them for those files do not."""
    front = _frontmatter(PREFLIGHT)
    qmd = _frontmatter(QMD_REGISTRATION)
    assert front["forgeTierRwProbeOrder"] == qmd["forgeTierRwProbeOrder"] == [
        "{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py",
        "{project-root}/src/shared/scripts/skf-forge-tier-rw.py",
    ]
    assert front["forgeTierFile"] == qmd["forgeTierFile"] == "{sidecar_path}/forge-tier.yaml"
    for path in (GATHER_INTENT, WRITE_BRIEF):
        assert not {"forgeTierRwProbeOrder", "forgeTierFile"} & set(_frontmatter(path)), path.name
    section = _flow(_forge_tier_section())
    assert ("`{forgeTierRwHelper}`, resolved from `{forgeTierRwProbeOrder}` (first existing path wins; HALT if no "
            "candidate exists)") in section


def test_step_zero_binds_the_tier_and_the_tools_the_documented_call_prints(tmp_path):
    (tmp_path / "forge-tier.yaml").write_text(
        "tools:\n  ast_grep: true\n  qmd: true\n  ccc: false\ntier: Forge\n", encoding="utf-8")
    (tmp_path / "preferences.yaml").write_text("tier_override: Deep\n", encoding="utf-8")
    done = _run_documented_effective(tmp_path)
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert (payload["exists"], payload["tier"], payload["detected_tier"], payload["tier_source"]) == (
        True, "Deep", "Forge", "override")
    assert payload["tools"]["qmd"] is True and payload["tools"]["ccc"] is False
    found = _flow(_branch("**If found**"))
    assert "(exit 0 with `exists` true): bind `tier`, `detected_tier`, `tier_source` and `tools` from its JSON" in found
    assert "`tier_source` `override` is step 1 §2's \"tier override was applied\"" in found
    # Each key the branch reads is one the helper prints.
    for key in ("override_rejected", "tier_override", "preferences_error", "detected_tier"):
        assert re.search(rf"[`{{]{key}[`}}]", found) and key in payload, key
    # An ignored override and an unreadable preferences.yaml each reach the envelope as one warning, through the
    # file route: the override is a value the user typed, the error a helper's message (#1134).
    assert found.count(RECORD_FILE) == 1 and "record that line the same way, through `{run_dir}/warning.txt`" in found
    assert "write that line to `{run_dir}/warning.txt` with a file write, never `echo`" in found
    assert "`warn: tier_override {tier_override} is not one of Quick, Forge, Forge+, Deep" in found


def test_step_zero_warns_on_an_override_that_names_no_tier(tmp_path):
    (tmp_path / "forge-tier.yaml").write_text("tools: {}\ntier: Forge\n", encoding="utf-8")
    (tmp_path / "preferences.yaml").write_text("tier_override: deep\n", encoding="utf-8")
    payload = json.loads(_run_documented_effective(tmp_path).stdout)
    assert payload["tier"] == "Forge" and payload["tier_source"] == "detected"
    assert payload["override_rejected"] is True and payload["tier_override"] == "deep"


def test_step_zero_halts_forge_tier_missing_when_the_documented_call_finds_no_file(tmp_path):
    (tmp_path / "preferences.yaml").write_text("tier_override: Deep\n", encoding="utf-8")
    done = _run_documented_effective(tmp_path)
    assert done.returncode == 0 and json.loads(done.stdout)["exists"] is False
    missing = _branch("**If not found**")
    assert missing.strip().startswith("**If not found** (exit 0 with `exists` false): emit the halt envelope first")
    match = HALT_LINE_RE.search(missing)
    assert match and (match.group("reason"), match.group("code")) == ("forge-tier-missing", "3"), missing


@pytest.mark.parametrize("content", ["tools:\n  ast_grep: true\n  qmd: tr", "tools:\n  qmd: true\ntier: De",
                                     "tier: [\n"], ids=["cut-before-tier", "cut-inside-tier", "unparseable"])
def test_step_zero_falls_back_to_quick_when_the_documented_call_exits_2(tmp_path, content):
    """A forge-tier.yaml cut short or not YAML holds no tier it can use: exit 2, and the run goes on at Quick."""
    (tmp_path / "forge-tier.yaml").write_text(content, encoding="utf-8")
    done = _run_documented_effective(tmp_path)
    assert done.returncode == 2 and done.stdout == ""
    assert "forge-tier.yaml" in json.loads(done.stderr)["message"]
    fallback = _flow(_branch("**If found but not usable**"))
    assert fallback.startswith("**If found but not usable** (exit 2, any other non-zero exit, or no JSON")
    for needle in ('`tier = "Quick"`, `tools = {}` and `tier_source: "fallback-corrupted-config"`',
                   "Do not HALT.", "`{message}` is the helper's stderr `message`, else its first stderr line",
                   f"to `{{run_dir}}/warning.txt` with a file write, never `echo`, then run {RECORD_FILE}"):
        assert needle in fallback, needle
    assert "halt_reason" not in fallback


def test_no_step_reads_the_forge_tier_or_its_tools_by_eye():
    section = _forge_tier_section()
    for stale in ("Attempt to load", "Read `{sidecar_path}/preferences.yaml`", "Read the tier level",
                  "cannot be parsed"):
        assert stale not in section, stale
    for path, binding in TOOL_READERS:
        text = _flow(_read(path))
        assert binding in text, path.name
        assert "in forge-tier.yaml" not in text and "in `forge-tier.yaml`" not in text, path.name
    confirm = _read(REFERENCES / "confirm-brief.md")
    assert ('{If `tier_source` is `fallback-corrupted-config`:}\n'
            '"**Note:** Forge tier defaulted to Quick (forge-tier.yaml could not be read)."') in confirm
    assert "no forge-tier.yaml found" not in confirm


# --------------------------------------------------------------------------
# #1135: every run starts in stage 0, and each rule is stated once
# --------------------------------------------------------------------------


def _headings(text: str, level: str) -> list[str]:
    """The headings of one level, outside the frontmatter."""
    return re.findall(rf"^{re.escape(level)} (.+)$", text, re.M)


def test_preflight_holds_the_run_folder_the_tier_and_the_routing():
    """#1135 (architecture-3): stage 0 is the old gather-intent.md §1 and §1b, which every mode runs; the interactive
    stage starts at §2 and holds nothing a headless or [auto] run needs."""
    preflight = _read(PREFLIGHT)
    assert _headings(preflight, "###") == ["1. Discover Forge Tier", "1b. Route by Mode"]
    assert _headings(preflight, "#") == ["Step 0: Preflight"] and _headings(preflight, "##") == ["Sequence"]
    front = _frontmatter(PREFLIGHT)
    assert front["nextStepFile"] == "gather-intent.md"
    assert (front["autoBriefFile"], front["headlessArgsFile"]) == ("references/step-auto-brief.md",
                                                                   "references/headless-args.md")
    routes = _section(preflight, "### 1b. Route by Mode")
    [otherwise] = [line for line in routes.splitlines() if line.startswith("- **Otherwise**")]
    assert otherwise == ("- **Otherwise** the run is interactive: load, read fully, and execute `{nextStepFile}` "
                         "(gather-intent.md) at its §2.")
    gather = _read(GATHER_INTENT)
    assert _headings(gather, "###")[0] == "2. Welcome and Explain"
    assert "### 1. " not in gather and "### 1b. " not in gather
    for gone in ("{headlessArgsFile}", "{autoBriefFile}", "{forgeTierRwHelper}", "halt-state.json"):
        assert gone not in gather, gone
    assert not {"autoBriefFile", "headlessArgsFile", "forgeTierFile", "forgeTierRwProbeOrder"} & set(
        _frontmatter(GATHER_INTENT))
    assert ("Step 0 (`references/preflight.md`) ran §1 and §1b, and it sends only an interactive run here."
            in _section(gather, "## Sequence"))
    # SKILL.md loads stage 0 for every mode, and its Stages table lists it first.
    assert "5. Load, read the full file, and execute `references/preflight.md`." in _read(SKILL_MD)
    stages = _section(_read(SKILL_MD), "## Stages")
    rows = [line for line in stages.splitlines() if re.match(r"^\| \d", line)]
    assert rows[0] == "| 0 | Preflight (every run) | references/preflight.md | Yes |", rows[0]


# A citation of the sections stage 0 now holds, under their old step.
OLD_STEP_RE = re.compile(r"(?i)step[ -]0?1 §1b?\b|gather-intent(?:\.md)? §1b?\b")


def test_no_brief_file_cites_the_moved_sections_under_their_old_step():
    stale = [f"{path.relative_to(SKILL_DIR).as_posix()}:{number}" for path in sorted(SKILL_DIR.rglob("*"))
             if path.is_file() for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if OLD_STEP_RE.search(line)]
    assert not stale, stale
    assert not OLD_STEP_RE.search(FORGE_TIER_RW.read_text(encoding="utf-8"))
    assert "Used by skf-brief-skill step 0 §1 and" in FORGE_TIER_RW.read_text(encoding="utf-8")


TIERS = ["Quick", "Forge", "Forge+", "Deep"]


def test_the_tier_glosses_are_one_set():
    """#1135 (leanness-7): step 1's welcome and step 4's review gloss each tier the same way."""
    [welcome] = [line for line in _read(GATHER_INTENT).splitlines() if line.startswith("(Substitute `{tier_gloss}`")]
    step_one = dict(re.findall(r'`(Quick|Forge\+?|Deep)` → "([^"]+)"', welcome))
    confirm = _read(REFERENCES / "confirm-brief.md")
    block = confirm[confirm.index("- **Forge tier glosses**"):confirm.index("- **`scripts_intent` / `assets_intent`")]
    step_four = dict(re.findall(r"^  - `(Quick|Forge\+?|Deep)`: (.+)$", block, re.M))
    assert list(step_one) == list(step_four) == TIERS, (step_one, step_four)
    assert step_one == step_four
    # The note that explained why the glosses are shown is gone, and the quote ends on the last gloss.
    assert "the gloss just clarifies" not in confirm
    assert "create-skill treats it as the user's spec\"\n" in confirm


AUTO_AND_QMD = (AUTO_BRIEF, AUTO_VALIDATE, QMD_REGISTRATION)
SCRIPTS_RULE = "- Let the scripts render the YAML and the envelope: one written by hand drifts from the schema."


@pytest.mark.parametrize("path", [pytest.param(path, id=path.stem) for path in AUTO_AND_QMD])
def test_the_auto_and_qmd_files_state_each_rule_as_the_failure_it_prevents(path):
    """#1135 (leanness-13, leanness-12): no all-caps rule or heading, and no rule a section of the file handles."""
    text = _read(path)
    for gone in ("Do NOT", "MUST", "STEP GOAL", "MANDATORY"):
        assert gone not in text, gone
    if path == QMD_REGISTRATION:
        assert "The brief is already written, so go on." in _section(text, "## Error Handling")
        return
    assert _headings(text, "##") == ["Goal", "Rules", "Sequence"]
    assert SCRIPTS_RULE in _section(text, "## Rules").splitlines()
    if path == AUTO_BRIEF:
        assert ("- Keep AN's scope fields as they are: AN derived them from the analysis this route skips."
                in _section(text, "## Rules").splitlines())
        [failed] = [line for line in text.splitlines() if line.startswith("- **Exit 2 (error):**")]
        assert failed.endswith("Go on to §4 without doc enrichment: it is best-effort.")
    else:
        assert [line for line in _section(text, "## Rules").splitlines() if line.startswith("- ")] == [
            SCRIPTS_RULE, "- The summary is always displayed, even in headless mode, for logging transparency"]
        summary = _section(text, "### 2. Present the Summary")
        assert "Pipeline:" not in summary and "quality target" not in summary
        rows = re.findall(r"^([A-Z][A-Za-z -]+):", summary.split("```", 2)[1], re.M)
        assert rows == ["Auto-Brief Summary", "Source", "Language", "Scope", "Docs", "Version", "Forge Tier",
                        "Description"], rows


# Text a brief file no longer holds: a key, a heading or a restatement #1135 cut.
CUT = ("writeBriefFile", "18 fields", "Scripts & Assets Detection", "STEP GOAL", "MANDATORY SEQUENCE", "Do NOT", "MUST",
       "Determinism delegation", "fsync", "translates flat", "Scope guidance for first-time users",
       "documented rule table")


def test_no_brief_file_keeps_a_rule_another_file_or_helper_owns():
    """#1135 (leanness-5, -6, -8, -10): each rule is stated where it is used, or left to the helper that applies it."""
    for path in sorted(SKILL_DIR.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for gone in CUT:
                assert gone not in text, (path.relative_to(SKILL_DIR).as_posix(), gone)
    holders = sorted(path.relative_to(SKILL_DIR).as_posix() for path in sorted(SKILL_DIR.rglob("*.md"))
                     if "versionResolutionFile" in _read(path))
    assert holders == ["references/analyze-target.md"], holders
    resolution = _read(REFERENCES / "version-resolution.md")
    assert _headings(resolution, "##") == ["Detection Algorithm", "Precedence"]
    assert resolution.endswith("\n## Precedence\n\n`target_version`, else the detected version, else 1.0.0: "
                               "`skf-write-skill-brief.py` applies it and keeps `target_version == version`.\n")
    assert "Loaded by step 2 §4b when §4.2's fallback read the source.\n" in resolution
    # Step 4 points at the fields instead of listing them, and states the 1.0.0 default where it shows the version.
    confirm = _read(REFERENCES / "confirm-brief.md")
    assemble = _section(confirm, "### 1. Assemble Complete Brief")
    assert "- **name:**" not in assemble and "Compile all gathered data" not in assemble
    assert "§2 shows the fields the user reviews, and step 5 §3 names every key the writer takes." in assemble
    # The bindings the cut list alone stated: §2 shows these before step 5 runs.
    assert ("On a derive run, `forge_tier` is the `tier` step 0 §1 bound, `created` is today's date and `created_by` "
            "is `{user_name}`; an unset `scripts_intent` or `assets_intent` is `detect`.") in assemble
    assert "Version:    {version; a derive run's is the detected version, else 1.0.0}\n" in confirm
    # Step 5 passes the payload and branches on the result; the writer's internals are its own.
    write = _section(_read(WRITE_BRIEF), "### 3. Write the Brief")
    assert "Pass every key, `null` when unset: the writer decides what reaches the YAML." in write
    assert ("Either way, on success the writer prints `{status, brief_path, version, bytes, warnings}`, which the "
            "call saves in `{run_dir}/brief-write.json`.") in write
    assert ("It returns `{language, confidence, detection_source, fallback_to_extension_frequency, source_language, "
            "detected_languages}`: use them directly, §5 shows them.") in _read(ANALYZE_TARGET)
    assert "The script upserts the entry by `name`.\n" in _read(QMD_REGISTRATION)
    assert ("**Recommend a scope type.** Present the recommender's pick as the marked default, not five equal "
            "options.") in _read(SCOPE_DEFINITION)
    # The ratify force rule is stated in the Inputs cell, and the Headless row points at it.
    [headless] = [line for line in _read(CONTRACT).splitlines() if line.startswith("| **Headless** |")]
    assert ("routes step 1 to the ratify path described in the `from_brief` Inputs cell rather than deriving a new "
            "brief.") in headless and "`force`" not in headless.split("from_brief <path>", 1)[1]
    assert _read(SKILL_DIR / "assets" / "scope-templates.md").endswith(
        'Prompt: "Does this component library scope look right? Adjust before continuing."\n')
