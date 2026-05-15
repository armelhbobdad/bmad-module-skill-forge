# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Check Workspace Drift — pre-flight guard for gap-driven update-skill runs.

`skf-update-skill/references/re-extract.md §0.a` defines a four-state guard:
the workspace at `source_root` must point at the commit the skill was pinned
against (`metadata.source_commit`), otherwise gap-driven spot-checks read
bytes that differ from the pinned tree and silently produce wrong results
(symbols appear "verified" because the recorded line now points at different
code).

The guard's logic is deterministic — three git commands and a comparison —
but the prose form asked the LLM to chain them per run, with subtle short-
SHA prefix matching and skip-paths for non-git workspaces. This script bakes
the dispatch in.

CLI:
  uv run skf-check-workspace-drift.py <source-root> \\
      --pinned-commit <SHA or empty> \\
      [--source-ref <ref>] \\
      [--allow-drift]

Inputs:
  source_root       Filesystem path to the workspace under test.
  --pinned-commit   The pinned commit SHA (full or short). Pass an empty
                    string OR the literal "local" to declare that this
                    skill has no pinned commit — the guard skips with
                    skip_reason="no-pinned-commit".
  --source-ref      Optional. The ref name (tag, branch) the workspace
                    was pinned to. Included in the halt message for
                    user-facing context only.
  --allow-drift     Suppress the drift halt. Mismatches still return
                    status="overridden" so the caller can surface a
                    warning in the final report.

Output (JSON on stdout):
  {
    "status": "ok" | "skipped" | "mismatch" | "overridden",
    "skip_reason": "no-pinned-commit" | "not-a-git-tree" | null,
    "pinned_commit": "<as-given>",
    "head_sha": "<full SHA>" | null,
    "head_short_sha": "<7-12 chars>" | null,
    "match_kind": "full" | "short-prefix" | null,
    "log_message": "workspace_drift_check: ok (abc1234)",
    "halt_message": "<multi-line user-facing message>" | null
  }

Exit codes:
  0  — caller may continue (status is ok, skipped, or overridden)
  1  — script error (bad args, source_root missing, git unavailable)
  2  — drift detected and --allow-drift was NOT passed; caller MUST halt
       with status="halted-for-workspace-drift". The halt_message field
       is pre-formatted with all substitutions applied.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


SKIP_NO_PINNED = "no-pinned-commit"
SKIP_NOT_GIT = "not-a-git-tree"


# --------------------------------------------------------------------------
# Git probes
# --------------------------------------------------------------------------


def _git(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run a git command; return (rc, stdout, stderr). Stdout/stderr stripped."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def is_git_working_tree(source_root: Path) -> bool:
    """True if `git rev-parse --is-inside-work-tree` says yes."""
    rc, out, _ = _git(["rev-parse", "--is-inside-work-tree"], cwd=source_root)
    return rc == 0 and out == "true"


def head_sha(source_root: Path) -> str | None:
    """Return the workspace HEAD SHA, or None if it can't be read."""
    rc, out, _ = _git(["rev-parse", "HEAD"], cwd=source_root)
    if rc != 0 or not out:
        return None
    return out


# --------------------------------------------------------------------------
# Match logic
# --------------------------------------------------------------------------


def is_skippable_pinned(pinned_commit: str) -> bool:
    """Recognize the scalar values that mean 'no pinned commit'."""
    if pinned_commit is None:
        return True
    stripped = pinned_commit.strip()
    return stripped == "" or stripped.lower() == "local"


def classify_match(pinned: str, head: str) -> str | None:
    """Return 'full' if pinned == head, 'short-prefix' if pinned is a prefix
    of head (≥ 7 chars to avoid coincidental collisions on short SHAs).
    Returns None on no match."""
    if pinned == head:
        return "full"
    if len(pinned) >= 7 and head.startswith(pinned):
        return "short-prefix"
    return None


def short(sha: str) -> str:
    return sha[:7]


# --------------------------------------------------------------------------
# Halt message
# --------------------------------------------------------------------------


HALT_MESSAGE_TEMPLATE = """Workspace HEAD does not match the commit this skill was pinned against.

  pinned (metadata.source_commit): {pinned_commit}
  pinned ref (metadata.source_ref): {source_ref}
  workspace HEAD ({source_root}):  {head_sha}

Gap-driven spot-checks read source at pinned line numbers — verifying
against a drifted tree silently produces wrong results (symbols appear at
unintended locations). Re-sync the workspace before re-running:

  git -C "{source_root}" checkout {checkout_target}

Or, to intentionally proceed against the current workspace HEAD (accepting
that spot-checks will read bytes that differ from the pinned commit),
re-run update-skill with `--allow-workspace-drift`."""


def build_halt_message(
    *, source_root: Path, pinned_commit: str, head_sha_full: str, source_ref: str | None
) -> str:
    ref_display = source_ref if source_ref else "unset"
    checkout_target = source_ref if source_ref else pinned_commit
    return HALT_MESSAGE_TEMPLATE.format(
        pinned_commit=pinned_commit,
        source_ref=ref_display,
        source_root=str(source_root),
        head_sha=head_sha_full,
        checkout_target=checkout_target,
    )


# --------------------------------------------------------------------------
# Core check
# --------------------------------------------------------------------------


def check(
    source_root: Path,
    *,
    pinned_commit: str,
    source_ref: str | None,
    allow_drift: bool,
) -> dict:
    """Run the four-state guard and return a result envelope."""
    if is_skippable_pinned(pinned_commit):
        return {
            "status": "skipped",
            "skip_reason": SKIP_NO_PINNED,
            "pinned_commit": pinned_commit,
            "head_sha": None,
            "head_short_sha": None,
            "match_kind": None,
            "log_message": "workspace_drift_check: skipped (no pinned commit)",
            "halt_message": None,
        }

    if not is_git_working_tree(source_root):
        return {
            "status": "skipped",
            "skip_reason": SKIP_NOT_GIT,
            "pinned_commit": pinned_commit,
            "head_sha": None,
            "head_short_sha": None,
            "match_kind": None,
            "log_message": "workspace_drift_check: skipped (not a git working tree)",
            "halt_message": None,
        }

    head = head_sha(source_root)
    if head is None:
        # git tree exists but HEAD can't be resolved (orphan / empty repo).
        # Treat as not-a-git-tree for guard purposes — we can't verify pinning.
        return {
            "status": "skipped",
            "skip_reason": SKIP_NOT_GIT,
            "pinned_commit": pinned_commit,
            "head_sha": None,
            "head_short_sha": None,
            "match_kind": None,
            "log_message": "workspace_drift_check: skipped (HEAD unreadable)",
            "halt_message": None,
        }

    match_kind = classify_match(pinned_commit, head)
    if match_kind is not None:
        return {
            "status": "ok",
            "skip_reason": None,
            "pinned_commit": pinned_commit,
            "head_sha": head,
            "head_short_sha": short(head),
            "match_kind": match_kind,
            "log_message": f"workspace_drift_check: ok ({short(head)})",
            "halt_message": None,
        }

    # Mismatch path
    halt_message = build_halt_message(
        source_root=source_root,
        pinned_commit=pinned_commit,
        head_sha_full=head,
        source_ref=source_ref,
    )
    if allow_drift:
        return {
            "status": "overridden",
            "skip_reason": None,
            "pinned_commit": pinned_commit,
            "head_sha": head,
            "head_short_sha": short(head),
            "match_kind": None,
            "log_message": (
                f"workspace_drift_check: overridden "
                f"(pinned={pinned_commit}, head={head})"
            ),
            "halt_message": halt_message,  # surfaced as warning by caller
        }

    return {
        "status": "mismatch",
        "skip_reason": None,
        "pinned_commit": pinned_commit,
        "head_sha": head,
        "head_short_sha": short(head),
        "match_kind": None,
        "log_message": (
            f"workspace_drift_check: mismatch "
            f"(pinned={pinned_commit}, head={head})"
        ),
        "halt_message": halt_message,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-check-workspace-drift",
        description=(
            "Verify that the source-root workspace HEAD matches the pinned "
            "commit recorded in metadata.source_commit."
        ),
    )
    parser.add_argument("source_root", help="path to the workspace under test")
    parser.add_argument(
        "--pinned-commit",
        required=True,
        help='pinned commit SHA; pass "" or "local" to skip the guard',
    )
    parser.add_argument(
        "--source-ref",
        default=None,
        help="optional pinned ref (tag/branch) for halt-message display",
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="suppress the drift halt; mismatch becomes status=overridden",
    )
    args = parser.parse_args(argv)

    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(f"error: source-root not a directory: {source_root}", file=sys.stderr)
        return 1
    if shutil.which("git") is None:
        print("error: git binary not on PATH", file=sys.stderr)
        return 1

    result = check(
        source_root,
        pinned_commit=args.pinned_commit,
        source_ref=args.source_ref,
        allow_drift=args.allow_drift,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if result["status"] == "mismatch":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
