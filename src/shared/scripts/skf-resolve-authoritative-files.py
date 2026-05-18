# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Resolve Authoritative Files — §2a deterministic pre-prompt pipeline.

`skf-create-skill/references/extract.md §2a "Discovered Authoritative Files
Protocol"` performs five deterministic phases before the LLM can prompt the
user on each candidate:

  1. **Heuristic scan** — walk the source tree, find files whose case-
     insensitive basename matches the auth-doc heuristic list (`llms.txt`,
     `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, etc.).
  2. **Scope diff** — for each match, decide whether it is already in
     §2's filtered list (matched by `scope.include` AND not by
     `scope.exclude`) or excluded.
  3. **Amendment reconciliation** — consult `brief.scope.amendments[]`
     for a prior decision on this path.
  4. **Preview load** — for unresolved candidates, read the first 20
     lines and capture line_count + size_bytes for the prompt.
  5. **Content hash** — SHA-256 of the file's bytes (needed for any
     candidate that will populate `promoted_docs[]`).

The prose previously asked the LLM to chain all five per run, with the
SHA-256 hashing and the scope-filter glob matching being the most
drift-prone parts. The helper consolidates them into one `resolve` call.

Subcommand:
  resolve --source-root <path> --brief <brief.yaml-path>
          [--preview-lines 20]

Output JSON (stdout):

  {
    "status": "no-candidates" | "candidates-found",
    "summary": {
      "candidates_total":       N,
      "already_in_scope_count": N,
      "pre_decided_count":      N,
      "unresolved_count":       N
    },
    "already_in_scope": [
      {"path": "...", "heuristic": "llms.txt", "size_bytes": N,
       "line_count": N, "content_hash": "sha256:..."}
    ],
    "pre_decided": [
      {"path": "...", "heuristic": "...", "prior_action": "promoted"|"skipped",
       "should_add_to_promoted_docs": <bool>,
       "size_bytes": N|null, "line_count": N|null,
       "content_hash": "sha256:..." | null}
    ],
    "unresolved": [
      {"path": "...", "heuristic": "...", "size_bytes": N,
       "line_count": N, "content_hash": "sha256:...",
       "preview": "<first N lines as a string>",
       "excluded_by_pattern": "<glob>" | "not matched by any scope.include"}
    ]
  }

Paths are emitted relative to `source-root`, forward-slash form
(cross-platform JSON convention — same as skf-detect-scripts-assets.py).

`pre_decided` semantics:
  - `prior_action="promoted"` AND `should_add_to_promoted_docs=true` →
    the path is in scope but the caller still needs to add it to
    `promoted_docs[]` so step 5 §6 writes the `file_entries[]` row.
    `content_hash` / `size_bytes` / `line_count` are populated.
  - `prior_action="skipped"` → the user previously declined; caller
    does nothing. Hash/size/lines are null (no need to read the file).

Exit codes:
  0  — operation succeeded (any status)
  1  — user error (paths invalid, brief unparseable)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml


# --------------------------------------------------------------------------
# Heuristic list — case-insensitive basename match
# --------------------------------------------------------------------------


AUTH_DOC_BASENAMES = {
    "llms.txt",
    "llms-full.txt",
    "agents.md",
    "claude.md",
    "gemini.md",
    "copilot.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
}


# Path-segment names that mark generated/vendored output trees — same
# exclusion set as skf-detect-scripts-assets.py.
EXCLUDED_DIR_NAMES = {
    "node_modules", "__pycache__", "dist", "build", ".webpack",
    "target", ".next", ".nuxt", "out", "coverage", ".git",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".vscode",
}


# --------------------------------------------------------------------------
# Source-tree walk
# --------------------------------------------------------------------------


def iter_auth_doc_files(source_root: Path) -> Iterable[tuple[Path, str]]:
    """Yield (file_path, matched_heuristic_basename) pairs for every file
    in the source tree whose basename matches an auth-doc heuristic.

    Heuristic matching is case-insensitive on the basename, depth-agnostic.
    Pruned: EXCLUDED_DIR_NAMES at any depth.
    """
    stack: list[Path] = [source_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in EXCLUDED_DIR_NAMES:
                    continue
                stack.append(entry)
            elif entry.is_file():
                heuristic = entry.name.lower()
                if heuristic in AUTH_DOC_BASENAMES:
                    yield entry, heuristic


# --------------------------------------------------------------------------
# Scope filtering — supports `**` recursive globs
# --------------------------------------------------------------------------


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob pattern with `**` support into a compiled regex.

    Semantics (gitignore-compatible enough for brief.scope.include/exclude):
      - `**`        matches zero-or-more path segments (across separators)
      - `*`         matches anything but the path separator
      - `?`         matches any single character but the path separator
      - other chars are escaped literally

    Examples:
      `**/llms.txt`  → matches `llms.txt`, `a/llms.txt`, `a/b/llms.txt`
      `src/**`       → matches `src/anything`, `src/a/b/c`, but NOT bare `src`
      `**/test_*`    → matches `test_x`, `a/test_x`, `a/b/test_x`
    """
    cached = _GLOB_CACHE.get(pattern)
    if cached is not None:
        return cached

    parts = pattern.split("/")
    regex_parts: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == "**":
            # `a/**/b` should match `a/b` (zero segments between) AND
            # `a/x/y/b` (any number). The trick: consume the trailing `/`
            # before `**` if there's one, then emit `(?:.*/)?` for the
            # `**/` case or `.*` at end of pattern.
            if i + 1 < len(parts):
                # `**` followed by more — must allow zero-or-more segments
                regex_parts.append("(?:.*/)?")
                i += 1
                continue
            # `**` at end — match anything (including nothing)
            regex_parts.append(".*")
            i += 1
            continue
        # Translate a single segment (no `**` inside)
        segment = []
        for ch in part:
            if ch == "*":
                segment.append("[^/]*")
            elif ch == "?":
                segment.append("[^/]")
            else:
                segment.append(re.escape(ch))
        regex_parts.append("".join(segment))
        if i + 1 < len(parts):
            regex_parts.append("/")
        i += 1

    regex_str = "^" + "".join(regex_parts) + "$"
    compiled = re.compile(regex_str)
    _GLOB_CACHE[pattern] = compiled
    return compiled


def glob_match(rel_path: str, pattern: str) -> bool:
    return bool(_glob_to_regex(pattern).match(rel_path))


def scope_match(
    rel_path: str, includes: list[str], excludes: list[str]
) -> tuple[bool, str | None]:
    """Return (is_in_scope, excluded_by_pattern).

    is_in_scope is True iff at least one include matches AND no exclude
    matches. excluded_by_pattern is set when the path is OUT of scope:
      - the matching exclude pattern if an exclude rule fires
      - "not matched by any scope.include" if no include matches
      - None when the path IS in scope
    """
    matched_exclude = next(
        (p for p in excludes if glob_match(rel_path, p)), None
    )
    matched_include = any(glob_match(rel_path, p) for p in includes)

    if matched_exclude is not None:
        return False, matched_exclude
    if not matched_include:
        return False, "not matched by any scope.include"
    return True, None


# --------------------------------------------------------------------------
# Brief load
# --------------------------------------------------------------------------


def load_brief(brief_path: Path) -> dict:
    try:
        text = brief_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read brief at {brief_path}: {exc}") from exc
    try:
        brief = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"brief at {brief_path} is not valid YAML: {exc}"
        ) from exc
    if not isinstance(brief, dict):
        raise ValueError(
            f"brief at {brief_path} must be a YAML mapping; got "
            f"{type(brief).__name__}"
        )
    return brief


def extract_scope(brief: dict) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Extract (includes, excludes, amendments_by_path) from the brief.

    amendments_by_path maps each path to a list of actions seen, in the
    order they appear in the brief (so reconcile() can pick most-recent
    by iterating in reverse).
    """
    scope = brief.get("scope") if isinstance(brief.get("scope"), dict) else {}
    includes = scope.get("include") if isinstance(scope.get("include"), list) else []
    excludes = scope.get("exclude") if isinstance(scope.get("exclude"), list) else []
    amendments = scope.get("amendments") if isinstance(scope.get("amendments"), list) else []

    by_path: dict[str, list[str]] = {}
    for amend in amendments:
        if not isinstance(amend, dict):
            continue
        path = amend.get("path")
        action = amend.get("action")
        if isinstance(path, str) and isinstance(action, str):
            by_path.setdefault(path, []).append(action)

    # filter to strings only — schema requires strings but defensively guard
    includes = [p for p in includes if isinstance(p, str)]
    excludes = [p for p in excludes if isinstance(p, str)]
    return includes, excludes, by_path


# --------------------------------------------------------------------------
# File metadata: hash + size + lines + preview
# --------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def count_lines(path: Path) -> int:
    n = 0
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def load_preview(path: Path, *, max_lines: int) -> str:
    """Read up to `max_lines` lines from `path` and return them as a single
    string (newline-joined, no trailing newline). Best-effort UTF-8 decode;
    binary content returns "".
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines: list[str] = []
            for _ in range(max_lines):
                line = fh.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
        return "\n".join(lines)
    except OSError:
        return ""


# --------------------------------------------------------------------------
# Resolve
# --------------------------------------------------------------------------


_PROMOTED = "promoted"
_SKIPPED = "skipped"


def _latest_action(actions: list[str]) -> str | None:
    """Most-recent matching amendment wins. Returns 'promoted', 'skipped',
    or None if no recognized action was seen."""
    for action in reversed(actions):
        if action in (_PROMOTED, _SKIPPED):
            return action
    return None


def resolve(
    source_root: Path,
    brief_path: Path,
    *,
    preview_lines: int = 20,
) -> dict:
    """Run the §2a deterministic pipeline. See module docstring for output shape."""
    brief = load_brief(brief_path)
    includes, excludes, amendments_by_path = extract_scope(brief)

    already_in_scope: list[dict] = []
    pre_decided: list[dict] = []
    unresolved: list[dict] = []

    for file_path, heuristic in iter_auth_doc_files(source_root):
        rel = file_path.relative_to(source_root).as_posix()
        in_scope, excluded_by = scope_match(rel, includes, excludes)
        prior_action = _latest_action(amendments_by_path.get(rel, []))

        if in_scope and prior_action != _SKIPPED:
            # Already in scope — remove from §2 filtered list and add to
            # promoted_docs[]. Includes the "user manually added to
            # scope.include" case AND the "amendments has promoted" case
            # (which is the deterministic replay path).
            already_in_scope.append({
                "path": rel,
                "heuristic": heuristic,
                "size_bytes": file_path.stat().st_size,
                "line_count": count_lines(file_path),
                "content_hash": sha256_of_file(file_path),
            })
            continue

        if prior_action == _PROMOTED:
            # Amendment says promoted but scope.include doesn't currently
            # match — unusual (brief was edited?) — still populate
            # promoted_docs[] per the deterministic replay rule.
            pre_decided.append({
                "path": rel,
                "heuristic": heuristic,
                "prior_action": _PROMOTED,
                "should_add_to_promoted_docs": True,
                "size_bytes": file_path.stat().st_size,
                "line_count": count_lines(file_path),
                "content_hash": sha256_of_file(file_path),
            })
            continue

        if prior_action == _SKIPPED:
            pre_decided.append({
                "path": rel,
                "heuristic": heuristic,
                "prior_action": _SKIPPED,
                "should_add_to_promoted_docs": False,
                "size_bytes": None,
                "line_count": None,
                "content_hash": None,
            })
            continue

        # No prior amendment and out of scope → unresolved
        unresolved.append({
            "path": rel,
            "heuristic": heuristic,
            "size_bytes": file_path.stat().st_size,
            "line_count": count_lines(file_path),
            "content_hash": sha256_of_file(file_path),
            "preview": load_preview(file_path, max_lines=preview_lines),
            "excluded_by_pattern": excluded_by,
        })

    # Deterministic ordering for stable diffs / cache keys
    already_in_scope.sort(key=lambda r: r["path"])
    pre_decided.sort(key=lambda r: r["path"])
    unresolved.sort(key=lambda r: r["path"])

    candidates_total = (
        len(already_in_scope) + len(pre_decided) + len(unresolved)
    )
    return {
        "status": "candidates-found" if candidates_total > 0 else "no-candidates",
        "summary": {
            "candidates_total": candidates_total,
            "already_in_scope_count": len(already_in_scope),
            "pre_decided_count": len(pre_decided),
            "unresolved_count": len(unresolved),
        },
        "already_in_scope": already_in_scope,
        "pre_decided": pre_decided,
        "unresolved": unresolved,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_resolve(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(
            f"error: source-root not a directory: {source_root}", file=sys.stderr
        )
        return 1
    brief_path = Path(args.brief)
    if not brief_path.is_file():
        print(f"error: brief not found: {brief_path}", file=sys.stderr)
        return 1
    if args.preview_lines < 1:
        print("error: --preview-lines must be >= 1", file=sys.stderr)
        return 1
    try:
        result = resolve(source_root, brief_path, preview_lines=args.preview_lines)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-resolve-authoritative-files",
        description=(
            "Scan a source tree for authoritative AI documentation files, "
            "classify each against scope filters + amendments, emit "
            "already-in-scope / pre-decided / unresolved buckets."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("resolve", help="run the §2a pipeline")
    p.add_argument("--source-root", required=True, help="path to the source tree")
    p.add_argument("--brief", required=True, help="path to skill-brief.yaml")
    p.add_argument(
        "--preview-lines",
        type=int,
        default=20,
        help="number of lines to capture for the prompt preview (default: 20)",
    )
    p.set_defaults(func=_cmd_resolve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
