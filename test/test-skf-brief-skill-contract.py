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

#1136: an interactive run asks only what it cannot take, derive or
default. Step 1 runs the draft-resume check right after the target, asks
for no doc URL, authority or version, binds `first_brief` from its `find`
instead of asking a Y/N, and drops §5 and §6's prompt; §7 sets the
authority as the headless gate does, with no warning, and marks each value
the user did not give "(default)". Step 3 shows a scope type's flow in one
message and its summary does not wait, so step 4 is the one scope
confirmation: it shows the scripts and assets intent as `detect` defaults
and notes a defaulted 1.0.0 version.

#1137: what the user or an earlier run decided reaches the brief. Step 1's
draft-resume check takes the draft from skf-brief-drafts.py `find`, which
matches a normalized target, and then offers `[U] Revise` of a finished
brief that `briefs` lists, through the ratify route; draft-checkpoint.md
Half 1 reads the name, the mtime and `holds_scope` from that result and
binds `{draft_name}`. Step 4 §4 writes the draft after each adjustment, a
rename moves it, and step 5 §3 removes a draft a failed rename left. Asides
noted at step 1 are `scope_note_candidates`, which §7 shows, the draft
holds and step 3 §5 seeds into `scope.notes`. Step 4's menu has no `[A]` or
`[P]`, whose results never reached the brief.

#1138: step 2 §5 prints the `export_count` and `dependency_count`
skf-extract-public-api.py writes, the count step 3's recommender reads, and
step 3 takes its tier-A and headless public-API file sets from the
extractor's `--print` and quick mode's `reexport_files`. The tier-A surface
and the headless boundary defaults are files of their own, loaded only for a
monorepo subpackage with coarse globs and a headless run with no `include`,
and SKILL.md names the one recipe-runner exception to its cheap signals.

#1139: step 1 §3.2, step 3 §2b and the headless input gate check doc URLs
with one skf-check-urls.py call, which follows redirects and asks again
with GET when a server refuses HEAD, and run curl only when the helper is
missing. The [auto] route skips doc detection for a source that is not a
GitHub repository URL, and every `{name}` step-auto-brief.md uses is bound.
The portfolio check and the QMD embed verification are each one
skf-qmd-portfolio-similarity.py call.

No test runs the step prose, so these checks pin it, and they run the
commands it documents against the emitter and validate what it prints
against the schema.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
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
TIER_A_SURFACE = REFERENCES / "tier-a-surface.md"
HEADLESS_DEFAULTS = REFERENCES / "headless-boundary-defaults.md"
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
HALT_SITE_FILES = (PREFLIGHT, GATHER_INTENT, HEADLESS_ARGS, RATIFY, ANALYZE_TARGET, SCOPE_DEFINITION, HEADLESS_DEFAULTS,
                   AUTO_BRIEF, AUTO_VALIDATE, WRITE_BRIEF)
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
    # preflight 3, headless-args 1, gather-intent-ratify 2, analyze-target 4, headless-boundary-defaults 1 (#1138:
    # scope-definition.md's, moved with the defaults), step-auto-brief 4, step-auto-validate 2, write-brief 3
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
                # #1138: the public-api default's warn line is the one scope-definition.md §3's GATE records
                assert RECORD in line or "§3's GATE records" in line, where
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
    assert ("Version:    {version; a derive run's is the detected version when it is full X.Y.Z, else 1.0.0 "
            "(default)}\n") in confirm
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
    # #1136 (enhancement-2): the [C] flow ends at its variant question, since step 4 confirms the scope.
    assert _read(SKILL_DIR / "assets" / "scope-templates.md").endswith(
        'Prompt: "I detected {count} design system variants: {list with counts}. Which is the primary variant? '
        'Include all? [Y/n]"\n')


# --------------------------------------------------------------------------
# #1136: steps 1 and 3 ask only what they cannot take, derive or default, and step 4 confirms the scope once
# --------------------------------------------------------------------------


DRAFT_CHECKPOINT = REFERENCES / "draft-checkpoint.md"
CONFIRM_BRIEF = REFERENCES / "confirm-brief.md"
SCOPE_TEMPLATES = SKILL_DIR / "assets" / "scope-templates.md"
# A quoted prompt that ends in a question: `"...?"` or `"**...?**"`.
QUESTION_RE = re.compile(r'\?\**"')
# The step 1 sections a resumed draft skips, in both files that list them.
SKIPPED_SECTIONS = "**§3b, §4, §6, §7, and §7b are"


def test_the_draft_check_is_the_first_question_after_the_target():
    """#1136 (enhancement-1, leanness-4): §3.3 asks for no doc URL and no authority, so the draft-resume check, whose
    [Y] restores those answers, follows the validated target; §5 is gone from step 1 and from both skipped lists."""
    text = _read(GATHER_INTENT)
    between = text[text.index("#### 3.3 Branch"):text.index("**Draft-resume check.**")]
    assert not QUESTION_RE.search(between) and "Wait for" not in between, between
    for gone in ("Are you the maintainer", "documentation URLs you'd like", "### 5. Capture Scope Hints",
                 "Wait for confirmation or alternative", "Confirm the target."):
        assert gone not in text, gone
    assert "**Draft-resume check.** Right after the target is validated, before step 1 asks anything else" in text
    assert "then end with the draft-resume check" in text and "continue at the draft-resume check below" in text
    assert not re.search(r"§5\b", text)
    draft = _read(DRAFT_CHECKPOINT)
    assert "the offer is the first question after the target is validated" in _section(
        draft, "## Half 1: Resume Check (loaded from §3 after the target is confirmed)")
    assert "(§3b version check, §4 intent, §6 name, §7 summary)" in draft
    assert set(re.findall(r"§5\w*", draft)) == {"§5c"}
    for path in (GATHER_INTENT, DRAFT_CHECKPOINT):
        assert _read(path).count(SKIPPED_SECTIONS) == 1, path.name


def test_step_one_shows_what_it_derived_or_defaulted_instead_of_asking():
    """#1136 (enhancement-1, enhancement-9, leanness-4): §3b asks for no version, §4 binds `first_brief` instead of
    asking a Y/N, §6 neither asks nor waits, and §7 sets the authority and marks each value the user did not give."""
    text = _read(GATHER_INTENT)
    # A target answer that states more pre-fills it: an expert goes from the target to the §7 message.
    [prefill] = [line for line in _section(text, "#### 3.1 Collect target").splitlines()
                 if line.startswith("Wait for user response. **Parse the response")]
    for needle in ("scope hints, supplemental doc URLs, source authority and a proposed name (§6)",
                   "§3b checks a pre-filled version, §4 asks only for a missing intent, and §7 shows the rest"):
        assert needle in prefill, needle
    version = _section(text, "### 3b. Gather Target Version")
    assert "Ask nothing here when §3.1 pre-filled no version" in version and "Wait for" not in version
    intent = _section(text, "### 4. Gather User Intent")
    assert "[Y/N]" not in intent and "**`first_brief`.** Bind it from this `find`" in intent
    assert "When §3.1 pre-filled the intent, skip the question: §7 shows it." in intent
    assert 'find "{forge_data_folder}" -maxdepth 2 -name "skill-brief.yaml" -print -quit' in intent
    assert "an unset `first_brief` counts as false" in intent
    name = _section(text, "### 6. Derive Skill Name")
    assert "Ask nothing here" in name and "Wait for" not in name and not QUESTION_RE.search(name)
    assert "[C] keeps `{name}` and leaves the overwrite question to step 5 §2b" in name
    summary = _section(text, "### 7. Summarize Gathered Intent")
    assert '"(default)" marks a value the user did not give' in summary
    for line in ("- **Skill name:** {name, with (default) when §6 derived it}",
                 "- **Source authority:** {official/community/internal, with (default) when this section set it, or "
                 "(forced for docs-only) when §3.2 set it}",
                 "- **Target version:** auto-detected in step 2 (default)", "- **Doc URLs:** none (default)"):
        assert line in summary.splitlines(), line
    assert "- **Target version:** 1.0.0 (default). With no source code to read it from" in summary
    # The authority is set as the headless gate sets it, with no warning: the summary shows it for the user to change.
    [authority] = [part for part in summary.split("\n\n") if part.startswith("**Source authority.**")]
    for needle in ("neither the §3.1 answer nor a resumed draft gave `source_authority`", "`gh api user --jq .login`",
                   "both lower-cased: a match is `official`", "Another login, a local path or a failed call is "
                   "`community`", "Record no warning", "(5-second timeout)",
                   "is `official` for a maintainer, `internal` for a private or company codebase and `community`"):
        assert needle in authority, needle
    # The authority alternate uses the value §7 settles, and the heads-up's briefs do not share the alternates' numbers.
    assert "when the authority, settled at the top of §7 before the list is shown" in text
    assert "{its heads-up, its briefs as bullets, not numbers, so a number picks only an alternate}" in summary
    description = _section(text, "### 7b. Synthesize Skill Description")
    assert "When `first_brief` (§4) is true" in description and "{If first_brief is true:}" in description
    [edit] = [line for line in _section(text, "### 8. Present MENU OPTIONS").splitlines()
              if line.startswith("- IF an edit")]
    assert "the number of a §6 alternate" in edit and "a new version the §3b check" in edit
    assert "a new version or doc URL §3b's doc-URL question when both are set" in edit
    heads_up = _read(PORTFOLIO_CHECK)
    assert "Continue with `{name}`, or pick a different name?" not in heads_up
    assert "show them in the step 1 §7 message as a heads-up, *not* a HALT" in heads_up


def test_first_brief_replaces_the_first_timer_rail():
    """#1136 (enhancement-9): step 3's reassurance and the voice examples key on `first_brief`, not a rail."""
    for path in sorted(SKILL_DIR.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for gone in ("first-time user", "First-timer", "first-timer rail"):
                assert gone not in text, (path.relative_to(SKILL_DIR).as_posix(), gone)
    assert "when `first_brief` is true" in _section(_read(SCOPE_DEFINITION), "### 2c. Offer Scope Templates")
    assert ("Loaded by step 1 only: §7b, or the headless input gate, composes the description from them, and on a "
            "first brief §7b shows one of them beside the candidate.") in _read(
                SKILL_DIR / "assets" / "description-voice-examples.md")
    assert "showing one beside it on a first brief" in _flow(_read(CUSTOMIZE).replace("#", " "))


def test_step_four_is_the_one_scope_confirmation():
    """#1136 (leanness-3, enhancement-2): step 3 shows a type's flow in one message, and no phase, summary or gate
    asks whether the scope looks right; the scripts and assets intent left step 3 for step 4."""
    texts = {path.name: _read(path) for path in (SCOPE_DEFINITION, SCOPE_TEMPLATES, CONTRACT)}
    for name, text in texts.items():
        for gone in ("wait for user input at each phase", "Does this look right", "### 5b.", "Phase 3: Confirmation",
                     "Phase 4: Scope Confirmation", "Any additional exclusions", "step 3: Confirm Gate"):
            assert gone not in text, (name, gone)
    scope = texts["scope-definition.md"]
    boundaries = _section(scope, "### 3. Define Boundaries Based on Selection")
    assert "Show the selected type's flow from `{scopeTemplatesPath}` in one message" in boundaries
    assert "For [C], run the component library detection below first" in boundaries
    supplemental = _section(scope, "### 2b. Confirm Supplemental Documentation (if doc_urls collected)")
    assert "Wait for" not in supplemental and "change them at step 4" in supplemental
    assert "**GATE [default: keep them]**" in supplemental and "Check the URLs with one call" in supplemental
    assert ("a URL the check below fails joins that message with its correct/keep choice, and an answer that does not "
            "take the choice up keeps the URL") in supplemental
    assert "Which pages should be included in the skill?" in scope  # a docs-only scope still picks its pages
    [reentry] = [line for line in _section(scope, "## Rules").splitlines()
                 if line.startswith("- **Re-entry from step 4 [R] revise:**")]
    assert "`scripts_intent`" not in reentry and "`assets_intent`" not in reentry
    assert "**Phase 2: Exclusions**" in texts["scope-templates.md"]


def test_step_four_marks_the_defaults_it_shows():
    """#1136 (enhancement-2, enhancement-7): step 4 marks a 1.0.0 fallback and an unset scripts or assets intent
    (default), notes the tag a defaulted source version sends create-skill to, and asks a reference app for its
    wiring scripts; a ratify run keeps its own version, so the note is for a derive run only."""
    confirm = _read(CONFIRM_BRIEF)
    review = _section(confirm, "### 2. Present Brief for Review")
    for prefix in ("Version:    ", "Scripts:    ", "Assets:     "):
        [line] = [line for line in review.splitlines() if line.startswith(prefix)]
        assert "(default)" in line, line
    # The [C] picks that step 3 no longer summarizes show here, the one scope confirmation.
    for line in ("  Registry: {scope.registry_path; omit this line entirely when unset}",
                 "  Variants: {scope.ui_variants names; omit this line entirely when unset}"):
        assert line in review.splitlines(), line
    assert "A headless run takes both from `normalized`" in _section(confirm, "### 1. Assemble Complete Brief")
    attention = _section(confirm, "### 3. Highlight Items Needing Attention")
    # Create Skill reads a local path as checked out, a Quick-tier remote at HEAD and a target_ref as given.
    assert ("{If this is a derive run, target_version and target_ref are unset, source_type is source, source_repo is "
            "a GitHub URL and no X.Y.Z version was detected:}\n\"**Note:** no X.Y.Z version was detected, so the brief "
            "says 1.0.0, and create-skill at Forge tier or above will look for tag 1.0.0 or v1.0.0. Give the version now "
            "if you know it.\"") in attention
    assert ("{If scope.type is reference-app and scripts_intent or assets_intent is the detect default:}\n"
            "\"**Scripts and assets:** a reference app often ships wiring scripts") in attention
    assert "scripts or assets intent" in _section(confirm, "### 4. Handle Inline Adjustments")
    [after_r] = [line for line in confirm.splitlines() if line.startswith("After a `[R]` pass on a ratify run")]
    assert "take `scope.*` and `doc_urls` from step 3" in after_r
    model = _read(REPO / "docs" / "skill-model.md")
    assert "Brief Skill asks whether you maintain the library" not in model
    assert "An interactive run shows the pick in its summary for you to change" in model


# --------------------------------------------------------------------------
# #1137: drafts found by a normalized target, a finished brief to revise, step 4 edits checkpointed, asides noted
# --------------------------------------------------------------------------


ATOMIC_WRITE = REPO / "src" / "shared" / "scripts" / "skf-atomic-write.py"
BASH_BLOCK_RE = re.compile(r"^```bash\n(?P<body>.*?)^```\n", re.DOTALL | re.M)
HALF_1 = "## Half 1: Resume Check (loaded from §3 after the target is confirmed)"
HALF_2 = "## Half 2: Checkpoint Write (loaded from step 1 §8, step 3 §5c and step 4 §4)"
RENAME_RM = 'rm -f "{forge_data_folder}/{draft_name}/.brief-draft.json"'


def _bash_blocks(text: str, needle: str) -> list[str]:
    return [m.group("body") for m in BASH_BLOCK_RE.finditer(text) if needle in m.group("body")]


def test_no_brief_file_matches_a_target_by_hand_or_offers_the_unread_menu_items():
    """#1137 (determinism-4, enhancement-5, enhancement-6): no grep, no sort by eye, no [A] or [P] item whose
    result never reached the brief, and no aside left "carried forward" with nothing reading it."""
    for path in sorted(SKILL_DIR.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for gone in ("grep -lF", "most-recently-modified", "advancedElicitationSkill", "partyModeSkill",
                         "[A] Advanced Elicitation", "[P] Party Mode", "carried forward into the brief's"):
                assert gone not in text, (path.relative_to(SKILL_DIR).as_posix(), gone)
    confirm = _read(CONFIRM_BRIEF)
    assert "Display: **Select an Option:** [R] Revise Scope [C] Approve and Write [X] Cancel and exit\n" in confirm
    assert not re.search(r"^- IF [AP]:", confirm, re.M)
    synergy = _read(REPO / "docs" / "bmad-synergy.md")
    assert "Brief Skill's scope and confirmation menus offer them" not in synergy
    assert "Analyze Source's recommendation menu offers them as `[A]` and `[P]`." in synergy


def test_the_draft_resume_check_takes_the_draft_and_its_fields_from_the_helper():
    """#1137 (determinism-4): step 1 runs `find` and hands its result to Half 1, which takes the name, the mtime and
    `holds_scope` from it and binds `{draft_name}`; with no helper the check offers nothing and goes on."""
    gather = _read(GATHER_INTENT)
    assert re.search(r"^briefDraftsProbeOrder:$", gather, re.M)
    check = gather[gather.index("**Draft-resume check.**"):gather.index("### 3b. Gather Target Version")]
    for needle in ("Resolve `{briefDraftsHelper}` from `{briefDraftsProbeOrder}` (first existing path wins).",
                   "letter case, a trailing slash, `.git`, `owner/repo` or a relative path",
                   "the repo URL (for a package, §3.1b's `resolved_url`, not the name typed)",
                   "a docs-only draft whose `doc_urls` do", "the docs-only briefs whose `doc_urls` do",
                   "When `{briefDraftsHelper}` has no path, or a call prints no JSON, offer nothing, warn nothing and "
                   "continue at §3b", "It prints `{name, path, mtime, holds_scope}`, or `null`.",
                   "load `{draftCheckpointFile}` and follow Half 1 (Resume Check) with that result"):
        assert needle in check, needle
    assert "warn:" not in check
    half_1 = _section(_read(DRAFT_CHECKPOINT), HALF_1)
    assert ("passes the result of its `find` call: the draft folder's `name`, which is the candidate skill name, the "
            "draft's `path`, its `mtime` (UTC) and `holds_scope`") in half_1
    assert "(last updated: {mtime})" in half_1
    [resume] = [line for line in half_1.splitlines() if line.startswith("Bind the skill name and `{draft_name}`")]
    assert "read the JSON at its `path`" in resume and "`scope_note_candidates`" in resume
    for prefix, flag in (("- **A draft written after step 3**", "(`holds_scope` is true)"),
                         ("- **A draft written by step 1**", "(`holds_scope` is false)")):
        [line] = [line for line in half_1.splitlines() if line.startswith(prefix)]
        assert line.startswith(f"{prefix} {flag}"), line
    [fresh] = [line for line in half_1.splitlines() if line.startswith("Leave the draft in place")]
    assert "go on to the check's finished-brief step (gather-intent §3), then to §3b" in fresh


def test_step_four_checkpoints_each_adjustment_and_a_rename_moves_the_draft():
    """#1137 (enhancement-8): step 4 §4 follows Half 2 after an adjustment on an interactive derive run, Half 2
    removes the draft under the old name once the write under the new one succeeds, and step 5 removes a draft a
    failed rename write left."""
    half_2 = _section(_read(DRAFT_CHECKPOINT), HALF_2)
    # The step 3 fields, scope included, even when the step 3 §5c write failed (review of #1137).
    assert "- At step 4 (§4), the same fields as after step 3, with the adjustment applied." in half_2
    [step_one] = [line for line in half_2.splitlines() if line.startswith("- From step 1 (§8):")]
    assert "`scope_note_candidates` (if any)" in step_one
    assert half_2.index("{atomicWriteHelper} write") < half_2.index(RENAME_RM)
    assert ("**A new name.** After a write that succeeds, when `{draft_name}` is set and differs from `{skill-name}`"
            in half_2) and "then bind `{draft_name}` to `{skill-name}`; a first write only binds it" in half_2
    assert "A failed write keeps `{draft_name}` and its draft, which step 5 §3 removes" in half_2
    confirm = _read(CONFIRM_BRIEF)
    assert re.search(r"^draftCheckpointFile: 'references/draft-checkpoint\.md'$", confirm, re.M)
    steps = _section(confirm, "### 4. Handle Inline Adjustments").splitlines()
    follow = ("- On an interactive run that is not a ratify run, load `{draftCheckpointFile}` and follow Half 2 "
              "(Checkpoint Write)")
    [checkpoint] = [i for i, line in enumerate(steps) if line.startswith(follow)]
    assert steps[checkpoint - 1] == "- Make the adjustment"
    assert steps[checkpoint + 1] == "- Re-present the updated brief"
    [other] = [line for line in confirm.splitlines() if line.startswith("- IF Any other comments or queries:")]
    assert "apply any field adjustments as §4 does" in other
    cleanup = [line for line in _read(WRITE_BRIEF).splitlines() if line.startswith("**Draft cleanup.**")]
    assert len(cleanup) == 1 and ("`{forge_data_folder}/{draft_name}/.brief-draft.json` too when `{draft_name}` is "
                                  "set and differs from `{skill-name}`") in cleanup[0]


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented blocks in a POSIX bash")
def test_a_rename_writes_the_draft_under_the_new_name_and_removes_the_old_one(tmp_path):
    """The step 4 rename of the I/O matrix: Half 2's write under `zod-v4`, then its rename rule for `zod`."""
    text = _section(_read(DRAFT_CHECKPOINT), HALF_2)
    [write] = _bash_blocks(text, "{atomicWriteHelper}")
    [rename] = _bash_blocks(text, RENAME_RM)
    forge, run_dir = tmp_path / "forge", tmp_path / "run"
    run_dir.mkdir()
    old = forge / "zod" / ".brief-draft.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"target_repo": "https://github.com/colinhacks/zod"}', encoding="utf-8")
    draft = {"target_repo": "https://github.com/colinhacks/zod", "intent": "zod's v4 API", "scope": {"type": "x"}}
    script = (write + rename).replace("<the draft, as one JSON object>", json.dumps(draft))
    for placeholder, value in (("{run_dir}", run_dir.as_posix()), ("{forge_data_folder}", forge.as_posix()),
                               ("{skill-name}", "zod-v4"), ("{draft_name}", "zod"),
                               ("uv run {atomicWriteHelper}", f'"{sys.executable}" "{ATOMIC_WRITE.as_posix()}"')):
        script = script.replace(placeholder, value)
    proc = subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8", timeout=120,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads((forge / "zod-v4" / ".brief-draft.json").read_text(encoding="utf-8")) == draft
    assert not old.exists()


def test_noted_asides_reach_the_summary_the_draft_and_scope_notes():
    """#1137 (enhancement-6): the asides step 1 notes are `scope_note_candidates`: §7 shows them, the draft holds
    them, and step 3 §5 adds each one `scope.notes` lacks before its summary, then clears the list, so step 4, the
    one scope confirmation, is where the user drops any."""
    gather = _read(GATHER_INTENT)
    [prefill] = [line for line in _section(gather, "#### 3.1 Collect target").splitlines()
                 if line.startswith("Wait for user response. **Parse the response")]
    assert "plus each out-of-scope aside as a `scope_note_candidates` line (§4)" in prefill
    intent = _section(gather, "### 4. Gather User Intent")
    assert ("Add it as one line to `scope_note_candidates`, which §7 shows and step 3 seeds into "
            "`scope.notes`") in intent
    [capture] = [line for line in intent.splitlines() if line.startswith("**Capture, don't interrupt.**")]
    assert "\u2014" not in capture
    summary = _section(gather, "### 7. Summarize Gathered Intent")
    assert ('{If scope_note_candidates is not empty:}\n- **Noted for scope notes:** {the lines, joined with "; "}\n'
            in summary)
    scope = _section(_read(SCOPE_DEFINITION), "### 5. Summarize Scope Decisions")
    seed = scope.index("**Noted asides.** When `scope_note_candidates` (step 1 §3.1 and §4) is not empty")
    assert seed < scope.index("Show this summary with no wait")
    assert ("append each of its lines that `scope.notes` does not already hold to `scope.notes`, each on a line of "
            "its own after the notes this step set") in scope
    assert "then clear the list, so a step 4 `[R]` pass does not add back a line the user dropped there" in scope
    assert ("{If this section added lines from scope_note_candidates:}\n**Noted in step 1:** {those lines} (drop any "
            "at step 4)") in scope


# --------------------------------------------------------------------------
# #1138: counts and file sets read from skf-extract-public-api.py, and the tier-A and headless boundary rules
# loaded only where they apply
# --------------------------------------------------------------------------

EXTRACTOR = REPO / "src" / "shared" / "scripts" / "skf-extract-public-api.py"
RECOMMENDER = REPO / "src" / "shared" / "scripts" / "skf-recommend-scope-type.py"
CARVED = (SCOPE_DEFINITION, TIER_A_SURFACE, HEADLESS_DEFAULTS)


def test_step_two_and_the_recommender_show_the_same_export_count(tmp_path):
    """determinism-6: on a barrel that exports one name from two files, step 2 §4.1's documented call writes the
    `export_count` §5 prints, and step 3 §2c's recommender, reading that file, recommends on the same number."""
    analyze = _read(ANALYZE_TARGET)
    procedure = _section(analyze, "#### 4.1 Procedure \u2014 script-supported languages")
    [call] = re.findall(r"^ *(uv run \{extractPublicApiHelper\} --mode quick [^\n]*)$", procedure, re.M)
    assert '> "{run_dir}/extract.json"' in call
    source = tmp_path / "source"
    for rel, text in {"package.json": '{"name": "demo", "version": "1.0.0", "dependencies": {"zod": "3"}}\n',
                      "src/a.ts": "export const foo = 1;\nexport const bar = 2;\n",
                      "src/b.ts": "export const foo = 3;\n"}.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(text.encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "tree.json").write_bytes(json.dumps(["package.json", "src/a.ts", "src/b.ts"]).encode("utf-8"))
    # a local source: no --repo or --ref, and one --entry-file per entry file
    line = (re.sub(r" \[--repo [^\]]*\]", "", call.split(" > ", 1)[0])
            .replace("<language>", "typescript").replace("<source root>", source.as_posix())
            .replace("{run_dir}", run_dir.as_posix()).replace("<manifest path>", "package.json")
            .replace('--entry-file "<entry path>"', '--entry-file "src/a.ts" --entry-file "src/b.ts"'))
    proc = _run([sys.executable, str(EXTRACTOR), *shlex.split(line)[3:]])
    assert proc.returncode == 0, proc.stderr
    (run_dir / "extract.json").write_bytes(proc.stdout.encode("utf-8"))
    extract = json.loads(proc.stdout)
    assert [e["name"] for e in extract["exports"]] == ["foo", "bar", "foo"]
    assert (extract["export_count"], extract["dependency_count"]) == (2, 1)
    summary = _section(analyze, "### 5. Report Analysis Summary")
    assert "**Public Exports/Entry Points ({export_count}):**" in summary
    assert "**Package:** {package_name} ({dependency_count} dependencies)" in summary
    payload = {"signals": {"wants_wiring_pattern": False, "named_module_subset": [], "wants_narrow_api": True},
               "module_count": 1, "source_type": "source", "mode": "interactive"}
    proc = _run([sys.executable, str(RECOMMENDER), "--tree-file", str(run_dir / "tree.json"), "--extract-file",
                 str(run_dir / "extract.json")], stdin=json.dumps(payload))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["signals"]["export_count"] == extract["export_count"]
    assert ("The script reads the `export_count` step 2 §4 wrote there (0 after §4.2, where the public-api rule does "
            "not fire)") in _section(_read(SCOPE_DEFINITION), "### 2c. Offer Scope Templates")


def test_no_file_set_is_built_by_hand():
    """determinism-7, architecture-7: no one-liner, no read by eye and no §3c is left, scope-definition.md calls no
    recipe runner, and it fits its 6,000-token budget (chars/4, the fallback SKILL.md's budget uses)."""
    for path in CARVED:
        text = _read(path)
        for gone in ("python -c", "by eye", "\u00a73c"):
            assert gone not in text, (path.name, gone)
        assert "\u2014" not in text or path == SCOPE_DEFINITION, path.name
    scope = _read(SCOPE_DEFINITION)
    assert "{extractPublicApiHelper}" not in scope and "extractPublicApiProbeOrder" not in scope
    assert len(scope) // 4 < 6000, len(scope)
    assert "\u00a73c" not in _read(WRITE_BRIEF) and "\u00a73c" not in _read(REFERENCES / "confirm-brief.md")
    assert "from step 3's references/tier-a-surface.md" in _read(WRITE_BRIEF)


def test_the_carved_files_load_only_where_they_apply():
    """architecture-7: an interactive run on a repository that is not a monorepo loads neither file: the tier-A
    surface loads from §3b for a workspace with coarse globs, the defaults from §3's GATE for a headless run with
    no `include`, and the defaults load the tier-A file's runner alone at Forge tier and above."""
    scope = _read(SCOPE_DEFINITION)
    frontmatter = scope[4:scope.index("\n---\n", 4)]
    assert "tierASurfaceFile: 'references/tier-a-surface.md'" in frontmatter
    assert "headlessBoundaryDefaultsFile: 'references/headless-boundary-defaults.md'" in frontmatter
    [tier_a] = [line for line in scope.splitlines() if "load `{tierASurfaceFile}`" in line]
    assert tier_a in _section(scope, "### 3b. Monorepo Subpackage Convention")
    assert tier_a.startswith("**Tier-A surface.** When `monorepo_workspace` is set and `scope.include` uses coarse "
                             "directory globs")
    assert tier_a.endswith("Otherwise leave `scope.tier_a_include` unset.")
    [defaults] = [line for line in scope.splitlines() if "load `{headlessBoundaryDefaultsFile}`" in line]
    assert defaults.startswith("**GATE [default: the scope type's boundary default]**: **Headless:**")
    assert ("Otherwise (`{headless_mode}` true and no `include` argument), load `{headlessBoundaryDefaultsFile}` and "
            "take the resolved scope type's default it gives") in defaults
    [runner] = [line for line in _read(HEADLESS_DEFAULTS).splitlines() if "load `{tierASurfaceFile}`" in line]
    assert "At Forge tier and above, load `{tierASurfaceFile}` for its recipe runner" in runner
    # no other file loads them, and neither is a stage
    for path in sorted(SKILL_DIR.rglob("*.md")):
        if path in (SCOPE_DEFINITION, HEADLESS_DEFAULTS):
            continue
        text = _read(path)
        for name in ("{tierASurfaceFile}", "{headlessBoundaryDefaultsFile}", "references/headless-boundary-defaults",
                     "load `references/tier-a-surface"):
            assert name not in text, (path.name, name)
    for path in (TIER_A_SURFACE, HEADLESS_DEFAULTS):
        assert "nextStepFile" not in _read(path), path.name
    assert "extractPublicApiProbeOrder:" in _read(TIER_A_SURFACE)
    assert "tierASurfaceFile: 'references/tier-a-surface.md'" in _read(HEADLESS_DEFAULTS)


def test_skill_md_names_the_one_recipe_runner_exception():
    """architecture-4: the Overview's cheap signals name the one place step 3 runs create-skill's recipe runner."""
    [line] = [line for line in _read(SKILL_MD).splitlines() if "not full AST extraction" in line]
    assert ("Scope on cheap signals (manifests, top-level exports, intent), not full AST extraction, with one "
            "exception: at Forge tier and above, step 3 runs create-skill's recipe runner only to pin a file list a "
            "glob cannot express (`scope.tier_a_include` and the headless `public-api` include).") in line
    assert "\u2014" not in line
    assert len(_read(SKILL_MD)) // 4 < 2500


# --------------------------------------------------------------------------
# #1139: the doc-URL, portfolio and embed checks are helper calls, and doc detection reads only GitHub sources
# --------------------------------------------------------------------------

CHECK_URLS = REPO / "src" / "shared" / "scripts" / "skf-check-urls.py"
DETECT_DOCS = REPO / "src" / "shared" / "scripts" / "skf-detect-docs.py"
CHECK_URLS_CALL = "uv run {checkUrlsHelper} --timeout 5 --urls-file - <<'SKF_URLS'"
CHECK_URLS_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-check-urls.py",
                    "{project-root}/src/shared/scripts/skf-check-urls.py"]
PORTFOLIO_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-qmd-portfolio-similarity.py",
                   "{project-root}/src/shared/scripts/skf-qmd-portfolio-similarity.py"]
CURL_FALLBACK = ("When `{checkUrlsHelper}` has no path, run `curl -sIL --max-time 5 \"{url}\"` for each URL instead and take "
                 "a 2xx or 3xx on its last status line as `ok`.")
DOCS_BRANCH = "#### 3.2 Branch \u2014 Documentation URLs (docs-only)"
SUPPLEMENTAL = "### 2b. Confirm Supplemental Documentation (if doc_urls collected)"
DERIVE = "### 5. Derive the Brief Fields"
# Each site that checks doc URLs, the section that holds its check, and the outcome a URL that is not `ok` keeps.
URL_CHECK_SITES = (
    (GATHER_INTENT, DOCS_BRANCH,
     'warn `"Could not reach {url} ({status or error}). Confirm the URL is correct, or proceed anyway."`'),
    (SCOPE_DEFINITION, SUPPLEMENTAL, 'warn `"Could not reach {url} ({status or error})."`'),
    (HEADLESS_ARGS, DERIVE, 'log `"warn: could not reach {url} ({status or error})"`'),
)
# A `{name}` placeholder: prose with spaces (`{first error message}`) and JSON (`{"interactive": ...}`) are not one.
PLACEHOLDER_NAME_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)\}")


@pytest.mark.parametrize("path,heading,outcome", [pytest.param(*site, id=site[0].stem) for site in URL_CHECK_SITES])
def test_each_doc_url_check_is_one_helper_call(path, heading, outcome):
    """determinism-5: the three sites hold the same call and probe order, branch on `ok`, and run curl only when the
    helper is missing."""
    text = _read(path)
    section = _section(text, heading)
    command, body = _heredoc(section, "SKF_URLS")
    assert command == CHECK_URLS_CALL and "one per line" in body
    assert _frontmatter(path)["checkUrlsProbeOrder"] == CHECK_URLS_PROBE
    assert re.search(r"[Rr]esolve `\{checkUrlsHelper\}` from `\{checkUrlsProbeOrder\}` \(first existing path wins\)",
                     section)
    assert "A URL that is `ok` passes silently." in section
    assert outcome in section and "with `{status or error}` from its entry" in section
    # No header dump is read by hand: the one curl is the clause for a missing helper.
    for gone in ("curl -sI ", "HEAD-check", "parallel Bash calls"):
        assert gone not in text, gone
    assert text.count("curl ") == 1 and CURL_FALLBACK in section
    for line in section.splitlines():
        if "{checkUrlsHelper}" in line or "could not reach" in line.lower():
            assert "\u2014" not in line, line


def test_a_url_that_fails_keeps_each_sites_outcome():
    """Step 1 and step 3 re-prompt with a correct/keep choice and check a corrected URL the same way; the input gate
    keeps the URL and records one warning per failure; step 3 does not check again what the input gate checked."""
    scope = _section(_read(SCOPE_DEFINITION), SUPPLEMENTAL)
    assert "step 1's input gate has checked them, so skip the check below." in scope
    assert "offer step 1 §3.2's correct/keep choice, a corrected URL checked the same way" in scope
    gather = _section(_read(GATHER_INTENT), DOCS_BRANCH)
    assert "re-prompt for a corrected URL, checked the same way, or `[K] Keep anyway`" in gather
    [doc_urls] = [line for line in _section(_read(HEADLESS_ARGS), DERIVE).splitlines()
                  if line.startswith("- **Doc URLs:**")]
    assert "Keep any other" in doc_urls and RECORD_FILE in doc_urls
    assert "Record the failures one at a time" in doc_urls


class _RefusesHead(http.server.BaseHTTPRequestHandler):
    """A docs server that answers HEAD with 405 and GET with 200 at /docs, and 404 anywhere else."""

    def _answer(self):
        status = 404 if self.path != "/docs" else 405 if self.command == "HEAD" else 200
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_HEAD = _answer  # noqa: N815 - http.server's names
    do_GET = _answer  # noqa: N815

    def log_message(self, *args):
        pass


def test_the_headless_call_takes_a_url_that_refuses_head():
    """The input gate's documented call, run on a local server URL whose HEAD answers 405 and GET 200: its entry is
    `ok`, so §5 records nothing for it, while a missing page is not."""
    command, _ = _heredoc(_section(_read(HEADLESS_ARGS), DERIVE), "SKF_URLS")
    words = shlex.split(command.split(" <<", 1)[0])
    assert words[:3] == ["uv", "run", "{checkUrlsHelper}"]
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RefusesHead)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        env = {key: value for key, value in os.environ.items() if "proxy" not in key.lower()}
        proc = subprocess.run([sys.executable, str(CHECK_URLS), *words[3:]], input=f"{base}/docs\n{base}/gone\n",
                              capture_output=True, text=True, encoding="utf-8", timeout=60, check=False, env=env)
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [{"url": f"{base}/docs", "ok": True, "status": 200, "error": None},
                                       {"url": f"{base}/gone", "ok": False, "status": 404, "error": None}]


def _auto_brief_bound_names() -> set[str]:
    """The names step-auto-brief.md may use: its frontmatter keys and the helpers their probe orders resolve, the
    names it binds itself, and the run names whose binders are checked here."""
    front = _frontmatter(AUTO_BRIEF)
    body = _read(AUTO_BRIEF).split("\n---\n", 1)[1]
    bound = set(front) | {key[:-len("ProbeOrder")] + "Helper" for key in front if key.endswith("ProbeOrder")}
    bound |= set(re.findall(r"`([A-Za-z][\w-]*)` \u2190", body))
    bound |= set(re.findall(r"bind `\{([A-Za-z][\w-]*)\}`", body))
    preflight, skill = _read(PREFLIGHT), _read(SKILL_MD)
    assert "Bind `{run_dir}` \u2190 the path the last command prints." in preflight
    assert "read `brief_path` from the pipeline data context" in _section(preflight, "### 1b. Route by Mode")
    assert "`{emitEnvelopeHelper}` \u2190 `{project-root}/_bmad/skf/shared/scripts/" in skill
    [config] = [line for line in skill.splitlines() if line.strip().startswith("- `project_name`")]
    assert "`forge_data_folder`" in config and "`communication_language`" in config
    return bound | {"run_dir", "brief_path", "emitEnvelopeHelper", "forge_data_folder", "communication_language"}


def test_every_placeholder_the_auto_brief_uses_is_bound():
    """architecture-8: a `{name}` the [auto] route never binds, as `{local_clone_path}` was, reaches a command as
    text. A `suppressed` entry's line logs the entry's own `{url}` and `{reason}`."""
    bound = _auto_brief_bound_names()
    body = _read(AUTO_BRIEF).split("\n---\n", 1)[1]
    unbound = [(number, name) for number, line in enumerate(body.splitlines(), 1)
               for name in PLACEHOLDER_NAME_RE.findall(line)
               if name not in bound and not ("`suppressed`" in line and name in ("url", "reason"))]
    assert not unbound, unbound
    assert "local_clone_path" not in _read(AUTO_BRIEF) and "--local-path" not in _read(AUTO_BRIEF)


def test_a_source_that_is_not_a_github_repository_skips_doc_detection():
    """architecture-8: the detector reads only a GitHub repository URL and exits 2 on a local path, so the [auto]
    route skips §2 and §3 for any other source, with an info line and nothing recorded."""
    text = _read(AUTO_BRIEF)
    [check] = [part for part in text.split("\n\n") if part.startswith("**Local-source check:**")]
    assert text.index("**Docs-only check:**") < text.index(check) < text.index("### 2. ")
    assert "record" not in check and "warn" not in check
    for needle in ("If `source_repo` is not a GitHub repository URL of the form skf-detect-docs.py reads "
                   "(`https://github.com/<owner>/<repo>`, `http://` or a `www.` host too, optionally ending in `.git` or `/`)",
                   "skip §2 and §3", 'Log: "Local or non-GitHub source: skipping repo-based doc detection."',
                   "Proceed directly to §4 (Write Enriched Brief), which leaves `--doc-urls-file` out."):
        assert needle in check, needle
    assert "Leave `--doc-urls-file` out when §2 and §3 were skipped" in _section(text, "### 4. Write Enriched Brief")
    # The form the check names is the one the detector accepts.
    spec = importlib.util.spec_from_file_location("skf_detect_docs_1139", DETECT_DOCS)
    detector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detector)
    for url in ("https://github.com/acme/lib", "https://github.com/acme/lib.git", "https://github.com/acme/lib/",
                "http://github.com/acme/lib", "https://www.github.com/acme/lib"):
        assert detector._GITHUB_URL_RE.match(url), url
    for source in ("/home/u/proj", "./proj", "C:\\work\\proj", "https://gitlab.com/acme/lib", "acme/lib"):
        assert not detector._GITHUB_URL_RE.match(source), source


def test_the_portfolio_and_embed_checks_are_helper_calls():
    """determinism-8: no qmd command is run, capped or merged by hand; the [auto] route resolves the helper from the
    registration file it loads, and the embed check branches on `documents`."""
    for path in (PORTFOLIO_CHECK, QMD_REGISTRATION):
        text = _read(path)
        for gone in ("awk", "qmd query", "qmd collection list", "qmd status", "\u2014"):
            assert gone not in text, (path.name, gone)
        assert not re.search(r"(?<![-\w])timeout 20", text), path.name  # the shell's `timeout`, not the flag
    assert _frontmatter(GATHER_INTENT)["qmdPortfolioSimilarityProbeOrder"] == PORTFOLIO_PROBE
    assert _frontmatter(QMD_REGISTRATION)["qmdPortfolioSimilarityProbeOrder"] == PORTFOLIO_PROBE
    assert "qmdPortfolioSimilarityProbeOrder" not in _read(WRITE_BRIEF)
    portfolio = _read(PORTFOLIO_CHECK)
    command, body = _heredoc(portfolio, "SKF_QUERY")
    assert command == ('uv run {qmdPortfolioSimilarityHelper} similar --name "{name}" --text-file - --cap 12 '
                       "--concurrency 4 --timeout 20 --min-score 0.6 --top 3 <<'SKF_QUERY'")
    assert body == "<the §4 intent>"
    procedure = _section(portfolio, "## Procedure")
    assert "**Heads up: these existing briefs look semantically close to `{name}`:**\n" in procedure
    assert "- {hit-name} (similarity: {score}): {description}\n" in procedure
    assert "`{hit-name}` is its `name`" in procedure  # not the proposed `{name}` of the heading
    assert "whether to rename stays the user's call at §8" in procedure
    failure = _section(portfolio, "## Failure modes")
    [warn] = [line for line in failure.splitlines() if '"warn: portfolio-similarity check skipped: {reason}"' in line]
    assert RECORD_FILE in warn and "when `skipped` is not empty" in warn and "The hits still show." in warn
    assert "No `-brief` collection is no failure" in warn and "nothing is recorded" in warn
    verify = _section(_read(QMD_REGISTRATION), "## Embed Verification")
    [call] = [line for line in verify.splitlines() if line.startswith("uv run {qmdPortfolioSimilarityHelper}")]
    assert call == 'uv run {qmdPortfolioSimilarityHelper} verify-collection "{skill-name}-brief"'
    [above] = [line for line in verify.splitlines() if line.startswith("- `documents` above 0:")]
    assert "proceed to registry update with no `status` field" in above
    [pending] = [line for line in verify.splitlines() if line.startswith("- `documents` 0 or null")]
    for needle in ("a non-zero exit, no JSON, or no helper path", 'include `status: "pending"` in the entry', RECORD):
        assert needle in pending, needle
    assert "HALT" not in verify
