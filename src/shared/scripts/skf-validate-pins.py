# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Validate Pins — resolve and validate version pins for a GitHub repository.

Shared pin validation script consumed by skf-analyze-source (AN auto-scope,
deepwiki --pin) and campaign workflows.  Validates that a user-supplied --pin
resolves to an existing tag or branch, or auto-resolves the latest release tag
when no --pin is provided.

Tag matching priority mirrors source-resolution-protocols.md:

  1. Exact match:   {pin}
  2. v-prefixed:    v{pin}
  3. Package scope: {name}@{pin}, @{scope}/{name}@{pin}
  4. Crate prefix:  {name}/v{pin}, {name}/{pin}, {name}-v{pin}

CLI:
  uv run src/shared/scripts/skf-validate-pins.py \\
      --repo-url <url> [--pin <version>] [--format tag|branch|any]

Input:
  --repo-url   GitHub repository URL (required)
  --pin        Version pin to validate (optional — resolves latest release when absent)
  --format     Restrict matching to tag, branch, or any (optional, default: any)

Output (JSON on stdout):
  {
    "status":       "valid" | "invalid" | "resolved",
    "pin":          "<input_pin_or_null>",
    "resolved_ref": "<matched_tag_or_branch>",
    "ref_type":     "tag" | "branch",
    "version":      "<semver_or_null>",
    "suggestions":  ["<nearest_tags_on_invalid>"]
  }

Exit codes:
  0  valid/resolved (pin matches a tag or branch, or latest release resolved)
  1  invalid (no match found for the supplied pin, or no releases for auto-resolve)
  2  error (invalid args, gh not found, network error, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

_GITHUB_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

_SEMVER_RE = re.compile(
    r"^v?(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?(?:\+[a-zA-Z0-9.]+)?)$"
)


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------

def _run_gh(args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except FileNotFoundError:
        return None


def _check_gh_available() -> bool:
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        return False


def _run_git(args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Version extraction
# ---------------------------------------------------------------------------

def extract_version(tag: str) -> Optional[str]:
    m = _SEMVER_RE.match(tag)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Tag listing
# ---------------------------------------------------------------------------

def list_tags(owner: str, repo: str, repo_url: str) -> List[str]:
    raw = _run_gh([
        "api", f"repos/{owner}/{repo}/tags",
        "--paginate", "--jq", ".[].name",
    ])
    if raw:
        return [t for t in raw.splitlines() if t.strip()]

    raw = _run_git(["ls-remote", "--tags", repo_url])
    if raw:
        tags = []
        for line in raw.splitlines():
            parts = line.split("refs/tags/")
            if len(parts) == 2:
                tag = parts[1].strip()
                if not tag.endswith("^{}"):
                    tags.append(tag)
        return tags

    return []


# ---------------------------------------------------------------------------
# Branch verification
# ---------------------------------------------------------------------------

def check_branch_exists(repo_url: str, branch: str) -> bool:
    raw = _run_git(["ls-remote", "--heads", repo_url, branch])
    if raw and branch in raw:
        return True
    return False


# ---------------------------------------------------------------------------
# Tag matching (mirrors source-resolution-protocols.md)
# ---------------------------------------------------------------------------

def _derive_name_from_url(owner: str, repo: str) -> str:
    return repo.lower()


def match_tag(pin: str, tags: List[str], owner: str, repo: str) -> Optional[str]:
    name = _derive_name_from_url(owner, repo)

    candidates = [
        pin,
        f"v{pin}",
        f"{name}@{pin}",
        f"{name}/v{pin}",
        f"{name}/{pin}",
        f"{name}-v{pin}",
    ]

    for candidate in candidates:
        if candidate in tags:
            return candidate

    return None


# ---------------------------------------------------------------------------
# Suggestion generation
# ---------------------------------------------------------------------------

def _semver_sort_key(tag: str) -> Tuple:
    v = extract_version(tag)
    if v is None:
        return (0, 0, 0, tag)
    parts = v.split("-")[0].split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return (0, 0, 0, tag)


def generate_suggestions(pin: str, tags: List[str], max_count: int = 5) -> List[str]:
    if not tags:
        return []

    prefixes_to_try = []
    if "." in pin:
        prefixes_to_try.append(pin.rsplit(".", 1)[0] + ".")
        prefixes_to_try.append(pin.split(".")[0])
    prefixes_to_try.append(pin)

    for prefix in prefixes_to_try:
        prefix_matches = [t for t in tags if t.startswith(prefix)]
        if prefix_matches:
            sorted_matches = sorted(prefix_matches, key=_semver_sort_key, reverse=True)
            return sorted_matches[:max_count]

    sorted_tags = sorted(tags, key=_semver_sort_key, reverse=True)
    return sorted_tags[:max_count]


# ---------------------------------------------------------------------------
# Latest release resolution
# ---------------------------------------------------------------------------

def resolve_latest_release(owner: str, repo: str) -> Optional[str]:
    raw = _run_gh([
        "api", f"repos/{owner}/{repo}/releases/latest",
        "--jq", ".tag_name",
    ])
    if raw and raw != "null":
        return raw.strip()

    raw = _run_gh([
        "api", f"repos/{owner}/{repo}/tags",
        "--jq", ".[0].name",
    ])
    if raw and raw != "null":
        return raw.strip()

    return None


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------

def validate_pin(
    repo_url: str,
    pin: Optional[str] = None,
    format_filter: str = "any",
) -> Dict[str, Any]:
    m = _GITHUB_URL_RE.match(repo_url.strip())
    if not m:
        return {
            "status": "invalid",
            "pin": pin,
            "resolved_ref": None,
            "ref_type": None,
            "version": None,
            "suggestions": [],
        }

    owner, repo = m.group(1), m.group(2)

    if pin is None:
        tag = resolve_latest_release(owner, repo)
        if tag is None:
            return {
                "status": "invalid",
                "pin": None,
                "resolved_ref": None,
                "ref_type": None,
                "version": None,
                "suggestions": [],
            }
        return {
            "status": "resolved",
            "pin": None,
            "resolved_ref": tag,
            "ref_type": "tag",
            "version": extract_version(tag),
            "suggestions": [],
        }

    tags: List[str] = []
    if format_filter in ("tag", "any"):
        tags = list_tags(owner, repo, repo_url)
        matched = match_tag(pin, tags, owner, repo)
        if matched:
            return {
                "status": "valid",
                "pin": pin,
                "resolved_ref": matched,
                "ref_type": "tag",
                "version": extract_version(matched),
                "suggestions": [],
            }

    if format_filter in ("branch", "any"):
        if check_branch_exists(repo_url, pin):
            return {
                "status": "valid",
                "pin": pin,
                "resolved_ref": pin,
                "ref_type": "branch",
                "version": None,
                "suggestions": [],
            }

    if not tags:
        tags = list_tags(owner, repo, repo_url)
    suggestions = generate_suggestions(pin, tags)

    return {
        "status": "invalid",
        "pin": pin,
        "resolved_ref": None,
        "ref_type": None,
        "version": None,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and resolve version pins for a GitHub repository.",
    )
    parser.add_argument("--repo-url", required=True, help="GitHub repository URL")
    parser.add_argument("--pin", default=None, help="Version pin to validate")
    parser.add_argument(
        "--format",
        choices=["tag", "branch", "any"],
        default="any",
        help="Restrict matching to tag, branch, or any (default: any)",
    )
    args = parser.parse_args()

    if not _check_gh_available():
        json.dump({"error": "gh CLI not found", "code": "GH_NOT_FOUND"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    m = _GITHUB_URL_RE.match(args.repo_url.strip())
    if not m:
        json.dump(
            {"error": f"Not a GitHub URL: {args.repo_url}", "code": "INVALID_URL"},
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 2

    try:
        result = validate_pin(args.repo_url, args.pin, args.format)
    except Exception as exc:
        json.dump({"error": str(exc), "code": "VALIDATION_ERROR"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")

    if result["status"] == "invalid":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
