#!/usr/bin/env python3
"""skf-resolve-customization.py: BMAD core's customization resolver on any core from 6.4.0 (#770).

Every SKF activation passes core's resolver `--project-root`, which core
takes only from 6.11.0; core 6.4.0 to 6.10.0 stops on it with argparse's
exit 2, and the `_bmad/custom/` overrides were dropped. The helper runs core
with the flag, and when core rejects it, runs core again without the flag if
core would then read this project's overrides, else refuses with a reason
that names the outdated core. Two stand-ins for core, written into a
scratch project as `_bmad/scripts/resolve_customization.py`, play 6.12 (the
flag known) and 6.10 (the flag unknown, argparse's real error lines, the
root rule 6.4.0 to 6.10.0 share). Each appends its arguments to a
`calls.jsonl` beside it, so a test tells one call from a rerun.

The helper runs under `sys.executable` and runs core the same way, so no
test needs uv, and every test runs on POSIX and Windows.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-resolve-customization.py"
KICKOFF = REPO / "src" / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
SKILL = "skf-demo"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load("skf_resolve_customization", HELPER)

# What both stand-ins share: the call log, a core that hangs (SKF_TEST_CORE_SLEEP, in seconds) or kills itself
# (SKF_TEST_CORE_KILL), core's Python check (exit 3 when SKF_TEST_CORE_NO_TOMLLIB is set, as on a Python
# without tomllib), a failure after part of the JSON is out (SKF_TEST_CORE_PARTIAL), the three-layer merge,
# the dotted --key and core's JSON on stdout.
_PRELUDE = r'''
import argparse
import json
import os
import sys
from pathlib import Path

with Path(__file__).with_name("calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "executable": sys.executable,
                          "safepath": os.environ.get("PYTHONSAFEPATH"),
                          "ioencoding": os.environ.get("PYTHONIOENCODING")}) + "\n")
if os.environ.get("SKF_TEST_CORE_SLEEP"):
    import time
    time.sleep(float(os.environ["SKF_TEST_CORE_SLEEP"]))
if os.environ.get("SKF_TEST_CORE_KILL"):
    import signal
    os.kill(os.getpid(), signal.SIGKILL)
if os.environ.get("SKF_TEST_CORE_NO_TOMLLIB"):
    sys.stderr.write("error: Python 3.11+ is required (stdlib `tomllib` not found).\n"
                     "Install a newer Python or run the resolution manually per the\n"
                     "fallback instructions in the skill's SKILL.md.\n")
    sys.exit(3)
if os.environ.get("SKF_TEST_CORE_PARTIAL"):
    sys.stdout.write('{"workflow": {')
    sys.stdout.flush()
    sys.stderr.write("error: interrupted\n")
    sys.exit(1)
import tomllib


def merge(base, over):
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key] = base[key] + value
        else:
            base[key] = value
    return base


def resolve(skill, root, keys):
    defaults = skill / "customize.toml"
    if not defaults.is_file():
        sys.stderr.write(f"error: required customization file not found: {defaults}\n")
        sys.exit(1)
    merged = merge({}, tomllib.loads(defaults.read_text(encoding="utf-8")))
    if root is not None:
        for layer in (f"{skill.name}.toml", f"{skill.name}.user.toml"):
            path = root / "_bmad" / "custom" / layer
            if path.is_file():
                merge(merged, tomllib.loads(path.read_text(encoding="utf-8")))
    output = merged
    if keys:
        missing = object()
        output = {}
        for key in keys:
            value = merged
            for part in key.split("."):
                value = value.get(part, missing) if isinstance(value, dict) else missing
            if value is not missing:
                output[key] = value
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
'''

# BMAD core 6.12: --project-root picks the root; without it, the nearest `_bmad/` folder above the cwd.
CORE_6_12 = '''#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
''' + _PRELUDE + r'''

def nearest_bmad(start):
    for folder in (start, *start.parents):
        if (folder / "_bmad").is_dir():
            return folder
    return None


parser = argparse.ArgumentParser()
parser.add_argument("--skill", "-s", required=True)
parser.add_argument("--project-root", "-p")
parser.add_argument("--key", "-k", action="append", default=[])
args = parser.parse_args()
root = Path(args.project_root).resolve() if args.project_root else nearest_bmad(Path.cwd().resolve())
resolve(Path(args.skill).resolve(), root, args.key)
'''

# BMAD core 6.4.0 to 6.10.0: no --project-root, no PEP 723 header, and the root is the nearest folder above the
# skill (the skill folder first) that holds `_bmad` or `.git`, a file or a folder, else the same from the cwd.
CORE_6_10 = '''#!/usr/bin/env python3
''' + _PRELUDE + r'''

def find_project_root(start):
    current = start.resolve()
    while True:
        if (current / "_bmad").exists() or (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


parser = argparse.ArgumentParser(description="Resolve customization for a BMad skill using three-layer TOML merge.")
parser.add_argument("--skill", "-s", required=True)
parser.add_argument("--key", "-k", action="append", default=[])
args = parser.parse_args()
skill = Path(args.skill).resolve()
resolve(skill, find_project_root(skill) or find_project_root(Path.cwd()), args.key)
'''
CORES = {"6.12": CORE_6_12, "6.10": CORE_6_10}

DEFAULTS = '[workflow]\nname = "default"\npersistent_facts = ["file:{project-root}/**/project-context.md"]\n'
# A team override with a fact outside ASCII, so stdout is checked byte for byte.
TEAM = '[workflow]\nname = "team"\npersistent_facts = ["Déployer sur AWS uniquement ✓"]\n'
MERGED = {"name": "team",
          "persistent_facts": ["file:{project-root}/**/project-context.md", "Déployer sur AWS uniquement ✓"]}
# argparse's two lines when 6.10.0 meets the flag, as the real resolver prints them.
REJECTED = ("usage: resolve_customization.py [-h] --skill SKILL [--key KEY]\n"
            "resolve_customization.py: error: unrecognized arguments: --project-root {root}\n")


def _project(tmp_path: Path, core: str | None) -> Path:
    """A project with core's resolver (unless None) and a team override for skf-demo."""
    root = tmp_path / "project"
    (root / "_bmad" / "custom").mkdir(parents=True)
    (root / "_bmad" / "custom" / f"{SKILL}.toml").write_bytes(TEAM.encode("utf-8"))
    if core is not None:
        (root / "_bmad" / "scripts").mkdir()
        (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(CORES[core].encode("utf-8"))
    return root


def _skill(folder: Path) -> Path:
    """A skill folder holding the bundled customize.toml."""
    folder.mkdir(parents=True)
    (folder / "customize.toml").write_bytes(DEFAULTS.encode("utf-8"))
    return folder


def _installed_skill(root: Path) -> Path:
    return _skill(root / ".claude" / "skills" / SKILL)


def _env(**extra: str) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("SKF_TEST_")}
    # A narrow terminal's COLUMNS would wrap argparse's usage line, which REJECTED holds on one line.
    env["COLUMNS"] = "200"
    env.update(extra)
    return env


def _run(skill: Path, root: Path, *keys: str, cwd: Path | None = None, env: dict | None = None):
    argv = [sys.executable, str(HELPER), "--skill", str(skill), "--project-root", str(root)]
    for key in keys:
        argv += ["--key", key]
    return subprocess.run(argv, capture_output=True, cwd=cwd or root.parent, env=env or _env(), timeout=120)


def _core(root: Path, *args: str, env: dict | None = None):
    """Core's resolver run directly, as the helper runs it, for the bytes it prints."""
    return subprocess.run([sys.executable, str(root / "_bmad" / "scripts" / "resolve_customization.py"), *args],
                          capture_output=True, cwd=root, env={**(env or _env()), "PYTHONIOENCODING": "utf-8"},
                          timeout=120)


def _calls(root: Path) -> list[dict]:
    log = root / "_bmad" / "scripts" / "calls.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _flagged(call: dict) -> bool:
    return "--project-root" in call["argv"]


def _stderr(proc) -> str:
    return ANSI.sub("", proc.stderr.decode("utf-8"))


def _outdated(legacy: Path, root: Path) -> str:
    return (f"BMAD core before 6.11.0: its customization resolver takes no --project-root and would read the "
            f"overrides under {legacy.resolve()}, not under {Path(os.path.abspath(root))}; upgrade BMAD core to "
            f"6.11.0 or later")


def _marked_above(folder: Path) -> bool:
    return any((p / "_bmad").exists() or (p / ".git").exists() for p in (folder, *folder.parents))


# --------------------------------------------------------------------------
# The stand-ins behave as the real resolvers do
# --------------------------------------------------------------------------


def test_the_6_10_stand_in_rejects_the_flag_with_argparse_s_real_lines(tmp_path):
    root = _project(tmp_path, "6.10")
    skill = _installed_skill(root)
    proc = _core(root, "--skill", str(skill), "--project-root", str(root), "--key", "workflow")
    assert proc.returncode == 2 and proc.stdout == b""
    assert _stderr(proc).replace("\r\n", "\n") == REJECTED.format(root=root)


def test_the_6_12_stand_in_takes_the_flag(tmp_path):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)
    proc = _core(root, "--skill", str(skill), "--project-root", str(root), "--key", "workflow")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8")) == {"workflow": MERGED}


# --------------------------------------------------------------------------
# The matrix: 6.11 and later, 6.4 to 6.10 on the same root or another, no core
# --------------------------------------------------------------------------


def test_core_6_11_and_later_runs_once_with_the_flag(tmp_path):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 0, proc.stderr
    assert [_flagged(call) for call in _calls(root)] == [True]
    assert json.loads(proc.stdout.decode("utf-8")) == {"workflow": MERGED}
    assert proc.stderr == b""
    # Byte for byte what core prints, the non-ASCII fact included.
    assert proc.stdout == _core(root, "--skill", str(skill), "--project-root", str(root), "--key", "workflow").stdout


def test_core_before_6_11_on_the_same_root_runs_again_without_the_flag(tmp_path):
    root = _project(tmp_path, "6.10")
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8")) == {"workflow": MERGED}
    # The rejected first attempt's output is discarded: nothing of argparse's reaches stderr.
    assert proc.stderr == b""
    assert [_flagged(call) for call in _calls(root)] == [True, False]
    direct = _core(root, "--skill", str(skill), "--key", "workflow")
    assert proc.stdout == direct.stdout


def test_a_skill_with_no_marked_folder_above_falls_back_to_the_project_root(tmp_path):
    """Core before 6.11.0 searches from the cwd when nothing above the skill is marked; the helper runs it there."""
    elsewhere = tmp_path / "elsewhere"
    if _marked_above(tmp_path):
        pytest.skip(f"a folder above {tmp_path} holds _bmad or .git")
    root = _project(tmp_path, "6.10")
    skill = _skill(elsewhere / SKILL)
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8")) == {"workflow": MERGED}
    assert [_flagged(call) for call in _calls(root)] == [True, False]


# Where a nearer marker sits: inside the project above the skill (a submodule's `.git` file, a nested repo, a stray
# `_bmad` file or folder), or above a skill installed outside the project (a home folder under git).
NEARER_ROOTS = {
    "git-file-in-project": ("project/vendor", ".git", "file"),
    "git-folder-in-project": ("project/vendor", ".git", "folder"),
    "bmad-file-in-project": ("project/vendor", "_bmad", "file"),
    "bmad-folder-in-project": ("project/vendor", "_bmad", "folder"),
    "git-folder-outside": ("home", ".git", "folder"),
}


@pytest.mark.parametrize("case", sorted(NEARER_ROOTS))
def test_core_before_6_11_with_a_nearer_root_refuses_and_names_the_upgrade(tmp_path, case):
    folder, marker, kind = NEARER_ROOTS[case]
    root = _project(tmp_path, "6.10")
    nearer = tmp_path / folder
    nearer.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        (nearer / marker).write_bytes(b"gitdir: ../.git/modules/vendor\n")
    else:
        (nearer / marker).mkdir()
    skill = _skill(nearer / "skills" / SKILL)
    proc = _run(skill, root, "workflow.persistent_facts")
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert _stderr(proc).splitlines()[0] == _outdated(nearer, root)
    # One call: core is never run without the flag when it would read another folder's overrides.
    assert [_flagged(call) for call in _calls(root)] == [True]


def test_a_missing_core_resolver_is_not_found(tmp_path):
    root = _project(tmp_path, None)
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 1
    assert proc.stdout == b""
    lines = _stderr(proc).splitlines()
    assert lines[0] == "not found"
    assert str(root / "_bmad" / "scripts" / "resolve_customization.py") in lines[1]


# --------------------------------------------------------------------------
# Core's own failures pass through, with nothing on stdout
# --------------------------------------------------------------------------


@pytest.mark.parametrize("core", sorted(CORES))
def test_python_too_old_passes_through_exit_3(tmp_path, core):
    """Core checks its Python before argparse, so a 6.10 core exits 3 on the first call and is not run again."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_NO_TOMLLIB="1"))
    assert proc.returncode == 3
    assert proc.stdout == b""
    assert _stderr(proc).splitlines()[0] == "error: Python 3.11+ is required (stdlib `tomllib` not found)."
    assert [_flagged(call) for call in _calls(root)] == [True]


@pytest.mark.parametrize("core", sorted(CORES))
def test_a_config_error_passes_through_exit_1(tmp_path, core):
    """No customize.toml: core exits 1, after the rerun on a 6.10 core, whose argparse stops on the flag first."""
    root = _project(tmp_path, core)
    skill = root / ".claude" / "skills" / SKILL
    skill.mkdir(parents=True)
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 1
    assert proc.stdout == b""
    stderr = _stderr(proc)
    assert stderr.splitlines()[0].startswith("error: required customization file not found: ")
    assert "unrecognized arguments" not in stderr
    assert [_flagged(call) for call in _calls(root)] == ([True] if core == "6.12" else [True, False])


@pytest.mark.parametrize("core", sorted(CORES))
def test_a_failure_after_partial_output_prints_nothing(tmp_path, core):
    """Campaign pipes the helper into the kickoff script, which would read a partial JSON: none reaches stdout."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    assert _core(root, "--skill", str(skill), env=_env(SKF_TEST_CORE_PARTIAL="1")).stdout  # core did print
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_PARTIAL="1"))
    assert proc.returncode == 1
    assert proc.stdout == b""
    assert _stderr(proc).splitlines() == ["error: interrupted"]


# --------------------------------------------------------------------------
# The helper's own failures: a core that hangs, cannot start or is killed
# --------------------------------------------------------------------------


def _main(capsysbinary, skill: Path, root: Path) -> tuple[int, bytes, list[str]]:
    """The helper run in this process, so a test can shorten its time limit or break its start."""
    code = helper.main(["--skill", str(skill), "--project-root", str(root), "--key", "workflow"])
    out, err = capsysbinary.readouterr()
    return code, out, ANSI.sub("", err.decode("utf-8")).splitlines()


def test_a_core_that_does_not_finish_is_stopped(tmp_path, monkeypatch, capsysbinary):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)
    monkeypatch.setattr(helper, "CORE_TIMEOUT_SEC", 1)
    monkeypatch.setenv("SKF_TEST_CORE_SLEEP", "30")
    code, out, err = _main(capsysbinary, skill, root)
    assert code == 1
    assert out == b""
    assert err[0] == "BMAD core's customization resolver did not finish within 1 seconds"


def test_a_core_that_cannot_start_names_why(tmp_path, monkeypatch, capsysbinary):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied", args[0][0])

    monkeypatch.setattr(helper.subprocess, "run", refuse)
    code, out, err = _main(capsysbinary, skill, root)
    assert code == 1
    assert out == b""
    assert err[0].startswith("BMAD core's customization resolver could not start: ")
    assert "Permission denied" in err[0]


@pytest.mark.skipif(os.name == "nt", reason="a POSIX signal")
def test_a_core_stopped_by_a_signal_names_it(tmp_path):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_KILL="1"))
    assert proc.returncode == 1
    assert proc.stdout == b""
    assert _stderr(proc).splitlines()[0] == (
        f"BMAD core's customization resolver was stopped by signal {int(signal.SIGKILL)}")


# --------------------------------------------------------------------------
# How core is run, and what Campaign's kickoff pipe reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize("core", sorted(CORES))
def test_core_runs_under_this_interpreter_from_the_project_root(tmp_path, core):
    """sys.executable, the project root as cwd, PYTHONSAFEPATH dropped (6.11+ imports a sibling module) and a
    UTF-8 stdout; relative arguments resolve from the caller's cwd."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    env = _env(PYTHONSAFEPATH="1", PYTHONIOENCODING="cp1252")
    rel_skill = Path(os.path.relpath(skill, tmp_path))
    proc = _run(rel_skill, Path("project"), "workflow", cwd=tmp_path, env=env)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8")) == {"workflow": MERGED}
    calls = _calls(root)
    assert calls
    for call in calls:
        assert os.path.samefile(call["cwd"], root)
        assert os.path.samefile(call["executable"], sys.executable)
        assert call["safepath"] is None and call["ioencoding"] == "utf-8"
        assert os.path.isabs(call["argv"][call["argv"].index("--skill") + 1])


@pytest.mark.parametrize("core", sorted(CORES))
def test_stdout_is_what_the_kickoff_facts_parser_accepts(tmp_path, core):
    """step-05 pipes the helper into `campaign-render-kickoff.py --facts-json -`."""
    kickoff = _load("campaign_render_kickoff_for_resolver", KICKOFF)
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    proc = _run(skill, root, kickoff.RESOLVER_KEY)
    assert proc.returncode == 0, proc.stderr
    assert kickoff._facts_entries(proc.stdout.decode("utf-8-sig")) == MERGED["persistent_facts"]


# --------------------------------------------------------------------------
# The rejected-flag test and the old root rule, unit by unit
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stderr", [
    REJECTED.format(root="/p"),
    "usage: resolve_customization.py [-h] --skill SKILL [--key KEY]\n"
    "resolve_customization.py: error: unrecognized arguments: --project-root=/p --key workflow\n",
    # A narrow terminal wraps the usage line, so the error is not always the second line.
    "usage: resolve_customization.py [-h] --skill SKILL\n                                [--key KEY]\n"
    "resolve_customization.py: error: unrecognized arguments: --project-root /p\n",
    # Python 3.14 colours argparse's output when asked to.
    "\x1b[1;34musage: \x1b[0mresolve_customization.py [-h]\n"
    "resolve_customization.py: \x1b[1;31merror:\x1b[0m unrecognized arguments: --project-root /p\n",
])
def test_a_rejected_flag_is_recognised(stderr):
    assert helper.rejects_project_root(2, b"", stderr.encode("utf-8"))


@pytest.mark.parametrize("returncode,stdout,stderr", [
    # Exit 2 alone is never enough: a missing script, another unknown flag, a path that merely holds the flag.
    (2, b"", "python: can't open file 'resolve_customization.py': [Errno 2] No such file or directory\n"),
    (2, b"", "resolve_customization.py: error: unrecognized arguments: --bogus x\n"),
    (2, b"", "resolve_customization.py: error: unrecognized arguments: /x/--project-roots\n"),
    (2, b"", "resolve_customization.py: error: the following arguments are required: --skill\n"),
    (2, b"{}\n", "resolve_customization.py: error: unrecognized arguments: --project-root /p\n"),
    (1, b"", "resolve_customization.py: error: unrecognized arguments: --project-root /p\n"),
])
def test_anything_else_is_not_a_rejected_flag(returncode, stdout, stderr):
    assert not helper.rejects_project_root(returncode, stdout, stderr.encode("utf-8"))


def test_the_old_root_rule_takes_the_nearest_marker_from_the_skill_first(tmp_path):
    root = tmp_path / "project"
    (root / "_bmad").mkdir(parents=True)
    skill = root / "pkg" / "skills" / SKILL
    skill.mkdir(parents=True)
    assert helper.legacy_project_root(skill, root) == root.resolve()
    (root / "pkg" / ".git").write_bytes(b"gitdir: x\n")
    assert helper.legacy_project_root(skill, root) == (root / "pkg").resolve()
    (skill / "_bmad").write_bytes(b"")  # the skill folder itself counts
    assert helper.legacy_project_root(skill, root) == skill.resolve()


def test_help_is_ascii_and_the_parser_is_importable():
    """The helper-call contract test parses every SKF call with _build_parser(); --help survives any console."""
    parser = helper._build_parser()
    args = parser.parse_args(["--skill", "s", "--project-root", "p", "--key", "a", "--key", "b"])
    assert (args.skill, args.project_root, args.key) == ("s", "p", ["a", "b"])
    proc = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, timeout=60,
                          env=_env(PYTHONIOENCODING="ascii"))
    assert proc.returncode == 0, proc.stderr
    proc.stdout.decode("ascii")
    assert HELPER.read_bytes().decode("ascii")
