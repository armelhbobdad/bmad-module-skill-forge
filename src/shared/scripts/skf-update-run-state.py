# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Update Run State: what an update-skill run wrote, so a halt can undo it.

An update writes the skill in one of two ways. A gap-driven repair edits the
current version in place (SKILL.md, references/, metadata.json and the
version's provenance map and evidence report, and for a rescope the skill
brief). Every other mode creates a new version folder and its forge folder
beside the unchanged previous version. Before the first write, merge.md
runs `begin`, which records in the run folder what the run is about to
change: for an in-place repair a snapshot of every file it may write, for a
new version the folders it creates. A HALT after that runs `rollback`,
which puts the skill back as it was: it restores the snapshot, or removes
the folders this run created. write.md runs `finish` once the run's writes
stand (after its last check), and from then on `rollback` changes
nothing. A run that died (its run lock went stale) never rolled
back: the next update's init.md hands the stale lock's owner to
`rollback --run-root --owner --remove-run-dir`, which finds that run's
folder by the run id in the owner. Every HALT of an update runs `halt`,
which does a halt's cleanup in one call.

CLI:

  uv run skf-update-run-state.py begin --run-dir <dir> --mode in-place \\
      --package <skill package> --forge-version <forge version folder> \\
      [--brief <skill-brief.yaml>]
  uv run skf-update-run-state.py begin --run-dir <dir> --mode new-version \\
      --created <folder> [--created <folder> ...] [--staging <folder>] \\
      [--skill-group <skill group>]
  uv run skf-update-run-state.py rollback --run-dir <dir> [--remove-run-dir]
  uv run skf-update-run-state.py rollback --run-root <.skf-run folder> \\
      --owner <the stale lock's owner> --skill <skill> --remove-run-dir
  uv run skf-update-run-state.py finish --run-dir <dir>
  uv run skf-update-run-state.py halt --run-dir <dir> [--tree <tree>] \\
      [--lock <lock file> --owner <owner>] [--emit] < <halt payload>

begin (in-place) copies the package folder to <run-dir>/snapshot/package
(each link copied as a link, never followed), the forge version folder's
provenance-map.json and evidence-report.md to <run-dir>/snapshot/forge/,
and the brief to <run-dir>/snapshot/skill-brief.yaml, noting which of the
files existed. begin (new-version) records each --created folder, which
must not exist yet (exit 3 names the first that does: a version is never
overwritten), and the --staging folder, which may (a staging folder an
interrupted run left is the stage step's to clear). Either way it writes
<run-dir>/run-state.json and refuses a run folder that already holds one.

rollback reads run-state.json. Nothing to do when there is none, when the
run finished, or when it already rolled back. In place, it rebuilds the
package from the snapshot beside it and swaps it in, restores each forge
file and the brief, and removes one the run created. For a new version it
removes each recorded folder, never a link; once the skill group's
`active` link names the run's version folder, that version is live and
every recorded folder is kept (each named, with the reason). With
--remove-run-dir it then deletes the run folder (an interrupted run's),
which must be `.skf-run/skf-update-skill-<run id>` with a run id that holds
no path separator and no `..` (exit 1 otherwise, before anything changes).
With --run-root and --owner in place of --run-dir, the run folder is
<run-root>/skf-update-skill-<run id>, the run id taken from an owner
`update-skill:<skill>:<run id>`; an owner of another workflow or another
skill, or one with no run id (an older SKF's lock), names no run folder
and changes nothing (status `no-run-folder`).

finish marks the run finished, then deletes the snapshot.

halt is a HALT's cleanup, in this order, never stopping on a result: the
rollback above when the run folder holds a run state; with --tree, the
private source tree removed (skf-source-tree.py close); with --lock and
--owner, the run lock released (skf-run-lock.py release, which never
removes a lock another run holds); with --emit, the halt payload read on
stdin printed through skf-emit-result-envelope.py emit-halt --workflow
skf-update-skill (with --run-dir when the folder still exists, so the
line carries the decisions and warnings the run recorded). Each step it
could not finish adds a warning to the payload's warnings[] (and to its
own output): `rollback-incomplete: <path>: <error>`,
`source-tree-not-removed: <tree> (<close status>)` and
`run-lock-not-released: <lock>`. The three helpers are read from beside
this script. Without --emit, stdin is not read.

Output: one JSON line,
  {"status": "began" | "exists" | "rolled-back" | "nothing-to-roll-back"
             | "already-rolled-back" | "finished" | "no-run-folder",
   "restored": [paths], "removed": [paths], "kept": [{"path", "why"}],
   "failed": [{"path", "error"}], "run_dir_removed": bool, "path": <exists>}
and for halt
  {"status": "halted", "rollback": <rollback's status, or "error">,
   "restored", "removed", "kept", "failed": as above,
   "tree": <close's status, or null>, "lock": "released" | "absent" |
   "not-owner" | "failed" | null, "warnings": [...], "emitted": bool}
followed, with --emit, by the emitter's SKF_UPDATE_RESULT_JSON line.

Exit codes:
  0  done (see status); halt: every step ran, its failures in warnings[]
  1  bad arguments, or a run-state.json that cannot be read or written;
     halt: a payload that is not a JSON object, or one the emitter refused
     (its message on stderr): fix the payload and run halt again, which
     redoes nothing already done
  2  a copy, restore or removal failed (each named in failed[]; rollback
     goes on with the rest)
  3  begin: a --created folder already exists
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

STATE = "run-state.json"
SNAPSHOT = "snapshot"
FORGE_FILES = ("provenance-map.json", "evidence-report.md")
TOOL = "skf-update-run-state"
EXIT_FAILED = 2
EXIT_EXISTS = 3
HERE = Path(__file__).resolve().parent
SOURCE_TREE_HELPER = HERE / "skf-source-tree.py"
RUN_LOCK_HELPER = HERE / "skf-run-lock.py"
EMITTER = HERE / "skf-emit-result-envelope.py"
WORKFLOW = "skf-update-skill"
OWNER_PREFIX = "update-skill"
HELPER_TIMEOUT_SEC = 120


def _out(status: str, **fields) -> dict:
    result = {"status": status, "restored": [], "removed": [], "kept": [], "failed": [],
              "run_dir_removed": False}
    result.update(fields)
    return result


def _make_writable(func, path, _exc) -> None:
    """rmtree's error handler: clear a read-only bit (Windows) and retry once."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable)
    else:  # pragma: no cover - Python 3.11
        shutil.rmtree(path, onerror=_make_writable)


def _remove(path: Path) -> None:
    """Remove a file, a link or a folder (the folder's content, never a link's target)."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        _rmtree(path)


def _copy_file(src: Path, dst: Path) -> None:
    """Copy src over dst through a temporary file and one rename."""
    tmp = dst.with_name(f".{dst.name}.skf-restore-tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _read_state(run_dir: Path) -> dict | None:
    path = run_dir / STATE
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.as_posix()}: {exc}") from exc
    if not isinstance(state, dict) or state.get("tool") != TOOL:
        raise ValueError(f"{path.as_posix()} is not a run state this helper wrote")
    return state


def _write_state(run_dir: Path, state: dict) -> None:
    path = run_dir / STATE
    tmp = run_dir / f".{STATE}.skf-tmp"
    try:
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise ValueError(f"cannot write {path.as_posix()}: {exc}") from exc


def _abs(path: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(path)))


# --------------------------------------------------------------------------
# begin
# --------------------------------------------------------------------------


def begin_in_place(run_dir: Path, package: Path, forge_version: Path, brief: Path | None) -> dict:
    if _read_state(run_dir) is not None:
        raise ValueError(f"{(run_dir / STATE).as_posix()} exists: this run already began writing")
    if not package.is_dir():
        raise ValueError(f"--package is not a folder: {package.as_posix()}")
    snap = run_dir / SNAPSHOT
    failed = []
    try:
        if snap.exists():
            _remove(snap)
        (snap / "forge").mkdir(parents=True)
        shutil.copytree(package, snap / "package", symlinks=True)
    except OSError as exc:
        return _out("began", failed=[{"path": package.as_posix(), "error": str(exc)}])
    forge_files = {}
    for name in FORGE_FILES:
        source = forge_version / name
        forge_files[name] = source.is_file()
        if source.is_file():
            try:
                shutil.copy2(source, snap / "forge" / name)
            except OSError as exc:
                failed.append({"path": source.as_posix(), "error": str(exc)})
    brief_existed = bool(brief and brief.is_file())
    if brief_existed:
        try:
            shutil.copy2(brief, snap / "skill-brief.yaml")
        except OSError as exc:
            failed.append({"path": brief.as_posix(), "error": str(exc)})
    if failed:
        return _out("began", failed=failed)
    _write_state(run_dir, {
        "tool": TOOL, "mode": "in-place", "finished": False, "rolled_back": False,
        "snapshot": {"package": package.as_posix(), "forge_version": forge_version.as_posix(),
                     "forge_files": forge_files, "brief": brief.as_posix() if brief else None,
                     "brief_existed": brief_existed},
        "created": [], "staging": None, "skill_group": None,
    })
    return _out("began")


def begin_new_version(run_dir: Path, created: list[Path], staging: Path | None, skill_group: Path | None) -> dict:
    if _read_state(run_dir) is not None:
        raise ValueError(f"{(run_dir / STATE).as_posix()} exists: this run already began writing")
    for path in created:
        if os.path.lexists(path):
            return _out("exists", path=path.as_posix())
    _write_state(run_dir, {
        "tool": TOOL, "mode": "new-version", "finished": False, "rolled_back": False, "snapshot": None,
        "created": [p.as_posix() for p in created], "staging": staging.as_posix() if staging else None,
        "skill_group": skill_group.as_posix() if skill_group else None,
    })
    return _out("began")


# --------------------------------------------------------------------------
# rollback and finish
# --------------------------------------------------------------------------


def _active_target(skill_group: str | None) -> Path | None:
    """The folder the group's `active` link resolves to, or None."""
    if not skill_group:
        return None
    link = Path(skill_group) / "active"
    try:
        return link.resolve(strict=True) if os.path.lexists(link) else None
    except OSError:
        return None


def _restore_in_place(run_dir: Path, snap_state: dict, result: dict) -> None:
    snap = run_dir / SNAPSHOT
    package = Path(snap_state["package"])
    copy = snap / "package"
    if copy.is_dir():
        fresh = package.with_name(f"{package.name}.skf-restore")
        aside = package.with_name(f"{package.name}.skf-rollback")
        try:
            for leftover in (fresh, aside):
                if os.path.lexists(leftover):
                    _remove(leftover)
            shutil.copytree(copy, fresh, symlinks=True)
            if os.path.lexists(package):
                os.replace(package, aside)
            os.replace(fresh, package)
            if os.path.lexists(aside):
                _remove(aside)
            result["restored"].append(package.as_posix())
        except OSError as exc:
            result["failed"].append({"path": package.as_posix(), "error": str(exc)})
    forge = Path(snap_state["forge_version"])
    for name, existed in (snap_state.get("forge_files") or {}).items():
        target = forge / name
        try:
            if existed:
                _copy_file(snap / "forge" / name, target)
                result["restored"].append(target.as_posix())
            elif os.path.lexists(target):
                _remove(target)
                result["removed"].append(target.as_posix())
        except OSError as exc:
            result["failed"].append({"path": target.as_posix(), "error": str(exc)})
    brief = snap_state.get("brief")
    if brief:
        target = Path(brief)
        try:
            if snap_state.get("brief_existed"):
                _copy_file(snap / "skill-brief.yaml", target)
                result["restored"].append(target.as_posix())
            elif os.path.lexists(target):
                _remove(target)
                result["removed"].append(target.as_posix())
        except OSError as exc:
            result["failed"].append({"path": target.as_posix(), "error": str(exc)})


def _remove_created(state: dict, result: dict) -> None:
    active = _active_target(state.get("skill_group"))
    paths = list(state.get("created") or [])
    if state.get("staging"):
        paths.append(state["staging"])
    live = active is not None and any(
        os.path.lexists(raw) and not Path(raw).is_symlink() and Path(raw).resolve() == active for raw in paths)
    for raw in paths:
        path = Path(raw)
        if not os.path.lexists(path):
            continue
        if path.is_symlink():
            result["kept"].append({"path": path.as_posix(), "why": "a link: this run never creates one"})
            continue
        if live:
            # The active link already names this run's version: it is live,
            # and so is its forge folder.
            why = "the active link names it" if path.resolve() == active else "the active link names its version"
            result["kept"].append({"path": path.as_posix(), "why": why})
            continue
        try:
            _remove(path)
            result["removed"].append(path.as_posix())
        except OSError as exc:
            result["failed"].append({"path": path.as_posix(), "error": str(exc)})


RUN_DIR_PREFIX = "skf-update-skill-"
RUN_ROOT_NAME = ".skf-run"


def _is_update_run_dir(run_dir: Path) -> bool:
    """True for `<...>/.skf-run/skf-update-skill-<run id>`: the only folder --remove-run-dir deletes.

    init.md builds the path from a run id it reads in a stale lock's owner;
    a run id holding a path separator or `..` must never reach a folder
    outside the run root.
    """
    name = run_dir.name
    run_id = name[len(RUN_DIR_PREFIX):]
    return (name.startswith(RUN_DIR_PREFIX) and bool(run_id) and run_dir.parent.name == RUN_ROOT_NAME
            and not any(ch in run_id for ch in "/\\") and ".." not in run_id)


def rollback(run_dir: Path, remove_run_dir: bool) -> dict:
    if remove_run_dir and not _is_update_run_dir(run_dir):
        raise ValueError(f"--remove-run-dir deletes only an update run folder (.skf-run/{RUN_DIR_PREFIX}<run id>), "
                         f"not {run_dir.as_posix()}")
    state = _read_state(run_dir)
    if state is None:
        result = _out("nothing-to-roll-back")
    elif state.get("finished"):
        result = _out("finished")
    elif state.get("rolled_back"):
        result = _out("already-rolled-back")
    else:
        result = _out("rolled-back")
        if state.get("mode") == "in-place" and isinstance(state.get("snapshot"), dict):
            _restore_in_place(run_dir, state["snapshot"], result)
        else:
            _remove_created(state, result)
        if not result["failed"]:
            _write_state(run_dir, {**state, "rolled_back": True})
    if remove_run_dir and not result["failed"] and run_dir.is_dir():
        try:
            _rmtree(run_dir)
            result["run_dir_removed"] = True
        except OSError as exc:
            result["failed"].append({"path": run_dir.as_posix(), "error": str(exc)})
    return result


def finish(run_dir: Path) -> dict:
    state = _read_state(run_dir)
    if state is None:
        raise ValueError(f"no {STATE} in {run_dir.as_posix()}: begin never ran")
    # Finished first: a crash before the snapshot goes leaves a finished run
    # whose writes stand, never an unfinished one with no snapshot to restore.
    _write_state(run_dir, {**state, "finished": True})
    snap = run_dir / SNAPSHOT
    failed = []
    if snap.exists():
        try:
            _remove(snap)
        except OSError as exc:
            failed.append({"path": snap.as_posix(), "error": str(exc)})
    return _out("finished", failed=failed)


def run_dir_of_owner(run_root: Path, owner: str, skill: str | None) -> Path | None:
    """The run folder an update's lock owner names, or None when it names none.

    An owner is `update-skill:<skill>:<run id>`; one of another workflow or
    skill, or with no run id (an older SKF's lock), has no run folder here.
    """
    parts = owner.split(":", 2) if isinstance(owner, str) else []
    if len(parts) != 3 or parts[0] != OWNER_PREFIX or not parts[2]:
        return None
    if skill is not None and parts[1] != skill:
        return None
    return run_root / f"{RUN_DIR_PREFIX}{parts[2]}"


# --------------------------------------------------------------------------
# halt
# --------------------------------------------------------------------------


def _call(helper: Path, args: list[str], stdin: str | None = None) -> tuple[int | None, str, str]:
    """Run a helper beside this script: (exit code, stdout, stderr); None when it could not run."""
    if not helper.is_file():
        return None, "", f"{helper.name} is missing beside {Path(__file__).name}; re-install SKF"
    try:
        proc = subprocess.run([sys.executable, str(helper), *args], input=stdin, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=HELPER_TIMEOUT_SEC)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", f"{helper.name}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _json_line(text: str) -> dict | None:
    for line in reversed(text.strip().splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no output")


def halt(run_dir: Path, tree: str | None, lock: str | None, owner: str | None) -> dict:
    """A HALT's cleanup: rollback, source tree, run lock. Never stops on a result."""
    result = {"status": "halted", "rollback": None, "restored": [], "removed": [], "kept": [], "failed": [],
              "tree": None, "lock": None, "warnings": [], "emitted": False}
    try:
        undone = rollback(run_dir, remove_run_dir=False)
    except ValueError as exc:
        result["rollback"] = "error"
        result["warnings"].append(f"rollback-incomplete: {exc}")
    else:
        result["rollback"] = undone["status"]
        for key in ("restored", "removed", "kept", "failed"):
            result[key] = undone[key]
        for item in undone["failed"]:
            result["warnings"].append(f"rollback-incomplete: {item['path']}: {item['error']}")
    if tree:
        code, out, err = _call(SOURCE_TREE_HELPER, ["close", "--tree", tree])
        closed = _json_line(out) if code == 0 else None
        result["tree"] = closed.get("status") if closed else "failed"
        if result["tree"] not in ("removed", "missing"):
            result["warnings"].append(f"source-tree-not-removed: {tree} "
                                      f"({result['tree'] if closed else _first_line(err)})")
    if lock and owner:
        code, out, err = _call(RUN_LOCK_HELPER, ["release", "--lock", lock, "--owner", owner])
        released = _json_line(out) if code == 0 else None
        if released is None:
            result["lock"] = "failed"
            result["warnings"].append(f"run-lock-not-released: {lock}")
        else:
            result["lock"] = "released" if released.get("released") else released.get("reason") or "absent"
    return result


def emit_halt(run_dir: Path, payload: dict, warnings: list[str]) -> tuple[int, str, str]:
    """Print the halt's line through the shared emitter: (exit code, its stdout, its stderr)."""
    listed = payload.get("warnings")
    payload = {**payload, "warnings": [*(listed if isinstance(listed, list) else []), *warnings]}
    args = ["emit-halt", "--workflow", WORKFLOW]
    if run_dir.is_dir():
        args += ["--run-dir", str(run_dir)]
    code, out, err = _call(EMITTER, args, stdin=json.dumps(payload))
    return (1 if code is None else code), out, err


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-update-run-state",
        description="Record what an update-skill run writes, undo it on a halt, and close the window "
                    "once the writes stand.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_begin = sub.add_parser("begin", help="record what the run is about to write (before the first write)")
    p_begin.add_argument("--run-dir", required=True, help="the run folder")
    p_begin.add_argument("--mode", required=True, choices=("in-place", "new-version"),
                         help="in-place (a gap-driven repair) or new-version (every other mode)")
    p_begin.add_argument("--package", help="in-place: the skill package folder to snapshot")
    p_begin.add_argument("--forge-version", help="in-place: the version's forge folder")
    p_begin.add_argument("--brief", help="in-place: the skill brief a rescope amends")
    p_begin.add_argument("--created", action="append", default=[],
                         help="new-version: a folder the run creates (repeat); it must not exist yet")
    p_begin.add_argument("--staging", help="new-version: the staging folder, removed with the rest")
    p_begin.add_argument("--skill-group", help="new-version: the skill group, whose active link is never removed")

    p_rollback = sub.add_parser("rollback", help="undo what the run wrote, unless it finished")
    p_rollback.add_argument("--run-dir", help="the run folder")
    p_rollback.add_argument("--run-root", help="in place of --run-dir: the .skf-run folder, with --owner")
    p_rollback.add_argument("--owner", help="with --run-root: the stale lock's owner, update-skill:<skill>:<run id>")
    p_rollback.add_argument("--skill", help="with --run-root: the skill the owner must name")
    p_rollback.add_argument("--remove-run-dir", action="store_true",
                            help="then delete the run folder (an interrupted run's)")

    p_finish = sub.add_parser("finish", help="the writes stand: close the rollback window, drop the snapshot")
    p_finish.add_argument("--run-dir", required=True, help="the run folder")

    p_halt = sub.add_parser("halt", help="a HALT's cleanup: rollback, source tree, run lock, then the halt's line")
    p_halt.add_argument("--run-dir", required=True, help="the run folder")
    p_halt.add_argument("--tree", help="the private source tree to remove (skf-source-tree.py open's tree)")
    p_halt.add_argument("--lock", help="the run lock file to release, with --owner")
    p_halt.add_argument("--owner", help="the run lock's owner, as acquire printed it")
    p_halt.add_argument("--emit", action="store_true",
                        help="read the halt payload on stdin and print its line through the shared emitter")
    return parser


def _cmd_halt(args: argparse.Namespace, run_dir: Path) -> int:
    if bool(args.lock) != bool(args.owner):
        raise ValueError("--lock and --owner go together")
    payload = None
    if args.emit:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            raise ValueError(f"the halt payload on stdin is not JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("the halt payload on stdin must be a JSON object")
    result = halt(run_dir, args.tree, args.lock, args.owner)
    if payload is None:
        print(json.dumps(result))
        return 0
    code, out, err = emit_halt(run_dir, payload, result["warnings"])
    result["emitted"] = code == 0
    print(json.dumps(result))
    sys.stdout.write(out)
    sys.stdout.flush()
    if err:
        sys.stderr.write(err)
    return 0 if code == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "rollback" and args.run_root:
            if args.run_dir or not args.owner:
                raise ValueError("--run-root takes --owner (and --skill), in place of --run-dir")
            found = run_dir_of_owner(_abs(args.run_root), args.owner, args.skill)
            if found is None:
                print(json.dumps(_out("no-run-folder")))
                return 0
            run_dir = found
        elif args.cmd == "rollback" and (not args.run_dir or args.owner or args.skill):
            raise ValueError("rollback takes --run-dir, or --run-root with --owner")
        else:
            run_dir = _abs(args.run_dir)
        if args.cmd == "halt":
            return _cmd_halt(args, run_dir)
        if args.cmd == "begin":
            if not run_dir.is_dir():
                raise ValueError(f"--run-dir is not a folder: {run_dir.as_posix()}")
            if args.mode == "in-place":
                if not args.package or not args.forge_version or args.created or args.staging:
                    raise ValueError("--mode in-place takes --package and --forge-version (and --brief)")
                result = begin_in_place(run_dir, _abs(args.package), _abs(args.forge_version),
                                        _abs(args.brief) if args.brief else None)
            else:
                if not args.created or args.package or args.forge_version or args.brief:
                    raise ValueError("--mode new-version takes --created (and --staging, --skill-group)")
                result = begin_new_version(run_dir, [_abs(p) for p in args.created],
                                           _abs(args.staging) if args.staging else None,
                                           _abs(args.skill_group) if args.skill_group else None)
        elif args.cmd == "rollback":
            result = rollback(run_dir, args.remove_run_dir)
        else:
            result = finish(run_dir)
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    if result["status"] == "exists":
        return EXIT_EXISTS
    return EXIT_FAILED if result["failed"] else 0


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
