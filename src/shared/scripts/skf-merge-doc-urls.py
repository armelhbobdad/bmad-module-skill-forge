# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Merge Doc URLs — merge corpora-seeded + detected docs for a skill brief.

Deterministic merge of an upstream brief's `doc_urls` (registry-seeded
companion corpora, source: language-registry) with the docs freshly
discovered by `skf-detect-docs.py` (mapped to the brief `{url, label, source}`
contract). Replaces the prose dedup/suppression that lived inline in
`skf-brief-skill/references/step-auto-brief.md` §3 — that logic is fiddly
(normalized-URL collisions, non-corpus path segments, locale duplicates) and
must behave identically on every run, so it belongs in a tested script.

Three operations, in order:

  1. Normalized-URL dedup — lowercase host, strip a trailing `/index.html`
     and any trailing `/` before comparing, so a seeded `…/book/` and a
     README's `…/book/index.html` collapse to one entry. Existing
     (corpora-seeded) entries always win and are NEVER dropped.

  2. Non-corpus segment suppression (whole-language references only) — when
     the brief is a whole-language reference (scope_type == "full-library"
     AND ≥1 existing entry carries source == "language-registry"), drop a
     README-detected entry whose host matches a registry corpus host and
     whose path contains a known non-corpus segment (whatsnew / contribute /
     wiki). Path-component-anchored, never a bare substring — `/whatsnew/`
     and `/whatsnew-2024/` drop, `/docs/whatsnewfeatures/` does not.

  3. Non-primary-locale collapse (whole-language references only) — drop a
     README-detected entry on a registry host whose leading path segment is a
     non-primary locale (e.g. `/ja/master/`) when a locale-stripped twin is
     already kept (e.g. a seeded `/en/master/` or `/master/`). Twin-required:
     a `/ja/…` page with no `/en/…` counterpart is kept.

Suppression is GATED on the whole-language marker so ordinary skills pass
through with byte-identical merge behaviour (dedup only). N==0 whole-language
references (registry miss → no seeded corpora) carry no language-registry
entry, so the gate is inactive and their README docs are NOT suppressed — the
DEGRADED case is intentionally out of scope (there is no canonical corpus host
to anchor suppression against).

CLI:
  echo '{"scope_type": "...", "existing": [...], "detected": [...]}' \
    | uv run src/shared/scripts/skf-merge-doc-urls.py

Input (JSON object on stdin):
  {
    "scope_type": "full-library",
    "existing":   [{"url": "...", "label": "...", "source": "language-registry"}, ...],
    "detected":   [{"url": "...", "label": "...", "source": "readme-detection"}, ...]
  }

Output (JSON object on stdout):
  {
    "doc_urls":   [{"url": "...", "label": "...", "source": "..."}, ...],
    "suppressed": [{"url": "...", "reason": "non-corpus-segment|non-primary-locale-dup"}, ...]
  }

Exit codes:
  0  success (merged list emitted)
  2  error (bad JSON, wrong input shape)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any
from urllib.parse import urlsplit

# Path components (case-insensitive) that mark a non-corpus page on a doc host:
# changelogs/news, contribution guides, wikis. Matched as whole path components
# (or component + a separator), never as a bare substring.
_NON_CORPUS_SEGMENTS = ("whatsnew", "contribute", "wiki")

# Closed allowlist of plausible doc-site locale codes. A leading path segment is
# treated as a locale only when it is in this set (or a `ll-rr` form whose
# language part is). Keeps a genuine subsection like `/go/` or `/is/` from being
# misread as a locale.
_LOCALE_CODES = {
    "en", "ja", "zh", "ko", "fr", "de", "es", "pt", "ru", "it", "nl", "pl",
    "tr", "uk", "cs", "id", "vi", "fa", "ar", "hi", "th", "sv", "da", "fi",
    "nb", "no", "hu", "ro", "el", "he", "bg", "hr", "sk", "sl", "et", "lv",
    "lt", "sr", "ca",
}
_LOCALE_REGION_RE = re.compile(r"^([a-z]{2})-[a-z]{2}$")


def _norm_parts(url: str) -> tuple[str, str]:
    """Return (lowercased host, normalized path) for dedup / host matching.

    Path normalization strips a trailing `/index.html` and any trailing `/`.
    Scheme, query, and fragment are ignored — a doc page is identified by its
    host + path.
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path
    low = path.lower()
    if low.endswith("/index.html"):
        path = path[: -len("/index.html")]
    path = path.rstrip("/")
    return host, path


def _norm_key(url: str) -> tuple[str, str]:
    return _norm_parts(url)


def _is_locale(seg: str) -> bool:
    s = seg.lower()
    if s in _LOCALE_CODES:
        return True
    m = _LOCALE_REGION_RE.match(s)
    return bool(m) and m.group(1) in _LOCALE_CODES


def _is_primary_locale(seg: str) -> bool:
    s = seg.lower()
    return s == "en" or s.startswith("en-")


def _path_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _locale_stripped_key(url: str) -> tuple[str, str, bool, bool]:
    """Return (host, path-without-leading-locale, has_locale, is_primary).

    The third/fourth flags let the caller tell `/ja/master/` (non-primary
    locale) apart from `/master/` (no locale) and `/en/master/` (primary).
    """
    host, path = _norm_parts(url)
    segs = _path_segments(path)
    has_locale = bool(segs) and _is_locale(segs[0])
    is_primary = has_locale and _is_primary_locale(segs[0])
    if has_locale:
        segs = segs[1:]
    return host, "/".join(segs), has_locale, is_primary


def _matches_non_corpus_segment(path: str) -> bool:
    for seg in _path_segments(path):
        low = seg.lower()
        for token in _NON_CORPUS_SEGMENTS:
            if low == token:
                return True
            # component + separator (whatsnew-2024) — but NOT whatsnewfeatures
            if low.startswith(token) and len(low) > len(token) and not low[len(token)].isalnum():
                return True
    return False


def merge_doc_urls(
    scope_type: str,
    existing: list[dict[str, Any]],
    detected: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge existing (seeded) + detected doc_urls. Returns (doc_urls, suppressed)."""
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # 1. Existing (corpora-seeded) entries win and are never dropped.
    for e in existing:
        if not isinstance(e, dict) or not e.get("url"):
            continue
        key = _norm_key(e["url"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(e)

    # Whole-language gate: registry-seeded corpora present on a full-library brief.
    registry_hosts = {
        _norm_parts(e["url"])[0]
        for e in kept
        if isinstance(e, dict) and e.get("url") and e.get("source") == "language-registry"
    }
    suppression_active = scope_type == "full-library" and bool(registry_hosts)

    for d in detected:
        if not isinstance(d, dict) or not d.get("url"):
            continue
        url = d["url"]
        key = _norm_key(url)
        if key in seen:
            continue  # dedup — a seeded/earlier entry already covers this URL

        if suppression_active:
            host, path = _norm_parts(url)
            if host in registry_hosts:
                if _matches_non_corpus_segment(path):
                    suppressed.append({"url": url, "reason": "non-corpus-segment"})
                    continue
                dh, dpath, has_locale, is_primary = _locale_stripped_key(url)
                if has_locale and not is_primary:
                    twin = any(
                        _locale_stripped_key(k["url"])[0] == dh
                        and _locale_stripped_key(k["url"])[1] == dpath
                        for k in kept
                        if k.get("url")
                    )
                    if twin:
                        suppressed.append({"url": url, "reason": "non-primary-locale-dup"})
                        continue

        seen.add(key)
        kept.append(d)

    return kept, suppressed


def main() -> int:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        sys.stderr.write("skf-merge-doc-urls: empty stdin (expected JSON object)\n")
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"skf-merge-doc-urls: invalid JSON on stdin: {exc}\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("skf-merge-doc-urls: input must be a JSON object\n")
        return 2

    scope_type = payload.get("scope_type") or ""
    existing = payload.get("existing") or []
    detected = payload.get("detected") or []
    if not isinstance(existing, list) or not isinstance(detected, list):
        sys.stderr.write("skf-merge-doc-urls: 'existing' and 'detected' must be arrays\n")
        return 2

    doc_urls, suppressed = merge_doc_urls(scope_type, existing, detected)
    json.dump({"doc_urls": doc_urls, "suppressed": suppressed}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
