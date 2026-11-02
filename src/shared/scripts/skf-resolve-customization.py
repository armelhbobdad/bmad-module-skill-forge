# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Resolve Customization: BMAD core's customization resolver, on any core from 6.4.0.

Every SKF workflow, and Ferris, reads its `_bmad/custom/` overrides through
BMAD core's customization resolver, `_bmad/scripts/resolve_customization.py`
under the project root, which the BMAD Method installer adds. SKF passes it
`--project-root`, a flag core takes only from 6.11.0: core 6.4.0 to 6.10.0
stops on it with argparse's exit 2, so SKF runs this helper in its place.
It takes core's long flags only (core's -s, -p and -k are refused):

  uv run skf-resolve-customization.py --skill <skill-root> \\
      --project-root <project-root> --key <key> [--key <key>]...

1. It runs core's resolver with those arguments, `--project-root` included,
   under its own interpreter, from the project root. `uv run` gives this
   file a Python that meets its requires-python, which core needs for
   `tomllib`; core 6.10.0 and earlier declare none, so uv would not choose
   one for them.
2. When core rejects `--project-root` (exit 2, nothing on stdout, and
   `error: unrecognized arguments: ... --project-root` on stderr), it works
   out the root a core before 6.11.0 picks without the flag: the nearest
   folder, from the skill folder up and the skill folder itself first, that
   holds `_bmad` or `.git` (a file or a folder), else the same search from
   the project root. When that is the project root, it runs core again
   without the flag, and that run's result is the helper's. Otherwise core
   would read another folder's overrides, so it refuses.

Output:
  stdout  on exit 0, core's stdout byte for byte (the JSON core prints);
          on any other exit, nothing.
  stderr  the stderr of the core run whose result is the helper's: on a
          rerun without the flag, the rerun's only (the rejected call's is
          dropped). A failure of the helper's own prints one line first: the
          reason a workflow's warning quotes.

Exit codes:
  0  core resolved the customization
  1  core's resolver is missing (first stderr line: `not found`), could
     not start, did not finish or was stopped by a signal, or core exited 1
     (a customize.toml or an override it cannot read)
  2  a core before 6.11.0 would read the overrides under another folder
     (first stderr line: `BMAD core before 6.11.0: ...`), a usage error of
     the helper's, or core's own exit 2 (a core from 6.11.0), passed through
  3  core found no Python 3.11 or later (`tomllib`)
  Any other exit code is core's own, passed through.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

CORE_RESOLVER = ("_bmad", "scripts", "resolve_customization.py")
FIRST_CORE_WITH_FLAG = "6.11.0"
CORE_TIMEOUT_SEC = 120
PROJECT_ROOT_FLAG = "--project-root"
MISSING = "not found"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# argparse's line for a flag it does not know, wherever the usage line wraps.
REJECTED_FLAG_RE = re.compile(r"error: unrecognized arguments: (?:.*\s)?--project-root(?:[=\s]|$)", re.M)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-resolve-customization",
        description=(
            "Run BMAD core's customization resolver with --project-root. On a core before "
            f"{FIRST_CORE_WITH_FLAG}, which rejects that flag, run it again without the flag when "
            "core would read this project's overrides anyway, and refuse otherwise."
        ),
    )
    parser.add_argument("--skill", required=True, help="the skill folder that holds customize.toml")
    parser.add_argument(
        "--project-root",
        required=True,
        help="the project folder: core's resolver is under its _bmad/scripts/, the overrides under _bmad/custom/",
    )
    parser.add_argument(
        "--key",
        action="append",
        default=[],
        help="a dotted key to resolve, repeatable; with none, core prints the whole merge",
    )
    return parser


def _nearest_marked(start: Path) -> Path | None:
    """The nearest folder, `start` itself first, holding `_bmad` or `.git` (a file or a folder)."""
    current = start.resolve()
    while True:
        if (current / "_bmad").exists() or (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def legacy_project_root(skill: Path, cwd: Path) -> Path | None:
    """The project root BMAD core 6.4.0 to 6.10.0 picks without --project-root, run from `cwd`."""
    return _nearest_marked(skill) or _nearest_marked(cwd)


def _same_folder(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return a.resolve() == b.resolve()


def rejects_project_root(returncode: int, stdout: bytes, stderr: bytes) -> bool:
    """True when core stopped on --project-root as a flag it does not know; never on exit 2 alone."""
    if returncode != 2 or stdout:
        return False
    text = ANSI_RE.sub("", stderr.decode("utf-8", "replace"))
    return REJECTED_FLAG_RE.search(text) is not None


def _run_core(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Core 6.11.0 and later import config_utils from their own folder, which a safe path drops.
    env.pop("PYTHONSAFEPATH", None)
    # Core before 6.8.0 writes its JSON in the locale's encoding.
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        timeout=CORE_TIMEOUT_SEC, check=False,
    )


def _write(stream, data: bytes) -> None:
    if not data:
        return
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        stream.write(data.decode("utf-8", "replace"))
        stream.flush()
        return
    buffer.write(data)
    buffer.flush()


def _say(*lines: str) -> None:
    _write(sys.stderr, "".join(line + "\n" for line in lines).encode("utf-8"))


def _finish(proc: subprocess.CompletedProcess) -> int:
    """Core's result as the helper's: its stdout only on exit 0, its stderr always."""
    if proc.returncode < 0:  # stopped by a signal: core may have printed no reason
        _say(f"BMAD core's customization resolver was stopped by signal {-proc.returncode}")
        _write(sys.stderr, proc.stderr)
        return 1
    if proc.returncode == 0:
        _write(sys.stdout, proc.stdout)
    _write(sys.stderr, proc.stderr)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(os.path.abspath(args.project_root))
    skill = Path(os.path.abspath(args.skill))
    core = root.joinpath(*CORE_RESOLVER)
    if not core.is_file():
        _say(MISSING, f"BMAD core's customization resolver is not at {core}: the BMAD Method installer adds it.")
        return 1
    command = [sys.executable, str(core), "--skill", str(skill)]
    keys = [word for key in args.key for word in ("--key", key)]
    try:
        first = _run_core([*command, PROJECT_ROOT_FLAG, str(root), *keys], root)
        if not rejects_project_root(first.returncode, first.stdout, first.stderr):
            return _finish(first)
        legacy = legacy_project_root(skill, root)
        if legacy is not None and _same_folder(legacy, root):
            return _finish(_run_core([*command, *keys], root))
    except subprocess.TimeoutExpired:
        _say(f"BMAD core's customization resolver did not finish within {CORE_TIMEOUT_SEC} seconds")
        return 1
    except OSError as exc:
        _say(f"BMAD core's customization resolver could not start: {exc}")
        return 1
    _say(
        f"BMAD core before {FIRST_CORE_WITH_FLAG}: its customization resolver takes no {PROJECT_ROOT_FLAG} "
        f"and would read the overrides under {legacy}, not under {root}; upgrade BMAD core to "
        f"{FIRST_CORE_WITH_FLAG} or later"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
