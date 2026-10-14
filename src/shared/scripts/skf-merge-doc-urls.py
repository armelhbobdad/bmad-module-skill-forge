# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Merge Doc URLs — merge corpora-seeded + detected docs for a skill brief.

Deterministic merge of an upstream brief's `doc_urls` (registry-seeded
companion corpora, source: language-registry) with the docs freshly
discovered by `skf-detect-docs.py` (mapped to the brief `{url, label, source}`
contract). Replaces the prose mapping, dedup and suppression that lived inline
in `skf-brief-skill/references/step-auto-brief.md` §3. That logic is fiddly
(normalized-URL collisions, non-corpus path segments, locale duplicates) and
must behave identically on every run, so it belongs in a tested script.

With --detected-file, each skf-detect-docs.py entry {url, detected_via,
content_type} is first mapped to {url, label, source}: `source` from
`detected_via` and `label` from `content_type`, by the two tables below (a
content_type they do not list gives the label ""). An entry whose
`detected_via` they do not list is never merged: `suppressed` lists it with
reason unknown-detected-via.

Three merge operations, in order:

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
  uv run src/shared/scripts/skf-merge-doc-urls.py --scope-type <type> \
      --detected-file <detect-docs.json> --existing-brief <skill-brief.yaml>
  echo '{"scope_type": "...", "existing": [...], "detected": [...]}' \
    | uv run src/shared/scripts/skf-merge-doc-urls.py

Files form (stdin is not read): --detected-file holds skf-detect-docs.py's
JSON array, mapped as above; --existing-brief is a skill-brief.yaml whose
`doc_urls` are the existing entries (none when it has no doc_urls), read as
skf-resolve-authoritative-files.py reads a brief; --scope-type is the scope
type. Each flag is optional: an absent one gives no entries (or "").

Input of the stdin form (a JSON object), whose entries are merged as given:
  {
    "scope_type": "full-library",
    "existing":   [{"url": "...", "label": "...", "source": "language-registry"}, ...],
    "detected":   [{"url": "...", "label": "...", "source": "readme-detection"}, ...]
  }

Output (JSON object on stdout):
  {
    "doc_urls":   [{"url": "...", "label": "...", "source": "..."}, ...],
    "suppressed": [{"url": "...", "reason":
                    "unknown-detected-via|non-corpus-segment|non-primary-locale-dup"}, ...]
  }

Exit codes:
  0  success (merged list emitted)
  2  error (bad JSON, wrong input shape, a file that cannot be read, a brief
     that is not a YAML mapping)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# skf-detect-docs.py's `detected_via` -> the brief's coarse provenance, the
# skill-brief.v1.json doc_urls[].source enum (a test pins it to the schema).
_SOURCE_BY_DETECTED_VIA = {
    "homepageUrl": "homepage",
    "readme_link": "readme-detection",
    "pages_api": "pages-api",
    "docs_folder": "docs-folder",
}
# skf-detect-docs.py's `content_type` -> the entry's display label.
_LABEL_BY_CONTENT_TYPE = {
    "api-docs": "API Documentation",
    "guide": "Guide",
    "reference": "Reference",
}

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


def map_detected(raw: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """skf-detect-docs.py entries as brief doc_urls entries {url, label, source}.

    Returns (mapped, suppressed): an entry whose detected_via maps to no
    source is suppressed with reason unknown-detected-via; one with no url is
    skipped, as the merge skips it.
    """
    mapped: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for d in raw:
        if not isinstance(d, dict) or not d.get("url"):
            continue
        via, content_type = d.get("detected_via"), d.get("content_type")
        source = _SOURCE_BY_DETECTED_VIA.get(via) if isinstance(via, str) else None
        if source is None:
            suppressed.append({"url": d["url"], "reason": "unknown-detected-via"})
            continue
        label = _LABEL_BY_CONTENT_TYPE.get(content_type, "") if isinstance(content_type, str) else ""
        mapped.append({"url": d["url"], "label": label, "source": source})
    return mapped, suppressed


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


def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8 (issue #465).

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (ensure_ascii=False output, raw UTF-8 input). Preserves
    each stream's existing error handler — reconfigure(encoding=...) alone
    would reset it to 'strict', downgrading e.g. an already-UTF-8 stderr on
    Linux. For stdin this must run before the first read. Skips in-process
    test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


class InputError(Exception):
    """An input the merge cannot read (exit 2)."""


def _read_detected(path: str) -> list[Any]:
    """The JSON array skf-detect-docs.py wrote to `path`."""
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except OSError as exc:
        raise InputError(f"cannot read --detected-file {path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"--detected-file {path} is not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise InputError(f"--detected-file {path} must hold a JSON array (skf-detect-docs.py output)")
    return data


def _brief_doc_urls(path: str) -> list[Any]:
    """The doc_urls of the skill brief at `path`, read by
    skf-resolve-authoritative-files.py's parse_brief_yaml (beside this file)."""
    resolver_path = Path(__file__).resolve().parent / "skf-resolve-authoritative-files.py"
    spec = importlib.util.spec_from_file_location("skf_resolve_authoritative_files", resolver_path)
    if spec is None or spec.loader is None:
        raise InputError(f"cannot load {resolver_path.name} beside {Path(__file__).name}")
    resolver = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(resolver)
    except (OSError, ImportError, SyntaxError) as exc:
        raise InputError(f"cannot load {resolver_path.name} beside {Path(__file__).name}: {exc}") from exc
    try:
        brief = resolver.parse_brief_yaml(Path(path).read_bytes().decode("utf-8-sig"))
    except OSError as exc:
        raise InputError(f"cannot read --existing-brief {path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, resolver.yaml.YAMLError) as exc:
        raise InputError(f"--existing-brief {path} is not YAML: {exc}") from exc
    if not isinstance(brief, dict):
        raise InputError(f"--existing-brief {path} holds no brief mapping")
    doc_urls = brief.get("doc_urls") or []
    if not isinstance(doc_urls, list):
        raise InputError(f"the doc_urls of --existing-brief {path} must be a list")
    return doc_urls


def _stdin_payload() -> tuple[str, list[Any], list[Any]]:
    """(scope_type, existing, detected) of the stdin form."""
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        raise InputError("empty stdin (expected JSON object)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON on stdin: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputError("input must be a JSON object")
    existing = payload.get("existing") or []
    detected = payload.get("detected") or []
    if not isinstance(existing, list) or not isinstance(detected, list):
        raise InputError("'existing' and 'detected' must be arrays")
    return payload.get("scope_type") or "", existing, detected


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdin, sys.stdout)
    parser = argparse.ArgumentParser(
        prog="skf-merge-doc-urls",
        description="Merge a brief's doc_urls with the docs skf-detect-docs.py found. With no flag, read the "
                    "{scope_type, existing, detected} JSON object on stdin.",
    )
    parser.add_argument("--detected-file", metavar="PATH",
                        help="skf-detect-docs.py's JSON array, mapped to {url, label, source}")
    parser.add_argument("--existing-brief", metavar="PATH",
                        help="the skill-brief.yaml whose doc_urls are the existing entries")
    parser.add_argument("--scope-type", metavar="TYPE", help="the brief's scope.type")
    args = parser.parse_args(argv)
    unknown: list[dict[str, Any]] = []
    try:
        if args.detected_file is None and args.existing_brief is None and args.scope_type is None:
            scope_type, existing, detected = _stdin_payload()
        else:
            scope_type = args.scope_type or ""
            existing = _brief_doc_urls(args.existing_brief) if args.existing_brief is not None else []
            detected = []
            if args.detected_file is not None:
                detected, unknown = map_detected(_read_detected(args.detected_file))
    except InputError as exc:
        sys.stderr.write(f"skf-merge-doc-urls: {exc}\n")
        return 2

    doc_urls, suppressed = merge_doc_urls(scope_type, existing, detected)
    json.dump({"doc_urls": doc_urls, "suppressed": unknown + suppressed}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
