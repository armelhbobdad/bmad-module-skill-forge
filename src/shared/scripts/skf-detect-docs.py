# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Detect Docs — discover documentation URLs for a GitHub repository.

Standalone doc-detection script that discovers documentation URLs through
multiple methods.  BS, CS, AS, and campaign workflows all locate a repo's
docs through this shared entry point, eliminating duplicate detection logic.

Detection chain (all four methods attempted, results aggregated):

  1. homepageUrl    — GitHub repo metadata homepage field
  2. readme_link    — links parsed from the repo README
  3. pages_api      — GitHub Pages site URL
  4. docs_folder    — markdown files in the repo's docs/ directory

CLI:
  uv run src/shared/scripts/skf-detect-docs.py \\
      --repo-url <url> [--local-path <path>] [--skip-pages-api]

Input:
  --repo-url        GitHub repository URL (required)
  --local-path      local clone path for docs/ folder scan (optional)
  --skip-pages-api  skip GitHub Pages API detection (optional flag)

Output (JSON array on stdout):
  [
    {
      "url":          "https://docs.example.com",
      "detected_via": "homepageUrl",
      "content_hash": "sha256:a1b2c3...",
      "content_type": "api-docs"
    }
  ]

Exit codes:
  0  found >=1 documentation source
  1  no documentation sources found (empty array)
  2  error (invalid args, gh not found, etc.)

---------------------------------------------------------------------------
Subcommand: compare-hashes
---------------------------------------------------------------------------

Doc-drift detection for audit-skill.  Given a set of tracked doc sources
(each `{url, content_hash}`), re-fetch every URL, hash the response bytes with
the SAME fetch+sha256 primitive the compile side used, and classify each entry
as changed / unchanged / fetch_failed / skipped_null_hash.  This replaces the
per-URL fetch/hash/compare/count prose at
`src/skf-audit-skill/references/step-doc-drift.md` §2-3 — the model no longer
orchestrates HTTP GETs or computes sha256 by hand, and correctness no longer
depends on whether a WebFetch tool is wired.

  uv run src/shared/scripts/skf-detect-docs.py compare-hashes <source>

Input `<source>`:
  - a path to a JSON file that is EITHER an array of `{url, content_hash}`
    entries OR an object with a `doc_sources` array (e.g. a skill's
    metadata.json), OR
  - `-` to read that JSON from stdin.

Output (JSON object on stdout):
  {
    "changed":           [{"url","old_hash","new_hash"}],
    "unchanged":         [{"url"}],
    "fetch_failed":      [{"url","old_hash","reason"}],
    "skipped_null_hash": [{"url"}],
    "stats": {"total_tracked","changed","unchanged",
              "fetch_failed","skipped_null_hash"}
  }

Each list is stably sorted by url.  Stored hashes are normalized (leading
`algo:` prefix stripped) before comparison so a bare-hex writer form still
matches.  Exit 0 on any well-formed input (never blocks the informational
audit); exit 2 on malformed args or JSON.

---------------------------------------------------------------------------
Subcommand: hash-urls
---------------------------------------------------------------------------

Compile-time `doc_sources[]` for docs-only skills (create-skill step 5a).
The detect path above needs a GitHub repository; a docs-only brief has none
— its `source_repo` is the documentation site and its corpus is the brief's
`doc_urls`.  This subcommand fetches each URL and hashes the raw response
bytes with the SAME primitive `compare-hashes` uses, so a hash recorded here
compares byte-for-byte at audit time.  (Hashing the markdown a web-fetch tool
rendered would not: the audit re-fetches the raw bytes.)

  uv run src/shared/scripts/skf-detect-docs.py hash-urls <source>

Input `<source>`:
  - a path to a JSON file that is EITHER an array whose items are URL
    strings or `{url, ...}` objects (the brief's `doc_urls[]` entry shape)
    OR an object with a `doc_urls` array (the brief block itself), OR
  - `-` to read that JSON from stdin.

Output (JSON object on stdout):
  {
    "doc_sources":  [{"url", "detected_via": "brief_doc_urls",
                      "content_hash": "sha256:..."|null, "recorded_at"}],
    "fetch_failed": [{"url", "reason"}],
    "stats": {"total", "hashed", "fetch_failed", "invalid"}
  }

URLs keep their input order and are deduplicated on first occurrence; an
entry without a usable url string is dropped and counted under
`stats.invalid`.  A URL that cannot be fetched still gets an entry with
`content_hash: null` — the audit side files it under `skipped_null_hash`
instead of reporting drift.  `doc_sources` is already in the metadata.json
schema, and the whole object is valid `compare-hashes` input.  Exit 0 on any
well-formed input; exit 2 on malformed args or JSON.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_GITHUB_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

USER_AGENT = "skf-detect-docs/1.0 (+https://github.com/armelhbobdad/bmad-module-skill-forge)"

_FETCH_TIMEOUT = 15

# ---------------------------------------------------------------------------
# URL exclusion patterns (AC #5)
# ---------------------------------------------------------------------------

_EXCLUSION_PATTERNS = re.compile(
    r"(?:^|/)(?:"
    r"CHANGELOG|CHANGES|HISTORY"
    r"|MIGRATION|MIGRATING|UPGRADE"
    r"|RELEASE|release-notes|releases"
    r"|CONTRIBUTING|CODE_OF_CONDUCT"
    r"|LICENSE|SECURITY"
    r")(?:\.|/|$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# README link scanning patterns
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_HTML_LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)
_BARE_URL_RE = re.compile(r"^(https?://\S+)$", re.MULTILINE)

# `docs?\.` (not `docs\.`) so a `doc.` subdomain matches too — language doc
# sites use the singular form (doc.rust-lang.org, doc.qt.io).
_DOC_DOMAIN_RE = re.compile(
    r"(?:docs?\.|\.readthedocs\.|wiki\.|documentation\.)",
    re.IGNORECASE,
)

# Language reference/guide path segments (a Book, a std/library API, a tutorial)
# are doc URLs even on a bare domain (doc.rust-lang.org/book/, .../std/).
_DOC_PATH_RE = re.compile(
    r"(?:/docs/|/documentation/|/api/|/reference/|/guide/|/wiki/"
    r"|/book/|/std/|/library/|/tutorial/)",
    re.IGNORECASE,
)

_DOC_TEXT_RE = re.compile(
    r"(?:documentation|docs|api\s+reference|guide|wiki)",
    re.IGNORECASE,
)

_REJECT_URL_RE = re.compile(
    r"(?:"
    r"github\.com/[^/]+/[^/]+/(?:issues|pull|actions)"
    r"|img\.shields\.io"
    r"|badge"
    r"|\.(?:svg|png|gif|jpg|jpeg)(?:\?|$)"
    r"|travis-ci\."
    r"|circleci\."
    r"|npmjs\.com"
    r"|pypi\.org"
    r"|crates\.io"
    r"|twitter\.com|x\.com"
    r"|discord\.(?:gg|com)"
    r"|slack\.com"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Content type classification
# ---------------------------------------------------------------------------

_API_DOCS_RE = re.compile(r"(?:/api/|/reference/|/sdk/|api-docs|api\.)", re.IGNORECASE)
_GUIDE_RE = re.compile(
    r"(?:/guide/|/tutorial/|/getting-started|/quickstart|/howto)",
    re.IGNORECASE,
)


def _classify_content_type(url: str) -> str:
    if _API_DOCS_RE.search(url):
        return "api-docs"
    if _GUIDE_RE.search(url):
        return "guide"
    return "reference"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _is_excluded(url: str) -> bool:
    return bool(_EXCLUSION_PATTERNS.search(url))


def _is_github_self_url(url: str, owner: str, repo: str) -> bool:
    return bool(re.match(
        rf"https?://(?:www\.)?github\.com/{re.escape(owner)}/{re.escape(repo)}/?$",
        url,
        re.IGNORECASE,
    ))


def _is_doc_url(url: str, link_text: str = "") -> bool:
    if _REJECT_URL_RE.search(url):
        return False
    if _DOC_DOMAIN_RE.search(url):
        return True
    if _DOC_PATH_RE.search(url):
        return True
    if link_text and _DOC_TEXT_RE.search(link_text):
        return True
    return False


# ---------------------------------------------------------------------------
# gh CLI helper
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


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------

def _fetch_and_hash(url: str) -> Optional[str]:
    if url.startswith("file://"):
        try:
            local_path = url[7:]
            with open(local_path, "rb") as fh:
                content = fh.read()
            return "sha256:" + hashlib.sha256(content).hexdigest()
        except (OSError, IOError):
            return None
    try:
        # Request() itself raises ValueError on a scheme-less or relative URL;
        # it must sit inside the guard so a bad entry degrades to None.
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            content = resp.read()
        return "sha256:" + hashlib.sha256(content).hexdigest()
    except Exception:
        return None


# Leading algorithm-name prefix on a stored hash (`sha256:`, `sha1:`, ...) so a
# bare-hex writer form and the prefixed form compare equal.
_HASH_PREFIX_RE = re.compile(r"^[a-z0-9]+:")


def _normalize_hash(value: Optional[str]) -> Optional[str]:
    """Strip a leading `algo:` prefix from a hash so bare-hex and prefixed
    forms compare equal. Returns None for non-string input. Idempotent."""
    if not isinstance(value, str):
        return None
    return _HASH_PREFIX_RE.sub("", value, count=1)


def _fetch_and_hash_reason(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Byte-symmetric sibling of `_fetch_and_hash` that surfaces WHY a fetch
    failed for drift reporting.

    Uses the identical fetch+sha256 primitive as the compile side — same
    `USER_AGENT`, same `_FETCH_TIMEOUT`, sha256 of the raw response bytes with
    the `sha256:` prefix — so a hash produced here compares byte-for-byte
    against a `content_hash` written by `_fetch_and_hash` at compile time.

    Returns `(content_hash, None)` on success or `(None, reason)` on failure.
    Never raises: the doc-drift audit must never abort on a bad URL.
    """
    if url.startswith("file://"):
        local_path = url[7:]
        try:
            with open(local_path, "rb") as fh:
                content = fh.read()
        except OSError as exc:
            return None, f"local read failed: {exc}"
        return "sha256:" + hashlib.sha256(content).hexdigest(), None
    try:
        # Request() raises ValueError ("unknown url type") on a scheme-less or
        # relative URL — a legal brief entry, since the brief schema only
        # requires a non-empty string. Keep it inside the guard so one bad
        # entry lands in fetch_failed instead of aborting the whole run.
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    except ValueError as exc:
        return None, f"invalid URL: {exc}"
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            content = resp.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (socket.timeout, TimeoutError):
        return None, f"timeout after {_FETCH_TIMEOUT}s"
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return None, f"timeout after {_FETCH_TIMEOUT}s"
        return None, f"URL error: {reason}"
    except Exception as exc:  # never let a malformed URL crash the audit
        return None, f"fetch failed: {exc}"
    return "sha256:" + hashlib.sha256(content).hexdigest(), None


# ---------------------------------------------------------------------------
# Detection method 1 — homepageUrl
# ---------------------------------------------------------------------------

def _detect_homepage_url(owner: str, repo: str) -> List[Dict[str, Any]]:
    raw = _run_gh(["api", f"repos/{owner}/{repo}", "--jq", ".homepage"])
    if not raw or raw == "null":
        return []
    url = raw.strip()
    if not url:
        return []
    if _is_github_self_url(url, owner, repo):
        return []
    return [{"url": url, "detected_via": "homepageUrl", "content_type": _classify_content_type(url)}]


# ---------------------------------------------------------------------------
# Detection method 2 — README link scanning
# ---------------------------------------------------------------------------

def _detect_readme_links(owner: str, repo: str) -> List[Dict[str, Any]]:
    raw = _run_gh(["api", f"repos/{owner}/{repo}/readme"])
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    encoded = data.get("content", "")
    if not encoded:
        return []
    try:
        readme_text = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return []

    urls_with_text: List[tuple] = []
    for text, url in _MD_LINK_RE.findall(readme_text):
        urls_with_text.append((url.strip(), text.strip()))
    for url in _HTML_LINK_RE.findall(readme_text):
        urls_with_text.append((url.strip(), ""))
    for url in _BARE_URL_RE.findall(readme_text):
        urls_with_text.append((url.strip(), ""))

    results: List[Dict[str, Any]] = []
    seen: set = set()
    for url, text in urls_with_text:
        if not url.startswith("http"):
            continue
        if url in seen:
            continue
        if _is_doc_url(url, text):
            seen.add(url)
            results.append({
                "url": url,
                "detected_via": "readme_link",
                "content_type": _classify_content_type(url),
            })
    return results


# ---------------------------------------------------------------------------
# Detection method 3 — Pages API
# ---------------------------------------------------------------------------

def _detect_pages_api(owner: str, repo: str) -> List[Dict[str, Any]]:
    raw = _run_gh(["api", f"repos/{owner}/{repo}/pages", "--jq", ".html_url"])
    if not raw or raw == "null":
        return []
    url = raw.strip()
    if not url:
        return []
    return [{"url": url, "detected_via": "pages_api", "content_type": _classify_content_type(url)}]


# ---------------------------------------------------------------------------
# Detection method 4 — docs/ folder
# ---------------------------------------------------------------------------

def _detect_docs_folder(owner: str, repo: str, local_path: Optional[str] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if local_path:
        docs_dir = Path(local_path) / "docs"
        if docs_dir.is_dir():
            for md_file in sorted(docs_dir.rglob("*.md")):
                file_url = "file://" + md_file.as_posix()
                results.append({
                    "url": file_url,
                    "detected_via": "docs_folder",
                    "content_type": _classify_content_type(md_file.as_posix()),
                })
    else:
        raw = _run_gh(["api", f"repos/{owner}/{repo}/contents/docs"])
        if not raw:
            return []
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(entries, list):
            return []
        for entry in entries:
            name = entry.get("name", "")
            if not name.lower().endswith(".md"):
                continue
            download_url = entry.get("download_url", "")
            if download_url:
                results.append({
                    "url": download_url,
                    "detected_via": "docs_folder",
                    "content_type": _classify_content_type(download_url),
                })
    return results


# ---------------------------------------------------------------------------
# Main detection orchestrator
# ---------------------------------------------------------------------------

def detect(
    repo_url: str,
    local_path: Optional[str] = None,
    skip_pages_api: bool = False,
) -> List[Dict[str, Any]]:
    m = _GITHUB_URL_RE.match(repo_url.strip())
    if not m:
        return []

    owner, repo = m.group(1), m.group(2)

    all_results: List[Dict[str, Any]] = []
    all_results.extend(_detect_homepage_url(owner, repo))
    all_results.extend(_detect_readme_links(owner, repo))
    if not skip_pages_api:
        all_results.extend(_detect_pages_api(owner, repo))
    all_results.extend(_detect_docs_folder(owner, repo, local_path))

    filtered = [r for r in all_results if not _is_excluded(r["url"])]

    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for r in filtered:
        if r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)

    for entry in deduped:
        entry["content_hash"] = _fetch_and_hash(entry["url"])

    return deduped


# ---------------------------------------------------------------------------
# compare-hashes subcommand — doc-drift detection for audit-skill
# ---------------------------------------------------------------------------

def _load_doc_sources(raw_text: str, source_label: str) -> List[Any]:
    """Parse a compare-hashes input blob into a list of doc-source entries.

    Accepts either a top-level JSON array of `{url, content_hash}` entries or a
    top-level object with a `doc_sources` array (e.g. a skill's metadata.json).
    An object without `doc_sources` yields an empty list (nothing tracked).

    Raises ValueError on malformed JSON or an unexpected top-level shape.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {source_label}: {exc}") from exc
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = data.get("doc_sources")
        if entries is None:
            return []
        if not isinstance(entries, list):
            raise ValueError(f"`doc_sources` in {source_label} is not an array")
        return entries
    raise ValueError(
        f"{source_label} must be a JSON array or an object with a "
        f"`doc_sources` array; got {type(data).__name__}"
    )


def compare_doc_hashes(doc_sources: List[Any]) -> Dict[str, Any]:
    """Fetch/hash/compare each tracked doc source and categorize it.

    Deterministic: the same entries served the same upstream bytes always
    yield the same categorization. Every entry lands in exactly one bucket, so
    `stats.total_tracked` == the sum of the four category counts.
    """
    changed: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    fetch_failed: List[Dict[str, Any]] = []
    skipped_null_hash: List[Dict[str, Any]] = []

    for entry in doc_sources:
        if not isinstance(entry, dict):
            fetch_failed.append(
                {"url": "", "old_hash": None, "reason": "invalid entry: not an object"}
            )
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            fetch_failed.append({
                "url": url if isinstance(url, str) else "",
                "old_hash": entry.get("content_hash"),
                "reason": "invalid entry: missing url",
            })
            continue
        stored = entry.get("content_hash")
        if stored is None:
            # No baseline hash was recorded at compile time — nothing to
            # compare against, so skip the fetch entirely.
            skipped_null_hash.append({"url": url})
            continue
        new_hash, reason = _fetch_and_hash_reason(url)
        if new_hash is None:
            fetch_failed.append({"url": url, "old_hash": stored, "reason": reason})
        elif _normalize_hash(new_hash) == _normalize_hash(stored):
            unchanged.append({"url": url})
        else:
            changed.append({"url": url, "old_hash": stored, "new_hash": new_hash})

    changed.sort(key=lambda e: e["url"])
    unchanged.sort(key=lambda e: e["url"])
    fetch_failed.sort(key=lambda e: e["url"])
    skipped_null_hash.sort(key=lambda e: e["url"])

    total = len(changed) + len(unchanged) + len(fetch_failed) + len(skipped_null_hash)
    return {
        "changed": changed,
        "unchanged": unchanged,
        "fetch_failed": fetch_failed,
        "skipped_null_hash": skipped_null_hash,
        "stats": {
            "total_tracked": total,
            "changed": len(changed),
            "unchanged": len(unchanged),
            "fetch_failed": len(fetch_failed),
            "skipped_null_hash": len(skipped_null_hash),
        },
    }


def _cmd_compare_hashes(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py compare-hashes",
        description=(
            "Re-fetch each tracked doc URL, hash the response bytes, and "
            "compare against the stored content_hash to detect doc drift."
        ),
    )
    parser.add_argument(
        "source",
        help=(
            "path to a JSON file (array of {url, content_hash} entries, or an "
            "object with a doc_sources array such as metadata.json), or - to "
            "read that JSON from stdin"
        ),
    )
    args = parser.parse_args(argv)

    if args.source == "-":
        raw = sys.stdin.read()
        label = "<stdin>"
    else:
        path = Path(args.source)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            json.dump({"error": f"cannot read {path}: {exc}", "code": "READ_ERROR"}, sys.stderr)
            sys.stderr.write("\n")
            return 2
        label = str(path)

    try:
        doc_sources = _load_doc_sources(raw, label)
    except ValueError as exc:
        json.dump({"error": str(exc), "code": "INVALID_JSON"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    result = compare_doc_hashes(doc_sources)
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: hash-urls — docs-only doc_sources from the brief's doc_urls
# ---------------------------------------------------------------------------

# `doc_sources[].detected_via` value for entries that come from the brief's
# `doc_urls` (and the subpages step 3c fetched from them) rather than from
# repository detection. Listed in skf-create-skill/assets/skill-sections.md.
BRIEF_DOC_URLS_DETECTED_VIA = "brief_doc_urls"


def _load_url_list(raw_text: str, source_label: str) -> List[Any]:
    """Parse a hash-urls input blob into a list of URL entries.

    Accepts a top-level JSON array whose items are URL strings or objects
    with a `url` key (the brief's `doc_urls[]` entry shape), or a top-level
    object with a `doc_urls` array (the brief block itself). An object without
    `doc_urls` yields an empty list (nothing to hash).

    Raises ValueError on malformed JSON or an unexpected top-level shape.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {source_label}: {exc}") from exc
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = data.get("doc_urls")
        if entries is None:
            return []
        if not isinstance(entries, list):
            raise ValueError(f"`doc_urls` in {source_label} is not an array")
        return entries
    raise ValueError(
        f"{source_label} must be a JSON array or an object with a "
        f"`doc_urls` array; got {type(data).__name__}"
    )


def hash_urls(entries: List[Any], recorded_at: Optional[str] = None) -> Dict[str, Any]:
    """Fetch and hash each URL into a compile-time `doc_sources[]` entry.

    Byte-symmetric with `compare_doc_hashes`: both go through
    `_fetch_and_hash_reason`, so a hash recorded here reads as `unchanged` at
    audit time for unchanged bytes. URLs keep their input order (brief order,
    then discovered subpages) and are deduplicated on first occurrence. A URL
    that cannot be fetched still gets an entry with `content_hash: None`, which
    the audit side skips rather than reporting as drift.
    """
    stamp = recorded_at or datetime.now(timezone.utc).isoformat()
    doc_sources: List[Dict[str, Any]] = []
    fetch_failed: List[Dict[str, Any]] = []
    seen: set = set()
    invalid = 0
    for entry in entries:
        url = entry.get("url") if isinstance(entry, dict) else entry
        if not isinstance(url, str) or not url.strip():
            invalid += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        content_hash, reason = _fetch_and_hash_reason(url)
        doc_sources.append({
            "url": url,
            "detected_via": BRIEF_DOC_URLS_DETECTED_VIA,
            "content_hash": content_hash,
            "recorded_at": stamp,
        })
        if content_hash is None:
            fetch_failed.append({"url": url, "reason": reason})
    return {
        "doc_sources": doc_sources,
        "fetch_failed": fetch_failed,
        "stats": {
            "total": len(doc_sources),
            "hashed": len(doc_sources) - len(fetch_failed),
            "fetch_failed": len(fetch_failed),
            "invalid": invalid,
        },
    }


def _cmd_hash_urls(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py hash-urls",
        description=(
            "Fetch each documentation URL, hash the response bytes, and emit "
            "compile-time doc_sources entries (detected_via: brief_doc_urls) "
            "for a docs-only skill."
        ),
    )
    parser.add_argument(
        "source",
        help=(
            "path to a JSON file (array of URL strings or {url, ...} objects, "
            "or an object with a doc_urls array such as the brief's block), "
            "or - to read that JSON from stdin"
        ),
    )
    args = parser.parse_args(argv)

    if args.source == "-":
        raw = sys.stdin.read()
        label = "<stdin>"
    else:
        path = Path(args.source)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            json.dump({"error": f"cannot read {path}: {exc}", "code": "READ_ERROR"}, sys.stderr)
            sys.stderr.write("\n")
            return 2
        label = str(path)

    try:
        entries = _load_url_list(raw, label)
    except ValueError as exc:
        json.dump({"error": str(exc), "code": "INVALID_JSON"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    result = hash_urls(entries)
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8 (issue #465).

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (raw UTF-8 input on stdin for `compare-hashes -` and
    `hash-urls -`). Preserves each stream's existing error handler —
    reconfigure(encoding=...) alone would reset it to 'strict', downgrading
    e.g. an already-UTF-8 stderr on Linux. For stdin this must run before the
    first read. Skips in-process test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main() -> int:
    _force_utf8(sys.stdin, sys.stdout)
    # Additive subcommand: route `compare-hashes ...` to the doc-drift path
    # before the existing detect parser runs. The default (no subcommand)
    # invocation `--repo-url <url> ...` is unchanged.
    if len(sys.argv) > 1 and sys.argv[1] == "compare-hashes":
        return _cmd_compare_hashes(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "hash-urls":
        return _cmd_hash_urls(sys.argv[2:])

    parser = argparse.ArgumentParser(
        description="Detect documentation URLs for a GitHub repository.",
    )
    parser.add_argument("--repo-url", required=True, help="GitHub repository URL")
    parser.add_argument("--local-path", default=None, help="Local clone path for docs/ folder scan")
    parser.add_argument("--skip-pages-api", action="store_true", help="Skip GitHub Pages API detection")
    args = parser.parse_args()

    if not _check_gh_available():
        json.dump({"error": "gh CLI not found", "code": "GH_NOT_FOUND"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    m = _GITHUB_URL_RE.match(args.repo_url.strip())
    if not m:
        json.dump({"error": f"Not a GitHub URL: {args.repo_url}", "code": "INVALID_URL"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    try:
        results = detect(args.repo_url, args.local_path, args.skip_pages_api)
    except Exception as exc:
        json.dump({"error": str(exc), "code": "DETECTION_ERROR"}, sys.stderr)
        sys.stderr.write("\n")
        return 2

    json.dump(results, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
