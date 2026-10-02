# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Check Workspace Drift — pre-flight guard for gap-driven update-skill runs.

`skf-update-skill/references/gap-driven.md §3` defines a four-state guard:
the workspace at `source_root` must point at the commit the skill was pinned
against (`metadata.source_commit`), otherwise gap-driven spot-checks read
bytes that differ from the pinned tree and silently produce wrong results
(symbols appear "verified" because the recorded line now points at different
code).

The guard's logic is deterministic — three git commands and a comparison —
but the prose form asked the LLM to chain them per run, with subtle short-
SHA prefix matching and skip-paths for non-git workspaces. This script bakes
the dispatch in. test-skill runs the same guard (`--workflow test-skill`,
one call per repository of a stack skill), and audit-skill asks the
`upstream` command below whether the remote moved past the skill's commit.

git runs with the git location variables (GIT_DIR, GIT_INDEX_FILE, ...)
removed from its environment. A git hook or `git rebase --exec` exports
them (GIT_DIR too when run in a linked worktree); inherited by
`git -C <source-root>`, they would make the check read another
repository's HEAD.

CLI:
  uv run skf-check-workspace-drift.py <source-root> \\
      --pinned-commit <SHA or empty> \\
      [--source-ref <ref>] \\
      [--allow-drift] \\
      [--workflow update-skill|test-skill]

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
  --workflow        The workflow the halt message speaks for (WORKFLOWS):
                    update-skill (the default) or test-skill, which
                    checks each repository of a stack skill with its own
                    call. It changes halt_message only.

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

upstream: has the remote moved past the baseline?

  uv run skf-check-workspace-drift.py upstream --source-root <path> \\
      --baseline-commit <SHA> --baseline-ref <ref> [--timeout <seconds>]

  A first argument `upstream` selects this command; a source root that is
  a folder named `upstream` in the current folder is passed as
  `./upstream` to the check above.

  One `git ls-remote --symref origin` call reads the remote's default
  branch, its tags (an annotated tag resolves to its commit) and the
  baseline branch. Nothing is fetched and nothing in the clone changes, so
  a `--depth 1 --branch <tag>` clone, which has no `origin/HEAD`, is read
  like any other. The baseline ref decides what "moved" means:

  - A tag whose name ends in a version (`v1.2.3`, `1.2.3-rc.1`,
    `pkg@1.2.3`, `tokio/v1.0.0`): the newest tag of its family, a release
    unless the baseline is a pre-release, sorted by version. A monorepo
    prefix (`pkg@`, `tokio/v`) is a family of its own. The release
    prefixes, none, `v` and `V` (RELEASE_PREFIXES), are one family, since
    a project may switch between them (express went from `4.22.0` to
    `v4.22.1`); a tag under another of them than the baseline's counts
    only when its version has a major and a minor number, so a date or
    build number (`20240101`, `1234`) does not. The remote moved when that
    tag names another commit and is newer than the baseline, or when no
    newer tag exists and the baseline tag itself now names another commit,
    unless `git merge-base --is-ancestor` finds that commit in the
    baseline's history (it cannot in a shallow clone that lacks the
    commit, so version order decides there). Commits on the default branch
    after the tag are not a move.
  - Any other tag: the commit it names now.
  - A branch: the commit the remote branch names now.
  - `HEAD` or a commit: the remote's default branch.

  Output (JSON on stdout; every key is always present):
    status               "unchanged" | "moved" | "skipped" | "fetch-failed"
    skip_reason          null | "no-baseline-ref" | "no-baseline-commit" |
                         "git-unavailable" | "not-a-git-tree" |
                         "invalid-baseline-ref" | "baseline-ref-missing"
                         (UPSTREAM_SKIP_REASONS)
    fetch_error          git's last error line (fetch-failed), else null
    basis                null | "same-commit" | "no-newer-tag" |
                         "contained" | "newer-tag" | "tag-moved" |
                         "ref-moved" (UPSTREAM_BASES): what decided it
    baseline_ref         as given
    ref_kind             "tag" | "branch" | "head" | "commit" | null
    baseline_commit      the full commit when the clone holds it, else as given
    baseline_commit_short
    remote_head          the commit of the remote's default branch, else null
    remote_head_short
    remote_default_branch  its name ("main"), else null
    latest_tag           the newest tag of the baseline's family (for a
                         branch, HEAD or commit: of a release prefix), else null
    latest_tag_commit    and its commit, else null
    latest_tag_commit_short
    upstream_ref         moved: the ref to read instead (the newer tag, the
                         moved tag or branch, or "HEAD"), else null
    upstream_commit      moved: its commit, else null
    upstream_commit_short
    audit_ref            the values an audit that stays on the baseline
    audit_ref_source     records: baseline_ref or "(unknown)", "baseline"
    audit_commit         ("unavailable" without ref and commit), and
                         baseline_commit or "(unknown)"
    log_message          "upstream_check: <status> (...)"
    warnings             list of strings

  A baseline commit that is not 7 to 40 hex digits counts as missing.

  Exit codes: 0 once the JSON is printed (it never gates; the caller
  owns the choice), 1 unexpected error (one JSON line on stderr), 2 usage
  error. git runs through skf-source-tree.py (the sibling in this folder,
  which must sit beside this script) with LC_ALL=C, no hooks, no terminal
  or credential-manager prompt and the git location variables removed. A
  remote query still running after --timeout seconds (60 by default) is
  stopped with everything git started, and reported as fetch-failed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SKIP_NO_PINNED = "no-pinned-commit"
SKIP_NOT_GIT = "not-a-git-tree"
# Keep identical to GIT_LOCATION_VARS in skf-merge-ccc-exclusions.py.
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)


# --------------------------------------------------------------------------
# Git probes
# --------------------------------------------------------------------------


def _git(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run a git command; return (rc, stdout, stderr). Stdout/stderr stripped.

    The git location variables are dropped from the child's environment
    (see the module docstring).
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
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


def short(sha: str | None) -> str | None:
    return sha[:7] if sha else None


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


TEST_HALT_MESSAGE_TEMPLATE = """\
Workspace HEAD does not match the commit this skill was pinned against.

  pinned (metadata.source_commit): {pinned_commit}
  pinned ref (metadata.source_ref): {source_ref}
  workspace HEAD ({source_root}):  {head_sha}

Test-skill verifies against the source the skill was extracted from.
Testing against a drifted tree produces false gaps and mismatches. Re-sync:

  git -C "{source_root}" checkout {checkout_target}

Or re-run test-skill with `--allow-workspace-drift` to test against the
current workspace (accepts that findings reflect HEAD, not the pin)."""

HALT_MESSAGES = {
    "update-skill": HALT_MESSAGE_TEMPLATE,
    "test-skill": TEST_HALT_MESSAGE_TEMPLATE,
}
WORKFLOWS = tuple(HALT_MESSAGES)


def build_halt_message(
    *,
    source_root: Path,
    pinned_commit: str,
    head_sha_full: str,
    source_ref: str | None,
    workflow: str = "update-skill",
) -> str:
    ref_display = source_ref if source_ref else "unset"
    checkout_target = source_ref if source_ref else pinned_commit
    return HALT_MESSAGES[workflow].format(
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
    workflow: str = "update-skill",
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
        workflow=workflow,
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
# upstream
# --------------------------------------------------------------------------


UPSTREAM_SKIP_REASONS = (
    "no-baseline-ref",
    "no-baseline-commit",
    "git-unavailable",
    "not-a-git-tree",
    "invalid-baseline-ref",
    "baseline-ref-missing",
)
UPSTREAM_BASES = (
    "same-commit",
    "no-newer-tag",
    "contained",
    "newer-tag",
    "tag-moved",
    "ref-moved",
)
DEFAULT_UPSTREAM_TIMEOUT_SEC = 60.0
LOCAL_TIMEOUT_SEC = 30.0
# The version prefixes of release tags (`4.22.0`, `v4.22.1`, `V2.0`): one
# family, since a project may switch from one to another.
RELEASE_PREFIXES = ("", "v", "V")
_MAJOR_MINOR_RE = re.compile(r"\d+\.\d+")
_UNSET = {"", "null", "none", "local"}
_HEAD_REFS = {"head"}
_SOURCE_TREE = None


def _sibling():
    """skf-source-tree.py from this folder, loaded once: upstream runs git
    through its runner (_run stops a call and all it started at the time
    limit; _resolve_outside_cwd never takes a git planted in the current
    folder), sorts tags with its split_version and shares its SHA40_RE,
    REF_RE, _last_error and _stat_dir."""
    global _SOURCE_TREE
    if _SOURCE_TREE is None:
        path = Path(__file__).resolve().parent / "skf-source-tree.py"
        spec = importlib.util.spec_from_file_location("skf_source_tree", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SOURCE_TREE = module
    return _SOURCE_TREE


def _git_capped(cwd: Path, *args: str, timeout: float) -> tuple[int | None, str, str]:
    """`git -C cwd <args>` with no hooks, no prompts and a time limit.

    (returncode, stdout, stderr): returncode None when git cannot start or
    the time limit stopped it (stderr then says which).
    """
    tree = _sibling()
    exe = tree._resolve_outside_cwd("git")
    if exe is None:
        return None, "", "git is not installed"
    argv = [exe, "-c", f"core.hooksPath={os.devnull}", "-C", str(cwd), *args]
    try:
        rc, out, err, _killed = tree._run(argv, max(0.1, timeout))
    except (OSError, ValueError) as e:
        return None, "", f"git could not run: {e}"
    if rc is None:
        return None, "", f"timed out after {timeout:g} seconds"
    return (
        rc,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


def _parse_ls_remote(text: str) -> tuple[dict, dict, dict]:
    """(refs, tags, symrefs) of `git ls-remote --symref` output.

    tags maps a tag name to the commit it names: the peeled `^{}` line of
    an annotated tag wins over the tag object.
    """
    sha40 = _sibling().SHA40_RE
    refs, tags, symrefs = {}, {}, {}
    for line in text.splitlines():
        left, _, name = line.partition("\t")
        left, name = left.strip(), name.strip()
        if not name:
            continue
        if left.startswith("ref: "):
            symrefs[name] = left[len("ref: ") :].strip()
        elif sha40.match(left):
            refs[name] = left
            if name.startswith("refs/tags/"):
                tag = name[len("refs/tags/") :]
                if tag.endswith("^{}"):
                    tags[tag[:-3]] = left
                else:
                    tags.setdefault(tag, left)
    return refs, tags, symrefs


def _family(prefix: str):
    """The test a tag passes, given its name and version prefix, to count
    as a release of a baseline tag whose version prefix is `prefix`.

    A monorepo prefix (`pkg@`, `tokio/v`) counts only itself. A release
    prefix counts the other two as well, for a tag whose version has a
    major and a minor number: a date or build number (`20240101`, `1234`)
    under another release prefix never counts.
    """
    if prefix not in RELEASE_PREFIXES:
        return lambda name, tag_prefix: tag_prefix == prefix
    return lambda name, tag_prefix: tag_prefix == prefix or (
        tag_prefix in RELEASE_PREFIXES
        and _MAJOR_MINOR_RE.match(name, len(tag_prefix)) is not None
    )


def _newest(tags: dict, counts, releases_only: bool) -> tuple[str | None, tuple | None]:
    """(name, key) of the newest tag counts(name, prefix) takes, else (None, None)."""
    best, best_key = None, None
    for name in tags:
        split = _sibling().split_version(name)
        if split is None or not counts(name, split[0]):
            continue
        if releases_only and split[1][1] == 0:
            continue
        if best is None or (split[1], name) > (best_key, best):
            best, best_key = name, split[1]
    return best, best_key


def upstream(
    source_root: Path,
    *,
    baseline_commit: str,
    baseline_ref: str,
    timeout: float = DEFAULT_UPSTREAM_TIMEOUT_SEC,
) -> dict:
    """Compare the baseline with what the remote names now (module docstring)."""
    ref = (baseline_ref or "").strip()
    commit = (baseline_commit or "").strip()
    ref_unset = ref.lower() in _UNSET
    # "", "local", "null" and "none" are not 7 to 40 hex digits either.
    commit_unset = not re.fullmatch(r"[0-9A-Fa-f]{7,40}", commit)
    out = {
        "status": "skipped",
        "skip_reason": None,
        "fetch_error": None,
        "basis": None,
        "baseline_ref": baseline_ref,
        "ref_kind": None,
        "baseline_commit": baseline_commit,
        "baseline_commit_short": None if commit_unset else short(commit),
        "remote_head": None,
        "remote_head_short": None,
        "remote_default_branch": None,
        "latest_tag": None,
        "latest_tag_commit": None,
        "latest_tag_commit_short": None,
        "upstream_ref": None,
        "upstream_commit": None,
        "upstream_commit_short": None,
        "audit_ref": "(unknown)" if ref_unset else ref,
        "audit_ref_source": "unavailable" if ref_unset and commit_unset else "baseline",
        "audit_commit": "(unknown)" if commit_unset else commit,
        "log_message": "",
        "warnings": [],
    }

    def done(status: str, reason: str | None = None) -> dict:
        out["status"] = status
        out["skip_reason"] = reason if status == "skipped" else None
        if status == "skipped":
            detail = reason
        elif status == "fetch-failed":
            detail = out["fetch_error"]
        elif status == "moved":
            detail = (
                f"{ref} {out['baseline_commit_short']} -> "
                f"{out['upstream_ref']} {out['upstream_commit_short']}"
            )
        else:
            detail = f"{ref} at {out['baseline_commit_short']}"
        out["log_message"] = f"upstream_check: {status} ({detail})"
        return out

    if ref_unset:
        return done("skipped", "no-baseline-ref")
    if commit_unset:
        return done("skipped", "no-baseline-commit")
    tree = _sibling()
    if tree._resolve_outside_cwd("git") is None:
        return done("skipped", "git-unavailable")
    # os.stat, not pathlib: before Python 3.14, is_dir() raises inside a
    # folder the user cannot search.
    if tree._stat_dir(source_root) is not True:
        return done("skipped", "not-a-git-tree")
    rc, text, _err = _git_capped(
        source_root, "rev-parse", "--is-inside-work-tree", timeout=LOCAL_TIMEOUT_SEC
    )
    if rc != 0 or text.strip() != "true":
        return done("skipped", "not-a-git-tree")
    head_ref = ref.lower() in _HEAD_REFS
    if not head_ref and (
        not tree.REF_RE.fullmatch(ref) or ".." in ref or ref.endswith((".", "/"))
    ):
        return done("skipped", "invalid-baseline-ref")

    lowered = commit.lower()
    rc, text, _err = _git_capped(
        source_root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{lowered}^{{commit}}",
        timeout=LOCAL_TIMEOUT_SEC,
    )
    full = text.strip() if rc == 0 and tree.SHA40_RE.match(text.strip()) else None
    if full and classify_match(lowered, full):
        out.update(
            baseline_commit=full,
            baseline_commit_short=short(full),
            audit_commit=full,
        )
    base = full or lowered

    patterns = ["HEAD", "refs/tags/*"]
    if not head_ref:
        patterns.append(f"refs/heads/{ref}")
    rc, text, err = _git_capped(
        source_root, "ls-remote", "--symref", "--", "origin", *patterns, timeout=timeout
    )
    if rc != 0:
        out["fetch_error"] = tree._last_error(err) if rc is not None else err
        return done("fetch-failed")
    refs, tags, symrefs = _parse_ls_remote(text)
    remote_head = refs.get("HEAD")
    out.update(remote_head=remote_head, remote_head_short=short(remote_head))
    head_target = symrefs.get("HEAD", "")
    if head_target.startswith("refs/heads/"):
        out["remote_default_branch"] = head_target[len("refs/heads/") :]

    def newer(name: str | None, sha: str | None, basis: str) -> dict:
        out.update(
            upstream_ref=name,
            upstream_commit=sha,
            upstream_commit_short=short(sha),
            basis=basis,
        )
        return done("moved")

    def same(basis: str) -> dict:
        out["basis"] = basis
        return done("unchanged")

    def show_latest(name: str) -> None:
        out.update(
            latest_tag=name,
            latest_tag_commit=tags[name],
            latest_tag_commit_short=short(tags[name]),
        )

    split = tree.split_version(ref)
    if ref in tags:
        kind = "tag"
    elif f"refs/heads/{ref}" in refs:
        kind = "branch"
    elif head_ref:
        kind = "head"
    elif re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        kind = "commit"
    elif split is not None:
        kind = "tag"  # deleted upstream: its newer siblings still count
        out["warnings"].append(f"the baseline tag {ref} no longer exists upstream")
    else:
        return done("skipped", "baseline-ref-missing")
    out["ref_kind"] = kind

    if kind != "tag":
        latest, _key = _newest(
            tags, lambda _name, prefix: prefix in RELEASE_PREFIXES, releases_only=True
        )
        if latest:
            show_latest(latest)
        if kind == "branch":
            name, tip = ref, refs[f"refs/heads/{ref}"]
        else:
            name, tip = "HEAD", remote_head
        if tip is None:
            return done("skipped", "baseline-ref-missing")
        if classify_match(base, tip):
            return same("same-commit")
        return newer(name, tip, "ref-moved")

    tip = tags.get(ref)
    if split is None:
        if classify_match(base, tip):
            return same("same-commit")
        return newer(ref, tip, "tag-moved")
    prefix, key = split
    latest, latest_key = _newest(tags, _family(prefix), releases_only=key[1] == 1)
    if latest is None:
        return done("skipped", "baseline-ref-missing")
    latest_commit = tags[latest]
    show_latest(latest)
    if classify_match(base, latest_commit):
        return same("same-commit")

    def contained(sha: str) -> bool:
        """True when the clone holds sha in the baseline commit's history."""
        if not full:
            return False
        rc, _text, _err = _git_capped(
            source_root,
            "merge-base",
            "--is-ancestor",
            sha,
            full,
            timeout=LOCAL_TIMEOUT_SEC,
        )
        return rc == 0

    if latest_key <= key:
        if tip is None or classify_match(base, tip):
            return same("no-newer-tag")
        return same("contained") if contained(tip) else newer(ref, tip, "tag-moved")
    if contained(latest_commit):
        return same("contained")
    return newer(latest, latest_commit, "newer-tag")


def _build_upstream_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-check-workspace-drift upstream",
        description=(
            "Tell whether the remote moved past the commit and ref a skill was "
            "built from."
        ),
    )
    parser.add_argument(
        "--source-root",
        required=True,
        help="the skill's source clone",
    )
    parser.add_argument(
        "--baseline-commit",
        required=True,
        help="the commit the skill was built from",
    )
    parser.add_argument(
        "--baseline-ref",
        required=True,
        help="the tag, branch or HEAD it was built from",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_UPSTREAM_TIMEOUT_SEC,
        help="seconds the remote query may take (default 60)",
    )
    return parser


def upstream_main(argv: list[str]) -> int:
    args = _build_upstream_parser().parse_args(argv)
    try:
        result = upstream(
            Path(os.path.expanduser(args.source_root)),
            baseline_commit=args.baseline_commit,
            baseline_ref=args.baseline_ref,
            timeout=args.timeout,
        )
    except Exception as e:  # noqa: BLE001 - one JSON error line, never a traceback
        error = {"status": "error", "message": f"{type(e).__name__}: {e}"}
        print(json.dumps(error), file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["upstream"]:
        return upstream_main(argv[1:])
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
    parser.add_argument(
        "--workflow",
        choices=WORKFLOWS,
        default="update-skill",
        help="the workflow the halt message speaks for (default update-skill)",
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
        workflow=args.workflow,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if result["status"] == "mismatch":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
