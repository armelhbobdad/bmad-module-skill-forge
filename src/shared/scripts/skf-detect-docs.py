# /// script
# requires-python = ">=3.11"
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
`src/skf-audit-skill/references/doc-drift.md` §2-3: the model no longer
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
Subcommand: refresh-hashes
---------------------------------------------------------------------------

Records the new hashes of the documents a `compare-hashes` run found
changed, once update-skill has re-read them (update-skill write.md §2), so
the next comparison starts from the documents this update used.

  uv run src/shared/scripts/skf-detect-docs.py refresh-hashes \\
      <metadata.json> --compare <compare-hashes output>

Each `doc_sources[]` entry whose url is in the comparison's `changed[]`
takes that entry's `new_hash` as its `content_hash` and the current UTC
time as its `recorded_at`; every other entry and every other key of the
file stays as it was. The file is rewritten through a temporary file and
one rename.

Output (JSON object on stdout):
  {"metadata": <path>, "refreshed": [urls], "not_found": [changed urls
   that metadata.json does not track]}

Exit 0 once written; exit 2 on malformed args, JSON that is not the shape
named, or a file that cannot be read or written.

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

---------------------------------------------------------------------------
Subcommand: readme-entry
---------------------------------------------------------------------------

The README entry create-skill step 5a adds to `doc_sources[]` when detection
found none.  The helper picks the README, builds its URL and hashes it with
the `hash-urls` primitive, so the model never parses the repository or
builds the URL by hand.

  uv run src/shared/scripts/skf-detect-docs.py readme-entry \\
      --source-repo <repo> --ref <ref> [--local-root <path>]

Input:
  --source-repo  the brief's source_repo
  --ref          the ref the skill was built from: a tag, branch or commit,
                 `HEAD` for the default branch (also for an empty, `null` or
                 `none` value), `local` for a local source
  --local-root   the folder the source was read from, when it is a local
                 folder (a local source, or the tree create-skill read a
                 remote one into); the README is picked from its files

A local source (`--ref local`) records `file://` and the absolute path of
its README, with `/` separators and no percent-encoding, as
`_fetch_and_hash` reads it back; its folder is --local-root, else
--source-repo.  A GitHub source (an https, ssh or git URL, the scp-like
`git@github.com:owner/repo`, or the `owner/repo` shorthand; a trailing
`.git` is dropped) records the raw file at --ref:
`https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<README>`.  The
README is picked from the top-level files of --local-root, or, without a
local folder, from the repository's top level at --ref through the GitHub
API: `README.md` in any letter case first, then a README with no language
suffix (`README.rst`, `README.markdown`, `README`), then the first other
README in name order (a translation such as `README-ja.md`, which sorts
before `README.md`).  With none listed it is `README.md`.  Any other source
gets no entry.

Output (JSON object on stdout): the `hash-urls` object for the one URL,
with `detected_via: "readme_always"` on its entry, plus
  "skip_reason": null | "not-github"  (no entry: a source on another host)

Exit 0 once JSON is printed; exit 2 on malformed args.

---------------------------------------------------------------------------
Subcommand: page-metrics
---------------------------------------------------------------------------

create-skill step 3c fetches each `doc_urls` page and looks for its
subpages when the page is a documentation root with little API content of
its own (a Mintlify, Docusaurus, ReadTheDocs or GitBook landing page). This
subcommand measures a fetched page, saved as markdown, so the step reads the
decision instead of counting words and link lines by eye.

  uv run src/shared/scripts/skf-detect-docs.py page-metrics \\
      --url <url> <file>

Input: --url is the page's URL; <file> is its markdown, or `-` for stdin.

Output (JSON object on stdout):
  {
    "url": "<url>",
    "path_segments":   N,     # non-empty segments of the URL path
    "root_like":       bool,  # N <= 1, or the path ends in `/`, `/index`
                              #   or `/index.html`
    "code_fences":     N,     # fenced code blocks (``` or ~~~)
    "table_rows":      N,     # table separator rows (`|---|`), one a table
    "signature_hits":  N,     # `def `, `function `, `fn `, `func `,
                              #   `export ` as words
    "link_lines":      N,     # non-empty lines holding only markdown links
    "non_empty_lines": N,
    "link_line_ratio": 0.0-1.0,  # link_lines / non_empty_lines, 4 places
    "word_count":      N,     # words, link targets left out
    "trigger1":        bool,  # root_like, no code fence, table row or
                              #   signature, and link_line_ratio > 0.7
    "trigger2":        bool,  # root_like and word_count < 2000
    "discover_subpages": bool # trigger1 or trigger2
  }

A link line is a line whose text, once its list marker, quote marker or
heading marks and its `[text](url)` links are taken out, holds no letter or
digit. Exit 0 once JSON is printed; exit 2 on malformed args or an input
that cannot be read or decoded as UTF-8.

---------------------------------------------------------------------------
Subcommand: filter-urls
---------------------------------------------------------------------------

The subpages step 3c may fetch for a root page: the URLs a site map, a
sitemap.xml or a crawl found, cut to the root page's own site.

  uv run src/shared/scripts/skf-detect-docs.py filter-urls \\
      --root <url> <source>

Input `<source>` (a file, or `-` for stdin), read as UTF-8 and gunzipped
first when it is gzip compressed (a `.xml.gz` sitemap):
  - a sitemap.xml (its `<loc>` values), or
  - a JSON array of URL strings or `{url, title?}` objects, or an object
    with such an array under `links` or `urls` (a map tool's result), or
  - one URL per line.
A URL given as a path from the site root (`/docs/api`) is read against
the root URL.

A URL is kept when it is http or https, on the root URL's registrable
domain (any subdomain of it), not the root page itself, not a repeat once
its `#fragment` is dropped (scheme and host compared in any letter case),
and has no path segment, less its file extension, that is one of
SUBPAGE_EXCLUDED_WORDS (`blog`, `changelog`, `pricing`, `about`,
`careers`): such a segment names a section with no API content, while a
longer one (`about-the-rest-api`) can head a section of API pages. The
registrable domain is worked out without a public suffix list: the last two
labels of the host, or the last three when the last two are a hosting
suffix (HOSTED_SUFFIXES: `github.io`, `readthedocs.io` and the like, where
each subdomain is another owner's site) or a country-code second level
(`co.uk`, `com.au`). An IP address or a one-label host is its own domain.

Output (JSON object on stdout):
  {
    "root": "<url>",
    "registrable_domain": "example.com",
    "kept": [{"url", "title": "..." | null,
              "terms": ["api", "reference", ...]}],   # input order
    "sitemaps": ["<url>", ...],   # same-site .xml / .xml.gz URLs
    "stats": {"input", "kept", "other_domain", "excluded_path",
              "not_http", "duplicate", "root", "sitemap"}
  }

`terms` lists the API words (API_TERMS) the URL path or title holds, to
help choose the most relevant subpages; choosing them is the caller's call.
A same-site URL ending in `.xml` or `.xml.gz` is a sitemap, not a page (a
sitemap index lists them): it goes to `sitemaps`, for the caller to fetch
and filter in turn.
Exit 0 once JSON is printed; exit 2 on malformed args, an input that
cannot be read or decoded as UTF-8, malformed JSON or a root URL that is
not http or https.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
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
# Subcommand: refresh-hashes: record the hashes compare-hashes found changed
# ---------------------------------------------------------------------------

def refresh_doc_hashes(
    metadata: Dict[str, Any], comparison: Dict[str, Any], recorded_at: Optional[str] = None
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """(metadata with the changed documents' new hashes, refreshed urls, urls it does not track).

    Raises ValueError when `doc_sources` or `changed` is not an array.
    """
    entries = metadata.get("doc_sources")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("`doc_sources` in the metadata is not an array")
    changed = comparison.get("changed")
    if not isinstance(changed, list):
        raise ValueError("the comparison has no `changed` array: is it compare-hashes output?")
    new_hashes = {
        e["url"]: e["new_hash"] for e in changed
        if isinstance(e, dict) and isinstance(e.get("url"), str) and isinstance(e.get("new_hash"), str)
    }
    stamp = recorded_at or datetime.now(timezone.utc).isoformat()
    refreshed: List[str] = []
    out: List[Any] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("url") in new_hashes:
            entry = {**entry, "content_hash": new_hashes[entry["url"]], "recorded_at": stamp}
            refreshed.append(entry["url"])
        out.append(entry)
    not_found = sorted(url for url in new_hashes if url not in refreshed)
    return {**metadata, "doc_sources": out}, refreshed, not_found


def _cmd_refresh_hashes(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py refresh-hashes",
        description=(
            "Record in metadata.json's doc_sources the new content_hash of each "
            "document a compare-hashes run found changed."
        ),
    )
    parser.add_argument("metadata", help="the skill's metadata.json, rewritten in place")
    parser.add_argument("--compare", required=True, help="the compare-hashes output for that metadata.json")
    args = parser.parse_args(argv)

    path = Path(args.metadata)
    tmp = path.with_name(f".{path.name}.skf-{os.getpid()}-tmp")
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        comparison = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or not isinstance(comparison, dict):
            raise ValueError("metadata.json and the comparison must each hold a JSON object")
        updated, refreshed, not_found = refresh_doc_hashes(metadata, comparison)
        tmp.write_bytes((json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        os.replace(tmp, path)
    except (OSError, ValueError) as exc:
        if tmp.exists():
            tmp.unlink()
        json.dump({"error": str(exc), "code": "REFRESH_FAILED"}, sys.stderr)
        sys.stderr.write("\n")
        return 2
    json.dump({"metadata": path.as_posix(), "refreshed": refreshed, "not_found": not_found}, sys.stdout)
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
# Subcommand: readme-entry, the README entry create-skill step 5a adds
# ---------------------------------------------------------------------------

# `doc_sources[].detected_via` of that entry. Listed in
# skf-create-skill/assets/skill-sections.md.
README_ALWAYS_DETECTED_VIA = "readme_always"

# Serves a GitHub repository's files as they are, one path per ref.
RAW_GITHUB = "https://raw.githubusercontent.com"

# A GitHub repository as a brief's source_repo names it: an https, ssh or git
# URL, the scp-like `git@github.com:owner/repo`, `github.com/owner/repo`, or
# the `owner/repo` shorthand. A trailing `.git` or `/` is not part of the
# name, which may itself hold dots (`vercel/next.js`).
_GITHUB_REPO_RE = re.compile(
    r"^(?:(?:https?|ssh|git)://(?:[^@/\s]+@)?(?:www\.)?github\.com(?::\d+)?/"
    r"|[^@/\s:]+@github\.com:"
    r"|(?:www\.)?github\.com/)?"
    r"([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

# The README a folder shows, in the order it is picked: README.md in any
# letter case, then a README with no language suffix (README.rst,
# README.markdown, README), then any other README, such as a translation
# (README-ja.md), which sorts before README.md by name.
_README_PREFERENCE = (
    re.compile(r"^readme\.md$", re.IGNORECASE),
    re.compile(r"^readme(?:\.[A-Za-z0-9]+)?$", re.IGNORECASE),
    re.compile(r"^readme", re.IGNORECASE),
)


def parse_github_repo(source_repo: str) -> Optional[Tuple[str, str]]:
    """(owner, repo) of the GitHub repository `source_repo` names, else None."""
    m = _GITHUB_REPO_RE.match((source_repo or "").strip())
    if not m or m.group(2) in (".", ".."):
        return None
    return m.group(1), m.group(2)


def pick_readme(names: List[str]) -> Optional[str]:
    """The README among a folder's top-level file names, by _README_PREFERENCE."""
    ordered = sorted(names)
    for pattern in _README_PREFERENCE:
        for name in ordered:
            if pattern.match(name):
                return name
    return None


def _local_files(folder: Path) -> List[str]:
    try:
        return [p.name for p in folder.iterdir() if p.is_file()]
    except OSError:
        return []


def _github_files(owner: str, repo: str, ref: str) -> List[str]:
    """Names of the files at the top of the repository at `ref`; [] when gh cannot list them."""
    query = "" if ref == "HEAD" else "?ref=" + urllib.parse.quote(ref, safe="")
    raw = _run_gh(["api", f"repos/{owner}/{repo}/contents{query}",
                   "--jq", '.[] | select(.type == "file") | .name'])
    return raw.splitlines() if raw else []


def readme_url(source_repo: str, ref: str, local_root: Optional[str] = None) -> Optional[str]:
    """The URL of the README entry, or None for a source that is neither local nor on GitHub.

    See the readme-entry section of the module docstring.
    """
    ref = (ref or "").strip()
    if ref.lower() in ("", "null", "none", "head"):
        ref = "HEAD"
    root = Path(local_root.strip()) if local_root and local_root.strip() else None
    if ref.lower() == "local":
        # Written as _fetch_and_hash reads it back: `file://` and the path, never percent-encoded.
        folder = Path(os.path.abspath(root if root is not None else (source_repo or "").strip()))
        return "file://" + (folder / (pick_readme(_local_files(folder)) or "README.md")).as_posix()
    parsed = parse_github_repo(source_repo)
    if parsed is None:
        return None
    owner, repo = parsed
    names = _local_files(root) if root is not None and root.is_dir() else _github_files(owner, repo, ref)
    name = pick_readme(names) or "README.md"
    return (f"{RAW_GITHUB}/{owner}/{repo}/{urllib.parse.quote(ref, safe='/@+')}/"
            f"{urllib.parse.quote(name, safe='')}")


def readme_entry(source_repo: str, ref: str, local_root: Optional[str] = None,
                 recorded_at: Optional[str] = None) -> Dict[str, Any]:
    """The readme-entry output: hash_urls for the README URL, its entry marked readme_always."""
    url = readme_url(source_repo, ref, local_root)
    if url is None:
        result = hash_urls([], recorded_at)
        result["skip_reason"] = "not-github"
        return result
    result = hash_urls([url], recorded_at)
    for entry in result["doc_sources"]:
        entry["detected_via"] = README_ALWAYS_DETECTED_VIA
    result["skip_reason"] = None
    return result


def _cmd_readme_entry(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py readme-entry",
        description=(
            "Pick a skill source's README and emit its doc_sources entry "
            "(detected_via: readme_always): the raw GitHub file at --ref, or a "
            "file:// URL for a local source, hashed as compare-hashes hashes it."
        ),
    )
    parser.add_argument("--source-repo", required=True, help="the brief's source_repo")
    parser.add_argument(
        "--ref", required=True,
        help="the ref the skill was built from: a tag, branch or commit, HEAD "
             "for the default branch, local for a local source",
    )
    parser.add_argument(
        "--local-root", default=None,
        help="the folder the source was read from, when it is a local folder; "
             "the README is picked from its files",
    )
    args = parser.parse_args(argv)

    result = readme_entry(args.source_repo, args.ref, args.local_root)
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: page-metrics, the root-page test create-skill step 3c runs
# ---------------------------------------------------------------------------

# A page is a navigation hub when more than this share of its non-empty
# lines are links (trigger 1), or a landing page when it has fewer words
# than ROOT_WORD_LIMIT (trigger 2).
LINK_RATIO_THRESHOLD = 0.7
ROOT_WORD_LIMIT = 2000

_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_SIGNATURE_RE = re.compile(r"(?<![A-Za-z0-9_])(?:def|function|fn|func|export) ")
# A markdown link that is not an image: `[text](target)`, the target
# optionally followed by a quoted title.
_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*[^)\s]*(?:\s+\"[^\"]*\")?\s*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINE_MARKER_RE = re.compile(r"^(?:>\s*)*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)?")
_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def _table_separator(line: str) -> bool:
    """A markdown table's separator row: pipes, dashes, colons and spaces
    only, with at least one pipe and three dashes in a row."""
    text = line.strip()
    return "|" in text and "---" in text and set(text) <= set("|-: \t")


def _link_line(line: str) -> bool:
    """True for a line that holds markdown links and no other text."""
    text = _LINE_MARKER_RE.sub("", line.strip(), count=1)
    if not _LINK_RE.search(text):
        return False
    return not re.search(r"[^\W_]", _LINK_RE.sub("", text))


def _root_like(path: str) -> Tuple[int, bool]:
    """(path segments, root-like) for a URL path."""
    segments = [s for s in path.split("/") if s]
    return len(segments), len(segments) <= 1 or path.endswith(("/", "/index", "/index.html"))


def page_metrics(url: str, markdown: str) -> Dict[str, Any]:
    """Measure a fetched page for the step 3c subpage decision."""
    segments, root_like = _root_like(urllib.parse.urlsplit(url.strip()).path)
    lines = markdown.splitlines()
    fences = 0
    open_fence: Optional[str] = None
    for line in lines:
        m = _FENCE_OPEN_RE.match(line)
        if not m:
            continue
        mark = m.group(1)
        if open_fence is None:
            open_fence = mark
            fences += 1
        elif mark[0] == open_fence[0] and len(mark) >= len(open_fence):
            open_fence = None
    table_rows = sum(1 for line in lines if _table_separator(line))
    signature_hits = len(_SIGNATURE_RE.findall(markdown))
    non_empty = [line for line in lines if line.strip()]
    link_lines = sum(1 for line in non_empty if _link_line(line))
    ratio = link_lines / len(non_empty) if non_empty else 0.0
    visible = _LINK_RE.sub(lambda m: " " + m.group(1) + " ", _IMAGE_RE.sub(lambda m: " " + m.group(1) + " ", markdown))
    words = len(_WORD_RE.findall(visible))
    trigger1 = (root_like and fences == 0 and table_rows == 0 and signature_hits == 0
                and ratio > LINK_RATIO_THRESHOLD)
    trigger2 = root_like and words < ROOT_WORD_LIMIT
    return {
        "url": url,
        "path_segments": segments,
        "root_like": root_like,
        "code_fences": fences,
        "table_rows": table_rows,
        "signature_hits": signature_hits,
        "link_lines": link_lines,
        "non_empty_lines": len(non_empty),
        "link_line_ratio": round(ratio, 4),
        "word_count": words,
        "trigger1": trigger1,
        "trigger2": trigger2,
        "discover_subpages": trigger1 or trigger2,
    }


def _read_source(source: str) -> Tuple[Optional[str], Optional[str]]:
    """(text, None) of a file or of stdin for `-`, gunzipped first when it is
    gzip compressed (a `.xml.gz` sitemap); (None, error) when it cannot be
    read or decoded as UTF-8."""
    label = "<stdin>" if source == "-" else source
    try:
        if source == "-":
            stream = getattr(sys.stdin, "buffer", None)  # an in-process test double has none
            data = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
        else:
            data = Path(source).read_bytes()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data.decode("utf-8-sig"), None
    except (OSError, EOFError, zlib.error, UnicodeDecodeError) as exc:
        return None, f"cannot read {label}: {exc}"


def _doc_section(name: str) -> str:
    """The module docstring's section on one subcommand, shown by its --help."""
    m = re.search(rf"^Subcommand: {re.escape(name)}\n-+\n(.*?)(?=^-{{10,}}\n|\Z)", __doc__ or "", re.S | re.M)
    return m.group(1).strip() if m else ""


def _cmd_page_metrics(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py page-metrics",
        description=(
            "Measure a fetched documentation page (saved as markdown) and say "
            "whether create-skill step 3c should look for its subpages."
        ),
        epilog=_doc_section("page-metrics"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="the URL the page was fetched from")
    parser.add_argument("source", help="the page's markdown file, or - to read it from stdin")
    args = parser.parse_args(argv)

    text, error = _read_source(args.source)
    if text is None:
        json.dump({"error": error, "code": "READ_ERROR"}, sys.stderr)
        sys.stderr.write("\n")
        return 2
    json.dump(page_metrics(args.url, text), sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: filter-urls, the subpages step 3c may fetch for a root page
# ---------------------------------------------------------------------------

# Multi-label suffixes a documentation site is often hosted under: each name
# directly below one of them is another owner's site
# (`project.readthedocs.io` and `other.readthedocs.io` are two sites). A
# small stand-in for the public suffix list, which the script does not ship.
HOSTED_SUFFIXES = frozenset({
    "github.io", "gitlab.io", "codeberg.page", "readthedocs.io", "readthedocs-hosted.com",
    "netlify.app", "vercel.app", "pages.dev", "workers.dev", "web.app", "firebaseapp.com",
    "herokuapp.com", "gitbook.io", "mintlify.app", "azurewebsites.net", "cloudfront.net",
    "surge.sh", "fly.dev", "onrender.com", "blogspot.com", "appspot.com", "hf.space",
    "streamlit.app", "glitch.me", "sourceforge.io",
})
# Second-level labels country-code domains register names under (`co.uk`,
# `com.au`): the registrable name is one label further left.
_CCTLD_SECOND_LEVELS = frozenset({
    "ac", "co", "com", "edu", "go", "gob", "gov", "ltd", "mil", "ne", "net", "nom", "or", "org", "plc",
})
# Path segments that name a page with no API content.
SUBPAGE_EXCLUDED_WORDS = ("blog", "changelog", "pricing", "about", "careers")
# Words in a URL path or title that point at API documentation. A word
# matches when it starts with one (`configuration`, `methods`).
API_TERMS = ("api", "reference", "quickstart", "setup", "config", "getting-started", "guide", "sdk",
             "method", "function")

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def registrable_domain(host: str) -> str:
    """The registrable domain of a host name, by the heuristic in the
    filter-urls section of the module docstring."""
    host = (host or "").strip().lower().rstrip(".")
    labels = host.split(".")
    if ":" in host or _IPV4_RE.match(host) or len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in HOSTED_SUFFIXES or (len(labels[-1]) == 2 and labels[-2] in _CCTLD_SECOND_LEVELS):
        return ".".join(labels[-3:])
    return last_two


def _excluded_path(path: str) -> bool:
    """True when a path segment, less its file extension, is one of SUBPAGE_EXCLUDED_WORDS."""
    for segment in path.lower().split("/"):
        stem = segment.rsplit(".", 1)[0] if "." in segment else segment
        if stem in SUBPAGE_EXCLUDED_WORDS:
            return True
    return False


def _api_terms(path: str, title: str) -> List[str]:
    """The API_TERMS a URL path or title holds, as whole words (a word may go on: `configuration`)."""
    words = re.findall(r"[a-z0-9]+", (path + " " + title).lower())
    found = []
    for term in API_TERMS:
        parts = term.split("-")
        for i in range(len(words) - len(parts) + 1):
            head = words[i:i + len(parts)]
            if head[:-1] == parts[:-1] and head[-1].startswith(parts[-1]):
                found.append(term)
                break
    return found


def _candidate_urls(text: str, source_label: str) -> List[Tuple[str, Optional[str]]]:
    """(url, title) pairs from a sitemap, a JSON list or map result, or one URL per line.

    Raises ValueError on malformed JSON or a JSON shape with no URL list.
    """
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return [(m.group(1).replace("&amp;", "&"), None) for m in _LOC_RE.finditer(text)]
    if stripped.startswith(("[", "{")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON in {source_label}: {exc}") from exc
        if isinstance(data, dict):
            items = next((data[k] for k in ("links", "urls") if isinstance(data.get(k), list)), None)
            if items is None:
                raise ValueError(f"{source_label} holds no `links` or `urls` array")
            data = items
        if not isinstance(data, list):
            raise ValueError(f"{source_label} must be a JSON array of URLs")
        out: List[Tuple[str, Optional[str]]] = []
        for item in data:
            if isinstance(item, str):
                out.append((item, None))
            elif isinstance(item, dict) and isinstance(item.get("url"), str):
                title = item.get("title")
                out.append((item["url"], title if isinstance(title, str) else None))
        return out
    return [(line.strip(), None) for line in text.splitlines() if line.strip()]


def _url_key(parts: urllib.parse.SplitResult) -> str:
    """A URL as filter-urls compares it: scheme and host in lower case, no `#fragment`."""
    return parts._replace(scheme=parts.scheme.lower(), netloc=parts.netloc.lower(), fragment="").geturl()


def filter_urls(root: str, candidates: List[Tuple[str, Optional[str]]]) -> Dict[str, Any]:
    """Cut subpage candidates to the root page's site and drop non-API pages."""
    root_parts = urllib.parse.urlsplit(root.strip())
    if root_parts.scheme.lower() not in ("http", "https") or not root_parts.hostname:
        raise ValueError(f"root is not an http or https URL: {root!r}")
    domain = registrable_domain(root_parts.hostname)
    root_key = _url_key(root_parts).rstrip("/")
    stats = {"input": len(candidates), "kept": 0, "other_domain": 0, "excluded_path": 0,
             "not_http": 0, "duplicate": 0, "root": 0, "sitemap": 0}
    kept: List[Dict[str, Any]] = []
    sitemaps: List[str] = []
    seen: set = set()
    for url, title in candidates:
        url = url.strip()
        if url.startswith("/"):
            # A crawl may list a page by its path: read it against the root.
            url = urllib.parse.urljoin(root.strip(), url)
        try:
            parts = urllib.parse.urlsplit(url)
            host = parts.hostname
        except ValueError:
            parts, host = None, None
        if parts is None or parts.scheme.lower() not in ("http", "https") or not host:
            stats["not_http"] += 1
            continue
        key = _url_key(parts)
        if key.rstrip("/") == root_key:
            stats["root"] += 1
            continue
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        if registrable_domain(host) != domain:
            stats["other_domain"] += 1
            continue
        if parts.path.lower().endswith((".xml", ".xml.gz")):
            # A sitemap index lists sitemaps, not pages.
            sitemaps.append(key)
            stats["sitemap"] += 1
            continue
        if _excluded_path(parts.path):
            stats["excluded_path"] += 1
            continue
        kept.append({"url": key, "title": title, "terms": _api_terms(parts.path, title or "")})
    stats["kept"] = len(kept)
    return {"root": root, "registrable_domain": domain, "kept": kept, "sitemaps": sitemaps, "stats": stats}


def _cmd_filter_urls(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-docs.py filter-urls",
        description=(
            "Keep the subpage URLs on a documentation root page's own site "
            "(its registrable domain) and drop pages with no API content."
        ),
        epilog=_doc_section("filter-urls"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", required=True, help="the root page's URL")
    parser.add_argument(
        "source",
        help=(
            "a sitemap.xml, a JSON array of URLs or {url, title} objects (or an "
            "object with a links or urls array), or one URL per line; - for stdin"
        ),
    )
    args = parser.parse_args(argv)

    text, error = _read_source(args.source)
    if text is None:
        json.dump({"error": error, "code": "READ_ERROR"}, sys.stderr)
        sys.stderr.write("\n")
        return 2
    label = "<stdin>" if args.source == "-" else args.source
    try:
        result = filter_urls(args.root, _candidate_urls(text, label))
    except ValueError as exc:
        json.dump({"error": str(exc), "code": "INVALID_INPUT"}, sys.stderr)
        sys.stderr.write("\n")
        return 2
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
    if len(sys.argv) > 1 and sys.argv[1] == "refresh-hashes":
        return _cmd_refresh_hashes(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "hash-urls":
        return _cmd_hash_urls(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "readme-entry":
        return _cmd_readme_entry(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "page-metrics":
        return _cmd_page_metrics(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "filter-urls":
        return _cmd_filter_urls(sys.argv[2:])

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
