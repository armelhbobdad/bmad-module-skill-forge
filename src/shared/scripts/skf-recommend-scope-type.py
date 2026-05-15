# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Recommend Scope Type — deterministic 5-rule heuristic ladder.

Single source of truth for the scope-type recommendation logic that
skf-brief-skill step 3 §2c applies. Both the interactive recommendation
and the headless auto-selection paths invoke this script with the same
inputs to eliminate the drift seam between them.

The five-rule ladder (apply in order, first match wins):

  1. component-library — registry.ts / components.ts present (with 10+
     entries or `Component[]` annotation when contents available;
     presence-only when contents not available)
  2. reference-app    — intent text mentions wiring / integration / starter
     / lifecycle / build-config keywords, OR analysis flagged as demo/example
  3. specific-modules — intent names a specific subset ("just the X",
     "only the Y") OR module_count >= 6
  4. public-api       — export_count <= 8 AND intent mentions "the API",
     "the SDK", "client library", "public API"
  5. full-library     — fallback when no rule matches

Plus two short-circuits applied before the ladder:

  - source_type == "docs-only"  → docs-only (no source surface to scope)
  - When mode == "interactive" the component-registry rule additionally
    inspects file contents (10+ entries or Component[] annotation); when
    mode == "headless" with no entry_files supplied, the script falls back
    to file-presence-only matching for that rule.

CLI:
  echo '{...}' | uv run skf-recommend-scope-type.py
  uv run skf-recommend-scope-type.py --json '{...}'

Input (JSON object on stdin or via --json):
  intent          — string (combined intent + scope_hint), default ""
  module_count    — integer (top-level modules from step 2), default 0
  export_count    — integer (named exports from manifest), default 0
  tree            — list of repo-relative file paths, default []
  entry_files     — optional [{path, content}], default null
  source_type     — "source" | "docs-only" | null, default null
  mode            — "interactive" | "headless", default "headless"

Output (JSON on stdout):
  scope_type        — one of full-library | specific-modules | public-api
                      | component-library | reference-app | docs-only
  matched_heuristic — "component-registry" | "reference-app-keywords"
                      | "specific-modules-naming" | "specific-modules-count"
                      | "narrow-public-api" | "default-full-library"
                      | "docs-only-shortcircuit"
  signals           — object naming the signals that fired (path, count, etc.)
  rationale         — one-sentence explanation referencing the signals

Exit codes:
  0 — recommendation produced
  2 — internal error (bad JSON input, IO failure)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

REFERENCE_APP_KEYWORDS = (
    "wiring",
    "integration example",
    "integration sample",
    "starter",
    "lifecycle",
    "build config",
    "build-config",
    "demo app",
    "example app",
    "reference app",
)

NARROW_PUBLIC_API_KEYWORDS = (
    "the api",
    "the sdk",
    "public api",
    "client library",
    "client sdk",
)

# Phrases that indicate the user wants only a specific subset of modules
# rather than the whole library. The match is substring + lowercase, so
# "just the auth module" / "only the streaming part" / "specifically the
# parser" all match.
SPECIFIC_MODULE_NAMING_PATTERNS = (
    re.compile(r"\bjust the\s+\w+", re.IGNORECASE),
    re.compile(r"\bonly the\s+\w+", re.IGNORECASE),
    re.compile(r"\bspecifically the\s+\w+", re.IGNORECASE),
    re.compile(r"\bjust\s+(?:want|need|use)\s+the\s+\w+", re.IGNORECASE),
    re.compile(r"\bonly\s+(?:want|need|use)\s+the\s+\w+", re.IGNORECASE),
    re.compile(r"\bjust\s+\w+\s+module\b", re.IGNORECASE),
    re.compile(r"\bonly\s+\w+\s+module\b", re.IGNORECASE),
)

VALID_MODES = {"interactive", "headless"}
VALID_SOURCE_TYPES = {None, "source", "docs-only"}


def _die(message: str, code: int = 2) -> None:
    sys.stderr.write(f"skf-recommend-scope-type: {message}\n")
    sys.exit(code)


def _find_registry_files(tree: list[str]) -> list[str]:
    """Return repo-relative paths matching registry.ts / components.ts (any depth)."""
    hits: list[str] = []
    for path in tree:
        if not isinstance(path, str):
            continue
        basename = path.rsplit("/", 1)[-1]
        if basename in {"registry.ts", "components.ts", "registry.tsx", "components.tsx"}:
            hits.append(path)
    return hits


def _registry_entry_count(content: str) -> int:
    """Approximate the number of entries in a registry array literal.

    Counts top-level `{ ... }` objects within the first array-like body
    we encounter. Approximate by design — used only as a >=10 threshold.
    """
    # Strip line comments to reduce noise; do not bother with block comments.
    cleaned = re.sub(r"//.*", "", content)
    # Find array literals — match `[` followed by whitespace then `{`.
    array_match = re.search(r"\[\s*\{", cleaned)
    if not array_match:
        return 0
    body_start = array_match.start()
    # Walk forward, count balanced top-level `{` matches up to the closing `]`.
    depth = 0
    in_string: str | None = None
    count = 0
    for ch in cleaned[body_start:]:
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            continue
        if ch == "{":
            if depth == 0:
                count += 1
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
        elif ch == "]" and depth == 0:
            break
    return count


def _has_component_array_annotation(content: str) -> bool:
    """Detect a `Component[]` type annotation, allowing trivial whitespace and generics."""
    return bool(re.search(r"\bComponent(?:\s*<[^>]*>)?\s*\[\s*\]", content))


def _component_registry_match(
    tree: list[str],
    entry_files: list[dict] | None,
    mode: str,
) -> dict | None:
    """Apply rule 1 — component-library.

    Returns a signals dict on match, or None.
    """
    registry_paths = _find_registry_files(tree)
    if not registry_paths:
        return None

    # Index entry-file contents by path for O(1) lookup
    contents: dict[str, str] = {}
    if entry_files:
        for ef in entry_files:
            if not isinstance(ef, dict):
                continue
            path = ef.get("path")
            content = ef.get("content")
            if isinstance(path, str) and isinstance(content, str):
                contents[path] = content

    # When we have contents for any registry file, do the deep check
    for path in registry_paths:
        if path in contents:
            entry_count = _registry_entry_count(contents[path])
            has_annotation = _has_component_array_annotation(contents[path])
            if entry_count >= 10 or has_annotation:
                return {
                    "registry_path": path,
                    "entry_count": entry_count if entry_count >= 10 else None,
                    "component_array_annotation": has_annotation,
                    "contents_inspected": True,
                }
            # File present but neither threshold met — content disqualifies
            continue

    # No contents available for any registry file
    if mode == "headless":
        return {
            "registry_path": registry_paths[0],
            "entry_count": None,
            "component_array_annotation": False,
            "contents_inspected": False,
        }
    # Interactive without contents — fall through; the rule does not match
    return None


def _reference_app_match(intent_lower: str) -> dict | None:
    matches = [kw for kw in REFERENCE_APP_KEYWORDS if kw in intent_lower]
    if matches:
        return {"keywords": matches}
    return None


def _specific_modules_match(intent: str, module_count: int) -> tuple[str, dict] | None:
    naming_hits: list[str] = []
    for pattern in SPECIFIC_MODULE_NAMING_PATTERNS:
        m = pattern.search(intent)
        if m:
            naming_hits.append(m.group(0).strip())
    if naming_hits:
        return ("specific-modules-naming", {"phrases": naming_hits})
    if module_count >= 6:
        return ("specific-modules-count", {"module_count": module_count})
    return None


def _narrow_public_api_match(intent_lower: str, export_count: int) -> dict | None:
    keyword_hits = [kw for kw in NARROW_PUBLIC_API_KEYWORDS if kw in intent_lower]
    if keyword_hits and 0 < export_count <= 8:
        return {"keywords": keyword_hits, "export_count": export_count}
    return None


def recommend(payload: dict) -> dict:
    """Apply the five-rule ladder. Always returns a recommendation."""
    intent = (payload.get("intent") or "").strip()
    intent_lower = intent.lower()
    module_count = int(payload.get("module_count") or 0)
    export_count = int(payload.get("export_count") or 0)
    tree = payload.get("tree") or []
    entry_files = payload.get("entry_files")
    source_type = payload.get("source_type")
    mode = payload.get("mode") or "headless"

    if source_type not in VALID_SOURCE_TYPES:
        _die(f"source_type must be one of {sorted(t for t in VALID_SOURCE_TYPES if t)} or null; got {source_type!r}")
    if mode not in VALID_MODES:
        _die(f"mode must be one of {sorted(VALID_MODES)}; got {mode!r}")

    # Short-circuit: docs-only has no source surface to scope
    if source_type == "docs-only":
        return {
            "scope_type": "docs-only",
            "matched_heuristic": "docs-only-shortcircuit",
            "signals": {"source_type": "docs-only"},
            "rationale": "source_type is docs-only — there is no source surface to scope, so the brief uses the docs-only template.",
        }

    # Rule 1 — component-library
    cr = _component_registry_match(tree, entry_files, mode)
    if cr:
        rationale_bits = [f"a component registry was detected at {cr['registry_path']}"]
        if cr.get("entry_count"):
            rationale_bits.append(f"with {cr['entry_count']} entries")
        if cr.get("component_array_annotation"):
            rationale_bits.append("and a Component[] type annotation")
        if not cr.get("contents_inspected"):
            rationale_bits.append("(presence-only match — file contents not inspected in headless mode)")
        return {
            "scope_type": "component-library",
            "matched_heuristic": "component-registry",
            "signals": cr,
            "rationale": "Component Library because " + " ".join(rationale_bits) + ".",
        }

    # Rule 2 — reference-app
    ra = _reference_app_match(intent_lower)
    if ra:
        kw_str = ", ".join(f"'{k}'" for k in ra["keywords"])
        return {
            "scope_type": "reference-app",
            "matched_heuristic": "reference-app-keywords",
            "signals": ra,
            "rationale": f"Reference App because the intent mentions {kw_str} — language consistent with a wiring-pattern skill rather than a library API.",
        }

    # Rule 3 — specific-modules
    sm = _specific_modules_match(intent, module_count)
    if sm:
        heuristic, signals = sm
        if heuristic == "specific-modules-naming":
            phrases = ", ".join(f"'{p}'" for p in signals["phrases"])
            rationale = f"Specific Modules because the intent names a subset ({phrases})."
        else:
            rationale = f"Specific Modules because the analysis surfaced {signals['module_count']} top-level modules — likely too many for a single cohesive scope."
        return {
            "scope_type": "specific-modules",
            "matched_heuristic": heuristic,
            "signals": signals,
            "rationale": rationale,
        }

    # Rule 4 — narrow public API
    pa = _narrow_public_api_match(intent_lower, export_count)
    if pa:
        kw_str = ", ".join(f"'{k}'" for k in pa["keywords"])
        return {
            "scope_type": "public-api",
            "matched_heuristic": "narrow-public-api",
            "signals": pa,
            "rationale": f"Public API Only because the intent mentions {kw_str} and the manifest exposes {pa['export_count']} named exports — a clear narrow public surface.",
        }

    # Rule 5 — fallback
    return {
        "scope_type": "full-library",
        "matched_heuristic": "default-full-library",
        "signals": {
            "module_count": module_count,
            "export_count": export_count,
        },
        "rationale": "Full Library — no signal matched a narrower scope, so the default is to cover everything.",
    }


def _parse_argv(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(
        description="Recommend a scope type by applying the documented 5-rule heuristic ladder.",
    )
    parser.add_argument(
        "--json",
        help="JSON payload (alternative to stdin)",
    )
    args = parser.parse_args(argv)
    if args.json is not None:
        raw = args.json
    else:
        raw = sys.stdin.read()
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
    result = recommend(payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
