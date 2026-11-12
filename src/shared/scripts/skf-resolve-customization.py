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
      --project-root <project-root> --key <key> [--key <key>]... [--facts]

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
3. With `--facts`, it resolves `persistent_facts` in core's JSON, under a
   `workflow` or `agent` table or as a `workflow.persistent_facts` or
   `agent.persistent_facts` key, since core's merge only appends: each `!`
   entry is removed with every earlier entry equal to what follows its `!`;
   each other `file:` entry gets the project root for `{project-root}` and
   becomes one `file:<path>` entry per file it names, the path itself or
   each file its glob (`*`, `?`, `[`) matches, sorted, so a glob that
   matches nothing goes. The glob is matched one name at a time by a walk
   of the folders: a wildcard never matches a name that starts with `.`,
   so a `**` never enters a hidden folder, and the walk never enters a
   folder reached through a directory link (one the pattern spells out
   may be a link). No file under `<project-root>/_bmad-output/.skf-run/`,
   where a halted run keeps its source clones, is ever named, and each
   file is named once, at the first entry that names it. An entry it
   cannot resolve (a path with no glob character that names no file, a
   placeholder other than `{project-root}`) stays as written, with the root
   in place of `{project-root}`, and stderr says why in a
   `persistent_facts: <reason>` line. Campaign's kickoff script loads its
   facts with the same functions.

Output:
  stdout  on exit 0, core's stdout byte for byte (the JSON core prints), or
          with `--facts` that JSON with `persistent_facts` resolved, in core's
          layout (two-space indent, UTF-8, a closing newline), except that a
          path that is not UTF-8 goes out as its own bytes; on any other
          exit, nothing.
  stderr  the stderr of the core run whose result is the helper's: on a
          rerun without the flag, the rerun's only (the rejected call's is
          dropped). A failure of the helper's own prints one line first: the
          reason a workflow's warning quotes. With `--facts`, one
          `persistent_facts: <reason>` line follows for each entry kept as
          written.

Exit codes:
  0  core resolved the customization
  1  core's resolver is missing (first stderr line: `not found`), could
     not start, did not finish or was stopped by a signal, or core exited 1
     (a customize.toml or an override it cannot read); with `--facts`, core
     printed no JSON object (first stderr line: `BMAD core's customization
     resolver printed no JSON object`)
  2  a core before 6.11.0 would read the overrides under another folder
     (first stderr line: `BMAD core before 6.11.0: ...`), a usage error of
     the helper's, or core's own exit 2 (a core from 6.11.0), passed through
  3  core found no Python 3.11 or later (`tomllib`)
  Any other exit code is core's own, passed through.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePath
from typing import Any, Callable, Iterator

CORE_RESOLVER = ("_bmad", "scripts", "resolve_customization.py")
FIRST_CORE_WITH_FLAG = "6.11.0"
CORE_TIMEOUT_SEC = 120
PROJECT_ROOT_FLAG = "--project-root"
MISSING = "not found"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# argparse's line for a flag it does not know, wherever the usage line wraps.
REJECTED_FLAG_RE = re.compile(r"error: unrecognized arguments: (?:.*\s)?--project-root(?:[=\s]|$)", re.M)
# persistent_facts entries: `file:<path-or-glob>` loads files, `!<entry>` drops the earlier entries equal to <entry>.
FILE_PREFIX = "file:"
DROP_PREFIX = "!"
PROJECT_ROOT = "{project-root}"
GLOB_CHARS = ("*", "?", "[")
# A glob part that matches any number of folders, and a glob character escaped as glob.escape writes it.
ANY_FOLDERS = "**"
ESCAPED_RE = re.compile(r"\[([*?[])\]")
# A placeholder left in a `file:` entry would match no file.
UNRESOLVED_RE = re.compile(r"\{[A-Za-z][\w-]*\}")
# Where a halted run keeps its source clones, whose project-context.md files are not this project's.
RUN_FOLDER = ("_bmad-output", ".skf-run")
FACTS_TABLES = ("workflow", "agent")
NO_JSON = "BMAD core's customization resolver printed no JSON object"


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
    parser.add_argument(
        "--facts",
        action="store_true",
        help=(
            "resolve persistent_facts in core's output: drop each ! entry and the earlier entries it names, and "
            "turn each file: entry into one file:<path> entry per file it names, none under "
            "_bmad-output/.skf-run/"
        ),
    )
    return parser


# --------------------------------------------------------------------------
# persistent_facts: the `!` drop and the `file:` expansion core's merge lacks
# --------------------------------------------------------------------------


def drop_entries(entries: list) -> list:
    """The entries with each `!` entry removed, and with it every earlier entry equal to what follows its `!`."""
    kept: list = []
    for entry in entries:
        if isinstance(entry, str) and entry.startswith(DROP_PREFIX):
            dropped = entry[len(DROP_PREFIX):]
            kept = [earlier for earlier in kept if earlier != dropped]
        else:
            kept.append(entry)
    return kept


def _real(path: Path) -> Path:
    """The path with its links followed, or made absolute when a link loops."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return Path(os.path.abspath(path))


def in_run_folder(path: Path, root: str | None) -> bool:
    """True when path, its links followed, is under <root>/_bmad-output/.skf-run/."""
    if not root:
        return False
    return _real(path).is_relative_to(_real(Path(root).joinpath(*RUN_FOLDER)))


def _is_wild(part: str) -> bool:
    """True when one part of a glob holds a wildcard that is not escaped."""
    return any(c in ESCAPED_RE.sub("", part) for c in GLOB_CHARS)


def _name_matches(part: str, name: str) -> bool:
    """True when one name matches one part of a glob; a wildcard never matches a name that starts with `.`."""
    if part == ANY_FOLDERS:
        return not name.startswith(".")
    return (part.startswith(".") or not name.startswith(".")) and fnmatch.fnmatch(name, part)


def _closure(parts: tuple[str, ...], states: set[int] | frozenset[int]) -> frozenset[int]:
    """The states, each with the states a `**` that matches no folder lets it skip to."""
    reached: set[int] = set()
    for i in states:
        reached.add(i)
        while i < len(parts) and parts[i] == ANY_FOLDERS:
            i += 1
            reached.add(i)
    return frozenset(reached)


def _inside(parts: tuple[str, ...], states: frozenset[int], name: str, linked: bool) -> frozenset[int]:
    """The parts still to match inside a folder called name, as states (an index into parts).

    A `**` or a wildcard steps into a real folder only; a part that spells
    the name out steps into a linked folder too. The last part names a file,
    so it never steps into a folder, unless it is `**`.
    """
    last = len(parts) - 1
    reached: set[int] = set()
    for i in states:
        if i > last:
            continue
        part = parts[i]
        if part == ANY_FOLDERS:
            if not linked and _name_matches(part, name):
                reached.add(i)
        elif i < last and not (linked and _is_wild(part)) and _name_matches(part, name):
            reached.add(i + 1)
    return _closure(parts, reached)


def _linked(path: str) -> bool:
    """True for a link (a Windows junction too)."""
    isjunction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or (isjunction is not None and isjunction(path))


def _walk(base: str, parts: tuple[str, ...], states: frozenset[int], run_folder: Path | None) -> Iterator[str]:
    """Each file under base that parts match from states.

    os.walk never follows a link, and _walk walks a linked folder on its own
    only when a part spells its name out, so a link back up the tree never
    loops. Neither enters run_folder.
    """
    if run_folder is not None and _real(Path(base)).is_relative_to(run_folder):
        return
    last = len(parts) - 1
    pending = {base: states}
    for folder, folders, files in os.walk(base, followlinks=False):
        here = pending.pop(folder, frozenset())
        if last in here:
            for name in files:
                path = os.path.join(folder, name)
                if _name_matches(parts[last], name) and os.path.isfile(path):
                    yield path
        entered = []
        for name in folders:
            path = os.path.join(folder, name)
            if run_folder is not None and name == run_folder.name and _real(Path(path)) == run_folder:
                continue
            linked = _linked(path)
            inside = _inside(parts, here, name, linked)
            if not inside:
                continue
            if linked:
                yield from _walk(path, parts, inside, run_folder)
            else:
                pending[path] = inside
                entered.append(name)
        folders[:] = entered


def _glob_files(pattern: str, root: str | None) -> list[Path]:
    """Every file a glob matches, sorted, walked from the folder its leading parts with no wildcard name."""
    parts = PurePath(pattern).parts
    first_wild = next((i for i, part in enumerate(parts) if _is_wild(part)), len(parts))
    base = Path(*(ESCAPED_RE.sub(r"\1", part) for part in parts[:first_wild]))
    if first_wild == len(parts):  # each glob character is escaped: the pattern names one path
        return [base] if base.is_file() else []
    rest = parts[first_wild:]
    run_folder = _real(Path(root).joinpath(*RUN_FOLDER)) if root else None
    return [Path(p) for p in sorted(_walk(str(base), rest, _closure(rest, {0}), run_folder))]


def fact_files(entry: str, root: str | None) -> list[Path]:
    """The files a `file:` entry names: the path itself, else every file its glob matches, sorted.

    `{project-root}` becomes root, escaped where it joins a glob. The glob is
    matched by _walk, which enters no hidden folder unless a part names it,
    no folder reached through a directory link unless a part spells it out,
    and never <root>/_bmad-output/.skf-run/; no file there is named, links
    followed. Raises ValueError on an entry that keeps a placeholder
    (`{project-root}` too when root is None), and FileNotFoundError on a path
    with no glob character that names no file; a glob that matches nothing
    names none.
    """
    pattern = entry[len(FILE_PREFIX):].strip()
    placeholder = UNRESOLVED_RE.search(pattern if root is None else pattern.replace(PROJECT_ROOT, ""))
    if placeholder:
        hint = "; pass --project-root" if placeholder.group(0) == PROJECT_ROOT else ""
        raise ValueError(f"`{entry}` holds the unresolved placeholder `{placeholder.group(0)}`{hint}")
    path = Path(pattern.replace(PROJECT_ROOT, root or ""))
    if path.is_file():
        found = [path]
    elif not any(c in pattern for c in GLOB_CHARS):
        raise FileNotFoundError(f"`{entry}` names no file ({path.as_posix()})")
    else:
        found = _glob_files(pattern.replace(PROJECT_ROOT, glob.escape(root or "")), root)
    return [p for p in found if not in_run_folder(p, root)]


def resolve_facts(entries: list, root: str | None, on_problem: Callable[[str], None] | None = None) -> list:
    """persistent_facts with each `!` entry applied and each `file:` entry turned into one `file:<path>` per file.

    Each file, its links followed, is named once, where the first entry that
    names it put it. Any other entry, a string or not, stays where it is.
    With on_problem None an entry that cannot be resolved raises, as
    fact_files does; otherwise it stays as written, with root in place of
    `{project-root}`, and on_problem gets the reason.
    """
    resolved: list = []
    named: set[Path] = set()
    for entry in drop_entries(entries):
        if not (isinstance(entry, str) and entry.startswith(FILE_PREFIX)):
            resolved.append(entry)
            continue
        try:
            files = fact_files(entry, root)
        except (OSError, ValueError) as exc:
            if on_problem is None:
                raise
            on_problem(str(exc))
            resolved.append(entry.replace(PROJECT_ROOT, root) if root else entry)
            continue
        for path in files:
            real = _real(path)
            if real not in named:
                named.add(real)
                resolved.append(FILE_PREFIX + path.as_posix())
    return resolved


def resolve_output(data: dict, root: str, on_problem: Callable[[str], None]) -> dict:
    """Core's JSON with each persistent_facts list it holds resolved; any other value is left as it is."""
    for table in FACTS_TABLES:
        section = data.get(table)
        if isinstance(section, dict) and isinstance(section.get("persistent_facts"), list):
            section["persistent_facts"] = resolve_facts(section["persistent_facts"], root, on_problem)
        key = f"{table}.persistent_facts"
        if isinstance(data.get(key), list):
            data[key] = resolve_facts(data[key], root, on_problem)
    return data


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


def _resolved_stdout(stdout: bytes, root: Path, notes: list[str]) -> bytes | None:
    """Core's stdout with persistent_facts resolved, in core's layout, or None when it holds no JSON object."""
    try:
        data = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data = resolve_output(data, root.as_posix(), lambda reason: notes.append(f"persistent_facts: {reason}"))
    # A folder name that is not UTF-8 reaches a path as surrogates, which go back out as its own bytes.
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8", errors="surrogateescape")


def _finish(proc: subprocess.CompletedProcess, facts_root: Path | None = None) -> int:
    """Core's result as the helper's: its stdout only on exit 0, its stderr always.

    With facts_root (`--facts`), stdout is core's JSON with persistent_facts
    resolved from that project root, and a reason line follows core's stderr
    for each entry kept as written.
    """
    if proc.returncode < 0:  # stopped by a signal: core may have printed no reason
        _say(f"BMAD core's customization resolver was stopped by signal {-proc.returncode}")
        _write(sys.stderr, proc.stderr)
        return 1
    if proc.returncode != 0 or facts_root is None:
        if proc.returncode == 0:
            _write(sys.stdout, proc.stdout)
        _write(sys.stderr, proc.stderr)
        return proc.returncode
    notes: list[str] = []
    stdout = _resolved_stdout(proc.stdout, facts_root, notes)
    if stdout is None:
        _say(NO_JSON)
        _write(sys.stderr, proc.stderr)
        return 1
    _write(sys.stdout, stdout)
    _write(sys.stderr, proc.stderr)
    _say(*notes)
    return 0


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
    facts_root = root if args.facts else None
    try:
        first = _run_core([*command, PROJECT_ROOT_FLAG, str(root), *keys], root)
        if not rejects_project_root(first.returncode, first.stdout, first.stderr):
            return _finish(first, facts_root)
        legacy = legacy_project_root(skill, root)
        if legacy is not None and _same_folder(legacy, root):
            return _finish(_run_core([*command, *keys], root), facts_root)
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
