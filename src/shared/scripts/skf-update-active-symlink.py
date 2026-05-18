# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Update Active Symlink — atomic + idempotent + verified flip of
{skill_group}/active to point at a target version directory.

`skf-update-skill/references/write.md §5b` previously asked the LLM to
"create or update the active symlink at {skill_group}/active pointing
to the new {version}; if the symlink already exists, remove it first
and recreate". That two-step (`rm` then `ln`) leaves a brief window
where the symlink doesn't exist — readers that resolve `active`
mid-update see a `FileNotFoundError`. §6 then re-reads the symlink
to verify it points where expected and halts on divergence.

This helper consolidates the two steps into one workflow-specific
invocation:

  - detects whether a flip is required (idempotent: already pointing
    at the target → no-op)
  - performs the flip atomically (symlink → temp name → os.replace)
    so concurrent readers never see a missing symlink
  - verifies the post-state and surfaces ok / flipped / mismatch
    / missing-target

Two subcommands:

  update --skill-group <path> --version <name>
      Make {skill-group}/active point at {version}. Atomic.
      Idempotent: returns status=ok with action=no-op when the link
      already points there.

  verify --skill-group <path> --version <name>
      Read-only: check that {skill-group}/active currently points at
      {version}. Used by step-06 derived-artifact verification.

The target version directory (`{skill-group}/{version}/`) MUST exist
on disk before this script is called. The helper refuses to point
the symlink at a path that doesn't resolve — a dangling `active`
silently breaks downstream consumers that expect it to resolve.

Output JSON (stdout):
  {
    "status": "ok" | "flipped" | "mismatch" | "missing-target",
    "skill_group": "<abs path>",
    "active_link": "<abs path to active>",
    "expected_target": "<version>",
    "current_target": "<previous target>" | null,
    "action_taken": "no-op" | "flipped" | "halt",
    "log_message": "...",
    "halt_message": "<multi-line user message>" | null
  }

Exit codes:
  0  — ok (already correct) or flipped (just updated)
  1  — script error (bad args, group path invalid)
  2  — mismatch (verify mode and target diverges) OR missing-target
       (the {version} directory doesn't exist; caller must halt)

Platform: POSIX symlinks. On Windows this script intentionally
exits 1 with a clear error — update-skill's documented supported
platform is WSL2 (same as skf-atomic-write.py's flip-link).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ACTIVE_NAME = "active"


# --------------------------------------------------------------------------
# Symlink primitives
# --------------------------------------------------------------------------


def read_link_target(link_path: Path) -> str | None:
    """Return the symlink target as a relative string, or None if the link
    doesn't exist. Raises ValueError if `link_path` exists but isn't a symlink
    (someone replaced it with a regular dir/file)."""
    if not link_path.exists() and not link_path.is_symlink():
        return None
    if not link_path.is_symlink():
        raise ValueError(
            f"{link_path} exists but is not a symlink — refusing to overwrite "
            "(manual recovery required)"
        )
    return os.readlink(link_path)


def atomic_flip_symlink(link_path: Path, target_name: str) -> None:
    """Atomically point `link_path` at `target_name` using the
    create-temp + rename pattern. `target_name` is a relative path
    interpreted in the parent of `link_path` (same convention as
    {skill_group}/active → version-dir-sibling).

    Implementation: os.symlink writes a new link at link_path.tmp,
    then os.replace atomically renames it over link_path. POSIX
    rename is atomic for symlinks, so concurrent readers either see
    the old target or the new one, never a missing file.
    """
    parent = link_path.parent
    tmp = parent / f".{link_path.name}.skf-symlink.tmp"
    # Clean up a stale temp from a prior crash, if any.
    if tmp.is_symlink() or tmp.exists():
        os.unlink(tmp)
    try:
        os.symlink(target_name, tmp)
        os.replace(tmp, link_path)
    except OSError:
        # Best-effort cleanup; raise the original error.
        try:
            if tmp.is_symlink() or tmp.exists():
                os.unlink(tmp)
        except OSError:
            pass
        raise


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
            "disk. Verify the version directory was written before §5b runs."
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
            f"{version}`. §5b did not apply. Re-point the symlink manually "
            f"(`ln -sfn {version} {skill_group / ACTIVE_NAME}`) or re-run "
            "update-skill, then re-verify."
        ),
    }


def update(skill_group: Path, version: str) -> dict:
    """Idempotently flip {skill_group}/active to point at {version}."""
    target_dir = skill_group / version
    if not target_dir.is_dir():
        return _envelope_missing_target(skill_group, version)

    link_path = skill_group / ACTIVE_NAME
    current = read_link_target(link_path)
    if current == version:
        return _envelope_ok(skill_group, version, current)

    atomic_flip_symlink(link_path, version)

    # Re-read to confirm
    post = read_link_target(link_path)
    if post != version:
        # Should be impossible — os.replace would have raised — but defend
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
# CLI
# --------------------------------------------------------------------------


def _exit_code_for_status(status: str) -> int:
    if status in ("ok", "flipped"):
        return 0
    if status in ("mismatch", "missing-target"):
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

    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform.startswith("win"):
        print(
            "error: native Windows symlinks require admin/developer mode; "
            "use WSL2 to run update-skill (same constraint as "
            "skf-atomic-write.py flip-link)",
            file=sys.stderr,
        )
        return 1
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
