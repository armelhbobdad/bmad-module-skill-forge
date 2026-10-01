"""Prose-contract tests: /skf-setup --quiet and --headless display only the envelope.

No test executes the step files, so these check the wording the agent follows:
every display instruction in a setup step carries the `{quiet_mode}` guard,
every step forbids the agent's own notes between tool calls, every halt shows
only the blocked envelope, the success envelope is held until it can be a
standalone run's final message (`claude -p` prints only that message) while a
forger pipeline gets control back after it, the orphan gate resolves under
quiet to a listed default, and the shared health check has a silent path plus
a listed headless default for its review gate. The docs promise no more than
that final message. The activation halts name a runner chain the stdlib-only
envelope helper runs under, and every status list agrees with the schema.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
SETUP_DIR = SRC / "skf-setup"
REFS = SETUP_DIR / "references"
SKILL_MD = SETUP_DIR / "SKILL.md"
# The headless contract lifted out of SKILL.md (#600).
INVOCATION_CONTRACT = REFS / "invocation-contract.md"
SHARED_HEALTH_CHECK = SRC / "shared" / "health-check.md"
EMIT_HELPER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
PREFLIGHT = SRC / "shared" / "scripts" / "skf-preflight.py"
CUSTOMIZE = SETUP_DIR / "customize.toml"
SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-setup-result-envelope.v1.json"
TROUBLESHOOTING = REPO_ROOT / "docs" / "troubleshooting.md"
WORKFLOWS_DOC = REPO_ROOT / "docs" / "workflows.md"
CAMPAIGN_RELAY = SRC / "skf-campaign" / "references" / "health-check.md"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"
HEADLESS_CONVENTION = SRC / "shared" / "references" / "headless-gate-convention.md"

# Step file -> the step label its phases use (`step <label>:...`).
STEP_LABELS = {
    "detect-and-tier.md": "1",
    "ccc-index.md": "1b",
    "write-config.md": "2",
    "auto-index.md": "3",
    "report.md": "4",
}
STEP_FILES = list(STEP_LABELS)
QUIET = "{quiet_mode}"
DISPLAY_RULE = "Display messages only when `{quiet_mode}` is false"
NO_NARRATION_RULE = (
    "When `{quiet_mode}` is true, write no assistant text at all between "
    "tool calls: no status, progress or step-transition notes, however brief"
)
PIPELINE = "{pipeline_mode}"
# A display verb, up to three words (never "nothing"), then a colon, a quote or
# "this": `display:`, `display one line:`, `Display to the user:`, `log "…"`.
DISPLAY_RE = re.compile(
    r'(?i)\b(?:display|log|report|announce|print|show|say)\b(?!\s+nothing\b)'
    r'(?:\s+(?!nothing\b)[\w-]+){0,3}?\s*(?::|"|`"|\bthis\b)'
)
LIST_ITEM_RE = re.compile(r"^(?:[-*]|\d+\.)\s")
EMIT_PROBE_PATHS = (
    "'{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'",
    "'{project-root}/src/shared/scripts/skf-emit-result-envelope.py'",
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "step file has no frontmatter"
    return m.group(1), text[m.end():]


def _prose_blocks(text: str, items: bool = False):
    """Yield (first lineno, governing heading, unit) for each blank-line-separated
    block outside code fences, or with `items` for each paragraph or top-level
    list item. A guard stated anywhere in the unit, or in the heading that
    governs it, covers the unit; with `items`, a guard on one list item never
    covers its sibling."""
    heading, in_fence, block, start = "", False, [], 0
    for lineno, line in enumerate(text.splitlines() + [""], 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        starts_item = items and bool(LIST_ITEM_RE.match(line))
        if line.strip() and not line.startswith("#") and not (starts_item and block):
            if not block:
                start = lineno
            block.append(line)
            continue
        if block:
            yield start, heading, "\n".join(block)
            block = []
        if starts_item:
            start, block = lineno, [line]
        elif line.startswith("#"):
            heading = line


def _section(text: str, prefix: str) -> str:
    m = re.search(rf"^{re.escape(prefix)}.*?(?=^#{{2,3}} |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, f"section {prefix!r} not found"
    assert m.group(0).strip(), f"section {prefix!r} is empty"
    return m.group(0)


def _on_activation(text: str) -> str:
    return _section(text, "## On Activation")


# ---------------------------------------------------------------- setup step files


# Step files that display nothing outside their halts: write-config.md's one
# display was its "Proceeding to ..." banner, gone with the other banners.
NO_DISPLAY_STEPS = {"write-config.md"}


@pytest.mark.parametrize("name", STEP_FILES)
def test_step_display_instructions_carry_quiet_guard(name):
    _, body = _split_frontmatter(_read(REFS / name))
    displays = [
        (n, heading, block) for n, heading, block in _prose_blocks(body, items=True) if DISPLAY_RE.search(block)
    ]
    assert bool(displays) != (name in NO_DISPLAY_STEPS), (
        f"{name}: the display instructions no longer fit the pattern or NO_DISPLAY_STEPS")
    unguarded = [
        f"{name}:{n}: {block.strip()[:100]}"
        for n, heading, block in displays
        if QUIET not in block and QUIET not in heading
    ]
    assert unguarded == []


@pytest.mark.parametrize("name", sorted(p.name for p in REFS.glob("*.md")))
def test_step_headless_conditions_also_name_quiet(name):
    headless_only = [
        f"{name}:{n}: {block.strip()[:100]}"
        for n, heading, block in _prose_blocks(_read(REFS / name))
        if "{headless_mode}" in block and QUIET not in block and QUIET not in heading
    ]
    assert headless_only == []


@pytest.mark.parametrize("name", STEP_FILES)
def test_every_setup_step_declares_envelope_probe_order_and_helper_missing_halt(name):
    frontmatter, body = _split_frontmatter(_read(REFS / name))
    m = re.search(r"^emitEnvelopeProbeOrder:\n((?:  - .*\n?)+)", frontmatter + "\n", re.MULTILINE)
    assert m, f"{name}: frontmatter lacks emitEnvelopeProbeOrder"
    entries = [line.strip()[2:] for line in m.group(1).splitlines()]
    assert entries == list(EMIT_PROBE_PATHS)
    assert "{emitEnvelopeHelper}" in body
    rules = _section(body, "## Rules")
    assert DISPLAY_RULE in rules
    assert f"`step {STEP_LABELS[name]}:helper-missing`" in rules


def test_skill_md_routes_unresolved_helpers_through_halt_contract():
    conventions = _section(_read(SKILL_MD), "## Conventions")
    probe_line = next(line for line in conventions.splitlines() if "ProbeOrder" in line)
    assert "halt contract" in probe_line
    assert "helper-missing" in probe_line


def test_skill_md_folds_headless_into_quiet():
    text = _read(SKILL_MD)
    reconcile = next(line for line in text.splitlines() if "**Reconcile `{headless_mode}`**" in line)
    assert "set `{quiet_mode}` to true" in reconcile


def test_activation_checks_uv_before_a_helper_parses_the_config():
    """config.yaml and preferences.yaml are parsed by skf-preflight.py (#592),
    which needs uv: the config check runs no script, so it still comes first,
    and headless_mode from preferences.yaml is folded in only once it is read."""
    items = re.findall(r"^(\d+)\. \*\*(.+?)\*\*", _on_activation(_read(SKILL_MD)), re.MULTILINE)
    order = [title for _, title in items]
    expected = ["Parse invocation flags first", "Check for the config.", "Probe `uv` runtime.",
                "Load config and preferences.", "Reconcile `{headless_mode}`", "Resolve workflow customization."]
    assert [t for t in order if t in expected] == expected
    assert [int(n) for n, _ in items] == list(range(1, len(items) + 1))
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert "`headless_mode` from `preferences.yaml` only after item 5" in halt_contract


def test_halts_display_only_the_blocked_envelope():
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert "nothing else" in halt_contract
    assert "verbatim" in halt_contract
    assert "Interactive runs display the reason as their diagnostic and emit no envelope" in halt_contract
    assert "nothing else" in _section(_read(REFS / "write-config.md"), "### 1.")


def test_halt_contract_falls_back_to_the_reason_when_the_helper_fails():
    """A payload emit-blocked rejects must not leave a quiet run with no line at all."""
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert ("If neither path exists, or no runner exits 0 and prints that line, "
            "display the reason alone as that one line.") in halt_contract
    fallback = _section(_read(REFS / "write-config.md"), "### 1.")
    assert "If the helper exits non-zero or prints no line, display the reason alone." in fallback


def test_halt_contract_names_a_runner_chain_for_the_activation_halts():
    """The activation halts can fire before uv is proven present, and Windows
    often has `python` or `py` but only a store alias for `python3`; by the
    time a step file runs, activation has proven uv present."""
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert "`<runner>` is `uv run` in the step files" in halt_contract
    assert "try the runners `uv run`, `python3`, `python` and `py -3` in that order" in halt_contract
    prefix = re.search(r'^ENVELOPE_PREFIX = "(.+)"$', _read(EMIT_HELPER), re.M).group(1)
    assert f"stop at the first that exits 0 and prints a line starting `{prefix.strip()}`" in halt_contract
    assert "`python3` for the halts in this list" not in halt_contract


ACTIVATION_RUNNERS = re.compile(r"try the runners ((?:`[^`]+`(?:, | and ))+`[^`]+`) in that order")
UV_MISSING = {"phase": "on-activation:uv-missing",
              "reason": "Setup cannot proceed: uv is not installed."}
# Every module the envelope helper may import. Each is in the standard library
# of Python 3.9, the oldest `python3` a runner may be (macOS Command Line
# Tools); add one only after checking that it is.
PY39_STDLIB_IMPORTS = frozenset({"__future__", "argparse", "json", "os", "pathlib", "sys", "time"})


def _emit_blocked(payload: dict, *flags: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *flags, str(EMIT_HELPER), "emit-blocked"],
                          input=json.dumps(payload).encode("utf-8"), capture_output=True,
                          timeout=10, env=env)


def test_activation_halt_runners_can_run_the_envelope_helper():
    """Every runner the halt contract names for the activation halts is a bare
    interpreter except `uv run`, so the helper must stay stdlib-only."""
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    chain = ACTIVATION_RUNNERS.search(halt_contract)
    assert chain, "no runner chain for the activation halts"
    assert re.findall(r"`([^`]+)`", chain.group(1)) == ["uv run", "python3", "python", "py -3"]
    assert "stdlib-only" in halt_contract
    src = _read(EMIT_HELPER)
    header = re.search(r"^# /// script$(.*?)^# ///$", src, re.M | re.S)
    assert header and re.search(r"^# dependencies = \[\]$", header.group(1), re.M)
    # Syntax only: a system python3 older than the requires-python uv enforces
    # may be the first runner that works (macOS Command Line Tools ship 3.9).
    tree = ast.parse(src, feature_version=(3, 9))
    roots = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    roots |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    # The test interpreter's own stdlib would let a newer module (tomllib) through.
    assert roots <= PY39_STDLIB_IMPORTS, roots - PY39_STDLIB_IMPORTS
    sentinel = "<unknown \u2014 halt before config_path resolved>"
    # No uv, no environment variables, no site-packages.
    bare = _emit_blocked(UV_MISSING, "-I", "-S")
    assert bare.returncode == 0, bare.stderr.decode("utf-8", "replace")
    [line] = bare.stdout.decode("utf-8").splitlines()
    assert line.startswith("SKF_SETUP_RESULT_JSON: ")
    envelope = json.loads(line[len("SKF_SETUP_RESULT_JSON: "):])["skf_setup"]
    assert envelope["status"] == "blocked"
    assert envelope["error"] == {**UV_MISSING, "path": "<n/a>"}
    assert envelope["config_path"] == sentinel
    # A cp1252 console (Windows `python` or `py -3`) still carries the dash.
    cp1252 = _emit_blocked(UV_MISSING, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert cp1252.returncode == 0
    assert sentinel in cp1252.stdout.decode("utf-8")
    # A payload the helper rejects prints no line, so the contract falls back to the reason.
    rejected = _emit_blocked({"phase": "on-activation:uv-missing"})
    assert rejected.returncode == 1 and rejected.stdout == b""


@pytest.mark.parametrize("name", [n for n in STEP_FILES if n != "report.md"])
def test_step_halts_run_emit_blocked_under_uv_with_a_fallback(name):
    text = _read(REFS / name)
    rule = next(line for line in _section(text, "## Rules").splitlines() if "emit-blocked" in line)
    assert "`uv run {emitEnvelopeHelper} emit-blocked`" in rule
    assert "or the helper exits non-zero or prints no line" in rule
    assert "python3 {emitEnvelopeHelper}" not in text


def test_blocked_reason_rules_stated():
    """Reasons travel inside a single-quoted shell payload and match the
    troubleshooting headings users search for."""
    text = _read(SKILL_MD)
    halt_contract = next(line for line in text.splitlines() if "Halt contract" in line)
    assert HALT_RULE in halt_contract
    headings = re.findall(r'^### "(Setup cannot proceed: .+)"$', _read(TROUBLESHOOTING), re.MULTILINE)
    assert len(headings) >= 2
    activation = _on_activation(text)
    for heading in headings:
        rendered = heading.replace("`", "")
        assert f"reason `{rendered}" in activation, rendered
    reasons = re.findall(r"reason `([^`]+)`", activation)
    assert len(reasons) >= 3
    assert all("'" not in r and "\\" not in r for r in reasons), reasons
    # A malformed config halts with the parser's own message, as Ferris shows it.
    load = next(line for line in activation.splitlines() if "Any other `hard-halt`" in line)
    assert "phase `on-activation:config-malformed`" in load
    assert "reason `Setup cannot proceed: <message>`" in load
    assert "its `error` without the leading `Cannot initialize. `" in load
    assert "sanitized per the halt contract" in load


def test_config_missing_reason_names_the_installer():
    """Setup never writes config.yaml, only the installer does, so the halt
    names it (#608). The reason keeps the troubleshooting heading as its
    prefix, and it travels in a single-quoted JSON payload from a code span,
    so it holds no quote, backslash or backtick and the helper carries it
    through unchanged."""
    m = re.search(r"phase `on-activation:config-missing`[^\n]*?reason `([^`]+)`", _on_activation(_read(SKILL_MD)))
    assert m, "config-missing halt not found"
    reason = m.group(1)
    assert reason.startswith("Setup cannot proceed: _bmad/skf/config.yaml was not found. ")
    for command in ("npx bmad-module-skill-forge install", "npx bmad-method install"):
        assert command in reason, command
    assert not set(reason) & set("'\"\\`"), reason
    done = _emit_blocked({"phase": "on-activation:config-missing", "reason": reason,
                          "path": "/project/_bmad/skf/config.yaml"})
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    assert json.loads(line[len("SKF_SETUP_RESULT_JSON: "):])["skf_setup"]["error"]["reason"] == reason


HALT_RULE = "no `'`, `\"` or `\\` in it (a backtick for either quote, `/` for a backslash)"
# The halt contract's rule, as HALT_RULE states it.
SANITIZE = str.maketrans({"'": "`", '"': "`", "\\": "/"})
ENVELOPE_PREFIX = "SKF_SETUP_RESULT_JSON: "


def _typed_blocked(phase: str, reason: str, path: str) -> subprocess.CompletedProcess:
    """emit-blocked on the payload as the halt contract has the model type it:
    each value sanitized and put between double quotes, with no JSON escape."""
    text = '{"phase":"%s","reason":"%s","path":"%s"}' % (
        phase, reason.translate(SANITIZE), path.translate(SANITIZE))
    assert "'" not in text  # it travels inside a single-quoted shell payload
    return subprocess.run([sys.executable, str(EMIT_HELPER), "emit-blocked"], input=text.encode("utf-8"),
                          capture_output=True, timeout=10)


def _blocked_error(done: subprocess.CompletedProcess) -> dict:
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    assert line.startswith(ENVELOPE_PREFIX)
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["status"] == "blocked"
    return envelope["error"]


def test_a_malformed_config_halt_still_emits_its_blocked_envelope(tmp_path):
    """skf-preflight.py's YAML parse error names the file between double
    quotes. Sanitized per the halt contract, the hand-typed payload is still
    JSON, so a quiet run gets a blocked envelope, not the bare reason."""
    assert HALT_RULE in next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    config = tmp_path / "_bmad" / "skf" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"project_name: demo\nbad: key: here\n")
    proc = subprocess.run([sys.executable, str(PREFLIGHT), str(tmp_path), "--allow-missing-sidecar"],
                          capture_output=True, timeout=60)
    assert proc.returncode == 1, proc.stderr.decode("utf-8", "replace")
    result = json.loads(proc.stdout)
    assert result["code"] == "CONFIG_MALFORMED"
    assert '"' in result["error"], result["error"]
    reason = "Setup cannot proceed: " + result["error"].removeprefix("Cannot initialize. ")
    error = _blocked_error(_typed_blocked("on-activation:config-malformed", reason, config.as_posix()))
    assert error == {"phase": "on-activation:config-malformed", "reason": reason.translate(SANITIZE),
                     "path": config.as_posix()}


@pytest.mark.parametrize("reason", [
    'Setup cannot proceed: tool detection failed: C:\\Users\\bob\\x is not "readable"',
    "Setup cannot proceed: the run folder could not be created: it's \"read-only\"",
], ids=["windows-path-and-quotes", "both-quotes"])
def test_the_halt_contract_rule_keeps_a_typed_payload_json(reason):
    error = _blocked_error(_typed_blocked("step 1:detect-tools", reason, "C:\\p"))
    assert error["reason"] == reason.translate(SANITIZE) and error["path"] == "C:/p"
    assert not set(error["reason"]) & set("'\"\\")


def test_step_files_sanitize_reasons_per_the_halt_contract():
    """The rule is stated once, in the SKILL.md halt contract: a step that
    restated part of it (only `'` and the backslash) let a double quote
    through into the hand-typed JSON."""
    for name in ("detect-and-tier.md", "write-config.md"):
        text = _read(REFS / name)
        assert "sanitized per the SKILL.md halt contract" in text, name
        assert "replaced by a backtick" not in text, name
    assert "as a backtick and each" not in _on_activation(_read(SKILL_MD))


def test_detector_failure_branch_is_defined():
    section = _section(_read(REFS / "detect-and-tier.md"), "### 1.")
    branch = next(b for _, _, b in _prose_blocks(section) if "exits non-zero" in b)
    assert "`step 1:detect-tools`" in branch
    assert "halt" in branch
    assert QUIET in branch


def test_clean_stale_failure_binds_flags():
    """Step 4 reads both cleanups from the empty staged output, so the step
    binds nothing for them."""
    section = _section(_read(REFS / "auto-index.md"), "### 4.")
    branch = next(b for _, _, b in _prose_blocks(section) if "exits non-zero" in b)
    assert re.findall(r"set `\{([^`]*)\}`", branch) == []
    assert "ccc_registry_stale" not in section
    assert "WARNING line" not in section
    assert "logged in the script" not in section
    assert "carry every pruned path" not in section


def test_auto_index_missing_helper_is_not_a_hygiene_error():
    rules = _section(_read(REFS / "auto-index.md"), "## Rules")
    halt = next(line for line in rules.splitlines() if "`step 3:helper-missing`" in line)
    assert "not a hygiene error" in halt
    tolerance = next(line for line in rules.splitlines() if "hygiene encounters errors" in line)
    assert "a missing helper is not a hygiene error" in tolerance


def test_report_holds_the_envelope_for_the_final_message():
    """`claude -p` prints only the final message, and the health check runs tool
    calls after step 4, so §4 binds the line and a later display shows it."""
    report = _read(REFS / "report.md")
    emit = _section(report, "### 4.")
    assert "Bind `{setup_envelope_line}` ← that stdout line, and do not display it here" in emit
    assert "run's final message" in emit and "verbatim" in emit
    assert "Display that stdout line" not in emit
    chain = _section(report, "### 5.")
    tier_miss = next(u for _, _, u in _prose_blocks(chain, items=True) if "`{require_tier_satisfied}` is `false`" in u)
    assert "display `{setup_envelope_line}` verbatim as the run's final message" in tier_miss
    assert QUIET in tier_miss
    relay_rules = _section(_read(REFS / "health-check.md"), "## Rules")
    assert "`{setup_envelope_line}` verbatim last, as the final message of a standalone run" in relay_rules


def test_tier_miss_halt_emits_no_blocked_envelope():
    """The tier_failure envelope is that halt's one line; a second, blocked
    envelope would give a pipeline two conflicting statuses."""
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert "Every halt in this workflow that names a phase" in halt_contract
    assert "tier-miss halt names none" in halt_contract
    chain = _section(_read(REFS / "report.md"), "### 5.")
    tier_miss = next(u for _, _, u in _prose_blocks(chain, items=True) if "`{require_tier_satisfied}` is `false`" in u)
    assert "This halt emits no blocked envelope" in tier_miss


def test_on_complete_is_silent_under_quiet():
    chain = _section(_read(REFS / "report.md"), "### 5.")
    item = next(u for _, _, u in _prose_blocks(chain, items=True)
                if "{onCompleteCommand}" in u and "carry out that instruction now" in u)
    assert "when `{quiet_mode}` is true, display nothing about it" in item
    # Setup builds the index itself, so on_complete never offers that (#596).
    assert "trigger the first index build" not in item


def test_report_envelope_failure_makes_no_stderr_claim():
    section = _section(_read(REFS / "report.md"), "### 4.")
    branch = next(b for _, _, b in _prose_blocks(section) if "exits non-zero" in b)
    assert "stderr" not in branch
    assert "Display nothing" in branch


def test_orphan_gate_resolves_under_quiet_with_listed_default():
    text = _read(REFS / "auto-index.md")
    assert 'source: "quiet-default"' in text
    assert "**GATE [default: K]**" in text
    assert "**[K]eep**" in text


def test_orphan_resolution_sources_named_in_envelope_helper_and_schema():
    sources = set(re.findall(r'source: "([a-z-]+)"', _read(REFS / "auto-index.md")))
    assert {"orphan-action-flag", "headless-default", "quiet-default"} <= sources
    doc = ast.get_docstring(ast.parse(_read(EMIT_HELPER)))
    assert all(s in doc for s in sources), sources
    assert "{headless_mode} or {quiet_mode}" in _read(SCHEMA)


def test_quiet_scope_restated_in_relay_step():
    rules = _section(_read(REFS / "health-check.md"), "## Rules")
    line = next(line for line in rules.splitlines() if QUIET in line)
    assert "only workflow that sets it" in line


# ---------------------------------------------------------------- shared health check


@pytest.mark.parametrize("prefix", ["### 0.", "### 2.", "### 3.", "### 5c."])
def test_shared_health_check_has_quiet_path(prefix):
    assert QUIET in _section(_read(SHARED_HEALTH_CHECK), prefix)


def test_shared_health_check_arrival_gate_is_silent_under_quiet():
    """The headless log line must not print ahead of (or after) the setup envelope."""
    section = _section(_read(SHARED_HEALTH_CHECK), "### 0.")
    gate = next(b for _, _, b in _prose_blocks(section) if b.startswith("**GATE"))
    assert "If `{quiet_mode}` is true: skip the display and log nothing." in gate
    assert gate.index(QUIET) < gate.index("{headless_mode}")


def test_shared_health_check_ends_quiet_runs_with_the_setup_envelope():
    text = _read(SHARED_HEALTH_CHECK)
    scope = next(b for _, _, b in _prose_blocks(_section(text, "### 0.")) if "Envelope-only runs" in b)
    assert "`{setup_envelope_line}` verbatim after every tool call" in scope
    assert "In a standalone setup run that line is the final message" in scope
    for prefix in ("### 2.", "### 5c."):
        quiet = [b for _, _, b in _prose_blocks(_section(text, prefix)) if QUIET in b]
        assert quiet and all("display only `{setup_envelope_line}`" in b for b in quiet), prefix


def test_shared_health_check_quiet_scope_is_setup_only():
    section = _section(_read(SHARED_HEALTH_CHECK), "### 0.")
    scope = next(b for _, _, b in _prose_blocks(section) if "Envelope-only runs" in b)
    assert "skf-setup" in scope
    assert "treat it as false" in scope


def test_only_setup_and_the_shared_health_check_read_quiet_mode():
    """The shared health check's quiet branches stay dormant for every other workflow."""
    readers = sorted(
        p.relative_to(SRC).as_posix() for p in SRC.rglob("*.md")
        if QUIET in _read(p) and SETUP_DIR not in p.parents
    )
    assert readers == ["shared/health-check.md"]


def test_shared_health_check_quiet_findings_go_to_local_queue_only():
    quiet_lines = [l for l in _section(_read(SHARED_HEALTH_CHECK), "### 3.").splitlines() if QUIET in l]
    assert quiet_lines and all("§5c" in l for l in quiet_lines)


def test_shared_health_check_gate_has_listed_headless_default_q():
    """Every workflow's headless run resolves the review gate to a listed option
    instead of waiting for input, and that option never submits anything."""
    section = _section(_read(SHARED_HEALTH_CHECK), "### 4.")
    assert "**GATE [default: Q]**" in section
    assert "- **[Q]** Queue locally — save every finding to {localFallbackFolder}/, submit nothing" in section
    assert '"headless: queued {N} finding(s) locally"' in section
    gate = next(b for _, _, b in _prose_blocks(section) if "**GATE [default: Q]**" in b)
    assert "{headless_mode}" in gate and QUIET in gate
    quiet_part, headless_part = gate.split("Otherwise", 1)
    assert QUIET in quiet_part and "choose **[Q]**" in quiet_part
    assert "{headless_mode}" in headless_part and "choose **[Q]**" in headless_part
    assert re.findall(r"\bchoose \*\*\[(\w)\]\*\*", gate) == ["Q", "Q"]
    handling = next(line for line in section.splitlines() if line.startswith("- **IF Q:**"))
    assert "§5a sub-step 1" in handling and "§5c" in handling
    local_queue = _section(_read(SHARED_HEALTH_CHECK), "### 5c.")
    assert "**\\[Q]**" in local_queue


def test_queue_fingerprint_has_a_portable_form():
    """[Q] is the default for every headless run with findings, so its
    fingerprint cannot depend on `sha1sum`, which stock macOS and Windows lack."""
    section = _section(_read(SHARED_HEALTH_CHECK), "### 5a.")
    assert "`shasum -a 1`" in section
    m = re.search(r'^uv run python -c "(.+?)" "\{severity\}\|\{workflow\}\|\{step_file\}\|\{section-slug\}"$',
                  section, re.MULTILINE)
    assert m, "portable fingerprint snippet not found"
    key = "bug|skf-setup|references/report.md|emit-headless-json-envelope"
    out = subprocess.run([sys.executable, "-c", m.group(1), key], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout.strip()
    assert out == hashlib.sha1(key.encode("utf-8")).hexdigest()[:7]


def test_campaign_relay_carries_no_routing_consent():
    """Campaign no longer asks at setup where findings go, so its relay step
    only delegates: the shared review gate decides, and a headless run takes
    its default [Q] and queues every finding locally."""
    text = _read(CAMPAIGN_RELAY)
    assert "health_findings_queue" not in text
    assert "consent" not in text
    assert "Load `{nextStepFile}`, read it fully, then execute it." in text


# ---------------------------------------------------------------- agent notes between tool calls


@pytest.mark.parametrize("name", [*STEP_FILES, "health-check.md"])
def test_every_setup_step_forbids_notes_between_tool_calls(name):
    """Live quiet runs showed the agent narrating step transitions, so each
    step restates the rule where the agent reads it, not only SKILL.md."""
    rules = _section(_read(REFS / name), "## Rules")
    assert NO_NARRATION_RULE in rules


def test_skill_md_forbids_notes_between_tool_calls():
    rules = _section(_read(SKILL_MD), "## Workflow Rules")
    assert NO_NARRATION_RULE in rules
    assert "narration of your own" not in rules


def test_shared_health_check_quiet_path_writes_no_notes():
    section = _section(_read(SHARED_HEALTH_CHECK), "### 0.")
    scope = next(b for _, _, b in _prose_blocks(section) if "Envelope-only runs" in b)
    assert "writes no text between tool calls" in scope


# ---------------------------------------------------------------- setup inside a forger pipeline


def _final_message_units():
    """Every prose unit in setup and the shared health check's §0 that makes
    the envelope the run's final message or says it ends the run."""
    sources = {"SKILL.md": _read(SKILL_MD)}
    sources.update({f"references/{p.name}": _read(p) for p in sorted(REFS.glob("*.md"))})
    sources["shared/health-check.md §0"] = _section(_read(SHARED_HEALTH_CHECK), "### 0.")
    sources["headless-gate-convention.md"] = _read(HEADLESS_CONVENTION)
    for label, text in sources.items():
        for n, _, block in _prose_blocks(text, items=True):
            # A table row is its own unit: the contract rows are scoped one by one.
            rows = block.splitlines() if block.startswith("|") else [block]
            for offset, unit in enumerate(rows):
                if "final message" in unit or "ends the run" in unit:
                    yield label, n + (offset if len(rows) > 1 else 0), unit


def test_pipeline_mode_marks_every_workflow_it_invokes():
    """`{pipeline_alias}` is null for an ad-hoc sequence such as `SF QS TS EX`,
    so it cannot tell a pipeline step from a standalone run."""
    step = next(line for line in _read(PIPELINE_MODE).splitlines() if "**Invoke the workflow**" in line)
    assert "`{pipeline_mode}` = true" in step
    assert "`{pipeline_alias}` is null for an ad-hoc sequence" in step
    assert "control returns here: continue with d" in step


def test_forger_and_pipeline_state_name_pipeline_mode():
    """The forger routes every chain to pipeline-mode.md, whose step 4c sets
    the marker (above), and the Pipeline State contract forwards it too."""
    forger = _section(_read(SRC / "skf-forger" / "SKILL.md"), "## Pipeline Mode")
    assert "`references/pipeline-mode.md`" in forger
    state = _section(_read(SRC / "shared" / "references" / "pipeline-contracts.md"), "## Pipeline State")
    assert "data context carries `pipeline_mode: true`" in state


def test_pipeline_mode_reads_the_setup_envelope_status():
    special = _section(_read(PIPELINE_MODE), "## Special behaviors")
    sf = next(line for line in special.splitlines() if line.startswith("- **`SF` in a sequence:**"))
    assert "`SKF_SETUP_RESULT_JSON`" in sf
    assert "Continue on `status` `success`" in sf
    assert "halts the pipeline" in sf


def test_setup_binds_pipeline_mode_only_from_the_forger():
    parse = next(line for line in _on_activation(_read(SKILL_MD)).splitlines()
                 if "**Parse invocation flags first**" in line)
    assert "`{pipeline_mode}` is not a flag" in parse
    assert "false otherwise, including every direct `/skf-setup` run" in parse


def test_final_message_rule_is_scoped_to_a_standalone_run():
    units = list(_final_message_units())
    assert len(units) >= 5, units
    unscoped = [f"{label}:{n}: {unit.strip()[:100]}" for label, n, unit in units
                if "standalone" not in unit and PIPELINE not in unit]
    assert unscoped == []


def test_pipeline_run_returns_control_to_the_forger():
    rules = _section(_read(SKILL_MD), "## Workflow Rules")
    rule = next(line for line in rules.splitlines() if PIPELINE in line)
    assert "return control to the forger, which keeps chaining" in rule
    section = _section(_read(SHARED_HEALTH_CHECK), "### 0.")
    scope = next(b for _, _, b in _prose_blocks(section) if "Envelope-only runs" in b)
    assert "When `{pipeline_mode}` is true" in scope
    assert "control then returns to the forger, which keeps chaining" in scope
    chain = _section(_read(REFS / "report.md"), "### 5.")
    tier_miss = next(u for _, _, u in _prose_blocks(chain, items=True) if "`{require_tier_satisfied}` is `false`" in u)
    assert "control then returns to the forger" in tier_miss


# ---------------------------------------------------------------- orphan removal consent


def test_orphan_removal_rule_names_both_consents():
    """`--orphan-action=remove` removes without a prompt; the rule must not
    tell the agent to prompt anyway."""
    text = _read(REFS / "auto-index.md")
    assert "always prompt" not in text
    assert "prompt the user before removing" not in text
    rule = next(line for line in _section(text, "## Rules").splitlines() if "`qmd collection remove`" in line)
    assert "interactive **[R]**" in rule
    assert "`--orphan-action=remove`" in rule
    assert "{orphan_auto_resolution}" in rule


def test_unprompted_orphan_removals_are_recorded_by_name():
    """The classifier's remove-orphans stages what it deleted, and the emitter
    folds the names into the audit trail: the step types no list (#592)."""
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    assert ('remove-orphans \\\n    --classification-from "{run_dir}/qmd-classify.json" \\\n'
            '    --project-root "{project-root}" \\\n    > "{run_dir}/qmd-remove.json"') in gate
    assert "Set `{orphan_auto_resolution: {action: <keep|remove>, source: <as above>}}`" in gate
    assert "Auto-decision (--orphan-action=remove): removed {removed, comma-separated}" in gate
    assert "qmd collection remove <name>" not in gate and "len(" not in gate
    doc = ast.get_docstring(ast.parse(_read(EMIT_HELPER)))
    assert '"removed": ["name", ...], "failed": ["name", ...]' in doc
    assert "`orphan_removed: <name>`, `orphan_remove_failed: <name>`" in doc


# ---------------------------------------------------------------- activation inputs fail closed


DETECT_HELPER = SRC / "shared" / "scripts" / "skf-detect-tools.py"


def _parse_flags_item() -> str:
    return next(line for line in _on_activation(_read(SKILL_MD)).splitlines()
                if "**Parse invocation flags first**" in line)


def test_require_tier_is_bound_raw_and_checked_by_the_detector():
    """A wrong-case tier used to become null, so the tier gate never ran."""
    parse = _parse_flags_item()
    assert ("`{require_tier}` and `{orphan_action}` (each flag's raw value exactly as given, "
            "after `=` or a space; an empty string when nothing, or another flag, follows it; null only "
            "when the flag is absent)") in parse
    assert "unparseable" not in parse
    assert "Step 1's detector rejects a `{require_tier}` that names no tier." in parse
    detect = _section(_read(REFS / "detect-and-tier.md"), "### 1.")
    # The = form: a raw value that starts with a dash is still the flag's
    # value, so the detector's own message names the valid tiers.
    assert '[--tier-override="{tier_override}"] [--require-tier="{require_tier}"]' in detect
    assert "with the value exactly as activation bound it, even when it names no tier" in detect


def test_a_wrong_case_require_tier_ends_blocked_naming_the_valid_tiers(tmp_path):
    """`/skf-setup --headless --require-tier=deep`: step 1's detector call
    fails, and its halt emits a blocked envelope whose reason names the tiers."""
    proc = subprocess.run([sys.executable, str(DETECT_HELPER), "--project-root", str(tmp_path),
                           "--require-tier", "deep"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1 and proc.stdout == ""
    message = json.loads(proc.stderr)["message"]
    branch = _section(_read(REFS / "detect-and-tier.md"), "### 1.")
    assert "reason `Setup cannot proceed: tool detection failed: <message>`" in branch
    reason = "Setup cannot proceed: tool detection failed: " + message.replace("'", "`").replace("\\", "/")
    done = _emit_blocked({"phase": "step 1:detect-tools", "reason": reason, "path": tmp_path.as_posix()})
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line[len("SKF_SETUP_RESULT_JSON: "):])["skf_setup"]
    assert envelope["status"] == "blocked" and envelope["error"]["phase"] == "step 1:detect-tools"
    assert "Quick, Forge, Forge+, Deep" in envelope["error"]["reason"]
    assert envelope["error"]["reason"].endswith("did you mean Deep?")


def test_orphan_action_other_than_keep_or_remove_halts_at_activation():
    """The flag is the consent to delete collections: a value setup cannot read halts."""
    parse = _parse_flags_item()
    m = re.search(r"halt with phase `on-activation:orphan-action-invalid`, no `path`, and reason `([^`]+)`", parse)
    assert m, "orphan-action halt not found"
    reason = m.group(1)
    assert reason.startswith("Setup cannot proceed: --orphan-action takes keep or remove, not <value>.")
    assert not set(reason) & set("'\"\\")
    done = _emit_blocked({"phase": "on-activation:orphan-action-invalid",
                          "reason": reason.replace("<value>", "Remove")})
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert "not Remove." in done.stdout.decode("utf-8")
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    assert "`{orphan_action}` is non-null (activation lets through only `keep` or `remove`)" in gate
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    failure = next(line for line in contract.splitlines() if line.startswith("| **Failure modes**"))
    assert "an `--orphan-action` other than `keep` or `remove`" in failure


def test_quiet_is_an_alias_of_headless_and_a_pipeline_implies_it():
    parse = _parse_flags_item()
    assert "`{headless_mode}` (true on `--headless` / `-H`, and when `{pipeline_mode}` is true)" in parse
    assert ("`{quiet_mode}` (true on `--quiet`, the alias of `--headless`, and whenever `{headless_mode}` "
            "is true)") in parse
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    flags = next(line for line in contract.splitlines() if line.startswith("| **Flags**"))
    assert "`--quiet` (an alias of `--headless`" in flags
    # One non-interactive case, and a --quiet run keeps labelling its orphan default quiet-default.
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    assert ('- `{quiet_mode}` is true → the default **Keep**, with `source: "headless-default"` when '
            '`{headless_mode}` is true and `source: "quiet-default"` otherwise (a `--quiet` run)') in gate
    assert "- `{headless_mode}` is true →" not in gate


SETUP_FILES = [SKILL_MD, *sorted(REFS.glob("*.md"))]


@pytest.mark.parametrize("path", SETUP_FILES, ids=lambda p: p.name)
def test_every_setup_guard_reads_quiet_mode_alone(path):
    """--quiet is an alias of --headless, so setup has one envelope-only mode
    and one switch for it: a guard that tests both variables could drift
    into testing one of them and leak text into the envelope-only output."""
    text = _read(path)
    for doubled in ("`{headless_mode}` or `{quiet_mode}`", "`{headless_mode}` and `{quiet_mode}`",
                    "`{quiet_mode}` or `{headless_mode}`"):
        assert doubled not in text, doubled
    # {headless_mode} is only parsed, folded with preferences.yaml, and named
    # as the source of the step 3 orphan default.
    allowed = {"SKILL.md": ("1. **Parse invocation flags first**", "5. **Reconcile `{headless_mode}`**"),
               "auto-index.md": ("- `{quiet_mode}` is true → the default **Keep**",)}.get(path.name, ())
    readers = [line.strip()[:60] for line in text.splitlines() if "{headless_mode}" in line]
    assert [line for line in readers if not line.startswith(allowed)] == []


# ---------------------------------------------------------------- step order, staged payloads, banner


def test_preamble_and_rerun_notice_follow_the_bindings_they_read():
    """The notices read `prior.previous_tier`, which only the detector
    produces and section 2 binds; the tier override comes from activation."""
    text = _read(REFS / "detect-and-tier.md")
    headings = re.findall(r"^### (\d+)\. (.+)$", text, re.MULTILINE)
    assert [int(n) for n, _ in headings] == list(range(1, len(headings) + 1))
    titles = [title.split(" (skip when ", 1)[0] for _, title in headings]
    assert titles[0] == "Run Detection Helper"
    order = [titles.index(t) for t in ("Run Detection Helper", "Parse Output and Set Context Flags",
                                       "Show the First-Run Preamble or the Re-run Notice", "Auto-Proceed")]
    assert order == sorted(order)
    # preferences.yaml is parsed at activation, never read by eye here.
    assert "Read the Tier Override" not in text
    assert "`{tier_override}` (bound at activation from `preferences.yaml`)" in _section(text, "### 1.")
    notice = _section(text, "### 3.")
    assert notice.startswith("### 3. Show the First-Run Preamble or the Re-run Notice "
                             "(skip when `{quiet_mode}` is true)\n")
    assert ("Now that section 2 has bound `{previous_tier}` and `{previous_detection_date}`, and before "
            "step 1b or step 2 writes anything") in notice
    # Each notice states its condition once; the heading carries the quiet guard.
    assert notice.count("**First-run preamble:** when `{previous_tier}` is null:") == 1
    assert notice.count("**Re-run notice:** when `{previous_tier}` is non-null:") == 1
    assert notice.count("`{previous_tier}` is") == 2 and notice.count(QUIET) == 1
    assert "§2 below" not in text


def test_notices_promise_no_abort_window():
    """The step auto-proceeds in the same turn, so no notice may offer a
    pause before the writes it announces (#599)."""
    for name in STEP_FILES:
        text = _read(REFS / name)
        for promise in ("Esc or Ctrl+C", "if you stop here", "nothing has been rewritten yet",
                        "has been written yet"):
            assert promise not in text, (name, promise)
    rerun = _section(_read(REFS / "detect-and-tier.md"), "### 3.")
    assert "Next time, to refresh only the tier without paying the ccc re-index cost" in rerun


# Every file a setup step writes into the run folder, by redirect or --result-to.
RUN_DIR_WRITE_RE = re.compile(r'(?:>|--result-to) "\{run_dir\}/([a-z-]+\.json)"')
# Section 5's delete: the saved files by name, then the folder only if it is empty.
RUN_DIR_DELETE_RE = re.compile(r'^rm -f ((?:"\{run_dir\}/[a-z-]+\.json" )+)&& rmdir "\{run_dir\}"$', re.M)


def test_run_folder_is_made_in_step_1_and_removed_in_step_4():
    detect = _section(_read(REFS / "detect-and-tier.md"), "### 1.")
    assert 'mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX"' in detect
    assert "Bind `{run_dir}` ← the path it prints" in detect
    assert "halt with phase `step 1:run-folder`" in detect
    report = _read(REFS / "report.md")
    chain = _section(report, "### 5.")
    delete = RUN_DIR_DELETE_RE.search(chain)
    assert delete, "section 5 does not delete the run folder file by file"
    written = {name for step in STEP_FILES for name in RUN_DIR_WRITE_RE.findall(_read(REFS / step))}
    assert set(re.findall(r'"\{run_dir\}/([a-z-]+\.json)"', delete.group(1))) == written
    # A recursive delete of a mis-bound {run_dir} could take every run's folder with it.
    assert "rm -r" not in report
    # Deleted before the tier-miss line shows, so that line stays the final message.
    assert delete.start() < chain.index("`{require_tier_satisfied}` is `false`")
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    outputs = next(line for line in contract.splitlines() if line.startswith("| **Outputs**"))
    assert "`{project-root}/_bmad-output/.skf-run/`" in outputs
    assert "a halt that names a phase leaves it in place" in outputs


STAGED_RE = re.compile(r'(?:> "\{run_dir\}/([a-z-]+\.json)" && cat "\{run_dir\}/\1"'
                       r'|--result-to "\{run_dir\}/([a-z-]+\.json)")')


def test_every_staged_helper_output_is_one_the_emitter_reads():
    staged = {a or b for step in STEP_FILES for a, b in STAGED_RE.findall(_read(REFS / step))}
    declared = set(re.findall(r'^STAGED_[A-Z_]+ = "([a-z-]+\.json)"$', _read(EMIT_HELPER), re.MULTILINE))
    assert staged == declared == {"detect-tools.json", "ccc-exclusions.json", "qmd-classify.json",
                                  "qmd-remove.json", "clean-stale.json"}


def test_report_payload_is_staged_before_the_banner_and_shared_with_the_envelope():
    report = _read(REFS / "report.md")
    staged = _section(report, "### 1.")
    assert "cat > \"{run_dir}/report-context.json\" <<'SKF_JSON'" in staged
    keys = set(re.findall(r'^  "([a-z_]+)":', staged, re.MULTILINE))
    # Only what no helper output holds: every other value comes from a staged file (#592).
    assert keys == {"project_root", "config_path", "forge_data_folder", "orphan_auto_resolution", "error"}
    doc = ast.get_docstring(ast.parse(_read(EMIT_HELPER)))
    assert all(f'"{key}"' in doc for key in keys), keys
    banner = _section(report, "### 2.")
    assert ('render-report --run-dir "{run_dir}" --tier-rules "{skill-root}/references/tier-rules.md" '
            '< "{run_dir}/report-context.json"') in banner
    assert (REFS / "tier-rules.md").is_file()
    # The script owns the banner's lines: no template of them is left to drift from it.
    assert "kept for reference only" not in report and "{if " not in report
    emit = _section(report, "### 4.")
    assert 'emit --run-dir "{run_dir}" < "{run_dir}/report-context.json"' in emit
    assert "echo '" not in report and "tierRulesData" not in report
    rules = _section(report, "## Rules")
    assert "negative framing" not in rules
    # The one place the step says who owns the FORGE STATUS lines.
    assert "never compose, add or drop a line yourself" in rules
    frontmatter, _ = _split_frontmatter(report)
    assert "FORGE STATUS" not in frontmatter


def test_a_banner_that_cannot_render_is_one_line_not_a_halt():
    """An interactive run has written its configuration by step 4, so a
    missing or failing helper costs the banner, never the rest of the run;
    only the envelope-only run halts without the helper."""
    report = _read(REFS / "report.md")
    halt = next(line for line in _section(report, "## Rules").splitlines() if "`step 4:helper-missing`" in line)
    assert halt.startswith("- If section 4 finds no existing path in `emitEnvelopeProbeOrder`")
    frontmatter, _ = _split_frontmatter(report)
    assert "halt if neither exists when section 4 emits the envelope" in " ".join(
        line.lstrip("# ") for line in frontmatter.splitlines())
    banner = _section(report, "### 2.")
    fallback = next(b for _, _, b in _prose_blocks(banner) if "could not be rendered" in b)
    assert "or no path in `emitEnvelopeProbeOrder` exists" in fallback
    assert "`skf-emit-result-envelope.py was not found`" in fallback
    assert "continue: the forge is configured either way" in fallback
    assert "helper-missing" not in banner


def test_payload_strings_escape_control_characters_and_a_bad_payload_is_rewritten_once():
    """A failed `ccc index` reports on several lines, and a raw newline in the
    heredoc would make both render-report and emit refuse the payload."""
    report = _read(REFS / "report.md")
    rule = next(b for _, _, b in _prose_blocks(_section(report, "### 1.")) if b.startswith("Write each path"))
    assert "any `\"`, `\\` or control character in it escaped (a newline as `\\n`)" in rule
    retry = "names invalid JSON on stdin, fix `report-context.json` once and run it again"
    for prefix in ("### 2.", "### 4."):
        assert retry in _section(report, prefix), prefix
    emit_failure = next(b for _, _, b in _prose_blocks(_section(report, "### 4.")) if "exits non-zero" in b)
    assert "failed schema validation" not in emit_failure


def test_required_tier_block_points_at_no_section_a_deep_banner_lacks():
    """Deep can miss `--require-tier=Forge+` (Deep does not require ccc), and
    render-report prints "Climb to next tier" only below Deep. The banner
    ends with the block, so section 3 covers the banner that could not be
    rendered: without it, section 5 would halt on the miss unexplained."""
    block = _section(_read(REFS / "report.md"), "### 3.")
    assert "REQUIRED TIER NOT MET" in block
    assert "Climb to next tier" not in block
    assert "If section 2 displayed `FORGE STATUS could not be rendered`" in block
    assert "{require_tier_failure_missing_tools}" in block


# ---------------------------------------------------------------- what the docs promise


def test_contract_promises_only_the_final_message():
    """A skill-level rule cannot guarantee zero agent text between tool calls;
    the contract promises the final message, which is what `claude -p` prints."""
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    headless = next(line for line in contract.splitlines() if line.startswith("| **Headless**"))
    assert "a standalone run's final message, and so everything `claude -p` prints, is exactly one line" in headless
    assert "progress message" not in headless
    flags = next(line for line in contract.splitlines() if line.startswith("| **Flags**"))
    assert "progress messages" not in flags
    assert "all `claude -p` prints" in _read(HEADLESS_CONVENTION)


def test_workflows_doc_promises_only_the_final_message():
    doc = _read(WORKFLOWS_DOC)
    for overclaim in ("only line the agent displays", "the only line the run displays",
                      "SUPPRESSES all other output", "no progress messages"):
        assert overclaim not in doc, overclaim
    exception = next(line for line in doc.splitlines()
                     if line.startswith("**Exception: `/skf-setup` headless"))
    assert "this line is the run's final message, so it is exactly what `claude -p` prints" in exception


def test_workflows_doc_places_the_health_check_by_outcome():
    """The health check runs only on success; a tier miss or a halt ends before it."""
    exception = next(line for line in _read(WORKFLOWS_DOC).splitlines()
                     if line.startswith("**Exception: `/skf-setup` headless"))
    assert "after the health check has run, so" not in exception
    assert "On success the health check runs first and the envelope follows it" in exception
    assert "On a tier miss or a halt the health check does not run" in exception


def test_docs_state_when_no_envelope_arrives():
    """With SKF's scripts absent there is no helper to build an envelope, so
    the one line is the bare reason; pipelines must treat that as a failure."""
    exception = next(line for line in _read(WORKFLOWS_DOC).splitlines()
                     if line.startswith("**Exception: `/skf-setup` headless"))
    assert "SKF's scripts are not installed in the project" in exception
    assert "the run's one line is the bare halt reason" in exception
    assert "Pipelines should treat a missing envelope as a failure" in exception
    entry = _section(_read(TROUBLESHOOTING), '### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"')
    assert "the run's one line is the message alone" in entry
    assert "Pipelines should treat a run with no `SKF_SETUP_RESULT_JSON` line as a failure" in entry
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    failure = next(line for line in contract.splitlines() if line.startswith("| **Failure modes**"))
    assert "bare halt reason with no envelope" in failure
    # A machine where no runner in the halt contract can run the helper.
    assert "none of `uv`, `python3`, `python` and `py -3` can run it" in failure
    assert "Two cases have no envelope" in exception
    assert "neither `uv` nor a Python interpreter (`python3`, `python` or `py -3`)" in exception
    uv_entry = _section(_read(TROUBLESHOOTING), '### "Setup cannot proceed: `uv` is not installed"')
    assert "needs only the Python standard library" in uv_entry
    assert "the first of `python3`, `python` or `py -3` that runs on the machine" in uv_entry
    assert "the run's one line is the message alone" in uv_entry
    assert "Pipelines should treat a run with no `SKF_SETUP_RESULT_JSON` line as a failure" in uv_entry
    assert "`uv` or a Python interpreter can run them" in entry


# ---------------------------------------------------------------- envelope status contract


def _status_enum() -> list[str]:
    return json.loads(_read(SCHEMA))["properties"]["skf_setup"]["properties"]["status"]["enum"]


def _statuses(text: str) -> set[str]:
    return set(re.findall(r"`([a-z]+(?:_[a-z]+)*)`", text))


def test_status_lists_agree_with_the_schema_enum():
    """SKILL.md and docs/workflows.md list exactly the statuses the schema allows."""
    enum = set(_status_enum())
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    headless = next(line for line in contract.splitlines() if line.startswith("| **Headless**"))
    assert _statuses(headless.split("top-level `status` field:")[1].split(". ")[0]) == enum
    doc = next(l for l in _read(WORKFLOWS_DOC).splitlines() if "Branch on the top-level `status` field (" in l)
    assert _statuses(doc.split("Branch on the top-level `status` field (")[1].split(")")[0]) == enum
    require_tier = next(l for l in _read(WORKFLOWS_DOC).splitlines() if l.startswith("- `--require-tier="))
    assert "Pipelines branch on the envelope's `status` field" in require_tier
    assert "branch on the JSON envelope's `require_tier_satisfied`" not in require_tier


def test_no_surface_promises_the_retired_write_failure_status():
    hits = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for base in (SRC, REPO_ROOT / "docs") for p in base.rglob("*")
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".yaml", ".csv", ".toml"}
        and "write_failure" in p.read_text(encoding="utf-8", errors="replace")
    )
    assert hits == []


def test_write_failure_phases_named_wherever_a_write_failure_is_described():
    phases = set(re.findall(r'[`"](step 2:[a-z-]+)[`"]', _read(REFS / "write-config.md")))
    phases.discard("step 2:helper-missing")  # an install fault, not a write failure
    assert phases == {"step 2:write-tools", "step 2:forge-data-dir"}
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    failure = next(line for line in contract.splitlines() if line.startswith("| **Failure modes**"))
    doc = next(l for l in _read(WORKFLOWS_DOC).splitlines() if "Branch on the top-level `status` field (" in l)
    schema = json.loads(_read(SCHEMA))["properties"]["skf_setup"]["properties"]["status"]["description"]
    for phase in sorted(phases):
        assert f"`{phase}`" in failure, phase
        assert f"`{phase}`" in doc, phase
        assert f"'{phase}'" in schema, phase


def test_step_4_passes_a_null_error_and_step_2_binds_none():
    """A halt that names a phase never reaches step 4, so its payload's error is null."""
    report = _read(REFS / "report.md")
    staged = _section(report, "### 1.")
    assert '"error": null' in staged
    assert "`error` stays `null`: a halt that names a phase never reaches this step" in staged
    assert "{error_object_or_null}" not in report
    assert "set `{error:" not in _read(REFS / "write-config.md")


# ---------------------------------------------------------------- contract lift, sidecar path, helper staging


def test_skill_md_lifts_its_invocation_contract():
    """#600: the headless-only contract lives behind a one-line pointer, so
    SKILL.md stays under its 3,000-token budget (len // 4, the SKF convention)."""
    skill = _read(SKILL_MD)
    pointer = _section(skill, "## Invocation Contract")
    assert "`references/invocation-contract.md`" in pointer and "| **" not in pointer
    assert len(skill) // 4 < 3000, len(skill) // 4
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    rows = re.findall(r"^\| \*\*([A-Za-z ]+)\*\* \|", contract, re.MULTILINE)
    assert rows == ["Inputs", "Flags", "Gates", "Outputs", "Headless", "Failure modes"]
    headless = next(line for line in contract.splitlines() if line.startswith("| **Headless**"))
    assert "Schema: `shared/scripts/schemas/skf-setup-result-envelope.v1.json`" in headless
    assert "report.md` §4" not in contract
    convention = _read(HEADLESS_CONVENTION)
    assert "skf-setup's `references/invocation-contract.md` states this" in convention
    assert "Its SKILL.md Invocation Contract" not in convention


def test_description_trigger_names_its_object():
    """A bare "set up" matches any setup request; the trigger names the forge."""
    description = re.search(r"^description: (.+)$", _read(SKILL_MD), re.MULTILINE).group(1)
    triggers = re.findall(r'"([^"]+)"', description)
    assert triggers == ["set up the forge", "initialize the forge"]


SETUP_PROSE = [SKILL_MD, *sorted(REFS.glob("*.md"))]


@pytest.mark.parametrize("path", SETUP_PROSE, ids=lambda p: p.name)
def test_setup_reads_and_writes_the_sidecar_through_sidecar_path(path):
    """#596: sidecar_path is resolved at activation, so no setup file
    hard-codes the default sidecar folder."""
    text = _read(path)
    assert "forger-sidecar" not in text
    for match in re.finditer(r"[{}\w/-]*(forge-tier\.yaml|preferences\.yaml)", text):
        if "/" in match.group(0):
            assert match.group(0).startswith("{sidecar_path}/"), (path.name, match.group(0))


@pytest.mark.parametrize("path", SETUP_PROSE, ids=lambda p: p.name)
def test_no_step_transition_banners(path):
    """#599: a guarded "Proceeding to ..." line carries no information and
    is one more display the quiet contract must police."""
    assert "Proceeding to" not in _read(path)


def test_step_goals_state_no_tier_gate_of_their_own():
    """Section 1 of each step is the only statement of when it runs: ccc
    alone for step 1b, the tier for step 3's QMD part and ccc for its prune."""
    ccc_goal = _section(_read(REFS / "ccc-index.md"), "## STEP GOAL:")
    assert "Quick" not in ccc_goal and "Forge" not in ccc_goal
    hygiene = _read(REFS / "auto-index.md")
    assert "For Quick and Forge tiers" not in hygiene and "(Forge+ or Deep)" not in hygiene
    first = _section(hygiene, "### 1.")
    assert ("The QMD sections (2 and 3) run only when `{calculated_tier}` is Deep, and section 4 runs "
            "when `{calculated_tier}` is Deep or `{ccc}` is true") in first


def test_preferences_yaml_is_left_to_the_installer():
    """Setup no longer writes preferences.yaml: the installer's setupSidecar
    creates it, and every read falls back to defaults without it."""
    for path in SETUP_PROSE:
        assert "init-prefs" not in _read(path), path.name
    write = _read(REFS / "write-config.md")
    assert "Never create or edit `{sidecar_path}/preferences.yaml`: the installer writes it" in write
    assert "### 2. Initialize preferences.yaml" not in write and "preferences_yaml_created" not in write
    preamble = _section(_read(REFS / "detect-and-tier.md"), "### 3.")
    assert "preferences.yaml" not in preamble
    outputs = next(line for line in _section(_read(INVOCATION_CONTRACT), "## Invocation Contract").splitlines()
                   if line.startswith("| **Outputs**"))
    assert "setup never writes `preferences.yaml`: the installer creates it" in outputs
    installer = _read(REPO_ROOT / "tools" / "cli" / "lib" / "installer.js")
    assert "async setupSidecar(" in installer
    assert (SRC / "forger" / "preferences.yaml").is_file()


def test_step_1b_stages_the_helper_result_and_binds_nothing():
    """#592: the merge helper builds the index, stamps it and writes its result
    for steps 2 and 4, so no step reads ccc status or types a timestamp."""
    text = _read(REFS / "ccc-index.md")
    for flag in ("--config", "--build-index", '--result-to "{run_dir}/ccc-exclusions.json"'):
        assert flag in text, flag
    assert "←" not in text and "{current ISO timestamp}" not in text
    assert "ccc index\n" not in text and "cd \"{project-root}\" && ccc" not in text
    write = _section(_read(REFS / "write-config.md"), "### 1.")
    assert '--detect-from "{run_dir}/detect-tools.json"' in write
    assert '--ccc-from "{run_dir}/ccc-exclusions.json"' in write
    assert "echo '" not in write


def _project(tmp_path: pathlib.Path, config: str, preferences: str | None = None) -> pathlib.Path:
    (tmp_path / "_bmad" / "skf").mkdir(parents=True)
    (tmp_path / "_bmad" / "skf" / "config.yaml").write_text(config, encoding="utf-8")
    if preferences is not None:
        sidecar = tmp_path / "custom-sidecar"
        sidecar.mkdir()
        (sidecar / "preferences.yaml").write_text(preferences, encoding="utf-8")
    return tmp_path


def _preflight(project: pathlib.Path) -> tuple[int, dict]:
    done = subprocess.run([sys.executable, str(PREFLIGHT), str(project), "--allow-missing-sidecar"],
                          capture_output=True, text=True, timeout=30)
    return done.returncode, json.loads(done.stdout)


def test_preflight_gives_every_value_activation_binds(tmp_path):
    """Item 4 binds these fields of skf-preflight.py's output, a custom
    sidecar_path included, and the tier override exactly as stored."""
    project = _project(tmp_path, "skills_output_folder: skills\nforge_data_folder: forge-data\n"
                                 "sidecar_path: custom-sidecar\nproject_name: demo\n",
                       "tier_override: ~\nheadless_mode: true\n")
    code, out = _preflight(project)
    assert code == 0 and out["status"] == "ok", out
    load = next(line for line in _on_activation(_read(SKILL_MD)).splitlines() if "`status` `ok`" in line)
    for name in ("output_folder", "skills_output_folder", "forge_data_folder", "sidecar_path"):
        assert f"`{{{name}}}`" in load, name
        assert f"{name}_resolved" in out["config"], name
    assert "`config.<name>_resolved`" in load
    assert pathlib.Path(out["config"]["sidecar_path_resolved"]) == project / "custom-sidecar"
    assert "`{tier_override}` from `sidecar.preferences.tier_override`" in load
    assert out["sidecar"]["preferences"]["tier_override"] is None
    assert out["derived"]["headless_mode"] is True


@pytest.mark.parametrize("config,code", [
    ("skills_output_folder: [unclosed\n", "CONFIG_MALFORMED"),
    ("skills_output_folder: skills\n", "SIDECAR_UNDEFINED"),
    ("sidecar_path: '{project-root}/{sidecar_path}'\n", "SIDECAR_UNDEFINED"),
], ids=["malformed", "no-sidecar-path", "placeholder"])
def test_preflight_errors_carry_the_prefix_the_halt_drops(tmp_path, config, code):
    """The config-malformed reason is the helper's error without its leading
    `Cannot initialize. `, which every hard halt but CONFIG_MISSING starts with."""
    rc, out = _preflight(_project(tmp_path, config))
    assert rc == 1 and out["status"] == "hard-halt" and out["code"] == code
    assert out["error"].startswith("Cannot initialize. ")


def test_customize_toml_hook_comments_match_the_activation_order():
    """#596: the prepend hook runs after the uv probe and the config load, and
    setup's on_complete is an instruction, not a shell command."""
    text = _read(CUSTOMIZE)
    prepend = text[:text.index("activation_steps_prepend = []")]
    assert "after flag parsing, the config check, the uv\n# probe and the config load" in prepend
    assert "cannot install uv or create\n# config.yaml" in prepend
    on_complete = text[text.index("persistent_facts = []"):text.index('on_complete = ""')]
    assert "An instruction the agent carries out (not a shell command" in on_complete
