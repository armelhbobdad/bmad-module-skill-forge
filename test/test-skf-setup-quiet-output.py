"""Prose-contract tests: /skf-setup --quiet and --headless display only the envelope.

No test executes the step files, so these check the wording the agent follows:
every display instruction in a setup step carries the `{quiet_mode}` guard,
every step forbids the agent's own notes between tool calls, every halt shows
only the blocked envelope, and the success envelope waits in the run folder
until the run's last tool call prints it as a standalone run's final message
(`claude -p` prints only that message), while a forger pipeline gets control
back after it. A quiet run runs no health check, and the `headless_mode`
preference only resolves the gates: the orphan gate resolves under it or
quiet to a listed default, and the shared health check keeps a listed
headless default for its review gate. The docs promise no more than that
final message. The activation halts name a runner chain the stdlib-only
envelope helper runs under, and every status list agrees with the schema.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
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
# The halt contract, which only a halt that names a phase loads (#1184).
HALT_CONTRACT = REFS / "halt-contract.md"
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


def _halt_contract() -> str:
    """The halt-contract paragraph of references/halt-contract.md, which On Activation points at (#1184)."""
    [line] = [line for line in _read(HALT_CONTRACT).splitlines() if "follows this contract" in line]
    return line


def _activation_halts() -> str:
    """The halt contract's list of each On Activation halt's path and reason, which SKILL.md names by phase
    only, so only a halt reads them (#1184)."""
    return _section(_read(HALT_CONTRACT), "## On Activation Halts")


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
    """#1117: activation resolves every step's probe order at once, so a
    missing helper halts before any step runs; the step halts stay as a backstop."""
    conventions = _section(_read(SKILL_MD), "## Conventions")
    probe_line = next(line for line in conventions.splitlines() if "ProbeOrder" in line)
    assert ("On Activation item 4 resolves them all and halts (`on-activation:helper-missing`) on any helper "
            "with neither path.") in probe_line
    # The Done when shortens the bullet: shorter than its 389 bytes before #1117.
    assert len(probe_line.encode("utf-8")) < 389
    assert "Run the first that exists" not in probe_line


def test_conventions_say_where_each_path_resolves():
    """#601: the installed helper folder carries {project-root}; module-level
    and sibling-skill paths resolve from the SKF module root; tier-rules.md,
    which no stage chains to, is named with the step that reads it."""
    conventions = _section(_read(SKILL_MD), "## Conventions")
    assert ("- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the "
            "SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root") in conventions
    assert ("- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the "
            "SKF module root, and that skill must be installed with this one.") in conventions
    probe = next(line for line in conventions.splitlines() if "ProbeOrder" in line)
    assert ("installed path (`{project-root}/_bmad/skf/shared/scripts/<name>`) then its dev path "
            "(`{project-root}/src/shared/scripts/<name>`)") in probe
    assert "installed as `_bmad/" not in conventions
    assert ("`tier-rules.md`, the tier table `report.md` passes to the emitter's banner") in conventions
    assert '--tier-rules "{skill-root}/references/tier-rules.md"' in _read(REFS / "report.md")
    assert "\u2014" not in conventions
    toml = _read(CUSTOMIZE)
    assert "# Team overrides:     {project-root}/_bmad/custom/skf-setup.toml" in toml
    assert "# Personal overrides: {project-root}/_bmad/custom/skf-setup.user.toml" in toml


def test_the_preference_sets_headless_mode_alone():
    """#1183: `headless_mode: true` in preferences.yaml resolves the gates and keeps the output, as
    docs/getting-started.md says; only the flags and a pipeline make setup envelope-only."""
    text = _read(SKILL_MD)
    reconcile = next(line for line in text.splitlines() if "**Reconcile `{headless_mode}`**" in line)
    assert ("OR it with `derived.headless_mode` (`headless_mode: true` in `preferences.yaml`), which resolves the "
            "gates only: `{quiet_mode}` stays as item 1 set it.") in reconcile
    assert "set `{quiet_mode}` to true" not in reconcile
    # Only item 1 sets {quiet_mode}: no later activation item turns it on.
    activation = _on_activation(text)
    later = activation[activation.index("2. **Check for the config.**"):]
    setters = [line.strip()[:60] for line in later.splitlines()
               if re.search(r"set `\{quiet_mode\}`|`\{quiet_mode\}` (?:is|to) true when", line)]
    assert setters == [], setters


def test_activation_checks_uv_before_a_helper_parses_the_config():
    """config.yaml and preferences.yaml are parsed by skf-preflight.py (#592),
    which needs uv: the config check runs no script, so it still comes first,
    and headless_mode from preferences.yaml is folded in only once it is read
    (it sets no quiet mode, #1183)."""
    items = re.findall(r"^(\d+)\. \*\*(.+?)\*\*", _on_activation(_read(SKILL_MD)), re.MULTILINE)
    order = [title for _, title in items]
    expected = ["Parse invocation flags first", "Check for the config.", "Probe `uv` runtime.",
                "Load config and preferences.", "Reconcile `{headless_mode}`", "Resolve workflow customization."]
    assert [t for t in order if t in expected] == expected
    assert [int(n) for n, _ in items] == list(range(1, len(items) + 1))
    # The preference no longer changes {quiet_mode}, so the halts need no clause on when it is known.
    halt_contract = _halt_contract()
    assert "preferences.yaml" not in halt_contract and "known at every halt" not in halt_contract


def test_halts_display_only_the_blocked_envelope():
    halt_contract = _halt_contract()
    assert "nothing else" in halt_contract
    assert "verbatim" in halt_contract
    assert "Interactive runs display the reason as their diagnostic and emit no envelope" in halt_contract
    assert "nothing else" in _section(_read(REFS / "write-config.md"), "### 1.")


def test_halt_contract_falls_back_to_the_reason_when_the_helper_fails():
    """A payload emit-blocked rejects must not leave a quiet run with no line at all."""
    halt_contract = _halt_contract()
    assert ("If neither path exists, or no runner exits 0 and prints that line, "
            "display the reason alone as that one line.") in halt_contract
    fallback = _section(_read(REFS / "write-config.md"), "### 1.")
    assert "If the helper exits non-zero or prints no line, display the reason alone." in fallback


def _runner_loop() -> str:
    """The fenced runner loop right after the halt-contract paragraph (#1117), in its own file (#1184)."""
    text = _read(HALT_CONTRACT)
    halt_contract = _halt_contract()
    m = re.match(r"\n\n```bash\n(.*?\n)```\n", text[text.index(halt_contract) + len(halt_contract):], re.S)
    assert m, "no runner loop right after the halt contract"
    return m.group(1)


def test_halt_contract_names_a_runner_chain_for_the_activation_halts():
    """The activation halts can fire before uv is proven present, and Windows
    often has `python` or `py` but only a store alias for `python3`; by the
    time a step file runs, activation has proven uv present. The chain is one
    loop the halts run as written (#1117)."""
    halt_contract = _halt_contract()
    assert "`<runner>` is `uv run` in the step files" in halt_contract
    assert ("so they run the loop below as written, dropping `--path` or the `--stderr-from -` heredoc as the "
            "halt needs") in halt_contract
    # Every halt the loop serves comes before item 6, which binds the resolver reason (#1119).
    assert "or adding `--customization-resolver-unavailable`" not in halt_contract
    prefix = re.search(r'^ENVELOPE_PREFIX = "(.+)"$', _read(EMIT_HELPER), re.M).group(1)
    assert f"it stops at the first runner that exits 0 and prints a line starting `{prefix.strip()}`" in halt_contract
    assert ("`<helper>` is `{emitEnvelopeHelper}` once item 4 bound it, and for the halts of items 1 to 4 "
            "`skf-emit-result-envelope.py` at its installed path, else its dev path "
            "(`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else "
            "`{project-root}/src/shared/scripts/skf-emit-result-envelope.py`)") in halt_contract
    # #1184: the file a halt loads names the emitter's paths and the items it means, not SKILL.md's Conventions.
    assert "(Conventions)" not in halt_contract
    assert "Item numbers name SKILL.md On Activation items." in halt_contract
    assert "The halts of items 1 to 4 can fire before `uv` is proven present" in halt_contract
    assert "try the runners" not in halt_contract and "`python3` for the halts in this list" not in halt_contract
    loop = _runner_loop()
    assert f'case "$line" in "{prefix}"*) printf' in loop
    assert loop.count("<<'SKF_TEXT'") == 1 and "\nSKF_TEXT\n) && " in loop
    assert loop.endswith("done\n")


ACTIVATION_RUNNERS = re.compile(r"^for r in (.+); do$", re.M)
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
    halt_contract = _halt_contract()
    chain = ACTIVATION_RUNNERS.search(_runner_loop())
    assert chain, "no runner chain for the activation halts"
    assert shlex.split(chain.group(1)) == ["uv run", "python3", "python", "py -3"]
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


def _filled_loop(phase: str, reason: str, path: str | None, text: str | None) -> str:
    """The runner loop as an activation halt runs it: no `--path` for a halt
    without one, and no heredoc for a halt with no text from the user or a helper."""
    loop = _runner_loop()
    if path is None:
        loop = loop.replace(' --path "<path>"', "", 1)
    if text is None:
        loop = loop.replace(" --stderr-from - <<'SKF_TEXT'\n<text>\nSKF_TEXT\n", "\n", 1)
        assert "SKF_TEXT" not in loop
    return (loop.replace("<helper>", EMIT_HELPER.as_posix()).replace("<phase>", phase)
            .replace("<reason>", reason).replace("<path>", path or "").replace("<text>", text or ""))


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_the_runner_loop_prints_one_envelope_with_only_python3_on_path(tmp_path):
    """#1117: before uv is proven, the first runner that works prints the line;
    the quoted heredoc keeps every quote, `$( )`, backtick and backslash literal.
    A `uv` that exits 0 but prints no envelope line is skipped, not displayed."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    env = {"PATH": str(bindir), "HOME": str(tmp_path)}
    message = "it's \"read-only\" $(touch pwned) `touch pwned2` C:\\x ( unbalanced"
    loop = _filled_loop("on-activation:helper-missing", "Setup cannot proceed: <message>",
                        "/project/_bmad/skf/shared/scripts", message)
    expected = {"phase": "on-activation:helper-missing", "reason": "Setup cannot proceed: " + message,
                "path": "/project/_bmad/skf/shared/scripts"}
    # Only python3 on PATH: `uv run` is not found, and python3 prints the line.
    done = subprocess.run([shutil.which("bash"), "-c", loop], capture_output=True, timeout=30, cwd=tmp_path, env=env)
    assert _blocked_error(done) == expected
    # A `uv` that exits 0 with a line that is no envelope: the guard skips it and python3 still prints.
    uv = bindir / "uv"
    uv.write_text("#!/bin/sh\n: > \"$HOME/uv-ran\"\nprintf '%s\\n' 'uv: not an envelope line'\nexit 0\n",
                  encoding="utf-8")
    uv.chmod(0o755)
    done = subprocess.run([shutil.which("bash"), "-c", loop], capture_output=True, timeout=30, cwd=tmp_path, env=env)
    assert _blocked_error(done) == expected
    assert (tmp_path / "uv-ran").exists(), "the uv stub never ran, so the prefix guard was not exercised"
    assert b"not an envelope line" not in done.stdout
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()
    # A halt with no path and no text drops both, and still prints one line.
    error = _blocked_error(subprocess.run([shutil.which("bash"), "-c", _filled_loop(
        UV_MISSING["phase"], UV_MISSING["reason"], None, None)], capture_output=True, timeout=30, cwd=tmp_path,
        env=env))
    assert error == {**UV_MISSING, "path": "<n/a>"}
    # No runner prints the line (only the stray uv is left): nothing is printed, so the
    # contract displays the reason alone.
    (bindir / "python3").unlink()
    nothing = subprocess.run([shutil.which("bash"), "-c", _filled_loop(
        UV_MISSING["phase"], UV_MISSING["reason"], None, None)], capture_output=True, timeout=30, cwd=tmp_path,
        env=env)
    assert nothing.stdout == b""


# The emit-blocked call each step's halt rule names: the emitter builds the payload.
# The phase and reason go between single quotes, so a backtick the halt contract
# puts for a quote stays literal.
STEP_HALT_CALL = """`uv run {emitEnvelopeHelper} emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"`"""


@pytest.mark.parametrize("name", [n for n in STEP_FILES if n != "report.md"])
def test_step_halts_run_emit_blocked_under_uv_with_a_fallback(name):
    text = _read(REFS / name)
    rule = next(line for line in _section(text, "## Rules").splitlines() if "emit-blocked" in line)
    assert STEP_HALT_CALL in rule and "which builds the payload itself" in rule
    assert "or the helper exits non-zero or prints no line" in rule
    assert "python3 {emitEnvelopeHelper}" not in text
    # No step types a halt payload: the options carry it (determinism-3).
    assert "pipe `{phase, reason, path}`" not in text and "pipe that `{phase, reason, path}`" not in text


def test_blocked_reason_rules_stated():
    """Reasons travel as a single-quoted `--reason`, so a fixed one holds no
    quote, and match the troubleshooting headings users search for; text from
    the user or a helper goes in on stdin, never typed into the argument."""
    text = _read(SKILL_MD)
    halt_contract = _halt_contract()
    assert QUOTE_RULE in halt_contract
    assert "a backtick for either quote" not in halt_contract and "single-quoted shell payload" not in halt_contract
    # A Windows path keeps the envelope's posix form, and a trailing `\` cannot escape the closing quote.
    assert '--path "<path>"` (`<path>` written with `/`; no `--path` for a halt without one)' in halt_contract
    headings = re.findall(r'^### "(Setup cannot proceed: .+)"$', _read(TROUBLESHOOTING), re.MULTILINE)
    assert len(headings) >= 2
    halts = _activation_halts()
    for heading in headings:
        rendered = heading.replace("`", "")
        assert f"reason `{rendered}" in halts, rendered
    reasons = re.findall(r"reason `([^`]+)`", halts)
    assert len(reasons) >= 3
    assert all("'" not in r and "\\" not in r for r in reasons), reasons
    assert "passed as the contract above says" in halts
    # A malformed config halts with the parser's own message, as Ferris shows it.
    load = next(line for line in _on_activation(text).splitlines() if "Any other `hard-halt`" in line)
    assert load.endswith("halt with phase `on-activation:config-malformed`."), load
    malformed = next(line for line in halts.splitlines() if "`on-activation:config-malformed`" in line)
    assert "reason `Setup cannot proceed: <message>`" in malformed
    assert "its `error` without the leading `Cannot initialize. `" in malformed
    assert "never preflight's whole JSON" in malformed
    assert "sanitized per the halt contract" not in load + malformed


def test_config_missing_reason_names_the_installer():
    """Setup never writes config.yaml, only the installer does, so the halt
    names it (#608). The reason keeps the troubleshooting heading as its
    prefix and leaves the file's path to the envelope's `path` (#601: no bare
    `_bmad/` path), and it travels in a single-quoted `--reason` from a code
    span, so it holds no quote, backslash or backtick and the helper carries
    it through unchanged."""
    assert "halt with phase `on-activation:config-missing`." in _on_activation(_read(SKILL_MD))
    m = re.search(r"`on-activation:config-missing` \(item 2\)[^\n]*?reason `([^`]+)`", _activation_halts())
    assert m, "config-missing halt not found"
    reason = m.group(1)
    assert reason.startswith("Setup cannot proceed: the SKF config file was not found. ")
    assert "_bmad/" not in reason
    assert '### "Setup cannot proceed: the SKF config file was not found"' in _read(TROUBLESHOOTING)
    for command in ("npx bmad-module-skill-forge install", "npx bmad-method install"):
        assert command in reason, command
    assert not set(reason) & set("'\"\\`"), reason
    done = _emit_blocked({"phase": "on-activation:config-missing", "reason": reason,
                          "path": "/project/_bmad/skf/config.yaml"})
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    assert json.loads(line[len("SKF_SETUP_RESULT_JSON: "):])["skf_setup"]["error"]["reason"] == reason


# The halt contract's rule for text from the user or a helper, in place of the
# hand-typed JSON payload: it goes on stdin, and `--reason` holds `<message>`.
QUOTE_RULE = ("Text from the user or a helper never goes into the single-quoted `--reason`: write `<message>` "
              "there and pass the text on stdin with `--stderr-from -` and a quoted `<<'SKF_TEXT'` heredoc, "
              "one per runner tried, for the emitter to fold to one line and escape.")
# The resolver reason every halt passes once On Activation item 6 bound it (#595): the file
# item 6 saved its stderr in, which the emitter reads, so no step escapes the reason (#1119).
RESOLVER_FILE = '--customization-resolver-unavailable-from "{run_dir}/resolver.err"'
RESOLVER_RULE = ("Once item 6 binds `{customization_resolver_unavailable}` to a reason, every later halt also "
                 f"passes `{RESOLVER_FILE}`, which the emitter folds to one line and escapes.")
ENVELOPE_PREFIX = "SKF_SETUP_RESULT_JSON: "


def _stdin_blocked(phase: str, reason: str, text: str, path: str | None = None) -> subprocess.CompletedProcess:
    """emit-blocked as the halt contract runs it for text from the user or a
    helper: the fixed reason holds `<message>`, and the text comes on stdin."""
    argv = [sys.executable, str(EMIT_HELPER), "emit-blocked", "--phase", phase, "--reason", reason]
    if path is not None:
        argv += ["--path", path]
    return subprocess.run([*argv, "--stderr-from", "-"], input=text.encode("utf-8"), capture_output=True,
                          timeout=10)


def _contract_call(text: str, run_dir: pathlib.Path | None = None) -> str:
    """The halt contract's emit-blocked call for the config-malformed halt, as a
    bash command: single-quoted phase and reason, the text in a quoted heredoc,
    and, with `run_dir`, the file option that names item 6's saved reason."""
    halt_contract = _halt_contract()
    call = re.search(r"run `(<runner> <helper> emit-blocked [^`]+)`", halt_contract).group(1)
    assert call == "<runner> <helper> emit-blocked --phase '<phase>' --reason '<reason>' --path \"<path>\"", call
    runner = f"{shlex.quote(sys.executable)} {shlex.quote(EMIT_HELPER.as_posix())}"
    command = (call.replace("<runner> <helper>", runner)
               .replace("<phase>", "on-activation:config-malformed")
               .replace("<reason>", "Setup cannot proceed: <message>")
               .replace("<path>", "/project/_bmad/skf/config.yaml"))
    if run_dir is not None:
        command += " " + RESOLVER_FILE.replace("{run_dir}", run_dir.as_posix())
    return f"{command} --stderr-from - <<'SKF_TEXT'\n{text}\nSKF_TEXT\n"


def _blocked_error(done: subprocess.CompletedProcess) -> dict:
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    assert line.startswith(ENVELOPE_PREFIX)
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["status"] == "blocked"
    return envelope["error"]


def test_a_malformed_config_halt_still_emits_its_blocked_envelope(tmp_path):
    """skf-preflight.py's YAML parse error names the file between double
    quotes. Passed on stdin, as the halt contract says, never typed into an
    argument, it reaches a quiet run's blocked envelope whole."""
    assert QUOTE_RULE in _halt_contract()
    config = tmp_path / "_bmad" / "skf" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"project_name: demo\nbad: key: here\n")
    proc = subprocess.run([sys.executable, str(PREFLIGHT), str(tmp_path), "--allow-missing-sidecar"],
                          capture_output=True, timeout=60)
    assert proc.returncode == 1, proc.stderr.decode("utf-8", "replace")
    result = json.loads(proc.stdout)
    assert result["code"] == "CONFIG_MALFORMED"
    assert '"' in result["error"], result["error"]
    message = result["error"].removeprefix("Cannot initialize. ")
    error = _blocked_error(_stdin_blocked("on-activation:config-malformed", "Setup cannot proceed: <message>",
                                          message, config.as_posix()))
    assert error == {"phase": "on-activation:config-malformed", "reason": "Setup cannot proceed: " + message,
                     "path": config.as_posix()}
    # preflight's whole JSON would put the JSON line in the reason: it carries `error`, not `message`.
    whole = _blocked_error(_stdin_blocked("on-activation:config-malformed", "Setup cannot proceed: <message>",
                                          proc.stdout.decode("utf-8")))
    assert whole["reason"] != "Setup cannot proceed: " + message


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("message", [
    'tool detection failed: C:\\Users\\bob\\x is not "readable"',
    "it's \"read-only\" $(touch pwned) `id` $HOME",
], ids=["windows-path-and-quotes", "quotes-and-substitutions"])
def test_the_halt_contract_passes_helper_text_on_stdin(tmp_path, message):
    """The documented call, run by bash: the quoted heredoc keeps every quote,
    backslash, `$( )` and backtick literal, and nothing runs."""
    done = subprocess.run(["bash", "-c", _contract_call(message)], capture_output=True, timeout=20, cwd=tmp_path)
    error = _blocked_error(done)
    assert error["reason"] == "Setup cannot proceed: " + message
    assert not (tmp_path / "pwned").exists()


# What item 6's `2> "{run_dir}/resolver.err"` saves when the resolver fails, and the
# one-line reason the emitter takes from it: backticks, `$( )`, quotes and a backslash
# path the shell would have run or eaten in an argument (#1119).
RESOLVER_ERR = (b"error: Python 3.11+ is required (stdlib `tomllib` not found).\n"
                b"  hint: run it in \"$HOME\" $(touch pwned) with C:\\py\\python.exe\n")
RESOLVER_REASON = "error: Python 3.11+ is required (stdlib `tomllib` not found)."


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("saved,reason", [
    (RESOLVER_ERR, RESOLVER_REASON),
    (b"exit 1: No module named 'tomllib' in \"$HOME\" $(touch pwned) `x` C:\\py\n",
     "exit 1: No module named 'tomllib' in \"$HOME\" $(touch pwned) `x` C:\\py"),
    (None, "(no error message)"),
], ids=["uv-python-error", "shell-characters", "missing-file"])
def test_a_halt_after_item_6_carries_the_resolver_reason(tmp_path, saved, reason):
    """#595, #1119: once item 6 bound a resolver reason, the halt names the file
    item 6 saved it in, and the blocked envelope warns, the reason on one line,
    that the overrides were not applied. Nothing in the reason runs."""
    halt_contract = _halt_contract()
    assert RESOLVER_RULE in halt_contract
    assert "escaping each" not in halt_contract
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    if saved is not None:
        (run_dir / "resolver.err").write_bytes(saved)
    done = subprocess.run(["bash", "-c", _contract_call("bad: key: here", run_dir)], capture_output=True,
                          timeout=20, cwd=tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["status"] == "blocked"
    assert envelope["warnings"] == [f"customization_resolver_unavailable: {reason}"]
    assert not (tmp_path / "pwned").exists()


def test_every_step_halt_passes_the_resolver_reason():
    """#595: the step files' halt rules pass the resolver reason as the halt
    contract does, and so does every fenced emit-blocked call, which a halt
    copies as written."""
    fenced = []
    for name in ("detect-and-tier.md", "write-config.md", "ccc-index.md", "auto-index.md"):
        text = _read(REFS / name)
        rule = next(line for line in _section(text, "## Rules").splitlines() if "emit-blocked" in line)
        # #1184: the contract is its own file, which a halt loads.
        assert rule.startswith("- Every halt follows `references/halt-contract.md`:"), name
        assert "SKILL.md halt contract" not in text, name
        assert (f"and `{RESOLVER_FILE}` once SKILL.md On Activation item 6 bound "
                "`{customization_resolver_unavailable}` to a reason)") in rule, name
        assert "escaped as the halt contract says" not in text, name
        calls = [line for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
                 for line in _joined(block).splitlines() if "emit-blocked" in line]
        for call in calls:
            assert call.rstrip().endswith(" " + RESOLVER_GROUP), (name, call)
        if calls:
            assert ("In each `emit-blocked` call of this step, keep the bracketed "
                    "`--customization-resolver-unavailable-from` only when On Activation item 6 bound "
                    "`{customization_resolver_unavailable}` to a reason; otherwise leave it out.") in text, name
        fenced += calls
    assert len(fenced) == len(STDERR_HALTS)


def test_item_6_runs_the_resolver_through_uv_and_binds_its_reason():
    """#595 option (a): the resolver runs under uv with --project-root, a failure
    prints one warning (never under --quiet: setup's envelope carries it) and
    keeps the reason for report.md and every later halt."""
    item = _section(_on_activation(_read(SKILL_MD)), "6. **Resolve workflow customization.**")
    assert ("uv run {resolveCustomizationHelper} --skill {skill-root} "
            "--project-root {project-root} --key workflow --facts 2> \"{run_dir}/resolver.err\"") in item
    assert "{project-root}/_bmad/scripts/resolve_customization.py" not in item
    flat = " ".join(item.split())
    assert ("It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-setup.toml` "
            "(team overrides, committed) and `.user.toml` (personal overrides, gitignored).") in flat
    # Item 4 halts when the script is missing (#1117), so item 6 names no reason for that case.
    assert ("When it exits non-zero or prints no JSON, print one line, "
            "`[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, "
            "`no JSON` when it printed none).") in flat
    assert "when the script is missing" not in flat and "is missing, print one line" not in flat
    assert ("If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: "
            "the `{project-root}/_bmad/custom/` overrides do not apply to this run.") in flat
    assert "Bind `{customization_resolver_unavailable}` ← that reason (null when the resolver ran)" in flat
    assert "print the warning only when `{quiet_mode}` is false" in flat
    # The redirect hides the resolver's stderr from the run, so the reason is read from the file,
    # and the file holds the reason whenever it is bound, also when the resolver printed none (#1119).
    assert ITEM_6_FILE_RULE in flat
    assert flat.index("overrides do not apply to this run.") < flat.index(ITEM_6_FILE_RULE) < \
        flat.index("Bind `{customization_resolver_unavailable}` ← that reason")
    assert (f"`references/report.md` and every later halt then pass `{RESOLVER_FILE}` to the emitter") in flat
    # #601: no bare `_bmad/` path is left for the path-standards scan to flag.
    assert re.search(r"(?<!\{project-root\}/)_bmad/", _on_activation(_read(SKILL_MD))) is None
    report = _read(REFS / "report.md")
    assert f"[{RESOLVER_FILE}]" in report and "{customization_resolver_unavailable}," not in report


# Item 6's sentence after the fallback: where `<reason>` is read, and the fixed reason the
# file gets when the resolver printed none (#1119 review round 1).
ITEM_6_FILE_RULE = ("The resolver's stderr is in `{run_dir}/resolver.err`, so read `<reason>` from that file "
                    "(`(no error message)` when it is empty); when it exits 0 and prints "
                    "no JSON, first write that fixed reason into the file "
                    "(`printf '%s\\n' '<the fixed reason>' > \"{run_dir}/resolver.err\"`), so the file holds the "
                    "reason whenever `{customization_resolver_unavailable}` is bound.")


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("case", ["resolver-fails", "resolver-silent", "resolver-no-json"])
def test_item_6_leaves_the_reason_in_the_file_the_halts_read(tmp_path, case):
    """#1119 review round 1: item 6's documented command, run by bash with a resolver that
    fails, saves its stderr in resolver.err; a silent failure leaves `(no error message)`; a
    run that exits 0 with no JSON gets its fixed reason through the documented printf. Each later halt's
    emitter then warns with that reason, and nothing in it runs."""
    item = _section(_on_activation(_read(SKILL_MD)), "6. **Resolve workflow customization.**")
    [command] = [line.strip() for line in re.findall(r"```bash\n(.*?)```", item, re.S)[0].splitlines()
                 if line.strip()]
    printf = re.search(r"\(`(printf [^`]+)`\)", " ".join(item.split())).group(1)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    resolver = tmp_path / "fake-resolver.py"
    stderr_text = {"resolver-fails": "error: Python 3.11+ is required (stdlib `tomllib` not found) $(touch pwned)",
                   "resolver-silent": ""}.get(case)
    if stderr_text is not None:
        written = f"{stderr_text}\n" if stderr_text else ""
        resolver.write_text(f"import sys\nsys.stderr.write({written!r})\nsys.exit(1)\n", encoding="utf-8")
        values = {"resolveCustomizationHelper": shlex.quote(resolver.as_posix()),
                  "skill-root": SETUP_DIR.as_posix(), "project-root": tmp_path.as_posix(), "run_dir": run_dir.as_posix()}
        shell = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], command).replace(
            "uv run ", shlex.quote(sys.executable) + " ", 1)
        ran = subprocess.run(["bash", "-c", shell], capture_output=True, timeout=20, cwd=tmp_path)
        assert ran.returncode == 1 and ran.stderr == b"", "the redirect sends the resolver's stderr to the file"
        expected = stderr_text or "(no error message)"
    else:
        fixed = "no JSON"
        shell = printf.replace("<the fixed reason>", fixed).replace("{run_dir}", run_dir.as_posix())
        assert subprocess.run(["bash", "-c", shell], timeout=20, cwd=tmp_path).returncode == 0
        expected = fixed
    done = subprocess.run(["bash", "-c", _contract_call("bad: key: here", run_dir)], capture_output=True,
                          timeout=20, cwd=tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    assert json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]["warnings"] == [
        f"customization_resolver_unavailable: {expected}"]
    assert not (tmp_path / "pwned").exists()


# Each step halt that quotes a failed command's stderr: its phase, and the file
# the emitter reads the diagnostic from. The run-folder halt, which pipes its
# stderr, is On Activation item 5b's (#1119).
STDERR_HALTS = {
    "step 1:detect-tools": ("detect-and-tier.md", "{run_dir}/detect-tools.err"),
    "step 2:write-tools": ("write-config.md", "{run_dir}/write-tools.err"),
    "step 2:forge-data-dir": ("write-config.md", "{run_dir}/forge-data-dir.err"),
}


def _joined(text: str) -> str:
    """`text` with its backslash line continuations joined."""
    return re.sub(r"\\\n\s*", "", text)


# The optional resolver option each fenced step halt carries (#595), naming item 6's file (#1119).
RESOLVER_GROUP = f"[{RESOLVER_FILE}]"


def _with_resolver(call: str, resolver: bool = False) -> str:
    """`call` with its resolver group left out, or kept, as a run whose item 6
    bound a reason keeps it."""
    assert call.endswith(" " + RESOLVER_GROUP), call
    base = call[:-len(RESOLVER_GROUP) - 1]
    return f"{base} {RESOLVER_FILE}" if resolver else base


def _blocked_calls(text: str) -> dict[str, str]:
    """The fenced emit-blocked calls of a step file, by the phase each passes."""
    calls = {}
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in _joined(block).splitlines():
            m = re.search(r'emit-blocked --phase "([^"]+)"', line)
            if m:
                calls[m.group(1)] = line.strip()
    return calls


def test_step_files_leave_the_reason_to_the_emitter():
    """determinism-3: a halt that quotes a helper's stderr passes that stderr to
    emit-blocked, which takes the message, folds it to one line and escapes it,
    so no step extracts or sanitizes a reason by hand."""
    for name in ("detect-and-tier.md", "ccc-index.md", "write-config.md", "auto-index.md"):
        text = _read(REFS / name)
        assert "sanitized per" not in text, name
        assert "replaced by a backtick" not in text and "parse the stderr JSON" not in text, name
    assert "as a backtick and each" not in _on_activation(_read(SKILL_MD))
    for phase, (name, source) in STDERR_HALTS.items():
        call = _blocked_calls(_read(REFS / name)).get(phase)
        assert call, (name, phase)
        call = _with_resolver(call)
        assert f'--stderr-from "{source}"' in call, call
        assert "<message>" in call, call
        # The helper's stderr goes to that file where it runs, and an
        # interactive run, which calls no emitter, reads it there.
        text = _joined(_read(REFS / name))
        assert f'2> "{source}"' in text, (name, source)
        halt = next(b for _, _, b in _prose_blocks(text) if f"`{phase}`" in b)
        assert re.search(r"\breads? that file\b", halt), (name, phase)
    [pipe] = [c for p, c in _blocked_calls(_activation_halts()).items() if p == "on-activation:run-folder"]
    assert pipe.endswith('--reason "Setup cannot proceed: the run folder could not be created: <message>" '
                         "--stderr-from -"), pipe


def _documented_blocked(name: str, phase: str, values: dict) -> list[str]:
    """The documented emit-blocked call of `phase`, filled in, as argv for this interpreter."""
    call = _with_resolver(_blocked_calls(_read(REFS / name))[phase]).split(" | ")[-1]
    words = shlex.split(re.sub(r"\{([\w-]+)\}", lambda m: values.get(m.group(1), m.group(0)), call))
    assert words[:3] == ["uv", "run", EMIT_HELPER.as_posix()], words
    return [sys.executable, *words[2:]]


@pytest.mark.parametrize("phase", ["step 1:detect-tools", "step 2:write-tools", "step 2:forge-data-dir"])
def test_a_documented_stderr_halt_emits_its_blocked_envelope(tmp_path, phase):
    """uv's own lines, then a JSON error holding quotes, a backslash and a newline:
    the envelope still arrives, its reason the message on one line."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    name, source = STDERR_HALTS[phase]
    (run_dir / source.split("/")[-1]).write_bytes(
        b'Installed 1 package in 3ms\n{"status": "error", "message": "cannot write \\"C:\\\\x\\":\\nPermission denied"}\n')
    values = {"emitEnvelopeHelper": EMIT_HELPER.as_posix(), "run_dir": run_dir.as_posix(),
              "project-root": tmp_path.as_posix(), "sidecar_path": tmp_path.as_posix(),
              "forge_data_folder": (tmp_path / "forge-data").as_posix()}
    done = subprocess.run(_documented_blocked(name, phase, values), capture_output=True, timeout=10)
    error = _blocked_error(done)
    assert error["phase"] == phase
    assert error["reason"].endswith('cannot write "C:\\x": Permission denied'), error["reason"]
    assert error["path"] != "<n/a>"


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("phase", sorted(STDERR_HALTS))
def test_a_documented_step_halt_carries_the_resolver_reason(tmp_path, phase):
    """Each fenced step halt, its resolver option kept, run by bash on a resolver.err
    holding shell characters: the envelope keeps the reason whole, and nothing runs."""
    name, source = STDERR_HALTS[phase]
    project = tmp_path / "project"
    project.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / source.split("/")[-1]).write_bytes(b"cannot write the file\n")
    reason = "exit 1: No module named 'tomllib' in \"$HOME\" $(touch pwned) `x` C:\\py"
    (run_dir / "resolver.err").write_bytes(reason.encode("utf-8") + b"\n")
    values = {"emitEnvelopeHelper": shlex.quote(EMIT_HELPER.as_posix()), "run_dir": run_dir.as_posix(),
              "project-root": project.as_posix(), "sidecar_path": project.as_posix(),
              "forge_data_folder": (project / "forge-data").as_posix()}
    call = _with_resolver(_blocked_calls(_read(REFS / name))[phase], resolver=True)
    command = re.sub(r"\{([\w-]+)\}", lambda m: values.get(m.group(1), m.group(0)), call)
    command = command.replace("uv run ", shlex.quote(sys.executable) + " ")
    done = subprocess.run(["bash", "-c", command], capture_output=True, timeout=20, cwd=tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["error"]["phase"] == phase
    assert envelope["warnings"] == [f"customization_resolver_unavailable: {reason}"]
    assert not (tmp_path / "pwned").exists()


# The staged payload file and the phase #1119 retired, written in two parts so that a
# grep of src/ and test/ for either finds no live use of it.
RETIRED_PAYLOAD = "report-context" + ".json"
RETIRED_PHASE = "step 1:" + "run-folder"


def _run_folder_item() -> str:
    """On Activation item 5b, which makes the run folder before item 6 saves the resolver's stderr in it."""
    text = _read(SKILL_MD)
    start = text.index("5b. **Create the run folder.**")
    return text[start:text.index("6. **Resolve workflow customization.**", start)]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_the_run_folder_halt_pipes_the_failed_command_to_the_emitter(tmp_path):
    """No run folder holds the stderr, so the documented pipe hands it over. It runs
    before item 6, so it passes no resolver option (#1119)."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "_bmad-output").write_bytes(b"a file where the folder goes\n")
    [pipe] = [c for p, c in _blocked_calls(_activation_halts()).items() if p == "on-activation:run-folder"]
    assert "resolver" not in pipe, pipe
    values = {"emitEnvelopeHelper": shlex.quote(EMIT_HELPER.as_posix()), "project-root": project.as_posix()}
    command = re.sub(r"\{([\w-]+)\}", lambda m: values.get(m.group(1), m.group(0)), pipe)
    command = command.replace("uv run ", shlex.quote(sys.executable) + " ")
    done = subprocess.run(["bash", "-c", command], capture_output=True, timeout=20)
    error = _blocked_error(done)
    assert error["phase"] == "on-activation:run-folder"
    assert error["path"] == f"{project.as_posix()}/_bmad-output/.skf-run"
    assert error["reason"].startswith("Setup cannot proceed: the run folder could not be created: mkdir")
    assert "\n" not in error["reason"]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_a_run_folder_repeat_that_succeeds_leaves_no_folder(tmp_path):
    """A failure that does not come back: the repeat removes the folder it made,
    and the reason says the stderr held nothing."""
    project = tmp_path / "project"
    project.mkdir()
    [pipe] = [c for p, c in _blocked_calls(_activation_halts()).items() if p == "on-activation:run-folder"]
    values = {"emitEnvelopeHelper": shlex.quote(EMIT_HELPER.as_posix()), "project-root": project.as_posix()}
    command = re.sub(r"\{([\w-]+)\}", lambda m: values.get(m.group(1), m.group(0)), pipe)
    command = command.replace("uv run ", shlex.quote(sys.executable) + " ")
    error = _blocked_error(subprocess.run(["bash", "-c", command], capture_output=True, timeout=20))
    assert error["reason"] == "Setup cannot proceed: the run folder could not be created: (no error message)"
    assert list((project / "_bmad-output" / ".skf-run").iterdir()) == []
    assert "a repeat that succeeds removes the folder it made" in _activation_halts()


def test_the_notices_say_a_tier_miss_builds_no_index():
    """A run that misses --require-tier defers the index build and skips the
    hygiene (#599), so neither notice may promise them."""
    notice = _section(_read(REFS / "detect-and-tier.md"), "### 3.")
    miss = next(b for _, _, b in _prose_blocks(notice) if "`{require_tier_satisfied}` is `false`" in b)
    assert miss.startswith("When `{require_tier_satisfied}` is `false`, end the one you display with:")
    assert "builds no ccc index and runs no registry hygiene" in miss


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


# The quiet run's last tool call (#1183): it prints the line section 4 saved, then removes it and the folder.
LAST_CALL = 'cat "{run_dir}/envelope.line" && rm -f "{run_dir}/envelope.line" && rmdir "{run_dir}"'
ENVELOPE_FILE = '> "{run_dir}/envelope.line"'


def test_report_holds_the_envelope_for_the_final_message():
    """`claude -p` prints only the final message, so section 4 saves the line in the run folder,
    displays nothing, and section 5 ends a quiet run with the call that prints it (#1183)."""
    report = _read(REFS / "report.md")
    emit = _section(report, "### 4.")
    assert "It writes the single prefixed line `SKF_SETUP_RESULT_JSON: {…}` to `{run_dir}/envelope.line`" in emit
    assert "this section displays nothing" in emit
    assert "run's final message" in emit and "verbatim" in emit
    assert "Display that stdout line" not in emit and "Bind `{setup_envelope_line}`" not in emit
    failure = next(b for _, _, b in _prose_blocks(emit) if "exits non-zero" in b)
    assert "`{run_dir}/envelope.line` is empty" in failure
    chain = _section(report, "### 5.")
    tier_miss = next(u for _, _, u in _prose_blocks(chain, items=True) if "`{require_tier_satisfied}` is `false`" in u)
    assert (f"When `{{quiet_mode}}` is true, end with one tool call, `{LAST_CALL}`, and display its output verbatim "
            "as the run's final message in a standalone run (nothing when it printed nothing)") in tier_miss
    # No file under src/ holds the line in the model's memory any more.
    holders = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*")
                     if p.is_file() and p.suffix in (".md", ".py", ".json", ".yaml", ".toml")
                     and "{setup_envelope_line}" in p.read_text(encoding="utf-8", errors="replace"))
    assert holders == []


def test_tier_miss_halt_emits_no_blocked_envelope():
    """The tier_failure envelope is that halt's one line; a second, blocked
    envelope would give a pipeline two conflicting statuses."""
    halt_contract = _halt_contract()
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
    description = json.loads(_read(SCHEMA))["description"]
    assert "displays when {quiet_mode} is true (--headless, -H, --quiet or a forger pipeline)" in description
    assert "{headless_mode}" not in description


# ---------------------------------------------------------------- shared health check


def test_only_setup_reads_quiet_mode():
    """#1183: a quiet run runs no health check, so the shared health check has no quiet branch,
    and no file outside skf-setup names `{quiet_mode}`."""
    readers = sorted(
        p.relative_to(SRC).as_posix() for p in SRC.rglob("*.md")
        if QUIET in _read(p) and SETUP_DIR not in p.parents
    )
    assert readers == []
    shared = _read(SHARED_HEALTH_CHECK)
    assert "Envelope-only runs" not in shared and "{setup_envelope_line}" not in shared
    assert "**Zero overhead for clean runs.** If nothing went wrong, say so and exit immediately." in shared
    gate = next(b for _, _, b in _prose_blocks(_section(shared, "### 0.")) if b.startswith("**GATE"))
    assert gate == ('**GATE [default: skip]**: if `{headless_mode}`, skip the display entirely, log: '
                    '"headless: skipped health-check arrival announcement".')
    clean = _section(shared, "### 2.")
    assert "\nDisplay:\n" in clean
    assert "After writing all files, display the block below." in _section(shared, "### 5c.")


def test_shared_health_check_gate_has_listed_headless_default_q():
    """Every workflow's headless run resolves the review gate to a listed option
    instead of waiting for input, and that option never submits anything."""
    section = _section(_read(SHARED_HEALTH_CHECK), "### 4.")
    assert "**GATE [default: Q]**" in section
    assert "- **[Q]** Queue locally — save every finding to {localFallbackFolder}/, submit nothing" in section
    assert '"headless: queued {N} finding(s) locally"' in section
    gate = next(b for _, _, b in _prose_blocks(section) if "**GATE [default: Q]**" in b)
    assert gate.startswith("**GATE [default: Q]**: if `{headless_mode}` is true, choose **[Q]**")
    assert QUIET not in gate and "Otherwise" not in gate
    assert ("skip the question below and go to Menu Handling: live submission always needs an interactive "
            "**[Y]**") in gate
    assert re.findall(r"\bchoose \*\*\[(\w)\]\*\*", gate) == ["Q"]
    handling = next(line for line in section.splitlines() if line.startswith("- **IF Q:**"))
    assert "§5a sub-step 1" in handling and "§5c" in handling
    local_queue = _section(_read(SHARED_HEALTH_CHECK), "### 5c.")
    assert "**\\[Q]**" in local_queue


def test_queue_fingerprint_has_a_portable_form():
    """[Q] is the default for every headless run with findings, so its
    fingerprint cannot depend on `sha1sum`, which stock macOS and Windows lack:
    the shared helper hashes it in Python (#1122)."""
    section = _section(_read(SHARED_HEALTH_CHECK), "### 5a.")
    assert "sha1sum" not in section and "shasum" not in section
    call = ('uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" '
            '--step-file "{step_file}" --section "{section-slug}" --defect-key "{defect-key}"')
    assert call in section.splitlines()
    helper = SRC / "shared" / "scripts" / "skf-health-check-seen.py"
    values = {"{severity}": "bug", "{workflow}": "skf-setup", "{step_file}": "references/report.md",
              "{section-slug}": "emit-headless-json-envelope", "{defect-key}": "result-envelope"}
    for placeholder, value in values.items():
        call = call.replace(placeholder, value)
    out = subprocess.run([sys.executable, str(helper), *shlex.split(call)[3:]], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    key = "bug|skf-setup|references/report.md|emit-headless-json-envelope|result-envelope"
    assert json.loads(out)["fp"] == "fp-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:7]


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
    parse = _parse_flags_item()
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
    chain = _section(_read(REFS / "report.md"), "### 5.")
    tier_miss = next(u for _, _, u in _prose_blocks(chain, items=True) if "`{require_tier_satisfied}` is `false`" in u)
    assert "control then returns to the forger" in tier_miss
    # #1183: a quiet success ends in section 5 too, so it hands control back there.
    success = next(u for _, _, u in _prose_blocks(chain, items=True) if "carry out that instruction now" in u)
    assert "when `{pipeline_mode}` is true, control then returns to the forger, which keeps chaining" in success


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
    assert "the emitter records the decision from the flags step 4 passes" in rule


def test_unprompted_orphan_removals_are_recorded_by_name():
    """The classifier's remove-orphans stages what it deleted, and the emitter
    folds the names into the audit trail: the step types no list (#592)."""
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    assert ('remove-orphans \\\n    --classification-from "{run_dir}/qmd-classify.json" \\\n'
            '    --project-root "{project-root}" \\\n    > "{run_dir}/qmd-remove.json"') in gate
    # #1119: the step types no decision; the emitter derives it from the flags step 4 passes.
    assert ("Record nothing yourself: step 4 passes the flags that decided it, and the emitter records the "
            "decision with its `source` (`orphan-action-flag`, `headless-default` or `quiet-default`), the count "
            "and, after a removal, the collections removed and not removed") in gate
    assert "{orphan_auto_resolution" not in _read(REFS / "auto-index.md")
    assert "Auto-decision (--orphan-action=remove): removed {removed, comma-separated}" in gate
    assert "qmd collection remove <name>" not in gate and "len(" not in gate
    doc = ast.get_docstring(ast.parse(_read(EMIT_HELPER)))
    assert '"removed": ["name", ...], "failed": ["name", ...]' in doc
    assert "`orphan_removed: <name>`, `orphan_remove_failed: <name>`" in doc


# ---------------------------------------------------------------- activation inputs fail closed


DETECT_HELPER = SRC / "shared" / "scripts" / "skf-detect-tools.py"


def _parse_flags_item() -> str:
    """On Activation item 1, its runner loop and binding paragraph included (to item 2)."""
    activation = _on_activation(_read(SKILL_MD))
    start = activation.index("1. **Parse invocation flags first**")
    return activation[start:activation.index("\n2. **Check for the config.**", start)]


ARGS_HELPER = SRC / "shared" / "scripts" / "skf-setup-args.py"


def _parsed_flags(arguments: str) -> dict:
    """The object skf-setup-args.py prints for `arguments`, as item 1 binds from it (#1183)."""
    done = subprocess.run([sys.executable, str(ARGS_HELPER)], input=arguments.encode("utf-8"),
                          capture_output=True, timeout=10)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout)


def test_require_tier_is_bound_raw_and_checked_by_the_detector():
    """A wrong-case tier used to become null, so the tier gate never ran. The helper keeps
    each value exactly as given (#1183)."""
    parse = _parse_flags_item()
    assert ("Bind `{headless_mode}`, `{quiet_mode}`, `{require_tier}`, `{orphan_action}` and `{ccc_skip_index}` "
            "from the object it prints (`headless`, `quiet`, `require_tier`, `orphan_action`, "
            "`ccc_skip_index`)") in parse
    assert "unparseable" not in parse and "raw value exactly as given" not in parse
    assert _parsed_flags("--require-tier=deep")["require_tier"] == "deep"
    assert _parsed_flags("--require-tier deep")["require_tier"] == "deep"
    # Another flag after it is no value: the run stays quiet, and the detector rejects "".
    assert _parsed_flags("--require-tier --headless") == {
        "headless": True, "quiet": True, "require_tier": "", "orphan_action": None, "ccc_skip_index": False}
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
    """The flag is the consent to delete collections: a value setup cannot read halts. The helper
    checks it and writes the reason, which goes on stdin, quotes and all (#1183)."""
    parse = _parse_flags_item()
    m = re.search(r"halt with phase `on-activation:orphan-action-invalid`, no `path`, and reason `([^`]+)`", parse)
    assert m, "orphan-action halt not found"
    assert m.group(1) == "<message>"
    assert "its `reason` passed as the halt contract says" in parse
    parsed = _parsed_flags("--quiet --orphan-action 'Remove'")
    assert parsed["phase"] == "on-activation:orphan-action-invalid"
    error = _blocked_error(_stdin_blocked(parsed["phase"], m.group(1), parsed["reason"]))
    assert error["reason"] == ("Setup cannot proceed: --orphan-action takes keep or remove, not 'Remove'. "
                               "Re-run with --orphan-action=keep or --orphan-action=remove.")
    assert "phase" not in _parsed_flags("--orphan-action=remove")
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    assert "`{orphan_action}` is non-null (activation lets through only `keep` or `remove`)" in gate
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    failure = next(line for line in contract.splitlines() if line.startswith("| **Failure modes**"))
    assert "an `--orphan-action` other than `keep` or `remove`" in failure


def test_quiet_is_an_alias_of_headless_and_a_pipeline_implies_it():
    parse = _parse_flags_item()
    assert "set both modes true when `{pipeline_mode}` is true" in parse
    assert ("When no runner prints an object, `{quiet_mode}` is true when the arguments hold `--headless`, `-H` "
            "or `--quiet`, or `{pipeline_mode}` is true.") in parse
    for arguments in ("--headless", "-H", "--quiet"):
        assert _parsed_flags(arguments)["quiet"] is True, arguments
    assert _parsed_flags("--quiet")["headless"] is False
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    flags = next(line for line in contract.splitlines() if line.startswith("| **Flags**"))
    assert "`--quiet` (an alias of `--headless`" in flags
    # One non-interactive case, and a --quiet run keeps labelling its orphan default quiet-default.
    gate = _section(_read(REFS / "auto-index.md"), "### 3.")
    # #1183: the preference sets {headless_mode} alone, so the case names both modes.
    assert ('- `{headless_mode}` or `{quiet_mode}` is true → the default **Keep**, with `source: "headless-default"` '
            'when `{headless_mode}` is true and `source: "quiet-default"` otherwise (a `--quiet` run)') in gate
    assert "- `{headless_mode}` is true →" not in gate
    assert ('display `"Auto-decision (<cause>): kept {count} orphaned forge collection(s)"`, where `<cause>` is '
            '`--orphan-action=keep` for the flag and `headless_mode: true` for the default') in gate
    assert ("**GATE [default: K]**: reached only when none of the cases above applies, so `{orphan_action}` is null "
            "and `{headless_mode}` and `{quiet_mode}` are false.") in gate


SETUP_FILES = [SKILL_MD, *sorted(REFS.glob("*.md"))]


@pytest.mark.parametrize("path", SETUP_FILES, ids=lambda p: p.name)
def test_every_setup_guard_reads_quiet_mode_alone(path):
    """--quiet is an alias of --headless, so setup has one envelope-only mode
    and one switch for it: a display guard that tests both variables could
    drift into testing one of them and leak text into the envelope-only
    output. `headless_mode: true` in preferences.yaml sets `{headless_mode}`
    alone (#1183), so only the gate that it resolves reads both."""
    text = _read(path)
    # {headless_mode} is only bound (item 1), folded with preferences.yaml (item 5), resolves the step 3
    # orphan gate (its case and its GATE line), and step 4 passes --headless so the emitter names that
    # default (#1119).
    allowed = {"SKILL.md": ("Bind `{headless_mode}`, `{quiet_mode}`", "5. **Reconcile `{headless_mode}`**"),
               "auto-index.md": ("- `{headless_mode}` or `{quiet_mode}` is true → the default **Keep**",
                                 "**GATE [default: K]**: reached only when"),
               "report.md": ("- `--orphan-action {orphan_action}` when",)}.get(path.name, ())
    readers = [line.strip() for line in text.splitlines() if "{headless_mode}" in line]
    assert [line[:60] for line in readers if not line.startswith(allowed)] == []
    gate_lines = [line for line in readers if line.startswith(allowed[:2] if path.name == "auto-index.md" else ())]
    for doubled in ("`{headless_mode}` or `{quiet_mode}`", "`{headless_mode}` and `{quiet_mode}`",
                    "`{quiet_mode}` or `{headless_mode}`"):
        assert sum(line.count(doubled) for line in gate_lines) == text.count(doubled), doubled
    # Every display guard reads {quiet_mode}, never {headless_mode}, except the gate's own question.
    body = _split_frontmatter(text)[1] if text.startswith("---\n") else text
    for _, heading, block in _prose_blocks(body, items=True):
        if DISPLAY_RE.search(block) and QUIET in block + heading and not block.startswith("**GATE"):
            assert "{headless_mode}" not in block, block[:100]


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


# Every file a setup step writes into the run folder, by redirect (a helper's
# stdout, or its stderr for a halt to quote) or --result-to.
RUN_DIR_WRITE_RE = re.compile(r'(?:>|--result-to) "\{run_dir\}/([a-z-]+\.(?:json|err))"')
# Section 5's delete: the saved files by name, then the folder only if it is empty, a bracket a quiet
# run drops, since its envelope.line stays for the last call (#1183).
RUN_DIR_DELETE_RE = re.compile(r'^rm -f ((?:"\{run_dir\}/[a-z-]+\.(?:json|err)" )+)\[&& rmdir "\{run_dir\}"\]$',
                               re.M)


def test_run_folder_is_made_at_activation_and_removed_in_step_4():
    """#1119: item 5b makes the folder before item 6 saves the resolver's stderr in it."""
    item = _run_folder_item()
    assert 'mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX"' in item
    assert "Bind `{run_dir}` ← the path it prints" in item
    assert "halt with phase `on-activation:run-folder`." in item and "emit-blocked" not in item
    halts = _activation_halts()
    assert "`on-activation:run-folder` (item 5b): `path` `{project-root}/_bmad-output/.skf-run`" in halts
    assert "Item 3 proved `uv` and item 4 bound the helper, so this halt runs its own pipe, not the loop" in halts
    activation = _on_activation(_read(SKILL_MD))
    assert activation.index("5. **Reconcile") < activation.index("5b. **Create the run folder.**") < \
        activation.index("6. **Resolve workflow customization.**")
    detect = _section(_read(REFS / "detect-and-tier.md"), "### 1.")
    assert "mktemp" not in detect and "run-folder" not in detect
    assert "Run the detector into `{run_dir}`, the run folder SKILL.md On Activation item 5b made:" in detect
    for path in [SKILL_MD, *sorted(REFS.glob("*.md")), *sorted((SRC / "shared").rglob("*"))]:
        if path.is_file() and path.suffix in (".md", ".py", ".json"):
            assert RETIRED_PHASE not in _read(path), path.name
    report = _read(REFS / "report.md")
    chain = _section(report, "### 5.")
    delete = RUN_DIR_DELETE_RE.search(chain)
    assert delete, "section 5 does not delete the run folder file by file"
    written = {name for path in (SKILL_MD, *(REFS / step for step in STEP_FILES))
               for name in RUN_DIR_WRITE_RE.findall(_read(path))}
    assert set(re.findall(r'"\{run_dir\}/([a-z-]+\.(?:json|err))"', delete.group(1))) == written
    assert {"detect-tools.err", "write-tools.err", "forge-data-dir.err", "resolver.err"} <= written
    assert RETIRED_PAYLOAD not in written
    # A recursive delete of a mis-bound {run_dir} could take every run's folder with it.
    assert "rm -r" not in report
    # Deleted before the tier-miss line shows, so that line stays the final message.
    assert delete.start() < chain.index("`{require_tier_satisfied}` is `false`")
    assert "envelope.line" not in delete.group(0)
    assert ("Keep the bracket only when `{quiet_mode}` is false: a quiet run still holds "
            "`{run_dir}/envelope.line`") in chain
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    outputs = next(line for line in contract.splitlines() if line.startswith("| **Outputs**"))
    assert "`{project-root}/_bmad-output/.skf-run/`" in outputs
    assert "a halt that names a phase leaves it in place" in outputs


def _section_5_bullets() -> tuple[str, str]:
    """Section 5's tier-miss bullet and its success bullet."""
    units = [u for _, _, u in _prose_blocks(_section(_read(REFS / "report.md"), "### 5."), items=True)]
    tier_miss = next(u for u in units if "`{require_tier_satisfied}` is `false`" in u)
    success = next(u for u in units if "carry out that instruction now" in u)
    return tier_miss, success


def test_a_quiet_run_ends_in_section_5_without_the_health_check():
    """#1183: a quiet success runs its hook, then the call that prints the saved line, and
    stops there: the shared health check, which had to hide everything and retype the line,
    never loads. An interactive success still chains to it."""
    report = _read(REFS / "report.md")
    assert "### 5. Delete the Run Folder and Finish\n" in report and "Chain to Health Check" not in report
    tier_miss, success = _section_5_bullets()
    for bullet in (tier_miss, success):
        assert bullet.count(f"end with one tool call, `{LAST_CALL}`") == 1, bullet[:80]
        assert "display its output verbatim as the run's final message in a standalone run" in bullet
    hook = success.index("{onCompleteCommand}")
    last = success.index(LAST_CALL)
    stop = success.index("A quiet run stops there, without loading `{nextStepFile}`: it runs no health check.")
    chain = success.index("When `{quiet_mode}` is false, load `{nextStepFile}`, read it fully, and execute it.")
    assert hook < last < stop < chain
    assert success[:last].rindex("When `{quiet_mode}` is true") > hook
    assert "{nextStepFile}" not in tier_miss.replace("without chaining to step 5", "")
    closing = next(b for _, _, b in _prose_blocks(_section(report, "### 5.")) if "true terminal step" in b)
    assert closing.startswith("On a success where `{quiet_mode}` is false, the health-check step is the true "
                              "terminal step:")
    assert "\u2014" not in closing


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("quiet,line", [
    (True, ENVELOPE_PREFIX + '{"skf_setup":{"status":"success","tier":"Forge"}}'),
    (True, ""),
    (False, None),
], ids=["quiet", "quiet-emit-failed", "interactive"])
def test_section_5_keeps_the_line_until_the_last_call_prints_it(tmp_path, quiet, line):
    """#1183: section 5's delete, run by bash, leaves `envelope.line` and the folder of a quiet run,
    and the last call then prints the line (nothing when the emit failed) and leaves no folder.
    An interactive run, which saves no line, deletes the folder at once."""
    run_dir = tmp_path / "a project" / "_bmad-output" / ".skf-run" / "skf-setup-abcd1234"
    run_dir.mkdir(parents=True)
    delete = RUN_DIR_DELETE_RE.search(_section(_read(REFS / "report.md"), "### 5.")).group(0)
    for name in re.findall(r'"\{run_dir\}/([a-z-]+\.(?:json|err))"', delete):
        (run_dir / name).write_bytes(b"{}\n")
    if line is not None:
        (run_dir / "envelope.line").write_bytes((line + "\n").encode("utf-8") if line else b"")
    command = delete.replace(' [&& rmdir "{run_dir}"]', "" if quiet else ' && rmdir "{run_dir}"')
    command = command.replace("{run_dir}", run_dir.as_posix())
    done = subprocess.run(["bash", "-c", command], capture_output=True, timeout=20)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    if not quiet:
        assert not run_dir.exists()
        return
    assert [p.name for p in run_dir.iterdir()] == ["envelope.line"]
    last = subprocess.run(["bash", "-c", LAST_CALL.replace("{run_dir}", run_dir.as_posix())],
                          capture_output=True, timeout=20)
    assert last.returncode == 0, last.stderr.decode("utf-8", "replace")
    assert last.stdout.decode("utf-8").splitlines() == ([line] if line else [])
    assert last.stderr == b""
    assert not run_dir.exists() and run_dir.parent.exists()


STAGED_RE = re.compile(r'(?:> "\{run_dir\}/([a-z-]+\.json)"(?: 2> "\{run_dir\}/[a-z-]+\.err")? '
                       r'&& cat "\{run_dir\}/\1"|--result-to "\{run_dir\}/([a-z-]+\.json)")')


def test_every_staged_helper_output_is_one_the_emitter_reads():
    staged = {a or b for step in STEP_FILES for a, b in STAGED_RE.findall(_read(REFS / step))}
    declared = set(re.findall(r'^STAGED_[A-Z_]+ = "([a-z-]+\.json)"$', _read(EMIT_HELPER), re.MULTILINE))
    assert staged == declared == {"detect-tools.json", "ccc-exclusions.json", "qmd-classify.json",
                                  "qmd-remove.json", "clean-stale.json"}


# The options report.md section 1 names, which both report calls end with (#1119), and the
# empty stdin after them, so a call never reads or waits on one the host left open (round 1).
REPORT_GROUP = f"[--orphan-action {{orphan_action}}] [--headless] [--quiet] {RESOLVER_GROUP}"
NO_STDIN = " < /dev/null"
# Section 4 saves the envelope line in the run folder for section 5's last call (#1183).
EMIT_SUFFIX = NO_STDIN + " " + ENVELOPE_FILE


def test_report_passes_options_and_no_payload_to_the_banner_and_the_envelope():
    """#1119: the orphan decision and the resolver reason go to the emitter as
    options, so step 4 types no payload and escapes nothing."""
    report = _read(REFS / "report.md")
    staged = _section(report, "### 1.")
    for stale in (RETIRED_PAYLOAD, "<<'SKF_JSON'", "{orphan_auto_resolution", "Stage the"):
        assert stale not in report, stale
    assert (f"No step types a payload: both calls end with the same option group, `{REPORT_GROUP}`, each "
            "bracket kept only when its value holds, and then with `< /dev/null`, which the emitter reads as "
            "the empty payload `{}`, so neither call reads or waits on a stdin the host left open (section 4 "
            "then saves its stdout in `{run_dir}/envelope.line`):") in staged
    assert ("`--orphan-action {orphan_action}` when `{orphan_action}` is non-null, `--headless` when "
            "`{headless_mode}` is true, and `--quiet` when `{quiet_mode}` is true") in staged
    doc = ast.get_docstring(ast.parse(_read(EMIT_HELPER)))
    for option in ("--orphan-action", "--headless", "--quiet", "--customization-resolver-unavailable-from"):
        assert option in doc, option
    # The folders On Activation bound from preflight: the emitter reads no config.yaml.
    paths = '--project-root "{project-root}" --sidecar-path "{sidecar_path}" --forge-data-folder "{forge_data_folder}"'
    banner = _joined(_section(report, "### 2."))
    assert (f'render-report --run-dir "{{run_dir}}" {paths} --tier-rules "{{skill-root}}/references/tier-rules.md" '
            f"{REPORT_GROUP}{NO_STDIN}\n") in banner
    assert (REFS / "tier-rules.md").is_file()
    # The script owns the banner's lines: no template of them is left to drift from it.
    assert "kept for reference only" not in report and "{if " not in report
    emit = _joined(_section(report, "### 4."))
    assert f'emit --run-dir "{{run_dir}}" {paths} {REPORT_GROUP}{EMIT_SUFFIX}\n' in emit
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


def test_report_types_no_path_and_repairs_no_payload():
    """determinism-2: the emitter derives the run's paths, so the step types none,
    escapes none and never rewrites a payload the emitter refused."""
    report = _read(REFS / "report.md")
    staged = _section(report, "### 1.")
    assert "Write each path" not in report and "{sidecar_path}/forge-tier.yaml" not in staged
    assert (f"`{RESOLVER_FILE}` when SKILL.md On Activation item 6 bound `{{customization_resolver_unavailable}}` "
            "to a reason: the emitter reads the reason from that file, folds it to one line and escapes it") in staged
    assert "escaped" not in staged and "JSON string" not in staged
    for prefix in ("### 2.", "### 4."):
        assert "report-context" not in _section(report, prefix), prefix
        assert "run it again" not in _section(report, prefix), prefix
    emit_failure = next(b for _, _, b in _prose_blocks(_section(report, "### 4.")) if "exits non-zero" in b)
    assert "failed schema validation" not in emit_failure


def _report_option_group(call: str, orphan_action: str | None, headless: bool, quiet: bool,
                         resolver: bool) -> str:
    """A report call's option group as section 1 keeps it: each bracket only when its value holds,
    then the empty stdin, and for the emit the file section 5 reads the line from (#1183)."""
    suffix = EMIT_SUFFIX if call.endswith(EMIT_SUFFIX) else NO_STDIN
    assert call.endswith(f" {REPORT_GROUP}{suffix}"), call
    kept = [f"--orphan-action {orphan_action}"] if orphan_action else []
    kept += ["--headless"] * headless + ["--quiet"] * quiet + [RESOLVER_FILE] * resolver
    return " ".join([call[:-len(REPORT_GROUP + suffix) - 1], *kept]) + suffix


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("orphan_action,headless,quiet,decision", [
    (None, True, True, "keep 2 orphaned collection(s) (non-interactive, headless-default)"),
    (None, False, True, "keep 2 orphaned collection(s) (non-interactive, quiet-default)"),
    # #1183: `headless_mode: true` in preferences.yaml alone: the banner renders, the default is headless's.
    (None, True, False, "keep 2 orphaned collection(s) (non-interactive, headless-default)"),
    ("remove", False, False, "remove 2 orphaned collection(s) (non-interactive, orphan-action-flag)"),
    (None, False, False, None),
], ids=["headless", "quiet", "preference", "orphan-action-remove", "interactive"])
def test_both_report_calls_run_as_documented_with_no_payload(tmp_path, orphan_action, headless, quiet, decision):
    """#1119: the documented calls, run by bash on a stdin the host left open, which they
    never wait on (round 1): the paths come from the folders activation bound, the orphan
    decision from the flags and the staged classification, and the resolver reason from
    item 6's file, shell characters and all. The emit writes its line to the run folder,
    and prints nothing (#1183)."""
    project = tmp_path / "project"
    (project / "_bmad" / "skf").mkdir(parents=True)
    (project / "_bmad" / "skf" / "config.yaml").write_bytes(
        b"# SKF Configuration\nforge_data_folder: '{project-root}/forge-data'\n"
        b"sidecar_path: _bmad/_memory/forger-sidecar\nides:\n  - claude-code\n")
    run_dir = project / "_bmad-output" / ".skf-run" / "skf-setup-abcd1234"
    run_dir.mkdir(parents=True)
    # What SKILL.md On Activation binds from skf-preflight.py's config.
    preflight = subprocess.run([sys.executable, str(PREFLIGHT), str(project), "--allow-missing-sidecar"],
                               capture_output=True, timeout=60)
    assert preflight.returncode == 0, preflight.stderr.decode("utf-8", "replace")
    bound = json.loads(preflight.stdout)["config"]
    detect = {"tools": {"ast_grep": {"available": True, "version": "ast-grep 0.45.3"}},
              "tier": {"calculated": "Forge"}, "prior": {"previous_tier": "Forge"}, "require_tier": {}}
    (run_dir / "detect-tools.json").write_bytes(json.dumps(detect).encode("utf-8"))
    (run_dir / "qmd-classify.json").write_bytes(json.dumps(
        {"status": "ok", "healthy": [], "orphaned": ["a-docs", "b-brief"]}).encode("utf-8"))
    if orphan_action == "remove":
        (run_dir / "qmd-remove.json").write_bytes(json.dumps(
            {"status": "ok", "removed": ["a-docs", "b-brief"], "failed": [], "errors": {}}).encode("utf-8"))
    (run_dir / "resolver.err").write_bytes(RESOLVER_ERR)
    root = project.resolve().as_posix()
    values = {"emitEnvelopeHelper": shlex.quote(EMIT_HELPER.as_posix()), "run_dir": run_dir.as_posix(),
              "project-root": project.as_posix(), "skill-root": SETUP_DIR.as_posix(),
              "sidecar_path": bound["sidecar_path_resolved"], "forge_data_folder": bound["forge_data_folder_resolved"],
              "orphan_action": orphan_action or ""}
    report = _read(REFS / "report.md")
    outputs = {}
    for prefix, word in (("### 2.", "render-report"), ("### 4.", "emit")):
        [call] = [line for block in re.findall(r"```bash\n(.*?)```", _section(report, prefix), re.S)
                  for line in _joined(block).splitlines() if f" {word} " in line]
        command = _report_option_group(call, orphan_action, headless, quiet, resolver=True)
        command = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], command)
        command = command.replace("uv run ", shlex.quote(sys.executable) + " ", 1)
        # A pipe whose write end this test holds open: a call that read it would block until killed.
        host_stdin, held_open = os.pipe()
        try:
            done = subprocess.run(["bash", "-c", command], stdin=host_stdin, capture_output=True, timeout=20,
                                  cwd=tmp_path)
        finally:
            os.close(host_stdin)
            os.close(held_open)
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        outputs[word] = done.stdout.decode("utf-8")
    assert outputs["emit"] == ""
    [line] = (run_dir / "envelope.line").read_bytes().decode("utf-8").splitlines()
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["config_path"] == f"{root}/_bmad/_memory/forger-sidecar/forge-tier.yaml"
    assert envelope["warnings"][0] == f"customization_resolver_unavailable: {RESOLVER_REASON}"
    trail = [w for w in envelope["warnings"] if w.startswith("orphan_")]
    if decision is None:
        assert trail == [], "a gate the user answered records no decision"
    else:
        removed = ["orphan_removed: a-docs", "orphan_removed: b-brief"] if orphan_action == "remove" else []
        assert trail == [f"orphan_auto_resolution: {decision}", *removed]
    assert not (tmp_path / "pwned").exists()
    banner = outputs["render-report"].splitlines()
    assert banner and not banner[0].startswith(ENVELOPE_PREFIX)
    assert f"  - forge-tier.yaml: {root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" in banner
    assert f"  - {root}/forge-data/ (directory ensured)" in banner


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


PREFERENCE_ONLY_GATES = ("`headless_mode: true` in `{sidecar_path}/preferences.yaml` only resolves the gates: "
                         "that run keeps its FORGE STATUS banner, notices and health check.")


def test_convention_names_every_switch_that_makes_setup_envelope_only():
    """The convention's skf-setup exception names each switch the contract's
    Headless row names, the flag and its alias, and both say the preference
    only resolves the gates (#1183)."""
    exception = next(paragraph for paragraph in _read(HEADLESS_CONVENTION).split("\n\n")
                     if paragraph.startswith("Exception: skf-setup"))
    headless = next(line for line in _section(_read(INVOCATION_CONTRACT), "## Invocation Contract").splitlines()
                    if line.startswith("| **Headless**"))
    for text in (exception, headless):
        for switch in ("`--headless`", "`--quiet`", PREFERENCE_ONLY_GATES, "runs no health check"):
            assert switch in text, switch
        for gone in ("the health check still runs", "displayed once the health check has finished",
                     "known once activation", "adds nothing of its own"):
            assert gone not in text, gone
    assert "Under `--headless` or `--quiet`, a standalone run's final message" in headless
    assert "final message of a standalone `--headless` or `--quiet` run" in exception


def test_workflows_doc_promises_only_the_final_message():
    doc = _read(WORKFLOWS_DOC)
    for overclaim in ("only line the agent displays", "the only line the run displays",
                      "SUPPRESSES all other output", "no progress messages"):
        assert overclaim not in doc, overclaim
    exception = next(line for line in doc.splitlines()
                     if line.startswith("**Exception: `/skf-setup` headless"))
    assert "this line is the run's final message, so it is exactly what `claude -p` prints" in exception


def test_workflows_doc_places_the_health_check_by_outcome():
    """#1183: a `--headless`, `-H` or `--quiet` run runs no health check, whatever its outcome, and
    the preference alone keeps the banner and the health check."""
    doc = _read(WORKFLOWS_DOC)
    exception = next(line for line in doc.splitlines() if line.startswith("**Exception: `/skf-setup` headless"))
    assert "after the health check has run, so" not in exception
    assert "On success the health check runs first" not in exception
    assert "`/skf-setup` with `--headless`, `-H` or `--quiet` skips its status banner" in exception
    assert ('Such a run runs no health check: the `status: "success"` or `status: "tier_failure"` envelope, or a '
            '`status: "blocked"` envelope') in exception
    preference = next(line for line in doc.splitlines() if line.startswith("You can also set `headless_mode: true`"))
    assert ("For `/skf-setup` the preference only answers the orphan question: setup keeps its banner and health "
            "check, so a script that reads its envelope line passes `--headless` or `--quiet`.") in preference
    health = next(line for line in doc.splitlines() if line.startswith("In headless mode the review gate takes"))
    assert "A `/skf-setup --headless` or `--quiet` run runs no health check" in health


def test_docs_state_when_no_envelope_arrives():
    """With SKF's scripts absent there is no helper to build an envelope, so
    the one line is the bare reason; pipelines must treat that as a failure."""
    exception = next(line for line in _read(WORKFLOWS_DOC).splitlines()
                     if line.startswith("**Exception: `/skf-setup` headless"))
    assert "SKF's scripts are not installed in the project" in exception
    assert "the run's one line is the bare halt reason" in exception
    assert "Pipelines should treat a missing envelope as a failure" in exception
    entry = _section(_read(TROUBLESHOOTING), '### "Setup cannot proceed: the SKF config file was not found"')
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
    """A halt that names a phase never reaches step 4, so its error is null: step 4 passes none."""
    report = _read(REFS / "report.md")
    staged = _section(report, "### 1.")
    assert '"error"' not in staged
    assert "`error` stays `null`: a halt that names a phase never reaches this step" in staged
    assert "{error_object_or_null}" not in report
    assert "set `{error:" not in _read(REFS / "write-config.md")


# ---------------------------------------------------------------- contract lift, sidecar path, helper staging


def test_skill_md_lifts_its_invocation_contract():
    """#600: the headless-only contract lives behind a one-line pointer
    (test_stage_files_stay_under_their_budgets holds SKILL.md's budget)."""
    skill = _read(SKILL_MD)
    pointer = _section(skill, "## Invocation Contract")
    assert "`references/invocation-contract.md`" in pointer and "| **" not in pointer
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    rows = re.findall(r"^\| \*\*([A-Za-z ]+)\*\* \|", contract, re.MULTILINE)
    assert rows == ["Inputs", "Flags", "Gates", "Outputs", "Headless", "Failure modes"]
    headless = next(line for line in contract.splitlines() if line.startswith("| **Headless**"))
    assert "Schema: `shared/scripts/schemas/skf-setup-result-envelope.v1.json`" in headless
    assert "report.md` §4" not in contract
    convention = _read(HEADLESS_CONVENTION)
    assert "skf-setup's `references/invocation-contract.md` states this" in convention
    assert "Its SKILL.md Invocation Contract" not in convention


# On Activation's one sentence for the halt contract (#1184).
HALT_POINTER = "On any halt that names a phase, load `references/halt-contract.md` and follow it."


def test_stage_files_stay_under_their_budgets():
    """#1184: the halt contract, which only a halt reads, has its own file with each On Activation halt's path
    and reason, so SKILL.md stays under BMad's 2,500 tokens and the single-purpose reference under 9,000, on
    the chars/4 fallback (len // 4, the SKF convention)."""
    for path, budget in ((SKILL_MD, 2500), (HALT_CONTRACT, 9000)):
        assert len(_read(path)) // 4 < budget, (path.name, len(_read(path)) // 4)


def test_every_activation_halt_has_its_path_and_reason_in_the_halt_contract():
    """#1184: On Activation names each halt by its phase alone, and the halt contract it loads on a halt lists
    that phase's path and reason, except item 1's, whose reason is the parser's own."""
    named = re.findall(r"halt with phase `(on-activation:[a-z-]+)`(?: for (the parser|preflight|the helpers))?",
                       _on_activation(_read(SKILL_MD)))
    listed = re.findall(r"^- `(on-activation:[a-z-]+)`(?: for (the parser|preflight|the helpers))? \(item \d+b?[,)]",
                        _activation_halts(), re.M)
    assert len(listed) == len(set(listed)) == 7, listed
    assert sorted(set(named) - {("on-activation:orphan-action-invalid", "")}) == sorted(listed)
    for line in _activation_halts().splitlines():
        if line.startswith("- `on-activation:"):
            assert "`path` `{project-root}/" in line or "no `path`" in line, line
            assert "reason `Setup cannot proceed: " in line, line


def test_on_activation_loads_the_halt_contract_only_on_a_halt():
    """#1184: On Activation keeps one sentence that loads references/halt-contract.md, ahead of item 1, and no
    copy of the contract or its runner loop; Conventions names the file, and no Setup file points at a halt
    contract in SKILL.md any more."""
    activation = _on_activation(_read(SKILL_MD))
    assert activation.count(HALT_POINTER) == 1
    assert activation.index(HALT_POINTER) < activation.index("1. **Parse invocation flags first**")
    assert "SKF_TEXT" not in activation and "Halt contract" not in activation
    assert "follows this contract" not in activation
    conventions = _section(_read(SKILL_MD), "## Conventions")
    assert ("the invocation contract, `halt-contract.md`, which a halt that names a phase loads, and "
            "`tier-rules.md`") in conventions
    assert _read(HALT_CONTRACT).startswith("# Halt Contract\n\n")
    for path in [SKILL_MD, *sorted(REFS.glob("*.md"))]:
        assert "SKILL.md halt contract" not in _read(path), path.name
    assert "display that reason alone as the run's one line (`references/halt-contract.md`)" in \
        _read(REFS / "report.md")


def test_each_rule_is_stated_once():
    """#1184: step 3 resolves its orphan gate from its own section 3, so Workflow Rules no longer restates it,
    and report.md and write-config.md drop the rules their own sections state."""
    rules = _section(_read(SKILL_MD), "## Workflow Rules")
    assert "orphan-removal gate" not in rules and "{orphan_action}" not in rules
    report = _read(REFS / "report.md")
    for gone in ("Focus only on display + envelope emission", "Chains to the local health-check step",
                 "LLM schema drift", "Step 5 in turn delegates to `shared/health-check.md`"):
        assert gone not in report, gone
    frontmatter, _ = _split_frontmatter(report)
    assert frontmatter.splitlines()[1:3] == [
        "# `{emitEnvelopeHelper}` = first existing path in `{emitEnvelopeProbeOrder}`;",
        "# halt if neither exists when section 4 emits the envelope."]
    assert "control then returns to the forger" not in _section(report, "### 4.")
    assert "File write failures are errors" not in _read(REFS / "write-config.md")


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
    assert ("the QMD sections (2 and 3) run only when `{calculated_tier}` is Deep, and section 4 runs "
            "when `{calculated_tier}` is Deep or `{ccc}` is true") in first


def test_a_tier_miss_skips_the_due_index_build_and_the_hygiene():
    """enhancement-2: a run that ends tier_failure builds no index that is due and
    removes no QMD collection, and the Failure modes row says so once."""
    ccc = _read(REFS / "ccc-index.md")
    assert "add `--defer-index` only when `{require_tier_satisfied}` (from step 1) is `false`" in ccc
    [call] = [b for b in re.findall(r"```bash\n(.*?)```", ccc, re.S) if "{mergeCccExclusionsHelper}" in b]
    assert "[--defer-index]" in call and "--skip-index \"{ccc_skip_index}\"" in call
    first = _section(_read(REFS / "auto-index.md"), "### 1.")
    skip = "When `{require_tier_satisfied}` (from step 1) is `false`, go to section 5 with no output"
    assert skip in first
    # The skip comes before every route into a hygiene section.
    assert first.index(skip) < first.index("Go to section 2 at Deep tier")
    assert "orphan_auto_resolution" not in first, "the emitter, not step 3, records the orphan decision"
    contract = _section(_read(INVOCATION_CONTRACT), "## Invocation Contract")
    failure = next(line for line in contract.splitlines() if line.startswith("| **Failure modes**"))
    assert ("Such a run fails fast: it builds no ccc index that is due (`ccc_index.status` `\"skipped\"`, "
            "while a fresh index record still carries forward) and runs no registry hygiene") in failure
    assert "even under `--orphan-action=remove`" in failure and "it still writes `forge-tier.yaml`" in failure
    # Step 2 still records the detected tier: write-config.md runs whatever the miss.
    assert "require_tier" not in _read(REFS / "write-config.md")


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


def _item_4() -> str:
    return _section(_on_activation(_read(SKILL_MD)), "4. **Load config and preferences.**")


def test_item_4_resolves_every_helper_the_step_files_run(tmp_path):
    """#1117: item 4's one preflight call, run as written against this repository,
    binds every `{...Helper}` the step files and item 6 run, none of them null."""
    item = _item_4()
    [call] = re.findall(r'Run `(uv run "<preflight>" [^`]+)`', item)
    assert call == 'uv run "<preflight>" "{project-root}" --allow-missing-sidecar --helpers "{skill-root}"'
    argv = shlex.split(call.replace('uv run "<preflight>"', "").replace("{project-root}", REPO_ROOT.as_posix())
                       .replace("{skill-root}", SETUP_DIR.as_posix()))
    config = tmp_path / "config.yaml"
    config.write_text(f"sidecar_path: {(tmp_path / 'sidecar').as_posix()}\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(PREFLIGHT), *argv, "--config-path", str(config)],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stdout + done.stderr
    helpers = json.loads(done.stdout)["helpers"]
    ok = next(line for line in item.splitlines() if "`status` `ok`" in line)
    bind = ok[ok.index("Bind `{detectToolsHelper}`"):]
    bound = re.findall(r"`\{([A-Za-z]+)Helper\}`", bind[:bind.index("from `helpers.<stem>`")])
    used = set()
    for name in STEP_FILES:
        used |= set(re.findall(r"\{([A-Za-z]+)Helper\}", _read(REFS / name)))
    used |= set(re.findall(r"\{([A-Za-z]+)Helper\}", _section(_on_activation(_read(SKILL_MD)),
                                                               "6. **Resolve workflow customization.**")))
    assert sorted(bound) == sorted(used) == sorted(helpers)
    for stem in bound:
        assert helpers[stem] and pathlib.Path(helpers[stem]).is_file(), stem
    assert "`helpers.detectTools` for `{detectToolsHelper}`" in ok


def test_a_missing_helper_halts_at_item_4_naming_it(tmp_path):
    """#1117: a missing helper ends the run at activation, before any step
    file loads, with the error that names it as the reason."""
    item = _item_4()
    [bullet] = [line for line in item.splitlines() if "`code` starting `HELPERS_`" in line]
    assert "halt with phase `on-activation:helper-missing` for the helpers. No step file loads." in bullet
    [halt] = [line for line in _activation_halts().splitlines()
              if line.startswith("- `on-activation:helper-missing` for the helpers")]
    for needle in ("`path` `{project-root}/_bmad/skf/shared/scripts`",
                   "reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. `"):
        assert needle in halt, needle
    assert item.index(bullet) < item.index("`code` `CONFIG_MISSING`")
    project = _project(tmp_path, f"sidecar_path: {(tmp_path / 'sidecar').as_posix()}\n")
    proc = subprocess.run([sys.executable, str(PREFLIGHT), str(project), "--allow-missing-sidecar", "--helpers",
                           str(SETUP_DIR)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["code"] == "HELPERS_MISSING" and out["code"].startswith("HELPERS_")
    assert "skf-detect-tools.py" in out["helpers_missing"] and "skf-detect-tools.py" in out["error"]
    message = out["error"].removeprefix("Cannot initialize. ")
    assert message != out["error"]
    path = (project / "_bmad" / "skf" / "shared" / "scripts").as_posix()
    error = _blocked_error(_stdin_blocked("on-activation:helper-missing", "Setup cannot proceed: <message>", message,
                                          path))
    assert error == {"phase": "on-activation:helper-missing", "reason": "Setup cannot proceed: " + message,
                     "path": path}


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
