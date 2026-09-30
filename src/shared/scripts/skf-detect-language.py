# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Detect Language — deterministic primary-language detection from a flat file tree.

Single source of truth for the language-detection rule table that
skf-brief-skill step 2 §3 applies. The rule walk is purely deterministic:
manifest-file presence first (Cargo.toml → rust, package.json → js/ts,
etc.), then extension-frequency fallback. Moving it into a shared script
saves ~150-250 tokens per workflow invocation and removes a quiet drift
seam — the JS-vs-TS disambiguation in particular benefits from being
co-located with a deterministic rule rather than restated in prose.

Detection rules (apply in order, first match wins):

  0. workspace_signal (optional, from skf-detect-workspaces.manifest_kind):
       "cargo-workspace"       → rust (high)
       "python-multi-package"  → python (high)
       A non-JS workspace root's language wins over a nested package.json +
       tsconfig.json (e.g. a docs/ or website/ site that is not a workspace
       member). JS-family workspaces (npm/pnpm/lerna/rush/nx) carry no entry
       here and fall through to rule 1, whose package.json files correctly
       resolve js/ts.
  1. package.json (with optional tsconfig.json companion):
       tsconfig.json present → typescript (high)
       tsconfig.json absent  → javascript (high)
  2. Cargo.toml          → rust (high)
  3. pyproject.toml | setup.py | setup.cfg → python (high)
  4. go.mod              → go (high)
  5. pom.xml             → java (high)
  6. build.gradle.kts    → kotlin (high)
  7. build.gradle (Groovy) — check tree:
       src/main/kotlin/  → kotlin (medium)
       else              → java (medium)
  8. Package.swift       → swift (high)
  9. *.csproj | *.sln    → csharp (high)
 10. Gemfile             → ruby (high)
 11. Extension-frequency fallback over the full tree.
       dominant extension >= 50% of code files → that language (medium)
       no clear winner                        → unknown (low)

CLI:
  echo '{"tree": ["path1", "path2", ...]}' | uv run skf-detect-language.py
  uv run skf-detect-language.py --json '{"tree": [...]}'
  uv run skf-detect-language.py --tree-file <file> [--workspace-signal <manifest_kind>]
  <listing> | uv run skf-detect-language.py --tree-file - [--workspace-signal <manifest_kind>]

--tree-file reads the repository's file list from a file (`-` reads it from
stdin), so a tree of any size reaches the script whole and never passes
through a shell string or the model:
  - JSON: an object whose `tree` lists the paths, such as the output of
    skf-github-probe.py tree (a listing whose `status` is not "ok" is
    refused, with its `message`) or a GitHub git/trees response (only its
    `blob` entries count); or a JSON list of paths.
  - Anything else: one path per line, as `git -c core.quotePath=false
    ls-files` prints them (a leading `./`, as `find .` prints it, is
    dropped).
A byte order mark before the listing is dropped, and a listing that holds
no path is refused. These are the listings skf-recommend-scope-type.py's
--tree-file reads, which takes `[]` as its deliberate fallback.
read_tree_file() is the reader skf-detect-workspaces.py and
skf-shape-detect.py load for their own --tree-file. With --tree-file, stdin
is never read for the payload, so a payload piped in beside a --tree-file
<file> is not seen: pass workspace_signal with --workspace-signal (or the
payload with --json, which may not carry `tree` as well).
--workspace-signal sets the payload's workspace_signal in any form; passing
it in the payload as well is an error.

Input (JSON object on stdin or via --json):
  tree              list of repo-relative file paths (required, non-empty;
                    or --tree-file)
  workspace_signal  optional manifest_kind from skf-detect-workspaces (or
                    --workspace-signal). When it names a non-JS workspace
                    ("cargo-workspace", "python-multi-package"), rule 0
                    returns the root language and ignores nested
                    package.json/tsconfig matches.

Output (JSON on stdout):
  language          — javascript | typescript | rust | python | go
                       | java | kotlin | csharp | ruby | swift | php
                       | unknown
  confidence        — "high" | "medium" | "low"
  detection_source  — human-readable string naming what fired (manifest
                       basename, extension share, etc.)
  fallback_to_extension_frequency — bool (true when rule 10 fired)
  detected_languages — ordered, deduplicated list of EVERY manifest-level
                       match in the same priority order the winner walk uses.
                       language == detected_languages[0] whenever the manifest
                       table fired, so a caller can auto-pick detected_languages[0]
                       and gate multi-language disambiguation on
                       len(detected_languages) > 1. Special cases: a
                       workspace_signal override (rule 0) is decisive and returns
                       a single-element [language]; the extension-frequency
                       fallback (rule 10) contributes [language] for a best guess
                       or [] when language is "unknown".

Exit codes:
  0  recommendation produced (even when language is "unknown")
  2  bad input: invalid JSON, a missing or empty tree, the tree or the
     workspace_signal passed twice, or a tree listing that cannot be read,
     holds no path or reports a failure
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

# A --tree-file listing is JSON when it opens like a JSON object or list of
# paths. A bare leading bracket is not enough: a line listing can start with
# a path such as `[slug]/page.tsx`.
JSON_LISTING_RE = re.compile(r'\{\s*["}]|\[\s*["{\]]')

# Workspace manifest_kind → root language (rule 0). Only non-JS workspace kinds
# appear here: a Cargo/Python workspace root is unambiguously rust/python, and a
# nested package.json+tsconfig (a docs or website subproject) must not win. JS
# workspace kinds (npm-workspaces/pnpm-workspaces/lerna/rush/nx) are
# intentionally absent: their repositories hold package.json files, so rule 1
# resolves js/ts correctly. generic-folders / null carry no language signal.
_WORKSPACE_SIGNAL_LANGUAGE: dict[str, str] = {
    "cargo-workspace": "rust",
    "python-multi-package": "python",
}

# Manifest basenames the rule table checks. Kept tight — tree-wide pattern
# matches (e.g. *.csproj) are handled separately to avoid false positives
# from generated artifacts under build/ or dist/.
_MANIFEST_RULES: list[tuple[str, str, str]] = [
    # (basename, language, detection_source)
    ("Cargo.toml", "rust", "Cargo.toml present"),
    ("pyproject.toml", "python", "pyproject.toml present"),
    ("setup.py", "python", "setup.py present"),
    ("setup.cfg", "python", "setup.cfg present"),
    ("go.mod", "go", "go.mod present"),
    ("pom.xml", "java", "pom.xml present"),
    ("build.gradle.kts", "kotlin", "build.gradle.kts present"),
    ("Package.swift", "swift", "Package.swift present"),
    ("Gemfile", "ruby", "Gemfile present"),
]

# Glob-style suffix rules — matches anywhere in the tree. csproj/sln are
# C#-specific. Ordered so the first hit wins.
_SUFFIX_RULES: list[tuple[str, str, str]] = [
    (".csproj", "csharp", ".csproj project file present"),
    (".sln", "csharp", ".sln solution file present"),
]

# Extension → language for the frequency fallback. Tightly limited to source
# extensions; keeping this small avoids the fallback being skewed by
# auto-generated assets (.json, .md, .yaml, etc.).
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
}

_DOMINANCE_THRESHOLD = 0.50


def _die(message: str, code: int = 2) -> None:
    sys.stderr.write(f"skf-detect-language: {message}\n")
    sys.exit(code)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _has_basename(tree: list[str], basename: str) -> bool:
    return any(_basename(p) == basename for p in tree)


def _has_suffix(tree: list[str], suffix: str) -> bool:
    return any(p.endswith(suffix) for p in tree)


def _has_path_segment(tree: list[str], segment: str) -> bool:
    """True when any path contains the given segment (e.g. 'src/main/kotlin/')."""
    return any(segment in p for p in tree)


def _extension(path: str) -> str:
    """Return the lowercased file extension including the leading dot, or empty string."""
    base = _basename(path)
    if "." not in base or base.startswith("."):
        return ""
    return "." + base.rsplit(".", 1)[-1].lower()


def is_source_file(path: str) -> bool:
    """Whether a path is a source file the extension-frequency fallback
    counts (skf-detect-workspaces.py's tree snapshot counts the same)."""
    return _extension(path) in _EXTENSION_TO_LANGUAGE


def _frequency_fallback(tree: list[str]) -> dict[str, Any]:
    """Score the tree by source-extension frequency. Returns the result envelope."""
    counter: Counter[str] = Counter()
    for path in tree:
        ext = _extension(path)
        if ext in _EXTENSION_TO_LANGUAGE:
            counter[ext] += 1

    total = sum(counter.values())
    if total == 0:
        return {
            "language": "unknown",
            "confidence": "low",
            "detection_source": "no recognized source extensions in tree",
            "fallback_to_extension_frequency": True,
        }

    # Largest-share extension wins. Ties (e.g. equal counts) broken by
    # the natural order of _EXTENSION_TO_LANGUAGE — Counter.most_common
    # is stable for equal counts and we don't rely on which loses.
    top_ext, top_count = counter.most_common(1)[0]
    share = top_count / total
    language = _EXTENSION_TO_LANGUAGE[top_ext]

    if share >= _DOMINANCE_THRESHOLD:
        confidence = "medium"
        source = f"extension frequency: {top_ext} is {top_count}/{total} of source files ({share:.0%})"
    else:
        confidence = "low"
        source = f"no dominant extension: top is {top_ext} at {top_count}/{total} ({share:.0%}, threshold {int(_DOMINANCE_THRESHOLD * 100)}%)"
        # Still surface the best-guess language; caller / step 3 §4 lets
        # the user override on low confidence.
    return {
        "language": language,
        "confidence": confidence,
        "detection_source": source,
        "fallback_to_extension_frequency": True,
    }


def _detected_languages(payload: dict[str, Any], winner: dict[str, Any]) -> list[str]:
    """Accumulate every manifest-level match into an ordered, deduplicated list.

    The walk mirrors the winner-selection priority order exactly, so
    winner["language"] == detected_languages[0] whenever the manifest table
    fired. Two decisive short-circuits diverge from a full walk on purpose:

      * A workspace_signal override (rule 0) is authoritative — the workspace
        root language wins over any nested package.json, so this returns a
        single-element [winner_language] and never surfaces a spurious
        multi-language gate for what workspace detection already resolved.
      * When no manifest matched (rule 10 fired), the list carries the
        extension-frequency best guess as a single element, or [] when the
        guess was "unknown".
    """
    tree: list[str] = payload["tree"]  # validated non-empty by _winner()

    workspace_signal = payload.get("workspace_signal")
    if isinstance(workspace_signal, str) and workspace_signal in _WORKSPACE_SIGNAL_LANGUAGE:
        return [winner["language"]]

    langs: list[str] = []

    def add(lang: str) -> None:
        if lang not in langs:
            langs.append(lang)

    # Rule 1 — package.json (tsconfig.json disambiguation)
    if _has_basename(tree, "package.json"):
        add("typescript" if _has_basename(tree, "tsconfig.json") else "javascript")

    # Rules 2-6 / 8 / 10 — single-basename manifests (same order as _MANIFEST_RULES)
    for basename, language, _source in _MANIFEST_RULES:
        if _has_basename(tree, basename):
            add(language)

    # Rule 7b — build.gradle (Groovy) Java/Kotlin disambiguation
    if _has_basename(tree, "build.gradle"):
        add("kotlin" if _has_path_segment(tree, "src/main/kotlin/") else "java")

    # Rules 8-9 — suffix-based (csproj, sln)
    for suffix, language, _source in _SUFFIX_RULES:
        if _has_suffix(tree, suffix):
            add(language)

    if langs:
        return langs

    # No manifest matched — the winner came from the extension-frequency
    # fallback (rule 10). Carry its best guess, or [] when it was "unknown".
    fallback_language = winner["language"]
    return [] if fallback_language == "unknown" else [fallback_language]


def detect(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the documented rule walk and annotate the full manifest match set.

    Returns the single-winner envelope (language/confidence/detection_source/
    fallback_to_extension_frequency) unchanged, plus detected_languages[] — the
    ordered, deduplicated set of every manifest-level match — so a caller can
    both auto-pick and gate multi-language disambiguation off one JSON shape.
    """
    winner = _winner(payload)
    winner["detected_languages"] = _detected_languages(payload, winner)
    return winner


def _winner(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the documented rule walk. Always returns a recommendation."""
    tree = payload.get("tree")
    if not isinstance(tree, list):
        _die("payload.tree must be an array of repo-relative file paths")
    if len(tree) == 0:
        _die("payload.tree must be non-empty")

    # Rule 0 — workspace precedence. A non-JS workspace root (from
    # skf-detect-workspaces.manifest_kind) wins over any nested package.json +
    # tsconfig.json, which would otherwise be misread as a typescript root.
    workspace_signal = payload.get("workspace_signal")
    if isinstance(workspace_signal, str) and workspace_signal in _WORKSPACE_SIGNAL_LANGUAGE:
        return {
            "language": _WORKSPACE_SIGNAL_LANGUAGE[workspace_signal],
            "confidence": "high",
            "detection_source": f"workspace manifest_kind={workspace_signal} (root manifest wins over nested package.json)",
            "fallback_to_extension_frequency": False,
        }

    # Rule 1 — package.json (with tsconfig.json disambiguation)
    if _has_basename(tree, "package.json"):
        if _has_basename(tree, "tsconfig.json"):
            return {
                "language": "typescript",
                "confidence": "high",
                "detection_source": "package.json + tsconfig.json present",
                "fallback_to_extension_frequency": False,
            }
        return {
            "language": "javascript",
            "confidence": "high",
            "detection_source": "package.json present (no tsconfig.json)",
            "fallback_to_extension_frequency": False,
        }

    # Rules 2-6 — single-basename manifests walked in priority order. Note
    # that build.gradle (Groovy DSL) is NOT in this table; it requires
    # tree-aware Java/Kotlin disambiguation handled in Rule 7b below.
    # build.gradle.kts IS in the table (returns kotlin high) and fires
    # here before the Groovy variant is considered.
    for basename, language, source in _MANIFEST_RULES:
        if _has_basename(tree, basename):
            return {
                "language": language,
                "confidence": "high",
                "detection_source": source,
                "fallback_to_extension_frequency": False,
            }

    # Rule 7b — build.gradle (Groovy DSL): check src/main/kotlin/ to disambiguate.
    # This rule sits *after* the basename loop because build.gradle.kts is
    # already covered by the loop and we don't want it to pre-empt that match.
    if _has_basename(tree, "build.gradle"):
        if _has_path_segment(tree, "src/main/kotlin/"):
            return {
                "language": "kotlin",
                "confidence": "medium",
                "detection_source": "build.gradle (Groovy) + src/main/kotlin/ present",
                "fallback_to_extension_frequency": False,
            }
        return {
            "language": "java",
            "confidence": "medium",
            "detection_source": "build.gradle (Groovy) present without src/main/kotlin/ — defaulting to java",
            "fallback_to_extension_frequency": False,
        }

    # Rules 8-9 — suffix-based (csproj, sln)
    for suffix, language, source in _SUFFIX_RULES:
        if _has_suffix(tree, suffix):
            return {
                "language": language,
                "confidence": "high",
                "detection_source": source,
                "fallback_to_extension_frequency": False,
            }

    # Rule 10 — extension-frequency fallback
    return _frequency_fallback(tree)


# --------------------------------------------------------------------------
# --tree-file listings
# --------------------------------------------------------------------------


class TreeListingError(ValueError):
    """A --tree-file listing that cannot be read, holds no path or reports a failure."""


def parse_tree_listing(text: str, source: str) -> tuple[list[str], bool]:
    """(the file paths, whether the listing was cut short) of a --tree-file
    listing: JSON, or one path per line, after a byte order mark (Windows
    PowerShell writes one into a pipe). Only a JSON listing can say it was
    cut short (a GitHub tree's `truncated`). `source` says where the
    listing came from in an error. Raises TreeListingError, also for a
    listing that holds no path (`[]`, or a tree with no file)."""
    stripped = text.lstrip("﻿").strip()
    if not stripped:
        raise TreeListingError(f"the tree listing {source} is empty; the command that wrote it may have failed")
    truncated = False
    if not JSON_LISTING_RE.match(stripped):
        paths = []
        for line in stripped.splitlines():
            path = line.strip().removeprefix("./")
            if path:
                paths.append(path)
    else:
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise TreeListingError(f"the tree listing {source} is not valid JSON: {e}") from e
        entries = data
        if isinstance(data, dict):
            status = data.get("status")
            if status is not None and status != "ok":
                raise TreeListingError(
                    f"the tree listing {source} reports a failure ({status}): {data.get('message') or 'no message'}")
            entries, truncated = data.get("tree"), data.get("truncated") is True
        if not isinstance(entries, list):
            raise TreeListingError(f"the tree listing {source} holds no list of paths (a `tree` list, or a JSON list)")
        paths = []
        for entry in entries:
            if isinstance(entry, str):
                paths.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry.get("type", "blob") == "blob":
                paths.append(entry["path"])
    if not paths:
        raise TreeListingError(f"the tree listing {source} holds no file path; the command that wrote it may have failed")
    return paths, truncated


def read_tree_file(value: str) -> tuple[list[str], bool]:
    """parse_tree_listing() of the file `value` names, or of stdin for `-`
    (a caller reconfigures stdin to UTF-8 first). Raises TreeListingError."""
    if value == "-":
        return parse_tree_listing(sys.stdin.read(), "on stdin")
    try:
        with open(value, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        raise TreeListingError(f"cannot read --tree-file {value}: {getattr(e, 'strerror', None) or e}") from e
    return parse_tree_listing(text, f"in {value}")


def _parse_argv(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(
        description="Detect primary language from a flat repo file tree by walking the documented rule table.",
    )
    parser.add_argument("--json", help="JSON payload (alternative to stdin)")
    parser.add_argument(
        "--tree-file",
        help="the repository's file list: JSON (a `tree` list, or a list) or one path per line; - reads stdin. "
             "With --tree-file <file>, stdin is not read: pass the other keys with --workspace-signal or --json",
    )
    parser.add_argument(
        "--workspace-signal",
        help="the payload's workspace_signal: the manifest_kind skf-detect-workspaces.py returns",
    )
    args = parser.parse_args(argv)
    if args.tree_file is not None:
        # The listing is the tree; stdin is never read for the payload here.
        payload = _load_payload(args.json) if args.json is not None else {}
        if "tree" in payload:
            _die("pass the tree once: in the payload or with --tree-file, not both")
        try:
            payload["tree"] = read_tree_file(args.tree_file)[0]
        except TreeListingError as e:
            _die(str(e))
    else:
        payload = _load_payload(args.json if args.json is not None else sys.stdin.read())
    if args.workspace_signal is not None:
        if "workspace_signal" in payload:
            _die("pass workspace_signal once: in the payload or with --workspace-signal, not both")
        payload["workspace_signal"] = args.workspace_signal
    return payload


def _load_payload(raw: str) -> dict:
    if not raw or not raw.strip():
        _die("empty input (expected JSON payload on stdin or via --json)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON input: {e}")
    if not isinstance(payload, dict):
        _die("payload must be a JSON object")
    return payload


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


def main(argv: list[str]) -> int:
    _force_utf8(sys.stdin, sys.stdout)
    payload = _parse_argv(argv)
    result = detect(payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
