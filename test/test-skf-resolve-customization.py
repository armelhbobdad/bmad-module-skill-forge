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

With `--facts` (#1106) the helper also resolves persistent_facts in core's
JSON, which core's merge only appends: each `!` entry drops the earlier
entries it names, each `file:` glob becomes one entry per file, matched by a
walk that enters no hidden folder and no folder reached through a directory
link, no file under `_bmad-output/.skf-run/`, where a halted run keeps its
source clones, is named, and each file is named once. Campaign's kickoff
script runs the same functions.

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
# without tomllib), a failure after part of the JSON is out (SKF_TEST_CORE_PARTIAL), an exit 0 whose stdout is
# not a JSON object (SKF_TEST_CORE_STDOUT, a JSON string whose text it prints, so an empty output survives any
# platform's environment), the three-layer merge, the dotted --key and core's JSON on stdout.
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
if "SKF_TEST_CORE_STDOUT" in os.environ:
    sys.stdout.write(json.loads(os.environ["SKF_TEST_CORE_STDOUT"]))
    sys.stderr.write("core's own note\n")
    sys.exit(0)
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


def _run(skill: Path, root: Path, *keys: str, cwd: Path | None = None, env: dict | None = None,
         facts: bool = False, timeout: int = 120):
    argv = [sys.executable, str(HELPER), "--skill", str(skill), "--project-root", str(root)]
    for key in keys:
        argv += ["--key", key]
    if facts:
        argv.append("--facts")
    return subprocess.run(argv, capture_output=True, cwd=cwd or root.parent, env=env or _env(), timeout=timeout)


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


# With --facts too: the facts pass runs on core's exit 0 only, so each of core's failures keeps its own code.
@pytest.mark.parametrize("facts", [False, True], ids=["plain", "facts"])
@pytest.mark.parametrize("core", sorted(CORES))
def test_python_too_old_passes_through_exit_3(tmp_path, core, facts):
    """Core checks its Python before argparse, so a 6.10 core exits 3 on the first call and is not run again."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_NO_TOMLLIB="1"), facts=facts)
    assert proc.returncode == 3
    assert proc.stdout == b""
    assert _stderr(proc).splitlines()[0] == "error: Python 3.11+ is required (stdlib `tomllib` not found)."
    assert [_flagged(call) for call in _calls(root)] == [True]


@pytest.mark.parametrize("facts", [False, True], ids=["plain", "facts"])
@pytest.mark.parametrize("core", sorted(CORES))
def test_a_config_error_passes_through_exit_1(tmp_path, core, facts):
    """No customize.toml: core exits 1, after the rerun on a 6.10 core, whose argparse stops on the flag first."""
    root = _project(tmp_path, core)
    skill = root / ".claude" / "skills" / SKILL
    skill.mkdir(parents=True)
    proc = _run(skill, root, "workflow", facts=facts)
    assert proc.returncode == 1
    assert proc.stdout == b""
    stderr = _stderr(proc)
    assert stderr.splitlines()[0].startswith("error: required customization file not found: ")
    assert "unrecognized arguments" not in stderr
    assert [_flagged(call) for call in _calls(root)] == ([True] if core == "6.12" else [True, False])


@pytest.mark.parametrize("facts", [False, True], ids=["plain", "facts"])
@pytest.mark.parametrize("core", sorted(CORES))
def test_a_failure_after_partial_output_prints_nothing(tmp_path, core, facts):
    """Campaign pipes the helper into the kickoff script, which would read a partial JSON: none reaches stdout."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    assert _core(root, "--skill", str(skill), env=_env(SKF_TEST_CORE_PARTIAL="1")).stdout  # core did print
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_PARTIAL="1"), facts=facts)
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
# --facts: the `!` drop and the glob, applied after core's merge (#1106)
# --------------------------------------------------------------------------

DEFAULT_FACT = "file:{project-root}/**/project-context.md"


def _team(root: Path, facts: list[str]) -> None:
    """The team override for skf-demo, holding these persistent_facts after the bundled default."""
    (root / "_bmad" / "custom" / f"{SKILL}.toml").write_bytes(
        f'[workflow]\nname = "team"\npersistent_facts = {json.dumps(facts, ensure_ascii=False)}\n'.encode("utf-8"))


def _context(folder: Path, text: str = "rule\n") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project-context.md").write_bytes(text.encode("utf-8"))
    return folder / "project-context.md"


def _facts(proc) -> list:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))["workflow"]["persistent_facts"]


def _file(path: Path) -> str:
    return "file:" + Path(os.path.abspath(path)).as_posix()


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_a_drop_entry_drops_the_bundled_default(tmp_path, core):
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    _context(root / "docs")
    _team(root, [f"!{DEFAULT_FACT}"])
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == []
    assert proc.stderr == b""


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_never_name_a_kept_clone_s_context(tmp_path, core):
    """A halted Analyze Source run keeps its clones under _bmad-output/.skf-run/: the default glob skips them, an
    entry that names that folder outright yields nothing, and `**` enters no hidden folder."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    docs = _context(root / "docs")
    _context(root / "_bmad-output" / ".skf-run" / "x" / "source-1", "the clone's rule\n")
    _context(root / ".hidden", "a hidden folder's rule\n")
    _team(root, ["file:{project-root}/_bmad-output/.skf-run/**/project-context.md",
                 "file:{project-root}/_bmad-output/.skf-run/x/source-1/project-context.md"])
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [_file(docs)]
    assert proc.stderr == b""


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_a_leading_double_star_matches_no_folder_too(tmp_path, core):
    """`**` may match no folder at all, so the default glob names a `project-context.md` at the project root, as
    glob.glob did, beside one in a subfolder, sorted as strings."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    files = [_context(root / "docs"), _context(root)]
    assert helper.resolve_facts([DEFAULT_FACT], root.as_posix()) == [_file(path) for path in files]
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [*map(_file, files), "Déployer sur AWS uniquement ✓"]


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_keep_an_entry_that_names_no_file_and_say_why(tmp_path, core):
    """A typo never fails the resolve, which would drop every override: the entry stays, with the root put in."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    _team(root, ["file:{project-root}/missing.md", "file:{skill-root}/facts.md", "Cite sources."])
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [f"file:{Path(os.path.abspath(root)).as_posix()}/missing.md", "file:{skill-root}/facts.md",
                            "Cite sources."]
    assert _stderr(proc).splitlines() == [
        f"persistent_facts: `file:{{project-root}}/missing.md` names no file "
        f"({Path(os.path.abspath(root)).as_posix()}/missing.md)",
        "persistent_facts: `file:{skill-root}/facts.md` holds the unresolved placeholder `{skill-root}`",
    ]


def _link_or_skip(link: Path, target: str | Path, *, directory: bool = True) -> None:
    """A link at link to target, as written (a relative target from link's folder), or a skip where none can be made."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


def _link_loops(root: Path) -> None:
    """Two links back up to the root and npm's node_modules/node_modules -> node_modules, as the main checkout has."""
    for folder in ("a", "b", "node_modules"):
        (root / folder).mkdir()
    _link_or_skip(root / "a" / "up", "..")
    _link_or_skip(root / "b" / "up", "..")
    _link_or_skip(root / "node_modules" / "node_modules", root / "node_modules")


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_a_link_loop_names_each_file_once_and_ends(tmp_path, core):
    """A glob that follows directory links listed one file once per path through `a/up -> ..`, and two such
    links never finished: the walk enters no linked folder, so the default glob names the file once, at once."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    docs = _context(root / "docs")
    _link_loops(root)
    proc = _run(skill, root, "workflow", facts=True, timeout=30)
    assert _facts(proc) == [_file(docs), "Déployer sur AWS uniquement ✓"]
    assert proc.stderr == b""


def test_the_walk_enters_no_linked_folder(tmp_path, monkeypatch):
    """No folder the walk lists lies under a directory link, and a link the pattern spells out is still read.

    One loop only: a glob that follows links ends on it, at the system's link limit, so this test fails rather
    than hangs on one."""
    root = tmp_path / "project"
    docs = _context(root / "docs")
    (root / "a").mkdir()
    _link_or_skip(root / "a" / "up", "..")
    walked: list[str] = []
    real_walk = os.walk

    def spy(top, *args, **kwargs):
        for folder, folders, files in real_walk(top, *args, **kwargs):
            walked.append(folder)
            yield folder, folders, files

    monkeypatch.setattr(helper.os, "walk", spy)
    assert helper.resolve_facts([DEFAULT_FACT], root.as_posix()) == [_file(docs)]
    assert walked and not [folder for folder in walked
                           if any(os.path.islink(parent) for parent in [folder, *map(str, Path(folder).parents)])]
    # A folder the pattern names may be a link: `a/up` is spelled out, and leads back to docs.
    assert helper.resolve_facts(["file:{project-root}/a/up/docs/*.md"], root.as_posix()) == [
        "file:" + (root / "a" / "up" / "docs" / "project-context.md").as_posix()]


def test_the_walk_reads_a_link_a_part_spells_out_after_a_wildcard(tmp_path):
    """A part after a wildcard that spells a linked folder out still enters it, as glob.glob did: `pkg/a/docs`
    links to another folder, `pkg/*/docs/...` names its file, and `**` never enters it."""
    root = tmp_path / "project"
    elsewhere = _context(tmp_path / "elsewhere")
    (root / "pkg" / "a").mkdir(parents=True)
    _link_or_skip(root / "pkg" / "a" / "docs", elsewhere.parent)
    assert helper.resolve_facts(["file:{project-root}/pkg/*/docs/project-context.md"], root.as_posix()) == [
        "file:" + (root / "pkg" / "a" / "docs" / "project-context.md").as_posix()]
    assert helper.resolve_facts([DEFAULT_FACT], root.as_posix()) == []


def test_a_single_star_enters_no_hidden_and_no_linked_folder(tmp_path):
    """The hidden-name and link rules hold for `*` as for `**`: `*/project-context.md` names the docs folder's
    file, not a hidden folder's, and not one in a folder linked to another project."""
    root = tmp_path / "project"
    docs = _context(root / "docs")
    _context(root / ".hidden", "a hidden folder's rule\n")
    elsewhere = _context(tmp_path / "elsewhere", "another project's rule\n")
    entry = "file:{project-root}/*/project-context.md"
    assert helper.resolve_facts([entry], root.as_posix()) == [_file(docs)]
    _link_or_skip(root / "vendored", elsewhere.parent)
    assert helper.resolve_facts([entry], root.as_posix()) == [_file(docs)]


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_skip_a_context_reached_only_through_a_linked_folder(tmp_path, core):
    """A linked folder is not entered, so a `project-context.md` under it is not listed; a linked file still is."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    elsewhere = _context(tmp_path / "elsewhere", "another project's rule\n")
    _link_or_skip(root / "vendored", elsewhere.parent)
    (root / "docs").mkdir()
    _link_or_skip(root / "docs" / "project-context.md", elsewhere, directory=False)
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [_file(root / "docs" / "project-context.md"), "Déployer sur AWS uniquement ✓"]


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_name_a_file_two_entries_name_once(tmp_path, core):
    """The default glob and an explicit path to the same file, or a file link to it, give one entry, where the
    first entry that names it put it."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    docs = _context(root / "docs")
    _team(root, ["file:{project-root}/docs/project-context.md", "Cite sources."])
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [_file(docs), "Cite sources."]
    _link_or_skip(root / "alias.md", docs, directory=False)
    _team(root, ["file:{project-root}/alias.md", "file:{project-root}/docs/*.md"])
    proc = _run(skill, root, "workflow", facts=True)
    assert _facts(proc) == [_file(docs)]
    # The first entry that names the file sets the path it is named by.
    assert helper.resolve_facts(["file:{project-root}/alias.md", DEFAULT_FACT], root.as_posix()) == [
        _file(root / "alias.md")]


@pytest.mark.skipif(os.name == "nt", reason="a POSIX file name that is not UTF-8")
@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_survive_a_folder_name_that_is_not_utf_8(tmp_path, core):
    """A path that is not UTF-8 goes out as its own bytes, instead of an encoding error that drops every override."""
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    docs = _context(root / "docs")
    try:
        odd = Path(os.fsdecode(os.fsencode(root) + b"/\xff"))
        odd.mkdir()
    except OSError as exc:
        pytest.skip(f"this file system takes no such name: {exc}")
    clashed = _context(odd)
    proc = _run(skill, root, "workflow", facts=True)
    assert proc.returncode == 0, proc.stderr
    facts = json.loads(proc.stdout.decode("utf-8", "surrogateescape"))["workflow"]["persistent_facts"]
    assert facts == [_file(docs), _file(clashed), "Déployer sur AWS uniquement ✓"]
    assert b"/\xff/project-context.md" in proc.stdout


@pytest.mark.parametrize("core", sorted(CORES))
def test_without_facts_core_s_bytes_pass_unchanged(tmp_path, core):
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    _context(root / "docs")
    _team(root, [f"!{DEFAULT_FACT}"])
    proc = _run(skill, root, "workflow")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == _core(root, "--skill", str(skill), "--key", "workflow").stdout
    assert _facts(proc) == [DEFAULT_FACT, f"!{DEFAULT_FACT}"]
    not_json = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_STDOUT=json.dumps("not json\n")))
    assert (not_json.returncode, not_json.stdout) == (0, b"not json\n")


@pytest.mark.parametrize("core", sorted(CORES))
def test_facts_with_nothing_to_resolve_print_core_s_own_bytes(tmp_path, core):
    """With no `file:` or `!` entry, `--facts` prints exactly the bytes core printed, so its layout is core's."""
    root = _project(tmp_path, core)
    skill = root / ".claude" / "skills" / SKILL
    skill.mkdir(parents=True)
    (skill / "customize.toml").write_bytes(b'[workflow]\nname = "default"\npersistent_facts = ["Cite sources."]\n')
    for keys in (("workflow",), ("workflow.persistent_facts",), ()):
        proc = _run(skill, root, *keys, facts=True)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == _core(root, "--skill", str(skill), *(w for key in keys for w in ("--key", key))).stdout


@pytest.mark.parametrize("core", sorted(CORES))
@pytest.mark.parametrize("stdout", ["not json\n", "", "[1, 2]\n", '"text"\n'], ids=["text", "empty", "list", "string"])
def test_facts_on_output_that_is_no_json_object_print_nothing(tmp_path, core, stdout):
    root = _project(tmp_path, core)
    skill = _installed_skill(root)
    proc = _run(skill, root, "workflow", env=_env(SKF_TEST_CORE_STDOUT=json.dumps(stdout)), facts=True)
    assert proc.returncode == 1
    assert proc.stdout == b""
    assert _stderr(proc).splitlines() == ["BMAD core's customization resolver printed no JSON object",
                                          "core's own note"]


@pytest.mark.parametrize("keys", [("workflow",), ("workflow.persistent_facts",), ()], ids=["table", "key", "whole"])
def test_facts_resolve_every_shape_core_prints(tmp_path, keys):
    root = _project(tmp_path, "6.12")
    skill = _installed_skill(root)
    docs = _context(root / "docs")
    proc = _run(skill, root, *keys, facts=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.decode("utf-8"))
    expected = [_file(docs), "Déployer sur AWS uniquement ✓"]
    if keys == ("workflow.persistent_facts",):
        assert data == {"workflow.persistent_facts": expected}
    else:
        assert data == {"workflow": {**MERGED, "persistent_facts": expected}}
    # In core's layout: two-space indent, the fact outside ASCII as UTF-8, a closing newline.
    assert proc.stdout == (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def test_facts_resolve_ferris_s_agent_table(tmp_path):
    root = _project(tmp_path, "6.12")
    skill = root / ".claude" / "skills" / SKILL
    skill.mkdir(parents=True)
    (skill / "customize.toml").write_bytes(b'[agent]\npersistent_facts = ["file:{project-root}/**/project-context.md"]\n')
    (root / "_bmad" / "custom" / f"{SKILL}.toml").write_bytes(
        b'[agent]\npersistent_facts = ["file:{project-root}/docs/style.md", "!file:{project-root}/docs/style.md"]\n')
    docs = _context(root / "docs")
    for keys, pick in ((("agent",), lambda d: d["agent"]["persistent_facts"]),
                       (("agent.persistent_facts",), lambda d: d["agent.persistent_facts"])):
        proc = _run(skill, root, *keys, facts=True)
        assert proc.returncode == 0, proc.stderr
        assert pick(json.loads(proc.stdout.decode("utf-8"))) == [_file(docs)]


def test_the_kickoff_loads_the_files_the_helper_names(tmp_path):
    """Campaign's load_facts runs the helper's own resolution: the same drop, the same files, in the same order."""
    kickoff = _load("campaign_render_kickoff_for_facts", KICKOFF)
    root = tmp_path / "project"
    files = [_context(root / sub, f"{sub} rule\n") for sub in ("b", "a/deep", "docs")]
    _context(root / "_bmad-output" / ".skf-run" / "x" / "source-1")
    _context(root / ".hidden")
    (root / "style.md").write_bytes(b"house style\n")
    entries = [DEFAULT_FACT, "Cite sources.", "file:{project-root}/style.md", "!file:{project-root}/style.md",
               "file:{project-root}/_bmad-output/.skf-run/**/project-context.md"]
    resolved = helper.resolve_facts(entries, root.as_posix())
    assert resolved == [_file(path) for path in sorted(files, key=lambda p: p.as_posix())] + ["Cite sources."]
    facts = kickoff.load_facts(entries, str(root))
    assert [fact.split("`")[1] if fact.startswith("From `") else fact for fact in facts] == [
        entry.removeprefix("file:") for entry in resolved]


def test_the_shared_resolution_unit_by_unit(tmp_path):
    assert helper.drop_entries(["One.", "Two.", "One.", "!One.", "One.", "!Gone."]) == ["Two.", "One."]
    # Anything but a `file:` string stays where it is, a value that is not a list included.
    assert helper.resolve_facts(["Cite.", 3, None, {"a": 1}], tmp_path.as_posix()) == ["Cite.", 3, None, {"a": 1}]
    data = {"workflow": {"persistent_facts": "file:{project-root}/x.md", "name": "w"}, "other": [1]}
    assert helper.resolve_output(json.loads(json.dumps(data)), tmp_path.as_posix(), print) == data
    # A strict caller (no on_problem) gets the reason as an exception.
    with pytest.raises(FileNotFoundError, match="names no file"):
        helper.resolve_facts(["file:{project-root}/missing.md"], tmp_path.as_posix())
    with pytest.raises(ValueError, match=r"\{project-root\}.*pass --project-root"):
        helper.resolve_facts([DEFAULT_FACT], None)
    notes = []
    assert helper.resolve_facts([DEFAULT_FACT], None, notes.append) == [DEFAULT_FACT] and len(notes) == 1
    # A root with glob characters is taken literally.
    odd = tmp_path / "proj [old]"
    ctx = _context(odd / "sub")
    assert helper.resolve_facts([DEFAULT_FACT], odd.as_posix()) == [_file(ctx)]


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
    assert (args.skill, args.project_root, args.key, args.facts) == ("s", "p", ["a", "b"], False)
    assert parser.parse_args(["--skill", "s", "--project-root", "p", "--key", "a", "--facts"]).facts is True
    proc = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, timeout=60,
                          env=_env(PYTHONIOENCODING="ascii"))
    assert proc.returncode == 0, proc.stderr
    proc.stdout.decode("ascii")
    assert HELPER.read_bytes().decode("ascii")
