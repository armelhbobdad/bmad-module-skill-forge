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
       member). JS-family workspaces (npm/pnpm/lerna) carry no entry here and
       fall through to rule 1, whose root package.json correctly resolves js/ts.
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
  8. *.csproj | *.sln    → csharp (high)
  9. Gemfile             → ruby (high)
 10. Extension-frequency fallback over the full tree.
       dominant extension >= 50% of code files → that language (medium)
       no clear winner                        → unknown (low)

CLI:
  echo '{"tree": ["path1", "path2", ...]}' | uv run skf-detect-language.py
  uv run skf-detect-language.py --json '{"tree": [...]}'

Input (JSON object on stdin or via --json):
  tree — list of repo-relative file paths (required, non-empty)
  workspace_signal — optional manifest_kind from skf-detect-workspaces. When it
                     names a non-JS workspace ("cargo-workspace",
                     "python-multi-package"), rule 0 returns the root language
                     and ignores nested package.json/tsconfig matches.

Output (JSON on stdout):
  language          — javascript | typescript | rust | python | go
                       | java | kotlin | csharp | ruby | swift | php
                       | unknown
  confidence        — "high" | "medium" | "low"
  detection_source  — human-readable string naming what fired (manifest
                       basename, extension share, etc.)
  fallback_to_extension_frequency — bool (true when rule 10 fired)

Exit codes:
  0 — recommendation produced (even when language is "unknown")
  2 — internal error (bad JSON input, IO failure)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

# Workspace manifest_kind → root language (rule 0). Only non-JS workspace kinds
# appear here: a Cargo/Python workspace root is unambiguously rust/python, and a
# nested package.json+tsconfig (a docs or website subproject) must not win. JS
# workspace kinds (npm-workspaces/pnpm-workspaces/lerna) are intentionally
# absent — their root manifest IS package.json, so rule 1 resolves js/ts
# correctly. generic-folders / null carry no language signal.
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


def detect(payload: dict[str, Any]) -> dict[str, Any]:
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


def _parse_argv(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(
        description="Detect primary language from a flat repo file tree by walking the documented rule table.",
    )
    parser.add_argument("--json", help="JSON payload (alternative to stdin)")
    args = parser.parse_args(argv)
    raw = args.json if args.json is not None else sys.stdin.read()
    if not raw or not raw.strip():
        _die("empty input (expected JSON payload on stdin or via --json)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON input: {e}")
    if not isinstance(payload, dict):
        _die("payload must be a JSON object")
    return payload


def main(argv: list[str]) -> int:
    payload = _parse_argv(argv)
    result = detect(payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
