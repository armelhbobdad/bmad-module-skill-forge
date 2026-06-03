# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Provenance — verify repo access and record commit SHAs for all targets.

Replaces the step-04 prose that asked the LLM to string-munge each repo_url
("handle trailing .git or slashes"), run `gh repo view` + `gh api commits/{ref}`
per target, and aggregate failures across 15+ targets in-context. All of that
is deterministic; doing it by hand is both token-expensive and a fragile-parse
risk. This script owns the parse, the gh calls, and the aggregation, and — when
every (or nearly every) target fails the same way — collapses the wall of
near-identical errors into a single actionable root-cause hint instead of N
independent failures.

For each skill it resolves `{owner}/{repo}` from the brief's repo_url, picks the
ref (the skill's pin, or the repo default branch), verifies access, and records
the commit SHA.

CLI:
  uv run campaign-provenance.py --state-file <path> --brief-file <path>

Output (JSON on stdout):
  {
    "results": [
      {"name": "...", "repo_url": "...", "owner": "...", "repo": "...",
       "ref": "...", "commit_sha": "..." | null,
       "status": "accessible" | "inaccessible", "error": "..." | null}
    ],
    "all_accessible": bool,
    "inaccessible_count": N,
    "systemic_hint": "..." | null
  }

Exit codes:
  0  all targets accessible
  1  one or more targets inaccessible
  2  error (missing files, bad YAML, gh not installed)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess  # noqa: S404 — invoking the user's authenticated `gh` CLI is the point
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

# A command runner returns (returncode, stdout, stderr). Injectable for tests.
Runner = Callable[[List[str]], Tuple[int, str, str]]


def _emit_error(message: str, code: str) -> None:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_owner_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    """Extract (owner, repo) from a GitHub URL or `owner/repo` shorthand.

    Tolerates trailing `.git`, trailing slashes, `git@` SSH form, and a bare
    `owner/repo`. Returns None when no owner/repo pair can be recovered.
    """
    if not repo_url or not isinstance(repo_url, str):
        return None
    url = repo_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # git@github.com:owner/repo
    ssh = re.match(r"^git@[^:]+:(?P<owner>[^/]+)/(?P<repo>[^/]+)$", url)
    if ssh:
        return ssh.group("owner"), ssh.group("repo")
    # https://host/owner/repo (take the last two path segments)
    https = re.match(r"^[a-zA-Z]+://[^/]+/(?P<rest>.+)$", url)
    rest = https.group("rest") if https else url
    parts = [p for p in rest.split("/") if p]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None


def _default_runner(args: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(args, capture_output=True, text=True)  # noqa: S603
    return proc.returncode, proc.stdout, proc.stderr


def _classify_error(stderr: str) -> str:
    """Bucket a gh failure so systemic root causes can be detected."""
    low = stderr.lower()
    if "authentication" in low or "gh auth" in low or "not logged" in low or "401" in low:
        return "auth"
    if "could not resolve" in low or "network" in low or "timeout" in low or "dial tcp" in low:
        return "network"
    if "rate limit" in low or "403" in low:
        return "rate-limit"
    if "not found" in low or "404" in low:
        return "not-found"
    return "other"


_SYSTEMIC_HINTS = {
    "auth": "All targets failed authentication — run `gh auth status` / `gh auth login`, then `campaign resume`.",
    "network": "All targets failed with network errors — check connectivity, then `campaign resume`.",
    "rate-limit": "All targets hit GitHub rate limiting — wait for the limit to reset, then `campaign resume`.",
}


def run(state_file: str, brief_file: str, runner: Runner = _default_runner) -> int:
    state_path = Path(state_file)
    brief_path = Path(brief_file)

    if not state_path.is_file():
        _emit_error(f"State file not found: {state_file}", "STATE_NOT_FOUND")
        return 2
    if not brief_path.is_file():
        _emit_error(f"Brief file not found: {brief_file}", "BRIEF_NOT_FOUND")
        return 2
    if shutil.which("gh") is None and runner is _default_runner:
        _emit_error("GitHub CLI `gh` not found on PATH", "GH_NOT_FOUND")
        return 2

    try:
        state = _load_yaml(state_path)
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")
        return 2
    try:
        brief = _load_yaml(brief_path)
    except Exception as exc:  # noqa: BLE001
        _emit_error(f"Failed to parse brief file: {exc}", "BRIEF_PARSE_ERROR")
        return 2

    skills = state.get("skills", [])
    if not isinstance(skills, list):
        _emit_error("State file 'skills' is not an array", "INVALID_STATE")
        return 2
    targets = brief.get("targets", [])
    if not isinstance(targets, list):
        _emit_error("Brief file 'targets' is not an array", "INVALID_BRIEF")
        return 2

    name_to_repo: Dict[str, str] = {t["name"]: t["repo_url"] for t in targets}

    results: List[Dict[str, Any]] = []
    error_classes: List[str] = []

    for skill in skills:
        name = skill["name"]
        repo_url = name_to_repo.get(name)
        record: Dict[str, Any] = {
            "name": name,
            "repo_url": repo_url,
            "owner": None,
            "repo": None,
            "ref": None,
            "commit_sha": None,
            "status": "inaccessible",
            "error": None,
        }
        if repo_url is None:
            record["error"] = f"Skill '{name}' has no repo_url in brief targets"
            error_classes.append("other")
            results.append(record)
            continue

        parsed = parse_owner_repo(repo_url)
        if parsed is None:
            record["error"] = f"Could not parse owner/repo from '{repo_url}'"
            error_classes.append("other")
            results.append(record)
            continue
        owner, repo = parsed
        record["owner"], record["repo"] = owner, repo

        rc, _out, err = runner(["gh", "repo", "view", f"{owner}/{repo}", "--json", "name"])
        if rc != 0:
            record["error"] = err.strip() or "gh repo view failed"
            error_classes.append(_classify_error(err))
            results.append(record)
            continue

        ref = skill.get("pin")
        if not ref:
            rc, out, err = runner(
                ["gh", "repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"]
            )
            if rc != 0:
                record["error"] = err.strip() or "could not resolve default branch"
                error_classes.append(_classify_error(err))
                results.append(record)
                continue
            ref = out.strip()
        record["ref"] = ref

        rc, out, err = runner(["gh", "api", f"repos/{owner}/{repo}/commits/{ref}", "--jq", ".sha"])
        if rc != 0:
            record["error"] = err.strip() or f"could not resolve commit for ref '{ref}'"
            error_classes.append(_classify_error(err))
            results.append(record)
            continue

        record["commit_sha"] = out.strip()
        record["status"] = "accessible"
        results.append(record)

    inaccessible = [r for r in results if r["status"] != "accessible"]
    systemic_hint: Optional[str] = None
    if inaccessible and len(inaccessible) == len(results):
        # Every target failed — if they share a class, surface one root cause.
        distinct = set(error_classes)
        if len(distinct) == 1:
            systemic_hint = _SYSTEMIC_HINTS.get(next(iter(distinct)))

    output = {
        "results": results,
        "all_accessible": not inaccessible,
        "inaccessible_count": len(inaccessible),
        "systemic_hint": systemic_hint,
    }
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if not inaccessible else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-provenance",
        description="Verify repo access and record commit SHAs for all campaign targets.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument("--brief-file", required=True, help="Path to campaign-brief.yaml")
    args = parser.parse_args(argv)
    return run(args.state_file, args.brief_file)


if __name__ == "__main__":
    raise SystemExit(main())
