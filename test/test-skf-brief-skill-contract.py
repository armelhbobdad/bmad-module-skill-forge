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

No test runs the step prose, so these checks pin it, and they run the
commands it documents against the emitter and validate what it prints
against the schema.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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
GATHER_INTENT = REFERENCES / "gather-intent.md"
HEADLESS_ARGS = REFERENCES / "headless-args.md"
RATIFY = REFERENCES / "gather-intent-ratify.md"
SCOPE_DEFINITION = REFERENCES / "scope-definition.md"
HEALTH_CHECK = REFERENCES / "health-check.md"
QMD_REGISTRATION = REFERENCES / "qmd-collection-registration.md"
PORTFOLIO_CHECK = REFERENCES / "portfolio-similarity-check.md"
CUSTOMIZE = SKILL_DIR / "customize.toml"
EMITTER = REPO / "src" / "shared" / "scripts" / "skf-emit-brief-result-envelope.py"
VALIDATE_BRIEF = REPO / "src" / "shared" / "scripts" / "skf-validate-brief-schema.py"
FORGE_TIER_RW = REPO / "src" / "shared" / "scripts" / "skf-forge-tier-rw.py"
SCHEMA_PATH = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-brief-result-envelope.v1.json"
PREFIX = "SKF_BRIEF_RESULT_JSON: "
BASH = shutil.which("bash")
# The documented block is POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"

HEREDOC_RE = re.compile(r"<<'(?P<tag>[A-Z_]+)'\n(?P<body>.*?)\n(?P=tag)\n", re.DOTALL)
# The halt command each halt site names, with its halt_reason beside it.
HALT_CALL = "`uv run {emitBriefEnvelopeHelper} emit --target stderr`"
# The step files whose halts call the emitter where they stop.
HALT_SITE_FILES = (GATHER_INTENT, HEADLESS_ARGS, RATIFY, ANALYZE_TARGET, SCOPE_DEFINITION, AUTO_BRIEF, AUTO_VALIDATE,
                   WRITE_BRIEF)
# The [auto] success path: the envelope, the hook, the run folder's removal, the chain.
AUTO_SUCCESS = "### 3. Envelope, Hook and Chain"
HALT_LINE_RE = re.compile(r'halt_reason: "(?P<reason>[a-z-]+)".*\bHALT\b.*?exit code (?P<code>\d+)')
HOOK_CALL = "{onCompleteCommand} --result-path={brief_path}"
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


def _fill(body: str, *, halt_reason: str | None = None, mode: str | None = None, warnings=()) -> str:
    """The documented payload with its placeholders filled in, still as text."""
    body = body.replace('<"auto" or null>', json.dumps(mode))
    body = body.replace("[<workflow_warnings[] as JSON strings>]", json.dumps(list(warnings)))
    body = body.replace('"<halt_reason>"', json.dumps(halt_reason))
    body = body.replace('"<scope.type>"', '"public-api"').replace('"{scope_type}"', '"public-api"')
    body = re.sub(r'"<[^"<>]*>"', '"demo"', body)  # "<skill name>", "<brief_path from §3>" ...
    return re.sub(r'"\{[a-z_]+\}"', '"demo"', body)  # "{skill_name}", "{brief_path}" ...


def _emit(payload: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EMITTER), "emit", *args], input=payload, capture_output=True,
                          text=True, encoding="utf-8", timeout=30, check=False)


def _envelope(line: str) -> dict:
    assert line.startswith(PREFIX), line
    envelope = json.loads(line[len(PREFIX):])
    errors = [error.message for error in VALIDATOR.iter_errors(envelope)]
    assert not errors, errors
    return envelope


def _as_line(warning: dict) -> str:
    """A {field, message} helper warning as the documented workflow_warnings[] line."""
    return OBJECT_WARNING.replace("<field>", warning["field"]).replace("<message>", warning["message"])


@pytest.fixture(scope="module")
def validator_warning(tmp_path_factory) -> dict:
    """The warning skf-validate-brief-schema.py returns for a docs-only brief with source_authority official."""
    brief = {
        "name": "demo", "version": "1.0.0", "source_type": "docs-only", "source_authority": "official",
        "source_repo": "https://example.com/docs", "doc_urls": [{"url": "https://example.com/docs"}],
        "language": "python", "description": "Demo docs.", "forge_tier": "Forge", "created": "2026-05-15",
        "created_by": "demo", "scope": {"type": "docs-only", "include": [], "exclude": [], "notes": ""},
    }
    path = tmp_path_factory.mktemp("brief") / "skill-brief.yaml"
    path.write_bytes(json.dumps(brief).encode("utf-8"))  # JSON is YAML
    proc = subprocess.run([sys.executable, str(VALIDATE_BRIEF), str(path)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["valid"] is True
    [warning] = result["warnings"]
    assert sorted(warning) == ["field", "message"]
    return warning


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
# SKILL.md resolves the emitter at activation and states the halt command
# --------------------------------------------------------------------------


def _activation_steps() -> dict[int, str]:
    activation = _section(_read(SKILL_MD), "## On Activation")
    parts = re.split(r"^(\d+)\. ", activation, flags=re.M)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


def test_activation_resolves_the_emitter_before_the_first_stage_loads():
    steps = _activation_steps()
    [resolve] = [n for n, body in steps.items() if "`{emitBriefEnvelopeHelper}` ←" in body]
    [first_stage] = [n for n, body in steps.items() if "`references/gather-intent.md`" in body]
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
        assert "emitBriefEnvelopeProbeOrder" not in text, path.name
        assert "Error Envelope (Canonical)" not in text, path.name
        assert "**Resolve `{emitBriefEnvelopeHelper}`**" not in text, path.name


def test_halt_contract_is_one_unindented_block():
    """A heredoc ends only at a delimiter line with no indent, so the block sits outside any list."""
    contract = _section(_read(SKILL_MD), "## Halt Contract")
    command, body = _heredoc(contract, "SKF_BRIEF_HALT")
    assert command == "uv run {emitBriefEnvelopeHelper} emit --target stderr <<'SKF_BRIEF_HALT'"
    assert "\nSKF_BRIEF_HALT\n" in contract
    assert "{headless_mode}" in contract and "{auto_mode}" in contract
    assert "`unknown`" in contract, "the placeholder for a halt before the name is resolved"


@pytest.mark.parametrize("mode", [pytest.param("auto", id="auto"), pytest.param(None, id="not-auto")])
@pytest.mark.parametrize("reason", [pytest.param(r, id=r) for r in SETTINGS["exit_codes"]])
def test_halt_contract_payload_emits_every_halt_reason(reason, mode):
    _, body = _heredoc(_section(_read(SKILL_MD), "## Halt Contract"), "SKF_BRIEF_HALT")
    proc = _emit(_fill(body, halt_reason=reason, mode=mode, warnings=[QUOTED_WARNING]), "--target", "stderr")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    envelope = _envelope(proc.stderr.strip())
    assert envelope["status"] == "error" and envelope["halt_reason"] == reason
    assert envelope["exit_code"] == SETTINGS["exit_codes"][reason]
    assert envelope["mode"] == mode and envelope["skill_name"] == "demo"
    assert envelope["warnings"] == [QUOTED_WARNING]


def test_halt_contract_payload_without_warnings_leaves_the_list_out():
    _, body = _heredoc(_section(_read(SKILL_MD), "## Halt Contract"), "SKF_BRIEF_HALT")
    proc = _emit(_fill(body, halt_reason="forge-tier-missing"), "--target", "stderr")
    assert proc.returncode == 0, proc.stderr
    assert "warnings" not in _envelope(proc.stderr.strip())


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")
def test_documented_halt_block_passes_a_quoted_warning_through_bash(validator_warning):
    """The quoted heredoc hands a warning with a single quote, or with backticks, to the helper unchanged."""
    warnings = [QUOTED_WARNING, _as_line(validator_warning)]
    assert "`" in warnings[1], "an unquoted heredoc would run the backticked words as commands"
    contract = _section(_read(SKILL_MD), "## Halt Contract")
    [block] = [b for b in re.findall(r"```bash\n(.*?)```", contract, re.DOTALL) if "SKF_BRIEF_HALT" in b]
    heredoc = HEREDOC_RE.search(block)
    filled = _fill(heredoc.group("body"), halt_reason="target-inaccessible", warnings=warnings)
    block = block[:heredoc.start("body")] + filled + block[heredoc.end("body"):]
    block = block.replace("uv run {emitBriefEnvelopeHelper}", f'"{sys.executable}" "{EMITTER}"')
    proc = subprocess.run([BASH, "-c", block], capture_output=True, text=True, encoding="utf-8", timeout=30,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr.strip())
    assert envelope["warnings"] == warnings and envelope["exit_code"] == 3


# --------------------------------------------------------------------------
# Each halt site calls the emitter where it stops
# --------------------------------------------------------------------------


def test_every_halt_site_emits_its_envelope_before_it_stops():
    sites = 0
    for path in HALT_SITE_FILES:
        text = _read(path)
        assert "error envelope per" not in text, f"{path.name} points its halt envelope elsewhere"
        assert "SKILL.md Halt Contract" in text, path.name
        for line in text.splitlines():
            match = HALT_LINE_RE.search(line)
            if not match:
                continue
            sites += 1
            where = f"{path.name}: {line[:80]}"
            # The envelope first, then the halt.
            assert re.search(re.escape(HALT_CALL) + r".*\bthen (?:HARD )?HALT\b", line), where
            assert int(match.group("code")) == SETTINGS["exit_codes"][match.group("reason")], where
    # gather-intent 3, gather-intent-ratify 2, analyze-target 5, scope-definition 1, step-auto-brief 4,
    # step-auto-validate 2, write-brief 3 (headless-args.md's one halt names the validator's halt_reason)
    assert sites == 20, sites


def test_write_brief_points_step_one_halts_at_the_halt_contract():
    """write-brief.md section 4b sends a step 1 or 2 halt to the SKILL.md Halt Contract, which owns `unknown`."""
    section = _section(_read(WRITE_BRIEF), "### 4b. Result Envelope (Headless)")
    assert "steps 1 and 2" in section and "SKILL.md Halt Contract" in section and "`unknown`" in section


def test_step_one_halts_emit_in_headless_and_auto_mode_alike():
    """The Halt Contract fires on {headless_mode} or {auto_mode}: no step 1 halt narrows it to headless,
    points at write-brief.md section 4b or restates the `unknown` placeholder rule."""
    step_one = (GATHER_INTENT, HEADLESS_ARGS, RATIFY)
    for path in step_one:
        text = _read(path)
        assert "In headless mode, emit" not in text, path.name
        assert "§4b" not in text and "step 5 section 4b" not in text and "placeholder convention" not in text
    [auto] = [line for line in _read(GATHER_INTENT).splitlines() if "brief_path` is not available" in line]
    assert HALT_CALL in auto and '`halt_reason: "input-missing"`' in auto and '`"auto"`' in auto
    # The validators' {field, message} warnings reach the envelope as one line each: the input
    # validator's in the headless input gate, the schema validator's in the ratify route.
    for path in (HEADLESS_ARGS, RATIFY):
        valid = [line for line in _read(path).splitlines() if line.lstrip().startswith("- **`valid: true`**")]
        assert len(valid) == 1 and "workflow_warnings[]" in valid[0], (path.name, valid)
        assert f"`{OBJECT_WARNING}`" in valid[0], path.name
    assert "- **`valid: true`**" not in _read(GATHER_INTENT)


# --------------------------------------------------------------------------
# The success envelope carries the run's warnings
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,heading,mode",
    [
        pytest.param(WRITE_BRIEF, "### 4b. Result Envelope (Headless)", None, id="write-brief"),
        pytest.param(AUTO_VALIDATE, AUTO_SUCCESS, "auto", id="auto"),
    ],
)
def test_success_envelope_carries_the_run_warnings(path, heading, mode):
    command, body = _heredoc(_section(_read(path), heading), "SKF_BRIEF_RESULT")
    assert command == "uv run {emitBriefEnvelopeHelper} emit <<'SKF_BRIEF_RESULT'"
    proc = _emit(_fill(body, warnings=[QUOTED_WARNING, "Doc detection failed: proceeding without doc enrichment."]))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout.strip())
    assert envelope["status"] == "success" and envelope["exit_code"] == SETTINGS["success_exit_code"]
    assert envelope["mode"] == mode
    assert envelope["warnings"][0] == QUOTED_WARNING and len(envelope["warnings"]) == 2


def test_run_warnings_are_declared_once_and_fed_by_the_helpers():
    rules = _section(_read(SKILL_MD), "## Workflow Rules")
    assert "`workflow_warnings[]`" in rules and "carries the list as `warnings`" in rules
    assert f"goes in as one line, `{OBJECT_WARNING}`" in rules
    for path in (AUTO_BRIEF, AUTO_VALIDATE, WRITE_BRIEF):
        assert "to `workflow_warnings[]`" in _read(path), path.name
    # skf-validate-brief-schema.py returns {field, message} objects: each [auto] step converts them.
    for path in (AUTO_BRIEF, AUTO_VALIDATE):
        [valid] = [line for line in _read(path).splitlines() if line.startswith("- **`valid: true`**")]
        assert f"to `workflow_warnings[]` as `{OBJECT_WARNING}`" in valid, path.name
    assert f"`{OBJECT_WARNING}`" in _section(_read(CONTRACT), "## Result Contract (Headless)")


def test_a_validator_warning_reaches_every_envelope_as_one_line(validator_warning):
    """A real {field, message} warning, converted as documented, passes the halt and both success payloads."""
    line = _as_line(validator_warning)
    _, halt = _heredoc(_section(_read(SKILL_MD), "## Halt Contract"), "SKF_BRIEF_HALT")
    # As the helper returns it, the object costs the run its envelope line.
    raw = _emit(_fill(halt, halt_reason="input-invalid", mode="auto", warnings=[validator_warning]),
                "--target", "stderr")
    assert raw.returncode != 0 and PREFIX not in raw.stdout + raw.stderr
    proc = _emit(_fill(halt, halt_reason="input-invalid", mode="auto", warnings=[line]), "--target", "stderr")
    assert proc.returncode == 0, proc.stderr
    assert _envelope(proc.stderr.strip())["warnings"] == [line]
    for path, heading in ((WRITE_BRIEF, "### 4b. Result Envelope (Headless)"), (AUTO_VALIDATE, AUTO_SUCCESS)):
        _, body = _heredoc(_section(_read(path), heading), "SKF_BRIEF_RESULT")
        proc = _emit(_fill(body, warnings=[line]))
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
    assert "registered by step 5 §3b " in _read(PORTFOLIO_CHECK)
    assert "Used by skf-brief-skill step 5 §3b" in FORGE_TIER_RW.read_text(encoding="utf-8")
    stale = [path.name for path in sorted(SKILL_DIR.rglob("*.md")) if "step 5 §5" in _read(path)]
    assert not stale, stale


def test_qmd_registration_never_halts_after_the_write():
    """A missing skf-forge-tier-rw.py costs the registry update, not the envelope of a brief already written."""
    section = _section(_read(WRITE_BRIEF), "### 3b. QMD Collection Registration (Deep Tier Only)")
    assert "HALT if no candidate exists" not in section
    assert "add `QMD registry not updated: skf-forge-tier-rw.py not found` to `workflow_warnings[]`" in section
    assert "skip the Registry Update" in _section(_read(QMD_REGISTRATION), "## Error Handling")


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
    """Handoff from W2-brief-scope-signals: an [R] pass runs step 2 on a ratify run."""
    text = _read(WRITE_BRIEF)
    [line] = [line for line in text.splitlines() if line.startswith("**Ratify mode (`ratify_mode: true`):**")]
    assert ("step 2 never re-derives the version on a ratify run (an [R] pass analyzes the brief's ref "
            "but keeps the hydrated version)") in line
    assert "this path never ran step 2" not in line and "`version_resolved`" in line
