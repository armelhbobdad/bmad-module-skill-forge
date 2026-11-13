"""skf-setup-args.py: Setup Forge's flags, parsed by a helper (#1183).

On Activation item 1 used to split the invocation in prose, so
`--require-tier --headless` could bind `--headless` as the tier, lose quiet
mode and end a `claude -p` run on a prose reason. The helper reads the
arguments on stdin and prints one JSON object; these tests run it on each
kind of invocation it reads (a flag after a valued flag, empty and quoted
values, space and `=` forms, unknown tokens, CRLF, empty stdin), check that
an orphan-action reason it writes reaches the blocked envelope unchanged,
that it stays runnable by a bare python3, and that item 1's runner loop
prints its object.
"""

from __future__ import annotations

import ast
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
PARSER = SRC / "shared" / "scripts" / "skf-setup-args.py"
EMIT_HELPER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
SKILL_MD = SRC / "skf-setup" / "SKILL.md"
QUIET_OUTPUT_TEST = REPO_ROOT / "test" / "test-skf-setup-quiet-output.py"
DETECT_HELPER = SRC / "shared" / "scripts" / "skf-detect-tools.py"
ENVELOPE_PREFIX = "SKF_SETUP_RESULT_JSON: "
ORPHAN_PHASE = "on-activation:orphan-action-invalid"
DEFAULTS = {"headless": False, "quiet": False, "require_tier": None, "orphan_action": None, "ccc_skip_index": False}


def _orphan_reason(given: str) -> str:
    return (f"Setup cannot proceed: --orphan-action takes keep or remove, not {given}. "
            "Re-run with --orphan-action=keep or --orphan-action=remove.")


def _run(stdin: bytes, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PARSER)], input=stdin, capture_output=True, timeout=10, env=env)


def _parse(stdin: bytes, env=None) -> dict:
    done = _run(stdin, env)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stderr == b""
    [line] = done.stdout.decode("utf-8").splitlines()
    return json.loads(line)


CASES = {
    # The flag taken as a value: a following token that starts with `-` is read as a flag.
    "require-tier-then-headless": (b"--require-tier --headless\n",
                                   {"headless": True, "quiet": True, "require_tier": ""}),
    "require-tier-then-short-headless": (b"--require-tier -H\n",
                                         {"headless": True, "quiet": True, "require_tier": ""}),
    "orphan-action-then-short-headless": (b"--orphan-action -H\n",
                                          {"headless": True, "quiet": True, "orphan_action": "", "phase": ORPHAN_PHASE,
                                           "reason": _orphan_reason("an empty value")}),
    "empty-orphan-action": (b"--orphan-action=\n", {"orphan_action": "", "phase": ORPHAN_PHASE,
                                                   "reason": _orphan_reason("an empty value")}),
    "quoted-orphan-action": (b"--quiet --orphan-action 'Remove'\n",
                             {"quiet": True, "orphan_action": "'Remove'", "phase": ORPHAN_PHASE,
                              "reason": _orphan_reason("'Remove'")}),
    "orphan-action-space-form": (b"--orphan-action remove\n", {"orphan_action": "remove"}),
    "unknown-tokens": (b"foo --verbose --orphan-action remove -X\n", {"orphan_action": "remove"}),
    "short-headless": (b"-H\n", {"headless": True, "quiet": True}),
    "quiet-alone": (b"--quiet\n", {"quiet": True}),
    "equals-form-with-a-dash": (b"--require-tier=-x\n", {"require_tier": "-x"}),
    "space-form-then-flag": (b"--require-tier Deep --headless\n",
                             {"headless": True, "quiet": True, "require_tier": "Deep"}),
    "last-occurrence-wins": (b"--require-tier Deep --orphan-action=keep --require-tier=Forge+ --orphan-action remove\n",
                             {"require_tier": "Forge+", "orphan_action": "remove"}),
    "flag-at-the-end": (b"--ccc-skip-index --require-tier\n", {"ccc_skip_index": True, "require_tier": ""}),
    "crlf-and-several-lines": (b"--headless\r\n--orphan-action\r\nremove\r\n--ccc-skip-index\r\n",
                               {"headless": True, "quiet": True, "orphan_action": "remove", "ccc_skip_index": True}),
    "bom-and-bad-bytes": (b"\xef\xbb\xbf--quiet \xff --require-tier=Deep\n", {"quiet": True, "require_tier": "Deep"}),
    "empty-stdin": (b"", {}),
    "keep-is-valid": (b"--orphan-action=keep", {"orphan_action": "keep"}),
    "wrong-case-keep": (b"--orphan-action=Keep", {"orphan_action": "Keep", "phase": ORPHAN_PHASE,
                                                  "reason": _orphan_reason("Keep")}),
}


@pytest.mark.parametrize("stdin,expected", list(CASES.values()), ids=list(CASES))
def test_the_parser_prints_one_object_for_each_case(stdin, expected):
    assert _parse(stdin) == {**DEFAULTS, **expected}


def test_the_parser_keeps_its_keys_in_order_and_unicode_on_a_cp1252_console():
    """A Windows `python` or `py -3` writes cp1252 by default: the helper writes UTF-8 anyway."""
    done = _run("--require-tier=D\u00e9ep\n".encode("utf-8"), env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    value = json.loads(done.stdout.decode("utf-8"))
    assert list(value) == ["headless", "quiet", "require_tier", "orphan_action", "ccc_skip_index"]
    assert value["require_tier"] == "D\u00e9ep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX pty")
def test_a_terminal_stdin_is_no_arguments():
    """A run with no heredoc never blocks on a terminal it would wait on forever."""
    import pty  # POSIX only: Windows has no termios

    leader, follower = pty.openpty()
    try:
        done = subprocess.run([sys.executable, str(PARSER)], stdin=follower, capture_output=True, timeout=10)
    finally:
        os.close(leader)
        os.close(follower)
    assert done.returncode == 0
    assert json.loads(done.stdout) == DEFAULTS


@pytest.mark.parametrize("value", ["", "'Remove'", "Remove;$(touch", "`x`", "C:\\x", "\u00e9t\u00e9"])
def test_the_reason_reaches_the_blocked_envelope_unchanged(tmp_path, value):
    """Item 1 halts with reason `<message>` and passes the helper's reason on stdin, as the halt contract
    passes text from a helper: the envelope's error.reason is that reason, quotes and all."""
    flag = f"--orphan-action={value}" if value else "--orphan-action="
    parsed = _parse(f"--quiet {flag}\n".encode("utf-8"))
    assert parsed["phase"] == ORPHAN_PHASE
    done = subprocess.run([sys.executable, str(EMIT_HELPER), "emit-blocked", "--phase", parsed["phase"],
                           "--reason", "<message>", "--stderr-from", "-"],
                          input=parsed["reason"].encode("utf-8"), capture_output=True, timeout=10, cwd=tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    error = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]["error"]
    assert error == {"phase": ORPHAN_PHASE, "reason": _orphan_reason(value or "an empty value"), "path": "<n/a>"}
    assert list(tmp_path.iterdir()) == []


def _py39_stdlib() -> frozenset:
    """The quiet-output test's PY39_STDLIB_IMPORTS: the modules a helper a bare python3 runs may import."""
    tree = ast.parse(QUIET_OUTPUT_TEST.read_text(encoding="utf-8"))
    [node] = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "PY39_STDLIB_IMPORTS" for t in n.targets)]
    return frozenset(ast.literal_eval(node.value.args[0]))


def test_the_parser_runs_under_any_runner_of_the_halt_contract():
    """Item 1 runs before uv is proven present, so a bare python3 as old as 3.9 may run it."""
    src = PARSER.read_text(encoding="utf-8")
    header = re.search(r"^# /// script$(.*?)^# ///$", src, re.M | re.S)
    assert header, "no PEP 723 header"
    assert re.search(r'^# requires-python = ">=3\.11"$', header.group(1), re.M)
    assert re.search(r"^# dependencies = \[\]$", header.group(1), re.M)
    tree = ast.parse(src, feature_version=(3, 9))
    roots = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    roots |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    allowed = _py39_stdlib()
    assert "argparse" in allowed and roots <= allowed, roots - allowed
    # No uv, no environment variables, no site-packages.
    bare = subprocess.run([sys.executable, "-I", "-S", str(PARSER)], input=b"-H", capture_output=True, timeout=10)
    assert bare.returncode == 0, bare.stderr.decode("utf-8", "replace")
    assert json.loads(bare.stdout) == {**DEFAULTS, "headless": True, "quiet": True}


def _item_1() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.index("1. **Parse invocation flags first**")
    return text[start:text.index("\n2. **Check for the config.**", start)]


def _item_1_loop() -> str:
    """Item 1's fenced runner loop, without the list item's indent."""
    [block] = re.findall(r"^   ```bash\n(.*?)^   ```$", _item_1(), re.M | re.S)
    lines = block.splitlines()
    assert all(line.startswith("   ") for line in lines), lines
    return "\n".join(line[3:] for line in lines) + "\n"


def test_item_1_runs_the_parser_through_the_runner_chain():
    item = _item_1()
    assert "`<parser>` is `skf-setup-args.py` at its installed path, else its dev path (Conventions)" in item
    loop = _item_1_loop()
    chain = re.search(r"^for r in (.+); do$", loop, re.M)
    assert chain and shlex.split(chain.group(1)) == ["uv run", "python3", "python", "py -3"]
    assert "<<'SKF_ARGS'\n<the arguments>\nSKF_ARGS\n) && " in loop
    # The parser reads stdin to its end, so a run with no arguments keeps the heredoc rather than
    # leave the parser on a stdin the host may hold open.
    assert "exactly as given (keep the heredoc, empty, when there are none):" in item
    assert 'case "$out" in "{"*) printf \'%s\\n\' "$out"; break ;; esac' in loop
    assert loop.endswith("done\n")
    for key in DEFAULTS:
        assert f"`{key}`" in item, key
    assert "set both modes true when `{pipeline_mode}` is true" in item
    assert ("When the object has a `phase`, halt with phase `on-activation:orphan-action-invalid`, no `path`, and "
            "reason `<message>`, its `reason` passed as the halt contract says.") in item
    assert ("When no runner prints an object, `{quiet_mode}` is true when the arguments hold `--headless`, `-H` or "
            "`--quiet`, or `{pipeline_mode}` is true.") in item


def _filled(arguments: str) -> str:
    return _item_1_loop().replace("<parser>", PARSER.as_posix()).replace("<the arguments>", arguments)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_the_item_1_loop_prints_the_object_with_only_python3_on_path(tmp_path):
    """Before uv is proven, the first runner that works prints the object; the quoted heredoc keeps the
    arguments literal, so nothing in them runs."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    env = {"PATH": str(bindir), "HOME": str(tmp_path)}
    bash = shutil.which("bash")
    arguments = "--require-tier --headless --orphan-action=$(touch${IFS}pwned)`touch${IFS}pwned2`"
    done = subprocess.run([bash, "-c", _filled(arguments)], capture_output=True, timeout=30, cwd=tmp_path, env=env)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    value = json.loads(line)
    assert {k: value[k] for k in DEFAULTS} == {**DEFAULTS, "headless": True, "quiet": True, "require_tier": "",
                                               "orphan_action": "$(touch${IFS}pwned)`touch${IFS}pwned2`"}
    assert value["phase"] == ORPHAN_PHASE
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()
    # No arguments: the empty heredoc is the parser's stdin, so a stdin the host holds open is never read.
    host_stdin, held_open = os.pipe()
    try:
        done = subprocess.run([bash, "-c", _filled("")], stdin=host_stdin, capture_output=True, timeout=30,
                              cwd=tmp_path, env=env)
    finally:
        os.close(host_stdin)
        os.close(held_open)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert json.loads(done.stdout) == DEFAULTS
    # A `uv` that exits 0 but prints no object is skipped, and python3 still prints it.
    uv = bindir / "uv"
    uv.write_text("#!/bin/sh\n: > \"$HOME/uv-ran\"\nprintf '%s\\n' 'uv: no object'\nexit 0\n", encoding="utf-8")
    uv.chmod(0o755)
    done = subprocess.run([bash, "-c", _filled("--quiet")], capture_output=True, timeout=30, cwd=tmp_path, env=env)
    assert (tmp_path / "uv-ran").exists(), "the uv stub never ran, so the guard was not exercised"
    assert json.loads(done.stdout) == {**DEFAULTS, "quiet": True}
    # No runner prints an object: nothing is printed, and item 1 falls back to its one prose rule.
    (bindir / "python3").unlink()
    nothing = subprocess.run([bash, "-c", _filled("--quiet")], capture_output=True, timeout=30, cwd=tmp_path,
                             env=env)
    assert nothing.stdout == b""


def test_a_parser_that_printed_nothing_halts_once_uv_is_found():
    """Items 2 and 3 keep their reasons for a folder without SKF or a machine without uv; after them, a run
    that could not read its flags halts rather than drop --require-tier and --orphan-action."""
    text = SKILL_MD.read_text(encoding="utf-8")
    item_3 = text[text.index("3. **Probe `uv` runtime.**"):text.index("4. **Load config and preferences.**")]
    assert ("Once `uv` is present, if item 1's parser printed no object, halt with phase "
            "`on-activation:helper-missing`, `path` its installed path, reason `Setup cannot proceed: "
            "skf-setup-args.py could not read the flags. Reinstall SKF, then re-run /skf-setup.`") in item_3
    assert item_3.index("`on-activation:uv-missing`") < item_3.index("`on-activation:helper-missing`")


@pytest.mark.parametrize("arguments,value", [("--require-tier --headless", ""), ("--quiet --require-tier=-x", "-x")],
                         ids=["flag-taken-as-value", "equals-form-with-a-dash"])
def test_a_tier_that_names_no_tier_ends_blocked_at_step_1(tmp_path, arguments, value):
    """`--require-tier` followed by a flag, and `--require-tier=-x`: the run stays quiet, step 1's
    detector rejects the value, and its halt emits the blocked envelope as the run's one line."""
    parsed = _parse(arguments.encode("utf-8"))
    assert parsed["quiet"] is True and parsed["require_tier"] == value
    detect = subprocess.run([sys.executable, str(DETECT_HELPER), "--project-root", str(tmp_path),
                             f"--require-tier={parsed['require_tier']}"], capture_output=True, timeout=60)
    assert detect.returncode == 1 and detect.stdout == b""
    message = json.loads(detect.stderr)["message"]
    assert "Quick, Forge, Forge+, Deep" in message
    done = subprocess.run([sys.executable, str(EMIT_HELPER), "emit-blocked", "--phase", "step 1:detect-tools",
                           "--reason", "Setup cannot proceed: tool detection failed: <message>",
                           "--path", tmp_path.as_posix(), "--stderr-from", "-"],
                          input=detect.stderr, capture_output=True, timeout=10)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    [line] = done.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line[len(ENVELOPE_PREFIX):])["skf_setup"]
    assert envelope["status"] == "blocked" and envelope["error"]["phase"] == "step 1:detect-tools"
    assert envelope["error"]["reason"] == "Setup cannot proceed: tool detection failed: " + message
