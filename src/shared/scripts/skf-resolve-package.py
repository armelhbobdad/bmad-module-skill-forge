# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Resolve Package — resolve a package name to a GitHub repository URL.

Walks the canonical fallback chain documented in
`src/skf-quick-skill/references/registry-resolution.md`:

  1. npm registry        (JavaScript/TypeScript)
  2. PyPI registry       (Python)
  3. crates.io registry  (Rust)

Per-call timeout (default 10s); a timeout is treated as a soft failure
and the resolver falls through to the next entry. Web-search fallback
is intentionally NOT in this helper — registries are deterministic;
web search is judgment, and stays in the LLM step.

CLI:

  python3 skf-resolve-package.py <package_name> [--timeout 10]

Output JSON (stdout):

  status:           "ok" | "fallthrough"
  package_name:     "<input>"
  resolved_url:     "https://github.com/<owner>/<repo>"  (when status == "ok")
  repo_owner:       "<owner>"                            (when status == "ok")
  repo_name:        "<repo>"                             (when status == "ok")
  registry_used:    "npm" | "pypi" | "crates"            (when status == "ok")
  registries_tried: ["npm", ...]
  registry_outcomes: {"npm": "ok|404|timeout|error|no-github-link", ...}

Exit codes:

  0  status == "ok"
  1  status == "fallthrough" — every registry replied without a GitHub
     URL; the LLM step should fall back to web search.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

REGISTRY_TIMEOUT_SECONDS = 10.0
USER_AGENT = "skf-resolve-package/1.0 (+https://github.com/armelhbobdad/bmad-module-skill-forge)"

_GITHUB_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_github_url(url: str) -> Optional[tuple[str, str, str]]:
    """Parse a GitHub URL/string into (canonical_url, owner, repo).

    Handles the variants registries actually emit:
      - https://github.com/owner/repo
      - http://github.com/owner/repo
      - github.com/owner/repo
      - git+https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
      - github:owner/repo (npm shortcut)
    """
    if not url or not isinstance(url, str):
        return None

    s = url.strip()

    if s.startswith("github:"):
        rest = s[len("github:") :]
        if "/" in rest:
            owner, _, repo = rest.partition("/")
            repo = repo.removesuffix(".git").rstrip("/")
            if owner and repo:
                return f"https://github.com/{owner}/{repo}", owner, repo
        return None

    if s.startswith("git+"):
        s = s[len("git+") :]

    if s.startswith("git@github.com:"):
        rest = s[len("git@github.com:") :]
        rest = rest.removesuffix(".git").rstrip("/")
        if "/" in rest:
            owner, _, repo = rest.partition("/")
            if owner and repo:
                return f"https://github.com/{owner}/{repo}", owner, repo
        return None

    if s.startswith("github.com/"):
        s = "https://" + s

    m = _GITHUB_URL_RE.match(s)
    if m:
        owner, repo = m.group(1), m.group(2)
        return f"https://github.com/{owner}/{repo}", owner, repo

    return None


def _http_get_json(url: str, timeout: float) -> tuple[Optional[dict], str]:
    """Fetch JSON. Returns (payload_or_None, outcome).

    Outcome values:
      "ok"       — valid JSON object returned
      "404"      — HTTP 404 (package does not exist on this registry)
      "timeout"  — socket / urlopen timed out
      "error"    — any other transport / parse error
    """
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload, "ok"
            return None, "error"
    except urllib.error.HTTPError as e:
        return None, "404" if e.code == 404 else "error"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            return None, "timeout"
        return None, "error"
    except (TimeoutError, socket.timeout):
        return None, "timeout"
    except (ValueError, json.JSONDecodeError):
        return None, "error"


def try_npm(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str]], str]:
    """Try the npm registry. Returns (parsed_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="@")
    url = f"https://registry.npmjs.org/{encoded}"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    candidates: list[str] = []
    repo = payload.get("repository")
    if isinstance(repo, dict) and isinstance(repo.get("url"), str):
        candidates.append(repo["url"])
    elif isinstance(repo, str):
        candidates.append(repo)
    homepage = payload.get("homepage")
    if isinstance(homepage, str):
        candidates.append(homepage)
    for c in candidates:
        parsed = parse_github_url(c)
        if parsed:
            return parsed, "ok"
    return None, "no-github-link"


def try_pypi(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str]], str]:
    """Try the PyPI registry. Returns (parsed_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="")
    url = f"https://pypi.org/pypi/{encoded}/json"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    info = payload.get("info") or {}
    candidates: list[str] = []
    project_urls = info.get("project_urls") or {}
    if isinstance(project_urls, dict):
        for key in ("Source", "Source Code", "Repository", "Homepage"):
            v = project_urls.get(key)
            if isinstance(v, str):
                candidates.append(v)
    home_page = info.get("home_page")
    if isinstance(home_page, str):
        candidates.append(home_page)
    for c in candidates:
        parsed = parse_github_url(c)
        if parsed:
            return parsed, "ok"
    return None, "no-github-link"


def try_crates(package_name: str, timeout: float) -> tuple[Optional[tuple[str, str, str]], str]:
    """Try the crates.io registry. Returns (parsed_or_None, outcome)."""
    encoded = urllib.parse.quote(package_name, safe="")
    url = f"https://crates.io/api/v1/crates/{encoded}"
    payload, outcome = _http_get_json(url, timeout)
    if payload is None:
        return None, outcome
    crate = payload.get("crate") or {}
    for key in ("repository", "homepage"):
        v = crate.get(key)
        if isinstance(v, str):
            parsed = parse_github_url(v)
            if parsed:
                return parsed, "ok"
    return None, "no-github-link"


_RESOLVER_NAMES: tuple[tuple[str, str], ...] = (
    ("npm", "try_npm"),
    ("pypi", "try_pypi"),
    ("crates", "try_crates"),
)


def resolve_package(package_name: str, timeout: float = REGISTRY_TIMEOUT_SECONDS) -> dict:
    registries_tried: list[str] = []
    outcomes: dict[str, str] = {}

    # Dynamic lookup so test code can monkeypatch try_npm / try_pypi / try_crates
    # without re-binding entries in a module-level tuple of function refs.
    for name, fn_name in _RESOLVER_NAMES:
        registries_tried.append(name)
        fn = globals()[fn_name]
        result, outcome = fn(package_name, timeout)
        outcomes[name] = outcome
        if result is not None:
            url, owner, repo = result
            return {
                "status": "ok",
                "package_name": package_name,
                "resolved_url": url,
                "repo_owner": owner,
                "repo_name": repo,
                "registry_used": name,
                "registries_tried": registries_tried,
                "registry_outcomes": outcomes,
            }

    return {
        "status": "fallthrough",
        "package_name": package_name,
        "registries_tried": registries_tried,
        "registry_outcomes": outcomes,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a package name to a GitHub repository URL via npm/PyPI/crates.io.",
    )
    parser.add_argument(
        "package_name",
        help="Package name to resolve (e.g., lodash, @tanstack/query, requests, serde).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=REGISTRY_TIMEOUT_SECONDS,
        help=f"Per-registry timeout in seconds (default: {REGISTRY_TIMEOUT_SECONDS}).",
    )
    args = parser.parse_args(argv)

    result = resolve_package(args.package_name, timeout=args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
