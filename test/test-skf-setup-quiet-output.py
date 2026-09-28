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
SHARED_HEALTH_CHECK = SRC / "shared" / "health-check.md"
EMIT_HELPER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
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
DISPLAY_RULE = "Display messages only when `{headless_mode}` and `{quiet_mode}` are both false"
NO_NARRATION_RULE = (
    "When `{headless_mode}` or `{quiet_mode}` is true, write no assistant text at all between "
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


@pytest.mark.parametrize("name", STEP_FILES)
def test_step_display_instructions_carry_quiet_guard(name):
    _, body = _split_frontmatter(_read(REFS / name))
    displays = [
        (n, heading, block) for n, heading, block in _prose_blocks(body, items=True) if DISPLAY_RE.search(block)
    ]
    assert displays, f"{name}: no display instruction matched; the pattern no longer fits this file"
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


def test_uv_probe_follows_headless_reconcile():
    """Headless from preferences.yaml must be known before the uv halt fires."""
    items = re.findall(r"^(\d+)\. \*\*(.+?)\*\*", _on_activation(_read(SKILL_MD)), re.MULTILINE)
    order = [title for _, title in items]
    expected = ["Parse invocation flags first", "Load config", "Reconcile `{headless_mode}`",
                "Probe `uv` runtime.", "Resolve workflow customization."]
    assert [t for t in order if t in expected] == expected
    assert [int(n) for n, _ in items] == list(range(1, len(items) + 1))


def test_halts_display_only_the_blocked_envelope():
    halt_contract = next(line for line in _read(SKILL_MD).splitlines() if "Halt contract" in line)
    assert "nothing else" in halt_contract
    assert "verbatim" in halt_contract
    assert "Interactive runs display the human diagnostic and emit no envelope" in halt_contract
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
PY39_STDLIB_IMPORTS = frozenset({"__future__", "argparse", "json", "os", "pathlib", "sys"})


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
    assert "no `'` and no `\\`" in halt_contract
    headings = re.findall(r'^### "(Setup cannot proceed: .+)"$', _read(TROUBLESHOOTING), re.MULTILINE)
    assert len(headings) >= 2
    activation = _on_activation(text)
    for heading in headings:
        rendered = heading.replace("`", "")
        assert f"reason `{rendered}" in activation, rendered
    reasons = re.findall(r"reason `([^`]+)`", activation)
    assert len(reasons) >= 3
    assert all("'" not in r and "\\" not in r for r in reasons), reasons
    malformed = next(r for r in reasons if "not valid YAML" in r)
    assert "first line of the parser error" in malformed


def test_detector_failure_branch_is_defined():
    section = _section(_read(REFS / "detect-and-tier.md"), "### 2.")
    branch = next(b for _, _, b in _prose_blocks(section) if "exits non-zero" in b)
    assert "`step 1:detect-tools`" in branch
    assert "halt" in branch
    assert QUIET in branch


def test_clean_stale_failure_binds_flags():
    section = _section(_read(REFS / "auto-index.md"), "### 4.")
    branch = next(b for _, _, b in _prose_blocks(section) if "exits non-zero" in b)
    for binding in ("hygiene_stale_cleaned: 0", "ccc_registry_stale_cleaned: 0",
                    "ccc_registry_stale_removed_paths: []"):
        assert binding in branch, binding
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
    item = next(u for _, _, u in _prose_blocks(chain, items=True) if "{onCompleteCommand}" in u and "execute it now" in u)
    assert "when `{headless_mode}` or `{quiet_mode}` is true, display nothing about it" in item


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


def test_campaign_consent_does_not_override_the_headless_queue():
    """The campaign's "improvement" consent pre-satisfies the friction/gap
    opt-in only; a headless review gate still queues every finding locally."""
    text = _read(CAMPAIGN_RELAY)
    assert "follows an interactive **[Y]**" in text
    assert "Under `{headless_mode}` that gate takes its listed default **[Q]**" in text


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
    """The forger's own summary and the Pipeline State block forward the marker too."""
    forger = _read(SRC / "skf-forger" / "SKILL.md")
    sentence = next(line for line in forger.splitlines() if "Each chained workflow runs with" in line)
    assert "`{pipeline_mode}` = true" in sentence
    state = _section(_read(SRC / "shared" / "references" / "pipeline-contracts.md"), "## Pipeline State")
    assert re.search(r"^\s+pipeline_mode: true\b", state, re.M)


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


# ---------------------------------------------------------------- what the docs promise


def test_contract_promises_only_the_final_message():
    """A skill-level rule cannot guarantee zero agent text between tool calls;
    the contract promises the final message, which is what `claude -p` prints."""
    contract = _section(_read(SKILL_MD), "## Invocation Contract")
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
    contract = _section(_read(SKILL_MD), "## Invocation Contract")
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
    contract = _section(_read(SKILL_MD), "## Invocation Contract")
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
    assert phases == {"step 2:write-tools", "step 2:init-prefs", "step 2:forge-data-dir"}
    contract = _section(_read(SKILL_MD), "## Invocation Contract")
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
    assert '"error": null' in _section(report, "### 4.")
    assert "{error_object_or_null}" not in report
    assert "set `{error:" not in _read(REFS / "write-config.md")
