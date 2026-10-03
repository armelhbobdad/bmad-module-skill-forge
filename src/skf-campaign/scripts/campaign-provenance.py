# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Campaign Provenance: verify repo access and record commit SHAs for all targets.

Replaces the step-04 prose that asked the LLM to string-munge each repo_url
("handle trailing .git or slashes"), call `gh` per target, and aggregate
failures across 15+ targets in-context. All of that is deterministic; doing
it by hand is both token-expensive and a fragile-parse risk. This script
owns the parse, the gh calls, and the aggregation, and, when every target
fails the same way, adds a single actionable root-cause hint above the
per-repo errors.

For each skill it resolves `{owner}/{repo}` from the brief's repo_url, reads
the repository with one REST call, `gh api repos/{owner}/{repo}` (which
proves access and gives the default branch), picks the ref (the skill's pin,
or that default branch), and records the commit SHA from
`gh api repos/{owner}/{repo}/commits/{ref}`.

A failed call is classified by gh's exit code and the `(HTTP nnn)` code gh
prints on stderr, as skf-github-probe.py does: exit 4 or HTTP 401
`unauthenticated`, 404 or 422 (no such repository or ref) `not-found`, 429
or a 403 that names a rate limit `rate-limited`, any other 403 (an SSO or
SAML policy, a token without the scope) `forbidden`, and anything else
`network`. A target the script cannot even look up (no repo_url in the
brief, an unparseable URL) is `other`.

CLI:
  uv run campaign-provenance.py --state-file <path> --brief-file <path>

Output (JSON on stdout):
  {
    "results": [
      {"name": "...", "repo_url": "...", "owner": "...", "repo": "...",
       "ref": "...", "commit_sha": "..." | null,
       "status": "accessible" | "inaccessible", "error": "..." | null,
       "error_class": "unauthenticated" | "not-found" | "rate-limited"
                      | "forbidden" | "network" | "other" | null}
    ],
    "all_accessible": bool,
    "inaccessible_count": N,
    "systemic_hint": "..." | null
  }

  systemic_hint is one root-cause line when every target failed with the
  same class (unauthenticated, rate-limited, forbidden or network), else
  null. It sums up results[]; each result keeps its own error.

Exit codes:
  0  all targets accessible
  1  one or more targets inaccessible
  2  error (missing files, bad YAML, gh not installed), or INVALID_BRIEF: a
     brief that is no mapping, or a target with no name or no repo_url
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


def _malformed_target(targets: List[Any]) -> Optional[str]:
    """Why the first brief target with no name or no repo_url is unusable, or None.

    Names the target by its 1-based number, and by its name when it has one,
    and says which key it lacks.
    """
    for number, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            return f"Brief target {number} is not a mapping"
        missing = [
            key for key in ("name", "repo_url")
            if not (isinstance(target.get(key), str) and target[key].strip())
        ]
        if missing:
            named = "" if "name" in missing else f" ({target['name']})"
            return f"Brief target {number}{named} has no {' and no '.join(missing)}"
    return None


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


# gh prints the REST status code of a failed call as "(HTTP 404)" on stderr.
_HTTP_CODE_RE = re.compile(r"\(HTTP (\d{3})\)")


def _classify_error(returncode: int, stderr: str) -> str:
    """Bucket a failed gh call so a systemic root cause can be detected."""
    if returncode == 4:  # gh: authentication required
        return "unauthenticated"
    match = _HTTP_CODE_RE.search(stderr or "")
    code = int(match.group(1)) if match else None
    if code == 401:
        return "unauthenticated"
    if code in (404, 422):
        return "not-found"
    if code == 429 or (code == 403 and "rate limit" in stderr.lower()):
        return "rate-limited"
    if code == 403:
        return "forbidden"
    return "network"


_SYSTEMIC_HINTS = {
    "unauthenticated": "Every target failed authentication: run `gh auth status` (or `gh auth login`), "
                       "then `campaign resume`.",
    "network": "Every target failed to reach GitHub: check the connection, then `campaign resume`.",
    "rate-limited": "Every target hit GitHub's rate limit: wait for it to reset, then `campaign resume`.",
    "forbidden": "GitHub refused every target (HTTP 403): authorize your token for the organization's "
                 "SSO, or give it access to these repositories, then `campaign resume`.",
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
    if not isinstance(brief, dict):
        _emit_error("Brief file is not a YAML mapping", "INVALID_BRIEF")
        return 2
    targets = brief.get("targets", [])
    if not isinstance(targets, list):
        _emit_error("Brief file 'targets' is not an array", "INVALID_BRIEF")
        return 2
    malformed = _malformed_target(targets)
    if malformed is not None:
        _emit_error(malformed, "INVALID_BRIEF")
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
            "error_class": None,
        }

        def fail(message: str, error_class: str) -> None:
            record["error"] = message
            record["error_class"] = error_class
            error_classes.append(error_class)
            results.append(record)

        if repo_url is None:
            fail(f"Skill '{name}' has no repo_url in brief targets", "other")
            continue

        parsed = parse_owner_repo(repo_url)
        if parsed is None:
            fail(f"Could not parse owner/repo from '{repo_url}'", "other")
            continue
        owner, repo = parsed
        record["owner"], record["repo"] = owner, repo

        # One REST call proves access and names the default branch.
        rc, out, err = runner(["gh", "api", f"repos/{owner}/{repo}", "--jq", ".default_branch"])
        if rc != 0:
            fail(err.strip() or f"gh api repos/{owner}/{repo} failed", _classify_error(rc, err))
            continue

        ref = skill.get("pin") or out.strip()
        record["ref"] = ref

        rc, out, err = runner(["gh", "api", f"repos/{owner}/{repo}/commits/{ref}", "--jq", ".sha"])
        if rc != 0:
            fail(err.strip() or f"could not resolve commit for ref '{ref}'", _classify_error(rc, err))
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
