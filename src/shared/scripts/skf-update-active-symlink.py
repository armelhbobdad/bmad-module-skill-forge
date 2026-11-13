# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Update Active Symlink — atomic + idempotent + verified flip of
{skill_group}/active to point at a target version directory.

update-skill's `write.md` (its active-link step) previously asked the LLM to
"create or update the active symlink at {skill_group}/active pointing
to the new {version}; if the symlink already exists, remove it first
and recreate". That two-step (`rm` then `ln`) leaves a brief window
where the symlink doesn't exist — readers that resolve `active`
mid-update see a `FileNotFoundError`. A second check then re-reads the symlink
to verify it points where expected and halts on divergence.

This helper consolidates the two steps into one workflow-specific
invocation:

  - holds {skill-group}/active.skf-lock, the lock skf-atomic-write.py
    flip-link takes, from the read through the re-read, so one flip of
    the link runs at a time; while another flip holds it, waits up to
    FLIP_LOCK_WAIT_SECONDS, then returns busy without touching the link
  - detects whether a flip is required (idempotent: already pointing
    at the target → no-op)
  - performs the flip through skf-atomic-write.py's replace_link, the
    code flip-link runs (link at a temp name → os.replace), so on POSIX
    concurrent readers never see a missing symlink
  - verifies the post-state and surfaces ok / flipped / mismatch
    / missing-target / busy

Three subcommands:

  update --skill-group <path> --version <name>
      Make {skill-group}/active point at {version}. Atomic.
      Idempotent: returns status=ok with action=no-op when the link
      already points there.

  verify --skill-group <path> --version <name>
      Read-only: check that {skill-group}/active currently points at
      {version}. Used by step-06 derived-artifact verification.

  repair-after-drop --skill-group <path> --dropped <version>
      Drop Skill's repair after a version purge deleted {skill-group}/
      {dropped}. It reads the export manifest beside {skill-group} through
      skf-skill-inventory.py and picks the replacement (pick_new_active):
      the manifest's active_version unless it is null, deprecated, the
      dropped version or not on disk; else the newest manifest version that
      is not deprecated, is on disk and is not the dropped one; else none.
      Then, holding the flip lock, it reads the link and acts only when it
      names {dropped} (a stored `...\\<group>\\<dropped>` path counts, as a
      Windows junction whose folder is gone reads back): it points the link
      at the replacement, or removes it when there is none. A link that
      names anything else, and no link, are left alone.

      Output JSON (stdout): {"action": "none" | "flipped" | "unlinked" |
      "failed", "link_target": what the link named, or null, "new_active":
      the version it points at now (the one it was to point at when the
      action failed), or null, "manual_fix": null, or on a failure the one
      command that repairs the link by hand, "error": null, or what failed}.
      Every manual fix runs skf-atomic-write.py flip-link (or `rm` for a
      link to remove) after "if `active` still names <dropped>, ", with
      "once the other run has finished, " before it when another flip held
      the lock, else with the error after it in parentheses.

The target version directory (`{skill-group}/{version}/`) MUST exist
on disk before this script is called. The helper refuses to point
the symlink at a path that doesn't resolve — a dangling `active`
silently breaks downstream consumers that expect it to resolve.

Output JSON (stdout):
  {
    "status": "ok" | "flipped" | "mismatch" | "missing-target" | "busy",
    "skill_group": "<abs path>",
    "active_link": "<abs path to active>",
    "expected_target": "<version>",
    "current_target": "<previous target>" | null,
    "action_taken": "no-op" | "flipped" | "halt",
    "log_message": "...",
    "halt_message": "<multi-line user message>" | null
  }

Exit codes:
  0: ok (already correct) or flipped (just updated)
  1: script error, one `error:` line on stderr and nothing on stdout
     (group path invalid, a real folder or file at {skill-group}/active,
     skf-atomic-write.py not loadable from this script's folder, or the
     link could not be moved); argparse exits 2 on bad arguments
  2: mismatch (verify mode and target diverges), missing-target
     (the {version} directory doesn't exist; caller must halt), or
     busy (update: another flip held the link's lock for the whole
     wait; the link is unchanged, caller must halt)

repair-after-drop exits 0 for none, flipped and unlinked, and 2 with its
JSON for failed: once it has picked the replacement, every failure (the
lock held past FLIP_LOCK_WAIT_SECONDS, a lock or flip error, a link that
names something else after the flip) leaves a manual_fix. It exits 1 with
one `error:` line on stderr and nothing on stdout when it fails before
that: the group is not a folder, skf-skill-inventory.py or
skf-atomic-write.py cannot be loaded from this script's folder, or the
manifest cannot be read. A manifest it cannot read never leads to an
unlink: the link is left as it is.

Platform: Linux, macOS and native Windows, as skf-atomic-write.py's
flip-link. On Windows the flip removes the old link first whenever the
rename over it is refused, which it always is over a directory link, so
it is not atomic there; without symlink privilege the new link is a
directory junction. A junction reads back as the name of the version folder it
resolves to, so `ok` means the link names {version} whichever kind it is.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


ACTIVE_NAME = "active"
ATOMIC_WRITE_HELPER = Path(__file__).resolve().parent / "skf-atomic-write.py"
# repair-after-drop reads the manifest's versions through it, loaded only by that subcommand.
INVENTORY_HELPER = Path(__file__).resolve().parent / "skf-skill-inventory.py"
# What the inventory helper raises on a manifest or a folder it cannot read as it expects.
INVENTORY_ERRORS = (AttributeError, TypeError, ValueError, OSError)
# The prefix of a manual fix when another flip held the lock.
BUSY_PREFIX = "once the other run has finished, "
# A flip holds <link>.skf-lock for well under a millisecond, so update waits
# this long for another flip to let it go before it returns busy.
FLIP_LOCK_WAIT_SECONDS = 5.0


def _load_atomic_write():
    """Load skf-atomic-write.py, which installs into the same folder as this script."""
    try:
        spec = importlib.util.spec_from_file_location("skf_atomic_write", ATOMIC_WRITE_HELPER)
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as e:
        raise OSError(f"cannot load the flip-lock helper {ATOMIC_WRITE_HELPER}: {e}") from e
    return module


def _load_inventory():
    """Load skf-skill-inventory.py, which installs into the same folder as this script."""
    try:
        spec = importlib.util.spec_from_file_location("skf_skill_inventory", INVENTORY_HELPER)
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as e:
        raise OSError(f"cannot load the inventory helper {INVENTORY_HELPER}: {e}") from e
    return module


# --------------------------------------------------------------------------
# Symlink primitives
# --------------------------------------------------------------------------


def read_link_target(link_path: Path) -> str | None:
    """Return what the link at `link_path` names, or None if nothing is there.

    A symlink gives its stored target (`1.6.2` for the links SKF makes). A
    Windows junction, which Path.is_symlink() does not report and whose
    os.readlink is an absolute `\\\\?\\` path, gives the name of the folder it
    resolves to when that folder sits beside it, else its stored path (a
    junction whose folder is gone, one that leads elsewhere, or a loop). Raises
    ValueError if `link_path` exists but is not a link (someone replaced it
    with a regular dir/file)."""
    if not os.path.lexists(link_path):
        return None
    if link_path.is_symlink():
        return os.readlink(link_path)
    try:
        stored = os.readlink(link_path)
    except (OSError, ValueError):
        raise ValueError(
            f"{link_path} exists but is not a symlink — refusing to overwrite "
            "(manual recovery required)"
        ) from None
    try:
        resolved = link_path.resolve(strict=True)
    except (OSError, RuntimeError):  # Python 3.11 and 3.12 raise RuntimeError on a loop
        return stored
    if resolved.parent == link_path.parent.resolve():
        return resolved.name
    return stored


def atomic_flip_symlink(link_path: Path, target_name: str) -> None:
    """Point `link_path` at `target_name` using the create-temp + rename
    pattern. `target_name` is a relative path interpreted in the parent of
    `link_path` (same convention as {skill_group}/active → version-dir-sibling).

    Implementation: skf-atomic-write.py's replace_link, the code flip-link
    runs, with `.{name}.skf-symlink.tmp` as the temp name: it removes a stale
    temp from a prior crash, writes the new link there and os.replace renames
    it over link_path. POSIX rename is atomic for symlinks, so concurrent
    readers either see the old target or the new one, never a missing file.
    On Windows the old link is removed first whenever the rename over it is
    refused, which it always is over a directory link; without symlink
    privilege the new link is a junction.
    """
    tmp = link_path.parent / f".{link_path.name}.skf-symlink.tmp"
    _load_atomic_write().replace_link(link_path, target_name, tmp)


# --------------------------------------------------------------------------
# Core operations
# --------------------------------------------------------------------------


def _envelope_missing_target(skill_group: Path, version: str) -> dict:
    return {
        "status": "missing-target",
        "skill_group": str(skill_group),
        "active_link": str(skill_group / ACTIVE_NAME),
        "expected_target": version,
        "current_target": None,
        "action_taken": "halt",
        "log_message": (
            f"active_symlink_update: missing-target "
            f"({skill_group / version} does not exist)"
        ),
        "halt_message": (
            f"Cannot point {skill_group / ACTIVE_NAME} at `{version}` — "
            f"target directory `{skill_group / version}` does not exist on "
            "disk. Verify the version directory was written before the flip runs."
        ),
    }


def _envelope_ok(skill_group: Path, version: str, current: str | None) -> dict:
    return {
        "status": "ok",
        "skill_group": str(skill_group),
        "active_link": str(skill_group / ACTIVE_NAME),
        "expected_target": version,
        "current_target": current,
        "action_taken": "no-op",
        "log_message": f"active_symlink_update: ok ({version})",
        "halt_message": None,
    }


def _envelope_flipped(skill_group: Path, version: str, previous: str | None) -> dict:
    prev = previous if previous is not None else "(none)"
    return {
        "status": "flipped",
        "skill_group": str(skill_group),
        "active_link": str(skill_group / ACTIVE_NAME),
        "expected_target": version,
        "current_target": version,
        "action_taken": "flipped",
        "log_message": f"active_symlink_update: flipped ({prev} -> {version})",
        "halt_message": None,
    }


def _envelope_mismatch(skill_group: Path, version: str, current: str | None) -> dict:
    cur = current if current is not None else "(none)"
    return {
        "status": "mismatch",
        "skill_group": str(skill_group),
        "active_link": str(skill_group / ACTIVE_NAME),
        "expected_target": version,
        "current_target": current,
        "action_taken": "halt",
        "log_message": (
            f"active_symlink_update: mismatch "
            f"(expected={version}, current={cur})"
        ),
        "halt_message": (
            f"Active symlink divergence. `{skill_group / ACTIVE_NAME}` "
            f"resolves to `{cur}` but metadata.json reports `version: "
            f"{version}`. The flip did not apply. Re-point the symlink manually "
            f"(`uv run \"{ATOMIC_WRITE_HELPER}\" flip-link --link \"{skill_group / ACTIVE_NAME}\" "
            f"--target \"{version}\"`) or re-run update-skill, then re-verify."
        ),
    }


def _envelope_busy(skill_group: Path, version: str, message: str) -> dict:
    return {
        "status": "busy",
        "skill_group": str(skill_group),
        "active_link": str(skill_group / ACTIVE_NAME),
        "expected_target": version,
        "current_target": None,
        "action_taken": "halt",
        "log_message": f"active_symlink_update: busy ({message})",
        "halt_message": (
            f"Another flip of `{skill_group / ACTIVE_NAME}` held its lock for "
            f"{FLIP_LOCK_WAIT_SECONDS:g} s, so the link is unchanged. "
            "Re-run once the other run ends."
        ),
    }


def update(skill_group: Path, version: str) -> dict:
    """Idempotently flip {skill_group}/active to point at {version}."""
    target_dir = skill_group / version
    if not target_dir.is_dir():
        return _envelope_missing_target(skill_group, version)

    link_path = skill_group / ACTIVE_NAME
    atomic_write = _load_atomic_write()
    try:
        lock_fd = atomic_write.take_flip_lock(link_path, wait=FLIP_LOCK_WAIT_SECONDS)
    except atomic_write.FlipLockHeld as exc:
        return _envelope_busy(skill_group, version, str(exc))
    try:
        current = read_link_target(link_path)
        if current == version:
            return _envelope_ok(skill_group, version, current)

        atomic_flip_symlink(link_path, version)

        # Re-read to confirm
        post = read_link_target(link_path)
    finally:
        atomic_write.release_flip_lock(link_path, lock_fd)
    if post != version:
        # Only a writer that skips the lock, such as a hand-run `ln -sfn`, gets here.
        return _envelope_mismatch(skill_group, version, post)
    return _envelope_flipped(skill_group, version, current)


def verify(skill_group: Path, version: str) -> dict:
    """Read-only check: assert active points at version."""
    link_path = skill_group / ACTIVE_NAME
    current = read_link_target(link_path)
    if current == version:
        return _envelope_ok(skill_group, version, current)
    return _envelope_mismatch(skill_group, version, current)


# --------------------------------------------------------------------------
# repair-after-drop
# --------------------------------------------------------------------------


def pick_new_active(active_version: str | None, versions: list[dict], dropped: str | None) -> str | None:
    """The version `active` points at once `dropped` is gone, or None to remove the link.

    `versions` are skf-skill-inventory.py resolve's rows, newest first, each
    with `version`, `status`, `in_manifest` and `on_disk`. The manifest's
    active_version wins unless it is null, deprecated, the dropped version or
    not on disk; else the newest manifest version that is not deprecated, is
    on disk and is not the dropped one. Drop Skill's roster offers the same
    pick as `keep_candidate`, with the active version as the dropped one,
    unless the `active` link names another version.
    """
    rows = {row.get("version"): row for row in versions if isinstance(row, dict)}

    def usable(version, row):
        return (isinstance(version, str) and version != dropped and row is not None
                and row.get("on_disk") is True and row.get("status") != "deprecated")

    if usable(active_version, rows.get(active_version)):
        return active_version
    return next((row["version"] for row in versions
                 if isinstance(row, dict) and row.get("in_manifest") is True and usable(row.get("version"), row)),
                None)


def names_version(target: str | None, skill_group: Path, version: str) -> bool:
    """True when the link text `target` names `version` of this skill group.

    A link SKF makes stores the bare version. A Windows junction whose folder
    is gone reads back as its stored absolute path (`\\\\?\\C:\\...\\<group>\\<v>`),
    and a hand-made link may store a path: those name it when their last two
    parts are the group's folder name and the version.
    """
    if not target:
        return False
    text = target[4:] if target.startswith("\\\\?\\") else target
    parts = [part for part in re.split(r"[\\/]+", text) if part not in ("", ".")]
    if not parts or parts[-1] != version:
        return False
    return len(parts) == 1 or os.path.normcase(parts[-2]) == os.path.normcase(skill_group.name)


def _manual_fix(skill_group: Path, dropped: str, new_active: str | None, *, busy: bool = False,
                error: str | None = None) -> str:
    """The one command that repairs `active` by hand, with its condition first."""
    link = skill_group / ACTIVE_NAME
    if new_active is None:
        command = f'remove the link: `rm "{link}"`'
    else:
        command = (f'run `uv run "{ATOMIC_WRITE_HELPER}" flip-link --link "{link}" '
                   f'--target "{new_active}"`')
    prefix = BUSY_PREFIX if busy else ""
    tail = f" ({error})" if error and not busy else ""
    return f"{prefix}if `active` still names {dropped}, {command}{tail}"


def _repair_result(action: str, link_target: str | None, new_active: str | None, *,
                   manual_fix: str | None = None, error: str | None = None) -> dict:
    return {"action": action, "link_target": link_target, "new_active": new_active,
            "manual_fix": manual_fix, "error": error}


def repair_after_drop(skill_group: Path, dropped: str) -> dict:
    """Point {skill_group}/active away from the purged `dropped` version, or remove it.

    Raises OSError or ValueError before the replacement is picked (a helper
    that cannot be loaded, a manifest that cannot be read): the link is then
    untouched. Every failure after the pick returns action "failed" with a
    manual_fix.
    """
    inventory = _load_inventory()
    atomic_write = _load_atomic_write()
    try:
        # forge_data_folder feeds resolve's provenance paths only, which this pick never reads.
        resolved = inventory.resolve_skill(str(skill_group.parent), skill_group.name, str(skill_group.parent))
    except INVENTORY_ERRORS as exc:
        raise ValueError(f"cannot read the versions of {skill_group}: {type(exc).__name__}: {exc}") from exc
    if resolved is not None and resolved.get("manifest_error"):
        raise ValueError(f"cannot read the export manifest: {resolved['manifest_error']}")
    resolved = resolved or {"active_version": None, "versions": []}
    new_active = pick_new_active(resolved.get("active_version"), resolved.get("versions") or [], dropped)

    link_path = skill_group / ACTIVE_NAME
    try:
        lock_fd = atomic_write.take_flip_lock(link_path, wait=FLIP_LOCK_WAIT_SECONDS)
    except atomic_write.FlipLockHeld as exc:
        return _repair_result("failed", None, new_active, error=str(exc),
                              manual_fix=_manual_fix(skill_group, dropped, new_active, busy=True))
    except OSError as exc:
        return _repair_result("failed", None, new_active, error=str(exc),
                              manual_fix=_manual_fix(skill_group, dropped, new_active, error=str(exc)))
    current, result = None, None
    try:
        try:
            current = read_link_target(link_path)
        except ValueError:
            current = None  # a real folder or file at `active` is no link, so it names no version
        if not names_version(current, skill_group, dropped):
            result = _repair_result("none", current, None)
        elif new_active is None:
            atomic_write._remove_link(link_path)
            post = read_link_target(link_path)
            if post is not None:
                error = f"`active` still names {post} after the removal"
                result = _repair_result("failed", current, None, error=error,
                                        manual_fix=_manual_fix(skill_group, dropped, None, error=error))
            else:
                result = _repair_result("unlinked", current, None)
        elif not (skill_group / new_active).is_dir():
            error = f"{skill_group / new_active} does not exist"
            result = _repair_result("failed", current, new_active, error=error,
                                    manual_fix=_manual_fix(skill_group, dropped, new_active, error=error))
        else:
            atomic_flip_symlink(link_path, new_active)
            post = read_link_target(link_path)
            if post != new_active:
                # Only a writer that skips the lock, such as a hand-run `ln -sfn`, gets here.
                error = f"`active` names {post} after the flip"
                result = _repair_result("failed", current, new_active, error=error,
                                        manual_fix=_manual_fix(skill_group, dropped, new_active, error=error))
            else:
                result = _repair_result("flipped", current, new_active)
    except (OSError, ValueError) as exc:
        error = str(exc) or type(exc).__name__
        result = _repair_result("failed", current, new_active, error=error,
                                manual_fix=_manual_fix(skill_group, dropped, new_active, error=error))
    finally:
        try:
            atomic_write.release_flip_lock(link_path, lock_fd)
        except OSError as exc:
            error = str(exc) or type(exc).__name__
            if result is not None and result["action"] != "failed":
                result = _repair_result("failed", current, result["new_active"], error=error,
                                        manual_fix=_manual_fix(skill_group, dropped, new_active, error=error))
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _exit_code_for_status(status: str) -> int:
    if status in ("ok", "flipped"):
        return 0
    if status in ("mismatch", "missing-target", "busy"):
        return 2
    return 1


def _cmd_update(args: argparse.Namespace) -> int:
    skill_group = Path(args.skill_group)
    if not skill_group.is_dir():
        print(
            f"error: skill-group not a directory: {skill_group}", file=sys.stderr
        )
        return 1
    try:
        result = update(skill_group, args.version)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return _exit_code_for_status(result["status"])


def _cmd_verify(args: argparse.Namespace) -> int:
    skill_group = Path(args.skill_group)
    if not skill_group.is_dir():
        print(
            f"error: skill-group not a directory: {skill_group}", file=sys.stderr
        )
        return 1
    try:
        result = verify(skill_group, args.version)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return _exit_code_for_status(result["status"])


def _cmd_repair_after_drop(args: argparse.Namespace) -> int:
    skill_group = Path(args.skill_group)
    if not skill_group.is_dir():
        print(f"error: skill-group not a directory: {skill_group}", file=sys.stderr)
        return 1
    try:
        result = repair_after_drop(skill_group, args.dropped)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 2 if result["action"] == "failed" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-update-active-symlink",
        description=(
            "Atomically + idempotently update {skill-group}/active to point "
            "at a target version directory."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_upd = sub.add_parser("update", help="flip the symlink if needed")
    p_upd.add_argument("--skill-group", required=True, help="path to the skill_group dir")
    p_upd.add_argument("--version", required=True, help="version directory name")
    p_upd.set_defaults(func=_cmd_update)

    p_ver = sub.add_parser("verify", help="read-only: assert symlink matches version")
    p_ver.add_argument("--skill-group", required=True)
    p_ver.add_argument("--version", required=True)
    p_ver.set_defaults(func=_cmd_verify)

    p_rep = sub.add_parser("repair-after-drop",
                           help="after a version purge: repoint or remove an `active` that names the dropped version")
    p_rep.add_argument("--skill-group", required=True, help="path to the skill_group dir")
    p_rep.add_argument("--dropped", required=True, help="the version folder the purge deleted")
    p_rep.set_defaults(func=_cmd_repair_after_drop)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
